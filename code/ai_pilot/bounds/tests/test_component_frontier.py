import random
import sys
import unittest
from fractions import Fraction
from pathlib import Path


BOUNDS_DIR = Path(__file__).resolve().parents[1]
BENCHMARKS_DIR = Path(__file__).resolve().parents[2] / "benchmarks"
sys.path.insert(0, str(BOUNDS_DIR))
sys.path.insert(0, str(BENCHMARKS_DIR))

from component_frontier import (  # noqa: E402
    PATH_FRONTIER_INTERNAL_API_REVISION,
    ComponentFrontierLimitExceeded,
    decompose_incidence_components,
    solve_component_frontier_endpoints,
)
from path_frontier_dp import (  # noqa: E402
    CountConstraint,
    EdgeSpec,
    ExactPathProblem,
    NodeSpec,
    solve_path_frontier_endpoints,
    validate_path_witness,
)
from path_frontier_benchmark import exhaustive_endpoints  # noqa: E402


class ExactComponentFrontierTests(unittest.TestCase):
    @staticmethod
    def _tradeoff_component(prefix: str, high_query: int) -> tuple:
        nodes = tuple(
            NodeSpec(f"{prefix}{name}", "core", (0,))
            for name in ("a", "b", "c", "d")
        )
        # ab+cd is free, score zero, query zero.  ac+bd uses two units of
        # Gamma, has raw score four, and contributes high_query.
        edges = (
            EdgeSpec(f"{prefix}ab", f"{prefix}a", f"{prefix}b"),
            EdgeSpec(f"{prefix}cd", f"{prefix}c", f"{prefix}d"),
            EdgeSpec(
                f"{prefix}ac",
                f"{prefix}a",
                f"{prefix}c",
                score=1,
                query=high_query,
                omitted=True,
            ),
            EdgeSpec(
                f"{prefix}bd",
                f"{prefix}b",
                f"{prefix}d",
                score=1,
                omitted=True,
            ),
        )
        return nodes, edges

    def test_global_gamma_and_score_are_convolved_not_imposed_locally(self):
        nodes_0, edges_0 = self._tradeoff_component("p", 10)
        nodes_1, edges_1 = self._tradeoff_component("q", 1)
        problem = ExactPathProblem(nodes_0 + nodes_1, edges_0 + edges_1)
        order = ("pa", "qa", "pb", "qb", "pc", "qc", "pd", "qd")
        result = solve_component_frontier_endpoints(
            problem,
            forget_order=order,
            gamma=2,
            score_floor=4,
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        self.assertEqual((result.lower, result.upper), (Fraction(1), Fraction(10)))
        self.assertEqual(len(result.components), 2)
        self.assertGreater(result.global_schedule.schedule_width, 2)
        self.assertEqual(
            max(schedule.schedule_width for schedule in result.component_schedules),
            2,
        )
        for solution in (result.lower_solution, result.upper_solution):
            self.assertEqual(len(solution.component_witnesses), 2)
            self.assertEqual(solution.witness.omitted_edge_count, 2)
            self.assertEqual(solution.witness.raw_score, Fraction(4))
            self.assertTrue(
                validate_path_witness(
                    problem,
                    solution.witness,
                    gamma=2,
                    score_floor=4,
                )
            )

    def test_candidate_graph_only_split_has_a_shared_release_factor_counterexample(self):
        factor = "shared-release-cell"
        count_source = NodeSpec(
            "count-source",
            "context_only",
            (0, 1),
            factor_contributions={0: {}, 1: {factor: 1}},
            label_query={0: 0, 1: 1},
        )
        release_target = NodeSpec(
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
        problem = ExactPathProblem(
            (count_source, release_target),
            (),
            (constraint,),
        )

        # The candidate graph has two isolated vertices.  Duplicating the
        # shared release factor across those singleton graph components makes
        # HIGH locally impossible at release-target and gives the false upper
        # endpoint 1 instead of the attained global endpoint 11.
        naive_source = solve_path_frontier_endpoints(
            ExactPathProblem((count_source,), (), (constraint,)),
            forget_order=("count-source",),
        )
        naive_target = solve_path_frontier_endpoints(
            ExactPathProblem((release_target,), (), (constraint,)),
            forget_order=("release-target",),
        )
        self.assertEqual(naive_source.upper + naive_target.upper, Fraction(1))

        components = decompose_incidence_components(problem)
        self.assertEqual(len(components), 1)
        self.assertEqual(set(components[0].node_ids), {"count-source", "release-target"})
        self.assertEqual(components[0].factors, (factor,))
        exact = solve_component_frontier_endpoints(
            problem,
            forget_order=("count-source", "release-target"),
        )
        self.assertEqual((exact.lower, exact.upper), (Fraction(0), Fraction(11)))
        self.assertEqual(
            dict(exact.upper_solution.witness.label_assignments),
            {"count-source": 1, "release-target": "HIGH"},
        )

    def test_orphan_factor_component_preserves_exact_infeasible_status(self):
        problem = ExactPathProblem(
            nodes=(
                NodeSpec("a", "core", (0,)),
                NodeSpec("b", "core", (0,)),
            ),
            edges=(EdgeSpec("ab", "a", "b"),),
            count_constraints=(CountConstraint("orphan", 1, 1),),
        )
        components = decompose_incidence_components(problem)
        self.assertEqual(len(components), 2)
        self.assertTrue(any(not component.node_ids for component in components))
        result = solve_component_frontier_endpoints(
            problem,
            forget_order=("a", "b"),
        )
        monolithic = solve_path_frontier_endpoints(
            problem,
            forget_order=("a", "b"),
        )
        self.assertEqual(result.status, "EXACT_INFEASIBLE")
        self.assertEqual(result.status, monolithic.status)
        self.assertTrue(result.certified)
        self.assertIsNone(result.lower_solution.witness)
        self.assertIsNone(result.upper_solution.witness)

    def test_global_score_shift_survives_variable_local_edge_cardinality(self):
        problem = ExactPathProblem(
            nodes=(
                NodeSpec("a", "core", (0,)),
                NodeSpec("b", "core", (0,)),
                NodeSpec("x", "buffer", (0,)),
                NodeSpec("y", "buffer", (0,)),
                NodeSpec("c", "core", (0,)),
                NodeSpec("d", "core", (0,)),
            ),
            edges=(
                # One edge and two core incidences: raw score -4.
                EdgeSpec("ab", "a", "b", score=-2),
                # Two edges and one core incidence each: raw score -2.
                EdgeSpec("ax", "a", "x", score=-1, query=1),
                EdgeSpec("by", "b", "y", score=-1, query=1),
                EdgeSpec("cd", "c", "d", score=0),
            ),
        )
        order = ("a", "c", "x", "d", "b", "y")
        monolithic = solve_path_frontier_endpoints(
            problem,
            forget_order=order,
            score_floor=-2,
        )
        decomposed = solve_component_frontier_endpoints(
            problem,
            forget_order=order,
            score_floor=-2,
        )
        self.assertEqual(
            (decomposed.lower, decomposed.upper),
            (Fraction(2), Fraction(2)),
        )
        self.assertEqual(
            (decomposed.lower, decomposed.upper),
            (monolithic.lower, monolithic.upper),
        )
        self.assertEqual(decomposed.score_shift_per_core_incidence, Fraction(2))
        self.assertEqual(
            set(decomposed.lower_solution.witness.selected_edge_ids),
            {"ax", "by", "cd"},
        )
        self.assertEqual(decomposed.lower_solution.witness.raw_score, Fraction(-2))

    @staticmethod
    def _random_problem(seed: int) -> tuple[ExactPathProblem, tuple[str, ...], int]:
        rng = random.Random(seed)
        component_count = rng.randint(1, 3)
        nodes = []
        edges = []
        constraints = []
        orders = []
        score_values = (Fraction(-1), Fraction(-1, 2), Fraction(0), Fraction(1, 2), Fraction(1))
        query_values = (Fraction(-2), Fraction(-1, 2), Fraction(0), Fraction(1, 3), Fraction(2))
        label_pairs = tuple((left, right) for left in (0, 1) for right in (0, 1))
        for component in range(component_count):
            prefix = f"s{seed}c{component}:"
            factor = ("factor", seed, component)
            core_ids = tuple(prefix + name for name in ("a", "b", "c", "d"))
            for node_id in core_ids:
                nodes.append(
                    NodeSpec(
                        node_id,
                        "core",
                        (0, 1),
                        factor_contributions={0: {}, 1: {factor: 1}},
                        label_query={
                            0: rng.choice(query_values),
                            1: rng.choice(query_values),
                        },
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
                        "none": rng.choice(query_values),
                        "LOW": rng.choice(query_values),
                        "HIGH": rng.choice(query_values),
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
                allowed = tuple(
                    pair for pair in label_pairs if rng.random() < 0.75
                )
                if not allowed:
                    allowed = (rng.choice(label_pairs),)
                edges.append(
                    EdgeSpec(
                        prefix + edge_name,
                        core_ids[left],
                        core_ids[right],
                        omitted=bool(rng.getrandbits(1)),
                        allowed_label_pairs=allowed,
                        score_by_label_pair={
                            pair: rng.choice(score_values) for pair in allowed
                        },
                        query_by_label_pair={
                            pair: rng.choice(query_values) for pair in allowed
                        },
                    )
                )
            orders.append(core_ids + (release_id,))

        interleaved = tuple(
            node_id
            for position in range(5)
            for order in orders
            for node_id in (order[position],)
        )
        return (
            ExactPathProblem(tuple(nodes), tuple(edges), tuple(constraints)),
            interleaved,
            component_count,
        )

    def test_deterministic_random_battery_matches_monolithic_endpoints_and_replay(self):
        configurations = (
            (None, None),
            (0, Fraction(-2)),
            (1, Fraction(0)),
            (2, Fraction(2)),
        )
        checked = 0
        for seed in range(18):
            problem, order, expected_components = self._random_problem(seed)
            self.assertEqual(
                len(decompose_incidence_components(problem)),
                expected_components,
            )
            for gamma, score_floor in configurations:
                with self.subTest(seed=seed, gamma=gamma, score_floor=score_floor):
                    monolithic = solve_path_frontier_endpoints(
                        problem,
                        forget_order=order,
                        gamma=gamma,
                        score_floor=score_floor,
                    )
                    decomposed = solve_component_frontier_endpoints(
                        problem,
                        forget_order=order,
                        gamma=gamma,
                        score_floor=score_floor,
                    )
                    self.assertEqual(decomposed.status, monolithic.status)
                    self.assertEqual(decomposed.lower, monolithic.lower)
                    self.assertEqual(decomposed.upper, monolithic.upper)
                    self.assertEqual(
                        decomposed.score_shift_per_core_incidence,
                        monolithic.score_shift_per_core_incidence,
                    )
                    self.assertEqual(
                        decomposed.capped_integer_score_target,
                        monolithic.capped_integer_score_target,
                    )
                    if decomposed.status == "EXACT_OPTIMAL":
                        for solution in (
                            decomposed.lower_solution,
                            decomposed.upper_solution,
                        ):
                            self.assertTrue(solution.certified)
                            self.assertEqual(
                                solution.objective_value,
                                solution.witness.query_value,
                            )
                            self.assertEqual(
                                len(solution.component_witnesses),
                                expected_components,
                            )
                            self.assertTrue(
                                validate_path_witness(
                                    problem,
                                    solution.witness,
                                    gamma=gamma,
                                    score_floor=score_floor,
                                )
                            )
                    checked += 1
        self.assertEqual(checked, 72)

    def test_tiny_random_battery_matches_independent_exhaustive_oracle(self):
        checked = 0
        for seed in range(30):
            problem, order, component_count = self._random_problem(seed)
            if component_count > 2:
                continue
            for gamma, score_floor in (
                (None, None),
                (1, Fraction(0)),
            ):
                oracle = exhaustive_endpoints(
                    problem,
                    gamma=gamma,
                    score_floor=score_floor,
                )
                decomposed = solve_component_frontier_endpoints(
                    problem,
                    forget_order=order,
                    gamma=gamma,
                    score_floor=score_floor,
                )
                self.assertEqual(
                    (decomposed.status, decomposed.lower, decomposed.upper),
                    (oracle.status, oracle.lower, oracle.upper),
                )
                checked += 1
            if checked >= 12:
                break
        self.assertEqual(checked, 12)

    def test_component_limit_is_explicit_and_internal_revision_is_pinned(self):
        self.assertIn("2026-08-27", PATH_FRONTIER_INTERNAL_API_REVISION)
        nodes, edges = self._tradeoff_component("z", 1)
        problem = ExactPathProblem(nodes, edges)
        with self.assertRaises(ComponentFrontierLimitExceeded):
            solve_component_frontier_endpoints(
                problem,
                forget_order=("za", "zb", "zc", "zd"),
                max_frontier_records=1,
            )


if __name__ == "__main__":
    unittest.main()
