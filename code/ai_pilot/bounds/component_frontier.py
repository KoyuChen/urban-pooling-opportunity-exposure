#!/usr/bin/env python3
"""Exact incidence-component decomposition for the temporal frontier DP.

This module is an engineering layer over :mod:`path_frontier_dp`; it is not a
new identification result or a new complexity theorem.  It exploits genuine
disconnection while retaining the three quantities that still couple the
components: the global omitted-edge budget ``Gamma``, the global additive
score floor, and the additive query objective.

Exact decomposition condition
-----------------------------
Form an undirected incidence graph with one vertex for every record and one
vertex for every declared count/release factor.  Join the endpoints of every
candidate matching edge.  Join a record to a factor whenever at least one of
the record's supported labels contributes to that factor or activates a
``LOW``/``HIGH`` requirement on it.  The connected components of this graph
are the only components split by this implementation.  In particular, a
factor referenced by records in two otherwise disconnected candidate graphs
joins those graphs and is never duplicated or checked componentwise.

For these components, every matching-degree constraint, allowed label-pair
restriction, label support, count bound, and release requirement is local.
For a complete world ``w = (w_1,...,w_k)``, the remaining quantities satisfy

``gamma(w) = sum_i gamma(w_i)``,
``score(w) = sum_i score(w_i)``, and
``query(w) = sum_i query(w_i)``.

Consequently, unions give a bijection between structurally feasible global
worlds and tuples of structurally feasible component worlds.  The global
world is resource-feasible exactly when its summed omission count is at most
``Gamma`` and its summed score reaches the score floor.  The convolution below
therefore enumerates the exact nondominated resource/query frontier.  A record
with weakly smaller omission use, weakly larger score, and a no-worse query
value can replace a dominated record under every continuation.  Induction over
the components proves that pruning preserves an optimizer.  The returned
endpoint is attained because the implementation retains and unions the local
witnesses; the union is independently revalidated against the original raw
problem.

Score arithmetic uses the *single global* per-core-incidence shift and integer
scale from ``path_frontier_dp``.  Since every core has selected degree one, the
shift adds the same constant times the global core count to every feasible
world and remains additive across components.  Using separately chosen local
score origins without translating them back to one global floor would be an
invalid convolution; this implementation does not do that.

The speed benefit is operational, not universal.  It is largest when a supplied
temporal order interleaves disconnected incidence components: the monolithic
live bag then contains records from several components, whereas each local path
is solved at its own width and only a two-resource frontier is convolved.  A
single incidence component receives no structural speedup.

The implementation intentionally reuses validated internal preparation and
transition primitives from ``path_frontier_dp``.  Keeping this module beside
that solver and testing it against the monolithic public API makes this coupling
explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Hashable, Literal, Sequence

import path_frontier_dp as _path


Sense = Literal["min", "max"]

# This layer deliberately reuses the reference solver's validated internal
# transition objects.  There is no stable third-party API promise: fail loudly
# if the selected object layout drifts instead of silently misaddressing state.
# This is not a semantic-version check; exact cross-checks remain necessary.
PATH_FRONTIER_INTERNAL_API_REVISION = (
    "path_frontier_dp-internal-layout-2026-08-27"
)


def _assert_path_frontier_compatibility() -> None:
    required_callables = (
        "_prepare_problem",
        "_compile_prepared_path",
        "_score_transform",
        "_factor_lifecycle",
        "_active_counts_can_finish",
        "_offer",
        "_final_witness",
        "_validate_prepared_witness",
        "_nonnegative_integer",
        "_StateKey",
        "_Record",
        "_MutableStats",
    )
    missing = [name for name in required_callables if not callable(getattr(_path, name, None))]
    if missing:
        raise RuntimeError(
            "component_frontier is incompatible with path_frontier_dp; "
            f"missing internal callables {missing!r} under "
            f"{PATH_FRONTIER_INTERNAL_API_REVISION}"
        )
    expected_fields = {
        "_StateKey": (
            "labels",
            "matched",
            "counts",
            "requirements",
            "gamma_used",
            "score_cap",
        ),
        "_Record": ("key", "query", "selected_edges", "assignments"),
        "_FactorStage": (
            "active_before",
            "active_during",
            "active_after",
            "minimum_remaining",
            "maximum_remaining",
        ),
        "_ScoreTransform": (
            "floor",
            "shift",
            "transformed_floor",
            "scale",
            "target",
            "shifted_edge_scores",
        ),
        "_MutableStats": (
            "introduced_states",
            "accepted_records",
            "dominance_pruned_records",
            "peak_live_records",
            "transition_count",
        ),
    }
    for class_name, expected in expected_fields.items():
        cls = getattr(_path, class_name, None)
        actual = tuple(getattr(cls, "__dataclass_fields__", {}))
        if actual != expected:
            raise RuntimeError(
                "component_frontier is incompatible with path_frontier_dp; "
                f"{class_name} fields are {actual!r}, expected {expected!r} "
                f"under {PATH_FRONTIER_INTERNAL_API_REVISION}"
            )


@dataclass(frozen=True)
class IncidenceComponent:
    """One maximal record/factor incidence component."""

    index: int
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    factors: tuple[Hashable, ...]


@dataclass(frozen=True)
class ComponentFrontierStats:
    """Deterministic record counters for one decomposed endpoint run.

    These are live-frontier record counts, not heap/RSS measurements.  Complete
    witnesses make records variable-sized, so no field should be interpreted
    as a memory estimate.
    """

    component_count: int
    local_action_count: int
    local_introduced_states: int
    local_accepted_records: int
    local_dominance_pruned_records: int
    local_transition_count: int
    local_max_single_frontier_records: int
    component_terminal_frontier_sizes: tuple[int, ...]
    convolution_introduced_records: int
    convolution_accepted_records: int
    convolution_dominance_pruned_records: int
    convolution_transition_count: int
    convolution_max_single_frontier_records: int
    max_frontier_records: int

    @property
    def max_single_frontier_records(self) -> int:
        return max(
            self.local_max_single_frontier_records,
            self.convolution_max_single_frontier_records,
        )

    @property
    def total_component_terminal_frontier_records(self) -> int:
        return sum(self.component_terminal_frontier_sizes)

    @property
    def transition_count(self) -> int:
        return self.local_transition_count + self.convolution_transition_count


@dataclass(frozen=True)
class ComponentPathSolution:
    """One attained endpoint and its global and component witnesses."""

    status: Literal["EXACT_OPTIMAL", "EXACT_INFEASIBLE"]
    certified: bool
    objective_value: Fraction | None
    witness: _path.ExactPathWitness | None
    component_witnesses: tuple[_path.ExactPathWitness, ...]
    stats: ComponentFrontierStats


@dataclass(frozen=True)
class ComponentPathEndpoints:
    """Exact endpoints returned by incidence decomposition and convolution."""

    status: Literal["EXACT_OPTIMAL", "EXACT_INFEASIBLE"]
    certified: bool
    lower: Fraction | None
    upper: Fraction | None
    lower_solution: ComponentPathSolution
    upper_solution: ComponentPathSolution
    components: tuple[IncidenceComponent, ...]
    global_schedule: _path.PathSchedule
    component_schedules: tuple[_path.PathSchedule, ...]
    core_node_count: int
    score_floor: Fraction | None
    score_shift_per_core_incidence: Fraction
    transformed_score_floor: Fraction | None
    integer_score_scale: int
    capped_integer_score_target: int


class ComponentFrontierLimitExceeded(RuntimeError):
    """Raised when a local or convolution frontier exceeds its exact limit."""

    def __init__(
        self,
        *,
        phase: Literal["local", "convolution"],
        component_index: int,
        live_records: int,
        limit: int,
        action_index: int | None = None,
        action: _path.NicePathAction | None = None,
    ) -> None:
        self.phase = phase
        self.component_index = component_index
        self.live_records = live_records
        self.limit = limit
        self.action_index = action_index
        self.action = action
        if phase == "local":
            detail = (
                f"component {component_index}, action {action_index} "
                f"({action.kind}:{action.item_id})"
                if action is not None
                else f"component {component_index}"
            )
        else:
            detail = f"after convolving component {component_index}"
        super().__init__(
            f"exact component frontier exceeded limit {limit} {detail}; "
            f"required {live_records} records"
        )


@dataclass(frozen=True)
class _ComponentWork:
    public: IncidenceComponent
    problem: _path.ExactPathProblem
    prepared: Any
    schedule: _path.PathSchedule


@dataclass(frozen=True)
class _LocalResult:
    status: Literal["EXACT_FRONTIER", "EXACT_INFEASIBLE"]
    records: tuple[Any, ...]
    stats: _path.FrontierStats


@dataclass(frozen=True)
class _ConvolutionRecord:
    gamma_used: int
    score_cap: int
    query: Fraction
    selected_edges: tuple[str, ...]
    assignments: tuple[tuple[str, Hashable], ...]
    local_records: tuple[Any, ...]


@dataclass
class _MutableConvolutionStats:
    introduced: int = 0
    accepted: int = 0
    dominance_pruned: int = 0
    transitions: int = 0
    max_live_records: int = 1


def _record_witness_key(record: Any) -> tuple[Any, ...]:
    assignments = tuple(
        (node_id, repr(label)) for node_id, label in record.assignments
    )
    return (record.selected_edges, assignments)


def _convolution_witness_key(record: _ConvolutionRecord) -> tuple[Any, ...]:
    assignments = tuple(
        (node_id, repr(label)) for node_id, label in record.assignments
    )
    return (record.selected_edges, assignments)


def _query_no_worse(left: Fraction, right: Fraction, sense: Sense) -> bool:
    return left <= right if sense == "min" else left >= right


def _query_better(left: Fraction, right: Fraction, sense: Sense) -> bool:
    return left < right if sense == "min" else left > right


def _resource_dominates(left: Any, right: Any, sense: Sense) -> bool:
    """Whether one path record dominates another under every continuation."""

    if left.key.gamma_used > right.key.gamma_used:
        return False
    if left.key.score_cap < right.key.score_cap:
        return False
    if not _query_no_worse(left.query, right.query, sense):
        return False
    return (
        left.key.gamma_used < right.key.gamma_used
        or left.key.score_cap > right.key.score_cap
        or _query_better(left.query, right.query, sense)
    )


def _resource_dominance_prune(
    records: dict[Any, Any],
    *,
    sense: Sense,
    stats: Any,
) -> dict[Any, Any]:
    """Prune gamma/score/query dominance at a common structural state."""

    groups: dict[tuple[Any, ...], list[Any]] = {}
    for record in records.values():
        key = record.key
        structural = (
            key.labels,
            key.matched,
            key.counts,
            key.requirements,
        )
        groups.setdefault(structural, []).append(record)
    kept: dict[Any, Any] = {}
    for group in groups.values():
        ordered = sorted(
            group,
            key=lambda record: (
                record.key.gamma_used,
                -record.key.score_cap,
                record.query if sense == "min" else -record.query,
                _record_witness_key(record),
            ),
        )
        for index, record in enumerate(ordered):
            if any(
                _resource_dominates(other, record, sense)
                for other_index, other in enumerate(ordered)
                if other_index != index
            ):
                stats.dominance_pruned_records += 1
            else:
                kept[record.key] = record
    return kept


def _component_incidence_sets(
    prepared: Any,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Return maximal sets of node and factor indices in deterministic order."""

    node_count = len(prepared.nodes)
    factor_count = len(prepared.constraints)
    item_count = node_count + factor_count
    parent = list(range(item_count))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            if root_left < root_right:
                parent[root_right] = root_left
            else:
                parent[root_left] = root_right

    node_index = {
        node.node_id: index for index, node in enumerate(prepared.nodes)
    }
    for edge in prepared.edges:
        union(node_index[edge.u], node_index[edge.v])
    for index, node in enumerate(prepared.nodes):
        relevant: set[int] = set()
        for label in node.support:
            relevant.update(node.factor_contributions[label])
            relevant.update(node.factor_requirements[label])
        for factor_index in relevant:
            union(index, node_count + factor_index)

    grouped_nodes: dict[int, list[int]] = {}
    grouped_factors: dict[int, list[int]] = {}
    for index in range(node_count):
        grouped_nodes.setdefault(find(index), []).append(index)
    for factor_index in range(factor_count):
        grouped_factors.setdefault(
            find(node_count + factor_index), []
        ).append(factor_index)
    roots = set(grouped_nodes) | set(grouped_factors)
    components = [
        (
            tuple(grouped_nodes.get(root, ())),
            tuple(grouped_factors.get(root, ())),
        )
        for root in roots
    ]
    return tuple(
        sorted(
            components,
            key=lambda item: (
                item[0][0] if item[0] else node_count + item[1][0],
                item,
            ),
        )
    )


