#!/usr/bin/env python3
"""Bounded operational profile for the temporal frontier DP.

This is an engineering capacity-planning harness, not a scientific validation
suite.  It builds deterministic synthetic temporal markets and varies one
declared workload axis at a time: record count, maximum candidate degree,
simultaneously active privacy factors, joint-label support, score threshold,
and ``Gamma``.  Every solve runs in a fresh worker process with both a hard
wall-clock timeout and the solver's live-frontier limit.

Three deterministic order constructors are compiled for every case: declared
input order, temporal-adjacent order, and a release-aware greedy order.  The
timed worker uses the smallest live-record bag among those three schedules,
then the active-factor count and a fixed tie break.  This is candidate
selection, not an exact order search, and no heuristic is called optimal.

The reported structural quantities describe each supplied temporal schedule:
``peak_active_records`` is the largest live record bag and
``peak_active_factors`` is the largest simultaneously active factor set.
``schedule_width`` is simply ``max(0, peak_active_records - 1)``.  No claim is
made that the schedule is optimal for the candidate graph.

Memory fields are deliberately labelled as proxies.  ``peak_python_heap_mib``
is the peak traced Python allocation during the solve.  ``peak_worker_rss_mib``
is the parent's sampled resident-set high-water mark for the isolated worker;
it includes interpreter and imported-module overhead and remains available for
workers stopped by the wall-clock timeout when ``/proc`` is present.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import io
import json
import multiprocessing as mp
import os
import platform
import queue
import resource
import sys
import threading
import time
import traceback
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Sequence


HERE = Path(__file__).resolve().parent
BOUNDS = HERE.parents[1] / "bounds"
if str(BOUNDS) not in sys.path:
    sys.path.insert(0, str(BOUNDS))

from path_frontier_dp import (  # noqa: E402
    CountConstraint,
    EdgeSpec,
    ExactPathProblem,
    FrontierLimitExceeded,
    NodeSpec,
    PathSchedule,
    compile_temporal_path,
    solve_path_frontier_endpoints,
)


GENERATOR_VERSION = "temporal-frontier-runtime-profile-v2"
DEFAULT_OUTPUT = HERE.parent / "results" / "runtime_profile"
MIB = 1024 * 1024
ORDER_NAMES = (
    "input_natural",
    "temporal_adjacent",
    "release_aware_greedy",
)


@dataclass(frozen=True)
class MarketSpec:
    """One deterministic synthetic temporal-market workload."""

    case_id: str
    axis: str
    axis_value: str
    core_records: int
    requested_max_degree: int
    factor_overlap: int
    label_support: int
    score_floor_per_core: int | None
    gamma: int | None

    @property
    def record_count(self) -> int:
        return 2 * self.core_records

    @property
    def score_floor(self) -> int | None:
        if self.score_floor_per_core is None:
            return None
        return self.score_floor_per_core * self.core_records


@dataclass(frozen=True)
class ScheduleCandidate:
    """One constructed order and its validated, auditable schedule."""

    name: str
    forget_order: tuple[str, ...]
    schedule: PathSchedule


@dataclass(frozen=True)
class CompiledCase:
    spec: MarketSpec
    problem: ExactPathProblem
    schedule_candidates: tuple[ScheduleCandidate, ...]
    selected_order_name: str
    instance_sha256: str
    edge_count: int
    actual_max_degree: int

    @property
    def selected_candidate(self) -> ScheduleCandidate:
        return next(
            candidate
            for candidate in self.schedule_candidates
            if candidate.name == self.selected_order_name
        )

    @property
    def schedule(self) -> PathSchedule:
        return self.selected_candidate.schedule


def _spec(
    case_id: str,
    axis: str,
    axis_value: object,
    *,
    core_records: int = 7,
    degree: int = 3,
    factors: int = 1,
    labels: int = 2,
    score_per_core: int | None = 3,
    gamma: int | None = 2,
) -> MarketSpec:
    return MarketSpec(
        case_id=case_id,
        axis=axis,
        axis_value=str(axis_value),
        core_records=core_records,
        requested_max_degree=degree,
        factor_overlap=factors,
        label_support=labels,
        score_floor_per_core=score_per_core,
        gamma=gamma,
    )


def workload_specs(suite: str) -> tuple[MarketSpec, ...]:
    """Return the locked one-axis-at-a-time workload matrix."""

    if suite not in {"quick", "extended"}:
        raise ValueError("suite must be 'quick' or 'extended'")
    if suite == "quick":
        record_sizes = (6, 10, 14, 18)
        degrees = (1, 3, 5)
        overlaps = (0, 1, 2, 3)
        supports = (1, 2, 3, 4)
        score_levels: tuple[int | None, ...] = (None, 2, 3, 4)
        gammas: tuple[int | None, ...] = (None, 0, 2, 4)
    else:
        record_sizes = (6, 10, 14, 18, 24, 32)
        degrees = (1, 3, 5, 7)
        overlaps = (0, 1, 2, 3, 4, 5)
        supports = (1, 2, 3, 4, 5)
        score_levels = (None, 1, 2, 3, 4)
        gammas = (None, 0, 2, 4, 6, 8)

    cases: list[MarketSpec] = []
    for records in record_sizes:
        cases.append(
            _spec(
                f"records_n{records:03d}",
                "records",
                records,
                core_records=records // 2,
            )
        )
    for degree in degrees:
        cases.append(
            _spec(
                f"degree_d{degree:02d}",
                "candidate_degree",
                degree,
                degree=degree,
            )
        )
    for overlap in overlaps:
        cases.append(
            _spec(
                f"factors_overlap{overlap:02d}",
                "factor_overlap",
                overlap,
                factors=overlap,
            )
        )
    for support in supports:
        cases.append(
            _spec(
                f"labels_d{support:02d}",
                "label_support",
                support,
                core_records=6,
                labels=support,
            )
        )
    for score_level in score_levels:
        name = "none" if score_level is None else f"per_core_{score_level}"
        cases.append(
            _spec(
                f"score_{name}",
                "score_threshold",
                name,
                score_per_core=score_level,
            )
        )
    for gamma in gammas:
        name = "unbounded" if gamma is None else str(gamma)
        cases.append(
            _spec(
                f"gamma_{name}",
                "gamma",
                name,
                gamma=gamma,
            )
        )
    return tuple(cases)


def _validate_spec(spec: MarketSpec) -> None:
    if spec.core_records < 2:
        raise ValueError("core_records must be at least two")
    if spec.requested_max_degree < 1 or spec.requested_max_degree % 2 != 1:
        raise ValueError("requested_max_degree must be a positive odd integer")
    if spec.requested_max_degree > 2 * spec.core_records - 1:
        raise ValueError("requested_max_degree is too large for this market")
    if not 0 <= spec.factor_overlap <= spec.core_records // 2:
        raise ValueError("factor_overlap must fit disjoint nested factor endpoints")
    if spec.label_support < 1:
        raise ValueError("label_support must be positive")
    if spec.score_floor_per_core is not None and not (
        0 <= spec.score_floor_per_core <= 4
    ):
        raise ValueError("score_floor_per_core must be between zero and four")
    if spec.gamma is not None and spec.gamma < 0:
        raise ValueError("gamma must be nonnegative")


def build_temporal_market(
    spec: MarketSpec,
) -> ExactPathProblem:
    """Build a banded bipartite market with a deliberately plain input order.

    There is one core and one buffer record at every synthetic time index.  A
    core can match buffers within the declared temporal radius, so diagonal
    edges guarantee feasibility while off-diagonal edges are marked omitted
    and consume ``Gamma`` when it is active.  Edge score falls with temporal
    distance; the score floor is therefore an explicit retained-quality load.

    Privacy factors use nested, overlapping scopes.  Factor ``f`` touches the
    core records at indices ``f`` and ``m-1-f`` and requires at least one of
    their labels to contribute.  Consequently the requested factor-overlap
    sweep translates into auditable co-active factor coordinates.
    """

    _validate_spec(spec)
    m = spec.core_records
    labels = tuple(range(spec.label_support))
    factor_names = tuple(f"privacy_{index:02d}" for index in range(spec.factor_overlap))

    factor_nodes: dict[str, tuple[str, str]] = {}
    for index, factor in enumerate(factor_names):
        factor_nodes[factor] = (f"c{index:03d}", f"c{m - 1 - index:03d}")

    core_nodes: list[NodeSpec] = []
    buffer_nodes: list[NodeSpec] = []
    for index in range(m):
        core_id = f"c{index:03d}"
        contributions: dict[int, dict[str, int]] = {}
        for label in labels:
            label_contributions = {
                factor: 1
                for factor, endpoints in factor_nodes.items()
                if core_id in endpoints and label % 2 == 0
            }
            contributions[label] = label_contributions
        core_nodes.append(
            NodeSpec(
                node_id=core_id,
                role="core",
                label_support=labels,
                factor_contributions=contributions,
                label_query={label: label * (1 + index % 3) for label in labels},
            )
        )
        buffer_id = f"b{index:03d}"
        buffer_nodes.append(
            NodeSpec(
                node_id=buffer_id,
                role="buffer",
                label_support=labels,
                label_query={label: -(label * (1 + index % 2)) for label in labels},
            )
        )

    radius = (spec.requested_max_degree - 1) // 2
    edges: list[EdgeSpec] = []
    for core_index in range(m):
        lower = max(0, core_index - radius)
        upper = min(m, core_index + radius + 1)
        for buffer_index in range(lower, upper):
            distance = abs(core_index - buffer_index)
            score = max(1, 4 - distance)
            query = 10 * distance + ((2 * core_index + buffer_index) % 5)
            edges.append(
                EdgeSpec(
                    edge_id=f"e_c{core_index:03d}_b{buffer_index:03d}",
                    u=f"c{core_index:03d}",
                    v=f"b{buffer_index:03d}",
                    score=score,
                    query=query,
                    omitted=distance > 0,
                )
            )

    constraints = tuple(
        CountConstraint(factor=factor, lower=1, upper=2)
        for factor in factor_names
    )
    # Grouped roles emulate an ingestion order with no locality guarantee.  The
    # automatic constructors below recover temporal adjacency from record IDs.
    nodes = tuple(core_nodes + buffer_nodes)
    return ExactPathProblem(nodes, tuple(edges), constraints)


def _temporal_key(node_id: str) -> tuple[int, int, str]:
    """Deterministic synthetic time/role key used only by this workload family."""

    try:
        time_index = int(node_id[1:])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"synthetic node id has no time index: {node_id!r}") from exc
    role_rank = 0 if node_id.startswith("c") else 1
    return time_index, role_rank, node_id


def input_natural_order(problem: ExactPathProblem) -> tuple[str, ...]:
    """Retain the declared input record order without optimization."""

    return tuple(node.node_id for node in problem.nodes)


def temporal_adjacent_order(problem: ExactPathProblem) -> tuple[str, ...]:
    """Place same-time core/buffer records together in deterministic time order."""

    return tuple(sorted((node.node_id for node in problem.nodes), key=_temporal_key))


def _factor_scopes(problem: ExactPathProblem) -> dict[object, frozenset[str]]:
    scoped_nodes: dict[object, set[str]] = {
        constraint.factor: set() for constraint in problem.count_constraints
    }
    for node in problem.nodes:
        support = tuple(node.label_support)
        for label in support:
            for factor, contribution in (node.factor_contributions or {}).get(
                label, {}
            ).items():
                if contribution:
                    scoped_nodes[factor].add(node.node_id)
            for factor in (node.factor_requirements or {}).get(label, {}):
                scoped_nodes[factor].add(node.node_id)
    return {
        factor: frozenset(node_ids)
        for factor, node_ids in scoped_nodes.items()
        if node_ids
    }


def release_aware_greedy_order(problem: ExactPathProblem) -> tuple[str, ...]:
    """Construct a deterministic order from live-record and factor projections.

    At every step, the heuristic simulates which not-yet-introduced neighbours
    would enter the live record bag.  It also projects factors that would be
    active during those introductions and factors left open afterwards.  The
    lexicographic key minimizes a simple combined load proxy, then factor load,
    record load, temporal displacement, and node ID.  This is a heuristic; the
    compiled width is exact for the resulting order but is not claimed to be a
    globally minimum schedule width.
    """

    node_ids = tuple(node.node_id for node in problem.nodes)
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in problem.edges:
        adjacency[edge.u].add(edge.v)
        adjacency[edge.v].add(edge.u)
    factor_scopes = _factor_scopes(problem)
    remaining = set(node_ids)
    introduced: set[str] = set()
    active: set[str] = set()
    order: list[str] = []
    previous_time: int | None = None

    while remaining:
        ranked: list[
            tuple[tuple[int, int, int, int, int, int, str], str, set[str]]
        ] = []
        for node_id in remaining:
            future_neighbours = adjacency[node_id] & (remaining - {node_id})
            newly_introduced = ({node_id} | future_neighbours) - introduced
            live_during = active | newly_introduced
            introduced_after = introduced | newly_introduced
            active_factor_count = 0
            open_factor_count = 0
            closed_factor_count = 0
            for scope in factor_scopes.values():
                was_resolved = scope <= introduced
                is_resolved = scope <= introduced_after
                if not was_resolved and scope & introduced_after:
                    active_factor_count += 1
                if scope & introduced_after and not is_resolved:
                    open_factor_count += 1
                if not was_resolved and is_resolved:
                    closed_factor_count += 1
            time_index, role_rank, _stable = _temporal_key(node_id)
            displacement = (
                0 if previous_time is None else abs(time_index - previous_time)
            )
            # A factor coordinate and a live labelled record both multiply the
            # state bound.  The sum is only a deterministic construction proxy.
            combined_load = len(live_during) + active_factor_count
            key = (
                combined_load,
                active_factor_count,
                open_factor_count,
                len(live_during),
                -closed_factor_count,
                displacement,
                f"{role_rank}:{node_id}",
            )
            ranked.append((key, node_id, newly_introduced))
        _key, chosen, newly_introduced = min(ranked, key=lambda item: item[0])
        introduced.update(newly_introduced)
        active.update(newly_introduced)
        active.discard(chosen)
        remaining.remove(chosen)
        order.append(chosen)
        previous_time = _temporal_key(chosen)[0]
    return tuple(order)


def construct_schedule_candidates(
    problem: ExactPathProblem,
) -> tuple[ScheduleCandidate, ...]:
    """Compile and validate all deterministic order constructors."""

    orders = {
        "input_natural": input_natural_order(problem),
        "temporal_adjacent": temporal_adjacent_order(problem),
        "release_aware_greedy": release_aware_greedy_order(problem),
    }
    if tuple(orders) != ORDER_NAMES:
        raise AssertionError("schedule constructor registry changed unexpectedly")
    return tuple(
        ScheduleCandidate(
            name=name,
            forget_order=forget_order,
            schedule=compile_temporal_path(problem, forget_order),
        )
        for name, forget_order in orders.items()
    )


def compile_case(spec: MarketSpec) -> CompiledCase:
    problem = build_temporal_market(spec)
    candidates = construct_schedule_candidates(problem)
    tie_priority = {
        "release_aware_greedy": 0,
        "temporal_adjacent": 1,
        "input_natural": 2,
    }
    selected = min(
        candidates,
        key=lambda candidate: (
            candidate.schedule.max_bag_size,
            candidate.schedule.max_active_factor_count,
            tie_priority[candidate.name],
        ),
    )
    degrees = {node.node_id: 0 for node in problem.nodes}
    for edge in problem.edges:
        degrees[edge.u] += 1
        degrees[edge.v] += 1
    declared = (
        GENERATOR_VERSION,
        spec,
        problem,
        tuple((candidate.name, candidate.forget_order) for candidate in candidates),
        selected.name,
    )
    instance_hash = hashlib.sha256(repr(declared).encode("utf-8")).hexdigest()
    return CompiledCase(
        spec=spec,
        problem=problem,
        schedule_candidates=candidates,
        selected_order_name=selected.name,
        instance_sha256=instance_hash,
        edge_count=len(problem.edges),
        actual_max_degree=max(degrees.values(), default=0),
    )


def _fraction_text(value: Fraction | None) -> str:
    return "" if value is None else str(value)


def _solve_worker(
    result_queue: Any,
    compiled: CompiledCase,
    max_frontier_records: int,
    heartbeat_python_bytes: Any,
    heartbeat_rss_bytes: Any,
    heartbeat_seconds: float,
) -> None:
    """Solve one case and return only small, serialization-safe telemetry."""

    payload: dict[str, Any]
    gc.collect()
    tracemalloc.start()
    monitor_stop = threading.Event()

    def monitor_memory() -> None:
        while not monitor_stop.is_set():
            _current, peak_python_bytes = tracemalloc.get_traced_memory()
            heartbeat_python_bytes.value = max(
                heartbeat_python_bytes.value, peak_python_bytes
            )
            peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            current_rss_bytes = (
                peak_rss if sys.platform == "darwin" else peak_rss * 1024
            )
            heartbeat_rss_bytes.value = max(
                heartbeat_rss_bytes.value, current_rss_bytes
            )
            monitor_stop.wait(heartbeat_seconds)

    monitor = threading.Thread(
        target=monitor_memory,
        name="temporal-profile-memory-monitor",
        daemon=True,
    )
    monitor.start()
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    try:
        result = solve_path_frontier_endpoints(
            compiled.problem,
            schedule=compiled.schedule,
            gamma=compiled.spec.gamma,
            score_floor=compiled.spec.score_floor,
            max_frontier_records=max_frontier_records,
        )
        lower_stats = result.lower_solution.stats
        upper_stats = result.upper_solution.stats
        payload = {
            "run_status": "RESOLVED",
            "resolved": True,
            "solver_status": result.status,
            "lower": _fraction_text(result.lower),
            "upper": _fraction_text(result.upper),
            "capped_integer_score_target": result.capped_integer_score_target,
            "peak_frontier_states": max(
                lower_stats.peak_live_records,
                upper_stats.peak_live_records,
            ),
            "introduced_frontier_states": (
                lower_stats.introduced_states + upper_stats.introduced_states
            ),
            "accepted_frontier_records": (
                lower_stats.accepted_records + upper_stats.accepted_records
            ),
            "dominance_pruned_records": (
                lower_stats.dominance_pruned_records
                + upper_stats.dominance_pruned_records
            ),
            "transition_count": (
                lower_stats.transition_count + upper_stats.transition_count
            ),
            "status_detail": "",
        }
    except FrontierLimitExceeded as exc:
        payload = {
            "run_status": "FRONTIER_LIMIT",
            "resolved": False,
            "solver_status": "",
            "lower": "",
            "upper": "",
            "capped_integer_score_target": "",
            "peak_frontier_states": exc.live_records,
            "introduced_frontier_states": "",
            "accepted_frontier_records": "",
            "dominance_pruned_records": "",
            "transition_count": "",
            "status_detail": str(exc),
        }
    except BaseException as exc:  # keep the matrix running and expose the error
        payload = {
            "run_status": "ERROR",
            "resolved": False,
            "solver_status": "",
            "lower": "",
            "upper": "",
            "capped_integer_score_target": "",
            "peak_frontier_states": "",
            "introduced_frontier_states": "",
            "accepted_frontier_records": "",
            "dominance_pruned_records": "",
            "transition_count": "",
            "status_detail": "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip(),
        }
    finally:
        monitor_stop.set()
        monitor.join(timeout=max(0.1, 2 * heartbeat_seconds))
        payload["solver_cpu_ms"] = round(
            (time.process_time_ns() - cpu_start) / 1_000_000, 6
        )
        payload["solver_wall_ms"] = round(
            (time.perf_counter_ns() - wall_start) / 1_000_000, 6
        )
        _current, peak_python_bytes = tracemalloc.get_traced_memory()
        heartbeat_python_bytes.value = max(
            heartbeat_python_bytes.value, peak_python_bytes
        )
        tracemalloc.stop()
        payload["peak_python_heap_mib"] = round(peak_python_bytes / MIB, 6)
        # Linux reports KiB and macOS reports bytes.  This child-side high-water
        # mark complements parent sampling in runtimes where child PIDs are not
        # visible through the parent's procfs mount.
        peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_rss_bytes = peak_rss if sys.platform == "darwin" else peak_rss * 1024
        heartbeat_rss_bytes.value = max(
            heartbeat_rss_bytes.value, peak_rss_bytes
        )
        payload["worker_highwater_rss_mib"] = round(peak_rss_bytes / MIB, 6)
    result_queue.put(payload)


def _read_linux_rss_bytes(pid: int) -> int | None:
    """Return current RSS from procfs; unavailable on non-Linux platforms."""

    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            fields = line.split()
            if len(fields) >= 2:
                return int(fields[1]) * 1024
    return None


def _base_row(compiled: CompiledCase) -> dict[str, Any]:
    spec = compiled.spec
    candidates = {
        candidate.name: candidate for candidate in compiled.schedule_candidates
    }

    def candidate_metric(name: str, metric: str) -> int:
        schedule = candidates[name].schedule
        return int(getattr(schedule, metric))

    return {
        "case_id": spec.case_id,
        "axis": spec.axis,
        "axis_value": spec.axis_value,
        "instance_sha256": compiled.instance_sha256,
        "record_count": spec.record_count,
        "core_record_count": spec.core_records,
        "buffer_record_count": spec.core_records,
        "edge_count": compiled.edge_count,
        "requested_max_degree": spec.requested_max_degree,
        "actual_max_degree": compiled.actual_max_degree,
        "factor_count": spec.factor_overlap,
        "requested_factor_overlap": spec.factor_overlap,
        "label_support": spec.label_support,
        "score_floor_per_core": (
            "" if spec.score_floor_per_core is None else spec.score_floor_per_core
        ),
        "score_floor": "" if spec.score_floor is None else spec.score_floor,
        "gamma": "" if spec.gamma is None else spec.gamma,
        "selected_order": compiled.selected_order_name,
        "selection_scope": "best_of_three_declared_candidates",
        "input_certified_schedule_width": candidate_metric(
            "input_natural", "schedule_width"
        ),
        "adjacent_certified_schedule_width": candidate_metric(
            "temporal_adjacent", "schedule_width"
        ),
        "release_greedy_certified_schedule_width": candidate_metric(
            "release_aware_greedy", "schedule_width"
        ),
        "input_peak_active_records": candidate_metric(
            "input_natural", "max_bag_size"
        ),
        "adjacent_peak_active_records": candidate_metric(
            "temporal_adjacent", "max_bag_size"
        ),
        "release_greedy_peak_active_records": candidate_metric(
            "release_aware_greedy", "max_bag_size"
        ),
        "input_peak_active_factors": candidate_metric(
            "input_natural", "max_active_factor_count"
        ),
        "adjacent_peak_active_factors": candidate_metric(
            "temporal_adjacent", "max_active_factor_count"
        ),
        "release_greedy_peak_active_factors": candidate_metric(
            "release_aware_greedy", "max_active_factor_count"
        ),
        "action_count": len(compiled.schedule.actions),
        "peak_active_records": compiled.schedule.max_bag_size,
        "schedule_width": compiled.schedule.schedule_width,
        "peak_active_factors": compiled.schedule.max_active_factor_count,
        "max_factor_count_cap": max(
            (cap for _factor, cap in compiled.schedule.factor_count_caps),
            default=0,
        ),
    }


def run_case_bounded(
    compiled: CompiledCase,
    *,
    context: Any,
    timeout_seconds: float,
    max_frontier_records: int,
    rss_sample_ms: float,
) -> dict[str, Any]:
    """Run one isolated solve and enforce its wall-clock budget."""

    result_queue = context.Queue(maxsize=1)
    heartbeat_python_bytes = context.Value("Q", 0)
    heartbeat_rss_bytes = context.Value("Q", 0)
    process = context.Process(
        target=_solve_worker,
        args=(
            result_queue,
            compiled,
            max_frontier_records,
            heartbeat_python_bytes,
            heartbeat_rss_bytes,
            rss_sample_ms / 1_000,
        ),
        name=f"temporal-profile-{compiled.spec.case_id}",
    )
    parent_start = time.perf_counter()
    process.start()
    deadline = parent_start + timeout_seconds
    peak_rss_bytes: int | None = None
    poll_seconds = rss_sample_ms / 1_000
    timed_out = False
    while process.is_alive():
        rss_bytes = _read_linux_rss_bytes(process.pid)
        if rss_bytes is not None:
            peak_rss_bytes = max(peak_rss_bytes or 0, rss_bytes)
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            timed_out = True
            break
        process.join(min(poll_seconds, remaining))

    if timed_out:
        process.terminate()
        process.join(1.0)
        if process.is_alive():
            process.kill()
            process.join(1.0)
    else:
        process.join()
    parent_wall_ms = round((time.perf_counter() - parent_start) * 1_000, 6)

    row = _base_row(compiled)
    if timed_out:
        worker_payload: dict[str, Any] = {
            "run_status": "TIMEOUT",
            "resolved": False,
            "solver_status": "",
            "lower": "",
            "upper": "",
            "capped_integer_score_target": "",
            "peak_frontier_states": "",
            "introduced_frontier_states": "",
            "accepted_frontier_records": "",
            "dominance_pruned_records": "",
            "transition_count": "",
            "solver_cpu_ms": "",
            "solver_wall_ms": "",
            "peak_python_heap_mib": round(
                heartbeat_python_bytes.value / MIB, 6
            ),
            "worker_highwater_rss_mib": round(
                heartbeat_rss_bytes.value / MIB, 6
            ),
            "status_detail": f"worker exceeded {timeout_seconds:g} seconds",
        }
    else:
        try:
            worker_payload = result_queue.get(timeout=1.0)
        except queue.Empty:
            worker_payload = {
                "run_status": "ERROR",
                "resolved": False,
                "solver_status": "",
                "lower": "",
                "upper": "",
                "capped_integer_score_target": "",
                "peak_frontier_states": "",
                "introduced_frontier_states": "",
                "accepted_frontier_records": "",
                "dominance_pruned_records": "",
                "transition_count": "",
                "solver_cpu_ms": "",
                "solver_wall_ms": "",
                "peak_python_heap_mib": round(
                    heartbeat_python_bytes.value / MIB, 6
                ),
                "worker_highwater_rss_mib": round(
                    heartbeat_rss_bytes.value / MIB, 6
                ),
                "status_detail": (
                    "worker exited without telemetry "
                    f"(exit code {process.exitcode})"
                ),
            }
    row.update(worker_payload)
    row["parent_wall_ms"] = parent_wall_ms
    # This comparable bounded-case runtime includes fresh-worker startup.  The
    # solver-only wall and CPU times remain separate CSV/JSON fields.
    row["reported_runtime_ms"] = parent_wall_ms
    sampled_rss_mib = (
        None if peak_rss_bytes is None else round(peak_rss_bytes / MIB, 6)
    )
    child_rss_mib = worker_payload["worker_highwater_rss_mib"]
    rss_candidates = [
        value
        for value in (sampled_rss_mib, child_rss_mib)
        if isinstance(value, (int, float))
    ]
    row["peak_worker_rss_mib"] = max(rss_candidates) if rss_candidates else ""
    row["worker_exit_code"] = process.exitcode
    row["timeout_seconds"] = timeout_seconds
    row["frontier_limit"] = max_frontier_records
    result_queue.close()
    result_queue.join_thread()
    return row


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(
    rows: Sequence[dict[str, Any]],
    *,
    suite: str,
    timeout_seconds: float,
    max_frontier_records: int,
    rss_sample_ms: float,
) -> dict[str, Any]:
    status_counts = {
        status: sum(row["run_status"] == status for row in rows)
        for status in ("RESOLVED", "FRONTIER_LIMIT", "TIMEOUT", "ERROR")
    }
    resolved_rows = [row for row in rows if row["resolved"]]
    frontier_rows = [
        row for row in rows if isinstance(row["peak_frontier_states"], int)
    ]
    runtime_rows = [
        row
        for row in rows
        if isinstance(row["reported_runtime_ms"], (int, float))
    ]
    heap_rows = [
        row
        for row in rows
        if isinstance(row["peak_python_heap_mib"], (int, float))
    ]
    rss_rows = [
        row
        for row in rows
        if isinstance(row["peak_worker_rss_mib"], (int, float))
    ]
    selected_order_counts = {
        name: sum(row["selected_order"] == name for row in rows)
        for name in ORDER_NAMES
    }

    def largest(
        candidates: Sequence[dict[str, Any]], key: str
    ) -> dict[str, Any] | None:
        if not candidates:
            return None
        row = max(candidates, key=lambda item: item[key])
        return {"case_id": row["case_id"], "value": row[key]}

    return {
        "profile_kind": "operational_scaling_profile",
        "scientific_validation": False,
        "generator_version": GENERATOR_VERSION,
        "suite": suite,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": len(rows),
        "status_counts": status_counts,
        "resolved_fraction": (
            0.0 if not rows else round(len(resolved_rows) / len(rows), 6)
        ),
        "case_timeout_seconds": timeout_seconds,
        "max_frontier_records": max_frontier_records,
        "rss_sample_ms": rss_sample_ms,
        "schedule_constructors": list(ORDER_NAMES),
        "selected_order_counts": selected_order_counts,
        "order_search_exact": False,
        "order_selection_scope": "three deterministic declared candidates",
        "largest_observed_frontier": largest(
            frontier_rows, "peak_frontier_states"
        ),
        "largest_reported_runtime_ms": largest(
            runtime_rows, "reported_runtime_ms"
        ),
        "largest_peak_python_heap_mib": largest(
            heap_rows, "peak_python_heap_mib"
        ),
        "largest_peak_worker_rss_mib": largest(
            rss_rows, "peak_worker_rss_mib"
        ),
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor_count": os.cpu_count(),
            "dp_sha256": _sha256_file(BOUNDS / "path_frontier_dp.py"),
        },
        "interpretation_boundary": (
            "Synthetic operational capacity profile only; it does not validate "
            "candidate coverage, observation assumptions, identification, or "
            "empirical conclusions. Runtime and memory proxies are machine-specific."
        ),
    }


def _display(value: Any, *, digits: int = 1) -> str:
    if value == "" or value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(
    summary: dict[str, Any], rows: Sequence[dict[str, Any]]
) -> str:
    counts = summary["status_counts"]
    lines = [
        "# Temporal frontier operational scaling profile",
        "",
        (
            "This report is an engineering capacity profile for deterministic "
            "synthetic temporal markets. It is kept separate from scientific "
            "validation and supports no empirical or identification claim."
        ),
        "",
        "## Bounded execution summary",
        "",
        "| Item | Value |",
        "|---|---:|",
        f"| Suite | {summary['suite']} |",
        f"| Cases | {summary['case_count']} |",
        f"| Exact solver returned | {counts['RESOLVED']} |",
        f"| Frontier limit | {counts['FRONTIER_LIMIT']} |",
        f"| Wall-clock timeout | {counts['TIMEOUT']} |",
        f"| Harness/solver error | {counts['ERROR']} |",
        f"| Per-case timeout | {summary['case_timeout_seconds']:g} s |",
        f"| Live-frontier limit | {summary['max_frontier_records']:,} |",
        f"| Worker RSS sampling | {summary['rss_sample_ms']:g} ms |",
        "",
        "## Schedule-constructor comparison",
        "",
        (
            "Each width below is certified for the listed constructor's validated "
            "action schedule. The release-aware greedy order and the adjacent order "
            "are deterministic heuristics; none of these widths is claimed globally "
            "minimum. The timed solve uses the smallest active-record bag among the "
            "three candidates, then active factors, with a fixed tie break."
        ),
        "",
        (
            "No exact order-search oracle is run in this operational harness. Any "
            "small-instance order oracle belongs in a separate correctness audit."
        ),
        "",
        (
            "| Case | Input width | Input factors | Adjacent width | Adjacent factors | "
            "Release-greedy width | Release-greedy factors | Selected order |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    row["case_id"],
                    str(row["input_certified_schedule_width"]),
                    str(row["input_peak_active_factors"]),
                    str(row["adjacent_certified_schedule_width"]),
                    str(row["adjacent_peak_active_factors"]),
                    str(row["release_greedy_certified_schedule_width"]),
                    str(row["release_greedy_peak_active_factors"]),
                    row["selected_order"],
                )
            )
            + " |"
        )
    lines.extend(
        [
        "",
        "## Case telemetry",
        "",
        (
            "`peak_active_records` and `peak_active_factors` are computed from "
            "the supplied schedule before the worker starts. Frontier telemetry "
            "is unavailable when a worker is stopped mid-solve."
        ),
        "",
        (
            "| Case | Axis value | Records | Max degree | Peak active records | "
            "Peak active factors | Labels | Floor | Gamma | Status | Peak frontier | "
            "Runtime ms | Python heap MiB | Worker RSS MiB |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    row["case_id"],
                    row["axis_value"],
                    str(row["record_count"]),
                    str(row["actual_max_degree"]),
                    str(row["peak_active_records"]),
                    str(row["peak_active_factors"]),
                    str(row["label_support"]),
                    _display(row["score_floor"], digits=0),
                    _display(row["gamma"], digits=0),
                    row["run_status"],
                    _display(row["peak_frontier_states"], digits=0),
                    _display(row["reported_runtime_ms"]),
                    _display(row["peak_python_heap_mib"], digits=2),
                    _display(row["peak_worker_rss_mib"], digits=2),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## How to read the profile",
            "",
            (
                "The market has one core and one buffer record per synthetic time "
                "index. Candidate edges are temporal bands, diagonal edges guarantee "
                "feasibility, and off-diagonal edges consume Gamma. Nested privacy "
                "factor scopes control factor overlap. The score floor is the integer "
                "threshold used by the exact score coordinate."
            ),
            "",
            (
                "`schedule_width` in the CSV/JSON is exactly one less than the selected "
                "schedule's peak active-record count (with a floor at zero). It "
                "describes that supplied record schedule; selecting among three "
                "constructors does not establish a globally minimum width."
            ),
            "",
            (
                "`peak_python_heap_mib` is traced during the solve. "
                "`peak_worker_rss_mib` is a process high-water proxy from child resource "
                "usage, augmented by parent sampling when procfs exposes the child. It "
                "includes Python startup and imports. Runtime and both memory measures "
                "are machine-specific diagnostics, not speed or memory guarantees."
            ),
            "",
            (
                "The table's runtime is isolated case wall time, including fresh-worker "
                "startup but excluding parent-side schedule compilation. CSV/JSON also "
                "retain solver-only wall/CPU time and schedule compilation time."
            ),
            "",
            (
                "Status `RESOLVED` means both exact endpoint runs returned (optimal or "
                "infeasible as shown by `solver_status` in CSV/JSON). "
                "`FRONTIER_LIMIT` and `TIMEOUT` are explicit unresolved outcomes."
            ),
            "",
            "## Interpretation boundary",
            "",
            summary["interpretation_boundary"],
            "",
            (
                f"Generator `{summary['generator_version']}`; Python "
                f"{summary['environment']['python']}; platform "
                f"`{summary['environment']['platform']}`."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, contents: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(contents, encoding="utf-8")
    os.replace(temporary, path)


def write_outputs(
    output_dir: Path,
    summary: dict[str, Any],
    rows: Sequence[dict[str, Any]],
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=list(rows[0]),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    csv_path = output_dir / "temporal_frontier_profile.csv"
    json_path = output_dir / "temporal_frontier_profile.json"
    report_path = output_dir / "TEMPORAL_FRONTIER_PROFILE.md"
    _atomic_write(csv_path, csv_buffer.getvalue())
    payload = dict(summary)
    payload["cases"] = list(rows)
    _atomic_write(json_path, json.dumps(payload, indent=2) + "\n")
    _atomic_write(report_path, render_markdown(summary, rows))
    return csv_path, json_path, report_path


def _select_specs(
    specs: Iterable[MarketSpec], case_ids: Sequence[str]
) -> tuple[MarketSpec, ...]:
    all_specs = tuple(specs)
    if not case_ids:
        return all_specs
    by_id = {spec.case_id: spec for spec in all_specs}
    unknown = sorted(set(case_ids) - set(by_id))
    if unknown:
        raise ValueError(f"unknown case id(s): {', '.join(unknown)}")
    requested = set(case_ids)
    return tuple(spec for spec in all_specs if spec.case_id in requested)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the bounded temporal-frontier operational profile."
    )
    parser.add_argument("--suite", choices=("quick", "extended"), default="quick")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--case-timeout-seconds", type=float, default=3.0)
    parser.add_argument("--max-frontier-records", type=int, default=200_000)
    parser.add_argument("--rss-sample-ms", type=float, default=10.0)
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="run one named locked case (repeatable)",
    )
    parser.add_argument("--list-cases", action="store_true")
    args = parser.parse_args()
    if args.case_timeout_seconds <= 0:
        raise ValueError("--case-timeout-seconds must be positive")
    if args.max_frontier_records < 1:
        raise ValueError("--max-frontier-records must be positive")
    if args.rss_sample_ms <= 0:
        raise ValueError("--rss-sample-ms must be positive")

    specs = _select_specs(workload_specs(args.suite), args.case_id)
    if args.list_cases:
        for spec in specs:
            print(spec.case_id)
        return
    context = mp.get_context("spawn")
    rows: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        compile_start = time.perf_counter_ns()
        compiled = compile_case(spec)
        compile_ms = round((time.perf_counter_ns() - compile_start) / 1_000_000, 6)
        print(
            f"[{index:02d}/{len(specs):02d}] {spec.case_id} "
            f"(order={compiled.selected_order_name}, "
            f"active records={compiled.schedule.max_bag_size}, "
            f"active factors={compiled.schedule.max_active_factor_count})",
            flush=True,
        )
        row = run_case_bounded(
            compiled,
            context=context,
            timeout_seconds=args.case_timeout_seconds,
            max_frontier_records=args.max_frontier_records,
            rss_sample_ms=args.rss_sample_ms,
        )
        row["compile_ms"] = compile_ms
        rows.append(row)
        print(
            f"    {row['run_status']} in {row['reported_runtime_ms']} ms; "
            f"peak frontier={row['peak_frontier_states'] or '--'}",
            flush=True,
        )

    summary = summarize(
        rows,
        suite=args.suite,
        timeout_seconds=args.case_timeout_seconds,
        max_frontier_records=args.max_frontier_records,
        rss_sample_ms=args.rss_sample_ms,
    )
    csv_path, json_path, report_path = write_outputs(
        args.output_dir, summary, rows
    )
    print(json.dumps(summary, indent=2))
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Report: {report_path}")
    if summary["status_counts"]["ERROR"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
