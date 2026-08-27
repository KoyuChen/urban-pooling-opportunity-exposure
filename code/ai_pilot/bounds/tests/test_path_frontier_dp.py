import itertools
import random
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
    FrontierLimitExceeded,
    NicePathAction,
    NodeSpec,
    PathSchedule,
    compile_temporal_path,
    solve_path_frontier_endpoints,
    solve_path_frontier_outward_relaxation,
    validate_path_witness,
)


class ExactPathFrontierTests(unittest.TestCase):
    @staticmethod
    def four_cycle_problem(*, omitted_cross=False):
        nodes = tuple(
            NodeSpec(node_id, "core", ("L",))
            for node_id in ("a", "b", "c", "d")
        )
        edges = (
            EdgeSpec("ab", "a", "b", query=Fraction(1, 3), score=-1),
            EdgeSpec("cd", "c", "d", query=Fraction(2, 5), score=-1),
            EdgeSpec(
                "ac",
                "a",
                "c",
                query=Fraction(-1, 7),
                score=Fraction(1, 2),
                omitted=omitted_cross,
            ),
            EdgeSpec(
                "bd",
                "b",
                "d",
                query=Fraction(1, 7),
                score=Fraction(1, 2),
                omitted=omitted_cross,
            ),
        )
        return ExactPathProblem(nodes, edges)

    def test_exact_fraction_endpoints_witnesses_and_score_shift(self):
        problem = self.four_cycle_problem()
        result = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "b", "c", "d"),
            score_floor=0,
        )
        # ab+cd has raw score -4; ac+bd has raw score 2 and is retained.
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        self.assertEqual((result.lower, result.upper), (Fraction(0), Fraction(0)))
        self.assertEqual(result.score_shift_per_core_incidence, Fraction(1))
        self.assertEqual(result.transformed_score_floor, Fraction(4))
        self.assertEqual(result.integer_score_scale, 2)
        self.assertEqual(result.capped_integer_score_target, 8)
        for solution in (result.lower_solution, result.upper_solution):
            self.assertEqual(set(solution.witness.selected_edge_ids), {"ac", "bd"})
            self.assertEqual(solution.witness.raw_score, Fraction(2))
            self.assertTrue(
                validate_path_witness(problem, solution.witness, score_floor=0)
            )

    def test_core_incidence_shift_is_safe_when_edge_cardinality_varies(self):
        problem = ExactPathProblem(
            nodes=(
                NodeSpec("a", "core", (0,)),
                NodeSpec("b", "core", (0,)),
                NodeSpec("x", "buffer", (0,)),
                NodeSpec("y", "buffer", (0,)),
            ),
            edges=(
                # One selected edge, two core incidences: raw score -4.
                EdgeSpec("ab", "a", "b", score=-2, query=0),
                # Two selected edges, one core incidence each: raw score -2.
                EdgeSpec("ax", "a", "x", score=-1, query=1),
                EdgeSpec("by", "b", "y", score=-1, query=1),
            ),
        )
        result = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "x", "b", "y"),
            score_floor=-3,
        )
        self.assertEqual((result.lower, result.upper), (Fraction(2), Fraction(2)))
        self.assertEqual(result.score_shift_per_core_incidence, Fraction(2))
        self.assertEqual(result.transformed_score_floor, Fraction(1))
        self.assertEqual(
            set(result.lower_solution.witness.selected_edge_ids), {"ax", "by"}
        )
        self.assertEqual(result.lower_solution.witness.raw_score, Fraction(-2))

    def test_gamma_is_one_global_selected_omitted_edge_budget(self):
        problem = self.four_cycle_problem(omitted_cross=True)
        gamma_zero = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "b", "c", "d"),
            gamma=0,
        )
        gamma_one = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "b", "c", "d"),
            gamma=1,
        )
        gamma_two = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "b", "c", "d"),
            gamma=2,
        )
        flat_value = Fraction(11, 15)
        self.assertEqual((gamma_zero.lower, gamma_zero.upper), (flat_value, flat_value))
        self.assertEqual((gamma_one.lower, gamma_one.upper), (flat_value, flat_value))
        self.assertEqual((gamma_two.lower, gamma_two.upper), (Fraction(0), flat_value))
        self.assertEqual(gamma_two.lower_solution.witness.omitted_edge_count, 2)

    def test_multiple_endpoint_factors_and_paired_suppression_or_compilation(self):
        pickup = ("pickup", "cell")
        dropoff = ("dropoff", "cell")
        visible = ("visible", None)
        hidden_pickup_witness = ("hidden", "pickup_low")
        hidden_dropoff_witness = ("hidden", "dropoff_low")
        target = NodeSpec(
            "target",
            "context_only",
            (visible, hidden_pickup_witness, hidden_dropoff_witness),
            factor_contributions={
                visible: {pickup: 1, dropoff: 1},
                hidden_pickup_witness: {pickup: 1, dropoff: 1},
                hidden_dropoff_witness: {pickup: 1, dropoff: 1},
            },
            factor_requirements={
                visible: {pickup: "HIGH", dropoff: "HIGH"},
                # Hidden is pickup-LOW OR dropoff-LOW, compiled as duplicate labels.
                hidden_pickup_witness: {pickup: "LOW"},
                hidden_dropoff_witness: {dropoff: "LOW"},
            },
            label_query={
                visible: 1,
                hidden_pickup_witness: 0,
                hidden_dropoff_witness: 0,
            },
        )
        hidden_target = NodeSpec(
            "target",
            "context_only",
            (hidden_pickup_witness, hidden_dropoff_witness),
            factor_contributions={
                hidden_pickup_witness: {pickup: 1, dropoff: 1},
                hidden_dropoff_witness: {pickup: 1, dropoff: 1},
            },
            factor_requirements={
                hidden_pickup_witness: {pickup: "LOW"},
                hidden_dropoff_witness: {dropoff: "LOW"},
            },
        )
        counts = (
            CountConstraint(pickup, 0, 3, low_upper=1, high_lower=2),
            CountConstraint(dropoff, 0, 3, low_upper=1, high_lower=2),
        )

        # Both cells have count two.  The hidden row has no valid LOW witness.
        both_high = ExactPathProblem(
            nodes=(
                NodeSpec(
                    "p_history",
                    "context_only",
                    ("fixed",),
                    factor_contributions={"fixed": {pickup: 1}},
                ),
                target,
                NodeSpec(
                    "d_history",
                    "context_only",
                    ("fixed",),
                    factor_contributions={"fixed": {dropoff: 1}},
                ),
            ),
            edges=(),
            count_constraints=counts,
        )
        high_result = solve_path_frontier_endpoints(
            both_high,
            forget_order=("p_history", "target", "d_history"),
        )
        self.assertEqual((high_result.lower, high_result.upper), (Fraction(1), Fraction(1)))
        self.assertEqual(
            dict(high_result.lower_solution.witness.label_assignments)["target"],
            visible,
        )

        # Conditioning on an actually hidden row removes the visible label.
        # With both endpoint cells HIGH, neither disjunctive LOW witness exists.
        both_high_hidden = ExactPathProblem(
            nodes=(both_high.nodes[0], hidden_target, both_high.nodes[2]),
            edges=(),
            count_constraints=counts,
        )
        hidden_high_result = solve_path_frontier_endpoints(
            both_high_hidden,
            forget_order=("p_history", "target", "d_history"),
        )
        self.assertEqual(hidden_high_result.status, "EXACT_INFEASIBLE")

        # Pickup now has count one and drop-off count two.  Only the duplicated
        # pickup-LOW hidden witness is feasible, proving OR rather than AND.
        pickup_low = ExactPathProblem(
            nodes=(hidden_target, both_high.nodes[2]),
            edges=(),
            count_constraints=counts,
        )
        low_result = solve_path_frontier_endpoints(
            pickup_low,
            forget_order=("target", "d_history"),
        )
        self.assertEqual((low_result.lower, low_result.upper), (Fraction(0), Fraction(0)))
        self.assertEqual(
            dict(low_result.lower_solution.witness.label_assignments)["target"],
            hidden_pickup_witness,
        )
        self.assertIn(
            (pickup, "LOW"),
            low_result.lower_solution.witness.factor_requirements,
        )

    def test_requirement_only_node_extends_factor_scope_until_resolved(self):
        factor = "release_cell"
        problem = ExactPathProblem(
            nodes=(
                NodeSpec(
                    "c1",
                    "context_only",
                    (0,),
                    factor_contributions={0: {factor: 1}},
                ),
                NodeSpec(
                    "c2",
                    "context_only",
                    (0,),
                    factor_contributions={0: {factor: 1}},
                ),
                NodeSpec(
                    "late_requirement",
                    "context_only",
                    (0,),
                    factor_requirements={0: {factor: "LOW"}},
                ),
            ),
            edges=(),
            count_constraints=(
                CountConstraint(factor, 0, 3, low_upper=1, high_lower=2),
            ),
        )
        schedule = compile_temporal_path(
            problem, ("c1", "c2", "late_requirement")
        )
        self.assertEqual(schedule.max_active_factor_count, 1)
        result = solve_path_frontier_endpoints(problem, schedule=schedule)
        self.assertEqual(result.status, "EXACT_INFEASIBLE")

    def test_disjoint_local_factors_are_finalized_not_multiplied(self):
        q = 16
        nodes = []
        constraints = []
        order = []
        for index in range(q):
            node_id = f"n{index:02d}"
            factor = ("local", index)
            order.append(node_id)
            nodes.append(
                NodeSpec(
                    node_id,
                    "context_only",
                    (0, 1),
                    factor_contributions={0: {}, 1: {factor: 1}},
                    label_query={0: 0, 1: 1},
                )
            )
            constraints.append(CountConstraint(factor, 0, 1))
        problem = ExactPathProblem(tuple(nodes), (), tuple(constraints))
        schedule = compile_temporal_path(problem, order)
        self.assertEqual(schedule.max_bag_size, 1)
        self.assertEqual(schedule.max_active_factor_count, 1)
        result = solve_path_frontier_endpoints(problem, schedule=schedule)
        self.assertEqual((result.lower, result.upper), (Fraction(0), Fraction(q)))
        # The current context label remains live until the immediately following
        # forget action, so the peak is two rather than one; it is independent q.
        self.assertEqual(result.lower_solution.stats.peak_live_records, 2)
        self.assertEqual(result.upper_solution.stats.peak_live_records, 2)
        self.assertLessEqual(result.lower_solution.stats.transition_count, 4 * q)
        self.assertLessEqual(result.upper_solution.stats.transition_count, 4 * q)

    def test_threshold_count_is_capped_and_ordinary_upper_overflow_is_not(self):
        factor = "threshold_cell"
        optional_nodes = tuple(
            NodeSpec(
                f"c{index}",
                "context_only",
                (0, 1),
                factor_contributions={0: {}, 1: {factor: 1}},
            )
            for index in range(8)
        )
        requirement = NodeSpec(
            "release",
            "context_only",
            ("visible",),
            factor_requirements={"visible": {factor: "HIGH"}},
        )
        threshold_problem = ExactPathProblem(
            nodes=optional_nodes + (requirement,),
            edges=(),
            count_constraints=(
                CountConstraint(factor, 0, 8, low_upper=1, high_lower=2),
            ),
        )
        order = tuple(node.node_id for node in threshold_problem.nodes)
        schedule = compile_temporal_path(threshold_problem, order)
        # Counts 2,3,...,8 are decision-equivalent and share state q=2.
        self.assertEqual(schedule.factor_count_caps, ((factor, 2),))
        threshold_result = solve_path_frontier_endpoints(
            threshold_problem, schedule=schedule
        )
        self.assertEqual(threshold_result.status, "EXACT_OPTIMAL")
        self.assertGreaterEqual(
            dict(threshold_result.lower_solution.witness.factor_counts)[factor],
            2,
        )

        overflow_problem = ExactPathProblem(
            nodes=(
                NodeSpec(
                    "x",
                    "context_only",
                    (0,),
                    factor_contributions={0: {factor: 1}},
                ),
                NodeSpec(
                    "y",
                    "context_only",
                    (0,),
                    factor_contributions={0: {factor: 1}},
                ),
            ),
            edges=(),
            count_constraints=(CountConstraint(factor, 0, 1),),
        )
        overflow_schedule = compile_temporal_path(overflow_problem, ("x", "y"))
        # upper+1 is preserved as a distinct overflow state and then rejected.
        self.assertEqual(overflow_schedule.factor_count_caps, ((factor, 2),))
        overflow_result = solve_path_frontier_endpoints(
            overflow_problem, schedule=overflow_schedule
        )
        self.assertEqual(overflow_result.status, "EXACT_INFEASIBLE")

    def test_context_counts_core_buffer_matching_and_node_query(self):
        factor = "known"
        problem = ExactPathProblem(
            nodes=(
                NodeSpec("a", "core", ("A",), label_query={"A": Fraction(1, 9)}),
                NodeSpec("b", "core", ("B",)),
                NodeSpec("x", "buffer", ("A",)),
                NodeSpec("y", "buffer", ("B",)),
                NodeSpec(
                    "history",
                    "context_only",
                    ("H",),
                    factor_contributions={"H": {factor: 1}},
                ),
            ),
            edges=(
                EdgeSpec("ax", "a", "x", query=Fraction(2, 9)),
                EdgeSpec("by", "b", "y", query=Fraction(1, 3)),
            ),
            count_constraints=(CountConstraint(factor, 1, 1),),
        )
        result = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "x", "b", "y", "history"),
        )
        self.assertEqual((result.lower, result.upper), (Fraction(2, 3), Fraction(2, 3)))
        witness = result.lower_solution.witness
        self.assertEqual(set(witness.selected_edge_ids), {"ax", "by"})
        self.assertEqual(witness.factor_counts, ((factor, 1),))

    def test_label_pair_specific_score_and_query(self):
        pairs = (("A", "A"), ("A", "B"), ("B", "A"), ("B", "B"))
        problem = ExactPathProblem(
            nodes=(
                NodeSpec("a", "core", ("A", "B")),
                NodeSpec("b", "core", ("A", "B")),
            ),
            edges=(
                EdgeSpec(
                    "ab",
                    "a",
                    "b",
                    allowed_label_pairs=pairs,
                    score_by_label_pair={
                        ("A", "A"): 1,
                        ("A", "B"): 0,
                        ("B", "A"): 0,
                        ("B", "B"): 2,
                    },
                    query_by_label_pair={
                        ("A", "A"): Fraction(1, 5),
                        ("A", "B"): Fraction(-1, 5),
                        ("B", "A"): Fraction(-2, 5),
                        ("B", "B"): Fraction(3, 5),
                    },
                ),
            ),
        )
        result = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "b"),
            score_floor=2,
        )
        # Scores are per core incidence: A,A totals 2 and B,B totals 4.
        self.assertEqual((result.lower, result.upper), (Fraction(1, 5), Fraction(3, 5)))
        self.assertEqual(
            dict(result.lower_solution.witness.label_assignments),
            {"a": "A", "b": "A"},
        )

    def test_schedule_validation_frontier_limit_and_threshold_partition(self):
        problem = ExactPathProblem(
            nodes=(NodeSpec("a", "core", (0, 1)), NodeSpec("b", "core", (0, 1))),
            edges=(EdgeSpec("ab", "a", "b"),),
        )
        with self.assertRaises(FrontierLimitExceeded):
            solve_path_frontier_endpoints(
                problem,
                forget_order=("a", "b"),
                max_frontier_records=1,
            )
        schedule = compile_temporal_path(problem, ("a", "b"))
        invalid = PathSchedule(
            actions=schedule.actions[:-1],
            forget_order=schedule.forget_order,
            max_bag_size=schedule.max_bag_size,
            max_active_factor_count=schedule.max_active_factor_count,
            factor_count_caps=schedule.factor_count_caps,
        )
        with self.assertRaisesRegex(ValueError, "forget every"):
            solve_path_frontier_endpoints(problem, schedule=invalid)
        bad_threshold = ExactPathProblem(
            nodes=(NodeSpec("c", "context_only", (0,)),),
            edges=(),
            count_constraints=(
                CountConstraint("f", 0, 5, low_upper=3, high_lower=3),
            ),
        )
        with self.assertRaisesRegex(ValueError, "strict partition"):
            compile_temporal_path(bad_threshold, ("c",))

    def test_external_witness_is_recomputed_not_trusted(self):
        problem = self.four_cycle_problem()
        result = solve_path_frontier_endpoints(
            problem, forget_order=("a", "b", "c", "d")
        )
        witness = result.lower_solution.witness
        bad = replace(witness, raw_score=witness.raw_score + 1)
        with self.assertRaisesRegex(ValueError, "raw score"):
            validate_path_witness(problem, bad)

    def test_path_order_reports_actual_live_bag(self):
        n = 12
        nodes = tuple(NodeSpec(str(index), "core", (0,)) for index in range(n))
        # Consecutive disjoint edges give a perfect matching and width one.
        edges = tuple(
            EdgeSpec(f"e{index}", str(index), str(index + 1))
            for index in range(0, n, 2)
        )
        problem = ExactPathProblem(nodes, edges)
        schedule = compile_temporal_path(problem, tuple(str(i) for i in range(n)))
        self.assertEqual(schedule.max_bag_size, 2)
        self.assertEqual(schedule.schedule_width, 1)
        result = solve_path_frontier_endpoints(problem, schedule=schedule)
        self.assertEqual(result.status, "EXACT_OPTIMAL")

    @staticmethod
    def _brute_four_core(problem, *, gamma, score_floor):
        nodes = tuple(problem.nodes)
        edges = tuple(problem.edges)
        values = []
        for labels_tuple in itertools.product(*(node.label_support for node in nodes)):
            labels = {
                node.node_id: label for node, label in zip(nodes, labels_tuple)
            }
            node_query = sum(
                (
                    Fraction(node.label_query.get(labels[node.node_id], 0))
                    if node.label_query
                    else Fraction(0)
                )
                for node in nodes
            )
            for selected in itertools.combinations(edges, 2):
                degrees = {node.node_id: 0 for node in nodes}
                omitted = 0
                raw_score = Fraction(0)
                query = node_query
                feasible = True
                for edge in selected:
                    pair = (labels[edge.u], labels[edge.v])
                    allowed = (
                        set(edge.allowed_label_pairs)
                        if edge.allowed_label_pairs is not None
                        else None
                    )
                    if allowed is not None and pair not in allowed:
                        feasible = False
                        break
                    degrees[edge.u] += 1
                    degrees[edge.v] += 1
                    omitted += int(edge.omitted)
                    score = (
                        edge.score_by_label_pair[pair]
                        if edge.score_by_label_pair is not None
                        else edge.score
                    )
                    contribution = (
                        edge.query_by_label_pair[pair]
                        if edge.query_by_label_pair is not None
                        else edge.query
                    )
                    raw_score += 2 * Fraction(score)
                    query += Fraction(contribution)
                if not feasible or any(degrees[node.node_id] != 1 for node in nodes):
                    continue
                if gamma is not None and omitted > gamma:
                    continue
                if score_floor is not None and raw_score < score_floor:
                    continue
                values.append(query)
        if not values:
            return None
        return min(values), max(values)

    def test_random_tiny_instances_match_brute_force_exactly(self):
        rng = random.Random(20260827)
        labels = (0, 1)
        complete_edges = (
            ("ab", "a", "b"),
            ("ac", "a", "c"),
            ("ad", "a", "d"),
            ("bc", "b", "c"),
            ("bd", "b", "d"),
            ("cd", "c", "d"),
        )
        for replicate in range(80):
            nodes = tuple(
                NodeSpec(
                    node_id,
                    "core",
                    labels,
                    label_query={0: 0, 1: Fraction(rng.randint(-2, 2), 3)},
                )
                for node_id in ("a", "b", "c", "d")
            )
            edges = []
            for edge_id, u, v in complete_edges:
                allowed = tuple(
                    pair
                    for pair in itertools.product(labels, labels)
                    if rng.random() < 0.75
                )
                if not allowed:
                    allowed = ((rng.choice(labels), rng.choice(labels)),)
                scores = {pair: rng.randint(-2, 2) for pair in allowed}
                queries = {
                    pair: Fraction(rng.randint(-4, 4), 5) for pair in allowed
                }
                edges.append(
                    EdgeSpec(
                        edge_id,
                        u,
                        v,
                        omitted=rng.random() < 0.3,
                        allowed_label_pairs=allowed,
                        score_by_label_pair=scores,
                        query_by_label_pair=queries,
                    )
                )
            problem = ExactPathProblem(nodes, tuple(edges))
            gamma = rng.choice((None, 0, 1, 2))
            score_floor = Fraction(rng.randint(-5, 5))
            expected = self._brute_four_core(
                problem, gamma=gamma, score_floor=score_floor
            )
            result = solve_path_frontier_endpoints(
                problem,
                forget_order=("a", "b", "c", "d"),
                gamma=gamma,
                score_floor=score_floor,
            )
            with self.subTest(replicate=replicate):
                if expected is None:
                    self.assertEqual(result.status, "EXACT_INFEASIBLE")
                else:
                    self.assertEqual(result.status, "EXACT_OPTIMAL")
                    self.assertEqual((result.lower, result.upper), expected)
                    self.assertTrue(
                        validate_path_witness(
                            problem,
                            result.lower_solution.witness,
                            gamma=gamma,
                            score_floor=score_floor,
                        )
                    )
                    self.assertTrue(
                        validate_path_witness(
                            problem,
                            result.upper_solution.witness,
                            gamma=gamma,
                            score_floor=score_floor,
                        )
                    )

    def test_outward_score_relaxation_contains_exact_endpoints(self):
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
        exact = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "b", "c", "d"),
            score_floor=4,
        )
        relaxed = solve_path_frontier_outward_relaxation(
            problem,
            forget_order=("a", "b", "c", "d"),
            score_floor=4,
            score_granularity=Fraction(1, 5),
        )
        self.assertEqual((exact.lower, exact.upper), (Fraction(0), Fraction(0)))
        self.assertEqual(
            (relaxed.lower, relaxed.upper),
            (Fraction(-5), Fraction(0)),
        )
        self.assertLessEqual(relaxed.lower, exact.lower)
        self.assertGreaterEqual(relaxed.upper, exact.upper)
        self.assertEqual(relaxed.maximum_score_shortfall, Fraction(4, 5))
        self.assertFalse(relaxed.lower_endpoint_exact_witnessed)
        self.assertTrue(relaxed.upper_endpoint_exact_witnessed)
        self.assertTrue(relaxed.exact_feasibility_witnessed)
        self.assertEqual(
            relaxed.lower_solution.witness.raw_score,
            Fraction(18, 5),
        )
        self.assertTrue(
            validate_path_witness(problem, relaxed.lower_solution.witness)
        )

    def test_relaxed_infeasibility_certifies_exact_infeasibility(self):
        problem = ExactPathProblem(
            nodes=(
                NodeSpec("a", "core", (0,)),
                NodeSpec("b", "core", (0,)),
            ),
            edges=(EdgeSpec("ab", "a", "b", score=0),),
        )
        relaxed = solve_path_frontier_outward_relaxation(
            problem,
            forget_order=("a", "b"),
            score_floor=3,
            score_granularity=1,
        )
        self.assertEqual(relaxed.status, "EXACT_INFEASIBLE")
        self.assertTrue(relaxed.exact_infeasibility_certified)
        self.assertIsNone(relaxed.lower)
        self.assertIsNone(relaxed.upper)

    def test_random_outward_relaxations_cover_exact_range(self):
        rng = random.Random(112358)
        for replicate in range(40):
            nodes = tuple(
                NodeSpec(node_id, "core", (0,))
                for node_id in ("a", "b", "c", "d")
            )
            edges = (
                EdgeSpec(
                    "ab",
                    "a",
                    "b",
                    score=Fraction(rng.randint(-6, 8), 3),
                    query=Fraction(rng.randint(-9, 9), 4),
                ),
                EdgeSpec(
                    "cd",
                    "c",
                    "d",
                    score=Fraction(rng.randint(-6, 8), 3),
                    query=Fraction(rng.randint(-9, 9), 4),
                ),
                EdgeSpec(
                    "ac",
                    "a",
                    "c",
                    score=Fraction(rng.randint(-6, 8), 3),
                    query=Fraction(rng.randint(-9, 9), 4),
                ),
                EdgeSpec(
                    "bd",
                    "b",
                    "d",
                    score=Fraction(rng.randint(-6, 8), 3),
                    query=Fraction(rng.randint(-9, 9), 4),
                ),
            )
            problem = ExactPathProblem(nodes, edges)
            score_floor = Fraction(rng.randint(-10, 14), 3)
            exact = solve_path_frontier_endpoints(
                problem,
                forget_order=("a", "b", "c", "d"),
                score_floor=score_floor,
            )
            relaxed = solve_path_frontier_outward_relaxation(
                problem,
                forget_order=("a", "b", "c", "d"),
                score_floor=score_floor,
                score_granularity=Fraction(1, 3),
            )
            with self.subTest(replicate=replicate):
                if relaxed.status == "EXACT_INFEASIBLE":
                    self.assertEqual(exact.status, "EXACT_INFEASIBLE")
                    continue
                if exact.status == "EXACT_OPTIMAL":
                    self.assertLessEqual(relaxed.lower, exact.lower)
                    self.assertGreaterEqual(relaxed.upper, exact.upper)
                for solution in (
                    relaxed.lower_solution,
                    relaxed.upper_solution,
                ):
                    self.assertTrue(validate_path_witness(problem, solution.witness))
                    shortfall = max(
                        Fraction(0),
                        score_floor - solution.witness.raw_score,
                    )
                    self.assertLessEqual(
                        shortfall,
                        relaxed.maximum_score_shortfall,
                    )


if __name__ == "__main__":
    unittest.main()
