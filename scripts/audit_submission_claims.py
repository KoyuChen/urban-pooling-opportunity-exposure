#!/usr/bin/env python3
"""Fail closed when manuscript headline claims drift from frozen evidence."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import tempfile

from rehearse_submission_artifacts import run as rehearse_artifacts


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
RESULTS = ROOT / "code" / "ai_pilot"


def read_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def read_json(relative: str) -> dict:
    return json.loads(read_text(relative))


def require(relative: str, *fragments: str) -> int:
    text = " ".join(read_text(relative).split())
    missing = [
        fragment for fragment in fragments
        if " ".join(fragment.split()) not in text
    ]
    if missing:
        raise AssertionError(f"{relative} is missing required claims: {missing}")
    return len(fragments)


def forbid(relative: str, *fragments: str) -> int:
    text = " ".join(read_text(relative).split())
    present = [
        fragment for fragment in fragments
        if " ".join(fragment.split()) in text
    ]
    if present:
        raise AssertionError(f"{relative} contains forbidden claims: {present}")
    return len(fragments)


def main() -> None:
    evidence_checks = 0
    boundary_guards = 0

    boundary_guards += require(
        "paper/main.tex",
        "Aggregate Identification over Hidden Temporal-Event Partitions",
        "Existing methods bound aggregates over uncertain record linkages or database repairs",
    )
    boundary_guards += require(
        "paper/sections/related_work.tex",
        "chen2019constrained",
        "possible-world aggregation, matching constraints, extremal bounds, and candidate-omission risk are not new here",
        "The narrow distinction is the latent world being quantified over",
        "object-level constraints rather than a new semantics for uncertain aggregation",
    )

    controlled_path = (
        RESULTS
        / "benchmarks"
        / "results"
        / "controlled_truth_joint_coverage_20260914"
        / "JOINT_COVERAGE_SUMMARY.csv"
    )
    with controlled_path.open(encoding="utf-8", newline="") as handle:
        controlled = {
            (int(row["capacity"]), int(row["retained_buffer_count"])): row
            for row in csv.DictReader(handle)
        }
    expected_six = {
        2: (0.83405, 0.314, 0.692, 0.6396666666666667, 0.07243355914538822),
        3: (0.8375, 0.319, 0.711, 0.6336666666666667, 0.06891109942135717),
        4: (0.83765, 0.326, 0.717, 0.6336666666666667, 0.07680168332456602),
    }
    for capacity, expected in expected_six.items():
        row = controlled[(capacity, 6)]
        actual = tuple(
            float(row[key])
            for key in (
                "mean_candidate_recall",
                "full_world_coverage_rate",
                "true_aggregate_coverage_rate",
                "threshold_certification_rate",
                "threshold_false_certificate_rate_among_certified",
            )
        )
        assert all(math.isclose(a, b, rel_tol=0.0, abs_tol=1e-15) for a, b in zip(actual, expected))
        assert float(controlled[(capacity, 8)]["threshold_false_certificate_rate_all_cells"]) == 0.0
        evidence_checks += 2
    evidence_checks += require(
        "paper/sections/controlled_validation.tex",
        "83.4\\% & 31.4\\%",
        "83.8\\% & 31.9\\%",
        "83.8\\% & 32.6\\%",
        "6.9--7.7\\%",
        "no certificate is false",
    )

    atr = read_json(
        "code/ai_pilot/benchmarks/results/atr_diamor_support_calibration/SUMMARY.json"
    )
    assert atr["status"] == "PASS"
    assert atr["followup_eligible_snapshots"] == 82
    assert atr["followup_selected_rule"]["covered_snapshots"] == 81
    assert atr["followup_frontier"]["threshold_decisions"] == 246
    assert atr["followup_frontier"]["certified_threshold_decisions"] == 29
    evidence_checks += 5
    evidence_checks += require(
        "paper/main.tex",
        "81/82 follow-up worlds",
        "29/246 decisions",
    )
    boundary_guards += require(
        "paper/sections/atr_transfer.tex",
        "one-coder annotated reference",
        "neither validates city candidate rules nor",
        "estimates group prevalence",
    )

    chicago = read_json(
        "code/ai_pilot/data_pipeline/results/chicago_k2_followup/"
        "gap_amendment_20260913/MANIFEST.json"
    )
    assert chicago["claim_status"] == "PASS_EXECUTION_NOT_FULL_ENDPOINT_CLOSURE"
    assert chicago["declared_window_count"] == 96
    assert chicago["data_complete_endpoint_pair_count"] == 10762
    assert abs(chicago["data_complete_numerical_certification_rate"] - 10728 / 10762) < 1e-15
    evidence_checks += 4
    chicago_report = read_text(
        "code/ai_pilot/data_pipeline/results/chicago_k2_followup/"
        "gap_amendment_20260913/FOLLOWUP_REPORT.md"
    )
    for fragment in (
        "96/90/6/0/0",
        "10,728 were numerically certified",
        "2,628 lacked public",
        "34 remained computationally unresolved",
    ):
        assert fragment in chicago_report
        evidence_checks += 1
    evidence_checks += require(
        "paper/main.tex",
        "90/96 windows",
        "10,728/10,762 data-complete endpoint pairs",
        "34 remain unresolved",
    )
    boundary_guards += require(
        "paper/sections/data_results.tex",
        "not independent samples, operational partner coverage, or citywide prevalence",
    )

    nyc = read_json(
        "code/ai_pilot/data_pipeline/results/nyc_hvfhv/"
        "evidence_ledger_20260915/NYC_EVIDENCE_LEDGER.json"
    )
    records = {record["evidence_object"]: record for record in nyc["records"]}
    panel = records["outcome_decision_panel"]
    support = records["support_maximization_lattice"]
    structure = records["fixed_q_structure_comparator"]
    geometry = records["outcome_blind_geometry_census"]
    assert (panel["analysis_cells"], panel["primary_certified_count"], panel["primary_unresolved_count"]) == (126, 101, 25)
    assert panel["secondary_result"].startswith("125/126")
    assert (support["analysis_cells"], support["primary_certified_count"]) == (18, 18)
    assert (structure["analysis_cells"], structure["primary_certified_count"]) == (24, 24)
    assert structure["secondary_result"] == "0/24 comparisons change an endpoint"
    assert (geometry["declared_units"], geometry["eligible_units"], geometry["scientifically_ineligible_units"], geometry["transport_or_missing_units"]) == (24, 8, 3, 13)
    evidence_checks += 6
    evidence_checks += require(
        "paper/sections/data_results.tex",
        "125 cells have replayed feasible values on both sides",
        "none of the 24 endpoint-pair comparisons changes",
        "eight geometry-complete, three scientifically ineligible, and thirteen",
        "closes all 18 maximum-support problems",
        "25 numerically unresolved outcome pairs",
    )
    boundary_guards += require(
        "paper/sections/data_results.tex",
        "does not by itself establish a complete feasible world",
        "a city-scale runtime guarantee",
        "or recover true memberships",
    )

    nonclique = read_json(
        "code/ai_pilot/data_pipeline/results/nyc_hvfhv/"
        "nonclique_structure_20260923/SUMMARY.json"
    )
    nonclique_summary = nonclique["summary"]
    assert nonclique["status"] == "PASS_PUBLIC_NONCLIQUE_TEST_NULL"
    assert nonclique["denominator"]["completed_geometry_windows"] == 8
    assert nonclique["denominator"]["eligible_nonclique_small_views"] == 4
    assert nonclique["denominator"]["transport_unresolved_cells"] == 13
    assert nonclique_summary["declared_comparisons"] == 192
    assert nonclique_summary["certified_comparisons"] == 96
    assert nonclique_summary["changed_comparisons"] == 0
    assert nonclique_summary["common_feasible_world_cells"] == 24
    assert nonclique_summary["ordered_more_worlds_than_clique_cells"] == 1
    assert nonclique_summary["ordered_more_worlds_than_pair_cells"] == 3
    assert nonclique_summary["unresolved_verification_count"] == 0
    evidence_checks += 11
    evidence_checks += require(
        "paper/sections/data_results.tex",
        "All 96\ncommon-support comparisons certify",
        "but 0/48 endpoints move for\neither restriction",
        "add buffer worlds versus\ncliques in 1/24",
    )
    boundary_guards += require(
        "paper/sections/data_results.tex",
        "The census denominator remains 8 complete, 3 ineligible",
        "this conditional null is neither model equivalence",
        "nor evidence of true-event recovery or prevalence",
    )
    boundary_guards += forbid(
        "paper/main.tex",
        "public-data advantage of general ordered-event structure",
        "city-scale closure",
    )

    attainment = read_json(
        "code/ai_pilot/data_pipeline/results/nyc_hvfhv/"
        "nonclique_endpoint_attainment_20260925/SUMMARY.json"
    )
    attainment_summary = attainment["summary"]
    assert attainment["status"] == "PASS_ENDPOINT_ATTAINMENT_NULL_EXPLAINED"
    assert attainment_summary["endpoint_attainment_checks"] == 192
    assert attainment_summary["attained_endpoint_checks"] == 192
    assert attainment_summary["unresolved_endpoint_checks"] == 0
    assert attainment_summary["partition_only_cells"] == 36
    assert attainment_summary["extra_subset_cells"] == 4
    assert attainment_summary["identical_partition_and_subset_cells"] == 8
    assert attainment_summary["endpoint_checks_with_ordered_only_ties"] == 0
    evidence_checks += 8
    evidence_checks += require(
        "paper/sections/data_results.tex",
        "in all 192 lower/upper\nchecks",
        "36 add only event partitions, four add projected\nsubsets, and eight add neither",
        "no added subset ties a declared-query endpoint",
    )
    boundary_guards += require(
        "paper/sections/data_results.tex",
        "without changing queries",
        "a family can expand before its projected additive frontier does",
    )

    projection = read_json(
        "code/ai_pilot/benchmarks/results/"
        "projection_frontier_theory_20260926/SUMMARY.json"
    )
    projection_audit = projection["audit"]
    projection_witness = projection["minimal_separation_witness"]
    assert projection["status"] == "PASS_PROJECTION_TO_FRONTIER_THEORY"
    assert projection_audit["fixed_q_cells"] == 14
    assert projection_audit["nested_family_pairs"] == 846
    assert projection_audit["exposed_face_checks"] == 503_310
    assert projection_audit["separator_checks"] == 728
    assert projection_audit["mismatches"] == 0
    assert projection_witness["strictly_interior"] is True
    assert projection_witness[
        "three_buffers_minimal_for_strict_interior_with_distinct_weights"
    ] is True
    evidence_checks += 8
    evidence_checks += require(
        "paper/sections/appendix.tex",
        "Projection-to-frontier equivalence",
        "if and only if $\\mathcal Z_R$ intersects both faces",
        "for every $w\\in\\mathbb R^{B_0}$ if and only if",
        "their positive Hamming distance",
    )
    evidence_checks += require(
        "paper/sections/data_results.tex",
        "the single-query case of Proposition~\\ref{prop:projectionfrontier}",
        "not a claim that all additive frontiers coincide",
    )
    boundary_guards += require(
        "paper/sections/appendix.tex",
        "Partition-dependent outcomes such as event count are outside the proposition",
        "they are not new public-data queries",
    )

    cache = read_json(
        "code/ai_pilot/data_pipeline/results/nyc_hvfhv/"
        "branch_price_cache_reconstruction_20260919/SUMMARY.json"
    )
    assert cache["cell_count"] == 4
    assert cache["all_certificates_and_branch_paths_equal"] is True
    assert cache["all_baselines_match_historical_diagnostics"] is True
    assert cache["byte_identical_old_input_claim"] is False
    assert cache["total_baseline_oracle_lp_calls"] == 1_880_627
    assert cache["total_accelerated_oracle_lp_calls"] == 1_324_841
    assert round(cache["total_oracle_lp_call_reduction_rate"] * 100, 1) == 29.6
    evidence_checks += 7
    evidence_checks += require(
        "paper/sections/data_results.tex",
        "29.6\\%",
        "snapshot-consistent",
        "not a byte-identical replay",
    )
    boundary_guards += require(
        "paper/sections/data_results.tex",
        "timing remains descriptive",
    )

    boundary_guards += forbid("paper/sections/appendix.tex", "& Exact &")
    boundary_guards += require(
        "paper/sections/appendix.tex",
        "& Certified &",
        "not exact arithmetic",
    )
    boundary_guards += require(
        "paper/sections/discussion.tex",
        "are not rational-arithmetic proof certificates",
        "Neither supports city-scale",
        "or population prevalence",
    )

    complexity = read_json(
        "code/ai_pilot/benchmarks/results/complexity_boundary_20260922/SUMMARY.json"
    )
    validation = complexity["exhaustive_validation"]
    assert complexity["gate"] == "PASS_TRACTABLE_BOUNDARY_WITH_HARDNESS_OPEN"
    assert complexity["hardness_status"] == "NOT_ESTABLISHED"
    assert validation["low_depth_capacity_cases_checked"] == 2956
    assert validation["fixed_q_cells_checked"] == 752
    assert validation["component_formula_mismatches"] == 0
    assert validation["well_anchored_fixed_q_mismatches"] == 0
    assert complexity["fixed_q_gap_witness"]["feasible_q_values"] == [0, 2]
    evidence_checks += 7
    boundary_guards += require(
        "paper/sections/algorithms.tex",
        "exact-$q$ feasibility and support-at-least-$q$ are distinct",
        "General core-cover complexity, including fixed $C=2$, is not settled here",
        "not NP-hardness",
    )
    boundary_guards += require(
        "paper/sections/appendix.tex",
        "A Tractable Global Boundary and a Fixed-Support Gap",
        "Thus $Q=\\{0,2\\}$",
    )
    boundary_guards += forbid(
        "paper/sections/algorithms.tex",
        "fixed $C=2$ is NP-hard",
        "fixed $C=2$ is polynomial",
    )

    with tempfile.TemporaryDirectory(prefix="eventfrontier-submission-rehearsal-") as temporary:
        rehearsal = rehearse_artifacts(ROOT, Path(temporary))
    print(f"Aggregate artifact rehearsal: PASS ({rehearsal['table_count']} tables, "
          f"{rehearsal['table_cells']} cells; raw replay limits retained)")
    print(
        "Submission claim audit: PASS "
        f"({evidence_checks} evidence checks, {boundary_guards} boundary guards)"
    )


if __name__ == "__main__":
    main()
