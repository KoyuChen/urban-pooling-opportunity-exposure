import sys
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import ordered_run_column_generation as column_generation  # noqa: E402
import ordered_run_fixed_time_master as exhaustive  # noqa: E402


class OrderedRunColumnGenerationTests(unittest.TestCase):
    def test_column_generation_matches_complete_master_lp(self):
        rows = [
            exhaustive.FixedTimeRow(0, "core", 0, 2),
            exhaustive.FixedTimeRow(1, "core", 3, 5),
            exhaustive.FixedTimeRow(2, "buffer", 0, 1.5),
            exhaustive.FixedTimeRow(3, "buffer", 3.5, 5),
        ]
        result = column_generation.compare_with_exhaustive(rows, 2, epsilon=0.1)
        self.assertEqual(
            result["column_generation_status"],
            "FULL_MASTER_LP_CERTIFIED_OPTIMAL",
        )
        self.assertEqual(result["full_lp_maximum_selected_buffers"], 2.0)
        self.assertEqual(result["exact_integer_maximum_selected_buffers"], 2)

    def test_master_nonintegrality_is_explicit(self):
        result = column_generation.compare_with_exhaustive(
            column_generation.integrality_gap_counterexample(), 2, epsilon=0.1
        )
        self.assertEqual(result["full_lp_maximum_selected_buffers"], 4.0)
        self.assertEqual(result["exact_integer_maximum_selected_buffers"], 3)
        self.assertEqual(result["full_master_lp_integrality_gap"], 1.0)

    def test_random_tiny_battery_matches_full_lp(self):
        for seed in range(10):
            rows = column_generation._random_rows(seed)
            for capacity in (2, 3):
                column_generation.compare_with_exhaustive(
                    rows, capacity, epsilon=0.1
                )


if __name__ == "__main__":
    unittest.main()
