#!/usr/bin/env python3
"""Attained outcome endpoints over feasible pair packings.

The public Chicago TNP data expose trip-level match indicators, but do not
publish partner, provider, vehicle, or group identifiers. This module therefore
treats candidate partner pairs as a graph and optimizes a contextual statistic
over every feasible matching. A selected edge is an admissible latent partner,
not an observed partner link.

The main backend is :func:`scipy.optimize.milp`.  A deterministic exhaustive
fallback is included for small graphs so tests and toy examples do not depend
on SciPy's MILP wrapper.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

import numpy as np
import pandas as pd

try:
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    SCIPY_MILP_AVAILABLE = True
except (ImportError, AttributeError):  # pragma: no cover - exercised only in lean envs
    SCIPY_MILP_AVAILABLE = False


Sense = Literal["min", "max"]
Backend = Literal["auto", "scipy", "fallback"]


@dataclass(frozen=True)
class PackingSolution:
    """One optimized feasible packing."""

    feasible: bool
    status: str
    selected_edge_ids: tuple[str, ...]
    selected_edge_count: int
    objective_sum: float | None
    objective_mean: float | None
    total_score: float | None
    backend: str
    message: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["selected_edge_ids"] = list(self.selected_edge_ids)
        return payload


@dataclass(frozen=True)
class PackingBounds:
    """Lower and upper bounds for a matching-level mean edge statistic."""

    feasible: bool
    metric: str
    metric_interpretation: str
    candidate_edge_count: int
    required_node_count: int
    selected_edge_count: int | None
    score_optimum: float | None
    score_retention: float | None
    score_floor: float | None
    lower: float | None
    upper: float | None
    width: float | None
    score_solution: PackingSolution
    lower_solution: PackingSolution
    upper_solution: PackingSolution
    warning: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["score_solution"] = self.score_solution.to_dict()
        payload["lower_solution"] = self.lower_solution.to_dict()
        payload["upper_solution"] = self.upper_solution.to_dict()
        return payload


def _as_bool(series: pd.Series, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(series):
        if not series.dropna().isin([0, 1]).all():
            raise ValueError(f"{name} must contain only 0/1 or boolean values")
        return series.fillna(0).astype(int).astype(bool)
    normalized = series.astype("string").str.strip().str.lower()
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }
    unknown = normalized.dropna()[~normalized.dropna().isin(mapping)]
    if not unknown.empty:
        raise ValueError(f"{name} contains unrecognized boolean value {unknown.iloc[0]!r}")
    return normalized.map(mapping).fillna(False).astype(bool)


def prepare_problem(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    metric: Literal["same_bin", "ses_gap"] = "same_bin",
    node_id_col: str = "node_id",
    u_col: str = "u",
    v_col: str = "v",
    edge_id_col: str = "edge_id",
    score_col: str = "edge_score",
    ses_col: str = "ses_value",
    ses_bin_col: str = "ses_bin",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate inputs and add a numeric ``metric_value`` edge column.

    ``same_bin`` is the share of selected pairs with equal SES bins.  It is an
    interpretable assortative-pairing rate, not Newman's degree-corrected
    categorical assortativity coefficient.  ``ses_gap`` is the mean absolute
    difference in the supplied (possibly log-transformed) SES value.
    """

    if node_id_col not in nodes:
        raise ValueError(f"nodes are missing {node_id_col!r}")
    missing_edge_cols = {u_col, v_col, score_col} - set(edges.columns)
    if missing_edge_cols:
        raise ValueError(f"edges are missing columns: {sorted(missing_edge_cols)}")

    node_frame = nodes.copy()
    edge_frame = edges.copy()
    node_frame[node_id_col] = node_frame[node_id_col].astype(str)
    edge_frame[u_col] = edge_frame[u_col].astype(str)
    edge_frame[v_col] = edge_frame[v_col].astype(str)
    if node_frame[node_id_col].duplicated().any():
        dup = node_frame.loc[node_frame[node_id_col].duplicated(), node_id_col].iloc[0]
        raise ValueError(f"duplicate node id {dup!r}")
    if (edge_frame[u_col] == edge_frame[v_col]).any():
        raise ValueError("self-loop candidate edges are not permitted")

    node_ids = set(node_frame[node_id_col])
    unknown = (set(edge_frame[u_col]) | set(edge_frame[v_col])) - node_ids
    if unknown:
        raise ValueError(f"candidate edge references unknown node {sorted(unknown)[0]!r}")

    edge_frame[score_col] = pd.to_numeric(edge_frame[score_col], errors="coerce")
    if edge_frame[score_col].isna().any() or (~np.isfinite(edge_frame[score_col])).any():
        raise ValueError(f"{score_col} must be finite")
    if (edge_frame[score_col] < 0).any():
        raise ValueError(f"{score_col} must be nonnegative for score-retention bounds")

    if edge_id_col not in edge_frame:
        edge_frame[edge_id_col] = [f"e{i}" for i in range(len(edge_frame))]
    edge_frame[edge_id_col] = edge_frame[edge_id_col].astype(str)
    if edge_frame[edge_id_col].duplicated().any():
        raise ValueError(f"{edge_id_col} must be unique")

    node_lookup = node_frame.set_index(node_id_col)
    if metric == "same_bin":
        if ses_bin_col not in node_frame:
            raise ValueError(f"nodes are missing {ses_bin_col!r}")
        bins = node_lookup[ses_bin_col]
        if bins.isna().any():
            raise ValueError(f"{ses_bin_col} contains missing values")
        left = edge_frame[u_col].map(bins)
        right = edge_frame[v_col].map(bins)
        edge_frame["metric_value"] = (left.to_numpy() == right.to_numpy()).astype(float)
    elif metric == "ses_gap":
        if ses_col not in node_frame:
            raise ValueError(f"nodes are missing {ses_col!r}")
        values = pd.to_numeric(node_lookup[ses_col], errors="coerce")
        if values.isna().any() or (~np.isfinite(values)).any():
            raise ValueError(f"{ses_col} must be finite")
        left = edge_frame[u_col].map(values).to_numpy(dtype=float)
        right = edge_frame[v_col].map(values).to_numpy(dtype=float)
        edge_frame["metric_value"] = np.abs(left - right)
    else:  # pragma: no cover - guarded by Literal in normal use
        raise ValueError(f"unsupported metric {metric!r}")

    return node_frame, edge_frame.reset_index(drop=True)


