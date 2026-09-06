import importlib.util
import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS = ROOT / "benchmarks"
sys.path.insert(0, str(BENCHMARKS))
MODULE_PATH = BENCHMARKS / "atr_diamor_unknown_q.py"
SPEC = importlib.util.spec_from_file_location("atr_unknown_q", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

SUMMARY_PATH = BENCHMARKS / "atr_diamor_unknown_q_summary.py"
SUMMARY_SPEC = importlib.util.spec_from_file_location("atr_unknown_q_summary", SUMMARY_PATH)
summary_module = importlib.util.module_from_spec(SUMMARY_SPEC)
assert SUMMARY_SPEC.loader is not None
sys.modules[SUMMARY_SPEC.name] = summary_module
SUMMARY_SPEC.loader.exec_module(summary_module)


class AtrUnknownQTests(unittest.TestCase):
    def test_frozen_unknown_q_evidence_and_hashes(self):
        result_dir = BENCHMARKS / "results" / "atr_diamor_unknown_q"
        summary = json.loads((result_dir / "SUMMARY.json").read_text())
        self.assertEqual(summary["summary_version"], "atr-diamor-unknown-q-summary/v1")
        self.assertEqual(
            summary["benchmark_sha256"], hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
        )
        protocol_path = BENCHMARKS / "ATR_DIAMOR_UNKNOWN_Q_PROTOCOL.json"
        self.assertEqual(
            summary["unknown_q_protocol_sha256"],
            hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        )
        oracle = summary["combined"]["oracle_q"]
        unknown = summary["combined"]["all_positive_q"]
        self.assertEqual((oracle["exact_cell_count"], unknown["exact_cell_count"]), (806, 826))
        self.assertEqual(
            (oracle["certified_threshold_decisions"], unknown["certified_threshold_decisions"]),
            (1286, 1136),
        )
        self.assertEqual(unknown["false_certificate_cells_with_representable_truth"], 0)

    def test_cardinality_regimes(self):
        self.assertEqual(module.cardinality_regimes(2, 6), {
            "oracle_q": [2], "q_pm_1": [1, 2, 3], "all_positive_q": [1, 2, 3]
        })
        self.assertEqual(module.cardinality_regimes(1, 4)["q_pm_1"], [1, 2])

    def test_union_frontier_contains_every_fixed_q_frontier(self):
        edges = [(0, 1, 1.0), (2, 3, 3.0), (0, 2, 2.0), (1, 3, 4.0)]
        fixed = module.union_matching_frontier(4, edges, [2], 5.0, 0.0)
        union = module.union_matching_frontier(4, edges, [1, 2], 5.0, 0.0)
        self.assertLessEqual(union["lower"], fixed["lower"])
        self.assertGreaterEqual(union["upper"], fixed["upper"])
        self.assertEqual(union["feasible_q"], [1, 2])

    def test_infeasible_q_does_not_invalidate_exact_union(self):
        result = module.union_matching_frontier(4, [(0, 1, 2.0)], [1, 2], 5.0, 0.0)
        self.assertEqual(result["status"], "EXACT_UNION_OF_REPLAYED_FIXED_Q_FRONTIERS")
        self.assertEqual(result["feasible_q"], [1])
        self.assertEqual(result["lower"], 2.0)
        self.assertEqual(result["upper"], 2.0)

    def test_summary_counts_proved_infeasibility_as_closed(self):
        cells = []
        for status in ("EXACT_UNION_OF_REPLAYED_FIXED_Q_FRONTIERS", "INFEASIBLE"):
            regimes = {}
            for name in ("oracle_q", "q_pm_1", "all_positive_q"):
                regimes[name] = {
                    "status": status,
                    "width": 1.0 if status.startswith("EXACT") else None,
                    "truth_covered": status.startswith("EXACT"),
                    "ambiguous_thresholds": 1 if status.startswith("EXACT") else None,
                    "false_certificates": 0 if status.startswith("EXACT") else None,
                }
            cells.append({"true_world_representable": status.startswith("EXACT"), "regimes": regimes})
        summary = module.summarize(cells, [1.0, 2.0])
        self.assertEqual(summary["oracle_q"]["computationally_closed_cell_count"], 2)
        self.assertEqual(summary["oracle_q"]["exact_cell_count"], 1)
        self.assertEqual(summary["oracle_q"]["infeasible_cell_count"], 1)

    def test_frozen_summary_rejects_hold_and_threshold_mismatch(self):
        base_report = {
            "status": "PASS", "dataset_day": "DIAMOR-1", "audit_role": "pilot",
            "benchmark_sha256": "b", "base_protocol_sha256": "p",
            "unknown_q_protocol_sha256": "u", "decision_threshold_count": 3,
            "eligible_snapshot_count": 1, "cell_count": 0, "summary": {}, "cells": [],
            "claim_scope": "scope",
        }
        other = dict(base_report, dataset_day="DIAMOR-2", audit_role="followup")
        with self.subTest("hold"):
            bad = dict(other, status="HOLD")
            with self.assertRaises(ValueError):
                summary_module.build([(Path("one"), base_report), (Path("two"), bad)])
        with self.subTest("threshold mismatch"):
            bad = dict(other, decision_threshold_count=4)
            with self.assertRaises(ValueError):
                summary_module.build([(Path("one"), base_report), (Path("two"), bad)])


if __name__ == "__main__":
    unittest.main()
