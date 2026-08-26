#!/usr/bin/env python3
"""Joint categorical-label and boundary-safe matching endpoints.

The feasible worlds in this module contain both a matching and one latent
categorical label for every supplied node.  The interface is deliberately
small and explicit:

* ``core`` nodes have matching degree exactly one;
* ``buffer`` nodes have degree at most one;
* ``context_only`` nodes do not match, but do participate in label counts;
* every edge must touch a core node (buffer--buffer and context edges are
  rejected);
* every node chooses exactly one value from its declared support;
* optional cell/value count bounds couple those choices globally; and
* the endpoint is the fraction of *core incidences* whose selected partner has
  the same ``query_bin``.

Thus a core--core edge contributes two incidences and a core--buffer edge one;
the fixed denominator is the number of core nodes.  Optional edge scores use
the same core-incidence weighting.  ``Gamma`` counts selected edges marked as
omitted/supergraph edges.

The exhaustive backend is an exact certificate for the declared finite Python
inputs.  SciPy/HiGHS is a floating-point MILP backend and is therefore reported
as numerical, even when HiGHS reports a zero MIP gap.  No result here certifies
that the supplied graph, supports, or count bounds contain the data-generating
truth.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Any, Hashable, Literal, Mapping, Sequence

import numpy as np
import pandas as pd

try:
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    SCIPY_MILP_AVAILABLE = True
except (ImportError, AttributeError):  # pragma: no cover - lean environments
    SCIPY_MILP_AVAILABLE = False


Backend = Literal["auto", "scipy", "fallback"]
Sense = Literal["min", "max"]
VALID_ROLES = frozenset({"core", "buffer", "context_only"})


@dataclass(frozen=True)
class JointWorldSolution:
    """One endpoint solution or unresolved incumbent."""

    status: str
    certified: bool
    feasible_incumbent: bool
    objective_value: float | None
    selected_edge_ids: tuple[str, ...]
    label_assignments: tuple[tuple[str, Hashable], ...]
    omitted_edge_count: int | None
    total_score: float | None
    backend: str
    message: str
    mip_gap: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["selected_edge_ids"] = list(self.selected_edge_ids)
        payload["label_assignments"] = dict(self.label_assignments)
        return payload


@dataclass(frozen=True)
class JointLabelMatchingEndpoints:
    """Attained lower and upper endpoints over the declared feasible worlds."""

    status: str
    certified: bool
    lower: float | None
    upper: float | None
    core_node_count: int
    buffer_node_count: int
    context_only_node_count: int
    candidate_edge_count: int
    gamma: int | None
    score_floor: float | None
    lower_solution: JointWorldSolution
    upper_solution: JointWorldSolution
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lower_solution"] = self.lower_solution.to_dict()
        payload["upper_solution"] = self.upper_solution.to_dict()
        return payload


@dataclass(frozen=True)
class _CountBound:
    cell: Hashable
    value: Hashable
    lower: int
    upper: int


@dataclass
class _PreparedProblem:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    supports: list[tuple[Hashable, ...]]
    allowed_pairs: list[frozenset[tuple[Hashable, Hashable]]]
    query_bin: dict[Hashable, Hashable]
    count_bounds: list[_CountBound]
    node_id_col: str
    role_col: str
    cell_col: str
    u_col: str
    v_col: str
    edge_id_col: str
    score_available: bool

    @property
    def node_ids(self) -> list[str]:
        return self.nodes[self.node_id_col].tolist()

    @property
    def roles(self) -> list[str]:
        return self.nodes[self.role_col].tolist()

    @property
    def core_indices(self) -> list[int]:
        return [i for i, role in enumerate(self.roles) if role == "core"]


class _StateLimit(RuntimeError):
    pass


def _is_missing(value: Any) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if isinstance(missing, (bool, np.bool_)) else False


def _require_hashable(value: Any, name: str) -> Hashable:
    if _is_missing(value):
        raise ValueError(f"{name} must not be missing")
    try:
        hash(value)
    except TypeError as exc:
        raise ValueError(f"{name} values must be hashable") from exc
    return value


def _string_ids(series: pd.Series, name: str) -> pd.Series:
    if series.isna().any():
        raise ValueError(f"{name} must not contain null values")
    result = series.astype(str)
    if result.str.strip().eq("").any():
        raise ValueError(f"{name} must not contain blank values")
    return result


def _explicit_support(raw: Any, node_id: str) -> tuple[Hashable, ...]:
    if isinstance(raw, (str, bytes)) or raw is None:
        raise ValueError(
            f"label support for node {node_id!r} must be an explicit nonempty sequence"
        )
    if isinstance(raw, (set, frozenset)):
        values = sorted(raw, key=repr)
    else:
        try:
            values = list(raw)
        except TypeError as exc:
            raise ValueError(
                f"label support for node {node_id!r} must be an explicit sequence"
            ) from exc
    if not values:
        raise ValueError(f"label support for node {node_id!r} must not be empty")
    result: list[Hashable] = []
    seen: set[Hashable] = set()
    for value in values:
        item = _require_hashable(value, f"label support for node {node_id!r}")
        if item in seen:
            raise ValueError(f"label support for node {node_id!r} has duplicates")
        seen.add(item)
        result.append(item)
    return tuple(result)


def _catalog_mapping(
    label_catalog: pd.DataFrame | Mapping[Hashable, Hashable],
    *,
    value_col: str,
    query_bin_col: str,
) -> dict[Hashable, Hashable]:
    if isinstance(label_catalog, Mapping):
        items = list(label_catalog.items())
    elif isinstance(label_catalog, pd.DataFrame):
        required = {value_col, query_bin_col}
        if missing := required - set(label_catalog.columns):
            raise ValueError(f"label_catalog is missing columns: {sorted(missing)}")
        items = list(zip(label_catalog[value_col], label_catalog[query_bin_col]))
    else:
        raise TypeError("label_catalog must be a mapping or pandas DataFrame")
    if not items:
        raise ValueError("label_catalog must not be empty")
    result: dict[Hashable, Hashable] = {}
    for raw_value, raw_bin in items:
        value = _require_hashable(raw_value, value_col)
        query_bin = _require_hashable(raw_bin, query_bin_col)
        if value in result:
            raise ValueError(f"duplicate label_catalog value {value!r}")
        result[value] = query_bin
    return result


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a nonnegative integer")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a nonnegative integer") from exc
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(numeric)


def _prepare_problem(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    label_catalog: pd.DataFrame | Mapping[Hashable, Hashable],
    count_bounds: pd.DataFrame | None,
    *,
    node_id_col: str,
    role_col: str,
    support_col: str,
    cell_col: str,
    value_col: str,
    query_bin_col: str,
    count_lower_col: str,
    count_upper_col: str,
    u_col: str,
    v_col: str,
    edge_id_col: str,
    score_col: str | None,
    omitted_col: str | None,
    allowed_label_pairs_col: str | None,
) -> tuple[_PreparedProblem, str | None]:
    required_node_columns = {node_id_col, role_col, support_col, cell_col}
    if missing := required_node_columns - set(nodes.columns):
        raise ValueError(f"nodes are missing columns: {sorted(missing)}")
    required_edge_columns = {u_col, v_col}
    if missing := required_edge_columns - set(edges.columns):
        raise ValueError(f"edges are missing columns: {sorted(missing)}")

    node_frame = nodes.copy().reset_index(drop=True)
    edge_frame = edges.copy().reset_index(drop=True)
    node_frame[node_id_col] = _string_ids(node_frame[node_id_col], node_id_col)
    if node_frame[node_id_col].duplicated().any():
        raise ValueError(f"{node_id_col} must be unique")
    roles = node_frame[role_col].astype(str)
    invalid_roles = sorted(set(roles) - VALID_ROLES)
    if invalid_roles:
        raise ValueError(f"invalid node role {invalid_roles[0]!r}")
    node_frame[role_col] = roles
    cells = [
        _require_hashable(value, cell_col) for value in node_frame[cell_col].tolist()
    ]
    node_frame[cell_col] = pd.Series(cells, dtype=object)
    supports = [
        _explicit_support(raw, node_id)
        for raw, node_id in zip(
            node_frame[support_col], node_frame[node_id_col], strict=True
        )
    ]
    query_bin = _catalog_mapping(
        label_catalog, value_col=value_col, query_bin_col=query_bin_col
    )
    for node_id, support in zip(node_frame[node_id_col], supports, strict=True):
        missing_values = [value for value in support if value not in query_bin]
        if missing_values:
            raise ValueError(
                f"support for node {node_id!r} contains uncatalogued value "
                f"{missing_values[0]!r}"
            )

    if edge_id_col not in edge_frame:
        edge_frame[edge_id_col] = [f"e{i}" for i in range(len(edge_frame))]
    edge_frame[edge_id_col] = _string_ids(edge_frame[edge_id_col], edge_id_col)
    edge_frame[u_col] = _string_ids(edge_frame[u_col], u_col)
    edge_frame[v_col] = _string_ids(edge_frame[v_col], v_col)
    if edge_frame[edge_id_col].duplicated().any():
        raise ValueError(f"{edge_id_col} must be unique")
    if (edge_frame[u_col] == edge_frame[v_col]).any():
        raise ValueError("self-loop candidate edges are not permitted")
    node_ids = set(node_frame[node_id_col])
    unknown = (set(edge_frame[u_col]) | set(edge_frame[v_col])) - node_ids
    if unknown:
        raise ValueError(f"edge references unknown node {sorted(unknown)[0]!r}")
    canonical: set[tuple[str, str]] = set()
    for u, v in zip(edge_frame[u_col], edge_frame[v_col], strict=True):
        pair = tuple(sorted((u, v)))
        if pair in canonical:
            raise ValueError(f"duplicate undirected candidate pair {pair!r}")
        canonical.add(pair)

    node_role = dict(zip(node_frame[node_id_col], node_frame[role_col], strict=True))
    node_position = {
        node_id: index for index, node_id in enumerate(node_frame[node_id_col])
    }
    core_incidence: list[int] = []
    for u, v in zip(edge_frame[u_col], edge_frame[v_col], strict=True):
        left, right = node_role[u], node_role[v]
        if "context_only" in (left, right):
            raise ValueError("context_only nodes must not appear in candidate edges")
        if left == right == "buffer":
            raise ValueError("buffer--buffer candidate edges are not permitted")
        incidence = int(left == "core") + int(right == "core")
        if incidence == 0:  # defensive; the two explicit checks imply this
            raise ValueError("every candidate edge must touch a core node")
        core_incidence.append(incidence)
    edge_frame["_core_incidence"] = np.asarray(core_incidence, dtype=int)

    allowed_pairs: list[frozenset[tuple[Hashable, Hashable]]] = []
    has_pair_column = (
        allowed_label_pairs_col is not None
        and allowed_label_pairs_col in edge_frame.columns
    )
    for edge_number, row in edge_frame.iterrows():
        u_index = node_position[row[u_col]]
        v_index = node_position[row[v_col]]
        full_pairs = frozenset(
            (left, right)
            for left in supports[u_index]
            for right in supports[v_index]
        )
        raw = row[allowed_label_pairs_col] if has_pair_column else None
        if raw is None or _is_missing(raw):
            allowed_pairs.append(full_pairs)
            continue
        if isinstance(raw, (str, bytes)):
            raise ValueError(
                f"{allowed_label_pairs_col} in edge row {edge_number} must be "
                "an iterable of ordered label pairs"
            )
        try:
            raw_pairs = list(raw)
        except TypeError as exc:
            raise ValueError(
                f"{allowed_label_pairs_col} in edge row {edge_number} must be "
                "an iterable of ordered label pairs"
            ) from exc
        parsed: set[tuple[Hashable, Hashable]] = set()
        for raw_pair in raw_pairs:
            if isinstance(raw_pair, (str, bytes)):
                raise ValueError("each allowed label pair must contain two values")
            try:
                pair_values = list(raw_pair)
            except TypeError as exc:
                raise ValueError("each allowed label pair must contain two values") from exc
            if len(pair_values) != 2:
                raise ValueError("each allowed label pair must contain two values")
            left = _require_hashable(pair_values[0], "allowed left label")
            right = _require_hashable(pair_values[1], "allowed right label")
            if left not in supports[u_index] or right not in supports[v_index]:
                raise ValueError(
                    f"allowed label pair {(left, right)!r} in edge row {edge_number} "
                    "is outside its endpoint supports"
                )
            if (left, right) in parsed:
                raise ValueError(
                    f"duplicate allowed label pair {(left, right)!r} in edge row "
                    f"{edge_number}"
                )
            parsed.add((left, right))
        allowed_pairs.append(frozenset(parsed))

    score_available = score_col is not None
    if score_col is None:
        edge_frame["_score"] = 0.0
    else:
        if score_col not in edge_frame:
            raise ValueError(f"edges are missing {score_col!r}")
        scores = pd.to_numeric(edge_frame[score_col], errors="coerce")
        if scores.isna().any() or not np.isfinite(scores.to_numpy(dtype=float)).all():
            raise ValueError(f"{score_col} must be finite")
        edge_frame["_score"] = scores.astype(float)

    if omitted_col is None:
        edge_frame["_omitted"] = 0
    else:
        if omitted_col not in edge_frame:
            raise ValueError(f"edges are missing {omitted_col!r}")
        omitted = pd.to_numeric(edge_frame[omitted_col], errors="coerce")
        if omitted.isna().any() or not omitted.isin([0, 1]).all():
            raise ValueError(f"{omitted_col} must contain only 0/1 values")
        edge_frame["_omitted"] = omitted.astype(int)

    parsed_bounds: list[_CountBound] = []
    if count_bounds is not None:
        required_count_columns = {
            cell_col,
            value_col,
            count_lower_col,
            count_upper_col,
        }
        if missing := required_count_columns - set(count_bounds.columns):
            raise ValueError(f"count_bounds is missing columns: {sorted(missing)}")
        seen_bounds: set[tuple[Hashable, Hashable]] = set()
        known_cells = set(cells)
        for row_number, row in count_bounds.reset_index(drop=True).iterrows():
            cell = _require_hashable(row[cell_col], cell_col)
            value = _require_hashable(row[value_col], value_col)
            if cell not in known_cells:
                raise ValueError(f"count bound references unknown cell {cell!r}")
            if value not in query_bin:
                raise ValueError(f"count bound references uncatalogued value {value!r}")
            key = (cell, value)
            if key in seen_bounds:
                raise ValueError(f"duplicate count bound for {key!r}")
            seen_bounds.add(key)
            lower = _nonnegative_integer(
                row[count_lower_col], f"count lower bound in row {row_number}"
            )
            upper = _nonnegative_integer(
                row[count_upper_col], f"count upper bound in row {row_number}"
            )
            if lower > upper:
                raise ValueError(f"count lower bound exceeds upper bound for {key!r}")
            parsed_bounds.append(_CountBound(cell, value, lower, upper))

    problem = _PreparedProblem(
        nodes=node_frame,
        edges=edge_frame,
        supports=supports,
        allowed_pairs=allowed_pairs,
        query_bin=query_bin,
        count_bounds=parsed_bounds,
        node_id_col=node_id_col,
        role_col=role_col,
        cell_col=cell_col,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        score_available=score_available,
    )

    core_ids = set(
        node_frame.loc[node_frame[role_col] == "core", node_id_col].tolist()
    )
    if not core_ids:
        raise ValueError("at least one core node is required")
    endpoint_counts = pd.concat([edge_frame[u_col], edge_frame[v_col]]).value_counts()
    isolated = [node_id for node_id in core_ids if endpoint_counts.get(node_id, 0) == 0]
    if isolated:
        return problem, f"core node {sorted(isolated)[0]!r} has no candidate edge"

    for bound in parsed_bounds:
        relevant = [
            support
            for cell, support in zip(cells, supports, strict=True)
            if cell == bound.cell
        ]
        fixed = sum(support == (bound.value,) for support in relevant)
        possible = sum(bound.value in support for support in relevant)
        if bound.upper < fixed:
            return problem, (
                f"count upper bound for {(bound.cell, bound.value)!r} is below "
                "the forced singleton count"
            )
        if bound.lower > possible:
            return problem, (
                f"count lower bound for {(bound.cell, bound.value)!r} exceeds "
                "the support-implied maximum"
            )
    return problem, None


def _blank_solution(
    status: str,
    backend: str,
    message: str,
    *,
    certified: bool = False,
) -> JointWorldSolution:
    return JointWorldSolution(
        status=status,
        certified=certified,
        feasible_incumbent=False,
        objective_value=None,
        selected_edge_ids=(),
        label_assignments=(),
        omitted_edge_count=None,
        total_score=None,
        backend=backend,
        message=message,
    )


def _world_solution(
    problem: _PreparedProblem,
    selected: Sequence[int],
    labels: Sequence[Hashable],
    *,
    status: str,
    certified: bool,
    backend: str,
    message: str,
    mip_gap: float | None = None,
) -> JointWorldSolution:
    selected_array = np.asarray(selected, dtype=int)
    numerator = 0
    for edge_index in selected_array:
        row = problem.edges.iloc[int(edge_index)]
        u_index = problem.nodes.index[
            problem.nodes[problem.node_id_col] == row[problem.u_col]
        ][0]
        v_index = problem.nodes.index[
            problem.nodes[problem.node_id_col] == row[problem.v_col]
        ][0]
        if problem.query_bin[labels[u_index]] == problem.query_bin[labels[v_index]]:
            numerator += int(row["_core_incidence"])
    core_count = len(problem.core_indices)
    weighted_score = None
    if problem.score_available and len(problem.edges):
        weighted_score = float(
            np.sum(
                problem.edges.iloc[selected_array]["_score"].to_numpy(dtype=np.longdouble)
                * problem.edges.iloc[selected_array]["_core_incidence"].to_numpy(
                    dtype=np.longdouble
                ),
                dtype=np.longdouble,
            )
        )
    return JointWorldSolution(
        status=status,
        certified=certified,
        feasible_incumbent=True,
        objective_value=float(Fraction(numerator, core_count)),
        selected_edge_ids=tuple(
            problem.edges.iloc[selected_array][problem.edge_id_col].astype(str)
        ),
        label_assignments=tuple(zip(problem.node_ids, labels, strict=True)),
        omitted_edge_count=int(
            problem.edges.iloc[selected_array]["_omitted"].sum()
        ),
        total_score=weighted_score,
        backend=backend,
        message=message,
        mip_gap=mip_gap,
    )


def _fallback_endpoints(
    problem: _PreparedProblem,
    *,
    gamma: int | None,
    score_floor: float | None,
    max_states: int,
) -> tuple[JointWorldSolution, JointWorldSolution]:
    states = 0

    def tick() -> None:
        nonlocal states
        states += 1
        if states > max_states:
            raise _StateLimit(f"fallback enumeration exceeded {max_states:,} states")

    node_count = len(problem.nodes)
    bounds = problem.count_bounds
    bound_lookup = {
        (bound.cell, bound.value): index for index, bound in enumerate(bounds)
    }
    node_order = sorted(
        range(node_count),
        key=lambda i: (len(problem.supports[i]), problem.node_ids[i]),
    )
    suffix_possible = np.zeros((node_count + 1, len(bounds)), dtype=int)
    for position in range(node_count - 1, -1, -1):
        suffix_possible[position] = suffix_possible[position + 1]
        node_index = node_order[position]
        cell = problem.nodes.iloc[node_index][problem.cell_col]
        for value in problem.supports[node_index]:
            bound_index = bound_lookup.get((cell, value))
            if bound_index is not None:
                suffix_possible[position, bound_index] += 1

    assignments: list[tuple[Hashable, ...]] = []
    current: list[Hashable | None] = [None] * node_count
    counts = np.zeros(len(bounds), dtype=int)

    def enumerate_labels(position: int) -> None:
        tick()
        if position == node_count:
            if all(
                bound.lower <= counts[index] <= bound.upper
                for index, bound in enumerate(bounds)
            ):
                assignments.append(tuple(current))  # type: ignore[arg-type]
            return
        node_index = node_order[position]
        cell = problem.nodes.iloc[node_index][problem.cell_col]
        for value in problem.supports[node_index]:
            bound_index = bound_lookup.get((cell, value))
            if bound_index is not None:
                counts[bound_index] += 1
                if counts[bound_index] > bounds[bound_index].upper:
                    counts[bound_index] -= 1
                    continue
            impossible = any(
                counts[index] + suffix_possible[position + 1, index] < bound.lower
                for index, bound in enumerate(bounds)
            )
            if not impossible:
                current[node_index] = value
                enumerate_labels(position + 1)
                current[node_index] = None
            if bound_index is not None:
                counts[bound_index] -= 1

    try:
        enumerate_labels(0)
    except _StateLimit as exc:
        unresolved = _blank_solution("UNRESOLVED", "fallback", str(exc))
        return unresolved, unresolved
    if not assignments:
        infeasible = _blank_solution(
            "PROVEN_INFEASIBLE",
            "fallback",
            f"enumerated {states:,} states; no feasible label assignment",
            certified=True,
        )
        return infeasible, infeasible

    id_to_index = {node_id: i for i, node_id in enumerate(problem.node_ids)}
    core = set(problem.core_indices)
    buffer = {i for i, role in enumerate(problem.roles) if role == "buffer"}
    endpoints = [
        (id_to_index[u], id_to_index[v])
        for u, v in zip(
            problem.edges[problem.u_col], problem.edges[problem.v_col], strict=True
        )
    ]
    incident: dict[int, list[int]] = {index: [] for index in core}
    for edge_index, (u, v) in enumerate(endpoints):
        if u in core:
            incident[u].append(edge_index)
        if v in core:
            incident[v].append(edge_index)
    omitted = problem.edges["_omitted"].to_numpy(dtype=int)
    exact_scores = [
        Fraction.from_float(float(score))
        * int(core_weight)
        for score, core_weight in zip(
            problem.edges["_score"], problem.edges["_core_incidence"], strict=True
        )
    ]
    exact_floor = (
        Fraction.from_float(float(score_floor)) if score_floor is not None else None
    )
    matchings: list[tuple[tuple[int, ...], int, Fraction]] = []

    def enumerate_matchings(
        covered_core: frozenset[int],
        used_buffer: frozenset[int],
        selected: tuple[int, ...],
        omitted_count: int,
        score: Fraction,
    ) -> None:
        tick()
        if gamma is not None and omitted_count > gamma:
            return
        remaining = core - set(covered_core)
        if not remaining:
            if exact_floor is not None and score < exact_floor:
                return
            matchings.append((selected, omitted_count, score))
            return

        choices: dict[int, list[int]] = {}
        for node in remaining:
            feasible_edges: list[int] = []
            for edge_index in incident[node]:
                u, v = endpoints[edge_index]
                other = v if u == node else u
                if other in core and other not in remaining:
                    continue
                if other in buffer and other in used_buffer:
                    continue
                feasible_edges.append(edge_index)
            if not feasible_edges:
                return
            choices[node] = feasible_edges
        node = min(choices, key=lambda i: (len(choices[i]), problem.node_ids[i]))
        for edge_index in choices[node]:
            u, v = endpoints[edge_index]
            edge_core = frozenset(index for index in (u, v) if index in core)
            edge_buffer = frozenset(index for index in (u, v) if index in buffer)
            enumerate_matchings(
                covered_core | edge_core,
                used_buffer | edge_buffer,
                selected + (edge_index,),
                omitted_count + int(omitted[edge_index]),
                score + exact_scores[edge_index],
            )

    try:
        enumerate_matchings(frozenset(), frozenset(), (), 0, Fraction(0))
    except _StateLimit as exc:
        unresolved = _blank_solution("UNRESOLVED", "fallback", str(exc))
        return unresolved, unresolved
    if not matchings:
        infeasible = _blank_solution(
            "PROVEN_INFEASIBLE",
            "fallback",
            f"enumerated {states:,} states; no feasible matching",
            certified=True,
        )
        return infeasible, infeasible

    lower_record: tuple[int, tuple[int, ...], tuple[Hashable, ...]] | None = None
    upper_record: tuple[int, tuple[int, ...], tuple[Hashable, ...]] | None = None
    core_count = len(core)
    try:
        for labels in assignments:
            for selected, _, _ in matchings:
                tick()
                if any(
                    (labels[endpoints[edge_index][0]], labels[endpoints[edge_index][1]])
                    not in problem.allowed_pairs[edge_index]
                    for edge_index in selected
                ):
                    continue
                numerator = 0
                for edge_index in selected:
                    u, v = endpoints[edge_index]
                    if (
                        problem.query_bin[labels[u]]
                        == problem.query_bin[labels[v]]
                    ):
                        numerator += int(
                            problem.edges.iloc[edge_index]["_core_incidence"]
                        )
                if lower_record is None or numerator < lower_record[0]:
                    lower_record = (numerator, selected, labels)
                if upper_record is None or numerator > upper_record[0]:
                    upper_record = (numerator, selected, labels)
    except _StateLimit as exc:
        message = str(exc)
        lower = (
            _world_solution(
                problem,
                lower_record[1],
                lower_record[2],
                status="UNRESOLVED",
                certified=False,
                backend="fallback",
                message=message,
            )
            if lower_record is not None
            else _blank_solution("UNRESOLVED", "fallback", message)
        )
        upper = (
            _world_solution(
                problem,
                upper_record[1],
                upper_record[2],
                status="UNRESOLVED",
                certified=False,
                backend="fallback",
                message=message,
            )
            if upper_record is not None
            else _blank_solution("UNRESOLVED", "fallback", message)
        )
        return lower, upper

    if lower_record is None or upper_record is None:
        infeasible = _blank_solution(
            "PROVEN_INFEASIBLE",
            "fallback",
            f"enumerated {states:,} states; no jointly feasible label/matching world",
            certified=True,
        )
        return infeasible, infeasible
    assert core_count > 0
    message = (
        f"enumerated {len(assignments):,} label assignments, "
        f"{len(matchings):,} matchings, and {states:,} states"
    )
    lower = _world_solution(
        problem,
        lower_record[1],
        lower_record[2],
        status="EXACT_OPTIMAL",
        certified=True,
        backend="fallback",
        message=message,
    )
    upper = _world_solution(
        problem,
        upper_record[1],
        upper_record[2],
        status="EXACT_OPTIMAL",
        certified=True,
        backend="fallback",
        message=message,
    )
    return lower, upper


def _validate_incumbent(
    problem: _PreparedProblem,
    selected: Sequence[int],
    labels: Sequence[Hashable],
    *,
    gamma: int | None,
    score_floor: float | None,
) -> bool:
    if len(labels) != len(problem.nodes):
        return False
    if any(label not in support for label, support in zip(labels, problem.supports)):
        return False
    degree = {node_id: 0 for node_id in problem.node_ids}
    id_to_index = {node_id: i for i, node_id in enumerate(problem.node_ids)}
    for edge_index in selected:
        row = problem.edges.iloc[int(edge_index)]
        if (
            labels[id_to_index[row[problem.u_col]]],
            labels[id_to_index[row[problem.v_col]]],
        ) not in problem.allowed_pairs[int(edge_index)]:
            return False
        degree[row[problem.u_col]] += 1
        degree[row[problem.v_col]] += 1
    for node_id, role in zip(problem.node_ids, problem.roles, strict=True):
        if role == "core" and degree[node_id] != 1:
            return False
        if role == "buffer" and degree[node_id] > 1:
            return False
        if role == "context_only" and degree[node_id] != 0:
            return False
    if gamma is not None and int(problem.edges.iloc[list(selected)]["_omitted"].sum()) > gamma:
        return False
    if score_floor is not None:
        exact_score = sum(
            (
                Fraction.from_float(float(problem.edges.iloc[index]["_score"]))
                * int(problem.edges.iloc[index]["_core_incidence"])
                for index in selected
            ),
            start=Fraction(0),
        )
        if exact_score < Fraction.from_float(float(score_floor)):
            return False
    for bound in problem.count_bounds:
        count = sum(
            problem.nodes.iloc[i][problem.cell_col] == bound.cell
            and labels[i] == bound.value
            for i in range(len(labels))
        )
        if not bound.lower <= count <= bound.upper:
            return False
    return True


def _scipy_one(
    problem: _PreparedProblem,
    *,
    sense: Sense,
    gamma: int | None,
    score_floor: float | None,
    time_limit: float | None,
) -> JointWorldSolution:
    if not SCIPY_MILP_AVAILABLE:
        raise RuntimeError("SciPy MILP backend requested but unavailable")

    edge_count = len(problem.edges)
    node_count = len(problem.nodes)
    id_to_node = {node_id: i for i, node_id in enumerate(problem.node_ids)}
    endpoints = [
        (id_to_node[u], id_to_node[v])
        for u, v in zip(
            problem.edges[problem.u_col], problem.edges[problem.v_col], strict=True
        )
    ]
    z_index = list(range(edge_count))
    next_variable = edge_count
    x_index: dict[tuple[int, Hashable], int] = {}
    for node_index, support in enumerate(problem.supports):
        for value in support:
            x_index[(node_index, value)] = next_variable
            next_variable += 1

    # q[e,a,b] is one exactly linearized selected-edge/endpoint-label product.
    # Summing the allowed q variables to z[e] makes every unlisted label pair
    # incompatible with selecting that edge.
    q_terms: list[tuple[int, Hashable, Hashable, int]] = []
    for edge_index, allowed in enumerate(problem.allowed_pairs):
        for left, right in sorted(allowed, key=repr):
            q_terms.append((edge_index, left, right, next_variable))
            next_variable += 1
    variable_count = next_variable

    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add_constraint(
        coefficients: dict[int, float], lb: float, ub: float
    ) -> None:
        rows.append(coefficients)
        lower.append(lb)
        upper.append(ub)

    for node_index, role in enumerate(problem.roles):
        if role == "context_only":
            continue
        coefficients = {
            z_index[edge_index]: 1.0
            for edge_index, (u, v) in enumerate(endpoints)
            if node_index in (u, v)
        }
        if role == "core":
            add_constraint(coefficients, 1.0, 1.0)
        else:
            add_constraint(coefficients, 0.0, 1.0)

    for node_index, support in enumerate(problem.supports):
        add_constraint(
            {x_index[(node_index, value)]: 1.0 for value in support},
            1.0,
            1.0,
        )

    for bound in problem.count_bounds:
        coefficients: dict[int, float] = {}
        for node_index, support in enumerate(problem.supports):
            if (
                problem.nodes.iloc[node_index][problem.cell_col] == bound.cell
                and bound.value in support
            ):
                coefficients[x_index[(node_index, bound.value)]] = 1.0
        add_constraint(coefficients, float(bound.lower), float(bound.upper))

    if gamma is not None:
        add_constraint(
            {
                z_index[index]: float(value)
                for index, value in enumerate(problem.edges["_omitted"])
                if value
            },
            0.0,
            float(gamma),
        )

    core_count = len(problem.core_indices)
    if score_floor is not None:
        scores = problem.edges["_score"].to_numpy(dtype=float)
        low, high = float(np.min(scores)), float(np.max(scores))
        if high != low:
            exact_floor = Fraction.from_float(float(score_floor))
            exact_minimum = core_count * Fraction.from_float(low)
            if exact_floor > exact_minimum:
                scale = np.longdouble(high) - np.longdouble(low)
                normalized_floor = float(
                    (np.longdouble(score_floor) - np.longdouble(low) * core_count)
                    / scale
                )
                add_constraint(
                    {
                        z_index[index]: float(core_weight)
                        * float((np.longdouble(score) - np.longdouble(low)) / scale)
                        for index, (score, core_weight) in enumerate(
                            zip(scores, problem.edges["_core_incidence"], strict=True)
                        )
                    },
                    normalized_floor,
                    np.inf,
                )

    q_by_edge: dict[int, list[int]] = {index: [] for index in range(edge_count)}
    for edge_index, left, right, q_index in q_terms:
        u, v = endpoints[edge_index]
        q_by_edge[edge_index].append(q_index)
        add_constraint({q_index: 1.0, z_index[edge_index]: -1.0}, -np.inf, 0.0)
        add_constraint(
            {q_index: 1.0, x_index[(u, left)]: -1.0}, -np.inf, 0.0
        )
        add_constraint(
            {q_index: 1.0, x_index[(v, right)]: -1.0}, -np.inf, 0.0
        )
        lower_coefficients = {
            q_index: 1.0,
            z_index[edge_index]: -1.0,
            x_index[(u, left)]: -1.0,
            x_index[(v, right)]: -1.0,
        }
        add_constraint(lower_coefficients, -2.0, np.inf)
    for edge_index in range(edge_count):
        coefficients = {q_index: 1.0 for q_index in q_by_edge[edge_index]}
        coefficients[z_index[edge_index]] = -1.0
        add_constraint(coefficients, 0.0, 0.0)

    row_indices: list[int] = []
    column_indices: list[int] = []
    data: list[float] = []
    for row_index, coefficients in enumerate(rows):
        for column_index, coefficient in coefficients.items():
            if coefficient != 0.0:
                row_indices.append(row_index)
                column_indices.append(column_index)
                data.append(coefficient)
    matrix = coo_matrix(
        (data, (row_indices, column_indices)),
        shape=(len(rows), variable_count),
        dtype=float,
    ).tocsr()
    constraint = LinearConstraint(
        matrix,
        lb=np.asarray(lower, dtype=float),
        ub=np.asarray(upper, dtype=float),
    )
    objective = np.zeros(variable_count, dtype=float)
    for edge_index, left, right, q_index in q_terms:
        if problem.query_bin[left] == problem.query_bin[right]:
            objective[q_index] = float(
                problem.edges.iloc[edge_index]["_core_incidence"]
            )
    if sense == "max":
        objective = -objective
    options: dict[str, float | bool] = {"presolve": True, "mip_rel_gap": 0.0}
    if time_limit is not None:
        options["time_limit"] = float(time_limit)
    result = milp(
        c=objective,
        integrality=np.ones(variable_count, dtype=np.int8),
        bounds=Bounds(np.zeros(variable_count), np.ones(variable_count)),
        constraints=constraint,
        options=options,
    )
    message = str(result.message)
    if int(result.status) == 2:
        return _blank_solution(
            "NUMERICALLY_INFEASIBLE",
            "scipy",
            "HiGHS reported infeasibility without an exact certificate: " + message,
        )

    vector = getattr(result, "x", None)
    if vector is None:
        return _blank_solution("UNRESOLVED", "scipy", message)
    vector = np.asarray(vector, dtype=float)
    integrality_valid = bool(
        np.all(np.minimum(np.abs(vector), np.abs(vector - 1.0)) <= 1e-6)
    )
    selected = [index for index in range(edge_count) if vector[z_index[index]] > 0.5]
    labels: list[Hashable] = []
    assignment_valid = True
    for node_index, support in enumerate(problem.supports):
        chosen = [
            value for value in support if vector[x_index[(node_index, value)]] > 0.5
        ]
        if len(chosen) != 1:
            assignment_valid = False
            labels.append(support[0])
        else:
            labels.append(chosen[0])
    q_valid = all(
        (vector[q_index] > 0.5)
        == (
            edge_index in selected
            and labels[endpoints[edge_index][0]] == left
            and labels[endpoints[edge_index][1]] == right
        )
        for edge_index, left, right, q_index in q_terms
    )
    incumbent_valid = (
        integrality_valid
        and assignment_valid
        and q_valid
        and _validate_incumbent(
            problem,
            selected,
            labels,
            gamma=gamma,
            score_floor=score_floor,
        )
    )
    status = "NUMERICALLY_OPTIMAL" if int(result.status) == 0 else "UNRESOLVED"
    if not incumbent_valid:
        return _blank_solution("UNRESOLVED", "scipy", message)
    gap = getattr(result, "mip_gap", None)
    return _world_solution(
        problem,
        selected,
        labels,
        status=status,
        certified=False,
        backend="scipy",
        message=message,
        mip_gap=float(gap) if gap is not None else None,
    )


def solve_joint_label_matching_endpoints(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    label_catalog: pd.DataFrame | Mapping[Hashable, Hashable],
    count_bounds: pd.DataFrame | None = None,
    *,
    backend: Backend = "auto",
    gamma: int | None = None,
    score_floor: float | None = None,
    node_id_col: str = "node_id",
    role_col: str = "role",
    support_col: str = "label_support",
    cell_col: str = "cell",
    value_col: str = "value",
    query_bin_col: str = "query_bin",
    count_lower_col: str = "lower",
    count_upper_col: str = "upper",
    u_col: str = "u",
    v_col: str = "v",
    edge_id_col: str = "edge_id",
    score_col: str | None = None,
    omitted_col: str | None = None,
    allowed_label_pairs_col: str | None = "allowed_label_pairs",
    time_limit: float | None = 60.0,
    fallback_max_states: int = 2_000_000,
) -> JointLabelMatchingEndpoints:
    """Optimize same-query-bin exposure over joint label/matching worlds.

    ``count_bounds`` rows constrain the total number of *all* supplied nodes
    (including unmatched buffers and ``context_only`` nodes) in a given
    ``(cell, value)``.  Unlisted cell/value combinations are unconstrained.

    ``score_floor`` is an absolute lower bound on
    ``sum(core_incidence[e] * score[e] * selected[e])``.  It requires
    ``score_col``.  ``gamma`` is an upper bound on the number of selected edges
    whose ``omitted_col`` equals one.

    If present, ``allowed_label_pairs_col`` contains an iterable of ordered
    ``(u_label, v_label)`` pairs for each edge, in the displayed endpoint
    order.  Selecting that edge is forbidden under every unlisted pair.  A
    missing column or missing cell permits the full Cartesian product; an
    explicit empty iterable makes the edge unusable in every label world.
    """

    if backend not in ("auto", "scipy", "fallback"):
        raise ValueError(f"unsupported backend {backend!r}")
    if gamma is not None:
        if isinstance(gamma, (bool, np.bool_)) or not isinstance(
            gamma, (int, np.integer)
        ) or gamma < 0:
            raise ValueError("gamma must be a nonnegative integer")
        if omitted_col is None:
            raise ValueError("gamma requires omitted_col")
        gamma = int(gamma)
    if score_floor is not None:
        if score_col is None:
            raise ValueError("score_floor requires score_col")
        if not math.isfinite(score_floor):
            raise ValueError("score_floor must be finite")
    if isinstance(fallback_max_states, (bool, np.bool_)) or not isinstance(
        fallback_max_states, (int, np.integer)
    ) or fallback_max_states < 0:
        raise ValueError("fallback_max_states must be a nonnegative integer")
    if time_limit is not None and (
        not math.isfinite(time_limit) or time_limit <= 0
    ):
        raise ValueError("time_limit must be finite and positive, or None")

    problem, structural_infeasibility = _prepare_problem(
        nodes,
        edges,
        label_catalog,
        count_bounds,
        node_id_col=node_id_col,
        role_col=role_col,
        support_col=support_col,
        cell_col=cell_col,
        value_col=value_col,
        query_bin_col=query_bin_col,
        count_lower_col=count_lower_col,
        count_upper_col=count_upper_col,
        u_col=u_col,
        v_col=v_col,
        edge_id_col=edge_id_col,
        score_col=score_col,
        omitted_col=omitted_col,
        allowed_label_pairs_col=allowed_label_pairs_col,
    )
    core_count = len(problem.core_indices)
    buffer_count = sum(role == "buffer" for role in problem.roles)
    context_count = sum(role == "context_only" for role in problem.roles)
    if problem.score_available:
        largest_score = np.max(np.abs(problem.edges["_score"].to_numpy(dtype=float)))
        aggregate_bound = np.longdouble(core_count) * np.longdouble(largest_score)
        if (
            not np.isfinite(aggregate_bound)
            or aggregate_bound > np.longdouble(np.finfo(float).max)
        ):
            raise ValueError(
                "core-incidence-weighted score totals are not representable as "
                "finite floats; rescale the scores"
            )

    if structural_infeasibility is None and score_floor is not None:
        exact_floor = Fraction.from_float(float(score_floor))
        exact_upper = Fraction(core_count) * max(
            Fraction.from_float(float(score)) for score in problem.edges["_score"]
        )
        if exact_floor > exact_upper:
            structural_infeasibility = (
                "score floor exceeds the fixed-core-incidence coefficient upper bound"
            )
        elif len(set(problem.edges["_score"].tolist())) == 1:
            constant = Fraction(core_count) * Fraction.from_float(
                float(problem.edges.iloc[0]["_score"])
            )
            if exact_floor > constant:
                structural_infeasibility = "score floor exceeds the constant total score"

    if structural_infeasibility is not None:
        infeasible = _blank_solution(
            "PROVEN_INFEASIBLE",
            "structural",
            structural_infeasibility,
            certified=True,
        )
        return JointLabelMatchingEndpoints(
            status="PROVEN_INFEASIBLE",
            certified=True,
            lower=None,
            upper=None,
            core_node_count=core_count,
            buffer_node_count=buffer_count,
            context_only_node_count=context_count,
            candidate_edge_count=len(problem.edges),
            gamma=gamma,
            score_floor=score_floor,
            lower_solution=infeasible,
            upper_solution=infeasible,
            warning="Infeasibility is proved for the declared finite domain only.",
        )

    selected_backend = backend
    if backend == "auto":
        selected_backend = "scipy" if SCIPY_MILP_AVAILABLE else "fallback"
    if selected_backend == "fallback":
        lower_solution, upper_solution = _fallback_endpoints(
            problem,
            gamma=gamma,
            score_floor=score_floor,
            max_states=int(fallback_max_states),
        )
    else:
        lower_solution = _scipy_one(
            problem,
            sense="min",
            gamma=gamma,
            score_floor=score_floor,
            time_limit=time_limit,
        )
        upper_solution = _scipy_one(
            problem,
            sense="max",
            gamma=gamma,
            score_floor=score_floor,
            time_limit=time_limit,
        )

    statuses = {lower_solution.status, upper_solution.status}
    if statuses == {"EXACT_OPTIMAL"}:
        status = "EXACT_OPTIMAL"
        certified = True
        lower = lower_solution.objective_value
        upper = upper_solution.objective_value
    elif statuses == {"NUMERICALLY_OPTIMAL"}:
        status = "NUMERICALLY_OPTIMAL"
        certified = False
        lower = lower_solution.objective_value
        upper = upper_solution.objective_value
    elif statuses == {"PROVEN_INFEASIBLE"}:
        status = "PROVEN_INFEASIBLE"
        certified = True
        lower = upper = None
    elif statuses == {"NUMERICALLY_INFEASIBLE"}:
        status = "NUMERICALLY_INFEASIBLE"
        certified = False
        lower = upper = None
    else:
        status = "UNRESOLVED"
        certified = False
        lower = upper = None

    warning = (
        "Endpoints are conditional on the supplied graph, supports, count bounds, "
        "score restriction, and Gamma budget."
    )
    if status == "NUMERICALLY_OPTIMAL":
        warning += " HiGHS optimality is numerical, not an exact certificate."
    if status in ("NUMERICALLY_INFEASIBLE", "UNRESOLVED"):
        warning += " No endpoint or exact infeasibility certificate is available."
    return JointLabelMatchingEndpoints(
        status=status,
        certified=certified,
        lower=lower,
        upper=upper,
        core_node_count=core_count,
        buffer_node_count=buffer_count,
        context_only_node_count=context_count,
        candidate_edge_count=len(problem.edges),
        gamma=gamma,
        score_floor=score_floor,
        lower_solution=lower_solution,
        upper_solution=upper_solution,
        warning=warning,
    )


__all__ = [
    "SCIPY_MILP_AVAILABLE",
    "JointLabelMatchingEndpoints",
    "JointWorldSolution",
    "solve_joint_label_matching_endpoints",
]
