from __future__ import annotations

import sys
import unittest
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parents[3] / "benchmarks"
sys.path.insert(0, str(BENCHMARK_DIR))

import controlled_truth_joint_panel as panel  # noqa: E402


class ControlledTruthJointPanelTests(unittest.TestCase):
    def test_false_certificate_requires_certification(self) -> None:
        report = {
            "design": {"thresholds": [0.25, 0.5, 0.75]},
            "instances": [{"capacity": 2, "seed": 1, "true_value": 0.8}],
            "candidate_truncation_cells": [{
                "capacity": 2,
                "seed": 1,
                "retained_buffer_count": 4,
                "true_member_recall": 0.5,
                "true_world_representable": False,
                "aggregate_value_covered": False,
                "frontier_lower": 0.1,
                "frontier_upper": 0.4,
            }],
        }
        row = panel.enrich(report)[0]
        self.assertEqual(row["threshold_certified_count"], 2)
        self.assertEqual(row["threshold_false_certificate_count"], 2)
        self.assertEqual(row["threshold_unresolved_count"], 1)

    def test_unavailable_frontier_is_never_certified(self) -> None:
        report = {
            "design": {"thresholds": [0.25, 0.5, 0.75]},
            "instances": [{"capacity": 3, "seed": 2, "true_value": 0.5}],
            "candidate_truncation_cells": [{
                "capacity": 3,
                "seed": 2,
                "retained_buffer_count": 4,
                "true_member_recall": 0.5,
                "true_world_representable": False,
                "aggregate_value_covered": False,
                "frontier_lower": None,
                "frontier_upper": None,
            }],
        }
        row = panel.enrich(report)[0]
        self.assertEqual(row["threshold_certified_count"], 0)
        self.assertEqual(row["threshold_false_certificate_count"], 0)
        self.assertIsNone(row["frontier_width"])


if __name__ == "__main__":
    unittest.main()
