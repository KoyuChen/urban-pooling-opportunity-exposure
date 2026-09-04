#!/usr/bin/env python3
"""Aggregate the predeclared NYC ordered-run panel without exposing witnesses."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VERSION = "nyc-hvfhv-ordered-run-panel-window/v1"


def median(values: Iterable[Any]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return statistics.median(clean) if clean else None


def discover(root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(root.rglob("report.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if report.get("report_version") == VERSION:
            report["_path"] = str(path)
            reports.append(report)
    return reports


def audit(reports: Sequence[Mapping[str, Any]], expected: int | None) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    labels = [str(row.get("window_label") or "") for row in reports]
    duplicates = sorted(k for k, v in Counter(labels).items() if v > 1)
    if duplicates:
        problems.append({"reason": "duplicate_labels", "labels": duplicates})
    if any(not label for label in labels):
        problems.append({"reason": "blank_label"})
    if expected is not None and len(reports) != expected:
        problems.append({"reason": "window_count", "expected": expected, "observed": len(reports)})

    fingerprints = {
        row.get("snapshot", {}).get("revision_fingerprint_sha256") for row in reports
    } - {None}
    if len(fingerprints) != 1:
        problems.append({"reason": "release_fingerprint_count", "count": len(fingerprints)})

    contract = {
        "raw_rows_emitted": False,
        "row_identifiers_emitted": False,
        "run_assignments_emitted": False,
        "partner_witnesses_emitted": False,
        "aggregate_only": True,
    }
    for report in reports:
        label = report.get("window_label")
        if report.get("audit", {}).get("status") != "PASS":
            problems.append({"reason": "window_audit", "label": label})
        for key, value in contract.items():
            if report.get("redaction", {}).get(key) is not value:
                problems.append({"reason": "redaction", "label": label, "field": key})
        cells = report.get("cells", [])
        expected_cells = len(report.get("time_models", [])) * len(report.get("capacities", []))
        if len(cells) != expected_cells:
            problems.append({"reason": "cell_count", "label": label, "expected": expected_cells, "observed": len(cells)})
        if sorted({int(c["capacity"]) for c in cells}) != sorted(map(int, report.get("capacities", []))):
            problems.append({"reason": "capacity_set", "label": label})
    return {
        "status": "PASS" if reports and not problems else "FAIL",
        "window_count": len(reports),
        "expected_window_count": expected,
        "release_fingerprint_count": len(fingerprints),
        "problem_count": len(problems),
        "problems": problems,
    }


def flatten(reports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for report in reports:
        cohort = report["cohort"]
        for cell in report["cells"]:
            low, high = cell["minimum_solve"], cell["maximum_solve"]
            output.append({
                "window_label": report["window_label"],
                "scan_start": report["scan_start"],
                "scan_end": report["scan_end"],
                "provider": cohort["provider"],
                "source_core_start": cohort["source_core_start"],
                "source_core_end": cohort["source_core_end"],
                "source_core_rows": cohort["source_core_rows"],
                "source_candidate_rows": cohort["source_candidate_rows"],
                "ordered_core_rows": cohort["ordered_core_rows"],
                "ordered_candidate_rows": cohort["ordered_candidate_rows"].get(cell["time_model"]),
                "time_model": cell["time_model"],
                "capacity": cell["capacity"],
                "status": cell["status"],
                "lower": cell["lower"],
                "upper": cell["upper"],
                "width": cell["width"],
                "outer_lower": cell["solver_outer_frontier_lower"],
                "outer_upper": cell["solver_outer_frontier_upper"],
                "outer_width": cell["solver_outer_width"],
                "inner_lower": cell["solver_inner_frontier_lower"],
                "inner_upper": cell["solver_inner_frontier_upper"],
                "inner_width": cell["solver_inner_width"],
                "peak_core_occupancy": cell["peak_core_occupancy"],
                "analytic_minimum_run_bound": cell["analytic_minimum_run_bound"],
                "analytic_bound_sharp": cell["analytic_bound_sharp"],
                "variables": cell["variables"],
                "binary_variables": cell["binary_variables"],
                "constraints": cell["constraints"],
                "minimum_status": low["status"],
                "maximum_status": high["status"],
                "minimum_mip_gap": low["mip_gap"],
                "maximum_mip_gap": high["mip_gap"],
                "total_seconds": low["elapsed_seconds"] + high["elapsed_seconds"],
            })
    return output


def summarize(reports: Sequence[Mapping[str, Any]], cells: Sequence[Mapping[str, Any]], checked: Mapping[str, Any]) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    keys = sorted({(int(r["ordered_core_rows"]), str(r["time_model"]), int(r["capacity"])) for r in cells})
    for core, time_model, capacity in keys:
        rows = [r for r in cells if (int(r["ordered_core_rows"]), str(r["time_model"]), int(r["capacity"])) == (core, time_model, capacity)]
        certified = [r for r in rows if r["status"] == "CERTIFIED_OPTIMAL_PAIR"]
        groups.append({
            "ordered_core_rows": core,
            "time_model": time_model,
            "capacity": capacity,
            "cell_count": len(rows),
            "certified_cell_count": len(certified),
            "certification_rate": len(certified) / len(rows),
            "median_exact_lower": median(r["lower"] for r in certified),
            "median_exact_upper": median(r["upper"] for r in certified),
            "median_exact_width": median(r["width"] for r in certified),
            "median_outer_width": median(r["outer_width"] for r in rows),
            "analytic_bound_sharp_rate_among_certified": (
                sum(bool(r["analytic_bound_sharp"]) for r in certified) / len(certified)
                if certified else None
            ),
            "median_candidate_rows": median(r["ordered_candidate_rows"] for r in rows),
            "maximum_candidate_rows": max(int(r["ordered_candidate_rows"]) for r in rows),
            "median_variables": median(r["variables"] for r in rows),
            "maximum_variables": max(int(r["variables"]) for r in rows),
            "median_seconds": median(r["total_seconds"] for r in rows),
            "maximum_seconds": max(float(r["total_seconds"]) for r in rows),
        })

    broad = [r for r in cells if int(r["ordered_core_rows"]) == 8]
    open_broad = [r for r in broad if r["status"] != "CERTIFIED_OPTIMAL_PAIR"]
    broad_rate = sum(r["status"] == "CERTIFIED_OPTIMAL_PAIR" for r in broad) / len(broad) if broad else 0.0
    finite_open = all(r["outer_lower"] is not None and r["outer_upper"] is not None for r in open_broad)
    gate = bool(broad and broad_rate >= 0.80 and finite_open and checked["status"] == "PASS")

    provider_counts = Counter(str(r["cohort"]["provider"]) for r in reports)
    return {
        "panel_audit": dict(checked),
        "window_count": len(reports),
        "capacity_cell_count": len(cells),
        "broad_window_count": sum(int(r["cohort"]["ordered_core_rows"]) == 8 for r in reports),
        "stress_window_count": sum(int(r["cohort"]["ordered_core_rows"]) > 8 for r in reports),
        "source_core_row_appearances": sum(int(r["cohort"]["source_core_rows"]) for r in reports),
        "source_candidate_row_appearances": sum(int(r["cohort"]["source_candidate_rows"]) for r in reports),
        "ordered_core_row_appearances": sum(int(r["cohort"]["ordered_core_rows"]) for r in reports),
        "provider_window_counts": dict(sorted(provider_counts.items())),
        "broad_capacity_cell_certification_rate": broad_rate,
        "broad_open_cell_count": len(open_broad),
        "broad_open_cells_have_finite_outer_enclosures": finite_open,
        "broad_manuscript_gate_pass": gate,
        "groups": groups,
        "counting_note": "row totals are panel-cell appearances, not unique riders, people, vehicles, or runs; nested stress cells may reuse public source rows",
    }


def render(report: Mapping[str, Any]) -> str:
    lines = [
        "# NYC ordered-run evidence panel", "",
        f"Panel audit: `{report['panel_audit']['status']}`; windows: **{report['window_count']}**; capacity cells: **{report['capacity_cell_count']}**.",
        f"Broad-cell certification rate: **{100 * report['broad_capacity_cell_certification_rate']:.1f}%**; manuscript gate: **{'PASS' if report['broad_manuscript_gate_pass'] else 'HOLD'}**.", "",
        "| Core | Time | C | Cells | Certified | Median exact interval | Median outer width | Max candidates | Max vars | Max sec. |",
        "|---:|---|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for row in report["groups"]:
        interval = "—" if row["median_exact_lower"] is None else f"[{row['median_exact_lower']:.4f}, {row['median_exact_upper']:.4f}]"
        lines.append(
            f"| {row['ordered_core_rows']} | {row['time_model']} | {row['capacity']} | {row['cell_count']} | "
            f"{100 * row['certification_rate']:.1f}% | {interval} | {row['median_outer_width']:.4f} | "
            f"{row['maximum_candidate_rows']} | {row['maximum_variables']} | {row['maximum_seconds']:.1f} |"
        )
    lines += [
        "", f"Source candidate-row appearances: **{report['source_candidate_row_appearances']}**; ordered-core appearances: **{report['ordered_core_row_appearances']}**.",
        "", report["counting_note"] + ".", "",
        "This panel supports descriptive feasible-world and computational claims only. It does not identify actual partners, vehicle runs, realized pool size/capacity, production logic, or population prevalence.", "",
    ]
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    fields = sorted({k for row in rows for k in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    def report(label: str, core: int) -> dict[str, Any]:
        cells = []
        for capacity in (2, 3, 4):
            cells.append({
                "time_model": "exact_second", "capacity": capacity,
                "status": "CERTIFIED_OPTIMAL_PAIR", "lower": 1 / capacity,
                "upper": 1.0, "width": 1 - 1 / capacity,
                "solver_outer_frontier_lower": 1 / capacity,
                "solver_outer_frontier_upper": 1.0, "solver_outer_width": 1 - 1 / capacity,
                "solver_inner_frontier_lower": 1 / capacity,
                "solver_inner_frontier_upper": 1.0, "solver_inner_width": 1 - 1 / capacity,
                "peak_core_occupancy": core, "analytic_minimum_run_bound": 1 / capacity,
                "analytic_bound_sharp": True, "variables": 100, "binary_variables": 80,
                "constraints": 90,
                "minimum_solve": {"status": "CERTIFIED_OPTIMAL", "mip_gap": 0.0, "elapsed_seconds": 0.1},
                "maximum_solve": {"status": "CERTIFIED_OPTIMAL", "mip_gap": 0.0, "elapsed_seconds": 0.1},
            })
        return {
            "report_version": VERSION, "window_label": label, "scan_start": "a", "scan_end": "b",
            "snapshot": {"revision_fingerprint_sha256": "same"},
            "cohort": {"provider": "HV", "source_core_start": "a", "source_core_end": "b", "source_core_rows": core, "source_candidate_rows": 20, "ordered_core_rows": core, "ordered_candidate_rows": {"exact_second": 20}},
            "time_models": ["exact_second"], "capacities": [2, 3, 4], "cells": cells,
            "audit": {"status": "PASS"},
            "redaction": {"raw_rows_emitted": False, "row_identifiers_emitted": False, "run_assignments_emitted": False, "partner_witnesses_emitted": False, "aggregate_only": True},
        }
    reports = [report("broad", 8), report("stress", 16)]
    checked = audit(reports, 2)
    assert checked["status"] == "PASS", checked
    summary = summarize(reports, flatten(reports), checked)
    assert summary["broad_manuscript_gate_pass"]
    print("NYC ordered-run panel aggregator self-test: PASS")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--expected-window-count", type=int)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input_dir is None or args.output_dir is None:
        p.error("--input-dir and --output-dir are required")
    reports = discover(args.input_dir)
    checked = audit(reports, args.expected_window_count)
    cells = flatten(reports)
    result = summarize(reports, cells, checked)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "REPORT.md").write_text(render(result), encoding="utf-8")
    write_csv(cells, args.output_dir / "panel_cells.csv")
    write_csv(result["groups"], args.output_dir / "panel_groups.csv")
    print(render(result))
    return 0 if checked["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
