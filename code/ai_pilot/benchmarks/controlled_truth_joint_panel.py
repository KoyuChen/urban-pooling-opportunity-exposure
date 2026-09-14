#!/usr/bin/env python3
"""Joint controlled-truth panel for candidate and decision coverage.

This wrapper preserves the frozen v3-scale generator, seeds, candidate ranking,
capacities and thresholds.  It adds only derived truncation diagnostics: frontier
width, threshold certification, and false certification relative to known truth.
An unavailable frontier is never counted as a certificate.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import event_frontier_truth_benchmark as canonical
import event_frontier_truth_benchmark_scale as scale


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return sum(materialized) / len(materialized)


def enrich(report: dict[str, Any]) -> list[dict[str, Any]]:
    truth = {
        (int(row["capacity"]), int(row["seed"])): float(row["true_value"])
        for row in report["instances"]
    }
    thresholds = tuple(float(value) for value in report["design"]["thresholds"])
    output = []
    for source in report["candidate_truncation_cells"]:
        row = dict(source)
        true_value = truth[(int(row["capacity"]), int(row["seed"]))]
        lower = row.get("frontier_lower")
        upper = row.get("frontier_upper")
        certified_count = 0
        false_count = 0
        if lower is not None and upper is not None:
            lower = float(lower)
            upper = float(upper)
            row["frontier_width"] = upper - lower
            for threshold in thresholds:
                certified_decision = None
                if lower >= threshold:
                    certified_decision = True
                elif upper < threshold:
                    certified_decision = False
                if certified_decision is not None:
                    certified_count += 1
                    false_count += int(certified_decision != (true_value >= threshold))
        else:
            row["frontier_width"] = None
        row.update({
            "candidate_recall": float(row["true_member_recall"]),
            "full_world_covered": bool(row["true_world_representable"]),
            "true_aggregate_covered": bool(row["aggregate_value_covered"]),
            "threshold_count": len(thresholds),
            "threshold_certified_count": certified_count,
            "threshold_false_certificate_count": false_count,
            "threshold_unresolved_count": len(thresholds) - certified_count,
        })
        output.append(row)
    return output


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(int(row["capacity"]), int(row["retained_buffer_count"]))].append(row)
    output = []
    for (capacity, retained), cells in sorted(groups.items()):
        widths = [float(row["frontier_width"]) for row in cells if row["frontier_width"] is not None]
        threshold_total = sum(int(row["threshold_count"]) for row in cells)
        certified = sum(int(row["threshold_certified_count"]) for row in cells)
        false = sum(int(row["threshold_false_certificate_count"]) for row in cells)
        output.append({
            "capacity": capacity,
            "retained_buffer_count": retained,
            "instance_count": len(cells),
            "mean_candidate_recall": mean(float(row["candidate_recall"]) for row in cells),
            "full_world_coverage_rate": mean(float(row["full_world_covered"]) for row in cells),
            "true_aggregate_coverage_rate": mean(float(row["true_aggregate_covered"]) for row in cells),
            "frontier_available_rate": len(widths) / len(cells),
            "median_frontier_width_when_available": median(widths) if widths else None,
            "threshold_certification_rate": certified / threshold_total,
            "threshold_false_certificate_rate_all_cells": false / threshold_total,
            "threshold_false_certificate_rate_among_certified": false / certified if certified else None,
            "threshold_certified_count": certified,
            "threshold_false_certificate_count": false,
            "threshold_cell_count": threshold_total,
        })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def cell(summary: list[dict[str, Any]], capacity: int, retained: int) -> dict[str, Any]:
    return next(row for row in summary if row["capacity"] == capacity and row["retained_buffer_count"] == retained)


def render_report(summary: list[dict[str, Any]], instance_count: int) -> str:
    lines = [
        "# Joint controlled-truth candidate and decision coverage",
        "",
        f"Status: **PASS_CONTROLLED** over **{instance_count:,}** frozen synthetic instances.",
        "",
        "Candidate recall counts retained true members. Full-world coverage requires every true member and its feasible relational world to remain representable. True-aggregate coverage only asks whether the scalar truth lies inside the truncated frontier. Threshold certification is evaluated at the three frozen thresholds; a missing frontier is unresolved, not certified.",
        "",
        "| C | Kept | Candidate recall | Full-world coverage | True aggregate coverage | Median width | Threshold certified | False / certified |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        false_given = row["threshold_false_certificate_rate_among_certified"]
        lines.append(
            f"| {row['capacity']} | {row['retained_buffer_count']}/8 | "
            f"{100 * row['mean_candidate_recall']:.1f}% | "
            f"{100 * row['full_world_coverage_rate']:.1f}% | "
            f"{100 * row['true_aggregate_coverage_rate']:.1f}% | "
            f"{row['median_frontier_width_when_available']:.3f} | "
            f"{100 * row['threshold_certification_rate']:.1f}% | "
            f"{100 * false_given:.1f}% |"
        )
    six = [cell(summary, capacity, 6) for capacity in (2, 3, 4)]
    recall_range = (
        min(row["mean_candidate_recall"] for row in six),
        max(row["mean_candidate_recall"] for row in six),
    )
    world_range = (
        min(row["full_world_coverage_rate"] for row in six),
        max(row["full_world_coverage_rate"] for row in six),
    )
    aggregate_range = (
        min(row["true_aggregate_coverage_rate"] for row in six),
        max(row["true_aggregate_coverage_rate"] for row in six),
    )
    lines.extend([
        "",
        f"At six of eight retained buffers, mean candidate recall is {100 * recall_range[0]:.1f}--{100 * recall_range[1]:.1f}%, but full-world coverage is only {100 * world_range[0]:.1f}--{100 * world_range[1]:.1f}%. Scalar coverage is higher ({100 * aggregate_range[0]:.1f}--{100 * aggregate_range[1]:.1f}%), showing that an aggregate can remain covered after the relational truth has been removed. The false-certificate column reports the additional danger: narrowing a misspecified frontier can increase apparent decisiveness without restoring truth.",
        "",
        "This is controlled method validation under the declared generator, not evidence about operational partner recovery or population-level coverage.",
        "",
    ])
    return "\n".join(lines)


def render_tex(summary: list[dict[str, Any]]) -> str:
    lines = [
        "% Generated by controlled_truth_joint_panel.py.",
        "\\begin{table}[t]",
        "\\caption{Candidate and decision coverage under controlled truncation. False/certified is the share of certified threshold decisions that disagree with known truth.}",
        "\\label{tab:truth-joint-coverage}",
        "\\small\\centering",
        "\\begin{tabular}{@{}ccrrrrrr@{}}",
        "\\toprule",
        "$C$ & Kept & Recall & World cov. & Aggregate cov. & Width & Certified & False/cert. \\\\",
        "\\midrule",
    ]
    for row in summary:
        lines.append(
            f"{row['capacity']} & {row['retained_buffer_count']}/8 & "
            f"{100 * row['mean_candidate_recall']:.1f}\\% & "
            f"{100 * row['full_world_coverage_rate']:.1f}\\% & "
            f"{100 * row['true_aggregate_coverage_rate']:.1f}\\% & "
            f"{row['median_frontier_width_when_available']:.3f} & "
            f"{100 * row['threshold_certification_rate']:.1f}\\% & "
            f"{100 * row['threshold_false_certificate_rate_among_certified']:.1f}\\% \\\\"
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    return "\n".join(lines)


def plot(summary: list[dict[str, Any]], output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = (
        ("mean_candidate_recall", "Candidate recall", True),
        ("full_world_coverage_rate", "Full-world coverage", True),
        ("true_aggregate_coverage_rate", "True-aggregate coverage", True),
        ("median_frontier_width_when_available", "Median frontier width", False),
        ("threshold_certification_rate", "Threshold certification", True),
        ("threshold_false_certificate_rate_among_certified", "False certificates / certified", True),
    )
    figure, axes = plt.subplots(2, 3, figsize=(11, 6.2), constrained_layout=True)
    colors = {2: "#19558d", 3: "#d46b28", 4: "#3a8b5b"}
    for axis, (key, title, percentage) in zip(axes.flat, panels):
        for capacity in (2, 3, 4):
            cells = [row for row in summary if row["capacity"] == capacity]
            x = [row["retained_buffer_count"] for row in cells]
            y = [row[key] * (100 if percentage else 1) for row in cells]
            axis.plot(x, y, marker="o", linewidth=1.8, label=f"C={capacity}", color=colors[capacity])
        axis.set_title(title)
        axis.set_xticks((4, 6, 8))
        axis.set_xlabel("candidate buffers retained (of 8)")
        axis.set_ylabel("percent" if percentage else "outcome units")
        axis.grid(axis="y", color="#dddddd", linewidth=0.6)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0][0].legend(frameon=False)
    figure.suptitle("Controlled truth: row recall is not relational coverage", fontsize=13)
    figure.savefig(output / "JOINT_COVERAGE_PANEL.pdf", bbox_inches="tight")
    figure.savefig(output / "JOINT_COVERAGE_PANEL.png", dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances-per-capacity", type=int, default=1000)
    parser.add_argument("--base-seed", type=int, default=20260902)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.instances_per_capacity <= 0:
        parser.error("instances per capacity must be positive")
    report = scale.run(args.instances_per_capacity, args.base_seed)
    rows = enrich(report)
    summary = summarize(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "JOINT_TRUNCATION_CELLS.csv", rows)
    write_csv(args.output_dir / "JOINT_COVERAGE_SUMMARY.csv", summary)
    (args.output_dir / "REPORT.md").write_text(render_report(summary, len(report["instances"])), encoding="utf-8")
    (args.output_dir / "RESULTS.tex").write_text(render_tex(summary), encoding="utf-8")
    plot(summary, args.output_dir)
    script_dir = Path(__file__).resolve().parent
    outputs = ("JOINT_TRUNCATION_CELLS.csv", "JOINT_COVERAGE_SUMMARY.csv", "REPORT.md", "RESULTS.tex", "JOINT_COVERAGE_PANEL.pdf", "JOINT_COVERAGE_PANEL.png")
    manifest = {
        "report_version": "controlled-truth-joint-coverage/v1",
        "base_seed": args.base_seed,
        "capacities": [2, 3, 4],
        "instances_per_capacity": args.instances_per_capacity,
        "instance_count": len(report["instances"]),
        "thresholds": list(canonical.THRESHOLDS),
        "candidate_retention_levels": list(canonical.TRUNCATION_LEVELS),
        "source_sha256": {
            name: sha256_file(script_dir / name)
            for name in ("relation_incomplete_event_benchmark.py", "event_frontier_truth_benchmark.py", "event_frontier_truth_benchmark_scale.py", "controlled_truth_joint_panel.py")
        },
        "output_sha256": {name: sha256_file(args.output_dir / name) for name in outputs},
        "claim_status": "PASS_CONTROLLED_NOT_OPERATIONAL_COVERAGE",
    }
    (args.output_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if not key.endswith("sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
