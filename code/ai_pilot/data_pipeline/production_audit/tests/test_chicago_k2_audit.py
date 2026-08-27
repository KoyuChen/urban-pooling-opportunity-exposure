import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR.parent))

from production_audit.chicago_k2_audit import (  # noqa: E402
    ContractError,
    LOGICAL_RULES,
    SCIPY_MILP_AVAILABLE,
    audit_rows,
    canonical_rows_sha256,
    load_contract,
    read_csv_rows,
    validate_contract,
    validate_report,
)


FIXTURE_DIR = PACKAGE_DIR / "fixtures"


def fixture_contract():
    return load_contract(FIXTURE_DIR / "synthetic_contract.json")


def fixture_rows():
    return read_csv_rows(FIXTURE_DIR / "synthetic_cross_midnight.csv")


def synthetic_row(
    trip_id,
    start,
    end,
    *,
    authorized="true",
    matched="true",
    pooled="2",
    pickup_lat="41.88",
    pickup_lon="-87.63",
    dropoff_lat="41.90",
    dropoff_lon="-87.62",
):
    return {
        "trip_id": trip_id,
        "trip_start_timestamp": start,
        "trip_end_timestamp": end,
        "shared_trip_authorized": authorized,
        "shared_trip_match": matched,
        "trips_pooled": pooled,
        "pickup_centroid_latitude": pickup_lat,
        "pickup_centroid_longitude": pickup_lon,
        "dropoff_centroid_latitude": dropoff_lat,
        "dropoff_centroid_longitude": dropoff_lon,
    }


def contract_for_rows(rows):
    contract = fixture_contract()
    contract["input"]["expected_row_count"] = len(rows)
    contract["input"]["expected_input_sha256"] = canonical_rows_sha256(rows)
    target_like_null_starts = sum(
        not str(row["trip_start_timestamp"]).strip()
        and str(row["shared_trip_match"]).strip().lower() == "true"
        and str(row["trips_pooled"]).strip() in {"2", "2.0"}
        for row in rows
    )
    if target_like_null_starts:
        contract["input"]["null_start_scope"] = (
            "all_literal_match_true_k2_null_start_rows_included"
        )
    else:
        contract["input"]["null_start_scope"] = (
            "server_verified_zero_literal_match_true_k2_null_start_rows"
        )
    contract["input"]["server_target_like_null_start_row_count"] = (
        target_like_null_starts
    )
    contract["input"]["null_start_count_evidence_sha256"] = "f" * 64
    contract["candidate_graph"]["heuristics"] = {
        "pickup_radius_km": None,
        "dropoff_radius_km": None,
        "direction_cosine_min": None,
        "per_node_degree_cap": None,
        "missing_spatial_policy": "retain",
    }
    return contract


