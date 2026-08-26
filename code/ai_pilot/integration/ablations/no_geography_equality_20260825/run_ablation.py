#!/usr/bin/env python3
"""Ablate geography-equality features from the weak-MIL edge scorer.

This script reads the locked synthetic public files and design, reconstructs
the locked candidate graph, verifies it is identical to the benchmark graph,
and changes only the weak-MIL feature matrix.  It does not overwrite any
locked benchmark output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
INTEGRATION_DIR = HERE.parents[1]
AI_PILOT_DIR = INTEGRATION_DIR.parent
if str(AI_PILOT_DIR) not in sys.path:
    sys.path.insert(0, str(AI_PILOT_DIR))

import model.run_weak_edge_pilot as weak_model  # noqa: E402
from integration.run_integration_benchmark import (  # noqa: E402
    edge_recovery_metrics,
    run_bounds,
)


DROP_FEATURES = {
    "pickup_area_same",
    "dropoff_area_same",
    "pickup_tract_same",
    "dropoff_tract_same",
    "same_area_both",
    "same_tract_both",
}


def json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON encode {type(value)!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locked-result-dir",
        type=Path,
        default=INTEGRATION_DIR / "results",
        help="Locked integration output containing synthetic public files and the full-model graph.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "results_rerun",
        help="New directory for ablation outputs; existing directories are never overwritten.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    design_path = INTEGRATION_DIR / "DESIGN_LOCK.json"
    locked_result_dir = args.locked_result_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    model_dir = output_dir / "model"
    model_dir.mkdir()

    design = json.loads(design_path.read_text(encoding="utf-8"))
    public_paths = [
        locked_result_dir
        / "synthetic_data"
        / f"synthetic_chicago_authorized_{day}.csv"
        for day in design["days"]
    ]
    node_truth = pd.read_csv(
        locked_result_dir / "synthetic_data" / "hidden_node_truth_NOT_MODEL_INPUT.csv"
    )
    pair_truth = pd.read_csv(
        locked_result_dir / "synthetic_data" / "hidden_pair_truth_NOT_MODEL_INPUT.csv"
    )

    original_feature_builder = weak_model.make_feature_matrices
    feature_audit: dict[str, list[str]] = {}

    def ablated_feature_builder(edges, cfg, feature_set="full"):
        full_x, full_names, rule_raw = original_feature_builder(edges, cfg, "full")
        keep = [index for index, name in enumerate(full_names) if name not in DROP_FEATURES]
        kept_names = [full_names[index] for index in keep]
        dropped_names = [name for name in full_names if name in DROP_FEATURES]
        if set(dropped_names) != DROP_FEATURES:
            raise AssertionError(
                f"Expected geography features {sorted(DROP_FEATURES)}, found {dropped_names}"
            )
        feature_audit.update(
            {
                "full_feature_names": full_names,
                "dropped_feature_names": dropped_names,
                "kept_feature_names": kept_names,
            }
        )
        return full_x[:, keep], kept_names, rule_raw

    weak_model.make_feature_matrices = ablated_feature_builder
    cfg = design["candidate_and_model"]
    argv: list[str] = []
    for path in public_paths:
        argv.extend(["--input", str(path)])
    argv.extend(
        [
            "--output-dir",
            str(model_dir),
            "--test-date",
            str(design["held_out_day"]),
            "--max-start-delta-min",
            str(cfg["max_start_delta_min"]),
            "--max-pickup-km",
            str(cfg["max_pickup_km"]),
            "--max-dropoff-km",
            str(cfg["max_dropoff_km"]),
            "--min-direction-cosine",
            str(cfg["min_direction_cosine"]),
            "--max-candidates-per-node",
            str(cfg["max_candidates_per_node"]),
            "--neighbor-search-k",
            str(cfg["neighbor_search_k"]),
            "--ai-l2",
            str(cfg["ai_l2"]),
            "--rule-l2",
            str(cfg["rule_l2"]),
            "--max-iter",
            str(cfg["max_iter"]),
            "--feature-set",
            "no_geography_equality",
        ]
    )
    model_args = weak_model.build_parser().parse_args(argv)
    model_card = weak_model.run(model_args)
    weak_model.make_feature_matrices = original_feature_builder

    node_predictions = pd.read_csv(model_dir / "node_predictions.csv")
    scored_edges = pd.read_csv(model_dir / "scored_candidate_edges.csv.gz")
    metrics = pd.read_csv(model_dir / "node_level_metrics.csv")
    locked_edges = pd.read_csv(
        locked_result_dir / "model" / "scored_candidate_edges.csv.gz"
    )

    graph_columns = ["src", "dst", "event_day", "split"]
    graph_equal = scored_edges[graph_columns].equals(locked_edges[graph_columns])
    if not graph_equal:
        raise AssertionError("Ablation candidate graph differs from the locked benchmark graph")

    held_out_day = str(design["held_out_day"])
    edge_metrics, ranks = edge_recovery_metrics(
        scored_edges, node_predictions, pair_truth, held_out_day
    )
    ranks.to_csv(output_dir / "heldout_true_edge_ranks.csv", index=False)
    bound_results, bound_rows = run_bounds(
        scored_edges,
        node_predictions,
        node_truth,
        pair_truth,
        held_out_day,
        design["set_packing"],
    )
    bound_rows.to_csv(output_dir / "heldout_same_income_bounds.csv", index=False)

    held_metrics = metrics.loc[metrics["subset"].eq("test_supported")].copy()
    held_metrics.to_csv(output_dir / "heldout_node_metrics.csv", index=False)
    ai_metrics = held_metrics.loc[held_metrics["model"].eq("weak_mil_ai")].iloc[0].to_dict()
    ai_ranks = edge_metrics["ranking_conditional_on_candidate_recall"]["weak_mil_ai"]
    ai_bounds = {
        retention: bound_results["scenarios"][f"weak_mil_ai_retention_{retention}"]
        for retention in ("0.90", "0.95")
    }

    locked_results = json.loads(
        (locked_result_dir / "benchmark_results.json").read_text(encoding="utf-8")
    )
    locked_ai_metrics = next(
        row
        for row in locked_results["node_benchmark"]["full_metric_rows"]
        if row["subset"] == "test_supported" and row["model"] == "weak_mil_ai"
    )
    locked_ai_ranks = locked_results["edge_recovery"][
        "ranking_conditional_on_candidate_recall"
    ]["weak_mil_ai"]

    result = {
        "ablation": "remove exact community-area and census-tract equality indicators from weak-MIL",
        "locked_inputs_reused": [str(path) for path in public_paths],
        "design_lock": str(design_path),
        "candidate_graph_identical_to_locked": graph_equal,
        "candidate_edge_count": int(len(scored_edges)),
        "held_out_candidate_edge_count": int(
            scored_edges["event_day"].eq(held_out_day).sum()
        ),
        "feature_audit": feature_audit,
        "transparent_rule_note": (
            "The disclosed transparent-rule baseline is unchanged; only the weak-MIL AI "
            "feature matrix is ablated."
        ),
        "held_out_node_metrics": held_metrics.to_dict(orient="records"),
        "weak_mil_ai_held_out": ai_metrics,
        "true_edge_recovery": edge_metrics,
        "weak_mil_ai_true_edge_ranking": ai_ranks,
        "same_income_bounds": bound_results,
        "weak_mil_ai_bounds": ai_bounds,
        "locked_full_model_comparison": {
            "weak_mil_ai_held_out": locked_ai_metrics,
            "weak_mil_ai_true_edge_ranking": locked_ai_ranks,
        },
        "circularity_assessment": {
            "exact_tract_indicator": (
                "Severe in this synthetic design: pickup tract is constructed from corridor and "
                "income bin, so pickup-tract equality can directly reveal equality of the target bin."
            ),
            "area_indicator": (
                "Not logically identical to the income-bin outcome, but route/wave areas are shared "
                "by construction and can proxy the opportunity set."
            ),
            "remaining_risk_after_ablation": (
                "Nonzero: income bins also create deterministic coordinate offsets, so continuous "
                "pickup/dropoff distances still carry SES information."
            ),
            "interpretation": (
                "Treat score-retention bounds as model-dependent sensitivity regions, not pure "
                "evidence of preference homophily. Untrimmed graph bounds do not use scores, though "
                "the candidate graph still conditions on spatial opportunity."
            ),
        },
        "model_card": model_card,
    }
    (output_dir / "ablation_results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=json_default) + "\n",
        encoding="utf-8",
    )

    report = f"""# Weak-MIL geography-equality feature ablation

