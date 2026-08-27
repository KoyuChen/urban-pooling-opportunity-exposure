#!/usr/bin/env python3
"""Deterministic audit and engineering profile for component convolution.

This benchmark makes no novelty, empirical, or identification claim.  It
checks the decomposed exact solver against the monolithic exact temporal-path
solver on a locked random-small-world grid, replays every attained endpoint
witness, records the minimal shared-release-factor counterexample, and profiles
an interleaved disconnected family where component separation reduces live-bag
width.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
BOUNDS = HERE.parent / "bounds"
if str(BOUNDS) not in sys.path:
    sys.path.insert(0, str(BOUNDS))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from component_frontier import (  # noqa: E402
    PATH_FRONTIER_INTERNAL_API_REVISION,
    solve_component_frontier_endpoints,
)
from path_frontier_dp import (  # noqa: E402
    CountConstraint,
    EdgeSpec,
    ExactPathProblem,
    FrontierLimitExceeded,
    NodeSpec,
    compile_temporal_path,
    solve_path_frontier_endpoints,
    validate_path_witness,
)
from path_frontier_benchmark import exhaustive_endpoints  # noqa: E402


GENERATOR_VERSION = "component-frontier-benchmark-v2"
DEFAULT_OUTPUT = HERE / "results" / "component_frontier"
RANDOM_SEED = 20260827
ORACLE_SEED = 20260828
RANDOM_CONFIGURATIONS = tuple(
    (gamma, floor)
    for gamma in (None, 0, 1, 2)
    for floor in (None, Fraction(0))
)


def _fraction_text(value: Fraction | None) -> str:
    return "" if value is None else str(value)


def _random_problem(
    rng: random.Random,
    instance: int,
) -> tuple[ExactPathProblem, tuple[str, ...], int]:
    component_count = rng.randint(1, 3)
    nodes: list[NodeSpec] = []
    edges: list[EdgeSpec] = []
    constraints: list[CountConstraint] = []
    local_orders: list[tuple[str, ...]] = []
    scores = (
        Fraction(-1),
        Fraction(-1, 2),
        Fraction(0),
        Fraction(1, 2),
        Fraction(1),
    )
    queries = (
        Fraction(-2),
        Fraction(-1, 2),
        Fraction(0),
        Fraction(1, 3),
        Fraction(2),
    )
    pairs = tuple((left, right) for left in (0, 1) for right in (0, 1))
    for component in range(component_count):
        prefix = f"r{instance:03d}:c{component}:"
        factor = ("factor", instance, component)
        core_ids = tuple(prefix + name for name in ("a", "b", "c", "d"))
        for node_id in core_ids:
            nodes.append(
                NodeSpec(
                    node_id,
                    "core",
                    (0, 1),
                    factor_contributions={0: {}, 1: {factor: 1}},
                    label_query={0: rng.choice(queries), 1: rng.choice(queries)},
                )
            )
        release_id = prefix + "release"
        nodes.append(
            NodeSpec(
                release_id,
                "context_only",
                ("none", "LOW", "HIGH"),
                factor_requirements={
                    "none": {},
                    "LOW": {factor: "LOW"},
                    "HIGH": {factor: "HIGH"},
                },
                label_query={
                    "none": rng.choice(queries),
                    "LOW": rng.choice(queries),
                    "HIGH": rng.choice(queries),
                },
            )
        )
        lower = rng.randint(0, 2)
        upper = rng.randint(max(2, lower), 4)
        constraints.append(
            CountConstraint(
                factor,
                lower,
                upper,
                low_upper=1,
                high_lower=2,
            )
        )
        for edge_name, left, right in (
            ("ab", 0, 1),
            ("cd", 2, 3),
            ("ac", 0, 2),
            ("bd", 1, 3),
        ):
            allowed = tuple(pair for pair in pairs if rng.random() < 0.75)
            if not allowed:
                allowed = (rng.choice(pairs),)
            edges.append(
                EdgeSpec(
                    prefix + edge_name,
                    core_ids[left],
                    core_ids[right],
                    omitted=bool(rng.getrandbits(1)),
                    allowed_label_pairs=allowed,
                    score_by_label_pair={pair: rng.choice(scores) for pair in allowed},
                    query_by_label_pair={pair: rng.choice(queries) for pair in allowed},
                )
            )
        local_orders.append(core_ids + (release_id,))
    interleaved_order = tuple(
        local_orders[component][position]
        for position in range(5)
        for component in range(component_count)
    )
    return (
        ExactPathProblem(tuple(nodes), tuple(edges), tuple(constraints)),
        interleaved_order,
        component_count,
    )


def run_random_audit(problem_count: int) -> dict[str, Any]:
    rng = random.Random(RANDOM_SEED)
    cases = 0
    feasible = 0
    infeasible = 0
    endpoint_agreements = 0
    witness_replays = 0
    component_counts: dict[int, int] = {}
    for instance in range(problem_count):
        problem, order, expected_components = _random_problem(rng, instance)
        component_counts[expected_components] = (
            component_counts.get(expected_components, 0) + 1
        )
        for gamma, floor in RANDOM_CONFIGURATIONS:
            monolithic = solve_path_frontier_endpoints(
                problem,
                forget_order=order,
                gamma=gamma,
                score_floor=floor,
            )
            decomposed = solve_component_frontier_endpoints(
                problem,
                forget_order=order,
                gamma=gamma,
                score_floor=floor,
            )
            cases += 1
            if (
                decomposed.status,
                decomposed.lower,
                decomposed.upper,
            ) != (
                monolithic.status,
                monolithic.lower,
                monolithic.upper,
            ):
                raise AssertionError(
                    "random audit endpoint disagreement at "
                    f"instance={instance}, gamma={gamma}, floor={floor}: "
                    f"decomposed={(decomposed.status, decomposed.lower, decomposed.upper)} "
                    f"monolithic={(monolithic.status, monolithic.lower, monolithic.upper)}"
                )
            if len(decomposed.components) != expected_components:
                raise AssertionError("incidence component count mismatch")
            endpoint_agreements += 1
            if decomposed.status == "EXACT_INFEASIBLE":
                infeasible += 1
                continue
            feasible += 1
            for solution in (
                monolithic.lower_solution,
                monolithic.upper_solution,
                decomposed.lower_solution,
                decomposed.upper_solution,
            ):
                if solution.witness is None:
                    raise AssertionError("optimal endpoint omitted its witness")
                validate_path_witness(
                    problem,
                    solution.witness,
                    gamma=gamma,
                    score_floor=floor,
                )
                if solution.objective_value != solution.witness.query_value:
                    raise AssertionError("endpoint witness query does not replay")
                witness_replays += 1
    return {
        "seed": RANDOM_SEED,
        "random_problems": problem_count,
        "resource_configurations_per_problem": len(RANDOM_CONFIGURATIONS),
        "cases": cases,
        "endpoint_agreements": endpoint_agreements,
        "feasible_cases": feasible,
        "infeasible_cases": infeasible,
        "endpoint_witness_replays": witness_replays,
        "component_count_histogram": {
            str(key): value for key, value in sorted(component_counts.items())
        },
    }


def run_independent_oracle_audit(problem_count: int) -> dict[str, Any]:
    """Compare directly with enumeration that imports no frontier recurrence."""

    rng = random.Random(ORACLE_SEED)
    cases = 0
    agreements = 0
    feasible = 0
    infeasible = 0
    witness_replays = 0
    label_assignments_examined = 0
    matching_leaves_examined = 0
    feasible_worlds = 0
    component_counts: dict[int, int] = {}
    for oracle_instance in range(problem_count):
        # Keep the independent enumeration deliberately tiny.  Rejected
        # three-component draws still advance this audit's private RNG stream.
        attempt = 0
        while True:
            problem, order, component_count = _random_problem(
                rng,
                100_000 + 100 * oracle_instance + attempt,
            )
            attempt += 1
            if component_count <= 2:
                break
        component_counts[component_count] = (
            component_counts.get(component_count, 0) + 1
        )
        for gamma, floor in RANDOM_CONFIGURATIONS:
            oracle = exhaustive_endpoints(
                problem,
                gamma=gamma,
                score_floor=floor,
            )
            decomposed = solve_component_frontier_endpoints(
                problem,
                forget_order=order,
                gamma=gamma,
                score_floor=floor,
            )
            cases += 1
            label_assignments_examined += oracle.label_assignments_examined
            matching_leaves_examined += oracle.matching_leaves_examined
            feasible_worlds += oracle.feasible_worlds
            if (
                decomposed.status,
                decomposed.lower,
                decomposed.upper,
            ) != (oracle.status, oracle.lower, oracle.upper):
                raise AssertionError(
                    "independent oracle disagreement at "
                    f"instance={oracle_instance}, gamma={gamma}, floor={floor}: "
                    f"decomposed={(decomposed.status, decomposed.lower, decomposed.upper)} "
                    f"oracle={(oracle.status, oracle.lower, oracle.upper)}"
                )
            agreements += 1
            if decomposed.status == "EXACT_INFEASIBLE":
                infeasible += 1
                continue
            feasible += 1
            for solution in (
                decomposed.lower_solution,
                decomposed.upper_solution,
            ):
                validate_path_witness(
                    problem,
                    solution.witness,
                    gamma=gamma,
                    score_floor=floor,
                )
                witness_replays += 1
    return {
        "seed": ORACLE_SEED,
        "random_problems": problem_count,
        "resource_configurations_per_problem": len(RANDOM_CONFIGURATIONS),
        "cases": cases,
        "exact_agreements": agreements,
        "feasible_cases": feasible,
        "infeasible_cases": infeasible,
        "decomposed_endpoint_witness_replays": witness_replays,
        "oracle_label_assignments_examined": label_assignments_examined,
        "oracle_matching_leaves_examined": matching_leaves_examined,
        "oracle_feasible_worlds": feasible_worlds,
        "component_count_histogram": {
            str(key): value for key, value in sorted(component_counts.items())
        },
        "oracle_kernel": (
            "independent raw-label and matching enumeration from "
            "path_frontier_benchmark.exhaustive_endpoints"
        ),
    }


def run_shared_factor_counterexample() -> dict[str, Any]:
    factor = "shared-release-cell"
    source = NodeSpec(
        "count-source",
        "context_only",
        (0, 1),
        factor_contributions={0: {}, 1: {factor: 1}},
        label_query={0: 0, 1: 1},
    )
    target = NodeSpec(
        "release-target",
        "context_only",
        ("LOW", "HIGH"),
        factor_requirements={
            "LOW": {factor: "LOW"},
            "HIGH": {factor: "HIGH"},
        },
        label_query={"LOW": 0, "HIGH": 10},
    )
    constraint = CountConstraint(
        factor,
        0,
        1,
        low_upper=0,
        high_lower=1,
    )
    problem = ExactPathProblem((source, target), (), (constraint,))
    exact = solve_component_frontier_endpoints(
        problem,
        forget_order=("count-source", "release-target"),
    )
    source_only = solve_path_frontier_endpoints(
        ExactPathProblem((source,), (), (constraint,)),
        forget_order=("count-source",),
    )
    target_only = solve_path_frontier_endpoints(
        ExactPathProblem((target,), (), (constraint,)),
        forget_order=("release-target",),
    )
    naive_upper = source_only.upper + target_only.upper
    if exact.upper != 11 or naive_upper != 1 or len(exact.components) != 1:
        raise AssertionError("shared-factor counterexample changed unexpectedly")
    return {
        "candidate_graph_components": 2,
        "incidence_components": len(exact.components),
        "exact_endpoints": [_fraction_text(exact.lower), _fraction_text(exact.upper)],
        "naive_duplicated_factor_upper": _fraction_text(naive_upper),
        "upper_witness": {
            node_id: repr(label)
            for node_id, label in exact.upper_solution.witness.label_assignments
        },
    }


def _scaling_problem(
    component_count: int,
) -> tuple[
    ExactPathProblem,
    tuple[str, ...],
    tuple[str, ...],
    int,
    int,
]:
    nodes: list[NodeSpec] = []
    edges: list[EdgeSpec] = []
    for component in range(component_count):
        prefix = f"c{component}:"
        nodes.extend(
            NodeSpec(prefix + name, "core", (0,)) for name in "abcd"
        )
        edges.extend(
            (
                EdgeSpec(prefix + "ab", prefix + "a", prefix + "b"),
                EdgeSpec(prefix + "cd", prefix + "c", prefix + "d"),
                EdgeSpec(
                    prefix + "ac",
                    prefix + "a",
                    prefix + "c",
                    score=1,
                    query=component + 1,
                    omitted=True,
                ),
                EdgeSpec(
                    prefix + "bd",
                    prefix + "b",
                    prefix + "d",
                    score=1,
                    omitted=True,
                ),
            )
        )
    interleaved_order = tuple(
        f"c{component}:{name}"
        for name in "abcd"
        for component in range(component_count)
    )
    concatenated_order = tuple(
        f"c{component}:{name}"
        for component in range(component_count)
        for name in "abcd"
    )
    required_high_components = (component_count + 2) // 3
    gamma = 2 * required_high_components
    score_floor = 4 * required_high_components
    return (
        ExactPathProblem(tuple(nodes), tuple(edges)),
        interleaved_order,
        concatenated_order,
        gamma,
        score_floor,
    )


def _run_monolithic_profile(
    problem: ExactPathProblem,
    order: tuple[str, ...],
    *,
    gamma: int,
    score_floor: int,
    frontier_limit: int,
) -> dict[str, Any]:
    schedule = compile_temporal_path(problem, order)
    start = time.perf_counter()
    try:
        result = solve_path_frontier_endpoints(
            problem,
            forget_order=order,
            gamma=gamma,
            score_floor=score_floor,
            max_frontier_records=frontier_limit,
        )
        status = result.status
        max_single_frontier_records = max(
            result.lower_solution.stats.peak_live_records,
            result.upper_solution.stats.peak_live_records,
        )
        lower = result.lower
        upper = result.upper
    except FrontierLimitExceeded as exc:
        status = "FRONTIER_LIMIT"
        max_single_frontier_records = exc.live_records
        lower = None
        upper = None
    runtime_ms = (time.perf_counter() - start) * 1000
    return {
        "schedule_width": schedule.schedule_width,
        "status": status,
        "max_single_frontier_records": max_single_frontier_records,
        "runtime_ms": round(runtime_ms, 3),
        "lower": lower,
        "upper": upper,
    }


def run_scaling_profile(
    component_counts: tuple[int, ...],
    frontier_limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for component_count in component_counts:
        (
            problem,
            interleaved_order,
            concatenated_order,
            gamma,
            score_floor,
        ) = _scaling_problem(component_count)
        interleaved = _run_monolithic_profile(
            problem,
            interleaved_order,
            gamma=gamma,
            score_floor=score_floor,
            frontier_limit=frontier_limit,
        )
        concatenated = _run_monolithic_profile(
            problem,
            concatenated_order,
            gamma=gamma,
            score_floor=score_floor,
            frontier_limit=frontier_limit,
        )

        component_start = time.perf_counter()
        decomposed = solve_component_frontier_endpoints(
            problem,
            forget_order=interleaved_order,
            gamma=gamma,
            score_floor=score_floor,
            max_frontier_records=frontier_limit,
        )
        component_ms = (time.perf_counter() - component_start) * 1000
        component_max_single = max(
            decomposed.lower_solution.stats.max_single_frontier_records,
            decomposed.upper_solution.stats.max_single_frontier_records,
        )
        component_total_terminal = max(
            decomposed.lower_solution.stats.total_component_terminal_frontier_records,
            decomposed.upper_solution.stats.total_component_terminal_frontier_records,
        )
        for label, baseline in (
            ("interleaved", interleaved),
            ("concatenated", concatenated),
        ):
            if baseline["status"] == "EXACT_OPTIMAL" and (
                baseline["lower"],
                baseline["upper"],
            ) != (decomposed.lower, decomposed.upper):
                raise AssertionError(
                    f"{label} scaling-family endpoint disagreement"
                )
        rows.append(
            {
                "components": component_count,
                "records": 4 * component_count,
                "gamma": gamma,
                "score_floor": score_floor,
                "interleaved_schedule_width": interleaved["schedule_width"],
                "concatenated_schedule_width": concatenated["schedule_width"],
                "max_component_schedule_width": max(
                    schedule.schedule_width
                    for schedule in decomposed.component_schedules
                ),
                "interleaved_monolithic_status": interleaved["status"],
                "interleaved_monolithic_max_single_frontier_records": (
                    interleaved["max_single_frontier_records"]
                ),
                "interleaved_monolithic_runtime_ms": interleaved["runtime_ms"],
                "concatenated_monolithic_status": concatenated["status"],
                "concatenated_monolithic_max_single_frontier_records": (
                    concatenated["max_single_frontier_records"]
                ),
                "concatenated_monolithic_runtime_ms": concatenated["runtime_ms"],
                "component_status": decomposed.status,
                "component_max_single_frontier_records": component_max_single,
                "component_total_terminal_frontier_records": (
                    component_total_terminal
                ),
                "component_runtime_ms": round(component_ms, 3),
                "lower": _fraction_text(decomposed.lower),
                "upper": _fraction_text(decomposed.upper),
            }
        )
    return rows


def _write_scaling_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _markdown_state_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Components | Records | Interleaved width | Interleaved max | "
        "Concatenated width | Concatenated max | Max local width | "
        "Decomposed max | Terminal total | Endpoints |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|",
    ]
    for row in rows:
        lines.append(
            "| {components} | {records} | {interleaved_schedule_width} | "
            "{interleaved_monolithic_max_single_frontier_records} | "
            "{concatenated_schedule_width} | "
            "{concatenated_monolithic_max_single_frontier_records} | "
            "{max_component_schedule_width} | "
            "{component_max_single_frontier_records} | "
            "{component_total_terminal_frontier_records} | "
            "[{lower}, {upper}] |".format(**row)
        )
    return "\n".join(lines)


def _markdown_runtime_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Components | Interleaved status | Interleaved ms | "
        "Concatenated status | Concatenated ms | Decomposed status | "
        "Decomposed ms |",
        "|---:|:---|---:|:---|---:|:---|---:|",
    ]
    for row in rows:
        lines.append(
            "| {components} | {interleaved_monolithic_status} | "
            "{interleaved_monolithic_runtime_ms:.1f} | "
            "{concatenated_monolithic_status} | "
            "{concatenated_monolithic_runtime_ms:.1f} | "
            "{component_status} | {component_runtime_ms:.1f} |".format(**row)
        )
    return "\n".join(lines)


def _write_report(
    path: Path,
    *,
    random_audit: dict[str, Any],
    oracle_audit: dict[str, Any],
    counterexample: dict[str, Any],
    scaling: list[dict[str, Any]],
    frontier_limit: int,
    canonical_evidence_sha256: str,
) -> None:
    report = f"""# Exact incidence-component frontier benchmark

