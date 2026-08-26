#!/usr/bin/env python3
"""Run the known-truth integration benchmark for the urban pooling AI pilot.

The benchmark deliberately uses synthetic Chicago-coordinate records because a
live complete-day Socrata extract was unavailable in this execution
environment.  It exercises the real candidate builder, weak node-label MIL
model, and set-packing bounds without exposing hidden pairs to fitting.

All design parameters live in ``DESIGN_LOCK.json`` and are read, not tuned, by
this script.  The second synthetic day is the sole held-out day.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/urban_pooling_ai_mplconfig")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


INTEGRATION_DIR = Path(__file__).resolve().parent
AI_PILOT_DIR = INTEGRATION_DIR.parent
if str(AI_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(AI_PILOT_DIR))

from bounds.set_packing_bounds import solve_bounds  # noqa: E402
from model.run_weak_edge_pilot import build_parser as build_model_parser  # noqa: E402
from model.run_weak_edge_pilot import run as run_weak_mil  # noqa: E402


CORRIDORS = (
    ((41.8820, -87.6270), (41.9005, -87.6350), 8, 8),
    ((41.9000, -87.6350), (41.9415, -87.6495), 8, 6),
    ((41.8785, -87.6500), (41.8520, -87.6505), 28, 60),
    ((41.8500, -87.6460), (41.7950, -87.5900), 60, 41),
    ((41.9390, -87.6530), (41.9690, -87.7580), 6, 11),
    ((41.7940, -87.5900), (41.7500, -87.6250), 41, 69),
    ((41.9690, -87.7580), (41.9210, -87.7040), 11, 15),
    ((41.7510, -87.6250), (41.8100, -87.7050), 69, 66),
)
INCOME_BY_BIN = {0: 35_000, 1: 48_000, 2: 65_000, 3: 87_000, 4: 122_000}
BIN_OFFSETS_KM = {
    0: (-0.28, -0.12),
    1: (0.18, -0.24),
    2: (0.00, 0.00),
    3: (-0.16, 0.25),
    4: (0.29, 0.12),
}


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON encode {type(value)!r}")


def _round_timestamp(timestamp: pd.Timestamp, minutes: int) -> pd.Timestamp:
    return timestamp.round(f"{minutes}min")


def _offset_latlon(lat: float, lon: float, east_km: float, north_km: float) -> tuple[float, float]:
    return (
        lat + north_km / 110.574,
        lon + east_km / (111.320 * math.cos(math.radians(lat))),
    )


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0088
    phi_a = math.radians(a_lat)
    phi_b = math.radians(b_lat)
    d_phi = phi_b - phi_a
    d_lambda = math.radians(b_lon - a_lon)
    hav = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(hav))


def _coordinate(
    rng: np.random.Generator,
    center: tuple[float, float],
    income_bin: int,
    common_jitter_km: tuple[float, float],
    individual_sd_km: float,
) -> tuple[float, float]:
    base_east, base_north = BIN_OFFSETS_KM[income_bin]
    east = base_east + common_jitter_km[0] + rng.normal(0, individual_sd_km)
    north = base_north + common_jitter_km[1] + rng.normal(0, individual_sd_km)
    return _offset_latlon(center[0], center[1], east, north)


def _record(
    *,
    trip_id: str,
    actual_start: pd.Timestamp,
    pickup: tuple[float, float],
    dropoff: tuple[float, float],
    duration_minutes: float,
    miles: float,
    matched: bool,
    pickup_area: int,
    dropoff_area: int,
    pickup_tract: int,
    dropoff_tract: int,
    coarsening_minutes: int,
) -> dict:
    duration_seconds = int(round(max(duration_minutes, 4.0) * 60))
    public_start = _round_timestamp(actual_start, coarsening_minutes)
    public_end = _round_timestamp(
        actual_start + pd.to_timedelta(duration_seconds, unit="s"), coarsening_minutes
    )
    fare = 3.25 + 1.28 * miles + 0.22 * duration_minutes
    return {
        "trip_id": trip_id,
        "trip_start_timestamp": public_start.strftime("%Y-%m-%d %H:%M:%S"),
        "trip_end_timestamp": public_end.strftime("%Y-%m-%d %H:%M:%S"),
        "trip_seconds": duration_seconds,
        "trip_miles": round(max(miles, 0.4), 3),
        "pickup_centroid_latitude": round(pickup[0], 6),
        "pickup_centroid_longitude": round(pickup[1], 6),
        "dropoff_centroid_latitude": round(dropoff[0], 6),
        "dropoff_centroid_longitude": round(dropoff[1], 6),
        "pickup_community_area": pickup_area,
        "dropoff_community_area": dropoff_area,
        "pickup_census_tract": pickup_tract,
        "dropoff_census_tract": dropoff_tract,
        "shared_trip_authorized": True,
        "shared_trip_match": matched,
        "trips_pooled": 2 if matched else 1,
        "fare": round(fare, 2),
        "trip_total": round(fare + 4.25, 2),
        "synthetic_data_warning": "SIMULATED; not a City of Chicago observation",
    }


def generate_day(
    day: str,
    day_index: int,
    rng: np.random.Generator,
    market: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    waves = int(market["route_waves"])
    pairs_per_wave = int(market["hidden_true_pairs_per_wave"])
    unmatched_per_wave = int(market["unmatched_authorized_trips_per_wave"])
    same_probability = float(market["same_income_bin_pair_probability"])
    coarsening = int(market["timestamp_coarsening_minutes"])
    records: list[dict] = []
    node_truth: list[dict] = []
    pair_truth: list[dict] = []
    day_start = pd.Timestamp(day)

    for wave in range(waves):
        corridor_id = (wave + 2 * day_index) % len(CORRIDORS)
        pickup_center, dropoff_center, pickup_area, dropoff_area = CORRIDORS[corridor_id]
        hour_offset = 6 * 60 + wave * 43 + int(rng.integers(-4, 5))
        wave_start = day_start + pd.to_timedelta(hour_offset, unit="m")
        route_km = _haversine_km(*pickup_center, *dropoff_center) * 1.22
        route_miles = route_km * 0.621371
        base_duration = 7.0 + 3.15 * route_miles

        for pair_index in range(pairs_per_wave):
            pair_id = f"{day}:pair:{wave:02d}:{pair_index:02d}"
            first_bin = int(rng.integers(0, 5))
            if rng.random() < same_probability:
                second_bin = first_bin
            else:
                choices = [value for value in range(5) if value != first_bin]
                second_bin = int(rng.choice(choices))
            bins = (first_bin, second_bin)
            pickup_common = (rng.normal(0, 0.42), rng.normal(0, 0.42))
            dropoff_common = (rng.normal(0, 0.58), rng.normal(0, 0.58))
            pair_start = wave_start + pd.to_timedelta(
                pair_index * 2.2 + rng.normal(0, 1.1), unit="m"
            )
            shared_duration = base_duration * rng.lognormal(0.0, 0.055)
            shared_miles = route_miles * rng.lognormal(0.0, 0.045)
            trip_ids: list[str] = []
            for member, income_bin in enumerate(bins):
                trip_id = f"syn-{day_index}-{wave:02d}-p{pair_index:02d}-{member}"
                trip_ids.append(trip_id)
                pickup = _coordinate(rng, pickup_center, income_bin, pickup_common, 0.055)
                destination_bin = (income_bin + corridor_id + 1) % 5
                dropoff = _coordinate(rng, dropoff_center, destination_bin, dropoff_common, 0.075)
                actual_start = pair_start + pd.to_timedelta(rng.normal(0, 1.15), unit="m")
                duration = shared_duration * rng.lognormal(0.0, 0.035)
                miles = shared_miles * rng.lognormal(0.0, 0.03)
                pickup_tract = 17031000000 + corridor_id * 100 + income_bin
                dropoff_tract = 17031900000 + corridor_id * 100 + destination_bin
                records.append(
                    _record(
                        trip_id=trip_id,
                        actual_start=actual_start,
                        pickup=pickup,
                        dropoff=dropoff,
                        duration_minutes=duration,
                        miles=miles,
                        matched=True,
                        pickup_area=pickup_area,
                        dropoff_area=dropoff_area,
                        pickup_tract=pickup_tract,
                        dropoff_tract=dropoff_tract,
                        coarsening_minutes=coarsening,
                    )
                )
                node_truth.append(
                    {
                        "trip_id": trip_id,
                        "event_day": day,
                        "hidden_pair_id": pair_id,
                        "income_bin": income_bin,
                        "tract_median_income": INCOME_BY_BIN[income_bin],
                        "matched_truth": True,
                    }
                )
            pair_truth.append(
                {
                    "event_day": day,
                    "hidden_pair_id": pair_id,
                    "trip_id_a": trip_ids[0],
                    "trip_id_b": trip_ids[1],
                    "income_bin_a": first_bin,
                    "income_bin_b": second_bin,
                    "same_income_bin": first_bin == second_bin,
                }
            )

        duration_factors = np.array([0.48, 0.78, 1.42, 2.05], dtype=float)
        mileage_factors = np.array([1.55, 0.72, 1.25, 0.62], dtype=float)
        if unmatched_per_wave != 4:
            duration_factors = np.linspace(0.5, 2.0, unmatched_per_wave)
            mileage_factors = np.linspace(1.5, 0.65, unmatched_per_wave)
        unmatched_common_pickup = (1.18 + rng.normal(0, 0.08), rng.normal(0, 0.16))
        unmatched_common_dropoff = (1.35 + rng.normal(0, 0.12), rng.normal(0, 0.20))
        for unmatched_index in range(unmatched_per_wave):
            income_bin = int((wave + unmatched_index + day_index) % 5)
            destination_bin = int((income_bin + corridor_id + 2) % 5)
            trip_id = f"syn-{day_index}-{wave:02d}-u{unmatched_index:02d}"
            pickup = _coordinate(rng, pickup_center, income_bin, unmatched_common_pickup, 0.04)
            dropoff = _coordinate(rng, dropoff_center, destination_bin, unmatched_common_dropoff, 0.055)
            actual_start = wave_start + pd.to_timedelta(
                unmatched_index * 0.7 + rng.normal(0, 0.75), unit="m"
            )
            duration = base_duration * float(duration_factors[unmatched_index]) * rng.lognormal(0, 0.025)
            miles = route_miles * float(mileage_factors[unmatched_index]) * rng.lognormal(0, 0.025)
            pickup_tract = 17031000000 + corridor_id * 100 + income_bin
            dropoff_tract = 17031900000 + corridor_id * 100 + destination_bin
            records.append(
                _record(
                    trip_id=trip_id,
                    actual_start=actual_start,
                    pickup=pickup,
                    dropoff=dropoff,
                    duration_minutes=duration,
                    miles=miles,
                    matched=False,
                    pickup_area=pickup_area,
                    dropoff_area=dropoff_area,
                    pickup_tract=pickup_tract,
                    dropoff_tract=dropoff_tract,
                    coarsening_minutes=coarsening,
                )
            )
            node_truth.append(
                {
                    "trip_id": trip_id,
                    "event_day": day,
                    "hidden_pair_id": "",
                    "income_bin": income_bin,
                    "tract_median_income": INCOME_BY_BIN[income_bin],
                    "matched_truth": False,
                }
            )

    public = pd.DataFrame(records).sort_values(["trip_start_timestamp", "trip_id"]).reset_index(drop=True)
    return public, pd.DataFrame(node_truth), pd.DataFrame(pair_truth)


def _edge_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def edge_recovery_metrics(
    edges: pd.DataFrame,
    node_predictions: pd.DataFrame,
    pairs: pd.DataFrame,
    held_out_day: str,
) -> tuple[dict, pd.DataFrame]:
    node_to_trip = node_predictions.set_index("node_id")["trip_id"].astype(str).to_dict()
    held_edges = edges.loc[edges["event_day"].eq(held_out_day)].copy()
    held_edges["trip_u"] = held_edges["src"].map(node_to_trip)
    held_edges["trip_v"] = held_edges["dst"].map(node_to_trip)
    held_edges["pair_key"] = [
        _edge_key(str(a), str(b)) for a, b in zip(held_edges["trip_u"], held_edges["trip_v"])
    ]
    edge_by_key = {
        row.pair_key: row
        for row in held_edges.itertuples(index=False)
    }
    held_pairs = pairs.loc[pairs["event_day"].eq(held_out_day)].copy()
    held_pairs["pair_key"] = [
        _edge_key(str(a), str(b)) for a, b in zip(held_pairs["trip_id_a"], held_pairs["trip_id_b"])
    ]
    held_pairs["candidate_present"] = held_pairs["pair_key"].isin(set(edge_by_key))

    rank_rows: list[dict] = []
    adjacency: dict[str, list[int]] = {}
    for edge_index, row in held_edges.reset_index(drop=True).iterrows():
        adjacency.setdefault(str(row["trip_u"]), []).append(edge_index)
        adjacency.setdefault(str(row["trip_v"]), []).append(edge_index)
    ranked_edges = held_edges.reset_index(drop=True)
    for pair in held_pairs.itertuples(index=False):
        if not pair.candidate_present:
            continue
        truth_key = pair.pair_key
        truth_row = edge_by_key[truth_key]
        for endpoint in (pair.trip_id_a, pair.trip_id_b):
            incident = ranked_edges.iloc[adjacency.get(str(endpoint), [])]
            for label, score_column in (
                ("transparent_rule", "p_rule_edge"),
                ("weak_mil_ai", "p_ai_edge"),
            ):
                truth_score = float(getattr(truth_row, score_column))
                scores = incident[score_column].to_numpy(dtype=float)
                rank = 1 + int(np.sum(scores > truth_score + 1e-12))
                rank_rows.append(
                    {
                        "hidden_pair_id": pair.hidden_pair_id,
                        "endpoint_trip_id": endpoint,
                        "model": label,
                        "rank": rank,
                        "reciprocal_rank": 1.0 / rank,
                        "candidate_degree": int(len(incident)),
                        "truth_edge_score": truth_score,
                    }
                )
    ranks = pd.DataFrame(rank_rows)
    summaries = {}
    for model, group in ranks.groupby("model"):
        summaries[model] = {
            "ranked_endpoint_count": int(len(group)),
            "mean_reciprocal_rank": float(group["reciprocal_rank"].mean()),
            "top_1_rate": float(group["rank"].eq(1).mean()),
            "top_3_rate": float(group["rank"].le(3).mean()),
            "median_rank": float(group["rank"].median()),
        }
    metrics = {
        "held_out_day": held_out_day,
        "hidden_true_pair_count": int(len(held_pairs)),
        "candidate_recalled_true_pair_count": int(held_pairs["candidate_present"].sum()),
        "candidate_true_edge_recall": float(held_pairs["candidate_present"].mean()),
        "ranking_conditional_on_candidate_recall": summaries,
    }
    return metrics, ranks


def run_bounds(
    edges: pd.DataFrame,
    node_predictions: pd.DataFrame,
    node_truth: pd.DataFrame,
    pair_truth: pd.DataFrame,
    held_out_day: str,
    bound_config: dict,
) -> tuple[dict, pd.DataFrame]:
    held_nodes = node_predictions.loc[node_predictions["event_day"].eq(held_out_day)].copy()
    held_nodes = held_nodes.merge(
        node_truth[["trip_id", "income_bin", "tract_median_income", "matched_truth"]],
        on="trip_id",
        how="left",
        validate="one_to_one",
    )
    held_nodes["node_id"] = held_nodes["node_id"].astype(str)
    held_nodes["ses_bin"] = held_nodes["income_bin"].astype(int)
    held_nodes["ses_value"] = np.log(held_nodes["tract_median_income"].astype(float))
    held_nodes["matched"] = held_nodes["matched_truth"].astype(bool)

    held_edges = edges.loc[edges["event_day"].eq(held_out_day)].copy()
    held_edges["u"] = held_edges["src"].astype(str)
    held_edges["v"] = held_edges["dst"].astype(str)
    held_edges["edge_id"] = held_edges["edge_id"].astype(str)

    held_pairs = pair_truth.loc[pair_truth["event_day"].eq(held_out_day)].copy()
    truth_value = float(held_pairs["same_income_bin"].astype(float).mean())
    trip_to_node = held_nodes.set_index("trip_id")["node_id"].to_dict()
    truth_edge_ids = []
    edge_lookup = {
        tuple(sorted((str(row.src), str(row.dst)))): str(row.edge_id)
        for row in held_edges.itertuples(index=False)
    }
    for pair in held_pairs.itertuples(index=False):
        key = tuple(sorted((str(trip_to_node[pair.trip_id_a]), str(trip_to_node[pair.trip_id_b]))))
        truth_edge_ids.append(edge_lookup.get(key))
    truth_graph_complete = all(edge_id is not None for edge_id in truth_edge_ids)

    result_rows: list[dict] = []
    result_objects: dict[str, dict] = {}
    scenarios = [("untrimmed_candidate_graph", "p_ai_edge", None)]
    for retention in bound_config["score_retentions"]:
        scenarios.extend(
            [
                (f"transparent_rule_retention_{retention:.2f}", "p_rule_edge", float(retention)),
                (f"weak_mil_ai_retention_{retention:.2f}", "p_ai_edge", float(retention)),
            ]
        )

    for scenario, score_column, retention in scenarios:
        edge_problem = held_edges[["u", "v", "edge_id", score_column]].rename(
            columns={score_column: "edge_score"}
        )
        bounds = solve_bounds(
            held_nodes[["node_id", "matched", "ses_bin", "ses_value"]],
            edge_problem,
            metric="same_bin",
            matched_col="matched",
            score_retention=retention,
            backend=str(bound_config["backend"]),
            time_limit=float(bound_config["time_limit_seconds"]),
        )
        truth_score_ratio = None
        truth_score_eligible = truth_graph_complete
        if truth_graph_complete and bounds.score_optimum is not None:
            by_id = edge_problem.set_index("edge_id")["edge_score"]
            truth_score = float(by_id.loc[truth_edge_ids].sum())
            truth_score_ratio = truth_score / bounds.score_optimum if bounds.score_optimum > 0 else 1.0
            if retention is not None:
                truth_score_eligible = truth_score_ratio + 1e-12 >= retention
        covers_truth = bool(
            bounds.feasible
            and bounds.lower is not None
            and bounds.upper is not None
            and bounds.lower - 1e-12 <= truth_value <= bounds.upper + 1e-12
        )
        row = {
            "scenario": scenario,
            "score_column": score_column,
            "score_retention": retention,
            "feasible": bounds.feasible,
            "lower": bounds.lower,
            "upper": bounds.upper,
            "width": bounds.width,
            "truth_same_income_bin_share": truth_value,
            "covers_truth": covers_truth,
            "truth_graph_complete": truth_graph_complete,
            "truth_score_ratio_to_optimum": truth_score_ratio,
            "truth_score_eligible": truth_score_eligible,
            "candidate_edge_count": bounds.candidate_edge_count,
            "required_node_count": bounds.required_node_count,
            "selected_edge_count": bounds.selected_edge_count,
        }
        result_rows.append(row)
        result_objects[scenario] = {**bounds.to_dict(), **row}

    raw_width = result_rows[0]["width"]
    for row in result_rows:
        row["width_reduction_vs_untrimmed"] = (
            (raw_width - row["width"]) / raw_width
            if raw_width not in (None, 0) and row["width"] is not None
            else None
        )
        result_objects[row["scenario"]]["width_reduction_vs_untrimmed"] = row[
            "width_reduction_vs_untrimmed"
        ]
    result_frame = pd.DataFrame(result_rows)
    return (
        {
            "held_out_day": held_out_day,
            "estimand": "share of selected pairs in the same synthetic pickup-income bin",
            "truth_same_income_bin_share": truth_value,
            "truth_pair_count": int(len(held_pairs)),
            "truth_candidate_graph_complete": truth_graph_complete,
            "scenarios": result_objects,
        },
        result_frame,
    )


def make_figure(metrics: pd.DataFrame, bound_rows: pd.DataFrame, output: Path) -> None:
    held = metrics.loc[metrics["subset"].eq("test_supported")].set_index("model")
    labels = ["Transparent rule", "Weak-MIL AI"]
    briers = [
        float(held.loc["transparent_rule", "brier"]),
        float(held.loc["weak_mil_ai", "brier"]),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4), constrained_layout=True)
    colors = ["#8C8C8C", "#2F6B9A"]
    axes[0].bar(labels, briers, color=colors, width=0.64)
    axes[0].set_ylabel("Held-out node Brier score (lower is better)")
    axes[0].set_title("Node-level benchmark")
    axes[0].grid(axis="y", alpha=0.25)
    for index, value in enumerate(briers):
        axes[0].text(index, value, f"{value:.3f}", ha="center", va="bottom", fontsize=9)

    scenario_labels = {
        "untrimmed_candidate_graph": "Untrimmed",
        "transparent_rule_retention_0.90": "Rule 90%",
        "weak_mil_ai_retention_0.90": "AI 90%",
        "transparent_rule_retention_0.95": "Rule 95%",
        "weak_mil_ai_retention_0.95": "AI 95%",
    }
    ordered = bound_rows.loc[bound_rows["scenario"].isin(scenario_labels)].copy()
    ordered["order"] = ordered["scenario"].map({name: i for i, name in enumerate(scenario_labels)})
    ordered = ordered.sort_values("order")
    for y, row in enumerate(ordered.itertuples(index=False)):
        if row.feasible:
            axes[1].plot([row.lower, row.upper], [y, y], color="#2F6B9A", linewidth=5, solid_capstyle="butt")
            axes[1].scatter([row.lower, row.upper], [y, y], color="#183B56", s=18, zorder=3)
    truth = float(ordered["truth_same_income_bin_share"].iloc[0])
    axes[1].axvline(truth, color="#C44E52", linestyle="--", linewidth=1.7, label=f"Hidden truth = {truth:.3f}")
    axes[1].set_yticks(range(len(ordered)), [scenario_labels[name] for name in ordered["scenario"]])
    axes[1].set_xlim(-0.03, 1.03)
    axes[1].set_xlabel("Same-income-bin pair share")
    axes[1].set_title("Held-out set-packing bounds")
    axes[1].grid(axis="x", alpha=0.25)
    axes[1].legend(loc="upper left", frameon=False, fontsize=8)
    fig.suptitle("Synthetic Chicago-coordinate AI integration pilot", fontsize=13)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_report(results: dict, bound_rows: pd.DataFrame, output: Path) -> None:
    node = results["node_benchmark"]
    edge = results["edge_recovery"]
    truth = results["bounds"]["truth_same_income_bin_share"]
    ai_rank = edge["ranking_conditional_on_candidate_recall"]["weak_mil_ai"]
    rule_rank = edge["ranking_conditional_on_candidate_recall"]["transparent_rule"]
    table_lines = []
    for row in bound_rows.itertuples(index=False):
        interval = f"[{row.lower:.3f}, {row.upper:.3f}]" if row.feasible else "infeasible"
        reduction = (
            f"{row.width_reduction_vs_untrimmed:.1%}"
            if pd.notna(row.width_reduction_vs_untrimmed)
            else "—"
        )
        table_lines.append(
            f"| {row.scenario} | {interval} | {row.width:.3f} | {reduction} | "
            f"{str(bool(row.covers_truth))} | {str(bool(row.truth_score_eligible))} |"
        )
    gate_label = "PASS" if node["relative_brier_improvement_ai_vs_rule"] >= 0.10 else "FAIL"
    recall_label = "PASS" if edge["candidate_true_edge_recall"] >= 0.95 else "FAIL"
    report = f"""# AI pilot integration benchmark

