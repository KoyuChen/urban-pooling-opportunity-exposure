#!/usr/bin/env python3
"""Controlled truth benchmark for relation-incomplete temporal events.

This is the canonical v2 benchmark.  It reuses the deterministic generator and
low-level frontier helpers from ``relation_incomplete_event_benchmark`` but
makes the evaluation contract explicit:

* the support-recovery task does not receive the true support count;
* the composition task conditions on the true support count q, while hiding all
  membership labels, to isolate relational ambiguity from cardinality error;
* pairwise reconstruction is an exact maximum-cardinality, maximum-overlap
  matching rather than a greedy pairing;
* candidate truncation distinguishes representability of the true world from a
  scalar aggregate falling inside a misspecified frontier by coincidence.

The experiment is controlled synthetic validation, not evidence about actual
partners, cases, households, referrals, or vehicle runs.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics
from typing import Any, Sequence

import relation_incomplete_event_benchmark as base

TOL = base.TOL
THRESHOLDS = base.THRESHOLDS
TRUNCATION_LEVELS = base.TRUNCATION_LEVELS


def pairwise_maximum_matching_mask(rows: Sequence[base.exact.FixedTimeRow]) -> int:
    """Exact cardinality-first bipartite matching using temporal overlap only."""

    ordered = sorted(rows, key=lambda row: row.index)
    cores = [position for position, row in enumerate(ordered) if row.role == "core"]
    buffers = [
        position for position, row in enumerate(ordered) if row.role == "buffer"
    ]
    candidate_buffers: dict[int, list[int]] = {}
    edge_score: dict[tuple[int, int], float] = {}
    for core in cores:
        candidates: list[int] = []
        for buffer in buffers:
            overlap = base._overlap(ordered[core], ordered[buffer])
            if overlap <= 0:
                continue
            distance = abs(base._midpoint(ordered[core]) - base._midpoint(ordered[buffer]))
            candidates.append(buffer)
            edge_score[(core, buffer)] = 20.0 * overlap - distance
        candidate_buffers[core] = sorted(candidates)

    best_cardinality = -1
    best_score = float("-inf")
    best_buffers: tuple[int, ...] = ()

    def recurse(
        core_offset: int,
        used_buffers: set[int],
        selected_buffers: tuple[int, ...],
        score: float,
    ) -> None:
        nonlocal best_cardinality, best_score, best_buffers
        if core_offset == len(cores):
            cardinality = len(selected_buffers)
            canonical = tuple(sorted(selected_buffers))
            if (
                cardinality > best_cardinality
                or (
                    cardinality == best_cardinality
                    and score > best_score + TOL
                )
                or (
                    cardinality == best_cardinality
                    and abs(score - best_score) <= TOL
                    and canonical < best_buffers
                )
            ):
                best_cardinality = cardinality
                best_score = score
                best_buffers = canonical
            return

        core = cores[core_offset]
        # The unmatched branch is required when a core has no compatible
        # buffer; cardinality is the primary matching objective.
        recurse(core_offset + 1, used_buffers, selected_buffers, score)
        for buffer in candidate_buffers[core]:
            if buffer in used_buffers:
                continue
            recurse(
                core_offset + 1,
                used_buffers | {buffer},
                selected_buffers + (buffer,),
                score + edge_score[(core, buffer)],
            )

    recurse(0, set(), (), 0.0)
    return base._member_mask(best_buffers)


def evaluate_instance(instance: base.GeneratedInstance) -> dict[str, Any]:
    master = base.exact.build_master(instance.rows, instance.capacity, epsilon=0.1)
    values = base._buffer_value_map(master.rows)
    true_mask = base._member_mask(instance.true_buffer_indices)
    true_q = true_mask.bit_count()
    lower, upper, width = base._frontier(master, true_q)
    true_value = base._mean(true_mask, values)
    truth_covered = lower - TOL <= true_value <= upper + TOL
    if true_mask not in master.reachable_buffer_masks or not truth_covered:
        raise AssertionError("full candidate universe failed to cover truth")

    # Composition task: q is deliberately supplied, but memberships are not.
    feasible_mask = base._feasible_score_point(master, true_q)
    feasible_value = base._mean(feasible_mask, values)
    nearest_mask = base._nearest_q_mask(master.rows, true_q)
    nearest_value = base._mean(nearest_mask, values)
    nearest_feasible = nearest_mask in master.reachable_buffer_masks
    nearest_outside = nearest_value < lower - TOL or nearest_value > upper + TOL

    # Support task: neither point rule receives true q.
    component_mask = base._connected_component_mask(master.rows)
    component_q = component_mask.bit_count()
    component_reachable = component_mask in master.reachable_buffer_masks
    pairwise_mask = pairwise_maximum_matching_mask(master.rows)
    pairwise_q = pairwise_mask.bit_count()

    feasible_decision_errors = 0
    nearest_decision_errors = 0
    frontier_ambiguous_thresholds = 0
    feasible_errors_flagged_ambiguous = 0
    for threshold in THRESHOLDS:
        truth_decision = true_value >= threshold
        feasible_decision = feasible_value >= threshold
        nearest_decision = nearest_value >= threshold
        identified = lower >= threshold or upper < threshold
        ambiguous = not identified
        frontier_ambiguous_thresholds += int(ambiguous)
        feasible_error = feasible_decision != truth_decision
        feasible_decision_errors += int(feasible_error)
        nearest_decision_errors += int(nearest_decision != truth_decision)
        feasible_errors_flagged_ambiguous += int(feasible_error and ambiguous)
        if feasible_error and identified:
            raise AssertionError(
                "two feasible worlds disagree despite an identified threshold decision"
            )

    reachable_counts = {mask.bit_count() for mask in master.reachable_buffer_masks}
    return {
        "seed": instance.seed,
        "capacity": instance.capacity,
        "core_count": master.all_core_mask.bit_count(),
        "buffer_count": master.all_buffer_mask.bit_count(),
        "true_selected_buffer_count": true_q,
        "reachable_support_min": min(reachable_counts),
        "reachable_support_max": max(reachable_counts),
        "reachable_buffer_mask_count": len(master.reachable_buffer_masks),
        "run_column_count": len(master.columns),
        "true_value": true_value,
        "frontier_lower": lower,
        "frontier_upper": upper,
        "frontier_width": width,
        "truth_covered": truth_covered,
        "feasible_temporal_point_value": feasible_value,
        "feasible_temporal_point_absolute_error": abs(feasible_value - true_value),
        "feasible_temporal_point_decision_errors": feasible_decision_errors,
        "feasible_errors_flagged_ambiguous": feasible_errors_flagged_ambiguous,
        "nearest_q_value": nearest_value,
        "nearest_q_absolute_error": abs(nearest_value - true_value),
        "nearest_q_mask_feasible": nearest_feasible,
        "nearest_q_value_outside_frontier": nearest_outside,
        "nearest_q_decision_errors": nearest_decision_errors,
        "component_selected_buffer_count": component_q,
        "component_mask_reachable": component_reachable,
        "component_support_count_reachable": component_q in reachable_counts,
        "maximum_matching_selected_buffer_count": pairwise_q,
        "maximum_matching_support_absolute_error": abs(pairwise_q - true_q),
        "maximum_matching_underselects_truth": pairwise_q < true_q,
        "frontier_ambiguous_thresholds": frontier_ambiguous_thresholds,
        "threshold_count": len(THRESHOLDS),
    }


def evaluate_truncation(
    instance: base.GeneratedInstance, retained_buffer_count: int
) -> dict[str, Any]:
    ordered = sorted(instance.rows, key=lambda row: row.index)
    scores = base._buffer_scores(ordered)
    ranked = sorted(scores, key=lambda position: (-scores[position], position))
    retained = set(ranked[:retained_buffer_count])
    true_set = set(instance.true_buffer_indices)
    remapped, mapping = base._remap_rows(ordered, retained)
    true_retained = true_set & retained
    true_q = len(true_set)
    true_value = sum(float(ordered[position].miles) for position in true_set) / true_q
    master = base.exact.build_master(remapped, instance.capacity, epsilon=0.1)
    counts = {mask.bit_count() for mask in master.reachable_buffer_masks}
    frontier_available = true_q in counts
    aggregate_value_covered = False
    lower = None
    upper = None
    if frontier_available:
        result = base.exact.solve_attribute(master, true_q, "miles")
        if result["status"] != "CERTIFIED_OPTIMAL_PAIR":
            raise AssertionError("truncated exact frontier unexpectedly unresolved")
        lower = float(result["lower"])
        upper = float(result["upper"])
        aggregate_value_covered = lower - TOL <= true_value <= upper + TOL

    true_world_representable = true_set <= retained
    if true_world_representable:
        remapped_true_mask = base._member_mask(mapping[position] for position in true_set)
        if remapped_true_mask not in master.reachable_buffer_masks:
            raise AssertionError("retained truth is absent from truncated master")
        if not aggregate_value_covered:
            raise AssertionError("frontier missed truth despite retaining every true member")

    return {
        "seed": instance.seed,
        "capacity": instance.capacity,
        "retained_buffer_count": retained_buffer_count,
        "true_selected_buffer_count": true_q,
        "true_member_recall": len(true_retained) / true_q,
        "true_world_representable": true_world_representable,
        "frontier_available_at_true_support": frontier_available,
        "aggregate_value_covered": aggregate_value_covered,
        "frontier_available_but_true_world_omitted": (
            frontier_available and not true_world_representable
        ),
        "aggregate_value_covered_despite_world_omission": (
            aggregate_value_covered and not true_world_representable
        ),
        "frontier_lower": lower,
        "frontier_upper": upper,
    }


def _mean_bool(rows: Sequence[dict[str, Any]], key: str) -> float:
    return sum(bool(row[key]) for row in rows) / len(rows)


def _mean_numeric(rows: Sequence[dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows)


def summarize(
    instances: Sequence[dict[str, Any]],
    truncations: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    by_capacity: dict[str, Any] = {}
    for capacity in sorted({int(row["capacity"]) for row in instances}):
        cells = [row for row in instances if int(row["capacity"]) == capacity]
        total_thresholds = sum(int(row["threshold_count"]) for row in cells)
        total_feasible_errors = sum(
            int(row["feasible_temporal_point_decision_errors"]) for row in cells
        )
        by_capacity[str(capacity)] = {
            "instance_count": len(cells),
            "truth_coverage_rate": _mean_bool(cells, "truth_covered"),
            "median_frontier_width": statistics.median(
                float(row["frontier_width"]) for row in cells
            ),
            "mean_feasible_temporal_point_absolute_error": _mean_numeric(
                cells, "feasible_temporal_point_absolute_error"
            ),
            "feasible_temporal_point_threshold_error_rate": (
                total_feasible_errors / total_thresholds
            ),
            "point_errors_flagged_ambiguous_rate": (
                sum(int(row["feasible_errors_flagged_ambiguous"]) for row in cells)
                / total_feasible_errors
                if total_feasible_errors
                else 1.0
            ),
            "nearest_q_infeasible_rate": 1.0
            - _mean_bool(cells, "nearest_q_mask_feasible"),
            "nearest_q_outside_frontier_rate": _mean_bool(
                cells, "nearest_q_value_outside_frontier"
            ),
            "nearest_q_threshold_error_rate": sum(
                int(row["nearest_q_decision_errors"]) for row in cells
            )
            / total_thresholds,
            "component_mask_unreachable_rate": 1.0
            - _mean_bool(cells, "component_mask_reachable"),
            "component_support_count_unreachable_rate": 1.0
            - _mean_bool(cells, "component_support_count_reachable"),
            "maximum_matching_underselection_rate": _mean_bool(
                cells, "maximum_matching_underselects_truth"
            ),
            "mean_maximum_matching_support_absolute_error": _mean_numeric(
                cells, "maximum_matching_support_absolute_error"
            ),
        }

    truncation_summary: list[dict[str, Any]] = []
    for capacity in sorted({int(row["capacity"]) for row in truncations}):
        for retained in sorted(
            {
                int(row["retained_buffer_count"])
                for row in truncations
                if int(row["capacity"]) == capacity
            }
        ):
            cells = [
                row
                for row in truncations
                if int(row["capacity"]) == capacity
                and int(row["retained_buffer_count"]) == retained
            ]
            truncation_summary.append(
                {
                    "capacity": capacity,
                    "retained_buffer_count": retained,
                    "instance_count": len(cells),
                    "mean_true_member_recall": _mean_numeric(
                        cells, "true_member_recall"
                    ),
                    "true_world_representable_rate": _mean_bool(
                        cells, "true_world_representable"
                    ),
                    "frontier_available_at_true_support_rate": _mean_bool(
                        cells, "frontier_available_at_true_support"
                    ),
                    "aggregate_value_coverage_rate": _mean_bool(
                        cells, "aggregate_value_covered"
                    ),
                    "frontier_available_but_true_world_omitted_rate": _mean_bool(
                        cells, "frontier_available_but_true_world_omitted"
                    ),
                    "aggregate_value_covered_despite_world_omission_rate": _mean_bool(
                        cells, "aggregate_value_covered_despite_world_omission"
                    ),
                }
            )
    return {
        "instance_count": len(instances),
        "truth_coverage_rate": _mean_bool(instances, "truth_covered"),
        "by_capacity": by_capacity,
        "candidate_truncation": truncation_summary,
    }


def run(instances_per_capacity: int, base_seed: int) -> dict[str, Any]:
    instance_rows: list[dict[str, Any]] = []
    truncation_rows: list[dict[str, Any]] = []
    for capacity in (2, 3):
        for offset in range(instances_per_capacity):
            seed = base_seed + capacity * 1_000_000 + offset
            instance = base.generate_instance(seed, capacity)
            instance_rows.append(evaluate_instance(instance))
            for retained in TRUNCATION_LEVELS:
                truncation_rows.append(evaluate_truncation(instance, retained))
    return {
        "report_version": "event-frontier-controlled-truth-benchmark/v2",
        "design": {
            "capacities": [2, 3],
            "instances_per_capacity": instances_per_capacity,
            "core_rows_per_instance": 3,
            "buffer_rows_per_instance": 8,
            "thresholds": list(THRESHOLDS),
            "candidate_retention_levels": list(TRUNCATION_LEVELS),
            "truth_memberships_used_as_model_input": False,
            "true_support_count_used_for_composition_task": True,
            "true_support_count_used_for_support_baselines": False,
            "candidate_ranking_uses_public_outcome": False,
            "point_rules": [
                "maximum-cardinality maximum-overlap pair matching",
                "positive-overlap connected components",
                "nearest-q temporal selection",
                "feasible maximum-temporal-score selection at true q",
            ],
        },
        "summary": summarize(instance_rows, truncation_rows),
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


def render(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Controlled truth benchmark for relation-incomplete event streams",
        "",
        "Membership labels generate and evaluate the data but are never supplied "
        "to the frontier or point rules. The composition task is explicitly "
        "conditioned on the true support count; the support baselines are not.",
        "",
        f"Full-universe aggregate truth coverage: **{100 * summary['truth_coverage_rate']:.1f}%** "
        f"over **{summary['instance_count']}** instances.",
        "",
        "| C | Instances | Median width | Feasible point MAE | Feasible point decision error | Errors flagged ambiguous | Nearest-q infeasible | Component mask unreachable | Maximum matching underselects truth |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for capacity, cell in sorted(summary["by_capacity"].items()):
        lines.append(
            f"| {capacity} | {cell['instance_count']} | "
            f"{cell['median_frontier_width']:.3f} | "
            f"{cell['mean_feasible_temporal_point_absolute_error']:.3f} | "
            f"{100 * cell['feasible_temporal_point_threshold_error_rate']:.1f}% | "
            f"{100 * cell['point_errors_flagged_ambiguous_rate']:.1f}% | "
            f"{100 * cell['nearest_q_infeasible_rate']:.1f}% | "
            f"{100 * cell['component_mask_unreachable_rate']:.1f}% | "
            f"{100 * cell['maximum_matching_underselection_rate']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Candidate-universe truncation",
            "",
            "| C | Buffers kept | Mean member recall | True world representable | Frontier exists at true q | Scalar value covered | Frontier exists but world omitted | Scalar covered despite world omission |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for cell in summary["candidate_truncation"]:
        lines.append(
            f"| {cell['capacity']} | {cell['retained_buffer_count']} | "
            f"{100 * cell['mean_true_member_recall']:.1f}% | "
            f"{100 * cell['true_world_representable_rate']:.1f}% | "
            f"{100 * cell['frontier_available_at_true_support_rate']:.1f}% | "
            f"{100 * cell['aggregate_value_coverage_rate']:.1f}% | "
            f"{100 * cell['frontier_available_but_true_world_omitted_rate']:.1f}% | "
            f"{100 * cell['aggregate_value_covered_despite_world_omission_rate']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "A feasible temporal-score point is inside the certified frontier but "
            "can choose the wrong side of a policy threshold; every such error is "
            "flagged by a frontier that straddles that threshold. Pair matching and "
            "connected components address support without receiving true q, but "
            "respectively miss sequential members or ignore capacity. Candidate "
            "truncation is logically separate: a solver can return a nonempty "
            "frontier even after the true relational world has been removed, and a "
            "scalar truth value can remain inside by coincidence.",
            "",
            "This is controlled synthetic method validation, not evidence of actual "
            "co-membership in a public city dataset.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Sequence[dict[str, Any]], path: Path) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    report = run(instances_per_capacity=5, base_seed=20260902)
    assert report["summary"]["instance_count"] == 10
    assert abs(report["summary"]["truth_coverage_rate"] - 1.0) <= TOL
    for cell in report["summary"]["by_capacity"].values():
        assert abs(cell["point_errors_flagged_ambiguous_rate"] - 1.0) <= TOL
    for cell in report["summary"]["candidate_truncation"]:
        assert 0.0 <= cell["aggregate_value_coverage_rate"] <= 1.0
        assert (
            cell["true_world_representable_rate"]
            <= cell["aggregate_value_coverage_rate"] + TOL
        )
    print("event-frontier controlled truth benchmark self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances-per-capacity", type=int, default=250)
    parser.add_argument("--base-seed", type=int, default=20260902)
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
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args.instances_per_capacity, args.base_seed)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    write_csv(report["instances"], args.output_dir / "instance_metrics.csv")
    write_csv(
        report["candidate_truncation_cells"],
        args.output_dir / "candidate_truncation_cells.csv",
    )
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
