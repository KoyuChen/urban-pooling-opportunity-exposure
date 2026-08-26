#!/usr/bin/env python3
"""Weakly supervised candidate-edge model for privacy-coarsened ride-pooling data.

The public Chicago TNP data provide a match label for each trip, but no co-rider
or pooled-group identifier.  This script therefore never creates or evaluates a
purported pair label.  It:

1. builds a physically plausible, degree-capped candidate graph from rounded
   time and OD centroids;
2. learns edge scores by maximizing *node-level* match likelihood under a
   noisy-OR/multiple-instance model; and
3. evaluates only node-level match probabilities on held-out days (or a held-
   out time block when only one day is supplied).

Scored edges are compatibility hypotheses for downstream set-packing and bound
calculations.  They are not observed co-rider links.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.spatial import cKDTree
from scipy.special import expit
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


REQUIRED_COLUMNS = {
    "trip_start_timestamp",
    "trip_end_timestamp",
    "trip_seconds",
    "trip_miles",
    "pickup_centroid_latitude",
    "pickup_centroid_longitude",
    "dropoff_centroid_latitude",
    "dropoff_centroid_longitude",
    "shared_trip_authorized",
    "shared_trip_match",
}

GEOGRAPHY_EQUALITY_FEATURES = {
    "pickup_area_same",
    "dropoff_area_same",
    "pickup_tract_same",
    "dropoff_tract_same",
    "same_area_both",
    "same_tract_both",
}


@dataclass(frozen=True)
class CandidateConfig:
    max_start_delta_min: float = 30.0
    max_pickup_km: float = 4.0
    max_dropoff_km: float = 7.0
    min_direction_cosine: float = -0.25
    max_candidates_per_node: int = 16
    neighbor_search_k: int = 96


def _json_safe(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON-encode {type(value)!r}")


def _parse_bool(series: pd.Series, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    normalized = series.astype("string").str.strip().str.lower()
    true_values = {"true", "t", "1", "yes", "y"}
    false_values = {"false", "f", "0", "no", "n", "", "<na>"}
    unknown = sorted(set(normalized.dropna().unique()) - true_values - false_values)
    if unknown:
        raise ValueError(f"Unrecognized boolean values in {name}: {unknown[:8]}")
    return normalized.isin(true_values)


def resolve_input_paths(explicit: Sequence[str], patterns: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in explicit:
        paths.append(Path(raw))
    for pattern in patterns:
        paths.extend(Path(p) for p in sorted(glob.glob(pattern)))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen:
            unique.append(path)
            seen.add(resolved)
    if not unique:
        raise FileNotFoundError("No input CSVs matched --input/--input-glob")
    missing = [str(p) for p in unique if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"Input files do not exist: {missing}")
    return unique


def load_authorized_trips(paths: Sequence[Path]) -> tuple[pd.DataFrame, dict]:
    frames = []
    input_rows: dict[str, int] = {}
    for path in paths:
        frame = pd.read_csv(path, low_memory=False)
        missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
        if missing:
            raise ValueError(f"{path} is missing required columns: {missing}")
        frame["_source_file"] = path.name
        input_rows[str(path)] = int(len(frame))
        frames.append(frame)

    trips = pd.concat(frames, ignore_index=True, sort=False)
    trips["shared_trip_authorized"] = _parse_bool(
        trips["shared_trip_authorized"], "shared_trip_authorized"
    )
    trips["shared_trip_match"] = _parse_bool(trips["shared_trip_match"], "shared_trip_match")
    rows_before_auth_filter = len(trips)
    trips = trips.loc[trips["shared_trip_authorized"]].copy()
    if trips.empty:
        raise ValueError("No shared-trip-authorized rows remain after filtering")

    trips["start_dt"] = pd.to_datetime(trips["trip_start_timestamp"], errors="coerce")
    trips["end_dt"] = pd.to_datetime(trips["trip_end_timestamp"], errors="coerce")
    numeric = [
        "trip_seconds",
        "trip_miles",
        "pickup_centroid_latitude",
        "pickup_centroid_longitude",
        "dropoff_centroid_latitude",
        "dropoff_centroid_longitude",
    ]
    optional_numeric = [
        "pickup_community_area",
        "dropoff_community_area",
        "pickup_census_tract",
        "dropoff_census_tract",
    ]
    for col in numeric + [c for c in optional_numeric if c in trips.columns]:
        trips[col] = pd.to_numeric(trips[col], errors="coerce")

    invalid_start = int(trips["start_dt"].isna().sum())
    trips = trips.loc[trips["start_dt"].notna()].copy()
    missing_end = trips["end_dt"].isna()
    trips.loc[missing_end, "end_dt"] = trips.loc[missing_end, "start_dt"] + pd.to_timedelta(
        trips.loc[missing_end, "trip_seconds"].fillna(0).clip(lower=0), unit="s"
    )
    trips["event_day"] = trips["start_dt"].dt.strftime("%Y-%m-%d")

    if "trip_id" in trips.columns:
        trip_ids = trips["trip_id"].astype("string")
        fallback = trips["_source_file"].astype(str) + ":" + trips.index.astype(str)
        trips["trip_id"] = trip_ids.fillna(fallback).astype(str)
    else:
        trips["trip_id"] = trips["_source_file"].astype(str) + ":" + trips.index.astype(str)
    duplicate_ids = int(trips["trip_id"].duplicated().sum())
    trips = trips.drop_duplicates("trip_id", keep="first").reset_index(drop=True)
    trips["node_id"] = np.arange(len(trips), dtype=np.int64)
    trips["y_match"] = trips["shared_trip_match"].astype(np.int8)

    coord_cols = [
        "pickup_centroid_latitude",
        "pickup_centroid_longitude",
        "dropoff_centroid_latitude",
        "dropoff_centroid_longitude",
    ]
    finite_coords = np.isfinite(trips[coord_cols].to_numpy(dtype=float)).all(axis=1)
    plausible_coords = (
        trips["pickup_centroid_latitude"].between(40.0, 43.0)
        & trips["dropoff_centroid_latitude"].between(40.0, 43.0)
        & trips["pickup_centroid_longitude"].between(-89.5, -86.0)
        & trips["dropoff_centroid_longitude"].between(-89.5, -86.0)
    ).to_numpy()
    trips["candidate_eligible"] = finite_coords & plausible_coords

    audit = {
        "input_files": [str(p) for p in paths],
        "input_rows_by_file": input_rows,
        "rows_before_authorized_filter": int(rows_before_auth_filter),
        "authorized_rows_after_cleaning": int(len(trips)),
        "invalid_start_rows_dropped": invalid_start,
        "duplicate_trip_ids_dropped": duplicate_ids,
        "candidate_eligible_rows": int(trips["candidate_eligible"].sum()),
        "candidate_eligible_rate": float(trips["candidate_eligible"].mean()),
        "match_rate": float(trips["y_match"].mean()),
        "days": sorted(trips["event_day"].unique().tolist()),
    }
    return trips, audit


def assign_splits(
    trips: pd.DataFrame, test_days: int, explicit_test_dates: Sequence[str]
) -> tuple[pd.DataFrame, dict]:
    trips = trips.copy()
    days = sorted(trips["event_day"].unique().tolist())
    explicit = sorted(set(explicit_test_dates))
    if explicit:
        unknown = sorted(set(explicit) - set(days))
        if unknown:
            raise ValueError(f"--test-date values absent from inputs: {unknown}")
        if set(explicit) == set(days):
            raise ValueError("At least one input day must remain in the training split")
        trips["split"] = np.where(trips["event_day"].isin(explicit), "test", "train")
        strategy = "explicit held-out dates"
        held_out = explicit
    elif len(days) >= 2:
        n_test = min(max(int(test_days), 1), len(days) - 1)
        held_out = days[-n_test:]
        trips["split"] = np.where(trips["event_day"].isin(held_out), "test", "train")
        strategy = "latest complete day(s) held out"
    else:
        # A whole-day split is preferable.  This fallback prevents edge leakage by
        # separating the graph at a time cutoff; candidates never cross the cutoff.
        valid_starts = trips["start_dt"].dropna().sort_values()
        cutoff = valid_starts.quantile(0.80)
        trips["split"] = np.where(trips["start_dt"] >= cutoff, "test", "train")
        if trips["split"].value_counts().min() < 20:
            raise ValueError("A one-day input needs at least 100 usable rows for a time-block split")
        held_out = [f"{days[0]} at/after {cutoff.isoformat()}"]
        strategy = "last 20% time block held out (one-day fallback)"

    summary = {
        "strategy": strategy,
        "held_out": held_out,
        "rows_by_split": {k: int(v) for k, v in trips["split"].value_counts().items()},
        "match_rate_by_split": {
            k: float(v) for k, v in trips.groupby("split")["y_match"].mean().items()
        },
    }
    return trips, summary


def _project_km(lat: np.ndarray, lon: np.ndarray, reference_lat: float) -> tuple[np.ndarray, np.ndarray]:
    y = lat * 110.574
    x = lon * (111.320 * math.cos(math.radians(reference_lat)))
    return x, y


def _same_nonmissing(a: pd.Series, b: pd.Series) -> np.ndarray:
    av = a.to_numpy()
    bv = b.to_numpy()
    return (pd.notna(av) & pd.notna(bv) & (av == bv)).astype(np.int8)


def build_candidates(trips: pd.DataFrame, cfg: CandidateConfig) -> tuple[pd.DataFrame, dict]:
    if cfg.max_candidates_per_node < 1 or cfg.neighbor_search_k < 2:
        raise ValueError("Candidate degree/search limits must be positive")
    eligible = trips["candidate_eligible"].to_numpy(dtype=bool)
    lat_values = np.concatenate(
        [
            trips.loc[eligible, "pickup_centroid_latitude"].to_numpy(dtype=float),
            trips.loc[eligible, "dropoff_centroid_latitude"].to_numpy(dtype=float),
        ]
    )
    if not len(lat_values):
        raise ValueError("No rows have complete, plausible pickup and dropoff centroids")
    reference_lat = float(np.nanmedian(lat_values))

    px, py = _project_km(
        trips["pickup_centroid_latitude"].to_numpy(dtype=float),
        trips["pickup_centroid_longitude"].to_numpy(dtype=float),
        reference_lat,
    )
    dx, dy = _project_km(
        trips["dropoff_centroid_latitude"].to_numpy(dtype=float),
        trips["dropoff_centroid_longitude"].to_numpy(dtype=float),
        reference_lat,
    )
    start_seconds = trips["start_dt"].astype("int64").to_numpy(dtype=np.int64) / 1e9
    end_seconds = trips["end_dt"].astype("int64").to_numpy(dtype=np.int64) / 1e9

    proposed_src: list[int] = []
    proposed_dst: list[int] = []
    proposed_cost: list[float] = []

    group_cols = ["event_day", "split"]
    for (_, _), group in trips.loc[eligible].groupby(group_cols, sort=True):
        ids = group["node_id"].to_numpy(dtype=np.int64)
        n_group = len(ids)
        if n_group < 2:
            continue
        midnight = group["start_dt"].dt.normalize().iloc[0].value / 1e9
        time_min = (start_seconds[ids] - midnight) / 60.0
        tree_values = np.column_stack(
            [
                time_min / cfg.max_start_delta_min,
                px[ids] / cfg.max_pickup_km,
                py[ids] / cfg.max_pickup_km,
            ]
        )
        tree = cKDTree(tree_values)
        k = min(cfg.neighbor_search_k + 1, n_group)
        _, neighbor_local = tree.query(
            tree_values,
            k=k,
            p=np.inf,
            distance_upper_bound=1.0,
            workers=-1,
        )
        if k == 1:
            neighbor_local = neighbor_local[:, None]

        for local_i, raw_js in enumerate(neighbor_local):
            raw_js = np.asarray(raw_js, dtype=np.int64)
            raw_js = raw_js[(raw_js < n_group) & (raw_js != local_i)]
            if not len(raw_js):
                continue
            i = int(ids[local_i])
            js = ids[raw_js]
            start_delta = np.abs(start_seconds[js] - start_seconds[i]) / 60.0
            pickup_dist = np.hypot(px[js] - px[i], py[js] - py[i])
            dropoff_dist = np.hypot(dx[js] - dx[i], dy[js] - dy[i])
            vi_x, vi_y = dx[i] - px[i], dy[i] - py[i]
            vj_x, vj_y = dx[js] - px[js], dy[js] - py[js]
            denom = np.hypot(vi_x, vi_y) * np.hypot(vj_x, vj_y)
            cosine = np.divide(
                vi_x * vj_x + vi_y * vj_y,
                denom,
                out=np.zeros_like(denom),
                where=denom > 1e-8,
            )
            keep = (
                (start_delta <= cfg.max_start_delta_min)
                & (pickup_dist <= cfg.max_pickup_km)
                & (dropoff_dist <= cfg.max_dropoff_km)
                & (cosine >= cfg.min_direction_cosine)
            )
            if not keep.any():
                continue
            js = js[keep]
            cost = (
                start_delta[keep] / cfg.max_start_delta_min
                + pickup_dist[keep] / cfg.max_pickup_km
                + dropoff_dist[keep] / cfg.max_dropoff_km
                + 0.50 * (1.0 - cosine[keep]) / 2.0
            )
            take_n = min(cfg.max_candidates_per_node, len(js))
            selected = np.argpartition(cost, take_n - 1)[:take_n] if take_n < len(js) else np.arange(len(js))
            for j, edge_cost in zip(js[selected], cost[selected]):
                s, d = (i, int(j)) if i < j else (int(j), i)
                proposed_src.append(s)
                proposed_dst.append(d)
                proposed_cost.append(float(edge_cost))

    if not proposed_src:
        raise ValueError("No candidate edges passed the configured time/OD filters")

    proposed = pd.DataFrame(
        {"src": proposed_src, "dst": proposed_dst, "candidate_cost": proposed_cost}
    )
    proposed = (
        proposed.sort_values("candidate_cost", kind="mergesort")
        .drop_duplicates(["src", "dst"], keep="first")
        .reset_index(drop=True)
    )

    # Enforce a hard degree cap.  Lower physical-compatibility cost receives
    # priority; this makes subsequent set-packing computationally manageable.
    degree = np.zeros(len(trips), dtype=np.int32)
    accepted = np.zeros(len(proposed), dtype=bool)
    for row_index, (s, d) in enumerate(
        proposed[["src", "dst"]].itertuples(index=False, name=None)
    ):
        if degree[s] < cfg.max_candidates_per_node and degree[d] < cfg.max_candidates_per_node:
            accepted[row_index] = True
            degree[s] += 1
            degree[d] += 1
    edges = proposed.loc[accepted].reset_index(drop=True)
    s = edges["src"].to_numpy(dtype=np.int64)
    d = edges["dst"].to_numpy(dtype=np.int64)

    start_delta = np.abs(start_seconds[s] - start_seconds[d]) / 60.0
    end_delta = np.abs(end_seconds[s] - end_seconds[d]) / 60.0
    pickup_dist = np.hypot(px[s] - px[d], py[s] - py[d])
    dropoff_dist = np.hypot(dx[s] - dx[d], dy[s] - dy[d])
    vi_x, vi_y = dx[s] - px[s], dy[s] - py[s]
    vj_x, vj_y = dx[d] - px[d], dy[d] - py[d]
    denom = np.hypot(vi_x, vi_y) * np.hypot(vj_x, vj_y)
    direction_cosine = np.divide(
        vi_x * vj_x + vi_y * vj_y,
        denom,
        out=np.zeros_like(denom),
        where=denom > 1e-8,
    )
    seconds = trips["trip_seconds"].fillna(0).clip(lower=0).to_numpy(dtype=float)
    miles = trips["trip_miles"].fillna(0).clip(lower=0).to_numpy(dtype=float)
    duration_rel_gap = np.abs(seconds[s] - seconds[d]) / np.maximum(
        np.maximum(seconds[s], seconds[d]), 60.0
    )
    miles_rel_gap = np.abs(miles[s] - miles[d]) / np.maximum(
        np.maximum(miles[s], miles[d]), 0.25
    )
    overlap_seconds = np.maximum(
        0.0, np.minimum(end_seconds[s], end_seconds[d]) - np.maximum(start_seconds[s], start_seconds[d])
    )
    min_duration = np.maximum(np.minimum(seconds[s], seconds[d]), 60.0)
    interval_overlap_ratio = np.clip(overlap_seconds / min_duration, 0.0, 1.0)

    edges["event_day"] = trips.iloc[s]["event_day"].to_numpy()
    edges["split"] = trips.iloc[s]["split"].to_numpy()
    edges["start_delta_min"] = start_delta
    edges["end_delta_min"] = end_delta
    edges["pickup_km"] = pickup_dist
    edges["dropoff_km"] = dropoff_dist
    edges["duration_rel_gap"] = np.clip(duration_rel_gap, 0.0, 1.0)
    edges["miles_rel_gap"] = np.clip(miles_rel_gap, 0.0, 1.0)
    edges["direction_cosine"] = np.clip(direction_cosine, -1.0, 1.0)
    edges["interval_overlap_ratio"] = interval_overlap_ratio

    for col, out_name in [
        ("pickup_community_area", "pickup_area_same"),
        ("dropoff_community_area", "dropoff_area_same"),
        ("pickup_census_tract", "pickup_tract_same"),
        ("dropoff_census_tract", "dropoff_tract_same"),
    ]:
        if col in trips.columns:
            edges[out_name] = _same_nonmissing(trips.iloc[s][col], trips.iloc[d][col])
        else:
            edges[out_name] = np.zeros(len(edges), dtype=np.int8)

    diagnostics = {
        "reference_latitude": reference_lat,
        "proposed_unique_edges_before_degree_cap": int(len(proposed)),
        "accepted_edges": int(len(edges)),
        "max_observed_degree": int(degree.max()),
        "supported_nodes": int((degree > 0).sum()),
        "supported_node_rate": float((degree > 0).mean()),
        "supported_rate_among_coordinate_eligible": float((degree[eligible] > 0).mean()),
        "supported_match_node_rate": float((degree[trips["y_match"].to_numpy() == 1] > 0).mean())
        if trips["y_match"].sum()
        else None,
        "supported_rate_among_coordinate_eligible_match_nodes": float(
            (degree[eligible & (trips["y_match"].to_numpy() == 1)] > 0).mean()
        )
        if (eligible & (trips["y_match"].to_numpy() == 1)).any()
        else None,
        "degree_quantiles_supported": {
            str(q): float(np.quantile(degree[degree > 0], q))
            for q in (0.0, 0.25, 0.5, 0.75, 1.0)
        },
    }
    return edges, diagnostics


def make_feature_matrices(
    edges: pd.DataFrame,
    cfg: CandidateConfig,
    feature_set: str = "full",
) -> tuple[np.ndarray, list[str], np.ndarray]:
    t = np.clip(edges["start_delta_min"].to_numpy() / cfg.max_start_delta_min, 0, 1)
    e = np.clip(edges["end_delta_min"].to_numpy() / 90.0, 0, 1)
    p = np.clip(edges["pickup_km"].to_numpy() / cfg.max_pickup_km, 0, 1)
    d = np.clip(edges["dropoff_km"].to_numpy() / cfg.max_dropoff_km, 0, 1)
    duration = np.clip(edges["duration_rel_gap"].to_numpy(), 0, 1)
    miles = np.clip(edges["miles_rel_gap"].to_numpy(), 0, 1)
    direction_bad = np.clip((1.0 - edges["direction_cosine"].to_numpy()) / 2.0, 0, 1)
    overlap = np.clip(edges["interval_overlap_ratio"].to_numpy(), 0, 1)
    pa = edges["pickup_area_same"].to_numpy(dtype=float)
    da = edges["dropoff_area_same"].to_numpy(dtype=float)
    pt = edges["pickup_tract_same"].to_numpy(dtype=float)
    dt = edges["dropoff_tract_same"].to_numpy(dtype=float)

    columns = {
        "intercept": np.ones(len(edges)),
        "time": t,
        "end_time": e,
        "pickup": p,
        "dropoff": d,
        "duration_gap": duration,
        "miles_gap": miles,
        "direction_bad": direction_bad,
        "overlap": overlap,
        "pickup_area_same": pa,
        "dropoff_area_same": da,
        "pickup_tract_same": pt,
        "dropoff_tract_same": dt,
        "time_sq": t**2,
        "pickup_sq": p**2,
        "dropoff_sq": d**2,
        "direction_bad_sq": direction_bad**2,
        "exp_time": np.exp(-3.0 * t),
        "exp_pickup": np.exp(-3.0 * p),
        "exp_dropoff": np.exp(-3.0 * d),
        "time_x_pickup": t * p,
        "time_x_dropoff": t * d,
        "pickup_x_dropoff": p * d,
        "time_x_direction_bad": t * direction_bad,
        "route_gap_interaction": duration * miles,
        "same_area_both": pa * da,
        "same_tract_both": pt * dt,
        "overlap_x_close_time": overlap * (1.0 - t),
    }
    if feature_set == "full":
        names = list(columns)
    elif feature_set == "no_geography_equality":
        names = [name for name in columns if name not in GEOGRAPHY_EQUALITY_FEATURES]
    else:
        raise ValueError(f"Unknown feature set: {feature_set}")
    ai_matrix = np.column_stack([columns[name] for name in names]).astype(np.float64)

    # Fully disclosed rule: smaller time/OD gaps and aligned routes are better.
    # Only its intercept and non-negative global scale are calibrated.
    rule_raw = (
        -2.0 * t
        -0.7 * e
        -1.2 * p
        -1.0 * d
        -0.5 * duration
        -0.5 * miles
        -0.6 * direction_bad
        +0.25 * overlap
        +0.30 * pa
        +0.30 * da
        +0.15 * pt
        +0.15 * dt
    )
    return ai_matrix, names, rule_raw


class NoisyOrMIL:
    """Linear edge hazard scorer trained solely against node labels."""

    def __init__(self, l2: float = 1e-3, max_iter: int = 150):
        self.l2 = float(l2)
        self.max_iter = int(max_iter)
        self.coef_: np.ndarray | None = None
        self.result_ = None

    @staticmethod
    def _initial_intercept(y: np.ndarray, src: np.ndarray, dst: np.ndarray, n_nodes: int) -> float:
        prevalence = float(np.clip(np.mean(y), 1e-3, 1 - 1e-3))
        degree = np.bincount(np.concatenate([src, dst]), minlength=n_nodes)
        avg_degree = max(float(degree[degree > 0].mean()), 1.0)
        target_lambda = -math.log1p(-prevalence)
        hazard = max(target_lambda / avg_degree, 1e-6)
        return float(np.clip(math.log(math.expm1(hazard)), -12.0, 4.0))

    def fit(
        self,
        x: np.ndarray,
        src: np.ndarray,
        dst: np.ndarray,
        y_all: np.ndarray,
        node_mask: np.ndarray,
        initial: np.ndarray | None = None,
        bounds=None,
    ) -> "NoisyOrMIL":
        n_nodes = len(y_all)
        fit_nodes = np.flatnonzero(node_mask)
        if not len(fit_nodes):
            raise ValueError("No supported training nodes are available for MIL fitting")
        y_fit = y_all[fit_nodes].astype(float)
        if np.unique(y_fit).size < 2:
            raise ValueError("Supported training nodes must contain both matched and unmatched labels")
        if initial is None:
            initial = np.zeros(x.shape[1], dtype=float)
            initial[0] = self._initial_intercept(y_fit, src, dst, n_nodes)

        def objective(w: np.ndarray) -> tuple[float, np.ndarray]:
            z = np.clip(x @ w, -35.0, 25.0)
            hazard = np.logaddexp(0.0, z)
            lam = np.bincount(src, weights=hazard, minlength=n_nodes)
            lam += np.bincount(dst, weights=hazard, minlength=n_nodes)
            fit_lambda = np.clip(lam[fit_nodes], 1e-12, 60.0)
            pos = y_fit == 1
            per_node = np.empty_like(fit_lambda)
            per_node[pos] = -np.log(-np.expm1(-fit_lambda[pos]))
            per_node[~pos] = fit_lambda[~pos]

            derivative = np.zeros(n_nodes, dtype=float)
            d_fit = np.ones_like(fit_lambda)
            d_fit[pos] = -1.0 / np.expm1(fit_lambda[pos])
            derivative[fit_nodes] = d_fit / len(fit_nodes)
            edge_derivative = (derivative[src] + derivative[dst]) * expit(z)
            grad = x.T @ edge_derivative
            penalty_coef = w.copy()
            penalty_coef[0] = 0.0
            loss = float(np.mean(per_node) + 0.5 * self.l2 * np.dot(penalty_coef, penalty_coef))
            grad += self.l2 * penalty_coef
            return loss, grad

        self.result_ = minimize(
            objective,
            np.asarray(initial, dtype=float),
            jac=True,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": self.max_iter, "ftol": 1e-10, "gtol": 1e-6, "maxls": 30},
        )
        self.coef_ = np.asarray(self.result_.x)
        return self

    def edge_logits(self, x: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            raise RuntimeError("Model is not fitted")
        return np.clip(x @ self.coef_, -35.0, 25.0)

    def status(self) -> dict:
        if self.result_ is None:
            return {}
        return {
            "success": bool(self.result_.success),
            "message": str(self.result_.message),
            "iterations": int(getattr(self.result_, "nit", -1)),
            "function_evaluations": int(getattr(self.result_, "nfev", -1)),
            "objective": float(self.result_.fun),
        }


def noisy_or_node_probability(
    edge_logits: np.ndarray, src: np.ndarray, dst: np.ndarray, n_nodes: int
) -> tuple[np.ndarray, np.ndarray]:
    hazard = np.logaddexp(0.0, edge_logits)
    lam = np.bincount(src, weights=hazard, minlength=n_nodes)
    lam += np.bincount(dst, weights=hazard, minlength=n_nodes)
    probability = -np.expm1(-np.clip(lam, 0.0, 60.0))
    return probability, lam


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    breaks = np.linspace(0.0, 1.0, bins + 1)
    bucket = np.minimum(np.digitize(p, breaks[1:-1], right=False), bins - 1)
    result = 0.0
    for b in range(bins):
        mask = bucket == b
        if mask.any():
            result += mask.mean() * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(result)


def metric_record(y: np.ndarray, p: np.ndarray) -> dict:
    p = np.clip(np.asarray(p, dtype=float), 1e-8, 1 - 1e-8)
    y = np.asarray(y, dtype=int)
    record = {
        "n_nodes": int(len(y)),
        "observed_match_rate": float(y.mean()) if len(y) else None,
        "mean_predicted_probability": float(p.mean()) if len(p) else None,
        "brier": float(brier_score_loss(y, p)) if len(y) else None,
        "log_loss": float(log_loss(y, p, labels=[0, 1])) if len(y) else None,
        "ece_10_bins": expected_calibration_error(y, p) if len(y) else None,
        "roc_auc": None,
        "average_precision": None,
    }
    if len(y) and np.unique(y).size == 2:
        record["roc_auc"] = float(roc_auc_score(y, p))
        record["average_precision"] = float(average_precision_score(y, p))
    return record


def calibration_rows(
    trips: pd.DataFrame, probability_columns: Sequence[str], subset_mask: np.ndarray, bins: int = 10
) -> pd.DataFrame:
    rows = []
    y = trips["y_match"].to_numpy(dtype=int)
    for column in probability_columns:
        values = trips[column].to_numpy(dtype=float)
        indices = np.flatnonzero(subset_mask)
        p = values[indices]
        yy = y[indices]
        bucket = np.minimum(np.digitize(p, np.linspace(0, 1, bins + 1)[1:-1]), bins - 1)
        for b in range(bins):
            keep = bucket == b
            if keep.any():
                rows.append(
                    {
                        "model": column,
                        "bin": b,
                        "n": int(keep.sum()),
                        "mean_prediction": float(p[keep].mean()),
                        "observed_match_rate": float(yy[keep].mean()),
                    }
                )
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict:
    input_paths = resolve_input_paths(args.input, args.input_glob)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = CandidateConfig(
        max_start_delta_min=args.max_start_delta_min,
        max_pickup_km=args.max_pickup_km,
        max_dropoff_km=args.max_dropoff_km,
        min_direction_cosine=args.min_direction_cosine,
        max_candidates_per_node=args.max_candidates_per_node,
        neighbor_search_k=args.neighbor_search_k,
    )

    trips, input_audit = load_authorized_trips(input_paths)
    trips, split_audit = assign_splits(trips, args.test_days, args.test_date)
    edges, candidate_audit = build_candidates(trips, cfg)
    ai_x, feature_names, rule_raw = make_feature_matrices(edges, cfg, args.feature_set)

    n_nodes = len(trips)
    y = trips["y_match"].to_numpy(dtype=int)
    src = edges["src"].to_numpy(dtype=np.int64)
    dst = edges["dst"].to_numpy(dtype=np.int64)
    train_edge = edges["split"].eq("train").to_numpy()
    if not train_edge.any():
        raise ValueError("No candidate edges were constructed in the training split")
    degree = np.bincount(np.concatenate([src, dst]), minlength=n_nodes)
    train_node_mask = trips["split"].eq("train").to_numpy() & (degree > 0)
    test_supported = trips["split"].eq("test").to_numpy() & (degree > 0)
    if not test_supported.any():
        raise ValueError("No candidate-supported nodes were constructed in the test split")

    train_src = src[train_edge]
    train_dst = dst[train_edge]
    rule_matrix = np.column_stack([np.ones(len(edges)), rule_raw])
    rule_model = NoisyOrMIL(l2=args.rule_l2, max_iter=args.max_iter)
    rule_model.fit(
        rule_matrix[train_edge],
        train_src,
        train_dst,
        y,
        train_node_mask,
        bounds=[(None, None), (0.0, 20.0)],
    )
    ai_model = NoisyOrMIL(l2=args.ai_l2, max_iter=args.max_iter)
    ai_model.fit(ai_x[train_edge], train_src, train_dst, y, train_node_mask)

    rule_logits = rule_model.edge_logits(rule_matrix)
    ai_logits = ai_model.edge_logits(ai_x)
    rule_graph_p, rule_lambda = noisy_or_node_probability(rule_logits, src, dst, n_nodes)
    ai_graph_p, ai_lambda = noisy_or_node_probability(ai_logits, src, dst, n_nodes)
    train_prevalence = float(y[trips["split"].eq("train").to_numpy()].mean())
    prior = np.full(n_nodes, train_prevalence)
    supported = degree > 0
    rule_coverage_p = np.where(supported, rule_graph_p, train_prevalence)
    ai_coverage_p = np.where(supported, ai_graph_p, train_prevalence)

    trips["candidate_degree"] = degree
    trips["p_prevalence"] = prior
    trips["p_rule_graph"] = rule_graph_p
    trips["p_ai_graph"] = ai_graph_p
    trips["p_rule"] = rule_coverage_p
    trips["p_ai"] = ai_coverage_p
    trips["rule_node_hazard"] = rule_lambda
    trips["ai_node_hazard"] = ai_lambda

    metric_rows = []
    subsets = {
        "train_supported": train_node_mask,
        "test_supported": test_supported,
        "test_all_authorized": trips["split"].eq("test").to_numpy(),
    }
    model_columns = {
        "prevalence": "p_prevalence",
        "transparent_rule": "p_rule",
        "weak_mil_ai": "p_ai",
    }
    for subset_name, subset_mask in subsets.items():
        for model_name, column in model_columns.items():
            record = metric_record(y[subset_mask], trips.loc[subset_mask, column].to_numpy())
            record.update({"subset": subset_name, "model": model_name})
            metric_rows.append(record)
    metrics = pd.DataFrame(metric_rows)

    test_metrics = metrics.loc[metrics["subset"].eq("test_supported")].set_index("model")
    rule_brier = float(test_metrics.loc["transparent_rule", "brier"])
    ai_brier = float(test_metrics.loc["weak_mil_ai", "brier"])
    brier_improvement = (rule_brier - ai_brier) / rule_brier if rule_brier > 0 else None

    # Add identifiers and scores, but deliberately omit endpoint labels: there
    # is no edge ground truth in the public data.
    edges_out = edges.copy()
    edges_out.insert(0, "edge_id", [f"candidate:{s}-{d}" for s, d in zip(src, dst)])
    edges_out.insert(3, "src_trip_id", trips.iloc[src]["trip_id"].to_numpy())
    edges_out.insert(4, "dst_trip_id", trips.iloc[dst]["trip_id"].to_numpy())
    edges_out["transparent_rule_raw"] = rule_raw
    edges_out["p_rule_edge"] = expit(rule_logits)
    edges_out["p_ai_edge"] = expit(ai_logits)

    node_columns = [
        "node_id",
        "trip_id",
        "event_day",
        "split",
        "y_match",
        "candidate_eligible",
        "candidate_degree",
        "p_prevalence",
        "p_rule_graph",
        "p_ai_graph",
        "p_rule",
        "p_ai",
        "rule_node_hazard",
        "ai_node_hazard",
        "_source_file",
    ]
    trips[node_columns].to_csv(output_dir / "node_predictions.csv", index=False)
    edges_out.to_csv(output_dir / "scored_candidate_edges.csv.gz", index=False, compression="gzip")
    metrics.to_csv(output_dir / "node_level_metrics.csv", index=False)
    calibration = calibration_rows(
        trips,
        ["p_prevalence", "p_rule", "p_ai"],
        test_supported,
        bins=args.calibration_bins,
    )
    calibration.to_csv(output_dir / "test_supported_calibration.csv", index=False)

    coefficients = pd.concat(
        [
            pd.DataFrame(
                {
                    "model": "transparent_rule",
                    "feature": ["intercept", "disclosed_rule_raw"],
                    "coefficient": rule_model.coef_,
                }
            ),
            pd.DataFrame(
                {
                    "model": "weak_mil_ai",
                    "feature": feature_names,
                    "coefficient": ai_model.coef_,
                }
            ),
        ],
        ignore_index=True,
    )
    coefficients.to_csv(output_dir / "model_coefficients.csv", index=False)

    endpoint_y_product = y[src] * y[dst]
    model_card = {
        "interpretation": {
            "estimand": "node-level probability that an authorized trip is reported as matched",
            "edge_output": "time/OD compatibility score for a candidate pair",
            "edge_ground_truth_available": False,
            "forbidden_claim": "A high-scoring edge is not evidence that the two trips shared a vehicle.",
            "downstream_use": "candidate weighting for set-packing and partial-identification bounds",
        },
        "input_audit": input_audit,
        "split": split_audit,
        "candidate_config": asdict(cfg),
        "candidate_audit": candidate_audit,
        "candidate_limitations": [
            "Rounded times and public centroids create ties; the degree/search caps can omit a true counterpart.",
            "Candidate recall cannot be measured without a pooled-group identifier.",
            "Threshold and cap sensitivity must accompany downstream exposure bounds.",
        ],
        "training": {
            "train_prevalence": train_prevalence,
            "rule_model": rule_model.status(),
            "weak_mil_ai_model": ai_model.status(),
            "ai_l2": args.ai_l2,
            "rule_l2": args.rule_l2,
            "feature_count": len(feature_names),
            "feature_set": args.feature_set,
            "geography_equality_features_removed": sorted(
                GEOGRAPHY_EQUALITY_FEATURES
                if args.feature_set == "no_geography_equality"
                else []
            ),
            "node_labels_used": ["shared_trip_match"],
            "edge_labels_used": [],
            "excluded_as_features": [
                "shared_trip_match",
                "shared_trip_authorized",
                "trips_pooled",
                "fare",
                "trip_total",
            ],
        },
        "evaluation": {
            "primary_subset": "test_supported",
            "primary_unit": "trip node",
            "edge_accuracy_reported": False,
            "test_supported_brier_relative_improvement_ai_vs_rule": brier_improvement,
        },
        "weak_diagnostics_not_edge_truth": {
            "candidate_edges_with_two_match_positive_endpoints_rate": float(endpoint_y_product.mean()),
            "reason_not_truth": "Two matched nodes can belong to different pooled groups; the public data expose no group ID.",
        },
        "outputs": {
            "node_predictions": "node_predictions.csv",
            "scored_candidate_edges": "scored_candidate_edges.csv.gz",
            "metrics": "node_level_metrics.csv",
            "calibration": "test_supported_calibration.csv",
            "coefficients": "model_coefficients.csv",
        },
    }
    (output_dir / "model_card.json").write_text(
        json.dumps(model_card, indent=2, ensure_ascii=False, default=_json_safe) + "\n",
        encoding="utf-8",
    )

    print(f"Loaded {len(trips):,} authorized trip nodes across {len(input_audit['days'])} day(s).")
    print(f"Constructed {len(edges):,} degree-capped candidate edges.")
    print(
        "Held-out supported-node Brier: "
        f"rule={rule_brier:.5f}, weak-MIL={ai_brier:.5f}, "
        f"relative improvement={brier_improvement:.1%}."
    )
    print("No edge labels were created or evaluated; scored edges are compatibility hypotheses only.")
    print(f"Outputs: {output_dir}")
    return model_card


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[], help="Input CSV; repeat as needed")
    parser.add_argument(
        "--input-glob", action="append", default=[], help="Quoted glob for complete-day input CSVs"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--test-days", type=int, default=1)
    parser.add_argument("--test-date", action="append", default=[], help="Explicit YYYY-MM-DD holdout")
    parser.add_argument("--max-start-delta-min", type=float, default=30.0)
    parser.add_argument("--max-pickup-km", type=float, default=4.0)
    parser.add_argument("--max-dropoff-km", type=float, default=7.0)
    parser.add_argument("--min-direction-cosine", type=float, default=-0.25)
    parser.add_argument("--max-candidates-per-node", type=int, default=16)
    parser.add_argument("--neighbor-search-k", type=int, default=96)
    parser.add_argument("--ai-l2", type=float, default=1e-3)
    parser.add_argument("--rule-l2", type=float, default=1e-5)
    parser.add_argument("--max-iter", type=int, default=150)
    parser.add_argument("--calibration-bins", type=int, default=10)
    parser.add_argument(
        "--feature-set",
        choices=("full", "no_geography_equality"),
        default="full",
        help=(
            "AI feature map. Use no_geography_equality for the primary specification; "
            "full is retained for the locked circularity diagnostic."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