## Result

This is a **known-truth synthetic integration test**, not a Chicago finding.
The model was trained on {results['data']['train_day']} and evaluated once on the locked
holdout day {results['data']['held_out_day']}.  Public-like timestamps were rounded to
15 minutes; hidden pair IDs and income bins were never supplied to model fitting.

- Held-out supported-node Brier: transparent rule **{node['transparent_rule_brier']:.4f}**;
  weak-MIL AI **{node['weak_mil_ai_brier']:.4f}**; relative improvement
  **{node['relative_brier_improvement_ai_vs_rule']:.1%}** ({gate_label} against the 10% gate).
- Hidden true-edge candidate recall: **{edge['candidate_true_edge_recall']:.1%}**
  ({recall_label} against the 95% gate).
- Conditional true-edge ranking: AI MRR **{ai_rank['mean_reciprocal_rank']:.3f}** and
  top-1 **{ai_rank['top_1_rate']:.1%}**, versus rule MRR
  **{rule_rank['mean_reciprocal_rank']:.3f}** and top-1
  **{rule_rank['top_1_rate']:.1%}**.
- Hidden same-income-bin pair share on the holdout was **{truth:.3f}**.

## Set-packing bounds

| Candidate restriction | Interval | Width | Width reduction | Contains truth | True packing meets score floor |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table_lines)}

