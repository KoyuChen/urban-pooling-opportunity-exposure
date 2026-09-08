import json
import hashlib
from fractions import Fraction
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import ordered_run_structure_audit as structure
from ordered_run_fixed_time_master import FixedTimeRow as Row, build_master


def protocol(core=2, buffer=3, capacities=(2, 3)):
    spec = json.loads((MODULE_DIR / "NYC_STRUCTURE_AUDIT_PROTOCOL.json").read_text())
    spec.update(core_rows=core, buffer_rows=buffer, capacities=list(capacities),
                overlap_epsilon_seconds=0.1, minimum_interval_duration_seconds=0.1)
    return spec


def sequential_rows():
    return [Row(0, "core", 0, 4), Row(1, "core", 3, 7),
            Row(2, "buffer", -1, 1, miles=1, seconds=60),
            Row(3, "buffer", 1, 2.5, miles=2, seconds=120),
            Row(4, "buffer", 5, 6, miles=10, seconds=600)]


class StructureAuditTests(unittest.TestCase):
    def test_fixed_count_frontier_differs_on_known_sequential_example(self):
        result = structure.audit(sequential_rows(), protocol())
        self.assertEqual(result["summary"]["verification_status"], "PASS")
        for row in result["comparisons"]:
            self.assertEqual(row["q"], 2)
            self.assertEqual(row["ordered_lower"], 1.5)
            self.assertEqual(row["restricted_lower"], 5.5)
            self.assertEqual(row["ordered_upper"], 6)
            self.assertEqual(row["restricted_upper"], 6)
        for cell in result["support_cells"]:
            self.assertEqual(cell["maximum_selected_buffers"], 3 if cell["family"] == "ordered" else 2)

    def test_null_result_is_preserved(self):
        rows = [Row(0, "core", 0, 3), Row(1, "core", 10, 13),
                Row(2, "buffer", 1, 2, 1, 60), Row(3, "buffer", 11, 12, 2, 120)]
        result = structure.audit(rows, protocol(buffer=2))
        self.assertEqual(result["summary"]["changed_fixed_q_comparisons"], 0)
        self.assertEqual(result["summary"]["fixed_q_comparisons"], 8)

    def test_restricted_infeasibility_is_not_ordered_infeasibility(self):
        rows = [Row(0, "core", 0, 2), Row(1, "core", 1, 4), Row(2, "core", 3, 5)]
        result = structure.audit(rows, protocol(core=3, buffer=0, capacities=(2,)))
        cells = {row["family"]: row for row in result["support_cells"]}
        self.assertEqual(cells["ordered"]["reachable_selected_buffer_counts"], [0])
        self.assertEqual(cells["pair"]["reachable_selected_buffer_counts"], [])
        self.assertEqual(cells["clique"]["reachable_selected_buffer_counts"], [])
        self.assertEqual(result["summary"]["outcome_endpoint_pairs"], 0)

    def test_missing_public_values_are_not_solver_failure(self):
        rows = sequential_rows()
        rows[-1] = Row(4, "buffer", 5, 6, None, 600)
        result = structure.audit(rows, protocol(capacities=(2,)))
        self.assertEqual(result["summary"]["verification_status"], "PASS")
        self.assertEqual(result["summary"]["missing_query_value_pairs"], 3)
        self.assertEqual(result["summary"]["certified_endpoint_pairs"], 3)

    def test_timeout_stays_unresolved(self):
        with patch.object(structure, "milp", return_value=SimpleNamespace(status=1)):
            result = structure.audit(sequential_rows(), protocol(capacities=(2,)))
        self.assertEqual(result["summary"]["verification_status"], "HOLD_UNRESOLVED_VERIFICATION")
        self.assertGreater(result["summary"]["unresolved_verification_count"], 0)
        self.assertTrue(all(check["status"] == "UNRESOLVED_MILP_VERIFICATION"
                            for cell in result["support_cells"] for check in cell["support_checks"]))

    def test_witness_replay_rejects_wrong_family_reuse_and_q(self):
        master = build_master(sequential_rows(), 2, epsilon=0.1)
        chain = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3)
        self.assertEqual(structure.replay(master, "ordered", [chain], 2), 12)
        for family, masks, q in (("clique", [chain], 2), ("ordered", [chain, chain], 2),
                                  ("ordered", [chain], 1)):
            with self.assertRaises(AssertionError):
                structure.replay(master, family, masks, q)

    def test_sub_epsilon_intervals_are_outside_protocol(self):
        rows = sequential_rows()
        rows[-1] = Row(4, "buffer", 5, 5.01, 10, 600)
        with self.assertRaisesRegex(ValueError, "sub-epsilon"):
            structure.audit(rows, protocol())

    def test_frozen_public_evidence_integrity_and_null_comparison(self):
        root = MODULE_DIR.parent / "results/nyc_hvfhv/structure_audit_20260908"
        manifest = json.loads((root / "MANIFEST.json").read_text())
        for name, expected in manifest["files_sha256"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected)
        report = json.loads((root / "REPORT.json").read_text())
        for name, expected in report["provenance"]["source_code_sha256"].items():
            self.assertEqual(hashlib.sha256((MODULE_DIR / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(hashlib.sha256((MODULE_DIR / "NYC_STRUCTURE_AUDIT_PROTOCOL.json").read_bytes()).hexdigest(),
                         report["provenance"]["protocol_sha256"])
        self.assertEqual(report["summary"]["verification_status"], "PASS")
        self.assertEqual(report["summary"]["certified_endpoint_pairs"], 36)
        self.assertEqual(report["summary"]["fixed_q_comparisons"], 24)
        self.assertEqual(report["summary"]["changed_fixed_q_comparisons"], 0)
        self.assertEqual(report["input_geometry"]["overlap_edges"], 120)
        self.assertEqual(report["input_geometry"]["all_rows_common_overlap_seconds"], 14)
        for cell in report["support_cells"]:
            self.assertEqual(len(cell["support_checks"]), 13)
            self.assertTrue(all(check["agreement"] for check in cell["support_checks"]))
        for cell in report["outcome_cells"]:
            self.assertEqual(cell["reachable_q_buffer_masks"], cell["all_possible_q_buffer_subsets"])
            self.assertEqual(Fraction(cell["upper_rational"]) - Fraction(cell["lower_rational"]),
                             Fraction(cell["width_rational"]))
            for direction in ("lower", "upper"):
                self.assertEqual(cell[direction + "_milp_status"], "OPTIMAL_NUMERICAL_MILP_REPLAYED")
                self.assertEqual(len(cell[direction + "_witness_sha256"]), 64)
        def check_redaction(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & {"rows", "member_mask", "core_mask", "buffer_mask",
                                             "lower_selected_buffer_mask", "upper_selected_buffer_mask"})
                for item in value.values():
                    check_redaction(item)
            elif isinstance(value, list):
                for item in value:
                    check_redaction(item)
        check_redaction(report)


if __name__ == "__main__":
    unittest.main()
