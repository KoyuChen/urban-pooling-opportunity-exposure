#!/usr/bin/env python3
"""Oracle-assisted truth audit for relation-incomplete ATR DIAMOR dyads.

Candidate edge scoring is label-blind.  Group annotations are nevertheless
used to construct the eligible cohort, quarantine rows outside the dyad-only
scope, disclose the true dyad count q, and audit the resulting endpoints.
Those uses are deliberately recorded rather than described as label-blind.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import platform
import sys
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


@dataclass(frozen=True)
class Observation:
    pedestrian_id: int
    time: float
    x_m: float
    y_m: float
    speed_mps: float
    motion_angle: float


@dataclass(frozen=True)
class GroupParseResult:
    membership: dict[int, frozenset[int]]
    excluded_ids: frozenset[int]
    audit: dict[str, int]


@dataclass(frozen=True)
class EndpointResult:
    status: str
    value: float | None
    incumbent_value: float | None
    selected: tuple[int, ...]
    solver_status: int | None
    solver_message: str
    mip_gap: float | None
    mip_dual_bound: float | None
    mip_node_count: int | None
    replay_pass: bool
    replay_max_degree: int | None
    replay_cardinality_residual: int | None
    replay_objective_residual: float | None
    solver_objective_residual: float | None
    solver_dual_residual: float | None
    raw_integrality_residual: float | None
    raw_cardinality_residual: float | None
    raw_max_degree_excess: float | None
    witness_sha256: str | None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_groups(path: Path) -> GroupParseResult:
    """Parse positive groups and conservatively quarantine uncertain members.

    ATR documents unknown/non-person negative IDs and a special multiple-ID
    record grammar.  This dyad benchmark does not attempt to infer a unique
    person relation from those records: every recoverable positive group ID is
    quarantined so it cannot silently enter the candidate graph as a singleton.
    """

    groups: dict[frozenset[int], set[int]] = {}
    excluded: set[int] = set()
    audit = {
        "total_rows": 0,
        "standard_positive_rows": 0,
        "malformed_rows": 0,
        "partial_or_nonpositive_group_rows": 0,
        "multiple_id_rows": 0,
        "nonperson_mobility_aid_rows": 0,
        "conflicting_membership_ids": 0,
        "conflicting_group_member_ids": 0,
        "larger_group_member_ids": 0,
        "quarantined_uncertain_ids": 0,
    }
    with path.open(encoding="utf-8") as handle:
        for raw in handle:
            audit["total_rows"] += 1
            fields = raw.split()
            if len(fields) < 2:
                audit["malformed_rows"] += 1
                continue
            try:
                subject_id, second = int(fields[0]), int(fields[1])
            except ValueError:
                audit["malformed_rows"] += 1
                continue

            subject_ids = [subject_id]
            cursor = 1
            if subject_id < 0 and second in {-2, -3}:
                audit["nonperson_mobility_aid_rows"] += 1
                cursor = 2
                if len(fields) <= cursor:
                    audit["malformed_rows"] += 1
                    continue
                try:
                    group_size = int(fields[cursor])
                except ValueError:
                    audit["malformed_rows"] += 1
                    continue
            elif second == 0 and subject_id > 0:
                audit["multiple_id_rows"] += 1
                if len(fields) < 4:
                    audit["malformed_rows"] += 1
                    excluded.add(subject_id)
                    continue
                try:
                    identity_count = int(fields[2])
                    if identity_count < 1 or len(fields) < 3 + identity_count:
                        raise ValueError
                    subject_ids.extend(int(value) for value in fields[3 : 2 + identity_count])
                    cursor = 2 + identity_count
                    group_size = int(fields[cursor])
                except ValueError:
                    audit["malformed_rows"] += 1
                    excluded.update(value for value in subject_ids if value > 0)
                    for value in fields[3:]:
                        try:
                            recovered = int(value)
                        except ValueError:
                            continue
                        if recovered > 0:
                            excluded.add(recovered)
                    continue
            else:
                group_size = second

            if group_size <= 0 or len(fields) < cursor + group_size:
                audit["malformed_rows"] += 1
                excluded.update(value for value in subject_ids if value > 0)
                for value in fields[cursor + 1 : min(len(fields), cursor + max(group_size, 1))]:
                    try:
                        recovered = int(value)
                    except ValueError:
                        continue
                    if recovered > 0:
                        excluded.add(recovered)
                continue
            try:
                partners = [int(value) for value in fields[cursor + 1 : cursor + group_size]]
            except ValueError:
                audit["malformed_rows"] += 1
                excluded.update(value for value in subject_ids if value > 0)
                continue

            known_positive_ids = {value for value in subject_ids + partners if value > 0}
            standard = (
                len(subject_ids) == 1
                and subject_id > 0
                and all(value > 0 for value in partners)
                and len(known_positive_ids) == group_size
            )
            if not standard:
                audit["partial_or_nonpositive_group_rows"] += 1
                excluded.update(known_positive_ids)
                continue

            audit["standard_positive_rows"] += 1
            canonical = frozenset(known_positive_ids)
            groups.setdefault(canonical, set()).add(subject_id)

    membership: dict[int, frozenset[int]] = {}
    reciprocal_groups: list[frozenset[int]] = []
    for group, declarers in groups.items():
        # Standard ATR rows are reciprocal.  A partial declaration is not used
        # as dyad truth because it cannot distinguish source corruption from a
        # genuinely incomplete group record.
        if declarers != set(group):
            excluded.update(group)
            continue
        reciprocal_groups.append(group)
        if len(group) > 2:
            excluded.update(group)

    groups_by_id: dict[int, list[frozenset[int]]] = {}
    for group in reciprocal_groups:
        for pedestrian_id in group:
            groups_by_id.setdefault(pedestrian_id, []).append(group)
    conflicts = {
        pedestrian_id for pedestrian_id, memberships in groups_by_id.items()
        if len(memberships) > 1
    }
    conflict_group_members = {
        member
        for pedestrian_id in conflicts
        for group in groups_by_id[pedestrian_id]
        for member in group
    }
    audit["conflicting_membership_ids"] = len(conflicts)
    audit["conflicting_group_member_ids"] = len(conflict_group_members)
    excluded.update(conflict_group_members)

    for group in reciprocal_groups:
        if len(group) != 2 or group & excluded:
            continue
        for pedestrian_id in group:
            membership[pedestrian_id] = group
    for pedestrian_id in excluded:
        membership.pop(pedestrian_id, None)
    audit["larger_group_member_ids"] = len(
        {pedestrian_id for group in groups if len(group) > 2 for pedestrian_id in group}
    )
    audit["quarantined_uncertain_ids"] = len(excluded)
    return GroupParseResult(membership, frozenset(excluded), audit)


def load_snapshots(
    path: Path, offsets: Sequence[float], half_width: float
) -> tuple[float, list[dict[int, Observation]]]:
    """Stream once and retain the nearest observation per ID around each target."""

    snapshots: list[dict[int, Observation]] = [dict() for _ in offsets]
    distances: list[dict[int, float]] = [dict() for _ in offsets]
    first_time: float | None = None
    with path.open(newline="", encoding="utf-8") as handle:
        for fields in csv.reader(handle):
            if len(fields) != 8:
                continue
            time = float(fields[0])
            if first_time is None:
                first_time = time
            relative = time - first_time
            insertion = bisect.bisect_left(offsets, relative)
            nearby = range(max(0, insertion - 1), min(len(offsets), insertion + 1))
            for index in nearby:
                offset = offsets[index]
                delta = abs(relative - offset)
                if delta > half_width:
                    continue
                pedestrian_id = int(fields[1])
                if delta >= distances[index].get(pedestrian_id, math.inf):
                    continue
                snapshots[index][pedestrian_id] = Observation(
                    pedestrian_id=pedestrian_id,
                    time=time,
                    x_m=float(fields[2]) / 1000.0,
                    y_m=float(fields[3]) / 1000.0,
                    speed_mps=float(fields[5]) / 1000.0,
                    motion_angle=float(fields[6]),
                )
                distances[index][pedestrian_id] = delta
            if offsets and relative > max(offsets) + half_width:
                break
    if first_time is None:
        raise ValueError("trajectory file contains no valid rows")
    return first_time, snapshots


def angular_distance(left: float, right: float) -> float:
    return abs((left - right + math.pi) % (2.0 * math.pi) - math.pi)


def candidate_edges(
    observations: Sequence[Observation], radius_m: float, max_angle_rad: float
) -> list[tuple[int, int, float]]:
    edges: list[tuple[int, int, float]] = []
    for left in range(len(observations)):
        for right in range(left + 1, len(observations)):
            a, b = observations[left], observations[right]
            distance = math.hypot(a.x_m - b.x_m, a.y_m - b.y_m)
            if distance <= radius_m and angular_distance(a.motion_angle, b.motion_angle) <= max_angle_rad:
                edges.append((left, right, distance))
    return edges


def _witness_digest(selected: Sequence[int], edges: Sequence[tuple[int, int, float]]) -> str:
    payload = [
        [int(edges[index][0]), int(edges[index][1]), format(float(edges[index][2]), ".17g")]
        for index in sorted(selected)
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def replay_matching_witness(
    vertex_count: int,
    edges: Sequence[tuple[int, int, float]],
    q: int,
    selected: Sequence[int],
    claimed_value: float,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    valid_indices = len(set(selected)) == len(selected) and all(
        0 <= index < len(edges) for index in selected
    )
    degrees = [0] * vertex_count
    if valid_indices:
        for index in selected:
            left, right, _ = edges[index]
            if not (0 <= left < right < vertex_count):
                valid_indices = False
                break
            degrees[left] += 1
            degrees[right] += 1
    objective = (
        sum(edges[index][2] for index in selected) / q
        if valid_indices and q > 0
        else 0.0
    )
    residual = abs(objective - claimed_value)
    cardinality_residual = abs(len(selected) - q)
    max_degree = max(degrees, default=0)
    return {
        "pass": bool(
            valid_indices
            and cardinality_residual == 0
            and max_degree <= 1
            and residual <= tolerance
        ),
        "max_degree": max_degree,
        "cardinality_residual": cardinality_residual,
        "objective_residual": residual,
    }


def solve_matching_endpoint(
    vertex_count: int,
    edges: Sequence[tuple[int, int, float]],
    q: int,
    maximize: bool,
    time_limit_seconds: float = 60.0,
    relative_gap: float = 0.0,
) -> EndpointResult:
    if vertex_count < 0 or q < 0 or q > vertex_count // 2:
        raise ValueError("matching cardinality must satisfy 0 <= q <= floor(vertex_count/2)")
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be finite and positive")
    if not math.isfinite(relative_gap) or relative_gap < 0:
        raise ValueError("relative_gap must be finite and nonnegative")
    for left, right, weight in edges:
        if not (0 <= left < right < vertex_count) or not math.isfinite(weight):
            raise ValueError("edges must have valid ordered endpoints and finite weights")

    if q == 0:
        return EndpointResult(
            status="NUMERICAL_MILP_OPTIMAL_REPLAYED",
            value=0.0,
            incumbent_value=0.0,
            selected=(),
            solver_status=0,
            solver_message="trivial q=0",
            mip_gap=0.0,
            mip_dual_bound=0.0,
            mip_node_count=0,
            replay_pass=True,
            replay_max_degree=0,
            replay_cardinality_residual=0,
            replay_objective_residual=0.0,
            solver_objective_residual=0.0,
            solver_dual_residual=0.0,
            raw_integrality_residual=0.0,
            raw_cardinality_residual=0.0,
            raw_max_degree_excess=0.0,
            witness_sha256=_witness_digest((), edges),
        )
    if not edges:
        return EndpointResult(
            status="INFEASIBLE", value=None, incumbent_value=None, selected=(),
            solver_status=2, solver_message="empty candidate graph", mip_gap=None,
            mip_dual_bound=None, mip_node_count=None, replay_pass=False,
            replay_max_degree=None, replay_cardinality_residual=None,
            replay_objective_residual=None, solver_objective_residual=None,
            solver_dual_residual=None, raw_integrality_residual=None,
            raw_cardinality_residual=None, raw_max_degree_excess=None,
            witness_sha256=None,
        )
    incidence = lil_matrix((vertex_count + 1, len(edges)), dtype=float)
    for edge_index, (left, right, _) in enumerate(edges):
        incidence[left, edge_index] = 1.0
        incidence[right, edge_index] = 1.0
        incidence[vertex_count, edge_index] = 1.0
    lower = np.concatenate((np.zeros(vertex_count), np.array([float(q)])))
    upper = np.concatenate((np.ones(vertex_count), np.array([float(q)])))
    weights = np.array([edge[2] for edge in edges], dtype=float)
    result = milp(
        c=-weights if maximize else weights,
        integrality=np.ones(len(edges), dtype=int),
        bounds=Bounds(np.zeros(len(edges)), np.ones(len(edges))),
        constraints=LinearConstraint(incidence.tocsr(), lower, upper),
        options={"time_limit": time_limit_seconds, "mip_rel_gap": relative_gap},
    )
    if result.status == 2:
        return EndpointResult(
            status="INFEASIBLE", value=None, incumbent_value=None, selected=(),
            solver_status=int(result.status), solver_message=str(result.message),
            mip_gap=None, mip_dual_bound=getattr(result, "mip_dual_bound", None),
            mip_node_count=getattr(result, "mip_node_count", None), replay_pass=False,
            replay_max_degree=None, replay_cardinality_residual=None,
            replay_objective_residual=None, solver_objective_residual=None,
            solver_dual_residual=None, raw_integrality_residual=None,
            raw_cardinality_residual=None, raw_max_degree_excess=None,
            witness_sha256=None,
        )
    if result.status != 0 or not result.success or result.x is None:
        return EndpointResult(
            status="UNRESOLVED", value=None, incumbent_value=None, selected=(),
            solver_status=int(result.status), solver_message=str(result.message),
            mip_gap=getattr(result, "mip_gap", None),
            mip_dual_bound=getattr(result, "mip_dual_bound", None),
            mip_node_count=getattr(result, "mip_node_count", None), replay_pass=False,
            replay_max_degree=None, replay_cardinality_residual=None,
            replay_objective_residual=None, solver_objective_residual=None,
            solver_dual_residual=None, raw_integrality_residual=None,
            raw_cardinality_residual=None, raw_max_degree_excess=None,
            witness_sha256=None,
        )

    raw_x = np.asarray(result.x, dtype=float)
    selected = [index for index, value in enumerate(raw_x) if value > 0.5]
    incumbent_value = float(weights[selected].sum() / q)
    replay = replay_matching_witness(vertex_count, edges, q, selected, incumbent_value)
    raw_integrality_residual = float(np.max(np.abs(raw_x - np.rint(raw_x))))
    raw_cardinality_residual = float(abs(raw_x.sum() - q))
    raw_degrees = np.asarray(incidence[:vertex_count, :].tocsr() @ raw_x).reshape(-1)
    raw_max_degree_excess = float(max(0.0, np.max(raw_degrees, initial=0.0) - 1.0))
    selected_total = float(weights[selected].sum())
    signed_selected_total = -selected_total if maximize else selected_total
    solver_fun = float(result.fun)
    solver_objective_residual = abs(solver_fun - signed_selected_total)
    raw_dual = getattr(result, "mip_dual_bound", None)
    dual_value = None if raw_dual is None else float((-raw_dual if maximize else raw_dual) / q)
    solver_dual_residual = None if raw_dual is None else abs(float(raw_dual) - solver_fun)
    gap = getattr(result, "mip_gap", None)
    gap_value = None if gap is None else float(gap)
    numerical_tolerance = 1e-8
    status = (
        "NUMERICAL_MILP_OPTIMAL_REPLAYED"
        if replay["pass"]
        and gap_value is not None
        and gap_value <= 1e-10
        and raw_dual is not None
        and solver_objective_residual <= numerical_tolerance
        and solver_dual_residual is not None
        and solver_dual_residual <= numerical_tolerance
        and raw_integrality_residual <= numerical_tolerance
        and raw_cardinality_residual <= numerical_tolerance
        and raw_max_degree_excess <= numerical_tolerance
        else "UNRESOLVED"
    )
    return EndpointResult(
        status=status,
        value=incumbent_value if status == "NUMERICAL_MILP_OPTIMAL_REPLAYED" else None,
        incumbent_value=incumbent_value,
        selected=tuple(selected),
        solver_status=int(result.status),
        solver_message=str(result.message),
        mip_gap=gap_value,
        mip_dual_bound=dual_value,
        mip_node_count=getattr(result, "mip_node_count", None),
        replay_pass=bool(replay["pass"]),
        replay_max_degree=int(replay["max_degree"]),
        replay_cardinality_residual=int(replay["cardinality_residual"]),
        replay_objective_residual=float(replay["objective_residual"]),
        solver_objective_residual=solver_objective_residual,
        solver_dual_residual=solver_dual_residual,
        raw_integrality_residual=raw_integrality_residual,
        raw_cardinality_residual=raw_cardinality_residual,
        raw_max_degree_excess=raw_max_degree_excess,
        witness_sha256=_witness_digest(selected, edges),
    )


def enumerate_matching_endpoint(
    vertex_count: int,
    edges: Sequence[tuple[int, int, float]],
    q: int,
    maximize: bool,
) -> tuple[float | None, tuple[int, ...]]:
    """Independent exact oracle for tiny graphs, using subset recursion."""

    incident: list[list[tuple[int, int]]] = [[] for _ in range(vertex_count)]
    for index, (left, right, _) in enumerate(edges):
        incident[left].append((right, index))
        incident[right].append((left, index))
    sign = 1.0 if maximize else -1.0

    @lru_cache(maxsize=None)
    def recurse(mask: int, remaining: int) -> tuple[float, tuple[int, ...]] | None:
        if remaining == 0:
            return 0.0, ()
        if mask.bit_count() < 2 * remaining:
            return None
        left = (mask & -mask).bit_length() - 1
        best = recurse(mask & ~(1 << left), remaining)
        for right, edge_index in incident[left]:
            if not (mask & (1 << right)):
                continue
            tail = recurse(mask & ~(1 << left) & ~(1 << right), remaining - 1)
            if tail is None:
                continue
            candidate = (tail[0] + edges[edge_index][2], tail[1] + (edge_index,))
            if best is None or sign * candidate[0] > sign * best[0] + 1e-12:
                best = candidate
        return best

    result = recurse((1 << vertex_count) - 1, q)
    if result is None:
        return None, ()
    return result[0] / q if q else 0.0, tuple(sorted(result[1]))


def true_dyads(
    observations: Sequence[Observation], membership: dict[int, frozenset[int]]
) -> list[frozenset[int]]:
    visible = {observation.pedestrian_id for observation in observations}
    return sorted(
        {
            group
            for pedestrian_id in visible
            for group in [membership.get(pedestrian_id, frozenset())]
            if len(group) == 2 and group <= visible
        },
        key=lambda group: tuple(sorted(group)),
    )


def evaluate_snapshot(
    observations_by_id: dict[int, Observation],
    membership: dict[int, frozenset[int]],
    excluded_ids: set[int],
    radii: Sequence[float],
    max_angle_rad: float,
    thresholds: Sequence[float],
    minimum_people: int,
    certificate: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    certificate = certificate or {}
    relative_gap = float(certificate.get("solver_relative_gap", 0.0))
    time_limit = float(certificate.get("solver_time_limit_seconds", 60.0))
    independent_max_vertices = int(certificate.get("independent_subset_oracle_max_vertices", 12))
    observations = sorted(
        (value for key, value in observations_by_id.items() if key not in excluded_ids),
        key=lambda value: value.pedestrian_id,
    )
    dyads = true_dyads(observations, membership)
    if len(observations) < minimum_people or not dyads:
        return []
    by_id = {item.pedestrian_id: item for item in observations}
    truth_distances = [
        math.hypot(by_id[a].x_m - by_id[b].x_m, by_id[a].y_m - by_id[b].y_m)
        for a, b in (tuple(sorted(group)) for group in dyads)
    ]
    true_value = sum(truth_distances) / len(truth_distances)
    id_to_index = {item.pedestrian_id: index for index, item in enumerate(observations)}
    truth_index_edges = {
        tuple(sorted((id_to_index[a], id_to_index[b])))
        for a, b in (tuple(sorted(group)) for group in dyads)
    }
    rows: list[dict[str, Any]] = []
    for radius in radii:
        edges = candidate_edges(observations, radius, max_angle_rad)
        edge_pairs = {(left, right) for left, right, _ in edges}
        representable = truth_index_edges <= edge_pairs
        lower_result = solve_matching_endpoint(
            len(observations), edges, len(dyads), False, time_limit, relative_gap
        )
        upper_result = solve_matching_endpoint(
            len(observations), edges, len(dyads), True, time_limit, relative_gap
        )
        lower_status, lower = lower_result.status, lower_result.value
        upper_status, upper = upper_result.status, upper_result.value
        exact = lower_status == upper_status == "NUMERICAL_MILP_OPTIMAL_REPLAYED"
        status_consistent = (lower_status == "INFEASIBLE") == (upper_status == "INFEASIBLE")
        independent_check = "NOT_RUN_SIZE_LIMIT"
        independent_lower = None
        independent_upper = None
        if len(observations) <= independent_max_vertices:
            independent_lower, _ = enumerate_matching_endpoint(
                len(observations), edges, len(dyads), False
            )
            independent_upper, _ = enumerate_matching_endpoint(
                len(observations), edges, len(dyads), True
            )
            if independent_lower is None or independent_upper is None:
                independent_check = "PASS_INFEASIBLE" if lower_status == upper_status == "INFEASIBLE" else "FAIL"
            else:
                independent_check = (
                    "PASS"
                    if exact
                    and abs(independent_lower - lower) <= 1e-8
                    and abs(independent_upper - upper) <= 1e-8
                    else "FAIL"
                )
        covered = bool(exact and lower is not None and upper is not None and lower - 1e-8 <= true_value <= upper + 1e-8)
        point_value = None
        point_errors = None
        errors_flagged = None
        ambiguous_count = None
        if exact and lower is not None and upper is not None:
            point_value = lower  # deterministic closest-pair reconstruction rule
            point_errors = sum((point_value >= t) != (true_value >= t) for t in thresholds)
            ambiguous = [not (lower >= t or upper < t) for t in thresholds]
            ambiguous_count = sum(ambiguous)
            errors_flagged = sum(
                ((point_value >= t) != (true_value >= t)) and flag
                for t, flag in zip(thresholds, ambiguous)
            )
        rows.append(
            {
                "radius_m": radius,
                "visible_people": len(observations),
                "true_dyad_count": len(dyads),
                "candidate_edge_count": len(edges),
                "true_world_representable": representable,
                "true_mean_distance_m": true_value,
                "lower_status": lower_status,
                "upper_status": upper_status,
                "endpoint_status_consistent": status_consistent,
                "frontier_lower_m": lower,
                "frontier_upper_m": upper,
                "lower_incumbent_m": lower_result.incumbent_value,
                "upper_incumbent_m": upper_result.incumbent_value,
                "frontier_width_m": None if not exact else upper - lower,
                "truth_covered": covered,
                "point_rule_mean_distance_m": point_value,
                "point_rule_threshold_errors": point_errors,
                "errors_flagged_ambiguous": errors_flagged,
                "ambiguous_thresholds": ambiguous_count,
                "decision_threshold_count": len(thresholds),
                "lower_witness_edge_count": len(lower_result.selected),
                "upper_witness_edge_count": len(upper_result.selected),
                "lower_witness_edges": [list(edges[index]) for index in lower_result.selected],
                "upper_witness_edges": [list(edges[index]) for index in upper_result.selected],
                "lower_witness_sha256": lower_result.witness_sha256,
                "upper_witness_sha256": upper_result.witness_sha256,
                "lower_replay_pass": lower_result.replay_pass,
                "upper_replay_pass": upper_result.replay_pass,
                "lower_replay_max_degree": lower_result.replay_max_degree,
                "upper_replay_max_degree": upper_result.replay_max_degree,
                "lower_replay_cardinality_residual": lower_result.replay_cardinality_residual,
                "upper_replay_cardinality_residual": upper_result.replay_cardinality_residual,
                "lower_replay_objective_residual": lower_result.replay_objective_residual,
                "upper_replay_objective_residual": upper_result.replay_objective_residual,
                "lower_solver_objective_residual": lower_result.solver_objective_residual,
                "upper_solver_objective_residual": upper_result.solver_objective_residual,
                "lower_solver_dual_residual": lower_result.solver_dual_residual,
                "upper_solver_dual_residual": upper_result.solver_dual_residual,
                "lower_raw_integrality_residual": lower_result.raw_integrality_residual,
                "upper_raw_integrality_residual": upper_result.raw_integrality_residual,
                "lower_raw_cardinality_residual": lower_result.raw_cardinality_residual,
                "upper_raw_cardinality_residual": upper_result.raw_cardinality_residual,
                "lower_raw_max_degree_excess": lower_result.raw_max_degree_excess,
                "upper_raw_max_degree_excess": upper_result.raw_max_degree_excess,
                "lower_mip_gap": lower_result.mip_gap,
                "upper_mip_gap": upper_result.mip_gap,
                "lower_mip_dual_bound_m": lower_result.mip_dual_bound,
                "upper_mip_dual_bound_m": upper_result.mip_dual_bound,
                "lower_mip_node_count": lower_result.mip_node_count,
                "upper_mip_node_count": upper_result.mip_node_count,
                "lower_solver_status": lower_result.solver_status,
                "upper_solver_status": upper_result.solver_status,
                "lower_solver_message": lower_result.solver_message,
                "upper_solver_message": upper_result.solver_message,
                "independent_tiny_check": independent_check,
                "independent_lower_m": independent_lower,
                "independent_upper_m": independent_upper,
            }
        )
    return rows


def run(
    trajectory: Path,
    groups: Path,
    protocol_path: Path,
    output: Path,
    audit_role: str,
) -> dict[str, Any]:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    selection = protocol["selection"]
    candidate = protocol["candidate_support"]
    query = protocol["query"]
    certificate = protocol.get("certificate", {})
    grid = selection.get("snapshot_grid_seconds")
    if grid is not None:
        offsets = list(
            range(
                int(grid["start"]),
                int(grid["stop_inclusive"]) + 1,
                int(grid["step"]),
            )
        )
    else:
        offsets = selection["snapshot_offsets_seconds"]
    if not offsets or offsets != sorted(set(offsets)):
        raise ValueError("snapshot offsets must be nonempty, sorted, and unique")
    parsed_groups = parse_groups(groups)
    first_time, snapshots = load_snapshots(
        trajectory,
        offsets,
        selection["snapshot_half_width_seconds"],
    )
    cells: list[dict[str, Any]] = []
    for offset, snapshot in zip(offsets, snapshots):
        evaluated = evaluate_snapshot(
            snapshot,
            parsed_groups.membership,
            set(parsed_groups.excluded_ids),
            candidate["distance_radii_m"],
            math.radians(candidate["maximum_motion_angle_degrees"]),
            query["decision_thresholds_m"],
            selection["minimum_visible_people"],
            certificate,
        )
        for cell in evaluated:
            cell["snapshot_offset_seconds"] = offset
            cell["snapshot_time_unix"] = first_time + offset
            cells.append(cell)
    eligible = len({cell["snapshot_offset_seconds"] for cell in cells})
    exact_cells = sum(
        cell["lower_status"] == cell["upper_status"] == "NUMERICAL_MILP_OPTIMAL_REPLAYED"
        for cell in cells
    )
    closed_cells = sum(
        cell["lower_status"] in {"NUMERICAL_MILP_OPTIMAL_REPLAYED", "INFEASIBLE"}
        and cell["upper_status"] in {"NUMERICAL_MILP_OPTIMAL_REPLAYED", "INFEASIBLE"}
        and cell["endpoint_status_consistent"]
        for cell in cells
    )
    replayed_exact_cells = sum(
        cell["lower_replay_pass"] and cell["upper_replay_pass"] for cell in cells
    )
    independent_tiny_checks = [
        cell for cell in cells if cell["independent_tiny_check"] != "NOT_RUN_SIZE_LIMIT"
    ]
    independent_tiny_passes = sum(
        cell["independent_tiny_check"] in {"PASS", "PASS_INFEASIBLE"}
        for cell in independent_tiny_checks
    )
    all_pass = bool(
        cells
        and closed_cells == len(cells)
        and exact_cells == replayed_exact_cells
        and independent_tiny_checks
        and independent_tiny_passes == len(independent_tiny_checks)
    )
    representable_cells = [cell for cell in cells if cell["true_world_representable"]]
    representable_truth_covered = sum(cell["truth_covered"] for cell in representable_cells)
    representable_point_errors = sum(
        cell["point_rule_threshold_errors"] or 0 for cell in representable_cells
    )
    representable_errors_flagged = sum(
        cell["errors_flagged_ambiguous"] or 0 for cell in representable_cells
    )
    report = {
        "report_version": "atr-diamor-dyad-truth-report/v3",
        "status": "PASS" if all_pass else "HOLD",
        "computational_status": "PASS" if cells and closed_cells == len(cells) else "HOLD",
        "semantic_status": "PASS" if cells and all(cell["endpoint_status_consistent"] for cell in cells) else "HOLD",
        "witness_replay_status": "PASS" if exact_cells == replayed_exact_cells else "HOLD",
        "independent_tiny_oracle_status": (
            "PASS"
            if independent_tiny_checks and independent_tiny_passes == len(independent_tiny_checks)
            else "HOLD"
        ),
        "dataset_day": trajectory.stem.replace("person_", "").replace("_all", ""),
        "audit_role": audit_role,
        "claim_scope": "DIAMOR fixed-snapshot dyads only; q-conditioned aggregate identification",
        "trajectory_sha256": sha256_file(trajectory),
        "groups_sha256": sha256_file(groups),
        "protocol_sha256": sha256_file(protocol_path),
        "benchmark_sha256": sha256_file(Path(__file__)),
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "solver": "scipy.optimize.milp (HiGHS)"
        },
        "predeclared_snapshot_count": len(offsets),
        "eligible_snapshot_count": eligible,
        "cell_count": len(cells),
        "exact_cell_count": exact_cells,
        "replayed_exact_cell_count": replayed_exact_cells,
        "computationally_closed_cell_count": closed_cells,
        "independent_tiny_checked_cell_count": len(independent_tiny_checks),
        "independent_tiny_passed_cell_count": independent_tiny_passes,
        "truth_representable_cell_count": len(representable_cells),
        "representable_truth_covered_cell_count": representable_truth_covered,
        "aggregate_value_covered_cell_count_including_misspecified_support": sum(
            cell["truth_covered"] for cell in cells
        ),
        "representable_point_rule_threshold_errors": representable_point_errors,
        "representable_errors_flagged_ambiguous": representable_errors_flagged,
        "group_parse_audit": parsed_groups.audit,
        "excluded_or_quarantined_member_count": len(parsed_groups.excluded_ids),
        "label_usage": {
            "candidate_edge_scoring": False,
            "cohort_exclusion": True,
            "snapshot_eligibility": True,
            "cardinality_q": True,
            "final_truth_audit": True
        },
        "cells": cells,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if cells:
        with (output / "CELLS.csv").open("w", newline="", encoding="utf-8") as handle:
            csv_cells = []
            for cell in cells:
                flat = dict(cell)
                flat["lower_witness_edges"] = json.dumps(flat["lower_witness_edges"], separators=(",", ":"))
                flat["upper_witness_edges"] = json.dumps(flat["upper_witness_edges"], separators=(",", ":"))
                csv_cells.append(flat)
            writer = csv.DictWriter(handle, fieldnames=list(csv_cells[0]))
            writer.writeheader()
            writer.writerows(csv_cells)
    (output / "RUN_MANIFEST.json").write_text(
        json.dumps({key: report[key] for key in report if key != "cells"}, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(__file__).with_name("ATR_DIAMOR_DYAD_PROTOCOL.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--audit-role",
        choices=("pilot", "confirmatory", "predeclared_followup"),
        required=True,
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    print(
        json.dumps(
            run(
                arguments.trajectory,
                arguments.groups,
                arguments.protocol,
                arguments.output,
                arguments.audit_role,
            ),
            indent=2,
        )
    )
