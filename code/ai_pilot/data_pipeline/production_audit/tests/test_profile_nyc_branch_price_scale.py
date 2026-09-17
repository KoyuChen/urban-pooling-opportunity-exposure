from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import profile_nyc_branch_price_scale as target  # noqa: E402


RESULTS = HERE.parent / "results" / "nyc_hvfhv"
SOURCE = RESULTS / "BRANCH_AND_PRICE_SCALE_CELLS.csv"


class BranchPriceScaleProfileTests(unittest.TestCase):
    def test_frozen_profile_localizes_oracle_volume_without_changing_status(self):
        cells = target.read_cells(SOURCE)
        report = target.profile(cells, target.sha256_file(SOURCE))
        self.assertEqual(report["input_scope"]["cell_count"], 18)
        self.assertEqual(report["input_scope"]["certified_cell_count"], 18)
        self.assertEqual(report["totals"]["nodes_processed"], 59)
        self.assertEqual(report["totals"]["maximum_nodes_in_one_cell"], 11)
        self.assertEqual(report["totals"]["oracle_lp_solve_count"], 2_389_799)
        self.assertGreater(report["runtime_concentration"]["top_four_share"], 0.87)
        correlations = report["log1p_pearson_with_runtime"]
        self.assertGreater(correlations["total_oracle_lp_solve_count"], 0.98)
        self.assertLess(correlations["nodes_processed"], 0.55)
        self.assertEqual(
            report["bottleneck"]["classification"],
            "PRICING_LP_VOLUME_PRIMARY_SCALING_SIGNAL",
        )
        self.assertTrue(
            all(cell["status"] == "INTEGER_OPTIMUM_CERTIFIED" for cell in report["cells"])
        )

    def test_outputs_are_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            target.run(SOURCE, Path(first))
            target.run(SOURCE, Path(second))
            for name in ("PROFILE.json", "PROFILE_CELLS.csv", "REPORT.md", "RESULTS.tex"):
                self.assertEqual(
                    (Path(first) / name).read_bytes(),
                    (Path(second) / name).read_bytes(),
                    name,
                )
            manifest = json.loads((Path(first) / "MANIFEST.json").read_text())
            self.assertFalse(manifest["certificate_statuses_changed"])

    def test_duplicate_cell_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            duplicate = Path(tmp) / "duplicate.csv"
            with SOURCE.open(newline="", encoding="utf-8") as source_handle:
                rows = list(csv.DictReader(source_handle))
            with duplicate.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows + [rows[0]])
            with self.assertRaisesRegex(ValueError, "duplicate scale cell"):
                target.read_cells(duplicate)


if __name__ == "__main__":
    unittest.main()