This is an **algorithm-engineering** result. It applies standard exact
constraint decomposition followed by a knapsack-style, pseudo-polynomial
resource convolution. It is not claimed as new relative to generic component
decomposition, dynamic programming, or knapsack convolution, and it carries no
empirical or identification implication.

## Exact condition and proof

Construct the joint incidence graph whose vertices are records and declared
count/release factors. Candidate edges join their two endpoint records. A
record is joined to every factor that any supported label can contribute to or
can require as `LOW`/`HIGH`. Only connected components of this joint graph are
split. A shared factor therefore remains one object and forces all records in
its scope into the same component.

**Proposition.** Under the declared `ExactPathProblem` semantics, let
`C_1,...,C_k` be those incidence components. The component solver returns the
same exact feasibility status and attained query endpoints as the monolithic
temporal-frontier solver for any supplied forget order, global `Gamma`, and
global additive score floor, unless either solver explicitly raises its
declared frontier limit.

**Proof.** Every matching edge, degree constraint, label restriction, count
bound, and release requirement lies in exactly one incidence component. Thus a
global structurally feasible world restricts uniquely to one feasible local
world per component, and the union of arbitrary feasible local worlds is a
global structurally feasible world. Omitted-edge use, per-core-incidence score,
and query value are additive across that bijection. The convolution retains
the nondominated triples `(gamma used, shifted score, query)`. A triple with no
more Gamma use, no less score, and no worse query can replace a dominated
triple under every remaining component; induction proves the pruning exact.
The single global score shift is valid because every core has degree one, so it
adds the same constant once per core. Finally, local witnesses are unioned and
replayed against the original unsplit problem, so both endpoints are attained.

