import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS = ROOT / "benchmarks"
sys.path.insert(0, str(BENCHMARKS))
PATH = BENCHMARKS / "atr_diamor_density_cap.py"
SPEC = importlib.util.spec_from_file_location("atr_density_cap", PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class AtrDensityCapTests(unittest.TestCase):
    def test_frozen_evidence_matches_code_protocol_and_baseline(self):
        result_dir = BENCHMARKS / "results" / "atr_diamor_density_cap"
        summary = json.loads((result_dir / "SUMMARY.json").read_text())
        protocol = BENCHMARKS / "ATR_DIAMOR_DENSITY_CAP_PROTOCOL.json"
        baseline = BENCHMARKS / "results" / "atr_diamor_support_calibration" / "SUMMARY.json"

        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["benchmark_sha256"], hashlib.sha256(PATH.read_bytes()).hexdigest())
        self.assertEqual(summary["density_protocol_sha256"], hashlib.sha256(protocol.read_bytes()).hexdigest())
        self.assertEqual(summary["support_summary_sha256"], hashlib.sha256(baseline.read_bytes()).hexdigest())
        self.assertEqual(summary["selected_cap"]["degree_cap"], 2)
        self.assertEqual(summary["selected_cap"]["covered_snapshots"], 85)
        self.assertEqual(summary["followup_selected_cap"]["covered_snapshots"], 81)
        self.assertEqual(summary["comparison_to_fixed"]["candidate_edges_saved"], 80)
        self.assertEqual(summary["comparison_to_fixed"]["coverage_change_snapshots"], 0)
        self.assertEqual(summary["comparison_to_fixed"]["certified_decision_change"], 0)
        self.assertEqual(summary["followup_frontier"]["false_certificates"], 0)

    def test_union_cap_is_deterministic_and_never_adds_outside_edges(self):
        snapshot = {
            "observations": [object()] * 4,
            "pairs": [
                (0, 1, 0.5, 10.0), (0, 2, 0.8, 10.0),
                (0, 3, 0.4, 150.0), (1, 2, 3.5, 10.0),
            ],
        }
        rule = {"radius_m": 3.0, "maximum_motion_angle_degrees": 120.0}
        self.assertEqual(module.capped_edges(snapshot, rule, 1), [(0, 1, 0.5), (0, 2, 0.8)])

    def test_nonpositive_cap_fails_closed(self):
        with self.assertRaises(ValueError):
            module.capped_edges({"observations": [], "pairs": []}, {}, 0)

    def test_selection_preserves_baseline_coverage_before_sparsifying(self):
        rows = [
            {"degree_cap": 1, "covered_snapshots": 84, "mean_candidate_edges": 3.0},
            {"degree_cap": 2, "covered_snapshots": 85, "mean_candidate_edges": 4.0},
            {"degree_cap": 3, "covered_snapshots": 85, "mean_candidate_edges": 5.0},
        ]
        self.assertEqual(module.select_cap(rows, 85)["degree_cap"], 2)


if __name__ == "__main__":
    unittest.main()
