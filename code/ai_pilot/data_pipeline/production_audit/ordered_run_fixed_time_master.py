#!/usr/bin/env python3
"""Exact small-cohort master for fixed-time ordered latent runs.

All feasible connected, capacity-respecting interval-run columns are enumerated.
A memoized set-partitioning dynamic program then covers every core exactly once,
uses every buffer at most once, and records the reachable selected-buffer masks.
For a fixed selected-buffer cardinality, any additive buffer attribute can be
bounded exactly by scanning those reachable masks.

The algorithm is exponential in the audit-cohort size. It is a correctness and
small-instance decomposition oracle, not a production-scale claim. Unlike the
root-indexed MILP, columns represent unlabeled physical run sets and therefore
contain no root or seat-label symmetry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

TOL = 1e-9


@dataclass(frozen=True)
class FixedTimeRow:
    index: int
    role: str
    start: float
    end: float
    miles: float | None = None
    seconds: float | None = None

    def __post_init__(self) -> None:
        if self.role not in {"core", "buffer"}:
            raise ValueError("role must be core or buffer")
        if self.end <= self.start:
            raise ValueError("fixed interval must have positive duration")


@dataclass(frozen=True)
class RunColumn:
    member_mask: int
    core_mask: int
    buffer_mask: int


@dataclass
class FixedTimeMaster:
    rows: list[FixedTimeRow]
    capacity: int
    epsilon: float
    columns: list[RunColumn]
    columns_by_core_position: dict[int, list[RunColumn]]
    all_core_mask: int
    all_buffer_mask: int
    reachable_buffer_masks: set[int]
    explored_state_count: int
    max_column_size: int


def _overlap(left: FixedTimeRow, right: FixedTimeRow, epsilon: float) -> bool:
    return (
        left.start + epsilon <= right.end + TOL
        and right.start + epsilon <= left.end + TOL
    )


def _connected(mask: int, adjacency: Sequence[int]) -> bool:
    seed = mask & -mask
    reached = seed
    frontier = seed
    while frontier:
        bit = frontier & -frontier
        frontier ^= bit
        position = bit.bit_length() - 1
        new = adjacency[position] & mask & ~reached
        reached |= new
        frontier |= new
    return reached == mask


def _capacity_ok(mask: int, active_masks: Sequence[int], capacity: int) -> bool:
    return all((mask & active).bit_count() <= capacity for active in active_masks)


def build_master(
    rows: Sequence[FixedTimeRow],
    capacity: int,
    *,
    epsilon: float = 1.0,
) -> FixedTimeMaster:
    rows = sorted(list(rows), key=lambda row: row.index)
    if capacity < 2:
        raise ValueError("capacity must be at least two")
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    if len({row.index for row in rows}) != len(rows):
        raise ValueError("row indices must be unique")
    if len(rows) > 24:
        raise ValueError("exact audit enumeration is capped at 24 rows")

    all_core_mask = 0
    all_buffer_mask = 0
    for position, row in enumerate(rows):
        if row.role == "core":
            all_core_mask |= 1 << position
        else:
            all_buffer_mask |= 1 << position
    if not all_core_mask:
        raise ValueError("at least one core row is required")

    adjacency = [0 for _row in rows]
    for left_position, left in enumerate(rows):
        for right_position in range(left_position + 1, len(rows)):
            right = rows[right_position]
            if _overlap(left, right, epsilon):
                adjacency[left_position] |= 1 << right_position
                adjacency[right_position] |= 1 << left_position

    endpoints = sorted({value for row in rows for value in (row.start, row.end)})
    active_masks: list[int] = []
    for left, right in zip(endpoints, endpoints[1:]):
        if left >= right:
            continue
        midpoint = (left + right) / 2.0
        active = 0
        for position, row in enumerate(rows):
            if row.start <= midpoint < row.end:
                active |= 1 << position
        if active:
            active_masks.append(active)

    columns: list[RunColumn] = []
    columns_by_core_position: dict[int, list[RunColumn]] = {
        position: []
        for position in range(len(rows))
        if all_core_mask & (1 << position)
    }
    max_column_size = 0
    for member_mask in range(1, 1 << len(rows)):
        if member_mask.bit_count() < 2:
            continue
        core_mask = member_mask & all_core_mask
        if not core_mask:
            continue
        if not _capacity_ok(member_mask, active_masks, capacity):
            continue
        if not _connected(member_mask, adjacency):
            continue
        column = RunColumn(
            member_mask=member_mask,
            core_mask=core_mask,
            buffer_mask=member_mask & all_buffer_mask,
        )
        columns.append(column)
        max_column_size = max(max_column_size, member_mask.bit_count())
        bits = core_mask
        while bits:
            bit = bits & -bits
            bits ^= bit
            columns_by_core_position[bit.bit_length() - 1].append(column)

    terminal_buffer_masks: set[int] = set()
    seen_states: set[tuple[int, int]] = set()
    stack = [(0, 0)]
    while stack:
        covered_core, used_buffer = stack.pop()
        state = (covered_core, used_buffer)
        if state in seen_states:
            continue
        seen_states.add(state)
        if covered_core == all_core_mask:
            terminal_buffer_masks.add(used_buffer)
            continue
        uncovered = all_core_mask & ~covered_core
        pivot_bit = uncovered & -uncovered
        pivot_position = pivot_bit.bit_length() - 1
        for column in columns_by_core_position[pivot_position]:
            if column.core_mask & covered_core:
                continue
            if column.buffer_mask & used_buffer:
                continue
            stack.append(
                (
                    covered_core | column.core_mask,
                    used_buffer | column.buffer_mask,
                )
            )

    return FixedTimeMaster(
        rows=rows,
        capacity=capacity,
        epsilon=epsilon,
        columns=columns,
        columns_by_core_position=columns_by_core_position,
        all_core_mask=all_core_mask,
        all_buffer_mask=all_buffer_mask,
        reachable_buffer_masks=terminal_buffer_masks,
        explored_state_count=len(seen_states),
        max_column_size=max_column_size,
    )


def support_frontier(master: FixedTimeMaster) -> dict[str, Any]:
    counts = sorted(
        {mask.bit_count() for mask in master.reachable_buffer_masks}
    )
    return {
        "status": "EXACT_ENUMERATION_COMPLETE",
        "capacity": master.capacity,
        "row_count": len(master.rows),
        "core_count": master.all_core_mask.bit_count(),
        "buffer_count": master.all_buffer_mask.bit_count(),
        "run_column_count": len(master.columns),
        "explored_master_state_count": master.explored_state_count,
        "reachable_buffer_mask_count": len(master.reachable_buffer_masks),
        "reachable_selected_buffer_counts": counts,
        "minimum_selected_buffers": min(counts) if counts else None,
        "maximum_selected_buffers": max(counts) if counts else None,
        "max_members_in_one_feasible_run_column": master.max_column_size,
    }


def solve_attribute(
    master: FixedTimeMaster,
    selected_buffer_count: int,
    attribute: str,
    *,
    scale: float = 1.0,
) -> dict[str, Any]:
    if selected_buffer_count <= 0:
        raise ValueError("selected_buffer_count must be positive")
    if scale <= 0:
        raise ValueError("scale must be positive")
    feasible_masks = [
        mask
        for mask in master.reachable_buffer_masks
        if mask.bit_count() == selected_buffer_count
    ]
    if not feasible_masks:
        return {
            "status": "PROVEN_INFEASIBLE_EXACT_ENUMERATION",
            "lower": None,
            "upper": None,
            "width": None,
            "feasible_buffer_mask_count": 0,
        }

    values: dict[int, float] = {}
    missing_positions: list[int] = []
    for position, row in enumerate(master.rows):
        if row.role != "buffer":
            continue
        value = getattr(row, attribute)
        if value is None:
            missing_positions.append(position)
        else:
            values[position] = float(value) / scale
    if missing_positions:
        potentially_selected = [
            position
            for position in missing_positions
            if any(mask & (1 << position) for mask in feasible_masks)
        ]
        if potentially_selected:
            return {
                "status": "UNRESOLVED_MISSING_PUBLIC_VALUES",
                "lower": None,
                "upper": None,
                "width": None,
                "missing_buffer_positions": potentially_selected,
            }

    def mean(mask: int) -> float:
        total = 0.0
        bits = mask
        while bits:
            bit = bits & -bits
            bits ^= bit
            total += values[bit.bit_length() - 1]
        return total / selected_buffer_count

    scored = [(mean(mask), mask) for mask in feasible_masks]
    lower_value, lower_mask = min(scored, key=lambda item: (item[0], item[1]))
    upper_value, upper_mask = max(scored, key=lambda item: (item[0], -item[1]))
    return {
        "status": "CERTIFIED_OPTIMAL_PAIR",
        "lower": lower_value,
        "upper": upper_value,
        "width": upper_value - lower_value,
        "lower_mip_gap": 0.0,
        "upper_mip_gap": 0.0,
        "solver": "EXACT_RUN_COLUMN_ENUMERATION_AND_MASTER_DP",
        "feasible_buffer_mask_count": len(feasible_masks),
        "lower_selected_buffer_mask": lower_mask,
        "upper_selected_buffer_mask": upper_mask,
    }


def solve_cell(
    rows: Sequence[FixedTimeRow],
    capacity: int,
    selected_buffers_per_core: float,
    *,
    epsilon: float = 1.0,
) -> dict[str, Any]:
    core_count = sum(row.role == "core" for row in rows)
    raw_count = selected_buffers_per_core * core_count
    selected_buffer_count = int(round(raw_count))
    if abs(raw_count - selected_buffer_count) > TOL:
        raise ValueError("selected buffers/core times core count must be integral")
    master = build_master(rows, capacity, epsilon=epsilon)
    frontier = support_frontier(master)
    if selected_buffer_count not in frontier["reachable_selected_buffer_counts"]:
        return {
            "capacity": capacity,
            "status": "PROVEN_INFEASIBLE_EXACT_ENUMERATION",
            "common_buffer_rows_per_core": selected_buffers_per_core,
            "common_buffer_rows": selected_buffer_count,
            "feasibility_status": "PROVEN_INFEASIBLE_EXACT_ENUMERATION",
            "feasibility_mip_gap": 0.0,
            "outcomes": [],
            "support_frontier": frontier,
        }

    outcomes: list[dict[str, Any]] = []
    for query, attribute, scale, unit in (
        (
            "mean_selected_buffer_miles_at_common_support",
            "miles",
            1.0,
            "miles",
        ),
        (
            "mean_selected_buffer_trip_minutes_at_common_support",
            "seconds",
            60.0,
            "minutes",
        ),
    ):
        result = solve_attribute(
            master,
            selected_buffer_count,
            attribute,
            scale=scale,
        )
        outcomes.append(
            {
                "query": query,
                "unit": unit,
                **{
                    key: value
                    for key, value in result.items()
                    if key
                    not in {
                        "lower_selected_buffer_mask",
                        "upper_selected_buffer_mask",
                    }
                },
            }
        )
    return {
        "capacity": capacity,
        "status": "CERTIFIED_COMMON_SUPPORT_FEASIBILITY",
        "common_buffer_rows_per_core": selected_buffers_per_core,
        "common_buffer_rows": selected_buffer_count,
        "feasibility_status": "CERTIFIED_EXACT_ENUMERATION",
        "feasibility_mip_gap": 0.0,
        "outcomes": outcomes,
        "support_frontier": frontier,
    }


def self_test() -> None:
    pairable = [
        FixedTimeRow(0, "core", 0, 2, miles=0.0, seconds=120.0),
        FixedTimeRow(1, "core", 3, 5, miles=0.0, seconds=120.0),
        FixedTimeRow(2, "buffer", 0, 1.5, miles=1.0, seconds=60.0),
        FixedTimeRow(3, "buffer", 3.5, 5, miles=9.0, seconds=180.0),
    ]
    c2 = build_master(pairable, 2, epsilon=0.1)
    frontier = support_frontier(c2)
    assert frontier["status"] == "EXACT_ENUMERATION_COMPLETE"
    assert frontier["maximum_selected_buffers"] == 2
    cell = solve_cell(pairable, 2, 1.0, epsilon=0.1)
    assert cell["status"] == "CERTIFIED_COMMON_SUPPORT_FEASIBILITY"
    miles = next(row for row in cell["outcomes"] if row["unit"] == "miles")
    assert miles["lower"] == miles["upper"] == 5.0

    touch = [
        FixedTimeRow(0, "core", 0, 1, miles=0.0, seconds=60.0),
        FixedTimeRow(1, "core", 1, 2, miles=0.0, seconds=60.0),
    ]
    touch_master = build_master(touch, 2, epsilon=0.1)
    assert not touch_master.reachable_buffer_masks

    c3 = build_master(pairable, 3, epsilon=0.1)
    assert c2.reachable_buffer_masks <= c3.reachable_buffer_masks
    print("fixed-time ordered-run column master self-test: PASS")


if __name__ == "__main__":
    self_test()