This is a known-truth synthetic robustness check, not a Chicago estimate. The
locked public-record CSVs, train/test dates, candidate configuration, candidate
graph, regularization, and optimizer settings are unchanged. Only six weak-MIL
features were removed: `{', '.join(feature_audit['dropped_feature_names'])}`.
The transparent-rule baseline is intentionally unchanged.

## Held-out results

- Candidate graph equality check: **{graph_equal}** ({len(scored_edges):,} total
  candidate edges; {int(scored_edges['event_day'].eq(held_out_day).sum()):,} held out).
- Weak-MIL node Brier: **{ai_metrics['brier']:.6f}**; log loss
  **{ai_metrics['log_loss']:.6f}**; ECE **{ai_metrics['ece_10_bins']:.6f}**;
  ROC AUC **{ai_metrics['roc_auc']:.3f}**; AP **{ai_metrics['average_precision']:.3f}**.
- Hidden true-edge ranking (160 matched endpoints): MRR
  **{ai_ranks['mean_reciprocal_rank']:.6f}**, top-1
  **{ai_ranks['top_1_rate']:.2%}**, top-3 **{ai_ranks['top_3_rate']:.2%}**.
- AI score-retention 0.90 bound: **[{ai_bounds['0.90']['lower']:.4f},
  {ai_bounds['0.90']['upper']:.4f}]**; truth 0.5625;
  coverage **{ai_bounds['0.90']['covers_truth']}**.
- AI score-retention 0.95 bound: **[{ai_bounds['0.95']['lower']:.4f},
  {ai_bounds['0.95']['upper']:.4f}]**; truth 0.5625;
  coverage **{ai_bounds['0.95']['covers_truth']}**.

## Circularity assessment

In the locked generator, pickup census tract equals a corridor-specific code
plus the synthetic income bin. Therefore `pickup_tract_same` can mechanically
encode the same-income-bin target; retaining it while narrowing same-income
bounds is circular. Community-area equality is a coarser opportunity proxy, not
an algebraic copy of the target. This ablation removes those exact equalities,
but it is not a complete de-circularization because income bins also generate
fixed spatial coordinate offsets. The score-retention bounds must therefore be
described as model-dependent sensitivity regions. The untrimmed candidate-graph
bounds are score-free, although their estimand remains conditional on spatial
opportunity.
"""
    (output_dir / "ABLATION_REPORT.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
