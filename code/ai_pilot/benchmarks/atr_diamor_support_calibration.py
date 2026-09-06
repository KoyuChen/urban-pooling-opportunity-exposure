#!/usr/bin/env python3
"""Pilot-calibrated ATR candidate support with frozen cross-day evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

import atr_diamor_dyad_truth as base


OPTIMAL = "NUMERICAL_MILP_OPTIMAL_REPLAYED"


def prepared_snapshots(
    trajectory: Path, groups: Path, protocol: dict[str, Any]
) -> tuple[list[dict[str, Any]], base.GroupParseResult]:
    selection = protocol["selection"]
    grid = selection["snapshot_grid_seconds"]
    offsets = list(range(grid["start"], grid["stop_inclusive"] + 1, grid["step"]))
    parsed = base.parse_groups(groups)
    _, snapshots = base.load_snapshots(
        trajectory, offsets, selection["snapshot_half_width_seconds"]
    )
    prepared = []
    for offset, snapshot in zip(offsets, snapshots):
        observations = sorted(
            (value for key, value in snapshot.items() if key not in parsed.excluded_ids),
            key=lambda value: value.pedestrian_id,
        )
        dyads = base.true_dyads(observations, parsed.membership)
        if len(observations) < selection["minimum_visible_people"] or not dyads:
            continue
        id_index = {item.pedestrian_id: index for index, item in enumerate(observations)}
        truth = {
            tuple(sorted((id_index[a], id_index[b])))
            for a, b in (tuple(sorted(group)) for group in dyads)
        }
        pairs = []
        for left in range(len(observations)):
            for right in range(left + 1, len(observations)):
                a, b = observations[left], observations[right]
                pairs.append((
                    left, right, math.hypot(a.x_m - b.x_m, a.y_m - b.y_m),
                    math.degrees(base.angular_distance(a.motion_angle, b.motion_angle)),
                ))
        truth_value = sum(
            next(distance for left, right, distance, _ in pairs if (left, right) == edge)
            for edge in truth
        ) / len(truth)
        prepared.append({
            "snapshot_offset_seconds": offset, "observations": observations,
            "truth_edges": truth, "true_q": len(truth),
            "true_mean_distance_m": truth_value, "pairs": pairs,
        })
    return prepared, parsed


def grid_metrics(
    snapshots: Sequence[dict[str, Any]], radii: Sequence[float], angles: Sequence[float]
) -> list[dict[str, Any]]:
    rows = []
    for radius in radii:
        for angle in angles:
            edge_counts = []
            covered = 0
            for snapshot in snapshots:
                edges = {
                    (left, right) for left, right, distance, heading in snapshot["pairs"]
                    if distance <= radius and heading <= angle
                }
                edge_counts.append(len(edges))
                covered += snapshot["truth_edges"] <= edges
            rows.append({
                "radius_m": radius, "maximum_motion_angle_degrees": angle,
                "eligible_snapshots": len(snapshots), "covered_snapshots": covered,
                "relational_coverage": covered / len(snapshots),
                "mean_candidate_edges": sum(edge_counts) / len(edge_counts),
                "total_candidate_edges": sum(edge_counts),
            })
    return rows


def select_rule(rows: Sequence[dict[str, Any]], target: float) -> dict[str, Any]:
    eligible = [row for row in rows if row["relational_coverage"] + 1e-12 >= target]
    if not eligible:
        raise ValueError("no support rule reaches the pilot coverage target")
    return min(
        eligible,
        key=lambda row: (
            row["mean_candidate_edges"], row["radius_m"],
            row["maximum_motion_angle_degrees"],
        ),
    )


def frontier_metrics(
    snapshots: Sequence[dict[str, Any]], rule: dict[str, Any],
    thresholds: Sequence[float], certificate: dict[str, Any],
) -> dict[str, Any]:
    cells = []
    for snapshot in snapshots:
        edges = [
            (left, right, distance)
            for left, right, distance, heading in snapshot["pairs"]
            if distance <= rule["radius_m"]
            and heading <= rule["maximum_motion_angle_degrees"]
        ]
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
            flags = [not (lower.value >= t or upper.value < t) for t in thresholds]
            ambiguous = sum(flags)
            false_certificates = sum(
                (not flag)
                and ((lower.value >= threshold) != (snapshot["true_mean_distance_m"] >= threshold))
                for threshold, flag in zip(thresholds, flags)
            )
        cells.append({
            "snapshot_offset_seconds": snapshot["snapshot_offset_seconds"],
            "candidate_edge_count": len(edges), "true_world_representable": representable,
            "lower_status": lower.status, "upper_status": upper.status,
            "lower": lower.value, "upper": upper.value,
            "ambiguous_thresholds": ambiguous, "false_certificates": false_certificates,
        })
    exact_cells = [cell for cell in cells if cell["lower_status"] == cell["upper_status"] == OPTIMAL]
    closed = [cell for cell in cells if cell["lower_status"] == cell["upper_status"] and cell["lower_status"] in {OPTIMAL, "INFEASIBLE"}]
    return {
        "computationally_closed_cells": len(closed), "exact_cells": len(exact_cells),
        "infeasible_cells": len(cells) - len(exact_cells),
        "threshold_decisions": len(exact_cells) * len(thresholds),
        "ambiguous_threshold_decisions": sum(cell["ambiguous_thresholds"] for cell in exact_cells),
        "certified_threshold_decisions": sum(len(thresholds) - cell["ambiguous_thresholds"] for cell in exact_cells),
        "false_certificates": sum(cell["false_certificates"] for cell in exact_cells),
        "false_certificate_representable_cells": sum(
            bool(cell["false_certificates"]) and cell["true_world_representable"] for cell in exact_cells
        ),
        "cells": cells,
    }


def run(
    pilot_trajectory: Path, pilot_groups: Path,
    followup_trajectory: Path, followup_groups: Path,
    base_protocol_path: Path, calibration_protocol_path: Path, output: Path,
) -> dict[str, Any]:
    base_protocol = json.loads(base_protocol_path.read_text())
    protocol = json.loads(calibration_protocol_path.read_text())
    pilot, _ = prepared_snapshots(pilot_trajectory, pilot_groups, base_protocol)
    pilot_grid = grid_metrics(
        pilot, protocol["distance_radii_m"], protocol["maximum_motion_angle_degrees"]
    )
    selected = select_rule(pilot_grid, protocol["pilot_relational_coverage_target"])
    followup, _ = prepared_snapshots(followup_trajectory, followup_groups, base_protocol)
    followup_grid = grid_metrics(
        followup, protocol["distance_radii_m"], protocol["maximum_motion_angle_degrees"]
    )
    followup_selected = next(
        row for row in followup_grid
        if row["radius_m"] == selected["radius_m"]
        and row["maximum_motion_angle_degrees"] == selected["maximum_motion_angle_degrees"]
    )
    frontier = frontier_metrics(
        followup, selected, base_protocol["query"]["decision_thresholds_m"],
        base_protocol["certificate"],
    )
    status = "PASS" if (
        frontier["computationally_closed_cells"] == len(followup)
        and frontier["false_certificate_representable_cells"] == 0
    ) else "HOLD"
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "report_version": "atr-diamor-support-calibration-report/v1",
        "status": status, "claim_scope": protocol["claim_boundary"],
        "pilot_trajectory_sha256": sha(pilot_trajectory),
        "pilot_groups_sha256": sha(pilot_groups),
        "followup_trajectory_sha256": sha(followup_trajectory),
        "followup_groups_sha256": sha(followup_groups),
        "base_protocol_sha256": sha(base_protocol_path),
        "calibration_protocol_sha256": sha(calibration_protocol_path),
        "benchmark_sha256": sha(Path(__file__)),
        "pilot_eligible_snapshots": len(pilot),
        "followup_eligible_snapshots": len(followup),
        "selected_rule": selected,
        "followup_selected_rule": followup_selected,
        "followup_frontier": {key: value for key, value in frontier.items() if key != "cells"},
        "pilot_grid": pilot_grid, "followup_grid": followup_grid,
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
    parser.add_argument("--base-protocol", type=Path, default=Path(__file__).with_name("ATR_DIAMOR_DYAD_PROTOCOL.json"))
    parser.add_argument("--calibration-protocol", type=Path, default=Path(__file__).with_name("ATR_DIAMOR_SUPPORT_CALIBRATION_PROTOCOL.json"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = run(
        args.pilot_trajectory, args.pilot_groups, args.followup_trajectory,
        args.followup_groups, args.base_protocol, args.calibration_protocol, args.output,
    )
    print(json.dumps({key: value for key, value in report.items() if key != "cells"}, indent=2))
