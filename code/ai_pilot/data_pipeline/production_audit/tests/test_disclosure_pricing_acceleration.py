"""Adversarial checks for accelerated canonical-root pricing and anytime bounds."""
from fractions import Fraction
from pathlib import Path
import itertools
import random
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ordered_run_disclosure_separator as s
import ordered_run_branch_and_price as bp
import ordered_run_column_generation as cg
import ordered_run_fixed_time_master as exact
from test_ordered_run_disclosure_separator import worlds, filtered


def context(rows, capacity, q, costs=None, event_cost=1, **limits):
    model = cg.layout(rows)
    return s.Context(model, capacity, q,
                     tuple(s.rational((costs or {}).get(i, 0)) for i in range(len(rows))),
                     s.rational(event_cost), s.Limits(**limits), time.perf_counter()+30)


class PricingAccelerationTests(unittest.TestCase):
    def test_sparse_dual_evaluation_equals_dense_exact_expression(self):
        for seed in range(32):
            rng = random.Random(seed)
            a = np.array([[rng.choice([-1, 0, 0, 1]) for _ in range(6)] for _ in range(5)])
            b = np.array([rng.randrange(-2, 4) for _ in range(5)])
            w = [Fraction(rng.randrange(-5, 6), 7) for _ in range(6)]
            lo = [rng.randrange(2) for _ in range(6)]
            hi = [1]*6
            mu = [rng.choice([0, 0, -0.7, 0.25, 1.3]) for _ in range(5)]
            lam = [max(Fraction(0), s._dual(x)) for x in mu]
            expected = sum((int(x)*y for x,y in zip(b,lam)), Fraction(0))
            for j in range(6):
                r = w[j]-sum((int(a[k,j])*lam[k] for k in range(5)), Fraction(0))
                expected += max(lo[j]*r, hi[j]*r)
            self.assertEqual(s._box_dual_upper(a,b,lo,hi,w,mu), expected)

    def test_objective_lattice_tightening_is_exact(self):
        rows = [exact.FixedTimeRow(i,'core' if i==0 else 'buffer',0,3) for i in range(3)]
        ctx = context(rows,2,1,{1:Fraction(1,3),2:Fraction(1,2)},event_cost=Fraction(1,6))
        self.assertEqual(ctx.objective_step,Fraction(1,6))
        self.assertEqual(ctx.lattice_lower(Fraction(49,100)),Fraction(1,2))
        self.assertEqual(ctx.lattice_lower(Fraction(-49,100)),Fraction(-1,3))
        tiny = context(rows,2,1,{1:Fraction(1,2),2:Fraction(1,2)-Fraction(1,10**10)},event_cost=0)
        x=Fraction(1,2)-Fraction(1,10**10)
        self.assertEqual(tiny.lattice_lower(x),x)

    def test_duration_bound_does_not_confuse_members_with_capacity(self):
        rows=[exact.FixedTimeRow(0,'core',0,2),exact.FixedTimeRow(1,'buffer',1,3),
              exact.FixedTimeRow(2,'buffer',2,4)]
        ctx=context(rows,2,2)
        self.assertEqual(s._initial_lower(ctx,s._node(ctx.model,{},{})),1)
        r=s.minimize(rows,2,2,event_cost=1)
        self.assertEqual((r.lower,r.upper),(1,1))

    def test_initial_bounds_valid_with_signed_costs_and_mandatory_buffers(self):
        for seed in range(10,18):
            rows=bp._random_rows(seed)
            costs={i:Fraction((5*i+seed)%11-5,7) for i in range(len(rows))}
            for capacity,q,kappa in itertools.product((2,3),(2,3),(-1,1)):
                master=exact.build_master(rows,capacity,epsilon=0.1)
                all_worlds=list(worlds(master,q))
                for usage in ({},{3:1},{3:0}):
                    vals=[s._target_value(w,costs,kappa) for w in all_worlds if filtered(w,usage,{})]
                    if not vals:continue
                    ctx=context(rows,capacity,q,costs,kappa)
                    self.assertLessEqual(s._initial_lower(ctx,s._node(ctx.model,usage,{})),min(vals))

    def test_batch_and_complete_pricing_agree(self):
        rows=bp._random_rows(7)
        for c,q in itertools.product((2,3),(2,3)):
            a=s.minimize(rows,c,q,{i:i-3 for i in range(len(rows))},event_cost=1,
                         limits=s.Limits(pricing_batch=1))
            b=s.minimize(rows,c,q,{i:i-3 for i in range(len(rows))},event_cost=1,
                         limits=s.Limits(pricing_batch=0))
            self.assertEqual(a.status,b.status)
            self.assertEqual(a.upper,b.upper)
            self.assertEqual(a.lower,b.lower)

    def test_interruption_retains_early_primal_world(self):
        rows=[exact.FixedTimeRow(i,'core' if i==0 else 'buffer',0,2+i) for i in range(3)]
        with patch.object(s,'_price',side_effect=s.BudgetStop('INJECTED_AFTER_PRIMAL')):
            r=s.minimize(rows,2,1,{1:2,2:3})
        self.assertEqual(r.status,'BOUNDED_UNRESOLVED')
        self.assertEqual(r.reason,'INJECTED_AFTER_PRIMAL')
        self.assertEqual(r.upper,2)
        self.assertTrue(r.witness)
        self.assertLessEqual(r.lower,2)

    def test_interrupted_pricing_prefixes_never_overstate_lower_bound(self):
        for seed in (6,7,8):
            rows=bp._random_rows(seed)
            master=exact.build_master(rows,2,epsilon=0.1)
            costs={i:Fraction(i-3,5) for i in range(len(rows))}
            vals=[s._target_value(w,costs,1) for w in worlds(master,3)]
            if not vals:continue
            optimum=min(vals)
            original=s._fixed_span
            for stop_at in (1,3,7,13):
                calls=[0]
                def stop(*args,**kwargs):
                    calls[0]+=1
                    if calls[0]==stop_at:raise s.BudgetStop('PREFIX_STOP')
                    return original(*args,**kwargs)
                with patch.object(s,'_fixed_span',side_effect=stop):
                    r=s.minimize(rows,2,3,costs,event_cost=1)
                self.assertLessEqual(r.lower,optimum)
                if r.upper is not None:self.assertGreaterEqual(r.upper,optimum)

    def test_cached_infeasibility_is_independent_of_objective(self):
        rows=[exact.FixedTimeRow(i,'core',0,3) for i in range(3)]
        ctx=context(rows,2,0)
        intervals=cg.compress_endpoints(rows)
        for weights in ([Fraction(1)]*3,[Fraction(-3),Fraction(4),Fraction(7)]):
            self.assertEqual(s._fixed_span(ctx,intervals,weights,(0,1),frozenset(range(3)),frozenset()),(None,None))
        self.assertEqual(ctx.counts['pricing_lp_calls'],0)
        self.assertEqual(ctx.counts['pricing_infeasible_cache_hits'],1)

    def test_canonical_root_bounds_dominate_no_feasible_world(self):
        for seed in (3,5,7):
            rows=bp._random_rows(seed)
            master=exact.build_master(rows,2,epsilon=0.1)
            costs={i:Fraction((i+seed)%5-2,3) for i in range(len(rows))}
            vals=[s._target_value(w,costs,1) for w in worlds(master,2)]
            if not vals:continue
            ctx=context(rows,2,2,costs,1,pricing_batch=0)
            node=s._node(ctx.model,{},{})
            mandatory,free,_=bp._row_classes(ctx.model,node)
            eq=[Fraction((i+1)%3-1,2) for i in range(len(mandatory)+1)]
            ub=[Fraction(-1,3)]*len(free)
            lower,_=s._price(ctx,node,eq,ub,mandatory,free,False)
            self.assertLessEqual(lower,min(vals))
            self.assertLessEqual(ctx.node_lower,min(vals))

    def test_zero_budget_32_row_geometry_bound_without_optimization(self):
        rows=[exact.FixedTimeRow(i,'core',3*i,3*i+4) for i in range(8)]
        for offset in (1,4,2):
            for i in range(8):rows.append(exact.FixedTimeRow(len(rows),'buffer',3*i+offset,3*i+offset+4))
        r=s.minimize(rows,2,16,event_cost=1,limits=s.Limits(seconds=0))
        self.assertEqual(r.lower,2)
        self.assertIsNone(r.upper)
        self.assertEqual(r.counts['pricing_lp_calls'],0)
        self.assertEqual(r.status,'BOUNDED_UNRESOLVED')

    def test_interleaved_core_positions_and_pair_facts(self):
        rows=[exact.FixedTimeRow(i,'core' if i%2==0 else 'buffer',i,i+4) for i in range(6)]
        master=exact.build_master(rows,3,epsilon=0.1)
        costs={i:2-i for i in range(6)}
        for pairs in ({(0,3):1},{(0,2):0},{(2,3):1,(0,4):0}):
            vals=[s._target_value(w,costs,1) for w in worlds(master,2) if filtered(w,{},pairs)]
            r=s.minimize(rows,3,2,costs,event_cost=1,pair_answers=pairs)
            if vals:
                self.assertEqual(r.upper,min(vals));self.assertLessEqual(r.lower,min(vals))
            else:self.assertEqual(r.status,'INFEASIBLE')

    def test_invalid_batch_size_rejected(self):
        for batch in (-1,1.5):
            with self.assertRaises(ValueError):s.Limits(pricing_batch=batch)


if __name__=='__main__':unittest.main()
