from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import nyc_branch_price_cache_replay as target  # noqa: E402


class NycBranchPriceCacheReplayTests(unittest.TestCase):
    def test_frozen_public_reconstruction_summary(self) -> None:
        result_dir = (
            HERE.parent
            / "results"
            / "nyc_hvfhv"
            / "branch_price_cache_reconstruction_20260919"
        )
        summary_path = result_dir / "SUMMARY.json"
        manifest = json.loads((result_dir / "MANIFEST.json").read_text())
        summary = json.loads(summary_path.read_text())
        self.assertEqual(summary["cell_count"], 4)
        self.assertEqual(summary["total_baseline_oracle_lp_calls"], 1_880_627)
        self.assertEqual(summary["total_accelerated_oracle_lp_calls"], 1_324_841)
        self.assertEqual(summary["runtime_win_cells"], 4)
        self.assertAlmostEqual(summary["total_oracle_lp_call_reduction_rate"], 0.295532287901854)
        hashes = {
            (row["target"]["core_rows"], row["target"]["capacity"]):
            row["reconstructed_fixed_input_sha256"]
            for row in summary["cells"]
        }
        self.assertEqual(hashes[(16, 3)], hashes[(16, 4)])
        self.assertEqual(
            hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            manifest["summary_sha256"],
        )

    def test_historical_path_check_uses_frozen_diagnostics(self) -> None:
        frozen = target.frozen_cell(16, 4)
        reconstructed = {"status": frozen["status"]}
        for field in target.INTEGER_HISTORICAL_FIELDS:
            reconstructed[field] = int(frozen[field])
        for field in (
            "integer_maximum_selected_buffers",
            "global_lower_bound",
            "global_upper_bound",
            "root_lp_upper_bound",
        ):
            reconstructed[field] = float(frozen[field])
        self.assertTrue(target.historical_path_matches(reconstructed, frozen))
        reconstructed["nodes_processed"] += 1
        self.assertFalse(target.historical_path_matches(reconstructed, frozen))

    def test_aggregate_requires_all_four_targets_and_preserves_denominator(self) -> None:
        reports = []
        for index, (core, capacity) in enumerate(sorted(target.TARGETS)):
            common = {
                "status": "INTEGER_OPTIMUM_CERTIFIED",
                "integer_maximum_selected_buffers": float(3 * core),
                "global_lower_bound": float(3 * core),
                "global_upper_bound": float(3 * core),
                "root_lp_upper_bound": float(3 * core),
                "nodes_processed": 1,
                "nodes_infeasible": 0,
                "nodes_bound_pruned": 1,
                "nodes_integral": 0,
                "buffer_branches": 0,
                "pair_branches": 0,
                "maximum_depth": 0,
                "selected_column_count": core,
                "total_generated_columns_across_nodes": 10,
                "total_pricing_case_count": 5,
                "maximum_pricing_cases_for_one_root": 1,
            }
            reports.append(
                {
                    "report_version": target.VERSION,
                    "target": {
                        "core_rows": core,
                        "buffer_rows": 3 * core,
                        "capacity": capacity,
                    },
                    "certificate_and_branch_path_equal": True,
                    "baseline_matches_historical_diagnostics": True,
                    "baseline": {
                        **common,
                        "total_oracle_lp_solve_count": 100 + index,
                        "elapsed_seconds": 2.0,
                    },
                    "accelerated": {
                        **common,
                        "total_oracle_lp_solve_count": 80 + index,
                        "elapsed_seconds": 1.0,
                    },
                    "oracle_lp_call_reduction_rate": 0.2,
                }
            )
        summary = target.aggregate_reports(reports)
        self.assertEqual(summary["cell_count"], 4)
        self.assertEqual(summary["total_oracle_lp_call_reduction"], 80)
        self.assertEqual(summary["runtime_win_cells"], 4)
        self.assertAlmostEqual(summary["descriptive_elapsed_time_reduction_rate"], 0.5)
        tex = target.render_tex(summary)
        self.assertIn("Dominant-cell pricing-cache reconstruction", tex)
        self.assertIn("19.7", tex)
        with self.assertRaisesRegex(ValueError, "exactly the four"):
            target.aggregate_reports(reports[:-1])

    def test_source_drift_fails_closed(self) -> None:
        selected = {
            "provider": "HV0005",
            "core_start": type("D", (), {"isoformat": lambda self: "2023-01-03T17:45:00"})(),
            "core_end": type("D", (), {"isoformat": lambda self: "2023-01-03T18:00:00"})(),
        }
        audit = {"core_rows": 38, "rows": 437}
        target.assert_frozen_source(dict(target.FROZEN_SNAPSHOT), selected, audit)
        changed = dict(target.FROZEN_SNAPSHOT)
        changed["rows_updated_at"] += 1
        with self.assertRaisesRegex(ValueError, "fingerprint differs"):
            target.assert_frozen_source(changed, selected, audit)


if __name__ == "__main__":
    unittest.main()
