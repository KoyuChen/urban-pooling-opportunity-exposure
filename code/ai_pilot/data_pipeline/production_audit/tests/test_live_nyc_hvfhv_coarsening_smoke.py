import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import live_nyc_hvfhv_coarsening_smoke as runner  # noqa: E402
import nyc_hvfhv_smoke_bounds as bounds  # noqa: E402
import nyc_hvfhv_smoke_types as types  # noqa: E402


class NYCHVFHVCandidateFrontierTests(unittest.TestCase):
    def setUp(self):
        base = datetime(2023, 1, 1, 12, 0)
        self.trips = [
            runner.synthetic_trip(
                0,
                "core",
                base,
                base + timedelta(minutes=20),
                "1",
                "2",
            ),
            runner.synthetic_trip(
                1,
                "core",
                base + timedelta(minutes=1),
                base + timedelta(minutes=21),
                "1",
                "2",
            ),
            runner.synthetic_trip(
                2,
                "buffer",
                base + timedelta(minutes=22),
                base + timedelta(minutes=40),
                "1",
                "3",
            ),
            runner.synthetic_trip(
                3,
                "buffer",
                base - timedelta(minutes=10),
                base + timedelta(minutes=5),
                "4",
                "2",
            ),
        ]

    def test_rounding_tie_goes_forward(self):
        base = datetime(2023, 1, 1, 12, 0)
        self.assertEqual(
            types.round15(base + timedelta(minutes=7, seconds=29)),
            base,
        )
        self.assertEqual(
            types.round15(base + timedelta(minutes=7, seconds=30)),
            base + timedelta(minutes=15),
        )

    def test_artificial_coarsening_never_shrinks_time_edges(self):
        exact = types.model_rows(self.trips, "exact_second")
        rounded = types.model_rows(self.trips, "rounded_15m_outer")
        exact_edges = set(bounds.temporal_edges(exact))
        rounded_edges = set(bounds.temporal_edges(rounded))
        self.assertTrue(exact_edges <= rounded_edges)
        self.assertNotIn((0, 2), exact_edges)
        self.assertIn((0, 2), rounded_edges)

    def test_zone_support_tiers_are_nested(self):
        for resolution in ("exact_second", "rounded_15m_outer"):
            rows = types.model_rows(self.trips, resolution)
            temporal = bounds.temporal_edges(rows)
            sets = {
                tier: set(bounds.tier_edges(rows, temporal, tier))
                for tier, _rank in types.TIERS
            }
            self.assertTrue(
                sets["same_od_zone"]
                <= sets["same_pickup_zone"]
                <= sets["provider_time_only"]
            )

    def test_pairwise_core_cover_replays_exactly(self):
        rows = types.model_rows(self.trips, "exact_second")
        edges = bounds.temporal_edges(rows)
        result = bounds.solve(rows, edges, [0.0] * len(edges), False, 10)
        self.assertEqual(result.status, types.CERTIFIED)
        self.assertEqual(result.residual, 0.0)

    def test_missing_numeric_values_fail_query_closed(self):
        first = self.trips[0]
        damaged = [
            types.Trip(
                first.index,
                first.provider,
                first.role,
                first.pickup,
                first.dropoff,
                first.pickup_zone,
                first.dropoff_zone,
                None,
                first.seconds,
                first.fare,
                first.driver_pay,
            ),
            *self.trips[1:],
        ]
        rows = types.model_rows(damaged, "exact_second")
        edges = bounds.temporal_edges(rows)
        miles = next(
            item
            for item in bounds.queries()
            if item[0].startswith("mean_absolute_trip_miles")
        )
        lower, upper, missing = bounds.coefficients(rows, edges, miles[2])
        self.assertIsNone(lower)
        self.assertIsNone(upper)
        self.assertGreater(missing, 0)


if __name__ == "__main__":
    unittest.main()
