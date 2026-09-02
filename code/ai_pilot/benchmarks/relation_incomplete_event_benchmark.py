#!/usr/bin/env python3
"""Truth-based benchmark for certified aggregates on relation-incomplete events.

Synthetic temporal events are generated with known ordered-run membership, then
only row intervals, roles, and a public scalar outcome are supplied to the
frontier and point baselines.  The benchmark tests three questions that cannot
be answered from the public-city audits alone:

1. Does the certified frontier contain the true aggregate when the candidate
   universe contains every true event member?
2. How often do plausible point reconstructions make a wrong threshold decision
   or select a support incompatible with any feasible ordered-run world?
3. How quickly does truth coverage fail when a temporal candidate screen omits
   true event members?

Truth labels are used only for evaluation.  The benchmark is semi-synthetic
method validation, not evidence about actual partners or vehicle runs.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
import statistics
import sys
from typing import Any, Iterable, Sequence

PRODUCTION_AUDIT = (
    Path(__file__).resolve().parents[1] / "data_pipeline" / "production_audit"
)
if str(PRODUCTION_AUDIT) not in sys.path:
    sys.path.insert(0, str(PRODUCTION_AUDIT))

import ordered_run_fixed_time_master as exact  # noqa: E402

TOL = 1e-9
THRESHOLDS = (0.25, 0.50, 0.75)
TRUNCATION_LEVELS = (4, 6, 8)


@dataclass(frozen=True)
class GeneratedInstance:
    seed: int
    capacity: int
    rows: tuple[exact.FixedTimeRow, ...]
    true_runs: tuple[tuple[int, ...], ...]
    true_buffer_indices: tuple[int, ...]


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return min(upper, max(lower, value))


def _overlap(left: exact.FixedTimeRow, right: exact.FixedTimeRow) -> float:
    return max(0.0, min(left.end, right.end) - max(left.start, right.start))


def _midpoint(row: exact.FixedTimeRow) -> float:
    return (row.start + row.end) / 2.0


def _temporal_score(
    buffer_row: exact.FixedTimeRow,
    core_rows: Sequence[exact.FixedTimeRow],
) -> float:
    """Outcome-blind proximity score used by all temporal point screens."""

    best_overlap = max(_overlap(buffer_row, core) for core in core_rows)
    best_midpoint_distance = min(
        abs(_midpoint(buffer_row) - _midpoint(core)) for core in core_rows
    )
    return 20.0 * best_overlap - best_midpoint_distance


def generate_instance(seed: int, capacity: int) -> GeneratedInstance:
    if capacity not in {2, 3}:
        raise ValueError("benchmark capacities are two and three")
    generator = random.Random(seed)
    core_count = 3
    buffer_count = 8
    rows: list[exact.FixedTimeRow] = []
    core_starts: list[int] = []

    for core in range(core_count):
        start = 3 * core + generator.choice((0, 0, 1))
        core_starts.append(start)
        rows.append(
            exact.FixedTimeRow(
                core,
                "core",
                float(start),
                float(start + 4),
                miles=0.0,
                seconds=240.0,
            )
        )

    true_runs: list[list[int]] = [[core] for core in range(core_count)]
    true_buffer_indices: list[int] = []

    # Every focal event has one direct member. Their intervals also overlap
    # neighboring cores, creating nontrivial alternative partitions.
    for core, start in enumerate(core_starts):
        index = core_count + len(true_buffer_indices)
        outcome_center = 0.20 + 0.28 * core
        outcome = _clip(outcome_center + generator.uniform(-0.12, 0.12))
        rows.append(
            exact.FixedTimeRow(
                index,
                "buffer",
                float(start + 1),
                float(start + 5),
                miles=outcome,
                seconds=float(120 + 30 * core),
            )
        )
        true_runs[core].append(index)
        true_buffer_indices.append(index)

    # Add one or two sequential members. They connect through the direct member
    # while touching or missing the core, so pairwise matching cannot represent
    # the full true event even though simultaneous occupancy remains two.
    extra_count = 1 + generator.randrange(2)
    extra_cores = generator.sample(range(core_count), extra_count)
    for core in extra_cores:
        start = core_starts[core]
        index = core_count + len(true_buffer_indices)
        outcome_center = 0.28 + 0.22 * core
        outcome = _clip(outcome_center + generator.uniform(-0.15, 0.15))
        rows.append(
            exact.FixedTimeRow(
                index,
                "buffer",
                float(start + 4),
                float(start + 8),
                miles=outcome,
                seconds=float(180 + 30 * core),
            )
        )
        true_runs[core].append(index)
        true_buffer_indices.append(index)

    # Distractors are temporally plausible and have deliberately broad public
    # outcomes, making an outcome-blind point linkage consequential.
    while len(rows) < core_count + buffer_count:
        index = len(rows)
        start = generator.randrange(0, 10)
        duration = generator.randrange(2, 7)
        extreme = generator.choice((0.04, 0.96))
        outcome = _clip(extreme + generator.uniform(-0.04, 0.04))
        rows.append(
            exact.FixedTimeRow(
                index,
                "buffer",
                float(start),
                float(start + duration),
                miles=outcome,
                seconds=float(60 * duration),
            )
        )

    instance = GeneratedInstance(
        seed=seed,
        capacity=capacity,
        rows=tuple(rows),
        true_runs=tuple(tuple(run) for run in true_runs),
        true_buffer_indices=tuple(sorted(true_buffer_indices)),
    )
    _assert_truth_feasible(instance)
    return instance


def _member_mask(indices: Iterable[int]) -> int:
    return sum(1 << index for index in indices)


def _assert_truth_feasible(instance: GeneratedInstance) -> None:
    master = exact.build_master(instance.rows, instance.capacity, epsilon=0.1)
    column_masks = {column.member_mask for column in master.columns}
    for run in instance.true_runs:
        if _member_mask(run) not in column_masks:
            raise AssertionError(f"generated truth run is infeasible: {run}")
    true_mask = _member_mask(instance.true_buffer_indices)
    if true_mask not in master.reachable_buffer_masks:
        raise AssertionError("generated truth partition is absent from exact master")


def _buffer_value_map(rows: Sequence[exact.FixedTimeRow]) -> dict[int, float]:
    values: dict[int, float] = {}
    for position, row in enumerate(sorted(rows, key=lambda item: item.index)):
        if row.role == "buffer":
            if row.miles is None:
                raise ValueError("benchmark public outcome is missing")
            values[position] = float(row.miles)
    return values


def _mean(mask: int, values: dict[int, float]) -> float:
    positions = [position for position in values if mask & (1 << position)]
    if not positions:
        raise ValueError("point mask selects no buffers")
    return sum(values[position] for position in positions) / len(positions)


def _buffer_scores(rows: Sequence[exact.FixedTimeRow]) -> dict[int, float]:
    ordered = sorted(rows, key=lambda row: row.index)
    cores = [row for row in ordered if row.role == "core"]
    return {
        position: _temporal_score(row, cores)
        for position, row in enumerate(ordered)
        if row.role == "buffer"
    }


def _nearest_q_mask(rows: Sequence[exact.FixedTimeRow], q: int) -> int:
    scores = _buffer_scores(rows)
    selected = sorted(scores, key=lambda position: (-scores[position], position))[:q]
    return _member_mask(selected)


def _feasible_score_point(
    master: exact.FixedTimeMaster,
    q: int,
) -> int:
    scores = _buffer_scores(master.rows)
    candidates = [
        mask for mask in master.reachable_buffer_masks if mask.bit_count() == q
    ]
    if not candidates:
        raise ValueError("requested point support is infeasible")
    return max(
        candidates,
        key=lambda mask: (
            sum(score for position, score in scores.items() if mask & (1 << position)),
            -mask,
        ),
    )


def _connected_component_mask(
    rows: Sequence[exact.FixedTimeRow], epsilon: float = 0.1
) -> int:
    ordered = sorted(rows, key=lambda row: row.index)
    adjacency = [set() for _row in ordered]
    for left in range(len(ordered)):
        for right in range(left + 1, len(ordered)):
            if _overlap(ordered[left], ordered[right]) + TOL >= epsilon:
                adjacency[left].add(right)
                adjacency[right].add(left)
    selected_buffers: set[int] = set()
    seen: set[int] = set()
    for seed, row in enumerate(ordered):
        if seed in seen:
            continue
        component: set[int] = set()
        stack = [seed]
        while stack:
            position = stack.pop()
            if position in component:
                continue
            component.add(position)
            seen.add(position)
            stack.extend(adjacency[position] - component)
        if any(ordered[position].role == "core" for position in component):
            selected_buffers.update(
                position
                for position in component
                if ordered[position].role == "buffer"
            )
    return _member_mask(selected_buffers)


def _pairwise_greedy_mask(rows: Sequence[exact.FixedTimeRow]) -> int:
    ordered = sorted(rows, key=lambda row: row.index)
    cores = [position for position, row in enumerate(ordered) if row.role == "core"]
    buffers = [
        position for position, row in enumerate(ordered) if row.role == "buffer"
    ]
    pairs: list[tuple[float, float, int, int]] = []
    for core in cores:
        for buffer in buffers:
            overlap = _overlap(ordered[core], ordered[buffer])
            if overlap <= 0:
                continue
            distance = abs(_midpoint(ordered[core]) - _midpoint(ordered[buffer]))
            pairs.append((-overlap, distance, core, buffer))
    used_cores: set[int] = set()
    used_buffers: set[int] = set()
    for _negative_overlap, _distance, core, buffer in sorted(pairs):
        if core in used_cores or buffer in used_buffers:
            continue
        used_cores.add(core)
        used_buffers.add(buffer)
    return _member_mask(used_buffers)


def _frontier(
    master: exact.FixedTimeMaster, q: int
) -> tuple[float, float, float]:
    result = exact.solve_attribute(master, q, "miles")
    if result["status"] != "CERTIFIED_OPTIMAL_PAIR":
        raise ValueError(f"frontier unresolved at q={q}: {result}")
    return float(result["lower"]), float(result["upper"]), float(result["width"])


def evaluate_instance(instance: GeneratedInstance) -> dict[str, Any]:
    master = exact.build_master(instance.rows, instance.capacity, epsilon=0.1)
    values = _buffer_value_map(master.rows)
    true_mask = _member_mask(instance.true_buffer_indices)
    q = true_mask.bit_count()
    lower, upper, width = _frontier(master, q)
    true_value = _mean(true_mask, values)
    truth_covered = lower - TOL <= true_value <= upper + TOL
    if true_mask not in master.reachable_buffer_masks or not truth_covered:
        raise AssertionError("full candidate universe failed to cover truth")

    feasible_mask = _feasible_score_point(master, q)
    feasible_value = _mean(feasible_mask, values)
    nearest_mask = _nearest_q_mask(master.rows, q)
    nearest_value = _mean(nearest_mask, values)
    nearest_feasible = nearest_mask in master.reachable_buffer_masks
    nearest_outside = nearest_value < lower - TOL or nearest_value > upper + TOL

    component_mask = _connected_component_mask(master.rows)
    component_q = component_mask.bit_count()
    component_reachable = component_mask in master.reachable_buffer_masks
    pairwise_mask = _pairwise_greedy_mask(master.rows)
    pairwise_q = pairwise_mask.bit_count()

    feasible_decision_errors = 0
    nearest_decision_errors = 0
    frontier_ambiguous_thresholds = 0
    for threshold in THRESHOLDS:
        truth_decision = true_value >= threshold
        feasible_decision = feasible_value >= threshold
        nearest_decision = nearest_value >= threshold
        identified = lower >= threshold or upper < threshold
        frontier_ambiguous_thresholds += int(not identified)
        feasible_decision_errors += int(feasible_decision != truth_decision)
        nearest_decision_errors += int(nearest_decision != truth_decision)
        if feasible_decision != truth_decision and identified:
            raise AssertionError(
                "two feasible worlds disagree despite an identified threshold decision"
            )

    return {
        "seed": instance.seed,
        "capacity": instance.capacity,
        "core_count": master.all_core_mask.bit_count(),
        "buffer_count": master.all_buffer_mask.bit_count(),
        "true_selected_buffer_count": q,
        "reachable_support_min": min(
            mask.bit_count() for mask in master.reachable_buffer_masks
        ),
        "reachable_support_max": max(
            mask.bit_count() for mask in master.reachable_buffer_masks
        ),
        "reachable_buffer_mask_count": len(master.reachable_buffer_masks),
        "run_column_count": len(master.columns),
        "true_value": true_value,
        "frontier_lower": lower,
        "frontier_upper": upper,
        "frontier_width": width,
        "truth_covered": truth_covered,
        "feasible_point_value": feasible_value,
        "feasible_point_absolute_error": abs(feasible_value - true_value),
        "feasible_point_decision_errors": feasible_decision_errors,
        "nearest_q_value": nearest_value,
        "nearest_q_absolute_error": abs(nearest_value - true_value),
        "nearest_q_mask_feasible": nearest_feasible,
        "nearest_q_value_outside_frontier": nearest_outside,
        "nearest_q_decision_errors": nearest_decision_errors,
        "component_selected_buffer_count": component_q,
        "component_mask_reachable": component_reachable,
        "component_support_count_reachable": component_q
        in {mask.bit_count() for mask in master.reachable_buffer_masks},
        "pairwise_selected_buffer_count": pairwise_q,
        "pairwise_support_absolute_error": abs(pairwise_q - q),
        "pairwise_underselects_truth": pairwise_q < q,
        "frontier_ambiguous_thresholds": frontier_ambiguous_thresholds,
        "threshold_count": len(THRESHOLDS),
    }


def _remap_rows(
    rows: Sequence[exact.FixedTimeRow], retained_buffer_positions: set[int]
) -> tuple[list[exact.FixedTimeRow], dict[int, int]]:
    ordered = sorted(rows, key=lambda row: row.index)
    retained_old_positions = [
        position
        for position, row in enumerate(ordered)
        if row.role == "core" or position in retained_buffer_positions
    ]
    mapping = {
        old_position: new_position
        for new_position, old_position in enumerate(retained_old_positions)
    }
    remapped = [
        exact.FixedTimeRow(
            mapping[old_position],
            ordered[old_position].role,
            ordered[old_position].start,
            ordered[old_position].end,
            miles=ordered[old_position].miles,
            seconds=ordered[old_position].seconds,
        )
        for old_position in retained_old_positions
    ]
    return remapped, mapping


def evaluate_truncation(
    instance: GeneratedInstance, retained_buffer_count: int
) -> dict[str, Any]:
    ordered = sorted(instance.rows, key=lambda row: row.index)
    scores = _buffer_scores(ordered)
    ranked = sorted(scores, key=lambda position: (-scores[position], position))
    retained = set(ranked[:retained_buffer_count])
    true_set = set(instance.true_buffer_indices)
    remapped, mapping = _remap_rows(ordered, retained)
    true_retained = true_set & retained
    q = len(true_set)
    true_value = sum(float(ordered[position].miles) for position in true_set) / q
    master = exact.build_master(remapped, instance.capacity, epsilon=0.1)
    counts = {mask.bit_count() for mask in master.reachable_buffer_masks}
    status = "PROVEN_INFEASIBLE_AT_TRUE_SUPPORT"
    covered = False
    lower = None
    upper = None
    if q in counts:
        result = exact.solve_attribute(master, q, "miles")
        if result["status"] != "CERTIFIED_OPTIMAL_PAIR":
            raise AssertionError("truncated exact frontier unexpectedly unresolved")
        status = "CERTIFIED_FRONTIER_AT_TRUE_SUPPORT"
        lower = float(result["lower"])
        upper = float(result["upper"])
        covered = lower - TOL <= true_value <= upper + TOL

    all_truth_retained = true_set <= retained
    if all_truth_retained:
        remapped_true_mask = _member_mask(mapping[position] for position in true_set)
        if remapped_true_mask not in master.reachable_buffer_masks:
            raise AssertionError("retained truth is absent from truncated master")
        if not covered:
            raise AssertionError("frontier missed truth despite retaining every true member")

    return {
        "seed": instance.seed,
        "capacity": instance.capacity,
        "retained_buffer_count": retained_buffer_count,
        "true_selected_buffer_count": q,
        "true_member_recall": len(true_retained) / q,
        "all_true_members_retained": all_truth_retained,
        "frontier_status": status,
        "truth_covered": covered,
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
        by_capacity[str(capacity)] = {
            "instance_count": len(cells),
            "truth_coverage_rate": _mean_bool(cells, "truth_covered"),
            "median_frontier_width": statistics.median(
                float(row["frontier_width"]) for row in cells
            ),
            "mean_feasible_point_absolute_error": _mean_numeric(
                cells, "feasible_point_absolute_error"
            ),
            "feasible_point_threshold_error_rate": sum(
                int(row["feasible_point_decision_errors"]) for row in cells
            )
            / sum(int(row["threshold_count"]) for row in cells),
            "nearest_q_infeasible_rate": 1.0
            - _mean_bool(cells, "nearest_q_mask_feasible"),
            "nearest_q_outside_frontier_rate": _mean_bool(
                cells, "nearest_q_value_outside_frontier"
            ),
            "nearest_q_threshold_error_rate": sum(
                int(row["nearest_q_decision_errors"]) for row in cells
            )
            / sum(int(row["threshold_count"]) for row in cells),
            "component_mask_unreachable_rate": 1.0
            - _mean_bool(cells, "component_mask_reachable"),
            "component_support_count_unreachable_rate": 1.0
            - _mean_bool(cells, "component_support_count_reachable"),
            "pairwise_underselection_rate": _mean_bool(
                cells, "pairwise_underselects_truth"
            ),
            "mean_pairwise_support_absolute_error": _mean_numeric(
                cells, "pairwise_support_absolute_error"
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
                    "all_true_members_retained_rate": _mean_bool(
                        cells, "all_true_members_retained"
                    ),
                    "frontier_available_at_true_support_rate": sum(
                        row["frontier_status"]
                        == "CERTIFIED_FRONTIER_AT_TRUE_SUPPORT"
                        for row in cells
                    )
                    / len(cells),
                    "unconditional_truth_coverage_rate": _mean_bool(
                        cells, "truth_covered"
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
            instance = generate_instance(seed, capacity)
            instance_rows.append(evaluate_instance(instance))
            for retained in TRUNCATION_LEVELS:
                truncation_rows.append(evaluate_truncation(instance, retained))
    return {
        "report_version": "relation-incomplete-event-truth-benchmark/v1",
        "design": {
            "capacities": [2, 3],
            "instances_per_capacity": instances_per_capacity,
            "core_rows_per_instance": 3,
            "buffer_rows_per_instance": 8,
            "thresholds": list(THRESHOLDS),
            "candidate_retention_levels": list(TRUNCATION_LEVELS),
            "truth_used_as_model_input": False,
            "candidate_ranking_uses_public_outcome": False,
        },
        "summary": summarize(instance_rows, truncation_rows),
        "instances": instance_rows,
        "candidate_truncation_cells": truncation_rows,
        "claim_boundary": {
            "supported": (
                "method and baseline behavior under the declared semi-synthetic "
                "ordered-event generator with known truth"
            ),
            "not_supported": (
                "actual partner or event recovery in Chicago, NYC, or any other "
                "operational system"
            ),
        },
    }


def render(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Relation-incomplete event-stream truth benchmark",
        "",
        "Truth labels generate and evaluate the instances but are not supplied to "
        "the frontier or point baselines.",
        "",
        f"Full-universe truth coverage: **{100 * summary['truth_coverage_rate']:.1f}%** "
        f"over **{summary['instance_count']}** instances.",
        "",
        "| C | Instances | Median width | Feasible-point MAE | Feasible-point decision error | Nearest-q infeasible | Nearest-q outside frontier | Component mask unreachable | Pairwise underselects truth |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for capacity, cell in sorted(summary["by_capacity"].items()):
        lines.append(
            f"| {capacity} | {cell['instance_count']} | "
            f"{cell['median_frontier_width']:.3f} | "
            f"{cell['mean_feasible_point_absolute_error']:.3f} | "
            f"{100 * cell['feasible_point_threshold_error_rate']:.1f}% | "
            f"{100 * cell['nearest_q_infeasible_rate']:.1f}% | "
            f"{100 * cell['nearest_q_outside_frontier_rate']:.1f}% | "
            f"{100 * cell['component_mask_unreachable_rate']:.1f}% | "
            f"{100 * cell['pairwise_underselection_rate']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Candidate-support truncation",
            "",
            "| C | Retained buffers | Mean true-member recall | All truth retained | Frontier available at true q | Unconditional truth coverage |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for cell in summary["candidate_truncation"]:
        lines.append(
            f"| {cell['capacity']} | {cell['retained_buffer_count']} | "
            f"{100 * cell['mean_true_member_recall']:.1f}% | "
            f"{100 * cell['all_true_members_retained_rate']:.1f}% | "
            f"{100 * cell['frontier_available_at_true_support_rate']:.1f}% | "
            f"{100 * cell['unconditional_truth_coverage_rate']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "A feasible point reconstruction is necessarily inside the certified "
            "frontier, but it can still choose the wrong side of a policy threshold. "
            "The frontier then correctly reports that the decision is not identified. "
            "Naive nearest-row and connected-component rules may select a mask that "
            "no capacity-respecting event decomposition can attain. Candidate "
            "truncation is a separate failure mode: certification cannot cover a true "
            "event member that was removed before optimization.",
            "",
            "This is semi-synthetic method validation, not evidence of actual "
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
    for cell in report["summary"]["candidate_truncation"]:
        assert 0.0 <= cell["unconditional_truth_coverage_rate"] <= 1.0
    print("relation-incomplete event benchmark self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances-per-capacity", type=int, default=200)
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
