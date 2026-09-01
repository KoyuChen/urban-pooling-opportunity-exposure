#!/usr/bin/env python3
"""Canonical-root live runner for the NYC ordered-run frontier.

This runner adds two exact refinements on top of the compact interval-segment
formulation:

1. minimum-core canonical roots remove label symmetry without changing the set
   of physical run partitions;
2. the peak simultaneous core occupancy is recorded as an analytic lower-bound
   certificate for the minimum number of runs under each declared capacity C.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import live_nyc_hvfhv_ordered_run_smoke as base
import nyc_ordered_run_symmetry as symmetry

RAW_BUILD_PROGRAM = base.build_program


def canonical_build_program(rows, capacity):
    return symmetry.canonicalize_program(RAW_BUILD_PROGRAM(rows, capacity))


# base.solve_frontier resolves build_program dynamically in the module global.
base.build_program = canonical_build_program


def run(args):
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError("dataset metadata/schema changed during extraction")
    determinate_after, _, _ = base.count(selected["where"]["determinate"])
    indeterminate_after, _, _ = base.count(selected["where"]["indeterminate"])
    if (
        determinate_after != selected["determinate_count"]
        or indeterminate_after != selected["indeterminate_count"]
    ):
        raise base.LiveDataError("candidate server counts changed during extraction")

    trips, audit_rows = base.parse_trips(
        selected["candidate_rows"],
        selected["provider"],
        selected["core_start"],
        selected["core_end"],
    )

    frontier = []
    ordered_sizes = {}
    certificates = {}
    ordered_by_model = {}
    for time_model in base.TIME_MODELS:
        full_model = base.model_rows(trips, time_model)
        ordered = base.ordered_subcohort(full_model, args.ordered_core)
        ordered_by_model[time_model] = ordered
        ordered_sizes[time_model] = len(ordered)
        frontier.extend(base.solve_frontier(ordered, time_model, args.solver_time_limit))

    audit_result = base.audit(frontier)
    if audit_result["status"] != "PASS":
        raise base.LiveDataError(
            "ordered-run capacity nesting audit failed: "
            + json.dumps(audit_result["problems"][:8])
        )

    index = {
        (row["time_model"], int(row["capacity"]), row["query"]): row
        for row in frontier
    }
    for time_model, ordered in ordered_by_model.items():
        peak = symmetry.peak_core_occupancy(ordered)
        cells = {}
        for capacity in base.CAPACITIES:
            bound = symmetry.peak_capacity_run_lower_bound(ordered, capacity)
            result = index[(time_model, capacity, "run_count_per_core")]
            milp_lower = result["lower"]
            cells[str(capacity)] = {
                "peak_capacity_lower_bound": bound,
                "milp_lower": milp_lower,
                "sharp": milp_lower is not None and abs(milp_lower - bound) <= 1e-8,
            }
        certificates[time_model] = {
            "peak_core_occupancy": peak,
            "capacity_cells": cells,
        }

    return {
        "report_version": "nyc-hvfhv-ordered-run/v3-canonical-root",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "core_start": selected["core_start"].isoformat(),
            "core_end": selected["core_end"].isoformat(),
            "source_core_rows": audit_rows["core_rows"],
            "source_candidate_rows": audit_rows["rows"],
            "ordered_core_rows": args.ordered_core,
            "ordered_candidate_rows": ordered_sizes,
        },
        "frontier": frontier,
        "audit": audit_result,
        "structural_certificates": certificates,
        "formulation": {
            "connectivity": "consecutive active elementary segments plus positive-overlap bridge at every active boundary",
            "capacity": "simultaneous occupancy <= C on every elementary segment",
            "total_run_cardinality_bounded_by_C": False,
            "edge_flow_variables": False,
            "canonical_root": "minimum-index core in each open run",
            "canonical_root_exact": True,
        },
        "claim_boundary": {
            "supported": "connected interval-run structural endpoints in a fixed public candidate universe under declared C",
            "not_supported": "actual vehicle/run recovery, true NYC capacity, partner recall, or population effects",
        },
    }


def render(report):
    text = base.render(report).rstrip()
    lines = [text, "", "## Structural run-count certificate", ""]
    lines.append("| Time model | Peak core occupancy | C | Peak-capacity lower bound | MILP lower | Sharp? |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for time_model, cert in report["structural_certificates"].items():
        peak = cert["peak_core_occupancy"]
        for capacity in base.CAPACITIES:
            cell = cert["capacity_cells"][str(capacity)]
            milp = "—" if cell["milp_lower"] is None else f"{cell['milp_lower']:.4f}"
            lines.append(
                f"| {time_model} | {peak} | {capacity} | "
                f"{cell['peak_capacity_lower_bound']:.4f} | {milp} | "
                f"{'yes' if cell['sharp'] else 'no'} |"
            )
    lines.extend(
        [
            "",
            "The peak-capacity bound is purely analytic: at a time when omega core intervals are active, every run can contain at most C of them, so at least ceil(omega/C) runs are required. Equality is reported only when the certified MILP lower endpoint attains that bound.",
            "",
        ]
    )
    return "\n".join(lines)


def self_test():
    symmetry.self_test()
    base.self_test()


def main() -> int:
    args = base.parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    base.validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    base.write_csv(report["frontier"], args.output_dir / "ordered_run_frontier.csv")
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
