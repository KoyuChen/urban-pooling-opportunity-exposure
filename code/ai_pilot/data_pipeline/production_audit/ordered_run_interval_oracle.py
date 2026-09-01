#!/usr/bin/env python3
"""Exact LP oracle for one rooted connected interval run.

For a fixed temporal span, positive-overlap connectivity plus simultaneous
occupancy capacity is represented by an augmented consecutive-ones interval
matrix.  The LP relaxation is integral.  This module is intentionally
independent of NYC extraction code so the structural claim can be audited on
small synthetic libraries.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import linprog

TOL = 1e-8


@dataclass(frozen=True)
class GridInterval:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("interval must have 0 <= start < end")


def covers_segment(interval: GridInterval, k: int) -> bool:
    """Whether [start,end) covers elementary segment (k,k+1)."""
    return interval.start <= k and interval.end >= k + 1


def bridges_boundary(interval: GridInterval, k: int) -> bool:
    """Whether interval positively crosses internal boundary k."""
    return interval.start < k < interval.end


def allowed_in_span(interval: GridInterval, span: tuple[int, int]) -> bool:
    a, b = span
    return interval.start >= a and interval.end <= b


def augmented_incidence(
    intervals: Sequence[GridInterval],
    span: tuple[int, int],
) -> tuple[np.ndarray, list[tuple[str, int]]]:
    """Return interleaved segment/boundary incidence rows for a fixed span.

    Row order is segment a, boundary a+1, segment a+1, ..., segment b-1.
    Every interval column has consecutive ones after intervals outside the span
    are ignored by the optimization bounds.
    """
    a, b = span
    if not (0 <= a < b):
        raise ValueError("span must satisfy 0 <= a < b")
    labels: list[tuple[str, int]] = []
    rows: list[list[float]] = []
    for k in range(a, b):
        labels.append(("segment", k))
        rows.append([float(covers_segment(interval, k)) for interval in intervals])
        if k + 1 < b:
            boundary = k + 1
            labels.append(("boundary", boundary))
            rows.append([float(bridges_boundary(interval, boundary)) for interval in intervals])
    return np.asarray(rows, dtype=float), labels


def consecutive_ones_columns(matrix: np.ndarray) -> bool:
    for column in matrix.T:
        support = np.flatnonzero(column > 0.5)
        if len(support) <= 1:
            continue
        if support[-1] - support[0] + 1 != len(support):
            return False
    return True


def solve_fixed_span(
    intervals: Sequence[GridInterval],
    weights: Sequence[float],
    root: int,
    span: tuple[int, int],
    capacity: int,
    *,
    maximize: bool = True,
    forced_companion: int | None = None,
) -> dict[str, object]:
    """Solve the fixed-span rooted single-run LP exactly.

    The result is certified only when HiGHS returns an optimum and the solution
    is integral to numerical tolerance.  A forced companion can be supplied to
    impose the at-least-two-members rule without a cardinality row.
    """
    n = len(intervals)
    if len(weights) != n:
        raise ValueError("weights must match intervals")
    if not (0 <= root < n):
        raise ValueError("root index out of range")
    if capacity < 1:
        raise ValueError("capacity must be positive")
    if forced_companion is not None and not (0 <= forced_companion < n):
        raise ValueError("forced companion index out of range")
    if forced_companion == root:
        raise ValueError("forced companion must differ from root")

    a, b = span
    if not allowed_in_span(intervals[root], span):
        return {"status": "INFEASIBLE_ROOT_OUTSIDE_SPAN", "value": None, "x": None}
    if forced_companion is not None and not allowed_in_span(intervals[forced_companion], span):
        return {"status": "INFEASIBLE_COMPANION_OUTSIDE_SPAN", "value": None, "x": None}

    bounds = [
        (0.0, 1.0) if allowed_in_span(interval, span) else (0.0, 0.0)
        for interval in intervals
    ]

    A_ub: list[np.ndarray] = []
    b_ub: list[float] = []

    # Every segment inside the declared run span must be covered, with depth <= C.
    for k in range(a, b):
        row = np.asarray([float(covers_segment(interval, k)) for interval in intervals])
        A_ub.append(row)
        b_ub.append(float(capacity))
        A_ub.append(-row)
        b_ub.append(-1.0)

    # Endpoint touching does not connect runs: each internal boundary needs a
    # selected interval that strictly crosses it.
    for k in range(a + 1, b):
        row = np.asarray([float(bridges_boundary(interval, k)) for interval in intervals])
        A_ub.append(-row)
        b_ub.append(-1.0)

    A_eq: list[np.ndarray] = []
    b_eq: list[float] = []
    root_row = np.zeros(n, dtype=float)
    root_row[root] = 1.0
    A_eq.append(root_row)
    b_eq.append(1.0)
    if forced_companion is not None:
        companion_row = np.zeros(n, dtype=float)
        companion_row[forced_companion] = 1.0
        A_eq.append(companion_row)
        b_eq.append(1.0)

    objective = np.asarray(weights, dtype=float)
    result = linprog(
        -objective if maximize else objective,
        A_ub=np.asarray(A_ub, dtype=float) if A_ub else None,
        b_ub=np.asarray(b_ub, dtype=float) if b_ub else None,
        A_eq=np.asarray(A_eq, dtype=float),
        b_eq=np.asarray(b_eq, dtype=float),
        bounds=bounds,
        method="highs",
    )
    if not result.success or result.x is None:
        return {
            "status": "PROVEN_INFEASIBLE" if result.status == 2 else "UNRESOLVED",
            "value": None,
            "x": None,
            "solver_status": int(result.status),
        }

    rounded = np.rint(result.x)
    residual = float(np.max(np.abs(result.x - rounded)))
    if residual > TOL:
        return {
            "status": "NONINTEGRAL_NUMERICAL_RESULT",
            "value": None,
            "x": result.x.tolist(),
            "integrality_residual": residual,
            "solver_status": int(result.status),
        }
    value = float(objective @ rounded)
    return {
        "status": "CERTIFIED_OPTIMAL_LP_INTEGER",
        "value": value,
        "x": rounded.astype(int).tolist(),
        "integrality_residual": residual,
        "solver_status": int(result.status),
    }


def solve_rooted_run(
    intervals: Sequence[GridInterval],
    weights: Sequence[float],
    root: int,
    capacity: int,
    *,
    maximize: bool = True,
) -> dict[str, object]:
    """Enumerate span and one forced companion; return best rooted run."""
    if len(intervals) < 2:
        return {"status": "PROVEN_INFEASIBLE", "value": None, "x": None}
    max_endpoint = max(interval.end for interval in intervals)
    best: dict[str, object] | None = None
    for a in range(max_endpoint):
        for b in range(a + 1, max_endpoint + 1):
            if not allowed_in_span(intervals[root], (a, b)):
                continue
            for companion in range(len(intervals)):
                if companion == root:
                    continue
                cell = solve_fixed_span(
                    intervals,
                    weights,
                    root,
                    (a, b),
                    capacity,
                    maximize=maximize,
                    forced_companion=companion,
                )
                if cell["status"] != "CERTIFIED_OPTIMAL_LP_INTEGER":
                    continue
                candidate = {
                    **cell,
                    "span": (a, b),
                    "forced_companion": companion,
                }
                if best is None:
                    best = candidate
                    continue
                if maximize and float(candidate["value"]) > float(best["value"]) + TOL:
                    best = candidate
                if not maximize and float(candidate["value"]) < float(best["value"]) - TOL:
                    best = candidate
    return best or {"status": "PROVEN_INFEASIBLE", "value": None, "x": None}


def brute_fixed_span(
    intervals: Sequence[GridInterval],
    weights: Sequence[float],
    root: int,
    span: tuple[int, int],
    capacity: int,
    *,
    maximize: bool = True,
    forced_companion: int | None = None,
) -> dict[str, object]:
    """Exponential reference solver for tiny deterministic audits only."""
    a, b = span
    best_value: float | None = None
    best_x: list[int] | None = None
    for bits in product((0, 1), repeat=len(intervals)):
        if bits[root] != 1:
            continue
        if forced_companion is not None and bits[forced_companion] != 1:
            continue
        selected = [i for i, bit in enumerate(bits) if bit]
        if any(not allowed_in_span(intervals[i], span) for i in selected):
            continue
        feasible = True
        for k in range(a, b):
            occupancy = sum(covers_segment(intervals[i], k) for i in selected)
            if occupancy < 1 or occupancy > capacity:
                feasible = False
                break
        if not feasible:
            continue
        for k in range(a + 1, b):
            if not any(bridges_boundary(intervals[i], k) for i in selected):
                feasible = False
                break
        if not feasible:
            continue
        value = float(sum(weights[i] for i in selected))
        if best_value is None or (maximize and value > best_value + TOL) or (
            not maximize and value < best_value - TOL
        ):
            best_value = value
            best_x = list(bits)
    if best_value is None:
        return {"status": "PROVEN_INFEASIBLE", "value": None, "x": None}
    return {"status": "BRUTE_OPTIMAL", "value": best_value, "x": best_x}


def self_test() -> None:
    # Endpoint-touch alone must not connect the two sides.
    touch = [GridInterval(0, 1), GridInterval(1, 2)]
    assert solve_fixed_span(touch, [1.0, 1.0], 0, (0, 2), 2)["status"] == "PROVEN_INFEASIBLE"

    # A-B-C chain is connected even though A and C do not overlap.
    chain = [GridInterval(0, 2), GridInterval(1, 3), GridInterval(2, 4)]
    matrix, _labels = augmented_incidence(chain, (0, 4))
    assert consecutive_ones_columns(matrix)
    lp = solve_fixed_span(chain, [1.0, 1.0, 1.0], 0, (0, 4), 2, forced_companion=1)
    assert lp["status"] == "CERTIFIED_OPTIMAL_LP_INTEGER"
    assert lp["x"] == [1, 1, 1]

    # Exhaustive small-library comparison against brute force.
    library = [
        GridInterval(0, 1),
        GridInterval(0, 2),
        GridInterval(1, 2),
        GridInterval(1, 3),
        GridInterval(2, 3),
        GridInterval(0, 3),
    ]
    weights = [0.3, -0.4, 1.2, 0.7, -0.1, 0.5]
    for capacity in (1, 2, 3):
        for root in range(len(library)):
            for a in range(3):
                for b in range(a + 1, 4):
                    for companion in range(len(library)):
                        if companion == root:
                            continue
                        for maximize in (False, True):
                            lp = solve_fixed_span(
                                library,
                                weights,
                                root,
                                (a, b),
                                capacity,
                                maximize=maximize,
                                forced_companion=companion,
                            )
                            brute = brute_fixed_span(
                                library,
                                weights,
                                root,
                                (a, b),
                                capacity,
                                maximize=maximize,
                                forced_companion=companion,
                            )
                            if brute["status"] == "PROVEN_INFEASIBLE":
                                assert lp["status"] == "PROVEN_INFEASIBLE"
                            else:
                                assert lp["status"] == "CERTIFIED_OPTIMAL_LP_INTEGER"
                                assert abs(float(lp["value"]) - float(brute["value"])) <= TOL
    print("ordered-run interval LP oracle self-test: PASS")


if __name__ == "__main__":
    self_test()
