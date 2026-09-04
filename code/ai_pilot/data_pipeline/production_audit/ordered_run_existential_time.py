#!/usr/bin/env python3
"""Exact continuous-time MILP for one cohort of latent ordered runs.

Each public row receives one latent pickup/drop-off completion inside supplied
closed intervals. Core rows are partitioned into connected latent runs; buffer
rows are optional and can enter at most one run. Positive-overlap connectivity
is enforced by a rooted flow on selected overlap edges. Simultaneous occupancy
is enforced exactly by C-coloring each interval graph with disjunctive seat
constraints. Because interval graphs are perfect, a C-seat assignment exists
if and only if maximum simultaneous occupancy is at most C.

The formulation is intended for small audit cohorts. It is exact for the
declared support intervals and positive-overlap margin, but it does not recover
actual vehicle runs, co-riders, or realized capacity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, lil_matrix

CERTIFIED = "OPTIMAL_NUMERICAL_MILP"
TOL = 1e-6


@dataclass(frozen=True)
class TimeSupportRow:
    index: int
    role: str
    start_lower: float
    start_upper: float
    end_lower: float
    end_upper: float
    miles: float | None = None
    seconds: float | None = None

    def __post_init__(self) -> None:
        if self.role not in {"core", "buffer"}:
            raise ValueError("role must be core or buffer")
        if self.start_lower > self.start_upper:
            raise ValueError("invalid start support")
        if self.end_lower > self.end_upper:
            raise ValueError("invalid end support")


@dataclass
class Program:
    rows: list[TimeSupportRow]
    roots: list[int]
    capacity: int
    common_buffer_count: int
    epsilon: float
    big_m: float
    y_col: dict[int, int]
    x_col: dict[tuple[int, int], int]
    seat_col: dict[tuple[int, int, int], int]
    edge_col: dict[tuple[int, int, int], int]
    flow_col: dict[tuple[int, int, int], int]
    order_col: dict[tuple[int, int, int, int], int]
    start_col: dict[int, int]
    end_col: dict[int, int]
    matrix: csr_matrix
    lower: np.ndarray
    upper: np.ndarray
    bounds: Bounds
    integrality: np.ndarray


def build_program(
    rows: Sequence[TimeSupportRow],
    capacity: int,
    common_buffer_count: int,
    *,
    epsilon: float = 1.0,
) -> Program:
    rows = list(rows)
    if capacity < 2:
        raise ValueError("capacity must be at least two")
    if common_buffer_count < 0:
        raise ValueError("common_buffer_count must be nonnegative")
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    if len({row.index for row in rows}) != len(rows):
        raise ValueError("row indices must be unique")
    by_index = {row.index: row for row in rows}
    roots = sorted(row.index for row in rows if row.role == "core")
    buffers = sorted(row.index for row in rows if row.role == "buffer")
    if not roots:
        raise ValueError("at least one core row is required")
    if common_buffer_count > len(buffers):
        raise ValueError("common buffer count exceeds available buffers")

    # Canonical representation: the smallest-index core in a run is its root.
    def allowed(member: int, root: int) -> bool:
        row = by_index[member]
        return row.role == "buffer" or member >= root

    cursor = 0
    y_col: dict[int, int] = {}
    for root in roots:
        y_col[root] = cursor
        cursor += 1

    x_col: dict[tuple[int, int], int] = {}
    for root in roots:
        for member in sorted(by_index):
            if allowed(member, root):
                x_col[(member, root)] = cursor
                cursor += 1

    seat_col: dict[tuple[int, int, int], int] = {}
    for member, root in x_col:
        for seat in range(capacity):
            seat_col[(member, root, seat)] = cursor
            cursor += 1

    edge_col: dict[tuple[int, int, int], int] = {}
    flow_col: dict[tuple[int, int, int], int] = {}
    pairs_by_root: dict[int, list[tuple[int, int]]] = {}
    for root in roots:
        members = [member for member in sorted(by_index) if (member, root) in x_col]
        pairs: list[tuple[int, int]] = []
        for left_pos, left in enumerate(members):
            for right in members[left_pos + 1 :]:
                edge_col[(left, right, root)] = cursor
                cursor += 1
                flow_col[(left, right, root)] = cursor
                cursor += 1
                flow_col[(right, left, root)] = cursor
                cursor += 1
                pairs.append((left, right))
        pairs_by_root[root] = pairs

    order_col: dict[tuple[int, int, int, int], int] = {}
    for root in roots:
        for left, right in pairs_by_root[root]:
            for seat in range(capacity):
                order_col[(left, right, root, seat)] = cursor
                cursor += 1

    start_col: dict[int, int] = {}
    end_col: dict[int, int] = {}
    for member in sorted(by_index):
        start_col[member] = cursor
        cursor += 1
        end_col[member] = cursor
        cursor += 1
    variable_count = cursor

    all_endpoints = [
        value
        for row in rows
        for value in (
            row.start_lower,
            row.start_upper,
            row.end_lower,
            row.end_upper,
        )
    ]
    earliest = min(all_endpoints)
    latest = max(all_endpoints)
    big_m = max(1.0, latest - earliest + 2.0 * epsilon)
    max_flow = max(1, len(rows) - 1)

    constraints: list[tuple[dict[int, float], float, float]] = []

    def add(
        coefficients: dict[int, float],
        lower: float = -np.inf,
        upper: float = np.inf,
    ) -> None:
        constraints.append((coefficients, lower, upper))

    # Every completion is a positive-length interval.
    for member in sorted(by_index):
        add(
            {end_col[member]: 1.0, start_col[member]: -1.0},
            epsilon,
            np.inf,
        )

    # Root identity, activation, and canonical assignments.
    for root in roots:
        add({x_col[(root, root)]: 1.0, y_col[root]: -1.0}, 0.0, 0.0)
        for member in sorted(by_index):
            if (member, root) in x_col:
                add(
                    {x_col[(member, root)]: 1.0, y_col[root]: -1.0},
                    -np.inf,
                    0.0,
                )

    # Core rows are partitioned exactly once; buffers are used at most once.
    for member, row in by_index.items():
        assignment_columns = [
            x_col[(member, root)]
            for root in roots
            if (member, root) in x_col
        ]
        coefficients = {column: 1.0 for column in assignment_columns}
        if row.role == "core":
            add(coefficients, 1.0, 1.0)
        else:
            add(coefficients, 0.0, 1.0)

    # Every open run contains at least two rows.
    for root in roots:
        coefficients = {
            x_col[(member, root)]: 1.0
            for member in by_index
            if (member, root) in x_col
        }
        coefficients[y_col[root]] = -2.0
        add(coefficients, 0.0, np.inf)

    # Common selected-buffer cardinality.
    buffer_coefficients: dict[int, float] = {}
    for member in buffers:
        for root in roots:
            if (member, root) in x_col:
                buffer_coefficients[x_col[(member, root)]] = 1.0
    add(
        buffer_coefficients,
        float(common_buffer_count),
        float(common_buffer_count),
    )

    # A selected row occupies exactly one of C seats in its run.
    for (member, root), assignment_column in x_col.items():
        coefficients = {
            seat_col[(member, root, seat)]: 1.0
            for seat in range(capacity)
        }
        coefficients[assignment_column] = -1.0
        add(coefficients, 0.0, 0.0)

    # Rows sharing a seat are temporally nonoverlapping. The order binary chooses
    # which of the two precedes the other. Interval-graph perfection makes this
    # equivalent to a simultaneous-occupancy cap of C.
    for (left, right, root, seat), order_column in order_col.items():
        left_seat = seat_col[(left, root, seat)]
        right_seat = seat_col[(right, root, seat)]
        add(
            {
                end_col[left]: 1.0,
                start_col[right]: -1.0,
                order_column: big_m,
                left_seat: big_m,
                right_seat: big_m,
            },
            -np.inf,
            3.0 * big_m,
        )
        add(
            {
                end_col[right]: 1.0,
                start_col[left]: -1.0,
                order_column: -big_m,
                left_seat: big_m,
                right_seat: big_m,
            },
            -np.inf,
            2.0 * big_m,
        )

    # Selected connectivity edges require positive overlap with margin epsilon.
    # Directed flow on these edges connects every selected member to the root.
    for (left, right, root), edge_column in edge_col.items():
        add(
            {edge_column: 1.0, x_col[(left, root)]: -1.0},
            -np.inf,
            0.0,
        )
        add(
            {edge_column: 1.0, x_col[(right, root)]: -1.0},
            -np.inf,
            0.0,
        )
        add(
            {
                start_col[left]: 1.0,
                end_col[right]: -1.0,
                edge_column: big_m,
            },
            -np.inf,
            big_m - epsilon,
        )
        add(
            {
                start_col[right]: 1.0,
                end_col[left]: -1.0,
                edge_column: big_m,
            },
            -np.inf,
            big_m - epsilon,
        )
        add(
            {
                flow_col[(left, right, root)]: 1.0,
                edge_column: -float(max_flow),
            },
            -np.inf,
            0.0,
        )
        add(
            {
                flow_col[(right, left, root)]: 1.0,
                edge_column: -float(max_flow),
            },
            -np.inf,
            0.0,
        )

    for root in roots:
        members = [member for member in by_index if (member, root) in x_col]
        for member in members:
            coefficients: dict[int, float] = {}
            for neighbor in members:
                if neighbor == member:
                    continue
                left, right = sorted((member, neighbor))
                if (left, right, root) not in edge_col:
                    continue
                incoming = flow_col[(neighbor, member, root)]
                outgoing = flow_col[(member, neighbor, root)]
                if member == root:
                    coefficients[outgoing] = coefficients.get(outgoing, 0.0) + 1.0
                    coefficients[incoming] = coefficients.get(incoming, 0.0) - 1.0
                else:
                    coefficients[incoming] = coefficients.get(incoming, 0.0) + 1.0
                    coefficients[outgoing] = coefficients.get(outgoing, 0.0) - 1.0
            if member == root:
                for selected_member in members:
                    column = x_col[(selected_member, root)]
                    coefficients[column] = coefficients.get(column, 0.0) - 1.0
                coefficients[y_col[root]] = coefficients.get(y_col[root], 0.0) + 1.0
            else:
                coefficients[x_col[(member, root)]] = (
                    coefficients.get(x_col[(member, root)], 0.0) - 1.0
                )
            add(coefficients, 0.0, 0.0)

    matrix = lil_matrix((len(constraints), variable_count), dtype=float)
    lower = np.empty(len(constraints), dtype=float)
    upper = np.empty(len(constraints), dtype=float)
    for row_index, (coefficients, row_lower, row_upper) in enumerate(constraints):
        for column, value in coefficients.items():
            matrix[row_index, column] = value
        lower[row_index] = row_lower
        upper[row_index] = row_upper

    variable_lower = np.zeros(variable_count, dtype=float)
    variable_upper = np.ones(variable_count, dtype=float)
    for member, row in by_index.items():
        variable_lower[start_col[member]] = row.start_lower
        variable_upper[start_col[member]] = row.start_upper
        variable_lower[end_col[member]] = row.end_lower
        variable_upper[end_col[member]] = row.end_upper
    for column in flow_col.values():
        variable_upper[column] = float(max_flow)

    integrality = np.zeros(variable_count, dtype=int)
    for mapping in (y_col, x_col, seat_col, edge_col, order_col):
        integrality[list(mapping.values())] = 1

    return Program(
        rows=rows,
        roots=roots,
        capacity=capacity,
        common_buffer_count=common_buffer_count,
        epsilon=epsilon,
        big_m=big_m,
        y_col=y_col,
        x_col=x_col,
        seat_col=seat_col,
        edge_col=edge_col,
        flow_col=flow_col,
        order_col=order_col,
        start_col=start_col,
        end_col=end_col,
        matrix=matrix.tocsr(),
        lower=lower,
        upper=upper,
        bounds=Bounds(variable_lower, variable_upper),
        integrality=integrality,
    )


def attribute_objective(
    program: Program,
    attribute: str,
) -> tuple[np.ndarray | None, list[int]]:
    if program.common_buffer_count <= 0:
        raise ValueError("attribute mean requires positive common buffer count")
    coefficients = np.zeros(program.matrix.shape[1], dtype=float)
    missing: list[int] = []
    by_index = {row.index: row for row in program.rows}
    for member, row in by_index.items():
        if row.role != "buffer":
            continue
        value = getattr(row, attribute)
        if value is None:
            missing.append(member)
            continue
        for root in program.roots:
            if (member, root) in program.x_col:
                coefficients[program.x_col[(member, root)]] = (
                    float(value) / program.common_buffer_count
                )
    return (None, missing) if missing else (coefficients, [])


def _max_row_violation(
    values: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> float:
    below = np.maximum(lower - values, 0.0)
    above = np.maximum(values - upper, 0.0)
    below = below[np.isfinite(below)]
    above = above[np.isfinite(above)]
    return max(
        float(np.max(below)) if below.size else 0.0,
        float(np.max(above)) if above.size else 0.0,
    )


def replay(program: Program, solution: np.ndarray) -> dict[str, Any]:
    by_index = {row.index: row for row in program.rows}
    binary_columns = np.flatnonzero(program.integrality == 1)
    rounded = solution.copy()
    rounded[binary_columns] = np.rint(rounded[binary_columns])
    linear_residual = max(
        float(np.max(np.abs(solution[binary_columns] - rounded[binary_columns])))
        if binary_columns.size
        else 0.0,
        _max_row_violation(
            np.asarray(program.matrix @ rounded).reshape(-1),
            program.lower,
            program.upper,
        ),
    )
    assignments = {
        (member, root)
        for (member, root), column in program.x_col.items()
        if rounded[column] > 0.5
    }
    times = {
        member: (
            float(rounded[program.start_col[member]]),
            float(rounded[program.end_col[member]]),
        )
        for member in by_index
    }
    problems: list[dict[str, Any]] = []
    for member, row in by_index.items():
        start, end = times[member]
        if start < row.start_lower - TOL or start > row.start_upper + TOL:
            problems.append({"reason": "start_outside_support", "member": member})
        if end < row.end_lower - TOL or end > row.end_upper + TOL:
            problems.append({"reason": "end_outside_support", "member": member})
        if end - start < program.epsilon - TOL:
            problems.append({"reason": "nonpositive_duration", "member": member})
        assignment_count = sum((member, root) in assignments for root in program.roots)
        if row.role == "core" and assignment_count != 1:
            problems.append({"reason": "core_assignment_count", "member": member})
        if row.role == "buffer" and assignment_count > 1:
            problems.append({"reason": "buffer_reused", "member": member})
    selected_buffers = sum(
        row.role == "buffer"
        and any((row.index, root) in assignments for root in program.roots)
        for row in program.rows
    )
    if selected_buffers != program.common_buffer_count:
        problems.append(
            {
                "reason": "common_buffer_count",
                "expected": program.common_buffer_count,
                "observed": selected_buffers,
            }
        )

    run_count = 0
    max_depth = 0
    for root in program.roots:
        selected = sorted(member for member in by_index if (member, root) in assignments)
        if not selected:
            continue
        run_count += 1
        if root not in selected or len(selected) < 2:
            problems.append({"reason": "bad_open_run", "root": root})
            continue
        adjacency = {member: set() for member in selected}
        for left_pos, left in enumerate(selected):
            for right in selected[left_pos + 1 :]:
                left_start, left_end = times[left]
                right_start, right_end = times[right]
                if (
                    left_start + program.epsilon <= right_end + TOL
                    and right_start + program.epsilon <= left_end + TOL
                ):
                    adjacency[left].add(right)
                    adjacency[right].add(left)
        seen = {root}
        frontier = [root]
        while frontier:
            current = frontier.pop()
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    frontier.append(neighbor)
        if seen != set(selected):
            problems.append({"reason": "run_not_connected", "root": root})
        endpoints = sorted({value for member in selected for value in times[member]})
        run_depth = 0
        for left, right in zip(endpoints, endpoints[1:]):
            if left >= right:
                continue
            midpoint = (left + right) / 2.0
            run_depth = max(
                run_depth,
                sum(
                    times[member][0] <= midpoint < times[member][1]
                    for member in selected
                ),
            )
        max_depth = max(max_depth, run_depth)
        if run_depth > program.capacity:
            problems.append(
                {
                    "reason": "capacity_violation",
                    "root": root,
                    "depth": run_depth,
                }
            )
    return {
        "status": "PASS" if linear_residual <= TOL and not problems else "FAIL",
        "linear_residual": linear_residual,
        "problem_count": len(problems),
        "problems": problems,
        "run_count": run_count,
        "selected_buffer_count": selected_buffers,
        "max_simultaneous_occupancy": max_depth,
        "times": times,
    }


def solve(
    program: Program,
    coefficients: np.ndarray,
    *,
    maximize: bool,
    time_limit: float,
) -> dict[str, Any]:
    result = milp(
        c=-coefficients if maximize else coefficients,
        integrality=program.integrality,
        bounds=program.bounds,
        constraints=LinearConstraint(program.matrix, program.lower, program.upper),
        options={"time_limit": time_limit, "presolve": True},
    )
    mip_gap = (
        float(result.mip_gap)
        if getattr(result, "mip_gap", None) is not None
        else None
    )
    if result.status == 2:
        return {
            "status": "PROVEN_INFEASIBLE_BY_HIGHS",
            "value": None,
            "mip_gap": mip_gap,
            "replay": None,
        }
    if result.x is None:
        return {
            "status": "UNRESOLVED_NO_INCUMBENT",
            "value": None,
            "mip_gap": mip_gap,
            "replay": None,
        }
    replay_audit = replay(program, np.asarray(result.x, dtype=float))
    if replay_audit["status"] != "PASS":
        return {
            "status": "UNRESOLVED_INVALID_INCUMBENT",
            "value": None,
            "mip_gap": mip_gap,
            "replay": replay_audit,
        }
    binary_columns = np.flatnonzero(program.integrality == 1)
    rounded = np.asarray(result.x, dtype=float).copy()
    rounded[binary_columns] = np.rint(rounded[binary_columns])
    return {
        "status": CERTIFIED if result.status == 0 else "INCUMBENT_ONLY_UNRESOLVED_LIMIT",
        "value": float(coefficients @ rounded),
        "mip_gap": mip_gap,
        "replay": {
            key: value
            for key, value in replay_audit.items()
            if key != "times"
        },
    }


def bound_attribute(
    rows: Sequence[TimeSupportRow],
    capacity: int,
    common_buffer_count: int,
    attribute: str,
    *,
    epsilon: float = 1.0,
    time_limit: float = 30.0,
) -> dict[str, Any]:
    program = build_program(
        rows,
        capacity,
        common_buffer_count,
        epsilon=epsilon,
    )
    objective, missing = attribute_objective(program, attribute)
    if objective is None:
        return {
            "status": "UNRESOLVED_MISSING_PUBLIC_VALUES",
            "lower": None,
            "upper": None,
            "width": None,
            "missing_rows": missing,
        }
    lower = solve(program, objective, maximize=False, time_limit=time_limit)
    upper = solve(program, objective, maximize=True, time_limit=time_limit)
    certified = (
        lower["status"] == upper["status"] == CERTIFIED
        and lower["value"] is not None
        and upper["value"] is not None
        and lower["value"] <= upper["value"] + TOL
    )
    return {
        "status": "CERTIFIED_OPTIMAL_PAIR" if certified else "UNRESOLVED_ENDPOINT_PAIR",
        "lower": lower["value"] if certified else None,
        "upper": upper["value"] if certified else None,
        "width": (
            upper["value"] - lower["value"]
            if certified
            and lower["value"] is not None
            and upper["value"] is not None
            else None
        ),
        "lower_status": lower["status"],
        "upper_status": upper["status"],
        "lower_mip_gap": lower["mip_gap"],
        "upper_mip_gap": upper["mip_gap"],
        "lower_replay": lower["replay"],
        "upper_replay": upper["replay"],
        "variable_count": program.matrix.shape[1],
        "constraint_count": program.matrix.shape[0],
    }


def self_test() -> None:
    # A-B-C is a connected C=2 ordered run although A and C do not overlap.
    chain = [
        TimeSupportRow(0, "core", 0, 0, 2, 2, miles=1.0),
        TimeSupportRow(1, "core", 1, 1, 3, 3, miles=2.0),
        TimeSupportRow(2, "core", 2, 2, 4, 4, miles=3.0),
    ]
    program = build_program(chain, 2, 0, epsilon=0.1)
    feasible = solve(
        program,
        np.zeros(program.matrix.shape[1]),
        maximize=False,
        time_limit=10,
    )
    assert feasible["status"] == CERTIFIED, feasible
    assert feasible["replay"]["max_simultaneous_occupancy"] == 2

    # Outer envelopes themselves violate C=2, but an existential support model
    # remains feasible because the exact chain is contained in every support.
    expanded = [
        TimeSupportRow(0, "core", -1, 1, 1, 3, miles=1.0),
        TimeSupportRow(1, "core", 0, 2, 2, 4, miles=2.0),
        TimeSupportRow(2, "core", 1, 3, 3, 5, miles=3.0),
    ]
    program = build_program(expanded, 2, 0, epsilon=0.1)
    feasible = solve(
        program,
        np.zeros(program.matrix.shape[1]),
        maximize=False,
        time_limit=10,
    )
    assert feasible["status"] == CERTIFIED, feasible

    # A coarse support can strictly enlarge a root-invariant outcome range while
    # preserving the exact singleton world as a subset.
    exact = [
        TimeSupportRow(0, "core", 0, 0, 4, 4, miles=0.0),
        TimeSupportRow(1, "core", 3, 3, 6, 6, miles=0.0),
        TimeSupportRow(2, "buffer", 0, 0, 2, 2, miles=1.0),
        TimeSupportRow(3, "buffer", 7, 7, 8, 8, miles=10.0),
    ]
    coarse = [
        TimeSupportRow(0, "core", 0, 0, 4, 4, miles=0.0),
        TimeSupportRow(1, "core", 3, 3, 6, 6, miles=0.0),
        TimeSupportRow(2, "buffer", 0, 0, 2, 2, miles=1.0),
        TimeSupportRow(3, "buffer", 5, 7, 6, 8, miles=10.0),
    ]
    exact_bound = bound_attribute(
        exact,
        2,
        1,
        "miles",
        epsilon=0.1,
        time_limit=10,
    )
    coarse_bound = bound_attribute(
        coarse,
        2,
        1,
        "miles",
        epsilon=0.1,
        time_limit=10,
    )
    assert exact_bound["status"] == coarse_bound["status"] == "CERTIFIED_OPTIMAL_PAIR"
    assert exact_bound["lower"] == exact_bound["upper"] == 1.0
    assert coarse_bound["lower"] <= exact_bound["lower"] + TOL
    assert coarse_bound["upper"] >= exact_bound["upper"] - TOL
    assert coarse_bound["upper"] == 10.0
    print("ordered-run existential-time self-test: PASS")


if __name__ == "__main__":
    self_test()
