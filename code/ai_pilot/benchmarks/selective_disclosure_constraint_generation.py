#!/usr/bin/env python3
"""Exact constraint-generation audit for selective relation disclosure.

A certificate master chooses row-usage or same-event pair facts. A complete
small event-column MILP then separates any feasible world with the opposite
downstream decision. Each witness contributes one disagreement-set cut. The
procedure never enumerates feasible worlds; explicit enumeration is used only
as a small-instance audit oracle.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import statistics
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

import event_frontier_truth_benchmark as canonical
import event_frontier_truth_benchmark_scale as scaled
import selective_disclosure_benchmark as explicit

TOL = 1e-8


def positions(mask: int, n: int) -> tuple[int, ...]:
    return tuple(i for i in range(n) if mask & (1 << i))


def solve_event_master(
    master: Any,
    objective: Sequence[float],
    *,
    maximize: bool,
    q: int,
    fixed_usage: Mapping[int, int] | None = None,
    fixed_pairs: Mapping[tuple[int, int], int] | None = None,
    selected_buffer_mask: int | None = None,
) -> tuple[tuple[int, ...] | None, float, float | None]:
    """Solve the complete-column integer event master and return event masks."""

    fixed_usage = fixed_usage or {}
    fixed_pairs = fixed_pairs or {}
    columns = tuple(master.columns)
    if len(objective) != len(columns):
        raise ValueError("objective length does not match column count")

    rows: list[np.ndarray] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(coefficients: Sequence[float], lo: float, hi: float) -> None:
        rows.append(np.asarray(coefficients, dtype=float))
        lower.append(float(lo))
        upper.append(float(hi))

    for i in positions(master.all_core_mask, len(master.rows)):
        add([bool(c.member_mask & (1 << i)) for c in columns], 1, 1)
    for i in positions(master.all_buffer_mask, len(master.rows)):
        add([bool(c.member_mask & (1 << i)) for c in columns], 0, 1)
    add([c.buffer_count for c in columns], q, q)

    if selected_buffer_mask is not None:
        for i in positions(master.all_buffer_mask, len(master.rows)):
            answer = int(bool(selected_buffer_mask & (1 << i)))
            add([bool(c.member_mask & (1 << i)) for c in columns], answer, answer)
    for i, answer in sorted(fixed_usage.items()):
        add([bool(c.member_mask & (1 << i)) for c in columns], answer, answer)
    for (i, j), answer in sorted(fixed_pairs.items()):
        add(
            [
                bool(c.member_mask & (1 << i))
                and bool(c.member_mask & (1 << j))
                for c in columns
            ],
            answer,
            answer,
        )

    cost = np.asarray(objective, dtype=float)
    if maximize:
        cost = -cost
    start = time.perf_counter()
    result = milp(
        c=cost,
        integrality=np.ones(len(columns), dtype=int),
        bounds=Bounds(np.zeros(len(columns)), np.ones(len(columns))),
        constraints=LinearConstraint(
            np.vstack(rows), np.asarray(lower), np.asarray(upper)
        ),
        options={"time_limit": 30.0, "mip_rel_gap": 0.0},
    )
    elapsed = time.perf_counter() - start
    gap = getattr(result, "mip_gap", None)
    if (
        not result.success
        or result.x is None
        or result.fun is None
        or (gap is not None and float(gap) > TOL)
    ):
        return None, elapsed, None if gap is None else float(gap)
    selected = tuple(
        columns[k].member_mask for k, value in enumerate(result.x) if value >= 0.5
    )
    return selected, elapsed, None if gap is None else float(gap)


def usage_mask(master: Any, events: Sequence[int]) -> int:
    mask = 0
    for event in events:
        mask |= event & master.all_buffer_mask
    return mask


def pair_signature(events: Sequence[int], pairs: Sequence[tuple[int, int]]) -> int:
    signature = 0
    for atom, (i, j) in enumerate(pairs):
        if any(event & (1 << i) and event & (1 << j) for event in events):
            signature |= 1 << atom
    return signature


def usage_separation(
    master: Any,
    values: Mapping[int, float],
    q: int,
    threshold: float,
    true_mask: int,
    certificate: Sequence[int],
) -> tuple[str, frozenset[int], float]:
    true_decision = explicit._decision(true_mask, values, q, threshold)
    fixed = {i: int(bool(true_mask & (1 << i))) for i in certificate}
    objective = [
        sum(value for i, value in values.items() if c.buffer_mask & (1 << i))
        for c in master.columns
    ]
    events, elapsed, _gap = solve_event_master(
        master,
        objective,
        maximize=not true_decision,
        q=q,
        fixed_usage=fixed,
    )
    if events is None:
        return "UNRESOLVED", frozenset(), elapsed
    witness = usage_mask(master, events)
    if explicit._decision(witness, values, q, threshold) == true_decision:
        return "NO_OPPOSITE_WORLD", frozenset(), elapsed
    cut = frozenset(
        i
        for i in values
        if bool(witness & (1 << i)) != bool(true_mask & (1 << i))
    )
    if not cut:
        raise AssertionError("opposite usage world has empty disagreement set")
    return "OPPOSITE_WORLD", cut, elapsed


def pair_separation(
    master: Any,
    instance: Any,
    pairs: Sequence[tuple[int, int]],
    certificate: Sequence[int],
    cutoff: int = 2,
) -> tuple[str, frozenset[int], float]:
    true_buffer_mask = explicit._member_mask(instance.true_buffer_indices)
    true_events = tuple(explicit._member_mask(run) for run in instance.true_runs)
    true_decision = len(true_events) <= cutoff
    truth = pair_signature(true_events, pairs)
    fixed = {pairs[a]: int(bool(truth & (1 << a))) for a in certificate}
    events, elapsed, _gap = solve_event_master(
        master,
        np.ones(len(master.columns)),
        maximize=true_decision,
        q=true_buffer_mask.bit_count(),
        fixed_pairs=fixed,
        selected_buffer_mask=true_buffer_mask,
    )
    if events is None:
        return "UNRESOLVED", frozenset(), elapsed
    if (len(events) <= cutoff) == true_decision:
        return "NO_OPPOSITE_WORLD", frozenset(), elapsed
    witness = pair_signature(events, pairs)
    cut = frozenset(
        a
        for a in range(len(pairs))
        if bool(truth & (1 << a)) != bool(witness & (1 << a))
    )
    if not cut:
        raise AssertionError("opposite partition has empty pair disagreement set")
    return "OPPOSITE_WORLD", cut, elapsed


def minimum_hitting_set(
    cuts: Iterable[frozenset[int]], atoms: Sequence[int]
) -> tuple[int, tuple[int, ...]]:
    cuts = explicit._inclusion_minimal_sets(cuts)
    if not cuts:
        return 0, ()
    return explicit._minimum_hitting_set(cuts, atoms)


def constraint_generate(atoms: Sequence[int], separator: Any) -> dict[str, Any]:
    cuts: list[frozenset[int]] = []
    elapsed = 0.0
    for iteration in range(10_000):
        size, certificate = minimum_hitting_set(cuts, atoms)
        status, cut, seconds = separator(certificate)
        elapsed += seconds
        if status == "NO_OPPOSITE_WORLD":
            return {
                "status": "CERTIFIED_OPTIMAL_CERTIFICATE",
                "certificate_size": size,
                "iterations": iteration + 1,
                "generated_cuts": len(cuts),
                "separation_seconds": elapsed,
            }
        if status != "OPPOSITE_WORLD":
            return {
                "status": status,
                "certificate_size": None,
                "iterations": iteration + 1,
                "generated_cuts": len(cuts),
                "separation_seconds": elapsed,
            }
        if cut in cuts:
            raise AssertionError("separator returned a duplicate unhit cut")
        cuts.append(cut)
    raise RuntimeError("constraint generation exceeded 10,000 cuts")


def explicit_usage_size(
    masks: Sequence[int],
    true_mask: int,
    values: Mapping[int, float],
    q: int,
    threshold: float,
    atoms: Sequence[int],
) -> int:
    truth = explicit._decision(true_mask, values, q, threshold)
    cuts = [
        frozenset(
            i
            for i in atoms
            if bool(mask & (1 << i)) != bool(true_mask & (1 << i))
        )
        for mask in masks
        if explicit._decision(mask, values, q, threshold) != truth
    ]
    return minimum_hitting_set(cuts, atoms)[0]


def describe(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "maximum": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "maximum": max(values),
    }


def run(
    usage_instances_per_capacity: int,
    pair_instances_per_capacity: int,
    base_seed: int,
) -> dict[str, Any]:
    usage_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    for capacity in scaled.CAPACITIES:
        for offset in range(usage_instances_per_capacity):
            seed = base_seed + capacity * 1_000_000 + offset
            instance = scaled.generate_instance(seed, capacity)
            master = canonical.base.exact.build_master(
                instance.rows, capacity, epsilon=0.1
            )
            true_mask = explicit._member_mask(instance.true_buffer_indices)
            q = true_mask.bit_count()
            values = explicit._buffer_values(master)
            usage_atoms = explicit._buffer_positions(master)
            masks = tuple(
                mask
                for mask in master.reachable_buffer_masks
                if mask.bit_count() == q
            )
            for threshold in explicit.DEFAULT_THRESHOLDS:
                exact = explicit_usage_size(
                    masks, true_mask, values, q, threshold, usage_atoms
                )
                generated = constraint_generate(
                    usage_atoms,
                    lambda certificate, threshold=threshold: usage_separation(
                        master,
                        values,
                        q,
                        threshold,
                        true_mask,
                        certificate,
                    ),
                )
                if generated["certificate_size"] != exact:
                    raise AssertionError(
                        f"usage mismatch seed={seed} C={capacity} "
                        f"threshold={threshold}: {exact} versus {generated}"
                    )
                usage_rows.append(
                    {
                        "seed": seed,
                        "capacity": capacity,
                        "threshold": threshold,
                        "event_columns": len(master.columns),
                        "explicit_size": exact,
                        **generated,
                    }
                )

            if offset < pair_instances_per_capacity:
                exact = explicit.minimum_pair_certificate_for_event_count(
                    master, instance
                )
                true_buffer_mask = explicit._member_mask(instance.true_buffer_indices)
                active = tuple(
                    i
                    for i in range(len(master.rows))
                    if master.all_core_mask & (1 << i)
                    or true_buffer_mask & (1 << i)
                )
                pairs = tuple(itertools.combinations(active, 2))
                pair_atoms = tuple(range(len(pairs)))
                generated = constraint_generate(
                    pair_atoms,
                    lambda certificate: pair_separation(
                        master, instance, pairs, certificate
                    ),
                )
                exact_size = int(exact["minimum_pair_certificate_size"])
                if generated["certificate_size"] != exact_size:
                    raise AssertionError(
                        f"pair mismatch seed={seed} C={capacity}: "
                        f"{exact_size} versus {generated}"
                    )
                pair_rows.append(
                    {
                        "seed": seed,
                        "capacity": capacity,
                        "event_columns": len(master.columns),
                        "explicit_size": exact_size,
                        "initially_ambiguous": exact["ambiguous_before_disclosure"],
                        **generated,
                    }
                )

    def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "cell_count": len(rows),
            "exact_agreement_count": sum(
                row["status"] == "CERTIFIED_OPTIMAL_CERTIFICATE" for row in rows
            ),
            "iterations": describe([float(row["iterations"]) for row in rows]),
            "generated_cuts": describe(
                [float(row["generated_cuts"]) for row in rows]
            ),
            "separation_seconds": describe(
                [float(row["separation_seconds"]) for row in rows]
            ),
        }

    return {
        "report_version": "eventfrontier-selective-disclosure-separation/v1",
        "design": {
            "capacities": list(scaled.CAPACITIES),
            "usage_instances_per_capacity": usage_instances_per_capacity,
            "usage_thresholds": list(explicit.DEFAULT_THRESHOLDS),
            "pair_instances_per_capacity": pair_instances_per_capacity,
            "world_enumeration_used_by_separation": False,
            "explicit_enumeration_used_only_as_oracle": True,
        },
        "usage_summary": summarize(usage_rows),
        "pair_summary": summarize(pair_rows),
        "usage_cells": usage_rows,
        "pair_cells": pair_rows,
        "claim_boundary": {
            "supported": "exact small-instance agreement of constraint generation and explicit certificates",
            "not_supported": "branch-and-price scaling, noisy answers, or operational disclosure",
        },
    }


def render(report: Mapping[str, Any]) -> str:
    usage = report["usage_summary"]
    pair = report["pair_summary"]
    return "\n".join(
        [
            "# Selective-disclosure constraint generation",
            "",
            f"Usage certificates: **{usage['exact_agreement_count']}/{usage['cell_count']}** exact agreements.",
            f"Pair certificates: **{pair['exact_agreement_count']}/{pair['cell_count']}** exact agreements.",
            "",
            "| Interface | Mean iterations | Max | Mean cuts | Mean separation seconds |",
            "|---|---:|---:|---:|---:|",
            f"| Row usage | {usage['iterations']['mean']:.2f} | {usage['iterations']['maximum']:.0f} | {usage['generated_cuts']['mean']:.2f} | {usage['separation_seconds']['mean']:.4f} |",
            f"| Pair co-membership | {pair['iterations']['mean']:.2f} | {pair['iterations']['maximum']:.0f} | {pair['generated_cuts']['mean']:.2f} | {pair['separation_seconds']['mean']:.4f} |",
            "",
            "Separation solves the complete small event-column integer master but never enumerates feasible worlds. Explicit enumeration is only the audit oracle. The next scale step replaces the complete-column separator with branch-and-price.",
            "",
        ]
    )


def self_test() -> None:
    report = run(1, 1, 20260905)
    assert report["usage_summary"]["exact_agreement_count"] == 9
    assert report["pair_summary"]["exact_agreement_count"] == 3
    print("selective disclosure constraint-generation self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usage-instances-per-capacity", type=int, default=100)
    parser.add_argument("--pair-instances-per-capacity", type=int, default=30)
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
        args.pair_instances_per_capacity,
        args.base_seed,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    compact = {
        key: value
        for key, value in report.items()
        if key not in {"usage_cells", "pair_cells"}
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
