import sys
import unittest
from pathlib import Path

import pandas as pd


BOUNDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOUNDS_DIR))

from set_packing_bounds import solve_bounds  # noqa: E402
from synthetic_validation import build_candidates, generate_market  # noqa: E402


class SetPackingBoundsTests(unittest.TestCase):
    def setUp(self):
        self.nodes = pd.DataFrame(
            {
                "node_id": ["a", "b", "c", "d"],
                "ses_bin": [0, 0, 1, 1],
                "ses_value": [0.0, 1.0, 4.0, 5.0],
                "matched": [1, 1, 1, 1],
            }
        )
        self.edges = pd.DataFrame(
            {
                "edge_id": ["ab", "cd", "ac", "bd"],
                "u": ["a", "c", "a", "b"],
                "v": ["b", "d", "c", "d"],
                "edge_score": [1.0, 1.0, 0.5, 0.5],
            }
        )

    def test_raw_same_bin_bounds_cover_both_perfect_matchings(self):
        result = solve_bounds(
            self.nodes,
            self.edges,
            metric="same_bin",
            matched_col="matched",
        )
        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.lower, 0.0)
        self.assertAlmostEqual(result.upper, 1.0)
        self.assertAlmostEqual(result.width, 1.0)

    def test_score_retention_shrinks_identified_set(self):
        result = solve_bounds(
            self.nodes,
            self.edges,
            metric="same_bin",
            matched_col="matched",
            score_retention=0.9,
        )
        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.score_optimum, 2.0)
        self.assertAlmostEqual(result.lower, 1.0)
        self.assertAlmostEqual(result.upper, 1.0)

    def test_ses_gap_metric(self):
        result = solve_bounds(
            self.nodes,
            self.edges,
            metric="ses_gap",
            matched_col="matched",
        )
        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.lower, 1.0)
        self.assertAlmostEqual(result.upper, 4.0)

    def test_exhaustive_fallback_matches_milp(self):
        result = solve_bounds(
            self.nodes,
            self.edges,
            metric="same_bin",
            matched_col="matched",
            backend="fallback",
        )
        self.assertTrue(result.feasible)
        self.assertEqual(result.lower_solution.backend, "fallback")
        self.assertAlmostEqual(result.lower, 0.0)
        self.assertAlmostEqual(result.upper, 1.0)

    def test_unmatched_nodes_are_excluded(self):
        nodes = pd.concat(
            [
                self.nodes,
                pd.DataFrame(
                    {
                        "node_id": ["x"],
                        "ses_bin": [0],
                        "ses_value": [0.3],
                        "matched": [0],
                    }
                ),
            ],
            ignore_index=True,
        )
        edges = pd.concat(
            [
                self.edges,
                pd.DataFrame(
                    {
                        "edge_id": ["ax"],
                        "u": ["a"],
                        "v": ["x"],
                        "edge_score": [99.0],
                    }
                ),
            ],
            ignore_index=True,
        )
        result = solve_bounds(nodes, edges, matched_col="matched")
        self.assertTrue(result.feasible)
        self.assertEqual(result.candidate_edge_count, 4)
        self.assertNotIn("ax", result.score_solution.selected_edge_ids)

    def test_odd_exact_node_count_is_infeasible(self):
        result = solve_bounds(self.nodes.iloc[:3], self.edges.iloc[[0, 2]], match_all=True)
        self.assertFalse(result.feasible)
        self.assertIn("even", result.warning)

    def test_synthetic_candidate_builder_retains_truth(self):
        nodes = generate_market(12, n_pairs=10)
        edges = build_candidates(nodes, time_bin_minutes=30)
        self.assertEqual(int(edges["is_true"].sum()), 10)


if __name__ == "__main__":
    unittest.main()
