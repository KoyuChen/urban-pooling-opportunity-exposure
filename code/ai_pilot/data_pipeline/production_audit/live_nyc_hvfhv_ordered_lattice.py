#!/usr/bin/env python3
"""Deterministic time-model x capacity sensitivity for NYC ordered latent runs.

The analysis holds selected-buffer support fixed at 4.0 rows/core and bounds
the same root-invariant public attributes under exact released seconds and an
artificial nearest-15-minute outer-envelope model for C in {2,3,4}.

Capacity is a nested relaxation *within either fixed time model*.  The two time
models are not assumed to be nested.  Replacing each realized interval by its
outer envelope has two opposing effects: it creates additional overlap bridges
but can also create artificial simultaneous occupancy and thereby tighten a
capacity constraint.  Consequently the outer-envelope model is a deterministic
robust sensitivity model, not the existential latent-time completion required
for a monotone release-coarsening identified set.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import live_nyc_hvfhv_ordered_common_support as common
import live_nyc_hvfhv_ordered_run_smoke as base

TIME_MODELS = ("exact_second", "rounded_15m_outer")
REFERENCE_SUPPORT_PER_CORE = 4.0
TOL = 1e-7


def outcome_map(cell: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["query"]: row for row in cell.get("outcomes", [])}


def compare_time_models(
    cells_by_time: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Compare certified endpoint pairs without asserting feasible-set nesting."""

    comparisons: list[dict[str, Any]] = []
    relation_counts: Counter[str] = Counter()
    exact = {
        int(cell["capacity"]): cell
        for cell in cells_by_time["exact_second"]
    }
    coarse = {
        int(cell["capacity"]): cell
        for cell in cells_by_time["rounded_15m_outer"]
    }
    for capacity in base.CAPACITIES:
        exact_outcomes = outcome_map(exact[capacity])
        coarse_outcomes = outcome_map(coarse[capacity])
        for query in (
            "mean_selected_buffer_miles_at_common_support",
            "mean_selected_buffer_trip_minutes_at_common_support",
        ):
            exact_row = exact_outcomes.get(query)
            coarse_row = coarse_outcomes.get(query)
            if (
                exact_row is None
                or coarse_row is None
                or exact_row.get("status") != "CERTIFIED_OPTIMAL_PAIR"
                or coarse_row.get("status") != "CERTIFIED_OPTIMAL_PAIR"
            ):
                continue
            coarse_contains_exact = (
                coarse_row["lower"] <= exact_row["lower"] + TOL
                and coarse_row["upper"] >= exact_row["upper"] - TOL
            )
            exact_contains_coarse = (
                exact_row["lower"] <= coarse_row["lower"] + TOL
                and exact_row["upper"] >= coarse_row["upper"] - TOL
            )
            if coarse_contains_exact and exact_contains_coarse:
                relation = "ENDPOINTS_EQUAL_WITHIN_TOLERANCE"
            elif coarse_contains_exact:
                relation = "COARSE_ENDPOINT_INTERVAL_CONTAINS_EXACT"
            elif exact_contains_coarse:
                relation = "EXACT_ENDPOINT_INTERVAL_CONTAINS_COARSE"
            else:
                relation = "ENDPOINT_INTERVALS_CROSS_OR_ARE_DISJOINT"
            relation_counts[relation] += 1
            comparisons.append(
                {
                    "capacity": capacity,
                    "query": query,
                    "exact_lower": exact_row["lower"],
                    "exact_upper": exact_row["upper"],
                    "exact_width": exact_row["width"],
                    "outer_lower": coarse_row["lower"],
                    "outer_upper": coarse_row["upper"],
                    "outer_width": coarse_row["width"],
                    "lower_delta_outer_minus_exact": (
                        coarse_row["lower"] - exact_row["lower"]
                    ),
                    "upper_delta_outer_minus_exact": (
                        coarse_row["upper"] - exact_row["upper"]
                    ),
                    "width_delta_outer_minus_exact": (
                        coarse_row["width"] - exact_row["width"]
                    ),
                    "endpoint_relation": relation,
                }
            )
    return {
        "status": (
            "DIAGNOSTIC_COMPLETE"
            if comparisons
            else "NO_CERTIFIED_CROSS_TIME_COMPARISONS"
        ),
        "comparison_count": len(comparisons),
        "relation_counts": dict(relation_counts),
        "comparisons": comparisons,
        "outer_endpoint_containment_holds_for_all_certified_cells": bool(
            comparisons
        )
        and all(
            row["endpoint_relation"]
            in {
                "ENDPOINTS_EQUAL_WITHIN_TOLERANCE",
                "COARSE_ENDPOINT_INTERVAL_CONTAINS_EXACT",
            }
            for row in comparisons
        ),
        "feasible_set_nesting_claimed": False,
    }


