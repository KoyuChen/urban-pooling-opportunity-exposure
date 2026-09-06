#!/usr/bin/env python3
"""Build a disclosure-safe ATR evidence summary from two full local reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCALAR_FIELDS = (
    "eligible_snapshot_count",
    "cell_count",
    "exact_cell_count",
    "computationally_closed_cell_count",
    "truth_representable_cell_count",
    "representable_truth_covered_cell_count",
    "representable_point_rule_threshold_errors",
    "representable_errors_flagged_ambiguous",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_current_reports(reports: list[dict[str, Any]]) -> None:
    if len(reports) != 2:
        raise ValueError("exactly two current ATR reports are required")
    expected_statuses = (
        "status",
        "computational_status",
        "semantic_status",
        "witness_replay_status",
        "independent_tiny_oracle_status",
    )
    for report in reports:
        if any(report.get(field) != "PASS" for field in expected_statuses):
            raise ValueError(f"current report is not fully PASS: {report.get('dataset_day')}")
        if report.get("cell_count") != len(report.get("cells", [])):
            raise ValueError("reported cell count does not match serialized cells")
        if report.get("exact_cell_count") != report.get("replayed_exact_cell_count"):
            raise ValueError("exact endpoints are not all witness-replayed")
        if report.get("independent_tiny_checked_cell_count") != report.get(
            "independent_tiny_passed_cell_count"
        ):
            raise ValueError("independent tiny-oracle checks are incomplete")
    if len({report["dataset_day"] for report in reports}) != 2:
        raise ValueError("current reports must refer to distinct dataset days")
    if len({report["protocol_sha256"] for report in reports}) != 1:
        raise ValueError("current reports use different protocols")
    if len({report["benchmark_sha256"] for report in reports}) != 1:
        raise ValueError("current reports use different benchmark code")


def safe_day(report: dict[str, Any], path: Path) -> dict[str, Any]:
    result = {field: report[field] for field in SCALAR_FIELDS}
    result.update(
        {
            "dataset_day": report["dataset_day"],
            "audit_role": report["audit_role"],
            "report_sha256": sha256(path),
            "trajectory_sha256": report["trajectory_sha256"],
            "groups_sha256": report["groups_sha256"],
            "protocol_sha256": report["protocol_sha256"],
            "benchmark_sha256": report["benchmark_sha256"],
            "runtime": report["runtime"],
            "computational_status": report["computational_status"],
            "semantic_status": report["semantic_status"],
            "witness_replay_status": report["witness_replay_status"],
            "independent_tiny_oracle_status": report["independent_tiny_oracle_status"],
            "replayed_exact_cell_count": report["replayed_exact_cell_count"],
            "independent_tiny_checked_cell_count": report["independent_tiny_checked_cell_count"],
            "independent_tiny_passed_cell_count": report["independent_tiny_passed_cell_count"],
            "excluded_or_quarantined_member_count": report["excluded_or_quarantined_member_count"],
            "group_parse_audit": report["group_parse_audit"],
            "label_usage": report["label_usage"],
        }
    )
    return result


def combined_metrics(reports: list[dict[str, Any]]) -> dict[str, Any]:
    cells = [dict(cell, dataset_day=report["dataset_day"]) for report in reports for cell in report["cells"]]
    representable = [cell for cell in cells if cell["true_world_representable"]]
    misspecified = [cell for cell in cells if not cell["true_world_representable"]]
    optimal_statuses = {"CERTIFIED_OPTIMAL", "NUMERICAL_MILP_OPTIMAL_REPLAYED"}
    exact = lambda cell: cell["lower_status"] == cell["upper_status"] and cell["lower_status"] in optimal_statuses
    false_certificates = sum(
        max(0, (cell["point_rule_threshold_errors"] or 0) - (cell["errors_flagged_ambiguous"] or 0))
        for cell in misspecified
    )
    false_certificate_snapshots = {
        (cell["dataset_day"], cell["snapshot_offset_seconds"])
        for cell in misspecified
        if (cell["point_rule_threshold_errors"] or 0) > (cell["errors_flagged_ambiguous"] or 0)
    }
    result: dict[str, Any] = {
        "eligible_snapshots": len({(cell["dataset_day"], cell["snapshot_offset_seconds"]) for cell in cells}),
        "cells": len(cells),
        "numerical_optimal_replayed_cells": sum(exact(cell) for cell in cells),
        "infeasible_cells": sum(cell["lower_status"] == cell["upper_status"] == "INFEASIBLE" for cell in cells),
        "truth_representable_cells": len(representable),
        "representable_truth_covered_cells": sum(cell["truth_covered"] for cell in representable),
        "representable_point_rule_threshold_errors": sum(cell["point_rule_threshold_errors"] or 0 for cell in representable),
        "representable_errors_flagged_ambiguous": sum(cell["errors_flagged_ambiguous"] or 0 for cell in representable),
        "misspecified_but_solver_feasible_cells": sum(exact(cell) for cell in misspecified),
        "misspecified_support_unflagged_wrong_decisions": false_certificates,
        "misspecified_support_unflagged_wrong_snapshot_count": len(false_certificate_snapshots),
        "independent_tiny_checked_cells": sum(
            cell.get("independent_tiny_check", "NOT_RUN_LEGACY")
            not in {"NOT_RUN_SIZE_LIMIT", "NOT_RUN_LEGACY"}
            for cell in cells
        ),
        "truth_representable_snapshots_by_radius_m": {},
    }
    for radius in sorted({cell["radius_m"] for cell in cells}):
        at_radius = [cell for cell in cells if cell["radius_m"] == radius]
        result["truth_representable_snapshots_by_radius_m"][str(radius)] = {
            "numerator": sum(cell["true_world_representable"] for cell in at_radius),
            "denominator": len(at_radius),
        }
    widest = max(cell["radius_m"] for cell in cells)
    widest_valid = [cell for cell in representable if cell["radius_m"] == widest]
    result["widest_radius_valid_decisions"] = {
        "radius_m": widest,
        "ambiguous": sum(cell["ambiguous_thresholds"] or 0 for cell in widest_valid),
        "total": sum(cell.get("decision_threshold_count", 3) for cell in widest_valid),
    }
    return result


def version_diff(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    old = combined_metrics(previous)
    new = combined_metrics(current)
    fields = [
        "eligible_snapshots", "cells", "numerical_optimal_replayed_cells", "infeasible_cells",
        "truth_representable_cells", "representable_truth_covered_cells",
        "representable_point_rule_threshold_errors", "representable_errors_flagged_ambiguous",
        "misspecified_support_unflagged_wrong_decisions",
        "misspecified_support_unflagged_wrong_snapshot_count",
    ]
    return {field: {"previous": old[field], "current": new[field], "delta": new[field] - old[field]} for field in fields}


def markdown(summary: dict[str, Any]) -> str:
    c = summary["combined"]
    wide = c["widest_radius_valid_decisions"]
    pct = 100.0 * wide["ambiguous"] / wide["total"] if wide["total"] else 0.0
    lines = [
        "# ATR DIAMOR dyad evidence audit v4", "",
        "Status: **PASS for computation, endpoint consistency, witness replay, and the independent tiny oracle.**", "",
        "This remains an oracle-assisted, q-conditioned audit. Candidate edge scoring is label-blind, but annotations are used for cohort exclusion, eligibility, the true dyad count q, and final evaluation.", "",
        "## Frozen result", "",
        f"- {c['eligible_snapshots']} eligible snapshots and {c['cells']} radius cells.",
        f"- {c['numerical_optimal_replayed_cells']} cells have replayed numerical MILP optima; {c['infeasible_cells']} are candidate-graph infeasible.",
        f"- Truth is representable in {c['truth_representable_cells']} cells and covered in {c['representable_truth_covered_cells']} of those cells.",
        f"- The minimum-distance point rule makes {c['representable_point_rule_threshold_errors']} threshold errors under valid support; all are ambiguous by construction.",
        f"- Under misspecified support, {c['misspecified_support_unflagged_wrong_decisions']} wrong point decisions are not flagged, across {c['misspecified_support_unflagged_wrong_snapshot_count']} snapshots.",
        f"- At {wide['radius_m']:g} m under valid support, {wide['ambiguous']}/{wide['total']} ({pct:.1f}%) threshold decisions are ambiguous.",
        f"- {c['independent_tiny_checked_cells']} cells are cross-checked by an independent subset-recursion oracle.", "",
        "The conditional coverage and conditional error flagging are implementation checks implied by optimizing over a feasible set that contains truth. They are not independent evidence of transfer or unconditional safety.", "",
        "## Version change", "",
        "The v4 parser understands the documented record layout sufficiently to quarantine all recoverable positive IDs in partial/nonpositive, mobility-aid, multiple-ID, one-sided, or conflicting annotations. Conflict quarantine closes over every affected group, so uncertain partners cannot re-enter as presumed singletons. DIAMOR-1 headline counts are unchanged. Relative to v2, DIAMOR-2 loses one eligible snapshot and changes several q-conditioned cells; the exact deltas are in `VERSION_DIFF.json`.", "",
        "The v4 replay additionally checks the raw solver vector, objective, dual bound, cardinality, degree, and integrality residuals. Full local reports contain index-based witnesses and solver diagnostics. Raw pedestrian IDs and relation assignments are not published in this summary.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--followup", type=Path, required=True)
    parser.add_argument("--previous-pilot", type=Path)
    parser.add_argument("--previous-followup", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    current_paths = [args.pilot, args.followup]
    current = [load(path) for path in current_paths]
    validate_current_reports(current)
    summary = {
        "report_version": "atr-diamor-dyad-truth-summary/v4",
        "days": [safe_day(report, path) for report, path in zip(current, current_paths)],
        "combined": combined_metrics(current),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (args.output / "REPORT.md").write_text(markdown(summary), encoding="utf-8")
    if args.previous_pilot and args.previous_followup:
        diff = version_diff([load(args.previous_pilot), load(args.previous_followup)], current)
        (args.output / "VERSION_DIFF.json").write_text(json.dumps(diff, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
