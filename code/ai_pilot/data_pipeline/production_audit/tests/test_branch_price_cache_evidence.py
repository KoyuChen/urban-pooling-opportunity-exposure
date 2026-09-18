"""Check frozen pricing-cache evidence without asserting runner timings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS = ROOT / "benchmarks"
RESULTS = BENCHMARKS / "results" / "branch_price_cache_20260918"
SOLVER = ROOT / "data_pipeline" / "production_audit" / "ordered_run_branch_and_price.py"
PROTOCOL = BENCHMARKS / "BRANCH_PRICE_CACHE_PROTOCOL.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BranchPriceCacheEvidenceTests(unittest.TestCase):
    def test_frozen_certificate_and_lp_call_counts(self) -> None:
        summary = json.loads((RESULTS / "SUMMARY.json").read_text(encoding="utf-8"))

        self.assertEqual(summary["report_version"], "ordered-branch-price-cache-paired/v1")
        self.assertEqual(summary["cell_count"], 5)
        self.assertEqual(summary["paired_run_count"], 10)
        self.assertTrue(summary["all_certificates_equal"])
        self.assertTrue(summary["all_runs_integer_optimum_certified"])
        self.assertEqual(summary["total_baseline_oracle_lp_calls"], 9_900)
        self.assertEqual(summary["total_accelerated_oracle_lp_calls"], 7_770)
        self.assertEqual(summary["total_oracle_lp_call_reduction"], 2_130)
        self.assertAlmostEqual(
            summary["total_oracle_lp_call_reduction_rate"], 2_130 / 9_900
        )
        self.assertIn("not the frozen NYC public cohort", summary["claim_boundary"])

        by_label = {cell["label"]: cell for cell in summary["cells"]}
        self.assertEqual(
            {
                label: (
                    cell["baseline_oracle_lp_calls"],
                    cell["accelerated_oracle_lp_calls"],
                )
                for label, cell in by_label.items()
            },
            {
                "fractional_master": (1_030, 573),
                "regular_n3_c2": (960, 866),
                "regular_n3_c3": (396, 396),
                "regular_n4_c2": (6_520, 4_941),
                "regular_n4_c3": (994, 994),
            },
        )

    def test_manifest_hashes_and_deterministic_outputs(self) -> None:
        manifest = json.loads((RESULTS / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["protocol_sha256"], sha256(PROTOCOL))
        self.assertEqual(manifest["solver_sha256"], sha256(SOLVER))
        self.assertEqual(
            manifest["deterministic_fields"],
            "certificates, branch paths, LP-call counts, cache counts",
        )
        for name, expected in manifest["outputs"].items():
            self.assertEqual(sha256(RESULTS / name), expected, name)


if __name__ == "__main__":
    unittest.main()