def max_depth(intervals: Sequence[tuple[float, float]]) -> int:
    endpoints = sorted({value for interval in intervals for value in interval})
    if len(endpoints) < 2:
        return 0
    depth = 0
    for left, right in zip(endpoints, endpoints[1:]):
        midpoint = (left + right) / 2.0
        depth = max(
            depth,
            sum(start <= midpoint < end for start, end in intervals),
        )
    return depth


def outer_envelope_counterexample() -> dict[str, Any]:
    """A connected C=2 chain whose expanded envelopes have depth three."""

    exact = ((0.0, 2.0), (1.0, 3.0), (2.0, 4.0))
    outer = ((-1.0, 3.0), (0.0, 4.0), (1.0, 5.0))
    exact_depth = max_depth(exact)
    outer_depth = max_depth(outer)
    return {
        "exact_intervals": exact,
        "outer_envelopes": outer,
        "capacity": 2,
        "exact_max_depth": exact_depth,
        "outer_max_depth": outer_depth,
        "exact_chain_capacity_feasible": exact_depth <= 2,
        "outer_envelope_capacity_feasible": outer_depth <= 2,
        "lesson": (
            "occupancy on outer envelopes is a universal/robust screen and can "
            "exclude a release-consistent exact completion"
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError(
            "dataset metadata/schema changed during extraction"
        )
    determinate_after, _, _ = base.count(selected["where"]["determinate"])
    indeterminate_after, _, _ = base.count(selected["where"]["indeterminate"])
    if (
        determinate_after != selected["determinate_count"]
        or indeterminate_after != selected["indeterminate_count"]
    ):
        raise base.LiveDataError(
            "candidate server counts changed during extraction"
        )

    trips, row_audit = base.parse_trips(
        selected["candidate_rows"],
        selected["provider"],
        selected["core_start"],
        selected["core_end"],
    )

    cells_by_time: dict[str, list[dict[str, Any]]] = {}
    candidate_rows_by_time: dict[str, int] = {}
    for time_model in TIME_MODELS:
        ordered = base.ordered_subcohort(
            base.model_rows(trips, time_model),
            args.ordered_core,
        )
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
    for time_model, audit in capacity_audits.items():
        if audit["problems"]:
            raise base.LiveDataError(
                f"capacity nestedness failed for {time_model}: {audit}"
            )

    time_model_comparison = compare_time_models(cells_by_time)
    counterexample = outer_envelope_counterexample()
    if not counterexample["exact_chain_capacity_feasible"]:
        raise AssertionError("counterexample exact chain must be C=2 feasible")
    if counterexample["outer_envelope_capacity_feasible"]:
        raise AssertionError("counterexample envelopes must violate C=2")

    return {
        "report_version": (
            "nyc-hvfhv-ordered-outcomes/v4-deterministic-time-model-sensitivity"
        ),
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
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
            "definition": (
                "predeclared common support, fixed before outcome optimization "
                "and shared across both deterministic time models and C=2,3,4"
            ),
        },
        "cells_by_time": cells_by_time,
        "capacity_audits": capacity_audits,
        "time_model_comparison": time_model_comparison,
        "outer_envelope_counterexample": counterexample,
        "time_semantics": {
            "exact_second": "released public intervals as written",
            "rounded_15m_outer": (
                "each nearest-15-minute outer envelope is treated as the active "
                "interval for both connectivity and occupancy"
            ),
            "correct_monotone_release_world": (
                "select latent exact endpoints inside each released support, then "
                "impose connectivity and capacity on that selected completion"
            ),
            "quantifier_warning": (
                "existence of one feasible latent-time completion is not equivalent "
                "to requiring the outer envelopes themselves to satisfy capacity"
            ),
        },
        "estimand": (
            "mean public attribute among exactly 4 selected buffer rows/core under "
            "a common ordered-run support target"
        ),
        "claim_boundary": {
            "supported": (
                "within-time capacity frontiers and a cross-time deterministic "
                "model-sensitivity diagnostic where endpoint pairs are certified"
            ),
            "not_supported": (
                "cross-time feasible-set nesting, existential latent-time partial "
                "identification, actual co-rider composition, realized vehicle run, "
                "true capacity, TLC production matching logic, or an actual TLC "
                "15-minute release operator"
            ),
        },
    }


def render(report: dict[str, Any]) -> str:
    reference = report["reference_support"]
    lines = [
        "# NYC HVFHV ordered-run deterministic time-model sensitivity",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Ordered core: **{report['cohort']['ordered_core_rows']}**.  ",
        "Common selected-buffer support: "
        f"**{reference['buffer_rows']:.0f} rows** "
        f"(**{reference['buffer_rows_per_core']:.1f}/core**).",
        "",
        "| Time model | C | Outcome | Lower | Upper | Width | Status |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for time_model in TIME_MODELS:
        for cell in report["cells_by_time"][time_model]:
            if not cell.get("outcomes"):
                lines.append(
                    f"| {time_model} | {cell['capacity']} | — | — | — | — | "
                    f"`{cell['status']}` |"
                )
                continue
            for row in cell["outcomes"]:
                lower = (
                    "—" if row.get("lower") is None else f"{row['lower']:.4f}"
                )
                upper = (
                    "—" if row.get("upper") is None else f"{row['upper']:.4f}"
                )
                width = (
                    "—" if row.get("width") is None else f"{row['width']:.4f}"
                )
                lines.append(
                    f"| {time_model} | {cell['capacity']} | {row['query']} | "
                    f"{lower} | {upper} | {width} | `{row['status']}` |"
                )
    comparison = report["time_model_comparison"]
    lines.extend(
        [
            "",
            "Capacity audits: "
            + ", ".join(
                f"`{time_model}="
                f"{report['capacity_audits'][time_model]['status']}`"
                for time_model in TIME_MODELS
            )
            + ".",
            "Cross-time diagnostic: "
            f"`{comparison['status']}` over "
            f"**{comparison['comparison_count']}** certified endpoint pairs.",
            "",
            "The exact and outer-envelope models are not required to be nested. "
            "Outer expansion adds overlap bridges but can create artificial "
            "simultaneous occupancy, so it may remove capacity-feasible exact worlds.",
            "",
        ]
    )
    for row in comparison["comparisons"]:
        lines.append(
            "- "
            f"C={row['capacity']}, `{row['query']}`: "
            f"`{row['endpoint_relation']}`; "
            f"lower delta={row['lower_delta_outer_minus_exact']:.6f}, "
            f"upper delta={row['upper_delta_outer_minus_exact']:.6f}."
        )
    lines.extend(
        [
            "",
            "For a monotone release-coarsening identified set, latent exact "
            "timestamps must be selected inside the released supports and capacity "
            "must be imposed on that selected completion. The present outer-envelope "
            "comparison is only a deterministic robustness diagnostic.",
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
                        "common_buffer_rows_per_core": cell[
                            "common_buffer_rows_per_core"
                        ],
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
    cells = [
        common.solve_common_cell(rows, capacity, 0.5, 10.0)
        for capacity in base.CAPACITIES
    ]
    assert common.audit_nestedness(cells)["status"] == "PASS"
    identical = {
        "exact_second": cells,
        "rounded_15m_outer": cells,
    }
    comparison = compare_time_models(identical)
    assert comparison["status"] == "DIAGNOSTIC_COMPLETE"
    assert comparison[
        "outer_endpoint_containment_holds_for_all_certified_cells"
    ]
    counterexample = outer_envelope_counterexample()
    assert counterexample["exact_chain_capacity_feasible"]
    assert not counterexample["outer_envelope_capacity_feasible"]
    print("NYC ordered-run deterministic time-model sensitivity self-test: PASS")


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
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        render(report),
        encoding="utf-8",
    )
    write_csv(report, args.output_dir / "time_capacity_lattice.csv")
    (args.output_dir / "time_model_comparison.json").write_text(
        json.dumps(
            report["time_model_comparison"],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
