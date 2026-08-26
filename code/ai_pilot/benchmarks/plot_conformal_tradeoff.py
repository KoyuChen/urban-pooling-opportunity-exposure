#!/usr/bin/env python3
"""Render the deterministic conformal benchmark as editable vector graphics.

The script reads only the exact-enumeration frontier CSV.  It does not rerun
or aggregate the benchmark.  PDF text is embedded as Type 42 and SVG text
remains editable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd


HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = (
    HERE / "results" / "conformal_matching" / "exact_conformal_frontier.csv"
)
DEFAULT_OUTPUT = HERE.parents[2] / "paper" / "figures" / "conformal_tradeoff"


def render(frontier_path: Path, output_stem: Path) -> None:
    frame = pd.read_csv(frontier_path)
    expected = {"target_free", "query_leaking"}
    if set(frame["scorer"]) != expected:
        raise ValueError(f"expected scorer rows {sorted(expected)}")

    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.0,
            "axes.labelsize": 8.0,
            "axes.titlesize": 8.5,
            "legend.fontsize": 7.4,
            "xtick.labelsize": 7.2,
            "ytick.labelsize": 7.2,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )

    colors = {"target_free": "#0072B2", "query_leaking": "#D55E00"}
    labels = {"target_free": "Target-free", "query_leaking": "Query-leaking"}
    panels = [
        ("Matching-set retention", "matching_coverage"),
        ("Downstream-query coverage", "statistic_coverage"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.55), sharey=True)
    for axis, (title, coverage_column) in zip(axes, panels, strict=True):
        axis.axvspan(90, 100, color="#009E73", alpha=0.07, linewidth=0)
        axis.axvline(90, color="#777777", linestyle=(0, (3, 2)), linewidth=0.8)
        for scorer in ("target_free", "query_leaking"):
            scorer_rows = frame.loc[frame["scorer"].eq(scorer)]
            grid = scorer_rows.loc[scorer_rows["radius_kind"].eq("grid")].sort_values(
                "radius"
            )
            calibrated_row = scorer_rows.loc[
                scorer_rows["radius_kind"].eq("calibrated")
            ].iloc[0]
            arbitrary_row = grid.loc[grid["radius"].sub(0.05).abs().le(1e-12)].iloc[0]
            axis.plot(
                100 * grid[coverage_column],
                100 * grid["mean_width_reduction"],
                color=colors[scorer],
                linewidth=1.15,
                alpha=0.78,
                zorder=1,
            )
            arbitrary = (
                100 * float(arbitrary_row[coverage_column]),
                100 * float(arbitrary_row["mean_width_reduction"]),
            )
            calibrated = (
                100 * float(calibrated_row[coverage_column]),
                100 * float(calibrated_row["mean_width_reduction"]),
            )
            axis.annotate(
                "",
                xy=calibrated,
                xytext=arbitrary,
                arrowprops={
                    "arrowstyle": "-|>",
                    "color": colors[scorer],
                    "linewidth": 1.15,
                    "mutation_scale": 8,
                    "shrinkA": 5,
                    "shrinkB": 5,
                },
            )
            axis.scatter(
                *arbitrary,
                marker="X",
                s=42,
                color=colors[scorer],
                edgecolor="white",
                linewidth=0.45,
                zorder=3,
            )
            axis.scatter(
                *calibrated,
                marker="o",
                s=38,
                color=colors[scorer],
                edgecolor="white",
                linewidth=0.45,
                zorder=3,
            )
        axis.set_title(title, pad=5)
        axis.set_xlabel("True object retained / covered (%)")
        axis.set_xlim(0, 102)
        axis.set_ylim(0, 102)
        axis.set_xticks([0, 25, 50, 75, 90, 100])
        axis.set_yticks([0, 25, 50, 75, 100])
        axis.grid(True, color="#dddddd", linewidth=0.55)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Range-width reduction (%)")

    color_handles = [
        mpl.lines.Line2D(
            [], [], color=colors[name], marker="o", linestyle="-", label=labels[name]
        )
        for name in ("target_free", "query_leaking")
    ]
    marker_handles = [
        mpl.lines.Line2D(
            [], [], color="#555555", marker="X", linestyle="none", label="Radius 0.05"
        ),
        mpl.lines.Line2D(
            [], [], color="#555555", marker="o", linestyle="none", label="Calibrated"
        ),
    ]
    fig.legend(
        handles=[*color_handles, *marker_handles],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.015),
        ncol=4,
        frameon=False,
        handletextpad=0.45,
        columnspacing=1.4,
    )
    fig.subplots_adjust(left=0.08, right=0.99, top=0.88, bottom=0.26, wspace=0.18)

    output_stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_stem.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.02)
    fig.savefig(output_stem.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontier", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-stem", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    render(args.frontier, args.output_stem)


if __name__ == "__main__":
    main()
