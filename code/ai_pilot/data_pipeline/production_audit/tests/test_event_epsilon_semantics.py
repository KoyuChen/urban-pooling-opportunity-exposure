"""Geometric boundary cases for the declared positive-margin event model.

Each three-core example must form one event: singleton events are forbidden.
Expected answers follow directly from the stated intervals, independently of
the MILP's flow, seat, and big-M encodings.
"""

from pathlib import Path
import sys
import unittest

import numpy as np

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import ordered_run_existential_time as event_time  # noqa: E402


def exact(index, start, end, role="core"):
    return event_time.TimeSupportRow(index, role, start, start, end, end)


def chain():
    # Consecutive overlaps are 1/4, the outer intervals are disjoint, depth=2.
    return [exact(0, 0, 1), exact(1, 0.75, 1.75), exact(2, 1.5, 2.5)]


class EventEpsilonSemanticsTests(unittest.TestCase):
    def assert_feasibility(self, rows, capacity, epsilon, expected):
        program = event_time.build_program(rows, capacity, 0, epsilon=epsilon)
        result = event_time.solve(
            program,
            np.zeros(program.matrix.shape[1]),
            maximize=False,
            time_limit=10.0,
        )
        self.assertEqual(
            result["status"],
            event_time.CERTIFIED if expected else "PROVEN_INFEASIBLE_BY_HIGHS",
        )
        if expected:
            self.assertEqual(result["replay"]["status"], "PASS")

    def test_overlap_chain_is_connected_without_being_a_clique(self):
        self.assert_feasibility(chain(), 2, 0.2, True)

    def test_larger_margin_breaks_the_same_chain(self):
        self.assert_feasibility(chain(), 2, 0.3, False)

    def test_three_identical_intervals_exceed_capacity_two(self):
        self.assert_feasibility([exact(i, 0, 1) for i in range(3)], 2, 0.1, False)

    def test_three_identical_intervals_fit_capacity_three(self):
        self.assert_feasibility([exact(i, 0, 1) for i in range(3)], 3, 0.1, True)

    def test_capacity_uses_ordinary_overlap_not_the_epsilon_graph(self):
        # The epsilon=1/2 graph is a path, but all three occupy [0.9,1).
        rows = [exact(0, 0, 1), exact(1, 0.5, 1.5), exact(2, 0.9, 1.9)]
        self.assert_feasibility(rows, 2, 0.5, False)

    def test_thresholded_path_with_depth_three_fits_capacity_three(self):
        rows = [exact(0, 0, 1), exact(1, 0.5, 1.5), exact(2, 0.9, 1.9)]
        self.assert_feasibility(rows, 3, 0.5, True)

    def test_rectangular_support_admits_one_common_bridge_completion(self):
        rows = [
            exact(0, 0, 1),
            event_time.TimeSupportRow(1, "core", 0.7, 0.8, 2.2, 2.3),
            exact(2, 2, 3),
        ]
        self.assert_feasibility(rows, 2, 0.2, True)

    def test_unused_buffer_still_requires_minimum_duration(self):
        self.assert_feasibility(chain() + [exact(3, 10, 10.05, "buffer")], 2, 0.1, False)

    def test_smaller_margin_allows_the_same_unused_buffer(self):
        self.assert_feasibility(chain() + [exact(3, 10, 10.05, "buffer")], 2, 0.01, True)

    def test_endpoint_touching_does_not_connect_an_event(self):
        self.assert_feasibility([exact(i, i, i + 1) for i in range(3)], 2, 0.01, False)

    def test_overlap_exactly_equal_to_margin_is_allowed(self):
        self.assert_feasibility([exact(0, 0, 1), exact(1, 0.75, 1.75)], 2, 0.25, True)

    def test_overlap_below_margin_is_rejected(self):
        self.assert_feasibility([exact(0, 0, 1), exact(1, 0.75, 1.75)], 2, 0.26, False)


if __name__ == "__main__":
    unittest.main()
