#!/usr/bin/env python3
"""Two-dimensional time-coarsening x capacity Gate for NYC ordered latent runs.

The Gate holds selected-buffer support fixed at 4.0 rows/core, then bounds the
same root-invariant public attributes under both exact-second and artificial
15-minute outer public-time models for C in {2,3,4}.  Because the estimand is
common, feasible sets must be nested along both dimensions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import live_nyc_hvfhv_ordered_common_support as common
import live_nyc_hvfhv_ordered_run_smoke as base

TIME_MODELS = ("exact_second", "rounded_15m_outer")
REFERENCE_SUPPORT_PER_CORE = 4.0
TOL = 1e-7


def outcome_map(cell: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["query"]: row for row in cell.get("outcomes", [])}


def audit_coarsening(cells_by_time: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    comparisons = 0
    exact = {int(cell["capacity"]): cell for cell in cells_by_time["exact_second"]}
    coarse = {int(cell["capacity"]): cell for cell in cells_by_time["rounded_15m_outer"]}
    for capacity in base.CAPACITIES:
        e = outcome_map(exact[capacity])
        c = outcome_map(coarse[capacity])
        for query in (
            "mean_selected_buffer_miles_at_common_support",
            "mean_selected_buffer_trip_minutes_at_common_support",
        ):
            erow = e.get(query)
            crow = c.get(query)
            if (
                erow is None
                or crow is None
                or erow.get("status") != "CERTIFIED_OPTIMAL_PAIR"
                or crow.get("status") != "CERTIFIED_OPTIMAL_PAIR"
            ):
                continue
            comparisons += 1
            if crow["lower"] > erow["lower"] + TOL:
                problems.append(
                    {
                        "capacity": capacity,
                        "query": query,
                        "reason": "coarse_lower_exceeds_exact_lower",
                        "exact": erow["lower"],
                        "coarse": crow["lower"],
                    }
                )
            if crow["upper"] < erow["upper"] - TOL:
                problems.append(
                    {
                        "capacity": capacity,
                        "query": query,
                        "reason": "coarse_upper_below_exact_upper",
                        "exact": erow["upper"],
                        "coarse": crow["upper"],
                    }
                )
    return {
        "status": "PASS" if comparisons and not problems else "FAIL",
        "comparisons": comparisons,
        "problems": problems,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError("dataset metadata/schema changed during extraction")
    determinate_after, _, _ = base.count(selected["where"]["determinate"])
    indeterminate_after, _, _ = base.count(selected["where"]["indeterminate"])
    if determinate_after != selected["determinate_count"] or indeterminate_after != selected["indeterminate_count"]:
        raise base.LiveDataError("candidate server counts changed during extraction")

    trips, row_audit = base.parse_trips(
        selected["candidate_rows"],
        selected["provider"],
        selected["core_start"],
        selected["core_end"],
    )

    cells_by_time: dict[str, list[dict[str, Any]]] = {}
    candidate_rows_by_time: dict[str, int] = {}
    for time_model in TIME_MODELS:
        ordered = base.ordered_subcohort(base.model_rows(trips, time_model), args.ordered_core)
        candidate_rows_by_time[time_model] = len(ordered)
        cells_by_time[time_model] = [
            common.solve_common_cell(
                ordered,
                capacity,
                REFERENCE_SUPPORT_PER_CORE,
                args.solver_time_limit,
            )
            for capacity in base.CAPACITIES
        ]

    capacity_audits = {
        time_model: common.audit_nestedness(cells)
        for time_model, cells in cells_by_time.items()
    }
    coarsening_audit = audit_coarsening(cells_by_time)

    # Fail closed only on a certified monotonicity contradiction. If an endpoint
    # is unresolved, the relevant audit simply has fewer comparisons and the
    # report records that status rather than treating it as evidence.
    for time_model, audit in capacity_audits.items():
        if audit["problems"]:
            raise base.LiveDataError(f"capacity nestedness failed for {time_model}: {audit}")
    if coarsening_audit["problems"]:
        raise base.LiveDataError(f"coarsening nestedness failed: {coarsening_audit}")

    return {
        "report_version": "nyc-hvfhv-ordered-outcomes/v3-time-capacity-lattice",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "core_start": selected["core_start"].isoformat(),
            "core_end": selected["core_end"].isoformat(),
            "source_core_rows": row_audit["core_rows"],
            "source_candidate_rows": row_audit["rows"],
            "ordered_core_rows": args.ordered_core,
            "ordered_candidate_rows_by_time": candidate_rows_by_time,
        },
        "reference_support": {
            "buffer_rows_per_core": REFERENCE_SUPPORT_PER_CORE,
            "buffer_rows": REFERENCE_SUPPORT_PER_CORE * args.ordered_core,
            "definition": "predeclared common support, fixed before outcome optimization and shared across both public-time models and C=2,3,4",
        },
        "cells_by_time": cells_by_time,
        "capacity_audits": capacity_audits,
        "coarsening_audit": coarsening_audit,
        "estimand": "mean public attribute among exactly 4 selected buffer rows/core under a common ordered-run support target",
        "claim_boundary": {
            "supported": "root-invariant two-dimensional time-coarsening/capacity feasible-world bounds where endpoints are certified",
            "not_supported": "actual co-rider composition, realized vehicle run, true capacity, TLC production matching logic, or an actual 15-minute TLC release operator",
        },
    }


def render(report: dict[str, Any]) -> str:
    ref = report["reference_support"]
    lines = [
        "# NYC HVFHV ordered-run time-capacity lattice",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Ordered core: **{report['cohort']['ordered_core_rows']}**.  ",
        f"Common selected-buffer support: **{ref['buffer_rows']:.0f} rows** (**{ref['buffer_rows_per_core']:.1f}/core**).",
        "",
        "| Time model | C | Outcome | Lower | Upper | Width | Status |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for time_model in TIME_MODELS:
        for cell in report["cells_by_time"][time_model]:
            if not cell.get("outcomes"):
                lines.append(
                    f"| {time_model} | {cell['capacity']} | — | — | — | — | `{cell['status']}` |"
                )
                continue
            for row in cell["outcomes"]:
                lo = "—" if row.get("lower") is None else f"{row['lower']:.4f}"
                hi = "—" if row.get("upper") is None else f"{row['upper']:.4f}"
                width = "—" if row.get("width") is None else f"{row['width']:.4f}"
                lines.append(
                    f"| {time_model} | {cell['capacity']} | {row['query']} | {lo} | {hi} | {width} | `{row['status']}` |"
                )
    lines.extend(
        [
            "",
            "Capacity audits: "
            + ", ".join(
                f"`{tm}={report['capacity_audits'][tm]['status']}`"
                for tm in TIME_MODELS
            )
            + ".",
            f"Coarsening audit: `{report['coarsening_audit']['status']}` over **{report['coarsening_audit']['comparisons']}** certified comparisons.",
            "",
            "Only certified endpoint pairs support identification claims. Unresolved cells remain unpublished evidence, not negative results.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: dict[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for time_model in TIME_MODELS:
        for cell in report["cells_by_time"][time_model]:
            if not cell.get("outcomes"):
                rows.append(
                    {
                        "time_model": time_model,
                        "capacity": cell["capacity"],
                        "cell_status": cell["status"],
                        "query": None,
                    }
                )
                continue
            for row in cell["outcomes"]:
                rows.append(
                    {
                        "time_model": time_model,
                        "capacity": cell["capacity"],
                        "cell_status": cell["status"],
                        "common_buffer_rows_per_core": cell["common_buffer_rows_per_core"],
                        "common_buffer_rows": cell["common_buffer_rows"],
                        **row,
                    }
                )
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    rows = base.synthetic_chain()
    c2 = common.solve_common_cell(rows, 2, 0.5, 10.0)
    c3 = common.solve_common_cell(rows, 3, 0.5, 10.0)
    c4 = common.solve_common_cell(rows, 4, 0.5, 10.0)
    cells = [c2, c3, c4]
    assert common.audit_nestedness(cells)["status"] == "PASS"
    lattice = {"exact_second": cells, "rounded_15m_outer": cells}
    assert audit_coarsening(lattice)["status"] == "PASS"
    print("NYC ordered-run time-capacity lattice self-test: PASS")


def parser() -> argparse.ArgumentParser:
    return base.parser()


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    base.validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    write_csv(report, args.output_dir / "time_capacity_lattice.csv")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
