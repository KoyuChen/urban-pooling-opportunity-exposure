#!/usr/bin/env python3
"""Decision-focused selective-disclosure benchmark for EventFrontier.

The benchmark asks a different question from latent relation recovery. Given a
realized controlled-truth world and a downstream binary decision, how many
truthful relation facts are sufficient to certify that decision against every
other feasible event world?

Two audit interfaces are studied.

1. ``row usage`` asks whether an optional buffer belongs to any selected event.
   This is sufficient for selected-member means once the support count is fixed.
2. ``pair co-membership`` asks whether two active rows belong to the same event.
   This is needed for genuinely partition-dependent targets such as event count.

For a realized world F* and an opposite-decision world F, every certificate must
query at least one atom on which F* and F disagree. Thus the minimum realized
certificate is an exact hitting set over opposite-world disagreement sets. The
small controlled cohorts permit complete feasible-world enumeration and exact
mixed-integer solution of that hitting set.

This is controlled synthetic method exploration. It does not estimate the
amount of private information available from Chicago, NYC, or any platform.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from functools import lru_cache
import itertools
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

import event_frontier_truth_benchmark as canonical
import event_frontier_truth_benchmark_scale as scaled

TOL = canonical.TOL
DEFAULT_THRESHOLDS = tuple(float(value) for value in canonical.THRESHOLDS)


@dataclass(frozen=True)
class PartitionWorld:
    """One exact partition of all cores and a fixed selected-buffer set."""

    event_masks: tuple[int, ...]
    event_count: int


def _member_mask(indices: Iterable[int]) -> int:
    return sum(1 << int(index) for index in indices)


def _buffer_positions(master: Any) -> tuple[int, ...]:
    return tuple(
        position for position, row in enumerate(master.rows) if row.role == "buffer"
    )


def _buffer_values(master: Any) -> dict[int, float]:
    values: dict[int, float] = {}
    for position, row in enumerate(master.rows):
        if row.role != "buffer":
            continue
        if row.miles is None:
            raise ValueError("controlled benchmark requires a public buffer outcome")
        values[position] = float(row.miles)
    return values


def _mean(mask: int, values: Mapping[int, float], q: int) -> float:
    if q <= 0:
        raise ValueError("selected support q must be positive")
    selected = [value for position, value in values.items() if mask & (1 << position)]
    if len(selected) != q:
        raise ValueError("mask cardinality does not equal declared support")
    return sum(selected) / q


def _decision(mask: int, values: Mapping[int, float], q: int, threshold: float) -> bool:
    return _mean(mask, values, q) >= threshold - TOL


def _inclusion_minimal_sets(sets: Iterable[frozenset[int]]) -> list[frozenset[int]]:
    """Remove duplicate and superset constraints from a hitting-set instance."""

    unique = sorted(set(sets), key=lambda item: (len(item), tuple(sorted(item))))
    minimal: list[frozenset[int]] = []
    for candidate in unique:
        if not candidate:
            raise ValueError("an opposite world has no disagreeing audit atom")
        if any(existing <= candidate for existing in minimal):
            continue
        minimal.append(candidate)
    return minimal


def _minimum_hitting_set(
    disagreement_sets: Iterable[frozenset[int]],
    atom_universe: Sequence[int],
) -> tuple[int, tuple[int, ...]]:
    """Solve an exact unit-cost hitting set and independently replay it."""

    sets = _inclusion_minimal_sets(disagreement_sets)
    if not sets:
        return 0, ()
    atoms = tuple(atom_universe)
    atom_to_column = {atom: column for column, atom in enumerate(atoms)}
    matrix = np.zeros((len(sets), len(atoms)), dtype=float)
    for row, disagreement in enumerate(sets):
        for atom in disagreement:
            matrix[row, atom_to_column[atom]] = 1.0
    result = milp(
        c=np.ones(len(atoms), dtype=float),
        integrality=np.ones(len(atoms), dtype=int),
        bounds=Bounds(np.zeros(len(atoms)), np.ones(len(atoms))),
        constraints=LinearConstraint(
            matrix,
            np.ones(len(sets)),
            np.full(len(sets), np.inf),
        ),
        options={"time_limit": 30.0, "mip_rel_gap": 0.0},
    )
    if not result.success or result.x is None or result.fun is None:
        raise RuntimeError(f"certificate hitting set unresolved: {result.message}")
    chosen = tuple(atoms[index] for index, value in enumerate(result.x) if value >= 0.5)
    if any(not (set(chosen) & set(disagreement)) for disagreement in sets):
        raise AssertionError("certificate failed independent hitting-set replay")
    objective = int(round(float(result.fun)))
    if objective != len(chosen):
        raise AssertionError("certificate objective and rounded support disagree")
    return objective, chosen


def minimum_usage_certificate(
    feasible_masks: Sequence[int],
    true_mask: int,
    values: Mapping[int, float],
    q: int,
    threshold: float,
    buffer_positions: Sequence[int],
) -> dict[str, Any]:
    """Minimum row-usage facts that rule out every opposite mean decision."""

    true_decision = _decision(true_mask, values, q, threshold)
    opposite = [
        mask
        for mask in feasible_masks
        if _decision(mask, values, q, threshold) != true_decision
    ]
    if not opposite:
        return {
            "ambiguous_before_disclosure": False,
            "opposite_world_count": 0,
            "minimum_certificate_size": 0,
            "fixed_support_upper_bound": 0,
        }
    disagreement = [
        frozenset(
            position
            for position in buffer_positions
            if bool(true_mask & (1 << position)) != bool(mask & (1 << position))
        )
        for mask in opposite
    ]
    size, _chosen = _minimum_hitting_set(disagreement, buffer_positions)
    selected = sum(bool(true_mask & (1 << position)) for position in buffer_positions)
    upper_bound = min(selected, len(buffer_positions) - selected)
    if size > upper_bound:
        raise AssertionError("fixed-support row-usage certificate exceeded trivial bound")
    return {
        "ambiguous_before_disclosure": True,
        "opposite_world_count": len(opposite),
        "minimum_certificate_size": size,
        "fixed_support_upper_bound": upper_bound,
    }


def optimal_adaptive_usage_policy(
    feasible_masks: Sequence[int],
    true_mask: int,
    values: Mapping[int, float],
    q: int,
    threshold: float,
    buffer_positions: Sequence[int],
) -> dict[str, Any]:
    """Optimal minimax decision tree over row-usage questions."""

    worlds = tuple(sorted(set(int(mask) for mask in feasible_masks)))
    labels = {mask: _decision(mask, values, q, threshold) for mask in worlds}
    positions = tuple(sorted(int(position) for position in buffer_positions))

    def resolved(state: tuple[int, ...]) -> bool:
        return len({labels[mask] for mask in state}) <= 1

    @lru_cache(maxsize=None)
    def value(state: tuple[int, ...], remaining: tuple[int, ...]) -> int:
        if resolved(state):
            return 0
        best = math.inf
        for position in remaining:
            zero = tuple(mask for mask in state if not mask & (1 << position))
            one = tuple(mask for mask in state if mask & (1 << position))
            if not zero or not one:
                continue
            next_remaining = tuple(item for item in remaining if item != position)
            candidate = 1 + max(
                value(zero, next_remaining),
                value(one, next_remaining),
            )
            best = min(best, candidate)
        if not math.isfinite(best):
            raise AssertionError("usage atoms cannot separate opposite decisions")
        return int(best)

    worst_case = value(worlds, positions)
    state = worlds
    remaining = positions
    realized = 0
    while not resolved(state):
        candidates: list[tuple[int, int]] = []
        for position in remaining:
            zero = tuple(mask for mask in state if not mask & (1 << position))
            one = tuple(mask for mask in state if mask & (1 << position))
            if not zero or not one:
                continue
            next_remaining = tuple(item for item in remaining if item != position)
            candidates.append(
                (
                    1
                    + max(
                        value(zero, next_remaining),
                        value(one, next_remaining),
                    ),
                    position,
                )
            )
        _bound, chosen = min(candidates)
        state = tuple(
            mask
            for mask in state
            if bool(mask & (1 << chosen)) == bool(true_mask & (1 << chosen))
        )
        remaining = tuple(item for item in remaining if item != chosen)
        realized += 1
    return {
        "minimax_worst_case_queries": worst_case,
        "realized_queries": realized,
    }


def _enumerate_partitions_at_mask(
    master: Any,
    target_buffer_mask: int,
    *,
    maximum_worlds: int,
) -> list[PartitionWorld]:
    """Enumerate unlabeled partitions using the first-uncovered-core pivot."""

    worlds: list[PartitionWorld] = []

    def recurse(
        covered_core: int,
        used_buffer: int,
        event_masks: tuple[int, ...],
    ) -> None:
        if len(worlds) > maximum_worlds:
            raise RuntimeError("partition-world enumeration limit exceeded")
        if covered_core == master.all_core_mask:
            if used_buffer == target_buffer_mask:
                worlds.append(
                    PartitionWorld(
                        event_masks=tuple(sorted(event_masks)),
                        event_count=len(event_masks),
                    )
                )
            return
        uncovered = master.all_core_mask & ~covered_core
        pivot_bit = uncovered & -uncovered
        pivot = pivot_bit.bit_length() - 1
        for column in master.columns_by_core_position[pivot]:
            if column.core_mask & covered_core:
                continue
            if column.buffer_mask & used_buffer:
                continue
            if column.buffer_mask & ~target_buffer_mask:
                continue
            recurse(
                covered_core | column.core_mask,
                used_buffer | column.buffer_mask,
                event_masks + (column.member_mask,),
            )

    recurse(0, 0, ())
    unique = {world.event_masks: world for world in worlds}
    return [unique[key] for key in sorted(unique)]


def _pair_signature(event_masks: Sequence[int], pairs: Sequence[tuple[int, int]]) -> int:
    signature = 0
    for atom, (left, right) in enumerate(pairs):
        together = any(
            mask & (1 << left) and mask & (1 << right) for mask in event_masks
        )
        if together:
            signature |= 1 << atom
    return signature


def minimum_pair_certificate_for_event_count(
    master: Any,
    instance: Any,
    *,
    event_count_cutoff: int = 2,
    maximum_worlds: int = 200_000,
) -> dict[str, Any]:
    """Certify ``event_count <= cutoff`` using same-event pair facts."""

    true_buffer_mask = _member_mask(instance.true_buffer_indices)
    worlds = _enumerate_partitions_at_mask(
        master,
        true_buffer_mask,
        maximum_worlds=maximum_worlds,
    )
    true_events = tuple(_member_mask(run) for run in instance.true_runs)
    true_count = len(true_events)
    true_decision = true_count <= event_count_cutoff
    opposite = [
        world
        for world in worlds
        if (world.event_count <= event_count_cutoff) != true_decision
    ]
    counts = [world.event_count for world in worlds]
    if not opposite:
        return {
            "partition_world_count": len(worlds),
            "minimum_event_count": min(counts),
            "maximum_event_count": max(counts),
            "ambiguous_before_disclosure": False,
            "row_usage_can_resolve": True,
            "minimum_pair_certificate_size": 0,
        }

    active = tuple(
        position
        for position in range(len(master.rows))
        if master.all_core_mask & (1 << position)
        or true_buffer_mask & (1 << position)
    )
    pairs = tuple(itertools.combinations(active, 2))
    true_signature = _pair_signature(true_events, pairs)
    disagreement = []
    for world in opposite:
        signature = _pair_signature(world.event_masks, pairs)
        differing = frozenset(
            atom
            for atom in range(len(pairs))
            if bool(true_signature & (1 << atom))
            != bool(signature & (1 << atom))
        )
        disagreement.append(differing)
    size, _chosen = _minimum_hitting_set(disagreement, tuple(range(len(pairs))))
    return {
        "partition_world_count": len(worlds),
        "minimum_event_count": min(counts),
        "maximum_event_count": max(counts),
        "ambiguous_before_disclosure": True,
        "row_usage_can_resolve": False,
        "opposite_partition_count": len(opposite),
        "pair_atom_count": len(pairs),
        "minimum_pair_certificate_size": size,
    }


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = int(math.ceil(probability * len(ordered))) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def _describe(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p90": None,
            "maximum": None,
        }
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p90": _quantile(values, 0.90),
        "maximum": max(values),
    }


def _usage_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ambiguous = [row for row in rows if row["ambiguous_before_disclosure"]]
    sizes = [float(row["minimum_certificate_size"]) for row in ambiguous]
    by_cell: list[dict[str, Any]] = []
    for capacity in sorted({int(row["capacity"]) for row in rows}):
        for threshold in sorted({float(row["threshold"]) for row in rows}):
            selected = [
                row
                for row in rows
                if int(row["capacity"]) == capacity
                and abs(float(row["threshold"]) - threshold) <= TOL
            ]
            selected_ambiguous = [
                row for row in selected if row["ambiguous_before_disclosure"]
            ]
            cell_sizes = [
                float(row["minimum_certificate_size"])
                for row in selected_ambiguous
            ]
            by_cell.append(
                {
                    "capacity": capacity,
                    "threshold": threshold,
                    "comparison_count": len(selected),
                    "ambiguity_rate": len(selected_ambiguous) / len(selected),
                    **{
                        f"conditional_certificate_{key}": value
                        for key, value in _describe(cell_sizes).items()
                    },
                    "conditional_certificate_at_most_1_rate": (
                        sum(value <= 1 for value in cell_sizes) / len(cell_sizes)
                        if cell_sizes
                        else None
                    ),
                    "conditional_certificate_at_most_2_rate": (
                        sum(value <= 2 for value in cell_sizes) / len(cell_sizes)
                        if cell_sizes
                        else None
                    ),
                    "conditional_certificate_at_most_3_rate": (
                        sum(value <= 3 for value in cell_sizes) / len(cell_sizes)
                        if cell_sizes
                        else None
                    ),
                }
            )
    return {
        "comparison_count": len(rows),
        "ambiguous_comparison_count": len(ambiguous),
        "ambiguity_rate": len(ambiguous) / len(rows),
        "conditional_minimum_certificate": _describe(sizes),
        "conditional_certificate_at_most_1_rate": (
            sum(value <= 1 for value in sizes) / len(sizes) if sizes else None
        ),
        "conditional_certificate_at_most_2_rate": (
            sum(value <= 2 for value in sizes) / len(sizes) if sizes else None
        ),
        "conditional_certificate_at_most_3_rate": (
            sum(value <= 3 for value in sizes) / len(sizes) if sizes else None
        ),
        "by_capacity_threshold": by_cell,
    }


def _adaptive_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ambiguous = [row for row in rows if row["ambiguous_before_disclosure"]]
    return {
        "comparison_count": len(rows),
        "ambiguous_comparison_count": len(ambiguous),
        "conditional_realized_queries": _describe(
            [float(row["realized_queries"]) for row in ambiguous]
        ),
        "conditional_minimax_worst_case_queries": _describe(
            [float(row["minimax_worst_case_queries"]) for row in ambiguous]
        ),
    }


def _partition_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ambiguous = [row for row in rows if row["ambiguous_before_disclosure"]]
    by_capacity: list[dict[str, Any]] = []
    for capacity in sorted({int(row["capacity"]) for row in rows}):
        selected = [row for row in rows if int(row["capacity"]) == capacity]
        selected_ambiguous = [
            row for row in selected if row["ambiguous_before_disclosure"]
        ]
        by_capacity.append(
            {
                "capacity": capacity,
                "instance_count": len(selected),
                "event_count_ambiguity_rate": len(selected_ambiguous) / len(selected),
                "mean_event_count_width": statistics.fmean(
                    float(row["maximum_event_count"])
                    - float(row["minimum_event_count"])
                    for row in selected
                ),
                "conditional_minimum_pair_certificate": _describe(
                    [
                        float(row["minimum_pair_certificate_size"])
                        for row in selected_ambiguous
                    ]
                ),
                "ambiguous_cells_resolvable_by_row_usage": sum(
                    bool(row["row_usage_can_resolve"]) for row in selected_ambiguous
                ),
            }
        )
    return {
        "instance_count": len(rows),
        "ambiguous_instance_count": len(ambiguous),
        "event_count_ambiguity_rate": len(ambiguous) / len(rows),
        "conditional_minimum_pair_certificate": _describe(
            [float(row["minimum_pair_certificate_size"]) for row in ambiguous]
        ),
        "by_capacity": by_capacity,
    }


def run(
    *,
    instances_per_capacity: int,
    adaptive_instances_per_capacity: int,
    partition_instances_per_capacity: int,
    base_seed: int,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    if instances_per_capacity <= 0:
        raise ValueError("instances_per_capacity must be positive")
    if not (0 <= adaptive_instances_per_capacity <= instances_per_capacity):
        raise ValueError("adaptive count must lie between zero and the main count")
    if not (0 <= partition_instances_per_capacity <= instances_per_capacity):
        raise ValueError("partition count must lie between zero and the main count")

    usage_rows: list[dict[str, Any]] = []
    adaptive_rows: list[dict[str, Any]] = []
    partition_rows: list[dict[str, Any]] = []
    for capacity in scaled.CAPACITIES:
        for offset in range(instances_per_capacity):
            seed = base_seed + capacity * 1_000_000 + offset
            instance = scaled.generate_instance(seed, capacity)
            master = canonical.base.exact.build_master(
                instance.rows,
                capacity,
                epsilon=0.1,
            )
            true_mask = _member_mask(instance.true_buffer_indices)
            q = true_mask.bit_count()
            masks = tuple(
                sorted(
                    mask
                    for mask in master.reachable_buffer_masks
                    if mask.bit_count() == q
                )
            )
            if true_mask not in masks:
                raise AssertionError("generated true selected set is not feasible")
            values = _buffer_values(master)
            positions = _buffer_positions(master)
            for threshold in thresholds:
                certificate = minimum_usage_certificate(
                    masks,
                    true_mask,
                    values,
                    q,
                    float(threshold),
                    positions,
                )
                row = {
                    "seed": seed,
                    "capacity": capacity,
                    "threshold": float(threshold),
                    "true_selected_buffer_count": q,
                    "feasible_selected_set_count": len(masks),
                    **certificate,
                }
                usage_rows.append(row)
                if offset < adaptive_instances_per_capacity:
                    policy = optimal_adaptive_usage_policy(
                        masks,
                        true_mask,
                        values,
                        q,
                        float(threshold),
                        positions,
                    )
                    adaptive_rows.append({**row, **policy})
            if offset < partition_instances_per_capacity:
                partition = minimum_pair_certificate_for_event_count(master, instance)
                partition_rows.append(
                    {
                        "seed": seed,
                        "capacity": capacity,
                        "true_event_count": len(instance.true_runs),
                        "decision": "event_count_at_most_2",
                        **partition,
                    }
                )

    return {
        "report_version": "eventfrontier-selective-disclosure/v1",
        "design": {
            "capacities": list(scaled.CAPACITIES),
            "instances_per_capacity": instances_per_capacity,
            "adaptive_instances_per_capacity": adaptive_instances_per_capacity,
            "partition_instances_per_capacity": partition_instances_per_capacity,
            "thresholds": [float(value) for value in thresholds],
            "usage_atoms": "selected in any event",
            "pair_atoms": "same latent event",
            "composition_task_conditioned_on_true_support_count": True,
            "event_count_task_conditioned_on_complete_true_selected_set": True,
            "truth_used_only_for_oracle_answers_and_evaluation": True,
        },
        "usage_certificates": _usage_summary(usage_rows),
        "adaptive_usage_policy": _adaptive_summary(adaptive_rows),
        "partition_certificates": _partition_summary(partition_rows),
        "usage_cells": usage_rows,
        "adaptive_cells": adaptive_rows,
        "partition_cells": partition_rows,
        "claim_boundary": {
            "supported": (
                "exact realized-world and minimax query counts under the declared "
                "controlled generator, fixed support, audit atoms, and thresholds"
            ),
            "not_supported": (
                "availability, cost, legality, or accuracy of private relation queries "
                "in Chicago, NYC, or an operational platform"
            ),
        },
    }


def _percent(value: float | None) -> str:
    return "--" if value is None else f"{100.0 * value:.1f}%"


def render(report: Mapping[str, Any]) -> str:
    usage = report["usage_certificates"]
    adaptive = report["adaptive_usage_policy"]
    partition = report["partition_certificates"]
    cert = usage["conditional_minimum_certificate"]
    lines = [
        "# Decision-focused selective disclosure",
        "",
        "The benchmark asks for the smallest truthful relation certificate that "
        "rules out every feasible world with the opposite downstream decision. "
        "It does not try to reconstruct the entire latent event partition.",
        "",
        "## Selected-member mean decisions",
        "",
        f"Across **{usage['comparison_count']}** capacity-threshold comparisons, "
        f"**{usage['ambiguous_comparison_count']}** "
        f"({_percent(usage['ambiguity_rate'])}) are initially ambiguous. Conditional "
        f"on ambiguity, the minimum row-usage certificate has mean "
        f"**{cert['mean']:.2f}**, median **{cert['median']:.0f}**, 90th percentile "
        f"**{cert['p90']:.0f}**, and maximum **{cert['maximum']:.0f}** facts.",
        "",
        f"One fact suffices in {_percent(usage['conditional_certificate_at_most_1_rate'])}; "
        f"two facts suffice in {_percent(usage['conditional_certificate_at_most_2_rate'])}; "
        f"three facts suffice in {_percent(usage['conditional_certificate_at_most_3_rate'])}.",
        "",
        "| C | Threshold | Ambiguity | Mean cert. | Median | P90 | Max | <=1 | <=2 | <=3 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in usage["by_capacity_threshold"]:
        lines.append(
            f"| {row['capacity']} | {row['threshold']:.2f} | "
            f"{_percent(row['ambiguity_rate'])} | "
            f"{row['conditional_certificate_mean']:.2f} | "
            f"{row['conditional_certificate_median']:.0f} | "
            f"{row['conditional_certificate_p90']:.0f} | "
            f"{row['conditional_certificate_maximum']:.0f} | "
            f"{_percent(row['conditional_certificate_at_most_1_rate'])} | "
            f"{_percent(row['conditional_certificate_at_most_2_rate'])} | "
            f"{_percent(row['conditional_certificate_at_most_3_rate'])} |"
        )
    lines += ["", "## Adaptive audit interface", ""]
    if adaptive["ambiguous_comparison_count"]:
        realized = adaptive["conditional_realized_queries"]
        worst = adaptive["conditional_minimax_worst_case_queries"]
        lines.append(
            f"On the adaptive subset, the optimal minimax policy uses a median of "
            f"**{realized['median']:.0f}** realized queries; its median worst-case "
            f"depth is **{worst['median']:.0f}** and maximum is **{worst['maximum']:.0f}**."
        )
    else:
        lines.append("Adaptive evaluation was disabled.")
    lines += ["", "## Partition-dependent event count", ""]
    if partition["instance_count"]:
        pair = partition["conditional_minimum_pair_certificate"]
        lines.append(
            f"Even after revealing the complete selected-row set, event count remains "
            f"ambiguous in {_percent(partition['event_count_ambiguity_rate'])} of "
            f"**{partition['instance_count']}** instances. Row-usage facts cannot resolve "
            f"these cells. Same-event pair facts do: the minimum pair certificate has "
            f"median **{pair['median']:.0f}** and maximum **{pair['maximum']:.0f}**."
        )
        lines += [
            "",
            "| C | Instances | Event-count ambiguity | Mean width | Mean pair cert. | Median | Max |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in partition["by_capacity"]:
            cell = row["conditional_minimum_pair_certificate"]
            lines.append(
                f"| {row['capacity']} | {row['instance_count']} | "
                f"{_percent(row['event_count_ambiguity_rate'])} | "
                f"{row['mean_event_count_width']:.2f} | {cell['mean']:.2f} | "
                f"{cell['median']:.0f} | {cell['maximum']:.0f} |"
            )
    else:
        lines.append("Partition-dependent evaluation was disabled.")
    lines += [
        "",
        "The certificate problem is an exact hitting set over opposite-world "
        "disagreement sets. An implicit large-instance implementation can alternate "
        "between a hitting-set master and an EventFrontier separation solve that "
        "searches for an opposite-decision world consistent with the queried facts.",
        "",
        "These are controlled-truth audit costs, not claims that city releases or "
        "platforms currently expose the queried facts.",
        "",
    ]
    return "\n".join(lines)


def _write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("status\nNO_ROWS\n", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    report = run(
        instances_per_capacity=2,
        adaptive_instances_per_capacity=1,
        partition_instances_per_capacity=1,
        base_seed=20260904,
    )
    assert report["usage_certificates"]["comparison_count"] == 18
    for row in report["usage_cells"]:
        assert row["minimum_certificate_size"] <= row["fixed_support_upper_bound"]
    for row in report["partition_cells"]:
        if row["ambiguous_before_disclosure"]:
            assert row["row_usage_can_resolve"] is False
            assert row["minimum_pair_certificate_size"] >= 1
    print("selective disclosure benchmark self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances-per-capacity", type=int, default=1000)
    parser.add_argument("--adaptive-instances-per-capacity", type=int, default=200)
    parser.add_argument("--partition-instances-per-capacity", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=20260902)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output_dir is None:
        parser.error("--output-dir is required unless --self-test is used")
    report = run(
        instances_per_capacity=args.instances_per_capacity,
        adaptive_instances_per_capacity=args.adaptive_instances_per_capacity,
        partition_instances_per_capacity=args.partition_instances_per_capacity,
        base_seed=args.base_seed,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    _write_csv(report["usage_cells"], args.output_dir / "usage_cells.csv")
    _write_csv(report["adaptive_cells"], args.output_dir / "adaptive_cells.csv")
    _write_csv(report["partition_cells"], args.output_dir / "partition_cells.csv")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
