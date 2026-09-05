"""Correctness tests for the compact at-most-K event-slot probe."""
from fractions import Fraction
import itertools
from pathlib import Path
import sys
import unittest

AUDIT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parents[3] / "benchmarks"
sys.path.insert(0, str(AUDIT))
sys.path.insert(0, str(BENCH))

import compact_event_slot_probe as compact
import disclosure_independent_ablation as independent
import ordered_run_disclosure_separator as solver
from ordered_run_fixed_time_master import FixedTimeRow


def row(i, role, start, end):
    return FixedTimeRow(index=i, role=role, start=float(start), end=float(end))


class CompactEventSlotProbeTests(unittest.TestCase):
    def exact_minimum(self, rows, capacity, q, usage, pairs):
        master = independent.exact.build_master(rows, capacity, epsilon=0.1)
        values = []
        for world in independent.all_worlds(master, q):
            try:
                values.append(independent.replay(rows, capacity, q, usage, pairs, world))
            except AssertionError:
                pass
        self.assertTrue(values)
        return min(values)

    def test_capacity_proves_one_slot_impossible_and_two_slot_witness_replays(self):
        rows = [row(0, "core", 0, 1), row(1, "core", 0, 1), row(2, "buffer", 0, 1), row(3, "buffer", 0, 1)]
        result = compact.probe_minimum_events(rows, 2, 2, start_k=1, max_k=2, seconds=5)
        self.assertEqual(result.lower_event_count, 2)
        self.assertEqual(result.certified_infeasible_k, (1,))
        self.assertTrue(result.witness)
        self.assertEqual(independent.replay(rows, 2, 2, {}, {}, result.witness), 2)

    def test_connectivity_cut_rejects_disconnected_one_slot_world(self):
        rows = [row(0, "core", 0, 1), row(1, "core", 2, 3), row(2, "buffer", 0, 1), row(3, "buffer", 2, 3)]
        result = compact.probe_minimum_events(rows, 2, 2, start_k=1, max_k=2, seconds=5)
        self.assertEqual(result.lower_event_count, 2)
        self.assertEqual(result.certified_infeasible_k, (1,))
        self.assertEqual(independent.replay(rows, 2, 2, {}, {}, result.witness), 2)

    def test_positive_pair_makes_optional_endpoints_mandatory(self):
        rows = [row(0, "core", 0, 3), row(1, "core", 0, 3), row(2, "buffer", 0, 3), row(3, "buffer", 0, 3), row(4, "buffer", 0, 3)]
        model = compact.build_slot_model(rows, 3, 2, 2, pair_answers={(2, 3): 1})
        witness = compact._mip_witness(model, 5)
        self.assertTrue(witness)
        used = 0
        for event in witness:
            used |= event
        self.assertTrue(used & (1 << 2))
        self.assertTrue(used & (1 << 3))
        self.assertTrue(any(event & (1 << 2) and event & (1 << 3) for event in witness))

    def test_random_small_lower_bound_never_exceeds_exact_minimum(self):
        checked = 0
        for n, seed, regime, capacity in itertools.product((2, 4), (881, 919), ("none", "mixed"), (2, 3)):
            rows, _, usage, pairs = independent.generate(n, seed, regime)
            q = 2 * n
            optimum = self.exact_minimum(rows, capacity, q, usage, pairs)
            result = compact.probe_minimum_events(rows, capacity, q, start_k=1, max_k=min(optimum, n), usage_answers=usage, pair_answers=pairs, seconds=5)
            self.assertLessEqual(result.lower_event_count, optimum)
            if result.witness:
                value = independent.replay(rows, capacity, q, usage, pairs, result.witness)
                self.assertGreaterEqual(value, optimum)
            checked += 1
        self.assertEqual(checked, 16)

    def test_phase_one_certificate_is_outer_under_interruption(self):
        rows, _, usage, pairs = independent.generate(2, 1823, "mixed")
        optimum = self.exact_minimum(rows, 2, 4, usage, pairs)
        for seconds in (0.0001, 0.001, 0.01):
            result = compact.probe_minimum_events(rows, 2, 4, start_k=1, max_k=2, usage_answers=usage, pair_answers=pairs, seconds=seconds, seek_witness=False)
            self.assertLessEqual(result.lower_event_count, optimum)

    def test_default_solver_skips_probe_below_row_gate(self):
        rows = [row(0, "core", 0, 2), row(1, "core", 0, 2), row(2, "buffer", 0, 2), row(3, "buffer", 0, 2)]
        endpoint = solver.minimize(rows, 2, 2, event_cost=1, limits=solver.Limits(seconds=2, nodes=50))
        self.assertEqual(endpoint.counts["compact_probe_calls"], 0)

    def test_solver_probe_can_be_enabled_and_disabled_explicitly(self):
        rows = [row(i, "core" if i < 6 else "buffer", 0, 1) for i in range(24)]
        enabled = solver.minimize(rows, 4, 12, event_cost=1, limits=solver.Limits(seconds=3, nodes=100, compact_probe_seconds=0.5, compact_probe_rows_min=24, compact_probe_max_k=6))
        disabled = solver.minimize(rows, 4, 12, event_cost=1, limits=solver.Limits(seconds=3, nodes=100, compact_probe_seconds=0, compact_probe_rows_min=24, compact_probe_max_k=6))
        self.assertEqual(enabled.counts["compact_probe_calls"], 1)
        self.assertEqual(disabled.counts["compact_probe_calls"], 0)
        self.assertLessEqual(enabled.lower, Fraction(5))
        self.assertGreaterEqual(enabled.upper, Fraction(5))

    def test_probe_not_used_for_max_event_or_nonzero_row_objective(self):
        rows = [row(i, "core" if i < 6 else "buffer", 0, 1) for i in range(24)]
        for event_cost, costs in ((-1, {}), (1, {6: 1})):
            endpoint = solver.minimize(rows, 4, 12, row_costs=costs, event_cost=event_cost, limits=solver.Limits(seconds=1, nodes=10))
            self.assertEqual(endpoint.counts["compact_probe_calls"], 0)

    def test_invalid_and_zero_budget_inputs_fail_closed(self):
        rows = [row(0, "core", 0, 1), row(1, "buffer", 0, 1)]
        result = compact.probe_minimum_events(rows, 2, 1, start_k=1, max_k=1, seconds=0)
        self.assertEqual(result.status, "SKIPPED")
        self.assertEqual(result.lower_event_count, 1)
        with self.assertRaises(ValueError):
            compact.build_slot_model(rows, 2, 1, 1, pair_answers={(0, 0): 1})


if __name__ == "__main__":
    unittest.main()
