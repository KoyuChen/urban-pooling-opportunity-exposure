#!/usr/bin/env python3
"""Cross-day audit of a local degree cap inside frozen ATR support."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import atr_diamor_dyad_truth as base
import atr_diamor_support_calibration as support


OPTIMAL = "NUMERICAL_MILP_OPTIMAL_REPLAYED"


def capped_edges(snapshot: dict[str, Any], rule: dict[str, Any], degree_cap: int) -> list[tuple[int, int, float]]:
    if degree_cap <= 0:
        raise ValueError("degree cap must be positive")
    incident: dict[int, list[tuple[float, int]]] = {
        index: [] for index in range(len(snapshot["observations"]))
    }
    distances: dict[tuple[int, int], float] = {}
    for left, right, distance, heading in snapshot["pairs"]:
        if distance <= rule["radius_m"] and heading <= rule["maximum_motion_angle_degrees"]:
            incident[left].append((distance, right))
            incident[right].append((distance, left))
            distances[(left, right)] = distance
    retained = {
        tuple(sorted((node, neighbor)))
        for node, neighbors in incident.items()
        for _, neighbor in sorted(neighbors)[:degree_cap]
    }
    return [(left, right, distances[(left, right)]) for left, right in sorted(retained)]


def cap_metrics(snapshots: Sequence[dict[str, Any]], rule: dict[str, Any], caps: Sequence[int]) -> list[dict[str, Any]]:
    rows = []
    for cap in caps:
        graphs = [capped_edges(snapshot, rule, cap) for snapshot in snapshots]
        covered = sum(
            snapshot["truth_edges"] <= {(left, right) for left, right, _ in edges}
            for snapshot, edges in zip(snapshots, graphs)
        )
        rows.append({
            "degree_cap": cap,
            "eligible_snapshots": len(snapshots),
            "covered_snapshots": covered,
            "relational_coverage": covered / len(snapshots),
            "mean_candidate_edges": sum(map(len, graphs)) / len(graphs),
            "total_candidate_edges": sum(map(len, graphs)),
        })
    return rows


def select_cap(rows: Sequence[dict[str, Any]], minimum_covered: int) -> dict[str, Any]:
    eligible = [row for row in rows if row["covered_snapshots"] >= minimum_covered]
    if not eligible:
        raise ValueError("no degree cap preserves pilot fixed-rule coverage")
    return min(eligible, key=lambda row: (row["mean_candidate_edges"], row["degree_cap"]))


def frontier_metrics(
    snapshots: Sequence[dict[str, Any]], rule: dict[str, Any], degree_cap: int,
    thresholds: Sequence[float], certificate: dict[str, Any],
) -> dict[str, Any]:
    cells = []
    for snapshot in snapshots:
        edges = capped_edges(snapshot, rule, degree_cap)
        edge_pairs = {(left, right) for left, right, _ in edges}
        representable = snapshot["truth_edges"] <= edge_pairs
        q = snapshot["true_q"]
        lower = base.solve_matching_endpoint(
            len(snapshot["observations"]), edges, q, False,
            certificate["solver_time_limit_seconds"], certificate["solver_relative_gap"],
        )
        upper = base.solve_matching_endpoint(
            len(snapshot["observations"]), edges, q, True,
            certificate["solver_time_limit_seconds"], certificate["solver_relative_gap"],
        )
        exact = lower.status == upper.status == OPTIMAL
        ambiguous = false_certificates = None
        if exact:
            flags = [not (lower.value >= threshold or upper.value < threshold) for threshold in thresholds]
            ambiguous = sum(flags)
            false_certificates = sum(
                (not flag) and ((lower.value >= threshold) != (snapshot["true_mean_distance_m"] >= threshold))
                for threshold, flag in zip(thresholds, flags)
            )
        cells.append({
            "snapshot_offset_seconds": snapshot["snapshot_offset_seconds"],
            "candidate_edge_count": len(edges),
            "true_world_representable": representable,
            "lower_status": lower.status,
            "upper_status": upper.status,
            "lower": lower.value,
            "upper": upper.value,
            "ambiguous_thresholds": ambiguous,
            "false_certificates": false_certificates,
        })
    exact = [cell for cell in cells if cell["lower_status"] == cell["upper_status"] == OPTIMAL]
    closed = [
        cell for cell in cells
        if cell["lower_status"] == cell["upper_status"]
        and cell["lower_status"] in {OPTIMAL, "INFEASIBLE"}
    ]
    return {
        "computationally_closed_cells": len(closed),
        "exact_cells": len(exact),
        "infeasible_cells": len(cells) - len(exact),
        "threshold_decisions": len(exact) * len(thresholds),
        "ambiguous_threshold_decisions": sum(cell["ambiguous_thresholds"] for cell in exact),
        "certified_threshold_decisions": sum(len(thresholds) - cell["ambiguous_thresholds"] for cell in exact),
        "false_certificates": sum(cell["false_certificates"] for cell in exact),
        "false_certificate_representable_cells": sum(
            bool(cell["false_certificates"]) and cell["true_world_representable"] for cell in exact
        ),
        "cells": cells,
    }


def run(
    pilot_trajectory: Path, pilot_groups: Path, followup_trajectory: Path,
    followup_groups: Path, base_protocol_path: Path, density_protocol_path: Path,
    support_summary_path: Path, output: Path,
) -> dict[str, Any]:
    base_protocol = json.loads(base_protocol_path.read_text())
    protocol = json.loads(density_protocol_path.read_text())
    baseline = json.loads(support_summary_path.read_text())
    rule = baseline["selected_rule"]
    pilot, _ = support.prepared_snapshots(pilot_trajectory, pilot_groups, base_protocol)
    followup, _ = support.prepared_snapshots(followup_trajectory, followup_groups, base_protocol)
    pilot_grid = cap_metrics(pilot, rule, protocol["degree_caps"])
    selected = select_cap(pilot_grid, rule["covered_snapshots"])
    followup_grid = cap_metrics(followup, rule, protocol["degree_caps"])
    followup_selected = next(row for row in followup_grid if row["degree_cap"] == selected["degree_cap"])
    frontier = frontier_metrics(
        followup, rule, selected["degree_cap"],
        base_protocol["query"]["decision_thresholds_m"], base_protocol["certificate"],
    )
    baseline_followup = baseline["followup_selected_rule"]
    baseline_frontier = baseline["followup_frontier"]
    comparison = {
        "mean_edge_ratio_to_fixed": followup_selected["mean_candidate_edges"] / baseline_followup["mean_candidate_edges"],
        "candidate_edges_saved": baseline_followup["total_candidate_edges"] - followup_selected["total_candidate_edges"],
        "coverage_change_snapshots": followup_selected["covered_snapshots"] - baseline_followup["covered_snapshots"],
        "certified_decision_change": frontier["certified_threshold_decisions"] - baseline_frontier["certified_threshold_decisions"],
    }
    status = "PASS" if (
        frontier["computationally_closed_cells"] == len(followup)
        and frontier["false_certificate_representable_cells"] == 0
    ) else "HOLD"
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "report_version": "atr-diamor-density-cap-report/v1",
        "status": status,
        "claim_scope": protocol["claim_boundary"],
        "pilot_trajectory_sha256": sha(pilot_trajectory),
        "pilot_groups_sha256": sha(pilot_groups),
        "followup_trajectory_sha256": sha(followup_trajectory),
        "followup_groups_sha256": sha(followup_groups),
        "base_protocol_sha256": sha(base_protocol_path),
        "density_protocol_sha256": sha(density_protocol_path),
        "support_summary_sha256": sha(support_summary_path),
        "benchmark_sha256": sha(Path(__file__)),
        "fixed_rule": {"radius_m": rule["radius_m"], "maximum_motion_angle_degrees": rule["maximum_motion_angle_degrees"]},
        "pilot_fixed_covered_snapshots": rule["covered_snapshots"],
        "selected_cap": selected,
        "followup_selected_cap": followup_selected,
        "followup_frontier": {key: value for key, value in frontier.items() if key != "cells"},
        "comparison_to_fixed": comparison,
        "pilot_grid": pilot_grid,
        "followup_grid": followup_grid,
        "cells": frontier["cells"],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "RUN_MANIFEST.json").write_text(
        json.dumps({key: value for key, value in report.items() if key != "cells"}, indent=2) + "\n"
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for name in ("pilot-trajectory", "pilot-groups", "followup-trajectory", "followup-groups"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    here = Path(__file__).parent
    parser.add_argument("--base-protocol", type=Path, default=here / "ATR_DIAMOR_DYAD_PROTOCOL.json")
    parser.add_argument("--density-protocol", type=Path, default=here / "ATR_DIAMOR_DENSITY_CAP_PROTOCOL.json")
    parser.add_argument("--support-summary", type=Path, default=here / "results/atr_diamor_support_calibration/SUMMARY.json")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(
        args.pilot_trajectory, args.pilot_groups, args.followup_trajectory,
        args.followup_groups, args.base_protocol, args.density_protocol,
        args.support_summary, args.output,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "cells"}, indent=2))
