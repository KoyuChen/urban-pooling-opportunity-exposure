#!/usr/bin/env python3
"""Diagnose alternating structures sustaining frozen ATR frontier width."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

import atr_diamor_dyad_truth as base
import atr_diamor_density_cap as density
import atr_diamor_support_calibration as support


OPTIMAL = "NUMERICAL_MILP_OPTIMAL_REPLAYED"


def symmetric_difference_components(
    lower_edges: set[tuple[int, int]], upper_edges: set[tuple[int, int]]
) -> list[dict[str, Any]]:
    colored = [(edge, "lower") for edge in lower_edges - upper_edges]
    colored += [(edge, "upper") for edge in upper_edges - lower_edges]
    adjacency: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for (left, right), color in colored:
        adjacency[left].append((right, color))
        adjacency[right].append((left, color))
    unseen = set(adjacency)
    components = []
    while unseen:
        seed = min(unseen)
        stack = [seed]
        vertices = set()
        while stack:
            node = stack.pop()
            if node in vertices:
                continue
            vertices.add(node)
            stack.extend(neighbor for neighbor, _ in adjacency[node])
        unseen -= vertices
        edge_set = {
            (min(node, neighbor), max(node, neighbor), color)
            for node in vertices for neighbor, color in adjacency[node]
            if node < neighbor
        }
        degrees = [len(adjacency[node]) for node in vertices]
        component_type = "cycle" if degrees and all(value == 2 for value in degrees) else "path"
        components.append({
            "type": component_type,
            "vertex_count": len(vertices),
            "edge_count": len(edge_set),
            "lower_edge_count": sum(color == "lower" for _, _, color in edge_set),
            "upper_edge_count": sum(color == "upper" for _, _, color in edge_set),
        })
    return sorted(components, key=lambda item: (-item["edge_count"], item["type"]))


def graph_edges(snapshot: dict[str, Any], rule: dict[str, Any], cap: int | None) -> list[tuple[int, int, float]]:
    if cap is not None:
        return density.capped_edges(snapshot, rule, cap)
    return [
        (left, right, distance)
        for left, right, distance, heading in snapshot["pairs"]
        if distance <= rule["radius_m"] and heading <= rule["maximum_motion_angle_degrees"]
    ]


def diagnose_graph(
    snapshots: Sequence[dict[str, Any]], rule: dict[str, Any], cap: int | None,
    thresholds: Sequence[float], certificate: dict[str, Any],
) -> dict[str, Any]:
    cells = []
    for snapshot in snapshots:
        edges = graph_edges(snapshot, rule, cap)
        lower = base.solve_matching_endpoint(
            len(snapshot["observations"]), edges, snapshot["true_q"], False,
            certificate["solver_time_limit_seconds"], certificate["solver_relative_gap"],
        )
        upper = base.solve_matching_endpoint(
            len(snapshot["observations"]), edges, snapshot["true_q"], True,
            certificate["solver_time_limit_seconds"], certificate["solver_relative_gap"],
        )
        exact = lower.status == upper.status == OPTIMAL
        components = []
        ambiguous = None
        if exact:
            lower_pairs = {(edges[index][0], edges[index][1]) for index in lower.selected}
            upper_pairs = {(edges[index][0], edges[index][1]) for index in upper.selected}
            components = symmetric_difference_components(lower_pairs, upper_pairs)
            ambiguous = sum(not (lower.value >= value or upper.value < value) for value in thresholds)
        cells.append({
            "snapshot_offset_seconds": snapshot["snapshot_offset_seconds"],
            "candidate_edge_count": len(edges),
            "lower_status": lower.status,
            "upper_status": upper.status,
            "lower": lower.value,
            "upper": upper.value,
            "width": None if not exact else upper.value - lower.value,
            "ambiguous_thresholds": ambiguous,
            "component_count": len(components),
            "alternating_components": components,
        })
    exact_cells = [cell for cell in cells if cell["lower_status"] == cell["upper_status"] == OPTIMAL]
    type_counts = Counter(
        component["type"] for cell in exact_cells for component in cell["alternating_components"]
    )
    differing = [cell for cell in exact_cells if cell["component_count"]]
    ambiguous_cells = [cell for cell in exact_cells if cell["ambiguous_thresholds"]]
    return {
        "exact_cells": len(exact_cells),
        "mean_frontier_width": sum(cell["width"] for cell in exact_cells) / len(exact_cells),
        "positive_width_cells": sum(cell["width"] > 1e-12 for cell in exact_cells),
        "ambiguous_snapshot_count": len(ambiguous_cells),
        "distinct_endpoint_witness_cells": len(differing),
        "multi_component_cells": sum(cell["component_count"] > 1 for cell in differing),
        "path_component_count": type_counts["path"],
        "cycle_component_count": type_counts["cycle"],
        "component_edge_count_distribution": dict(sorted(Counter(
            component["edge_count"]
            for cell in differing for component in cell["alternating_components"]
        ).items())),
        "maximum_component_edges": max(
            (component["edge_count"] for cell in differing for component in cell["alternating_components"]),
            default=0,
        ),
        "cells": cells,
    }


def run(
    trajectory: Path, groups: Path, base_protocol_path: Path, diagnostic_protocol_path: Path,
    support_summary_path: Path, density_summary_path: Path, output: Path,
) -> dict[str, Any]:
    base_protocol = json.loads(base_protocol_path.read_text())
    protocol = json.loads(diagnostic_protocol_path.read_text())
    support_summary = json.loads(support_summary_path.read_text())
    density_summary = json.loads(density_summary_path.read_text())
    snapshots, _ = support.prepared_snapshots(trajectory, groups, base_protocol)
    rule = support_summary["selected_rule"]
    cap = density_summary["selected_cap"]["degree_cap"]
    thresholds = base_protocol["query"]["decision_thresholds_m"]
    certificate = base_protocol["certificate"]
    fixed = diagnose_graph(snapshots, rule, None, thresholds, certificate)
    capped = diagnose_graph(snapshots, rule, cap, thresholds, certificate)
    fixed_by_offset = {cell["snapshot_offset_seconds"]: cell for cell in fixed["cells"]}
    capped_by_offset = {cell["snapshot_offset_seconds"]: cell for cell in capped["cells"]}
    comparable = [
        offset for offset in fixed_by_offset
        if fixed_by_offset[offset]["lower_status"] == fixed_by_offset[offset]["upper_status"] == OPTIMAL
        and capped_by_offset[offset]["lower_status"] == capped_by_offset[offset]["upper_status"] == OPTIMAL
    ]
    upper_contractions = [
        fixed_by_offset[offset]["upper"] - capped_by_offset[offset]["upper"]
        for offset in comparable
        if fixed_by_offset[offset]["upper"] - capped_by_offset[offset]["upper"] > 1e-10
    ]
    comparison = {
        "comparable_exact_cells": len(comparable),
        "identical_lower_endpoint_cells": sum(
            abs(fixed_by_offset[o]["lower"] - capped_by_offset[o]["lower"]) <= 1e-10 for o in comparable
        ),
        "identical_upper_endpoint_cells": sum(
            abs(fixed_by_offset[o]["upper"] - capped_by_offset[o]["upper"]) <= 1e-10 for o in comparable
        ),
        "identical_ambiguity_count_cells": sum(
            fixed_by_offset[o]["ambiguous_thresholds"] == capped_by_offset[o]["ambiguous_thresholds"] for o in comparable
        ),
        "contracted_upper_endpoint_cells": len(upper_contractions),
        "mean_upper_contraction_among_changed": (
            sum(upper_contractions) / len(upper_contractions) if upper_contractions else 0.0
        ),
        "maximum_upper_contraction": max(upper_contractions, default=0.0),
    }
    status = "PASS" if len(comparable) == len(snapshots) else "HOLD"
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "report_version": "atr-diamor-alternating-structure-report/v1",
        "status": status,
        "claim_scope": protocol["claim_boundary"],
        "trajectory_sha256": sha(trajectory),
        "groups_sha256": sha(groups),
        "base_protocol_sha256": sha(base_protocol_path),
        "diagnostic_protocol_sha256": sha(diagnostic_protocol_path),
        "support_summary_sha256": sha(support_summary_path),
        "density_summary_sha256": sha(density_summary_path),
        "benchmark_sha256": sha(Path(__file__)),
        "eligible_snapshots": len(snapshots),
        "fixed": {key: value for key, value in fixed.items() if key != "cells"},
        "capped": {key: value for key, value in capped.items() if key != "cells"},
        "comparison": comparison,
        "fixed_cells": fixed["cells"],
        "capped_cells": capped["cells"],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    public = {key: value for key, value in report.items() if key not in {"fixed_cells", "capped_cells"}}
    (output / "RUN_MANIFEST.json").write_text(json.dumps(public, indent=2) + "\n")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    here = Path(__file__).parent
    parser.add_argument("--base-protocol", type=Path, default=here / "ATR_DIAMOR_DYAD_PROTOCOL.json")
    parser.add_argument("--diagnostic-protocol", type=Path, default=here / "ATR_DIAMOR_ALTERNATING_STRUCTURE_PROTOCOL.json")
    parser.add_argument("--support-summary", type=Path, default=here / "results/atr_diamor_support_calibration/SUMMARY.json")
    parser.add_argument("--density-summary", type=Path, default=here / "results/atr_diamor_density_cap/SUMMARY.json")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(
        args.trajectory, args.groups, args.base_protocol, args.diagnostic_protocol,
        args.support_summary, args.density_summary, args.output,
    )
    print(json.dumps({key: value for key, value in result.items() if key not in {"fixed_cells", "capped_cells"}}, indent=2))
