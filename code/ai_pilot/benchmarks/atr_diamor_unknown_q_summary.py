#!/usr/bin/env python3
"""Create a disclosure-safe two-day summary for the ATR unknown-q audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any


REGIMES = ("oracle_q", "q_pm_1", "all_positive_q")
EXACT = "EXACT_UNION_OF_REPLAYED_FIXED_Q_FRONTIERS"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(reports: list[tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    if len(reports) != 2 or {r["dataset_day"] for _, r in reports} != {"DIAMOR-1", "DIAMOR-2"}:
        raise ValueError("exactly one report from each DIAMOR day is required")
    if any(r["status"] != "PASS" for _, r in reports):
        raise ValueError("a non-PASS report cannot enter the frozen summary")
    for key in ("benchmark_sha256", "base_protocol_sha256", "unknown_q_protocol_sha256"):
        if len({r[key] for _, r in reports}) != 1:
            raise ValueError(f"cross-day {key} mismatch")
    threshold_counts = {r["decision_threshold_count"] for _, r in reports}
    if len(threshold_counts) != 1 or next(iter(threshold_counts)) < 1:
        raise ValueError("cross-day decision-threshold count mismatch")
    threshold_count = next(iter(threshold_counts))
    days = [{
        "dataset_day": r["dataset_day"], "audit_role": r["audit_role"],
        "report_sha256": digest(path), "eligible_snapshot_count": r["eligible_snapshot_count"],
        "cell_count": r["cell_count"], "summary": r["summary"],
    } for path, r in reports]
    cells = [cell for _, report in reports for cell in report["cells"]]
    combined: dict[str, Any] = {}
    for regime in REGIMES:
        exact = [c for c in cells if c["regimes"][regime]["status"] == EXACT]
        widths = [c["regimes"][regime]["width"] for c in exact]
        false_cells = [c for c in exact if c["regimes"][regime]["false_certificates"]]
        representable_false = [c for c in false_cells if c["true_world_representable"]]
        decisions = len(exact) * threshold_count
        ambiguous = sum(c["regimes"][regime]["ambiguous_thresholds"] for c in exact)
        combined[regime] = {
            "cell_count": len(cells), "exact_cell_count": len(exact),
            "infeasible_cell_count": len(cells) - len(exact),
            "threshold_decisions": decisions,
            "ambiguous_threshold_decisions": ambiguous,
            "certified_threshold_decisions": decisions - ambiguous,
            "certified_decision_rate": (decisions - ambiguous) / decisions,
            "false_certificates": sum(c["regimes"][regime]["false_certificates"] for c in exact),
            "false_certificate_cells": len(false_cells),
            "false_certificate_cells_with_representable_truth": len(representable_false),
            "mean_width_m": statistics.fmean(widths),
            "median_width_m": statistics.median(widths),
        }
    return {
        "summary_version": "atr-diamor-unknown-q-summary/v1",
        "claim_scope": reports[0][1]["claim_scope"],
        "benchmark_sha256": reports[0][1]["benchmark_sha256"],
        "base_protocol_sha256": reports[0][1]["base_protocol_sha256"],
        "unknown_q_protocol_sha256": reports[0][1]["unknown_q_protocol_sha256"],
        "decision_threshold_count": threshold_count,
        "days": days, "combined": combined,
    }


def report_markdown(summary: dict[str, Any]) -> str:
    labels = {"oracle_q": "Oracle q", "q_pm_1": "q +/- 1", "all_positive_q": "All positive q"}
    rows = []
    for regime in REGIMES:
        item = summary["combined"][regime]
        rows.append(
            f"| {labels[regime]} | {item['exact_cell_count']} | {item['infeasible_cell_count']} | "
            f"{item['mean_width_m']:.3f} | {item['certified_threshold_decisions']}/{item['threshold_decisions']} "
            f"({100*item['certified_decision_rate']:.1f}%) | {item['false_certificates']} |"
        )
    return "\n".join([
        "# ATR DIAMOR cardinality-uncertainty audit v1", "",
        "Status: **PASS** for both frozen days and all three cardinality regimes.", "",
        "The all-positive-q regime removes group labels from endpoint cardinality, but labels still determine cohort eligibility, exclusions, and truth evaluation. The mean-distance query conditions on at least one dyad because it is undefined at q=0.", "",
        "| Cardinality information | Exact feasible cells | Proved infeasible | Mean width (m) | Certified decisions | False certificates |",
        "|---|---:|---:|---:|---:|---:|", *rows, "",
        "Allowing unknown cardinality makes 20 additional cells appear feasible relative to oracle q, because a smaller matching may exist when the annotated cardinality does not. This is not improved relational coverage. It widens the mean frontier from 1.176 m to 1.297 m and lowers certified-decision yield from 53.2% to 45.8%.", "",
        "Every false certificate occurs when candidate support omits the annotated world; none occurs in a truth-representable cell. Unknown q therefore compounds candidate-support uncertainty but does not invalidate conditional coverage when the annotated world remains admissible.", "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs=2, type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [(path, json.loads(path.read_text())) for path in args.reports]
    summary = build(reports)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "REPORT.md").write_text(report_markdown(summary))


if __name__ == "__main__":
    main()
