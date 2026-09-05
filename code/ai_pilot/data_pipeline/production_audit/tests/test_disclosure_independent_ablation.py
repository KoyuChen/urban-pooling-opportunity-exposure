"""Audit instrumentation correctness without hardware-dependent CI assertions."""
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

BENCH = Path(__file__).resolve().parents[3] / 'benchmarks'
sys.path.insert(0, str(BENCH))
import disclosure_independent_ablation as a


class IndependentAblationTests(unittest.TestCase):
    def require_frozen_source(self):
        path = a.AUDIT/'ordered_run_disclosure_separator.py'
        if a.sha(path) != a.PIN:
            self.skipTest('reproduce frozen solver ablations at the pinned source checkout')

    def test_seeded_chains_are_nonclique_and_reference_is_valid(self):
        for n, seed, regime, cap in itertools.product((2, 4, 8, 12), (730001, 730019), ('none', 'mixed'), (2, 3)):
            rows, ref, usage, pairs = a.generate(n, seed, regime)
            self.assertEqual(len(rows), 4*n)
            self.assertEqual(a.replay(rows, cap, 2*n, usage, pairs, ref), n)
            for mask in ref:
                group = [r for i, r in enumerate(rows) if mask & (1 << i)]
                self.assertEqual(len(group), 3)
                self.assertTrue(any(max(x.start, y.start) >= min(x.end, y.end)
                                    for x, y in itertools.combinations(group, 2)))
            self.assertEqual(a.generate(n, seed, regime), (rows, ref, usage, pairs))

    def test_every_variant_matches_small_oracle(self):
        self.require_frozen_source()
        self.assertEqual(a.self_test(), 54)

    def test_every_variant_preserves_zero_budget_bound(self):
        self.require_frozen_source()
        rows, ref, usage, pairs = a.generate(4, 730019, 'mixed')
        for variant in a.VARIANTS:
            s = a.variant_module(variant)
            result = s.minimize(rows, 2, 8, event_cost=1, usage_answers=usage,
                                pair_answers=pairs, limits=s.Limits(seconds=0))
            self.assertEqual(result.status, 'BOUNDED_UNRESOLVED')
            self.assertLessEqual(result.lower, len(ref))
            self.assertIsNone(result.upper)

    def test_pin_mismatch_fails_closed(self):
        with patch.object(a, 'PIN', '0'*64):
            with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
                a.variant_module('full')
        with self.assertRaises(ValueError):
            a.variant_module('unregistered_variant')

    def test_no_canonical_interrupted_bounds_remain_outer(self):
        self.require_frozen_source()
        rows, _, usage, pairs = a.generate(2, 1823, 'mixed')
        master = a.exact.build_master(rows, 2, epsilon=0.1)
        valid = []
        for world in a.all_worlds(master, 4):
            try:
                valid.append(a.replay(rows, 2, 4, usage, pairs, world))
            except AssertionError:
                pass
        optimum = min(valid)
        for stop_at in (1, 3, 7):
            s = a.variant_module('no_canonical')
            original = s._fixed_span
            count = [0]
            def interrupt(*args, **kwargs):
                count[0] += 1
                if count[0] == stop_at:
                    raise s.BudgetStop('AUDIT_PREFIX_STOP')
                return original(*args, **kwargs)
            with patch.object(s, '_fixed_span', side_effect=interrupt):
                result = s.minimize(rows, 2, 4, event_cost=1, usage_answers=usage,
                                    pair_answers=pairs, limits=s.Limits(seconds=10))
            self.assertLessEqual(result.lower, optimum)
            if result.upper is not None:
                self.assertGreaterEqual(result.upper, optimum)

    def test_exact_intersection_detects_sub_float_contradiction(self):
        records = [dict(cell=[1], status='BOUNDED_UNRESOLVED', input_sha256='same',
                        lower_rational='1', upper_rational='1'),
                   dict(cell=[1], status='BOUNDED_UNRESOLVED', input_sha256='same',
                        lower_rational='100000000000000000001/100000000000000000000',
                        upper_rational=None)]
        with self.assertRaises(AssertionError):
            a.validate_intersections(records)

    def test_protocol_grid_counts(self):
        p = json.loads(a.PROTOCOL_PATH.read_text())
        endpoints = len(p['primary_core_counts'])*len(p['capacities'])*len(p['seed_regimes'])*len(p['event_costs'])
        self.assertEqual(endpoints, p['primary_unique_endpoint_count'])
        self.assertEqual(endpoints*len(p['variants'])*p['replicates'], p['primary_run_count'])
        self.assertEqual(p['stress_unique_endpoint_count']*p['replicates'], p['stress_run_count'])
        self.assertEqual(p['separator_sha256'], a.PIN)


if __name__ == '__main__':
    unittest.main()