The untrimmed interval is conditional on the physical candidate rules.  The 90% and
95% intervals add an explicit model-score-retention restriction; they are sensitivity
sets, not confidence intervals.  “Contains truth” is meaningful here only because the
synthetic generator stored the true matching out of model view.

Two negative checks matter.  First, despite much better node calibration, the AI did
**not** improve top-1 true-edge ranking over the rule ({ai_rank['top_1_rate']:.1%} vs
{rule_rank['top_1_rate']:.1%}); the weak node objective is not a pair-ranking guarantee.
Second, the 95% AI score restriction excluded the hidden truth because the true
packing achieved less than 95% of the model-optimal score.  The 90% sensitivity set
retained truth, while narrowing the untrimmed interval.  A hard high-score cutoff
therefore cannot be treated as identified without repeated coverage validation.

## What this establishes—and what it does not

The run verifies that the actual weak-MIL and MILP components interoperate, that a
held-out node benchmark can be computed without pair-label leakage, and that synthetic
pair recovery and SES-bound coverage can be audited.  It does **not** establish true
co-rider links, personal income, social homophily, or an echo chamber in Chicago.  A
complete real authorized-trip day and ACS join are still required for an empirical
opportunity-exposure result.

The synthetic generator intentionally makes matched and unmatched compatibility
patterns separable enough to test software behavior.  Its large node-level gain is
not a transportable performance estimate for City of Chicago data.

