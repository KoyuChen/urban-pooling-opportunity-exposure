#!/usr/bin/env python3
"""Aggregate the repaired NYC decision panel and audit threshold sensitivity.

This wrapper preserves the original fixed-support estimand, corrects the
predeclared-versus-observed denominator labels, separates technical failures
from scientific ineligibility/unresolved optimization, and evaluates the same
frontiers at candidate Q1/median/Q3 plus transparent fixed reference cutoffs.
The fixed cutoffs are robustness references, not claimed operational policies.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import aggregate_nyc_ordered_decision_panel as legacy

TECHNICAL = "TECHNICAL_FAILURE"
TOL = legacy.TOL


def frontier_decision(cell: Mapping[str, Any], threshold: float) -> str:
    outer_lower = cell.get("outer_lower")
    outer_upper = cell.get("outer_upper")
    inner_lower = cell.get("inner_lower")
    inner_upper = cell.get("inner_upper")
    if outer_lower is not None and float(outer_lower) >= threshold - TOL:
        return "CERTIFIED_ALL_ABOVE_OR_EQUAL"
    if outer_upper is not None and float(outer_upper) < threshold - TOL:
        return "CERTIFIED_ALL_BELOW"
    if (
        inner_lower is not None
        and inner_upper is not None
        and float(inner_lower) < threshold - TOL
        and float(inner_upper) >= threshold - TOL
    ):
        return "CERTIFIED_AMBIGUOUS"
    return "UNRESOLVED_DECISION"


def threshold_rules(cell: Mapping[str, Any]) -> list[tuple[str, float, str]]:
    rules: list[tuple[str, float, str]] = []
    for name, field in (
        ("candidate_q1", "candidate_q1"),
        ("candidate_median", "threshold"),
        ("candidate_q3", "candidate_q3"),
    ):
        value = cell.get(field)
        if value is not None:
            rules.append((name, float(value), "candidate-distribution sensitivity"))
    query = str(cell.get("query"))
    if query == "mean_selected_buffer_miles":
        rules.append(("reference_5_miles", 5.0, "post-hoc transparent reference"))
    elif query == "mean_selected_buffer_trip_minutes":
        rules.append(("reference_30_minutes", 30.0, "post-hoc transparent reference"))
    return rules


def baseline_values(report: Mapping[str, Any], query: str) -> list[float]:
    values: list[float] = []
    for baseline in report.get("baselines", []):
        if baseline.get("status") != "CERTIFIED_FEASIBLE_POINT":
            continue
        value = baseline.get("outcomes", {}).get(query, {}).get("value")
        if value is not None:
            values.append(float(value))
    return values


def sensitivity_cells(reports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        if report.get("status") != legacy.ELIGIBLE:
            continue
        core = int(report["cohort"]["ordered_core_rows"])
        for cell in report.get("cells", []):
            query = str(cell["query"])
            points = baseline_values(report, query)
            for rule, threshold, provenance in threshold_rules(cell):
                decisions = [
                    "ABOVE_OR_EQUAL" if value >= threshold else "BELOW"
                    for value in points
                ]
                rows.append(
                    {
                        "window_label": report["window_label"],
                        "ordered_core_rows": core,
                        "capacity": int(cell["capacity"]),
                        "query": query,
                        "threshold_rule": rule,
                        "threshold_provenance": provenance,
                        "threshold": threshold,
                        "frontier_decision": frontier_decision(cell, threshold),
                        "point_method_count": len(points),
                        "point_method_disagreement": len(set(decisions)) > 1,
                        "point_below_count": decisions.count("BELOW"),
                        "point_above_count": decisions.count("ABOVE_OR_EQUAL"),
                        "cell_status": cell.get("status"),
                    }
                )
    return rows


def sensitivity_groups(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, str, int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[
            (
                int(row["ordered_core_rows"]),
                str(row["query"]),
                int(row["capacity"]),
                str(row["threshold_rule"]),
            )
        ].append(row)
    output: list[dict[str, Any]] = []
    for key in sorted(buckets):
        selected = buckets[key]
        counts = Counter(str(row["frontier_decision"]) for row in selected)
        decided = sum(
            counts[name]
            for name in (
                "CERTIFIED_ALL_ABOVE_OR_EQUAL",
                "CERTIFIED_ALL_BELOW",
                "CERTIFIED_AMBIGUOUS",
            )
        )
        output.append(
            {
                "ordered_core_rows": key[0],
                "query": key[1],
                "capacity": key[2],
                "threshold_rule": key[3],
                "cell_count": len(selected),
                "certified_all_above_count": counts[
                    "CERTIFIED_ALL_ABOVE_OR_EQUAL"
                ],
                "certified_all_below_count": counts["CERTIFIED_ALL_BELOW"],
                "certified_ambiguous_count": counts["CERTIFIED_AMBIGUOUS"],
                "unresolved_count": counts["UNRESOLVED_DECISION"],
                "certified_ambiguity_rate": (
                    counts["CERTIFIED_AMBIGUOUS"] / decided if decided else None
                ),
                "point_disagreement_rate": (
                    sum(bool(row["point_method_disagreement"]) for row in selected)
                    / len(selected)
                ),
            }
        )
    return output


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    fields = sorted({key for row in rows for key in row}) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render(report: Mapping[str, Any]) -> str:
    text = legacy.render(report).rstrip()
    lines = [text, "", "## Denominator and execution audit", ""]
    lines.append(
        f"The design predeclared **{report['predeclared_window_count']}** windows; "
        f"**{report['observed_report_count']}** terminal reports were observed. "
        f"Technical failures: **{report['technical_failure_count']}**; missing "
        f"terminal reports: **{report['missing_report_count']}**."
    )
    if report.get("technical_failures"):
        lines += ["", "Technical failures remain excluded from scientific estimates:"]
        for row in report["technical_failures"]:
            lines.append(f"- `{row['window_label']}`: `{row.get('reason')}`")
    lines += ["", "## Threshold sensitivity", ""]
    lines.append(
        "Candidate quartiles test whether median-threshold ambiguity is mechanical. "
        "The 5-mile and 30-minute cutoffs are transparent post-hoc references, not "
        "claimed operational policy thresholds."
    )
    lines += [
        "",
        "| Core | Outcome | C | Threshold | Cells | All above | All below | Ambiguous | Unresolved | Point disagreement |",
        "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["threshold_sensitivity_groups"]:
        lines.append(
            f"| {row['ordered_core_rows']} | {row['query']} | {row['capacity']} | "
            f"{row['threshold_rule']} | {row['cell_count']} | "
            f"{row['certified_all_above_count']} | {row['certified_all_below_count']} | "
            f"{row['certified_ambiguous_count']} | {row['unresolved_count']} | "
            f"{100 * row['point_disagreement_rate']:.1f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def self_test() -> None:
    cell = {
        "query": "mean_selected_buffer_miles",
        "candidate_q1": 1.0,
        "threshold": 2.0,
        "candidate_q3": 3.0,
        "outer_lower": 0.5,
        "outer_upper": 3.5,
        "inner_lower": 0.5,
        "inner_upper": 3.5,
    }
    assert frontier_decision(cell, 2.0) == "CERTIFIED_AMBIGUOUS"
    assert {name for name, _, _ in threshold_rules(cell)} == {
        "candidate_q1",
        "candidate_median",
        "candidate_q3",
        "reference_5_miles",
    }
    print("NYC ordered decision-panel v2 aggregator self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-window-count", type=int, default=24)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input_dir is None or args.output_dir is None:
        parser.error("--input-dir and --output-dir are required")

    reports = legacy.discover(args.input_dir)
    checked = legacy.audit(reports, args.expected_window_count)
    cells = legacy.flatten_cells(reports)
    baselines = legacy.flatten_baselines(reports)
    result = legacy.summarize(reports, cells, baselines, checked)

    technical = [report for report in reports if report.get("status") == TECHNICAL]
    unresolved = [
        report
        for report in reports
        if report.get("status")
        not in {legacy.ELIGIBLE, legacy.INELIGIBLE, TECHNICAL}
    ]
    observed = len(reports)
    missing = max(0, args.expected_window_count - observed)
    result.update(
        {
            "predeclared_window_count": args.expected_window_count,
            "observed_report_count": observed,
            "missing_report_count": missing,
            "technical_failure_count": len(technical),
            "technical_failures": [
                {
                    "window_label": row.get("window_label"),
                    "reason": row.get("reason"),
                }
                for row in technical
            ],
            "unresolved_window_count": len(unresolved),
            "eligibility_rate": (
                result["eligible_window_count"] / args.expected_window_count
                if args.expected_window_count
                else 0.0
            ),
        }
    )
    sensitivity = sensitivity_cells(reports)
    groups = sensitivity_groups(sensitivity)
    result["threshold_sensitivity_groups"] = groups
    result["manuscript_gate_pass"] = bool(
        checked["status"] == "PASS"
        and not technical
        and not missing
        and not unresolved
        and result["eligible_window_count"] >= 16
        and cells
        and result["exact_outcome_cell_rate"] >= 0.80
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(result), encoding="utf-8")
    legacy.write_csv(cells, args.output_dir / "outcome_cells.csv")
    legacy.write_csv(baselines, args.output_dir / "baseline_outcomes.csv")
    legacy.write_csv(result["groups"], args.output_dir / "outcome_groups.csv")
    write_csv(sensitivity, args.output_dir / "threshold_sensitivity_cells.csv")
    write_csv(groups, args.output_dir / "threshold_sensitivity_groups.csv")
    print(render(result))
    return 0 if result["manuscript_gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