## Why candidate-graph components alone are wrong

The locked two-record counterexample has no candidate edge, so its candidate
graph has two singleton components. One record chooses whether to contribute
zero or one to a shared release factor. The other chooses a `LOW` or `HIGH`
release label; `LOW` requires count zero and `HIGH` requires count one. Its
query contribution is 0 under `LOW` and 10 under `HIGH`, while the count source
contributes query 1 when its count is one. The true attained interval is
`[{counterexample['exact_endpoints'][0]}, {counterexample['exact_endpoints'][1]}]`.
Naively duplicating and checking the factor inside the two candidate-graph
components makes `HIGH` locally impossible and reports the false upper endpoint
{counterexample['naive_duplicated_factor_upper']}. The joint incidence graph correctly
has {counterexample['incidence_components']} component.

## Locked same-kernel cross-check

- Generator: `{GENERATOR_VERSION}`; seed `{random_audit['seed']}`.
- Random problems: {random_audit['random_problems']}; each is solved at all
  {random_audit['resource_configurations_per_problem']} locked `(Gamma, score floor)`
  combinations.
- Exact endpoint agreements: **{random_audit['endpoint_agreements']}/{random_audit['cases']}**
  ({random_audit['feasible_cases']} feasible;
  {random_audit['infeasible_cases']} infeasible).