def _empty_solution(status: str, backend: str, message: str) -> PackingSolution:
    return PackingSolution(
        feasible=False,
        status=status,
        selected_edge_ids=(),
        selected_edge_count=0,
        objective_sum=None,
        objective_mean=None,
        total_score=None,
        backend=backend,
        message=message,
    )


def _solution_from_selection(
    selected: Sequence[int],
    objective: np.ndarray,
    scores: np.ndarray,
    edge_ids: Sequence[str],
    backend: str,
    status: str = "optimal",
    message: str = "",
) -> PackingSolution:
    chosen = np.asarray(selected, dtype=int)
    objective_sum = float(objective[chosen].sum()) if len(chosen) else 0.0
    total_score = float(scores[chosen].sum()) if len(chosen) else 0.0
    return PackingSolution(
        feasible=True,
        status=status,
        selected_edge_ids=tuple(edge_ids[i] for i in chosen),
        selected_edge_count=len(chosen),
        objective_sum=objective_sum,
        objective_mean=objective_sum / len(chosen) if len(chosen) else None,
        total_score=total_score,
        backend=backend,
        message=message,
    )


def _solve_scipy(
    edge_frame: pd.DataFrame,
    node_ids: Sequence[str],
    objective: np.ndarray,
    scores: np.ndarray,
    *,
    sense: Sense,
    exact: bool,
    target_edges: int | None,
    score_floor: float | None,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    time_limit: float | None,
) -> PackingSolution:
    m = len(edge_frame)
    if m == 0:
        return _empty_solution("infeasible", "scipy", "no candidate edges")

    node_index = {node_id: i for i, node_id in enumerate(node_ids)}
    row_count = len(node_ids) + (1 if target_edges is not None else 0)
    incidence = lil_matrix((row_count, m), dtype=float)
    for edge_idx, (u, v) in enumerate(zip(edge_frame[u_col], edge_frame[v_col])):
        incidence[node_index[u], edge_idx] = 1.0
        incidence[node_index[v], edge_idx] = 1.0

    lower = np.zeros(row_count, dtype=float)
    upper = np.ones(row_count, dtype=float)
    if exact:
        lower[: len(node_ids)] = 1.0
    if target_edges is not None:
        incidence[len(node_ids), :] = 1.0
        lower[-1] = float(target_edges)
        upper[-1] = float(target_edges)

    constraints: list[LinearConstraint] = [
        LinearConstraint(incidence.tocsr(), lb=lower, ub=upper)
    ]
    if score_floor is not None:
        constraints.append(
            LinearConstraint(
                scores.reshape(1, -1),
                lb=np.array([score_floor - 1e-9]),
                ub=np.array([np.inf]),
            )
        )

    c = np.asarray(objective, dtype=float)
    if sense == "max":
        c = -c
    options: dict[str, float | bool] = {"presolve": True, "mip_rel_gap": 0.0}
    if time_limit is not None:
        options["time_limit"] = float(time_limit)
    result = milp(
        c=c,
        integrality=np.ones(m, dtype=np.int8),
        bounds=Bounds(lb=np.zeros(m), ub=np.ones(m)),
        constraints=constraints,
        options=options,
    )
    status_lookup = {
        0: "optimal",
        1: "limit_reached",
        2: "infeasible",
        3: "unbounded",
        4: "solver_error",
    }
    status = status_lookup.get(int(result.status), f"status_{result.status}")
    # A time-limit incumbent can be a valid matching but does not certify a
    # sharp extremum, so it must not be returned as an identified bound.
    if result.x is None or status != "optimal":
        return _empty_solution(status, "scipy", str(result.message))
    selected = np.flatnonzero(np.asarray(result.x) > 0.5)
    return _solution_from_selection(
        selected,
        objective,
        scores,
        edge_frame[edge_id_col].tolist(),
        "scipy",
        status=status,
        message=str(result.message),
    )


