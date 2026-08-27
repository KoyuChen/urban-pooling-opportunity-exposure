import sys
import unittest
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd


BOUNDS_DIR = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = BOUNDS_DIR.parent / "benchmarks"
for path in (BOUNDS_DIR, BENCHMARK_DIR):
    sys.path.insert(0, str(path))

from conformal_matching import (  # noqa: E402
    FixedScoreRange,
    combined_miscoverage_bound,
    exact_additive_score,
    exact_score_floor_from_radius,
    normalized_matching_regret,
    score_floor_from_radius,
    split_conformal_radius,
)
from path_frontier_dp import (  # noqa: E402
    EdgeSpec,
    ExactPathProblem,
    NodeSpec,
    solve_path_frontier_endpoints,
)
from conformal_set_benchmark import (  # noqa: E402
    enumerate_matching_edge_rows,
    evaluate_market,
    score_geometry,
    validate_complete_graph_edge_order,
)


class ConformalMatchingTests(unittest.TestCase):
    def test_benchmark_rejects_noncanonical_complete_edge_order(self):
        nodes = pd.DataFrame({"node_id": ["a", "b", "c", "d"]})
        edges = pd.DataFrame(
            {
                "u": ["a", "a", "a", "b", "b", "c"],
                "v": ["b", "c", "d", "c", "d", "d"],
            }
        )
        validate_complete_graph_edge_order(nodes, edges)
        shuffled = edges.iloc[[1, 0, 2, 3, 4, 5]].reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "edge rows"):
            validate_complete_graph_edge_order(nodes, shuffled)

    def test_benchmark_retains_decimal_maximum_at_float_rounding_boundary(self):
        nodes = pd.DataFrame(
            {
                "node_id": ["a", "b", "c", "d"],
                "ses_bin": [0, 0, 1, 1],
            }
        )
        # Complete-graph row order is ab, ac, ad, bc, bd, cd.  The hidden
        # matching ab+cd has declared score 0.30000000000000002, which rounds
        # upward to float 0.30000000000000004.  Casting the exact maximum before
        # constructing a tau=0 floor used to exclude the maximum itself.
        edges = pd.DataFrame(
            {
                "edge_id": ["ab", "ac", "ad", "bc", "bd", "cd"],
                "u": ["a", "a", "a", "b", "b", "c"],
                "v": ["b", "c", "d", "c", "d", "d"],
                "same_ses": [1, 0, 0, 0, 0, 1],
                "score_boundary": [0.3, 0.0, 0.0, 0.0, 0.0, 2e-17],
            }
        )
        matching_rows = enumerate_matching_edge_rows(4)
        geometry = score_geometry(
            nodes,
            edges,
            ("ab", "cd"),
            "score_boundary",
            matching_rows,
        )
        exact_maximum = Fraction(15000000000000001, 50000000000000000)
        self.assertEqual(geometry["maximum_score"], exact_maximum)
        self.assertGreater(Fraction(str(float(exact_maximum))), exact_maximum)
        self.assertEqual(geometry["true_regret"], 0.0)

        result = evaluate_market(
            nodes,
            edges,
            ("ab", "cd"),
            scorer_name="boundary",
            tau=0.0,
            arbitrary_tau=0.0,
            matching_edge_rows=matching_rows,
        )
        self.assertTrue(result["calibrated_matching_retained"])
        self.assertTrue(result["calibrated_covers"])
        self.assertEqual((result["calibrated_lower"], result["calibrated_upper"]), (1.0, 1.0))

    def test_recomputing_score_range_breaks_gamma_nestedness(self):
        # Gamma=0 has one world.  Gamma=1 preserves it and adds one omitted-edge
        # world, so the structural feasible families are nested.
        gamma_zero = {"old": 1.0}
        gamma_one = {"old": 1.0, "new": 3.0}
        tau = 0.5

        naive_zero_floor = FixedScoreRange(1.0, 1.0).float_floor(tau)
        naive_one_floor = FixedScoreRange(1.0, 3.0).float_floor(tau)
        naive_zero = {
            world for world, score in gamma_zero.items()
            if score >= naive_zero_floor
        }
        naive_one = {
            world for world, score in gamma_one.items()
            if score >= naive_one_floor
        }
        self.assertEqual(naive_zero, {"old"})
        self.assertEqual(naive_one, {"new"})
        self.assertFalse(naive_zero <= naive_one)

        # Freezing the ambient Gamma=1 range gives one common floor.  Intersecting
        # nested feasible families with that fixed halfspace is nested.
        ambient_reference = FixedScoreRange(1.0, 3.0)
        fixed_floor = ambient_reference.float_floor(tau)
        fixed_zero = {
            world for world, score in gamma_zero.items() if score >= fixed_floor
        }
        fixed_one = {
            world for world, score in gamma_one.items() if score >= fixed_floor
        }
        self.assertTrue(fixed_zero <= fixed_one)

    def test_float_scorer_and_exact_dp_share_decimal_rationalization(self):
        # The exact DP declares float scores by their decimal spelling.  The
        # conformal layer must therefore use 1/10, 1/5, and 2/5 here, not their
        # binary64 dyadic encodings.
        regret = normalized_matching_regret(0.2, 0.1, 0.4)
        self.assertGreaterEqual(Fraction(str(regret)), Fraction(2, 3))

        exact_floor = exact_score_floor_from_radius(0.1, 0.4, regret)
        declared_matching_score = Fraction(str(0.2))
        self.assertLessEqual(exact_floor, declared_matching_score)

        # The compatibility float is also outward-safe after the exact DP
        # reparses its decimal spelling.
        float_floor = score_floor_from_radius(0.1, 0.4, regret)
        self.assertLessEqual(Fraction(str(float_floor)), exact_floor)
        self.assertLessEqual(Fraction(str(float_floor)), declared_matching_score)

    def test_additive_scores_are_rationalized_before_not_after_summing(self):
        rounded_float_total = sum([0.1, 0.1, 0.1])
        self.assertNotEqual(Fraction(str(rounded_float_total)), Fraction(3, 10))
        self.assertEqual(exact_additive_score([0.1, 0.1, 0.1]), Fraction(3, 10))

    def test_exact_conformal_floor_is_consumed_by_path_dp_without_requantization(self):
        nodes = tuple(
            NodeSpec(node_id, "core", ("L",))
            for node_id in ("a", "b", "c", "d")
        )
        problem = ExactPathProblem(
            nodes,
            (
                EdgeSpec("ab", "a", "b", score=0.1, query=0),
                EdgeSpec("cd", "c", "d", score=0.1, query=0),
                EdgeSpec("ac", "a", "c", score=0.2, query=1),
                EdgeSpec("bd", "b", "d", score=0.2, query=0),
            ),
        )
        # Per-core-incidence scoring makes the two matching totals 2/5 and 4/5.
        floor = exact_score_floor_from_radius(
            Fraction(2, 5), Fraction(4, 5), Fraction(1, 2)
        )
        self.assertEqual(floor, Fraction(3, 5))
        result = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "b", "c", "d"),
            score_floor=floor,
        )
        self.assertEqual(result.score_floor, floor)
        self.assertEqual((result.lower, result.upper), (Fraction(1), Fraction(1)))
        self.assertEqual(
            set(result.lower_solution.witness.selected_edge_ids),
            {"ac", "bd"},
        )

    def test_fraction_floor_avoids_float_quantization(self):
        lower = Fraction(1, 10)
        upper = Fraction(2, 5)
        tau = Fraction(2, 3)
        floor = exact_score_floor_from_radius(lower, upper, tau)
        self.assertEqual(floor, Fraction(1, 5))

    def test_regret_and_floor_are_positive_affine_invariant(self):
        regret = normalized_matching_regret(8.0, 2.0, 10.0)
        transformed = normalized_matching_regret(7 * 8 + 11, 7 * 2 + 11, 7 * 10 + 11)
        self.assertAlmostEqual(regret, 0.25)
        self.assertAlmostEqual(transformed, regret)

        floor = score_floor_from_radius(2.0, 10.0, regret)
        transformed_floor = score_floor_from_radius(7 * 2 + 11, 7 * 10 + 11, regret)
        self.assertAlmostEqual(floor, 8.0)
        self.assertAlmostEqual(transformed_floor, 7 * floor + 11)

    def test_positive_affine_invariance_across_tiny_and_huge_scales(self):
        base = (8.0, 2.0, 10.0)
        base_regret = normalized_matching_regret(*base)
        for scale in (1e-250, 5e-11, 1.0, 1e250):
            with self.subTest(scale=scale):
                shift = -3.0 * scale
                score, lower, upper = (
                    scale * value + shift for value in base
                )
                regret = normalized_matching_regret(score, lower, upper)
                self.assertAlmostEqual(regret, base_regret, places=15)
                floor = score_floor_from_radius(lower, upper, regret)
                self.assertLessEqual(floor, score)
                self.assertGreaterEqual(floor, lower)

    def test_nonzero_tiny_span_is_not_collapsed_or_falsely_excluded(self):
        # This is the former failure mode: the old absolute scale floor treated
        # delta < 1e-10 as a constant map, calibrated tau=0, and then returned
        # the strict upper endpoint as the score floor.
        delta = 5e-11
        regrets = [normalized_matching_regret(0.0, 0.0, delta) for _ in range(9)]
        self.assertEqual(regrets, [1.0] * 9)
        radius = split_conformal_radius(regrets, alpha=0.10)
        self.assertEqual(radius.tau, 1.0)
        floor = score_floor_from_radius(0.0, delta, radius.tau)
        self.assertLessEqual(floor, 0.0)

    def test_boundary_matching_is_retained_at_extreme_finite_scales(self):
        for scale in (1e-250, 1.0, 1e250):
            with self.subTest(scale=scale):
                lower = -2.0 * scale
                score = 4.0 * scale
                upper = 6.0 * scale
                regret = normalized_matching_regret(score, lower, upper)
                floor = score_floor_from_radius(lower, upper, regret)
                self.assertLessEqual(floor, score)
                self.assertGreaterEqual(floor, lower)

        regret = normalized_matching_regret(0.0, -1e308, 1e308)
        self.assertEqual(regret, 0.5)
        floor = score_floor_from_radius(-1e308, 1e308, regret)
        self.assertTrue(np.isfinite(floor))
        self.assertLessEqual(floor, 0.0)
        self.assertGreaterEqual(floor, -1e308)

    def test_constant_score_map_retains_every_matching(self):
        self.assertEqual(normalized_matching_regret(4.0, 4.0, 4.0), 0.0)
        self.assertEqual(score_floor_from_radius(4.0, 4.0, 0.0), 4.0)

    def test_exact_exchangeable_rank_coverage(self):
        # Enumerate which one of eleven distinct nonconformity scores is the
        # test market.  The other ten calibrate a 90% set.  Exactly ten of the
        # eleven exchangeable positions are covered, exceeding 90%.
        scores = np.linspace(0.0, 1.0, 11)
        covered = []
        for test_index in range(len(scores)):
            calibration = np.delete(scores, test_index)
            radius = split_conformal_radius(calibration, alpha=0.10)
            covered.append(scores[test_index] <= radius.tau)
        self.assertGreaterEqual(np.mean(covered), 0.90)
        self.assertEqual(sum(covered), 10)

    def test_small_calibration_sample_returns_support_bound(self):
        radius = split_conformal_radius([0.1, 0.2, 0.3], alpha=0.01)
        self.assertEqual(radius.order_rank, 4)
        self.assertEqual(radius.tau, 1.0)

    def test_union_bound(self):
        self.assertAlmostEqual(combined_miscoverage_bound(0.02, [0.05, 0.01]), 0.08)
        self.assertEqual(combined_miscoverage_bound(0.7, 0.6), 1.0)

    def test_invalid_inputs_are_rejected(self):
        for invalid_alpha in (0.0, 1.0, -0.1, float("nan")):
            with self.assertRaises(ValueError):
                split_conformal_radius([0.2], invalid_alpha)
        for values in ([], [-0.1], [1.1], [float("nan")]):
            with self.assertRaises(ValueError):
                split_conformal_radius(values, 0.1)
        with self.assertRaises(ValueError):
            normalized_matching_regret(11.0, 0.0, 10.0)
        with self.assertRaises(ValueError):
            score_floor_from_radius(2.0, 1.0, 0.5)
        with self.assertRaises(ValueError):
            combined_miscoverage_bound([])


if __name__ == "__main__":
    unittest.main()
