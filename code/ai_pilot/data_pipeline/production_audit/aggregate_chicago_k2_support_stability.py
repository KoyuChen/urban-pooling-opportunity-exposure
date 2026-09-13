#!/usr/bin/env python3
"""Aggregate sealed Chicago K=2 support-sensitivity curves across windows.

The analysis is paired within each completed window.  It never treats curve
cells as independent cohorts, excludes missing public outcomes from numerical
denominators, and retains computationally unresolved endpoint pairs as such.
For budgets whose full-support value differs by window, the terminal point is
identified within each window rather than pooled by its raw Gamma value.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import chicago_k2_followup as followup


CERTIFIED = "CERTIFIED_OPTIMAL_PAIR"
MISSING = "UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES"
COMMON_POINTS = {
    "radius": ("0 km", "0.25 km", "0.5 km", "1 km", "2 km", "4 km", "8 km", "16 km", "32 km", "temporal-only"),
    "gamma": ("0", "1", "2", "4", "8", "full-support"),
    "candidate_omission": ("0", "1", "2", "4", "8", "full-support"),
    "buffer_padding": ("0 min", "15 min"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quantile(values: Iterable[float], probability: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def numerical_status(row: dict[str, str]) -> str:
    if row.get("endpoint_pair_certification") == CERTIFIED:
        return "CERTIFIED"
    if row.get("lower_status") == MISSING or row.get("upper_status") == MISSING:
        return "MISSING_PUBLIC_VALUE"
    return "COMPUTATIONALLY_UNRESOLVED"


def parameter_order(row: dict[str, str]) -> float:
    value = row.get("parameter_value", "")
    if value == "" and row.get("curve_type") == "radius":
        return math.inf
    return float(value)


def load_rows(root: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    followup.verify(root)
    report = json.loads((root / "followup_report.json").read_text(encoding="utf-8"))
    if report.get("gate_status") != "PASS_EXECUTION":
        raise ValueError("support aggregation requires a PASS_EXECUTION checkpoint")
    rows: list[dict[str, Any]] = []
    pins: dict[str, str] = {}
    for path in sorted(root.glob("cohort_*/candidate_support_sensitivity.csv")):
        slug = path.parent.name
        pins[str(path.relative_to(root))] = sha256_file(path)
        with path.open(newline="", encoding="utf-8") as handle:
            for source in csv.DictReader(handle):
                row: dict[str, Any] = dict(source)
                row["window"] = slug
                row["numerical_status"] = numerical_status(source)
                if row["numerical_status"] == "CERTIFIED":
                    row["width_value"] = float(source["width"])
                rows.append(row)
    if len(pins) != int(report["completed_window_count"]):
        raise ValueError("completed-window count and sensitivity-file count differ")
    certified = sum(row["numerical_status"] == "CERTIFIED" for row in rows)
    missing = sum(row["numerical_status"] == "MISSING_PUBLIC_VALUE" for row in rows)
    unresolved = len(rows) - certified - missing
    expected = (
        int(report["endpoint_pair_count"]),
        int(report["certified_endpoint_pair_count"]),
        int(report["missing_public_query_value_endpoint_pair_count"]),
        int(report["computationally_unresolved_endpoint_pair_count"]),
    )
    if (len(rows), certified, missing, unresolved) != expected:
        raise ValueError("sensitivity rows do not reproduce the sealed aggregate counts")
    return rows, pins


def terminal_labels(rows: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    labels: dict[tuple[str, str], tuple[float, str]] = {}
    for row in rows:
        key = (row["window"], row["curve_type"])
        candidate = (parameter_order(row), row["parameter_label"])
        if key not in labels or candidate[0] > labels[key][0]:
            labels[key] = candidate
    return {key: label for key, (_, label) in labels.items()}


def canonical_labels(row: dict[str, Any], terminal: dict[tuple[str, str], str]) -> tuple[str, ...]:
    curve = row["curve_type"]
    label = row["parameter_label"]
    labels = []
    if label in COMMON_POINTS[curve]:
        labels.append(label)
    if curve in {"gamma", "candidate_omission"} and label == terminal[(row["window"], curve)]:
        labels.append("full-support")
    return tuple(dict.fromkeys(labels))


def summarize_points(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terminal = terminal_labels(rows)
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for label in canonical_labels(row, terminal):
            grouped[(row["curve_type"], row["query"], row["unit"], label)].append(row)
    output = []
    for (curve, query, unit, label), items in sorted(grouped.items()):
        widths = [item["width_value"] for item in items if item["numerical_status"] == "CERTIFIED"]
        certified = len(widths)
        missing = sum(item["numerical_status"] == "MISSING_PUBLIC_VALUE" for item in items)
        unresolved = len(items) - certified - missing
        data_complete = certified + unresolved
        output.append({
            "curve_type": curve,
            "query": query,
            "unit": unit,
            "parameter_label": label,
            "window_count": len(items),
            "certified_count": certified,
            "missing_public_value_count": missing,
            "computationally_unresolved_count": unresolved,
            "data_complete_certification_rate": certified / data_complete if data_complete else None,
            "width_q25": quantile(widths, 0.25),
            "width_median": median(widths) if widths else None,
            "width_q75": quantile(widths, 0.75),
        })
    return output


def summarize_stability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terminal = terminal_labels(rows)
    by_chain: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        for label in canonical_labels(row, terminal):
            by_chain[(row["window"], row["curve_type"], row["query"])][label] = row
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for (_, curve, query), points in by_chain.items():
        base_label = COMMON_POINTS[curve][0]
        terminal_label = COMMON_POINTS[curve][-1]
        base, end = points.get(base_label), points.get(terminal_label)
        if not base or not end or base["numerical_status"] != "CERTIFIED" or end["numerical_status"] != "CERTIFIED":
            continue
        denominator = max(abs(end["width_value"]), 1e-12)
        for label in COMMON_POINTS[curve]:
            point = points.get(label)
            if point is None or point["numerical_status"] != "CERTIFIED":
                continue
            grouped[(curve, query, label)].append({
                "absolute_distance_to_full": abs(end["width_value"] - point["width_value"]),
                "relative_distance_to_full": abs(end["width_value"] - point["width_value"]) / denominator,
                "base_to_full_change": end["width_value"] - base["width_value"],
            })
    output = []
    for (curve, query, label), items in sorted(grouped.items()):
        relative = [item["relative_distance_to_full"] for item in items]
        changes = [item["base_to_full_change"] for item in items]
        output.append({
            "curve_type": curve,
            "query": query,
            "parameter_label": label,
            "paired_window_count": len(items),
            "within_1pct_of_full_count": sum(value <= 0.01 for value in relative),
            "within_1pct_of_full_fraction": sum(value <= 0.01 for value in relative) / len(relative),
            "relative_distance_to_full_median": median(relative),
            "base_to_full_change_median": median(changes),
            "base_to_full_change_q25": quantile(changes, 0.25),
            "base_to_full_change_q75": quantile(changes, 0.75),
        })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def select(rows: list[dict[str, Any]], curve: str, query: str, label: str) -> dict[str, Any]:
    return next(row for row in rows if row["curve_type"] == curve and row["query"] == query and row["parameter_label"] == label)


def render_report(points: list[dict[str, Any]], stability: list[dict[str, Any]]) -> str:
    query = "mean_absolute_duration_gap_per_core"
    radius_base = select(points, "radius", query, "0 km")
    radius_full = select(points, "radius", query, "temporal-only")
    radius_pair = select(stability, "radius", query, "temporal-only")
    omission_8 = select(stability, "candidate_omission", query, "8")
    return (
        "# Chicago K=2 cross-window support sensitivity\n\n"
        "Status: **DESCRIPTIVE_FIXED_CALENDAR**. The unit is a completed window; curve cells are not treated as independent cohorts.\n\n"
        f"Across the 90 completed windows, median duration-frontier width increased from "
        f"{radius_base['width_median']:.3f} minutes/core at the 0-km measured-radius support "
        f"to {radius_full['width_median']:.3f} minutes/core under temporal-only support. "
        f"The paired median increase was {radius_pair['base_to_full_change_median']:.3f} minutes/core. "
        f"At generic omitted-incidence budget 8, {omission_8['within_1pct_of_full_count']}/"
        f"{omission_8['paired_window_count']} paired, numerically certified chains were within 1% of their own full-support width.\n\n"
        "These are fixed-calendar descriptive stability summaries, not sampling uncertainty, population estimates, or evidence that the public candidate universe contains the hidden true partner relation. Missing public outcomes are excluded from numerical denominators; computationally unresolved pairs remain unresolved.\n"
    )


def render_tex(points: list[dict[str, Any]], stability: list[dict[str, Any]]) -> str:
    query = "mean_absolute_duration_gap_per_core"
    base = select(points, "radius", query, "0 km")
    full = select(points, "radius", query, "temporal-only")
    paired = select(stability, "radius", query, "temporal-only")
    omission = select(stability, "candidate_omission", query, "8")
    return (
        "% Generated by aggregate_chicago_k2_support_stability.py.\n"
        "\\paragraph{Cross-window support sensitivity.} "
        f"Across 90 completed fixed-calendar windows, the median duration-frontier width rose from {base['width_median']:.3f} "
        f"minutes per core trip at the 0-km measured-radius support to {full['width_median']:.3f} under temporal-only support. "
        f"The paired median increase was {paired['base_to_full_change_median']:.3f} minutes per core trip. "
        f"At omitted-incidence budget $\\Gamma=8$, {omission['within_1pct_of_full_count']} of {omission['paired_window_count']} "
        "paired numerically certified chains were within 1\\% of their own full-support width. "
        "Cells within a curve are not independent cohorts; these fixed-calendar summaries are descriptive and conditional on the declared public candidate universe.\n"
    )


def plot_support_curves(points: list[dict[str, Any]], output_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    queries = (
        ("mean_absolute_trip_miles_gap_per_core", "Trip-distance frontier width", "miles/core"),
        ("mean_absolute_duration_gap_per_core", "Duration frontier width", "minutes/core"),
    )
    curves = (
        ("radius", "Candidate radius", COMMON_POINTS["radius"]),
        ("candidate_omission", "Omitted-incidence budget", COMMON_POINTS["candidate_omission"]),
    )
    figure, axes = plt.subplots(2, 2, figsize=(10.5, 6.4), constrained_layout=True)
    for row_index, (query, y_title, unit) in enumerate(queries):
        for column_index, (curve, x_title, labels) in enumerate(curves):
            axis = axes[row_index][column_index]
            selected = [select(points, curve, query, label) for label in labels]
            x = list(range(len(labels)))
            medians = [item["width_median"] for item in selected]
            q25 = [item["width_q25"] for item in selected]
            q75 = [item["width_q75"] for item in selected]
            axis.fill_between(x, q25, q75, color="#8bb8df", alpha=0.35, linewidth=0)
            axis.plot(x, medians, color="#19558d", marker="o", linewidth=1.8, markersize=3.8)
            axis.set_xticks(x, labels, rotation=35 if curve == "radius" else 0, ha="right" if curve == "radius" else "center")
            axis.set_xlabel(x_title)
            axis.set_ylabel(unit)
            axis.set_title(y_title)
            axis.grid(axis="y", color="#d7d7d7", linewidth=0.6)
            axis.spines[["top", "right"]].set_visible(False)
    figure.suptitle("Chicago K=2 support sensitivity across 90 completed windows\nmedian and interquartile range", fontsize=12)
    figure.savefig(output_dir / "SUPPORT_STABILITY_CURVES.pdf", bbox_inches="tight")
    figure.savefig(output_dir / "SUPPORT_STABILITY_CURVES.png", dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows, pins = load_rows(args.checkpoint_dir)
    points = summarize_points(rows)
    stability = summarize_stability(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "SUPPORT_POINT_SUMMARY.csv", points)
    write_csv(args.output_dir / "PAIRED_STABILITY_SUMMARY.csv", stability)
    (args.output_dir / "SUPPORT_STABILITY_REPORT.md").write_text(render_report(points, stability), encoding="utf-8")
    (args.output_dir / "SUPPORT_STABILITY_RESULTS.tex").write_text(render_tex(points, stability), encoding="utf-8")
    plot_support_curves(points, args.output_dir)
    manifest = {
        "report_version": "chicago-k2-support-stability/v1",
        "checkpoint_sha256": sha256_file(args.checkpoint_dir / "checkpoint.json"),
        "input_sensitivity_files": pins,
        "completed_window_count": len(pins),
        "raw_endpoint_pair_count": len(rows),
        "point_summary_row_count": len(points),
        "paired_stability_row_count": len(stability),
        "output_sha256": {
            name: sha256_file(args.output_dir / name)
            for name in (
                "SUPPORT_POINT_SUMMARY.csv",
                "PAIRED_STABILITY_SUMMARY.csv",
                "SUPPORT_STABILITY_REPORT.md",
                "SUPPORT_STABILITY_RESULTS.tex",
                "SUPPORT_STABILITY_CURVES.pdf",
                "SUPPORT_STABILITY_CURVES.png",
            )
        },
        "claim_status": "DESCRIPTIVE_FIXED_CALENDAR_NOT_POPULATION_INFERENCE",
    }
    (args.output_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "input_sensitivity_files"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