def _solve_fallback_exact(
    edge_frame: pd.DataFrame,
    node_ids: Sequence[str],
    objective: np.ndarray,
    scores: np.ndarray,
    *,
    sense: Sense,
    score_floor: float | None,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    max_states: int,
) -> PackingSolution:
    """Enumerate perfect matchings by branching on the most constrained node."""

    required = set(node_ids)
    incident: dict[str, list[int]] = {node_id: [] for node_id in node_ids}
    endpoints: list[tuple[str, str]] = []
    for i, (u, v) in enumerate(zip(edge_frame[u_col], edge_frame[v_col])):
        endpoints.append((u, v))
        incident[u].append(i)
        incident[v].append(i)

    states = 0
    best_selected: list[int] | None = None
    best_value = math.inf if sense == "min" else -math.inf

    def recurse(used: set[str], selected: list[int]) -> None:
        nonlocal states, best_selected, best_value
        states += 1
        if states > max_states:
            raise RuntimeError(f"fallback enumeration exceeded {max_states:,} states")
        remaining = required - used
        if not remaining:
            score = float(scores[selected].sum()) if selected else 0.0
            if score_floor is not None and score + 1e-9 < score_floor:
                return
            value = float(objective[selected].sum()) if selected else 0.0
            better = value < best_value - 1e-12 if sense == "min" else value > best_value + 1e-12
            if better or best_selected is None:
                best_value = value
                best_selected = selected.copy()
            return

        feasible_by_node: dict[str, list[int]] = {}
        for node in remaining:
            feasible = []
            for edge_idx in incident[node]:
                u, v = endpoints[edge_idx]
                other = v if u == node else u
                if other in remaining:
                    feasible.append(edge_idx)
            if not feasible:
                return
            feasible_by_node[node] = feasible
        node = min(feasible_by_node, key=lambda key: (len(feasible_by_node[key]), key))
        for edge_idx in feasible_by_node[node]:
            u, v = endpoints[edge_idx]
            recurse(used | {u, v}, selected + [edge_idx])

    try:
        recurse(set(), [])
    except RuntimeError as exc:
        return _empty_solution("limit_reached", "fallback", str(exc))
    if best_selected is None:
        return _empty_solution("infeasible", "fallback", "no feasible perfect matching")
    return _solution_from_selection(
        best_selected,
        objective,
        scores,
        edge_frame[edge_id_col].tolist(),
        "fallback",
        message=f"enumerated {states:,} states",
    )