def decompose_incidence_components(
    problem: _path.ExactPathProblem,
) -> tuple[IncidenceComponent, ...]:
    """Return the maximal safe incidence components of a validated problem."""

    _assert_path_frontier_compatibility()
    prepared = _path._prepare_problem(problem)
    result: list[IncidenceComponent] = []
    for component_index, (node_indices, factor_indices) in enumerate(
        _component_incidence_sets(prepared)
    ):
        node_ids = tuple(prepared.nodes[index].node_id for index in node_indices)
        node_set = set(node_ids)
        edge_ids = tuple(
            edge.edge_id
            for edge in prepared.edges
            if edge.u in node_set
        )
        factors = tuple(
            prepared.constraints[index].factor for index in factor_indices
        )
        result.append(
            IncidenceComponent(
                index=component_index,
                node_ids=node_ids,
                edge_ids=edge_ids,
                factors=factors,
            )
        )
    return tuple(result)


def _build_component_work(
    problem: _path.ExactPathProblem,
    prepared: Any,
    forget_order: tuple[str, ...],
) -> tuple[tuple[IncidenceComponent, ...], tuple[_ComponentWork, ...]]:
    raw_node_by_id = {node.node_id: node for node in problem.nodes}
    raw_edge_by_id = {edge.edge_id: edge for edge in problem.edges}
    raw_constraint_by_factor = {
        constraint.factor: constraint for constraint in problem.count_constraints
    }
    order_position = {node_id: index for index, node_id in enumerate(forget_order)}

    drafts: list[tuple[tuple[Any, ...], tuple[int, ...], tuple[int, ...]]] = []
    for node_indices, factor_indices in _component_incidence_sets(prepared):
        node_positions = tuple(
            order_position[prepared.nodes[index].node_id]
            for index in node_indices
        )
        key = (
            min(node_positions)
            if node_positions
            else len(forget_order) + factor_indices[0],
            node_positions,
            factor_indices,
        )
        drafts.append((key, node_indices, factor_indices))
    drafts.sort(key=lambda item: item[0])

    public_components: list[IncidenceComponent] = []
    work: list[_ComponentWork] = []
    for component_index, (_key, node_indices, factor_indices) in enumerate(drafts):
        node_ids = tuple(prepared.nodes[index].node_id for index in node_indices)
        node_set = set(node_ids)
        edge_ids = tuple(
            edge.edge_id
            for edge in prepared.edges
            if edge.u in node_set
        )
        factors = tuple(
            prepared.constraints[index].factor for index in factor_indices
        )
        public = IncidenceComponent(
            index=component_index,
            node_ids=node_ids,
            edge_ids=edge_ids,
            factors=factors,
        )
        local_problem = _path.ExactPathProblem(
            nodes=tuple(raw_node_by_id[node_id] for node_id in node_ids),
            edges=tuple(raw_edge_by_id[edge_id] for edge_id in edge_ids),
            count_constraints=tuple(
                raw_constraint_by_factor[factor] for factor in factors
            ),
        )
        local_prepared = _path._prepare_problem(local_problem)
        local_order = tuple(
            node_id for node_id in forget_order if node_id in node_set
        )
        local_schedule = _path._compile_prepared_path(
            local_prepared,
            local_order,
        )
        public_components.append(public)
        work.append(
            _ComponentWork(
                public=public,
                problem=local_problem,
                prepared=local_prepared,
                schedule=local_schedule,
            )
        )
    return tuple(public_components), tuple(work)


