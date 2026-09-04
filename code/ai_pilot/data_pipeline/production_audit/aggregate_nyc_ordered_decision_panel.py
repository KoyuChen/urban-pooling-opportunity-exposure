#!/usr/bin/env python3
"""Aggregate the predeclared NYC outcome/decision panel.

Ineligible windows remain part of the predeclared denominator. Eligible windows
contribute fixed-support outcome frontiers and deterministic point-reconstruction
diagnostics. The aggregator fails closed on missing window records, duplicate
labels, redaction violations, baseline containment failures, or capacity-nesting
contradictions; a declared ineligible window is not treated as a computational
failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VERSION = "nyc-hvfhv-ordered-decision-panel-window/v1"
ELIGIBLE = "ELIGIBLE_ANALYZED"
INELIGIBLE = "INELIGIBLE_NO_QUALIFIED_CORE"
TOL = 1e-7


def clean(values: Iterable[Any]) -> list[float]:
    return [float(value) for value in values if value is not None]


def median(values: Iterable[Any]) -> float | None:
    values = clean(values)
    return statistics.median(values) if values else None


def discover(root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(root.rglob("report.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if report.get("report_version") == VERSION:
            report["_path"] = str(path.relative_to(root))
            reports.append(report)
    return reports


def audit(reports: Sequence[Mapping[str, Any]], expected: int) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    labels = [str(report.get("window_label") or "") for report in reports]
    duplicates = sorted(label for label, count in Counter(labels).items() if count > 1)
    if duplicates:
        problems.append({"reason": "duplicate_window_labels", "labels": duplicates})
    if any(not label for label in labels):
        problems.append({"reason": "blank_window_label"})
    if len(reports) != expected:
        problems.append({"reason": "window_count", "expected": expected, "observed": len(reports)})

    allowed = {
        ELIGIBLE,
        INELIGIBLE,
        "UNRESOLVED_SUPPORT_SEARCH",
        "PROVEN_NO_POSITIVE_COMMON_SUPPORT",
    }
    contract = {
        "raw_rows_emitted": False,
        "row_identifiers_emitted": False,
        "run_assignments_emitted": False,
        "partner_witnesses_emitted": False,
        "aggregate_only": True,
    }
    fingerprints: set[str] = set()
    for report in reports:
        label = report.get("window_label")
        status = report.get("status")
        if status not in allowed:
            problems.append({"reason": "unknown_window_status", "label": label, "status": status})
        for key, expected_value in contract.items():
            if report.get("redaction", {}).get(key) is not expected_value:
                problems.append({"reason": "redaction", "label": label, "field": key})
        if status == ELIGIBLE:
            fingerprint = report.get("snapshot", {}).get("revision_fingerprint_sha256")
            if fingerprint:
                fingerprints.add(str(fingerprint))
            if report.get("audit", {}).get("status") != "PASS":
                problems.append({"reason": "window_audit", "label": label})
            cells = report.get("cells", [])
            if len(cells) != 6:
                problems.append({"reason": "eligible_cell_count", "label": label, "observed": len(cells)})
            if any(cell.get("baseline_containment_status") != "PASS" for cell in cells):
                problems.append({"reason": "baseline_containment", "label": label})
            baselines = report.get("baselines", [])
            if not any(
                baseline.get("status") == "CERTIFIED_FEASIBLE_POINT"
                for baseline in baselines
            ):
                problems.append({"reason": "no_certified_point_baseline", "label": label})
    if len(fingerprints) != 1:
        problems.append({"reason": "release_fingerprint_count", "count": len(fingerprints)})
    return {
        "status": "PASS" if reports and not problems else "FAIL",
        "expected_window_count": expected,
        "observed_window_count": len(reports),
        "eligible_window_count": sum(report.get("status") == ELIGIBLE for report in reports),
        "ineligible_window_count": sum(report.get("status") == INELIGIBLE for report in reports),
        "unresolved_window_count": sum(
            report.get("status") not in {ELIGIBLE, INELIGIBLE} for report in reports
        ),
        "release_fingerprint_count": len(fingerprints),
        "problem_count": len(problems),
        "problems": problems,
    }


def flatten_cells(reports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        if report.get("status") != ELIGIBLE:
            continue
        cohort = report["cohort"]
        q = report["support_selection"]["selected_buffer_count"]
        for cell in report["cells"]:
            low = cell.get("minimum_solve", {})
            high = cell.get("maximum_solve", {})
            iqr = cell.get("candidate_iqr")
            width = cell.get("width")
            rows.append(
                {
                    "window_label": report["window_label"],
                    "scan_start": report["scan_start"],
                    "scan_end": report["scan_end"],
                    "provider": cohort["provider"],
                    "ordered_core_rows": cohort["ordered_core_rows"],
                    "ordered_candidate_rows": cohort["ordered_candidate_rows"],
                    "fixed_selected_buffer_count": q,
                    "capacity": cell["capacity"],
                    "query": cell["query"],
                    "unit": cell["unit"],
                    "status": cell["status"],
                    "lower": cell.get("lower"),
                    "upper": cell.get("upper"),
                    "width": width,
                    "outer_lower": cell.get("outer_lower"),
                    "outer_upper": cell.get("outer_upper"),
                    "outer_width": (
                        None
                        if cell.get("outer_lower") is None
                        or cell.get("outer_upper") is None
                        else float(cell["outer_upper"]) - float(cell["outer_lower"])
                    ),
                    "candidate_median_threshold": cell.get("threshold"),
                    "candidate_iqr": iqr,
                    "width_over_candidate_iqr": (
                        None
                        if width is None or iqr is None or float(iqr) <= TOL
                        else float(width) / float(iqr)
                    ),
                    "frontier_decision": cell.get("frontier_decision"),
                    "baseline_value_min": cell.get("baseline_value_min"),
                    "baseline_value_max": cell.get("baseline_value_max"),
                    "baseline_decision_disagreement": cell.get(
                        "baseline_decision_disagreement"
                    ),
                    "baseline_containment_status": cell.get(
                        "baseline_containment_status"
                    ),
                    "variables": cell.get("variables"),
                    "binary_variables": cell.get("binary_variables"),
                    "constraints": cell.get("constraints"),
                    "minimum_status": low.get("status"),
                    "maximum_status": high.get("status"),
                    "minimum_seconds": low.get("elapsed_seconds"),
                    "maximum_seconds": high.get("elapsed_seconds"),
                    "total_seconds": (
                        None
                        if low.get("elapsed_seconds") is None
                        or high.get("elapsed_seconds") is None
                        else float(low["elapsed_seconds"])
                        + float(high["elapsed_seconds"])
                    ),
                }
            )
    return rows


def flatten_baselines(reports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        if report.get("status") != ELIGIBLE:
            continue
        cohort = report["cohort"]
        for baseline in report.get("baselines", []):
            for query, outcome in baseline.get("outcomes", {}).items():
                rows.append(
                    {
                        "window_label": report["window_label"],
                        "ordered_core_rows": cohort["ordered_core_rows"],
                        "method": baseline["name"],
                        "method_status": baseline["status"],
                        "selected_buffer_count": baseline["selected_buffer_count"],
                        "query": query,
                        "value": outcome.get("value"),
                        "threshold": outcome.get("threshold"),
                        "decision": outcome.get("decision"),
                        "solver_seconds": baseline.get("solver_seconds"),
                    }
                )
    return rows


def summarize(
    reports: Sequence[Mapping[str, Any]],
    cells: Sequence[Mapping[str, Any]],
    baselines: Sequence[Mapping[str, Any]],
    checked: Mapping[str, Any],
) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    keys = sorted(
        {
            (
                int(row["ordered_core_rows"]),
                str(row["query"]),
                int(row["capacity"]),
            )
            for row in cells
        }
    )
    for core, query, capacity in keys:
        selected = [
            row
            for row in cells
            if (
                int(row["ordered_core_rows"]),
                str(row["query"]),
                int(row["capacity"]),
            )
            == (core, query, capacity)
        ]
        exact = [
            row for row in selected if row["status"] == "CERTIFIED_OPTIMAL_PAIR"
        ]
        ambiguous = [
            row
            for row in selected
            if row["frontier_decision"] == "CERTIFIED_AMBIGUOUS"
        ]
        groups.append(
            {
                "ordered_core_rows": core,
                "query": query,
                "capacity": capacity,
                "cell_count": len(selected),
                "exact_cell_count": len(exact),
                "exact_rate": len(exact) / len(selected),
                "decision_ambiguity_rate": len(ambiguous) / len(selected),
                "baseline_disagreement_rate": (
                    sum(bool(row["baseline_decision_disagreement"]) for row in selected)
                    / len(selected)
                ),
                "median_exact_width": median(row["width"] for row in exact),
                "median_width_over_candidate_iqr": median(
                    row["width_over_candidate_iqr"] for row in exact
                ),
                "median_total_seconds": median(
                    row["total_seconds"] for row in selected
                ),
                "maximum_total_seconds": max(
                    float(row["total_seconds"])
                    for row in selected
                    if row["total_seconds"] is not None
                ),
                "maximum_candidate_rows": max(
                    int(row["ordered_candidate_rows"]) for row in selected
                ),
                "maximum_variables": max(int(row["variables"]) for row in selected),
            }
        )

    eligible = [report for report in reports if report.get("status") == ELIGIBLE]
    ineligible = [report for report in reports if report.get("status") == INELIGIBLE]
    unresolved = [
        report
        for report in reports
        if report.get("status") not in {ELIGIBLE, INELIGIBLE}
    ]
    feasible_baselines = [
        row for row in baselines if row["method_status"] == "CERTIFIED_FEASIBLE_POINT"
    ]
    baseline_methods = sorted({row["method"] for row in feasible_baselines})
    frontier_ambiguous_cells = [
        row for row in cells if row["frontier_decision"] == "CERTIFIED_AMBIGUOUS"
    ]
    point_decisions_in_ambiguous_cells = 0
    total_point_decisions = 0
    by_window_query: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in feasible_baselines:
        by_window_query[(str(row["window_label"]), str(row["query"]))].append(row)
    for cell in cells:
        point_rows = by_window_query[(str(cell["window_label"]), str(cell["query"]))]
        total_point_decisions += sum(
            row.get("decision") in {"ABOVE_OR_EQUAL", "BELOW"}
            for row in point_rows
        )
        if cell["frontier_decision"] == "CERTIFIED_AMBIGUOUS":
            point_decisions_in_ambiguous_cells += sum(
                row.get("decision") in {"ABOVE_OR_EQUAL", "BELOW"}
                for row in point_rows
            )

    manuscript_gate = bool(
        checked["status"] == "PASS"
        and checked["eligible_window_count"] >= 16
        and checked["unresolved_window_count"] == 0
        and cells
        and sum(row["status"] == "CERTIFIED_OPTIMAL_PAIR" for row in cells)
        / len(cells)
        >= 0.80
    )
    return {
        "panel_audit": dict(checked),
        "manuscript_gate_pass": manuscript_gate,
        "predeclared_window_count": len(reports),
        "eligible_window_count": len(eligible),
        "ineligible_window_count": len(ineligible),
        "unresolved_window_count": len(unresolved),
        "eligibility_rate": len(eligible) / len(reports) if reports else 0.0,
        "ineligible_windows": [
            {"window_label": row["window_label"], "reason": row.get("reason")}
            for row in ineligible
        ],
        "unresolved_windows": [
            {"window_label": row["window_label"], "status": row.get("status")}
            for row in unresolved
        ],
        "outcome_cell_count": len(cells),
        "exact_outcome_cell_count": sum(
            row["status"] == "CERTIFIED_OPTIMAL_PAIR" for row in cells
        ),
        "exact_outcome_cell_rate": (
            sum(row["status"] == "CERTIFIED_OPTIMAL_PAIR" for row in cells)
            / len(cells)
            if cells
            else 0.0
        ),
        "certified_ambiguous_cell_count": len(frontier_ambiguous_cells),
        "certified_ambiguity_rate": (
            len(frontier_ambiguous_cells) / len(cells) if cells else 0.0
        ),
        "baseline_method_count": len(baseline_methods),
        "baseline_methods": baseline_methods,
        "feasible_baseline_outcome_count": len(feasible_baselines),
        "baseline_decision_disagreement_cell_count": sum(
            bool(row["baseline_decision_disagreement"]) for row in cells
        ),
        "baseline_decision_disagreement_rate": (
            sum(bool(row["baseline_decision_disagreement"]) for row in cells)
            / len(cells)
            if cells
            else 0.0
        ),
        "point_decisions_made_inside_certified_ambiguous_cells": (
            point_decisions_in_ambiguous_cells
        ),
        "total_point_decisions": total_point_decisions,
        "share_point_decisions_not_relation_certifiable": (
            point_decisions_in_ambiguous_cells / total_point_decisions
            if total_point_decisions
            else None
        ),
        "groups": groups,
        "claim_boundary": {
            "supported": (
                "descriptive fixed-support outcome frontiers and deterministic "
                "point-decision comparisons over predeclared eligible public-data windows"
            ),
            "not_supported": (
                "actual event membership, true partner recall, realized capacity, "
                "production logic, population prevalence, point-method accuracy without "
                "ground truth, or causal effects"
            ),
        },
    }


def render(report: Mapping[str, Any]) -> str:
    lines = [
        "# NYC ordered outcome and decision panel",
        "",
        f"Panel audit: `{report['panel_audit']['status']}`; manuscript gate: "
        f"`{'PASS' if report['manuscript_gate_pass'] else 'HOLD'}`.",
        "",
        f"Predeclared windows: **{report['predeclared_window_count']}**; eligible: "
        f"**{report['eligible_window_count']}**; ineligible: "
        f"**{report['ineligible_window_count']}**; unresolved: "
        f"**{report['unresolved_window_count']}**.",
        f"Outcome cells: **{report['outcome_cell_count']}**; exact endpoint pairs: "
        f"**{100 * report['exact_outcome_cell_rate']:.1f}%**; certified decision "
        f"ambiguity: **{100 * report['certified_ambiguity_rate']:.1f}%**.",
        f"Point-method decision disagreement: "
        f"**{100 * report['baseline_decision_disagreement_rate']:.1f}%** of "
        "outcome-capacity cells.",
        "",
        "| Core | Outcome | C | Cells | Exact | Ambiguous at candidate median | "
        "Baselines disagree | Median width | Width / candidate IQR | Max candidates | "
        "Max vars | Max sec. |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["groups"]:
        width = (
            "—"
            if row["median_exact_width"] is None
            else f"{row['median_exact_width']:.3f}"
        )
        normalized = (
            "—"
            if row["median_width_over_candidate_iqr"] is None
            else f"{row['median_width_over_candidate_iqr']:.3f}"
        )
        lines.append(
            f"| {row['ordered_core_rows']} | {row['query']} | {row['capacity']} | "
            f"{row['cell_count']} | {100 * row['exact_rate']:.1f}% | "
            f"{100 * row['decision_ambiguity_rate']:.1f}% | "
            f"{100 * row['baseline_disagreement_rate']:.1f}% | {width} | "
            f"{normalized} | {row['maximum_candidate_rows']} | "
            f"{row['maximum_variables']} | {row['maximum_total_seconds']:.1f} |"
        )
    if report["ineligible_windows"]:
        lines += ["", "## Predeclared ineligible windows", ""]
        for row in report["ineligible_windows"]:
            lines.append(f"- `{row['window_label']}`: `{row['reason']}`")
    lines += [
        "",
        "A deterministic point method always returns a side of the threshold. "
        "The frontier reports whether that side is invariant to every admissible "
        "relation completion. No accuracy claim is made on public data because "
        "operational memberships are absent.",
        "",
    ]
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    fields = sorted({key for row in rows for key in row}) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    def eligible(label: str, core: int) -> dict[str, Any]:
        baselines = []
        for method, value in (("a", 1.0), ("b", 3.0)):
            baselines.append(
                {
                    "name": method,
                    "status": "CERTIFIED_FEASIBLE_POINT",
                    "selected_buffer_count": core,
                    "solver_seconds": 0.1,
                    "outcomes": {
                        "mean_selected_buffer_miles": {
                            "value": value,
                            "threshold": 2.0,
                            "decision": (
                                "ABOVE_OR_EQUAL" if value >= 2 else "BELOW"
                            ),
                        },
                        "mean_selected_buffer_trip_minutes": {
                            "value": value * 10,
                            "threshold": 20.0,
                            "decision": (
                                "ABOVE_OR_EQUAL" if value >= 2 else "BELOW"
                            ),
                        },
                    },
                }
            )
        cells = []
        for capacity in (2, 3, 4):
            for query, scale in (
                ("mean_selected_buffer_miles", 1.0),
                ("mean_selected_buffer_trip_minutes", 10.0),
            ):
                cells.append(
                    {
                        "capacity": capacity,
                        "query": query,
                        "unit": "u",
                        "status": "CERTIFIED_OPTIMAL_PAIR",
                        "lower": scale,
                        "upper": 3 * scale,
                        "width": 2 * scale,
                        "outer_lower": scale,
                        "outer_upper": 3 * scale,
                        "threshold": 2 * scale,
                        "candidate_iqr": scale,
                        "frontier_decision": "CERTIFIED_AMBIGUOUS",
                        "baseline_value_min": scale,
                        "baseline_value_max": 3 * scale,
                        "baseline_decision_disagreement": True,
                        "baseline_containment_status": "PASS",
                        "variables": 100,
                        "binary_variables": 80,
                        "constraints": 90,
                        "minimum_solve": {
                            "status": "CERTIFIED_OPTIMAL",
                            "elapsed_seconds": 0.1,
                        },
                        "maximum_solve": {
                            "status": "CERTIFIED_OPTIMAL",
                            "elapsed_seconds": 0.1,
                        },
                    }
                )
        return {
            "report_version": VERSION,
            "status": ELIGIBLE,
            "window_label": label,
            "scan_start": "a",
            "scan_end": "b",
            "snapshot": {"revision_fingerprint_sha256": "same"},
            "cohort": {
                "provider": "HV",
                "ordered_core_rows": core,
                "ordered_candidate_rows": 100,
            },
            "support_selection": {"selected_buffer_count": core},
            "baselines": baselines,
            "cells": cells,
            "audit": {"status": "PASS"},
            "redaction": {
                "raw_rows_emitted": False,
                "row_identifiers_emitted": False,
                "run_assignments_emitted": False,
                "partner_witnesses_emitted": False,
                "aggregate_only": True,
            },
        }

    reports = [eligible(f"w{i}", 8) for i in range(16)]
    reports.append(
        {
            "report_version": VERSION,
            "status": INELIGIBLE,
            "window_label": "missing",
            "reason": "no qualified core",
            "redaction": {
                "raw_rows_emitted": False,
                "row_identifiers_emitted": False,
                "run_assignments_emitted": False,
                "partner_witnesses_emitted": False,
                "aggregate_only": True,
            },
        }
    )
    checked = audit(reports, 17)
    assert checked["status"] == "PASS", checked
    cells = flatten_cells(reports)
    baselines = flatten_baselines(reports)
    result = summarize(reports, cells, baselines, checked)
    assert result["manuscript_gate_pass"], result
    assert result["certified_ambiguity_rate"] == 1.0
    print("NYC ordered decision-panel aggregator self-test: PASS")


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
    reports = discover(args.input_dir)
    checked = audit(reports, args.expected_window_count)
    cells = flatten_cells(reports)
    baselines = flatten_baselines(reports)
    result = summarize(reports, cells, baselines, checked)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(result), encoding="utf-8")
    write_csv(cells, args.output_dir / "outcome_cells.csv")
    write_csv(baselines, args.output_dir / "baseline_outcomes.csv")
    write_csv(result["groups"], args.output_dir / "outcome_groups.csv")
    print(render(result))
    return 0 if checked["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
