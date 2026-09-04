#!/usr/bin/env python3
"""NYC HVFHV unknown-capacity anchored-group smoke frontier.

This script extends the pairwise C=2 benchmark to an explicit family C=2,3,4.
Each latent group has one core public row as an anchor; every assigned member
must overlap the anchor under the declared public time model. Core rows are
explained exactly once, buffers at most once, and group cardinality lies in
[2,C]. This is a conditional partial-identification benchmark, not a recovered
vehicle run or an assertion about realized NYC pool size.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from nyc_hvfhv_smoke_fetch import choose_and_fetch, count, snapshot
from nyc_hvfhv_smoke_types import (
    CERTIFIED,
    DATASET_ID,
    DATASET_NAME,
    LiveDataError,
    ModelTrip,
    model_rows,
    parse_trips,
    required_dt,
    sha,
)

CAPACITIES = (2, 3, 4)
TIME_MODELS = ("exact_second", "rounded_15m_outer")


def overlaps(left: ModelTrip, right: ModelTrip) -> bool:
    if (
        left.start is None
        or left.end is None
        or right.start is None
        or right.end is None
    ):
        return True
    return left.start <= right.end and right.start <= left.end


def anchored_pairs(rows: Sequence[ModelTrip]) -> tuple[list[int], list[tuple[int, int]]]:
    anchors = [row.index for row in rows if row.role == "core"]
    by_index = {row.index: row for row in rows}
    pairs: list[tuple[int, int]] = []
    for anchor in anchors:
        for member, member_row in by_index.items():
            if member == anchor or overlaps(by_index[anchor], member_row):
                pairs.append((member, anchor))
    return anchors, pairs


def build_program(
    rows: Sequence[ModelTrip],
    capacity: int,
) -> tuple[
    list[int],
    list[tuple[int, int]],
    dict[int, int],
    dict[tuple[int, int], int],
    LinearConstraint,
    Bounds,
]:
    if capacity < 2:
        raise ValueError("capacity must be at least two")
    anchors, pairs = anchored_pairs(rows)
    by_index = {row.index: row for row in rows}
    y_col = {anchor: idx for idx, anchor in enumerate(anchors)}
    x_col = {
        pair: len(anchors) + idx
        for idx, pair in enumerate(pairs)
    }
    nvar = len(anchors) + len(pairs)
    constraints: list[tuple[dict[int, float], float, float]] = []

    # Anchor identity: x_rr = y_r.
    for anchor in anchors:
        constraints.append(
            (
                {x_col[(anchor, anchor)]: 1.0, y_col[anchor]: -1.0},
                0.0,
                0.0,
            )
        )

    # Every assignment requires an open anchor.
    for member, anchor in pairs:
        constraints.append(
            (
                {x_col[(member, anchor)]: 1.0, y_col[anchor]: -1.0},
                -np.inf,
                0.0,
            )
        )

    # Group size: 2 y_r <= sum_i x_ir <= C y_r.
    members_by_anchor: dict[int, list[int]] = defaultdict(list)
    for member, anchor in pairs:
        members_by_anchor[anchor].append(member)
    for anchor in anchors:
        lower_coeff = {x_col[(member, anchor)]: 1.0 for member in members_by_anchor[anchor]}
        lower_coeff[y_col[anchor]] = -2.0
        constraints.append((lower_coeff, 0.0, np.inf))
        upper_coeff = {x_col[(member, anchor)]: 1.0 for member in members_by_anchor[anchor]}
        upper_coeff[y_col[anchor]] = -float(capacity)
        constraints.append((upper_coeff, -np.inf, 0.0))

    # Core rows are explained exactly once; buffers are used at most once.
    assignments_by_member: dict[int, list[int]] = defaultdict(list)
    for member, anchor in pairs:
        assignments_by_member[member].append(anchor)
    for member, row in by_index.items():
        coeff = {
            x_col[(member, anchor)]: 1.0
            for anchor in assignments_by_member.get(member, [])
        }
        if row.role == "core":
            if not coeff:
                raise LiveDataError(f"core row {member} has no anchored assignment")
            constraints.append((coeff, 1.0, 1.0))
        elif coeff:
            constraints.append((coeff, 0.0, 1.0))

    matrix = lil_matrix((len(constraints), nvar), dtype=float)
    lower = np.empty(len(constraints), dtype=float)
    upper = np.empty(len(constraints), dtype=float)
    for row_idx, (coefficients, lo, hi) in enumerate(constraints):
        for col_idx, value in coefficients.items():
            matrix[row_idx, col_idx] = value
        lower[row_idx] = lo
        upper[row_idx] = hi
    return (
        anchors,
        pairs,
        y_col,
        x_col,
        LinearConstraint(matrix.tocsr(), lower, upper),
        Bounds(np.zeros(nvar), np.ones(nvar)),
    )


def solve_objective(
    rows: Sequence[ModelTrip],
    capacity: int,
    assignment_cost: Callable[[ModelTrip, ModelTrip], float | None],
    maximize: bool,
    time_limit: float,
) -> dict[str, Any]:
    anchors, pairs, _y_col, x_col, constraint, variable_bounds = build_program(
        rows,
        capacity,
    )
    by_index = {row.index: row for row in rows}
    core_count = sum(row.role == "core" for row in rows)
    objective = np.zeros(len(anchors) + len(pairs), dtype=float)
    missing = 0
    for member, anchor in pairs:
        value = assignment_cost(by_index[member], by_index[anchor])
        if value is None:
            missing += 1
            continue
        objective[x_col[(member, anchor)]] = float(value) / core_count
    if missing:
        return {
            "status": "UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES",
            "value": None,
            "mip_gap": None,
            "residual": None,
            "missing_assignment_values": missing,
            "variables": len(objective),
            "admissible_assignments": len(pairs),
        }
    result = milp(
        c=-objective if maximize else objective,
        integrality=np.ones(len(objective), dtype=int),
        bounds=variable_bounds,
        constraints=constraint,
        options={"time_limit": time_limit, "presolve": True},
    )
    gap = (
        float(result.mip_gap)
        if getattr(result, "mip_gap", None) is not None
        else None
    )
    if result.status == 2:
        return {
            "status": "PROVEN_INFEASIBLE_BY_HIGHS",
            "value": None,
            "mip_gap": gap,
            "residual": None,
            "missing_assignment_values": 0,
            "variables": len(objective),
            "admissible_assignments": len(pairs),
        }
    if result.x is None:
        return {
            "status": "UNRESOLVED_NO_INCUMBENT",
            "value": None,
            "mip_gap": gap,
            "residual": None,
            "missing_assignment_values": 0,
            "variables": len(objective),
            "admissible_assignments": len(pairs),
        }
    rounded = np.rint(np.asarray(result.x))
    residual = float(np.max(np.abs(np.asarray(result.x) - rounded)))
    status = CERTIFIED if result.status == 0 and residual <= 1e-7 else "UNRESOLVED_NUMERICAL"
    return {
        "status": status,
        "value": float(objective @ rounded) if status == CERTIFIED else None,
        "mip_gap": gap,
        "residual": residual,
        "missing_assignment_values": 0,
        "variables": len(objective),
        "admissible_assignments": len(pairs),
    }


def query_specs() -> tuple[
    tuple[str, str, Callable[[ModelTrip, ModelTrip], float | None]],
    ...,
]:
    def gap(attribute: str, scale: float = 1.0):
        def coefficient(member: ModelTrip, anchor: ModelTrip) -> float | None:
            left = getattr(member, attribute)
            right = getattr(anchor, attribute)
            if left is None or right is None:
                return None
            return abs(float(left) - float(right)) / scale

        return coefficient

    def same_dropoff(member: ModelTrip, anchor: ModelTrip) -> float | None:
        if member.dropoff_zone is None or anchor.dropoff_zone is None:
            return None
        return float(member.dropoff_zone == anchor.dropoff_zone)

    return (
        ("mean_anchor_relative_miles_gap", "miles", gap("miles")),
        ("mean_anchor_relative_trip_time_gap", "minutes", gap("seconds", 60.0)),
        ("same_dropoff_zone_share", "fraction", same_dropoff),
    )


def solve_cell(
    rows: Sequence[ModelTrip],
    time_model: str,
    capacity: int,
    time_limit: float,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for query, unit, coefficient in query_specs():
        lower = solve_objective(rows, capacity, coefficient, False, time_limit)
        upper = solve_objective(rows, capacity, coefficient, True, time_limit)
        certified = (
            lower["status"] == upper["status"] == CERTIFIED
            and lower["value"] is not None
            and upper["value"] is not None
            and lower["value"] <= upper["value"] + 1e-7
        )
        output.append(
            {
                "time_model": time_model,
                "capacity": capacity,
                "query": query,
                "unit": unit,
                "lower": lower["value"] if certified else None,
                "upper": upper["value"] if certified else None,
                "width": (
                    upper["value"] - lower["value"]
                    if certified
                    else None
                ),
                "endpoint_pair_certification": (
                    "CERTIFIED_OPTIMAL_PAIR" if certified else "UNCERTIFIED"
                ),
                "lower_status": lower["status"],
                "upper_status": upper["status"],
                "lower_mip_gap": lower["mip_gap"],
                "upper_mip_gap": upper["mip_gap"],
                "max_replay_residual": max(
                    value
                    for value in (lower["residual"], upper["residual"])
                    if value is not None
                )
                if any(
                    value is not None
                    for value in (lower["residual"], upper["residual"])
                )
                else None,
                "admissible_assignments": lower["admissible_assignments"],
                "variables": lower["variables"],
            }
        )
    return output


def audit(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    index = {
        (row["time_model"], int(row["capacity"]), row["query"]): row
        for row in rows
    }
    comparisons = 0
    for time_model in TIME_MODELS:
        for query, _unit, _coefficient in query_specs():
            previous = None
            for capacity in CAPACITIES:
                row = index[(time_model, capacity, query)]
                if row["endpoint_pair_certification"] != "CERTIFIED_OPTIMAL_PAIR":
                    continue
                if previous is not None:
                    comparisons += 1
                    if row["lower"] > previous["lower"] + 1e-7:
                        problems.append(
                            {
                                "reason": "lower_increased_with_capacity",
                                "time_model": time_model,
                                "query": query,
                                "capacity": capacity,
                            }
                        )
                    if row["upper"] < previous["upper"] - 1e-7:
                        problems.append(
                            {
                                "reason": "upper_decreased_with_capacity",
                                "time_model": time_model,
                                "query": query,
                                "capacity": capacity,
                            }
                        )
                previous = row
    return {
        "status": "PASS" if not problems and comparisons else "FAIL",
        "capacity_monotonicity_comparisons": comparisons,
        "problems": problems,
    }


def render(report: Mapping[str, Any]) -> str:
    cohort = report["cohort"]
    lines = [
        "# NYC HVFHV unknown-capacity anchored-group frontier",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Dataset: `{DATASET_ID}` ({DATASET_NAME})",
        "",
        f"Fixed provider `{cohort['provider']}` core `{cohort['core_start']}`--"
        f"`{cohort['core_end']}`: **{cohort['core_rows']}** core rows and "
        f"**{cohort['buffer_rows']}** buffer rows.",
        "",
        "This is an anchored latent-group benchmark. It conditions on a maximum "
        "group cardinality C and does not assert the realized NYC pool size.",
        "",
        "| Time model | C | Query | Lower | Upper | Width | Certification |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for row in report["frontier"]:
        lower = "—" if row["lower"] is None else f"{row['lower']:.4f}"
        upper = "—" if row["upper"] is None else f"{row['upper']:.4f}"
        width = "—" if row["width"] is None else f"{row['width']:.4f}"
        lines.append(
            f"| {row['time_model']} | {row['capacity']} | {row['query']} | "
            f"{lower} | {upper} | {width} | "
            f"`{row['endpoint_pair_certification']}` |"
        )
    lines.extend(
        [
            "",
            f"Capacity monotonicity audit: `{report['audit']['status']}` over "
            f"**{report['audit']['capacity_monotonicity_comparisons']}** certified "
            "adjacent-capacity comparisons.",
            "",
            "Claim boundary: these are conditional public-data identified sets "
            "under the anchored-group model, not recovered co-riders or vehicle runs.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    before = snapshot()
    selected = choose_and_fetch(args)
    after = snapshot()
    if before != after:
        raise LiveDataError("dataset metadata/schema changed during extraction")
    determinate_after, _, _ = count(selected["where"]["determinate"])
    indeterminate_after, _, _ = count(selected["where"]["indeterminate"])
    if (
        determinate_after != selected["determinate_count"]
        or indeterminate_after != selected["indeterminate_count"]
    ):
        raise LiveDataError("candidate server counts changed during extraction")
    trips, row_audit = parse_trips(
        selected["candidate_rows"],
        selected["provider"],
        selected["core_start"],
        selected["core_end"],
    )
    models = {name: model_rows(trips, name) for name in TIME_MODELS}
    frontier: list[dict[str, Any]] = []
    for time_model in TIME_MODELS:
        for capacity in CAPACITIES:
            frontier.extend(
                solve_cell(
                    models[time_model],
                    time_model,
                    capacity,
                    args.solver_time_limit,
                )
            )
    capacity_audit = audit(frontier)
    if capacity_audit["status"] != "PASS":
        raise LiveDataError(
            "capacity frontier audit failed: "
            + json.dumps(capacity_audit["problems"][:8])
        )
    report = {
        "report_version": "nyc-hvfhv-anchored-capacity/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "core_start": selected["core_start"].isoformat(),
            "core_end": selected["core_end"].isoformat(),
            "core_rows": row_audit["core_rows"],
            "buffer_rows": row_audit["buffer_rows"],
            "candidate_rows": row_audit["rows"],
            "row_audit": row_audit,
        },
        "capacity_values": list(CAPACITIES),
        "time_models": list(TIME_MODELS),
        "frontier": frontier,
        "audit": capacity_audit,
        "model_boundary": {
            "anchor_pool": "core public rows only",
            "member_rule": "member public interval overlaps anchor public interval",
            "group_cardinality": "2 <= size <= C",
            "core_assignment": "exactly one latent group",
            "buffer_assignment": "at most one latent group",
            "realized_pool_size_claimed": False,
            "partner_recovery_claimed": False,
            "ordered_vehicle_run_claimed": False,
        },
        "redaction": {
            "raw_rows_emitted": False,
            "row_identifiers_emitted": False,
            "assignment_witnesses_emitted": False,
            "aggregate_only": True,
        },
    }
    report["report_sha256"] = sha(report)
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


def write_outputs(report: Mapping[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_csv(report["frontier"], output / "capacity_frontier.csv")
    compact = dict(report)
    compact.pop("frontier", None)
    (output / "report.json").write_text(
        json.dumps(compact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "NYC_HVFHV_CAPACITY_REPORT.md").write_text(
        render(report),
        encoding="utf-8",
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/nyc-hvfhv-capacity"),
    )
    p.add_argument("--scan-start", default="2023-01-03T17:00:00")
    p.add_argument("--scan-end", default="2023-01-04T01:00:00")
    p.add_argument("--scan-window-hours", type=float, default=1.0)
    p.add_argument("--min-core-rows", type=int, default=6)
    p.add_argument("--max-core-rows", type=int, default=40)
    p.add_argument("--max-scan-rows", type=int, default=5000)
    p.add_argument("--max-candidate-rows", type=int, default=2500)
    p.add_argument("--max-indeterminate-rows", type=int, default=200)
    p.add_argument("--solver-time-limit", type=float, default=45.0)
    return p


def validate(args: argparse.Namespace) -> None:
    if required_dt(args.scan_start) >= required_dt(args.scan_end):
        raise SystemExit("scan start must precede scan end")
    if args.min_core_rows < 2 or args.max_core_rows < args.min_core_rows:
        raise SystemExit("invalid core caps")
    if args.max_candidate_rows < args.max_core_rows:
        raise SystemExit("candidate cap must cover the core")
    if args.solver_time_limit <= 0:
        raise SystemExit("solver time limit must be positive")


def main() -> int:
    args = parser().parse_args()
    validate(args)
    report = run(args)
    write_outputs(report, args.output_dir)
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
