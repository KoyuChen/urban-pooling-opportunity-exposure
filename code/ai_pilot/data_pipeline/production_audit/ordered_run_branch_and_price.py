#!/usr/bin/env python3
"""Exact branch-and-price for the fixed-time ordered-run integer master.

The root-node pricing problem is the integral interval LP used by the existing
column-generation audit.  Integer exactness requires branching because the
cross-run set-partitioning master is not generally integral.  This module uses
an exact finite branching scheme:

1. branch on a fractional optional-buffer usage;
2. once every public row has integral usage, apply Ryan--Foster branching on a
   fractional pair co-membership value.

At a branch node, a run column must satisfy all accumulated together/separate
pair decisions.  Pricing remains exact without a generic run-enumeration step:
each pair disjunction is expanded into forced-in/forced-out cases, and every
case is solved by the same fixed-span interval LP with additional unit rows and
variable bounds.  The number of pricing cases is exponential in branch depth,
so this is an exact medium-instance algorithm, not a polynomial-time claim for
the full integer decomposition.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import itertools
import math
import random
import time
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

import ordered_run_column_generation as root_cg
import ordered_run_fixed_time_master as exhaustive
from ordered_run_interval_oracle import (
    GridInterval,
    allowed_in_span,
    bridges_boundary,
    covers_segment,
)

TOL = 1e-7


@dataclass(frozen=True)
class BranchNode:
    """Canonical branch decisions.

    ``buffer_status`` stores only fixed optional-buffer usages: 0 means the row
    is excluded from every selected run and 1 means it must be used exactly
    once.  Unlisted buffers retain their original at-most-once status.
    Together pairs require equal membership inside every run column; separate
    pairs forbid joint membership.
    """

    buffer_status: tuple[tuple[int, int], ...] = ()
    together_pairs: tuple[tuple[int, int], ...] = ()
    separate_pairs: tuple[tuple[int, int], ...] = ()
    depth: int = 0

    def status_map(self) -> dict[int, int]:
        return dict(self.buffer_status)


@dataclass(frozen=True)
class NodeMaster:
    status: str
    objective: float | None = None
    column_values: tuple[float, ...] = ()
    artificial_values: tuple[float, ...] = ()
    equality_duals: tuple[tuple[int, float], ...] = ()
    inequality_duals: tuple[tuple[int, float], ...] = ()
    core_residual: float | None = None
    buffer_violation: float | None = None
    solver_status: int | None = None
    message: str | None = None


def _pair(left: int, right: int) -> tuple[int, int]:
    if left == right:
        raise ValueError("branch pair must contain two different rows")
    return (left, right) if left < right else (right, left)


def _canonical_node(
    *,
    buffer_status: dict[int, int] | None = None,
    together_pairs: Iterable[tuple[int, int]] = (),
    separate_pairs: Iterable[tuple[int, int]] = (),
    depth: int = 0,
) -> BranchNode:
    statuses = {} if buffer_status is None else dict(buffer_status)
    if any(value not in {0, 1} for value in statuses.values()):
        raise ValueError("buffer status must be zero or one")
    together = tuple(sorted({_pair(*pair) for pair in together_pairs}))
    separate = tuple(sorted({_pair(*pair) for pair in separate_pairs}))
    return BranchNode(
        buffer_status=tuple(sorted(statuses.items())),
        together_pairs=together,
        separate_pairs=separate,
        depth=depth,
    )


def _node_contradiction(model: root_cg.MasterLayout, node: BranchNode) -> str | None:
    status = node.status_map()
    buffer_set = set(model.buffer_positions)
    if any(position not in buffer_set for position in status):
        return "STATUS_ASSIGNED_TO_NONBUFFER_ROW"
    if set(node.together_pairs) & set(node.separate_pairs):
        return "PAIR_BOTH_TOGETHER_AND_SEPARATE"
    excluded = {position for position, value in status.items() if value == 0}
    required = {position for position, value in status.items() if value == 1}
    if excluded & required:
        return "BUFFER_BOTH_REQUIRED_AND_EXCLUDED"
    # A together component containing a mandatory core cannot contain an
    # excluded buffer.  General transitive contradictions are also caught by
    # the pricing-case propagation below; this quick check handles the common
    # case before an LP is built.
    adjacency: dict[int, set[int]] = {position: set() for position in range(len(model.rows))}
    for left, right in node.together_pairs:
        adjacency[left].add(right)
        adjacency[right].add(left)
    seen: set[int] = set()
    mandatory = set(model.core_positions) | required
    for seed in range(len(model.rows)):
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
        if component & mandatory and component & excluded:
            return "TOGETHER_COMPONENT_REQUIRED_AND_EXCLUDED"
    return None


def _column_allowed(column: root_cg.RunColumn, node: BranchNode) -> bool:
    status = node.status_map()
    for position, value in status.items():
        if value == 0 and column.member_mask & (1 << position):
            return False
    for left, right in node.together_pairs:
        left_in = bool(column.member_mask & (1 << left))
        right_in = bool(column.member_mask & (1 << right))
        if left_in != right_in:
            return False
    for left, right in node.separate_pairs:
        if (
            column.member_mask & (1 << left)
            and column.member_mask & (1 << right)
        ):
            return False
    return True


def _filter_columns(
    columns: Iterable[root_cg.RunColumn], node: BranchNode
) -> list[root_cg.RunColumn]:
    by_mask = {
        column.member_mask: column
        for column in columns
        if _column_allowed(column, node)
    }
    return sorted(by_mask.values(), key=lambda column: column.member_mask)


def _row_classes(
    model: root_cg.MasterLayout, node: BranchNode
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    status = node.status_map()
    required = tuple(
        position
        for position in model.buffer_positions
        if status.get(position) == 1
    )
    excluded = tuple(
        position
        for position in model.buffer_positions
        if status.get(position) == 0
    )
    free = tuple(
        position
        for position in model.buffer_positions
        if position not in status
    )
    equalities = tuple(model.core_positions) + required
    return equalities, free, excluded


def _master_matrices(
    model: root_cg.MasterLayout,
    columns: Sequence[root_cg.RunColumn],
    node: BranchNode,
    *,
    include_artificials: bool,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    tuple[int, ...],
    tuple[int, ...],
]:
    equality_positions, free_positions, _excluded = _row_classes(model, node)
    artificial_count = len(equality_positions) if include_artificials else 0
    variable_count = len(columns) + artificial_count
    equality_matrix = np.zeros((len(equality_positions), variable_count))
    for row_number, position in enumerate(equality_positions):
        bit = 1 << position
        for column_number, column in enumerate(columns):
            equality_matrix[row_number, column_number] = float(
                bool(column.member_mask & bit)
            )
        if include_artificials:
            equality_matrix[row_number, len(columns) + row_number] = 1.0
    inequality_matrix = np.zeros((len(free_positions), variable_count))
    for row_number, position in enumerate(free_positions):
        bit = 1 << position
        for column_number, column in enumerate(columns):
            inequality_matrix[row_number, column_number] = float(
                bool(column.member_mask & bit)
            )
    return (
        equality_matrix,
        np.ones(len(equality_positions)),
        inequality_matrix,
        np.ones(len(free_positions)),
        equality_positions,
        free_positions,
    )


def solve_node_master_lp(
    model: root_cg.MasterLayout,
    columns: Sequence[root_cg.RunColumn],
    node: BranchNode,
    phase: str,
) -> NodeMaster:
    if phase not in {"phase1", "max_support"}:
        raise ValueError("phase must be phase1 or max_support")
    columns = _filter_columns(columns, node)
    include_artificials = phase == "phase1"
    (
        equality_matrix,
        equality_rhs,
        inequality_matrix,
        inequality_rhs,
        equality_positions,
        free_positions,
    ) = _master_matrices(
        model, columns, node, include_artificials=include_artificials
    )
    objective = (
        np.concatenate(
            [np.zeros(len(columns)), np.ones(len(equality_positions))]
        )
        if phase == "phase1"
        else np.asarray([-float(column.buffer_count) for column in columns])
    )
    if len(objective) == 0:
        return NodeMaster(status="MASTER_LP_INFEASIBLE", message="no variables")
    result = linprog(
        objective,
        A_ub=inequality_matrix if len(free_positions) else None,
        b_ub=inequality_rhs if len(free_positions) else None,
        A_eq=equality_matrix,
        b_eq=equality_rhs,
        bounds=[(0.0, None)] * len(objective),
        method="highs",
    )
    if not result.success or result.x is None:
        return NodeMaster(
            status=(
                "MASTER_LP_INFEASIBLE"
                if result.status == 2
                else "MASTER_LP_UNRESOLVED"
            ),
            solver_status=int(result.status),
            message=result.message,
        )
    core_residual = float(
        np.max(np.abs(equality_matrix @ result.x - equality_rhs))
    )
    buffer_violation = (
        float(
            np.max(
                np.maximum(
                    inequality_matrix @ result.x - inequality_rhs,
                    0.0,
                )
            )
        )
        if len(free_positions)
        else 0.0
    )
    return NodeMaster(
        status="MASTER_LP_OPTIMAL",
        objective=float(result.fun),
        column_values=tuple(float(value) for value in result.x[: len(columns)]),
        artificial_values=(
            tuple(float(value) for value in result.x[len(columns) :])
            if include_artificials
            else ()
        ),
        equality_duals=tuple(
            (position, float(dual))
            for position, dual in zip(
                equality_positions, np.asarray(result.eqlin.marginals)
            )
        ),
        inequality_duals=(
            tuple(
                (position, float(dual))
                for position, dual in zip(
                    free_positions, np.asarray(result.ineqlin.marginals)
                )
            )
            if len(free_positions)
            else ()
        ),
        core_residual=core_residual,
        buffer_violation=buffer_violation,
        solver_status=int(result.status),
    )


def _propagate_case(
    forced_in: set[int],
    forced_out: set[int],
    together_pairs: Sequence[tuple[int, int]],
    separate_pairs: Sequence[tuple[int, int]],
) -> tuple[set[int], set[int]] | None:
    forced_in = set(forced_in)
    forced_out = set(forced_out)
    changed = True
    while changed:
        if forced_in & forced_out:
            return None
        changed = False
        for left, right in together_pairs:
            if left in forced_in or right in forced_in:
                for position in (left, right):
                    if position not in forced_in:
                        forced_in.add(position)
                        changed = True
            if left in forced_out or right in forced_out:
                for position in (left, right):
                    if position not in forced_out:
                        forced_out.add(position)
                        changed = True
        if forced_in & forced_out:
            return None
        for left, right in separate_pairs:
            if left in forced_in and right in forced_in:
                return None
            if left in forced_in and right not in forced_out:
                forced_out.add(right)
                changed = True
            if right in forced_in and left not in forced_out:
                forced_out.add(left)
                changed = True
    return forced_in, forced_out


def enumerate_pricing_cases(
    row_count: int,
    root: int,
    node: BranchNode,
    excluded_positions: Iterable[int],
    *,
    max_cases: int,
) -> list[tuple[frozenset[int], frozenset[int]]]:
    """Expand pair decisions into forced-in/forced-out LP cases.

    Together(a,b) is the union of ``both in`` and ``both out``.  Separate(a,b)
    is the union of ``a out`` and ``b out``.  Propagation removes most of these
    disjunctions once the priced column's core root is fixed.
    """

    if not (0 <= root < row_count):
        raise ValueError("root index out of range")
    results: set[tuple[frozenset[int], frozenset[int]]] = set()

    def recurse(forced_in: set[int], forced_out: set[int]) -> None:
        if len(results) > max_cases:
            return
        propagated = _propagate_case(
            forced_in,
            forced_out,
            node.together_pairs,
            node.separate_pairs,
        )
        if propagated is None:
            return
        current_in, current_out = propagated
        for left, right in node.together_pairs:
            if (left in current_in and right in current_in) or (
                left in current_out and right in current_out
            ):
                continue
            recurse(current_in | {left, right}, current_out)
            recurse(current_in, current_out | {left, right})
            return
        for left, right in node.separate_pairs:
            if left in current_out or right in current_out:
                continue
            # If one endpoint were forced in, propagation would have forced the
            # other endpoint out.  Thus both are genuinely unresolved here.
            recurse(current_in, current_out | {left})
            recurse(current_in, current_out | {right})
            return
        results.add((frozenset(current_in), frozenset(current_out)))

    recurse({root}, set(excluded_positions))
    if len(results) > max_cases:
        raise RuntimeError("PRICING_CASE_LIMIT")
    return sorted(results, key=lambda pair: (tuple(pair[0]), tuple(pair[1])))


def _solve_fixed_span_forced(
    intervals: Sequence[GridInterval],
    weights: Sequence[float],
    span: tuple[int, int],
    capacity: int,
    forced_in: frozenset[int],
    forced_out: frozenset[int],
) -> dict[str, Any]:
    if forced_in & forced_out:
        return {"status": "PROVEN_INFEASIBLE"}
    if any(not allowed_in_span(intervals[position], span) for position in forced_in):
        return {"status": "PROVEN_INFEASIBLE"}
    a, b = span
    bounds = []
    for position, interval in enumerate(intervals):
        if position in forced_out or not allowed_in_span(interval, span):
            bounds.append((0.0, 0.0))
        else:
            bounds.append((0.0, 1.0))

    inequality_rows: list[np.ndarray] = []
    inequality_rhs: list[float] = []
    for segment in range(a, b):
        row = np.asarray(
            [float(covers_segment(interval, segment)) for interval in intervals]
        )
        inequality_rows.append(row)
        inequality_rhs.append(float(capacity))
        inequality_rows.append(-row)
        inequality_rhs.append(-1.0)
    for boundary in range(a + 1, b):
        row = np.asarray(
            [float(bridges_boundary(interval, boundary)) for interval in intervals]
        )
        inequality_rows.append(-row)
        inequality_rhs.append(-1.0)

    equality_rows: list[np.ndarray] = []
    equality_rhs: list[float] = []
    for position in sorted(forced_in):
        row = np.zeros(len(intervals), dtype=float)
        row[position] = 1.0
        equality_rows.append(row)
        equality_rhs.append(1.0)

    objective = np.asarray(weights, dtype=float)
    result = linprog(
        -objective,
        A_ub=np.asarray(inequality_rows, dtype=float),
        b_ub=np.asarray(inequality_rhs, dtype=float),
        A_eq=np.asarray(equality_rows, dtype=float),
        b_eq=np.asarray(equality_rhs, dtype=float),
        bounds=bounds,
        method="highs",
    )
    if not result.success or result.x is None:
        return {
            "status": "PROVEN_INFEASIBLE" if result.status == 2 else "UNRESOLVED",
            "solver_status": int(result.status),
        }
    rounded = np.rint(result.x)
    residual = float(np.max(np.abs(result.x - rounded)))
    if residual > 1e-8:
        return {
            "status": "NONINTEGRAL_NUMERICAL_RESULT",
            "integrality_residual": residual,
        }
    return {
        "status": "CERTIFIED_OPTIMAL_LP_INTEGER",
        "value": float(objective @ rounded),
        "x": tuple(int(value) for value in rounded),
        "integrality_residual": residual,
    }


def _better_priced(
    candidate: dict[str, Any], incumbent: dict[str, Any] | None
) -> bool:
    if incumbent is None:
        return True
    candidate_value = float(candidate["value"])
    incumbent_value = float(incumbent["value"])
    if candidate_value > incumbent_value + TOL:
        return True
    if abs(candidate_value - incumbent_value) <= TOL:
        return (
            tuple(candidate["x"]),
            tuple(candidate["span"]),
        ) < (
            tuple(incumbent["x"]),
            tuple(incumbent["span"]),
        )
    return False


def _solve_rooted_case(
    intervals: Sequence[GridInterval],
    weights: Sequence[float],
    capacity: int,
    forced_in: frozenset[int],
    forced_out: frozenset[int],
) -> dict[str, Any]:
    earliest_forced_start = min(intervals[position].start for position in forced_in)
    latest_forced_end = max(intervals[position].end for position in forced_in)
    starts = sorted(
        {
            interval.start
            for interval in intervals
            if interval.start <= earliest_forced_start
        }
    )
    ends = sorted(
        {
            interval.end
            for interval in intervals
            if interval.end >= latest_forced_end
        }
    )
    best: dict[str, Any] | None = None
    lp_solve_count = 0
    span_count = 0
    for start in starts:
        for end in ends:
            if start >= end:
                continue
            span = (start, end)
            if any(
                not allowed_in_span(intervals[position], span)
                for position in forced_in
            ):
                continue
            span_count += 1
            result = _solve_fixed_span_forced(
                intervals,
                weights,
                span,
                capacity,
                forced_in,
                forced_out,
            )
            lp_solve_count += 1
            if result["status"] == "PROVEN_INFEASIBLE":
                continue
            if result["status"] != "CERTIFIED_OPTIMAL_LP_INTEGER":
                return {
                    "status": "UNRESOLVED_PRICING",
                    "detail": result,
                    "lp_solve_count": lp_solve_count,
                    "candidate_span_count": span_count,
                }
            candidates: list[dict[str, Any]] = []
            if sum(result["x"]) >= 2:
                candidates.append({**result, "span": span})
            else:
                for companion, interval in enumerate(intervals):
                    if companion in forced_in or companion in forced_out:
                        continue
                    if not allowed_in_span(interval, span):
                        continue
                    forced = _solve_fixed_span_forced(
                        intervals,
                        weights,
                        span,
                        capacity,
                        forced_in | {companion},
                        forced_out,
                    )
                    lp_solve_count += 1
                    if forced["status"] == "PROVEN_INFEASIBLE":
                        continue
                    if forced["status"] != "CERTIFIED_OPTIMAL_LP_INTEGER":
                        return {
                            "status": "UNRESOLVED_PRICING",
                            "detail": forced,
                            "lp_solve_count": lp_solve_count,
                            "candidate_span_count": span_count,
                        }
                    candidates.append({**forced, "span": span})
            for candidate in candidates:
                if _better_priced(candidate, best):
                    best = candidate
    if best is None:
        return {
            "status": "PROVEN_INFEASIBLE",
            "lp_solve_count": lp_solve_count,
            "candidate_span_count": span_count,
        }
    return {
        **best,
        "lp_solve_count": lp_solve_count,
        "candidate_span_count": span_count,
    }


def solve_rooted_run_at_node(
    model: root_cg.MasterLayout,
    intervals: Sequence[GridInterval],
    weights: Sequence[float],
    root: int,
    capacity: int,
    node: BranchNode,
    *,
    max_cases: int,
) -> dict[str, Any]:
    _equalities, _free, excluded = _row_classes(model, node)
    try:
        cases = enumerate_pricing_cases(
            len(model.rows),
            root,
            node,
            excluded,
            max_cases=max_cases,
        )
    except RuntimeError as error:
        return {"status": str(error), "value": None, "x": None}
    best: dict[str, Any] | None = None
    total_lp_solves = 0
    total_spans = 0
    for forced_in, forced_out in cases:
        result = _solve_rooted_case(
            intervals,
            weights,
            capacity,
            forced_in,
            forced_out,
        )
        total_lp_solves += int(result.get("lp_solve_count", 0))
        total_spans += int(result.get("candidate_span_count", 0))
        if result["status"] == "PROVEN_INFEASIBLE":
            continue
        if result["status"] != "CERTIFIED_OPTIMAL_LP_INTEGER":
            return {
                "status": "UNRESOLVED_PRICING",
                "detail": result,
                "lp_solve_count": total_lp_solves,
                "candidate_span_count": total_spans,
                "pricing_case_count": len(cases),
            }
        if _better_priced(result, best):
            best = result
    if best is None:
        return {
            "status": "PROVEN_INFEASIBLE",
            "value": None,
            "x": None,
            "lp_solve_count": total_lp_solves,
            "candidate_span_count": total_spans,
            "pricing_case_count": len(cases),
        }
    return {
        **best,
        "lp_solve_count": total_lp_solves,
        "candidate_span_count": total_spans,
        "pricing_case_count": len(cases),
    }


def _priced_column(
    solution: Sequence[int], model: root_cg.MasterLayout
) -> root_cg.RunColumn:
    member_mask = sum(
        1 << position for position, selected in enumerate(solution) if selected
    )
    core_mask = member_mask & model.all_core_mask
    buffer_mask = member_mask & model.all_buffer_mask
    if member_mask.bit_count() < 2 or not core_mask:
        raise ValueError("priced run is not a physical core-containing run")
    return root_cg.RunColumn(member_mask, core_mask, buffer_mask)


def price_node_columns(
    model: root_cg.MasterLayout,
    intervals: Sequence[GridInterval],
    master: NodeMaster,
    phase: str,
    capacity: int,
    node: BranchNode,
    *,
    max_cases: int,
) -> dict[str, Any]:
    duals = dict(master.equality_duals)
    duals.update(dict(master.inequality_duals))
    weights = np.zeros(len(model.rows))
    for position in range(len(model.rows)):
        weights[position] = float(duals.get(position, 0.0))
        if phase == "max_support" and position in model.buffer_positions:
            weights[position] += 1.0

    candidates: dict[int, tuple[root_cg.RunColumn, float]] = {}
    minimum_reduced_cost = math.inf
    total_lp_solves = 0
    total_spans = 0
    total_cases = 0
    maximum_cases_for_one_root = 0
    for root in model.core_positions:
        priced = solve_rooted_run_at_node(
            model,
            intervals,
            weights,
            root,
            capacity,
            node,
            max_cases=max_cases,
        )
        total_lp_solves += int(priced.get("lp_solve_count", 0))
        total_spans += int(priced.get("candidate_span_count", 0))
        root_cases = int(priced.get("pricing_case_count", 0))
        total_cases += root_cases
        maximum_cases_for_one_root = max(maximum_cases_for_one_root, root_cases)
        if priced["status"] == "PROVEN_INFEASIBLE":
            continue
        if priced["status"] != "CERTIFIED_OPTIMAL_LP_INTEGER":
            return {
                "status": "PRICING_UNRESOLVED",
                "root": root,
                "detail": priced,
                "lp_solve_count": total_lp_solves,
                "candidate_span_count": total_spans,
                "pricing_case_count": total_cases,
            }
        column = _priced_column(priced["x"], model)
        if not _column_allowed(column, node):
            raise AssertionError("pricing returned a column violating branch decisions")
        column_cost = 0.0 if phase == "phase1" else -float(column.buffer_count)
        dual_sum = sum(
            float(dual)
            for position, dual in duals.items()
            if column.member_mask & (1 << position)
        )
        reduced_cost = column_cost - dual_sum
        if abs(reduced_cost + float(priced["value"])) > 1e-6:
            raise AssertionError("pricing objective and reduced cost disagree")
        minimum_reduced_cost = min(minimum_reduced_cost, reduced_cost)
        previous = candidates.get(column.member_mask)
        if previous is None or reduced_cost < previous[1]:
            candidates[column.member_mask] = (column, reduced_cost)
    return {
        "status": "PRICING_CERTIFIED",
        "minimum_reduced_cost": (
            None if minimum_reduced_cost == math.inf else minimum_reduced_cost
        ),
        "improving_columns": [
            column
            for column, reduced_cost in candidates.values()
            if reduced_cost < -TOL
        ],
        "lp_solve_count": total_lp_solves,
        "candidate_span_count": total_spans,
        "pricing_case_count": total_cases,
        "maximum_cases_for_one_root": maximum_cases_for_one_root,
    }


def solve_restricted_integer_at_node(
    model: root_cg.MasterLayout,
    columns: Sequence[root_cg.RunColumn],
    node: BranchNode,
) -> dict[str, Any]:
    columns = _filter_columns(columns, node)
    if not columns:
        return {"status": "RESTRICTED_INTEGER_INFEASIBLE", "value": None}
    (
        equality_matrix,
        equality_rhs,
        inequality_matrix,
        inequality_rhs,
        _equality_positions,
        _free_positions,
    ) = _master_matrices(
        model, columns, node, include_artificials=False
    )
    matrix = np.vstack([equality_matrix, inequality_matrix])
    lower = np.concatenate(
        [equality_rhs, np.zeros(inequality_matrix.shape[0])]
    )
    upper = np.concatenate([equality_rhs, inequality_rhs])
    objective = np.asarray([-float(column.buffer_count) for column in columns])
    result = milp(
        objective,
        integrality=np.ones(len(columns), dtype=int),
        bounds=Bounds(np.zeros(len(columns)), np.ones(len(columns))),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"presolve": True},
    )
    if result.status == 2:
        return {"status": "RESTRICTED_INTEGER_INFEASIBLE", "value": None}
    if not result.success or result.x is None:
        return {
            "status": "RESTRICTED_INTEGER_UNRESOLVED",
            "value": None,
            "solver_status": int(result.status),
        }
    rounded = np.rint(result.x)
    residual = max(
        float(np.max(np.abs(result.x - rounded))),
        float(np.max(np.abs(equality_matrix @ rounded - equality_rhs))),
        (
            float(
                np.max(
                    np.maximum(
                        inequality_matrix @ rounded - inequality_rhs,
                        0.0,
                    )
                )
            )
            if inequality_matrix.shape[0]
            else 0.0
        ),
    )
    if residual > TOL:
        return {
            "status": "RESTRICTED_INTEGER_INVALID_INCUMBENT",
            "value": None,
            "residual": residual,
        }
    selected = tuple(
        columns[index].member_mask
        for index, value in enumerate(rounded)
        if value > 0.5
    )
    return {
        "status": "RESTRICTED_INTEGER_FEASIBLE",
        "value": float(-objective @ rounded),
        "residual": residual,
        "selected_member_masks": selected,
        "selected_column_count": len(selected),
    }


def column_generation_at_node(
    rows: Sequence[exhaustive.FixedTimeRow],
    capacity: int,
    node: BranchNode,
    *,
    initial_columns: Sequence[root_cg.RunColumn] = (),
    max_iterations_per_phase: int = 100,
    max_pricing_cases: int = 4096,
) -> dict[str, Any]:
    model = root_cg.layout(rows)
    contradiction = _node_contradiction(model, node)
    if contradiction is not None:
        return {"status": "NODE_PROVEN_INFEASIBLE", "reason": contradiction}
    intervals = root_cg.compress_endpoints(model.rows)
    seeds = root_cg.seed_pair_columns(model, intervals, capacity)
    columns_by_mask = {
        column.member_mask: column
        for column in _filter_columns(
            itertools.chain(seeds, initial_columns), node
        )
    }
    history: list[dict[str, Any]] = []
    total_oracle_lp_solves = 0
    total_candidate_spans = 0
    total_pricing_cases = 0
    maximum_cases_for_one_root = 0
    final_master: NodeMaster | None = None

    for phase in ("phase1", "max_support"):
        for iteration in range(max_iterations_per_phase):
            columns = sorted(columns_by_mask.values(), key=lambda column: column.member_mask)
            master = solve_node_master_lp(model, columns, node, phase)
            if master.status != "MASTER_LP_OPTIMAL":
                return {
                    "status": (
                        "NODE_PROVEN_INFEASIBLE"
                        if master.status == "MASTER_LP_INFEASIBLE"
                        else "NODE_LP_UNRESOLVED"
                    ),
                    "phase": phase,
                    "master": master.__dict__,
                }
            priced = price_node_columns(
                model,
                intervals,
                master,
                phase,
                capacity,
                node,
                max_cases=max_pricing_cases,
            )
            total_oracle_lp_solves += int(priced.get("lp_solve_count", 0))
            total_candidate_spans += int(priced.get("candidate_span_count", 0))
            total_pricing_cases += int(priced.get("pricing_case_count", 0))
            maximum_cases_for_one_root = max(
                maximum_cases_for_one_root,
                int(priced.get("maximum_cases_for_one_root", 0)),
            )
            if priced["status"] != "PRICING_CERTIFIED":
                return {
                    "status": "NODE_PRICING_UNRESOLVED",
                    "phase": phase,
                    "pricing": priced,
                    "history": history,
                }
            new_columns = 0
            for column in priced["improving_columns"]:
                if column.member_mask not in columns_by_mask:
                    columns_by_mask[column.member_mask] = column
                    new_columns += 1
            history.append(
                {
                    "phase": phase,
                    "iteration": iteration,
                    "master_objective": master.objective,
                    "minimum_reduced_cost": priced["minimum_reduced_cost"],
                    "new_column_count": new_columns,
                    "column_count_before_addition": len(columns),
                    "oracle_lp_solve_count": priced["lp_solve_count"],
                    "pricing_case_count": priced["pricing_case_count"],
                }
            )
            if new_columns == 0:
                minimum_reduced_cost = priced["minimum_reduced_cost"]
                if (
                    minimum_reduced_cost is not None
                    and float(minimum_reduced_cost) < -10 * TOL
                ):
                    return {
                        "status": "NODE_PRICING_STALLED_ON_DUPLICATE",
                        "phase": phase,
                        "history": history,
                    }
                final_master = master
                break
        else:
            return {
                "status": "NODE_COLUMN_GENERATION_ITERATION_LIMIT",
                "phase": phase,
                "history": history,
            }
        if phase == "phase1":
            artificial_mass = sum(final_master.artificial_values)
            if artificial_mass > TOL:
                return {
                    "status": "NODE_PROVEN_INFEASIBLE",
                    "reason": "POSITIVE_PHASE_ONE_ARTIFICIAL_MASS",
                    "phase_one_artificial_mass": artificial_mass,
                    "generated_column_count": len(columns_by_mask),
                    "history": history,
                }
            final_master = None

    columns = sorted(columns_by_mask.values(), key=lambda column: column.member_mask)
    restricted_integer = solve_restricted_integer_at_node(model, columns, node)
    return {
        "status": "NODE_LP_CERTIFIED_OPTIMAL",
        "capacity": capacity,
        "node": node,
        "lp_upper_bound": -float(final_master.objective),
        "columns": columns,
        "column_values": final_master.column_values,
        "restricted_integer": restricted_integer,
        "phase_one_iterations": sum(row["phase"] == "phase1" for row in history),
        "phase_two_iterations": sum(row["phase"] == "max_support" for row in history),
        "total_oracle_lp_solve_count": total_oracle_lp_solves,
        "total_candidate_span_count": total_candidate_spans,
        "total_pricing_case_count": total_pricing_cases,
        "maximum_cases_for_one_root": maximum_cases_for_one_root,
        "master_core_residual": final_master.core_residual,
        "master_buffer_violation": final_master.buffer_violation,
        "history": history,
    }


def _buffer_usages(
    model: root_cg.MasterLayout,
    columns: Sequence[root_cg.RunColumn],
    values: Sequence[float],
) -> dict[int, float]:
    return {
        position: float(
            sum(
                value
                for column, value in zip(columns, values)
                if column.member_mask & (1 << position)
            )
        )
        for position in model.buffer_positions
    }


def _fractional_buffer_branch(
    model: root_cg.MasterLayout,
    node: BranchNode,
    usages: dict[int, float],
) -> tuple[int, float] | None:
    status = node.status_map()
    candidates = [
        (position, usage)
        for position, usage in usages.items()
        if position not in status and TOL < usage < 1.0 - TOL
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: (abs(item[1] - 0.5), item[0]))


def _fractional_pair_branch(
    model: root_cg.MasterLayout,
    node: BranchNode,
    columns: Sequence[root_cg.RunColumn],
    values: Sequence[float],
    usages: dict[int, float],
) -> tuple[int, int, float] | None:
    active = list(model.core_positions) + [
        position
        for position in model.buffer_positions
        if usages[position] >= 1.0 - TOL
    ]
    already = set(node.together_pairs) | set(node.separate_pairs)
    candidates: list[tuple[int, int, float]] = []
    for left, right in itertools.combinations(sorted(active), 2):
        pair = _pair(left, right)
        if pair in already:
            continue
        together_value = float(
            sum(
                value
                for column, value in zip(columns, values)
                if column.member_mask & (1 << left)
                and column.member_mask & (1 << right)
            )
        )
        if TOL < together_value < 1.0 - TOL:
            candidates.append((left, right, together_value))
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (abs(item[2] - 0.5), item[0], item[1]),
    )


def _with_buffer_status(
    node: BranchNode, position: int, value: int
) -> BranchNode | None:
    status = node.status_map()
    if position in status and status[position] != value:
        return None
    status[position] = value
    return _canonical_node(
        buffer_status=status,
        together_pairs=node.together_pairs,
        separate_pairs=node.separate_pairs,
        depth=node.depth + 1,
    )


def _with_pair(
    model: root_cg.MasterLayout,
    node: BranchNode,
    left: int,
    right: int,
    *,
    together: bool,
) -> BranchNode | None:
    pair = _pair(left, right)
    together_pairs = set(node.together_pairs)
    separate_pairs = set(node.separate_pairs)
    if together:
        if pair in separate_pairs:
            return None
        together_pairs.add(pair)
    else:
        if pair in together_pairs:
            return None
        separate_pairs.add(pair)
    status = node.status_map()
    if together:
        for position in pair:
            if position in model.buffer_positions:
                if status.get(position) == 0:
                    return None
                status[position] = 1
    return _canonical_node(
        buffer_status=status,
        together_pairs=together_pairs,
        separate_pairs=separate_pairs,
        depth=node.depth + 1,
    )


def branch_and_price_max_support(
    rows: Sequence[exhaustive.FixedTimeRow],
    capacity: int,
    *,
    max_nodes: int = 5000,
    time_limit_seconds: float = 1800.0,
    max_iterations_per_phase: int = 100,
    max_pricing_cases: int = 4096,
) -> dict[str, Any]:
    """Certify the integer support maximum or return a rigorous open gap."""

    if capacity < 2:
        raise ValueError("capacity must be at least two")
    if max_nodes <= 0 or time_limit_seconds <= 0:
        raise ValueError("node and time limits must be positive")
    model = root_cg.layout(rows)
    started = time.perf_counter()
    root = _canonical_node()
    queue: list[
        tuple[float, int, BranchNode, tuple[root_cg.RunColumn, ...]]
    ] = []
    serial = 0
    heapq.heappush(queue, (-math.inf, serial, root, ()))
    seen: set[tuple[Any, ...]] = set()
    incumbent_value = -math.inf
    incumbent_masks: tuple[int, ...] = ()
    nodes_processed = 0
    nodes_infeasible = 0
    nodes_bound_pruned = 0
    nodes_integral = 0
    buffer_branches = 0
    pair_branches = 0
    total_generated_columns = 0
    total_oracle_lp_solves = 0
    total_pricing_cases = 0
    maximum_pricing_cases_for_one_root = 0
    maximum_depth = 0
    root_lp_bound: float | None = None
    unresolved_reason: str | None = None

    while queue:
        elapsed = time.perf_counter() - started
        if nodes_processed >= max_nodes:
            unresolved_reason = "NODE_LIMIT"
            break
        if elapsed >= time_limit_seconds:
            unresolved_reason = "TIME_LIMIT"
            break
        negative_hint, _item_serial, node, warm_columns = heapq.heappop(queue)
        hint = -negative_hint
        node_key = (
            node.buffer_status,
            node.together_pairs,
            node.separate_pairs,
        )
        if node_key in seen:
            continue
        seen.add(node_key)
        if math.isfinite(hint) and hint <= incumbent_value + TOL:
            nodes_bound_pruned += 1
            continue

        solved = column_generation_at_node(
            rows,
            capacity,
            node,
            initial_columns=warm_columns,
            max_iterations_per_phase=max_iterations_per_phase,
            max_pricing_cases=max_pricing_cases,
        )
        nodes_processed += 1
        maximum_depth = max(maximum_depth, node.depth)
        if solved["status"] == "NODE_PROVEN_INFEASIBLE":
            nodes_infeasible += 1
            continue
        if solved["status"] != "NODE_LP_CERTIFIED_OPTIMAL":
            unresolved_reason = solved["status"]
            break

        upper_bound = float(solved["lp_upper_bound"])
        if node.depth == 0:
            root_lp_bound = upper_bound
        total_generated_columns += len(solved["columns"])
        total_oracle_lp_solves += int(solved["total_oracle_lp_solve_count"])
        total_pricing_cases += int(solved["total_pricing_case_count"])
        maximum_pricing_cases_for_one_root = max(
            maximum_pricing_cases_for_one_root,
            int(solved["maximum_cases_for_one_root"]),
        )
        restricted = solved["restricted_integer"]
        if restricted.get("status") == "RESTRICTED_INTEGER_FEASIBLE":
            value = float(restricted["value"])
            if value > incumbent_value + TOL:
                incumbent_value = value
                incumbent_masks = tuple(restricted["selected_member_masks"])
        if upper_bound <= incumbent_value + TOL:
            nodes_bound_pruned += 1
            continue

        values = tuple(float(value) for value in solved["column_values"])
        columns = tuple(solved["columns"])
        integrality_residual = max(
            (abs(value - round(value)) for value in values), default=0.0
        )
        if integrality_residual <= TOL:
            nodes_integral += 1
            integer_value = float(
                sum(
                    column.buffer_count * round(value)
                    for column, value in zip(columns, values)
                )
            )
            if integer_value > incumbent_value + TOL:
                incumbent_value = integer_value
                incumbent_masks = tuple(
                    column.member_mask
                    for column, value in zip(columns, values)
                    if round(value) == 1
                )
            continue

        usages = _buffer_usages(model, columns, values)
        buffer_branch = _fractional_buffer_branch(model, node, usages)
        children: list[BranchNode] = []
        if buffer_branch is not None:
            position, _usage = buffer_branch
            zero_child = _with_buffer_status(node, position, 0)
            one_child = _with_buffer_status(node, position, 1)
            children = [child for child in (zero_child, one_child) if child is not None]
            buffer_branches += 1
        else:
            pair_branch = _fractional_pair_branch(
                model, node, columns, values, usages
            )
            if pair_branch is None:
                unresolved_reason = "NO_FRACTIONAL_RYAN_FOSTER_PAIR"
                break
            left, right, _together_value = pair_branch
            separate_child = _with_pair(
                model, node, left, right, together=False
            )
            together_child = _with_pair(
                model, node, left, right, together=True
            )
            children = [
                child
                for child in (separate_child, together_child)
                if child is not None
            ]
            pair_branches += 1
        for child in children:
            serial += 1
            heapq.heappush(queue, (-upper_bound, serial, child, columns))

    elapsed = time.perf_counter() - started
    if unresolved_reason is None and not queue:
        if incumbent_value == -math.inf:
            return {
                "status": "INTEGER_MASTER_PROVEN_INFEASIBLE",
                "capacity": capacity,
                "nodes_processed": nodes_processed,
                "elapsed_seconds": elapsed,
            }
        return {
            "status": "INTEGER_OPTIMUM_CERTIFIED",
            "capacity": capacity,
            "integer_maximum_selected_buffers": incumbent_value,
            "global_lower_bound": incumbent_value,
            "global_upper_bound": incumbent_value,
            "root_lp_upper_bound": root_lp_bound,
            "root_integrality_gap": (
                None
                if root_lp_bound is None
                else root_lp_bound - incumbent_value
            ),
            "nodes_processed": nodes_processed,
            "nodes_infeasible": nodes_infeasible,
            "nodes_bound_pruned": nodes_bound_pruned,
            "nodes_integral": nodes_integral,
            "buffer_branches": buffer_branches,
            "pair_branches": pair_branches,
            "maximum_depth": maximum_depth,
            "total_generated_columns_across_nodes": total_generated_columns,
            "total_oracle_lp_solve_count": total_oracle_lp_solves,
            "total_pricing_case_count": total_pricing_cases,
            "maximum_pricing_cases_for_one_root": maximum_pricing_cases_for_one_root,
            "selected_column_count": len(incumbent_masks),
            "elapsed_seconds": elapsed,
        }

    open_upper_bounds = [-item[0] for item in queue if math.isfinite(-item[0])]
    global_upper = max(
        [bound for bound in open_upper_bounds]
        + ([root_lp_bound] if root_lp_bound is not None else [])
        + ([incumbent_value] if incumbent_value > -math.inf else [])
    ) if (open_upper_bounds or root_lp_bound is not None or incumbent_value > -math.inf) else None
    return {
        "status": "INTEGER_BRANCH_AND_PRICE_UNRESOLVED",
        "reason": unresolved_reason,
        "capacity": capacity,
        "global_lower_bound": (
            None if incumbent_value == -math.inf else incumbent_value
        ),
        "global_upper_bound": global_upper,
        "absolute_gap": (
            None
            if incumbent_value == -math.inf or global_upper is None
            else global_upper - incumbent_value
        ),
        "root_lp_upper_bound": root_lp_bound,
        "open_node_count": len(queue),
        "nodes_processed": nodes_processed,
        "nodes_infeasible": nodes_infeasible,
        "nodes_bound_pruned": nodes_bound_pruned,
        "nodes_integral": nodes_integral,
        "buffer_branches": buffer_branches,
        "pair_branches": pair_branches,
        "maximum_depth": maximum_depth,
        "total_generated_columns_across_nodes": total_generated_columns,
        "total_oracle_lp_solve_count": total_oracle_lp_solves,
        "total_pricing_case_count": total_pricing_cases,
        "maximum_pricing_cases_for_one_root": maximum_pricing_cases_for_one_root,
        "elapsed_seconds": elapsed,
    }


def compare_with_exhaustive(
    rows: Sequence[exhaustive.FixedTimeRow],
    capacity: int,
    *,
    epsilon: float = 0.1,
    max_nodes: int = 5000,
    time_limit_seconds: float = 600.0,
) -> dict[str, Any]:
    exact_master = exhaustive.build_master(rows, capacity, epsilon=epsilon)
    exact_value = exhaustive.support_frontier(exact_master)[
        "maximum_selected_buffers"
    ]
    result = branch_and_price_max_support(
        rows,
        capacity,
        max_nodes=max_nodes,
        time_limit_seconds=time_limit_seconds,
    )
    if exact_value is None:
        if result["status"] != "INTEGER_MASTER_PROVEN_INFEASIBLE":
            raise AssertionError("branch-and-price did not reproduce infeasibility")
    else:
        if result["status"] != "INTEGER_OPTIMUM_CERTIFIED":
            raise AssertionError(f"branch-and-price unresolved: {result}")
        if abs(
            float(result["integer_maximum_selected_buffers"])
            - float(exact_value)
        ) > TOL:
            raise AssertionError("branch-and-price and exhaustive master disagree")
    return {
        **result,
        "full_run_column_count": len(exact_master.columns),
        "exhaustive_integer_maximum_selected_buffers": exact_value,
        "exhaustive_master_state_count": exact_master.explored_state_count,
    }


def _random_rows(seed: int) -> list[exhaustive.FixedTimeRow]:
    generator = random.Random(seed)
    rows: list[exhaustive.FixedTimeRow] = []
    for index in range(3):
        start = generator.randrange(0, 5)
        end = generator.randrange(start + 1, 7)
        rows.append(exhaustive.FixedTimeRow(index, "core", start, end))
    for offset in range(4):
        start = generator.randrange(0, 5)
        end = generator.randrange(start + 1, 7)
        rows.append(exhaustive.FixedTimeRow(3 + offset, "buffer", start, end))
    return rows


def self_test() -> None:
    pairable = [
        exhaustive.FixedTimeRow(0, "core", 0, 2),
        exhaustive.FixedTimeRow(1, "core", 3, 5),
        exhaustive.FixedTimeRow(2, "buffer", 0, 1.5),
        exhaustive.FixedTimeRow(3, "buffer", 3.5, 5),
    ]
    pair_result = compare_with_exhaustive(pairable, 2)
    assert pair_result["integer_maximum_selected_buffers"] == 2.0

    for seed in range(12):
        rows = _random_rows(seed)
        for capacity in (2, 3):
            compare_with_exhaustive(rows, capacity)

    gap = compare_with_exhaustive(
        root_cg.integrality_gap_counterexample(), 2
    )
    assert gap["root_lp_upper_bound"] == 4.0
    assert gap["integer_maximum_selected_buffers"] == 3.0
    assert gap["nodes_processed"] > 1
    print("ordered-run branch-and-price self-test: PASS")


if __name__ == "__main__":
    self_test()