def _solve_fallback_target(
    edge_frame: pd.DataFrame,
    objective: np.ndarray,
    scores: np.ndarray,
    *,
    target_edges: int,
    sense: Sense,
    score_floor: float | None,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    max_states: int,
) -> PackingSolution:
    endpoints = list(zip(edge_frame[u_col], edge_frame[v_col]))
    states = 0
    best_selected: list[int] | None = None
    best_value = math.inf if sense == "min" else -math.inf

    def recurse(index: int, used: set[str], selected: list[int]) -> None:
        nonlocal states, best_selected, best_value
        states += 1
        if states > max_states:
            raise RuntimeError(f"fallback enumeration exceeded {max_states:,} states")
        need = target_edges - len(selected)
        if need == 0:
            score = float(scores[selected].sum()) if selected else 0.0
            if score_floor is not None and score + 1e-9 < score_floor:
                return
            value = float(objective[selected].sum()) if selected else 0.0
            better = value < best_value - 1e-12 if sense == "min" else value > best_value + 1e-12
            if better or best_selected is None:
                best_value = value
                best_selected = selected.copy()
            return
        if index >= len(endpoints) or len(endpoints) - index < need:
            return
        u, v = endpoints[index]
        if u not in used and v not in used:
            recurse(index + 1, used | {u, v}, selected + [index])
        recurse(index + 1, used, selected)

    try:
        recurse(0, set(), [])
    except RuntimeError as exc:
        return _empty_solution("limit_reached", "fallback", str(exc))
    if best_selected is None:
        return _empty_solution("infeasible", "fallback", "no feasible target-size matching")
    return _solution_from_selection(
        best_selected,
        objective,
        scores,
        edge_frame[edge_id_col].tolist(),
        "fallback",
        message=f"enumerated {states:,} states",
    )


def _solve(
    edge_frame: pd.DataFrame,
    node_ids: Sequence[str],
    objective: np.ndarray,
    scores: np.ndarray,
    *,
    sense: Sense,
    exact: bool,
    target_edges: int | None,
    score_floor: float | None,
    backend: Backend,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    time_limit: float | None,
    fallback_max_states: int,
) -> PackingSolution:
    selected_backend = "scipy" if backend == "auto" and SCIPY_MILP_AVAILABLE else backend
    if selected_backend == "auto":
        selected_backend = "fallback"
    if selected_backend == "scipy":
        if not SCIPY_MILP_AVAILABLE:
            raise RuntimeError("SciPy MILP backend requested but unavailable")
        return _solve_scipy(
            edge_frame,
            node_ids,
            objective,
            scores,
            sense=sense,
            exact=exact,
            target_edges=target_edges,
            score_floor=score_floor,
            u_col=u_col,
            v_col=v_col,
            edge_id_col=edge_id_col,
            time_limit=time_limit,
        )
    if selected_backend != "fallback":
        raise ValueError(f"unsupported backend {backend!r}")
    if exact:
        return _solve_fallback_exact(
            edge_frame,
            node_ids,
            objective,
            scores,
            sense=sense,
            score_floor=score_floor,
            u_col=u_col,
            v_col=v_col,
            edge_id_col=edge_id_col,
            max_states=fallback_max_states,
        )
    if target_edges is None:
        raise ValueError("fallback backend needs exact=True or target_edges")
    return _solve_fallback_target(
        edge_frame,
        objective,
        scores,
        target_edges=target_edges,
        sense=sense,
        score_floor=score_floor,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        max_states=fallback_max_states,
    )


