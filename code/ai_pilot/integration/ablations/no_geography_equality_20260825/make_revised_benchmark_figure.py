#!/usr/bin/env python3
"""Create the revised publication figure from locked and ablation outputs.

The script is read-only with respect to the locked integration benchmark.  It
distinguishes the full weak-MIL feature map (diagnostic because tract equality
is circular for the synthetic same-income target) from the no-geography-
equality weak-MIL model used as the production-primary robustness specification.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/urban_pooling_benchmark_mplconfig")

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter


HERE = Path(__file__).resolve().parent
INTEGRATION_DIR = HERE.parents[1]
AI_PILOT_DIR = INTEGRATION_DIR.parent
REPOSITORY_ROOT = AI_PILOT_DIR.parents[1]
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "paper"
    / "figures"
    / "benchmark_summary_revised.png"
)

COLORS = {
    "rule": "#6B7280",
    "full": "#D55E00",
    "no_geo": "#0072B2",
    "raw": "#9CA3AF",
    "truth": "#111827",
}
MARKERS = {"rule": "o", "full": "X", "no_geo": "D"}


def load_inputs() -> dict:
    locked_dir = INTEGRATION_DIR / "results"
    ablation_dir = HERE / "results"
    locked = json.loads((locked_dir / "benchmark_results.json").read_text(encoding="utf-8"))
    ablation = json.loads((ablation_dir / "ablation_results.json").read_text(encoding="utf-8"))
    locked_bounds = pd.read_csv(locked_dir / "heldout_same_income_bounds.csv")
    ablation_bounds = pd.read_csv(ablation_dir / "heldout_same_income_bounds.csv")

    locked_metrics = pd.DataFrame(locked["node_benchmark"]["full_metric_rows"])
    held = locked_metrics.loc[locked_metrics["subset"].eq("test_supported")].set_index("model")
    no_geo_metrics = ablation["weak_mil_ai_held_out"]

    full_rank = locked["edge_recovery"]["ranking_conditional_on_candidate_recall"]
    no_geo_rank = ablation["weak_mil_ai_true_edge_ranking"]

    # The transparent rule and untrimmed graph must be invariant to the AI-only ablation.
    invariant_scenarios = [
        "untrimmed_candidate_graph",
        "transparent_rule_retention_0.90",
        "transparent_rule_retention_0.95",
    ]
    invariant_columns = ["lower", "upper", "width", "covers_truth"]
    for scenario in invariant_scenarios:
        left = locked_bounds.loc[locked_bounds["scenario"].eq(scenario), invariant_columns]
        right = ablation_bounds.loc[ablation_bounds["scenario"].eq(scenario), invariant_columns]
        if len(left) != 1 or len(right) != 1 or not np.allclose(
            left.iloc[0][["lower", "upper", "width"]].astype(float),
            right.iloc[0][["lower", "upper", "width"]].astype(float),
        ):
            raise AssertionError(f"Invariant scenario changed in ablation: {scenario}")

    def bound_row(frame: pd.DataFrame, scenario: str) -> dict:
        rows = frame.loc[frame["scenario"].eq(scenario)]
        if len(rows) != 1:
            raise AssertionError(f"Expected one row for {scenario}, got {len(rows)}")
        return rows.iloc[0].to_dict()

    bounds = [
        {
            "label": "Untrimmed graph",
            "group": "raw",
            **bound_row(locked_bounds, "untrimmed_candidate_graph"),
        },
        {
            "label": r"Rule, $\rho=.90$",
            "group": "rule",
            **bound_row(locked_bounds, "transparent_rule_retention_0.90"),
        },
        {
            "label": r"Rule, $\rho=.95$",
            "group": "rule",
            **bound_row(locked_bounds, "transparent_rule_retention_0.95"),
        },
        {
            "label": r"Full MIL, $\rho=.90$",
            "group": "full",
            **bound_row(locked_bounds, "weak_mil_ai_retention_0.90"),
        },
        {
            "label": r"Full MIL, $\rho=.95$",
            "group": "full",
            **bound_row(locked_bounds, "weak_mil_ai_retention_0.95"),
        },
        {
            "label": r"No-equality MIL, $\rho=.90$",
            "group": "no_geo",
            **bound_row(ablation_bounds, "weak_mil_ai_retention_0.90"),
        },
        {
            "label": r"No-equality MIL, $\rho=.95$",
            "group": "no_geo",
            **bound_row(ablation_bounds, "weak_mil_ai_retention_0.95"),
        },
    ]

    truth_values = {float(row["truth_same_income_bin_share"]) for row in bounds}
    if len(truth_values) != 1:
        raise AssertionError(f"Inconsistent hidden truth values: {truth_values}")

    return {
        "brier": {
            "rule": float(held.loc["transparent_rule", "brier"]),
            "full": float(held.loc["weak_mil_ai", "brier"]),
            "no_geo": float(no_geo_metrics["brier"]),
        },
        "ranking": {
            "rule": {
                "mrr": float(full_rank["transparent_rule"]["mean_reciprocal_rank"]),
                "top1": float(full_rank["transparent_rule"]["top_1_rate"]),
            },
            "full": {
                "mrr": float(full_rank["weak_mil_ai"]["mean_reciprocal_rank"]),
                "top1": float(full_rank["weak_mil_ai"]["top_1_rate"]),
            },
            "no_geo": {
                "mrr": float(no_geo_rank["mean_reciprocal_rank"]),
                "top1": float(no_geo_rank["top_1_rate"]),
            },
        },
        "bounds": bounds,
        "truth": truth_values.pop(),
        "no_geo_score_eligibility": {
            str(row["score_retention"]): bool(row["truth_score_eligible"])
            for row in bounds
            if row["group"] == "no_geo"
        },
    }


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.0,
            "axes.titlesize": 9.0,
            "axes.labelsize": 8.0,
            "xtick.labelsize": 7.4,
            "ytick.labelsize": 7.4,
            "legend.fontsize": 7.2,
            "axes.linewidth": 0.7,
            "axes.edgecolor": "#374151",
            "axes.labelcolor": "#111827",
            "xtick.color": "#374151",
            "ytick.color": "#374151",
            "grid.color": "#D1D5DB",
            "grid.linewidth": 0.55,
            "grid.alpha": 0.7,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def draw_figure(data: dict, output: Path, dpi: int) -> None:
    configure_style()
    fig = plt.figure(figsize=(12.4, 3.65))
    grid = fig.add_gridspec(
        1,
        3,
        width_ratios=(0.88, 1.15, 1.82),
        left=0.055,
        right=0.985,
        bottom=0.22,
        top=0.83,
        wspace=0.43,
    )
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[0, 2])

    display = {
        "rule": "Transparent rule",
        "full": "Full MIL\n(diagnostic)",
        "no_geo": "No-equality MIL\n(primary)",
    }
    order = ["rule", "full", "no_geo"]

    # Panel A: a log-scale dot plot keeps the two small MIL Brier scores legible.
    y = np.arange(len(order))[::-1]
    for yi, key in zip(y, order):
        value = data["brier"][key]
        ax_a.hlines(yi, 0.004, value, color=COLORS[key], linewidth=1.25, alpha=0.7)
        ax_a.scatter(
            value,
            yi,
            s=48,
            color=COLORS[key],
            marker=MARKERS[key],
            edgecolor="white",
            linewidth=0.55,
            zorder=3,
        )
        ax_a.annotate(
            f"{value:.4f}",
            (value, yi),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=7.2,
            color=COLORS[key],
            fontweight="bold" if key == "no_geo" else "normal",
        )
    ax_a.set_xscale("log")
    ax_a.set_xlim(0.004, 0.09)
    ax_a.xaxis.set_major_locator(FixedLocator([0.005, 0.01, 0.02, 0.05]))
    ax_a.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    ax_a.set_yticks(y, [display[key] for key in order])
    ax_a.set_ylim(-0.65, 2.65)
    ax_a.grid(axis="x", which="major")
    ax_a.set_xlabel("Brier score (log scale; lower is better)")
    ax_a.set_title("(a) Held-out node prediction", loc="left", fontweight="bold")
    for spine in ("top", "right", "left"):
        ax_a.spines[spine].set_visible(False)
    ax_a.tick_params(axis="y", length=0)

    # Panel B: point ranges avoid implying a zero baseline for bounded rank metrics.
    metric_labels = ["MRR", "Top-1"]
    metric_keys = ["mrr", "top1"]
    x = np.arange(len(metric_keys), dtype=float)
    offsets = {"rule": -0.17, "full": 0.0, "no_geo": 0.17}
    for key in order:
        values = [data["ranking"][key][metric] for metric in metric_keys]
        xx = x + offsets[key]
        ax_b.plot(
            xx,
            values,
            color=COLORS[key],
            linewidth=1.15,
            alpha=0.75,
            zorder=2,
        )
        ax_b.scatter(
            xx,
            values,
            s=45,
            color=COLORS[key],
            marker=MARKERS[key],
            edgecolor="white",
            linewidth=0.55,
            label=display[key].replace("\n", " "),
            zorder=3,
        )
        for xi, value in zip(xx, values):
            ax_b.annotate(
                f"{value:.2f}",
                (xi, value),
                xytext=(0, 6 if key != "full" else -10),
                textcoords="offset points",
                ha="center",
                va="bottom" if key != "full" else "top",
                color=COLORS[key],
                fontsize=6.8,
                fontweight="bold" if key == "no_geo" else "normal",
            )
    ax_b.set_xticks(x, metric_labels)
    ax_b.set_xlim(-0.42, 1.42)
    ax_b.set_ylim(0.58, 1.01)
    ax_b.set_yticks([0.6, 0.7, 0.8, 0.9, 1.0])
    ax_b.grid(axis="y")
    ax_b.set_ylabel("Rank metric (higher is better)")
    ax_b.set_title("(b) Hidden true-edge ranking", loc="left", fontweight="bold")
    ax_b.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.47),
        ncol=1,
        frameon=False,
        handletextpad=0.5,
        borderaxespad=0,
        labelspacing=0.25,
    )
    for spine in ("top", "right"):
        ax_b.spines[spine].set_visible(False)

    # Panel C: horizontal partial-identification intervals and hidden truth.
    bounds = data["bounds"]
    yy = np.arange(len(bounds))[::-1]
    linestyles = {"raw": (0, (2, 2)), "rule": "solid", "full": (0, (4, 2)), "no_geo": "solid"}
    markers = {"raw": "o", "rule": "o", "full": "X", "no_geo": "D"}
    for yi, row in zip(yy, bounds):
        key = row["group"]
        lower = float(row["lower"])
        upper = float(row["upper"])
        color = COLORS[key]
        width = 2.3 if key == "no_geo" else 1.65
        alpha = 1.0 if key in {"no_geo", "full"} else 0.86
        ax_c.hlines(
            yi,
            lower,
            upper,
            color=color,
            linewidth=width,
            linestyle=linestyles[key],
            alpha=alpha,
            zorder=2,
        )
        ax_c.scatter(
            [lower, upper],
            [yi, yi],
            s=24 if key == "no_geo" else 18,
            color=color,
            marker=markers[key],
            edgecolor="white",
            linewidth=0.45,
            zorder=3,
        )
    truth = float(data["truth"])
    ax_c.axvline(truth, color=COLORS["truth"], linewidth=1.25, linestyle=(0, (2, 2)), zorder=1)
    ax_c.annotate(
        f"hidden truth = {truth:.4f}",
        xy=(truth, yy[0] + 0.35),
        xytext=(3, 0),
        textcoords="offset points",
        ha="left",
        va="bottom",
        fontsize=7.2,
        color=COLORS["truth"],
        fontweight="bold",
    )
    # Full MIL at rho=.95 is the only displayed interval that misses truth.
    full_95_y = yy[[row["label"].startswith("Full MIL") for row in bounds].index(True) + 1]
    ax_c.scatter(
        truth,
        full_95_y,
        marker="x",
        s=32,
        color=COLORS["full"],
        linewidth=1.2,
        zorder=4,
    )
    ax_c.annotate(
        "excludes truth",
        xy=(truth, full_95_y),
        xytext=(-5, -10),
        textcoords="offset points",
        ha="right",
        va="top",
        fontsize=6.7,
        color=COLORS["full"],
    )
    ax_c.set_yticks(yy, [row["label"] for row in bounds])
    for tick, row in zip(ax_c.get_yticklabels(), bounds):
        tick.set_color(COLORS[row["group"]])
        if row["group"] == "no_geo":
            tick.set_fontweight("bold")
    ax_c.set_xlim(0.0, 0.82)
    ax_c.set_xticks([0.0, 0.2, 0.4, 0.6, 0.8])
    ax_c.set_ylim(-0.65, len(bounds) - 0.35)
    ax_c.grid(axis="x")
    ax_c.tick_params(axis="y", length=0)
    ax_c.set_xlabel("Feasible same-income-bin share")
    ax_c.set_title("(c) Set-packing identification intervals", loc="left", fontweight="bold")
    for spine in ("top", "right", "left"):
        ax_c.spines[spine].set_visible(False)

    fig.suptitle(
        "Known-truth synthetic benchmark (not an empirical Chicago estimate)",
        x=0.055,
        y=0.965,
        ha="left",
        fontsize=10.2,
        fontweight="bold",
        color="#111827",
    )
    fig.text(
        0.985,
        0.965,
        "Full MIL: diagnostic feature map  |  No-equality MIL: production-primary",
        ha="right",
        va="top",
        fontsize=7.3,
        color="#4B5563",
    )
    fig.text(
        0.985,
        0.035,
        r"Intervals retain at least $\rho$ of the model-optimal matching score; hidden pairs never enter training.",
        ha="right",
        va="bottom",
        fontsize=6.8,
        color="#4B5563",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dpi", type=int, default=360)
    args = parser.parse_args()
    data = load_inputs()
    draw_figure(data, args.output, args.dpi)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "no_geo_hidden_true_packing_score_eligible": data[
                    "no_geo_score_eligibility"
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
