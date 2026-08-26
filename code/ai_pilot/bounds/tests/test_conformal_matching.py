import sys
import unittest
from pathlib import Path

import numpy as np


BOUNDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOUNDS_DIR))

from conformal_matching import (  # noqa: E402
    combined_miscoverage_bound,
    normalized_matching_regret,
    score_floor_from_radius,
    split_conformal_radius,
)


class ConformalMatchingTests(unittest.TestCase):
    def test_regret_and_floor_are_positive_affine_invariant(self):
        regret = normalized_matching_regret(8.0, 2.0, 10.0)
        transformed = normalized_matching_regret(7 * 8 + 11, 7 * 2 + 11, 7 * 10 + 11)
        self.assertAlmostEqual(regret, 0.25)
        self.assertAlmostEqual(transformed, regret)

        floor = score_floor_from_radius(2.0, 10.0, regret)
        transformed_floor = score_floor_from_radius(7 * 2 + 11, 7 * 10 + 11, regret)
        self.assertAlmostEqual(floor, 8.0)
        self.assertAlmostEqual(transformed_floor, 7 * floor + 11)

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
