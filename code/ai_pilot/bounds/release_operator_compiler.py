#!/usr/bin/env python3
"""Compile declared row-release implications for ``path_frontier_dp``.

The temporal frontier solver intentionally knows only about labelled nodes,
count factors, and literal ``LOW``/``HIGH`` requirements.  This module is the
auditable boundary between a separately verified observation operator and
that low-level representation.  It does not infer a release rule from a data
set name or schema.  A caller must supply:

* an operator identifier and an external audit reference;
* observation values and their requirement clauses in disjunctive normal
  form; and
* for every compiled row and substantive label, the factor belonging to each
  declared endpoint.

A conjunction is compiled into one label copy.  A disjunction is compiled
into one copy per clause, so a hidden-row rule such as ``pickup LOW OR dropoff
LOW`` has an explicit witness branch.  This interface accepts DNF, not an
implicit arbitrary Boolean formula: callers must disclose any Boolean-to-DNF
expansion in ``ReleaseClause`` objects.  If an observation has ``c`` clauses,
each substantive label has exactly ``c`` compiled copies; that support blowup
is recorded in ``LabelSupportExpansion``.  Pair-dependent edge maps are lifted
to the copied labels.  The returned problem and schedule can be passed
directly to ``solve_path_frontier_endpoints``.

The compiler also independently audits node/edge event lifecycles, derives the
implicit running-intersection interval of every count factor, and checks the
derived factor width and caps against the schedule.  Projection of a solver
witness removes compiler labels while retaining the chosen release clause;
restoration replays and validates the original exact witness.

An ``audit_reference`` is provenance supplied by the caller, not a claim that
this code has verified the referenced external release semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Hashable, Literal, Mapping, Sequence

from path_frontier_dp import (
    EdgeSpec,
    ExactPathProblem,
    ExactPathWitness,
    NicePathAction,
    NodeSpec,
    PathSchedule,
    compile_temporal_path,
    validate_path_witness,
)


FactorRequirement = Literal["LOW", "HIGH"]
VALID_REQUIREMENTS = frozenset({"LOW", "HIGH"})
VALID_ACTIONS = frozenset(
    {"introduce_node", "introduce_edge", "forget_node"}
)


@dataclass(frozen=True)
class EndpointRequirement:
    """One literal in a release clause, expressed by endpoint role."""

    endpoint: Hashable
    requirement: FactorRequirement


@dataclass(frozen=True)
class ReleaseClause:
    """A conjunction of endpoint requirements and its stable audit label.

    The empty conjunction is TRUE and is accepted only as the sole clause for
    an observation, avoiding redundant witness copies beside a tautology.
    """

    clause_id: str
    requirements: tuple[EndpointRequirement, ...]


@dataclass(frozen=True)
class ObservationImplication:
    """The alternative accepting clauses for one observed row state."""

    observation: Hashable
    alternatives: tuple[ReleaseClause, ...]


@dataclass(frozen=True)
class ReleaseOperatorSpec:
    """Explicit, provenance-bearing row-release semantics.

    ``implications`` are in disjunctive normal form: the requirements inside a
    clause are joined by AND and the clauses for an observation are joined by
    OR.  Endpoint names and observation values are caller-defined hashables.
    """

    operator_id: str
    audit_reference: str
    endpoints: tuple[Hashable, ...]
    implications: tuple[ObservationImplication, ...]


@dataclass(frozen=True)
class ReleaseRowSpec:
    """Bind one problem node to an observed release state.

    For each substantive label, ``endpoint_factors_by_label`` must map every
    operator endpoint to the concrete count factor containing that endpoint.
    The compiler adds a unit contribution to each such factor.
    """

    node_id: str
    observation: Hashable
    endpoint_factors_by_label: Mapping[
        Hashable, Mapping[Hashable, Hashable]
    ]


@dataclass(frozen=True)
class CompiledReleaseLabel:
    """A substantive label paired with one accepting release clause."""

    operator_id: str
    node_id: str
    observation: Hashable
    substantive_label: Hashable
    alternative_index: int
    clause_id: str


@dataclass(frozen=True)
class LabelSupportExpansion:
    """The explicit DNF support blowup for one substantive row label."""

    node_id: str
    substantive_label: Hashable
    dnf_clause_count: int
    compiled_labels: tuple[CompiledReleaseLabel, ...]

    @property
    def compiled_label_count(self) -> int:
        return len(self.compiled_labels)


@dataclass(frozen=True)
class NodeEventLifecycle:
    node_id: str
    introduce_action_index: int
    incident_edge_action_indices: tuple[int, ...]
    forget_action_index: int


@dataclass(frozen=True)
class FactorEventLifecycle:
    """The closed interval over which a DP factor coordinate is live."""

    factor: Hashable
    scoped_node_ids: tuple[str, ...]
    touch_action_indices: tuple[int, ...]
    open_action_index: int | None
    finalize_action_index: int | None
    active_action_range: range


@dataclass(frozen=True)
class ScheduleLifecycleAudit:
    action_count: int
    node_lifecycles: tuple[NodeEventLifecycle, ...]
    factor_lifecycles: tuple[FactorEventLifecycle, ...]
    max_bag_size: int
    max_active_factor_count: int


@dataclass(frozen=True)
class ReleaseCompilation:
    """A solver-ready problem/schedule and their replayable compiler inputs."""

    operator: ReleaseOperatorSpec
    source_problem: ExactPathProblem
    rows: tuple[ReleaseRowSpec, ...]
    problem: ExactPathProblem
    schedule: PathSchedule
    lifecycle_audit: ScheduleLifecycleAudit
    support_expansions: tuple[LabelSupportExpansion, ...]


@dataclass(frozen=True)
class RowReleaseWitness:
    """The release clause selected for one projected row assignment."""

    node_id: str
    observation: Hashable
    substantive_label: Hashable
    alternative_index: int
    clause_id: str
    endpoint_requirements: tuple[
        tuple[Hashable, Hashable, FactorRequirement], ...
    ]


@dataclass(frozen=True)
class ProjectedReleaseWitness:
    """A substantive DP witness plus enough information to restore it."""

    substantive_witness: ExactPathWitness
    row_witnesses: tuple[RowReleaseWitness, ...]


@dataclass(frozen=True)
class _PreparedOperator:
    implication_by_observation: Mapping[Hashable, ObservationImplication]


def _nonblank(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")
    return value


def _hashable(value: object, name: str) -> Hashable:
    try:
        hash(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be hashable") from exc
    return value  # type: ignore[return-value]


def _prepare_operator(operator: ReleaseOperatorSpec) -> _PreparedOperator:
    _nonblank(operator.operator_id, "operator_id")
    _nonblank(operator.audit_reference, "audit_reference")
    if not operator.endpoints:
        raise ValueError("release operator must declare at least one endpoint")
    endpoint_set: set[Hashable] = set()
    for endpoint in operator.endpoints:
        endpoint = _hashable(endpoint, "operator endpoint")
        if endpoint in endpoint_set:
            raise ValueError("release operator endpoints must be distinct")
        endpoint_set.add(endpoint)

    if not operator.implications:
        raise ValueError("release operator must declare at least one implication")
    by_observation: dict[Hashable, ObservationImplication] = {}
    for implication in operator.implications:
        observation = _hashable(
            implication.observation, "release observation"
        )
        if observation in by_observation:
            raise ValueError(
                f"duplicate implication for observation {observation!r}"
            )
        if not implication.alternatives:
            raise ValueError(
                f"observation {observation!r} must have an accepting clause"
            )
        clause_ids: set[str] = set()
        for clause in implication.alternatives:
            clause_id = _nonblank(clause.clause_id, "release clause_id")
            if clause_id in clause_ids:
                raise ValueError(
                    f"duplicate clause_id {clause_id!r} for observation "
                    f"{observation!r}"
                )
            clause_ids.add(clause_id)
            if not clause.requirements and len(implication.alternatives) != 1:
                raise ValueError(
                    f"empty TRUE clause {clause_id!r} must be the sole "
                    "alternative for its observation"
                )
            seen_requirements: dict[Hashable, FactorRequirement] = {}
            for atom in clause.requirements:
                endpoint = _hashable(
                    atom.endpoint, f"endpoint in clause {clause_id!r}"
                )
                if endpoint not in endpoint_set:
                    raise ValueError(
                        f"clause {clause_id!r} references undeclared endpoint "
                        f"{endpoint!r}"
                    )
                if atom.requirement not in VALID_REQUIREMENTS:
                    raise ValueError(
                        "endpoint requirement must be literal 'LOW' or 'HIGH'"
                    )
                previous = seen_requirements.get(endpoint)
                if previous is not None:
                    if previous != atom.requirement:
                        raise ValueError(
                            f"clause {clause_id!r} has contradictory LOW/HIGH "
                            f"literals for endpoint {endpoint!r}"
                        )
                    raise ValueError(
                        f"clause {clause_id!r} repeats endpoint literal "
                        f"{endpoint!r}"
                    )
                seen_requirements[endpoint] = atom.requirement
        by_observation[observation] = implication
    return _PreparedOperator(by_observation)


def paired_visible_implication(
    *,
    observation: Hashable,
    endpoints: Sequence[Hashable],
) -> ObservationImplication:
    """Construct the one-clause DNF ``endpoint-0 HIGH AND endpoint-1 HIGH``."""

    endpoint_tuple = tuple(endpoints)
    if len(endpoint_tuple) != 2:
        raise ValueError("paired visible implication requires exactly two endpoints")
    for endpoint in endpoint_tuple:
        _hashable(endpoint, "paired visible endpoint")
    if len(set(endpoint_tuple)) != 2:
        raise ValueError("paired visible implication endpoints must be distinct")
    _hashable(observation, "paired visible observation")
    return ObservationImplication(
        observation,
        (
            ReleaseClause(
                "both-endpoints-high",
                tuple(
                    EndpointRequirement(endpoint, "HIGH")
                    for endpoint in endpoint_tuple
                ),
            ),
        ),
    )


def paired_hidden_implication(
    *,
    observation: Hashable,
    endpoints: Sequence[Hashable],
) -> ObservationImplication:
    """Construct the two-clause DNF ``endpoint-0 LOW OR endpoint-1 LOW``."""

    endpoint_tuple = tuple(endpoints)
    if len(endpoint_tuple) != 2:
        raise ValueError("paired hidden implication requires exactly two endpoints")
    for endpoint in endpoint_tuple:
        _hashable(endpoint, "paired hidden endpoint")
    if len(set(endpoint_tuple)) != 2:
        raise ValueError("paired hidden implication endpoints must be distinct")
    _hashable(observation, "paired hidden observation")
    return ObservationImplication(
        observation,
        tuple(
            ReleaseClause(
                f"endpoint-{index}-low",
                (EndpointRequirement(endpoint, "LOW"),),
            )
            for index, endpoint in enumerate(endpoint_tuple)
        ),
    )


def two_endpoint_threshold_release_operator(
    *,
    operator_id: str,
    audit_reference: str,
    endpoints: Sequence[Hashable],
    visible_observation: Hashable,
    hidden_observation: Hashable,
) -> ReleaseOperatorSpec:
    """Declare ``visible => HIGH AND HIGH`` and ``hidden => LOW OR LOW``.

    Nothing in this factory assigns data-set column names or observation
    values.  Both endpoint roles, both observed values, and the provenance
    reference are mandatory caller inputs.
    """

    endpoint_tuple = tuple(endpoints)
    if len(endpoint_tuple) != 2:
        raise ValueError("paired threshold operator requires exactly two endpoints")
    _hashable(visible_observation, "visible observation")
    _hashable(hidden_observation, "hidden observation")
    if visible_observation == hidden_observation:
        raise ValueError("visible and hidden observations must be distinct")
    operator = ReleaseOperatorSpec(
        operator_id=operator_id,
        audit_reference=audit_reference,
        endpoints=endpoint_tuple,
        implications=(
            paired_visible_implication(
                observation=visible_observation,
                endpoints=endpoint_tuple,
            ),
            paired_hidden_implication(
                observation=hidden_observation,
                endpoints=endpoint_tuple,
            ),
        ),
    )
    _prepare_operator(operator)
    return operator


def _source_support(node: NodeSpec) -> tuple[Hashable, ...]:
    if isinstance(node.label_support, (str, bytes)):
        raise ValueError(f"label support for {node.node_id!r} must be a sequence")
    return tuple(node.label_support)


def _validate_row(
    row: ReleaseRowSpec,
    node: NodeSpec,
    operator: ReleaseOperatorSpec,
    prepared_operator: _PreparedOperator,
    constraint_by_factor: Mapping[Hashable, object],
) -> None:
    _hashable(row.observation, f"observation for row {row.node_id!r}")
    if row.observation not in prepared_operator.implication_by_observation:
        raise ValueError(
            f"row {row.node_id!r} has undeclared observation "
            f"{row.observation!r}"
        )
    support = _source_support(node)
    if set(row.endpoint_factors_by_label) != set(support):
        raise ValueError(
            f"row {row.node_id!r} must bind endpoints for every substantive label"
        )
    implication = prepared_operator.implication_by_observation[row.observation]
    for label in support:
        endpoint_map = row.endpoint_factors_by_label[label]
        if set(endpoint_map) != set(operator.endpoints):
            raise ValueError(
                f"row {row.node_id!r}/{label!r} must bind exactly the declared "
                "operator endpoints"
            )
        factors: list[Hashable] = []
        for endpoint in operator.endpoints:
            factor = _hashable(
                endpoint_map[endpoint],
                f"factor for row {row.node_id!r}/{label!r}/{endpoint!r}",
            )
            if factor not in constraint_by_factor:
                raise ValueError(
                    f"row {row.node_id!r}/{label!r} references unconstrained "
                    f"factor {factor!r}"
                )
            factors.append(factor)
        if len(set(factors)) != len(factors):
            raise ValueError(
                f"row {row.node_id!r}/{label!r} must bind distinct endpoint cells"
            )
        for clause in implication.alternatives:
            for atom in clause.requirements:
                factor = endpoint_map[atom.endpoint]
                constraint = constraint_by_factor[factor]
                threshold = (
                    getattr(constraint, "low_upper")
                    if atom.requirement == "LOW"
                    else getattr(constraint, "high_lower")
                )
                if threshold is None:
                    threshold_name = (
                        "low_upper"
                        if atom.requirement == "LOW"
                        else "high_lower"
                    )
                    raise ValueError(
                        f"factor {factor!r} required {atom.requirement} by row "
                        f"{row.node_id!r} has no {threshold_name}"
                    )


def _lift_node(
    node: NodeSpec,
    row: ReleaseRowSpec,
    operator: ReleaseOperatorSpec,
    implication: ObservationImplication,
) -> tuple[NodeSpec, Mapping[Hashable, tuple[Hashable, ...]]]:
    raw_contributions = node.factor_contributions or {}
    raw_requirements = node.factor_requirements or {}
    raw_query = node.label_query or {}
    support: list[Hashable] = []
    contributions: dict[Hashable, Mapping[Hashable, int]] = {}
    requirements: dict[
        Hashable, Mapping[Hashable, FactorRequirement]
    ] = {}
    label_query: dict[Hashable, object] = {}
    expansion: dict[Hashable, tuple[Hashable, ...]] = {}

    for substantive_label in _source_support(node):
        variants: list[Hashable] = []
        endpoint_map = row.endpoint_factors_by_label[substantive_label]
        for alternative_index, clause in enumerate(implication.alternatives):
            compiled_label = CompiledReleaseLabel(
                operator_id=operator.operator_id,
                node_id=node.node_id,
                observation=row.observation,
                substantive_label=substantive_label,
                alternative_index=alternative_index,
                clause_id=clause.clause_id,
            )
            _hashable(compiled_label, "compiled release label")
            variants.append(compiled_label)
            support.append(compiled_label)

            compiled_contributions = dict(
                raw_contributions.get(substantive_label, {})
            )
            for endpoint in operator.endpoints:
                factor = endpoint_map[endpoint]
                if (
                    factor in compiled_contributions
                    and compiled_contributions[factor] != 1
                ):
                    raise ValueError(
                        f"row {node.node_id!r}/{substantive_label!r} declares "
                        f"non-unit contribution for endpoint factor {factor!r}"
                    )
                compiled_contributions[factor] = 1
            contributions[compiled_label] = compiled_contributions

            compiled_requirements = dict(
                raw_requirements.get(substantive_label, {})
            )
            for atom in clause.requirements:
                factor = endpoint_map[atom.endpoint]
                previous = compiled_requirements.get(factor)
                if previous is not None and previous != atom.requirement:
                    raise ValueError(
                        f"release clause {clause.clause_id!r} conflicts with "
                        f"an existing requirement on factor {factor!r}"
                    )
                compiled_requirements[factor] = atom.requirement
            requirements[compiled_label] = compiled_requirements
            label_query[compiled_label] = raw_query.get(substantive_label, 0)
        expansion[substantive_label] = tuple(variants)

    return (
        NodeSpec(
            node_id=node.node_id,
            role=node.role,
            label_support=tuple(support),
            factor_contributions=contributions,
            factor_requirements=requirements,
            label_query=label_query,
        ),
        expansion,
    )


def _clone_node(node: NodeSpec) -> NodeSpec:
    """Detach nested maps so replay validation can detect later mutation."""

    contributions = (
        None
        if node.factor_contributions is None
        else {
            label: dict(factors)
            for label, factors in node.factor_contributions.items()
        }
    )
    requirements = (
        None
        if node.factor_requirements is None
        else {
            label: dict(factors)
            for label, factors in node.factor_requirements.items()
        }
    )
    label_query = (
        None if node.label_query is None else dict(node.label_query)
    )
    return NodeSpec(
        node_id=node.node_id,
        role=node.role,
        label_support=_source_support(node),
        factor_contributions=contributions,
        factor_requirements=requirements,
        label_query=label_query,
    )


def _lift_edge(
    edge: EdgeSpec,
    expansions: Mapping[str, Mapping[Hashable, tuple[Hashable, ...]]],
    source_nodes: Mapping[str, NodeSpec],
) -> EdgeSpec:
    support_u = _source_support(source_nodes[edge.u])
    support_v = _source_support(source_nodes[edge.v])
    if edge.allowed_label_pairs is None:
        original_allowed = {
            (label_u, label_v)
            for label_u in support_u
            for label_v in support_v
        }
    else:
        original_allowed = set(edge.allowed_label_pairs)

    lifted_pairs: list[tuple[Hashable, Hashable]] = []
    source_pair_by_lifted: dict[
        tuple[Hashable, Hashable], tuple[Hashable, Hashable]
    ] = {}
    for label_u in support_u:
        for label_v in support_v:
            source_pair = (label_u, label_v)
            if source_pair not in original_allowed:
                continue
            for compiled_u in expansions[edge.u][label_u]:
                for compiled_v in expansions[edge.v][label_v]:
                    lifted_pair = (compiled_u, compiled_v)
                    lifted_pairs.append(lifted_pair)
                    source_pair_by_lifted[lifted_pair] = source_pair

    score_map = None
    if edge.score_by_label_pair is not None:
        score_map = {
            lifted: edge.score_by_label_pair[source]
            for lifted, source in source_pair_by_lifted.items()
        }
    query_map = None
    if edge.query_by_label_pair is not None:
        query_map = {
            lifted: edge.query_by_label_pair[source]
            for lifted, source in source_pair_by_lifted.items()
        }
    return replace(
        edge,
        allowed_label_pairs=tuple(lifted_pairs),
        score_by_label_pair=score_map,
        query_by_label_pair=query_map,
    )


def _build_compiled_problem(
    source_problem: ExactPathProblem,
    rows: tuple[ReleaseRowSpec, ...],
    operator: ReleaseOperatorSpec,
    prepared_operator: _PreparedOperator,
) -> ExactPathProblem:
    source_nodes: dict[str, NodeSpec] = {}
    for node in source_problem.nodes:
        if node.node_id in source_nodes:
            raise ValueError(f"duplicate node_id {node.node_id!r}")
        source_nodes[node.node_id] = node

    row_by_node: dict[str, ReleaseRowSpec] = {}
    for row in rows:
        _nonblank(row.node_id, "release row node_id")
        if row.node_id not in source_nodes:
            raise ValueError(f"release row references unknown node {row.node_id!r}")
        if row.node_id in row_by_node:
            raise ValueError(f"duplicate release row for node {row.node_id!r}")
        row_by_node[row.node_id] = row

    constraint_by_factor: dict[Hashable, object] = {}
    for constraint in source_problem.count_constraints:
        factor = _hashable(constraint.factor, "count factor")
        if factor in constraint_by_factor:
            raise ValueError(f"duplicate count constraint for factor {factor!r}")
        constraint_by_factor[factor] = constraint
    for node_id, row in row_by_node.items():
        _validate_row(
            row,
            source_nodes[node_id],
            operator,
            prepared_operator,
            constraint_by_factor,
        )

    lifted_nodes: list[NodeSpec] = []
    expansions: dict[
        str, Mapping[Hashable, tuple[Hashable, ...]]
    ] = {}
    for node in source_problem.nodes:
        row = row_by_node.get(node.node_id)
        if row is None:
            lifted_nodes.append(_clone_node(node))
            expansions[node.node_id] = {
                label: (label,) for label in _source_support(node)
            }
            continue
        implication = prepared_operator.implication_by_observation[
            row.observation
        ]
        lifted, expansion = _lift_node(node, row, operator, implication)
        lifted_nodes.append(lifted)
        expansions[node.node_id] = expansion

    lifted_edges = tuple(
        _lift_edge(edge, expansions, source_nodes)
        for edge in source_problem.edges
    )
    return ExactPathProblem(
        nodes=tuple(lifted_nodes),
        edges=lifted_edges,
        count_constraints=tuple(source_problem.count_constraints),
    )


def _support_expansion_audit(
    source_problem: ExactPathProblem,
    compiled_problem: ExactPathProblem,
    rows: tuple[ReleaseRowSpec, ...],
    prepared_operator: _PreparedOperator,
) -> tuple[LabelSupportExpansion, ...]:
    source_node_by_id = {
        node.node_id: node for node in source_problem.nodes
    }
    compiled_node_by_id = {
        node.node_id: node for node in compiled_problem.nodes
    }
    expansions: list[LabelSupportExpansion] = []
    for row in rows:
        source_node = source_node_by_id[row.node_id]
        compiled_support = _source_support(compiled_node_by_id[row.node_id])
        implication = prepared_operator.implication_by_observation[
            row.observation
        ]
        clause_count = len(implication.alternatives)
        for substantive_label in _source_support(source_node):
            labels = tuple(
                label
                for label in compiled_support
                if isinstance(label, CompiledReleaseLabel)
                and label.substantive_label == substantive_label
            )
            if len(labels) != clause_count:
                raise ValueError(
                    f"compiled support for row {row.node_id!r}/"
                    f"{substantive_label!r} does not equal its explicit DNF "
                    f"clause count {clause_count}"
                )
            expansions.append(
                LabelSupportExpansion(
                    node_id=row.node_id,
                    substantive_label=substantive_label,
                    dnf_clause_count=clause_count,
                    compiled_labels=labels,
                )
            )
    return tuple(expansions)


def _factor_scopes(
    problem: ExactPathProblem,
) -> tuple[
    Mapping[Hashable, set[str]],
    Mapping[Hashable, int],
]:
    scoped_nodes = {
        constraint.factor: set() for constraint in problem.count_constraints
    }
    scope_maxima = {
        constraint.factor: 0 for constraint in problem.count_constraints
    }
    for node in problem.nodes:
        support = _source_support(node)
        raw_contributions = node.factor_contributions or {}
        raw_requirements = node.factor_requirements or {}
        relevant: set[Hashable] = set()
        for label in support:
            relevant.update(
                factor
                for factor, contribution in raw_contributions.get(
                    label, {}
                ).items()
                if contribution
            )
            relevant.update(raw_requirements.get(label, {}))
        for factor in relevant:
            scoped_nodes[factor].add(node.node_id)
            scope_maxima[factor] += max(
                raw_contributions.get(label, {}).get(factor, 0)
                for label in support
            )
    return scoped_nodes, scope_maxima


def _expected_factor_caps(
    problem: ExactPathProblem,
    scope_maxima: Mapping[Hashable, int],
) -> tuple[tuple[Hashable, int], ...]:
    result: list[tuple[Hashable, int]] = []
    for constraint in problem.count_constraints:
        boundaries = [constraint.lower]
        if constraint.high_lower is not None:
            boundaries.append(constraint.high_lower)
        if constraint.low_upper is not None:
            boundaries.append(constraint.low_upper + 1)
        maximum = scope_maxima[constraint.factor]
        if constraint.upper < maximum:
            boundaries.append(constraint.upper + 1)
        result.append(
            (constraint.factor, min(maximum, max(boundaries, default=0)))
        )
    return tuple(result)


def audit_event_lifecycles(
    problem: ExactPathProblem,
    schedule: PathSchedule,
) -> ScheduleLifecycleAudit:
    """Validate every nice-path event and construct factor interval evidence.

    A factor is touched when a node that may contribute to or require it is
    introduced.  Its active events are exactly the closed interval from its
    first touch through its last, including unrelated events in between.  The
    derived interval is a running-intersection certificate; its maximum overlap
    and factor caps are independently checked against the schedule metadata.
    """

    # Validate raw problem declarations and the supplied forget-order domain.
    # The returned canonical schedule is intentionally ignored: the event
    # sequence supplied below is checked independently.
    compile_temporal_path(problem, schedule.forget_order)

    node_by_id = {node.node_id: node for node in problem.nodes}
    edge_by_id = {edge.edge_id: edge for edge in problem.edges}
    active: list[str] = []
    introduced_nodes: set[str] = set()
    forgotten_nodes: set[str] = set()
    introduced_edges: set[str] = set()
    introduce_at: dict[str, int] = {}
    forget_at: dict[str, int] = {}
    edge_at: dict[str, int] = {}
    actual_forget_order: list[str] = []
    max_bag = 0

    for action_index, action in enumerate(schedule.actions):
        if not isinstance(action, NicePathAction):
            raise ValueError(
                f"schedule action at index {action_index} is not NicePathAction"
            )
        if action.kind not in VALID_ACTIONS:
            raise ValueError(f"invalid schedule action at index {action_index}")
        if action.kind == "introduce_node":
            if action.item_id not in node_by_id:
                raise ValueError(
                    f"schedule introduces unknown node {action.item_id!r}"
                )
            if action.item_id in introduced_nodes:
                raise ValueError(
                    f"schedule introduces node {action.item_id!r} twice"
                )
            introduced_nodes.add(action.item_id)
            introduce_at[action.item_id] = action_index
            active.append(action.item_id)
            max_bag = max(max_bag, len(active))
        elif action.kind == "introduce_edge":
            if action.item_id not in edge_by_id:
                raise ValueError(
                    f"schedule introduces unknown edge {action.item_id!r}"
                )
            if action.item_id in introduced_edges:
                raise ValueError(
                    f"schedule introduces edge {action.item_id!r} twice"
                )
            edge = edge_by_id[action.item_id]
            if edge.u not in active or edge.v not in active:
                raise ValueError(
                    f"edge {edge.edge_id!r} must be introduced while both "
                    "endpoints are active"
                )
            introduced_edges.add(action.item_id)
            edge_at[action.item_id] = action_index
        else:
            if action.item_id not in active:
                raise ValueError(
                    f"schedule forgets inactive node {action.item_id!r}"
                )
            active.remove(action.item_id)
            forgotten_nodes.add(action.item_id)
            forget_at[action.item_id] = action_index
            actual_forget_order.append(action.item_id)

    if active:
        raise ValueError("schedule must forget every introduced node")
    if introduced_nodes != set(node_by_id):
        raise ValueError("schedule must introduce every problem node exactly once")
    if forgotten_nodes != set(node_by_id):
        raise ValueError("schedule must forget every problem node exactly once")
    if introduced_edges != set(edge_by_id):
        raise ValueError("schedule must introduce every problem edge exactly once")
    if tuple(actual_forget_order) != tuple(schedule.forget_order):
        raise ValueError("schedule.forget_order disagrees with its forget actions")
    if max_bag != schedule.max_bag_size:
        raise ValueError("schedule.max_bag_size disagrees with its actions")

    incident_edge_actions: dict[str, list[int]] = {
        node_id: [] for node_id in node_by_id
    }
    for edge_id, action_index in edge_at.items():
        edge = edge_by_id[edge_id]
        incident_edge_actions[edge.u].append(action_index)
        incident_edge_actions[edge.v].append(action_index)
    node_lifecycles: list[NodeEventLifecycle] = []
    for node in problem.nodes:
        edge_indices = tuple(sorted(incident_edge_actions[node.node_id]))
        introduction = introduce_at[node.node_id]
        forgetting = forget_at[node.node_id]
        if any(
            not introduction < edge_index < forgetting
            for edge_index in edge_indices
        ):
            raise ValueError(
                f"incident edge lifecycle escapes node {node.node_id!r}"
            )
        node_lifecycles.append(
            NodeEventLifecycle(
                node.node_id,
                introduction,
                edge_indices,
                forgetting,
            )
        )

    scoped_nodes, scope_maxima = _factor_scopes(problem)
    factor_lifecycles: list[FactorEventLifecycle] = []
    for constraint in problem.count_constraints:
        factor = constraint.factor
        node_ids = tuple(
            sorted(scoped_nodes[factor], key=introduce_at.__getitem__)
        )
        touches = tuple(introduce_at[node_id] for node_id in node_ids)
        if touches:
            opened = touches[0]
            finalized = touches[-1]
            active_range = range(opened, finalized + 1)
        else:
            opened = None
            finalized = None
            active_range = range(0)
        factor_lifecycles.append(
            FactorEventLifecycle(
                factor=factor,
                scoped_node_ids=node_ids,
                touch_action_indices=touches,
                open_action_index=opened,
                finalize_action_index=finalized,
                active_action_range=active_range,
            )
        )
    overlap_delta = [0] * (len(schedule.actions) + 1)
    for lifecycle in factor_lifecycles:
        if lifecycle.open_action_index is None:
            continue
        overlap_delta[lifecycle.open_action_index] += 1
        overlap_delta[lifecycle.finalize_action_index + 1] -= 1
    active_factor_count = 0
    max_active_factors = 0
    for delta in overlap_delta[:-1]:
        active_factor_count += delta
        max_active_factors = max(max_active_factors, active_factor_count)
    if max_active_factors != schedule.max_active_factor_count:
        raise ValueError(
            "schedule.max_active_factor_count disagrees with factor scopes"
        )
    expected_caps = _expected_factor_caps(problem, scope_maxima)
    if tuple(schedule.factor_count_caps) != expected_caps:
        raise ValueError("schedule.factor_count_caps disagrees with factor scopes")

    return ScheduleLifecycleAudit(
        action_count=len(schedule.actions),
        node_lifecycles=tuple(node_lifecycles),
        factor_lifecycles=tuple(factor_lifecycles),
        max_bag_size=max_bag,
        max_active_factor_count=max_active_factors,
    )


def compile_release_operator(
    source_problem: ExactPathProblem,
    *,
    rows: Sequence[ReleaseRowSpec],
    operator: ReleaseOperatorSpec,
    forget_order: Sequence[str],
) -> ReleaseCompilation:
    """Compile declared release implications into a solver-ready schedule."""

    prepared_operator = _prepare_operator(operator)
    row_tuple = tuple(rows)
    order = tuple(forget_order)
    # This validates the complete source problem before any label lifting can
    # obscure an error in its declared supports or pair maps.
    compile_temporal_path(source_problem, order)
    problem = _build_compiled_problem(
        source_problem, row_tuple, operator, prepared_operator
    )
    schedule = compile_temporal_path(problem, order)
    lifecycle_audit = audit_event_lifecycles(problem, schedule)
    support_expansions = _support_expansion_audit(
        source_problem, problem, row_tuple, prepared_operator
    )
    return ReleaseCompilation(
        operator=operator,
        source_problem=source_problem,
        rows=row_tuple,
        problem=problem,
        schedule=schedule,
        lifecycle_audit=lifecycle_audit,
        support_expansions=support_expansions,
    )


def validate_release_compilation(compilation: ReleaseCompilation) -> bool:
    """Recompile all declared inputs and compare the problem, events, and audit."""

    prepared_operator = _prepare_operator(compilation.operator)
    compile_temporal_path(
        compilation.source_problem, compilation.schedule.forget_order
    )
    expected_problem = _build_compiled_problem(
        compilation.source_problem,
        tuple(compilation.rows),
        compilation.operator,
        prepared_operator,
    )
    if expected_problem != compilation.problem:
        raise ValueError("compiled problem does not replay from release inputs")
    expected_schedule = compile_temporal_path(
        expected_problem, compilation.schedule.forget_order
    )
    if expected_schedule != compilation.schedule:
        raise ValueError("compiled event schedule does not replay from inputs")
    expected_audit = audit_event_lifecycles(
        compilation.problem, compilation.schedule
    )
    if expected_audit != compilation.lifecycle_audit:
        raise ValueError("stored lifecycle audit does not replay from schedule")
    expected_expansions = _support_expansion_audit(
        compilation.source_problem,
        compilation.problem,
        tuple(compilation.rows),
        prepared_operator,
    )
    if expected_expansions != compilation.support_expansions:
        raise ValueError("stored DNF support expansion does not replay from inputs")
    return True


def _row_maps(
    compilation: ReleaseCompilation,
) -> tuple[
    Mapping[str, ReleaseRowSpec],
    Mapping[str, NodeSpec],
    _PreparedOperator,
]:
    return (
        {row.node_id: row for row in compilation.rows},
        {node.node_id: node for node in compilation.source_problem.nodes},
        _prepare_operator(compilation.operator),
    )


def _row_witness_for_label(
    compilation: ReleaseCompilation,
    row: ReleaseRowSpec,
    label: CompiledReleaseLabel,
    prepared_operator: _PreparedOperator,
) -> RowReleaseWitness:
    if (
        label.operator_id != compilation.operator.operator_id
        or label.node_id != row.node_id
        or label.observation != row.observation
    ):
        raise ValueError(f"compiled label provenance fails for row {row.node_id!r}")
    implication = prepared_operator.implication_by_observation[row.observation]
    if not 0 <= label.alternative_index < len(implication.alternatives):
        raise ValueError(f"compiled label branch fails for row {row.node_id!r}")
    clause = implication.alternatives[label.alternative_index]
    if clause.clause_id != label.clause_id:
        raise ValueError(f"compiled label clause fails for row {row.node_id!r}")
    try:
        endpoint_map = row.endpoint_factors_by_label[label.substantive_label]
    except KeyError as exc:
        raise ValueError(
            f"compiled label has unsupported substantive label for {row.node_id!r}"
        ) from exc
    endpoint_requirements = tuple(
        (
            atom.endpoint,
            endpoint_map[atom.endpoint],
            atom.requirement,
        )
        for atom in clause.requirements
    )
    return RowReleaseWitness(
        node_id=row.node_id,
        observation=row.observation,
        substantive_label=label.substantive_label,
        alternative_index=label.alternative_index,
        clause_id=label.clause_id,
        endpoint_requirements=endpoint_requirements,
    )


def project_release_witness(
    compilation: ReleaseCompilation,
    witness: ExactPathWitness,
    *,
    gamma: int | None = None,
    score_floor: object | None = None,
) -> ProjectedReleaseWitness:
    """Validate and project a compiled witness to substantive row labels."""

    validate_release_compilation(compilation)
    validate_path_witness(
        compilation.problem, witness, gamma=gamma, score_floor=score_floor
    )
    row_by_node, _source_node_by_id, prepared_operator = _row_maps(compilation)
    projected_assignments: list[tuple[str, Hashable]] = []
    row_witnesses: list[RowReleaseWitness] = []
    for node_id, assigned_label in witness.label_assignments:
        row = row_by_node.get(node_id)
        if row is None:
            projected_assignments.append((node_id, assigned_label))
            continue
        if not isinstance(assigned_label, CompiledReleaseLabel):
            raise ValueError(f"release row {node_id!r} lacks a compiled label")
        row_witness = _row_witness_for_label(
            compilation, row, assigned_label, prepared_operator
        )
        row_witnesses.append(row_witness)
        projected_assignments.append(
            (node_id, assigned_label.substantive_label)
        )
    return ProjectedReleaseWitness(
        substantive_witness=replace(
            witness, label_assignments=tuple(projected_assignments)
        ),
        row_witnesses=tuple(row_witnesses),
    )


def restore_release_witness(
    compilation: ReleaseCompilation,
    projected: ProjectedReleaseWitness,
    *,
    gamma: int | None = None,
    score_floor: object | None = None,
) -> ExactPathWitness:
    """Restore, replay, and validate an exact compiled witness."""

    validate_release_compilation(compilation)
    row_by_node, source_node_by_id, prepared_operator = _row_maps(compilation)
    branch_by_node: dict[str, RowReleaseWitness] = {}
    for branch in projected.row_witnesses:
        if branch.node_id in branch_by_node:
            raise ValueError(
                f"projected witness repeats release row {branch.node_id!r}"
            )
        branch_by_node[branch.node_id] = branch
    if set(branch_by_node) != set(row_by_node):
        raise ValueError("projected witness must contain every release row branch")

    restored_assignments: list[tuple[str, Hashable]] = []
    seen_nodes: set[str] = set()
    for node_id, substantive_label in (
        projected.substantive_witness.label_assignments
    ):
        if node_id in seen_nodes:
            raise ValueError("projected witness repeats a node assignment")
        seen_nodes.add(node_id)
        row = row_by_node.get(node_id)
        if row is None:
            restored_assignments.append((node_id, substantive_label))
            continue
        branch = branch_by_node[node_id]
        if (
            branch.node_id != node_id
            or branch.observation != row.observation
            or branch.substantive_label != substantive_label
        ):
            raise ValueError(f"projected release branch fails for row {node_id!r}")
        if substantive_label not in _source_support(source_node_by_id[node_id]):
            raise ValueError(
                f"projected witness has unsupported label for row {node_id!r}"
            )
        compiled_label = CompiledReleaseLabel(
            operator_id=compilation.operator.operator_id,
            node_id=node_id,
            observation=row.observation,
            substantive_label=substantive_label,
            alternative_index=branch.alternative_index,
            clause_id=branch.clause_id,
        )
        expected_branch = _row_witness_for_label(
            compilation, row, compiled_label, prepared_operator
        )
        if expected_branch != branch:
            raise ValueError(f"projected release evidence fails for row {node_id!r}")
        restored_assignments.append((node_id, compiled_label))
    if seen_nodes != set(source_node_by_id):
        raise ValueError("projected witness must assign every problem node")

    restored = replace(
        projected.substantive_witness,
        label_assignments=tuple(restored_assignments),
    )
    validate_path_witness(
        compilation.problem,
        restored,
        gamma=gamma,
        score_floor=score_floor,
    )
    return restored


__all__ = [
    "CompiledReleaseLabel",
    "EndpointRequirement",
    "FactorEventLifecycle",
    "LabelSupportExpansion",
    "NodeEventLifecycle",
    "ObservationImplication",
    "ProjectedReleaseWitness",
    "ReleaseClause",
    "ReleaseCompilation",
    "ReleaseOperatorSpec",
    "ReleaseRowSpec",
    "RowReleaseWitness",
    "ScheduleLifecycleAudit",
    "audit_event_lifecycles",
    "compile_release_operator",
    "paired_hidden_implication",
    "paired_visible_implication",
    "project_release_witness",
    "restore_release_witness",
    "two_endpoint_threshold_release_operator",
    "validate_release_compilation",
]
