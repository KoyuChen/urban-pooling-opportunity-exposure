#!/usr/bin/env python3
"""Locked, claim-safe benchmark for the exact temporal-path frontier DP.

The benchmark separates three kinds of evidence:

* an independent ``Fraction``-arithmetic exhaustive oracle on small worlds;
* closed-form structured families that isolate locality, score-frontier, path,
  and Gamma parameters; and
* SciPy/HiGHS as a floating-point numerical comparator on singleton-label
  matching instances; plus
* one analytic certified outward-score relaxation with containment, score-slack,
  and sufficient endpoint-exactness witness checks.

The exact solver is never called an empirical identification certificate, and
HiGHS agreement is never relabelled as an exact certificate.  Runtime is one
tracemalloc-instrumented solve on the current machine; it supports diagnostics,
not a cross-language speed claim.  The instance grid, exact endpoints, state
counters, and witness checks are deterministic.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import itertools
import json
import math
import os
import platform
import random
import sys
import time
import tracemalloc
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Hashable, Iterable, Mapping, Sequence


# Keep the numerical comparator single-threaded when the script is launched as
# a fresh process.  The exact DP itself is single-threaded.
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import numpy as np

try:
    import scipy
    from scipy.optimize import Bounds, LinearConstraint, milp

    SCIPY_AVAILABLE = True
except (ImportError, AttributeError):  # pragma: no cover - lean environments
    scipy = None
    SCIPY_AVAILABLE = False


HERE = Path(__file__).resolve().parent
BOUNDS = HERE.parent / "bounds"
if str(BOUNDS) not in sys.path:
    sys.path.insert(0, str(BOUNDS))

from path_frontier_dp import (  # noqa: E402
    CountConstraint,
    EdgeSpec,
    ExactPathProblem,
    FrontierLimitExceeded,
    NodeSpec,
    compile_temporal_path,
    solve_path_frontier_endpoints,
    solve_path_frontier_outward_relaxation,
    validate_path_witness,
)


GENERATOR_VERSION = "path-frontier-benchmark-v1"
DEFAULT_OUTPUT = HERE / "results" / "path_frontier"


def _fraction(value: Any) -> Fraction:
    """Independent exact conversion matching the declared scalar semantics."""

    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        return Fraction(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("benchmark scalar must be finite")
        return Fraction(str(value))
    if isinstance(value, str):
        return Fraction(value)
    return Fraction(value)


def _fraction_text(value: Fraction | None) -> str:
    return "" if value is None else str(value)


def _pair_values(
    edge: EdgeSpec,
    left_support: Sequence[Hashable],
    right_support: Sequence[Hashable],
) -> tuple[
    frozenset[tuple[Hashable, Hashable]],
    dict[tuple[Hashable, Hashable], Fraction],
    dict[tuple[Hashable, Hashable], Fraction],
]:
    cartesian = {
        (left, right) for left in left_support for right in right_support
    }
    allowed = (
        frozenset(cartesian)
        if edge.allowed_label_pairs is None
        else frozenset(edge.allowed_label_pairs)
    )
    if edge.score_by_label_pair is None:
        scores = {pair: _fraction(edge.score) for pair in allowed}
    else:
        scores = {
            pair: _fraction(edge.score_by_label_pair[pair]) for pair in allowed
        }
    if edge.query_by_label_pair is None:
        queries = {pair: _fraction(edge.query) for pair in allowed}
    else:
        queries = {
            pair: _fraction(edge.query_by_label_pair[pair]) for pair in allowed
        }
    return allowed, scores, queries


@dataclass(frozen=True)
class OracleResult:
    status: str
    lower: Fraction | None
    upper: Fraction | None
    label_assignments_examined: int
    matching_leaves_examined: int
    feasible_worlds: int


def exhaustive_endpoints(
    problem: ExactPathProblem,
    *,
    gamma: int | None,
    score_floor: Any | None,
) -> OracleResult:
    """Independent exhaustive oracle; it imports no DP helper or state."""

    nodes = tuple(problem.nodes)
    edges = tuple(problem.edges)
    node_by_id = {node.node_id: node for node in nodes}
    edge_data: dict[
        str,
        tuple[
            EdgeSpec,
            frozenset[tuple[Hashable, Hashable]],
            Mapping[tuple[Hashable, Hashable], Fraction],
            Mapping[tuple[Hashable, Hashable], Fraction],
        ],
    ] = {}
    incident: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    for edge in edges:
        allowed, scores, queries = _pair_values(
            edge,
            node_by_id[edge.u].label_support,
            node_by_id[edge.v].label_support,
        )
        edge_data[edge.edge_id] = (edge, allowed, scores, queries)
        incident[edge.u].append(edge.edge_id)
        incident[edge.v].append(edge.edge_id)
    for edge_ids in incident.values():
        edge_ids.sort()

    constraints = {constraint.factor: constraint for constraint in problem.count_constraints}
    core = frozenset(node.node_id for node in nodes if node.role == "core")
    buffer = frozenset(node.node_id for node in nodes if node.role == "buffer")
    floor = None if score_floor is None else _fraction(score_floor)
    lower: Fraction | None = None
    upper: Fraction | None = None
    assignments_examined = 0
    matching_leaves = 0
    feasible_worlds = 0

    for labels_tuple in itertools.product(*(tuple(node.label_support) for node in nodes)):
        assignments_examined += 1
        labels = {
            node.node_id: label for node, label in zip(nodes, labels_tuple, strict=True)
        }
        counts = {factor: 0 for factor in constraints}
        requirements: dict[Hashable, str] = {}
        node_query = Fraction(0)
        assignment_ok = True
        for node in nodes:
            label = labels[node.node_id]
            for factor, contribution in (node.factor_contributions or {}).get(
                label, {}
            ).items():
                counts[factor] += int(contribution)
            for factor, requirement in (node.factor_requirements or {}).get(
                label, {}
            ).items():
                incumbent = requirements.get(factor)
                if incumbent is not None and incumbent != requirement:
                    assignment_ok = False
                    break
                requirements[factor] = requirement
            if not assignment_ok:
                break
            node_query += _fraction((node.label_query or {}).get(label, 0))
        if not assignment_ok:
            continue
        for factor, constraint in constraints.items():
            count = counts[factor]
            if not constraint.lower <= count <= constraint.upper:
                assignment_ok = False
                break
            requirement = requirements.get(factor)
            if requirement == "LOW":
                if constraint.low_upper is None or count > constraint.low_upper:
                    assignment_ok = False
                    break
            elif requirement == "HIGH":
                if constraint.high_lower is None or count < constraint.high_lower:
                    assignment_ok = False
                    break
        if not assignment_ok:
            continue

        compatible: dict[str, bool] = {}
        for edge_id, (edge, allowed, _scores, _queries) in edge_data.items():
            compatible[edge_id] = (labels[edge.u], labels[edge.v]) in allowed

        def recurse(
            uncovered: frozenset[str],
            used_buffer: frozenset[str],
            selected: tuple[str, ...],
        ) -> None:
            nonlocal lower, upper, matching_leaves, feasible_worlds
            if not uncovered:
                matching_leaves += 1
                omitted = 0
                raw_score = Fraction(0)
                query = node_query
                for edge_id in selected:
                    edge, _allowed, scores, queries = edge_data[edge_id]
                    pair = (labels[edge.u], labels[edge.v])
                    core_incidences = int(edge.u in core) + int(edge.v in core)
                    raw_score += scores[pair] * core_incidences
                    query += queries[pair]
                    omitted += int(edge.omitted)
                if gamma is not None and omitted > gamma:
                    return
                if floor is not None and raw_score < floor:
                    return
                feasible_worlds += 1
                lower = query if lower is None else min(lower, query)
                upper = query if upper is None else max(upper, query)
                return

            choices: dict[str, list[tuple[str, frozenset[str], frozenset[str]]]] = {}
            for node_id in sorted(uncovered):
                candidates: list[tuple[str, frozenset[str], frozenset[str]]] = []
                for edge_id in incident[node_id]:
                    if not compatible[edge_id]:
                        continue
                    edge = edge_data[edge_id][0]
                    endpoints = (edge.u, edge.v)
                    covered = frozenset(endpoint for endpoint in endpoints if endpoint in core)
                    touched_buffer = frozenset(
                        endpoint for endpoint in endpoints if endpoint in buffer
                    )
                    if node_id not in covered:
                        continue
                    if not covered <= uncovered or touched_buffer & used_buffer:
                        continue
                    candidates.append((edge_id, covered, touched_buffer))
                if not candidates:
                    return
                choices[node_id] = candidates
            pivot = min(choices, key=lambda item: (len(choices[item]), item))
            for edge_id, covered, touched_buffer in choices[pivot]:
                recurse(
                    uncovered - covered,
                    used_buffer | touched_buffer,
                    selected + (edge_id,),
                )

        recurse(core, frozenset(), ())

    status = "EXACT_OPTIMAL" if feasible_worlds else "EXACT_INFEASIBLE"
    return OracleResult(
        status=status,
        lower=lower,
        upper=upper,
        label_assignments_examined=assignments_examined,
        matching_leaves_examined=matching_leaves,
        feasible_worlds=feasible_worlds,
    )


@dataclass(frozen=True)
class HighsResult:
    status: str
    lower: Fraction | None
    upper: Fraction | None
    wall_ms: float
    max_mip_gap: float | None


def _highs_singleton_endpoint(
    problem: ExactPathProblem,
    *,
    gamma: int | None,
    score_floor: Any | None,
    maximize: bool,
) -> tuple[str, Fraction | None, float | None]:
    """Numerical MILP comparator for singleton-label matching instances."""

    if not SCIPY_AVAILABLE:
        return "UNAVAILABLE", None, None
    nodes = tuple(problem.nodes)
    edges = tuple(problem.edges)
    if problem.count_constraints or any(len(tuple(node.label_support)) != 1 for node in nodes):
        return "UNSUPPORTED", None, None
    node_by_id = {node.node_id: node for node in nodes}
    labels = {node.node_id: tuple(node.label_support)[0] for node in nodes}
    edge_query: list[Fraction] = []
    edge_score: list[Fraction] = []
    for edge in edges:
        allowed, scores, queries = _pair_values(
            edge,
            node_by_id[edge.u].label_support,
            node_by_id[edge.v].label_support,
        )
        pair = (labels[edge.u], labels[edge.v])
        if pair not in allowed:
            raise ValueError("singleton benchmark edge has no compatible label pair")
        core_incidences = int(node_by_id[edge.u].role == "core") + int(
            node_by_id[edge.v].role == "core"
        )
        edge_query.append(queries[pair])
        edge_score.append(scores[pair] * core_incidences)

    rows: list[list[float]] = []
    lower: list[float] = []
    upper: list[float] = []
    for node in nodes:
        if node.role == "context_only":
            continue
        row = [
            float(edge.u == node.node_id or edge.v == node.node_id) for edge in edges
        ]
        rows.append(row)
        if node.role == "core":
            lower.append(1.0)
            upper.append(1.0)
        else:
            lower.append(0.0)
            upper.append(1.0)
    if gamma is not None:
        rows.append([float(edge.omitted) for edge in edges])
        lower.append(0.0)
        upper.append(float(gamma))
    if score_floor is not None:
        rows.append([float(value) for value in edge_score])
        lower.append(float(_fraction(score_floor)))
        upper.append(np.inf)
    matrix = np.asarray(rows, dtype=float)
    objective = np.asarray([float(value) for value in edge_query], dtype=float)
    if maximize:
        objective = -objective
    result = milp(
        c=objective,
        integrality=np.ones(len(edges), dtype=np.int8),
        bounds=Bounds(np.zeros(len(edges)), np.ones(len(edges))),
        constraints=LinearConstraint(
            matrix,
            lb=np.asarray(lower, dtype=float),
            ub=np.asarray(upper, dtype=float),
        ),
        options={"presolve": True, "mip_rel_gap": 0.0, "time_limit": 30.0},
    )
    if int(result.status) == 2:
        return "NUMERICALLY_INFEASIBLE", None, None
    if int(result.status) != 0 or result.x is None:
        return "UNRESOLVED", None, None
    selected = [index for index, value in enumerate(result.x) if value > 0.5]
    # Recompute the incumbent in exact arithmetic and reject invalid rounding.
    degrees = {node.node_id: 0 for node in nodes}
    for index in selected:
        degrees[edges[index].u] += 1
        degrees[edges[index].v] += 1
    if any(
        (node.role == "core" and degrees[node.node_id] != 1)
        or (node.role == "buffer" and degrees[node.node_id] > 1)
        or (node.role == "context_only" and degrees[node.node_id] != 0)
        for node in nodes
    ):
        return "UNRESOLVED", None, None
    if gamma is not None and sum(edges[index].omitted for index in selected) > gamma:
        return "UNRESOLVED", None, None
    raw_score = sum((edge_score[index] for index in selected), Fraction(0))
    if score_floor is not None and raw_score < _fraction(score_floor):
        return "UNRESOLVED", None, None
    query = sum((edge_query[index] for index in selected), Fraction(0))
    gap = getattr(result, "mip_gap", None)
    return "NUMERICALLY_OPTIMAL", query, None if gap is None else float(gap)


def highs_singleton_endpoints(
    problem: ExactPathProblem,
    *,
    gamma: int | None,
    score_floor: Any | None,
) -> HighsResult:
    start = time.perf_counter_ns()
    lower_status, lower, lower_gap = _highs_singleton_endpoint(
        problem,
        gamma=gamma,
        score_floor=score_floor,
        maximize=False,
    )
    upper_status, upper, upper_gap = _highs_singleton_endpoint(
        problem,
        gamma=gamma,
        score_floor=score_floor,
        maximize=True,
    )
    wall_ms = (time.perf_counter_ns() - start) / 1_000_000
    if lower_status == upper_status == "NUMERICALLY_OPTIMAL":
        status = "NUMERICALLY_OPTIMAL"
    elif lower_status == upper_status == "NUMERICALLY_INFEASIBLE":
        status = "NUMERICALLY_INFEASIBLE"
    elif "UNAVAILABLE" in (lower_status, upper_status):
        status = "UNAVAILABLE"
    elif "UNSUPPORTED" in (lower_status, upper_status):
        status = "UNSUPPORTED"
    else:
        status = "UNRESOLVED"
    gaps = [gap for gap in (lower_gap, upper_gap) if gap is not None]
    return HighsResult(
        status=status,
        lower=lower,
        upper=upper,
        wall_ms=wall_ms,
        max_mip_gap=max(gaps) if gaps else None,
    )


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    family: str
    problem: ExactPathProblem
    forget_order: tuple[str, ...]
    gamma: int | None = None
    score_floor: Any | None = None
    expected_status: str | None = None
    expected_lower: Fraction | None = None
    expected_upper: Fraction | None = None
    relaxation_eta: Fraction | None = None
    expected_outer_lower: Fraction | None = None
    expected_outer_upper: Fraction | None = None
    expected_outer_lower_exact: bool | None = None
    expected_outer_upper_exact: bool | None = None
    run_exhaustive: bool = False
    run_highs: bool = False
    notes: str = ""


def _random_oracle_case(seed: int) -> BenchmarkCase:
    rng = random.Random(91_001 + seed)
    n = (4, 6, 8)[seed % 3]
    d = 2 + (seed % 2)
    labels_catalog = tuple(f"L{index}" for index in range(d))
    query_bin = {label: index % 2 for index, label in enumerate(labels_catalog)}
    truth = [labels_catalog[(seed + 2 * index) % d] for index in range(n)]
    supports: list[tuple[str, ...]] = []
    for index in range(n):
        values = [truth[index]]
        for label in labels_catalog:
            if label != truth[index] and rng.random() < 0.65:
                values.append(label)
        supports.append(tuple(sorted(set(values))))
    cell = {index: f"c{index // 4}" for index in range(n)}
    factors = [
        (cell_name, label)
        for cell_name in sorted(set(cell.values()))
        for label in labels_catalog
    ]
    constraints: list[CountConstraint] = []
    for cell_name, label in factors:
        count = sum(
            cell[index] == cell_name and truth[index] == label for index in range(n)
        )
        constraints.append(CountConstraint((cell_name, label), count, count))
    nodes: list[NodeSpec] = []
    for index in range(n):
        contributions = {
            label: {(cell[index], label): 1} for label in supports[index]
        }
        nodes.append(
            NodeSpec(
                f"n{index}",
                "core",
                supports[index],
                factor_contributions=contributions,
            )
        )
    base_pairs = {(index, index + 1) for index in range(0, n, 2)}
    horizon = 1 + seed % 3
    edge_rows: list[EdgeSpec] = []
    for left in range(n):
        for right in range(left + 1, n):
            if (left, right) not in base_pairs and right - left > horizon:
                continue
            cartesian = [
                (u_label, v_label)
                for u_label in supports[left]
                for v_label in supports[right]
            ]
            allowed = [pair for pair in cartesian if rng.random() < 0.72]
            truth_pair = (truth[left], truth[right])
            if (left, right) in base_pairs and truth_pair not in allowed:
                allowed.append(truth_pair)
            if not allowed:
                allowed.append(cartesian[0])
            allowed_tuple = tuple(sorted(set(allowed)))
            contribution = {
                pair: Fraction(2, n)
                if query_bin[pair[0]] == query_bin[pair[1]]
                else Fraction(0)
                for pair in allowed_tuple
            }
            edge_rows.append(
                EdgeSpec(
                    edge_id=f"e{left}:{right}",
                    u=f"n{left}",
                    v=f"n{right}",
                    omitted=(left, right) not in base_pairs and rng.random() < 0.25,
                    allowed_label_pairs=allowed_tuple,
                    query_by_label_pair=contribution,
                )
            )
    return BenchmarkCase(
        case_id=f"oracle_seed_{seed:02d}",
        family="exhaustive_oracle",
        problem=ExactPathProblem(tuple(nodes), tuple(edge_rows), tuple(constraints)),
        forget_order=tuple(f"n{index}" for index in range(n)),
        gamma=seed % 2,
        run_exhaustive=True,
        notes="Seeded feasible joint-label/matching world; exact-count factors.",
    )


def _release_requirement_case() -> BenchmarkCase:
    nodes = tuple(
        NodeSpec(
            node_id,
            "core",
            ("A", "B"),
            factor_contributions={"A": {"f": 1}, "B": {}},
            factor_requirements={"A": {"f": "HIGH"}, "B": {"f": "LOW"}},
            label_query={"A": 1, "B": 0},
        )
        for node_id in ("u", "v")
    )
    return BenchmarkCase(
        case_id="release_requirement_partition",
        family="exhaustive_oracle",
        problem=ExactPathProblem(
            nodes,
            (EdgeSpec("uv", "u", "v"),),
            (CountConstraint("f", 0, 2, low_upper=0, high_lower=2),),
        ),
        forget_order=("u", "v"),
        expected_status="EXACT_OPTIMAL",
        expected_lower=Fraction(0),
        expected_upper=Fraction(2),
        run_exhaustive=True,
        notes="Mixed LOW/HIGH labels conflict; all-low and all-high worlds survive.",
    )


def _count_overflow_infeasible_case() -> BenchmarkCase:
    nodes = tuple(
        NodeSpec(
            node_id,
            "core",
            ("A",),
            factor_contributions={"A": {"f": 1}},
        )
        for node_id in ("u", "v")
    )
    return BenchmarkCase(
        case_id="ordinary_upper_overflow",
        family="exhaustive_oracle",
        problem=ExactPathProblem(
            nodes,
            (EdgeSpec("uv", "u", "v"),),
            (CountConstraint("f", 0, 1),),
        ),
        forget_order=("u", "v"),
        expected_status="EXACT_INFEASIBLE",
        run_exhaustive=True,
        notes="Ordinary upper bounds must overflow-prune rather than saturate.",
    )


def _outward_relaxation_case() -> BenchmarkCase:
    """Pathwidth-2 case with one newly admitted, score-short witness."""

    problem = ExactPathProblem(
        nodes=tuple(
            NodeSpec(node_id, "core", (0,))
            for node_id in ("a", "b", "c", "d")
        ),
        edges=(
            EdgeSpec("ab", "a", "b", score=Fraction(11, 10)),
            EdgeSpec("cd", "c", "d", score=Fraction(11, 10)),
            EdgeSpec("ac", "a", "c", score=Fraction(9, 10), query=-5),
            EdgeSpec("bd", "b", "d", score=Fraction(9, 10)),
        ),
    )
    return BenchmarkCase(
        case_id="outward_eta_one_fifth",
        family="outward_score_relaxation",
        problem=problem,
        forget_order=("a", "b", "c", "d"),
        score_floor=4,
        expected_status="EXACT_OPTIMAL",
        expected_lower=Fraction(0),
        expected_upper=Fraction(0),
        relaxation_eta=Fraction(1, 5),
        expected_outer_lower=Fraction(-5),
        expected_outer_upper=Fraction(0),
        expected_outer_lower_exact=False,
        expected_outer_upper_exact=True,
        run_exhaustive=True,
        run_highs=True,
        notes=(
            "Certified outer interval contains the exact singleton; the new lower "
            "witness misses the raw floor by 2/5 <= eta*N=4/5."
        ),
    )


def _local_factor_problem(
    factor_count: int,
    pairs_per_factor: int,
) -> tuple[ExactPathProblem, tuple[str, ...], tuple[str, ...], Fraction, Fraction]:
    nodes: list[NodeSpec] = []
    edges: list[EdgeSpec] = []
    grouped: list[str] = []
    interleaved: list[str] = []
    for factor_index in range(factor_count):
        factor = f"f{factor_index}"
        for pair_index in range(pairs_per_factor):
            for side in range(2):
                node_id = f"f{factor_index}:p{pair_index}:{side}"
                weight = 2 * pair_index + side
                nodes.append(
                    NodeSpec(
                        node_id,
                        "core",
                        ("A", "B"),
                        factor_contributions={"A": {factor: 1}, "B": {}},
                        label_query={"A": weight, "B": 0},
                    )
                )
                grouped.append(node_id)
            edges.append(
                EdgeSpec(
                    f"f{factor_index}:e{pair_index}",
                    f"f{factor_index}:p{pair_index}:0",
                    f"f{factor_index}:p{pair_index}:1",
                )
            )
    for pair_index in range(pairs_per_factor):
        for factor_index in range(factor_count):
            interleaved.extend(
                [
                    f"f{factor_index}:p{pair_index}:0",
                    f"f{factor_index}:p{pair_index}:1",
                ]
            )
    constraints = tuple(
        CountConstraint(f"f{factor_index}", pairs_per_factor, pairs_per_factor)
        for factor_index in range(factor_count)
    )
    per_factor_lower = pairs_per_factor * (pairs_per_factor - 1) // 2
    per_factor_upper = pairs_per_factor * (3 * pairs_per_factor - 1) // 2
    return (
        ExactPathProblem(tuple(nodes), tuple(edges), constraints),
        tuple(grouped),
        tuple(interleaved),
        Fraction(factor_count * per_factor_lower),
        Fraction(factor_count * per_factor_upper),
    )


def _local_factor_cases(suite: str) -> list[BenchmarkCase]:
    parameter_grid = [(count, 2) for count in range(1, 4 if suite == "smoke" else 6)]
    if suite == "full":
        parameter_grid.extend((count, 3) for count in range(1, 4))
    cases: list[BenchmarkCase] = []
    for factor_count, pairs in parameter_grid:
        problem, grouped, interleaved, lower, upper = _local_factor_problem(
            factor_count, pairs
        )
        for ordering, order in (("grouped", grouped), ("interleaved", interleaved)):
            cases.append(
                BenchmarkCase(
                    case_id=f"local_r{factor_count}_k{pairs}_{ordering}",
                    family="local_factor_scaling",
                    problem=problem,
                    forget_order=order,
                    expected_status="EXACT_OPTIMAL",
                    expected_lower=lower,
                    expected_upper=upper,
                    run_exhaustive=len(problem.nodes) <= 8,
                    notes="Same world set; order changes simultaneous active-factor width.",
                )
            )
    return cases


def _c4_problem(
    weights: Sequence[int],
    *,
    score_tradeoff: bool,
    omitted_high: bool,
) -> tuple[ExactPathProblem, tuple[str, ...]]:
    nodes: list[NodeSpec] = []
    edges: list[EdgeSpec] = []
    order: list[str] = []
    for index, weight in enumerate(weights):
        a, b, x, y = (f"g{index}:{name}" for name in ("a", "b", "x", "y"))
        nodes.extend(
            [
                NodeSpec(a, "core", ("z",)),
                NodeSpec(b, "core", ("z",)),
                NodeSpec(x, "buffer", ("z",)),
                NodeSpec(y, "buffer", ("z",)),
            ]
        )
        # ax+by is skip; ay+bx is take.  The high edge has one core incidence,
        # so its declared score equals the gadget's total raw score.
        edges.extend(
            [
                EdgeSpec(f"g{index}:ax", a, x),
                EdgeSpec(f"g{index}:by", b, y),
                EdgeSpec(
                    f"g{index}:ay",
                    a,
                    y,
                    score=weight if score_tradeoff else 0,
                    query=weight,
                    omitted=omitted_high,
                ),
                EdgeSpec(f"g{index}:bx", b, x),
            ]
        )
        order.extend((a, b, x, y))
    return ExactPathProblem(tuple(nodes), tuple(edges)), tuple(order)


def _subset_ceiling(weights: Sequence[int], floor: int) -> int:
    attainable = {0}
    for weight in weights:
        attainable |= {value + weight for value in tuple(attainable)}
    return min(value for value in attainable if value >= floor)


def _score_frontier_cases(suite: str) -> list[BenchmarkCase]:
    sizes = (4, 8, 12) if suite == "smoke" else (4, 8, 12, 14, 16)
    cases: list[BenchmarkCase] = []
    for encoding in ("unit", "binary"):
        for size in sizes:
            weights = [1] * size if encoding == "unit" else [1 << index for index in range(size)]
            total = sum(weights)
            floor = (total + 1) // 2
            problem, order = _c4_problem(
                weights, score_tradeoff=True, omitted_high=False
            )
            cases.append(
                BenchmarkCase(
                    case_id=f"score_{encoding}_m{size}",
                    family="c4_score_frontier",
                    problem=problem,
                    forget_order=order,
                    score_floor=floor,
                    expected_status="EXACT_OPTIMAL",
                    expected_lower=Fraction(_subset_ceiling(weights, floor)),
                    expected_upper=Fraction(total),
                    run_exhaustive=size <= 12,
                    run_highs=True,
                    notes=(
                        "Pathwidth-2 subset-sum gadget; binary weights expose exact "
                        "pseudo-polynomial score-frontier growth."
                    ),
                )
            )
    return cases


def _gamma_cases(suite: str) -> list[BenchmarkCase]:
    size = 8 if suite == "smoke" else 16
    budgets = sorted(set((0, 1, 2, 4, size // 2, size)))
    problem, order = _c4_problem(
        [1] * size, score_tradeoff=False, omitted_high=True
    )
    return [
        BenchmarkCase(
            case_id=f"gamma_m{size}_g{budget}",
            family="gamma_sweep",
            problem=problem,
            forget_order=order,
            gamma=budget,
            expected_status="EXACT_OPTIMAL",
            expected_lower=Fraction(0),
            expected_upper=Fraction(min(budget, size)),
            run_exhaustive=size <= 12,
            run_highs=True,
            notes="At most Gamma take-edges; analytic interval is [0,min(Gamma,m)].",
        )
        for budget in budgets
    ]


def _nested_order_cases(suite: str) -> list[BenchmarkCase]:
    sizes = (8, 16) if suite == "smoke" else (8, 16, 32, 64)
    cases: list[BenchmarkCase] = []
    for size in sizes:
        nodes: list[NodeSpec] = []
        edges: list[EdgeSpec] = []
        adjacent: list[str] = []
        left_ids: list[str] = []
        right_ids: list[str] = []
        for index in range(size):
            left, right = f"a{index}", f"b{index}"
            nodes.extend(
                [NodeSpec(left, "core", ("z",)), NodeSpec(right, "core", ("z",))]
            )
            edges.append(EdgeSpec(f"e{index}", left, right, query=index + 1))
            adjacent.extend((left, right))
            left_ids.append(left)
            right_ids.append(right)
        problem = ExactPathProblem(tuple(nodes), tuple(edges))
        endpoint = Fraction(size * (size + 1) // 2)
        for ordering, order in (
            ("adjacent", tuple(adjacent)),
            ("nested", tuple(left_ids + right_ids)),
        ):
            cases.append(
                BenchmarkCase(
                    case_id=f"degree1_m{size}_{ordering}",
                    family="temporal_width_counterexample",
                    problem=problem,
                    forget_order=order,
                    expected_status="EXACT_OPTIMAL",
                    expected_lower=endpoint,
                    expected_upper=endpoint,
                    run_exhaustive=size <= 16,
                    notes="Same degree-one world; nested long edges force linear live-bag width.",
                )
            )
    return cases


def _band_cases(suite: str) -> list[BenchmarkCase]:
    n = 10 if suite == "smoke" else 16
    horizons = range(1, 5 if suite == "smoke" else 7)
    cases: list[BenchmarkCase] = []
    nodes = tuple(NodeSpec(f"n{index}", "core", ("z",)) for index in range(n))
    for horizon in horizons:
        edges = tuple(
            EdgeSpec(
                f"e{left}:{right}",
                f"n{left}",
                f"n{right}",
                query=((left + 1) * (right + 3)) % 11 - 5,
            )
            for left in range(n)
            for right in range(left + 1, min(n, left + horizon + 1))
        )
        cases.append(
            BenchmarkCase(
                case_id=f"band_n{n}_h{horizon}",
                family="band_width_sweep",
                problem=ExactPathProblem(nodes, edges),
                forget_order=tuple(f"n{index}" for index in range(n)),
                run_exhaustive=n <= 10,
                run_highs=True,
                notes="Candidate horizon varies audited live-bag width at fixed n.",
            )
        )
    return cases


def locked_cases(suite: str) -> list[BenchmarkCase]:
    oracle_count = 6 if suite == "smoke" else 18
    cases = [_random_oracle_case(seed) for seed in range(oracle_count)]
    cases.extend(
        (
            _release_requirement_case(),
            _count_overflow_infeasible_case(),
            _outward_relaxation_case(),
        )
    )
    cases.extend(_local_factor_cases(suite))
    cases.extend(_score_frontier_cases(suite))
    cases.extend(_nested_order_cases(suite))
    cases.extend(_gamma_cases(suite))
    cases.extend(_band_cases(suite))
    return cases


def _instance_hash(case: BenchmarkCase) -> str:
    declared = (
        GENERATOR_VERSION,
        case.case_id,
        case.problem,
        case.forget_order,
        case.gamma,
        case.score_floor,
        case.relaxation_eta,
        case.expected_outer_lower,
        case.expected_outer_upper,
    )
    return hashlib.sha256(repr(declared).encode("utf-8")).hexdigest()


def _endpoint_agreement(
    status: str,
    lower: Fraction | None,
    upper: Fraction | None,
    reference_status: str,
    reference_lower: Fraction | None,
    reference_upper: Fraction | None,
) -> bool:
    return (
        status == reference_status
        and lower == reference_lower
        and upper == reference_upper
    )


def run_case(case: BenchmarkCase, *, max_frontier_records: int) -> dict[str, Any]:
    schedule = compile_temporal_path(case.problem, case.forget_order)
    gc.collect()
    tracemalloc.start()
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    try:
        result = solve_path_frontier_endpoints(
            case.problem,
            schedule=schedule,
            gamma=case.gamma,
            score_floor=case.score_floor,
            max_frontier_records=max_frontier_records,
        )
        dp_error = ""
    except FrontierLimitExceeded as exc:
        result = None
        dp_error = str(exc)
    cpu_ms = (time.process_time_ns() - cpu_start) / 1_000_000
    wall_ms = (time.perf_counter_ns() - wall_start) / 1_000_000
    _current, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    if result is None:
        status = "FRONTIER_LIMIT"
        lower = upper = None
        witness_valid = False
        lower_stats = upper_stats = None
        score_target = None
    else:
        status = result.status
        lower, upper = result.lower, result.upper
        score_target = result.capped_integer_score_target
        lower_stats = result.lower_solution.stats
        upper_stats = result.upper_solution.stats
        witness_valid = True
        if status == "EXACT_OPTIMAL":
            assert result.lower_solution.witness is not None
            assert result.upper_solution.witness is not None
            witness_valid = bool(
                validate_path_witness(
                    case.problem,
                    result.lower_solution.witness,
                    gamma=case.gamma,
                    score_floor=case.score_floor,
                )
                and validate_path_witness(
                    case.problem,
                    result.upper_solution.witness,
                    gamma=case.gamma,
                    score_floor=case.score_floor,
                )
                and result.lower_solution.witness.query_value == lower
                and result.upper_solution.witness.query_value == upper
            )

    relaxation = None
    relaxation_wall_ms = None
    relaxation_peak_bytes = None
    relaxation_containment = None
    relaxation_slack_valid = None
    relaxation_witness_valid = None
    relaxation_analytic_agreement = None
    observed_maximum_shortfall: Fraction | None = None
    if case.relaxation_eta is not None:
        gc.collect()
        tracemalloc.start()
        relaxation_start = time.perf_counter_ns()
        relaxation = solve_path_frontier_outward_relaxation(
            case.problem,
            schedule=schedule,
            gamma=case.gamma,
            score_floor=case.score_floor,
            score_granularity=case.relaxation_eta,
            max_frontier_records=max_frontier_records,
        )
        relaxation_wall_ms = (
            time.perf_counter_ns() - relaxation_start
        ) / 1_000_000
        _relaxation_current, relaxation_peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if relaxation.status == "OUTER_OPTIMAL":
            assert relaxation.lower_solution.witness is not None
            assert relaxation.upper_solution.witness is not None
            relaxation_witness_valid = bool(
                validate_path_witness(
                    case.problem,
                    relaxation.lower_solution.witness,
                    gamma=case.gamma,
                )
                and validate_path_witness(
                    case.problem,
                    relaxation.upper_solution.witness,
                    gamma=case.gamma,
                )
            )
            relaxation_containment = bool(
                status == "EXACT_OPTIMAL"
                and relaxation.lower is not None
                and relaxation.upper is not None
                and lower is not None
                and upper is not None
                and relaxation.lower <= lower <= upper <= relaxation.upper
            )
            original_floor = _fraction(case.score_floor)
            shortfalls = tuple(
                max(Fraction(0), original_floor - solution.witness.raw_score)
                for solution in (
                    relaxation.lower_solution,
                    relaxation.upper_solution,
                )
            )
            observed_maximum_shortfall = max(shortfalls)
            relaxation_slack_valid = all(
                shortfall <= relaxation.maximum_score_shortfall
                for shortfall in shortfalls
            )
            relaxation_analytic_agreement = bool(
                relaxation.lower == case.expected_outer_lower
                and relaxation.upper == case.expected_outer_upper
                and relaxation.lower_endpoint_exact_witnessed
                == case.expected_outer_lower_exact
                and relaxation.upper_endpoint_exact_witnessed
                == case.expected_outer_upper_exact
            )
        else:
            relaxation_witness_valid = relaxation.exact_infeasibility_certified
            relaxation_containment = status == "EXACT_INFEASIBLE"
            relaxation_slack_valid = True
            relaxation_analytic_agreement = bool(
                case.expected_outer_lower is None
                and case.expected_outer_upper is None
            )

    oracle = None
    oracle_ms = None
    if case.run_exhaustive:
        oracle_start = time.perf_counter_ns()
        oracle = exhaustive_endpoints(
            case.problem,
            gamma=case.gamma,
            score_floor=case.score_floor,
        )
        oracle_ms = (time.perf_counter_ns() - oracle_start) / 1_000_000
    highs = (
        highs_singleton_endpoints(
            case.problem,
            gamma=case.gamma,
            score_floor=case.score_floor,
        )
        if case.run_highs
        else None
    )
    analytic_applicable = case.expected_status is not None
    analytic_agreement = (
        _endpoint_agreement(
            status,
            lower,
            upper,
            case.expected_status or "",
            case.expected_lower,
            case.expected_upper,
        )
        if analytic_applicable
        else None
    )
    oracle_agreement = (
        _endpoint_agreement(
            status,
            lower,
            upper,
            oracle.status,
            oracle.lower,
            oracle.upper,
        )
        if oracle is not None
        else None
    )
    if highs is None or highs.status in {"UNAVAILABLE", "UNSUPPORTED"}:
        highs_agreement = None
    elif status == "EXACT_INFEASIBLE":
        highs_agreement = highs.status == "NUMERICALLY_INFEASIBLE"
    else:
        highs_agreement = (
            highs.status == "NUMERICALLY_OPTIMAL"
            and highs.lower == lower
            and highs.upper == upper
        )
    checks = [witness_valid]
    checks.extend(
        value
        for value in (
            analytic_agreement,
            oracle_agreement,
            highs_agreement,
            relaxation_containment,
            relaxation_slack_valid,
            relaxation_witness_valid,
            relaxation_analytic_agreement,
        )
        if value is not None
    )
    reference_agreement = bool(checks) and all(checks)

    def stat(name: str, combine=max) -> int | None:
        if lower_stats is None or upper_stats is None:
            return None
        return combine((getattr(lower_stats, name), getattr(upper_stats, name)))

    maximum_support = max(
        (len(tuple(node.label_support)) for node in case.problem.nodes), default=0
    )
    maximum_cap = max((cap for _factor, cap in schedule.factor_count_caps), default=0)
    return {
        "case_id": case.case_id,
        "family": case.family,
        "instance_sha256": _instance_hash(case),
        "node_count": len(case.problem.nodes),
        "core_count": sum(node.role == "core" for node in case.problem.nodes),
        "buffer_count": sum(node.role == "buffer" for node in case.problem.nodes),
        "edge_count": len(case.problem.edges),
        "action_count": len(schedule.actions),
        "max_bag_size": schedule.max_bag_size,
        "schedule_width": schedule.schedule_width,
        "factor_count": len(case.problem.count_constraints),
        "max_active_factor_count": schedule.max_active_factor_count,
        "max_factor_count_cap": maximum_cap,
        "max_label_support": maximum_support,
        "gamma": "" if case.gamma is None else case.gamma,
        "score_floor": "" if case.score_floor is None else str(_fraction(case.score_floor)),
        "capped_integer_score_target": "" if score_target is None else score_target,
        "dp_status": status,
        "dp_lower": _fraction_text(lower),
        "dp_upper": _fraction_text(upper),
        "witness_valid": witness_valid,
        "dp_wall_ms_traced": round(wall_ms, 6),
        "dp_cpu_ms_traced": round(cpu_ms, 6),
        "dp_peak_python_mib": round(peak_bytes / (1024 * 1024), 6),
        "peak_live_records": stat("peak_live_records"),
        "introduced_states": stat("introduced_states", sum),
        "accepted_records": stat("accepted_records", sum),
        "dominance_pruned_records": stat("dominance_pruned_records", sum),
        "transition_count": stat("transition_count", sum),
        "frontier_limit": max_frontier_records,
        "dp_error": dp_error,
        "expected_status": case.expected_status or "",
        "expected_lower": _fraction_text(case.expected_lower),
        "expected_upper": _fraction_text(case.expected_upper),
        "analytic_agreement": "" if analytic_agreement is None else analytic_agreement,
        "oracle_status": "" if oracle is None else oracle.status,
        "oracle_lower": "" if oracle is None else _fraction_text(oracle.lower),
        "oracle_upper": "" if oracle is None else _fraction_text(oracle.upper),
        "oracle_worlds": "" if oracle is None else oracle.feasible_worlds,
        "oracle_label_assignments": ""
        if oracle is None
        else oracle.label_assignments_examined,
        "oracle_matching_leaves": ""
        if oracle is None
        else oracle.matching_leaves_examined,
        "oracle_wall_ms": "" if oracle_ms is None else round(oracle_ms, 6),
        "oracle_agreement": "" if oracle_agreement is None else oracle_agreement,
        "highs_status": "" if highs is None else highs.status,
        "highs_lower": "" if highs is None else _fraction_text(highs.lower),
        "highs_upper": "" if highs is None else _fraction_text(highs.upper),
        "highs_wall_ms": "" if highs is None else round(highs.wall_ms, 6),
        "highs_max_mip_gap": ""
        if highs is None or highs.max_mip_gap is None
        else highs.max_mip_gap,
        "highs_agreement": "" if highs_agreement is None else highs_agreement,
        "relaxation_eta": ""
        if case.relaxation_eta is None
        else str(case.relaxation_eta),
        "outer_status": "" if relaxation is None else relaxation.status,
        "outer_lower": ""
        if relaxation is None
        else _fraction_text(relaxation.lower),
        "outer_upper": ""
        if relaxation is None
        else _fraction_text(relaxation.upper),
        "outer_maximum_score_shortfall": ""
        if relaxation is None
        else str(relaxation.maximum_score_shortfall),
        "outer_observed_maximum_shortfall": ""
        if observed_maximum_shortfall is None
        else str(observed_maximum_shortfall),
        "outer_lower_endpoint_exact_witnessed": ""
        if relaxation is None
        else relaxation.lower_endpoint_exact_witnessed,
        "outer_upper_endpoint_exact_witnessed": ""
        if relaxation is None
        else relaxation.upper_endpoint_exact_witnessed,
        "outer_exact_feasibility_witnessed": ""
        if relaxation is None
        else relaxation.exact_feasibility_witnessed,
        "outer_containment": ""
        if relaxation_containment is None
        else relaxation_containment,
        "outer_slack_valid": ""
        if relaxation_slack_valid is None
        else relaxation_slack_valid,
        "outer_witness_valid": ""
        if relaxation_witness_valid is None
        else relaxation_witness_valid,
        "outer_analytic_agreement": ""
        if relaxation_analytic_agreement is None
        else relaxation_analytic_agreement,
        "outer_wall_ms_traced": ""
        if relaxation_wall_ms is None
        else round(relaxation_wall_ms, 6),
        "outer_peak_python_mib": ""
        if relaxation_peak_bytes is None
        else round(relaxation_peak_bytes / (1024 * 1024), 6),
        "reference_agreement": reference_agreement,
        "notes": case.notes,
    }


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(
    rows: Sequence[Mapping[str, Any]],
    *,
    suite: str,
    max_frontier_records: int,
) -> dict[str, Any]:
    oracle_rows = [row for row in rows if row["oracle_agreement"] != ""]
    highs_rows = [row for row in rows if row["highs_agreement"] != ""]
    analytic_rows = [row for row in rows if row["analytic_agreement"] != ""]
    relaxation_rows = [
        row for row in rows if row["outer_analytic_agreement"] != ""
    ]
    all_pass = all(bool(row["reference_agreement"]) for row in rows)
    module_path = BOUNDS / "path_frontier_dp.py"
    return {
        "generator_version": GENERATOR_VERSION,
        "suite": suite,
        "case_count": len(rows),
        "all_reference_checks_pass": all_pass,
        "exhaustive_agreements": sum(bool(row["oracle_agreement"]) for row in oracle_rows),
        "exhaustive_cases": len(oracle_rows),
        "analytic_agreements": sum(bool(row["analytic_agreement"]) for row in analytic_rows),
        "analytic_cases": len(analytic_rows),
        "highs_numerical_agreements": sum(bool(row["highs_agreement"]) for row in highs_rows),
        "highs_resolved_cases": len(highs_rows),
        "outward_relaxation_agreements": sum(
            bool(row["outer_analytic_agreement"])
            and bool(row["outer_containment"])
            and bool(row["outer_slack_valid"])
            and bool(row["outer_witness_valid"])
            for row in relaxation_rows
        ),
        "outward_relaxation_cases": len(relaxation_rows),
        "frontier_limit": max_frontier_records,
        "claim_safe_headline": (
            "The exact temporal-path DP agrees with every locked exact or analytic "
            "reference and every resolved HiGHS numerical comparator; its practical "
            "cost is governed by live-record width, active release factors, Gamma, "
            "and the exact score frontier. This is not a general MILP replacement."
            if all_pass
            else "BENCHMARK GATE FAILED: at least one locked reference check disagrees."
        ),
        "relaxed_score_status": (
            "Certified outward score relaxation is checked for exact-set "
            "containment, eta*N score slack, and sufficient endpoint-exactness witnesses; "
            "it is a bicriteria certificate, not a query FPTAS."
        ),
        "timing_note": (
            "One tracemalloc-instrumented run per DP case; timings are machine-specific "
            "and are not used for a speedup claim."
        ),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": None if scipy is None else scipy.__version__,
            "processor": platform.processor(),
        },
        "source_sha256": {
            "path_frontier_dp.py": _source_hash(module_path),
            "path_frontier_benchmark.py": _source_hash(Path(__file__).resolve()),
        },
    }


def render_markdown(summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> str:
    binary = [
        row
        for row in rows
        if row["family"] == "c4_score_frontier" and "binary" in row["case_id"]
    ]
    local = [row for row in rows if row["family"] == "local_factor_scaling"]
    width = [
        row for row in rows if row["family"] == "temporal_width_counterexample"
    ]
    gamma = [row for row in rows if row["family"] == "gamma_sweep"]
    relaxation = next(
        (row for row in rows if row["family"] == "outward_score_relaxation"),
        None,
    )
    largest_binary = max(binary, key=lambda row: int(row["node_count"])) if binary else None
    largest_width_size = max(int(row["core_count"]) for row in width) if width else 0
    width_pair = [row for row in width if int(row["core_count"]) == largest_width_size]
    grouped = max(
        (row for row in local if row["case_id"].endswith("grouped")),
        key=lambda row: int(row["factor_count"]),
        default=None,
    )
    interleaved = (
        next(
            (
                row
                for row in local
                if grouped is not None
                and row["case_id"] == grouped["case_id"].replace("grouped", "interleaved")
            ),
            None,
        )
        if grouped is not None
        else None
    )
    lines = [
        "# Exact temporal-path frontier benchmark",
        "",
        f"**Gate:** {'PASS' if summary['all_reference_checks_pass'] else 'FAIL'}",
        "",
        str(summary["claim_safe_headline"]),
        "",
        "| Check | Result |",
        "|---|---:|",
        f"| Independent exhaustive agreement | {summary['exhaustive_agreements']}/{summary['exhaustive_cases']} |",
        f"| Closed-form/analytic agreement | {summary['analytic_agreements']}/{summary['analytic_cases']} |",
        f"| Resolved HiGHS numerical agreement | {summary['highs_numerical_agreements']}/{summary['highs_resolved_cases']} |",
        f"| Certified outward-relaxation agreement | {summary['outward_relaxation_agreements']}/{summary['outward_relaxation_cases']} |",
        f"| Locked cases | {summary['case_count']} |",
        "",
        "## Parameter isolation",
        "",
    ]
    if largest_binary is not None:
        lines.append(
            "- **Exact score frontier:** the largest binary-weight disjoint-C4 case "
            f"uses schedule width {largest_binary['schedule_width']}, integer floor target "
            f"{largest_binary['capped_integer_score_target']}, and peak live frontier "
            f"{largest_binary['peak_live_records']}. Unit- and binary-encoded families "
            "separate ordinary size growth from the weakly NP-hard score coordinate."
        )
    if grouped is not None and interleaved is not None:
        lines.append(
            "- **Release-factor locality:** the same largest local-factor world has "
            f"active-factor width {grouped['max_active_factor_count']} under grouped "
            f"order and {interleaved['max_active_factor_count']} under interleaving; "
            "its exact endpoints are unchanged."
        )
    if width_pair:
        adjacent = next(row for row in width_pair if row["case_id"].endswith("adjacent"))
        nested = next(row for row in width_pair if row["case_id"].endswith("nested"))
        lines.append(
            "- **Temporal width is not degree:** the same degree-one graph has "
            f"supplied-schedule width {adjacent['schedule_width']} under adjacent "
            f"order and {nested['schedule_width']} under nested long edges; its "
            "graph pathwidth remains one."
        )
    if gamma:
        first, last = gamma[0], gamma[-1]
        lines.append(
            "- **Gamma:** the locked sweep expands the upper endpoint from "
            f"{first['dp_upper']} at Gamma={first['gamma']} to {last['dp_upper']} "
            f"at Gamma={last['gamma']}, matching the analytic interval."
        )
    if relaxation is not None:
        lines.append(
            "- **Certified score relaxation:** at eta="
            f"{relaxation['relaxation_eta']}, the exact interval "
            f"[{relaxation['dp_lower']},{relaxation['dp_upper']}] is contained in "
            f"[{relaxation['outer_lower']},{relaxation['outer_upper']}]. The observed "
            f"score shortfall {relaxation['outer_observed_maximum_shortfall']} is below "
            f"the eta*N certificate {relaxation['outer_maximum_score_shortfall']}; "
            f"lower/upper endpoint exactness is witnessed as "
            f"{str(relaxation['outer_lower_endpoint_exact_witnessed']).lower()}/"
            f"{str(relaxation['outer_upper_endpoint_exact_witnessed']).lower()}."
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "The exhaustive oracle is independent of the DP implementation. HiGHS is a "
            "floating-point numerical comparator, not an exact certificate. Peak memory "
            "is Python heap measured by `tracemalloc`; native HiGHS memory is not compared. "
            "All candidate sets, labels, factors, and schedules are declared synthetic "
            "inputs, so the benchmark says nothing about true-edge coverage or Chicago "
            "observation-operator validity.",
            "",
            f"{summary['relaxed_score_status']}",
            "",
            f"Timing protocol: {summary['timing_note']}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-frontier-records", type=int, default=500_000)
    args = parser.parse_args()
    if args.max_frontier_records < 1:
        raise ValueError("--max-frontier-records must be positive")
    cases = locked_cases(args.suite)
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index:02d}/{len(cases):02d}] {case.case_id}", flush=True)
        rows.append(
            run_case(case, max_frontier_records=args.max_frontier_records)
        )
    summary = summarize(
        rows,
        suite=args.suite,
        max_frontier_records=args.max_frontier_records,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "path_frontier_benchmark.csv"
    json_path = args.output_dir / "path_frontier_benchmark.json"
    markdown_path = args.output_dir / "PATH_FRONTIER_BENCHMARK.md"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    payload = dict(summary)
    payload["cases"] = rows
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_markdown(summary, rows), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    if not summary["all_reference_checks_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
