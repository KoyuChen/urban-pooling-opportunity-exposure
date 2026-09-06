#!/usr/bin/env python3
"""Cross-day ATR multi-query audit with query-independent point matchings."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.optimize import minimize

import atr_diamor_dyad_truth as base


OPTIMAL = "NUMERICAL_MILP_OPTIMAL_REPLAYED"


@dataclass(frozen=True)
class LogisticModel:
    mean: tuple[float, float, float]
    scale: tuple[float, float, float]
    coefficients: tuple[float, float, float]
    intercept: float
    training_edges: int
    training_positives: int

    def logit(self, features: Sequence[float]) -> float:
        standardized = [
            (float(value) - mean) / scale
            for value, mean, scale in zip(features, self.mean, self.scale)
        ]
        return self.intercept + sum(c * x for c, x in zip(self.coefficients, standardized))


def edge_features(a: base.Observation, b: base.Observation) -> tuple[float, float, float]:
    return (
        math.hypot(a.x_m - b.x_m, a.y_m - b.y_m),
        math.degrees(base.angular_distance(a.motion_angle, b.motion_angle)),
        abs(a.speed_mps - b.speed_mps),
    )


def feature_edges(
    observations: Sequence[base.Observation], radius_m: float, max_angle_rad: float
) -> list[tuple[int, int, tuple[float, float, float]]]:
    result = []
    for left in range(len(observations)):
        for right in range(left + 1, len(observations)):
            features = edge_features(observations[left], observations[right])
            if features[0] <= radius_m and math.radians(features[1]) <= max_angle_rad:
                result.append((left, right, features))
    return result


def fit_logistic(features: Sequence[Sequence[float]], labels: Sequence[int], l2: float) -> LogisticModel:
    x = np.asarray(features, dtype=float)
    y = np.asarray(labels, dtype=float)
    if x.ndim != 2 or x.shape[1] != 3 or len(x) != len(y):
        raise ValueError("training features must be an n by 3 matrix")
    positives = int(y.sum())
    negatives = len(y) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("both edge classes are required")
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-12] = 1.0
    z = (x - mean) / scale
    weights = np.where(y > 0.5, len(y) / (2 * positives), len(y) / (2 * negatives))

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        logits = beta[0] + z @ beta[1:]
        loss = np.sum(weights * (np.logaddexp(0.0, logits) - y * logits))
        loss += 0.5 * l2 * float(beta[1:] @ beta[1:])
        probabilities = 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))
        residual = weights * (probabilities - y)
        gradient = np.concatenate(([residual.sum()], z.T @ residual + l2 * beta[1:]))
        return float(loss), gradient

    fitted = minimize(
        lambda beta: objective(beta)[0], np.zeros(4),
        jac=lambda beta: objective(beta)[1], method="L-BFGS-B",
        options={"ftol": 1e-12, "gtol": 1e-8, "maxiter": 1000},
    )
    if not fitted.success or not np.all(np.isfinite(fitted.x)):
        raise RuntimeError(f"logistic training failed: {fitted.message}")
    return LogisticModel(
        mean=tuple(float(v) for v in mean), scale=tuple(float(v) for v in scale),
        coefficients=tuple(float(v) for v in fitted.x[1:]), intercept=float(fitted.x[0]),
        training_edges=len(y), training_positives=positives,
    )


def training_examples(
    snapshots: Sequence[dict[int, base.Observation]],
    membership: dict[int, frozenset[int]], excluded_ids: set[int],
    radius_m: float, max_angle_rad: float, minimum_people: int,
) -> tuple[list[tuple[float, float, float]], list[int]]:
    features: list[tuple[float, float, float]] = []
    labels: list[int] = []
    for snapshot in snapshots:
        observations = sorted(
            (value for key, value in snapshot.items() if key not in excluded_ids),
            key=lambda value: value.pedestrian_id,
        )
        dyads = base.true_dyads(observations, membership)
        if len(observations) < minimum_people or not dyads:
            continue
        truth = {tuple(sorted(group)) for group in dyads}
        for left, right, values in feature_edges(observations, radius_m, max_angle_rad):
            features.append(values)
            pair = tuple(sorted((observations[left].pedestrian_id, observations[right].pedestrian_id)))
            labels.append(int(pair in truth))
    return features, labels


def query_weights(features: Sequence[float]) -> dict[str, float]:
    return {
        "distance_m": float(features[0]),
        "heading_gap_deg": float(features[1]),
        "speed_gap_mps": float(features[2]),
    }


def evaluate_day(
    trajectory: Path, groups: Path, base_protocol: dict[str, Any],
    multi_protocol: dict[str, Any], model: LogisticModel,
) -> dict[str, Any]:
    selection = base_protocol["selection"]
    candidate = base_protocol["candidate_support"]
    certificate = base_protocol["certificate"]
    grid = selection["snapshot_grid_seconds"]
    offsets = list(range(grid["start"], grid["stop_inclusive"] + 1, grid["step"]))
    parsed = base.parse_groups(groups)
    _, snapshots = base.load_snapshots(trajectory, offsets, selection["snapshot_half_width_seconds"])
    max_angle = math.radians(candidate["maximum_motion_angle_degrees"])
    cells: list[dict[str, Any]] = []
    for offset, snapshot in zip(offsets, snapshots):
        observations = sorted(
            (value for key, value in snapshot.items() if key not in parsed.excluded_ids),
            key=lambda value: value.pedestrian_id,
        )
        dyads = base.true_dyads(observations, parsed.membership)
        if len(observations) < selection["minimum_visible_people"] or not dyads:
            continue
        q = len(dyads)
        truth_ids = {tuple(sorted(group)) for group in dyads}
        id_index = {item.pedestrian_id: i for i, item in enumerate(observations)}
        truth_indices = {tuple(sorted((id_index[a], id_index[b]))) for a, b in truth_ids}
        truth_query = {name: 0.0 for name in multi_protocol["queries"]}
        for a, b in truth_ids:
            values = query_weights(edge_features(observations[id_index[a]], observations[id_index[b]]))
            for name in truth_query:
                truth_query[name] += values[name] / q
        for radius in candidate["distance_radii_m"]:
            featured = feature_edges(observations, radius, max_angle)
            pairs = [(left, right) for left, right, _ in featured]
            representable = truth_indices <= set(pairs)
            baseline_costs = {
                "closest_distance": [values[0] for _, _, values in featured],
                "motion_affinity": [
                    values[0] / radius + values[1] / candidate["maximum_motion_angle_degrees"]
                    + values[2] / multi_protocol["speed_gap_scale_mps"]
                    for _, _, values in featured
                ],
                "learned_diamor1": [-model.logit(values) for _, _, values in featured],
            }
            baseline_results = {}
            baseline_relation_recall = {}
            for name, costs in baseline_costs.items():
                result = base.solve_matching_endpoint(
                    len(observations),
                    [(left, right, cost) for (left, right), cost in zip(pairs, costs)],
                    q, False, certificate["solver_time_limit_seconds"],
                    certificate["solver_relative_gap"],
                )
                baseline_results[name] = result
                baseline_relation_recall[name] = (
                    sum(pairs[index] in truth_indices for index in result.selected) / q
                    if result.status == OPTIMAL else None
                )
            query_results: dict[str, Any] = {}
            for query_name, thresholds in multi_protocol["queries"].items():
                weights = [query_weights(values)[query_name] for _, _, values in featured]
                weighted_edges = [(left, right, weight) for (left, right), weight in zip(pairs, weights)]
                lower = base.solve_matching_endpoint(len(observations), weighted_edges, q, False)
                upper = base.solve_matching_endpoint(len(observations), weighted_edges, q, True)
                exact = lower.status == upper.status == OPTIMAL
                query_entry: dict[str, Any] = {
                    "lower_status": lower.status, "upper_status": upper.status,
                    "lower": lower.value, "upper": upper.value,
                    "width": upper.value - lower.value if exact else None,
                    "truth_value": truth_query[query_name],
                    "truth_covered": bool(exact and lower.value - 1e-8 <= truth_query[query_name] <= upper.value + 1e-8),
                    "ambiguous_thresholds": None,
                    "baselines": {},
                }
                if exact:
                    flags = [not (lower.value >= t or upper.value < t) for t in thresholds]
                    query_entry["ambiguous_thresholds"] = sum(flags)
                    for baseline_name, result in baseline_results.items():
                        if result.status != OPTIMAL:
                            query_entry["baselines"][baseline_name] = {"status": result.status}
                            continue
                        point = sum(weights[index] for index in result.selected) / q
                        errors = [(point >= t) != (truth_query[query_name] >= t) for t in thresholds]
                        query_entry["baselines"][baseline_name] = {
                            "status": OPTIMAL, "point": point,
                            "threshold_errors": sum(errors),
                            "errors_flagged": sum(error and flag for error, flag in zip(errors, flags)),
                        }
                query_results[query_name] = query_entry
            cells.append({
                "snapshot_offset_seconds": offset, "radius_m": radius,
                "visible_people": len(observations), "true_dyad_count": q,
                "candidate_edge_count": len(featured),
                "true_world_representable": representable, "queries": query_results,
                "baseline_relation_recall": baseline_relation_recall,
            })
    return {"cells": cells, "excluded_or_quarantined_member_count": len(parsed.excluded_ids)}


def summarize_day(cells: Sequence[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for query_name, thresholds in protocol["queries"].items():
        exact = [c for c in cells if c["queries"][query_name]["lower_status"] == c["queries"][query_name]["upper_status"] == OPTIMAL]
        representable = [c for c in exact if c["true_world_representable"]]
        query_summary: dict[str, Any] = {
            "exact_cells": len(exact), "representable_exact_cells": len(representable),
            "truth_covered_representable_cells": sum(c["queries"][query_name]["truth_covered"] for c in representable),
            "ambiguous_threshold_decisions": sum(c["queries"][query_name]["ambiguous_thresholds"] for c in exact),
            "threshold_decisions": len(exact) * len(thresholds), "baselines": {},
        }
        for baseline in protocol["point_baselines"]:
            entries = [c["queries"][query_name]["baselines"].get(baseline, {}) for c in representable]
            valid = [entry for entry in entries if entry.get("status") == OPTIMAL]
            query_summary["baselines"][baseline] = {
                "evaluated_cells": len(valid),
                "threshold_errors": sum(entry["threshold_errors"] for entry in valid),
                "errors_flagged": sum(entry["errors_flagged"] for entry in valid),
                "mean_relation_recall": float(np.mean([
                    c["baseline_relation_recall"][baseline]
                    for c in representable
                    if c["baseline_relation_recall"][baseline] is not None
                ])),
            }
        result[query_name] = query_summary
    return result


def run(
    training_trajectory: Path, training_groups: Path,
    evaluation_trajectory: Path, evaluation_groups: Path,
    base_protocol_path: Path, multi_protocol_path: Path, output: Path,
) -> dict[str, Any]:
    base_protocol = json.loads(base_protocol_path.read_text())
    protocol = json.loads(multi_protocol_path.read_text())
    selection = base_protocol["selection"]
    grid = selection["snapshot_grid_seconds"]
    offsets = list(range(grid["start"], grid["stop_inclusive"] + 1, grid["step"]))
    parsed = base.parse_groups(training_groups)
    _, training_snapshots = base.load_snapshots(
        training_trajectory, offsets, selection["snapshot_half_width_seconds"]
    )
    features, labels = training_examples(
        training_snapshots, parsed.membership, set(parsed.excluded_ids),
        protocol["training_candidate_radius_m"],
        math.radians(base_protocol["candidate_support"]["maximum_motion_angle_degrees"]),
        selection["minimum_visible_people"],
    )
    model = fit_logistic(features, labels, protocol["logistic_l2"])
    evaluation = evaluate_day(
        evaluation_trajectory, evaluation_groups, base_protocol, protocol, model
    )
    summary = summarize_day(evaluation["cells"], protocol)
    status = "PASS" if evaluation["cells"] and all(
        item["exact_cells"] + sum(
            c["queries"][name]["lower_status"] == c["queries"][name]["upper_status"] == "INFEASIBLE"
            for c in evaluation["cells"]
        ) == len(evaluation["cells"])
        for name, item in summary.items()
    ) else "HOLD"
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = {
        "report_version": "atr-diamor-multiquery-report/v1", "status": status,
        "training_day": "DIAMOR-1", "evaluation_day": "DIAMOR-2",
        "claim_scope": protocol["claim_boundary"],
        "training_trajectory_sha256": sha(training_trajectory),
        "training_groups_sha256": sha(training_groups),
        "evaluation_trajectory_sha256": sha(evaluation_trajectory),
        "evaluation_groups_sha256": sha(evaluation_groups),
        "base_protocol_sha256": sha(base_protocol_path),
        "multiquery_protocol_sha256": sha(multi_protocol_path),
        "benchmark_sha256": sha(Path(__file__)),
        "model": model.__dict__, "evaluation_cell_count": len(evaluation["cells"]),
        "summary": summary, "cells": evaluation["cells"],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "RUN_MANIFEST.json").write_text(json.dumps({k: v for k, v in report.items() if k != "cells"}, indent=2) + "\n")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-trajectory", type=Path, required=True)
    parser.add_argument("--training-groups", type=Path, required=True)
    parser.add_argument("--evaluation-trajectory", type=Path, required=True)
    parser.add_argument("--evaluation-groups", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-protocol", type=Path, default=Path(__file__).with_name("ATR_DIAMOR_DYAD_PROTOCOL.json"))
    parser.add_argument("--multiquery-protocol", type=Path, default=Path(__file__).with_name("ATR_DIAMOR_MULTIQUERY_PROTOCOL.json"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = run(args.training_trajectory, args.training_groups, args.evaluation_trajectory, args.evaluation_groups, args.base_protocol, args.multiquery_protocol, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "cells"}, indent=2))
