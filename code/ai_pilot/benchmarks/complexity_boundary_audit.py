#!/usr/bin/env python3
"""Fail-closed audit of exact-time event-partition complexity boundaries.

This module does not claim a hardness result.  It proves and exhaustively
checks a tractable boundary that any future reduction must leave: when the
full exact interval family already has depth at most the event capacity,
maximum support is determined by positive-overlap components.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = (
    ROOT
    / "code"
    / "ai_pilot"
    / "benchmarks"
    / "results"
    / "complexity_boundary_20260922"
)
REPORT_VERSION = "exact-time-complexity-boundary/v1"


@dataclass(frozen=True)
class ExactRow:
    name: str
    start: int
    end: int
    role: str

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("an exact row must have positive duration")
        if self.role not in {"core", "buffer"}:
            raise ValueError("role must be core or buffer")


def positive_overlap(left: ExactRow, right: ExactRow) -> bool:
    return max(left.start, right.start) < min(left.end, right.end)


def maximum_depth(rows: Iterable[ExactRow]) -> int:
    """Maximum half-open occupancy; ends are processed before starts."""

    changes: list[tuple[int, int]] = []
    for row in rows:
        changes.append((row.start, 1))
        changes.append((row.end, -1))
    active = 0
    peak = 0
    for _, delta in sorted(changes, key=lambda item: (item[0], item[1])):
        active += delta
        peak = max(peak, active)
    return peak


def overlap_components(rows: list[ExactRow]) -> list[tuple[int, ...]]:
    remaining = set(range(len(rows)))
    components: list[tuple[int, ...]] = []
    while remaining:
        root = min(remaining)
        remaining.remove(root)
        stack = [root]
        component = {root}
        while stack:
            current = stack.pop()
            neighbors = {
                other
                for other in remaining
                if positive_overlap(rows[current], rows[other])
            }
            remaining.difference_update(neighbors)
            component.update(neighbors)
            stack.extend(neighbors)
        components.append(tuple(sorted(component)))
    return components


def is_connected(rows: list[ExactRow]) -> bool:
    return bool(rows) and len(overlap_components(rows)) == 1


def low_depth_support_certificate(
    rows: list[ExactRow], capacity: int
) -> dict[str, object]:
    """Return the component-formula certificate when full depth is small.

    Every core-containing full-overlap component is one event.  A singleton
    such component makes the model infeasible because every event needs two
    rows.  A buffer-only component can never join an event containing a core.
    """

    if capacity < 1:
        raise ValueError("capacity must be positive")
    depth = maximum_depth(rows)
    if depth > capacity:
        return {
            "status": "NOT_APPLICABLE_FULL_DEPTH_EXCEEDS_CAPACITY",
            "maximum_depth": depth,
            "capacity": capacity,
        }
    events: list[list[str]] = []
    selected_buffers: list[str] = []
    for component in overlap_components(rows):
        component_rows = [rows[index] for index in component]
        if not any(row.role == "core" for row in component_rows):
            continue
        if len(component_rows) == 1:
            return {
                "status": "INFEASIBLE_SINGLETON_CORE_COMPONENT",
                "maximum_depth": depth,
                "capacity": capacity,
                "singleton_core": component_rows[0].name,
            }
        events.append([row.name for row in component_rows])
        selected_buffers.extend(
            row.name for row in component_rows if row.role == "buffer"
        )
    if not events:
        return {
            "status": "INFEASIBLE_NO_CORE_EVENT",
            "maximum_depth": depth,
            "capacity": capacity,
        }
    return {
        "status": "MAXIMUM_SUPPORT_CERTIFIED",
        "maximum_depth": depth,
        "capacity": capacity,
        "maximum_selected_buffers": len(selected_buffers),
        "selected_buffers": sorted(selected_buffers),
        "events": events,
    }


def well_anchored_low_depth(rows: list[ExactRow], capacity: int) -> bool:
    """Sufficient condition for every q from zero through |B| to be feasible."""

    if maximum_depth(rows) > capacity:
        return False
    cores = [row for row in rows if row.role == "core"]
    buffers = [row for row in rows if row.role == "buffer"]
    if not cores:
        return False
    if any(len(component) < 2 for component in overlap_components(cores)):
        return False
    return all(any(positive_overlap(buffer, core) for core in cores) for buffer in buffers)


def feasible_event_masks(rows: list[ExactRow], capacity: int) -> list[int]:
    events: list[int] = []
    for mask in range(1, 1 << len(rows)):
        members = [rows[index] for index in range(len(rows)) if mask & (1 << index)]
        if len(members) < 2:
            continue
        if not any(row.role == "core" for row in members):
            continue
        if maximum_depth(members) > capacity:
            continue
        if not is_connected(members):
            continue
        events.append(mask)
    return events


def brute_force_q_values(rows: list[ExactRow], capacity: int) -> frozenset[int]:
    """Complete event-column enumeration for small audit instances."""

    core_mask = sum(
        1 << index for index, row in enumerate(rows) if row.role == "core"
    )
    buffer_mask = sum(
        1 << index for index, row in enumerate(rows) if row.role == "buffer"
    )
    if core_mask == 0:
        return frozenset()
    events = feasible_event_masks(rows, capacity)
    by_core = {
        index: [event for event in events if event & (1 << index)]
        for index, row in enumerate(rows)
        if row.role == "core"
    }
    memo: dict[int, frozenset[int]] = {}

    def recurse(used: int) -> frozenset[int]:
        if used in memo:
            return memo[used]
        uncovered = core_mask & ~used
        if not uncovered:
            result = frozenset({(used & buffer_mask).bit_count()})
            memo[used] = result
            return result
        first = (uncovered & -uncovered).bit_length() - 1
        values: set[int] = set()
        for event in by_core[first]:
            if event & used:
                continue
            values.update(recurse(used | event))
        result = frozenset(values)
        memo[used] = result
        return result

    return recurse(0)


def validate_star_witness() -> dict[str, object]:
    rows = [ExactRow("center", 0, 8, "core")]
    rows.extend(
        ExactRow(f"leaf_{index}", 2 * index, 2 * index + 1, "buffer")
        for index in range(4)
    )
    degrees = [
        sum(positive_overlap(row, other) for other in rows if other != row)
        for row in rows
    ]
    assert maximum_depth(rows) == 2
    assert is_connected(rows)
    assert max(degrees) == 4
    return {
        "rows": [asdict(row) for row in rows],
        "maximum_depth": 2,
        "connected": True,
        "maximum_overlap_graph_degree": 4,
        "path_claim_refuted": True,
    }


def validate_fixed_q_gap_witness() -> dict[str, object]:
    rows = [
        ExactRow("c_long", 0, 7, "core"),
        ExactRow("b_left", 2, 4, "buffer"),
        ExactRow("c_right", 3, 5, "core"),
        ExactRow("b_right", 4, 6, "buffer"),
    ]
    q_values = brute_force_q_values(rows, 2)
    assert q_values == frozenset({0, 2})
    return {
        "rows": [asdict(row) for row in rows],
        "capacity": 2,
        "feasible_q_values": sorted(q_values),
        "q_one_infeasible": True,
        "support_at_least_one_feasible": True,
    }


def run_exhaustive_audit() -> dict[str, object]:
    catalog = (
        ("long", 0, 7),
        ("left", 0, 2),
        ("left_mid", 1, 3),
        ("middle", 2, 4),
        ("right_mid", 3, 5),
        ("right", 4, 6),
        ("touch_only", 7, 8),
    )
    state_assignments = 0
    low_depth_cases = 0
    low_depth_feasible = 0
    low_depth_infeasible = 0
    well_anchored_cases = 0
    fixed_q_cells = 0
    for states in itertools.product((0, 1, 2), repeat=len(catalog)):
        # 0 absent, 1 core, 2 buffer.
        if 1 not in states:
            continue
        rows = [
            ExactRow(name, start, end, "core" if state == 1 else "buffer")
            for (name, start, end), state in zip(catalog, states)
            if state
        ]
        state_assignments += 1
        for capacity in (2, 3):
            if maximum_depth(rows) > capacity:
                continue
            low_depth_cases += 1
            q_values = brute_force_q_values(rows, capacity)
            certificate = low_depth_support_certificate(rows, capacity)
            if q_values:
                low_depth_feasible += 1
                assert certificate["status"] == "MAXIMUM_SUPPORT_CERTIFIED"
                assert certificate["maximum_selected_buffers"] == max(q_values)
            else:
                low_depth_infeasible += 1
                assert str(certificate["status"]).startswith("INFEASIBLE_")
            if well_anchored_low_depth(rows, capacity):
                well_anchored_cases += 1
                expected = frozenset(
                    range(1 + sum(row.role == "buffer" for row in rows))
                )
                assert q_values == expected
                fixed_q_cells += len(expected)
    return {
        "catalog_interval_count": len(catalog),
        "role_or_absence_assignments_with_a_core": state_assignments,
        "low_depth_capacity_cases_checked": low_depth_cases,
        "low_depth_feasible_cases": low_depth_feasible,
        "low_depth_infeasible_cases": low_depth_infeasible,
        "well_anchored_cases_checked": well_anchored_cases,
        "fixed_q_cells_checked": fixed_q_cells,
        "component_formula_mismatches": 0,
        "well_anchored_fixed_q_mismatches": 0,
    }


def build_summary() -> dict[str, object]:
    return {
        "report_version": REPORT_VERSION,
        "gate": "PASS_TRACTABLE_BOUNDARY_WITH_HARDNESS_OPEN",
        "hardness_status": "NOT_ESTABLISHED",
        "scope": "exact-time event partitions; no uncertain-time or city-scale claim",
        "proved_boundary": (
            "If full interval depth is at most C, maximum support is exactly the "
            "number of buffers in core-containing overlap components, unless a "
            "core lies in a singleton full component, in which case no world exists."
        ),
        "fixed_q_corollary": (
            "If, additionally, every core-overlap component has at least two cores "
            "and every buffer overlaps a core, every q from 0 through |B| is feasible."
        ),
        "star_witness": validate_star_witness(),
        "fixed_q_gap_witness": validate_fixed_q_gap_witness(),
        "exhaustive_validation": run_exhaustive_audit(),
        "rejected_transfers": [
            "unrelated-machine scheduling adds machine-dependent intervals or eligibility",
            "balanced connected k-partition fixes the number of parts and optimizes balance",
            "same-size star partition fixes event shape; its interval-graph case is polynomial",
            "a capacity-two event need not be a path, as the exact star witness shows",
        ],
        "claim_boundary": (
            "No complete polynomial reduction to the present core/buffer world model was "
            "verified; the manuscript must retain complexity-open wording."
        ),
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_outputs(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary()
    summary_path = output_dir / "SUMMARY.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    validation = summary["exhaustive_validation"]
    report = f"""# Exact-time complexity boundary audit

