#!/usr/bin/env python3
"""Constraint-generation audit for selective relation disclosure.

The explicit selective-disclosure benchmark enumerates all feasible selected
sets or partitions and solves a hitting set over their disagreement patterns.
This module validates the scalable decomposition proposed in the accompanying
research note:

1. a certificate master chooses row-usage or same-event pair facts;
2. a mixed-integer EventFrontier separation problem searches for an
   opposite-decision world consistent with the chosen facts;
3. every discovered world adds one disagreement-set cut.

The current implementation uses the complete small event-column master so it can
be audited against explicit enumeration.  Replacing this separation MILP with
the existing branch-and-price node solver is the next scale step.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import itertools
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

import event_frontier_truth_benchmark as canonical
import event_frontier_truth_benchmark_scale as scaled
import selective_disclosure_benchmark as explicit

TOL = explicit.TOL


@dataclass(frozen=True)
class SeparationResult:
    status: str
    disagreement: frozenset[int] = frozenset()
    objective: float | None = None
    selected_column_masks: tuple[int, ...] = ()
    solve_seconds: float = 0.0
    mip_gap: float | None = None


def _positions(mask: int, row_count: int) -> tuple[int, ...]:
    return tuple(position for position in range(row_count) if mask & (1 << position))


def _active_rows(master: Any, selected_buffer_mask: int) -> tuple[int, ...]:
    return tuple(
        position
        for position in range(len(master.rows))
        if master.all_core_mask & (1 << position)
        or selected_buffer_mask & (1 << position)
    )


def _solve_column_master(
    master: Any,
    objective: Sequence[float],
    *,
    maximize: bool,
    support_count: int,
    fixed_usage: Mapping[int, int],
    fixed_pairs: Mapping[tuple[int, int], int],
    selected_buffer_mask: int | None = None,
) -> tuple[Any, tuple[int, ...], float]:
    columns = tuple(master.columns)
    column_count = len(columns)
    if len(objective) != column_count:
        raise ValueError("objective length does not match event columns")

    lower_rows: list[float] = []
    upper_rows: list[float] = []
    matrix_rows: list[np.ndarray] = []

    for position in _positions(master.all_core_mask, len(master.rows)):
        row = np.asarray(
            [float(bool(column.member_mask & (1 << position))) for column in columns]
        )
        matrix_rows.append(row)
        lower_rows.append(1.0)
        upper_rows.append(1.0)

    for position in _positions(master.all_buffer_mask, len(master.rows)):
        row = np.asarray(
            [float(bool(column.member_mask & (1 << position))) for column in columns]
        )
        matrix_rows.append(row)
        lower_rows.append(0.0)
        upper_rows.append(1.0)

    support_row = np.asarray([float(column.buffer_count) for column in columns])
    matrix_rows.append(support_row)
    lower_rows.append(float(support_count))
    upper_rows.append(float(support_count))

    if selected_buffer_mask is not None:
        for position in _positions(master.all_buffer_mask, len(master.rows)):
            answer = int(bool(selected_buffer_mask & (1 << position)))
            row = np.asarray(
                [float(bool(column.member_mask & (1 << position))) for column in columns]
            )
            matrix_rows.append(row)
            lower_rows.append(float(answer))
            upper_rows.append(float(answer))

    for position, answer in sorted(fixed_usage.items()):
        row = np.asarray(
            [float(bool(column.member_mask & (1 << position))) for column in columns]
        )
        matrix_rows.append(row)
        lower_rows.append(float(answer))
        upper_rows.append(float(answer))

    for pair, answer in sorted(fixed_pairs.items()):
        left, right = pair
        row = np.asarray(
            [
                float(
                    bool(column.member_mask & (1 << left))
                    and bool(column.member_mask & (1 << right))
                )
                for column in columns
            ]
        )
        matrix_rows.append(row)
        lower_rows.append(float(answer))
        upper_rows.append(float(answer))

    matrix = np.vstack(matrix_rows)
    c = np.asarray(objective, dtype=float)
    if maximize:
        c = -c
    start = time.perf_counter()
    result = milp(
        c=c,
        integrality=np.ones(column_count, dtype=int),
        bounds=Bounds(np.zeros(column_count), np.ones(column_count)),
        constraints=LinearConstraint(
            matrix,
            np.asarray(lower_rows),
            np.asarray(upper_rows),
        ),
        options={"time_limit": 30.0, "mip_rel_gap": 0.0},
    )
    elapsed = time.perf_counter() - start
    mip_gap = getattr(result, "mip_gap", None)
    if (
        not result.success
        or result.x is None
        or result.fun is None
        or (mip_gap is not None and float(mip_gap) > 1e-8)
    ):
        return result, (), elapsed
    selected = tuple(
        columns[index].member_mask
        for index, value in enumerate(result.x)
        if value >= 0.5
    )
    return result, selected, elapsed


def _usage_mask_from_columns(master: Any, columns: Sequence[int]) -> int:
    used = 0
    for mask in columns:
        used |= mask & master.all_buffer_mask
    return used


def _pair_signature(
    event_masks: Sequence[int], pairs: Sequence[tuple[int, int]]
) -> int:
    return explicit._pair_signature(event_masks, pairs)


def separate_usage_decision(
    master: Any,
    values: Mapping[int, float],
    q: int,
    threshold: float,
    true_mask: int,
    disclosed_positions: Sequence[int],
) -> SeparationResult:
    true_decision = explicit._decision(true_mask, values, q, threshold)
    fixed_usage = {
        position: int(bool(true_mask & (1 << position)))
        for position in disclosed_positions
    }
    objective = [
        sum(
            values[position]
            for position in values
            if column.buffer_mask & (1 << position)
        )
        for column in master.columns
    ]
    result, selected_columns, elapsed = _solve_column_master(
        master,
        objective,
        maximize=not true_decision,
        support_count=q,
        fixed_usage=fixed_usage,
        fixed_pairs={},
    )
    if not result.success or result.x is None:
        return SeparationResult(status="SEPARATION_UNRESOLVED", solve_seconds=elapsed)
    witness_mask = _usage_mask_from_columns(master, selected_columns)
    witness_decision = explicit._decision(
        witness_mask, values, q, threshold
    )
    objective_value = sum(values[position] for position in values if witness_mask & (1 << position))
    mip_gap = getattr(result, "mip_gap", None)
    if witness_decision == true_decision:
        return SeparationResult(
            status="NO_OPPOSITE_WORLD",
            objective=objective_value,
            selected_column_masks=selected_columns,
            solve_seconds=elapsed,
            mip_gap=None if mip_gap is None else float(mip_gap),
        )
    disagreement = frozenset(
        position
        for position in values
        if bool(witness_mask & (1 << position))
        != bool(true_mask & (1 << position))
    )
    return SeparationResult(
        status="OPPOSITE_WORLD_FOUND",
        disagreement=disagreement,
        objective=objective_value,
        selected_column_masks=selected_columns,
        solve_seconds=elapsed,
        mip_gap=None if mip_gap is None else float(mip_gap),
    )


def separate_event_count_decision(
    master: Any,
    true_events: Sequence[int],
    true_buffer_mask: int,
    cutoff: int,
    pairs: Sequence[tuple[int, int]],
    disclosed_atoms: Sequence[int],
) -> SeparationResult:
    true_count = len(true_events)
    true_decision = true_count <= cutoff
    true_signature = _pair_signature(true_events, pairs)
    fixed_pairs = {
        pairs[atom]: int(bool(true_signature & (1 << atom)))
        for atom in disclosed_atoms
    }
    result, selected_columns, elapsed = _solve_column_master(
        master,
        np.ones(len(master.columns)),
        maximize=true_decision,
        support_count=true_buffer_mask.bit_count(),
        fixed_usage={},
        fixed_pairs=fixed_pairs,
        selected_buffer_mask=true_buffer_mask,
    )
    if not result.success or result.x is None:
        return SeparationResult(status="SEPARATION_UNRESOLVED", solve_seconds=elapsed)
    witness_count = len(selected_columns)
    witness_decision = witness_count <= cutoff
    mip_gap = getattr(result, "mip_gap", None)
    if witness_decision == true_decision:
        return SeparationResult(
            status="NO_OPPOSITE_WORLD",
            objective=float(witness_count),
            selected_column_masks=selected_columns,
            solve_seconds=elapsed,
            mip_gap=None if mip_gap is None else float(mip_gap),
        )
    witness_signature = _pair_signature(selected_columns, pairs)
    disagreement = frozenset(
        atom
        for atom in range(len(pairs))
        if bool(true_signature & (1 << atom))
        != bool(witness_signature & (1 << atom))
    )
    return SeparationResult(
        status="OPPOSITE_WORLD_FOUND",
        disagreement=disagreement,
        objective=float(witness_count),
        selected_column_masks=selected_columns,
        solve_seconds=elapsed,
        mip_gap=None if mip_gap is None else float(mip_gap),
    )


def _minimum_small_hitting_set(
    cuts: Iterable[frozenset[int]], atoms: Sequence[int]
) -> tuple[int, tuple[int, ...]]:
    cuts = explicit._inclusion_minimal_sets(cuts)
    if not cuts:
        return 0, ()
    for size in range(1, len(atoms) + 1):
        for chosen in itertools.combinations#atoms, size):
            chosen_set = set(chosen)
            if all(chosen_set & set(cut) for cut in cuts):
                return size, tuple(chosen)
    raise AssertionError("finite hitting-set master has no solution")


def constraint_generate_usage(
    master: Any,
    values: Mapping[int, float],
    q: int,
    threshold: float,
    true_mask: int,
    buffer_positions: Sequence[int],
) -> dict[str, Any]:
    cuts: list[frozenset[int]] = []
    total_seconds = 0.0
    for iteration in range(10_000):
        size, certificate = _minimum_small_hitting_set(cuts, buffer_positions)
        separated = separate_usage_decision(
            master,
            values,
            q,
            threshold,
            true_mask,
            certificate,
        )
        total_seconds += separated.solve_seconds
        if separated.status == "NO_OPPOSITE_WORLD":
            return {
                "status": "CERTIFIED_OPTIMAL_CERTIFICATE",
                "certificate_size": size,
                "separation_iterations": iteration + 1,
                "generated_cuts": len(cuts),
                "separation_seconds": total_seconds,
            }
        if separated.status != "OPPOSITE_WORLD_FOUND":
            return {
                "status": separated.status,
                "certificate_size": None,
                "separation_iterations": iteration + 1,
                "generated_cuts": len(cuts),
                "separation_seconds": total_seconds,
            }
        if separated.disagreement in cuts:
            raise AssertionError("separation returned a duplicate unhit cut")
        cuts.append(separated.disagreement)
    raise RuntimeError("usage constraint generation exceeded 10,000 cuts")


def constraint_generate_pairs(
    master: Any,
    instance: Any,
    cutoff: int = 2,
) 6ﬂŒwr´≤⁄Óù∆≠y