Design parameters were fixed in `DESIGN_LOCK.json` before the held-out run.  No
holdout-driven tuning was performed.
"""
    output.write_text(report, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=INTEGRATION_DIR / "DESIGN_LOCK.json")
    parser.add_argument("--output-dir", type=Path, default=INTEGRATION_DIR / "results")
    args = parser.parse_args()
    design = json.loads(args.design.read_text(encoding="utf-8"))
    output_dir = args.output_dir
    data_dir = output_dir / "synthetic_data"
    model_dir = output_dir / "model"
    data_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(int(design["seed"]))
    public_paths: list[Path] = []
    node_truth_frames = []
    pair_truth_frames = []
    for day_index, day in enumerate(design["days"]):
        public, node_truth, pair_truth = generate_day(
            day, day_index, rng, design["synthetic_market_per_day"]
        )
        path = data_dir / f"synthetic_chicago_authorized_{day}.csv"
        public.to_csv(path, index=False)
        public_paths.append(path)
        node_truth_frames.append(node_truth)
        pair_truth_frames.append(pair_truth)
    node_truth = pd.concat(node_truth_frames, ignore_index=True)
    pair_truth = pd.concat(pair_truth_frames, ignore_index=True)
    node_truth.to_csv(data_dir / "hidden_node_truth_NOT_MODEL_INPUT.csv", index=False)
    pair_truth.to_csv(data_dir / "hidden_pair_truth_NOT_MODEL_INPUT.csv", index=False)

    model_cfg = design["candidate_and_model"]
    model_argv: list[str] = []
    for path in public_paths:
        model_argv.extend(["--input", str(path)])
    model_argv.extend(
        [
            "--output-dir",
            str(model_dir),
            "--test-date",
            str(design["held_out_day"]),
            "--max-start-delta-min",
            str(model_cfg["max_start_delta_min"]),
            "--max-pickup-km",
            str(model_cfg["max_pickup_km"]),
            "--max-dropoff-km",
            str(model_cfg["max_dropoff_km"]),
            "--min-direction-cosine",
            str(model_cfg["min_direction_cosine"]),
            "--max-candidates-per-node",
            str(model_cfg["max_candidates_per_node"]),
            "--neighbor-search-k",
            str(model_cfg["neighbor_search_k"]),
            "--ai-l2",
            str(model_cfg["ai_l2"]),
            "--rule-l2",
            str(model_cfg["rule_l2"]),
            "--max-iter",
            str(model_cfg["max_iter"]),
        ]
    )
    model_args = build_model_parser().parse_args(model_argv)
    model_card = run_weak_mil(model_args)

    node_predictions = pd.read_csv(model_dir / "node_predictions.csv")
    scored_edges = pd.read_csv(model_dir / "scored_candidate_edges.csv.gz")
    metrics = pd.read_csv(model_dir / "node_level_metrics.csv")
    edge_metrics, rank_rows = edge_recovery_metrics(
        scored_edges, node_predictions, pair_truth, str(design["held_out_day"])
    )
    rank_rows.to_csv(output_dir / "heldout_true_edge_ranks.csv", index=False)
    bound_results, bound_rows = run_bounds(
        scored_edges,
        node_predictions,
        node_truth,
        pair_truth,
        str(design["held_out_day"]),
        design["set_packing"],
    )
    bound_rows.to_csv(output_dir / "heldout_same_income_bounds.csv", index=False)

    held_metrics = metrics.loc[metrics["subset"].eq("test_supported")].set_index("model")
    rule_brier = float(held_metrics.loc["transparent_rule", "brier"])
    ai_brier = float(held_metrics.loc["weak_mil_ai", "brier"])
    results = {
        "benchmark_type": "known-truth synthetic Chicago-coordinate integration test",
        "not_an_empirical_finding": True,
        "design_lock": design,
        "data": {
            "train_day": design["days"][0],
            "held_out_day": design["held_out_day"],
            "rows_per_day": {
                path.stem.rsplit("_", 1)[-1]: int(len(pd.read_csv(path))) for path in public_paths
            },
            "total_hidden_pairs": int(len(pair_truth)),
            "total_unmatched_authorized": int((~node_truth["matched_truth"]).sum()),
            "model_input_files": [
                str(path.relative_to(INTEGRATION_DIR))
                if path.is_relative_to(INTEGRATION_DIR)
                else str(path)
                for path in public_paths
            ],
            "truth_files_never_used_by_model": [
                "results/synthetic_data/hidden_node_truth_NOT_MODEL_INPUT.csv",
                "results/synthetic_data/hidden_pair_truth_NOT_MODEL_INPUT.csv",
            ],
        },
        "node_benchmark": {
            "primary_subset": "test_supported",
            "transparent_rule_brier": rule_brier,
            "weak_mil_ai_brier": ai_brier,
            "relative_brier_improvement_ai_vs_rule": (rule_brier - ai_brier) / rule_brier,
            "passes_10_percent_gate": (rule_brier - ai_brier) / rule_brier >= 0.10,
            "full_metric_rows": metrics.to_dict(orient="records"),
        },
        "edge_recovery": {
            **edge_metrics,
            "passes_95_percent_candidate_recall_gate": edge_metrics[
                "candidate_true_edge_recall"
            ]
            >= 0.95,
        },
        "bounds": bound_results,
        "model_card_summary": {
            "candidate_config": model_card["candidate_config"],
            "candidate_audit": model_card["candidate_audit"],
            "training": model_card["training"],
        },
        "interpretation": {
            "positive": "The pipeline can be audited against hidden truth without giving pair labels to training.",
            "forbidden": "Do not interpret synthetic ranks or bounds as evidence about Chicago riders.",
        },
    }
    (output_dir / "benchmark_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8",
    )
    make_figure(metrics, bound_rows, output_dir / "benchmark_summary.png")
    write_report(results, bound_rows, output_dir / "INTEGRATION_REPORT.md")
    print(json.dumps({
        "node_brier_rule": rule_brier,
        "node_brier_ai": ai_brier,
        "brier_relative_improvement": (rule_brier - ai_brier) / rule_brier,
        "candidate_true_edge_recall": edge_metrics["candidate_true_edge_recall"],
        "truth_same_income_bin_share": bound_results["truth_same_income_bin_share"],
        "outputs": str(output_dir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
