#!/usr/bin/env python3
"""Known-truth validation for privacy-coarsened co-rider candidate graphs.

Each synthetic market contains latent true rider pairs. Pair members share a
service time and similar origins/destinations; unrelated services can collide
after time is rounded. The validation checks whether sharp set-packing bounds
cover the known same-SES-bin pairing rate and how their width changes as the
public timestamps become coarser.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from set_packing_bounds import PackingBounds, prepare_problem, solve_bounds


def generate_market(
    seed: int,
    *,
    n_pairs: int = 30,
    homophily: float = 0.78,
    horizon_minutes: float = 120.0,
) -> pd.DataFrame:
    """Generate latent paired trips with SES and OD features."""

    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for pair_id in range(n_pairs):
        first_bin = int(rng.integers(0, 2))
        second_bin = first_bin if rng.random() < homophily else 1 - first_bin
        service_time = float(rng.uniform(0, horizon_minutes))
        pickup = rng.uniform(0.05, 0.95, size=2)
        angle = float(rng.uniform(0, 2 * np.pi))
        trip_length = float(rng.uniform(0.18, 0.42))
        dropoff = pickup + trip_length * np.array([np.cos(angle), np.sin(angle)])
        for member, ses_bin in enumerate([first_bin, second_bin]):
            # Pair members have close but nonidentical OD points. Their latent
            # service time is shared; only the published timestamp is coarsened.
            observed_pickup = pickup + rng.normal(0, 0.008, size=2)
            observed_dropoff = dropoff + rng.normal(0, 0.010, size=2)
            ses_value = float(0.35 + 0.9 * ses_bin + rng.normal(0, 0.12))
            rows.append(
                {
                    "node_id": f"p{pair_id:03d}_{member}",
                    "true_pair_id": pair_id,
                    "latent_time": service_time,
                    "pickup_x": float(observed_pickup[0]),
                    "pickup_y": float(observed_pickup[1]),
                    "dropoff_x": float(observed_dropoff[0]),
                    "dropoff_y": float(observed_dropoff[1]),
                    "ses_bin": ses_bin,
                    "ses_value": ses_value,
                    "matched_observed": 1,
                }
            )
    return pd.DataFrame(rows)


def build_candidates(
    nodes: pd.DataFrame,
    time_bin_minutes: int,
    *,
    pickup_radius: float = 0.32,
    dropoff_radius: float = 0.36,
) -> pd.DataFrame:
    """Create a candidate pair graph from coarsened time and OD compatibility."""

    frame = nodes.copy()
    frame["public_time"] = (
        np.floor(frame["latent_time"].to_numpy() / time_bin_minutes) * time_bin_minutes
    )
    # Mimic privacy coarsening of disclosed centroids as well as timestamps.
    for column in ["pickup_x", "pickup_y", "dropoff_x", "dropoff_y"]:
        frame[f"public_{column}"] = np.round(frame[column] / 0.02) * 0.02

    rows: list[dict] = []
    values = frame.to_dict("records")
    for i in range(len(values)):
        a = values[i]
        for j in range(i + 1, len(values)):
            b = values[j]
            if a["public_time"] != b["public_time"]:
                continue
            pickup_distance = float(
                np.hypot(
                    a["public_pickup_x"] - b["public_pickup_x"],
                    a["public_pickup_y"] - b["public_pickup_y"],
                )
            )
            dropoff_distance = float(
                np.hypot(
                    a["public_dropoff_x"] - b["public_dropoff_x"],
                    a["public_dropoff_y"] - b["public_dropoff_y"],
                )
            )
            if pickup_distance > pickup_radius or dropoff_distance > dropoff_radius:
                continue
            a_vector = np.array(
                [
                    a["public_dropoff_x"] - a["public_pickup_x"],
                    a["public_dropoff_y"] - a["public_pickup_y"],
                ]
            )
            b_vector = np.array(
                [
                    b["public_dropoff_x"] - b["public_pickup_x"],
                    b["public_dropoff_y"] - b["public_pickup_y"],
                ]
            )
            denominator = float(np.linalg.norm(a_vector) * np.linalg.norm(b_vector))
            direction_cosine = float(np.dot(a_vector, b_vector) / denominator) if denominator else -1.0
            if direction_cosine < 0.35:
                continue
            length_gap = abs(float(np.linalg.norm(a_vector) - np.linalg.norm(b_vector)))
            edge_score = float(
                np.exp(
                    -4.5 * pickup_distance
                    - 4.0 * dropoff_distance
                    - 2.0 * length_gap
                    - 0.4 * (1.0 - direction_cosine)
                )
            )
            same_bin = float(a["ses_bin"] == b["ses_bin"])
            rows.append(
                {
                    "edge_id": f"e_{i}_{j}",
                    "u": a["node_id"],
                    "v": b["node_id"],
                    "edge_score": edge_score,
                    "pickup_distance": pickup_distance,
                    "dropoff_distance": dropoff_distance,
                    "direction_cosine": direction_cosine,
                    "length_gap": length_gap,
                    "same_bin": same_bin,
                    "is_true": int(a["true_pair_id"] == b["true_pair_id"]),
                }
            )
    return pd.DataFrame(rows)


def true_statistics(nodes: pd.DataFrame) -> tuple[float, float]:
    grouped = nodes.sort_values(["true_pair_id", "node_id"]).groupby("true_pair_id")
    same = grouped["ses_bin"].nunique().eq(1).mean()
    gap = grouped["ses_value"].agg(lambda values: abs(values.iloc[0] - values.iloc[1])).mean()
    return float(same), float(gap)


def _covers(bounds: PackingBounds, truth: float) -> bool:
    return bool(
        bounds.feasible
        and bounds.lower is not None
        and bounds.upper is not None
        and bounds.lower - 1e-8 <= truth <= bounds.upper + 1e-8
    )


def validate_instance(
    seed: int,
    time_bin_minutes: int,
    *,
    n_pairs: int,
    score_retention: float,
    time_limit: float,
) -> dict:
    nodes = generate_market(seed, n_pairs=n_pairs)
    edges = build_candidates(nodes, time_bin_minutes)
    true_same, true_gap = true_statistics(nodes)
    true_edges = edges[edges["is_true"] == 1]
    recall = len(true_edges) / n_pairs

    raw = solve_bounds(
        nodes,
        edges,
        metric="same_bin",
        matched_col="matched_observed",
        score_retention=None,
        time_limit=time_limit,
    )
    constrained = solve_bounds(
        nodes,
        edges,
        metric="same_bin",
        matched_col="matched_observed",
        score_retention=score_retention,
        time_limit=time_limit,
    )

    _, metric_edges = prepare_problem(nodes, edges, metric="same_bin")
    metric_lookup = metric_edges.set_index("edge_id")["metric_value"]
    score_ids = list(constrained.score_solution.selected_edge_ids)
    point_same = float(metric_lookup.loc[score_ids].mean()) if score_ids else np.nan
    true_total_score = float(true_edges["edge_score"].sum())
    score_optimum = float(constrained.score_optimum or np.nan)
    true_retention = true_total_score / score_optimum if score_optimum > 0 else np.nan

    return {
        "seed": seed,
        "time_bin_minutes": time_bin_minutes,
        "n_nodes": len(nodes),
        "n_true_edges": n_pairs,
        "n_candidate_edges": len(edges),
        "candidate_multiplier": len(edges) / n_pairs,
        "candidate_recall": recall,
        "true_same_bin_share": true_same,
        "true_ses_gap": true_gap,
        "true_score_retention": true_retention,
        "raw_feasible": raw.feasible,
        "raw_lower": raw.lower,
        "raw_upper": raw.upper,
        "raw_width": raw.width,
        "raw_covers_truth": _covers(raw, true_same),
        "score_feasible": constrained.feasible,
        "score_lower": constrained.lower,
        "score_upper": constrained.upper,
        "score_width": constrained.width,
        "score_covers_truth": _covers(constrained, true_same),
        "max_score_same_bin_share": point_same,
        "max_score_absolute_error": abs(point_same - true_same),
    }


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    grouped = results.groupby("time_bin_minutes", as_index=False)
    summary = grouped.agg(
        replicates=("seed", "count"),
        candidate_recall=("candidate_recall", "mean"),
        candidate_multiplier_mean=("candidate_multiplier", "mean"),
        candidate_multiplier_sd=("candidate_multiplier", "std"),
        raw_coverage=("raw_covers_truth", "mean"),
        raw_width_mean=("raw_width", "mean"),
        raw_width_sd=("raw_width", "std"),
        score_coverage=("score_covers_truth", "mean"),
        score_width_mean=("score_width", "mean"),
        score_width_sd=("score_width", "std"),
        point_mae=("max_score_absolute_error", "mean"),
        true_score_retention_mean=("true_score_retention", "mean"),
    )
    summary["width_reduction_fraction"] = np.where(
        summary["raw_width_mean"] > 0,
        1 - summary["score_width_mean"] / summary["raw_width_mean"],
        np.nan,
    )
    return summary


def make_plot(summary: pd.DataFrame, output: Path, score_retention: float) -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-ai-pilot-bounds")
    import matplotlib.pyplot as plt

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2), constrained_layout=True)
    x = summary["time_bin_minutes"].to_numpy()
    axes[0].plot(
        x,
        summary["candidate_multiplier_mean"],
        marker="o",
        color="#0072B2",
        linewidth=2.2,
    )
    axes[0].set_xlabel("Published time-bin width (minutes)")
    axes[0].set_ylabel("Candidate edges / true edges")
    axes[0].set_title("Privacy coarsening expands ambiguity")

    axes[1].plot(
        x,
        summary["raw_width_mean"],
        marker="o",
        label="All feasible packings",
        color="#D55E00",
        linewidth=2.2,
    )
    axes[1].plot(
        x,
        summary["score_width_mean"],
        marker="s",
        label=f"Score ≥ {score_retention:.0%} of optimum",
        color="#009E73",
        linewidth=2.2,
    )
    axes[1].set_xlabel("Published time-bin width (minutes)")
    axes[1].set_ylabel("Same-SES-bin bound width")
    axes[1].set_ylim(bottom=0)
    axes[1].set_title("Set-packing bounds widen under coarsening")
    axes[1].legend(frameon=False, fontsize=9)
    fig.suptitle("Synthetic known-truth validation", fontsize=13)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_report(
    summary: pd.DataFrame,
    output: Path,
    *,
    n_pairs: int,
    score_retention: float,
) -> None:
    table = summary.copy()
    percent_cols = [
        "candidate_recall",
        "raw_coverage",
        "score_coverage",
        "width_reduction_fraction",
    ]
    for column in percent_cols:
        table[column] = table[column].map(lambda value: f"{value:.1%}" if pd.notna(value) else "NA")
    numeric_cols = [
        "candidate_multiplier_mean",
        "raw_width_mean",
        "score_width_mean",
        "point_mae",
        "true_score_retention_mean",
    ]
    for column in numeric_cols:
        table[column] = table[column].map(lambda value: f"{value:.3f}" if pd.notna(value) else "NA")
    display_cols = [
        "time_bin_minutes",
        "replicates",
        "candidate_recall",
        "candidate_multiplier_mean",
        "raw_coverage",
        "raw_width_mean",
        "score_coverage",
        "score_width_mean",
        "width_reduction_fraction",
        "point_mae",
    ]
    display = table[display_cols].astype(str)
    header = "| " + " | ".join(display.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display.columns)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in display.to_numpy().tolist()]
    markdown_table = "\n".join([header, separator, *body])
    text = f"""# Synthetic known-truth validation

