import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


BOUNDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOUNDS_DIR))

from structured_matching_bounds import (  # noqa: E402
    SCIPY_MILP_AVAILABLE,
    add_independent_same_bin_envelopes,
    add_signed_edge_envelopes,
    normalized_regret_floor,
    residualized_treatment_weights,
    solve_linear_endpoints,
)


class StructuredMatchingBoundsTests(unittest.TestCase):
    def setUp(self):
        self.nodes = pd.DataFrame({"node_id": ["a", "b", "c", "d"]})
        self.edges = pd.DataFrame(
            {
                "edge_id": ["ab", "cd", "ac", "bd"],
                "u": ["a", "c", "a", "b"],
                "v": ["b", "d", "c", "d"],
            }
        )

    def test_distinct_objectives_return_attained_endpoints(self):
        edges = self.edges.assign(lower=[1, 1, 0, 0], upper=[1, 1, 0, 0])
        result = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            normalizer=2,
            backend="fallback",
        )
        self.assertTrue(result.certified)
        self.assertEqual(result.status, "OPTIMAL")
        self.assertAlmostEqual(result.lower, 0.0)
        self.assertAlmostEqual(result.upper, 1.0)

    def test_missing_bin_envelopes_exact_cover_all_nodes(self):
        nodes = self.nodes.assign(ses_bin=[0, np.nan, 1, 1])
        edges = add_independent_same_bin_envelopes(
            nodes,
            self.edges,
            all_bins=[0, 1],
        )
        result = solve_linear_endpoints(
            nodes,
            edges,
            lower_objective_col="same_bin_lower",
            upper_objective_col="same_bin_upper",
            normalizer=2,
            backend="fallback",
        )
        self.assertTrue(result.certified)
        self.assertAlmostEqual(result.lower, 0.0)
        self.assertAlmostEqual(result.upper, 1.0)

    def test_signed_fwl_edge_identity(self):
        nuisance = np.column_stack([np.ones(4), [0.0, 1.0, 0.0, 1.0]])
        treatment = np.array([0.0, 0.0, 1.0, 1.0])
        weights = residualized_treatment_weights(nuisance, treatment)
        nodes = self.nodes.assign(fwl_weight=weights)
        edges = self.edges.assign(exposure_lower=[0.2, 0.8, 0.6, 0.1])
        edges["exposure_upper"] = edges["exposure_lower"]
        signed = add_signed_edge_envelopes(
            nodes,
            edges,
            node_weight_col="fwl_weight",
            exposure_lower_col="exposure_lower",
            exposure_upper_col="exposure_upper",
        )
        result = solve_linear_endpoints(
            nodes,
            signed,
            lower_objective_col="linear_lower",
            upper_objective_col="linear_upper",
            backend="fallback",
        )
        direct = []
        for matching in ((0, 1), (2, 3)):
            outcome = np.zeros(4)
            for edge_index in matching:
                row = edges.iloc[edge_index]
                value = row["exposure_lower"]
                outcome[self.nodes.index[self.nodes["node_id"] == row["u"]][0]] = value
                outcome[self.nodes.index[self.nodes["node_id"] == row["v"]][0]] = value
            direct.append(float(weights @ outcome))
        self.assertAlmostEqual(result.lower, min(direct))
        self.assertAlmostEqual(result.upper, max(direct))

    def test_residualization_rejects_collinear_treatment(self):
        nuisance = np.column_stack([np.ones(4), [0.0, 0.0, 1.0, 1.0]])
        treatment = np.array([0.0, 0.0, 1.0, 1.0])
        with self.assertRaises(ValueError):
            residualized_treatment_weights(nuisance, treatment)

    def test_gamma_candidate_miss_expands_range(self):
        edges = self.edges.assign(
            lower=[1, 1, 0, 0],
            upper=[1, 1, 0, 0],
            omitted=[0, 0, 1, 0],
        )
        gamma_zero = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            normalizer=2,
            omitted_col="omitted",
            gamma=0,
            backend="fallback",
        )
        gamma_one = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            normalizer=2,
            omitted_col="omitted",
            gamma=1,
            backend="fallback",
        )
        self.assertEqual((gamma_zero.lower, gamma_zero.upper), (1.0, 1.0))
        self.assertEqual((gamma_one.lower, gamma_one.upper), (0.0, 1.0))

    def test_normalized_regret_floor_is_positive_affine_invariant(self):
        original = normalized_regret_floor(8.0, 10.0, 0.5)
        transformed = normalized_regret_floor(7 * 8 + 22, 7 * 10 + 22, 0.5)
        self.assertAlmostEqual(transformed, 7 * original + 22)

    def test_state_limit_is_unresolved_not_infeasible(self):
        edges = self.edges.assign(lower=[1, 1, 0, 0], upper=[1, 1, 0, 0])
        result = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            backend="fallback",
            fallback_max_states=0,
        )
        self.assertEqual(result.status, "UNRESOLVED")
        self.assertFalse(result.certified)

    def test_proven_infeasible_domain_is_certified(self):
        edges = self.edges.iloc[[0]].assign(lower=[1], upper=[1])
        result = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            backend="fallback",
        )
        self.assertEqual(result.status, "PROVEN_INFEASIBLE")
        self.assertTrue(result.certified)
        self.assertIsNone(result.lower)
        self.assertIsNone(result.upper)

    def test_fallback_resolves_objective_differences_below_one_e_minus_twelve(self):
        edges = self.edges.assign(
            lower=[0.0, 0.0, -2.5e-13, -2.5e-13],
            upper=[0.0, 0.0, -2.5e-13, -2.5e-13],
        )
        result = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            backend="fallback",
        )
        self.assertEqual(result.lower, -5e-13)
        self.assertEqual(result.upper, 0.0)

    def test_score_floor_is_not_relaxed_by_manual_tolerance(self):
        edges = self.edges.assign(
            lower=[0.5, 0.5, 0.0, 0.0],
            upper=[0.5, 0.5, 0.0, 0.0],
            score=[0.5, 0.5, 0.5, 0.4999999995],
        )
        result = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            score_col="score",
            score_floor=1.0,
            backend="fallback",
        )
        self.assertEqual((result.lower, result.upper), (1.0, 1.0))

    def test_invalid_envelopes_and_parameters_are_rejected(self):
        inverted = self.edges.assign(lower=[1, 0, 0, 0], upper=[0, 0, 0, 0])
        with self.assertRaises(ValueError):
            solve_linear_endpoints(
                self.nodes,
                inverted,
                lower_objective_col="lower",
                upper_objective_col="upper",
            )
        valid = self.edges.assign(lower=0.0, upper=1.0, score=1.0)
        with self.assertRaises(ValueError):
            solve_linear_endpoints(
                self.nodes,
                valid,
                lower_objective_col="lower",
                upper_objective_col="upper",
                gamma=0.5,
            )
        with self.assertRaises(ValueError):
            solve_linear_endpoints(
                self.nodes,
                valid,
                lower_objective_col="lower",
                upper_objective_col="upper",
                score_col="score",
                score_floor=float("nan"),
            )
        with self.assertRaises(ValueError):
            solve_linear_endpoints(
                self.nodes.iloc[0:0],
                valid.iloc[0:0],
                lower_objective_col="lower",
                upper_objective_col="upper",
            )

    def test_fwl_weights_are_scale_invariant(self):
        nuisance = np.column_stack([np.ones(6), [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0]])
        treatment = np.array([0.0, 1.0, 0.0, 1.0, 1.0, 0.0])
        original = residualized_treatment_weights(nuisance, treatment)
        scaled_x = nuisance.copy()
        scaled_x[:, 1] *= 1e6
        rescaled_design = residualized_treatment_weights(scaled_x, treatment)
        self.assertTrue(np.allclose(original, rescaled_design, atol=1e-12, rtol=1e-12))
        treatment_scale = 5e-6
        rescaled_treatment = residualized_treatment_weights(
            nuisance,
            treatment_scale * treatment,
        )
        self.assertTrue(
            np.allclose(
                rescaled_treatment,
                original / treatment_scale,
                atol=1e-6,
                rtol=1e-10,
            )
        )

    def test_explicit_missing_supports_control_edge_envelopes(self):
        nodes = pd.DataFrame(
            {
                "node_id": ["a", "b"],
                "ses_bin": ["A", np.nan],
                "support": [None, ["B", "C"]],
            }
        )
        edge = pd.DataFrame({"edge_id": ["ab"], "u": ["a"], "v": ["b"]})
        bounded = add_independent_same_bin_envelopes(
            nodes,
            edge,
            support_col="support",
        )
        self.assertEqual(
            (bounded.loc[0, "same_bin_lower"], bounded.loc[0, "same_bin_upper"]),
            (0.0, 0.0),
        )

    def test_missing_bins_require_declared_support(self):
        nodes = self.nodes.assign(ses_bin=[0, np.nan, 1, 1])
        with self.assertRaisesRegex(ValueError, "explicit all_bins"):
            add_independent_same_bin_envelopes(nodes, self.edges)

    def test_identifiers_and_undirected_pairs_are_validated(self):
        base_edges = self.edges.assign(lower=0.0, upper=1.0)
        for invalid_id in (np.nan, "  "):
            bad_nodes = self.nodes.copy()
            bad_nodes.loc[0, "node_id"] = invalid_id
            with self.assertRaises(ValueError):
                solve_linear_endpoints(
                    bad_nodes,
                    base_edges,
                    lower_objective_col="lower",
                    upper_objective_col="upper",
                    backend="fallback",
                )
        duplicate_pair = pd.DataFrame(
            {
                "edge_id": ["ab1", "ab2"],
                "u": ["a", "b"],
                "v": ["b", "a"],
                "lower": [0.0, 1.0],
                "upper": [0.0, 1.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "duplicate undirected"):
            solve_linear_endpoints(
                self.nodes.iloc[:2],
                duplicate_pair,
                lower_objective_col="lower",
                upper_objective_col="upper",
                backend="fallback",
            )

    def test_envelope_helpers_reject_duplicate_node_ids_cleanly(self):
        duplicate_nodes = pd.DataFrame(
            {"node_id": ["a", "a"], "ses_bin": [0, 1], "weight": [1.0, 2.0]}
        )
        edge = pd.DataFrame(
            {
                "edge_id": ["aa"],
                "u": ["a"],
                "v": ["a"],
                "exposure_lower": [0.0],
                "exposure_upper": [1.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "must be unique"):
            add_independent_same_bin_envelopes(duplicate_nodes, edge)
        with self.assertRaisesRegex(ValueError, "must be unique"):
            add_signed_edge_envelopes(
                duplicate_nodes,
                edge,
                node_weight_col="weight",
                exposure_lower_col="exposure_lower",
                exposure_upper_col="exposure_upper",
            )

    def test_fwl_rejects_invalid_tolerance_and_ambiguous_rank(self):
        nuisance = np.ones((4, 1))
        treatment = np.array([0.0, 0.0, 1.0, 1.0])
        for tolerance in (float("nan"), 0.0, -1.0, 1.0):
            with self.assertRaises(ValueError):
                residualized_treatment_weights(
                    nuisance,
                    treatment,
                    tolerance=tolerance,
                )

        x = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]])
        d = np.array([0.0, 1.0, 0.0])
        transform = np.array([[1.0, 1.0], [0.0, 1e-12]])
        with self.assertRaisesRegex(ValueError, "ambiguous rank"):
            residualized_treatment_weights(x @ transform, d)

    def test_fwl_survives_extreme_finite_unit_changes(self):
        nuisance = np.ones((2, 1))
        treatment = np.array([0.0, 1.0])
        expected = np.array([-1.0, 1.0])
        self.assertTrue(
            np.allclose(
                residualized_treatment_weights(1e200 * nuisance, treatment),
                expected,
            )
        )
        for scale in (1e200, 1e-200):
            weights = residualized_treatment_weights(nuisance, scale * treatment)
            self.assertTrue(
                np.allclose(weights * scale, expected, atol=1e-14, rtol=1e-14)
            )

    @unittest.skipUnless(SCIPY_MILP_AVAILABLE, "SciPy MILP unavailable")
    def test_scipy_tiny_objective_gap_is_scaled_but_not_exactly_certified(self):
        edges = self.edges.assign(
            lower=[0.0, 0.0, -5e-10, -5e-10],
            upper=[0.0, 0.0, -5e-10, -5e-10],
        )
        result = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            backend="scipy",
            time_limit=None,
        )
        self.assertEqual(result.status, "NUMERICALLY_OPTIMAL")
        self.assertFalse(result.certified)
        self.assertAlmostEqual(result.lower, -1e-9, places=15)
        self.assertAlmostEqual(result.upper, 0.0, places=15)

    @unittest.skipUnless(SCIPY_MILP_AVAILABLE, "SciPy MILP unavailable")
    def test_scipy_normalization_handles_opposite_extreme_coefficients(self):
        edges = self.edges.assign(
            lower=[-1e308, 1e308, 0.0, 0.0],
            upper=[-1e308, 1e308, 0.0, 0.0],
        )
        result = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            backend="scipy",
            time_limit=None,
        )
        self.assertEqual(result.status, "NUMERICALLY_OPTIMAL")
        self.assertEqual((result.lower, result.upper), (0.0, 0.0))

    def test_unrepresentable_selected_aggregate_is_rejected(self):
        edges = self.edges.assign(lower=1e308, upper=1e308)
        for backend in ("fallback", "scipy"):
            if backend == "scipy" and not SCIPY_MILP_AVAILABLE:
                continue
            with self.assertRaisesRegex(ValueError, "not representable"):
                solve_linear_endpoints(
                    self.nodes,
                    edges,
                    lower_objective_col="lower",
                    upper_objective_col="upper",
                    backend=backend,
                    time_limit=None,
                )

    @unittest.skipUnless(SCIPY_MILP_AVAILABLE, "SciPy MILP unavailable")
    def test_large_score_floor_equality_is_not_falsely_infeasible(self):
        low_score = -4.2070601430730603e30
        high_score = 1.791461442436253e31
        floor = 3.582922884872506e31
        edges = self.edges.assign(
            lower=0.0,
            upper=0.0,
            score=[high_score, high_score, low_score, low_score],
        )
        exact = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            score_col="score",
            score_floor=floor,
            backend="fallback",
        )
        numeric = solve_linear_endpoints(
            self.nodes,
            edges,
            lower_objective_col="lower",
            upper_objective_col="upper",
            score_col="score",
            score_floor=floor,
            backend="scipy",
            time_limit=None,
        )
        self.assertEqual(exact.status, "OPTIMAL")
        self.assertEqual(numeric.status, "NUMERICALLY_OPTIMAL")
        self.assertEqual((numeric.lower, numeric.upper), (0.0, 0.0))
        self.assertFalse(numeric.certified)


if __name__ == "__main__":
    unittest.main()
