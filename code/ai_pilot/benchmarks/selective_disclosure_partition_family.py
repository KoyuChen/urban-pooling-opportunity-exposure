#!/usr/bin/env python3
"""Verify closed-form pair certificates on an all-partitions EventFrontier family.

Take n identical core intervals and capacity n. Every nonempty row subset is a
feasible event column, so every set partition is an admissible EventFrontier
world. Pair co-membership queries then have closed-form certificate sizes.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Iterable, Sequence

import selective_disclosure_benchmark as disclosure


def set_partitions(items: tuple[int, ...]) -> Iterable[tuple[tuple[int, ...], ...]]:
    if not items:
        yield ()
        return
    first, *rest = items
    for partition in set_partitions(tuple(rest)):
        yield ((first,),) + partition
        for index in range(len(partition)):
            block = tuple(sorted(partition[index] + (first,)))
            candidate = list(partition)
            candidate[index] = block
            yield tuple(sorted(candidate))


def unique_partitions(n: int) -> tuple[tuple[tuple[int, ...], ...], ...]:
    return tuple(sorted(set(set_partitions(tuple(range(n))))))


def balanced_partition(n: int, blocks: int) -> tuple[tuple[int, ...], ...]:
    if not 1 <= blocks <= n:
        raise ValueError("blocks must lie in 1..n")
    result = [[] for _ in range(blocks)]
    for item in range(n):
        result[item % blocks].append(item)
    return tuple(tuple(block) for block in result)


def pair_signature(
    partition: Sequence[Sequence[int]], pairs: Sequence[tuple[int, int]]
) -> int:
    block_of = {
        item: block_index
        for block_index, block in enumerate(partition)
        for item in block
    }
    signature = 0
    for atom, (left, right) in enumerate(pairs):
        if block_of[left] == block_of[right]:
            signature |= 1 << atom
    return signature


def disagreement(
    truth: int, candidate: int, atom_count: int
) -> frozenset[int]:
    return frozenset(
        atom
        for atom in range(atom_count)
        if bool(truth & (1 << atom)) != bool(candidate & (1 << atom))
    )


def exact_certificate(
    truth_partition: Sequence[Sequence[int]],
    alternatives: Sequence[Sequence[Sequence[int]]],
    pairs: Sequence[tuple[int, int]],
) -> int:
    truth = pair_signature(truth_partition, pairs)
    cuts = [
        disagreement(truth, pair_signature(partition, pairs), len(pairs))
        for partition in alternatives
        if tuple(partition) != tuple(truth_partition)
    ]
    return disclosure._minimum_hitting_set(cuts, tuple(range(len(pairs))))[0]


def full_recovery_formula(n: int, true_blocks: int) -> int:
    return n - true_blocks + math.comb(true_blocks, 2)


def decision_formula(n: int, true_blocks: int, cutoff: int) -> int:
    if true_blocks <= cutoff:
        return n - cutoff
    return math.comb(cutoff + 1, 2)


def run(max_exact_n: int) -> dict:
    rows = []
    for n in range(2, max_exact_n + 1):
        partitions = unique_partitions(n)
        pairs = tuple(itertools.combinations(range(n), 2))
        for true_blocks in range(1, n + 1):
            truth = balanced_partition(n, true_blocks)
            full_exact = exact_certificate(truth, partitions, pairs)
            full_formula = full_recovery_formula(n, true_blocks)
            if full_exact != full_formula:
                raise AssertionError(
                    f"full formula mismatch n={n} K={true_blocks}: "
                    f"{full_exact} versus {full_formula}"
                )
            for cutoff in range(1, n):
                true_decision = true_blocks <= cutoff
                opposite = tuple(
                    partition
                    for partition in partitions
                    if (len(partition) <= cutoff) != true_decision
                )
                decision_exact = exact_certificate(truth, opposite, pairs)
                decision_closed = decision_formula(n, true_blocks, cutoff)
                if decision_exact != decision_closed:
                    raise AssertionError(
                        f"decision formula mismatch n={n} K={true_blocks} "
                        f"k={cutoff}: {decision_exact} versus {decision_closed}"
                    )
                rows.append(
                    {
                        "n": n,
                        "true_event_count": true_blocks,
                        "cutoff": cutoff,
                        "true_decision": true_decision,
                        "decision_certificate": decision_exact,
                        "full_partition_certificate": full_exact,
                        "facts_saved": full_exact - decision_exact,
                    }
                )

    asymptotic = [
        {
            "n": n,
            "true_event_count": 3,
            "cutoff": 2,
            "decision_certificate": 3,
            "full_partition_certificate": n,
            "decision_to_full_ratio": 3 / n,
        }
        for n in (3, 6, 12, 30, 100)
    ]
    return {
        "report_version": "eventfrontier-all-partitions-certificates/v1",
        "design": {
            "max_exact_n": max_exact_n,
            "identical_core_intervals": True,
            "capacity_equals_n": True,
            "all_set_partitions_feasible": True,
        },
        "verified_cell_count": len(rows),
        "full_recovery_formula": "n-K+binom(K,2)",
        "decision_formula": {
            "K_le_k": "n-k",
            "K_gt_k": "binom(k+1,2)",
        },
        "asymptotic_K3_k2": asymptotic,
        "cells": rows,
    }


def render(report: dict) -> str:
    lines = [
        "# Closed-form pair certificates on the all-partitions family",
        "",
        f"Exact enumeration verifies **{report['verified_cell_count']}** parameter cells through n={report['design']['max_exact_n']}.",
        "",
        "For a realized partition with K events on n active rows:",
        "",
        "- full partition recovery requires `n-K+binom(K,2)` pair facts;",
        "- certifying `K <= k` requires `n-k` facts when the decision is true;",
        "- certifying `K <= k` requires `binom(k+1,2)` facts when the decision is false.",
        "",
        "For K=3 and k=2, decision certification always costs three negative pair facts, while full recovery costs n facts:",
        "",
        "| n | Decision facts | Recovery facts | Ratio |",
        "|---:|---:|---:|---:|",
    ]
    for row in report["asymptotic_K3_k2"]:
        lines.append(
            f"| {row['n']} | {row['decision_certificate']} | "
            f"{row['full_partition_certificate']} | "
            f"{row['decision_to_full_ratio']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def self_test() -> None:
    report = run(6)
    assert report["verified_cell_count"] > 0
    assert report["asymptotic_K3_k2"][-1]["decision_to_full_ratio"] == 0.03
    print("all-partitions certificate family self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-exact-n", type=int, default=7)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output_dir is None:
        parser.error("--output-dir is required unless --self-test is used")
    report = run(args.max_exact_n)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    compact = {key: value for key, value in report.items() if key != "cells"}
    (args.output_dir / "report.json").write_text(
        json.dumps(compact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
