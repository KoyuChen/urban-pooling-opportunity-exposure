import hashlib
import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS = ROOT / "benchmarks"
sys.path.insert(0, str(BENCHMARKS))
PATH = BENCHMARKS / "atr_diamor_alternating_structure.py"
SPEC = importlib.util.spec_from_file_location("atr_alternating", PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class AlternatingStructureTests(unittest.TestCase):
    def test_frozen_evidence_matches_inputs_and_code(self):
        summary_path = BENCHMARKS / "results" / "atr_diamor_alternating_structure" / "SUMMARY.json"
        summary = json.loads(summary_path.read_text())
        protocol = BENCHMARKS / "ATR_DIAMOR_ALTERNATING_STRUCTURE_PROTOCOL.json"
        support_summary = BENCHMARKS / "results" / "atr_diamor_support_calibration" / "SUMMARY.json"
        density_summary = BENCHMARKS / "results" / "atr_diamor_density_cap" / "SUMMARY.json"
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["benchmark_sha256"], hashlib.sha256(PATH.read_bytes()).hexdigest())
        self.assertEqual(summary["diagnostic_protocol_sha256"], hashlib.sha256(protocol.read_bytes()).hexdigest())
        self.assertEqual(summary["support_summary_sha256"], hashlib.sha256(support_summary.read_bytes()).hexdigest())
        self.assertEqual(summary["density_summary_sha256"], hashlib.sha256(density_summary.read_bytes()).hexdigest())
        self.assertEqual(summary["fixed"]["multi_component_cells"], 73)
        self.assertEqual(summary["fixed"]["maximum_component_edges"], 4)
        self.assertEqual(summary["comparison"]["identical_lower_endpoint_cells"], 82)
        self.assertEqual(summary["comparison"]["contracted_upper_endpoint_cells"], 21)
        self.assertEqual(summary["comparison"]["identical_ambiguity_count_cells"], 82)

    def test_four_cycle_is_recognized(self):
        components = module.symmetric_difference_components(
            {(0, 1), (2, 3)}, {(0, 2), (1, 3)}
        )
        self.assertEqual(components, [{
            "type": "cycle", "vertex_count": 4, "edge_count": 4,
            "lower_edge_count": 2, "upper_edge_count": 2,
        }])

    def test_alternating_path_is_recognized(self):
        components = module.symmetric_difference_components(
            {(0, 1), (2, 3)}, {(1, 2), (3, 4)}
        )
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["type"], "path")
        self.assertEqual(components[0]["edge_count"], 4)

    def test_identical_matchings_have_no_components(self):
        self.assertEqual(module.symmetric_difference_components({(0, 1)}, {(0, 1)}), [])

    def test_seeded_equal_cardinality_matchings_obey_decomposition_invariants(self):
        rng = random.Random(20260906)
        for vertex_count in range(4, 14, 2):
            for _ in range(50):
                lower_order = list(range(vertex_count))
                upper_order = list(range(vertex_count))
                rng.shuffle(lower_order)
                rng.shuffle(upper_order)
                q = rng.randint(1, vertex_count // 2)
                lower = {
                    tuple(sorted((lower_order[2 * index], lower_order[2 * index + 1])))
                    for index in range(q)
                }
                upper = {
                    tuple(sorted((upper_order[2 * index], upper_order[2 * index + 1])))
                    for index in range(q)
                }
                components = module.symmetric_difference_components(lower, upper)
                self.assertEqual(sum(item["lower_edge_count"] for item in components), len(lower - upper))
                self.assertEqual(sum(item["upper_edge_count"] for item in components), len(upper - lower))
                self.assertEqual(
                    sum(item["upper_edge_count"] - item["lower_edge_count"] for item in components),
                    0,
                )
                for item in components:
                    self.assertIn(item["type"], {"path", "cycle"})
                    self.assertLessEqual(abs(item["upper_edge_count"] - item["lower_edge_count"]), 1)
                    if item["type"] == "cycle":
                        self.assertEqual(item["upper_edge_count"], item["lower_edge_count"])


if __name__ == "__main__":
    unittest.main()