def solve_bounds(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    metric: Literal["same_bin", "ses_gap"] = "same_bin",
    matched_col: str | None = None,
    match_all: bool = True,
    target_edges: int | None = None,
    score_retention: float | None = None,
    backend: Backend = "auto",
    node_id_col: str = "node_id",
    u_col: str = "u",
    v_col: str = "v",
    edge_id_col: str = "edge_id",
    score_col: str = "edge_score",
    ses_col: str = "ses_value",
    ses_bin_col: str = "ses_bin",
    time_limit: float | None = 60.0,
    fallback_max_states: int = 2_000_000,
) -> PackingBounds:
    """Compute lower/upper outcome bounds over feasible pair packings.

    If ``matched_col`` is supplied, nodes equal to one must each have degree one
    and zero-valued nodes are excluded.  Otherwise ``match_all=True`` requires a
    perfect matching over all nodes.  Set ``match_all=False`` and supply
    ``target_edges`` for a fixed-size matching over optional nodes.

    ``score_retention`` restricts the admissible set to packings whose total
    edge score is at least that fraction of the maximum-score feasible packing.
    Scores must therefore be nonnegative.  A value of 0.95 is often a useful
    sensitivity analysis, not a data-identified confidence region.  The raw
    fraction is score-origin dependent and must not be compared across score
    maps as if it had a common coverage interpretation.
    """

    if score_retention is not None and not (0 <= score_retention <= 1):
        raise ValueError("score_retention must lie in [0, 1]")
    node_frame, edge_frame = prepare_problem(
        nodes,
        edges,
        metric=metric,
        node_id_col=node_id_col,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        score_col=score_col,
        ses_col=ses_col,
        ses_bin_col=ses_bin_col,
    )

    if matched_col is not None:
        if matched_col not in node_frame:
            raise ValueError(f"nodes are missing {matched_col!r}")
        required_mask = _as_bool(node_frame[matched_col], matched_col)
        required_nodes = node_frame.loc[required_mask, node_id_col].tolist()
        exact = True
    elif match_all:
        required_nodes = node_frame[node_id_col].tolist()
        exact = True
    else:
        required_nodes = node_frame[node_id_col].tolist()
        exact = False

    warning = ""
    if exact:
        required_set = set(required_nodes)
        edge_frame = edge_frame[
            edge_frame[u_col].isin(required_set) & edge_frame[v_col].isin(required_set)
        ].reset_index(drop=True)
        expected_edges = len(required_nodes) // 2
        if len(required_nodes) % 2:
            empty = _empty_solution("infeasible", backend, "odd number of required nodes")
            return PackingBounds(
                False,
                metric,
                _metric_interpretation(metric),
                len(edge_frame),
                len(required_nodes),
                None,
                None,
                score_retention,
                None,
                None,
                None,
                None,
                empty,
                empty,
                empty,
                "An exact pair packing requires an even number of matched nodes.",
            )
        if target_edges is not None and target_edges != expected_edges:
            raise ValueError(
                f"target_edges={target_edges} conflicts with {len(required_nodes)} exact nodes"
            )
        target_edges = expected_edges
    else:
        if target_edges is None or target_edges < 0:
            raise ValueError("non-exact mode requires nonnegative target_edges")
        if target_edges > len(required_nodes) // 2:
            raise ValueError("target_edges exceeds the node-disjoint pair capacity")

    objective = edge_frame["metric_value"].to_numpy(dtype=float)
    scores = edge_frame[score_col].to_numpy(dtype=float)
    score_solution = _solve(
        edge_frame,
        required_nodes,
        scores,
        scores,
        sense="max",
        exact=exact,
        target_edges=target_edges,
        score_floor=None,
        backend=backend,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        time_limit=time_limit,
        fallback_max_states=fallback_max_states,
    )
    if not score_solution.feasible:
        empty = _empty_solution(
            score_solution.status,
            score_solution.backend,
            score_solution.message,
        )
        if score_solution.status == "infeasible":
            warning = (
                "The solver certified that the candidate graph has no feasible "
                "packing under the requested node constraints."
            )
        else:
            warning = (
                "The score optimization did not certify an optimum; the graph's "
                "feasibility is unresolved."
            )
        return PackingBounds(
            False,
            metric,
            _metric_interpretation(metric),
            len(edge_frame),
            len(required_nodes),
            None,
            None,
            score_retention,
            None,
            None,
            None,
            None,
            score_solution,
            empty,
            empty,
            warning,
        )

    score_optimum = float(score_solution.total_score or 0.0)
    score_floor = (
        float(score_retention * score_optimum) if score_retention is not None else None
    )
    lower_solution = _solve(
        edge_frame,
        required_nodes,
        objective,
        scores,
        sense="min",
        exact=exact,
        target_edges=target_edges,
        score_floor=score_floor,
        backend=backend,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        time_limit=time_limit,
        fallback_max_states=fallback_max_states,
    )
    upper_solution = _solve(
        edge_frame,
        required_nodes,
        objective,
        scores,
        sense="max",
        exact=exact,
        target_edges=target_edges,
        score_floor=score_floor,
        backend=backend,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        time_limit=time_limit,
        fallback_max_states=fallback_max_states,
    )
    feasible = lower_solution.feasible and upper_solution.feasible
    lower = lower_solution.objective_mean if feasible else None
    upper = upper_solution.objective_mean if feasible else None
    if not feasible:
        statuses = {lower_solution.status, upper_solution.status}
        if statuses == {"infeasible"}:
            warning = (
                "The score-restricted outcome programs were certified infeasible "
                "despite an unrestricted feasible score packing."
            )
        else:
            warning = (
                "At least one outcome program did not certify an optimum; no "
                "endpoint is reported for the unresolved program."
            )
    return PackingBounds(
        feasible=feasible,
        metric=metric,
        metric_interpretation=_metric_interpretation(metric),
        candidate_edge_count=len(edge_frame),
        required_node_count=len(required_nodes),
        selected_edge_count=target_edges if feasible else None,
        score_optimum=score_optimum,
        score_retention=score_retention,
        score_floor=score_floor,
        lower=lower,
        upper=upper,
        width=(upper - lower) if feasible and lower is not None and upper is not None else None,
        score_solution=score_solution,
        lower_solution=lower_solution,
        upper_solution=upper_solution,
        warning=warning,
    )


