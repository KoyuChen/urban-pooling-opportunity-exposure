#!/usr/bin/env python3
"""Thin live runner for the compact NYC ordered-run formulation.

This wrapper keeps the tested formulation in ``live_nyc_hvfhv_ordered_run_smoke``
unchanged and fixes the live orchestration name-shadowing bug that prevented the
aggregate report from being written after the MILPs completed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import live_nyc_hvfhv_ordered_run_smoke as base


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
    for time_model in base.TIME_MODELS:
        full_model = base.model_rows(trips, time_model)
        ordered = base.ordered_subcohort(full_model, args.ordered_core)
        ordered_sizes[time_model] = len(ordered)
        frontier.extend(base.solve_frontier(ordered, time_model, args.solver_time_limit))

    audit_result = base.audit(frontier)
    if audit_result["status"] != "PASS":
        raise base.LiveDataError(
            "ordered-run capacity nesting audit failed: "
            + json.dumps(audit_result["problems"][:8])
        )

    return {
        "report_version": "nyc-hvfhv-ordered-run/v2-compact-segments",
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
        "formulation": {
            "connectivity": "consecutive active elementary segments plus positive-overlap bridge at every active boundary",
            "capacity": "simultaneous occupancy <= C on every elementary segment",
            "total_run_cardinality_bounded_by_C": False,
            "edge_flow_variables": False,
        },
        "claim_boundary": {
            "supported": "connected interval-run structural endpoints in a fixed public candidate universe under declared C",
            "not_supported": "actual vehicle/run recovery, true NYC capacity, partner recall, or population effects",
        },
    }


def main() -> int:
    args = base.parser().parse_args()
    if args.self_test:
        base.self_test()
        return 0
    base.validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    base.write_csv(report["frontier"], args.output_dir / "ordered_run_frontier.csv")
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(base.render(report), encoding="utf-8")
    print(base.render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
