"""Independent explicit-oracle checks for the implicit disclosure separator."""
from fractions import Fraction
from pathlib import Path
import itertools
import math
import sys
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ordered_run_fixed_time_master as exact
import ordered_run_column_generation as cg
import ordered_run_branch_and_price as old
import ordered_run_disclosure_separator as new


def worlds(master, q):
    """Enumerate partitions independently; used only by tests."""
    def visit(core, buffer, events):
        if not core:
            if buffer.bit_count() == q:
                yield tuple(events)
            return
        bit = core & -core
        for c in master.columns:
            if (c.core_mask & bit and c.core_mask & core == c.core_mask
                    and not c.buffer_mask & buffer):
                yield from visit(core ^ c.core_mask, buffer | c.buffer_mask,
                                 events + [c.member_mask])
    yield from visit(master.all_core_mask, 0, [])


def filtered(world, usage, pairs):
    used = 0
    for mask in world:
        used |= mask
    return (all(int(bool(used & (1 << i))) == y for i, y in usage.items())
            and all(int(any(mask & (1 << i) and mask & (1 << j) for mask in world)) == y
                    for (i, j), y in pairs.items()))


class DisclosureSeparatorTests(unittest.TestCase):
    def test_random_endpoints_against_complete_world_oracle(self):
        for seed in range(8):
            rows = old._random_rows(seed)
            costs = {i: Fraction((3 * i + seed) % 7 - 3, 5) for i in range(len(rows))}
            for capacity in (2, 3):
                master = exact.build_master(rows, capacity, epsilon=0.1)
                for q in (2, 3):
                    for kappa in (-1, 1):
                        vals = [new._target_value(w, costs, kappa) for w in worlds(master, q)]
                        result = new.minimize(rows, capacity, q, costs, event_cost=kappa)
                        if not vals:
                            self.assertEqual(result.status, 'INFEASIBLE', (seed, capacity, q, result))
                        else:
                            optimum = min(vals)
                            self.assertIsNotNone(result.lower)
                            self.assertIsNotNone(result.upper)
                            self.assertLessEqual(result.lower, optimum)
                            self.assertGreaterEqual(result.upper, optimum)
                            self.assertLessEqual(result.upper - result.lower, Fraction(1, 10**7))

    def test_no_full_column_or_world_enumeration_in_solver(self):
        rows = [exact.FixedTimeRow(i, 'core' if i < 2 else 'buffer', 0, 2) for i in range(5)]
        with patch.object(exact, 'build_master', side_effect=AssertionError('forbidden enumeration')):
            result = new.minimize(rows, 3, 2, {2: 1, 3: 2, 4: 3}, event_cost=1)
        self.assertEqual(result.upper, 5)

    def test_positive_optional_pair_requires_both_members(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2) for i in range(4)]
        result = new.minimize(rows, 3, 2, {1: 7, 2: 6, 3: -20}, pair_answers={(1, 2): 1})
        self.assertEqual(result.upper, 13)
        self.assertEqual(result.witness, (7,))

    def test_negative_pair_allows_an_unused_endpoint(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2) for i in range(4)]
        result = new.minimize(rows, 3, 1, {1: 2, 2: 4, 3: 8}, pair_answers={(1, 2): 0})
        self.assertEqual(result.upper, 2)

    def test_usage_and_pair_answers_match_enumeration(self):
        rows = old._random_rows(7)
        for capacity in (2, 3):
            master = exact.build_master(rows, capacity, epsilon=0.1)
            for usage, pairs in [({3: 1}, {(0, 3): 1}), ({3: 0}, {(0, 4): 0}),
                                 ({4: 1}, {(0, 1): 0, (4, 5): 0})]:
                costs = {i: i - 3 for i in range(len(rows))}
                values = [new._target_value(w, costs, -1) for w in worlds(master, 2)
                          if filtered(w, usage, pairs)]
                res = new.minimize(rows, capacity, 2, costs, event_cost=-1,
                                   usage_answers=usage, pair_answers=pairs)
                if values:
                    self.assertLessEqual(res.lower, min(values)); self.assertEqual(res.upper, min(values))
                else:
                    self.assertEqual(res.status, 'INFEASIBLE')

    def test_fractional_master_actually_branches(self):
        rows = cg.integrality_gap_counterexample()
        result = new.minimize(rows, 2, 4)
        self.assertEqual(result.status, 'INFEASIBLE')
        self.assertGreater(result.counts['nodes'], 1)
        self.assertGreater(result.counts['buffer_branches'] + result.counts['pair_branches'], 0)

    def test_no_singleton_and_no_touching_events(self):
        rows = [exact.FixedTimeRow(0, 'core', 0, 1), exact.FixedTimeRow(1, 'buffer', 1, 2)]
        self.assertEqual(new.minimize(rows, 2, 1).status, 'INFEASIBLE')
        self.assertEqual(new.minimize(rows[:1], 2, 0).status, 'INFEASIBLE')

    def test_sequential_nonclique_event_is_allowed(self):
        rows = [exact.FixedTimeRow(0, 'core', 0, 2), exact.FixedTimeRow(1, 'buffer', 1, 3),
                exact.FixedTimeRow(2, 'buffer', 2, 4)]
        result = new.minimize(rows, 2, 2, event_cost=1)
        self.assertEqual(result.upper, 1)
        self.assertEqual(result.witness, (7,))

    def test_zero_budget_preserves_finite_valid_bound(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2) for i in range(3)]
        for limits in [new.Limits(nodes=0), new.Limits(seconds=0), new.Limits(iterations=0),
                       new.Limits(pricing_cases=0)]:
            result = new.minimize(rows, 2, 1, {1: 2, 2: 3}, limits=limits)
            self.assertEqual(result.status, 'BOUNDED_UNRESOLVED')
            self.assertLessEqual(result.lower, 2)
            self.assertIsNone(result.upper)

    def test_interrupted_popped_node_not_lost(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2+i) for i in range(3)]
        with patch.object(new, '_fixed_span', side_effect=new.BudgetStop('INJECTED_TIMEOUT')):
            result = new.minimize(rows, 2, 1, {1: -4, 2: 3})
        self.assertEqual(result.status, 'BOUNDED_UNRESOLVED')
        self.assertEqual(result.lower, -4)
        self.assertEqual(result.reason, 'INJECTED_TIMEOUT')

    def test_exact_threshold_tie_is_positive(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2) for i in range(3)]
        # Reference 0.5 is positive; another feasible world is genuinely below.
        result = new.separate(rows, 2, 1, {1: Fraction(1, 2), 2: Fraction(1, 2)-Fraction(1, 10**10)},
                              Fraction(1, 2), (3,))
        self.assertNotEqual(result['status'], 'NO_OPPOSITE_WORLD')
        # A tied world is an opposite world for a strictly negative reference.
        result = new.separate(rows, 2, 1, {1: 0, 2: Fraction(1, 2)}, Fraction(1, 2), (3,))
        self.assertEqual(result['status'], 'OPPOSITE_WORLD')
        self.assertEqual(result['opposite_events'], (5,))

    def test_mip_incumbent_is_not_an_absence_proof(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2) for i in range(3)]
        fake = new.Endpoint('BOUNDED_UNRESOLVED', Fraction(49, 100), Fraction(51, 100), (3,), {}, 0)
        with patch.object(new, 'minimize', return_value=fake):
            result = new.separate(rows, 2, 1, {1: Fraction(51,100), 2: Fraction(49,100)},
                                  Fraction(1,2), (3,))
        self.assertEqual(result['status'], 'UNRESOLVED')

    def test_empty_or_inconsistent_reference_rejected(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2) for i in range(3)]
        for witness in [(), (1,), (3, 5)]:
            with self.assertRaises(ValueError):
                new.separate(rows, 2, 1, {1: 1, 2: 2}, 1, witness)
        with self.assertRaises(ValueError):
            new.minimize(rows, 3, 1, usage_answers={1: 0}, pair_answers={(0,1): 1})

    def test_pair_closure_and_contradiction(self):
        rows = [exact.FixedTimeRow(i, 'core' if i < 2 else 'buffer', 0, 2) for i in range(4)]
        result = new.minimize(rows, 4, 2, pair_answers={(0,2): 1, (2,3): 1, (0,3): 0})
        self.assertEqual(result.status, 'INFEASIBLE')

    def test_rational_dual_repair_bounds_every_box_feasible_point(self):
        a = np.array([[1, 1], [-1, 0]], dtype=float); b = np.array([1, 0], dtype=float)
        w = [Fraction(1, 3), Fraction(-1, 7)]
        for multipliers in [(0, 0), (1, -5), (0.3333333, 0), (1e-12, 2)]:
            bound = new._box_dual_upper(a, b, [0, 0], [1, 1], w, multipliers)
            self.assertGreaterEqual(bound, Fraction(1, 3))

    def test_invalid_arguments_fail_closed(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2) for i in range(3)]
        for arguments in [dict(row_costs={3: 1}), dict(row_costs={1: float('nan')}),
                          dict(pair_answers={(0, 8): 1}), dict(usage_answers={0: 1})]:
            with self.assertRaises(ValueError):
                new.minimize(rows, 2, 1, **arguments)
        for limits in [dict(seconds=-1), dict(nodes=-1), dict(iterations=1.5)]:
            with self.assertRaises(ValueError):
                new.Limits(**limits)

    def test_summary_redacts_witnesses_and_rounds_outwards(self):
        endpoint = new.Endpoint('EXACT_BOUND_CLOSED', Fraction(1,3), Fraction(1,3), (3,), {}, 0)
        summary = endpoint.summary()
        self.assertNotIn('witness', summary)
        self.assertLessEqual(Fraction(summary['lower_bound']), Fraction(1,3))
        self.assertGreaterEqual(Fraction(summary['upper_bound']), Fraction(1,3))

    def test_exact_hitting_set_matches_subset_enumeration(self):
        import random, time
        for seed in range(12):
            rng = random.Random(seed)
            cuts = [frozenset(rng.sample(range(6), rng.randrange(1, 7))) for _ in range(8)]
            expected = next(k for k in range(7) if any(all(set(s) & c for c in cuts)
                            for s in itertools.combinations(range(6), k)))
            chosen = new._exact_hitting_set(cuts, time.perf_counter()+5)
            self.assertEqual(len(chosen), expected)

    def test_end_to_end_usage_certificate(self):
        rows = [exact.FixedTimeRow(i, 'core' if i == 0 else 'buffer', 0, 2) for i in range(3)]
        result = new.minimum_certificate(rows, 2, 1, {1: 0, 2: 2}, 1, (3,), usage_atoms=(1,2))
        self.assertEqual(result['status'], 'MINIMUM_CERTIFICATE_CERTIFIED')
        self.assertEqual(result['certificate_size'], 1)

    def test_end_to_end_pair_certificate(self):
        rows = [exact.FixedTimeRow(i, 'core', 0, 2) for i in range(4)]
        result = new.minimum_certificate(rows, 4, 0, {}, Fraction(3,2), (3,12), event_cost=1,
                                         pair_atoms=tuple(itertools.combinations(range(4),2)))
        self.assertEqual(result['status'], 'MINIMUM_CERTIFICATE_CERTIFIED')
        self.assertEqual(result['certificate_size'], 1)

    def test_insufficient_interface_does_not_fabricate_certificate(self):
        rows = [exact.FixedTimeRow(i, 'core', 0, 2) for i in range(4)]
        result = new.minimum_certificate(rows, 4, 0, {}, Fraction(3,2), (3,12), event_cost=1)
        self.assertEqual(result['status'], 'UNIDENTIFIABLE_WITH_ALLOWED_ATOMS')
        self.assertIsNone(result['certificate_size'])

if __name__ == '__main__':
    unittest.main()
