#!/usr/bin/env python3
"""Audited linear endpoints over exact-cover matchings.

This module implements the formal repairs developed in the adversarial audit:

* lower and upper programs may use distinct signed edge coefficients;
* missing context can be represented by edgewise attainable envelopes when
  node supports are independent;
* a fixed OLS/DDD coefficient can be written as a signed edge objective; and
* candidate-miss sensitivity can admit at most ``gamma`` supergraph edges.

Every result is conditional on the supplied node set and supergraph.  The
module does not claim that the graph contains the hidden true matching.
Exhaustive fallback solutions are exact for the declared floating-point input;
SciPy/HiGHS solutions are explicitly labeled numerical rather than exact
certificates.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Literal, Sequence

import numpy as np
import pandas as pd

try:
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    SCIPY_MILP_AVAILABLE = True
except (ImportError, AttributeError):  # pragma: no cover - lean environments
    SCIPY_MILP_AVAILABLE = False


Backend = Literal["auto", "scipy", "fallback"]
Sense = Literal["min", "max"]


def _validated_string_series(series: pd.Series, name: str) -> pd.Series:
    """Return non-null, nonblank identifiers as strings."""

    if series.isna().any():
        raise ValueError(f"{name} must not contain null values")
    converted = series.astype(str)
    if converted.str.strip().eq("").any():
        raise ValueError(f"{name} must not contain blank values")
    return converted


def _reject_duplicate_undirected_pairs(
    edge_frame: pd.DataFrame,
    *,
    u_col: str,
    v_col: str,
) -> None:
    canonical = pd.Series(
        [tuple(sorted((u, v))) for u, v in zip(edge_frame[u_col], edge_frame[v_col])],
        dtype=object,
    )
    if canonical.duplicated().any():
        pair = canonical.loc[canonical.duplicated(keep=False)].iloc[0]
        raise ValueError(f"duplicate undirected candidate pair {pair!r}")


def _fixed_cardinality_normalization(
    values: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    """Normalize an edge objective by a harmless positive affine map."""

    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return values.copy(), 0.0, 1.0
    low = float(np.min(values))
    high = float(np.max(values))
    center = low / 2.0 + high / 2.0
    shifted = values - center
    if not np.isfinite(shifted).all():
        raise ValueError("objective normalization is not finitely representable")
    scale = float(np.max(np.abs(shifted)))
    if scale == 0.0:
        return np.zeros_like(values), center, 1.0
    normalized = shifted / scale
    if not np.isfinite(normalized).all():
        raise ValueError("normalized objective must be finite")
    return normalized, center, scale


def _extended_sum(values: np.ndarray | Sequence[float]) -> np.longdouble:
    return np.sum(np.asarray(values, dtype=np.longdouble), dtype=np.longdouble)


def _exact_float_sum(values: np.ndarray | Sequence[float]) -> Fraction:
    return sum(
        (Fraction.from_float(float(value)) for value in values),
        start=Fraction(0),
    )


def _finite_float(value: np.longdouble | float, name: str) -> float:
    wide = np.longdouble(value)
    limit = np.longdouble(np.finfo(float).max)
    if not np.isfinite(wide) or abs(wide) > limit:
        raise ValueError(
            f"{name} is not representable as a finite float; rescale the input"
        )
    return float(wide)


@dataclass(frozen=True)
class CertifiedLinearSolution:
    status: str
    certified: bool
    feasible_incumbent: bool
    selected_edge_ids: tuple[str, ...]
    objective_sum: float | None
    omitted_edge_count: int | None
    total_score: float | None
    backend: str
    message: str
    mip_gap: float | None = None
    mip_dual_bound: float | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["selected_edge_ids"] = list(self.selected_edge_ids)
        return payload


@dataclass(frozen=True)
class CertifiedLinearEndpoints:
    status: str
    certified: bool
    lower: float | None
    upper: float | None
    normalizer: float
    candidate_edge_count: int
    required_node_count: int
    gamma: int | None
    score_floor: float | None
    lower_solution: CertifiedLinearSolution
    upper_solution: CertifiedLinearSolution
    warning: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["lower_solution"] = self.lower_solution.to_dict()
        payload["upper_solution"] = self.upper_solution.to_dict()
        return payload


def _unresolved_solution(
    status: str,
    backend: str,
    message: str,
) -> CertifiedLinearSolution:
    return CertifiedLinearSolution(
        status=status,
        certified=status == "PROVEN_INFEASIBLE",
        feasible_incumbent=False,
        selected_edge_ids=(),
        objective_sum=None,
        omitted_edge_count=None,
        total_score=None,
        backend=backend,
        message=message,
    )


def _prepare_graph(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    node_id_col: str,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    lower_objective_col: str,
    upper_objective_col: str,
    omitted_col: str | None,
    score_col: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_node_columns = {node_id_col}
    required_edge_columns = {
        u_col,
        v_col,
        lower_objective_col,
        upper_objective_col,
    }
    if missing := required_node_columns - set(nodes.columns):
        raise ValueError(f"nodes are missing columns: {sorted(missing)}")
    if missing := required_edge_columns - set(edges.columns):
        raise ValueError(f"edges are missing columns: {sorted(missing)}")

    node_frame = nodes.copy()
    edge_frame = edges.copy()
    node_frame[node_id_col] = _validated_string_series(
        node_frame[node_id_col], node_id_col
    )
    edge_frame[u_col] = _validated_string_series(edge_frame[u_col], u_col)
    edge_frame[v_col] = _validated_string_series(edge_frame[v_col], v_col)
    if node_frame[node_id_col].duplicated().any():
        raise ValueError(f"{node_id_col} must be unique")
    if (edge_frame[u_col] == edge_frame[v_col]).any():
        raise ValueError("self-loop candidate edges are not permitted")
    _reject_duplicate_undirected_pairs(edge_frame, u_col=u_col, v_col=v_col)

    node_ids = set(node_frame[node_id_col])
    unknown = (set(edge_frame[u_col]) | set(edge_frame[v_col])) - node_ids
    if unknown:
        raise ValueError(f"edge references unknown node {sorted(unknown)[0]!r}")

    if edge_id_col not in edge_frame:
        edge_frame[edge_id_col] = [f"e{i}" for i in range(len(edge_frame))]
    else:
        edge_frame[edge_id_col] = _validated_string_series(
            edge_frame[edge_id_col], edge_id_col
        )
    if edge_frame[edge_id_col].duplicated().any():
        raise ValueError(f"{edge_id_col} must be unique")

    numeric_columns = [lower_objective_col, upper_objective_col]
    if score_col is not None:
        if score_col not in edge_frame:
            raise ValueError(f"edges are missing {score_col!r}")
        numeric_columns.append(score_col)
    for column in numeric_columns:
        edge_frame[column] = pd.to_numeric(edge_frame[column], errors="coerce")
        values = edge_frame[column].to_numpy(dtype=float)
        if np.isnan(values).any() or (~np.isfinite(values)).any():
            raise ValueError(f"{column} must be finite")
    if (
        edge_frame[lower_objective_col].to_numpy(dtype=float)
        > edge_frame[upper_objective_col].to_numpy(dtype=float)
    ).any():
        raise ValueError("lower edge objectives must not exceed upper edge objectives")

    if omitted_col is None:
        edge_frame["_omitted_edge"] = 0
    else:
        if omitted_col not in edge_frame:
            raise ValueError(f"edges are missing {omitted_col!r}")
        omitted = pd.to_numeric(edge_frame[omitted_col], errors="coerce")
        if omitted.isna().any() or not omitted.isin([0, 1]).all():
            raise ValueError(f"{omitted_col} must contain only 0/1 values")
        edge_frame["_omitted_edge"] = omitted.astype(int)

    return node_frame.reset_index(drop=True), edge_frame.reset_index(drop=True)


def _selection_is_feasible(
    selected: np.ndarray,
    edge_frame: pd.DataFrame,
    node_ids: Sequence[str],
    *,
    u_col: str,
    v_col: str,
    gamma: int | None,
    score_col: str | None,
    score_floor: float | None,
) -> bool:
    degree = {node_id: 0 for node_id in node_ids}
    for index in selected:
        row = edge_frame.iloc[int(index)]
        degree[row[u_col]] += 1
        degree[row[v_col]] += 1
    if any(value != 1 for value in degree.values()):
        return False
    if gamma is not None:
        omissions = int(edge_frame.iloc[selected]["_omitted_edge"].sum())
        if omissions > gamma:
            return False
    if score_floor is not None:
        if score_col is None:
            return False
        score = _exact_float_sum(
            edge_frame.iloc[selected][score_col].to_numpy(dtype=float)
        )
        if score < Fraction.from_float(float(score_floor)):
            return False
    return True


def _solution_from_selection(
    selected: Sequence[int],
    edge_frame: pd.DataFrame,
    objective: np.ndarray,
    *,
    edge_id_col: str,
    score_col: str | None,
    status: str,
    certified: bool,
    backend: str,
    message: str,
    mip_gap: float | None = None,
    mip_dual_bound: float | None = None,
) -> CertifiedLinearSolution:
    chosen = np.asarray(selected, dtype=int)
    score = (
        _finite_float(
            _extended_sum(edge_frame.iloc[chosen][score_col].to_numpy()),
            "selected total score",
        )
        if score_col is not None and len(chosen)
        else (0.0 if score_col is not None else None)
    )
    return CertifiedLinearSolution(
        status=status,
        certified=certified,
        feasible_incumbent=True,
        selected_edge_ids=tuple(edge_frame.iloc[chosen][edge_id_col].astype(str)),
        objective_sum=_finite_float(
            _extended_sum(objective[chosen]), "selected objective sum"
        ),
        omitted_edge_count=int(edge_frame.iloc[chosen]["_omitted_edge"].sum()),
        total_score=score,
        backend=backend,
        message=message,
        mip_gap=mip_gap,
        mip_dual_bound=mip_dual_bound,
    )


def _solve_scipy(
    edge_frame: pd.DataFrame,
    node_ids: Sequence[str],
    objective: np.ndarray,
    *,
    sense: Sense,
    gamma: int | None,
    score_col: str | None,
    score_floor: float | None,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    time_limit: float | None,
) -> CertifiedLinearSolution:
    if not SCIPY_MILP_AVAILABLE:
        raise RuntimeError("SciPy MILP backend requested but unavailable")
    if len(edge_frame) == 0:
        return _unresolved_solution(
            "PROVEN_INFEASIBLE", "scipy", "no candidate edges"
        )

    endpoint_counts = pd.concat([edge_frame[u_col], edge_frame[v_col]]).value_counts()
    if any(int(endpoint_counts.get(node_id, 0)) == 0 for node_id in node_ids):
        return _unresolved_solution(
            "PROVEN_INFEASIBLE", "scipy", "a required node has no candidate edge"
        )

    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    incidence = lil_matrix((len(node_ids), len(edge_frame)), dtype=float)
    for edge_index, (u, v) in enumerate(zip(edge_frame[u_col], edge_frame[v_col])):
        incidence[node_index[u], edge_index] = 1.0
        incidence[node_index[v], edge_index] = 1.0
    constraints: list[LinearConstraint] = [
        LinearConstraint(
            incidence.tocsr(),
            lb=np.ones(len(node_ids)),
            ub=np.ones(len(node_ids)),
        )
    ]
    if gamma is not None:
        constraints.append(
            LinearConstraint(
                edge_frame["_omitted_edge"].to_numpy(dtype=float).reshape(1, -1),
                lb=np.array([-np.inf]),
                ub=np.array([float(gamma)]),
            )
        )
    matching_cardinality = len(node_ids) // 2
    if score_floor is not None:
        if score_col is None:
            raise ValueError("score_floor requires score_col")
        normalized_score, score_center, score_scale = _fixed_cardinality_normalization(
            edge_frame[score_col].to_numpy(dtype=float)
        )
        exact_scores = [
            Fraction.from_float(float(value))
            for value in edge_frame[score_col].to_numpy(dtype=float)
        ]
        exact_floor = Fraction.from_float(float(score_floor))
        exact_unconstrained_upper = matching_cardinality * max(exact_scores)
        exact_unconstrained_lower = matching_cardinality * min(exact_scores)
        if exact_floor > exact_unconstrained_upper:
            return _unresolved_solution(
                "PROVEN_INFEASIBLE",
                "scipy",
                "score floor exceeds the exact fixed-cardinality upper bound",
            )
        normalized_floor_wide = (
            np.longdouble(score_floor)
            - np.longdouble(matching_cardinality) * np.longdouble(score_center)
        ) / np.longdouble(score_scale)
        if exact_floor > exact_unconstrained_lower:
            rounded_floor = _finite_float(
                normalized_floor_wide, "normalized score floor"
            )
            relaxation = 8.0 * np.finfo(float).eps * max(
                1.0,
                abs(rounded_floor),
                float(matching_cardinality),
            )
            normalized_floor = rounded_floor - relaxation
            constraints.append(
                LinearConstraint(
                    normalized_score.reshape(1, -1),
                    lb=np.array([normalized_floor]),
                    ub=np.array([np.inf]),
                )
            )

    normalized_objective, objective_center, objective_scale = (
        _fixed_cardinality_normalization(objective)
    )
    c = normalized_objective
    if sense == "max":
        c = -c
    options: dict[str, float | bool] = {"presolve": True, "mip_rel_gap": 0.0}
    if time_limit is not None:
        options["time_limit"] = float(time_limit)
    result = milp(
        c=c,
        integrality=np.ones(len(edge_frame), dtype=np.int8),
        bounds=Bounds(
            lb=np.zeros(len(edge_frame)),
            ub=np.ones(len(edge_frame)),
        ),
        constraints=constraints,
        options=options,
    )
    message = str(result.message)
    if int(result.status) == 2:
        return _unresolved_solution(
            "UNRESOLVED",
            "scipy",
            "numerical MILP backend reported infeasibility; no exact certificate: "
            + message,
        )

    selected = (
        np.flatnonzero(np.asarray(result.x) > 0.5)
        if getattr(result, "x", None) is not None
        else np.array([], dtype=int)
    )
    valid_incumbent = len(selected) > 0 and _selection_is_feasible(
        selected,
        edge_frame,
        node_ids,
        u_col=u_col,
        v_col=v_col,
        gamma=gamma,
        score_col=score_col,
        score_floor=score_floor,
    )
    if int(result.status) == 0 and valid_incumbent:
        status = "NUMERICALLY_OPTIMAL"
        certified = False
    else:
        status = "UNRESOLVED"
        certified = False
    if not valid_incumbent:
        return _unresolved_solution(status, "scipy", message)

    dual = getattr(result, "mip_dual_bound", None)
    if dual is not None and sense == "max":
        dual = -float(dual)
    elif dual is not None:
        dual = float(dual)
    if dual is not None:
        dual_wide = (
            np.longdouble(objective_scale) * np.longdouble(dual)
            + np.longdouble(objective_center) * np.longdouble(matching_cardinality)
        )
        try:
            dual = _finite_float(dual_wide, "MILP dual bound")
        except ValueError:
            dual = None
    gap = getattr(result, "mip_gap", None)
    return _solution_from_selection(
        selected,
        edge_frame,
        objective,
        edge_id_col=edge_id_col,
        score_col=score_col,
        status=status,
        certified=certified,
        backend="scipy",
        message=message,
        mip_gap=float(gap) if gap is not None else None,
        mip_dual_bound=dual,
    )


def _solve_fallback(
    edge_frame: pd.DataFrame,
    node_ids: Sequence[str],
    objective: np.ndarray,
    *,
    sense: Sense,
    gamma: int | None,
    score_col: str | None,
    score_floor: float | None,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    max_states: int,
) -> CertifiedLinearSolution:
    required = set(node_ids)
    incident: dict[str, list[int]] = {node_id: [] for node_id in node_ids}
    endpoints: list[tuple[str, str]] = []
    for index, (u, v) in enumerate(zip(edge_frame[u_col], edge_frame[v_col])):
        endpoints.append((u, v))
        incident[u].append(index)
        incident[v].append(index)

    scores = (
        edge_frame[score_col].to_numpy(dtype=float)
        if score_col is not None
        else np.zeros(len(edge_frame), dtype=float)
    )
    exact_scores = [Fraction.from_float(float(value)) for value in scores]
    exact_objective = [
        Fraction.from_float(float(value)) for value in np.asarray(objective)
    ]
    exact_score_floor = (
        Fraction.from_float(float(score_floor)) if score_floor is not None else None
    )
    omissions = edge_frame["_omitted_edge"].to_numpy(dtype=int)
    states = 0
    best: list[int] | None = None
    best_value: Fraction | None = None

    def recurse(used: set[str], selected: list[int]) -> None:
        nonlocal states, best, best_value
        states += 1
        if states > max_states:
            raise RuntimeError(f"fallback enumeration exceeded {max_states:,} states")
        if gamma is not None and int(omissions[selected].sum()) > gamma:
            return
        remaining = required - used
        if not remaining:
            if exact_score_floor is not None and sum(
                (exact_scores[index] for index in selected), start=Fraction(0)
            ) < exact_score_floor:
                return
            value = sum(
                (exact_objective[index] for index in selected), start=Fraction(0)
            )
            better = (
                best_value is None
                or (value < best_value if sense == "min" else value > best_value)
            )
            if best is None or better:
                best = list(selected)
                best_value = value
            return

        choices: dict[str, list[int]] = {}
        for node in remaining:
            feasible = []
            for edge_index in incident[node]:
                u, v = endpoints[edge_index]
                other = v if u == node else u
                if other in remaining:
                    feasible.append(edge_index)
            if not feasible:
                return
            choices[node] = feasible
        node = min(choices, key=lambda value: (len(choices[value]), value))
        for edge_index in choices[node]:
            u, v = endpoints[edge_index]
            recurse(used | {u, v}, selected + [edge_index])

    try:
        recurse(set(), [])
    except RuntimeError as exc:
        return _unresolved_solution("UNRESOLVED", "fallback", str(exc))
    if best is None:
        return _unresolved_solution(
            "PROVEN_INFEASIBLE",
            "fallback",
            f"enumerated {states:,} states; no feasible matching",
        )
    return _solution_from_selection(
        best,
        edge_frame,
        objective,
        edge_id_col=edge_id_col,
        score_col=score_col,
        status="OPTIMAL",
        certified=True,
        backend="fallback",
        message=f"enumerated {states:,} states",
    )


def _solve_one(
    edge_frame: pd.DataFrame,
    node_ids: Sequence[str],
    objective: np.ndarray,
    *,
    sense: Sense,
    gamma: int | None,
    score_col: str | None,
    score_floor: float | None,
    backend: Backend,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    time_limit: float | None,
    fallback_max_states: int,
) -> CertifiedLinearSolution:
    selected_backend = backend
    if backend == "auto":
        selected_backend = "scipy" if SCIPY_MILP_AVAILABLE else "fallback"
    if selected_backend == "scipy":
        return _solve_scipy(
            edge_frame,
            node_ids,
            objective,
            sense=sense,
            gamma=gamma,
            score_col=score_col,
            score_floor=score_floor,
            u_col=u_col,
            v_col=v_col,
            edge_id_col=edge_id_col,
            time_limit=time_limit,
        )
    if selected_backend == "fallback":
        return _solve_fallback(
            edge_frame,
            node_ids,
            objective,
            sense=sense,
            gamma=gamma,
            score_col=score_col,
            score_floor=score_floor,
            u_col=u_col,
            v_col=v_col,
            edge_id_col=edge_id_col,
            max_states=fallback_max_states,
        )
    raise ValueError(f"unsupported backend {backend!r}")


def solve_linear_endpoints(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    lower_objective_col: str,
    upper_objective_col: str,
    normalizer: float = 1.0,
    matched_col: str | None = None,
    omitted_col: str | None = None,
    gamma: int | None = None,
    score_col: str | None = None,
    score_floor: float | None = None,
    backend: Backend = "auto",
    node_id_col: str = "node_id",
    u_col: str = "u",
    v_col: str = "v",
    edge_id_col: str = "edge_id",
    time_limit: float | None = 60.0,
    fallback_max_states: int = 2_000_000,
) -> CertifiedLinearEndpoints:
    """Solve distinct signed lower/upper objectives over one exact-cover domain."""

    if not math.isfinite(normalizer) or normalizer <= 0:
        raise ValueError("normalizer must be finite and positive")
    if gamma is not None:
        if isinstance(gamma, (bool, np.bool_)) or not isinstance(gamma, (int, np.integer)):
            raise ValueError("gamma must be a nonnegative integer")
        if gamma < 0:
            raise ValueError("gamma must be a nonnegative integer")
    if score_floor is not None and score_col is None:
        raise ValueError("score_floor requires score_col")
    if score_floor is not None and not math.isfinite(score_floor):
        raise ValueError("score_floor must be finite")

    node_frame, edge_frame = _prepare_graph(
        nodes,
        edges,
        node_id_col=node_id_col,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        lower_objective_col=lower_objective_col,
        upper_objective_col=upper_objective_col,
        omitted_col=omitted_col,
        score_col=score_col,
    )
    if matched_col is None:
        required_nodes = node_frame[node_id_col].tolist()
    else:
        if matched_col not in node_frame:
            raise ValueError(f"nodes are missing {matched_col!r}")
        matched = pd.to_numeric(node_frame[matched_col], errors="coerce")
        if matched.isna().any() or not matched.isin([0, 1]).all():
            raise ValueError(f"{matched_col} must contain only 0/1 values")
        required_nodes = node_frame.loc[matched.astype(bool), node_id_col].tolist()
    if not required_nodes:
        raise ValueError("at least one required node is needed")
    if len(required_nodes) % 2:
        infeasible = _unresolved_solution(
            "PROVEN_INFEASIBLE", str(backend), "odd number of required nodes"
        )
        return CertifiedLinearEndpoints(
            status="PROVEN_INFEASIBLE",
            certified=True,
            lower=None,
            upper=None,
            normalizer=normalizer,
            candidate_edge_count=0,
            required_node_count=len(required_nodes),
            gamma=gamma,
            score_floor=score_floor,
            lower_solution=infeasible,
            upper_solution=infeasible,
            warning="An exact cover requires an even number of required nodes.",
        )

    required_set = set(required_nodes)
    edge_frame = edge_frame[
        edge_frame[u_col].isin(required_set) & edge_frame[v_col].isin(required_set)
    ].reset_index(drop=True)
    lower_objective = edge_frame[lower_objective_col].to_numpy(dtype=float)
    upper_objective = edge_frame[upper_objective_col].to_numpy(dtype=float)
    lower_solution = _solve_one(
        edge_frame,
        required_nodes,
        lower_objective,
        sense="min",
        gamma=gamma,
        score_col=score_col,
        score_floor=score_floor,
        backend=backend,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        time_limit=time_limit,
        fallback_max_states=fallback_max_states,
    )
    upper_solution = _solve_one(
        edge_frame,
        required_nodes,
        upper_objective,
        sense="max",
        gamma=gamma,
        score_col=score_col,
        score_floor=score_floor,
        backend=backend,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        time_limit=time_limit,
        fallback_max_states=fallback_max_states,
    )
    exact_endpoints = (
        lower_solution.status == "OPTIMAL"
        and upper_solution.status == "OPTIMAL"
        and lower_solution.certified
        and upper_solution.certified
    )
    endpoint_statuses = {"OPTIMAL", "NUMERICALLY_OPTIMAL"}
    numerical_endpoints = (
        lower_solution.status in endpoint_statuses
        and upper_solution.status in endpoint_statuses
    )
    domain_infeasible = (
        lower_solution.status == "PROVEN_INFEASIBLE"
        and upper_solution.status == "PROVEN_INFEASIBLE"
    )
    certified = exact_endpoints or domain_infeasible
    if exact_endpoints:
        status = "OPTIMAL"
        warning = ""
    elif numerical_endpoints:
        status = "NUMERICALLY_OPTIMAL"
        warning = (
            "Endpoints are feasible solver optima within floating-point MILP "
            "tolerances, not exact mathematical certificates."
        )
    elif domain_infeasible:
        status = "PROVEN_INFEASIBLE"
        warning = "The structural domain has no feasible exact cover."
    else:
        status = "UNRESOLVED"
        warning = "At least one endpoint lacks a global optimality certificate."
    return CertifiedLinearEndpoints(
        status=status,
        certified=certified,
        lower=(
            lower_solution.objective_sum / normalizer
            if lower_solution.objective_sum is not None
            and lower_solution.status in endpoint_statuses
            else None
        ),
        upper=(
            upper_solution.objective_sum / normalizer
            if upper_solution.objective_sum is not None
            and upper_solution.status in endpoint_statuses
            else None
        ),
        normalizer=normalizer,
        candidate_edge_count=len(edge_frame),
        required_node_count=len(required_nodes),
        gamma=gamma,
        score_floor=score_floor,
        lower_solution=lower_solution,
        upper_solution=upper_solution,
        warning=warning,
    )


def add_independent_same_bin_envelopes(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    node_id_col: str = "node_id",
    u_col: str = "u",
    v_col: str = "v",
    ses_bin_col: str = "ses_bin",
    support_col: str | None = None,
    all_bins: Sequence[object] | None = None,
    lower_col: str = "same_bin_lower",
    upper_col: str = "same_bin_upper",
) -> pd.DataFrame:
    """Add edgewise exact envelopes for independent Cartesian bin supports.

    Observed values have singleton support.  A missing value must have an
    explicit iterable in ``support_col`` or use the common ``all_bins`` set.
    The shortcut is globally exact only when every node is selected once, the
    graph/population/denominator are fixed, and there are no cross-node count
    or suppression constraints.
    """

    if node_id_col not in nodes or ses_bin_col not in nodes:
        raise ValueError("nodes must contain node IDs and SES bins")
    node_frame = nodes.copy()
    node_frame[node_id_col] = _validated_string_series(
        node_frame[node_id_col], node_id_col
    )
    if node_frame[node_id_col].duplicated().any():
        raise ValueError(f"{node_id_col} must be unique")
    if support_col is not None and support_col not in node_frame:
        raise ValueError(f"nodes are missing {support_col!r}")

    def support_set(raw: object, label: str) -> frozenset[object]:
        if isinstance(raw, (str, bytes)) or not isinstance(
            raw, (Sequence, set, frozenset, np.ndarray, pd.Series)
        ):
            values = [raw]
        else:
            values = list(raw)
        if not values:
            raise ValueError(f"{label} must not be empty")
        cleaned: set[object] = set()
        for value in values:
            try:
                missing = bool(pd.isna(value))
            except (TypeError, ValueError):
                missing = False
            if missing:
                raise ValueError(f"{label} must not contain missing values")
            try:
                cleaned.add(value)
            except TypeError as exc:
                raise ValueError(f"{label} values must be hashable") from exc
        return frozenset(cleaned)

    common_support = (
        support_set(all_bins, "all_bins") if all_bins is not None else None
    )
    supports: dict[str, frozenset[object]] = {}
    for _, row in node_frame.iterrows():
        node_id = row[node_id_col]
        value = row[ses_bin_col]
        if pd.notna(value):
            supports[node_id] = frozenset({value})
        elif support_col is not None:
            supports[node_id] = support_set(
                row[support_col], f"{support_col} for node {node_id!r}"
            )
        elif common_support is not None:
            supports[node_id] = common_support
        else:
            raise ValueError(
                "missing SES bins require support_col or an explicit all_bins set"
            )

    out = edges.copy()
    if u_col not in out or v_col not in out:
        raise ValueError("edges must contain endpoint columns")
    out[u_col] = _validated_string_series(out[u_col], u_col)
    out[v_col] = _validated_string_series(out[v_col], v_col)
    known_ids = set(supports)
    unknown = (set(out[u_col]) | set(out[v_col])) - known_ids
    if unknown:
        raise ValueError(f"edge references unknown node {sorted(unknown)[0]!r}")
    lower: list[float] = []
    upper: list[float] = []
    for u, v in zip(out[u_col], out[v_col]):
        left = supports[u]
        right = supports[v]
        lower.append(float(len(left) == 1 and left == right))
        upper.append(float(bool(left & right)))
    out[lower_col] = lower
    out[upper_col] = upper
    return out


def residualized_treatment_weights(
    nuisance_design: np.ndarray,
    treatment: np.ndarray,
    *,
    tolerance: float = 1e-10,
) -> np.ndarray:
    """Return FWL weights ``r / (r' treatment)`` using a stable least squares fit."""

    x = np.asarray(nuisance_design, dtype=float)
    d = np.asarray(treatment, dtype=float).reshape(-1)
    if not math.isfinite(tolerance) or not (0.0 < tolerance < 1.0):
        raise ValueError("tolerance must be finite and lie strictly between 0 and 1")
    if x.ndim != 2 or x.shape[0] != len(d):
        raise ValueError("nuisance design and treatment have incompatible shapes")
    if not np.isfinite(x).all() or not np.isfinite(d).all():
        raise ValueError("design and treatment must be finite")
    treatment_scale = float(np.max(np.abs(d)))
    if treatment_scale == 0.0:
        raise ValueError("treatment must not be identically zero")
    scaled_treatment = d / treatment_scale

    column_scales = np.max(np.abs(x), axis=0) if x.shape[1] else np.array([])
    nonzero = column_scales > 0.0
    if nonzero.any():
        max_scaled = x[:, nonzero] / column_scales[nonzero]
        column_norms = np.linalg.norm(max_scaled, axis=0)
        scaled_design = max_scaled / column_norms
        left, singular_values, _ = np.linalg.svd(
            scaled_design, full_matrices=False
        )
        if len(singular_values) and singular_values[0] > 0.0:
            machine_floor = (
                np.finfo(float).eps
                * max(scaled_design.shape)
                * singular_values[0]
            )
            ambiguous = (singular_values > machine_floor) & (
                singular_values <= tolerance * singular_values[0]
            )
            if ambiguous.any():
                raise ValueError(
                    "nuisance design has numerically ambiguous rank; "
                    "reparameterize or remove ill-conditioned columns"
                )
            rank = int(np.sum(singular_values > tolerance * singular_values[0]))
            basis = left[:, :rank]
            fitted = basis @ (basis.T @ scaled_treatment)
        else:
            fitted = np.zeros_like(scaled_treatment)
    else:
        scaled_design = np.empty((len(d), 0), dtype=float)
        fitted = np.zeros_like(scaled_treatment)
    residual = scaled_treatment - fitted
    residual_norm = float(np.linalg.norm(residual))
    denominator = float(residual @ scaled_treatment)
    treatment_energy = float(scaled_treatment @ scaled_treatment)
    if treatment_energy == 0.0 or denominator / treatment_energy <= tolerance:
        raise ValueError("treatment is not identified after residualizing nuisance terms")
    for column in scaled_design.T:
        column_norm = float(np.linalg.norm(column))
        if column_norm == 0.0:
            continue
        normalized_inner = abs(float(column @ residual)) / max(
            column_norm * max(residual_norm, np.finfo(float).tiny),
            np.finfo(float).tiny,
        )
        if normalized_inner > 10.0 * tolerance:
            raise RuntimeError("residualized treatment failed the orthogonality check")
    weights = (residual / denominator) / treatment_scale
    if not np.isfinite(weights).all():
        raise ValueError("FWL weights are not finitely representable")
    return weights


def add_signed_edge_envelopes(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    node_weight_col: str,
    exposure_lower_col: str,
    exposure_upper_col: str,
    node_id_col: str = "node_id",
    u_col: str = "u",
    v_col: str = "v",
    lower_col: str = "linear_lower",
    upper_col: str = "linear_upper",
) -> pd.DataFrame:
    """Convert endpoint exposure ranges into signed edge-coefficient ranges."""

    if node_weight_col not in nodes:
        raise ValueError(f"nodes are missing {node_weight_col!r}")
    out = edges.copy()
    node_frame = nodes.copy()
    if node_id_col not in node_frame:
        raise ValueError(f"nodes are missing {node_id_col!r}")
    node_frame[node_id_col] = _validated_string_series(
        node_frame[node_id_col], node_id_col
    )
    if node_frame[node_id_col].duplicated().any():
        raise ValueError(f"{node_id_col} must be unique")
    weights = node_frame.set_index(node_id_col)[node_weight_col]
    if u_col not in out or v_col not in out:
        raise ValueError("edges must contain endpoint columns")
    out[u_col] = _validated_string_series(out[u_col], u_col)
    out[v_col] = _validated_string_series(out[v_col], v_col)
    unknown = (set(out[u_col]) | set(out[v_col])) - set(weights.index)
    if unknown:
        raise ValueError(f"edge references unknown node {sorted(unknown)[0]!r}")
    k = out[u_col].map(weights).to_numpy(dtype=float) + out[v_col].map(
        weights
    ).to_numpy(dtype=float)
    exposure_lower = pd.to_numeric(out[exposure_lower_col], errors="coerce").to_numpy(
        dtype=float
    )
    exposure_upper = pd.to_numeric(out[exposure_upper_col], errors="coerce").to_numpy(
        dtype=float
    )
    if not np.isfinite(k).all() or not np.isfinite(exposure_lower).all() or not np.isfinite(
        exposure_upper
    ).all():
        raise ValueError("weights and exposure endpoints must be finite")
    if (exposure_lower > exposure_upper).any():
        raise ValueError("exposure lower endpoints exceed upper endpoints")
    first = k * exposure_lower
    second = k * exposure_upper
    out[lower_col] = np.minimum(first, second)
    out[upper_col] = np.maximum(first, second)
    return out


def normalized_regret_floor(
    minimum_score: float,
    maximum_score: float,
    tau: float,
) -> float:
    """Return the score floor for a positive-affine-invariant within-map radius."""

    if not (0.0 <= tau <= 1.0):
        raise ValueError("tau must lie in [0, 1]")
    if not all(math.isfinite(value) for value in (minimum_score, maximum_score)):
        raise ValueError("score extrema must be finite")
    if minimum_score > maximum_score:
        raise ValueError("minimum_score exceeds maximum_score")
    return maximum_score - tau * (maximum_score - minimum_score)