Gate: `{summary['gate']}`.

## Result

No valid NP-hardness reduction was established. The global exact-time,
multi-core classification therefore remains open in this manuscript. This is
not a literature-wide open-problem claim.

The audit instead proves a tractable boundary. If the full exact interval
family has depth at most capacity C, each full positive-overlap component that
contains a core can be used as one event. Every buffer in such a component is
selected, and no buffer in a buffer-only component can be selected. A
singleton core-containing component makes the model infeasible because events
must have at least two rows.

If the core-induced overlap components already have at least two cores and
every buffer overlaps a core, then every fixed q from 0 through |B| is
feasible. Thus connectivity alone does not yield the missing hardness result;
a valid reduction must exploit over-capacity conflicts or failure of this
anchoring condition.

Exact-q feasibility is also not interchangeable with the maximum-support
decision. The four-row capacity-two witness in `SUMMARY.json` has feasible
support set Q = {{0, 2}}: support at least one is feasible, but q=1 is not.

## Exact validation

- Role/absence assignments with at least one core: **{validation['role_or_absence_assignments_with_a_core']:,}**
- Low-depth capacity cases exhaustively compared: **{validation['low_depth_capacity_cases_checked']:,}**
- Feasible / infeasible cases: **{validation['low_depth_feasible_cases']:,} / {validation['low_depth_infeasible_cases']:,}**
- Well-anchored cases: **{validation['well_anchored_cases_checked']:,}**
- Fixed-q cells checked: **{validation['fixed_q_cells_checked']:,}**
- Mismatches: **0**

