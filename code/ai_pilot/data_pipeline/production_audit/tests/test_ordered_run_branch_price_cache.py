from __future__ import annotations

from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ordered_run_branch_and_price as target  # noqa: E402
import ordered_run_column_generation as column_generation  # noqa: E402
import ordered_run_fixed_time_master as exact  # noqa: E402
from ordered_run_interval_oracle import GridInterval  # noqa: E402


class OrderedRunBranchPriceCacheTests(unittest.TestCase):
    def test_exact_box_infeasibility_is_reused_across_objectives(self):
        intervals = [GridInterval(0, 3) for _ in range(3)]
        cache = target.PricingCache()
        first = target._solve_fixed_span_forced(
            intervals,
            [1.0, 1.0, 1.0],
            (0, 3),
            2,
            frozenset(range(3)),
            frozenset(),
            cache=cache,
        )
        second = target._solve_fixed_span_forced(
            intervals,
            [-3.0, 4.0, 7.0],
            (0, 3),
            2,
            frozenset(range(3)),
            frozenset(),
            cache=cache,
        )
        self.assertEqual(first["status"], "PROVEN_INFEASIBLE")
        self.assertEqual(second["status"], "PROVEN_INFEASIBLE")
        self.assertEqual(first["lp_solve_count"], 0)
        self.assertEqual(second["lp_solve_count"], 0)
        self.assertEqual(cache.exact_box_prunes, 1)
        self.assertEqual(cache.infeasible_box_cache_hits, 1)

    def test_cache_cannot_cross_interval_universes(self):
        cache = target.PricingCache()
        target._solve_fixed_span_forced(
            [GridInterval(0, 2), GridInterval(0, 2)],
            [1.0, 1.0],
            (0, 2),
            2,
            frozenset({0}),
            frozenset(),
            cache=cache,
        )
        with self.assertRaisesRegex(ValueError, "different interval universes"):
            target._solve_fixed_span_forced(
                [GridInterval(0, 3), GridInterval(0, 3)],
                [1.0, 1.0],
                (0, 3),
                2,
                frozenset({0}),
                frozenset(),
                cache=cache,
            )

    def test_cache_switch_preserves_fractional_master_certificate(self):
        rows = column_generation.integrality_gap_counterexample()
        baseline = target.branch_and_price_max_support(
            rows, 2, time_limit_seconds=30.0, use_pricing_cache=False
        )
        accelerated = target.branch_and_price_max_support(
            rows, 2, time_limit_seconds=30.0, use_pricing_cache=True
        )
        compared = (
            "status",
            "integer_maximum_selected_buffers",
            "global_lower_bound",
            "global_upper_bound",
            "root_lp_upper_bound",
            "nodes_processed",
            "buffer_branches",
            "pair_branches",
            "selected_column_count",
        )
        self.assertEqual(
            {key: baseline.get(key) for key in compared},
            {key: accelerated.get(key) for key in compared},
        )
        self.assertLess(
            accelerated["total_oracle_lp_solve_count"],
            baseline["total_oracle_lp_solve_count"],
        )
        self.assertGreater(accelerated["pricing_infeasible_box_cache_hits"], 0)

    def test_seeded_tiny_battery_matches_exhaustive_with_cache(self):
        for seed in range(6):
            rows = target._random_rows(seed)
            for capacity in (2, 3):
                master = exact.build_master(rows, capacity, epsilon=0.1)
                expected = exact.support_frontier(master)[
                    "maximum_selected_buffers"
                ]
                result = target.branch_and_price_max_support(
                    rows,
                    capacity,
                    time_limit_seconds=30.0,
                    use_pricing_cache=True,
                )
                if expected is None:
                    self.assertEqual(
                        result["status"], "INTEGER_MASTER_PROVEN_INFEASIBLE"
                    )
                else:
                    self.assertEqual(result["status"], "INTEGER_OPTIMUM_CERTIFIED")
                    self.assertAlmostEqual(
                        result["integer_maximum_selected_buffers"], expected
                    )

    def test_nonboolean_cache_switch_fails_closed(self):
        rows = [
            exact.FixedTimeRow(0, "core", 0, 2),
            exact.FixedTimeRow(1, "buffer", 0, 2),
        ]
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            target.branch_and_price_max_support(
                rows, 2, use_pricing_cache="yes"  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
