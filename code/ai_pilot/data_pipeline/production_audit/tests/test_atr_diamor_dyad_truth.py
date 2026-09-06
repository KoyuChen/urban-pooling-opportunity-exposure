import importlib.util
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "benchmarks" / "atr_diamor_dyad_truth.py"
SPEC = importlib.util.spec_from_file_location("atr_truth", MODULE_PATH)
atr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = atr
SPEC.loader.exec_module(atr)

SUMMARY_PATH = ROOT / "benchmarks" / "atr_diamor_evidence_summary.py"
SUMMARY_SPEC = importlib.util.spec_from_file_location("atr_summary", SUMMARY_PATH)
atr_summary = importlib.util.module_from_spec(SUMMARY_SPEC)
assert SUMMARY_SPEC.loader is not None
sys.modules[SUMMARY_SPEC.name] = atr_summary
SUMMARY_SPEC.loader.exec_module(atr_summary)


class AtrTruthTests(unittest.TestCase):
    def test_group_parser_and_larger_group_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.dat"
            path.write_text("1 2 2 0\n2 2 1 0\n3 3 4 5 0\n4 3 3 5 0\n5 3 3 4 0\n-1 2 9 0\n")
            parsed = atr.parse_groups(path)
            self.assertEqual(parsed.membership[1], frozenset({1, 2}))
            self.assertEqual(parsed.excluded_ids, frozenset({3, 4, 5, 9}))
            self.assertEqual(parsed.audit["partial_or_nonpositive_group_rows"], 1)
            self.assertEqual(parsed.audit["larger_group_member_ids"], 3)

    def test_partial_group_quarantines_known_positive_members(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.dat"
            path.write_text(
                "10592300 3 10592301 -1 2 10592301 -1\n"
                "10592301 3 10592300 -1 2 10592300 -1\n"
                "-1 3 10592300 10592301 2 10592300 10592301\n"
            )
            parsed = atr.parse_groups(path)
            self.assertEqual(parsed.excluded_ids, frozenset({10592300, 10592301}))
            self.assertNotIn(10592300, parsed.membership)
            self.assertEqual(parsed.audit["partial_or_nonpositive_group_rows"], 3)

    def test_multiple_id_row_quarantines_all_recoverable_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.dat"
            path.write_text(
                "16474400 0 2 16503601 3 16474300 16514000 2 16474300 16514000\n"
            )
            parsed = atr.parse_groups(path)
            self.assertEqual(
                parsed.excluded_ids,
                frozenset({16474400, 16503601, 16474300, 16514000}),
            )
            self.assertEqual(parsed.audit["multiple_id_rows"], 1)

    def test_mobility_aid_type_prefix_still_quarantines_group_partners(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.dat"
            path.write_text("-100 -2 3 7 8 0\n-101 -3 2 9 0\n")
            parsed = atr.parse_groups(path)
            self.assertEqual(parsed.excluded_ids, frozenset({7, 8, 9}))
            self.assertEqual(parsed.audit["nonperson_mobility_aid_rows"], 2)
            self.assertEqual(parsed.audit["partial_or_nonpositive_group_rows"], 2)

    def test_one_sided_group_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.dat"
            path.write_text("1 2 2 0\n")
            parsed = atr.parse_groups(path)
            self.assertEqual(parsed.excluded_ids, frozenset({1, 2}))
            self.assertEqual(parsed.membership, {})

    def test_conflict_quarantine_closes_over_every_affected_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.dat"
            path.write_text(
                "1 2 2 0\n2 2 1 0\n"
                "1 2 3 0\n3 2 1 0\n"
                "4 2 5 0\n5 2 4 0\n"
            )
            parsed = atr.parse_groups(path)
            self.assertEqual(parsed.excluded_ids, frozenset({1, 2, 3}))
            self.assertNotIn(2, parsed.membership)
            self.assertNotIn(3, parsed.membership)
            self.assertEqual(parsed.membership[4], frozenset({4, 5}))
            self.assertEqual(parsed.audit["conflicting_membership_ids"], 1)
            self.assertEqual(parsed.audit["conflicting_group_member_ids"], 3)

    def test_truncated_group_quarantines_recoverable_partner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groups.dat"
            path.write_text("1 3 2\n")
            parsed = atr.parse_groups(path)
            self.assertEqual(parsed.excluded_ids, frozenset({1, 2}))
            self.assertEqual(parsed.audit["malformed_rows"], 1)

    def test_exact_frontier_covers_representable_truth(self):
        observations = {
            1: atr.Observation(1, 0.0, 0.0, 0.0, 1.0, 0.0),
            2: atr.Observation(2, 0.0, 0.7, 0.0, 1.0, 0.0),
            3: atr.Observation(3, 0.0, 1.5, 0.0, 1.0, 0.0),
            4: atr.Observation(4, 0.0, 3.0, 0.0, 1.0, 0.0),
        }
        membership = {1: frozenset({1, 2}), 2: frozenset({1, 2})}
        cells = atr.evaluate_snapshot(observations, membership, set(), [2.0], 3.14, [1.0], 4)
        self.assertEqual(len(cells), 1)
        self.assertTrue(cells[0]["true_world_representable"])
        self.assertTrue(cells[0]["truth_covered"])
        self.assertEqual(cells[0]["lower_status"], "NUMERICAL_MILP_OPTIMAL_REPLAYED")
        self.assertTrue(cells[0]["lower_replay_pass"])
        self.assertTrue(cells[0]["upper_replay_pass"])
        self.assertEqual(cells[0]["independent_tiny_check"], "PASS")

    def test_missing_true_edge_is_reported_not_repaired(self):
        observations = {
            1: atr.Observation(1, 0.0, 0.0, 0.0, 1.0, 0.0),
            2: atr.Observation(2, 0.0, 3.0, 0.0, 1.0, 0.0),
            3: atr.Observation(3, 0.0, 0.5, 0.0, 1.0, 0.0),
            4: atr.Observation(4, 0.0, 0.8, 0.0, 1.0, 0.0),
        }
        membership = {1: frozenset({1, 2}), 2: frozenset({1, 2})}
        cell = atr.evaluate_snapshot(observations, membership, set(), [1.0], 3.14, [1.0], 4)[0]
        self.assertFalse(cell["true_world_representable"])
        self.assertFalse(cell["truth_covered"])

    def test_independent_oracle_matches_known_cardinality_two_optima(self):
        edges = [
            (0, 1, 1.0),
            (0, 2, 2.0),
            (1, 3, 3.0),
            (2, 3, 4.0),
        ]
        lower, lower_selected = atr.enumerate_matching_endpoint(4, edges, 2, False)
        upper, upper_selected = atr.enumerate_matching_endpoint(4, edges, 2, True)
        self.assertAlmostEqual(lower, 2.5)
        self.assertAlmostEqual(upper, 2.5)
        self.assertEqual(len(lower_selected), 2)
        self.assertEqual(len(upper_selected), 2)

    def test_witness_replay_rejects_degree_and_cardinality_violations(self):
        edges = [(0, 1, 1.0), (0, 2, 2.0), (2, 3, 3.0)]
        degree_failure = atr.replay_matching_witness(4, edges, 2, [0, 1], 1.5)
        cardinality_failure = atr.replay_matching_witness(4, edges, 2, [0], 0.5)
        self.assertFalse(degree_failure["pass"])
        self.assertFalse(cardinality_failure["pass"])

    def test_solver_infeasibility_is_consistent_with_independent_oracle(self):
        edges = [(0, 1, 1.0), (0, 2, 2.0)]
        result = atr.solve_matching_endpoint(4, edges, 2, False)
        exact, selected = atr.enumerate_matching_endpoint(4, edges, 2, False)
        self.assertEqual(result.status, "INFEASIBLE")
        self.assertIsNone(exact)
        self.assertEqual(selected, ())

    def test_timeout_with_incumbent_is_not_promoted_to_optimal(self):
        fake = SimpleNamespace(
            status=1,
            success=False,
            x=[1.0],
            message="time limit reached",
            mip_gap=0.25,
            mip_dual_bound=0.5,
            mip_node_count=12,
        )
        with patch.object(atr, "milp", return_value=fake):
            result = atr.solve_matching_endpoint(2, [(0, 1, 1.0)], 1, False)
        self.assertEqual(result.status, "UNRESOLVED")
        self.assertIsNone(result.value)
        self.assertFalse(result.replay_pass)

    def test_nonzero_gap_is_not_promoted_to_optimal(self):
        fake = SimpleNamespace(
            status=0,
            success=True,
            x=[1.0],
            message="nominal optimum",
            mip_gap=1e-4,
            mip_dual_bound=0.9999,
            mip_node_count=1,
            fun=1.0,
        )
        with patch.object(atr, "milp", return_value=fake):
            result = atr.solve_matching_endpoint(2, [(0, 1, 1.0)], 1, False)
        self.assertEqual(result.status, "UNRESOLVED")
        self.assertTrue(result.replay_pass)
        self.assertIsNone(result.value)
        self.assertEqual(result.incumbent_value, 1.0)

    def test_fractional_raw_solution_cannot_pass_rounded_witness_replay(self):
        fake = SimpleNamespace(
            status=0,
            success=True,
            x=[0.51],
            fun=0.51,
            message="fractional numerical solution",
            mip_gap=0.0,
            mip_dual_bound=0.51,
            mip_node_count=1,
        )
        with patch.object(atr, "milp", return_value=fake):
            result = atr.solve_matching_endpoint(2, [(0, 1, 1.0)], 1, False)
        self.assertEqual(result.status, "UNRESOLVED")
        self.assertTrue(result.replay_pass)
        self.assertGreater(result.raw_integrality_residual, 0.4)
        self.assertIsNone(result.value)

    def test_solver_objective_must_match_replayed_witness(self):
        fake = SimpleNamespace(
            status=0,
            success=True,
            x=[1.0],
            fun=0.5,
            message="inconsistent objective",
            mip_gap=0.0,
            mip_dual_bound=0.5,
            mip_node_count=1,
        )
        with patch.object(atr, "milp", return_value=fake):
            result = atr.solve_matching_endpoint(2, [(0, 1, 1.0)], 1, False)
        self.assertEqual(result.status, "UNRESOLVED")
        self.assertAlmostEqual(result.solver_objective_residual, 0.5)
        self.assertIsNone(result.value)

    def test_seeded_random_milp_agrees_with_independent_oracle(self):
        rng = random.Random(20260906)
        for _ in range(25):
            vertex_count = rng.randint(2, 9)
            q = rng.randint(0, vertex_count // 2)
            edge_probability = rng.uniform(0.1, 0.9)
            edges = [
                (left, right, rng.uniform(-5.0, 5.0))
                for left in range(vertex_count)
                for right in range(left + 1, vertex_count)
                if rng.random() < edge_probability
            ]
            for maximize in (False, True):
                expected, _ = atr.enumerate_matching_endpoint(
                    vertex_count, edges, q, maximize
                )
                actual = atr.solve_matching_endpoint(
                    vertex_count, edges, q, maximize, time_limit_seconds=5.0
                )
                if expected is None:
                    self.assertEqual(actual.status, "INFEASIBLE")
                else:
                    self.assertEqual(
                        actual.status, "NUMERICAL_MILP_OPTIMAL_REPLAYED"
                    )
                    self.assertTrue(math.isclose(actual.value, expected, abs_tol=1e-8))

    def test_invalid_matching_inputs_fail_before_solver(self):
        with self.assertRaisesRegex(ValueError, "cardinality"):
            atr.solve_matching_endpoint(3, [], 2, False)
        with self.assertRaisesRegex(ValueError, "finite weights"):
            atr.solve_matching_endpoint(2, [(0, 1, math.nan)], 1, False)

    def test_summary_rejects_hold_and_cross_protocol_reports(self):
        base = {
            "status": "PASS",
            "computational_status": "PASS",
            "semantic_status": "PASS",
            "witness_replay_status": "PASS",
            "independent_tiny_oracle_status": "PASS",
            "dataset_day": "DIAMOR-1",
            "protocol_sha256": "protocol-a",
            "benchmark_sha256": "benchmark-a",
            "cell_count": 0,
            "cells": [],
            "exact_cell_count": 0,
            "replayed_exact_cell_count": 0,
            "independent_tiny_checked_cell_count": 0,
            "independent_tiny_passed_cell_count": 0,
        }
        second = dict(base, dataset_day="DIAMOR-2")
        atr_summary.validate_current_reports([base, second])
        with self.assertRaisesRegex(ValueError, "not fully PASS"):
            atr_summary.validate_current_reports([dict(base, status="HOLD"), second])
        with self.assertRaisesRegex(ValueError, "different protocols"):
            atr_summary.validate_current_reports(
                [base, dict(second, protocol_sha256="protocol-b")]
            )


if __name__ == "__main__":
    unittest.main()