- Replayed monolithic/decomposed endpoint witnesses:
  **{random_audit['endpoint_witness_replays']}**.
- Canonical evidence SHA-256: `{canonical_evidence_sha256}`. This projection
  excludes Python/platform labels and all runtime columns, but retains every
  generator, status, endpoint, width, state-count, and witness-audit field.

These 160 comparisons are regression cross-checks, not independent-oracle
evidence: the two solvers intentionally share validated preparation and local
transition primitives. Every comparison uses exact `Fraction` endpoints.
Witness replay recomputes all labels, matching degrees, allowed label pairs,
factor counts, release requirements, Gamma use, raw score, and additive query
from the original problem.

## Independent exhaustive-oracle battery

The second battery compares the decomposed solver directly with raw label and
matching enumeration that imports no temporal-frontier state or transition
recurrence.

- Generator seed: `{oracle_audit['seed']}`; random problems:
  {oracle_audit['random_problems']}.
- Exact oracle agreements: **{oracle_audit['exact_agreements']}/{oracle_audit['cases']}**
  ({oracle_audit['feasible_cases']} feasible;
  {oracle_audit['infeasible_cases']} infeasible).
- Enumeration work: {oracle_audit['oracle_label_assignments_examined']:,} label
  assignments, {oracle_audit['oracle_matching_leaves_examined']:,} complete
  matching leaves, and {oracle_audit['oracle_feasible_worlds']:,} feasible
  worlds across resource configurations.