The finite audit is regression evidence for the proof, not a proof by
enumeration. It also verifies an exact capacity-two star event with overlap-
graph degree four, refuting the shortcut that every capacity-two event is a
path.

## Rejected hardness transfers

- Unrelated-machine interval scheduling supplies machine-dependent intervals
  or arbitrary eligibility that the event model does not have.
- Balanced connected k-partition fixes the number of parts and has a balance
  objective absent here.
- Same-size star partition fixes every part's shape; moreover its interval-
  graph case is polynomial.
- Induced-path/subtree variants add terminals, inducedness, or adjacency rules
  absent from freely regroupable event worlds.

## Claim boundary

`C=2 NP-hard` is **not established**. A fractional master, exponential branch
case count, and hard neighboring problems are not hardness proofs. No timeout
or numerical solver status enters this audit.
"""
    report_path = output_dir / "REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    manifest = {
        "report_version": REPORT_VERSION,
        "gate": summary["gate"],
        "files": {
            path.name: sha256(path) for path in (summary_path, report_path)
        },
    }
    (output_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = write_outputs(args.output_dir)
    validation = summary["exhaustive_validation"]
    print(
        f"{summary['gate']}: "
        f"{validation['low_depth_capacity_cases_checked']} low-depth cases and "
        f"{validation['fixed_q_cells_checked']} fixed-q cells checked"
    )


if __name__ == "__main__":
    main()
