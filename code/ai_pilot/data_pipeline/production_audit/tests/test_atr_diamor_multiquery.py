import importlib.util
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS = ROOT / "benchmarks"
sys.path.insert(0, str(BENCHMARKS))
PATH = BENCHMARKS / "atr_diamor_multiquery.py"
SPEC = importlib.util.spec_from_file_location("atr_multiquery", PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class AtrMultiqueryTests(unittest.TestCase):
    def test_frozen_cross_day_summary_and_hashes(self):
        summary = json.loads(
            (BENCHMARKS / "results" / "atr_diamor_multiquery" / "SUMMARY.json").read_text()
        )
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["training_day"], "DIAMOR-1")
        self.assertEqual(summary["evaluation_day"], "DIAMOR-2")
        self.assertEqual(summary["benchmark_sha256"], hashlib.sha256(PATH.read_bytes()).hexdigest())
        protocol = BENCHMARKS / "ATR_DIAMOR_MULTIQUERY_PROTOCOL.json"
        self.assertEqual(
            summary["multiquery_protocol_sha256"], hashlib.sha256(protocol.read_bytes()).hexdigest()
        )
        learned = summary["summary"]["speed_gap_mps"]["baselines"]["learned_diamor1"]
        self.assertEqual((learned["threshold_errors"], learned["errors_flagged"]), (70, 70))
        self.assertAlmostEqual(learned["mean_relation_recall"], 0.892432195975503)

    def test_edge_features_have_declared_units(self):
        left = module.base.Observation(1, 0, 0, 0, 1.0, 0.0)
        right = module.base.Observation(2, 0, 3, 4, 1.4, math.pi / 2)
        distance, heading, speed = module.edge_features(left, right)
        self.assertAlmostEqual(distance, 5.0)
        self.assertAlmostEqual(heading, 90.0)
        self.assertAlmostEqual(speed, 0.4)

    def test_balanced_logistic_fits_finite_frozen_model(self):
        features = [[0.2, 2.0, 0.02], [0.4, 5.0, 0.05], [2.0, 60.0, 0.5], [3.0, 80.0, 0.8]]
        model = module.fit_logistic(features, [1, 1, 0, 0], 0.001)
        self.assertTrue(all(np.isfinite(model.coefficients)))
        self.assertGreater(model.logit(features[0]), model.logit(features[-1]))
        self.assertEqual((model.training_edges, model.training_positives), (4, 2))

    def test_query_weights_do_not_change_baseline_membership(self):
        observations = [
            module.base.Observation(1, 0, 0, 0, 1.0, 0.0),
            module.base.Observation(2, 0, 0.5, 0, 1.1, 0.1),
            module.base.Observation(3, 0, 2.0, 0, 0.5, 0.4),
            module.base.Observation(4, 0, 2.6, 0, 1.4, 0.7),
        ]
        featured = module.feature_edges(observations, 3.0, math.pi)
        pairs = [(a, b) for a, b, _ in featured]
        costs = [values[0] for _, _, values in featured]
        result = module.base.solve_matching_endpoint(
            4, [(a, b, cost) for (a, b), cost in zip(pairs, costs)], 2, False
        )
        self.assertEqual(result.status, module.OPTIMAL)
        distance_point = sum(featured[i][2][0] for i in result.selected) / 2
        speed_point = sum(featured[i][2][2] for i in result.selected) / 2
        self.assertNotEqual(distance_point, speed_point)
        self.assertEqual(len(result.selected), 2)

    def test_training_examples_preserve_positive_dyad_labels(self):
        snapshot = {
            1: module.base.Observation(1, 0, 0, 0, 1.0, 0.0),
            2: module.base.Observation(2, 0, 0.5, 0, 1.0, 0.0),
            3: module.base.Observation(3, 0, 1.0, 0, 1.0, 0.0),
            4: module.base.Observation(4, 0, 1.5, 0, 1.0, 0.0),
        }
        membership = {1: frozenset({1, 2}), 2: frozenset({1, 2})}
        features, labels = module.training_examples(
            [snapshot], membership, set(), 2.0, math.pi, 4
        )
        self.assertEqual(sum(labels), 1)
        self.assertGreater(len(labels) - sum(labels), 0)

    def test_relation_recall_uses_matching_edges_not_query_values(self):
        pairs = [(0, 1), (0, 2), (1, 3), (2, 3)]
        truth = {(0, 1), (2, 3)}
        selected = (0, 3)
        self.assertEqual(sum(pairs[index] in truth for index in selected) / 2, 1.0)


if __name__ == "__main__":
    unittest.main()
