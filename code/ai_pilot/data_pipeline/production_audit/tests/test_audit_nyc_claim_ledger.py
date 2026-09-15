from __future__ import annotations

import sys
import unittest
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

import audit_nyc_claim_ledger as ledger  # noqa: E402


class NycClaimLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results = PACKAGE_DIR.parent / "results" / "nyc_hvfhv"
        cls.report = ledger.build(cls.results)

    def test_four_evidence_questions_remain_distinct(self) -> None:
        records = {row["evidence_object"]: row for row in self.report["records"]}
        self.assertEqual(set(records), {
            "outcome_decision_panel",
            "support_maximization_lattice",
            "fixed_q_structure_comparator",
            "outcome_blind_geometry_census",
        })
        self.assertEqual(records["outcome_decision_panel"]["primary_unresolved_count"], 25)
        self.assertEqual(records["support_maximization_lattice"]["primary_unresolved_count"], 0)
        self.assertEqual(records["outcome_blind_geometry_census"]["status"], "HOLD_TRANSPORT_INCOMPLETE")

    def test_decision_witnesses_do_not_require_endpoint_closure(self) -> None:
        row = self.report["records"][0]
        self.assertEqual(row["primary_certified_count"], 101)
        self.assertIn("125/126", row["secondary_result"])

    def test_structure_result_is_a_verified_null(self) -> None:
        row = self.report["records"][2]
        self.assertEqual(row["status"], "PASS_VERIFIED_NULL")
        self.assertEqual(row["primary_certified_count"], 24)
        self.assertIn("0/24", row["secondary_result"])


if __name__ == "__main__":
    unittest.main()
