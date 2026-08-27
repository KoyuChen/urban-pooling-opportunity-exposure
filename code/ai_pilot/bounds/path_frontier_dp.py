#!/usr/bin/env python3
"""Exact score-aware frontier DP on a supplied temporal path order.

This module is an exact, dependency-free reference implementation for the
joint hidden-label/hidden-matching problem.  It deliberately exposes the path
order rather than inferring that a large MILP will decompose.  A problem has:

* ``core`` nodes whose selected matching degree is exactly one;
* ``buffer`` nodes whose selected degree is at most one;
* ``context_only`` nodes that receive labels and enter counts but never match;
* one hashable (possibly tuple-valued) label per node;
* label-dependent 0/1 contributions to any number of privacy count factors;
* label-activated ``LOW``/``HIGH`` release requirements on those factors;
* optional label-pair restrictions and additive edge/node query terms;
* a budget ``Gamma`` for selected supergraph/omitted edges; and
* a lower floor on an additive compatibility score.

``compile_temporal_path`` turns an explicit vertex forget order into a nice
path schedule.  Just before a vertex is forgotten, all of its not-yet-seen
future neighbours are introduced and all edges for which it is the earlier
endpoint are processed.  The largest live bag is reported, so the claimed
structural parameter is auditable.

All arithmetic that affects feasibility or the endpoint is ``Fraction``
arithmetic.  Scores have one important convention: an edge score is *per core
incidence*.  A selected core--core edge therefore contributes twice its score
and a selected core--buffer edge once.  Since every complete feasible world
matches every core exactly once, adding a common constant to every score adds
the same constant times the number of core nodes to every world.  The solver
uses this invariant to shift all score values to nonnegative rationals, clears
denominators, and caps the integer score coordinate at the transformed floor.
The resulting DP is exact and pseudo-polynomial in that capped integer target.
The shift would not be valid for arbitrary per-edge scores when the selected
edge cardinality varies; that alternative score semantics is intentionally
unsupported.

Privacy factors obey an explicit running-intersection discipline.  A factor's
scope contains every node that can contribute to it or require it.  Its count
and ternary requirement coordinate remain live from the first such node
introduction through the last and are then checked and removed.  The relevant
factor parameter is therefore the maximum simultaneously active factor count,
reported in ``PathSchedule.max_active_factor_count``, not the total number of
factors.  A release rule "hidden iff pickup is LOW or drop-off is LOW" is
compiled by duplicating each hidden substantive label into witness-labelled
states (pickup-LOW versus dropoff-LOW, optionally both).  It must not be
compiled as simultaneous LOW requirements on both factors.

Successful results are exact certificates for the *declared* finite problem
and schedule.  They do not certify candidate-set coverage, the observation
operator, exchangeability, or any empirical identification assumption.  A
frontier-limit exception is explicit and never returned as an optimum.

For telemetry, let ``B`` be ``max_bag_size``, let ``d`` be the largest
*compiled* joint-label support (including any duplicated LOW-witness labels),
let ``R`` be the active factor set, let ``K_f`` be its reported count cap, let
``W`` be the capped integer score target, and let ``Gamma`` be the omission
budget.  A direct worst-case live-state bound for either endpoint run is

``(2d)^B * product_{f in R}(3(K_f+1)) * (Gamma+1) * (W+1)``.

The implementation normally retains less through exact score/query dominance.
There is no separate witness-branch parameter hidden outside ``d``.  Schedule
preprocessing scans the compiled input and ``actions x factors``; state
transitions touch only the active bag and active factor coordinates.  This
prototype stores complete witnesses in records for auditability rather than
using memory-optimal backpointers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from decimal import Decimal
from fractions import Fraction
from typing import Any, Hashable, Literal, Mapping, Sequence


Role = Literal["core", "buffer", "context_only"]
ActionKind = Literal["introduce_node", "introduce_edge", "forget_node"]
Sense = Literal["min", "max"]
FactorRequirement = Literal["LOW", "HIGH"]
VALID_ROLES = frozenset({"core", "buffer", "context_only"})
VALID_ACTIONS = frozenset({"introduce_node", "introduce_edge", "forget_node"})
VALID_REQUIREMENTS = frozenset({"LOW", "HIGH"})


@dataclass(frozen=True)
class NodeSpec:
    """One labelled record.

    ``factor_contributions[label][factor]`` is a 0/1 contribution.  The same
    label may contribute to multiple factors (for example, one pickup bucket
    and one drop-off bucket).  Joint labels can be ordinary tuples.
    """

    node_id: str
    role: Role
    label_support: Sequence[Hashable]
    factor_contributions: Mapping[
        Hashable, Mapping[Hashable, int]
    ] | None = None
    factor_requirements: Mapping[
        Hashable, Mapping[Hashable, FactorRequirement]
    ] | None = None
    label_query: Mapping[Hashable, Any] | None = None


@dataclass(frozen=True)
class EdgeSpec:
    """One candidate undirected matching edge.

    ``score`` and ``score_by_label_pair`` are per-core-incidence scores.
    ``query`` and ``query_by_label_pair`` are absolute contributions made once
    when this edge is selected.  Pair keys are ordered as ``(label_u,label_v)``.
    A supplied pair-dependent map must cover exactly the allowed label pairs.
    """

    edge_id: str
    u: str
    v: str
    score: Any = 0
    query: Any = 0
    omitted: bool = False
    allowed_label_pairs: Sequence[tuple[Hashable, Hashable]] | None = None
    score_by_label_pair: Mapping[tuple[Hashable, Hashable], Any] | None = None
    query_by_label_pair: Mapping[tuple[Hashable, Hashable], Any] | None = None


@dataclass(frozen=True)
class CountConstraint:
    """Bounds and optional release thresholds for one privacy count factor.

    ``LOW`` means the final factor count must not exceed ``low_upper``;
    ``HIGH`` means it must be at least ``high_lower``.  Label-activated
    requirements are merged globally.  Opposing requirements on the same
    factor make a world infeasible.
    """

    factor: Hashable
    lower: int
    upper: int
    low_upper: int | None = None
    high_lower: int | None = None


@dataclass(frozen=True)
class ExactPathProblem:
    nodes: Sequence[NodeSpec]
    edges: Sequence[EdgeSpec]
    count_constraints: Sequence[CountConstraint] = ()


@dataclass(frozen=True)
class NicePathAction:
    kind: ActionKind
    item_id: str


@dataclass(frozen=True)
class PathSchedule:
    actions: tuple[NicePathAction, ...]
    forget_order: tuple[str, ...]
    max_bag_size: int
    max_active_factor_count: int
    factor_count_caps: tuple[tuple[Hashable, int], ...]

    @property
    def schedule_width(self) -> int:
        """Width of this supplied live-record schedule, not graph pathwidth."""

        return max(0, self.max_bag_size - 1)


@dataclass(frozen=True)
class FrontierStats:
    """Deterministic implementation counters for one endpoint run.

    ``transition_count`` counts action branches examined, including locally
    infeasible select-edge branches.  ``introduced_states`` counts feasible
    candidate records offered to the frontier.  ``accepted_records`` counts
    insertions or improving replacements before cross-score pruning.
    ``dominance_pruned_records`` counts rejected candidates and displaced live
    records.  Runtime and memory are intentionally measured outside the solver.
    """

    introduced_states: int
    accepted_records: int
    dominance_pruned_records: int
    peak_live_records: int
    transition_count: int
    frontier_limit: int
    action_count: int


@dataclass(frozen=True)
class ExactPathWitness:
    selected_edge_ids: tuple[str, ...]
    label_assignments: tuple[tuple[str, Hashable], ...]
    factor_counts: tuple[tuple[Hashable, int], ...]
    factor_requirements: tuple[tuple[Hashable, str], ...]
    omitted_edge_count: int
    raw_score: Fraction
    query_value: Fraction


@dataclass(frozen=True)
class ExactPathSolution:
    status: Literal["EXACT_OPTIMAL", "EXACT_INFEASIBLE"]
    certified: bool
    objective_value: Fraction | None
    witness: ExactPathWitness | None
    stats: FrontierStats


@dataclass(frozen=True)
class ExactPathEndpoints:
    status: Literal["EXACT_OPTIMAL", "EXACT_INFEASIBLE"]
    certified: bool
    lower: Fraction | None
    upper: Fraction | None
    lower_solution: ExactPathSolution
    upper_solution: ExactPathSolution
    schedule: PathSchedule
    core_node_count: int
    score_floor: Fraction | None
    score_shift_per_core_incidence: Fraction
    transformed_score_floor: Fraction | None
    integer_score_scale: int
    capped_integer_score_target: int


@dataclass(frozen=True)
class OutwardScoreRelaxation:
    """Certified outer endpoints after downward score quantization.

    ``relaxed_endpoints`` is solved exactly for a rounded score resource.  Its
    structural witnesses are revalued under the original score map in
    ``lower_solution`` and ``upper_solution``.  The relaxed feasible-world set
    contains the exact score-floor set and is itself contained in the set with
    the original floor lowered by ``maximum_score_shortfall``.

    This is a bicriteria certificate, not a query approximation guarantee: an
    arbitrarily small score relaxation can admit an arbitrarily different
    query value.
    """

    status: Literal["OUTER_OPTIMAL", "EXACT_INFEASIBLE"]
    certified: bool
    lower: Fraction | None
    upper: Fraction | None
    lower_solution: ExactPathSolution
    upper_solution: ExactPathSolution
    relaxed_endpoints: ExactPathEndpoints
    original_score_floor: Fraction
    score_granularity: Fraction
    score_shift_per_core_incidence: Fraction
    rounded_integer_score_floor: int
    maximum_score_shortfall: Fraction
    exact_infeasibility_certified: bool
    exact_feasibility_witnessed: bool
    lower_endpoint_exact_witnessed: bool
    upper_endpoint_exact_witnessed: bool


class FrontierLimitExceeded(RuntimeError):
    """Raised when an exact run exceeds its declared live-frontier budget."""

    def __init__(
        self,
        *,
        action_index: int,
        action: NicePathAction,
        live_records: int,
        limit: int,
    ) -> None:
        self.action_index = action_index
        self.action = action
        self.live_records = live_records
        self.limit = limit
        super().__init__(
            "exact path frontier exceeded limit "
            f"{limit} after action {action_index} "
            f"({action.kind}:{action.item_id}); required {live_records} records"
        )


@dataclass(frozen=True)
class _PreparedNode:
    node_id: str
    role: Role
    support: tuple[Hashable, ...]
    factor_contributions: Mapping[Hashable, Mapping[int, int]]
    factor_requirements: Mapping[Hashable, Mapping[int, int]]
    label_query: Mapping[Hashable, Fraction]


@dataclass(frozen=True)
class _PreparedEdge:
    edge_id: str
    u: str
    v: str
    omitted: bool
    allowed_pairs: frozenset[tuple[Hashable, Hashable]]
    score_by_pair: Mapping[tuple[Hashable, Hashable], Fraction]
    query_by_pair: Mapping[tuple[Hashable, Hashable], Fraction]
    core_incidences: int


@dataclass(frozen=True)
class _PreparedProblem:
    nodes: tuple[_PreparedNode, ...]
    edges: tuple[_PreparedEdge, ...]
    constraints: tuple[CountConstraint, ...]
    node_by_id: Mapping[str, _PreparedNode]
    edge_by_id: Mapping[str, _PreparedEdge]
    incident_edges: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class _ScoreTransform:
    floor: Fraction | None
    shift: Fraction
    transformed_floor: Fraction | None
    scale: int
    target: int
    shifted_edge_scores: Mapping[
        tuple[str, tuple[Hashable, Hashable]], int
    ]


@dataclass(frozen=True)
class _FactorStage:
    active_before: tuple[int, ...]
    active_during: tuple[int, ...]
    active_after: tuple[int, ...]
    minimum_remaining: tuple[int, ...]
    maximum_remaining: tuple[int, ...]


@dataclass(frozen=True)
class _StateKey:
    labels: tuple[Hashable, ...]
    matched: tuple[bool, ...]
    counts: tuple[int, ...]
    requirements: tuple[int, ...]
    gamma_used: int
    score_cap: int


@dataclass(frozen=True)
class _Record:
    key: _StateKey
    query: Fraction
    selected_edges: tuple[str, ...]
    assignments: tuple[tuple[str, Hashable], ...]


@dataclass
class _MutableStats:
    introduced_states: int = 0
    accepted_records: int = 0
    dominance_pruned_records: int = 0
    peak_live_records: int = 1
    transition_count: int = 0

    def freeze(self, *, limit: int, action_count: int) -> FrontierStats:
        return FrontierStats(
            introduced_states=self.introduced_states,
            accepted_records=self.accepted_records,
            dominance_pruned_records=self.dominance_pruned_records,
            peak_live_records=self.peak_live_records,
            transition_count=self.transition_count,
            frontier_limit=limit,
            action_count=action_count,
        )


def _fraction(value: Any, name: str) -> Fraction:
    """Convert a finite scalar to an exact declared rational."""

    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite rational, not bool")
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{name} must be finite")
        result = Fraction(value)
    elif isinstance(value, int):
        result = Fraction(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        # Decimal spelling is the declared input semantics; subsequent work is exact.
        result = Fraction(str(value))
    elif isinstance(value, str):
        try:
            result = Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{name} must be a finite rational") from exc
    else:
        try:
            result = Fraction(value)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{name} must be a finite rational") from exc
    return result


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")
    return value


def _hashable(value: Any, name: str) -> Hashable:
    try:
        hash(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be hashable") from exc
    return value


def _prepare_problem(problem: ExactPathProblem) -> _PreparedProblem:
    constraints: list[CountConstraint] = []
    factor_index: dict[Hashable, int] = {}
    for raw in problem.count_constraints:
        factor = _hashable(raw.factor, "count factor")
        if factor in factor_index:
            raise ValueError(f"duplicate count constraint for factor {factor!r}")
        lower = _nonnegative_integer(raw.lower, f"lower bound for {factor!r}")
        upper = _nonnegative_integer(raw.upper, f"upper bound for {factor!r}")
        if lower > upper:
            raise ValueError(f"lower bound exceeds upper bound for factor {factor!r}")
        low_upper = (
            None
            if raw.low_upper is None
            else _nonnegative_integer(
                raw.low_upper, f"LOW threshold for {factor!r}"
            )
        )
        high_lower = (
            None
            if raw.high_lower is None
            else _nonnegative_integer(
                raw.high_lower, f"HIGH threshold for {factor!r}"
            )
        )
        if (
            low_upper is not None
            and high_lower is not None
            and low_upper >= high_lower
        ):
            raise ValueError(
                f"LOW/HIGH thresholds for {factor!r} must form a strict "
                "partition: low_upper < high_lower"
            )
        factor_index[factor] = len(constraints)
        constraints.append(
            CountConstraint(
                factor,
                lower,
                upper,
                low_upper=low_upper,
                high_lower=high_lower,
            )
        )

    nodes: list[_PreparedNode] = []
    node_ids: set[str] = set()
    for raw in problem.nodes:
        node_id = _identifier(raw.node_id, "node_id")
        if node_id in node_ids:
            raise ValueError(f"duplicate node_id {node_id!r}")
        node_ids.add(node_id)
        if raw.role not in VALID_ROLES:
            raise ValueError(f"invalid role {raw.role!r} for node {node_id!r}")
        if isinstance(raw.label_support, (str, bytes)):
            raise ValueError(f"label support for {node_id!r} must be a sequence")
        support = tuple(raw.label_support)
        if not support:
            raise ValueError(f"label support for {node_id!r} must not be empty")
        seen_labels: set[Hashable] = set()
        for label in support:
            _hashable(label, f"label for node {node_id!r}")
            if label in seen_labels:
                raise ValueError(f"duplicate label in support for node {node_id!r}")
            seen_labels.add(label)

        raw_factors = raw.factor_contributions or {}
        extra_labels = set(raw_factors) - seen_labels
        if extra_labels:
            raise ValueError(
                f"factor contributions reference unsupported label for {node_id!r}"
            )
        contributions: dict[Hashable, Mapping[int, int]] = {}
        for label in support:
            sparse: dict[int, int] = {}
            label_factors = raw_factors.get(label, {})
            for factor, contribution in label_factors.items():
                _hashable(factor, f"factor for node {node_id!r}")
                if factor not in factor_index:
                    raise ValueError(
                        f"node {node_id!r} contributes to unconstrained factor "
                        f"{factor!r}"
                    )
                if isinstance(contribution, bool) or contribution not in (0, 1):
                    raise ValueError(
                        "privacy factor contributions must be literal 0/1 integers"
                    )
                if contribution:
                    sparse[factor_index[factor]] = 1
            contributions[label] = sparse

        raw_requirements = raw.factor_requirements or {}
        extra_requirement_labels = set(raw_requirements) - seen_labels
        if extra_requirement_labels:
            raise ValueError(
                f"factor requirements reference unsupported label for {node_id!r}"
            )
        requirements: dict[Hashable, Mapping[int, int]] = {}
        for label in support:
            sparse = {}
            label_requirements = raw_requirements.get(label, {})
            for factor, requirement in label_requirements.items():
                _hashable(factor, f"requirement factor for node {node_id!r}")
                if factor not in factor_index:
                    raise ValueError(
                        f"node {node_id!r} requires unconstrained factor {factor!r}"
                    )
                if requirement not in VALID_REQUIREMENTS:
                    raise ValueError(
                        "factor requirements must be literal 'LOW' or 'HIGH'"
                    )
                constraint = constraints[factor_index[factor]]
                if requirement == "LOW" and constraint.low_upper is None:
                    raise ValueError(
                        f"factor {factor!r} has a LOW requirement but no low_upper"
                    )
                if requirement == "HIGH" and constraint.high_lower is None:
                    raise ValueError(
                        f"factor {factor!r} has a HIGH requirement but no high_lower"
                    )
                sparse[factor_index[factor]] = 1 if requirement == "LOW" else 2
            requirements[label] = sparse

        raw_label_query = raw.label_query or {}
        if set(raw_label_query) - seen_labels:
            raise ValueError(f"label_query references unsupported label for {node_id!r}")
        label_query = {
            label: _fraction(
                raw_label_query.get(label, 0),
                f"label query for {node_id!r}/{label!r}",
            )
            for label in support
        }
        nodes.append(
            _PreparedNode(
                node_id=node_id,
                role=raw.role,
                support=support,
                factor_contributions=contributions,
                factor_requirements=requirements,
                label_query=label_query,
            )
        )

    node_by_id = {node.node_id: node for node in nodes}
    edges: list[_PreparedEdge] = []
    edge_ids: set[str] = set()
    undirected_pairs: set[tuple[str, str]] = set()
    for raw in problem.edges:
        edge_id = _identifier(raw.edge_id, "edge_id")
        if edge_id in edge_ids:
            raise ValueError(f"duplicate edge_id {edge_id!r}")
        edge_ids.add(edge_id)
        u = _identifier(raw.u, f"u for edge {edge_id!r}")
        v = _identifier(raw.v, f"v for edge {edge_id!r}")
        if u == v:
            raise ValueError("self-loop candidate edges are not permitted")
        if u not in node_by_id or v not in node_by_id:
            raise ValueError(f"edge {edge_id!r} references an unknown node")
        pair_id = tuple(sorted((u, v)))
        if pair_id in undirected_pairs:
            raise ValueError(f"duplicate undirected candidate pair {pair_id!r}")
        undirected_pairs.add(pair_id)
        node_u = node_by_id[u]
        node_v = node_by_id[v]
        if "context_only" in (node_u.role, node_v.role):
            raise ValueError("context_only nodes must not have matching edges")
        if node_u.role != "core" and node_v.role != "core":
            raise ValueError("every matching edge must touch at least one core node")
        core_incidences = int(node_u.role == "core") + int(node_v.role == "core")

        cartesian = {
            (label_u, label_v)
            for label_u in node_u.support
            for label_v in node_v.support
        }
        if raw.allowed_label_pairs is None:
            allowed = frozenset(cartesian)
        else:
            normalized_pairs: set[tuple[Hashable, Hashable]] = set()
            for label_pair in raw.allowed_label_pairs:
                if not isinstance(label_pair, tuple) or len(label_pair) != 2:
                    raise ValueError(
                        f"allowed label pair for edge {edge_id!r} must be a 2-tuple"
                    )
                normalized_pairs.add(label_pair)
            if not normalized_pairs:
                raise ValueError(f"edge {edge_id!r} has no allowed label pair")
            if not normalized_pairs <= cartesian:
                raise ValueError(
                    f"edge {edge_id!r} has an allowed pair outside endpoint supports"
                )
            allowed = frozenset(normalized_pairs)

        def pair_map(
            supplied: Mapping[tuple[Hashable, Hashable], Any] | None,
            constant: Any,
            kind: str,
        ) -> dict[tuple[Hashable, Hashable], Fraction]:
            if supplied is None:
                value = _fraction(constant, f"{kind} for edge {edge_id!r}")
                return {label_pair: value for label_pair in allowed}
            if set(supplied) != set(allowed):
                raise ValueError(
                    f"{kind}_by_label_pair for edge {edge_id!r} must cover "
                    "exactly the allowed pairs"
                )
            return {
                label_pair: _fraction(
                    supplied[label_pair],
                    f"{kind} for edge {edge_id!r}/{label_pair!r}",
                )
                for label_pair in allowed
            }

        scores = pair_map(raw.score_by_label_pair, raw.score, "score")
        queries = pair_map(raw.query_by_label_pair, raw.query, "query")
        if not isinstance(raw.omitted, bool):
            raise ValueError(f"omitted for edge {edge_id!r} must be bool")
        edges.append(
            _PreparedEdge(
                edge_id=edge_id,
                u=u,
                v=v,
                omitted=raw.omitted,
                allowed_pairs=allowed,
                score_by_pair=scores,
                query_by_pair=queries,
                core_incidences=core_incidences,
            )
        )

    edge_by_id = {edge.edge_id: edge for edge in edges}
    incident: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    for edge in edges:
        incident[edge.u].append(edge.edge_id)
        incident[edge.v].append(edge.edge_id)
    incident_edges = {
        node_id: tuple(sorted(ids)) for node_id, ids in incident.items()
    }
    return _PreparedProblem(
        nodes=tuple(nodes),
        edges=tuple(edges),
        constraints=tuple(constraints),
        node_by_id=node_by_id,
        edge_by_id=edge_by_id,
        incident_edges=incident_edges,
    )


def _factor_lifecycle(
    prepared: _PreparedProblem,
    actions: Sequence[NicePathAction],
) -> tuple[
    tuple[_FactorStage, ...],
    tuple[int, ...],
    tuple[bool, ...],
    int,
]:
    """Return sparse per-action factor stages, caps, scopes, and width.

    A factor's scope contains every node that can contribute to it *or* can
    activate a LOW/HIGH requirement.  Its accumulated coordinate is retained
    from the first such node introduction through the last.  It is checked and
    reset immediately after the last scoped node is labelled.  Thus disjoint
    local release factors do not multiply the frontier state space.
    """

    introduction_index = {
        action.item_id: index
        for index, action in enumerate(actions)
        if action.kind == "introduce_node"
    }
    factor_count = len(prepared.constraints)
    scoped_nodes: list[set[str]] = [set() for _ in range(factor_count)]
    scope_maxima = [0] * factor_count
    node_ranges: dict[str, dict[int, tuple[int, int]]] = {}
    for node in prepared.nodes:
        relevant_factors: set[int] = set()
        for label in node.support:
            relevant_factors.update(node.factor_contributions[label])
            relevant_factors.update(node.factor_requirements[label])
        ranges_for_node: dict[int, tuple[int, int]] = {}
        for factor_index in relevant_factors:
            values = [
                node.factor_contributions[label].get(factor_index, 0)
                for label in node.support
            ]
            minimum = min(values)
            maximum = max(values)
            ranges_for_node[factor_index] = (minimum, maximum)
            scoped_nodes[factor_index].add(node.node_id)
            scope_maxima[factor_index] += maximum
        node_ranges[node.node_id] = ranges_for_node

    intervals: list[tuple[int, int] | None] = []
    caps: list[int] = []
    for factor_index in range(factor_count):
        if not scoped_nodes[factor_index]:
            intervals.append(None)
        else:
            indices = [
                introduction_index[node_id]
                for node_id in scoped_nodes[factor_index]
            ]
            intervals.append((min(indices), max(indices)))
        constraint = prepared.constraints[factor_index]
        decision_boundaries = [constraint.lower]
        if constraint.high_lower is not None:
            decision_boundaries.append(constraint.high_lower)
        if constraint.low_upper is not None:
            decision_boundaries.append(constraint.low_upper + 1)
        if constraint.upper < scope_maxima[factor_index]:
            # Preserve a distinct overflow state; it is pruned, never saturated
            # into an apparently feasible upper-bound state.
            decision_boundaries.append(constraint.upper + 1)
        caps.append(
            min(
                scope_maxima[factor_index],
                max(decision_boundaries, default=0),
            )
        )

    stages: list[_FactorStage] = []
    max_active = 0
    remaining_minimum = [0] * factor_count
    remaining_maximum = [0] * factor_count
    for ranges_for_node in node_ranges.values():
        for factor_index, (minimum, maximum) in ranges_for_node.items():
            remaining_minimum[factor_index] += minimum
            remaining_maximum[factor_index] += maximum
    for action_index, action in enumerate(actions):
        if action.kind == "introduce_node":
            for factor_index, (minimum, maximum) in node_ranges[
                action.item_id
            ].items():
                remaining_minimum[factor_index] -= minimum
                remaining_maximum[factor_index] -= maximum
        active_before = tuple(
            factor_index
            for factor_index, interval in enumerate(intervals)
            if interval is not None
            and interval[0] < action_index <= interval[1]
        )
        active_during = tuple(
            factor_index
            for factor_index, interval in enumerate(intervals)
            if interval is not None
            and interval[0] <= action_index <= interval[1]
        )
        active_after = tuple(
            factor_index
            for factor_index, interval in enumerate(intervals)
            if interval is not None
            and interval[0] <= action_index < interval[1]
        )
        stages.append(
            _FactorStage(
                active_before=active_before,
                active_during=active_during,
                active_after=active_after,
                minimum_remaining=tuple(
                    remaining_minimum[factor_index]
                    for factor_index in active_during
                ),
                maximum_remaining=tuple(
                    remaining_maximum[factor_index]
                    for factor_index in active_during
                ),
            )
        )
        max_active = max(max_active, len(active_during))
    scoped = tuple(interval is not None for interval in intervals)
    return tuple(stages), tuple(caps), scoped, max_active


def _compile_prepared_path(
    prepared: _PreparedProblem,
    forget_order: Sequence[str],
) -> PathSchedule:
    order = tuple(forget_order)
    if len(order) != len(prepared.nodes) or set(order) != set(prepared.node_by_id):
        raise ValueError("forget_order must contain every node_id exactly once")
    if len(set(order)) != len(order):
        raise ValueError("forget_order must not contain duplicates")
    position = {node_id: index for index, node_id in enumerate(order)}
    actions: list[NicePathAction] = []
    introduced: set[str] = set()
    active: set[str] = set()
    max_bag = 0

    def introduce(node_id: str) -> None:
        nonlocal max_bag
        if node_id not in introduced:
            actions.append(NicePathAction("introduce_node", node_id))
            introduced.add(node_id)
            active.add(node_id)
            max_bag = max(max_bag, len(active))

    for node_id in order:
        introduce(node_id)
        future_edges: list[_PreparedEdge] = []
        for edge_id in prepared.incident_edges[node_id]:
            edge = prepared.edge_by_id[edge_id]
            other = edge.v if edge.u == node_id else edge.u
            if position[other] > position[node_id]:
                introduce(other)
                future_edges.append(edge)
        for edge in sorted(future_edges, key=lambda item: item.edge_id):
            actions.append(NicePathAction("introduce_edge", edge.edge_id))
        actions.append(NicePathAction("forget_node", node_id))
        active.remove(node_id)

    base_schedule = PathSchedule(
        actions=tuple(actions),
        forget_order=order,
        max_bag_size=max_bag,
        max_active_factor_count=0,
        factor_count_caps=(),
    )
    _stages, caps, _scoped, max_active_factors = _factor_lifecycle(
        prepared, base_schedule.actions
    )
    return PathSchedule(
        actions=base_schedule.actions,
        forget_order=base_schedule.forget_order,
        max_bag_size=base_schedule.max_bag_size,
        max_active_factor_count=max_active_factors,
        factor_count_caps=tuple(
            (constraint.factor, cap)
            for constraint, cap in zip(prepared.constraints, caps)
        ),
    )


def compile_temporal_path(
    problem: ExactPathProblem,
    forget_order: Sequence[str],
) -> PathSchedule:
    """Compile and validate a nice path from a complete vertex forget order."""

    return _compile_prepared_path(_prepare_problem(problem), forget_order)


def _validate_schedule(
    prepared: _PreparedProblem,
    schedule: PathSchedule,
) -> None:
    active: list[str] = []
    introduced_nodes: set[str] = set()
    forgotten_nodes: set[str] = set()
    introduced_edges: set[str] = set()
    actual_forget_order: list[str] = []
    max_bag = 0
    for index, action in enumerate(schedule.actions):
        if action.kind not in VALID_ACTIONS:
            raise ValueError(f"invalid schedule action at index {index}")
        if action.kind == "introduce_node":
            if action.item_id not in prepared.node_by_id:
                raise ValueError(f"schedule introduces unknown node {action.item_id!r}")
            if action.item_id in introduced_nodes:
                raise ValueError(f"schedule introduces node {action.item_id!r} twice")
            introduced_nodes.add(action.item_id)
            active.append(action.item_id)
            max_bag = max(max_bag, len(active))
        elif action.kind == "introduce_edge":
            if action.item_id not in prepared.edge_by_id:
                raise ValueError(f"schedule introduces unknown edge {action.item_id!r}")
            if action.item_id in introduced_edges:
                raise ValueError(f"schedule introduces edge {action.item_id!r} twice")
            edge = prepared.edge_by_id[action.item_id]
            if edge.u not in active or edge.v not in active:
                raise ValueError(
                    f"edge {edge.edge_id!r} must be introduced while both endpoints "
                    "are active"
                )
            introduced_edges.add(action.item_id)
        else:
            if action.item_id not in active:
                raise ValueError(
                    f"schedule forgets inactive node {action.item_id!r}"
                )
            active.remove(action.item_id)
            forgotten_nodes.add(action.item_id)
            actual_forget_order.append(action.item_id)
    if active:
        raise ValueError("schedule must forget every introduced node")
    if introduced_nodes != set(prepared.node_by_id):
        raise ValueError("schedule must introduce every problem node exactly once")
    if forgotten_nodes != set(prepared.node_by_id):
        raise ValueError("schedule must forget every problem node exactly once")
    if introduced_edges != set(prepared.edge_by_id):
        raise ValueError("schedule must introduce every problem edge exactly once")
    if tuple(actual_forget_order) != tuple(schedule.forget_order):
        raise ValueError("schedule.forget_order disagrees with its forget actions")
    if max_bag != schedule.max_bag_size:
        raise ValueError("schedule.max_bag_size disagrees with its actions")
    _stages, caps, _scoped, max_active_factors = _factor_lifecycle(
        prepared, schedule.actions
    )
    if max_active_factors != schedule.max_active_factor_count:
        raise ValueError(
            "schedule.max_active_factor_count disagrees with factor scopes"
        )
    expected_caps = tuple(
        (constraint.factor, cap)
        for constraint, cap in zip(prepared.constraints, caps)
    )
    if schedule.factor_count_caps != expected_caps:
        raise ValueError("schedule.factor_count_caps disagrees with factor scopes")


def _score_transform(
    prepared: _PreparedProblem,
    score_floor: Any | None,
) -> _ScoreTransform:
    if score_floor is None:
        return _ScoreTransform(
            floor=None,
            shift=Fraction(0),
            transformed_floor=None,
            scale=1,
            target=0,
            shifted_edge_scores={},
        )

    floor = _fraction(score_floor, "score_floor")
    all_scores = [
        value
        for edge in prepared.edges
        for value in edge.score_by_pair.values()
    ]
    minimum = min(all_scores, default=Fraction(0))
    shift = max(Fraction(0), -minimum)
    core_count = sum(node.role == "core" for node in prepared.nodes)
    transformed_floor = floor + shift * core_count
    shifted_values = [value + shift for value in all_scores]
    denominators = [value.denominator for value in shifted_values]
    denominators.append(transformed_floor.denominator)
    scale = 1
    for denominator in denominators:
        scale = math.lcm(scale, denominator)
    target_exact = transformed_floor * scale
    if target_exact.denominator != 1:  # defensive; scale includes denominator
        raise AssertionError("score denominator clearing failed")
    target = max(0, target_exact.numerator)
    shifted_edge_scores: dict[
        tuple[str, tuple[Hashable, Hashable]], int
    ] = {}
    for edge in prepared.edges:
        for label_pair, raw_score in edge.score_by_pair.items():
            integer = (raw_score + shift) * scale
            if integer.denominator != 1 or integer < 0:
                raise AssertionError("shifted score is not a nonnegative integer")
            shifted_edge_scores[(edge.edge_id, label_pair)] = integer.numerator
    return _ScoreTransform(
        floor=floor,
        shift=shift,
        transformed_floor=transformed_floor,
        scale=scale,
        target=target,
        shifted_edge_scores=shifted_edge_scores,
    )


def _active_counts_can_finish(
    counts: tuple[int, ...],
    requirements: tuple[int, ...],
    minimum_remaining: tuple[int, ...],
    maximum_remaining: tuple[int, ...],
    active_factors: tuple[int, ...],
    constraints: tuple[CountConstraint, ...],
) -> bool:
    for (
        value,
        requirement,
        min_future,
        max_future,
        factor_index,
    ) in (
        zip(
            counts,
            requirements,
            minimum_remaining,
            maximum_remaining,
            active_factors,
        )
    ):
        constraint = constraints[factor_index]
        effective_lower = constraint.lower
        effective_upper = constraint.upper
        if requirement == 1:
            if constraint.low_upper is None:
                raise AssertionError("validated LOW requirement lacks a threshold")
            effective_upper = min(effective_upper, constraint.low_upper)
        elif requirement == 2:
            if constraint.high_lower is None:
                raise AssertionError("validated HIGH requirement lacks a threshold")
            effective_lower = max(effective_lower, constraint.high_lower)
        if value > effective_upper:
            return False
        if value + min_future > effective_upper:
            return False
        if value + max_future < effective_lower:
            return False
    return True


def _exact_counts_valid(
    counts: Sequence[int],
    requirements: Sequence[int],
    constraints: tuple[CountConstraint, ...],
) -> bool:
    return _active_counts_can_finish(
        tuple(counts),
        tuple(requirements),
        (0,) * len(constraints),
        (0,) * len(constraints),
        tuple(range(len(constraints))),
        constraints,
    )


def _merge_requirements(
    current: tuple[int, ...],
    added: Mapping[int, int],
) -> tuple[int, ...] | None:
    merged = list(current)
    for factor_index, new in added.items():
        old = merged[factor_index]
        if old and new and old != new:
            return None
        merged[factor_index] = old or new
    return tuple(merged)


def _better(left: Fraction, right: Fraction, sense: Sense) -> bool:
    return left < right if sense == "min" else left > right


def _witness_key(record: _Record) -> tuple[Any, ...]:
    assignments = tuple((node_id, repr(label)) for node_id, label in record.assignments)
    return (record.selected_edges, assignments)


def _offer(
    target: dict[_StateKey, _Record],
    record: _Record,
    *,
    sense: Sense,
    stats: _MutableStats,
) -> None:
    stats.introduced_states += 1
    incumbent = target.get(record.key)
    if incumbent is None:
        target[record.key] = record
        stats.accepted_records += 1
        return
    if _better(record.query, incumbent.query, sense) or (
        record.query == incumbent.query
        and _witness_key(record) < _witness_key(incumbent)
    ):
        target[record.key] = record
        stats.accepted_records += 1
        stats.dominance_pruned_records += 1
    else:
        stats.dominance_pruned_records += 1


def _score_dominance_prune(
    records: dict[_StateKey, _Record],
    *,
    sense: Sense,
    stats: _MutableStats,
) -> dict[_StateKey, _Record]:
    """Prune states worse in both achieved score and query."""

    groups: dict[tuple[Any, ...], list[_Record]] = {}
    for record in records.values():
        key = record.key
        base = (
            key.labels,
            key.matched,
            key.counts,
            key.requirements,
            key.gamma_used,
        )
        groups.setdefault(base, []).append(record)
    kept: dict[_StateKey, _Record] = {}
    for group in groups.values():
        ordered = sorted(
            group,
            key=lambda record: (
                -record.key.score_cap,
                record.query if sense == "min" else -record.query,
                _witness_key(record),
            ),
        )
        best_query: Fraction | None = None
        for record in ordered:
            if best_query is None or _better(record.query, best_query, sense):
                kept[record.key] = record
                best_query = record.query
            else:
                stats.dominance_pruned_records += 1
    return kept


def _final_witness(
    record: _Record,
    prepared: _PreparedProblem,
) -> ExactPathWitness:
    labels = dict(record.assignments)
    counts = [0] * len(prepared.constraints)
    requirements = (0,) * len(prepared.constraints)
    for node in prepared.nodes:
        label = labels[node.node_id]
        for factor_index, added in node.factor_contributions[label].items():
            counts[factor_index] += added
        merged = _merge_requirements(
            requirements,
            node.factor_requirements[label],
        )
        if merged is None:
            raise AssertionError("DP witness has conflicting factor requirements")
        requirements = merged
    raw_score = Fraction(0)
    omitted = 0
    for edge_id in record.selected_edges:
        edge = prepared.edge_by_id[edge_id]
        label_pair = (labels[edge.u], labels[edge.v])
        raw_score += edge.score_by_pair[label_pair] * edge.core_incidences
        omitted += int(edge.omitted)
    factor_counts = tuple(
        (constraint.factor, count)
        for constraint, count in zip(prepared.constraints, counts)
    )
    factor_requirements = tuple(
        (constraint.factor, "LOW" if requirement == 1 else "HIGH")
        for constraint, requirement in zip(
            prepared.constraints, requirements
        )
        if requirement
    )
    return ExactPathWitness(
        selected_edge_ids=record.selected_edges,
        label_assignments=tuple(sorted(record.assignments, key=lambda item: item[0])),
        factor_counts=factor_counts,
        factor_requirements=factor_requirements,
        omitted_edge_count=omitted,
        raw_score=raw_score,
        query_value=record.query,
    )


def _validate_prepared_witness(
    prepared: _PreparedProblem,
    witness: ExactPathWitness,
    *,
    gamma: int | None,
    score_floor: Fraction | None,
) -> None:
    """Recompute every witness constraint independently of the DP state."""

    assignments = dict(witness.label_assignments)
    if len(assignments) != len(witness.label_assignments):
        raise ValueError("witness repeats a node label assignment")
    if set(assignments) != set(prepared.node_by_id):
        raise ValueError("witness must assign exactly every problem node")
    counts = [0] * len(prepared.constraints)
    requirements = (0,) * len(prepared.constraints)
    query = Fraction(0)
    for node in prepared.nodes:
        label = assignments[node.node_id]
        if label not in node.support:
            raise ValueError(f"witness label is unsupported for {node.node_id!r}")
        for factor_index, added in node.factor_contributions[label].items():
            counts[factor_index] += added
        merged = _merge_requirements(
            requirements,
            node.factor_requirements[label],
        )
        if merged is None:
            raise ValueError("witness activates conflicting LOW/HIGH requirements")
        requirements = merged
        query += node.label_query[label]

    selected = tuple(witness.selected_edge_ids)
    if len(set(selected)) != len(selected):
        raise ValueError("witness selects an edge more than once")
    degrees = {node.node_id: 0 for node in prepared.nodes}
    raw_score = Fraction(0)
    omitted = 0
    for edge_id in selected:
        if edge_id not in prepared.edge_by_id:
            raise ValueError(f"witness selects unknown edge {edge_id!r}")
        edge = prepared.edge_by_id[edge_id]
        label_pair = (assignments[edge.u], assignments[edge.v])
        if label_pair not in edge.allowed_pairs:
            raise ValueError(f"witness violates label restriction on {edge_id!r}")
        degrees[edge.u] += 1
        degrees[edge.v] += 1
        query += edge.query_by_pair[label_pair]
        raw_score += edge.score_by_pair[label_pair] * edge.core_incidences
        omitted += int(edge.omitted)
    for node in prepared.nodes:
        degree = degrees[node.node_id]
        if node.role == "core" and degree != 1:
            raise ValueError(f"core node {node.node_id!r} does not have degree one")
        if node.role == "buffer" and degree > 1:
            raise ValueError(f"buffer node {node.node_id!r} has degree above one")
        if node.role == "context_only" and degree != 0:
            raise ValueError(f"context node {node.node_id!r} is matched")
    if gamma is not None and omitted > gamma:
        raise ValueError("witness exceeds Gamma")
    if score_floor is not None and raw_score < score_floor:
        raise ValueError("witness falls below the raw score floor")
    if not _exact_counts_valid(counts, requirements, prepared.constraints):
        raise ValueError("witness violates a final count or release requirement")

    expected_counts = tuple(
        (constraint.factor, count)
        for constraint, count in zip(prepared.constraints, counts)
    )
    expected_requirements = tuple(
        (constraint.factor, "LOW" if requirement == 1 else "HIGH")
        for constraint, requirement in zip(prepared.constraints, requirements)
        if requirement
    )
    if witness.factor_counts != expected_counts:
        raise ValueError("witness factor counts do not recompute")
    if witness.factor_requirements != expected_requirements:
        raise ValueError("witness factor requirements do not recompute")
    if witness.omitted_edge_count != omitted:
        raise ValueError("witness omitted-edge count does not recompute")
    if witness.raw_score != raw_score:
        raise ValueError("witness raw score does not recompute")
    if witness.query_value != query:
        raise ValueError("witness query does not recompute")


def validate_path_witness(
    problem: ExactPathProblem,
    witness: ExactPathWitness,
    *,
    gamma: int | None = None,
    score_floor: Any | None = None,
) -> bool:
    """Validate a returned or external witness from raw declared inputs."""

    prepared = _prepare_problem(problem)
    if gamma is not None:
        gamma = _nonnegative_integer(gamma, "gamma")
    floor = None if score_floor is None else _fraction(score_floor, "score_floor")
    _validate_prepared_witness(
        prepared,
        witness,
        gamma=gamma,
        score_floor=floor,
    )
    return True


def _run_endpoint(
    prepared: _PreparedProblem,
    schedule: PathSchedule,
    score: _ScoreTransform,
    *,
    sense: Sense,
    gamma: int | None,
    max_frontier_records: int,
) -> ExactPathSolution:
    stats = _MutableStats()
    initial = _Record(
        key=_StateKey(
            (),
            (),
            (),
            (),
            0,
            0,
        ),
        query=Fraction(0),
        selected_edges=(),
        assignments=(),
    )
    frontier: dict[_StateKey, _Record] = {initial.key: initial}
    bag: list[str] = []
    factor_stages, factor_caps, scoped_factors, _max_active_factors = _factor_lifecycle(
        prepared, schedule.actions
    )
    for factor_index, is_scoped in enumerate(scoped_factors):
        if is_scoped:
            continue
        if not _active_counts_can_finish(
            (0,),
            (0,),
            (0,),
            (0,),
            (factor_index,),
            prepared.constraints,
        ):
            return ExactPathSolution(
                status="EXACT_INFEASIBLE",
                certified=True,
                objective_value=None,
                witness=None,
                stats=stats.freeze(
                    limit=max_frontier_records,
                    action_count=len(schedule.actions),
                ),
            )

    for action_index, action in enumerate(schedule.actions):
        next_frontier: dict[_StateKey, _Record] = {}
        factor_stage = factor_stages[action_index]
        if action.kind == "introduce_node":
            node = prepared.node_by_id[action.item_id]
            for record in frontier.values():
                if len(record.key.counts) != len(factor_stage.active_before):
                    raise AssertionError("active factor coordinate mismatch")
                old_position = {
                    factor_index: position
                    for position, factor_index in enumerate(
                        factor_stage.active_before
                    )
                }
                for label in node.support:
                    stats.transition_count += 1
                    counts_during = []
                    requirements_during = []
                    conflict = False
                    for factor_index in factor_stage.active_during:
                        if factor_index in old_position:
                            position = old_position[factor_index]
                            current_count = record.key.counts[position]
                            current_requirement = record.key.requirements[position]
                        else:
                            current_count = 0
                            current_requirement = 0
                        added_count = node.factor_contributions[label].get(
                            factor_index, 0
                        )
                        counts_during.append(
                            min(
                                factor_caps[factor_index],
                                current_count + added_count,
                            )
                        )
                        added_requirement = node.factor_requirements[label].get(
                            factor_index, 0
                        )
                        if (
                            current_requirement
                            and added_requirement
                            and current_requirement != added_requirement
                        ):
                            conflict = True
                            break
                        requirements_during.append(
                            current_requirement or added_requirement
                        )
                    if conflict:
                        continue
                    counts_during_tuple = tuple(counts_during)
                    requirements_during_tuple = tuple(requirements_during)
                    if not _active_counts_can_finish(
                        counts_during_tuple,
                        requirements_during_tuple,
                        factor_stage.minimum_remaining,
                        factor_stage.maximum_remaining,
                        factor_stage.active_during,
                        prepared.constraints,
                    ):
                        continue
                    during_position = {
                        factor_index: position
                        for position, factor_index in enumerate(
                            factor_stage.active_during
                        )
                    }
                    counts_after = tuple(
                        counts_during_tuple[during_position[factor_index]]
                        for factor_index in factor_stage.active_after
                    )
                    requirements_after = tuple(
                        requirements_during_tuple[during_position[factor_index]]
                        for factor_index in factor_stage.active_after
                    )
                    candidate = _Record(
                        key=_StateKey(
                            labels=record.key.labels + (label,),
                            matched=record.key.matched + (False,),
                            counts=counts_after,
                            requirements=requirements_after,
                            gamma_used=record.key.gamma_used,
                            score_cap=record.key.score_cap,
                        ),
                        query=record.query + node.label_query[label],
                        selected_edges=record.selected_edges,
                        assignments=record.assignments + ((node.node_id, label),),
                    )
                    _offer(next_frontier, candidate, sense=sense, stats=stats)
            bag.append(node.node_id)
        elif action.kind == "introduce_edge":
            if factor_stage.active_before != factor_stage.active_after:
                raise AssertionError("factor scope can change only on node introduction")
            edge = prepared.edge_by_id[action.item_id]
            u_index = bag.index(edge.u)
            v_index = bag.index(edge.v)
            for record in frontier.values():
                # Every edge has an explicit not-selected branch.
                stats.transition_count += 1
                _offer(next_frontier, record, sense=sense, stats=stats)
                # The selected branch is counted even when locally infeasible.
                stats.transition_count += 1
                if record.key.matched[u_index] or record.key.matched[v_index]:
                    continue
                label_pair = (
                    record.key.labels[u_index],
                    record.key.labels[v_index],
                )
                if label_pair not in edge.allowed_pairs:
                    continue
                new_gamma = record.key.gamma_used
                if gamma is not None:
                    new_gamma += int(edge.omitted)
                    if new_gamma > gamma:
                        continue
                matched = list(record.key.matched)
                matched[u_index] = True
                matched[v_index] = True
                if score.floor is None:
                    new_score = 0
                else:
                    score_increment = (
                        score.shifted_edge_scores[(edge.edge_id, label_pair)]
                        * edge.core_incidences
                    )
                    new_score = min(
                        score.target,
                        record.key.score_cap + score_increment,
                    )
                candidate = _Record(
                    key=_StateKey(
                        labels=record.key.labels,
                        matched=tuple(matched),
                        counts=record.key.counts,
                        requirements=record.key.requirements,
                        gamma_used=new_gamma,
                        score_cap=new_score,
                    ),
                    query=record.query + edge.query_by_pair[label_pair],
                    selected_edges=record.selected_edges + (edge.edge_id,),
                    assignments=record.assignments,
                )
                _offer(next_frontier, candidate, sense=sense, stats=stats)
        else:
            if factor_stage.active_before != factor_stage.active_after:
                raise AssertionError("factor scope can change only on node introduction")
            node_index = bag.index(action.item_id)
            node = prepared.node_by_id[action.item_id]
            for record in frontier.values():
                stats.transition_count += 1
                if node.role == "core" and not record.key.matched[node_index]:
                    continue
                labels = record.key.labels[:node_index] + record.key.labels[node_index + 1 :]
                matched = record.key.matched[:node_index] + record.key.matched[node_index + 1 :]
                candidate = _Record(
                    key=_StateKey(
                        labels=labels,
                        matched=matched,
                        counts=record.key.counts,
                        requirements=record.key.requirements,
                        gamma_used=record.key.gamma_used,
                        score_cap=record.key.score_cap,
                    ),
                    query=record.query,
                    selected_edges=record.selected_edges,
                    assignments=record.assignments,
                )
                _offer(next_frontier, candidate, sense=sense, stats=stats)
            bag.pop(node_index)

        frontier = _score_dominance_prune(
            next_frontier,
            sense=sense,
            stats=stats,
        )
        stats.peak_live_records = max(stats.peak_live_records, len(frontier))
        if len(frontier) > max_frontier_records:
            raise FrontierLimitExceeded(
                action_index=action_index,
                action=action,
                live_records=len(frontier),
                limit=max_frontier_records,
            )
        if not frontier:
            return ExactPathSolution(
                status="EXACT_INFEASIBLE",
                certified=True,
                objective_value=None,
                witness=None,
                stats=stats.freeze(
                    limit=max_frontier_records,
                    action_count=len(schedule.actions),
                ),
            )

    feasible: list[_Record] = []
    for record in frontier.values():
        if record.key.labels or record.key.matched:
            raise AssertionError("validated schedule ended with a nonempty bag")
        if score.floor is not None and record.key.score_cap < score.target:
            continue
        if record.key.counts or record.key.requirements:
            raise AssertionError("validated factor lifecycle ended nonempty")
        feasible.append(record)
    if not feasible:
        return ExactPathSolution(
            status="EXACT_INFEASIBLE",
            certified=True,
            objective_value=None,
            witness=None,
            stats=stats.freeze(
                limit=max_frontier_records,
                action_count=len(schedule.actions),
            ),
        )
    ordered = sorted(
        feasible,
        key=lambda record: (
            record.query if sense == "min" else -record.query,
            _witness_key(record),
        ),
    )
    optimum = ordered[0]
    witness = _final_witness(optimum, prepared)
    _validate_prepared_witness(
        prepared,
        witness,
        gamma=gamma,
        score_floor=score.floor,
    )
    return ExactPathSolution(
        status="EXACT_OPTIMAL",
        certified=True,
        objective_value=optimum.query,
        witness=witness,
        stats=stats.freeze(
            limit=max_frontier_records,
            action_count=len(schedule.actions),
        ),
    )


def solve_path_frontier_endpoints(
    problem: ExactPathProblem,
    *,
    schedule: PathSchedule | None = None,
    forget_order: Sequence[str] | None = None,
    gamma: int | None = None,
    score_floor: Any | None = None,
    max_frontier_records: int = 1_000_000,
) -> ExactPathEndpoints:
    """Return exact attained query endpoints and complete witnesses.

    Exactly one of ``schedule`` and ``forget_order`` must be supplied.  The
    endpoint is conditional on the declared labels, factors, graph, path, Gamma
    budget, and score floor.  The method is exponential in live-bag width and
    pseudo-polynomial in the cleared-and-capped score target and count bounds.
    """

    prepared = _prepare_problem(problem)
    if (schedule is None) == (forget_order is None):
        raise ValueError("supply exactly one of schedule or forget_order")
    if schedule is None:
        assert forget_order is not None
        schedule = _compile_prepared_path(prepared, forget_order)
    _validate_schedule(prepared, schedule)
    if gamma is not None:
        gamma = _nonnegative_integer(gamma, "gamma")
    max_frontier_records = _nonnegative_integer(
        max_frontier_records, "max_frontier_records"
    )
    if max_frontier_records < 1:
        raise ValueError("max_frontier_records must be at least one")
    score = _score_transform(prepared, score_floor)
    lower_solution = _run_endpoint(
        prepared,
        schedule,
        score,
        sense="min",
        gamma=gamma,
        max_frontier_records=max_frontier_records,
    )
    upper_solution = _run_endpoint(
        prepared,
        schedule,
        score,
        sense="max",
        gamma=gamma,
        max_frontier_records=max_frontier_records,
    )
    if lower_solution.status == "EXACT_INFEASIBLE":
        if upper_solution.status != "EXACT_INFEASIBLE":
            raise AssertionError("min/max feasibility disagreement")
        return ExactPathEndpoints(
            status="EXACT_INFEASIBLE",
            certified=True,
            lower=None,
            upper=None,
            lower_solution=lower_solution,
            upper_solution=upper_solution,
            schedule=schedule,
            core_node_count=sum(node.role == "core" for node in prepared.nodes),
            score_floor=score.floor,
            score_shift_per_core_incidence=score.shift,
            transformed_score_floor=score.transformed_floor,
            integer_score_scale=score.scale,
            capped_integer_score_target=score.target,
        )
    if upper_solution.status == "EXACT_INFEASIBLE":
        raise AssertionError("min/max feasibility disagreement")
    return ExactPathEndpoints(
        status="EXACT_OPTIMAL",
        certified=True,
        lower=lower_solution.objective_value,
        upper=upper_solution.objective_value,
        lower_solution=lower_solution,
        upper_solution=upper_solution,
        schedule=schedule,
        core_node_count=sum(node.role == "core" for node in prepared.nodes),
        score_floor=score.floor,
        score_shift_per_core_incidence=score.shift,
        transformed_score_floor=score.transformed_floor,
        integer_score_scale=score.scale,
        capped_integer_score_target=score.target,
    )


def _ceil_fraction(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def _revalue_relaxed_solution(
    prepared: _PreparedProblem,
    solution: ExactPathSolution,
    *,
    gamma: int | None,
) -> ExactPathSolution:
    """Recompute a rounded-score witness under the original score map."""

    if solution.witness is None:
        return solution
    labels = dict(solution.witness.label_assignments)
    raw_score = Fraction(0)
    for edge_id in solution.witness.selected_edge_ids:
        edge = prepared.edge_by_id[edge_id]
        label_pair = (labels[edge.u], labels[edge.v])
        raw_score += edge.score_by_pair[label_pair] * edge.core_incidences
    witness = replace(solution.witness, raw_score=raw_score)
    _validate_prepared_witness(
        prepared,
        witness,
        gamma=gamma,
        score_floor=None,
    )
    return replace(solution, witness=witness)


def solve_path_frontier_outward_relaxation(
    problem: ExactPathProblem,
    *,
    score_floor: Any,
    score_granularity: Any,
    schedule: PathSchedule | None = None,
    forget_order: Sequence[str] | None = None,
    gamma: int | None = None,
    max_frontier_records: int = 1_000_000,
) -> OutwardScoreRelaxation:
    """Return an exact outer query interval with a bounded score shortfall.

    Let ``N`` be the number of core records, let ``h`` be the common
    per-core-incidence shift that makes every allowed score nonnegative, and
    let ``eta`` be ``score_granularity``.  This routine replaces each shifted
    score by ``floor((s + h) / eta)`` and imposes the integer floor

    ``max(0, ceil((score_floor + h*N) / eta) - N)``.

    The exact score-floor set is contained in the rounded set, which is in
    turn contained in the set whose original floor is relaxed by ``eta*N``.
    Thus the returned query endpoints are certified outward bounds.  If a
    relaxed endpoint witness also satisfies the original floor, that endpoint
    is certified exact a posteriori.  The method is deliberately not described
    as an FPTAS because it controls score slack, not query error.
    """

    prepared = _prepare_problem(problem)
    original_floor = _fraction(score_floor, "score_floor")
    eta = _fraction(score_granularity, "score_granularity")
    if eta <= 0:
        raise ValueError("score_granularity must be strictly positive")
    if gamma is not None:
        gamma = _nonnegative_integer(gamma, "gamma")

    all_scores = [
        value
        for edge in prepared.edges
        for value in edge.score_by_pair.values()
    ]
    minimum = min(all_scores, default=Fraction(0))
    shift = max(Fraction(0), -minimum)
    core_count = sum(node.role == "core" for node in prepared.nodes)
    shifted_floor = original_floor + shift * core_count
    rounded_floor = max(
        0,
        _ceil_fraction(shifted_floor / eta) - core_count,
    )

    rounded_edges: list[EdgeSpec] = []
    for edge in prepared.edges:
        allowed_pairs = tuple(sorted(edge.allowed_pairs, key=repr))
        rounded_scores = {
            label_pair: (edge.score_by_pair[label_pair] + shift) // eta
            for label_pair in allowed_pairs
        }
        rounded_edges.append(
            EdgeSpec(
                edge_id=edge.edge_id,
                u=edge.u,
                v=edge.v,
                omitted=edge.omitted,
                allowed_label_pairs=allowed_pairs,
                score_by_label_pair=rounded_scores,
                query_by_label_pair={
                    label_pair: edge.query_by_pair[label_pair]
                    for label_pair in allowed_pairs
                },
            )
        )
    rounded_problem = ExactPathProblem(
        nodes=problem.nodes,
        edges=tuple(rounded_edges),
        count_constraints=problem.count_constraints,
    )
    relaxed = solve_path_frontier_endpoints(
        rounded_problem,
        schedule=schedule,
        forget_order=forget_order,
        gamma=gamma,
        score_floor=rounded_floor,
        max_frontier_records=max_frontier_records,
    )
    lower_solution = _revalue_relaxed_solution(
        prepared,
        relaxed.lower_solution,
        gamma=gamma,
    )
    upper_solution = _revalue_relaxed_solution(
        prepared,
        relaxed.upper_solution,
        gamma=gamma,
    )
    maximum_shortfall = eta * core_count

    if relaxed.status == "EXACT_INFEASIBLE":
        return OutwardScoreRelaxation(
            status="EXACT_INFEASIBLE",
            certified=True,
            lower=None,
            upper=None,
            lower_solution=lower_solution,
            upper_solution=upper_solution,
            relaxed_endpoints=relaxed,
            original_score_floor=original_floor,
            score_granularity=eta,
            score_shift_per_core_incidence=shift,
            rounded_integer_score_floor=rounded_floor,
            maximum_score_shortfall=maximum_shortfall,
            exact_infeasibility_certified=True,
            exact_feasibility_witnessed=False,
            lower_endpoint_exact_witnessed=False,
            upper_endpoint_exact_witnessed=False,
        )

    if lower_solution.witness is None or upper_solution.witness is None:
        raise AssertionError("optimal relaxed endpoints must contain witnesses")
    lower_exact = lower_solution.witness.raw_score >= original_floor
    upper_exact = upper_solution.witness.raw_score >= original_floor
    for solution in (lower_solution, upper_solution):
        shortfall = max(
            Fraction(0),
            original_floor - solution.witness.raw_score,
        )
        if shortfall > maximum_shortfall:
            raise AssertionError("rounded witness exceeds proved score slack")
    return OutwardScoreRelaxation(
        status="OUTER_OPTIMAL",
        certified=True,
        lower=lower_solution.objective_value,
        upper=upper_solution.objective_value,
        lower_solution=lower_solution,
        upper_solution=upper_solution,
        relaxed_endpoints=relaxed,
        original_score_floor=original_floor,
        score_granularity=eta,
        score_shift_per_core_incidence=shift,
        rounded_integer_score_floor=rounded_floor,
        maximum_score_shortfall=maximum_shortfall,
        exact_infeasibility_certified=False,
        exact_feasibility_witnessed=lower_exact or upper_exact,
        lower_endpoint_exact_witnessed=lower_exact,
        upper_endpoint_exact_witnessed=upper_exact,
    )


__all__ = [
    "CountConstraint",
    "EdgeSpec",
    "ExactPathEndpoints",
    "ExactPathProblem",
    "ExactPathSolution",
    "ExactPathWitness",
    "FrontierLimitExceeded",
    "FrontierStats",
    "NicePathAction",
    "NodeSpec",
    "OutwardScoreRelaxation",
    "PathSchedule",
    "compile_temporal_path",
    "solve_path_frontier_endpoints",
    "solve_path_frontier_outward_relaxation",
    "validate_path_witness",
]
