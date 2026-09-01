#!/usr/bin/env python3
"""NYC HVFHV ordered latent-run smoke frontier.

A run is a connected component of the positive interval-overlap graph with
simultaneous occupancy bounded by C. Total run membership may exceed C. The
formulation uses root-indexed assignments plus single-commodity connectivity
flow and is polynomial in the declared candidate universe.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, lil_matrix

from nyc_hvfhv_smoke_fetch import choose_and_fetch, count, snapshot
from nyc_hvfhv_smoke_types import (
    CERTIFIED,
    DATASET_ID,
    DATASET_NAME,
    LiveDataError,
    ModelTrip,
    Trip,
    model_rows,
    parse_trips,
    required_dt,
)

CAPACITIES = (2, 3, 4)
TIME_MODELS = ("exact_second", "rounded_15m_outer")


@dataclass
class Program:
    rows: list[ModelTrip]
    roots: list[int]
    y_col: dict[int, int]
    x_col: dict[tuple[int, int], int]
    f_col: dict[tuple[int, int, int], int]
    matrix: csr_matrix
    lower: np.ndarray
    upper: np.ndarray
    bounds: Bounds
    integrality: np.ndarray


def positive_overlap(left: ModelTrip, right: ModelTrip) -> bool:
    if left.start is None or left.end is None or right.start is None or right.end is None:
        return False
    return max(left.start, right.start) < min(left.end, right.end)


def overlap_edges(rows: Sequence[ModelTrip]) -> list[tuple[int, int]]:
    edges: list[tuple[int, int]] = []
    for left_pos, left in enumerate(rows):
        for right in rows[left_pos + 1 :]:
            if positive_overlap(left, right):
                edges.append((left.index, right.index))
    return edges


def components(nodes: Sequence[int], edges: Sequence[tuple[int, int]]) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {node: set() for node in nodes}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    result: dict[int, set[int]] = {}
    seen: set[int] = set()
    for node in nodes:
        if node in seen:
            continue
        queue = deque([node])
        component: set[int] = set()
        seen.add(node)
        while queue:
            current = queue.popleft()
            component.add(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        for member in component:
            result[member] = component
    return result


def elementary_segments(rows: Sequence[ModelTrip]) -> list[tuple[datetime, datetime]]:
    endpoints = sorted(
        {
            value
            for row in rows
            for value in (row.start, row.end)
            if value is not None
        }
    )
    return [
        (left, right)
        for left, right in zip(endpoints, endpoints[1:])
        if left < right
    ]


def active_on(row: ModelTrip, segment: tuple[datetime, datetime]) -> bool:
    left, right = segment
    return row.start is not None and row.end is not None and row.start < right and row.end > left


def ordered_subcohort(rows: Sequence[ModelTrip], core_limit: int) -> list[ModelTrip]:
    original_core = sorted((row for row in rows if row.role == "core"), key=lambda row: row.index)
    if len(original_core) < core_limit:
        raise LiveDataError(f"ordered core limit {core_limit} exceeds available {len(original_core)}")
    selected = {row.index for row in original_core[:core_limit]}
    output: list[ModelTrip] = []
    for row in rows:
        if row.start is None or row.end is None:
            continue
        output.append(
            ModelTrip(
                row.index,
                row.provider,
                "core" if row.index in selected else "buffer",
                row.start,
                row.end,
                row.pickup_zone,
                row.dropoff_zone,
                row.miles,
                row.seconds,
                row.fare,
                row.driver_pay,
            )
        )
    return output


def build_program(rows: Sequence[ModelTrip], capacity: int) -> Program:
    if capacity < 2:
        raise ValueError("capacity must be >=2")
    rows = list(rows)
    by_index = {row.index: row for row in rows}
    nodes = list(by_index)
    roots = [row.index for row in rows if row.role == "core"]
    edges = overlap_edges(rows)
    component_by_node = components(nodes, edges)
    for root in roots:
        if len(component_by_node[root]) < 2:
            raise LiveDataError(f"core root {root} is isolated in positive-overlap graph")

    y_col: dict[int, int] = {}
    x_col: dict[tuple[int, int], int] = {}
    f_col: dict[tuple[int, int, int], int] = {}
    cursor = 0
    for root in roots:
        y_col[root] = cursor
        cursor += 1
    for root in roots:
        for member in sorted(component_by_node[root]):
            x_col[(member, root)] = cursor
            cursor += 1
    edge_set = {tuple(sorted(edge)) for edge in edges}
    for root in roots:
        component = component_by_node[root]
        for left, right in sorted(edge_set):
            if left in component and right in component:
                f_col[(left, right, root)] = cursor
                cursor += 1
                f_col[(right, left, root)] = cursor
                cursor += 1
    nvar = cursor
    constraints: list[tuple[dict[int, float], float, float]] = []

    # Root identity and assignment activation.
    for root in roots:
        constraints.append(({x_col[(root, root)]: 1.0, y_col[root]: -1.0}, 0.0, 0.0))
        for member in component_by_node[root]:
            constraints.append(({x_col[(member, root)]: 1.0, y_col[root]: -1.0}, -np.inf, 0.0))

    # Core exactly once, buffers at most once.
    for member, row in by_index.items():
        cols = [x_col[(member, root)] for root in roots if (member, root) in x_col]
        if row.role == "core":
            if not cols:
                raise LiveDataError(f"core row {member} has no run assignment")
            constraints.append(({col: 1.0 for col in cols}, 1.0, 1.0))
        elif cols:
            constraints.append(({col: 1.0 for col in cols}, 0.0, 1.0))

    # Every open run has at least two selected rows.
    for root in roots:
        coeff = {x_col[(member, root)]: 1.0 for member in component_by_node[root]}
        coeff[y_col[root]] = -2.0
        constraints.append((coeff, 0.0, np.inf))

    # Occupancy on every elementary time segment.
    segments = elementary_segments(rows)
    for root in roots:
        component = component_by_node[root]
        for segment in segments:
            active = [member for member in component if active_on(by_index[member], segment)]
            if not active:
                continue
            coeff = {x_col[(member, root)]: 1.0 for member in active}
            coeff[y_col[root]] = -float(capacity)
            constraints.append((coeff, -np.inf, 0.0))

    # Connectivity flow. Root supplies one unit per selected non-root member.
    outgoing: dict[tuple[int, int], list[int]] = defaultdict(list)
    incoming: dict[tuple[int, int], list[int]] = defaultdict(list)
    for (left, right, root), col in f_col.items():
        outgoing[(left, root)].append(col)
        incoming[(right, root)].append(col)
    big_m = float(max(1, len(nodes) - 1))
    for root in roots:
        component = component_by_node[root]
        root_coeff: dict[int, float] = {}
        for col in outgoing[(root, root)]:
            root_coeff[col] = root_coeff.get(col, 0.0) + 1.0
        for col in incoming[(root, root)]:
            root_coeff[col] = root_coeff.get(col, 0.0) - 1.0
        for member in component:
            if member != root:
                root_coeff[x_col[(member, root)]] = -1.0
        constraints.append((root_coeff, 0.0, 0.0))
        for member in component:
            if member == root:
                continue
            coeff: dict[int, float] = {x_col[(member, root)]: -1.0}
            for col in incoming[(member, root)]:
                coeff[col] = coeff.get(col, 0.0) + 1.0
            for col in outgoing[(member, root)]:
                coeff[col] = coeff.get(col, 0.0) - 1.0
            constraints.append((coeff, 0.0, 0.0))

    # Flow may traverse only selected endpoints in the same run.
    for (left, right, root), flow_col in f_col.items():
        constraints.append(({flow_col: 1.0, x_col[(left, root)]: -big_m}, -np.inf, 0.0))
        constraints.append(({flow_col: 1.0, x_col[(right, root)]: -big_m}, -np.inf, 0.0))

    matrix = lil_matrix((len(constraints), nvar), dtype=float)
    lower = np.empty(len(constraints), dtype=float)
    upper = np.empty(len(constraints), dtype=float)
    for row_index, (coeff, lo, hi) in enumerate(constraints):
        for col, value in coeff.items():
            matrix[row_index, col] = value
        lower[row_index] = lo
        upper[row_index] = hi
    lower_bounds = np.zeros(nvar, dtype=float)
    upper_bounds = np.full(nvar, big_m, dtype=float)
    binary_columns = [*y_col.values(), *x_col.values()]
    upper_bounds[binary_columns] = 1.0
    integrality = np.zeros(nvar, dtype=int)
    integrality[binary_columns] = 1
    return Program(
        rows,
        roots,
        y_col,
        x_col,
        f_col,
        matrix.tocsr(),
        lower,
        upper,
        Bounds(lower_bounds, upper_bounds),
        integrality,
    )


def objective(program: Program, name: str) -> np.ndarray:
    coeff = np.zeros(program.matrix.shape[1], dtype=float)
    core_count = len(program.roots)
    by_index = {row.index: row for row in program.rows}
    if name == "run_count_per_core":
        for col in program.y_col.values():
            coeff[col] = 1.0 / core_count
    elif name == "selected_buffer_rows_per_core":
        for (member, _root), col in program.x_col.items():
            if by_index[member].role == "buffer":
                coeff[col] = 1.0 / core_count
    elif name == "companion_mass_per_core":
        for col in program.x_col.values():
            coeff[col] += 1.0 / core_count
        for col in program.y_col.values():
            coeff[col] -= 1.0 / core_count
    else:
        raise ValueError(name)
    return coeff


def solve(program: Program, coeff: np.ndarray, maximize: bool, time_limit: float) -> dict[str, Any]:
    result = milp(
        c=-coeff if maximize else coeff,
        integrality=program.integrality,
        bounds=program.bounds,
        constraints=LinearConstraint(program.matrix, program.lower, program.upper),
        options={"time_limit": time_limit, "presolve": True},
    )
    gap = float(result.mip_gap) if getattr(result, "mip_gap", None) is not None else None
    if result.status == 2:
        return {"status": "PROVEN_INFEASIBLE_BY_HIGHS", "value": None, "mip_gap": gap, "residual": None}
    if result.x is None:
        return {"status": "UNRESOLVED_NO_INCUMBENT", "value": None, "mip_gap": gap, "residual": None}
    solution = np.asarray(result.x, dtype=float)
    binary_cols = np.flatnonzero(program.integrality == 1)
    replay = solution.copy()
    replay[binary_cols] = np.rint(replay[binary_cols])
    row_values = np.asarray(program.matrix @ replay).reshape(-1)
    residual = max(
        float(np.max(np.abs(solution[binary_cols] - replay[binary_cols]))) if len(binary_cols) else 0.0,
        float(np.max(np.maximum(program.lower - row_values, 0.0))),
        float(np.max(np.maximum(row_values - program.upper, 0.0))),
    )
    status = CERTIFIED if result.status == 0 and residual <= 1e-7 else "UNRESOLVED_NUMERICAL_OR_LIMIT"
    return {
        "status": status,
        "value": float(coeff @ replay) if status == CERTIFIED else None,
        "mip_gap": gap,
        "residual": residual,
    }


def solve_frontier(rows: Sequence[ModelTrip], time_model: str, time_limit: float) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for capacity in CAPACITIES:
        program = build_program(rows, capacity)
        for query in ("run_count_per_core", "selected_buffer_rows_per_core", "companion_mass_per_core"):
            coeff = objective(program, query)
            lower = solve(program, coeff, False, time_limit)
            upper = solve(program, coeff, True, time_limit)
            certified = lower["status"] == upper["status"] == CERTIFIED
            output.append(
                {
                    "time_model": time_model,
                    "capacity": capacity,
                    "query": query,
                    "lower": lower["value"] if certified else None,
                    "upper": upper["value"] if certified else None,
                    "width": upper["value"] - lower["value"] if certified else None,
                    "lower_status": lower["status"],
                    "upper_status": upper["status"],
                    "lower_mip_gap": lower["mip_gap"],
                    "upper_mip_gap": upper["mip_gap"],
                    "max_replay_residual": max(v for v in (lower["residual"], upper["residual"]) if v is not None) if any(v is not None for v in (lower["residual"], upper["residual"])) else None,
                    "variables": program.matrix.shape[1],
                    "constraints": program.matrix.shape[0],
                    "overlap_edges": len(overlap_edges(rows)),
                    "elementary_segments": len(elementary_segments(rows)),
                }
            )
    return output


def audit(frontier: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    comparisons = 0
    index = {(row["time_model"], int(row["capacity"]), row["query"]): row for row in frontier}
    for time_model in TIME_MODELS:
        for query in ("run_count_per_core", "selected_buffer_rows_per_core", "companion_mass_per_core"):
            previous = None
            for capacity in CAPACITIES:
                row = index[(time_model, capacity, query)]
                if row["lower"] is None or row["upper"] is None:
                    continue
                if previous is not None:
                    comparisons += 1
                    if row["lower"] > previous["lower"] + 1e-7:
                        problems.append({"reason": "lower_increased_with_capacity", "time_model": time_model, "query": query, "capacity": capacity})
                    if row["upper"] < previous["upper"] - 1e-7:
                        problems.append({"reason": "upper_decreased_with_capacity", "time_model": time_model, "query": query, "capacity": capacity})
                previous = row
    return {"status": "PASS" if comparisons and not problems else "FAIL", "comparisons": comparisons, "problems": problems}


def render(report: Mapping[str, Any]) -> str:
    lines = [
        "# NYC HVFHV ordered latent-run frontier",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Dataset: `{DATASET_ID}` ({DATASET_NAME})",
        "",
        f"Ordered subcore: **{report['cohort']['ordered_core_rows']}** rows from provider `{report['cohort']['provider']}`; determinate candidate universe: **{report['cohort']['ordered_candidate_rows']}** rows.",
        "",
        "Runs are connected positive-overlap interval subgraphs. Capacity C bounds simultaneous occupancy, not total run cardinality.",
        "",
        "| Time model | C | Query | Lower | Upper | Width | Variables | Constraints |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["frontier"]:
        lo = "—" if row["lower"] is None else f"{row['lower']:.4f}"
        hi = "—" if row["upper"] is None else f"{row['upper']:.4f}"
        width = "—" if row["width"] is None else f"{row['width']:.4f}"
        lines.append(f"| {row['time_model']} | {row['capacity']} | {row['query']} | {lo} | {hi} | {width} | {row['variables']} | {row['constraints']} |")
    lines.extend(["", f"Capacity nesting audit: `{report['audit']['status']}` over **{report['audit']['comparisons']}** adjacent certified comparisons.", "", "This remains a public-data identified-set benchmark, not recovered vehicle runs.", ""])
    return "\n".join(lines)


def synthetic_chain() -> list[ModelTrip]:
    base = datetime(2023, 1, 1, 12, 0)
    return [
        ModelTrip(0, "HV", "core", base, base + timedelta(minutes=10), "1", "2", 1.0, 600.0, 10.0, 8.0),
        ModelTrip(1, "HV", "core", base + timedelta(minutes=5), base + timedelta(minutes=15), "1", "3", 2.0, 600.0, 11.0, 9.0),
        ModelTrip(2, "HV", "buffer", base + timedelta(minutes=10), base + timedelta(minutes=20), "2", "4", 3.0, 600.0, 12.0, 10.0),
    ]


def self_test() -> None:
    rows = synthetic_chain()
    assert positive_overlap(rows[0], rows[1])
    assert positive_overlap(rows[1], rows[2])
    assert not positive_overlap(rows[0], rows[2])
    program = build_program(rows, 2)
    # Max buffer use must place C in one of the connected runs despite A and C not overlapping.
    result = solve(program, objective(program, "selected_buffer_rows_per_core"), True, 10.0)
    assert result["status"] == CERTIFIED
    assert abs(result["value"] - 0.5) < 1e-7
    # A three-way simultaneous overlap requires C=3.
    base = datetime(2023, 1, 1, 12, 0)
    clique = [
        ModelTrip(i, "HV", "core" if i < 2 else "buffer", base, base + timedelta(minutes=10), "1", str(i), 1.0, 600.0, 10.0, 8.0)
        for i in range(3)
    ]
    p2 = build_program(clique, 2)
    p3 = build_program(clique, 3)
    max2 = solve(p2, objective(p2, "selected_buffer_rows_per_core"), True, 10.0)
    max3 = solve(p3, objective(p3, "selected_buffer_rows_per_core"), True, 10.0)
    assert max2["status"] == max3["status"] == CERTIFIED
    assert max3["value"] >= max2["value"]
    print("NYC ordered-run self-test: PASS")


def run(args: argparse.Namespace) -> dict[str, Any]:
    before = snapshot()
    selected = choose_and_fetch(args)
    after = snapshot()
    if before != after:
        raise LiveDataError("dataset metadata/schema changed during extraction")
    determinate_after, _, _ = count(selected["where"]["determinate"])
    indeterminate_after, _, _ = count(selected["where"]["indeterminate"])
    if determinate_after != selected["determinate_count"] or indeterminate_after != selected["indeterminate_count"]:
        raise LiveDataError("candidate server counts changed during extraction")
    trips, audit_rows = parse_trips(selected["candidate_rows"], selected["provider"], selected["core_start"], selected["core_end"])
    frontier: list[dict[str, Any]] = []
    ordered_sizes: dict[str, int] = {}
    for time_model in TIME_MODELS:
        full_model = model_rows(trips, time_model)
        ordered = ordered_subcohort(full_model, args.ordered_core)
        ordered_sizes[time_model] = len(ordered)
        frontier.extend(solve_frontier(ordered, time_model, args.solver_time_limit))
    audit = audit(frontier)
    if audit["status"] != "PASS":
        raise LiveDataError("ordered-run capacity nesting audit failed: " + json.dumps(audit["problems"][:8]))
    report = {
        "report_version": "nyc-hvfhv-ordered-run/v1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "core_start": selected["core_start"].isoformat(),
            "core_end": selected["core_end"].isoformat(),
            "source_core_rows": audit_rows["core_rows"],
            "source_candidate_rows": audit_rows["rows"],
            "ordered_core_rows": args.ordered_core,
            "ordered_candidate_rows": ordered_sizes,
        },
        "frontier": frontier,
        "audit": audit,
        "claim_boundary": {
            "supported": "connected interval-run structural endpoints in a fixed public candidate universe under declared C",
            "not_supported": "actual vehicle/run recovery, true NYC capacity, partner recall, or population effects",
        },
    }
    return report


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=Path("tmp/nyc-hvfhv-ordered-run"))
    p.add_argument("--scan-start", default="2023-01-03T17:00:00")
    p.add_argument("--scan-end", default="2023-01-04T01:00:00")
    p.add_argument("--scan-window-hours", type=float, default=1.0)
    p.add_argument("--min-core-rows", type=int, default=6)
    p.add_argument("--max-core-rows", type=int, default=40)
    p.add_argument("--max-scan-rows", type=int, default=5000)
    p.add_argument("--max-candidate-rows", type=int, default=2500)
    p.add_argument("--max-indeterminate-rows", type=int, default=200)
    p.add_argument("--ordered-core", type=int, default=8)
    p.add_argument("--solver-time-limit", type=float, default=60.0)
    p.add_argument("--self-test", action="store_true")
    return p


def validate(args: argparse.Namespace) -> None:
    if required_dt(args.scan_start) >= required_dt(args.scan_end):
        raise SystemExit("scan start must precede scan end")
    if args.ordered_core < 2 or args.solver_time_limit <= 0:
        raise SystemExit("ordered core must be >=2 and solver limit positive")


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    validate(args)
    report = run(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(report["frontier"], args.output_dir / "ordered_run_frontier.csv")
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
