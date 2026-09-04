#!/usr/bin/env python3
"""Common-support outcome bounds for the NYC ordered latent-run model.

The max-support outcome Gate conditions on a different selected-buffer count for
each declared capacity C.  This stage removes that moving-conditioning effect.
It first certifies the maximum selected-buffer count under C=2 and fixes that
same cardinality for C in {2,3,4}.  Because the ordered-run feasible sets are
nested in C and the support cardinality is now common, the public-attribute
identified intervals must be nested as well: lower endpoints cannot rise and
upper endpoints cannot fall as C increases.

The stage uses the certified 15-minute outer public-time model.  It is a
conditional feasible-world comparison, not an estimate of realized capacity,
co-riders, or production matching logic.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import live_nyc_hvfhv_ordered_outcomes as outcome
import live_nyc_hvfhv_ordered_run_smoke as base

TIME_MODEL = outcome.TIME_MODEL
TOL = 1e-7


def solve_common_cell(rows, capacity: int, common_per_core: float, time_limit: float) -> dict[str, Any]:
    core_count = sum(row.role == "core" for row in rows)
    output: list[dict[str, Any]] = []

    # First certify that the common cardinality itself is feasible for this C.
    feasibility_program = outcome.canonical_program(rows, capacity)
    count = base.objective(feasibility_program, "selected_buffer_rows_per_core")
    outcome.append_equality(feasibility_program, count, common_per_core)
    feasibility = base.solve(
        feasibility_program,
        np.zeros(feasibility_program.matrix.shape[1], dtype=float),
        False,
        time_limit,
    )
    if feasibility["status"] != base.CERTIFIED:
        return {
            "capacity": capacity,
            "status": "UNRESOLVED_COMMON_SUPPORT_FEASIBILITY",
            "common_buffer_rows_per_core": common_per_core,
            "common_buffer_rows": common_per_core * core_count,
            "feasibility_status": feasibility["status"],
            "feasibility_mip_gap": feasibility["mip_gap"],
            "outcomes": [],
        }

    for query, attribute, scale, unit in (
        ("mean_selected_buffer_miles_at_common_support", "miles", 1.0, "miles"),
        ("mean_selected_buffer_trip_minutes_at_common_support", "seconds", 60.0, "minutes"),
    ):
        program = outcome.canonical_program(rows, capacity)
        count = base.objective(program, "selected_buffer_rows_per_core")
        outcome.append_equality(program, count, common_per_core)
        attr_coeff, missing = outcome.buffer_attribute_objective(program, attribute, scale)
        if missing:
            output.append(
                {
                    "query": query,
                    "unit": unit,
                    "lower": None,
                    "upper": None,
                    "width": None,
                    "status": "UNRESOLVED_MISSING_PUBLIC_VALUES",
                    "missing_buffer_rows": len(missing),
                }
            )
            continue
        lo = base.solve(program, attr_coeff, False, time_limit)
        hi = base.solve(program, attr_coeff, True, time_limit)
        if lo["status"] != base.CERTIFIED or hi["status"] != base.CERTIFIED:
            output.append(
                {
                    "query": query,
                    "unit": unit,
                    "lower": None,
                    "upper": None,
                    "width": None,
                    "status": "UNRESOLVED_ENDPOINT_PAIR",
                    "lower_status": lo["status"],
                    "upper_status": hi["status"],
                    "lower_mip_gap": lo["mip_gap"],
                    "upper_mip_gap": hi["mip_gap"],
                }
            )
            continue
        lower_mean = float(lo["value"]) / common_per_core
        upper_mean = float(hi["value"]) / common_per_core
        output.append(
            {
                "query": query,
                "unit": unit,
                "lower": lower_mean,
                "upper": upper_mean,
                "width": upper_mean - lower_mean,
                "status": "CERTIFIED_OPTIMAL_PAIR",
                "lower_mip_gap": lo["mip_gap"],
                "upper_mip_gap": hi["mip_gap"],
            }
        )

    return {
        "capacity": capacity,
        "status": "CERTIFIED_COMMON_SUPPORT_FEASIBILITY",
        "common_buffer_rows_per_core": common_per_core,
        "common_buffer_rows": common_per_core * core_count,
        "feasibility_status": feasibility["status"],
        "feasibility_mip_gap": feasibility["mip_gap"],
        "outcomes": output,
    }


def audit_nestedness(cells: list[dict[str, Any]]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    comparisons = 0
    by_capacity = {int(cell["capacity"]): cell for cell in cells}
    queries = (
        "mean_selected_buffer_miles_at_common_support",
        "mean_selected_buffer_trip_minutes_at_common_support",
    )
    for query in queries:
        previous = None
        for capacity in base.CAPACITIES:
            cell = by_capacity[capacity]
            match = next((row for row in cell["outcomes"] if row["query"] == query), None)
            if match is None or match["status"] != "CERTIFIED_OPTIMAL_PAIR":
                previous = None
                continue
            if previous is not None:
                comparisons += 1
                if match["lower"] > previous["lower"] + TOL:
                    problems.append(
                        {
                            "query": query,
                            "capacity": capacity,
                            "reason": "lower_increased_with_capacity",
                            "previous": previous["lower"],
                            "current": match["lower"],
                        }
                    )
                if match["upper"] < previous["upper"] - TOL:
                    problems.append(
                        {
                            "query": query,
                            "capacity": capacity,
                            "reason": "upper_decreased_with_capacity",
                            "previous": previous["upper"],
                            "current": match["upper"],
                        }
                    )
            previous = match
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
    ordered = base.ordered_subcohort(base.model_rows(trips, TIME_MODEL), args.ordered_core)

    c2_program = outcome.canonical_program(ordered, 2)
    count_coeff = base.objective(c2_program, "selected_buffer_rows_per_core")
    c2_max = base.solve(c2_program, count_coeff, True, args.solver_time_limit)
    if c2_max["status"] != base.CERTIFIED or c2_max["value"] is None or c2_max["value"] <= 0:
        raise base.LiveDataError(
            f"C=2 common-support anchor unresolved: {c2_max['status']}"
        )
    common_per_core = float(c2_max["value"])
    cells = [
        solve_common_cell(ordered, capacity, common_per_core, args.solver_time_limit)
        for capacity in base.CAPACITIES
    ]
    nestedness = audit_nestedness(cells)
    if nestedness["status"] != "PASS":
        raise base.LiveDataError(f"common-support nestedness audit failed: {nestedness}")

    return {
        "report_version": "nyc-hvfhv-ordered-outcomes/v2-common-support",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "core_start": selected["core_start"].isoformat(),
            "core_end": selected["core_end"].isoformat(),
            "source_core_rows": row_audit["core_rows"],
            "source_candidate_rows": row_audit["rows"],
            "ordered_core_rows": args.ordered_core,
            "ordered_candidate_rows": len(ordered),
            "time_model": TIME_MODEL,
        },
        "common_support": {
            "definition": "certified maximum selected-buffer cardinality under C=2, held fixed for C=2,3,4",
            "buffer_rows_per_core": common_per_core,
            "buffer_rows": common_per_core * args.ordered_core,
            "c2_max_status": c2_max["status"],
            "c2_max_mip_gap": c2_max["mip_gap"],
        },
        "cells": cells,
        "nestedness_audit": nestedness,
        "estimand": "mean public attribute among selected buffer rows at one common fixed selected-buffer cardinality across declared C",
        "claim_boundary": {
            "supported": "root-invariant common-support outcome composition bounds under the declared coarse public-time model",
            "not_supported": "actual co-rider composition, realized vehicle run, true capacity, or production matching logic",
        },
    }


def render(report: dict[str, Any]) -> str:
    common = report["common_support"]
    lines = [
        "# NYC HVFHV ordered-run common-support outcome bounds",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Time model: `{report['cohort']['time_model']}`  ",
        f"Ordered core: **{report['cohort']['ordered_core_rows']}**; candidate rows: **{report['cohort']['ordered_candidate_rows']}**.",
        "",
        f"Common selected-buffer cardinality: **{common['buffer_rows']:.0f} rows** "
        f"(**{common['buffer_rows_per_core']:.4f}/core**), defined by the certified C=2 maximum and then held fixed for C=2,3,4.",
        "",
        "| C | Outcome | Lower | Upper | Width | Status |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for cell in report["cells"]:
        for row in cell["outcomes"]:
            lo = "—" if row["lower"] is None else f"{row['lower']:.4f}"
            hi = "—" if row["upper"] is None else f"{row['upper']:.4f}"
            width = "—" if row["width"] is None else f"{row['width']:.4f}"
            lines.append(
                f"| {cell['capacity']} | {row['query']} | {lo} | {hi} | {width} | `{row['status']}` |"
            )
    lines.extend(
        [
            "",
            f"Capacity nestedness audit: `{report['nestedness_audit']['status']}` over "
            f"**{report['nestedness_audit']['comparisons']}** certified adjacent-capacity comparisons.",
            "",
            "With support cardinality fixed, capacity is now a pure feasible-set relaxation; lower endpoints must weakly fall and upper endpoints weakly rise. This is the clean comparison that the C-specific max-support Gate could not provide.",
            "",
            "These are conditional feasible-world bounds, not recovered NYC co-riders or realized pooling composition.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: dict[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for cell in report["cells"]:
        for row in cell["outcomes"]:
            rows.append(
                {
                    "capacity": cell["capacity"],
                    "common_buffer_rows_per_core": cell["common_buffer_rows_per_core"],
                    "common_buffer_rows": cell["common_buffer_rows"],
                    **row,
                }
            )
    fields = sorted({key for row in rows for key in row}) if rows else ["capacity"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    rows = base.synthetic_chain()
    c2 = outcome.canonical_program(rows, 2)
    count = base.objective(c2, "selected_buffer_rows_per_core")
    maximum = base.solve(c2, count, True, 10.0)
    assert maximum["status"] == base.CERTIFIED
    common = float(maximum["value"])
    cells = [solve_common_cell(rows, c, common, 10.0) for c in base.CAPACITIES]
    assert all(cell["status"] == "CERTIFIED_COMMON_SUPPORT_FEASIBILITY" for cell in cells)
    nestedness = audit_nestedness(cells)
    assert nestedness["status"] == "PASS", nestedness
    print("NYC ordered-run common-support self-test: PASS")


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
    write_csv(report, args.output_dir / "common_support_outcomes.csv")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
