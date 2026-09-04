#!/usr/bin/env python3
"""Compare decision certificates with certificates for full relation recovery.

The comparison isolates the value of the decision-focused target. Row-usage
facts identify a selected-buffer set; pair co-membership facts identify a
partition of a fixed active set. All quantities are exact on the controlled
small instances.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping, Sequence

import event_frontier_truth_benchmark as canonical
import event_frontier_truth_benchmark_scale as scaled
import selective_disclosure_benchmark as disclosure


def minimum_small_hitting_set(
    cuts: Iterable[frozenset[int]], atoms: Sequence[int]
) -> int:
    cuts = disclosure._inclusion_minimal_sets(cuts)
    if not cuts:
        return 0
    for size in range(1, len(atoms) + 1):
        for chosen in itertools.combinations(atoms, size):
            chosen_set = set(chosen)
            if all(chosen_set & set(cut) for cut in cuts):
                return size
    raise AssertionError("finite hitting-set instance has no solution")


def full_usage_certificate(
    feasible_masks: Sequence[int], true_mask: int, atoms: Sequence[int]
) -> int:
    cuts = [
        frozenset(
            atom
            for atom in atoms
            if bool(mask & (1 << atom)) != bool(true_mask & (1 << atom))
        )
        for mask in feasible_masks
        if mask != true_mask
    ]
    return minimum_small_hitting_set(cuts, atoms)


def decision_usage_certificate(
    feasible_masks: Sequence[int],
    true_mask: int,
    values: Mapping[int, float],
    q: int,
    threshold: float,
    atoms: Sequence[int],
) -> tuple[bool, int]:
    true_decision = disclosure._decision(true_mask, values, q, threshold)
    cuts = [
        frozenset(
            atom
            for atom in atoms
            if bool(mask & (1 << atom)) != bool(true_mask & (1 << atom))
        )
        for mask in feasible_masks
        if disclosure._decision(mask, values, q, threshold) != true_decision
    ]
    return bool(cuts), minimum_small_hitting_set(cuts, atoms)


def full_pair_certificate(
    signatures: Sequence[int], true_signature: int, atom_count: int
) -> int:
    cuts = [
        frozenset(
            atom
            for atom in range(atom_count)
            if bool(signature & (1 << atom))
            != bool(true_signature & (1 << atom))
        )
        for signature in signatures
        if signature != true_signature
    ]
    return disclosure._minimum_hitting_set(cuts, tuple(range(atom_count)))[0]


def decision_pair_certificate(
    worlds: Sequence[Any],
    signatures: Sequence[int],
    true_signature: int,
    true_event_count: int,
    atom_count: int,
    cutoff: int = 2,
) -> tuple[bool, int]:
    true_decision = true_event_count <= cutoff
    cuts = [
        frozenset(
            atom
            for atom in range(atom_count)
            if bool(signature & (1 << atom))
            != bool(true_signature & (1 << atom))
        )
        for world, signature in zip(worlds, signatures)
        if (world.event_count <= cutoff) != true_decision
    ]
    return bool(cuts), disclosure._minimum_hitting_set(
        cuts, tuple(range(atom_count))
    )[0]


def describe(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p90": None,
            "maximum": None,
        }
    ordered = sorted(float(value) for value in values)
    p90 = ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]
    return {
        "count": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p90": p90,
        "maximum": max(ordered),
    }


def run(
    usage_instances_per_capacity: int,
    partition_instances_per_capacity: int,
    base_seed: int,
) -> dict[str, Any]:
    usage_rows: list[dict[str, Any]] = []
    partition_rows: list[dict[str, Any]] = []

    for capacity in scaled.CAPACITIES:
        for offset in range(usage_instances_per_capacity):
            seed = base_seed + capacity * 1_000_000 + offset
            instance = scaled.generate_instance(seed, capacity)
            master = canonical.base.exact.build_master(
                instance.rows, capacity, epsilon=0.1
            )
            true_mask = disclosure._member_mask(instance.true_buffer_indices)
            q = true_mask.bit_count()
            atoms = disclosure._buffer_positions(master)
            values = disclosure._buffer_values(master)
            masks = tuple(
                sorted(
                    mask
                    for mask in master.reachable_buffer_masks
                    if mask.bit_count() == q
                )
            )
            full_size = full_usage_certificate(masks, true_mask, atoms)
            for threshold in disclosure.DEFAULT_THRESHOLDS:
                ambiguous, decision_size = decision_usage_certificate(
                    masks, true_mask, values, q, threshold, atoms
                )
                usage_rows.append(
                    {
                        "seed": seed,
                        "capacity": capacity,
                        "threshold": threshold,
                        "ambiguous_before_disclosure": ambiguous,
                        "decision_certificate_size": decision_size,
                        "full_selected_set_certificate_size": full_size,
                        "facts_saved": full_size - decision_size,
                        "decision_to_full_ratio": (
                            decision_size / full_size if full_size else 0.0
                        ),
                    }
                )

            if offset >= partition_instances_per_capacity:
                continue
            selected = true_mask
            worlds = disclosure._enumerate_partitions_at_mask(
                master, selected, maximum_worlds=200_000
            )
            true_events = tuple(
                disclosure._member_mask(run_members) for run_members in instance.true_runs
            )
            active = tuple(
                position
                for position in range(len(master.rows))
                if master.all_core_mask & (1 << position)
                or selected & (1 << position)
            )
            pairs = tuple(itertools.combinations(active, 2))
            signatures = tuple(
                disclosure._pair_signature(world.event_masks, pairs) for world in worlds
            )
            true_signature = disclosure._pair_signature(true_events, pairs)
            full_size = full_pair_certificate(
                signatures, true_signature, len(pairs)
            )
            ambiguous, decision_size = decision_pair_certificate(
                worlds,
                signatures,
                true_signature,
                len(true_events),
                len(pairs),
            )
            partition_rows.append(
                {
                    "seed": seed,
                    "capacity": capacity,
                    "partition_world_count": len(worlds),
                    "ambiguous_before_disclosure": ambiguous,
                    "decision_certificate_size": decision_size,
                    "full_partition_certificate_size": full_size,
                    "facts_saved": full_size - decision_size,
                    "decision_to_full_ratio": (
                        decision_size / full_size if full_size else 0.0
                    ),
                }
            )

    ambiguous_usage = [
        row for row in usage_rows if row["ambiguous_before_disclosure"]
    ]
    ambiguous_partition = [
        row for row in partition_rows if row["ambiguous_before_disclosure"]
    ]

    return {
        "report_version": "eventfrontier-selective-disclosure-recovery-gap/v1",
        "design": {
            "capacities": list(scaled.CAPACITIES),
            "usage_instances_per_capacity": usage_instances_per_capacity,
            "partition_instances_per_capacity": partition_instances_per_capacity,
            "thresholds": list(disclosure.DEFAULT_THRESHOLDS),
            "composition_conditioned_on_true_support_count": True,
            "partition_conditioned_on_complete_true_selected_set": True,
        },
        "usage_summary": {
            "comparison_count": len(usage_rows),
            "ambiguous_comparison_count": len(ambiguous_usage),
            "decision_certificate": describe(
                [row["decision_certificate_size"] for row in ambiguous_usage]
            ),
            "full_selected_set_certificate": describe(
                [
                    row["full_selected_set_certificate_size"]
                    for row in ambiguous_usage
                ]
            ),
            "facts_saved": describe(
                [row["facts_saved"] for row in ambiguous_usage]
            ),
            "decision_to_full_ratio": describe(
                [row["decision_to_full_ratio"] for row in ambiguous_usage]
            ),
            "strict_savings_rate": (
                sum(row["facts_saved"] > 0 for row in ambiguous_usage)
                / len(ambiguous_usage)
                if ambiguous_usage
                else None
            ),
        },
        "partition_summary": {
            "instance_count": len(partition_rows),
            "ambiguous_instance_count": len(ambiguous_partition),
            "decision_certificate": describe(
                [row["decision_certificate_size"] for row in ambiguous_partition]
            ),
            "full_partition_certificate": describe(
                [row["full_partition_certificate_size"] for row in ambiguous_partition]
            ),
            "facts_saved": describe(
                [row["facts_saved"] for row in ambiguous_partition]
            ),
            "decision_to_full_ratio": describe(
                [row["decision_to_full_ratio"] for row in ambiguous_partition]
            ),
            "strict_savings_rate": (
                sum(row["facts_saved"] > 0 for row in ambiguous_partition)
                / len(ambiguous_partition)
                if ambiguous_partition
                else None
            ),
        },
        "usage_cells": usage_rows,
        "partition_cells": partition_rows,
        "claim_boundary": {
            "supported": "exact information savings under the controlled generator and audit atom families",
            "not_supported": "operational query costs, privacy utility, or transfer to public city data",
        },
    }


def render(report: Mapping[str, Any]) -> str:
    usage = report["usage_summary"]
    partition = report["partition_summary"]
    return "\n".join(
        [
            "# Decision certification versus full relation recovery",
            "",
            f"Among {usage['ambiguous_comparison_count']} ambiguous selected-mean comparisons, the minimum decision certificate has mean **{usage['decision_certificate']['mean']:.2f}** facts, versus **{usage['full_selected_set_certificate']['mean']:.2f}** to identify the complete selected set. Strict savings occur in **{100 * usage['strict_savings_rate']:.1f}%** of cells; the mean decision/full ratio is **{usage['decision_to_full_ratio']['mean']:.3f}**.",
            "",
            f"Among {partition['ambiguous_instance_count']} ambiguous event-count instances, the minimum decision certificate has mean **{partition['decision_certificate']['mean']:.2f}** pair facts, versus **{partition['full_partition_certificate']['mean']:.2f}** to identify the complete partition. Strict savings occur in **{100 * partition['strict_savings_rate']:.1f}%** of cells; the mean decision/full ratio is **{partition['decision_to_full_ratio']['mean']:.3f}**.",
            "",
            "The comparison is exact for the controlled small instances and does not assign a real-world cost to a relation query.",
            "",
        ]
    )


def self_test() -> None:
    report = run(2, 1, 20260906)
    assert report["usage_summary"]["comparison_count"] == 18
    assert report["partition_summary"]["instance_count"] == 3
    for row in report["usage_cells"]:
        assert row["decision_certificate_size"] <= row[
            "full_selected_set_certificate_size"
        ]
    for row in report["partition_cells"]:
        assert row["decision_certificate_size"] <= row[
            "full_partition_certificate_size"
        ]
    print("selective disclosure recovery-gap self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage-instances-per-capacity", type=int, default=1000)
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
        args.usage_instances_per_capacity,
        args.partition_instances_per_capacity,
        args.base_seed,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    compact = {
        key: value
        for key, value in report.items()
        if key not in {"usage_cells", "partition_cells"}
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