class ChicagoK2ProductionAuditTests(unittest.TestCase):
    def test_duplicate_csv_headers_fail_closed_before_dict_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "duplicate-header.csv"
            path.write_text("trip_id,trip_id\nSYNTH_A,SYNTH_B\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate header"):
                read_csv_rows(path)

    def test_fixture_locks_cross_midnight_roles_and_closed_rounding_boundary(self):
        artifacts = audit_rows(
            fixture_rows(),
            fixture_contract(),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(
            set(artifacts.logical_edges),
            {(0, 1), (2, 3), (4, 5), (6, 7)},
        )
        self.assertEqual(artifacts.roles[0], "buffer")
        self.assertEqual(artifacts.roles[1], "core")
        self.assertEqual(artifacts.roles[6], "core")
        self.assertEqual(artifacts.roles[7], "buffer")
        logical = artifacts.report["candidate_graphs"]["logical_necessary"]
        self.assertEqual(logical["edge_provenance_counts"]["cross_midnight_edges"], 2)
        self.assertEqual(logical["cover_feasibility"]["status"], "EXACT_FEASIBLE")

        # Edge (2,3) exists only at equality:
        # 10:15 start / 10:30 end and 10:45 start / 11:00 end expand to
        # [10:07:30,10:37:30] and [10:37:30,11:07:30].
        self.assertIn((2, 3), artifacts.logical_edges)

    def test_possible_overlap_iff_inequalities_and_equality_is_not_dropped(self):
        rows = [
            synthetic_row("SYNTH_A", "2026-01-13T10:15:00", "2026-01-13T10:30:00"),
            synthetic_row("SYNTH_EQUAL", "2026-01-13T10:45:00", "2026-01-13T11:00:00"),
            synthetic_row("SYNTH_GAP", "2026-01-13T11:00:00", "2026-01-13T11:15:00"),
        ]
        artifacts = audit_rows(
            rows,
            contract_for_rows(rows),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertIn((0, 1), artifacts.logical_edges)
        self.assertNotIn((0, 2), artifacts.logical_edges)

    def test_authorized_is_audited_but_never_used_as_a_match_true_k2_screen(self):
        artifacts = audit_rows(
            fixture_rows(),
            fixture_contract(),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(artifacts.roles[4], "core")
        self.assertIn((4, 5), artifacts.logical_edges)
        consistency = artifacts.report["operator_consistency_audit"]
        self.assertEqual(consistency["counts"]["match_true_authorized_false"], 1)
        excluded = artifacts.report["candidate_graphs"]["logical_necessary"][
            "rules_explicitly_not_used"
        ]
        self.assertIn("authorization_equality_or_authorized_true_screen", excluded)

    def test_null_duplicate_and_literal_contradictions_are_not_coerced(self):
        artifacts = audit_rows(
            fixture_rows(),
            fixture_contract(),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        ids = artifacts.report["identifier_audit"]
        self.assertEqual(ids["null_or_blank_rows"], 1)
        self.assertEqual(ids["duplicate_rows"], 2)
        self.assertEqual(ids["duplicate_distinct_values"], 1)
        self.assertEqual(artifacts.roles[10:13], ("context", "context", "context"))
        fields = artifacts.report["literal_field_audit"]
        self.assertEqual(fields["match"]["null"], 1)
        self.assertEqual(fields["trips_pooled"]["positive_integer"], 16)
        consistency = artifacts.report["operator_consistency_audit"]["counts"]
        self.assertEqual(consistency["match_true_k_lt_2_or_unusable"], 1)
        self.assertEqual(
            consistency["match_false_k_2_not_a_logical_contradiction"], 1
        )

    def test_match_k_contradiction_and_unknown_match_block_population_claims(self):
        base = [
            synthetic_row("SYNTH_PAIR_A", "2026-01-13T10:00:00", "2026-01-13T10:30:00"),
            synthetic_row("SYNTH_PAIR_B", "2026-01-13T10:15:00", "2026-01-13T10:45:00"),
        ]
        with_k_contradiction = base + [
            synthetic_row(
                "SYNTH_BAD_K",
                "2026-01-13T12:00:00",
                "2026-01-13T12:30:00",
                pooled="1",
            )
        ]
        first = audit_rows(
            with_k_contradiction,
            contract_for_rows(with_k_contradiction),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(
            first.report["run_closure_audit"]["production_status"],
            "BLOCKED_MATCH_K_CONTRADICTIONS",
        )

        with_unknown_match = base + [
            synthetic_row(
                "SYNTH_UNKNOWN_MATCH",
                "2026-01-13T12:00:00",
                "2026-01-13T12:30:00",
                matched="",
            )
        ]
        second = audit_rows(
            with_unknown_match,
            contract_for_rows(with_unknown_match),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(
            second.report["run_closure_audit"]["production_status"],
            "BLOCKED_UNKNOWN_MATCH_LITERALS",
        )

    def test_spatial_radius_is_separate_and_can_destroy_declared_cover(self):
        artifacts = audit_rows(
            fixture_rows(),
            fixture_contract(),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertIn((0, 1), artifacts.logical_edges)
        self.assertNotIn((0, 1), artifacts.heuristic_edges)
        heuristic = artifacts.report["candidate_graphs"]["heuristic_sensitivity"]
        self.assertEqual(
            heuristic["classification"],
            "ANALYST_HEURISTIC_NOT_A_NECESSARY_SUPERGRAPH",
        )
        self.assertEqual(heuristic["partner_coverage_claim"], "NONE")
        self.assertEqual(
            heuristic["cover_feasibility"]["status"],
            "PROVEN_INFEASIBLE_ISOLATED_CORE",
        )

    def test_direction_screen_is_heuristic_and_does_not_mutate_logical_graph(self):
        rows = [
            synthetic_row("SYNTH_E1", "2026-01-13T10:00:00", "2026-01-13T11:00:00"),
            synthetic_row("SYNTH_E2", "2026-01-13T10:00:00", "2026-01-13T11:00:00"),
            synthetic_row(
                "SYNTH_W1",
                "2026-01-13T10:00:00",
                "2026-01-13T11:00:00",
                pickup_lat="41.90",
                pickup_lon="-87.62",
                dropoff_lat="41.88",
                dropoff_lon="-87.63",
            ),
            synthetic_row(
                "SYNTH_W2",
                "2026-01-13T10:00:00",
                "2026-01-13T11:00:00",
                pickup_lat="41.90",
                pickup_lon="-87.62",
                dropoff_lat="41.88",
                dropoff_lon="-87.63",
            ),
        ]
        contract = contract_for_rows(rows)
        contract["candidate_graph"]["heuristics"]["direction_cosine_min"] = 0.9
        artifacts = audit_rows(
            rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(len(artifacts.logical_edges), 6)
        self.assertEqual(len(artifacts.heuristic_edges), 2)
        self.assertEqual(
            artifacts.report["candidate_graphs"]["heuristic_sensitivity"][
                "sequential_edge_removals"
            ]["direction_cosine"],
            4,
        )

    def test_degree_cap_is_a_deterministic_sensitivity_graph_only(self):
        rows = [
            synthetic_row(f"SYNTH_CAP_{index}", "2026-01-13T10:00:00", "2026-01-13T11:00:00")
            for index in range(4)
        ]
        contract = contract_for_rows(rows)
        contract["candidate_graph"]["heuristics"]["per_node_degree_cap"] = 1
        first = audit_rows(
            rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        second = audit_rows(
            rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(len(first.logical_edges), 6)
        self.assertEqual(first.heuristic_edges, second.heuristic_edges)
        self.assertEqual(len(first.heuristic_edges), 2)
        heuristic = first.report["candidate_graphs"]["heuristic_sensitivity"]
        self.assertEqual(heuristic["sequential_edge_removals"]["degree_cap"], 4)
        self.assertEqual(heuristic["statistics"]["core_max_degree"], 1)

    def test_missing_timestamp_retains_indeterminate_edge_instead_of_false_exclusion(self):
        rows = [
            synthetic_row("SYNTH_CORE", "2026-01-13T10:00:00", "2026-01-13T10:30:00"),
            synthetic_row("SYNTH_UNKNOWN", "", ""),
        ]
        artifacts = audit_rows(
            rows,
            contract_for_rows(rows),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(artifacts.roles, ("core", "buffer"))
        self.assertEqual(artifacts.logical_edges, ((0, 1),))
        counts = artifacts.report["candidate_graphs"]["logical_necessary"][
            "edge_provenance_counts"
        ]
        self.assertEqual(counts["indeterminate_timestamp_edges"], 1)

    def test_one_buffer_cannot_cover_two_core_nodes(self):
        rows = [
            synthetic_row("SYNTH_CORE_A", "2026-01-13T10:00:00", "2026-01-13T10:15:00"),
            synthetic_row("SYNTH_CORE_B", "2026-01-13T11:00:00", "2026-01-13T11:15:00"),
            synthetic_row(
                "SYNTH_LONG_BUFFER",
                "2026-01-12T23:00:00",
                "2026-01-13T12:00:00",
            ),
        ]
        artifacts = audit_rows(
            rows,
            contract_for_rows(rows),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(set(artifacts.logical_edges), {(0, 2), (1, 2)})
        self.assertEqual(
            artifacts.report["candidate_graphs"]["logical_necessary"][
                "cover_feasibility"
            ]["status"],
            "EXACT_INFEASIBLE",
        )

    @unittest.skipUnless(SCIPY_MILP_AVAILABLE, "SciPy MILP is not installed")
    def test_production_milp_path_reports_numerical_not_exact_certificate(self):
        rows = [
            synthetic_row("SYNTH_MILP_A", "2026-01-13T10:00:00", "2026-01-13T10:30:00"),
            synthetic_row("SYNTH_MILP_B", "2026-01-13T10:15:00", "2026-01-13T10:45:00"),
        ]
        contract = contract_for_rows(rows)
        contract["candidate_graph"]["exact_fallback_max_core_nodes"] = 0
        artifacts = audit_rows(
            rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        feasibility = artifacts.report["candidate_graphs"]["logical_necessary"][
            "cover_feasibility"
        ]
        self.assertEqual(
            feasibility["status"],
            "NUMERICALLY_FEASIBLE_VALIDATED_INCUMBENT",
        )
        self.assertFalse(feasibility["certified_for_declared_graph"])
        self.assertEqual(feasibility["max_constraint_residual_after_rounding"], 0.0)
        self.assertIn(
            "NUMERICAL_UNCERTIFIED",
            artifacts.report["run_closure_audit"]["production_status"],
        )

    def test_duration_basis_changes_buffer_label_not_hidden_run_identification(self):
        rows = fixture_rows()[:8]
        contract = contract_for_rows(rows)
        contract["run_closure"]["duration_bound_basis"] = "operator_verified"
        contract["run_closure"]["duration_bound_evidence"] = {
            "authority": "city_of_chicago_or_dataset_operator",
            "effective_scope": "all_transactions_in_dataset_revision",
            "artifact_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        }
        artifacts = audit_rows(
            rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        closure = artifacts.report["run_closure_audit"]
        self.assertEqual(
            closure["boundary_extraction_support"]["status"],
            "PASS_UNDER_DECLARED_OPERATOR_VERIFIED_DURATION_BOUND",
        )
        self.assertEqual(
            closure["public_hidden_run_closure"]["status"],
            "NOT_IDENTIFIED_FROM_PUBLIC_ROWS",
        )
        self.assertEqual(
            artifacts.report["candidate_graphs"]["logical_necessary"][
                "partner_coverage_claim"
            ],
            "NOT_ESTIMATED_FROM_PUBLIC_ROWS",
        )

    def test_no_duration_bound_cannot_be_repaired_by_neighboring_day_buffer(self):
        rows = fixture_rows()[:8]
        contract = contract_for_rows(rows)
        contract["run_closure"]["maximum_transaction_duration_minutes"] = None
        contract["run_closure"]["duration_bound_basis"] = "none"
        contract["run_closure"]["duration_bound_evidence"] = {
            "authority": "none",
            "effective_scope": "none",
            "artifact_sha256": None,
        }
        artifacts = audit_rows(
            rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(
            artifacts.report["run_closure_audit"]["boundary_extraction_support"][
                "status"
            ],
            "NOT_EVALUATED_NO_DECLARED_DURATION_BOUND",
        )

    def test_authorized_only_extraction_fails_completeness_contract(self):
        rows = fixture_rows()[:8]
        contract = contract_for_rows(rows)
        contract["input"]["selection_scope"] = "authorized_only"
        artifacts = audit_rows(
            rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        checks = artifacts.report["input_checks"]
        self.assertEqual(checks["completeness_status"], "FAIL")
        self.assertIn("did not combine", " ".join(checks["failure_reasons"]))
        self.assertEqual(
            artifacts.report["run_closure_audit"]["production_status"],
            "BLOCKED_EXTRACTION_COMPLETENESS",
        )

    def test_input_hash_must_be_pinned_and_match_canonical_rows(self):
        rows = fixture_rows()[:8]
        contract = contract_for_rows(rows)
        contract["input"]["expected_input_sha256"] = None
        with self.assertRaisesRegex(ContractError, "pinned SHA-256"):
            validate_contract(contract)

        contract = contract_for_rows(rows)
        tampered_rows = deepcopy(rows)
        tampered_rows[0]["shared_trip_authorized"] = "false"
        artifacts = audit_rows(
            tampered_rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(len(tampered_rows), len(rows))
        self.assertNotEqual(
            artifacts.report["input_checks"]["actual_input_sha256"],
            contract["input"]["expected_input_sha256"],
        )
        self.assertEqual(artifacts.report["input_checks"]["completeness_status"], "FAIL")
        self.assertEqual(
            artifacts.report["run_closure_audit"]["production_status"],
            "BLOCKED_EXTRACTION_COMPLETENESS",
        )
        with self.assertRaises(TypeError):
            audit_rows(
                rows,
                contract_for_rows(rows),
                input_sha256=contract_for_rows(rows)["input"][
                    "expected_input_sha256"
                ],
            )

    def test_null_start_scope_blocks_range_query_omission_and_audits_supplement(self):
        rows_without_null_partner = [
            synthetic_row("SYNTH_CORE", "2026-01-13T10:00:00", "2026-01-13T10:30:00"),
            synthetic_row("SYNTH_FALSE_ALTERNATIVE", "2026-01-13T10:15:00", "2026-01-13T10:45:00"),
        ]
        unverified = contract_for_rows(rows_without_null_partner)
        unverified["input"]["null_start_scope"] = "not_verified"
        unverified["input"]["server_target_like_null_start_row_count"] = None
        unverified["input"]["null_start_count_evidence_sha256"] = None
        blocked = audit_rows(
            rows_without_null_partner,
            unverified,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(
            blocked.report["run_closure_audit"]["production_status"],
            "BLOCKED_NULL_START_SCOPE",
        )

        rows_with_null_partner = rows_without_null_partner + [
            synthetic_row("SYNTH_NULL_START_PARTNER", "", "2026-01-13T10:45:00")
        ]
        included = audit_rows(
            rows_with_null_partner,
            contract_for_rows(rows_with_null_partner),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(
            included.report["input_checks"]["null_start_scope_status"], "PASS"
        )
        self.assertEqual(included.roles[2], "buffer")
        self.assertIn((0, 2), included.logical_edges)

        omitted = contract_for_rows(rows_without_null_partner)
        omitted["input"]["null_start_scope"] = (
            "all_literal_match_true_k2_null_start_rows_included"
        )
        omitted["input"]["server_target_like_null_start_row_count"] = 1
        omitted["input"]["null_start_count_evidence_sha256"] = "f" * 64
        mismatch = audit_rows(
            rows_without_null_partner,
            omitted,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        self.assertEqual(
            mismatch.report["input_checks"]["null_start_scope_status"],
            "SERVER_INPUT_COUNT_MISMATCH",
        )
        self.assertEqual(
            mismatch.report["run_closure_audit"]["production_status"],
            "BLOCKED_NULL_START_SCOPE",
        )

    def test_date_only_and_off_grid_target_times_are_indeterminate_and_blocking(self):
        for malformed in ("2026-01-13", "2026-01-13T10:01:00"):
            with self.subTest(malformed=malformed):
                rows = [
                    synthetic_row(
                        "SYNTH_VALID_TIME",
                        "2026-01-13T10:00:00",
                        "2026-01-13T10:30:00",
                    ),
                    synthetic_row(
                        "SYNTH_MALFORMED_TIME",
                        malformed,
                        "2026-01-13T10:45:00",
                    ),
                ]
                artifacts = audit_rows(
                    rows,
                    contract_for_rows(rows),
                    generated_at_utc="2026-08-27T00:00:00+00:00",
                )
                self.assertEqual(artifacts.roles[1], "buffer")
                self.assertIn((0, 1), artifacts.logical_edges)
                self.assertEqual(
                    artifacts.report["run_closure_audit"]["production_status"],
                    "BLOCKED_TARGET_TIMESTAMP_INTEGRITY",
                )

    def test_declared_duration_bound_is_falsified_by_released_lower_bound(self):
        rows = [
            synthetic_row("SYNTH_LONG_A", "2026-01-13T10:00:00", "2026-01-13T10:30:00"),
            synthetic_row("SYNTH_LONG_B", "2026-01-13T10:15:00", "2026-01-13T10:45:00"),
        ]
        contract = contract_for_rows(rows)
        contract["run_closure"]["maximum_transaction_duration_minutes"] = 10
        artifacts = audit_rows(
            rows,
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        boundary = artifacts.report["run_closure_audit"][
            "boundary_extraction_support"
        ]
        self.assertEqual(
            boundary["status"],
            "FAIL_DURATION_BOUND_CONTRADICTED_BY_RELEASED_TIMES",
        )
        self.assertEqual(boundary["rows_contradicting_declared_duration_bound"], 2)
        self.assertEqual(
            artifacts.report["run_closure_audit"]["production_status"],
            "BLOCKED_BOUNDARY_SUPPORT",
        )

    def test_operational_edge_limit_aborts_instead_of_becoming_degree_cap(self):
        contract = fixture_contract()
        contract["candidate_graph"]["max_materialized_logical_edges"] = 2
        artifacts = audit_rows(
            fixture_rows(),
            contract,
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        logical = artifacts.report["candidate_graphs"]["logical_necessary"]
        self.assertEqual(logical["materialization_status"], "UNRESOLVED_NOT_TRIMMED")
        self.assertEqual(logical["statistics"]["edge_count"], None)
        self.assertEqual(
            artifacts.report["run_closure_audit"]["production_status"],
            "BLOCKED_LOGICAL_GRAPH_RESOURCE_LIMIT",
        )

    def test_report_serialization_contains_no_fixture_trip_ids(self):
        rows = fixture_rows()
        artifacts = audit_rows(
            rows,
            fixture_contract(),
            generated_at_utc="2026-08-27T00:00:00+00:00",
        )
        serialized = json.dumps(artifacts.report, sort_keys=True)
        for row in rows:
            trip_id = row["trip_id"].strip()
            if trip_id:
                self.assertNotIn(trip_id, serialized)
        self.assertFalse(artifacts.report["redaction"]["raw_trip_identifiers_emitted"])

    def test_contract_locks_logical_rules_and_closed_interval_policy(self):
        contract = fixture_contract()
        contract["candidate_graph"]["logical_rules"] = list(LOGICAL_RULES) + [
            "pickup_radius_km"
        ]
        with self.assertRaisesRegex(ContractError, "locked necessary-rule"):
            validate_contract(contract)

        contract = fixture_contract()
        contract["timestamp_release"]["interpretation"] = "half_open"
        with self.assertRaisesRegex(ContractError, "closed_outer_interval"):
            validate_contract(contract)

        contract = fixture_contract()
        contract["timestamp_release"]["rounding_minutes"] = 10
        with self.assertRaisesRegex(ContractError, "locked to 15"):
            validate_contract(contract)

        contract = fixture_contract()
        contract["run_closure"]["duration_bound_basis"] = "operator_verified"
        with self.assertRaisesRegex(ContractError, "authority"):
            validate_contract(contract)

        contract = fixture_contract()
        contract["run_closure"]["duration_bound_basis"] = "operator_verified"
        contract["run_closure"]["duration_bound_evidence"] = {
            "authority": "city_of_chicago_or_dataset_operator",
            "effective_scope": "all_transactions_in_dataset_revision",
            "artifact_sha256": "trust me",
        }
        with self.assertRaisesRegex(ContractError, "pinned artifact SHA-256"):
            validate_contract(contract)

        contract = fixture_contract()
        contract["run_closure"]["duration_bound_evidence"]["private_reference"] = (
            "PRIVATE_RAW_ID_MUST_NOT_BE_ACCEPTED"
        )
        with self.assertRaisesRegex(ContractError, "requires authority"):
            validate_contract(contract)

        contract = fixture_contract()
        contract["columns"]["shared_trip_authorized"] = contract["columns"][
            "shared_trip_match"
        ]
        with self.assertRaisesRegex(ContractError, "pairwise distinct"):
            validate_contract(contract)

    def test_machine_readable_contract_report_schemas_and_templates_are_json(self):
        paths = [
            PACKAGE_DIR / "contract.schema.json",
            PACKAGE_DIR / "report.schema.json",
            PACKAGE_DIR / "templates" / "contract.template.json",
            PACKAGE_DIR / "templates" / "report.template.json",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                with path.open("r", encoding="utf-8") as handle:
                    self.assertIsInstance(json.load(handle), dict)
        with (PACKAGE_DIR / "templates" / "contract.template.json").open(
            "r", encoding="utf-8"
        ) as handle:
            validate_contract(json.load(handle))
        with (PACKAGE_DIR / "templates" / "report.template.json").open(
            "r", encoding="utf-8"
        ) as handle:
            validate_report(json.load(handle))


if __name__ == "__main__":
    unittest.main()
