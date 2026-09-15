#!/usr/bin/env python3
"""Build and verify the NYC evidence/claim ledger from frozen summaries.

The ledger keeps four distinct questions separate: outcome endpoints and
decision ambiguity, integer support maximization, fixed-q model comparison,
and outcome-blind geometry coverage.  A pass for one question never repairs a
hold or unresolved status for another.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def integer_sum(rows: list[dict[str, str]], key: str) -> int:
    return sum(int(row[key]) for row in rows)


def decision_record(root: Path) -> dict[str, Any]:
    summary_path = root / "ORDERED_DECISION_PANEL_SUMMARY.json"
    groups_path = root / "ORDERED_DECISION_PANEL_GROUPS.csv"
    threshold_path = root / "ORDERED_DECISION_THRESHOLD_GROUPS.csv"
    summary = read_json(summary_path)
    groups = read_csv(groups_path)
    thresholds = read_csv(threshold_path)
    if summary["panel_audit"]["status"] != "PASS":
        raise ValueError("decision-panel denominator audit is not PASS")
    if int(summary["observed_report_count"]) != int(summary["predeclared_window_count"]):
        raise ValueError("decision panel lacks a terminal report")
    if int(summary["eligible_window_count"]) + int(summary["ineligible_window_count"]) != int(summary["predeclared_window_count"]):
        raise ValueError("decision-panel eligibility denominator does not reconcile")
    if integer_sum(groups, "cell_count") != int(summary["outcome_cell_count"]):
        raise ValueError("decision-panel outcome cells do not reconcile")
    if integer_sum(groups, "exact_cell_count") != int(summary["exact_outcome_cell_count"]):
        raise ValueError("decision-panel numerical endpoint counts do not reconcile")
    median_rows = [row for row in thresholds if row["threshold_rule"] == "candidate_median"]
    ambiguity = integer_sum(median_rows, "certified_ambiguous_count")
    unresolved = integer_sum(median_rows, "unresolved_count")
    if ambiguity != int(summary["certified_ambiguous_cell_count"]) or ambiguity + unresolved != int(summary["outcome_cell_count"]):
        raise ValueError("decision-panel ambiguity denominator does not reconcile")
    return {
        "evidence_object": "outcome_decision_panel",
        "question": "What outcome ranges and threshold decisions are invariant over the declared feasible worlds?",
        "status": "PASS_PANEL_WITH_UNRESOLVED_ENDPOINTS",
        "declared_units": int(summary["predeclared_window_count"]),
        "eligible_units": int(summary["eligible_window_count"]),
        "scientifically_ineligible_units": int(summary["ineligible_window_count"]),
        "transport_or_missing_units": int(summary["technical_failure_count"]) + int(summary["missing_report_count"]),
        "analysis_cells": int(summary["outcome_cell_count"]),
        "primary_certified_count": int(summary["exact_outcome_cell_count"]),
        "primary_unresolved_count": int(summary["outcome_cell_count"]) - int(summary["exact_outcome_cell_count"]),
        "secondary_result": (
            f"{ambiguity}/{summary['outcome_cell_count']} candidate-median decisions "
            f"witness-certified ambiguous; {unresolved} unresolved"
        ),
        "certificate_type": "NUMERICAL_ENDPOINT_PAIR_OR_TWO_SIDED_FEASIBLE_WITNESSES",
        "supported_claim": "Conditional fixed-support outcome frontiers and decision ambiguity on 21 eligible windows.",
        "not_supported": summary["claim_boundary"]["not_supported"],
        "source_files": [summary_path.name, groups_path.name, threshold_path.name],
    }


def scale_record(root: Path) -> dict[str, Any]:
    manifest_path = root / "BRANCH_AND_PRICE_SCALE_MANIFEST.json"
    cells_path = root / "BRANCH_AND_PRICE_SCALE_CELLS.csv"
    manifest = read_json(manifest_path)
    cells = read_csv(cells_path)
    declared = int(manifest["design"]["predeclared_cell_count"])
    if len(cells) != declared or int(manifest["summary"]["completed_cell_count"]) != declared:
        raise ValueError("scale-lattice denominator does not reconcile")
    for row in cells:
        if row["status"] != "INTEGER_OPTIMUM_CERTIFIED":
            raise ValueError("scale lattice retains a non-certified final cell")
        if abs(float(row["global_lower_bound"]) - float(row["global_upper_bound"])) > 1e-8:
            raise ValueError("scale-lattice certified cell has an open bound")
    historical_open = len(manifest.get("followup", {}).get("artifacts", []))
    return {
        "evidence_object": "support_maximization_lattice",
        "question": "Can the branch-and-price implementation certify maximum selected-buffer support on the frozen nested-size cohort?",
        "status": "PASS_INTEGER_SUPPORT",
        "declared_units": declared,
        "eligible_units": declared,
        "scientifically_ineligible_units": 0,
        "transport_or_missing_units": 0,
        "analysis_cells": declared,
        "primary_certified_count": declared,
        "primary_unresolved_count": 0,
        "secondary_result": f"{historical_open} cells were initially open and later closed; earlier anytime bounds remain in provenance",
        "certificate_type": "INTEGER_INCUMBENT_EQUALS_GLOBAL_BOUND_AND_BRANCH_QUEUE_CLOSED",
        "supported_claim": manifest["claim_boundary"]["supported"],
        "not_supported": manifest["claim_boundary"]["not_supported"],
        "source_files": [manifest_path.name, cells_path.name],
    }


def structure_record(root: Path) -> dict[str, Any]:
    report_path = root / "structure_audit_20260908" / "REPORT.json"
    report = read_json(report_path)
    summary = report["summary"]
    if summary["verification_status"] != "PASS" or int(summary["unresolved_verification_count"]) != 0:
        raise ValueError("fixed-q structure audit is not verified")
    if len(report["comparisons"]) != int(summary["fixed_q_comparisons"]):
        raise ValueError("fixed-q comparison denominator does not reconcile")
    changed = sum(bool(row["endpoint_changed_exactly"]) for row in report["comparisons"])
    if changed != int(summary["changed_fixed_q_comparisons"]):
        raise ValueError("fixed-q changed comparison count does not reconcile")
    return {
        "evidence_object": "fixed_q_structure_comparator",
        "question": "Do pair or clique restrictions change endpoints at common positive q on one fixed small input?",
        "status": "PASS_VERIFIED_NULL",
        "declared_units": int(summary["fixed_q_comparisons"]),
        "eligible_units": int(summary["fixed_q_comparisons"]),
        "scientifically_ineligible_units": 0,
        "transport_or_missing_units": 0,
        "analysis_cells": int(summary["fixed_q_comparisons"]),
        "primary_certified_count": int(summary["fixed_q_comparisons"]),
        "primary_unresolved_count": 0,
        "secondary_result": f"{changed}/{summary['fixed_q_comparisons']} comparisons change an endpoint",
        "certificate_type": "CERTIFIED_FIXED_Q_ENDPOINT_COMPARISON",
        "supported_claim": report["claim_boundary"]["supported"],
        "not_supported": report["claim_boundary"]["not_supported"],
        "source_files": [str(report_path.relative_to(root))],
    }


def geometry_record(root: Path) -> dict[str, Any]:
    audit_path = root / "geometry_census_20260908" / "recovery_attempt" / "RECOVERY_AUDIT.json"
    audit = read_json(audit_path)
    counts = audit["status_counts"]
    declared = int(audit["declared_cells"])
    if sum(int(value) for value in counts.values()) != declared:
        raise ValueError("geometry-census denominator does not reconcile")
    if not str(audit["status"]).startswith("HOLD"):
        raise ValueError("incomplete geometry census must remain HOLD")
    transport = int(counts["TRANSPORT_FAILURE"]) + int(counts["TRANSPORT_DEADLINE"])
    return {
        "evidence_object": "outcome_blind_geometry_census",
        "question": "How often is a local non-clique event column available in the declared public candidate geometry?",
        "status": "HOLD_TRANSPORT_INCOMPLETE",
        "declared_units": declared,
        "eligible_units": int(counts["GEOMETRY_COMPLETE"]),
        "scientifically_ineligible_units": int(counts["INELIGIBLE_NO_QUALIFIED_CORE"]),
        "transport_or_missing_units": transport,
        "analysis_cells": declared,
        "primary_certified_count": int(audit["full_nonclique_event_available_views"]),
        "primary_unresolved_count": transport,
        "secondary_result": "8/8 completed full views contain a local core-touching non-clique column; 13/24 cells remain transport-unresolved",
        "certificate_type": "LOCAL_EVENT_COLUMN_AVAILABILITY_ONLY",
        "supported_claim": "Geometry-only availability among eight completed views, with the full 24-cell denominator retained.",
        "not_supported": audit["claim_boundary"].replace("Geometry only. ", ""),
        "source_files": [str(audit_path.relative_to(root))],
    }


def build(root: Path) -> dict[str, Any]:
    records = [decision_record(root), scale_record(root), structure_record(root), geometry_record(root)]
    source_hashes = {}
    for record in records:
        for relative in record["source_files"]:
            source_hashes[relative] = sha256_file(root / relative)
    return {
        "report_version": "nyc-evidence-claim-ledger/v1",
        "overall_status": "PASS_CLAIM_ALIGNMENT_WITH_GEOMETRY_HOLD",
        "records": records,
        "source_sha256": source_hashes,
        "global_boundary": "No object identifies realized memberships, population prevalence, production logic, or a city-scale guarantee.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# NYC evidence and claim ledger",
        "",
        f"Overall status: **{report['overall_status']}**.",
        "",
        "| Evidence object | Scientific question | Status | Certified / cells | Unresolved |",
        "|---|---|---|---:|---:|",
    ]
    for row in report["records"]:
        lines.append(
            f"| `{row['evidence_object']}` | {row['question']} | `{row['status']}` | "
            f"{row['primary_certified_count']}/{row['analysis_cells']} | {row['primary_unresolved_count']} |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "The 18/18 support-maximization result does not close the decision panel's 25 numerically unresolved outcome endpoint pairs. Conversely, two-sided feasible witnesses certify 125/126 median-threshold decisions as ambiguous without requiring optimal endpoints. The 0/24 fixed-q structure result is a verified null on one small common-intersection input. The geometry census remains HOLD because 13/24 declared cells are transport-unresolved; its eight completed views establish only local column availability.",
        "",
        "Historical timeouts remain in provenance and are never called infeasible. " + report["global_boundary"],
        "",
    ])
    return "\n".join(lines)


def render_tex(report: dict[str, Any]) -> str:
    decision, scale, structure, geometry = report["records"]
    return (
        "% Generated by audit_nyc_claim_ledger.py.\n"
        "\\paragraph{NYC evidence ledger.} The outcome panel numerically closes "
        f"{decision['primary_certified_count']}/{decision['analysis_cells']} endpoint pairs, while two-sided feasible witnesses certify {decision['secondary_result'].split(' candidate-median')[0]} candidate-median decisions as ambiguous. "
        f"The separate support-maximization lattice certifies {scale['primary_certified_count']}/{scale['analysis_cells']} integer optima; it does not repair the outcome endpoints. "
        f"The fixed-$q$ model comparison changes {structure['secondary_result'].split(' comparisons')[0]} comparisons, whereas the geometry census remains HOLD with {geometry['transport_or_missing_units']}/{geometry['declared_units']} transport-unresolved cells. "
        "No result identifies realized memberships or population prevalence.\n"
    )


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    scalar_records = [{key: value for key, value in row.items() if key != "source_files"} for row in records]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scalar_records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(scalar_records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.results_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "NYC_EVIDENCE_LEDGER.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(args.output_dir / "NYC_EVIDENCE_LEDGER.csv", report["records"])
    (args.output_dir / "REPORT.md").write_text(render_markdown(report), encoding="utf-8")
    (args.output_dir / "RESULTS.tex").write_text(render_tex(report), encoding="utf-8")
    outputs = ("NYC_EVIDENCE_LEDGER.json", "NYC_EVIDENCE_LEDGER.csv", "REPORT.md", "RESULTS.tex")
    manifest = {
        "report_version": "nyc-evidence-claim-ledger-manifest/v1",
        "input_sha256": report["source_sha256"],
        "output_sha256": {name: sha256_file(args.output_dir / name) for name in outputs},
    }
    (args.output_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": report["overall_status"], "record_count": len(report["records"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
