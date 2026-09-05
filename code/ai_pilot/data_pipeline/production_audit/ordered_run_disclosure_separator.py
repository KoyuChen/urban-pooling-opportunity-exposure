#!/usr/bin/env python3
"""Implicit fixed-support branch-and-price for truthful relation disclosures.

Minimize sum_i w_i u_i + kappa * number_of_events, with core usage one,
optional usage at most one, and sum_buffer u_i = q. Each event has at least
two rows, contains a core, is positive-overlap connected, and respects capacity.

Only pair seeds and priced columns are constructed; this module never calls
build_master or enumerates all subsets, events, or complete worlds. It reuses
Ryan--Foster case propagation and the interval incidence functions. Pair=1
also makes both endpoints mandatory (columnwise together alone is not enough).

Floating-point LPs propose primal solutions and dual multipliers. Integer
witnesses are replayed combinatorially. Bounds are evaluated with Fraction on
the supplied binary-float data, with residual correction rather than trusting
an LP/MIP success flag or rounding a bound across a decision threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import heapq
import itertools
import math
import time
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

import ordered_run_branch_and_price as bp
import ordered_run_column_generation as cg
from ordered_run_fixed_time_master import FixedTimeRow
from ordered_run_interval_oracle import covers_segment, bridges_boundary, allowed_in_span

Number = int | float | Fraction


def rational(value: Number) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if not math.isfinite(float(value)):
        raise ValueError("all numbers must be finite")
    return Fraction(value)


def _dual(value: float) -> Fraction:
    # A dual multiplier need not be the solver's exact multiplier. Rational
    # compression is safe because every reduced-cost residual is repaired.
    if not math.isfinite(float(value)):
        raise ValueError("nonfinite dual multiplier")
    return Fraction(float(value)).limit_denominator(10**8)


def _outward(value: Fraction | None, *, lower: bool) -> float | None:
    if value is None:
        return None
    result = float(value)
    if (lower and Fraction(result) > value) or (not lower and Fraction(result) < value):
        result = math.nextafter(result, -math.inf if lower else math.inf)
    return result


@dataclass(frozen=True)
class Limits:
    seconds: float = 60.0
    nodes: int = 1000
    iterations: int = 100
    pricing_cases: int = 4096
    gap_tolerance: float = 1e-8

    def __post_init__(self) -> None:
        if (not math.isfinite(self.seconds) or self.seconds < 0
                or any(not isinstance(x, int) or x < 0
                       for x in (self.nodes, self.iterations, self.pricing_cases))
                or not math.isfinite(self.gap_tolerance) or self.gap_tolerance < 0):
            raise ValueError("limits must be finite and nonnegative; counts must be integers")


class BudgetStop(RuntimeError):
    pass


@dataclass
class Context:
    model: Any
    capacity: int
    q: int
    costs: tuple[Fraction, ...]
    event_cost: Fraction
    limits: Limits
    deadline: float
    counts: dict[str, int] = field(default_factory=lambda: {
        "nodes": 0, "pricing_lp_calls": 0, "farkas_lp_calls": 0,
        "master_lp_calls": 0, "integer_heuristic_calls": 0,
        "buffer_branches": 0, "pair_branches": 0,
        "pricing_cases": 0, "unique_generated_columns": 0,
    })
    pool: dict[int, Any] = field(default_factory=dict)
    span_cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)

    def remaining(self) -> float:
        seconds = self.deadline - time.perf_counter()
        if seconds <= 0:
            raise BudgetStop("TIME_LIMIT")
        return seconds

    def column_cost(self, mask: int) -> Fraction:
        return self.event_cost + sum((w for i, w in enumerate(self.costs)
                                      if mask & (1 << i)), Fraction(0))


@dataclass
class Endpoint:
    status: str
    lower: Fraction | None
    upper: Fraction | None
    witness: tuple[int, ...]
    counts: dict[str, int]
    seconds: float
    reason: str | None = None

    def summary(self) -> dict[str, Any]:
        # Deliberately omit relation witnesses from serializable evidence.
        return {
            "status": self.status,
            "lower_bound": _outward(self.lower, lower=True),
            "upper_bound": _outward(self.upper, lower=False),
            "absolute_gap": (None if self.lower is None or self.upper is None
                             else float(self.upper - self.lower)),
            "reason": self.reason, "seconds": self.seconds, **self.counts,
            "all_event_columns_enumerated": False,
            "all_worlds_enumerated": False,
            "bound_arithmetic": "rational residual-repaired dual bounds",
        }


def _node(model: Any, usage: Mapping[int, int], pairs: Mapping[tuple[int, int], int]) -> Any:
    n = len(model.rows)
    for i, answer in usage.items():
        if i not in model.buffer_positions or answer not in (0, 1):
            raise ValueError("usage keys must be sorted-row buffer positions; answers must be 0/1")
    statuses = dict(usage)
    together, separate = set(), set()
    for pair, answer in pairs.items():
        if len(pair) != 2 or any(not isinstance(i, int) or not 0 <= i < n for i in pair):
            raise ValueError("invalid pair positions")
        p = bp._pair(*pair)
        if answer not in (0, 1):
            raise ValueError("pair answers must be 0/1")
        if answer:
            together.add(p)
            for i in p:
                if i in model.buffer_positions:
                    if statuses.get(i) == 0:
                        raise ValueError("positive pair answer contradicts excluded endpoint")
                    statuses[i] = 1
        else:
            separate.add(p)
    if together & separate:
        raise ValueError("contradictory answers to reversed pair")
    return bp._canonical_node(buffer_status=statuses, together_pairs=together,
                              separate_pairs=separate)


def _valid_column(ctx: Context, mask: int, node: Any) -> bool:
    n = len(ctx.model.rows)
    if not isinstance(mask, int) or mask <= 0 or mask >> n:
        return False
    col = cg.RunColumn(mask, mask & ctx.model.all_core_mask, mask & ctx.model.all_buffer_mask)
    if mask.bit_count() < 2 or not col.core_mask or not bp._column_allowed(col, node):
        return False
    selected = [ctx.model.rows[i] for i in range(n) if mask & (1 << i)]
    ordered = sorted(selected, key=lambda r: (r.start, r.end))
    end = ordered[0].end
    for row in ordered[1:]:
        if row.start >= end:  # touching is not positive overlap
            return False
        end = max(end, row.end)
    for t in {row.start for row in selected}:
        if sum(row.start <= t < row.end for row in selected) > ctx.capacity:
            return False
    return True


def replay(ctx: Context, events: Sequence[int], node: Any) -> Fraction:
    used = 0
    for mask in events:
        if not _valid_column(ctx, mask, node) or used & mask:
            raise ValueError("invalid, repeated, disconnected, or disclosure-inconsistent event")
        used |= mask
    if used & ctx.model.all_core_mask != ctx.model.all_core_mask:
        raise ValueError("witness omits a core")
    if (used & ctx.model.all_buffer_mask).bit_count() != ctx.q:
        raise ValueError("witness violates fixed support")
    for i, value in node.buffer_status:
        if int(bool(used & (1 << i))) != value:
            raise ValueError("witness violates mandatory/excluded usage")
    return sum((ctx.column_cost(mask) for mask in events), Fraction(0))


def _matrices(ctx: Context, columns: Sequence[Any], node: Any):
    mandatory, free, _ = bp._row_classes(ctx.model, node)
    aeq = np.zeros((len(mandatory) + 1, len(columns)))
    for j, col in enumerate(columns):
        for k, i in enumerate(mandatory):
            aeq[k, j] = bool(col.member_mask & (1 << i))
        aeq[-1, j] = col.buffer_count
    beq = np.asarray([1] * len(mandatory) + [ctx.q], dtype=float)
    aub = np.asarray([[bool(c.member_mask & (1 << i)) for c in columns]
                      for i in free], dtype=float).reshape((len(free), len(columns)))
    return aeq, beq, aub, np.ones(len(free)), mandatory, free


def _span_matrix(ctx: Context, intervals: Sequence[Any], span: tuple[int, int]):
    if span not in ctx.span_cache:
        a, b = span
        rows, rhs = [], []
        for k in range(a, b):
            row = np.array([int(covers_segment(t, k)) for t in intervals], dtype=float)
            rows.extend([row, -row]); rhs.extend([ctx.capacity, -1])
        for k in range(a + 1, b):
            rows.append(-np.array([int(bridges_boundary(t, k)) for t in intervals], dtype=float))
            rhs.append(-1)
        ctx.span_cache[span] = np.asarray(rows), np.asarray(rhs, dtype=float)
    return ctx.span_cache[span]


def _box_dual_upper(a: np.ndarray, b: np.ndarray, lower: Sequence[int],
                   upper: Sequence[int], weights: Sequence[Fraction],
                   multipliers: Sequence[float]) -> Fraction:
    """Rigorous Lagrangian upper bound on max w*x, A*x<=b, l<=x<=u.

    Multipliers can be arbitrary. Project onto nonnegative values and repair
    every coefficient residual using the finite variable bounds.
    """
    lam = [max(Fraction(0), _dual(v)) for v in multipliers]
    bound = sum((int(rhs) * v for rhs, v in zip(b, lam)), Fraction(0))
    for j, w in enumerate(weights):
        residual = w - sum((int(a[k, j]) * v for k, v in enumerate(lam) if a[k, j]), Fraction(0))
        bound += max(lower[j] * residual, upper[j] * residual)
    return bound


def _fixed_span(ctx: Context, intervals: Sequence[Any], weights: Sequence[Fraction],
                span: tuple[int, int], forced_in: frozenset[int], forced_out: frozenset[int]):
    if forced_in & forced_out or any(not allowed_in_span(intervals[i], span) for i in forced_in):
        return None, None
    n = len(intervals)
    lower = [int(i in forced_in) for i in range(n)]
    upper = [int(i not in forced_out and allowed_in_span(intervals[i], span)) for i in range(n)]
    if any(lo > hi for lo, hi in zip(lower, upper)):
        return None, None
    a, b = _span_matrix(ctx, intervals, span)
    # Exact infeasibility precheck: a row cannot meet its RHS even at its
    # most favorable box point.
    for row, rhs in zip(a, b):
        if sum(int(x) * (lower[i] if x >= 0 else upper[i]) for i, x in enumerate(row)) > rhs:
            return None, None
    ctx.counts["pricing_lp_calls"] += 1
    res = linprog(-np.asarray([float(w) for w in weights]), A_ub=a, b_ub=b,
                  bounds=list(zip(lower, upper)), method="highs",
                  options={"time_limit": ctx.remaining()})
    if res.status == 2:
        # Do not trust an infeasible status alone. Seek an exact-rational
        # Farkas-style certificate from an always-feasible slack relaxation.
        ctx.counts["farkas_lp_calls"] += 1
        m = len(b)
        phase = linprog(np.r_[np.zeros(n), np.ones(m)],
                        A_ub=np.c_[a, -np.eye(m)], b_ub=b,
                        bounds=list(zip(lower, upper)) + [(0, None)] * m,
                        method="highs", options={"time_limit": ctx.remaining()})
        if phase.success:
            bound = _box_dual_upper(a, b, lower, upper, [Fraction(0)] * n,
                                    -np.asarray(phase.ineqlin.marginals))
            if bound < 0:
                return None, None  # feasible point would imply 0 < 0
        raise BudgetStop("PRICING_INFEASIBILITY_NOT_CERTIFIED")
    if not res.success or res.x is None:
        raise BudgetStop("PRICING_LP_UNRESOLVED")
    bound = _box_dual_upper(a, b, lower, upper, weights, -np.asarray(res.ineqlin.marginals))
    rounded = np.rint(res.x).astype(int)
    if (max(abs(res.x - rounded), default=0) > 1e-7
            or np.any(rounded < lower) or np.any(rounded > upper)
            or np.any(a @ rounded > b)):
        raise BudgetStop("PRICING_INTEGER_REPLAY_FAILED")
    mask = sum(1 << i for i, value in enumerate(rounded) if value)
    return mask, bound


def _price(ctx: Context, node: Any, eq_duals: Sequence[Fraction],
           ub_duals: Sequence[Fraction], mandatory: Sequence[int], free: Sequence[int],
           phase_one: bool):
    duals = {i: d for i, d in zip(mandatory, eq_duals[:-1])}
    duals.update(zip(free, ub_duals))
    sigma = eq_duals[-1]
    weights = [duals.get(i, Fraction(0)) + (sigma if i in ctx.model.buffer_positions else 0)
               - (0 if phase_one else ctx.costs[i]) for i in range(len(ctx.model.rows))]
    offset = Fraction(0) if phase_one else ctx.event_cost
    intervals = cg.compress_endpoints(ctx.model.rows)
    excluded = {i for i, y in node.buffer_status if y == 0}
    min_rc = None
    improved = []
    for root in ctx.model.core_positions:
        ctx.remaining()
        try:
            cases = bp.enumerate_pricing_cases(len(intervals), root, node, excluded,
                                               max_cases=ctx.limits.pricing_cases)
        except RuntimeError as error:
            raise BudgetStop(str(error)) from error
        ctx.counts["pricing_cases"] += len(cases)
        for forced_in, forced_out in cases:
            earliest = min(intervals[i].start for i in forced_in)
            latest = max(intervals[i].end for i in forced_in)
            starts = sorted({t.start for i, t in enumerate(intervals)
                             if i not in forced_out and t.start <= earliest})
            ends = sorted({t.end for i, t in enumerate(intervals)
                           if i not in forced_out and t.end >= latest})
            for start in starts:
                for end in ends:
                    if start >= end:
                        continue
                    span = (start, end)
                    mask, bound = _fixed_span(ctx, intervals, weights, span, forced_in, forced_out)
                    if mask is None:
                        continue
                    if mask.bit_count() >= 2:
                        candidates = [(mask, bound)]
                    else:
                        candidates = []
                        # Exclude singleton solutions by a union of forced-
                        # companion LPs; a cardinality inequality would break
                        # the inherited consecutive-ones proof.
                        for companion, interval in enumerate(intervals):
                            if (companion in forced_in or companion in forced_out
                                    or not allowed_in_span(interval, span)):
                                continue
                            propagated = bp._propagate_case(set(forced_in) | {companion},
                                                            set(forced_out), node.together_pairs,
                                                            node.separate_pairs)
                            if propagated is None:
                                continue
                            fi, fo = map(frozenset, propagated)
                            candidate, upper = _fixed_span(ctx, intervals, weights, span, fi, fo)
                            if candidate is not None:
                                candidates.append((candidate, upper))
                    for candidate, upper in candidates:
                        rc_lower = offset - upper
                        min_rc = rc_lower if min_rc is None else min(min_rc, rc_lower)
                        if not _valid_column(ctx, candidate, node):
                            raise BudgetStop("PRICED_COLUMN_REPLAY_FAILED")
                        value = sum((weights[i] for i in range(len(weights))
                                     if candidate & (1 << i)), Fraction(0))
                        if offset - value < 0 and candidate not in ctx.pool:
                            col = cg.RunColumn(candidate, candidate & ctx.model.all_core_mask,
                                               candidate & ctx.model.all_buffer_mask)
                            ctx.pool[candidate] = col
                            improved.append(col)
    ctx.counts["unique_generated_columns"] = len(ctx.pool)
    return min_rc, improved


def _node_lp(ctx: Context, node: Any):
    if bp._node_contradiction(ctx.model, node) is not None:
        return "INFEASIBLE", None, None, None
    statuses = node.status_map()
    if sum(y for y in statuses.values()) > ctx.q or sum(y == 0 for y in statuses.values()) > len(ctx.model.buffer_positions) - ctx.q:
        return "INFEASIBLE", None, None, None
    for phase_one in (True, False):
        for _ in range(ctx.limits.iterations):
            cols = bp._filter_columns(ctx.pool.values(), node)
            ae, be, au, bu, mandatory, free = _matrices(ctx, cols, node)
            m = len(be)
            if phase_one:
                eq = np.c_[ae, np.eye(m), -np.eye(m)]
                ub = np.c_[au, np.zeros((len(bu), 2 * m))]
                costs = np.r_[np.zeros(len(cols)), np.ones(2 * m)]
            else:
                eq, ub = ae, au
                costs = np.array([float(ctx.column_cost(c.member_mask)) for c in cols])
                if not len(costs):
                    return "INFEASIBLE", None, None, None
            ctx.counts["master_lp_calls"] += 1
            res = linprog(costs, A_eq=eq, b_eq=be,
                          A_ub=ub if len(bu) else None, b_ub=bu if len(bu) else None,
                          bounds=(0, None), method="highs", options={"time_limit": ctx.remaining()})
            if not res.success or res.x is None:
                raise BudgetStop("RESTRICTED_MASTER_UNRESOLVED")
            pi = [_dual(x) for x in res.eqlin.marginals]
            nu = [min(Fraction(0), _dual(x)) for x in res.ineqlin.marginals]
            rc, new = _price(ctx, node, pi, nu, mandatory, free, phase_one)
            dual = sum((int(b) * d for b, d in zip(be, pi)), Fraction(0)) + sum(nu, Fraction(0))
            # Every physical column covers at least one core, hence any
            # feasible original (non-artificial) master has sum x <= n_core.
            lower = dual + len(ctx.model.core_positions) * min(Fraction(0), rc or Fraction(0))
            if new:
                continue
            if phase_one:
                if lower > 0:
                    return "INFEASIBLE", None, None, None
                if sum(res.x[len(cols):]) > 1e-7:
                    raise BudgetStop("PHASE_ONE_UNRESOLVED")
                break
            return "LP_BOUNDED", lower, cols, tuple(res.x)
        else:
            raise BudgetStop("COLUMN_GENERATION_ITERATION_LIMIT")
    raise AssertionError("missing phase-two result")


def _heuristic(ctx: Context, node: Any, cols: Sequence[Any]):
    if not cols:
        return None, None
    ae, be, au, bu, _, _ = _matrices(ctx, cols, node)
    ctx.counts["integer_heuristic_calls"] += 1
    res = milp(np.array([float(ctx.column_cost(c.member_mask)) for c in cols]),
               integrality=np.ones(len(cols)), bounds=Bounds(0, 1),
               constraints=LinearConstraint(np.r_[ae, au], np.r_[be, np.zeros(len(bu))], np.r_[be, bu]),
               options={"time_limit": min(2.0, ctx.remaining()), "mip_rel_gap": 0.0})
    if res.x is None or np.any(~np.isfinite(res.x)) or max(abs(res.x - np.rint(res.x)), default=0) > 1e-7:
        return None, None
    events = tuple(c.member_mask for c, x in zip(cols, res.x) if round(x) == 1)
    try:
        return replay(ctx, events, node), events
    except ValueError:
        return None, None


def _clique_seed(ctx: Context, node: Any) -> tuple[int, ...]:
    """Deterministic feasible packing for the identical-interval special case.

    This is a warm start only. Closure still requires the repaired full-master
    bound. It is disabled with pair facts and does not use the reference world.
    """
    if (node.together_pairs or node.separate_pairs
            or len({(r.start, r.end) for r in ctx.model.rows}) != 1):
        return ()
    status = node.status_map()
    required = [i for i, y in status.items() if y == 1]
    free = sorted((i for i in ctx.model.buffer_positions if i not in status),
                  key=lambda i: (ctx.costs[i], i))
    if len(required) > ctx.q or len(required) + len(free) < ctx.q:
        return ()
    buffers = required + free[:ctx.q-len(required)]
    cores = list(ctx.model.core_positions)
    n = len(cores) + len(buffers)
    smallest = (n + ctx.capacity - 1) // ctx.capacity
    largest = min(len(cores), n // 2)
    if smallest > largest:
        return ()
    k = smallest if ctx.event_cost >= 0 else largest
    groups = [[i] for i in cores[:k]]
    rest = cores[k:] + buffers
    # Give every event a second member before filling remaining capacity.
    for group in groups:
        group.append(rest.pop(0))
    for group in groups:
        while rest and len(group) < ctx.capacity:
            group.append(rest.pop(0))
    if rest:
        raise AssertionError('clique warm start overfilled capacity')
    events = tuple(sum(1 << i for i in group) for group in groups)
    replay(ctx, events, node)
    return events


def minimize(rows: Sequence[FixedTimeRow], capacity: int, support_count: int,
             row_costs: Mapping[int, Number] | None = None, *, event_cost: Number = 0,
             usage_answers: Mapping[int, int] | None = None,
             pair_answers: Mapping[tuple[int, int], int] | None = None,
             initial_events: Sequence[int] = (), limits: Limits = Limits()) -> Endpoint:
    """Minimize a linear row/event target. Fact keys are sorted-row positions.

    Returned witness masks stay in memory; summary() redacts them. Initial
    events are optional warm columns, not assumed to form a feasible world.
    A popped but interrupted node retains its inherited lower bound.
    """
    started = time.perf_counter()
    model = cg.layout(rows)
    if not isinstance(capacity, int) or capacity < 2:
        raise ValueError("capacity must be an integer >= 2")
    if not isinstance(support_count, int) or not 0 <= support_count <= len(model.buffer_positions):
        raise ValueError("support_count must be a feasible-range integer")
    if any(not math.isfinite(float(t)) for r in model.rows for t in (r.start, r.end)):
        raise ValueError("timestamps must be finite")
    row_costs = dict(row_costs or {})
    if any(not isinstance(i, int) or not 0 <= i < len(model.rows) for i in row_costs):
        raise ValueError("row_cost keys must be sorted-row positions")
    costs = tuple(rational(row_costs.get(i, 0)) for i in range(len(model.rows)))
    ctx = Context(model, capacity, support_count, costs, rational(event_cost), limits, started + limits.seconds)
    root = _node(model, usage_answers or {}, pair_answers or {})
    for col in cg.seed_pair_columns(model, cg.compress_endpoints(model.rows), capacity):
        if bp._column_allowed(col, root):
            ctx.pool[col.member_mask] = col
    for mask in initial_events:
        if not _valid_column(ctx, mask, root):
            raise ValueError("invalid warm-start column")
        ctx.pool[mask] = cg.RunColumn(mask, mask & model.all_core_mask, mask & model.all_buffer_mask)
    # Unconditional, exact lower bound before any optimization succeeds.
    trivial = sum((costs[i] for i in model.core_positions), Fraction(0))
    trivial += sum(sorted(costs[i] for i in model.buffer_positions)[:support_count], Fraction(0))
    trivial += ctx.event_cost * (1 if ctx.event_cost >= 0 else len(model.core_positions))
    queue = [(trivial, 0, root)]
    serial = 0
    incumbent, witness = None, ()
    closed_lowers = []
    interrupted = None
    reason = None
    if limits.nodes and limits.iterations and limits.pricing_cases and limits.seconds:
        clique = _clique_seed(ctx, root)
        if clique:
            incumbent, witness = replay(ctx, clique, root), clique
            for mask in clique:
                ctx.pool[mask] = cg.RunColumn(mask, mask & model.all_core_mask, mask & model.all_buffer_mask)
    if initial_events:
        try:
            incumbent = replay(ctx, initial_events, root)
            witness = tuple(initial_events)
        except ValueError:
            pass  # a seed library need not be a complete partition
    while queue:
        if ctx.counts["nodes"] >= limits.nodes:
            reason = "NODE_LIMIT"; break
        if time.perf_counter() >= ctx.deadline:
            reason = "TIME_LIMIT"; break
        inherited, _, node = heapq.heappop(queue)
        interrupted = inherited
        if incumbent is not None and inherited >= incumbent:
            closed_lowers.append(inherited); interrupted = None; continue
        try:
            ctx.counts["nodes"] += 1
            status, lower, columns, values = _node_lp(ctx, node)
            if status == "INFEASIBLE":
                interrupted = None; continue
            lower = max(inherited, lower)
            interrupted = lower
            value, events = _heuristic(ctx, node, columns)
            if value is not None and (incumbent is None or value < incumbent):
                incumbent, witness = value, events
            if value is not None and lower > value:
                raise AssertionError("repaired lower bound exceeds replayed node incumbent")
            if incumbent is not None and incumbent - lower <= rational(limits.gap_tolerance):
                closed_lowers.append(lower); interrupted = None; continue
            residual = max((abs(x - round(x)) for x in values), default=0)
            if residual <= 1e-7:
                events = tuple(c.member_mask for c, x in zip(columns, values) if round(x) == 1)
                value = replay(ctx, events, node)
                if incumbent is None or value < incumbent:
                    incumbent, witness = value, events
                if value - lower <= rational(limits.gap_tolerance):
                    closed_lowers.append(lower); interrupted = None; continue
                raise BudgetStop("INTEGRAL_LP_WITH_OPEN_REPAIRED_BOUND")
            usages = bp._buffer_usages(model, columns, values)
            fractional = bp._fractional_buffer_branch(model, node, usages)
            if fractional is not None:
                i, _ = fractional
                children = [bp._with_buffer_status(node, i, y) for y in (0, 1)]
                ctx.counts["buffer_branches"] += 1
            else:
                pair = bp._fractional_pair_branch(model, node, columns, values, usages)
                if pair is None:
                    raise BudgetStop("NO_FRACTIONAL_PAIR")
                i, j, _ = pair
                children = [bp._with_pair(model, node, i, j, together=y) for y in (False, True)]
                ctx.counts["pair_branches"] += 1
            for child in children:
                if child is not None:
                    serial += 1
                    heapq.heappush(queue, (lower, serial, child))
            interrupted = None
        except BudgetStop as error:
            reason = str(error); break
    ctx.counts["unique_generated_columns"] = len(ctx.pool)
    remaining_bounds = [item[0] for item in queue] + closed_lowers
    if interrupted is not None:
        remaining_bounds.append(interrupted)
    if incumbent is not None:
        remaining_bounds.append(incumbent)
    lower = min(remaining_bounds) if remaining_bounds else None
    status = ("BOUNDED_UNRESOLVED" if reason is not None else
              "INFEASIBLE" if incumbent is None else
              "EXACT_BOUND_CLOSED" if lower == incumbent else "OPTIMAL_WITHIN_TOLERANCE")
    return Endpoint(status, lower, incumbent, witness, dict(ctx.counts), time.perf_counter() - started, reason)


def _target_value(events: Sequence[int], costs: Mapping[int, Number], event_cost: Number) -> Fraction:
    return rational(event_cost) * len(events) + sum((rational(w) for mask in events
                                                   for i, w in costs.items() if mask & (1 << i)), Fraction(0))


def separate(rows: Sequence[FixedTimeRow], capacity: int, support_count: int,
             row_costs: Mapping[int, Number], threshold: Number,
             reference_events: Sequence[int], *, event_cost: Number = 0,
             usage_positions: Sequence[int] = (),
             pair_positions: Sequence[tuple[int, int]] = (),
             limits: Limits = Limits()) -> dict[str, Any]:
    """Find an opposite world or certify its absence using an objective bound.

    Exact comparator: target >= threshold. No label-tolerance shift. Truth
    answers and reference feasibility are validated, but reference events are
    not injected as priced columns. Empty/inconsistent worlds never certify.
    """
    model = cg.layout(rows)
    ref_mask = 0
    for mask in reference_events:
        ref_mask |= mask
    usage = {i: int(bool(ref_mask & (1 << i))) for i in usage_positions}
    pairs = {p: int(any(mask & (1 << p[0]) and mask & (1 << p[1]) for mask in reference_events))
             for p in pair_positions}
    root = _node(model, usage, pairs)
    costs = tuple(rational(row_costs.get(i, 0)) for i in range(len(model.rows)))
    check = Context(model, capacity, support_count, costs, rational(event_cost), limits, math.inf)
    ref_value = replay(check, reference_events, root)
    threshold = rational(threshold)
    positive = ref_value >= threshold
    sign = 1 if positive else -1
    endpoint = minimize(rows, capacity, support_count,
                        {i: sign * rational(w) for i, w in row_costs.items()},
                        event_cost=sign * rational(event_cost), usage_answers=usage,
                        pair_answers=pairs, limits=limits)
    result = {"status": "UNRESOLVED", "endpoint": endpoint.summary(),
              "reference_decision": positive, "opposite_events": ()}
    if endpoint.witness:
        candidate = _target_value(endpoint.witness, row_costs, event_cost)
        if (candidate >= threshold) != positive:
            result.update(status="OPPOSITE_WORLD", opposite_events=endpoint.witness)
            return result
    if endpoint.status == "INFEASIBLE":
        # Truth was replayed above, so infeasibility indicates an implementation
        # or numerical contradiction; never report a vacuous certificate.
        result["status"] = "INCONSISTENT_SOLVER_RESULT"
        return result
    if endpoint.lower is not None:
        if (positive and endpoint.lower >= threshold) or (not positive and -endpoint.lower < threshold):
            result["status"] = "NO_OPPOSITE_WORLD"
    return result


def _exact_hitting_set(cuts: Sequence[frozenset[int]], deadline: float) -> tuple[int, ...]:
    """Unit-cost hitting set by exact finite search; no floating MIP gap."""
    minimal = []
    for cut in sorted(set(cuts), key=lambda c: (len(c), tuple(sorted(c)))):
        if not cut:
            raise ValueError("opposite world is indistinguishable by allowed audit atoms")
        if not any(old <= cut for old in minimal):
            minimal.append(cut)
    if not minimal:
        return ()
    pending = list(minimal)
    greedy = []
    while pending:
        counts = {a: sum(a in c for c in pending) for a in set().union(*pending)}
        atom = min(counts, key=lambda a: (-counts[a], a))
        greedy.append(atom); pending = [c for c in pending if atom not in c]
    best = tuple(sorted(greedy))

    def visit(remaining, chosen):
        nonlocal best
        if time.perf_counter() >= deadline:
            raise BudgetStop("CERTIFICATE_MASTER_TIME_LIMIT")
        if not remaining:
            if len(chosen) < len(best):
                best = tuple(sorted(chosen))
            return
        used, packing = set(), 0
        for cut in sorted(remaining, key=len):
            if not used.intersection(cut):
                used.update(cut); packing += 1
        if len(chosen) + packing >= len(best):
            return
        pivot = min(remaining, key=lambda c: (len(c), tuple(sorted(c))))
        for atom in sorted(pivot, key=lambda a: (-sum(a in c for c in remaining), a)):
            visit([c for c in remaining if atom not in c], chosen + (atom,))
    visit(minimal, ())
    if any(not cut.intersection(best) for cut in cuts):
        raise AssertionError("hitting-set replay failed")
    return best


def minimum_certificate(rows: Sequence[FixedTimeRow], capacity: int, support_count: int,
                        row_costs: Mapping[int, Number], threshold: Number,
                        reference_events: Sequence[int], *, event_cost: Number = 0,
                        usage_atoms: Sequence[int] = (),
                        pair_atoms: Sequence[tuple[int, int]] = (),
                        known_usage: Sequence[int] = (), known_pairs: Sequence[tuple[int, int]] = (),
                        seconds: float = 120.0, separator_limits: Limits = Limits(),
                        max_cuts: int = 1000) -> dict[str, Any]:
    """Curator/ex-post minimum certificate, with implicit B&P separation.

    The curator knows a reference world and answers chosen facts truthfully.
    This is not a policy that discovers unknown answers at the reported cost.
    Public/previously known facts are conditioned on and excluded from cost.
    The summary never serializes queried identities or answers.
    """
    if not math.isfinite(seconds) or seconds < 0 or max_cuts < 0:
        raise ValueError("certificate budgets must be nonnegative and finite")
    usage_atoms = tuple(sorted(set(usage_atoms) - set(known_usage)))
    known_pairs = tuple(sorted({bp._pair(*p) for p in known_pairs}))
    pair_atoms = tuple(sorted({bp._pair(*p) for p in pair_atoms} - set(known_pairs)))
    atoms = [('usage', i) for i in usage_atoms] + [('pair', p) for p in pair_atoms]
    ref_used = 0
    for mask in reference_events:
        ref_used |= mask

    def answers(events):
        used = 0
        for mask in events:
            used |= mask
        return [int(bool(used & (1 << atom))) if kind == 'usage' else
                int(any(mask & (1 << atom[0]) and mask & (1 << atom[1]) for mask in events))
                for kind, atom in atoms]
    truth = answers(reference_events)
    started = time.perf_counter()
    deadline = started + seconds
    cuts = []
    certificate = ()
    rounds = 0
    total_nodes = total_pricing = 0
    try:
        for rounds in range(1, max_cuts + 2):
            certificate = _exact_hitting_set(cuts, deadline)
            if time.perf_counter() >= deadline:
                raise BudgetStop('CERTIFICATE_TIME_LIMIT')
            usage = tuple(known_usage) + tuple(atoms[a][1] for a in certificate if atoms[a][0] == 'usage')
            pairs = tuple(known_pairs) + tuple(atoms[a][1] for a in certificate if atoms[a][0] == 'pair')
            limits = Limits(seconds=min(separator_limits.seconds, deadline-time.perf_counter()),
                            nodes=separator_limits.nodes, iterations=separator_limits.iterations,
                            pricing_cases=separator_limits.pricing_cases,
                            gap_tolerance=separator_limits.gap_tolerance)
            result = separate(rows, capacity, support_count, row_costs, threshold, reference_events,
                              event_cost=event_cost, usage_positions=usage, pair_positions=pairs,
                              limits=limits)
            total_nodes += result['endpoint']['nodes']
            total_pricing += result['endpoint']['pricing_lp_calls']
            if result['status'] == 'NO_OPPOSITE_WORLD':
                return {'status': 'MINIMUM_CERTIFICATE_CERTIFIED', 'certificate_size': len(certificate),
                        'certificate_lower_bound': len(certificate), 'iterations': rounds,
                        'generated_cuts': len(cuts), 'nodes': total_nodes,
                        'pricing_lp_calls': total_pricing, 'seconds': time.perf_counter()-started,
                        'certificate_type': 'curator_ex_post', 'all_event_columns_enumerated': False}
            if result['status'] != 'OPPOSITE_WORLD':
                raise BudgetStop(result['status'])
            candidate = answers(result['opposite_events'])
            cut = frozenset(a for a, (x, y) in enumerate(zip(truth, candidate)) if x != y)
            if not cut:
                return {'status': 'UNIDENTIFIABLE_WITH_ALLOWED_ATOMS', 'certificate_size': None,
                        'iterations': rounds, 'generated_cuts': len(cuts),
                        'seconds': time.perf_counter()-started}
            if cut.intersection(certificate) or cut in cuts:
                raise AssertionError('invalid or duplicate opposite-world disagreement cut')
            if len(cuts) >= max_cuts:
                raise BudgetStop('CERTIFICATE_CUT_LIMIT')
            cuts.append(cut)
    except BudgetStop as error:
        return {'status': 'UNRESOLVED', 'reason': str(error), 'certificate_size': None,
                'certificate_lower_bound': len(certificate), 'iterations': rounds,
                'generated_cuts': len(cuts), 'nodes': total_nodes,
                'pricing_lp_calls': total_pricing, 'seconds': time.perf_counter()-started}
    raise AssertionError('certificate loop escaped')