def _run_local_frontier(
    component: _ComponentWork,
    global_score: Any,
    *,
    sense: Sense,
    gamma: int | None,
    max_frontier_records: int,
) -> _LocalResult:
    """Run one component once and retain its exact resource/query frontier."""

    prepared = component.prepared
    schedule = component.schedule
    stats = _path._MutableStats()
    initial = _path._Record(
        key=_path._StateKey((), (), (), (), 0, 0),
        query=Fraction(0),
        selected_edges=(),
        assignments=(),
    )
    frontier = {initial.key: initial}
    bag: list[str] = []
    factor_stages, factor_caps, scoped_factors, _ = _path._factor_lifecycle(
        prepared,
        schedule.actions,
    )
    for factor_index, is_scoped in enumerate(scoped_factors):
        if is_scoped:
            continue
        if not _path._active_counts_can_finish(
            (0,),
            (0,),
            (0,),
            (0,),
            (factor_index,),
            prepared.constraints,
        ):
            return _LocalResult(
                status="EXACT_INFEASIBLE",
                records=(),
                stats=stats.freeze(
                    limit=max_frontier_records,
                    action_count=len(schedule.actions),
                ),
            )

    for action_index, action in enumerate(schedule.actions):
        next_frontier: dict[Any, Any] = {}
        stage = factor_stages[action_index]
        if action.kind == "introduce_node":
            node = prepared.node_by_id[action.item_id]
            for record in frontier.values():
                if len(record.key.counts) != len(stage.active_before):
                    raise AssertionError("active factor coordinate mismatch")
                old_position = {
                    factor_index: position
                    for position, factor_index in enumerate(stage.active_before)
                }
                for label in node.support:
                    stats.transition_count += 1
                    counts_during: list[int] = []
                    requirements_during: list[int] = []
                    conflict = False
                    for factor_index in stage.active_during:
                        if factor_index in old_position:
                            position = old_position[factor_index]
                            current_count = record.key.counts[position]
                            current_requirement = record.key.requirements[position]
                        else:
                            current_count = 0
                            current_requirement = 0
                        added_count = node.factor_contributions[label].get(
                            factor_index,
                            0,
                        )
                        counts_during.append(
                            min(
                                factor_caps[factor_index],
                                current_count + added_count,
                            )
                        )
                        added_requirement = node.factor_requirements[label].get(
                            factor_index,
                            0,
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
                    counts_tuple = tuple(counts_during)
                    requirements_tuple = tuple(requirements_during)
                    if not _path._active_counts_can_finish(
                        counts_tuple,
                        requirements_tuple,
                        stage.minimum_remaining,
                        stage.maximum_remaining,
                        stage.active_during,
                        prepared.constraints,
                    ):
                        continue
                    during_position = {
                        factor_index: position
                        for position, factor_index in enumerate(stage.active_during)
                    }
                    candidate = _path._Record(
                        key=_path._StateKey(
                            labels=record.key.labels + (label,),
                            matched=record.key.matched + (False,),
                            counts=tuple(
                                counts_tuple[during_position[factor_index]]
                                for factor_index in stage.active_after
                            ),
                            requirements=tuple(
                                requirements_tuple[during_position[factor_index]]
                                for factor_index in stage.active_after
                            ),
                            gamma_used=record.key.gamma_used,
                            score_cap=record.key.score_cap,
                        ),
                        query=record.query + node.label_query[label],
                        selected_edges=record.selected_edges,
                        assignments=record.assignments + ((node.node_id, label),),
                    )
                    _path._offer(
                        next_frontier,
                        candidate,
                        sense=sense,
                        stats=stats,
                    )
            bag.append(node.node_id)
        elif action.kind == "introduce_edge":
            if stage.active_before != stage.active_after:
                raise AssertionError("factor scope can change only on node introduction")
            edge = prepared.edge_by_id[action.item_id]
            u_index = bag.index(edge.u)
            v_index = bag.index(edge.v)
            for record in frontier.values():
                stats.transition_count += 1
                _path._offer(
                    next_frontier,
                    record,
                    sense=sense,
                    stats=stats,
                )
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
                if global_score.floor is None:
                    new_score = 0
                else:
                    increment = (
                        global_score.shifted_edge_scores[
                            (edge.edge_id, label_pair)
                        ]
                        * edge.core_incidences
                    )
                    new_score = min(
                        global_score.target,
                        record.key.score_cap + increment,
                    )
                matched = list(record.key.matched)
                matched[u_index] = True
                matched[v_index] = True
                candidate = _path._Record(
                    key=_path._StateKey(
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
                _path._offer(
                    next_frontier,
                    candidate,
                    sense=sense,
                    stats=stats,
                )
        else:
            if stage.active_before != stage.active_after:
                raise AssertionError("factor scope can change only on node introduction")
            node_index = bag.index(action.item_id)
            node = prepared.node_by_id[action.item_id]
            for record in frontier.values():
                stats.transition_count += 1
                if node.role == "core" and not record.key.matched[node_index]:
                    continue
                candidate = _path._Record(
                    key=_path._StateKey(
                        labels=(
                            record.key.labels[:node_index]
                            + record.key.labels[node_index + 1 :]
                        ),
                        matched=(
                            record.key.matched[:node_index]
                            + record.key.matched[node_index + 1 :]
                        ),
                        counts=record.key.counts,
                        requirements=record.key.requirements,
                        gamma_used=record.key.gamma_used,
                        score_cap=record.key.score_cap,
                    ),
                    query=record.query,
                    selected_edges=record.selected_edges,
                    assignments=record.assignments,
                )
                _path._offer(
                    next_frontier,
                    candidate,
                    sense=sense,
                    stats=stats,
                )
            bag.pop(node_index)

        frontier = _resource_dominance_prune(
            next_frontier,
            sense=sense,
            stats=stats,
        )
        stats.peak_live_records = max(stats.peak_live_records, len(frontier))
        if len(frontier) > max_frontier_records:
            raise ComponentFrontierLimitExceeded(
                phase="local",
                component_index=component.public.index,
                live_records=len(frontier),
                limit=max_frontier_records,
                action_index=action_index,
                action=action,
            )
        if not frontier:
            return _LocalResult(
                status="EXACT_INFEASIBLE",
                records=(),
                stats=stats.freeze(
                    limit=max_frontier_records,
                    action_count=len(schedule.actions),
                ),
            )

    for record in frontier.values():
        if record.key.labels or record.key.matched:
            raise AssertionError("validated component schedule ended with a live bag")
        if record.key.counts or record.key.requirements:
            raise AssertionError("validated factor lifecycle ended nonempty")
    return _LocalResult(
        status="EXACT_FRONTIER",
        records=tuple(
            sorted(
                frontier.values(),
                key=lambda record: (
                    record.key.gamma_used,
                    -record.key.score_cap,
                    record.query if sense == "min" else -record.query,
                    _record_witness_key(record),
                ),
            )
        ),
        stats=stats.freeze(
            limit=max_frontier_records,
            action_count=len(schedule.actions),
        ),
    )


def _convolution_dominates(
    left: _ConvolutionRecord,
    right: _ConvolutionRecord,
    sense: Sense,
) -> bool:
    if left.gamma_used > right.gamma_used or left.score_cap < right.score_cap:
        return False
    if not _query_no_worse(left.query, right.query, sense):
        return False
    return (
        left.gamma_used < right.gamma_used
        or left.score_cap > right.score_cap
        or _query_better(left.query, right.query, sense)
    )


def _offer_convolution(
    target: dict[tuple[int, int], _ConvolutionRecord],
    record: _ConvolutionRecord,
    *,
    sense: Sense,
    stats: _MutableConvolutionStats,
) -> None:
    stats.introduced += 1
    key = (record.gamma_used, record.score_cap)
    incumbent = target.get(key)
    if incumbent is None:
        target[key] = record
        stats.accepted += 1
        return
    if _query_better(record.query, incumbent.query, sense) or (
        record.query == incumbent.query
        and _convolution_witness_key(record)
        < _convolution_witness_key(incumbent)
    ):
        target[key] = record
        stats.accepted += 1
        stats.dominance_pruned += 1
    else:
        stats.dominance_pruned += 1


def _prune_convolution(
    records: dict[tuple[int, int], _ConvolutionRecord],
    *,
    sense: Sense,
    stats: _MutableConvolutionStats,
) -> dict[tuple[int, int], _ConvolutionRecord]:
    values = tuple(records.values())
    kept: dict[tuple[int, int], _ConvolutionRecord] = {}
    for index, record in enumerate(values):
        if any(
            _convolution_dominates(other, record, sense)
            for other_index, other in enumerate(values)
            if other_index != index
        ):
            stats.dominance_pruned += 1
        else:
            kept[(record.gamma_used, record.score_cap)] = record
    return kept


def _freeze_component_stats(
    local_results: Sequence[_LocalResult],
    convolution: _MutableConvolutionStats,
    *,
    component_count: int,
    max_frontier_records: int,
) -> ComponentFrontierStats:
    return ComponentFrontierStats(
        component_count=component_count,
        local_action_count=sum(result.stats.action_count for result in local_results),
        local_introduced_states=sum(
            result.stats.introduced_states for result in local_results
        ),
        local_accepted_records=sum(
            result.stats.accepted_records for result in local_results
        ),
        local_dominance_pruned_records=sum(
            result.stats.dominance_pruned_records for result in local_results
        ),
        local_transition_count=sum(
            result.stats.transition_count for result in local_results
        ),
        local_max_single_frontier_records=max(
            (result.stats.peak_live_records for result in local_results),
            default=1,
        ),
        component_terminal_frontier_sizes=tuple(
            len(result.records) for result in local_results
        ),
        convolution_introduced_records=convolution.introduced,
        convolution_accepted_records=convolution.accepted,
        convolution_dominance_pruned_records=convolution.dominance_pruned,
        convolution_transition_count=convolution.transitions,
        convolution_max_single_frontier_records=convolution.max_live_records,
        max_frontier_records=max_frontier_records,
    )


def _global_witness(
    record: _ConvolutionRecord,
    prepared: Any,
    *,
    gamma: int | None,
    score_floor: Fraction | None,
) -> _path.ExactPathWitness:
    shell = _path._Record(
        key=_path._StateKey((), (), (), (), record.gamma_used, record.score_cap),
        query=record.query,
        selected_edges=record.selected_edges,
        assignments=record.assignments,
    )
    witness = _path._final_witness(shell, prepared)
    _path._validate_prepared_witness(
        prepared,
        witness,
        gamma=gamma,
        score_floor=score_floor,
    )
    return witness


def _solve_sense(
    work: tuple[_ComponentWork, ...],
    prepared: Any,
    global_score: Any,
    *,
    sense: Sense,
    gamma: int | None,
    max_frontier_records: int,
) -> ComponentPathSolution:
    local_results: list[_LocalResult] = []
    convolution_stats = _MutableConvolutionStats()
    local_frontiers: list[tuple[Any, ...]] = []
    for component in work:
        local = _run_local_frontier(
            component,
            global_score,
            sense=sense,
            gamma=gamma,
            max_frontier_records=max_frontier_records,
        )
        local_results.append(local)
        if local.status == "EXACT_INFEASIBLE":
            return ComponentPathSolution(
                status="EXACT_INFEASIBLE",
                certified=True,
                objective_value=None,
                witness=None,
                component_witnesses=(),
                stats=_freeze_component_stats(
                    local_results,
                    convolution_stats,
                    component_count=len(work),
                    max_frontier_records=max_frontier_records,
                ),
            )
        local_frontiers.append(local.records)

    initial = _ConvolutionRecord(
        gamma_used=0,
        score_cap=0,
        query=Fraction(0),
        selected_edges=(),
        assignments=(),
        local_records=(),
    )
    frontier = {(0, 0): initial}
    for component_index, local_frontier in enumerate(local_frontiers):
        next_frontier: dict[tuple[int, int], _ConvolutionRecord] = {}
        for prefix in frontier.values():
            for local in local_frontier:
                convolution_stats.transitions += 1
                new_gamma = prefix.gamma_used + local.key.gamma_used
                if gamma is not None and new_gamma > gamma:
                    continue
                candidate = _ConvolutionRecord(
                    gamma_used=new_gamma,
                    score_cap=min(
                        global_score.target,
                        prefix.score_cap + local.key.score_cap,
                    ),
                    query=prefix.query + local.query,
                    selected_edges=prefix.selected_edges + local.selected_edges,
                    assignments=prefix.assignments + local.assignments,
                    local_records=prefix.local_records + (local,),
                )
                _offer_convolution(
                    next_frontier,
                    candidate,
                    sense=sense,
                    stats=convolution_stats,
                )
        frontier = _prune_convolution(
            next_frontier,
            sense=sense,
            stats=convolution_stats,
        )
        convolution_stats.max_live_records = max(
            convolution_stats.max_live_records,
            len(frontier),
        )
        if len(frontier) > max_frontier_records:
            raise ComponentFrontierLimitExceeded(
                phase="convolution",
                component_index=component_index,
                live_records=len(frontier),
                limit=max_frontier_records,
            )
        if not frontier:
            break

    feasible = [
        record
        for record in frontier.values()
        if record.score_cap >= global_score.target
    ]
    stats = _freeze_component_stats(
        local_results,
        convolution_stats,
        component_count=len(work),
        max_frontier_records=max_frontier_records,
    )
    if not feasible:
        return ComponentPathSolution(
            status="EXACT_INFEASIBLE",
            certified=True,
            objective_value=None,
            witness=None,
            component_witnesses=(),
            stats=stats,
        )
    optimum = sorted(
        feasible,
        key=lambda record: (
            record.query if sense == "min" else -record.query,
            _convolution_witness_key(record),
        ),
    )[0]
    witness = _global_witness(
        optimum,
        prepared,
        gamma=gamma,
        score_floor=global_score.floor,
    )
    component_witnesses: list[_path.ExactPathWitness] = []
    for component, local_record in zip(work, optimum.local_records, strict=True):
        local_witness = _path._final_witness(local_record, component.prepared)
        _path._validate_prepared_witness(
            component.prepared,
            local_witness,
            gamma=gamma,
            score_floor=None,
        )
        component_witnesses.append(local_witness)
    return ComponentPathSolution(
        status="EXACT_OPTIMAL",
        certified=True,
        objective_value=optimum.query,
        witness=witness,
        component_witnesses=tuple(component_witnesses),
        stats=stats,
    )


def solve_component_frontier_endpoints(
    problem: _path.ExactPathProblem,
    *,
    forget_order: Sequence[str],
    gamma: int | None = None,
    score_floor: Any | None = None,
    max_frontier_records: int = 1_000_000,
) -> ComponentPathEndpoints:
    """Solve exact attained endpoints by safe component convolution.

    ``forget_order`` must contain every record exactly once.  It is filtered to
    each incidence component, so relative temporal order is preserved while
    unrelated live bags are separated.  ``max_frontier_records`` is enforced
    independently on every local frontier and on every convolution frontier;
    exceeding it raises :class:`ComponentFrontierLimitExceeded` and is never
    returned as an optimum.
    """

    _assert_path_frontier_compatibility()
    prepared = _path._prepare_problem(problem)
    order = tuple(forget_order)
    global_schedule = _path._compile_prepared_path(prepared, order)
    if gamma is not None:
        gamma = _path._nonnegative_integer(gamma, "gamma")
    max_frontier_records = _path._nonnegative_integer(
        max_frontier_records,
        "max_frontier_records",
    )
    if max_frontier_records < 1:
        raise ValueError("max_frontier_records must be at least one")
    score = _path._score_transform(prepared, score_floor)
    components, work = _build_component_work(
        problem,
        prepared,
        order,
    )
    lower_solution = _solve_sense(
        work,
        prepared,
        score,
        sense="min",
        gamma=gamma,
        max_frontier_records=max_frontier_records,
    )
    upper_solution = _solve_sense(
        work,
        prepared,
        score,
        sense="max",
        gamma=gamma,
        max_frontier_records=max_frontier_records,
    )
    if lower_solution.status == "EXACT_INFEASIBLE":
        if upper_solution.status != "EXACT_INFEASIBLE":
            raise AssertionError("decomposed min/max feasibility disagreement")
        return ComponentPathEndpoints(
            status="EXACT_INFEASIBLE",
            certified=True,
            lower=None,
            upper=None,
            lower_solution=lower_solution,
            upper_solution=upper_solution,
            components=components,
            global_schedule=global_schedule,
            component_schedules=tuple(component.schedule for component in work),
            core_node_count=sum(node.role == "core" for node in prepared.nodes),
            score_floor=score.floor,
            score_shift_per_core_incidence=score.shift,
            transformed_score_floor=score.transformed_floor,
            integer_score_scale=score.scale,
            capped_integer_score_target=score.target,
        )
    if upper_solution.status == "EXACT_INFEASIBLE":
        raise AssertionError("decomposed min/max feasibility disagreement")
    return ComponentPathEndpoints(
        status="EXACT_OPTIMAL",
        certified=True,
        lower=lower_solution.objective_value,
        upper=upper_solution.objective_value,
        lower_solution=lower_solution,
        upper_solution=upper_solution,
        components=components,
        global_schedule=global_schedule,
        component_schedules=tuple(component.schedule for component in work),
        core_node_count=sum(node.role == "core" for node in prepared.nodes),
        score_floor=score.floor,
        score_shift_per_core_incidence=score.shift,
        transformed_score_floor=score.transformed_floor,
        integer_score_scale=score.scale,
        capped_integer_score_target=score.target,
    )


__all__ = [
    "PATH_FRONTIER_INTERNAL_API_REVISION",
    "ComponentFrontierLimitExceeded",
    "ComponentFrontierStats",
    "ComponentPathEndpoints",
    "ComponentPathSolution",
    "IncidenceComponent",
    "decompose_incidence_components",
    "solve_component_frontier_endpoints",
]
