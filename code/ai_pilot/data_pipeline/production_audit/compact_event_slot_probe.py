#!/usr/bin/env python3
"""Certified compact at-most-K event-slot relaxation.

The model is a necessary condition for a fixed-support ordered-event world with
at most ``K`` events. Integer assignments enforce row usage, truthful pair
facts, simultaneous capacity, at least one core and two rows per event, and
interval-union connectivity through cut constraints. The LP relaxation is
used only to certify impossibility: a strictly positive rational lower bound on
an always-feasible phase-I objective proves that no K-event world exists.

A MIP solution may provide a replayable incumbent, but solver failure or a
positive MIP lower bound never certifies infeasibility. This module therefore
remains fail-closed under time limits and numerical ambiguity.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import time
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import coo_matrix, csr_matrix, hstack, eye

from ordered_run_fixed_time_master import FixedTimeRow

Number = int | float | Fraction


def _rat(value: float, limit: int = 10**8) -> Fraction:
    if not math.isfinite(float(value)):
        raise ValueError("nonfinite dual")
    return Fraction(float(value)).limit_denominator(limit)


@dataclass(frozen=True)
class ProbeResult:
    lower_event_count: int
    witness: tuple[int, ...]
    tested_k: tuple[int, ...]
    certified_infeasible_k: tuple[int, ...]
    phase_one_calls: int
    mip_calls: int
    seconds: float
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class SlotModel:
    rows: tuple[FixedTimeRow, ...]
    capacity: int
    support_count: int
    slots: int
    variable_count: int
    x_count: int
    aeq: csr_matrix
    beq: np.ndarray
    aub: csr_matrix
    bub: np.ndarray
    lower: np.ndarray
    upper: np.ndarray

    def x_index(self, row: int, slot: int) -> int:
        return row * self.slots + slot

    def y_index(self, slot: int) -> int:
        return self.x_count + slot


class _Builder:
    def __init__(self, variable_count: int) -> None:
        self.variable_count = variable_count
        self.eq_rows: list[int] = []
        self.eq_cols: list[int] = []
        self.eq_vals: list[float] = []
        self.beq: list[float] = []
        self.ub_rows: list[int] = []
        self.ub_cols: list[int] = []
        self.ub_vals: list[float] = []
        self.bub: list[float] = []

    def eq(self, coefficients: Mapping[int, Number], rhs: Number) -> None:
        row = len(self.beq)
        for col, value in coefficients.items():
            if value:
                self.eq_rows.append(row)
                self.eq_cols.append(col)
                self.eq_vals.append(float(value))
        self.beq.append(float(rhs))

    def ub(self, coefficients: Mapping[int, Number], rhs: Number) -> None:
        row = len(self.bub)
        for col, value in coefficients.items():
            if value:
                self.ub_rows.append(row)
                self.ub_cols.append(col)
                self.ub_vals.append(float(value))
        self.bub.append(float(rhs))

    def finish(self) -> tuple[csr_matrix, np.ndarray, csr_matrix, np.ndarray]:
        aeq = coo_matrix(
            (self.eq_vals, (self.eq_rows, self.eq_cols)),
            shape=(len(self.beq), self.variable_count),
            dtype=float,
        ).tocsr()
        aub = coo_matrix(
            (self.ub_vals, (self.ub_rows, self.ub_cols)),
            shape=(len(self.bub), self.variable_count),
            dtype=float,
        ).tocsr()
        return aeq, np.asarray(self.beq), aub, np.asarray(self.bub)


def _validate_inputs(
    rows: Sequence[FixedTimeRow],
    capacity: int,
    support_count: int,
    slots: int,
    usage_answers: Mapping[int, int],
    pair_answers: Mapping[tuple[int, int], int],
) -> tuple[tuple[FixedTimeRow, ...], tuple[int, ...], tuple[int, ...]]:
    ordered = tuple(sorted(rows, key=lambda r: r.index))
    if len({r.index for r in ordered}) != len(ordered):
        raise ValueError("row indices must be unique")
    if any(not math.isfinite(float(v)) for r in ordered for v in (r.start, r.end)):
        raise ValueError("timestamps must be finite")
    if any(r.start >= r.end for r in ordered):
        raise ValueError("rows must have positive duration")
    if not isinstance(capacity, int) or capacity < 2:
        raise ValueError("capacity must be an integer >=2")
    if not isinstance(slots, int) or slots < 1:
        raise ValueError("slots must be positive")
    core = tuple(i for i, r in enumerate(ordered) if r.role == "core")
    buffer = tuple(i for i, r in enumerate(ordered) if r.role == "buffer")
    if not core:
        raise ValueError("at least one core is required")
    if not 0 <= support_count <= len(buffer):
        raise ValueError("support count out of range")
    for i, answer in usage_answers.items():
        if i not in buffer or answer not in (0, 1):
            raise ValueError("usage answers must address buffer positions")
    for pair, answer in pair_answers.items():
        if len(pair) != 2 or pair[0] == pair[1] or answer not in (0, 1):
            raise ValueError("invalid pair answer")
        if any(not isinstance(i, int) or not 0 <= i < len(ordered) for i in pair):
            raise ValueError("pair position out of range")
    return ordered, core, buffer


def build_slot_model(
    rows: Sequence[FixedTimeRow],
    capacity: int,
    support_count: int,
    slots: int,
    *,
    usage_answers: Mapping[int, int] | None = None,
    pair_answers: Mapping[tuple[int, int], int] | None = None,
) -> SlotModel:
    """Build the labeled at-most-K compact model.

    The LP relaxation contains every feasible K-event world after arbitrary
    event-to-slot labeling. Therefore certified LP infeasibility is a valid
    lower-bound certificate for the original event problem.
    """
    usage_answers = dict(usage_answers or {})
    normalized_pairs: dict[tuple[int, int], int] = {}
    for pair, answer in dict(pair_answers or {}).items():
        key = tuple(sorted(pair))
        if key in normalized_pairs and normalized_pairs[key] != answer:
            raise ValueError("contradictory pair answers")
        normalized_pairs[key] = answer
    ordered, core, buffer = _validate_inputs(
        rows, capacity, support_count, slots, usage_answers, normalized_pairs
    )
    n = len(ordered)
    x_count = n * slots

    endpoints = sorted({v for r in ordered for v in (r.start, r.end)})
    boundaries = tuple(endpoints[1:-1])
    y_offset = x_count
    left_offset = y_offset + slots
    right_offset = left_offset + len(boundaries) * slots
    variable_count = right_offset + len(boundaries) * slots

    def x(i: int, e: int) -> int:
        return i * slots + e

    def y(e: int) -> int:
        return y_offset + e

    def left(bi: int, e: int) -> int:
        return left_offset + bi * slots + e

    def right(bi: int, e: int) -> int:
        return right_offset + bi * slots + e

    builder = _Builder(variable_count)

    for i in core:
        builder.eq({x(i, e): 1 for e in range(slots)}, 1)
    for i in buffer:
        builder.ub({x(i, e): 1 for e in range(slots)}, 1)
    builder.eq({x(i, e): 1 for i in buffer for e in range(slots)}, support_count)

    for i, answer in sorted(usage_answers.items()):
        builder.eq({x(i, e): 1 for e in range(slots)}, answer)

    for (i, j), answer in sorted(normalized_pairs.items()):
        if answer:
            for e in range(slots):
                builder.eq({x(i, e): 1, x(j, e): -1}, 0)
            for endpoint in (i, j):
                if endpoint in buffer:
                    builder.eq({x(endpoint, e): 1 for e in range(slots)}, 1)
        else:
            for e in range(slots):
                builder.ub({x(i, e): 1, x(j, e): 1, y(e): -1}, 0)

    for e in range(slots):
        for i in range(n):
            builder.ub({x(i, e): 1, y(e): -1}, 0)
        builder.ub({y(e): 1, **{x(i, e): -1 for i in core}}, 0)
        builder.ub({y(e): 2, **{x(i, e): -1 for i in range(n)}}, 0)
    for e in range(slots - 1):
        builder.ub({y(e + 1): 1, y(e): -1}, 0)

    for a, b in zip(endpoints, endpoints[1:]):
        if a >= b:
            continue
        midpoint = (a + b) / 2
        active = [i for i, r in enumerate(ordered) if r.start <= midpoint < r.end]
        if not active:
            continue
        for e in range(slots):
            coefficients = {x(i, e): 1 for i in active}
            coefficients[y(e)] = -capacity
            builder.ub(coefficients, 0)

    for bi, boundary in enumerate(boundaries):
        left_rows = [i for i, r in enumerate(ordered) if r.end <= boundary]
        right_rows = [i for i, r in enumerate(ordered) if r.start >= boundary]
        bridge_rows = [
            i for i, r in enumerate(ordered) if r.start < boundary < r.end
        ]
        if not left_rows or not right_rows:
            continue
        for e in range(slots):
            for i in left_rows:
                builder.ub({x(i, e): 1, left(bi, e): -1}, 0)
            for i in right_rows:
                builder.ub({x(i, e): 1, right(bi, e): -1}, 0)
            coefficients = {left(bi, e): 1, right(bi, e): 1}
            for i in bridge_rows:
                coefficients[x(i, e)] = coefficients.get(x(i, e), 0) - 1
            builder.ub(coefficients, 1)

    aeq, beq, aub, bub = builder.finish()
    lower = np.zeros(variable_count)
    upper = np.ones(variable_count)
    return SlotModel(
        rows=ordered,
        capacity=capacity,
        support_count=support_count,
        slots=slots,
        variable_count=variable_count,
        x_count=x_count,
        aeq=aeq,
        beq=beq,
        aub=aub,
        bub=bub,
        lower=lower,
        upper=upper,
    )


def _phase_one_certificate(model: SlotModel, seconds: float) -> tuple[bool, Fraction | None]:
    """Return (certified infeasible, rational lower bound on phase-I cost)."""
    if seconds <= 0:
        return False, None
    p = model.aeq.shape[0]
    r = model.aub.shape[0]
    eq = hstack(
        [model.aeq, eye(p, format="csr"), -eye(p, format="csr"), csr_matrix((p, r))],
        format="csr",
    )
    ub = hstack(
        [model.aub, csr_matrix((r, 2 * p)), -eye(r, format="csr")],
        format="csr",
    )
    c = np.r_[np.zeros(model.variable_count), np.ones(2 * p + r)]
    bounds = [(0.0, 1.0)] * model.variable_count + [(0.0, None)] * (2 * p + r)
    result = linprog(
        c,
        A_ub=ub if r else None,
        b_ub=model.bub if r else None,
        A_eq=eq if p else None,
        b_eq=model.beq if p else None,
        bounds=bounds,
        method="highs",
        options={"time_limit": max(1e-4, seconds)},
    )
    if not result.success or result.x is None:
        return False, None

    pi = [max(Fraction(-1), min(Fraction(1), _rat(v))) for v in result.eqlin.marginals]
    nu = [max(Fraction(-1), min(Fraction(0), _rat(v))) for v in result.ineqlin.marginals]
    lower = sum((Fraction(int(round(b))) * d for b, d in zip(model.beq, pi)), Fraction(0))
    lower += sum((Fraction(int(round(b))) * d for b, d in zip(model.bub, nu)), Fraction(0))

    aeq_csc = model.aeq.tocsc()
    aub_csc = model.aub.tocsc()
    for j in range(model.variable_count):
        residual = Fraction(0)
        for k in range(aeq_csc.indptr[j], aeq_csc.indptr[j + 1]):
            residual -= Fraction(int(aeq_csc.data[k])) * pi[aeq_csc.indices[k]]
        for k in range(aub_csc.indptr[j], aub_csc.indptr[j + 1]):
            residual -= Fraction(int(aub_csc.data[k])) * nu[aub_csc.indices[k]]
        lower += min(Fraction(0), residual)

    if any(1 - d < 0 or 1 + d < 0 for d in pi):
        raise AssertionError("equality artificial residual sign failure")
    if any(1 + d < 0 for d in nu):
        raise AssertionError("inequality artificial residual sign failure")
    return lower > 0, lower


def _mip_witness(model: SlotModel, seconds: float) -> tuple[int, ...]:
    if seconds <= 0:
        return ()
    constraints = []
    if model.aeq.shape[0]:
        constraints.append(LinearConstraint(model.aeq, model.beq, model.beq))
    if model.aub.shape[0]:
        constraints.append(
            LinearConstraint(model.aub, -np.inf * np.ones_like(model.bub), model.bub)
        )
    result = milp(
        c=np.zeros(model.variable_count),
        integrality=np.ones(model.variable_count, dtype=int),
        bounds=Bounds(model.lower, model.upper),
        constraints=constraints,
        options={"time_limit": max(1e-4, seconds), "mip_rel_gap": 0.0},
    )
    if result.x is None or np.any(~np.isfinite(result.x)):
        return ()
    rounded = np.rint(result.x).astype(int)
    if max(abs(result.x - rounded), default=0) > 1e-7:
        return ()
    events: list[int] = []
    for e in range(model.slots):
        mask = sum(
            1 << i
            for i in range(len(model.rows))
            if rounded[model.x_index(i, e)] == 1
        )
        if mask:
            events.append(mask)
    return tuple(events)


def probe_minimum_events(
    rows: Sequence[FixedTimeRow],
    capacity: int,
    support_count: int,
    *,
    start_k: int,
    max_k: int,
    usage_answers: Mapping[int, int] | None = None,
    pair_answers: Mapping[tuple[int, int], int] | None = None,
    seconds: float = 1.0,
    seek_witness: bool = True,
) -> ProbeResult:
    """Certify consecutive impossible K values and optionally find a witness."""
    started = time.perf_counter()
    if not isinstance(start_k, int) or not isinstance(max_k, int) or start_k < 1:
        raise ValueError("K limits must be positive integers")
    if max_k < start_k or seconds <= 0:
        return ProbeResult(start_k, (), (), (), 0, 0, time.perf_counter() - started, "SKIPPED")
    deadline = started + seconds
    tested: list[int] = []
    impossible: list[int] = []
    phase_calls = 0
    mip_calls = 0
    witness: tuple[int, ...] = ()
    reason = None

    for k in range(start_k, max_k + 1):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            reason = "TIME_LIMIT"
            break
        model = build_slot_model(
            rows,
            capacity,
            support_count,
            k,
            usage_answers=usage_answers,
            pair_answers=pair_answers,
        )
        tested.append(k)
        phase_calls += 1
        certified, _ = _phase_one_certificate(model, remaining * (0.75 if seek_witness else 1.0))
        if certified:
            impossible.append(k)
            continue
        if seek_witness:
            mip_calls += 1
            witness = _mip_witness(model, deadline - time.perf_counter())
        break

    lower = start_k
    for k in impossible:
        if k == lower:
            lower += 1
        else:
            break
    status = "CERTIFIED_LOWER_BOUND" if impossible else "UNRESOLVED"
    if witness:
        status = "LOWER_BOUND_AND_WITNESS" if impossible else "FEASIBLE_WITNESS"
    return ProbeResult(
        lower_event_count=lower,
        witness=witness,
        tested_k=tuple(tested),
        certified_infeasible_k=tuple(impossible),
        phase_one_calls=phase_calls,
        mip_calls=mip_calls,
        seconds=time.perf_counter() - started,
        status=status,
        reason=reason,
    )
