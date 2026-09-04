import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import live_nyc_hvfhv_capacity_smoke as capacity  # noqa: E402
from nyc_hvfhv_smoke_types import ModelTrip  # noqa: E402


class NYCAnchoredCapacityTests(unittest.TestCase):
    def setUp(self):
        base = datetime(2023, 1, 1, 12, 0)
        self.rows = [
            ModelTrip(0, "HV0003", "core", base, base + timedelta(minutes=20), "1", "2", 1.0, 600.0, 10.0, 7.0),
            ModelTrip(1, "HV0003", "core", base + timedelta(minutes=1), base + timedelta(minutes=21), "1", "2", 2.0, 660.0, 11.0, 8.0),
            ModelTrip(2, "HV0003", "core", base + timedelta(minutes=2), base + timedelta(minutes=22), "3", "4", 4.0, 780.0, 13.0, 9.0),
            ModelTrip(3, "HV0003", "core", base + timedelta(minutes=3), base + timedelta(minutes=23), "3", "5", 8.0, 900.0, 16.0, 11.0),
            ModelTrip(4, "HV0003", "buffer", base + timedelta(minutes=4), base + timedelta(minutes=24), "6", "7", 16.0, 1200.0, 20.0, 14.0),
        ]

    def test_capacity_two_three_four_all_feasible(self):
        objective = lambda member, anchor: abs(member.miles - anchor.miles)
        for c in (2, 3, 4):
            result = capacity.solve_objective(self.rows, c, objective, False, 10)
            self.assertEqual(result["status"], "OPTIMAL_NUMERICAL_MILP")
            self.assertEqual(result["residual"], 0.0)

    def test_capacity_relaxation_nests_bounds(self):
        objective = lambda member, anchor: abs(member.miles - anchor.miles)
        lows = []
        highs = []
        for c in (2, 3, 4):
            lows.append(capacity.solve_objective(self.rows, c, objective, False, 10)["value"])
            highs.append(capacity.solve_objective(self.rows, c, objective, True, 10)["value"])
        self.assertGreaterEqual(lows[0] + 1e-9, lows[1])
        self.assertGreaterEqual(lows[1] + 1e-9, lows[2])
        self.assertLessEqual(highs[0] - 1e-9, highs[1])
        self.assertLessEqual(highs[1] - 1e-9, highs[2])

    def test_core_exactly_once_buffer_at_most_once_is_encoded(self):
        anchors, pairs, _y, _x, constraint, variable_bounds = capacity.build_program(self.rows, 3)
        self.assertEqual(anchors, [0, 1, 2, 3])
        self.assertGreaterEqual(len(pairs), 16)
        self.assertEqual(len(variable_bounds.lb), len(anchors) + len(pairs))
        self.assertEqual(constraint.A.shape[1], len(variable_bounds.lb))

    def test_missing_public_query_values_fail_closed(self):
        damaged = list(self.rows)
        first = damaged[0]
        damaged[0] = ModelTrip(
            first.index,
            first.provider,
            first.role,
            first.start,
            first.end,
            first.pickup_zone,
            first.dropoff_zone,
            None,
            first.seconds,
            first.fare,
            first.driver_pay,
        )
        objective = lambda member, anchor: None if member.miles is None or anchor.miles is None else abs(member.miles-anchor.miles)
        result = capacity.solve_objective(damaged, 2, objective, False, 10)
        self.assertEqual(result["status"], "UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES")
        self.assertGreater(result["missing_assignment_values"], 0)


if __name__ == "__main__":
    unittest.main()