- Replayed decomposed endpoint witnesses:
  **{oracle_audit['decomposed_endpoint_witness_replays']}**.

## Interleaved-component operational profile

The deterministic family has disconnected four-core cycles. It reports both
the supplied time order interleaved across components and a legal monolithic
baseline whose order concatenates complete components. Each local and
concatenated schedule has width two; only the interleaved monolithic schedule
accumulates live records from several components. The score floor and Gamma
budget are global and bind how many components use their high-score matching.
The live-frontier limit is {frontier_limit:,}.

{_markdown_state_table(scaling)}

Every `max` column is the largest number of records in any **single** live
frontier, not a memory peak. `Terminal total` sums the component-terminal
frontier records retained before convolution. Records contain variable-sized
complete witnesses, so neither count is a heap/RSS estimate.

{_markdown_runtime_table(scaling)}

Runtime is one machine-local Python run and is diagnostic only. The exact state
counters, width, status, and endpoints are the reproducible evidence. A
`FRONTIER_LIMIT` row is not an infeasibility or approximate answer.
The concatenated baseline shows that a caller who is free to reorder complete
components can recover much of the same structural benefit in the monolithic
solver. The component layer automates that safe separation and makes the
global resource convolution explicit; the table is not evidence of a universal
speedup over the best possible monolithic order.

