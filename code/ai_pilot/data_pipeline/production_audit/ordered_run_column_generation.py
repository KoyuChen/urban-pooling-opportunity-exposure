#!/usr/bin/env python3
"""Dantzig--Wolfe column generation for fixed-time ordered latent runs.

The full decomposition master covers each core row exactly once and uses each
buffer row at most once. A column is one connected interval run whose
simultaneous occupancy is bounded by ``capacity``. The master LP is solved by
column generation; pricing is the exact rooted single-run LP oracle from
``ordered_run_interval_oracle``.

This module certifies the LP relaxation only. It also solves the generated
restricted master as a binary MILP to obtain an integer feasible lower bound.
Because the set-partitioning master is not generally integral, that lower bound
is not advertised as a globally exact integer endpoint unless it is compared
with the exhaustive small-instance master.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

import ordered_run_fixed_time_master as exhaustive
from ordered_run_interval_oracle import GridInterval, allowed_in_span, solve_fixed_span

TOL = 1e-7


@dataclass(frozen=True)
class RunColumn:
    member_mask: int
    core_mask: int
    buffer_mask: int

    @property
    def buffer_count(self) -> int:
        return self.buffer_mask.bit_count()


@dataclass(frozen=True)
class MasterLayout:
    rows: tuple[exhaustive.FixedTimeRow, ...]
    core_positions: tuple[int, ...]
    buffer_positions: tuple[int, ...]
    all_core_mask: int
    all_buffer_mask: int


def layout(rows: Sequence[exhaustive.FixedTimeRow]) -> MasterLayout:
    ordered = tuple(sorted(rows, key=lambda row: row.index))
    if len({row.index for row in ordered}) != len(ordered):
        raise ValueError("row indices must be unique")
    core_positions = tuple(
        position for position, row in enumerate(ordered) if row.role == "core"
    )
    buffer_positions = tuple(
        position for position, row in enumerate(ordered) if row.role == "buffer"
    )
    if not core_positions:
        raise ValueError("at least one core row is required")
    return MasterLayout(
        rows=ordered,
        core_positions=core_positions,
        buffer_positions=buffer_positions,
        all_core_mask=sum(1 << position for position in core_positions),
        all_buffer_mask=sum(1 << position for position in buffer_positions),
    )


def compress_endpoints(
    rows: Sequence[exhaustive.FixedTimeRow],
) -> list[GridInterval]:
    """Compress endpoints to an equivalent elementary interval grid."""

    endpoints = sorted({value for row in rows for value in (row.start, row.end)})
    rank = {value: position for position, value in enumerate(endpoints)}
    return [GridInterval(rank[row.start], rank[row.end]) for row in rows]


def _better(
    candidate: dict[str, object],
    incumbent: dict[str, object] | None,
    maximize: bool,
) -> bool:
    if incumbent is None:
        return True
    left = float(candidate["value"])
    right = float(incumbent["value"])
    if maximize and left > right + TOL:
        return True
    if not maximize and left < right - TOL:
        return True
    if abs(left - right) <= TOL:
        return tuple(candidate["x"]) < tuple(incumbent["x"])
    return False


def solve_rooted_run_fast(
    intervals: Sequence[GridInterval],
    weights: Sequence[float],
    root: int,
    capacity: int,
    *,
    maximize: bool = True,
) -> dict[str, object]:
    """Price one root using one LP per span plus one exceptional companion scan.

    A feasible run starts at an observed interval start and ends at an observed
    interval end. If its span strictly extends the root interval, segment
    coverage already forces another member. Forced-companion enumeration is
    needed only when the span equals the root interval and the unconstrained
    optimum is the singleton root.
    """

    if len(intervals) < 2:
        return {
            "status": "PROVEN_INFEASIBLE",
            "value": None,
            "x": None,
            "lp_solve_count": 0,
            "candidate_span_count": 0,
        }
    if not (0 <= root < len(intervals)):
        raise ValueError("root index out of range")
    if len(weights) != len(intervals):
        raise ValueError("weights must match intervals")
    if capacity < 1:
        raise ValueError("capacity must be positive")

    root_interval = intervals[root]
    starts = sorted(
        interval.start
        for interval in set(intervals)
        if interval.start <= root_interval.start
    )
    ends = sorted(
        interval.end
        for interval in set(intervals)
        if interval.end >= root_interval.end
    )
    best: dict[str, object] | None = None
    lp_solve_count = 0
    candidate_span_count = 0

    for start in starts:
        for end in ends:
            span = (start, end)
            if start >= end or not allowed_in_span(root_interval, span):
                continue
            candidate_span_count += 1
            cell = solve_fixed_span(
                intervals,
                weights,
                root,
                span,
                capacity,
                maximize=maximize,
            )
            lp_solve_count += 1
            if cell["status"] == "PROVEN_INFEASIBLE":
                continue
            if cell["status"] != "CERTIFIED_OPTIMAL_LP_INTEGER":
                return {
                    "status": "UNRESOLVED_PRICING",
                    "reason": "UNRESOLVED_FIXED_SPAN",
                    "span": span,
                    "fixed_span_status": cell["status"],
                    "value": None,
                    "x": None,
                    "lp_solve_count": lp_solve_count,
                    "candidate_span_count": candidate_span_count,
                }

            span_best: dict[str, object] | None = None
            if sum(int(value) for value in cell["x"]) >= 2:
                span_best = {**cell, "span": span, "forced_companion": None}
            else:
                if span != (root_interval.start, root_interval.end):
                    raise AssertionError(
                        "a singleton root cannot cover a strictly larger span"
                    )
                for companion, interval in enumerate(intervals):
                    if companion == root or not allowed_in_span(interval, span):
                        continue
                    forced = solve_fixed_span(
                        intervals,
                        weights,
                        root,
                        span,
                        capacity,
                        maximize=maximize,
                        forced_companion=companion,
                    )
                    lp_solve_count += 1
                    if forced["status"] == "PROVEN_INFEASIBLE":
                        continue
                    if forced["status"] != "CERTIFIED_OPTIMAL_LP_INTEGER":
                        return {
                            "status": "UNRESOLVED_PRICING",
                            "reason": "UNRESOLVED_FORCED_COMPANION",
                            "span": span,
                            "forced_companion": companion,
                            "fixed_span_status": forced["status"],
                            "value": None,
                            "x": None,
                            "lp_solve_count": lp_solve_count,
                            "candidate_span_count": candidate_span_count,
                        }
                    candidate = {
                        **forced,
                        "span": span,
                        "forced_companion": companion,
                    }
                    if _better(candidate, span_best, maximize):
                        span_best = candidate
            if span_best is not None and _better(span_best, best, maximize):
                best = span_best

    if best is None:
        return {
            "status": "PROVEN_INFEASIBLE",
            "value": None,
            "x": None,
            "lp_solve_count": lp_solve_count,
            "candidate_span_count": candidate_span_count,
        }
    return {
        **best,
        "lp_solve_count": lp_solve_count,
        "candidate_span_count": candidate_span_count,
    }


def _positive_overlap(left: GridInterval, right: GridInterval) -> bool:
    return max(left.start, right.start) < min(left.end, right.end)


def seed_pair_columns(
    model: MasterLayout,
    intervals: Sequence[GridInterval],
    capacity: int,
) -> list[RunColumn]:
    if capacity < 2:
        return []
    columns: list[RunColumn] = []
    for left in range(len(model.rows)):
        for right in range(left + 1, len(model.rows)):
            mask = (1 << left) | (1 << right)
            core_mask = mask & model.all_core_mask
            if core_mask and _positive_overlap(intervals[left], intervals[right]):
                columns.append(
                    RunColumn(mask, core_mask, mask & model.all_buffer_mask)
                )
    return columns


def _column_from_solution(
    solution: Sequence[int],
    model: MasterLayout,
) -> RunColumn:
    member_mask = sum(
        1 << position for position, selected in enumerate(solution) if selected
    )
    core_mask = member_mask & model.all_core_mask
    if member_mask.bit_count() < 2 or not core_mask:
        raise ValueError("priced run must contain two rows and at least one core")
    return RunColumn(member_mask, core_mask, member_mask & model.all_buffer_mask)


def _master_arrays(
    model: MasterLayout,
    columns: Sequence[RunColumn],
    *,
    include_artificials: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    column_count = len(columns)
    artificial_count = len(model.core_positions) if include_artificials else 0
    variable_count = column_count + artificial_count
    core_matrix = np.zeros((len(model.core_positions), variable_count))
    for row_number, position in enumerate(model.core_positions):
        bit = 1 << position
        for column_number, column in enumerate(columns):
            core_matrix[row_number, column_number] = float(bool(column.core_mask & bit))
        if include_artificials:
            core_matrix[row_number, column_count + row_number] = 1.0
    buffer_matrix = np.zeros((len(model.buffer_positions), variable_count))
    for row_number, position in enumerate(model.buffer_positions):
        bit = 1 << position
        for column_number, column in enumerate(columns):
            buffer_matrix[row_number, column_number] = float(
                bool(column.buffer_mask & bit)
            )
    return (
        core_matrix,
        np.ones(len(model.core_positions)),
        buffer_matrix,
        np.ones(len(model.buffer_positions)),
    )


def solve_master_lp(
    model: MasterLayout,
    columns: Sequence[RunColumn],
    phase: str,
) -> dict[str, Any]:
    if phase not in {"phase1", "max_support"}:
        raise ValueError("phase must be phase1 or max_support")
    include_artificials = phase == "phase1"
    core_matrix, core_rhs, buffer_matrix, buffer_rhs = _master_arrays(
        model, columns, include_artificials=include_artificials
    )
    objective = (
        np.concatenate(
            [np.zeros(len(columns)), np.ones(len(model.core_positions))]
        )
        if phase == "phase1"
        else np.asarray([-float(column.buffer_count) for column in columns])
    )
    result = linprog(
        objective,
        A_ub=buffer_matrix if len(model.buffer_positions) else None,
        b_ub=buffer_rhs if len(model.buffer_positions) else None,
        A_eq=core_matrix,
        b_eq=core_rhs,
        bounds=[(0.0, None)] * len(objective),
        method="highs",
    )
    if not result.success or result.x is None:
        return {
            "status": "MASTER_LP_INFEASIBLE"
            if result.status == 2
            else "MASTER_LP_UNRESOLVED",
            "solver_status": int(result.status),
            "message": result.message,
        }
    return {
        "status": "MASTER_LP_OPTIMAL",
        "objective": float(result.fun),
        "column_values": result.x[: len(columns)].tolist(),
        "artificial_values": (
            result.x[len(columns) :].tolist() if include_artificials else []
        ),
        "core_duals": np.asarray(result.eqlin.marginals).tolist(),
        "buffer_duals": (
            np.asarray(result.ineqlin.marginals).tolist()
            if len(model.buffer_positions)
            else []
        ),
        "core_residual": float(np.max(np.abs(core_matrix @ result.x - core_rhs))),
        "buffer_violation": (
            float(np.max(np.maximum(buffer_matrix @ result.x - buffer_rhs, 0.0)))
            if len(model.buffer_positions)
            else 0.0
        ),
        "solver_status": int(result.status),
    }


def price_columns(
    model: MasterLayout,
    intervals: Sequence[GridInterval],
    master: dict[str, Any],
    phase: str,
    capacity: int,
) -> dict[str, Any]:
    weights = np.zeros(len(model.rows))
    for dual, position in zip(master["core_duals"], model.core_positions):
        weights[position] = float(dual)
    for dual, position in zip(master["buffer_duals"], model.buffer_positions):
        weights[position] = float(dual) + (1.0 if phase == "max_support" else 0.0)

    candidates: dict[int, tuple[RunColumn, float]] = {}
    best_reward = -np.inf
    lp_solve_count = 0
    span_count = 0
    for root in model.core_positions:
        priced = solve_rooted_run_fast(
            intervals, weights, root, capacity, maximize=True
        )
        lp_solve_count += int(priced.get("lp_solve_count", 0))
        span_count += int(priced.get("candidate_span_count", 0))
        if priced["status"] == "PROVEN_INFEASIBLE":
            continue
        if priced["status"] != "CERTIFIED_OPTIMAL_LP_INTEGER":
            return {
                "status": "PRICING_UNRESOLVED",
                "root": root,
                "detail": priced,
                "lp_solve_count": lp_solve_count,
                "candidate_span_count": span_count,
            }
        reward = float(priced["value"])
        best_reward = max(best_reward, reward)
        column = _column_from_solution(priced["x"], model)
        column_cost = 0.0 if phase == "phase1" else -float(column.buffer_count)
        dual_sum = sum(
            float(dual)
            for dual, position in zip(master["core_duals"], model.core_positions)
            if column.core_mask & (1 << position)
        ) + sum(
            float(dual)
            for dual, position in zip(master["buffer_duals"], model.buffer_positions)
            if column.buffer_mask & (1 << position)
        )
        reduced_cost = column_cost - dual_sum
        if abs(reduced_cost + reward) > 1e-6:
            raise AssertionError("pricing reward and reduced cost disagree")
        previous = candidates.get(column.member_mask)
        if previous is None or reduced_cost < previous[1]:
            candidates[column.member_mask] = (column, reduced_cost)
    return {
        "status": "PRICING_CERTIFIED",
        "best_reward": None if best_reward == -np.inf else best_reward,
        "minimum_reduced_cost": None if best_reward == -np.inf else -best_reward,
        "improving_columns": [
            column
            for column, reduced_cost in candidates.values()
            if reduced_cost < -TOL
        ],
        "lp_solve_count": lp_solve_count,
        "candidate_span_count": span_count,
    }


def column_generation_max_support(
    rows: Sequence[exhaustive.FixedTimeRow],
    capacity: int,
    *,
    max_iterations_per_phase: int = 100,
) -> dict[str, Any]:
    if capacity < 2 or max_iterations_per_phase <= 0:
        raise ValueError("invalid capacity or iteration limit")
    model = layout(rows)
    intervals = compress_endpoints(model.rows)
    seeds = seed_pair_columns(model, intervals, capacity)
    columns_by_mask = {column.member_mask: column for column in seeds}
    history: list[dict[str, Any]] = []
    total_oracle_lp_solves = 0
    total_candidate_spans = 0
    final_master: dict[str, Any] | None = None

    for phase in ("phase1", "max_support"):
        for iteration in range(max_iterations_per_phase):
            columns = sorted(columns_by_mask.values(), key=lambda col: col.member_mask)
            master = solve_master_lp(model, columns, phase)
            if master["status"] != "MASTER_LP_OPTIMAL":
                return {"status": master["status"], "phase": phase, "master": master}
            priced = price_columns(model, intervals, master, phase, capacity)
            total_oracle_lp_solves += int(priced.get("lp_solve_count", 0))
            total_candidate_spans += int(priced.get("candidate_span_count", 0))
            if priced["status"] != "PRICING_CERTIFIED":
                return {
                    "status": "PRICING_UNRESOLVED",
                    "phase": phase,
                    "history": history,
                    "pricing": priced,
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
                    "master_objective": master["objective"],
                    "best_pricing_reward": priced["best_reward"],
                    "minimum_reduced_cost": priced["minimum_reduced_cost"],
                    "new_column_count": new_columns,
                    "column_count_before_addition": len(columns),
                    "oracle_lp_solve_count": priced["lp_solve_count"],
                    "candidate_span_count": priced["candidate_span_count"],
                }
            )
            if new_columns == 0:
                if (
                    priced["minimum_reduced_cost"] is not None
                    and float(priced["minimum_reduced_cost"]) < -10 * TOL
                ):
                    return {
                        "status": "PRICING_STALLED_ON_DUPLICATE",
                        "phase": phase,
                        "history": history,
                    }
                final_master = master
                break
        else:
            return {
                "status": "COLUMN_GENERATION_ITERATION_LIMIT",
                "phase": phase,
                "history": history,
            }
        if phase == "phase1":
            artificial_mass = sum(final_master["artificial_values"])
            if artificial_mass > TOL:
                return {
                    "status": "FULL_MASTER_LP_PROVEN_INFEASIBLE",
                    "capacity": capacity,
                    "phase_one_artificial_mass": artificial_mass,
                    "generated_column_count": len(columns_by_mask),
                    "history": history,
                    "total_oracle_lp_solve_count": total_oracle_lp_solves,
                    "total_candidate_span_count": total_candidate_spans,
                }
            final_master = None

    columns = sorted(columns_by_mask.values(), key=lambda col: col.member_mask)
    restricted_integer = solve_restricted_integer_master(model, columns)
    return {
        "status": "FULL_MASTER_LP_CERTIFIED_OPTIMAL",
        "capacity": capacity,
        "lp_maximum_selected_buffers": -float(final_master["objective"]),
        "generated_column_count": len(columns),
        "seed_pair_column_count": len(seeds),
        "phase_one_iterations": sum(row["phase"] == "phase1" for row in history),
        "phase_two_iterations": sum(
            row["phase"] == "max_support" for row in history
        ),
        "total_oracle_lp_solve_count": total_oracle_lp_solves,
        "total_candidate_span_count": total_candidate_spans,
        "terminal_minimum_reduced_cost": history[-1]["minimum_reduced_cost"],
        "master_core_residual": final_master["core_residual"],
        "master_buffer_violation": final_master["buffer_violation"],
        "restricted_integer_master": restricted_integer,
        "history": history,
        "columns": columns,
    }


def solve_restricted_integer_master(
    model: MasterLayout,
    columns: Sequence[RunColumn],
) -> dict[str, Any]:
    if not columns:
        return {"status": "RESTRICTED_INTEGER_INFEASIBLE", "value": None}
    core_matrix, core_rhs, buffer_matrix, buffer_rhs = _master_arrays(
        model, columns, include_artificials=False
    )
    matrix = np.vstack([core_matrix, buffer_matrix])
    lower = np.concatenate([core_rhs, np.zeros(len(model.buffer_positions))])
    upper = np.concatenate([core_rhs, buffer_rhs])
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
        float(np.max(np.abs(core_matrix @ rounded - core_rhs))),
        (
            float(np.max(np.maximum(buffer_matrix @ rounded - buffer_rhs, 0.0)))
            if len(model.buffer_positions)
            else 0.0
        ),
    )
    if residual > TOL:
        return {
            "status": "RESTRICTED_INTEGER_INVALID_INCUMBENT",
            "value": None,
            "residual": residual,
        }
    return {
        "status": "RESTRICTED_INTEGER_FEASIBLE",
        "value": float(-objective @ rounded),
        "residual": residual,
        "selected_column_count": int(np.sum(rounded)),
    }


def exhaustive_master_lp(master: exhaustive.FixedTimeMaster) -> dict[str, Any]:
    columns = [
        RunColumn(column.member_mask, column.core_mask, column.buffer_mask)
        for column in master.columns
    ]
    result = solve_master_lp(layout(master.rows), columns, "max_support")
    if result["status"] == "MASTER_LP_INFEASIBLE":
        return {"status": "FULL_ENUMERATED_LP_INFEASIBLE", "value": None}
    if result["status"] != "MASTER_LP_OPTIMAL":
        return {"status": "FULL_ENUMERATED_LP_UNRESOLVED", "value": None}
    return {
        "status": "FULL_ENUMERATED_LP_OPTIMAL",
        "value": -float(result["objective"]),
        "core_residual": result["core_residual"],
        "buffer_violation": result["buffer_violation"],
    }


def compare_with_exhaustive(
    rows: Sequence[exhaustive.FixedTimeRow],
    capacity: int,
    *,
    epsilon: float = 1.0,
) -> dict[str, Any]:
    master = exhaustive.build_master(rows, capacity, epsilon=epsilon)
    frontier = exhaustive.support_frontier(master)
    full_lp = exhaustive_master_lp(master)
    generated = column_generation_max_support(rows, capacity)
    exact_integer = frontier["maximum_selected_buffers"]
    if full_lp["status"] == "FULL_ENUMERATED_LP_OPTIMAL":
        if generated["status"] != "FULL_MASTER_LP_CERTIFIED_OPTIMAL":
            raise AssertionError("column generation failed on a feasible full master")
        if abs(
            float(generated["lp_maximum_selected_buffers"])
            - float(full_lp["value"])
        ) > TOL:
            raise AssertionError("column generation and full enumerated LP disagree")
    elif generated["status"] != "FULL_MASTER_LP_PROVEN_INFEASIBLE":
        raise AssertionError("column generation did not reproduce LP infeasibility")
    restricted = generated.get("restricted_integer_master", {})
    restricted_value = restricted.get("value")
    if (
        restricted_value is not None
        and exact_integer is not None
        and float(restricted_value) > float(exact_integer) + TOL
    ):
        raise AssertionError("restricted integer lower bound exceeds exact optimum")
    return {
        "capacity": capacity,
        "row_count": len(rows),
        "core_count": sum(row.role == "core" for row in rows),
        "buffer_count": sum(row.role == "buffer" for row in rows),
        "full_run_column_count": len(master.columns),
        "generated_column_count": generated.get("generated_column_count"),
        "column_fraction_generated": (
            generated.get("generated_column_count", 0) / len(master.columns)
            if master.columns
            else None
        ),
        "full_lp_status": full_lp["status"],
        "full_lp_maximum_selected_buffers": full_lp["value"],
        "column_generation_status": generated["status"],
        "column_generation_lp_maximum_selected_buffers": generated.get(
            "lp_maximum_selected_buffers"
        ),
        "exact_integer_maximum_selected_buffers": exact_integer,
        "restricted_integer_maximum_selected_buffers": restricted_value,
        "full_master_lp_integrality_gap": (
            None
            if full_lp["value"] is None or exact_integer is None
            else float(full_lp["value"]) - float(exact_integer)
        ),
        "phase_one_iterations": generated.get("phase_one_iterations"),
        "phase_two_iterations": generated.get("phase_two_iterations"),
        "total_oracle_lp_solve_count": generated.get("total_oracle_lp_solve_count"),
        "terminal_minimum_reduced_cost": generated.get(
            "terminal_minimum_reduced_cost"
        ),
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


def integrality_gap_counterexample() -> list[exhaustive.FixedTimeRow]:
    """A C=2 instance with full master LP value 4 and integer value 3."""

    return [
        exhaustive.FixedTimeRow(0, "core", 1, 2),
        exhaustive.FixedTimeRow(1, "core", 4, 7),
        exhaustive.FixedTimeRow(2, "core", 0, 2),
        exhaustive.FixedTimeRow(3, "core", 1, 2),
        exhaustive.FixedTimeRow(4, "buffer", 0, 7),
        exhaustive.FixedTimeRow(5, "buffer", 5, 6),
        exhaustive.FixedTimeRow(6, "buffer", 5, 7),
        exhaustive.FixedTimeRow(7, "buffer", 1, 2),
        exhaustive.FixedTimeRow(8, "buffer", 2, 6),
    ]


def self_test() -> None:
    pairable = [
        exhaustive.FixedTimeRow(0, "core", 0, 2),
        exhaustive.FixedTimeRow(1, "core", 3, 5),
        exhaustive.FixedTimeRow(2, "buffer", 0, 1.5),
        exhaustive.FixedTimeRow(3, "buffer", 3.5, 5),
    ]
    pair_result = compare_with_exhaustive(pairable, 2, epsilon=0.1)
    assert pair_result["full_lp_maximum_selected_buffers"] == 2.0
    assert pair_result["exact_integer_maximum_selected_buffers"] == 2
    for seed in range(40):
        rows = _random_rows(seed)
        for capacity in (2, 3):
            compare_with_exhaustive(rows, capacity, epsilon=0.1)
    gap = compare_with_exhaustive(
        integrality_gap_counterexample(), 2, epsilon=0.1
    )
    assert abs(float(gap["full_lp_maximum_selected_buffers"]) - 4.0) <= TOL
    assert gap["exact_integer_maximum_selected_buffers"] == 3
    assert abs(float(gap["full_master_lp_integrality_gap"]) - 1.0) <= TOL
    print("ordered-run column-generation self-test: PASS")


if __name__ == "__main__":
    self_test()
