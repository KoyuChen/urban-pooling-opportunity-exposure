import sys
import unittest
from pathlib import Path

import pandas as pd


BOUNDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOUNDS_DIR))

from joint_label_matching import (  # noqa: E402
    SCIPY_MILP_AVAILABLE,
    solve_joint_label_matching_endpoints,
)


class JointLabelMatchingTests(unittest.TestCase):
    def four_core_nodes(self):
        return pd.DataFrame(
            {
                "node_id": ["a", "b", "c", "d"],
                "role": ["core"] * 4,
                "cell": ["g"] * 4,
                "label_support": [["A"], ["A"], ["B"], ["B"]],
            }
        )

    def four_cycle_edges(self):
        return pd.DataFrame(
            {
                "edge_id": ["ab", "cd", "ac", "bd"],
                "u": ["a", "c", "a", "b"],
                "v": ["b", "d", "c", "d"],
            }
        )

    def test_singleton_independent_case_degenerates_to_matching_endpoints(self):
        result = solve_joint_label_matching_endpoints(
            self.four_core_nodes(),
            self.four_cycle_edges(),
            {"A": "low", "B": "high"},
            backend="fallback",
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        self.assertTrue(result.certified)
        self.assertEqual((result.lower, result.upper), (0.0, 1.0))
        self.assertEqual(
            dict(result.upper_solution.label_assignments),
            {"a": "A", "b": "A", "c": "B", "d": "B"},
        )

    def test_four_node_global_count_coupling_shrinks_upper_endpoint(self):
        nodes = pd.DataFrame(
            {
                "node_id": ["a", "b", "c", "d"],
                "role": ["core"] * 4,
                "cell": ["g"] * 4,
                "label_support": [
                    ["A", "B"],
                    ["A", "C"],
                    ["A", "D"],
                    ["A", "E"],
                ],
            }
        )
        edges = pd.DataFrame(
            {"edge_id": ["ab", "cd"], "u": ["a", "c"], "v": ["b", "d"]}
        )
        catalog = {
            "A": 0,
            "B": 1,
            "C": 2,
            "D": 1,
            "E": 2,
        }
        independent = solve_joint_label_matching_endpoints(
            nodes, edges, catalog, backend="fallback"
        )
        coupled = solve_joint_label_matching_endpoints(
            nodes,
            edges,
            catalog,
            pd.DataFrame(
                {"cell": ["g"], "value": ["A"], "lower": [0], "upper": [2]}
            ),
            backend="fallback",
        )
        self.assertEqual(independent.upper, 1.0)
        self.assertEqual(coupled.status, "EXACT_OPTIMAL")
        self.assertEqual((coupled.lower, coupled.upper), (0.0, 0.5))

    def test_context_only_nodes_participate_in_counts_without_matching(self):
        nodes = pd.DataFrame(
            {
                "node_id": ["a", "b", "history"],
                "role": ["core", "core", "context_only"],
                "cell": ["g", "g", "g"],
                "label_support": [["B"], ["B"], ["A"]],
            }
        )
        edges = pd.DataFrame({"edge_id": ["ab"], "u": ["a"], "v": ["b"]})
        counts = pd.DataFrame(
            {
                "cell": ["g", "g"],
                "value": ["A", "B"],
                "lower": [1, 2],
                "upper": [1, 2],
            }
        )
        result = solve_joint_label_matching_endpoints(
            nodes,
            edges,
            {"A": 0, "B": 1},
            counts,
            backend="fallback",
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        self.assertEqual(result.context_only_node_count, 1)
        self.assertEqual(result.upper_solution.selected_edge_ids, ("ab",))
        self.assertEqual(dict(result.upper_solution.label_assignments)["history"], "A")

    def test_core_buffer_matching_uses_core_incidence_denominator(self):
        nodes = pd.DataFrame(
            {
                "node_id": ["a", "b", "x", "y"],
                "role": ["core", "core", "buffer", "buffer"],
                "cell": ["g"] * 4,
                "label_support": [["A"], ["B"], ["A"], ["B"]],
            }
        )
        edges = pd.DataFrame(
            {"edge_id": ["ax", "by"], "u": ["a", "b"], "v": ["x", "y"]}
        )
        result = solve_joint_label_matching_endpoints(
            nodes, edges, {"A": 0, "B": 1}, backend="fallback"
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        self.assertEqual((result.lower, result.upper), (1.0, 1.0))
        self.assertEqual(set(result.upper_solution.selected_edge_ids), {"ax", "by"})
        self.assertEqual(result.core_node_count, 2)
        self.assertEqual(result.buffer_node_count, 2)

    def test_gamma_expands_feasible_worlds_monotonically(self):
        edges = self.four_cycle_edges().assign(omitted=[0, 0, 1, 0])
        gamma_zero = solve_joint_label_matching_endpoints(
            self.four_core_nodes(),
            edges,
            {"A": 0, "B": 1},
            omitted_col="omitted",
            gamma=0,
            backend="fallback",
        )
        gamma_one = solve_joint_label_matching_endpoints(
            self.four_core_nodes(),
            edges,
            {"A": 0, "B": 1},
            omitted_col="omitted",
            gamma=1,
            backend="fallback",
        )
        self.assertEqual((gamma_zero.lower, gamma_zero.upper), (1.0, 1.0))
        self.assertEqual((gamma_one.lower, gamma_one.upper), (0.0, 1.0))
        self.assertLessEqual(gamma_one.lower, gamma_zero.lower)
        self.assertGreaterEqual(gamma_one.upper, gamma_zero.upper)

    def test_declared_truth_is_covered_and_score_floor_can_retain_it(self):
        edges = self.four_cycle_edges().assign(score=[0.9, 0.9, 0.1, 0.1])
        raw = solve_joint_label_matching_endpoints(
            self.four_core_nodes(),
            edges,
            {"A": 0, "B": 1},
            score_col="score",
            backend="fallback",
        )
        true_value = 1.0  # truth: edges ab/cd and singleton labels A,A,B,B
        self.assertLessEqual(raw.lower, true_value)
        self.assertGreaterEqual(raw.upper, true_value)

        restricted = solve_joint_label_matching_endpoints(
            self.four_core_nodes(),
            edges,
            {"A": 0, "B": 1},
            score_col="score",
            score_floor=3.5,
            backend="fallback",
        )
        self.assertEqual((restricted.lower, restricted.upper), (1.0, 1.0))
        self.assertGreaterEqual(restricted.lower_solution.total_score, 3.5)

    def test_attribute_conditioned_label_switch_changes_partner(self):
        nodes = pd.DataFrame(
            {
                "node_id": ["c", "x", "y"],
                "role": ["core", "buffer", "buffer"],
                "cell": ["target", "history", "history"],
                "label_support": [["A", "B"], ["A"], ["B"]],
            }
        )
        edges = pd.DataFrame(
            {
                "edge_id": ["cx", "cy"],
                "u": ["c", "c"],
                "v": ["x", "y"],
                "allowed_label_pairs": [[["A", "A"]], [["B", "B"]]],
            }
        )

        def solve_for(value, backend="fallback"):
            return solve_joint_label_matching_endpoints(
                nodes,
                edges,
                {"A": 0, "B": 1},
                pd.DataFrame(
                    {
                        "cell": ["target"],
                        "value": [value],
                        "lower": [1],
                        "upper": [1],
                    }
                ),
                backend=backend,
            )

        label_a = solve_for("A")
        label_b = solve_for("B")
        self.assertEqual(label_a.upper_solution.selected_edge_ids, ("cx",))
        self.assertEqual(label_b.upper_solution.selected_edge_ids, ("cy",))
        self.assertEqual(dict(label_a.upper_solution.label_assignments)["c"], "A")
        self.assertEqual(dict(label_b.upper_solution.label_assignments)["c"], "B")
        if SCIPY_MILP_AVAILABLE:
            scipy_a = solve_for("A", backend="scipy")
            scipy_b = solve_for("B", backend="scipy")
            self.assertEqual(scipy_a.upper_solution.selected_edge_ids, ("cx",))
            self.assertEqual(scipy_b.upper_solution.selected_edge_ids, ("cy",))

    def test_state_limit_and_structural_infeasibility_have_distinct_statuses(self):
        unresolved = solve_joint_label_matching_endpoints(
            self.four_core_nodes(),
            self.four_cycle_edges(),
            {"A": 0, "B": 1},
            backend="fallback",
            fallback_max_states=0,
        )
        self.assertEqual(unresolved.status, "UNRESOLVED")
        self.assertFalse(unresolved.certified)

        isolated = solve_joint_label_matching_endpoints(
            self.four_core_nodes(),
            self.four_cycle_edges().iloc[[0]],
            {"A": 0, "B": 1},
            backend="fallback",
        )
        self.assertEqual(isolated.status, "PROVEN_INFEASIBLE")
        self.assertTrue(isolated.certified)

    def test_buffer_buffer_and_context_edges_are_rejected(self):
        nodes = pd.DataFrame(
            {
                "node_id": ["a", "x", "y", "h"],
                "role": ["core", "buffer", "buffer", "context_only"],
                "cell": ["g"] * 4,
                "label_support": [["A"]] * 4,
            }
        )
        with self.assertRaisesRegex(ValueError, "buffer--buffer"):
            solve_joint_label_matching_endpoints(
                nodes,
                pd.DataFrame({"u": ["a", "x"], "v": ["x", "y"]}),
                {"A": 0},
                backend="fallback",
            )
        with self.assertRaisesRegex(ValueError, "context_only"):
            solve_joint_label_matching_endpoints(
                nodes,
                pd.DataFrame({"u": ["a", "a"], "v": ["x", "h"]}),
                {"A": 0},
                backend="fallback",
            )

    @unittest.skipUnless(SCIPY_MILP_AVAILABLE, "SciPy MILP unavailable")
    def test_fallback_and_highs_agree_but_only_fallback_is_certified(self):
        nodes = pd.DataFrame(
            {
                "node_id": ["a", "b", "c", "d"],
                "role": ["core"] * 4,
                "cell": ["g"] * 4,
                "label_support": [
                    ["A", "B"],
                    ["A", "C"],
                    ["A", "D"],
                    ["A", "E"],
                ],
            }
        )
        edges = pd.DataFrame(
            {"edge_id": ["ab", "cd"], "u": ["a", "c"], "v": ["b", "d"]}
        )
        catalog = {"A": 0, "B": 1, "C": 2, "D": 1, "E": 2}
        counts = pd.DataFrame(
            {"cell": ["g"], "value": ["A"], "lower": [0], "upper": [2]}
        )
        exact = solve_joint_label_matching_endpoints(
            nodes, edges, catalog, counts, backend="fallback"
        )
        numerical = solve_joint_label_matching_endpoints(
            nodes, edges, catalog, counts, backend="scipy", time_limit=None
        )
        self.assertEqual((numerical.lower, numerical.upper), (exact.lower, exact.upper))
        self.assertEqual(numerical.status, "NUMERICALLY_OPTIMAL")
        self.assertFalse(numerical.certified)
        self.assertTrue(exact.certified)


if __name__ == "__main__":
    unittest.main()