## Boundary and maintenance contract

This layer does not help a single joint incidence component. Local work remains
exponential in component path width and label support. The global convolution
is pseudo-polynomial in the capped integer score target and Gamma and can itself
be the bottleneck; this is not a removal of the score-resource hardness. The
implementation is pinned to `{PATH_FRONTIER_INTERNAL_API_REVISION}` and checks
selected reused callable/dataclass layouts before solving. Selected layout
drift therefore fails explicitly; semantic changes with the same layout still
require the same-kernel and independent-oracle tests above.
"""
    path.write_text(report, encoding="utf-8")


def _canonical_evidence_sha256(result: dict[str, Any]) -> str:
    """Hash deterministic evidence while excluding machine-dependent fields."""

    projection = json.loads(json.dumps(result))
    projection.pop("python", None)
    projection.pop("platform", None)
    projection.pop("canonical_evidence_sha256", None)
    for row in projection["scaling_profile"]:
        for key in tuple(row):
            if key.endswith("_runtime_ms"):
                row.pop(key)
    payload = json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-problems", type=int, default=20)
    parser.add_argument("--oracle-problems", type=int, default=24)
    parser.add_argument("--frontier-limit", type=int, default=10_000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.random_problems < 1:
        raise ValueError("random-problems must be positive")
    if args.oracle_problems < 1:
        raise ValueError("oracle-problems must be positive")
    if args.frontier_limit < 1:
        raise ValueError("frontier-limit must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    random_audit = run_random_audit(args.random_problems)
    oracle_audit = run_independent_oracle_audit(args.oracle_problems)
    counterexample = run_shared_factor_counterexample()
    scaling = run_scaling_profile(
        (2, 4, 6, 8, 10, 12, 13),
        args.frontier_limit,
    )
    result = {
        "generator_version": GENERATOR_VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "path_frontier_internal_api_revision": PATH_FRONTIER_INTERNAL_API_REVISION,
        "random_audit": random_audit,
        "independent_oracle_audit": oracle_audit,
        "shared_factor_counterexample": counterexample,
        "frontier_limit": args.frontier_limit,
        "scaling_profile": scaling,
    }
    result["canonical_evidence_sha256"] = _canonical_evidence_sha256(result)
    (args.output_dir / "component_frontier_benchmark.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_scaling_csv(
        scaling,
        args.output_dir / "component_frontier_scaling.csv",
    )
    _write_report(
        args.output_dir / "COMPONENT_FRONTIER_BENCHMARK.md",
        random_audit=random_audit,
        oracle_audit=oracle_audit,
        counterexample=counterexample,
        scaling=scaling,
        frontier_limit=args.frontier_limit,
        canonical_evidence_sha256=result["canonical_evidence_sha256"],
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
