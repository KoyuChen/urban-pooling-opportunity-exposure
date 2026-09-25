import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "audit_nyc_nonclique_endpoint_attainment",
    MODULE_DIR / "audit_nyc_nonclique_endpoint_attainment.py",
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

from ordered_run_fixed_time_master import FixedTimeRow, build_master
import ordered_run_structure_audit as structure


class EndpointAttainmentAuditTests(unittest.TestCase):
    def fixture(self):
        return [
            FixedTimeRow(0, "core", 0.0, 4.0, 0.0, 4.0),
            FixedTimeRow(1, "core", 1.0, 5.0, 0.0, 4.0),
            FixedTimeRow(2, "buffer", 2.0, 6.0, 1.0, 4.0),
            FixedTimeRow(3, "buffer", 3.0, 7.0, 3.0, 4.0),
        ]

    def test_partition_counts_match_reachable_projection(self):
        ordered = build_master(self.fixture(), 3, epsilon=1.0)
        for family in structure.FAMILIES:
            master = structure.restricted_master(ordered, family)
            counts = audit.partition_counts(master)
            self.assertEqual(set(counts), master.reachable_buffer_masks)
            self.assertTrue(all(value > 0 for value in counts.values()))

    def test_restricted_partitions_are_nested(self):
        ordered = build_master(self.fixture(), 3, epsilon=1.0)
        full = audit.partition_counts(ordered)
        for family in ("pair", "clique"):
            restricted = audit.partition_counts(
                structure.restricted_master(ordered, family)
            )
            self.assertLessEqual(set(restricted), set(full))
            self.assertTrue(all(restricted[m] <= full[m] for m in restricted))

    def test_endpoint_returns_all_exact_ties(self):
        rows = self.fixture()
        rows[3] = FixedTimeRow(3, "buffer", 3.0, 7.0, 1.0, 4.0)
        master = build_master(rows, 3, epsilon=1.0)
        query = {"attribute": "miles", "scale": 1}
        value, ties = audit.endpoint(master, 1, query, "lower")
        self.assertEqual(float(value), 1.0)
        self.assertEqual(len(ties), 2)

    def test_frozen_artifact_integrity_and_claim_boundary(self):
        root = MODULE_DIR.parent / "results/nyc_hvfhv/nonclique_endpoint_attainment_20260925"
        manifest = json.loads((root / "MANIFEST.json").read_text())
        self.assertTrue(manifest["aggregate_only"])
        for name, expected in manifest["files_sha256"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected)
        report = json.loads((root / "SUMMARY.json").read_text())
        summary = report["summary"]
        self.assertEqual(report["status"], "PASS_ENDPOINT_ATTAINMENT_NULL_EXPLAINED")
        self.assertEqual(summary["endpoint_attainment_checks"], 192)
        self.assertEqual(summary["attained_endpoint_checks"], 192)
        self.assertEqual(summary["unresolved_endpoint_checks"], 0)
        self.assertEqual(summary["extra_subset_cells"], 4)
        self.assertEqual(summary["partition_only_cells"], 36)
        self.assertEqual(summary["identical_partition_and_subset_cells"], 8)
        self.assertEqual(summary["endpoint_checks_with_ordered_only_ties"], 0)
        serialized = json.dumps(report, sort_keys=True)
        for forbidden in ("pickup_datetime", "dropoff_datetime", "member_mask", "buffer_mask"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
