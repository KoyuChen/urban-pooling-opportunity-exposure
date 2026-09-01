import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import live_nyc_hvfhv_ordered_run_smoke as ordered  # noqa: E402
from nyc_hvfhv_smoke_types import CERTIFIED, ModelTrip  # noqa: E402


class OrderedRunTests(unittest.TestCase):
    def test_chain_connectivity_allows_non_pairwise_run(self):
        rows = ordered.synthetic_chain()
        self.assertTrue(ordered.positive_overlap(rows[0], rows[1]))
        self.assertTrue(ordered.positive_overlap(rows[1], rows[2]))
        self.assertFalse(ordered.positive_overlap(rows[0], rows[2]))
        program = ordered.build_program(rows, 2)
        result = ordered.solve(
            program,
            ordered.objective(program, "selected_buffer_rows_per_core"),
            True,
            10.0,
        )
        self.assertEqual(result["status"], CERTIFIED)
        self.assertAlmostEqual(result["value"], 0.5)

    def test_capacity_three_weakly_expands_clique_feasible_set(self):
        base = datetime(2023, 1, 1, 12)
        rows = [
            ModelTrip(
                i,
                "HV",
                "core" if i < 2 else "buffer",
                base,
                base + timedelta(minutes=10),
                "1",
                str(i),
                1.0,
                600.0,
                10.0,
                8.0,
            )
            for i in range(3)
        ]
        values = []
        for capacity in (2, 3):
            program = ordered.build_program(rows, capacity)
            result = ordered.solve(
                program,
                ordered.objective(program, "selected_buffer_rows_per_core"),
                True,
                10.0,
            )
            self.assertEqual(result["status"], CERTIFIED)
            values.append(result["value"])
        self.assertLessEqual(values[0], values[1])

    def test_capacity_frontier_is_nested_on_chain_fixture(self):
        rows = ordered.synthetic_chain()
        frontier = ordered.solve_frontier(rows, "exact_second", 10.0)
        # Duplicate under second time-model label so the generic audit sees both chains.
        twin = [{**row, "time_model": "rounded_15m_outer"} for row in frontier]
        audit = ordered.audit([*frontier, *twin])
        self.assertEqual(audit["status"], "PASS")
        self.assertGreater(audit["comparisons"], 0)


if __name__ == "__main__":
    unittest.main()
