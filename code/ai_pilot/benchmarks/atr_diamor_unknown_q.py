#!/usr/bin/env python3
"""ATR cardinality-uncertainty audit over unions of fixed-q matchings."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Sequence

import atr_diamor_dyad_truth as base


OPTIMAL = "NUMERICAL_MILP_OPTIMAL_REPLAYED"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cardinality_regimes(true_q: int, vertex_count: int) -> dict[str, list[int]]:
    maximum = vertex_count // 2
    if true_q < 1 or true_q > maximum:
        raise ValueError("true q must be positive and compatible with vertex count")
    return {
        "oracle_q": [true_q],
        "q_pm_1": list(range(max(1, true_q - 1), min(maximum, true_q + 1) + 1)),
        "all_positive_q": list(range(1, maximum + 1)),
    }


def union_matching_frontier(
    vertex_count: int,
    edges: Sequence[tuple[int, int, float]],
    q_values: Sequence[int],
    time_limit: float,
    relative_gap: float,
) -> dict[str, Any]:
    if not q_values or list(q_values) != sorted(set(q_values)) or min(q_values) < 1:
        raise ValueError("q_values must be nonempty sorted unique positive integers")
    endpoints: list[dict[str, Any]] = []
    for q in q_values:
        lower = base.solve_matching_endpoint(
            vertex_count, edges, q, False, time_limit, relative_gap
        )
        upper = base.solve_matching_endpoint(
            vertex_count, edges, q, True, time_limit, relative_gap
        )
        if (lower.status == "INFEASIBLE") != (upper.status == "INFEASIBLE"):
            return {"status": "HOLD_INCONSISTENT", "q_endpoints": endpoints}
        endpoints.append(
            {
                "q": q,
                "lower_status": lower.status,
                "upper_status": upper.status,
                "lower": lower.value,
                "upper": upper.value,
                "lower_witness_sha256": lower.witness_sha256,
                "upper_witness_sha256": upper.witness_sha256,
            }
        )
    if any(
        endpoint[side] not in {OPTIMAL, "INFEASIBLE"}
        for endpoint in endpoints
        for side in ("lower_status", "upper_status")
    ):
        return {"status": "UNRESOLVED", "q_endpoints": endpoints}
    feasible = [endpoint for endpoint in endpoints if endpoint["lower_status"] == OPTIMAL]
    if not feasible:
        return {
            "status": "INFEASIBLE",
            "q_endpoints": endpoints,
            "feasible_q": [],
            "lower": None,
            "upper": None,
        }
    lower_endpoint = min(feasible, key=lambda item: (item["lower"], item["q"]))
    upper_endpoint = max(feasible, key=lambda item: (item["upper"], -item["q"]))
    return {
        "status": "EXACT_UNION_OF_REPLAYED_FIXED_Q_FRONTIERS",
        "q_endpoints": endpoints,
        "feasible_q": [item["q"] for item in feasible],
        "lower": lower_endpoint["lower"],
        "upper": upper_endpoint["upper"],
        "lower_attained_q": lower_endpoint["q"],
        "upper_attained_q": upper_endpoint["q"],
        "lower_witness_sha256": lower_endpoint["lower_witness_sha256"],
        "upper_witness_sha256": upper_endpoint["upper_witness_sha256"],
    }


def evaluate_snapshot(
    observations_by_id: dict[int, base.Observation],
    membership: dict[int, frozenset[int]],
    excluded_ids: set[int],
    radii: Sequence[float],
    max_angle_rad: float,
    thresholds: Sequence[float],
    minimum_people: int,
    certificate: dict[str, Any],
) -> list[dict[str, Any]]:
    observations = sorted(
        (value for key, value in observations_by_id.items() if key not in excluded_ids),
        key=lambda value: value.pedestrian_id,
    )
    dyads = base.true_dyads(observations, membership)
    if len(observations) < minimum_people or not dyads:
        return []
    by_id = {item.pedestrian_id: item for item in observations}
    truth_distances = [
        math.hypot(by_id[a].x_m - by_id[b].x_m, by_id[a].y_m - by_id[b].y_m)
        for a, b in (tuple(sorted(group)) for group in dyads)
    ]
    truth_value = sum(truth_distances) / len(truth_distances)
    id_to_index = {item.pedestrian_id: index for index, item in enumerate(observations)}
    truth_edges = {
        tuple(sorted((id_to_index[a], id_to_index[b])))
        for a, b in (tuple(sorted(group)) for group in dyads)
    }
    time_limit = float(certificate.get("solver_time_limit_seconds", 60.0))
    relative_gap = float(certificate.get("solver_relative_gap", 0.0))
    rows: list[dict[str, Any]] = []
    for radius in radii:
        edges = base.candidate_edges(observations, radius, max_angle_rad)
        representable = truth_edges <= {(left, right) for left, right, _ in edges}
        row: dict[str, Any] = {
            "radius_m": radius,
            "visible_people": len(observations),
            "true_dyad_count": len(dyads),
            "candidate_edge_count": len(edges),
            "true_world_representable": representable,
            "true_mean_distance_m": truth_value,
            "regimes": {},
        }
        for name, q_values in cardinality_regimes(len(dyads), len(observations)).items():
            result = union_matching_frontier(
                len(observations), edges, q_values, time_limit, relative_gap
            )
            exact = result["status"] == "EXACT_UNION_OF_REPLAYED_FIXED_Q_FRONTIERS"
            lower, upper = result.get("lower"), result.get("upper")
            ambiguous = None
            false_certificates = None
            if exact:
                ambiguous_flags = [not (lower >= t or upper < t) for t in thresholds]
                ambiguous = sum(ambiguous_flags)
                false_certificates = sum(
                    (not flag)
                    and ((lower >= threshold) != (truth_value >= threshold))
                    for threshold, flag in zip(thresholds, ambiguous_flags)
                )
            row["regimes"][name] = {
                **result,
                "q_candidates": q_values,
                "width": None if not exact else upper - lower,
                "truth_covered": bool(
                    exact and lower - 1e-8 <= truth_value <= upper + 1e-8
                ),
                "ambiguous_thresholds": ambiguous,
                "false_certificates": false_certificates,
            }
        rows.append(row)
    return rows


def summarize(cells: Sequence[dict[str, Any]], thresholds: Sequence[float]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for regime in ("oracle_q", "q_pm_1", "all_positive_q"):
        closed = [
            cell for cell in cells
            if cell["regimes"][regime]["status"]
            in {"EXACT_UNION_OF_REPLAYED_FIXED_Q_FRONTIERS", "INFEASIBLE"}
        ]
        exact = [
            cell for cell in cells
            if cell["regimes"][regime]["status"]
            == "EXACT_UNION_OF_REPLAYED_FIXED_Q_FRONTIERS"
        ]
        widths = [cell["regimes"][regime]["width"] for cell in exact]
        representable = [cell for cell in exact if cell["true_world_representable"]]
        summary[regime] = {
            "cell_count": len(cells),
            "computationally_closed_cell_count": len(closed),
            "exact_cell_count": len(exact),
            "infeasible_cell_count": sum(
                cell["regimes"][regime]["status"] == "INFEASIBLE"
                for cell in cells
            ),
            "truth_representable_exact_cells": len(representable),
            "truth_covered_representable_cells": sum(
                cell["regimes"][regime]["truth_covered"] for cell in representable
            ),
            "threshold_decisions": len(exact) * len(thresholds),
            "ambiguous_threshold_decisions": sum(
                cell["regimes"][regime]["ambiguous_thresholds"] for cell in exact
            ),
            "certified_threshold_decisions": sum(
                len(thresholds) - cell["regimes"][regime]["ambiguous_thresholds"]
                for cell in exact
            ),
            "false_certificates": sum(
                cell["regimes"][regime]["false_certificates"] for cell in exact
            ),
            "mean_width_m": statistics.fmean(widths) if widths else None,
            "median_width_m": statistics.median(widths) if widths else None,
        }
    return summary


def run(
    trajectory: Path,
    groups: Path,
    base_protocol_path: Path,
    unknown_protocol_path: Path,
    output: Path,
    audit_role: str,
) -> dict[str, Any]:
    protocol = json.loads(base_protocol_path.read_text())
    unknown_protocol = json.loads(unknown_protocol_path.read_text())
    selection, candidate, query = (
        protocol["selection"], protocol["candidate_support"], protocol["query"]
    )
    grid = selection["snapshot_grid_seconds"]
    offsets = list(range(grid["start"], grid["stop_inclusive"] + 1, grid["step"]))
    parsed = base.parse_groups(groups)
    first_time, snapshots = base.load_snapshots(
        trajectory, offsets, selection["snapshot_half_width_seconds"]
    )
    cells: list[dict[str, Any]] = []
    for offset, snapshot in zip(offsets, snapshots):
        evaluated = evaluate_snapshot(
            snapshot,
            parsed.membership,
            set(parsed.excluded_ids),
            candidate["distance_radii_m"],
            math.radians(candidate["maximum_motion_angle_degrees"]),
            query["decision_thresholds_m"],
            selection["minimum_visible_people"],
            protocol["certificate"],
        )
        for cell in evaluated:
            cell["snapshot_offset_seconds"] = offset
            cell["snapshot_time_unix"] = first_time + offset
            cells.append(cell)
    summary = summarize(cells, query["decision_thresholds_m"])
    all_closed = all(
        item["computationally_closed_cell_count"] == item["cell_count"]
        for item in summary.values()
    )
    report = {
        "report_version": "atr-diamor-unknown-q-report/v1",
        "status": "PASS" if cells and all_closed else "HOLD",
        "dataset_day": trajectory.stem.replace("person_", "").replace("_all", ""),
        "audit_role": audit_role,
        "claim_scope": unknown_protocol["claim_boundary"],
        "trajectory_sha256": _sha256(trajectory),
        "groups_sha256": _sha256(groups),
        "base_protocol_sha256": _sha256(base_protocol_path),
        "unknown_q_protocol_sha256": _sha256(unknown_protocol_path),
        "benchmark_sha256": _sha256(Path(__file__)),
        "eligible_snapshot_count": len({c["snapshot_offset_seconds"] for c in cells}),
        "cell_count": len(cells),
        "decision_threshold_count": len(query["decision_thresholds_m"]),
        "summary": summary,
        "cells": cells,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "RUN_MANIFEST.json").write_text(
        json.dumps({key: value for key, value in report.items() if key != "cells"}, indent=2)
        + "\n"
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-role", required=True)
    parser.add_argument(
        "--base-protocol", type=Path,
        default=Path(__file__).with_name("ATR_DIAMOR_DYAD_PROTOCOL.json"),
    )
    parser.add_argument(
        "--unknown-q-protocol", type=Path,
        default=Path(__file__).with_name("ATR_DIAMOR_UNKNOWN_Q_PROTOCOL.json"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(
        args.trajectory, args.groups, args.base_protocol,
        args.unknown_q_protocol, args.output, args.audit_role,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "cells"}, indent=2))
