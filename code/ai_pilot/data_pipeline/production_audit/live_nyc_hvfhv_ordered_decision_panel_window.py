#!/usr/bin/env python3
"""Certified outcome and point-reconstruction audit for one NYC window.

The public rows are complete but event membership is absent. For a deterministic
ordered core, this stage chooses a common selected-buffer support count using
only exact-time feasibility under C=2, then holds that count fixed while it:

* certifies mean-mile and mean-duration frontiers for C in {2,3,4};
* evaluates four deterministic point reconstructions; and
* asks whether each point decision relative to the public candidate median is
  invariant across every feasible ordered-event completion.

The report is aggregate-only. It never emits row identifiers, event assignments,
or latent partner witnesses.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.optimize import LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import csr_matrix, vstack

import live_nyc_hvfhv_ordered_run_smoke as base
import nyc_ordered_run_symmetry as symmetry

CAPACITIES = (2, 3, 4)
TIME_MODEL = "exact_second"
TOL = 1e-7
REPORT_VERSION = "nyc-hvfhv-ordered-decision-panel-window/v1"
OUTCOMES = (
    ("mean_selected_buffer_miles", "miles", 1.0, "miles"),
    ("mean_selected_buffer_trip_minutes", "seconds", 60.0, "minutes"),
)


@dataclass(frozen=True)
class PointWorld:
    name: str
    selected_buffers: tuple[int, ...]
    status: str
    solver_seconds: float | None = None
    note: str | None = None


def finite(value: Any) -> float | None:
    if value is None:
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def append_equality(
    program: base.Program, coeff: np.ndarray, target: float
) -> base.Program:
    row = csr_matrix(coeff.reshape(1, -1))
    program.matrix = vstack([program.matrix, row], format="csr")
    program.lower = np.concatenate([program.lower, np.array([target], dtype=float)])
    program.upper = np.concatenate([program.upper, np.array([target], dtype=float)])
    return program


def fixed_support_program(
    rows: Sequence[base.ModelTrip], capacity: int, selected_buffer_count: int
) -> base.Program:
    program = symmetry.canonicalize_program(base.build_program(rows, capacity))
    target = selected_buffer_count / len(program.roots)
    append_equality(
        program,
        base.objective(program, "selected_buffer_rows_per_core"),
        target,
    )
    return program


def solve_vector(
    program: base.Program,
    coeff: np.ndarray,
    maximize: bool,
    limit: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = milp(
        c=-coeff if maximize else coeff,
        integrality=program.integrality,
        bounds=program.bounds,
        constraints=LinearConstraint(program.matrix, program.lower, program.upper),
        options={"time_limit": limit, "presolve": True},
    )
    elapsed = time.perf_counter() - started
    status = int(result.status)
    if status == 2:
        return {
            "status": "PROVEN_INFEASIBLE",
            "solver_status": status,
            "solver_message": str(result.message),
            "incumbent_value": None,
            "objective_lower_bound": None,
            "objective_upper_bound": None,
            "mip_gap": finite(getattr(result, "mip_gap", None)),
            "mip_node_count": None,
            "replay_residual": None,
            "elapsed_seconds": elapsed,
            "solution": None,
        }

    incumbent = residual = None
    replay: np.ndarray | None = None
    if result.x is not None:
        raw = np.asarray(result.x, dtype=float)
        binary = np.flatnonzero(program.integrality == 1)
        replay = raw.copy()
        replay[binary] = np.rint(replay[binary])
        values = np.asarray(program.matrix @ replay).reshape(-1)
        residual = max(
            float(np.max(np.abs(raw[binary] - replay[binary])))
            if len(binary)
            else 0.0,
            float(np.max(np.maximum(program.lower - values, 0.0))),
            float(np.max(np.maximum(values - program.upper, 0.0))),
        )
        if residual <= TOL:
            incumbent = float(coeff @ replay)
        else:
            replay = None

    dual = finite(getattr(result, "mip_dual_bound", None))
    optimal = status == 0 and incumbent is not None
    if optimal:
        lower = upper = incumbent
        label = "CERTIFIED_OPTIMAL"
    elif maximize:
        lower = incumbent
        upper = None if dual is None else -dual
        label = "RIGOROUS_OPEN_ENDPOINT" if upper is not None else "UNRESOLVED"
    else:
        lower = dual
        upper = incumbent
        label = "RIGOROUS_OPEN_ENDPOINT" if lower is not None else "UNRESOLVED"

    return {
        "status": label,
        "solver_status": status,
        "solver_message": str(result.message),
        "incumbent_value": incumbent,
        "objective_lower_bound": lower,
        "objective_upper_bound": upper,
        "mip_gap": finite(getattr(result, "mip_gap", None)),
        "mip_node_count": (
            None
            if getattr(result, "mip_node_count", None) is None
            else int(result.mip_node_count)
        ),
        "replay_residual": residual,
        "elapsed_seconds": elapsed,
        "solution": replay,
    }


def public_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "solution"}


def eligible_buffer_indices(program: base.Program) -> list[int]:
    by_index = {row.index: row for row in program.rows}
    return sorted(
        {
            member
            for member, _root in program.x_col
            if by_index[member].role == "buffer"
        }
    )


def find_common_support(
    rows: Sequence[base.ModelTrip], target: int, limit: float
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for count in range(target, 0, -1):
        program = fixed_support_program(rows, 2, count)
        result = solve_vector(
            program,
            np.zeros(program.matrix.shape[1], dtype=float),
            False,
            limit,
        )
        attempts.append(
            {"selected_buffer_count": count, **public_result(result)}
        )
        if result["status"] == "CERTIFIED_OPTIMAL":
            return {
                "status": "CERTIFIED_FEASIBLE_SUPPORT",
                "target_selected_buffer_count": target,
                "selected_buffer_count": count,
                "attempts": attempts,
            }
        if result["status"] != "PROVEN_INFEASIBLE":
            return {
                "status": "UNRESOLVED_SUPPORT_SEARCH",
                "target_selected_buffer_count": target,
                "selected_buffer_count": None,
                "attempts": attempts,
            }
    return {
        "status": "PROVEN_NO_POSITIVE_COMMON_SUPPORT",
        "target_selected_buffer_count": target,
        "selected_buffer_count": None,
        "attempts": attempts,
    }


def outcome_coeff(
    program: base.Program,
    selected_buffer_count: int,
    attribute: str,
    scale: float,
) -> tuple[np.ndarray, list[int], dict[int, float]]:
    coeff = np.zeros(program.matrix.shape[1], dtype=float)
    by_index = {row.index: row for row in program.rows}
    eligible = eligible_buffer_indices(program)
    missing: list[int] = []
    values: dict[int, float] = {}
    for member in eligible:
        value = getattr(by_index[member], attribute)
        if value is None:
            missing.append(member)
        else:
            values[member] = float(value) / scale
    for (member, _root), col in program.x_col.items():
        if member in values:
            coeff[col] = values[member] / selected_buffer_count
    return coeff, missing, values


def midpoint_seconds(row: base.ModelTrip) -> float:
    assert row.start is not None and row.end is not None
    return (row.start.timestamp() + row.end.timestamp()) / 2.0


def overlap_seconds(left: base.ModelTrip, right: base.ModelTrip) -> float:
    if not base.positive_overlap(left, right):
        return 0.0
    assert left.start is not None and left.end is not None
    assert right.start is not None and right.end is not None
    return max(
        0.0,
        (min(left.end, right.end) - max(left.start, right.start)).total_seconds(),
    )


def point_score(program: base.Program, kind: str) -> np.ndarray:
    coeff = np.zeros(program.matrix.shape[1], dtype=float)
    by_index = {row.index: row for row in program.rows}
    for (member, root), col in program.x_col.items():
        if member == root:
            continue
        left, right = by_index[member], by_index[root]
        overlap = overlap_seconds(left, right)
        midpoint_gap = abs(midpoint_seconds(left) - midpoint_seconds(right))
        pickup = float(
            left.pickup_zone is not None
            and left.pickup_zone == right.pickup_zone
        )
        dropoff = float(
            left.dropoff_zone is not None
            and left.dropoff_zone == right.dropoff_zone
        )
        if kind == "ordered_temporal_score":
            coeff[col] = overlap - 0.01 * midpoint_gap
        elif kind == "ordered_zone_score":
            coeff[col] = (
                3600.0 * (pickup + dropoff)
                + overlap
                - 0.001 * midpoint_gap
            )
        else:
            raise ValueError(kind)
    return coeff


def selected_buffers(
    program: base.Program, solution: np.ndarray
) -> tuple[int, ...]:
    by_index = {row.index: row for row in program.rows}
    usage: dict[int, float] = {}
    for (member, _root), col in program.x_col.items():
        if by_index[member].role == "buffer":
            usage[member] = usage.get(member, 0.0) + float(solution[col])
    return tuple(
        sorted(member for member, value in usage.items() if value > 0.5)
    )


def solve_ordered_point(
    rows: Sequence[base.ModelTrip],
    selected_buffer_count: int,
    kind: str,
    limit: float,
) -> PointWorld:
    program = fixed_support_program(rows, 2, selected_buffer_count)
    result = solve_vector(
        program, point_score(program, kind), True, limit
    )
    if result["status"] != "CERTIFIED_OPTIMAL" or result["solution"] is None:
        return PointWorld(
            kind, (), result["status"], result["elapsed_seconds"]
        )
    chosen = selected_buffers(program, result["solution"])
    status = (
        "CERTIFIED_FEASIBLE_POINT"
        if len(chosen) == selected_buffer_count
        else "INVALID_SELECTED_COUNT"
    )
    return PointWorld(kind, chosen, status, result["elapsed_seconds"])


def pair_point(
    rows: Sequence[base.ModelTrip], kind: str, selected_buffer_count: int
) -> PointWorld:
    cores = sorted(
        (row for row in rows if row.role == "core"), key=lambda row: row.index
    )
    buffers = sorted(
        (row for row in rows if row.role == "buffer"),
        key=lambda row: row.index,
    )
    if selected_buffer_count != len(cores):
        return PointWorld(
            kind, (), "NOT_APPLICABLE_SUPPORT_BELOW_CORE_COUNT"
        )
    if len(buffers) < len(cores):
        return PointWorld(kind, (), "NO_PERFECT_CORE_BUFFER_MATCHING")

    big = 1e15
    costs = np.full((len(cores), len(buffers)), big, dtype=float)
    for i, core in enumerate(cores):
        for j, buffer in enumerate(buffers):
            if not base.positive_overlap(core, buffer):
                continue
            overlap = overlap_seconds(core, buffer)
            gap = abs(midpoint_seconds(core) - midpoint_seconds(buffer))
            pickup = float(
                core.pickup_zone is not None
                and core.pickup_zone == buffer.pickup_zone
            )
            dropoff = float(
                core.dropoff_zone is not None
                and core.dropoff_zone == buffer.dropoff_zone
            )
            tie = 1e-9 * (j + 1)
            if kind == "pair_nearest_time":
                costs[i, j] = gap + tie
            elif kind == "pair_zone_overlap":
                score = (
                    1e8 * (pickup + dropoff)
                    + overlap
                    - 0.001 * gap
                )
                costs[i, j] = -score + tie
            else:
                raise ValueError(kind)
    row_ind, col_ind = linear_sum_assignment(costs)
    if len(row_ind) != len(cores) or any(
        costs[i, j] >= big / 2 for i, j in zip(row_ind, col_ind)
    ):
        return PointWorld(kind, (), "NO_PERFECT_CORE_BUFFER_MATCHING")
    chosen = tuple(sorted(buffers[j].index for j in col_ind))
    if len(set(chosen)) != selected_buffer_count:
        return PointWorld(kind, (), "INVALID_SELECTED_COUNT")
    return PointWorld(kind, chosen, "CERTIFIED_FEASIBLE_POINT")


def threshold_decision(value: float, threshold: float) -> str:
    return "ABOVE_OR_EQUAL" if value >= threshold else "BELOW"


def frontier_decision(
    minimum: Mapping[str, Any], maximum: Mapping[str, Any], threshold: float
) -> str:
    min_lb = minimum.get("objective_lower_bound")
    max_ub = maximum.get("objective_upper_bound")
    min_witness = minimum.get("incumbent_value")
    max_witness = maximum.get("incumbent_value")
    if min_lb is not None and float(min_lb) >= threshold - TOL:
        return "CERTIFIED_ALL_ABOVE_OR_EQUAL"
    if max_ub is not None and float(max_ub) < threshold - TOL:
        return "CERTIFIED_ALL_BELOW"
    if (
        min_witness is not None
        and max_witness is not None
        and float(min_witness) < threshold - TOL
        and float(max_witness) >= threshold - TOL
    ):
        return "CERTIFIED_AMBIGUOUS"
    return "UNRESOLVED_DECISION"


def baseline_metrics(
    point: PointWorld,
    by_index: Mapping[int, base.ModelTrip],
    thresholds: Mapping[str, float],
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "name": point.name,
        "status": point.status,
        "selected_buffer_count": len(point.selected_buffers),
        "solver_seconds": point.solver_seconds,
        "note": point.note,
        "outcomes": {},
    }
    if point.status != "CERTIFIED_FEASIBLE_POINT":
        return output
    for query, attribute, scale, _unit in OUTCOMES:
        values = [
            getattr(by_index[index], attribute)
            for index in point.selected_buffers
        ]
        if any(value is None for value in values):
            output["outcomes"][query] = {
                "value": None,
                "decision": "MISSING_PUBLIC_VALUES",
            }
            continue
        mean = statistics.fmean(float(value) / scale for value in values)
        output["outcomes"][query] = {
            "value": mean,
            "threshold": thresholds[query],
            "decision": threshold_decision(mean, thresholds[query]),
        }
    return output


def solve_outcome(
    rows: Sequence[base.ModelTrip],
    capacity: int,
    selected_buffer_count: int,
    query: str,
    attribute: str,
    scale: float,
    unit: str,
    limit: float,
    baseline_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    program = fixed_support_program(rows, capacity, selected_buffer_count)
    coeff, missing, values = outcome_coeff(
        program, selected_buffer_count, attribute, scale
    )
    if missing:
        return {
            "capacity": capacity,
            "query": query,
            "unit": unit,
            "status": "UNRESOLVED_MISSING_PUBLIC_VALUES",
            "missing_eligible_buffer_rows": len(missing),
        }
    threshold = statistics.median(values.values())
    low = solve_vector(program, coeff, False, limit)
    high = solve_vector(program, coeff, True, limit)
    exact = low["status"] == high["status"] == "CERTIFIED_OPTIMAL"
    lower = low["incumbent_value"] if exact else None
    upper = high["incumbent_value"] if exact else None
    if exact and (
        lower is None or upper is None or float(lower) > float(upper) + TOL
    ):
        raise base.LiveDataError("certified outcome frontier is reversed")

    decision = frontier_decision(low, high, threshold)
    point_values = [
        row.get("outcomes", {}).get(query, {}).get("value")
        for row in baseline_rows
        if row.get("status") == "CERTIFIED_FEASIBLE_POINT"
    ]
    point_values = [
        float(value) for value in point_values if value is not None
    ]
    containment_failures: list[str] = []
    for row in baseline_rows:
        value = row.get("outcomes", {}).get(query, {}).get("value")
        if value is None:
            continue
        min_lb = low.get("objective_lower_bound")
        max_ub = high.get("objective_upper_bound")
        if min_lb is not None and float(value) < float(min_lb) - 1e-6:
            containment_failures.append(str(row["name"]))
        if max_ub is not None and float(value) > float(max_ub) + 1e-6:
            containment_failures.append(str(row["name"]))
    decisions = {
        row.get("outcomes", {}).get(query, {}).get("decision")
        for row in baseline_rows
        if row.get("outcomes", {}).get(query, {}).get("decision")
        in {"ABOVE_OR_EQUAL", "BELOW"}
    }
    candidate_values = sorted(values.values())
    q1 = float(np.quantile(candidate_values, 0.25))
    q3 = float(np.quantile(candidate_values, 0.75))
    return {
        "capacity": capacity,
        "query": query,
        "unit": unit,
        "selected_buffer_count": selected_buffer_count,
        "status": (
            "CERTIFIED_OPTIMAL_PAIR"
            if exact
            else "RIGOROUS_OPEN_ENDPOINTS"
        ),
        "lower": lower,
        "upper": upper,
        "width": (
            None if not exact else float(upper) - float(lower)
        ),
        "outer_lower": low.get("objective_lower_bound"),
        "outer_upper": high.get("objective_upper_bound"),
        "inner_lower": low.get("incumbent_value"),
        "inner_upper": high.get("incumbent_value"),
        "threshold_rule": (
            "median public attribute among eligible buffer candidates"
        ),
        "threshold": threshold,
        "candidate_q1": q1,
        "candidate_q3": q3,
        "candidate_iqr": q3 - q1,
        "frontier_decision": decision,
        "baseline_value_min": min(point_values) if point_values else None,
        "baseline_value_max": max(point_values) if point_values else None,
        "baseline_decision_disagreement": len(decisions) > 1,
        "baseline_containment_status": (
            "PASS" if not containment_failures else "FAIL"
        ),
        "baseline_containment_failures": sorted(
            set(containment_failures)
        ),
        "minimum_solve": public_result(low),
        "maximum_solve": public_result(high),
        "variables": int(program.matrix.shape[1]),
        "binary_variables": int(np.count_nonzero(program.integrality)),
        "constraints": int(program.matrix.shape[0]),
    }


def audit(
    cells: Sequence[Mapping[str, Any]],
    baselines: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    for cell in cells:
        if cell.get("baseline_containment_status") == "FAIL":
            problems.append(
                {
                    "reason": "baseline_outside_certified_outer_enclosure",
                    "capacity": cell.get("capacity"),
                    "query": cell.get("query"),
                    "baselines": cell.get("baseline_containment_failures"),
                }
            )
    for baseline in baselines:
        if (
            baseline["status"] == "CERTIFIED_FEASIBLE_POINT"
            and baseline["selected_buffer_count"] <= 0
        ):
            problems.append(
                {
                    "reason": "empty_certified_baseline",
                    "baseline": baseline["name"],
                }
            )
    for query, _attribute, _scale, _unit in OUTCOMES:
        ordered = sorted(
            (row for row in cells if row.get("query") == query),
            key=lambda row: int(row["capacity"]),
        )
        for left, right in zip(ordered, ordered[1:]):
            if (
                left.get("status")
                == right.get("status")
                == "CERTIFIED_OPTIMAL_PAIR"
                and (
                    float(right["lower"]) > float(left["lower"]) + TOL
                    or float(right["upper"])
                    < float(left["upper"]) - TOL
                )
            ):
                problems.append(
                    {
                        "reason": "capacity_nesting_violation",
                        "query": query,
                        "left_capacity": left["capacity"],
                        "right_capacity": right["capacity"],
                    }
                )
    return {
        "status": "PASS" if not problems else "FAIL",
        "problem_count": len(problems),
        "problems": problems,
    }


def redaction_contract() -> dict[str, bool]:
    return {
        "raw_rows_emitted": False,
        "row_identifiers_emitted": False,
        "run_assignments_emitted": False,
        "partner_witnesses_emitted": False,
        "aggregate_only": True,
    }


def claim_boundary() -> dict[str, str]:
    return {
        "supported": (
            "conditional outcome frontiers, deterministic point-reconstruction "
            "diagnostics, and decision invariance within the declared public "
            "candidate universe"
        ),
        "not_supported": (
            "actual co-riders or event membership, partner recall outside the "
            "declared universe, realized capacity, production logic, population "
            "prevalence, or causal effects"
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError(
            "dataset metadata/schema changed during extraction"
        )
    determinate, _, _ = base.count(selected["where"]["determinate"])
    indeterminate, _, _ = base.count(selected["where"]["indeterminate"])
    if (determinate, indeterminate) != (
        selected["determinate_count"],
        selected["indeterminate_count"],
    ):
        raise base.LiveDataError(
            "candidate server counts changed during extraction"
        )

    trips, row_audit = base.parse_trips(
        selected["candidate_rows"],
        selected["provider"],
        selected["core_start"],
        selected["core_end"],
    )
    rows = base.ordered_subcohort(
        base.model_rows(trips, TIME_MODEL), args.ordered_core
    )
    support = find_common_support(
        rows, args.ordered_core, args.support_time_limit
    )
    if support["status"] != "CERTIFIED_FEASIBLE_SUPPORT":
        return {
            "report_version": REPORT_VERSION,
            "status": support["status"],
            "generated_at_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "window_label": args.window_label,
            "scan_start": args.scan_start,
            "scan_end": args.scan_end,
            "snapshot": after,
            "cohort": {
                "provider": selected["provider"],
                "source_core_start": selected["core_start"].isoformat(),
                "source_core_end": selected["core_end"].isoformat(),
                "source_core_rows": row_audit["core_rows"],
                "source_candidate_rows": row_audit["rows"],
                "ordered_core_rows": args.ordered_core,
                "ordered_candidate_rows": len(rows),
            },
            "support_selection": support,
            "cells": [],
            "baselines": [],
            "audit": {
                "status": "HOLD",
                "problem_count": 0,
                "problems": [],
            },
            "redaction": redaction_contract(),
            "claim_boundary": claim_boundary(),
        }

    q = int(support["selected_buffer_count"])
    by_index = {row.index: row for row in rows}
    threshold_program = fixed_support_program(rows, 2, q)
    thresholds: dict[str, float] = {}
    for query, attribute, scale, _unit in OUTCOMES:
        _coeff, missing, values = outcome_coeff(
            threshold_program, q, attribute, scale
        )
        if missing:
            raise base.LiveDataError(
                f"query {query} has {len(missing)} eligible buffers with "
                "missing public values"
            )
        thresholds[query] = statistics.median(values.values())

    point_worlds = [
        pair_point(rows, "pair_nearest_time", q),
        pair_point(rows, "pair_zone_overlap", q),
        solve_ordered_point(
            rows, q, "ordered_temporal_score", args.point_time_limit
        ),
        solve_ordered_point(
            rows, q, "ordered_zone_score", args.point_time_limit
        ),
    ]
    baselines = [
        baseline_metrics(point, by_index, thresholds)
        for point in point_worlds
    ]

    cells: list[dict[str, Any]] = []
    for capacity in CAPACITIES:
        for query, attribute, scale, unit in OUTCOMES:
            cells.append(
                solve_outcome(
                    rows,
                    capacity,
                    q,
                    query,
                    attribute,
                    scale,
                    unit,
                    args.solver_time_limit,
                    baselines,
                )
            )
    checked = audit(cells, baselines)
    if checked["status"] != "PASS":
        raise base.LiveDataError(
            "decision-panel audit failed: "
            + json.dumps(checked["problems"][:8])
        )

    return {
        "report_version": REPORT_VERSION,
        "status": "ELIGIBLE_ANALYZED",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "window_label": args.window_label,
        "scan_start": args.scan_start,
        "scan_end": args.scan_end,
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "source_core_start": selected["core_start"].isoformat(),
            "source_core_end": selected["core_end"].isoformat(),
            "source_core_rows": row_audit["core_rows"],
            "source_candidate_rows": row_audit["rows"],
            "ordered_core_rows": args.ordered_core,
            "ordered_candidate_rows": len(rows),
            "selection": (
                "first qualifying provider-window under count-reconciled scan; "
                "first core rows by frozen source order; no outcome values used"
            ),
        },
        "support_selection": support,
        "thresholds": thresholds,
        "baselines": baselines,
        "cells": cells,
        "audit": checked,
        "redaction": redaction_contract(),
        "estimand": (
            "mean public outcome among a fixed number of selected buffer rows; "
            "the common support count is the largest certified feasible count "
            "not exceeding one selected buffer per ordered core under C=2"
        ),
        "claim_boundary": claim_boundary(),
    }


def ineligible_report(
    args: argparse.Namespace, reason: str
) -> dict[str, Any]:
    return {
        "report_version": REPORT_VERSION,
        "status": "INELIGIBLE_NO_QUALIFIED_CORE",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "window_label": args.window_label,
        "scan_start": args.scan_start,
        "scan_end": args.scan_end,
        "reason": reason,
        "cells": [],
        "baselines": [],
        "audit": {
            "status": "NOT_APPLICABLE",
            "problem_count": 0,
            "problems": [],
        },
        "redaction": redaction_contract(),
        "claim_boundary": claim_boundary(),
    }


def render(report: Mapping[str, Any]) -> str:
    lines = [
        f"# NYC ordered outcome-decision audit: {report['window_label']}",
        "",
        f"Status: `{report['status']}`.",
    ]
    if report["status"] != "ELIGIBLE_ANALYZED":
        if report.get("reason"):
            lines += ["", f"Reason: `{report['reason']}`.", ""]
        return "\n".join(lines)
    cohort = report["cohort"]
    q = report["support_selection"]["selected_buffer_count"]
    lines += [
        "",
        f"Provider `{cohort['provider']}`; ordered cores: "
        f"**{cohort['ordered_core_rows']}**; candidate rows: "
        f"**{cohort['ordered_candidate_rows']}**; fixed selected-buffer "
        f"support: **{q}**.",
        "",
        "| C | Outcome | Exact frontier | Outer enclosure | "
        "Candidate-median threshold | Decision | Baseline disagreement |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for cell in report["cells"]:
        exact = (
            "—"
            if cell.get("lower") is None
            else f"[{cell['lower']:.3f}, {cell['upper']:.3f}]"
        )
        outer = (
            "—"
            if cell.get("outer_lower") is None
            or cell.get("outer_upper") is None
            else f"[{cell['outer_lower']:.3f}, {cell['outer_upper']:.3f}]"
        )
        lines.append(
            f"| {cell['capacity']} | {cell['query']} | {exact} | {outer} | "
            f"{cell['threshold']:.3f} | `{cell['frontier_decision']}` | "
            f"{'yes' if cell['baseline_decision_disagreement'] else 'no'} |"
        )
    lines += ["", "## Deterministic point reconstructions", ""]
    lines += [
        "| Method | Status | Miles | Miles decision | Minutes | "
        "Minutes decision |",
        "|---|---|---:|---|---:|---|",
    ]
    for baseline in report["baselines"]:
        miles = baseline.get("outcomes", {}).get(
            "mean_selected_buffer_miles", {}
        )
        minutes = baseline.get("outcomes", {}).get(
            "mean_selected_buffer_trip_minutes", {}
        )
        miles_text = (
            "—"
            if miles.get("value") is None
            else f"{float(miles['value']):.3f}"
        )
        minutes_text = (
            "—"
            if minutes.get("value") is None
            else f"{float(minutes['value']):.3f}"
        )
        lines.append(
            f"| {baseline['name']} | `{baseline['status']}` | "
            f"{miles_text} | {miles.get('decision', '—')} | "
            f"{minutes_text} | {minutes.get('decision', '—')} |"
        )
    lines += [
        "",
        "All certified point worlds are replayed against the same ordered-event "
        "constraints. Their numerical values must lie inside every applicable "
        "certified outer frontier enclosure.",
        "",
    ]
    return "\n".join(lines)


def write_csv(
    rows: Iterable[Mapping[str, Any]], path: Path
) -> None:
    rows = list(rows)
    fields = (
        sorted({key for row in rows for key in row})
        if rows
        else ["status"]
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    rows = base.synthetic_chain()
    support = find_common_support(rows, 1, 10.0)
    assert support["status"] == "CERTIFIED_FEASIBLE_SUPPORT", support
    assert support["selected_buffer_count"] == 1
    by_index = {row.index: row for row in rows}
    threshold_program = fixed_support_program(rows, 2, 1)
    thresholds = {}
    for query, attribute, scale, _unit in OUTCOMES:
        _coeff, missing, values = outcome_coeff(
            threshold_program, 1, attribute, scale
        )
        assert not missing
        thresholds[query] = statistics.median(values.values())
    points = [
        baseline_metrics(
            solve_ordered_point(
                rows, 1, "ordered_temporal_score", 10.0
            ),
            by_index,
            thresholds,
        ),
        baseline_metrics(
            solve_ordered_point(
                rows, 1, "ordered_zone_score", 10.0
            ),
            by_index,
            thresholds,
        ),
    ]
    miles = solve_outcome(
        rows,
        2,
        1,
        "mean_selected_buffer_miles",
        "miles",
        1.0,
        "miles",
        10.0,
        points,
    )
    assert miles["status"] == "CERTIFIED_OPTIMAL_PAIR", miles
    assert abs(miles["lower"] - 3.0) <= 1e-8
    assert abs(miles["upper"] - 3.0) <= 1e-8
    assert miles["baseline_containment_status"] == "PASS"
    checked = audit([miles], points)
    assert checked["status"] == "PASS", checked
    print("NYC ordered outcome-decision panel self-test: PASS")


def parser() -> argparse.ArgumentParser:
    parser = base.parser()
    parser.add_argument("--window-label", default="manual")
    parser.add_argument("--support-time-limit", type=float, default=30.0)
    parser.add_argument("--point-time-limit", type=float, default=45.0)
    return parser


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    base.validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = run(args)
    except base.LiveDataError as exc:
        if (
            "no scan window produced an integrity- and cap-qualified core"
            not in str(exc)
        ):
            raise
        report = ineligible_report(args, str(exc))
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        render(report), encoding="utf-8"
    )
    write_csv(
        report.get("cells", []), args.output_dir / "decision_cells.csv"
    )
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
