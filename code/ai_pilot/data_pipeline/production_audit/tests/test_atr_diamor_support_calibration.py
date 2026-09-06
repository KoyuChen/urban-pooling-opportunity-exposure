import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS = ROOT / "benchmarks"
sys.path.insert(0, str(BENCHMARKS))
PATH = BENCHMARKS / "atr_diamor_support_calibration.py"
SPEC = importlib.util.spec_from_file_location("atr_support_calibration", PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class AtrSupportCalibrationTests(unittest.TestCase):
    def test_frozen_evidence_matches_benchmark_and_protocol(self):
        result_dir = BENCHMARKS / "results" / "atr_diamor_support_calibration"
        summary = json.loads((result_dir / "SUMMARY.json").read_text())
        protocol = BENCHMARKS / "ATR_DIAMOR_SUPPORT_CALIBRATION_PROTOCOL.json"

        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["benchmark_sha256"], hashlib.sha256(PATH.read_bytes()).hexdigest())
        self.assertEqual(
            summary["calibration_protocol_sha256"],
            hashlib.sha256(protocol.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            (summary["selected_rule"]["radius_m"], summary["selected_rule"]["maximum_motion_angle_degrees"]),
            (3.0, 120.0),
        )
        self.assertEqual(summary["selected_rule"]["covered_snapshots"], 85)
        self.assertEqual(summary["selected_rule"]["eligible_snapshots"], 88)
        self.assertEqual(summary["followup_selected_rule"]["covered_snapshots"], 81)
        self.assertEqual(summary["followup_selected_rule"]["eligible_snapshots"], 82)
        frontier = summary["followup_frontier"]
        self.assertEqual(frontier["exact_cells"], 82)
        self.assertEqual(frontier["certified_threshold_decisions"], 29)
        self.assertEqual(frontier["ambiguous_threshold_decisions"], 217)
        self.assertEqual(frontier["false_certificates"], 0)

    def test_selection_minimizes_edges_after_coverage_gate(self):
        rows = [
            {"relational_coverage": 0.94, "mean_candidate_edges": 1.0, "radius_m": 1.0, "maximum_motion_angle_degrees": 90.0},
            {"relational_coverage": 0.96, "mean_candidate_edges": 4.0, "radius_m": 3.0, "maximum_motion_angle_degrees": 120.0},
            {"relational_coverage": 0.99, "mean_candidate_edges": 8.0, "radius_m": 5.0, "maximum_motion_angle_degrees": 180.0},
        ]
        selected = module.select_rule(rows, 0.95)
        self.assertEqual((selected["radius_m"], selected["maximum_motion_angle_degrees"]), (3.0, 120.0))

    def test_selection_fails_when_target_is_unmet(self):
        with self.assertRaises(ValueError):
            module.select_rule([
                {"relational_coverage": 0.9, "mean_candidate_edges": 1.0, "radius_m": 1.0, "maximum_motion_angle_degrees": 90.0}
            ], 0.95)

    def test_grid_reports_snapshot_level_joint_world_coverage(self):
        snapshots = [
            {"truth_edges": {(0, 1), (2, 3)}, "pairs": [(0, 1, 0.5, 10.0), (2, 3, 2.0, 10.0)]},
            {"truth_edges": {(0, 1)}, "pairs": [(0, 1, 0.5, 100.0)]},
        ]
        row = module.grid_metrics(snapshots, [1.0], [90.0])[0]
        self.assertEqual(row["covered_snapshots"], 0)
        self.assertEqual(row["relational_coverage"], 0.0)
        self.assertEqual(row["total_candidate_edges"], 1)


if __name__ == "__main__":
    unittest.main()
