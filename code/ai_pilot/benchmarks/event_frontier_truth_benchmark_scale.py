#!/usr/bin/env python3
"""Scaled controlled-truth benchmark for relation-incomplete event streams.

This wrapper preserves the canonical benchmark's evaluation contract while
expanding the predeclared capacity lattice to C=2,3,4 and the replication count
to a paper-scale default.  Capacity four reuses the same outcome-blind temporal
generator as capacity three and only enlarges the feasible decomposition set;
its generated truth has peak simultaneous occupancy at most two and therefore
remains feasible under C=4.

The experiment is controlled synthetic method validation.  It is not evidence
of actual partners, households, referrals, service runs, co-riders, or vehicle
runs in an operational dataset.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import event_frontier_truth_benchmark as canonical

CAPACITIES = (2, 3, 4)


def generate_instance(seed: int, capacity: int):
    if capacity in (2, 3):
        return canonical.base.generate_instance(seed, capacity)
    if capacity == 4:
        template = canonical.base.generate_instance(seed, 3)
        return canonical.base.GeneratedInstance(
            seed=seed,
            capacity=4,
            rows=template.rows,
            true_runs=template.true_runs,
            true_buffer_indices=template.true_buffer_indices,
        )
    raise ValueError("scaled benchmark capacities are two, three, and four")


def run(
    instances_per_capacity: int,
    base_seed: int,
    capacities: Sequence[int] = CAPACITIES,
) -> dict[str, Any]:
    capacities = tuple(sorted(set(int(value) for value in capacities)))
    if not capacities or any(value not in CAPACITIES for value in capacities):
        raise ValueError("capacities must be a nonempty subset of 2,3,4")

    instance_rows: list[dict[str, Any]] = []
    truncation_rows: list[dict[str, Any]] = []
    for capacity in capacities:
        for offset in range(instances_per_capacity):
            seed = base_seed + capacity * 1_000_000 + offset
            instance = generate_instance(seed, capacity)
            instance_rows.append(canonical.evaluate_instance(instance))
            for retained in canonical.TRUNCATION_LEVELS:
                truncation_rows.append(
                    canonical.evaluate_truncation(instance, retained)
                )

    return {
        "report_version": "event-frontier-controlled-truth-benchmark/v3-scale",
        "design": {
            "capacities": list(capacities),
            "instances_per_capacity": instances_per_capacity,
            "core_rows_per_instance": 3,
            "buffer_rows_per_instance": 8,
            "thresholds": list(canonical.THRESHOLDS),
            "candidate_retention_levels": list(canonical.TRUNCATION_LEVELS),
            "truth_memberships_used_as_model_input": False,
            "true_support_count_used_for_composition_task": True,
            "true_support_count_used_for_support_baselines": False,
            "candidate_ranking_uses_public_outcome": False,
            "capacity_four_design": (
                "same temporal generator as C=3, re-evaluated under C=4; "
                "generated truth peak occupancy is at most two"
            ),
            "point_rules": [
                "maximum-cardinality maximum-overlap pair matching",
                "positive-overlap connected components",
                "nearest-q temporal selection",
                "feasible maximum-temporal-score selection at true q",
            ],
        },
        "summary": canonical.summarize(instance_rows, truncation_rows),
        "instances": instance_rows,
        "candidate_truncation_cells": truncation_rows,
        "claim_boundary": {
            "supported": (
                "method and baseline behavior under the declared controlled "
                "synthetic ordered-event generator with known truth"
            ),
            "not_supported": (
                "actual partner, case, household, referral, service-run, or "
                "vehicle-run recovery in an operational dataset"
            ),
        },
    }


def self_test() -> None:
    report = run(instances_per_capacity=2, base_seed=20260902)
    assert report["summary"]["instance_count"] == 6
    assert abs(report["summary"]["truth_coverage_rate"] - 1.0) <= canonical.TOL
    assert set(report["summary"]["by_capacity"]) == {"2", "3", "4"}
    for cell in report["summary"]["by_capacity"].values():
        assert abs(cell["point_errors_flagged_ambiguous_rate"] - 1.0) <= canonical.TOL
    print("scaled event-frontier controlled truth benchmark self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances-per-capacity", type=int, default=1000)
    parser.add_argument("--base-seed", type=int, default=20260902)
    parser.add_argument(
        "--capacities",
        type=int,
        nargs="+",
        default=list(CAPACITIES),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.instances_per_capacity <= 0:
        parser.error("--instances-per-capacity must be positive")
    if args.output_dir is None:
        parser.error("--output-dir is required")
    if not args.capacities or any(value not in CAPACITIES for value in args.capacities):
        parser.error("--capacities must be a nonempty subset of 2 3 4")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(
        args.instances_per_capacity,
        args.base_seed,
        args.capacities,
    )
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        canonical.render(report),
        encoding="utf-8",
    )
    canonical.write_csv(
        report["instances"],
        args.output_dir / "instance_metrics.csv",
    )
    canonical.write_csv(
        report["candidate_truncation_cells"],
        args.output_dir / "candidate_truncation_cells.csv",
    )
    print(canonical.render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