This experiment creates {n_pairs} latent co-rider pairs per replicate, then
rounds their timestamps before candidate generation. It evaluates the share of
selected pairs in the same SES bin. The score-constrained interval contains
only packings with at least {score_retention:.0%} of the maximum compatibility
score; it is a sensitivity region, not a confidence interval.

{markdown_table}

## Interpretation

- Raw set-packing bounds should cover truth whenever every latent pair remains
  in the candidate graph. This is the implementation's primary coverage check.
- Coarser public time bins admit more alternative pairings and should widen the
  raw identified interval.
- Score restriction can shorten intervals, but coverage is an empirical model
  diagnostic. It must not be described as data-identified without assumptions.
- The maximum-score matching is a point reconstruction for diagnostics only.
  The pilot's estimand is the interval over feasible compatibility packings.
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicates", type=int, default=20)
    parser.add_argument("--n-pairs", type=int, default=30)
    parser.add_argument("--time-bins", type=int, nargs="+", default=[1, 5, 15, 30])
    parser.add_argument("--score-retention", type=float, default=0.95)
    parser.add_argument("--seed-start", type=int, default=1729)
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "results",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.replicates <= 0 or args.n_pairs <= 1:
        raise ValueError("replicates must be positive and n-pairs must exceed one")
    rows = []
    for replicate in range(args.replicates):
        seed = args.seed_start + replicate
        for time_bin in args.time_bins:
            rows.append(
                validate_instance(
                    seed,
                    time_bin,
                    n_pairs=args.n_pairs,
                    score_retention=args.score_retention,
                    time_limit=args.time_limit,
                )
            )
    results = pd.DataFrame(rows)
    summary = summarize(results)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output_dir / "synthetic_validation_instances.csv", index=False)
    summary.to_csv(args.output_dir / "synthetic_validation_summary.csv", index=False)
    payload = {
        "design": {
            "replicates": args.replicates,
            "n_pairs": args.n_pairs,
            "time_bins": args.time_bins,
            "score_retention": args.score_retention,
            "seed_start": args.seed_start,
        },
        "summary": summary.to_dict("records"),
    }
    (args.output_dir / "synthetic_validation.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    make_plot(summary, args.output_dir / "synthetic_bounds.png", args.score_retention)
    write_report(
        summary,
        args.output_dir / "SYNTHETIC_RESULTS.md",
        n_pairs=args.n_pairs,
        score_retention=args.score_retention,
    )
    print(summary.to_string(index=False))
    if not summary["raw_coverage"].eq(1.0).all():
        print("WARNING: raw bounds failed known-truth coverage in at least one setting")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