def _metric_interpretation(metric: str) -> str:
    if metric == "same_bin":
        return "mean share of selected pairs in the same SES bin"
    return "mean absolute SES-value gap among selected pairs"


def _write_selected_edges(
    output: Path,
    edges: pd.DataFrame,
    bounds: PackingBounds,
    edge_id_col: str,
) -> None:
    rows = []
    by_id = edges.assign(**{edge_id_col: edges[edge_id_col].astype(str)}).set_index(edge_id_col)
    for label, solution in [
        ("max_score", bounds.score_solution),
        ("lower_bound", bounds.lower_solution),
        ("upper_bound", bounds.upper_solution),
    ]:
        for edge_id in solution.selected_edge_ids:
            row = by_id.loc[edge_id].to_dict()
            row[edge_id_col] = edge_id
            row["solution"] = label
            rows.append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selected-output", type=Path)
    parser.add_argument("--metric", choices=["same_bin", "ses_gap"], default="same_bin")
    parser.add_argument("--matched-col")
    parser.add_argument("--optional-nodes", action="store_true")
    parser.add_argument("--target-edges", type=int)
    parser.add_argument("--score-retention", type=float)
    parser.add_argument("--backend", choices=["auto", "scipy", "fallback"], default="auto")
    parser.add_argument("--node-id-col", default="node_id")
    parser.add_argument("--u-col", default="u")
    parser.add_argument("--v-col", default="v")
    parser.add_argument("--edge-id-col", default="edge_id")
    parser.add_argument("--score-col", default="edge_score")
    parser.add_argument("--ses-col", default="ses_value")
    parser.add_argument("--ses-bin-col", default="ses_bin")
    parser.add_argument("--time-limit", type=float, default=60.0)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    nodes = pd.read_csv(args.nodes)
    edges = pd.read_csv(args.edges)
    bounds = solve_bounds(
        nodes,
        edges,
        metric=args.metric,
        matched_col=args.matched_col,
        match_all=not args.optional_nodes,
        target_edges=args.target_edges,
        score_retention=args.score_retention,
        backend=args.backend,
        node_id_col=args.node_id_col,
        u_col=args.u_col,
        v_col=args.v_col,
        edge_id_col=args.edge_id_col,
        score_col=args.score_col,
        ses_col=args.ses_col,
        ses_bin_col=args.ses_bin_col,
        time_limit=args.time_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bounds.to_dict(), indent=2), encoding="utf-8")
    if args.selected_output:
        if args.edge_id_col not in edges:
            edges = edges.copy()
            edges[args.edge_id_col] = [f"e{i}" for i in range(len(edges))]
        _write_selected_edges(args.selected_output, edges, bounds, args.edge_id_col)
    print(json.dumps(bounds.to_dict(), indent=2))
    return 0 if bounds.feasible else 2


if __name__ == "__main__":
    raise SystemExit(main())
