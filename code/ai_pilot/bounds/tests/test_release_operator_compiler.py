import sys
import unittest
from dataclasses import replace
from fractions import Fraction
from pathlib import Path


BOUNDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOUNDS_DIR))

from path_frontier_dp import (  # noqa: E402
    CountConstraint,
    EdgeSpec,
    ExactPathProblem,
    NodeSpec,
    solve_path_frontier_endpoints,
    validate_path_witness,
)
from release_operator_compiler import (  # noqa: E402
    CompiledReleaseLabel,
    EndpointRequirement,
    ObservationImplication,
    ReleaseClause,
    ReleaseOperatorSpec,
    ReleaseRowSpec,
    audit_event_lifecycles,
    compile_release_operator,
    paired_hidden_implication,
    paired_visible_implication,
    project_release_witness,
    restore_release_witness,
    two_endpoint_threshold_release_operator,
    validate_release_compilation,
)


class ReleaseOperatorCompilerTests(unittest.TestCase):
    ORIGIN = "declared-origin-endpoint"
    DESTINATION = "declared-destination-endpoint"
    ORIGIN_CELL = ("cell", "origin", "z")
    DESTINATION_CELL = ("cell", "destination", "z")

    @classmethod
    def operator(cls):
        return two_endpoint_threshold_release_operator(
            operator_id="audited-paired-k2-fixture",
            audit_reference="fixture-audit://paired-k2/v1",
            endpoints=(cls.ORIGIN, cls.DESTINATION),
            visible_observation="fixture-published-pair",
            hidden_observation="fixture-withheld-pair",
        )

    @classmethod
    def constraints(cls):
        return (
            CountConstraint(
                cls.ORIGIN_CELL,
                0,
                3,
                low_upper=1,
                high_lower=2,
            ),
            CountConstraint(
                cls.DESTINATION_CELL,
                0,
                3,
                low_upper=1,
                high_lower=2,
            ),
        )

    @classmethod
    def row(cls, observation):
        return ReleaseRowSpec(
            node_id="target",
            observation=observation,
            endpoint_factors_by_label={
                "substantive-z": {
                    cls.ORIGIN: cls.ORIGIN_CELL,
                    cls.DESTINATION: cls.DESTINATION_CELL,
                }
            },
        )

    @classmethod
    def simple_problem(
        cls,
        *,
        origin_history: bool,
        destination_history: bool,
        include_middle: bool = False,
    ):
        nodes = []
        if origin_history:
            nodes.append(
                NodeSpec(
                    "origin_history",
                    "context_only",
                    ("fixed",),
                    factor_contributions={
                        "fixed": {cls.ORIGIN_CELL: 1}
                    },
                )
            )
        if include_middle:
            nodes.append(NodeSpec("unrelated_middle", "context_only", (0,)))
        nodes.append(
            NodeSpec(
                "target",
                "context_only",
                ("substantive-z",),
                label_query={"substantive-z": Fraction(2, 7)},
            )
        )
        if destination_history:
            nodes.append(
                NodeSpec(
                    "destination_history",
                    "context_only",
                    ("fixed",),
                    factor_contributions={
                        "fixed": {cls.DESTINATION_CELL: 1}
                    },
                )
            )
        return ExactPathProblem(tuple(nodes), (), cls.constraints())

    def test_visible_row_compiles_one_two_high_clause(self):
        problem = self.simple_problem(
            origin_history=True,
            destination_history=True,
        )
        compilation = compile_release_operator(
            problem,
            rows=(self.row("fixture-published-pair"),),
            operator=self.operator(),
            forget_order=tuple(node.node_id for node in problem.nodes),
        )
        self.assertTrue(validate_release_compilation(compilation))

        target = next(
            node for node in compilation.problem.nodes if node.node_id == "target"
        )
        self.assertEqual(len(target.label_support), 1)
        self.assertEqual(len(compilation.support_expansions), 1)
        self.assertEqual(compilation.support_expansions[0].dnf_clause_count, 1)
        self.assertEqual(compilation.support_expansions[0].compiled_label_count, 1)
        compiled_label = target.label_support[0]
        self.assertIsInstance(compiled_label, CompiledReleaseLabel)
        self.assertEqual(
            target.factor_requirements[compiled_label],
            {
                self.ORIGIN_CELL: "HIGH",
                self.DESTINATION_CELL: "HIGH",
            },
        )
        result = solve_path_frontier_endpoints(
            compilation.problem, schedule=compilation.schedule
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        self.assertEqual(
            (result.lower, result.upper),
            (Fraction(2, 7), Fraction(2, 7)),
        )
        self.assertEqual(
            set(result.lower_solution.witness.factor_requirements),
            {
                (self.ORIGIN_CELL, "HIGH"),
                (self.DESTINATION_CELL, "HIGH"),
            },
        )

        # A visible row cannot be accepted with only one HIGH endpoint.
        one_high = self.simple_problem(
            origin_history=True,
            destination_history=False,
        )
        one_high_compilation = compile_release_operator(
            one_high,
            rows=(self.row("fixture-published-pair"),),
            operator=self.operator(),
            forget_order=tuple(node.node_id for node in one_high.nodes),
        )
        one_high_result = solve_path_frontier_endpoints(
            one_high_compilation.problem,
            schedule=one_high_compilation.schedule,
        )
        self.assertEqual(one_high_result.status, "EXACT_INFEASIBLE")

    def test_hidden_low_or_low_branch_and_exact_witness_round_trip(self):
        # Origin count is one (LOW); destination count is two (HIGH).  A
        # simultaneous LOW/LOW encoding would reject this feasible row.
        problem = self.simple_problem(
            origin_history=False,
            destination_history=True,
        )
        compilation = compile_release_operator(
            problem,
            rows=(self.row("fixture-withheld-pair"),),
            operator=self.operator(),
            forget_order=tuple(node.node_id for node in problem.nodes),
        )
        target = next(
            node for node in compilation.problem.nodes if node.node_id == "target"
        )
        self.assertEqual(len(target.label_support), 2)
        self.assertEqual(compilation.support_expansions[0].dnf_clause_count, 2)
        self.assertEqual(compilation.support_expansions[0].compiled_label_count, 2)
        requirements = {
            tuple(mapping.items())
            for mapping in target.factor_requirements.values()
        }
        self.assertEqual(
            requirements,
            {
                ((self.ORIGIN_CELL, "LOW"),),
                ((self.DESTINATION_CELL, "LOW"),),
            },
        )

        result = solve_path_frontier_endpoints(
            compilation.problem, schedule=compilation.schedule
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        witness = result.lower_solution.witness
        self.assertTrue(validate_path_witness(compilation.problem, witness))
        assigned = dict(witness.label_assignments)["target"]
        self.assertEqual(assigned.alternative_index, 0)

        projected = project_release_witness(compilation, witness)
        self.assertEqual(
            dict(projected.substantive_witness.label_assignments)["target"],
            "substantive-z",
        )
        self.assertEqual(
            projected.row_witnesses[0].endpoint_requirements,
            ((self.ORIGIN, self.ORIGIN_CELL, "LOW"),),
        )
        restored = restore_release_witness(compilation, projected)
        self.assertEqual(restored, witness)

        bad_branch = replace(projected.row_witnesses[0], clause_id="tampered")
        tampered = replace(projected, row_witnesses=(bad_branch,))
        with self.assertRaisesRegex(ValueError, "(clause|release evidence) fails"):
            restore_release_witness(compilation, tampered)

        # Once both cells are HIGH, neither disjunct supplies a LOW witness.
        both_high = self.simple_problem(
            origin_history=True,
            destination_history=True,
        )
        both_high_compilation = compile_release_operator(
            both_high,
            rows=(self.row("fixture-withheld-pair"),),
            operator=self.operator(),
            forget_order=tuple(node.node_id for node in both_high.nodes),
        )
        both_high_result = solve_path_frontier_endpoints(
            both_high_compilation.problem,
            schedule=both_high_compilation.schedule,
        )
        self.assertEqual(both_high_result.status, "EXACT_INFEASIBLE")

    def test_paired_operator_exhaustive_high_low_truth_table(self):
        observations = (
            (
                "fixture-published-pair",
                lambda origin, destination: origin and destination,
            ),
            (
                "fixture-withheld-pair",
                lambda origin, destination: not (origin and destination),
            ),
        )
        for observation, expected in observations:
            for origin_high in (False, True):
                for destination_high in (False, True):
                    with self.subTest(
                        observation=observation,
                        origin_high=origin_high,
                        destination_high=destination_high,
                    ):
                        problem = self.simple_problem(
                            origin_history=origin_high,
                            destination_history=destination_high,
                        )
                        compilation = compile_release_operator(
                            problem,
                            rows=(self.row(observation),),
                            operator=self.operator(),
                            forget_order=tuple(
                                node.node_id for node in problem.nodes
                            ),
                        )
                        result = solve_path_frontier_endpoints(
                            compilation.problem,
                            schedule=compilation.schedule,
                        )
                        expected_status = (
                            "EXACT_OPTIMAL"
                            if expected(origin_high, destination_high)
                            else "EXACT_INFEASIBLE"
                        )
                        self.assertEqual(result.status, expected_status)
                        if (
                            observation == "fixture-withheld-pair"
                            and origin_high
                            and not destination_high
                        ):
                            projected = project_release_witness(
                                compilation, result.lower_solution.witness
                            )
                            self.assertEqual(
                                projected.row_witnesses[0].alternative_index,
                                1,
                            )
                            self.assertEqual(
                                projected.row_witnesses[0].endpoint_requirements,
                                (
                                    (
                                        self.DESTINATION,
                                        self.DESTINATION_CELL,
                                        "LOW",
                                    ),
                                ),
                            )
                            self.assertEqual(
                                restore_release_witness(
                                    compilation, projected
                                ),
                                result.lower_solution.witness,
                            )

    def test_pair_dependent_edges_are_lifted_across_release_witnesses(self):
        origin_red = ("origin", "red")
        destination_red = ("destination", "red")
        origin_blue = ("origin", "blue")
        destination_blue = ("destination", "blue")
        constraints = tuple(
            CountConstraint(factor, 0, 2, low_upper=1, high_lower=2)
            for factor in (
                origin_red,
                destination_red,
                origin_blue,
                destination_blue,
            )
        )
        problem = ExactPathProblem(
            nodes=(
                NodeSpec(
                    "a",
                    "core",
                    ("red", "blue"),
                    label_query={"red": Fraction(1, 7), "blue": 0},
                ),
                NodeSpec("b", "core", ("partner",)),
            ),
            edges=(
                EdgeSpec(
                    "ab",
                    "a",
                    "b",
                    allowed_label_pairs=(("red", "partner"),),
                    score_by_label_pair={
                        ("red", "partner"): Fraction(3, 2)
                    },
                    query_by_label_pair={
                        ("red", "partner"): Fraction(5, 7)
                    },
                ),
            ),
            count_constraints=constraints,
        )
        row = ReleaseRowSpec(
            "a",
            "fixture-withheld-pair",
            {
                "red": {
                    self.ORIGIN: origin_red,
                    self.DESTINATION: destination_red,
                },
                "blue": {
                    self.ORIGIN: origin_blue,
                    self.DESTINATION: destination_blue,
                },
            },
        )
        compilation = compile_release_operator(
            problem,
            rows=(row,),
            operator=self.operator(),
            forget_order=("a", "b"),
        )
        lifted_edge = compilation.problem.edges[0]
        self.assertEqual(
            [item.dnf_clause_count for item in compilation.support_expansions],
            [2, 2],
        )
        self.assertEqual(
            sum(
                item.compiled_label_count
                for item in compilation.support_expansions
            ),
            4,
        )
        self.assertEqual(len(lifted_edge.allowed_label_pairs), 2)
        self.assertEqual(
            set(lifted_edge.score_by_label_pair.values()), {Fraction(3, 2)}
        )
        self.assertEqual(
            set(lifted_edge.query_by_label_pair.values()), {Fraction(5, 7)}
        )
        result = solve_path_frontier_endpoints(
            compilation.problem,
            schedule=compilation.schedule,
            score_floor=3,
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        self.assertEqual(
            (result.lower, result.upper),
            (Fraction(6, 7), Fraction(6, 7)),
        )
        projected = project_release_witness(
            compilation, result.lower_solution.witness, score_floor=3
        )
        self.assertEqual(
            dict(projected.substantive_witness.label_assignments)["a"],
            "red",
        )
        self.assertEqual(
            restore_release_witness(
                compilation, projected, score_floor=3
            ),
            result.lower_solution.witness,
        )

    def test_single_empty_clause_is_true_but_still_contributes_counts(self):
        unrestricted = ReleaseOperatorSpec(
            operator_id="audited-unrestricted-fixture",
            audit_reference="fixture-audit://unrestricted/v1",
            endpoints=(self.ORIGIN, self.DESTINATION),
            implications=(
                ObservationImplication(
                    "audited-no-release-restriction",
                    (ReleaseClause("true", ()),),
                ),
            ),
        )
        problem = self.simple_problem(
            origin_history=False,
            destination_history=False,
        )
        row = self.row("audited-no-release-restriction")
        compilation = compile_release_operator(
            problem,
            rows=(row,),
            operator=unrestricted,
            forget_order=("target",),
        )
        target = compilation.problem.nodes[0]
        compiled_label = target.label_support[0]
        self.assertEqual(target.factor_requirements[compiled_label], {})
        self.assertEqual(
            target.factor_contributions[compiled_label],
            {self.ORIGIN_CELL: 1, self.DESTINATION_CELL: 1},
        )
        result = solve_path_frontier_endpoints(
            compilation.problem, schedule=compilation.schedule
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        self.assertEqual(result.lower_solution.witness.factor_requirements, ())
        self.assertEqual(
            dict(result.lower_solution.witness.factor_counts),
            {self.ORIGIN_CELL: 1, self.DESTINATION_CELL: 1},
        )

    def test_lifecycle_audit_spans_gaps_and_rejects_corrupt_events(self):
        problem = self.simple_problem(
            origin_history=True,
            destination_history=True,
            include_middle=True,
        )
        compilation = compile_release_operator(
            problem,
            rows=(self.row("fixture-published-pair"),),
            operator=self.operator(),
            forget_order=tuple(node.node_id for node in problem.nodes),
        )
        factors = {
            lifecycle.factor: lifecycle
            for lifecycle in compilation.lifecycle_audit.factor_lifecycles
        }
        origin = factors[self.ORIGIN_CELL]
        self.assertEqual(
            origin.scoped_node_ids, ("origin_history", "target")
        )
        self.assertEqual(
            tuple(origin.active_action_range),
            tuple(
                range(origin.open_action_index, origin.finalize_action_index + 1)
            ),
        )
        unrelated_introduction = next(
            index
            for index, action in enumerate(compilation.schedule.actions)
            if action.kind == "introduce_node"
            and action.item_id == "unrelated_middle"
        )
        self.assertIn(unrelated_introduction, origin.active_action_range)
        self.assertNotIn(unrelated_introduction, origin.touch_action_indices)
        self.assertEqual(compilation.schedule.max_active_factor_count, 2)

        wrong_width = replace(
            compilation.schedule,
            max_active_factor_count=1,
        )
        with self.assertRaisesRegex(ValueError, "active_factor_count"):
            audit_event_lifecycles(compilation.problem, wrong_width)

        broken_origin = replace(
            origin,
            active_action_range=range(
                origin.open_action_index, origin.open_action_index + 1
            ),
        )
        broken_lifecycles = tuple(
            broken_origin if item.factor == self.ORIGIN_CELL else item
            for item in compilation.lifecycle_audit.factor_lifecycles
        )
        broken_audit = replace(
            compilation.lifecycle_audit,
            factor_lifecycles=broken_lifecycles,
        )
        with self.assertRaisesRegex(ValueError, "lifecycle audit"):
            validate_release_compilation(
                replace(compilation, lifecycle_audit=broken_audit)
            )

        # Edge events are independently checked to occur inside both endpoint
        # node lifetimes, rather than trusted because telemetry looks right.
        edge_compilation = self._edge_lifecycle_compilation()
        actions = list(edge_compilation.schedule.actions)
        edge_index = next(
            index
            for index, action in enumerate(actions)
            if action.kind == "introduce_edge"
        )
        forget_a_index = next(
            index
            for index, action in enumerate(actions)
            if action.kind == "forget_node" and action.item_id == "a"
        )
        actions[edge_index], actions[forget_a_index] = (
            actions[forget_a_index],
            actions[edge_index],
        )
        broken_schedule = replace(
            edge_compilation.schedule, actions=tuple(actions)
        )
        with self.assertRaisesRegex(ValueError, "both endpoints are active"):
            audit_event_lifecycles(
                edge_compilation.problem, broken_schedule
            )

    def test_explicit_zero_is_not_a_factor_touch_and_maps_are_detached(self):
        factor = "zero-only-factor"
        mutable_query = {0: 1}
        mutable_contributions = {0: {factor: 0}}
        problem = ExactPathProblem(
            nodes=(
                NodeSpec(
                    "zero",
                    "context_only",
                    (0,),
                    factor_contributions=mutable_contributions,
                    label_query=mutable_query,
                ),
            ),
            edges=(),
            count_constraints=(CountConstraint(factor, 0, 0),),
        )
        compilation = compile_release_operator(
            problem,
            rows=(),
            operator=self.operator(),
            forget_order=("zero",),
        )
        self.assertEqual(compilation.schedule.max_active_factor_count, 0)
        lifecycle = compilation.lifecycle_audit.factor_lifecycles[0]
        self.assertEqual(lifecycle.touch_action_indices, ())
        self.assertEqual(lifecycle.active_action_range, range(0))
        result = solve_path_frontier_endpoints(
            compilation.problem, schedule=compilation.schedule
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")

        # Source and compiled declarations must not share mutable nested maps;
        # otherwise replay validation could not detect post-compile changes.
        mutable_query[0] = 999
        mutable_contributions[0][factor] = 1
        self.assertEqual(compilation.problem.nodes[0].label_query[0], 1)
        self.assertEqual(
            compilation.problem.nodes[0].factor_contributions[0][factor], 0
        )
        with self.assertRaisesRegex(ValueError, "compiled problem does not replay"):
            validate_release_compilation(compilation)

    def _edge_lifecycle_compilation(self):
        problem = ExactPathProblem(
            nodes=(
                NodeSpec("a", "core", (0,)),
                NodeSpec("b", "core", (0,)),
            ),
            edges=(EdgeSpec("ab", "a", "b"),),
        )
        return compile_release_operator(
            problem,
            rows=(),
            operator=self.operator(),
            forget_order=("a", "b"),
        )

    def test_configuration_requires_provenance_and_exact_row_bindings(self):
        visible = paired_visible_implication(
            observation="shown",
            endpoints=(self.ORIGIN, self.DESTINATION),
        )
        hidden = paired_hidden_implication(
            observation="not-shown",
            endpoints=(self.ORIGIN, self.DESTINATION),
        )
        self.assertEqual(len(visible.alternatives), 1)
        self.assertEqual(len(hidden.alternatives), 2)

        with self.assertRaisesRegex(ValueError, "audit_reference"):
            two_endpoint_threshold_release_operator(
                operator_id="operator",
                audit_reference=" ",
                endpoints=(self.ORIGIN, self.DESTINATION),
                visible_observation="shown",
                hidden_observation="not-shown",
            )

        problem = self.simple_problem(
            origin_history=False,
            destination_history=False,
        )
        unknown_observation = replace(
            self.row("fixture-withheld-pair"), observation="not-declared"
        )
        with self.assertRaisesRegex(ValueError, "undeclared observation"):
            compile_release_operator(
                problem,
                rows=(unknown_observation,),
                operator=self.operator(),
                forget_order=("target",),
            )

        contradictory = ReleaseOperatorSpec(
            operator_id="contradictory-fixture",
            audit_reference="fixture-audit://contradiction",
            endpoints=(self.ORIGIN, self.DESTINATION),
            implications=(
                ObservationImplication(
                    "contradictory",
                    (
                        ReleaseClause(
                            "bad-clause",
                            (
                                EndpointRequirement(self.ORIGIN, "LOW"),
                                EndpointRequirement(self.ORIGIN, "HIGH"),
                            ),
                        ),
                    ),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "contradictory LOW/HIGH"):
            compile_release_operator(
                problem,
                rows=(),
                operator=contradictory,
                forget_order=("target",),
            )

        redundant_true = ReleaseOperatorSpec(
            operator_id="redundant-true-fixture",
            audit_reference="fixture-audit://redundant-true",
            endpoints=(self.ORIGIN, self.DESTINATION),
            implications=(
                ObservationImplication(
                    "redundant",
                    (
                        ReleaseClause("true", ()),
                        ReleaseClause(
                            "also-low",
                            (EndpointRequirement(self.ORIGIN, "LOW"),),
                        ),
                    ),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "empty TRUE clause"):
            compile_release_operator(
                problem,
                rows=(),
                operator=redundant_true,
                forget_order=("target",),
            )

        missing_endpoint = ReleaseRowSpec(
            "target",
            "fixture-withheld-pair",
            {
                "substantive-z": {
                    self.ORIGIN: self.ORIGIN_CELL,
                }
            },
        )
        with self.assertRaisesRegex(ValueError, "exactly the declared"):
            compile_release_operator(
                problem,
                rows=(missing_endpoint,),
                operator=self.operator(),
                forget_order=("target",),
            )


if __name__ == "__main__":
    unittest.main()
