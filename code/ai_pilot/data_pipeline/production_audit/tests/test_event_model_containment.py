"""Exact finite checks of the manuscript's event-model containment witnesses.

This oracle enumerates subsets and set partitions directly. It imports no
production event generator, matching solver, MILP, or pricing implementation.
All interval comparisons and reported means use exact rational arithmetic.
"""

from fractions import Fraction
from itertools import combinations
import unittest


def _partitions(items):
    """Generate every unlabeled set partition once, including singletons."""
    if not items:
        yield ()
        return
    first, *rest = items
    for partition in _partitions(rest):
        yield ((first,),) + partition
        for index, block in enumerate(partition):
            yield partition[:index] + ((first,) + block,) + partition[index + 1:]


def _worlds(intervals, cores, q, capacity, family):
    """All worlds at the same exact times, buffer count, and capacity."""
    if family not in {"pair", "clique", "event"}:
        raise ValueError(family)
    cores = frozenset(cores)
    buffers = sorted(set(intervals) - cores)

    def overlap(left, right):
        return (max(intervals[left][0], intervals[right][0])
                < min(intervals[left][1], intervals[right][1]))

    def allowed(block):
        if len(block) < 2 or not cores.intersection(block):
            return False
        # Occupancy of half-open intervals can increase only at a start.
        if any(sum(intervals[row][0] <= start < intervals[row][1]
                   for row in block) > capacity
               for start in {intervals[row][0] for row in block}):
            return False
        if family == "pair":
            return len(block) == 2 and overlap(*block)
        if family == "clique":
            return all(overlap(left, right)
                       for left, right in combinations(block, 2))
        reached = {block[0]}
        while True:
            expanded = reached | {
                row for row in block
                if any(overlap(row, previous) for previous in reached)
            }
            if expanded == reached:
                return len(reached) == len(block)
            reached = expanded

    result = set()
    for selected in combinations(buffers, q):
        for partition in _partitions(sorted(cores) + list(selected)):
            if all(allowed(block) for block in partition):
                result.add(frozenset(frozenset(block) for block in partition))
    return result


def _mean_range(worlds, cores, values):
    means = []
    for world in worlds:
        selected_buffers = frozenset().union(*world) - frozenset(cores)
        means.append(Fraction(sum(values.get(row, 0) for row in selected_buffers),
                              len(selected_buffers)))
    return min(means), max(means)


def _core_saturating_matchings(intervals, cores, q):
    """Independent graph oracle for the K=2 theorem."""
    cores = frozenset(cores)
    if (len(cores) + q) % 2:
        return set()
    edge_count = (len(cores) + q) // 2

    def overlaps(left, right):
        return (max(intervals[left][0], intervals[right][0])
                < min(intervals[left][1], intervals[right][1]))

    edges = [
        (left, right)
        for left, right in combinations(sorted(intervals), 2)
        if cores.intersection((left, right)) and overlaps(left, right)
    ]
    result = set()
    for matching in combinations(edges, edge_count):
        vertices = [vertex for edge in matching for vertex in edge]
        if len(set(vertices)) != len(vertices):
            continue
        if not cores.issubset(vertices):
            continue
        if len(set(vertices) - cores) != q:
            continue
        result.add(frozenset(frozenset(edge) for edge in matching))
    return result


def _decision_status(bounds, threshold):
    lower, upper = bounds
    if lower >= threshold:
        return "CERTIFIED_POSITIVE"
    if upper < threshold:
        return "CERTIFIED_NEGATIVE"
    return "AMBIGUOUS"


def _anytime_certificate(threshold, minimum_lower=None, maximum_upper=None,
                         feasible_values=()):
    """Audit the sufficient bound/witness conditions without exact endpoints."""
    if minimum_lower is not None and minimum_lower >= threshold:
        return "CERTIFIED_POSITIVE"
    if maximum_upper is not None and maximum_upper < threshold:
        return "CERTIFIED_NEGATIVE"
    if (any(value < threshold for value in feasible_values)
            and any(value >= threshold for value in feasible_values)):
        return "AMBIGUOUS"
    return "UNRESOLVED"


class EventModelContainmentTests(unittest.TestCase):
    def test_k2_worlds_equal_core_saturating_matchings(self):
        intervals = {
            row: (Fraction(0), Fraction(1))
            for row in ("c1", "c2", "b1", "b2", "b3")
        }
        cores = {"c1", "c2"}
        for q in (0, 1, 2):
            with self.subTest(q=q):
                pair_worlds = _worlds(intervals, cores, q, 2, "pair")
                graph_matchings = _core_saturating_matchings(intervals, cores, q)
                self.assertEqual(pair_worlds, graph_matchings)
        self.assertFalse(_worlds(intervals, cores, 1, 2, "pair"))

    def test_c2_event_changes_fixed_q_selected_buffer_mean(self):
        # The full overlap graph is the path b0--c1--c2--b1--b2.
        intervals = {
            "c1": (Fraction(0), Fraction(2)),
            "c2": (Fraction(1), Fraction(3)),
            "b0": (Fraction(-1), Fraction(1, 2)),
            "b1": (Fraction(5, 2), Fraction(4)),
            "b2": (Fraction(7, 2), Fraction(5)),
        }
        cores = {"c1", "c2"}
        worlds = {family: _worlds(intervals, cores, 2, 2, family)
                  for family in ("pair", "clique", "event")}
        self.assertEqual([len(worlds[family]) for family in worlds], [1, 1, 3])
        self.assertEqual(worlds["pair"], worlds["clique"])
        self.assertLess(worlds["clique"], worlds["event"])
        self.assertEqual(_mean_range(worlds["pair"], cores, {"b2": 1}), (0, 0))
        self.assertEqual(_mean_range(worlds["event"], cores, {"b2": 1}),
                         (0, Fraction(1, 2)))
        upper_witness = frozenset({frozenset({"c1", "c2", "b1", "b2"})})
        self.assertIn(upper_witness, worlds["event"])
        self.assertNotIn(upper_witness, worlds["clique"])

    def test_c3_clique_changes_fixed_q_selected_buffer_mean(self):
        # Two disconnected cliques. Capacity three applies within each event.
        intervals = {row: (Fraction(0), Fraction(1))
                     for row in ("c1", "a1", "a2")}
        intervals.update({row: (Fraction(2), Fraction(3))
                          for row in ("c2", "c3", "b1", "b2")})
        cores = {"c1", "c2", "c3"}
        values = {"a1": 1, "a2": 1}
        worlds = {family: _worlds(intervals, cores, 3, 3, family)
                  for family in ("pair", "clique", "event")}
        self.assertEqual([len(worlds[family]) for family in worlds], [4, 6, 6])
        self.assertLess(worlds["pair"], worlds["clique"])
        self.assertEqual(worlds["clique"], worlds["event"])
        self.assertEqual(_mean_range(worlds["pair"], cores, values),
                         (Fraction(1, 3), Fraction(1, 3)))
        self.assertEqual(_mean_range(worlds["clique"], cores, values),
                         (Fraction(1, 3), Fraction(2, 3)))
        upper_witness = frozenset({frozenset({"c1", "a1", "a2"}),
                                   frozenset({"c2", "c3", "b1"})})
        self.assertIn(upper_witness, worlds["clique"])
        self.assertNotIn(upper_witness, worlds["pair"])

    def test_common_positive_intersection_collapses_event_to_clique_at_every_c(self):
        names = ("c1", "c2", "c3", "b1", "b2", "b3")
        intervals = {row: (Fraction(index, 10), 2 + Fraction(index, 10))
                     for index, row in enumerate(names)}
        cores = {"c1", "c2", "c3"}
        for capacity in (2, 3, 4, 6):
            with self.subTest(capacity=capacity):
                pair = _worlds(intervals, cores, 3, capacity, "pair")
                clique = _worlds(intervals, cores, 3, capacity, "clique")
                event = _worlds(intervals, cores, 3, capacity, "event")
                self.assertTrue(pair)
                self.assertLessEqual(pair, clique)
                self.assertEqual(clique, event)
                self.assertTrue(all(len(block) <= capacity
                                    for world in event for block in world))
                if capacity == 2:
                    self.assertEqual(pair, clique)

    def test_endpoint_touching_does_not_connect(self):
        intervals = {"c1": (Fraction(0), Fraction(1)),
                     "c2": (Fraction(1), Fraction(2))}
        for family in ("pair", "clique", "event"):
            with self.subTest(family=family):
                self.assertFalse(_worlds(intervals, {"c1", "c2"}, 0, 2, family))

    def test_candidate_addition_expands_frontier_but_coverage_is_required(self):
        outer_intervals = {
            "c1": (Fraction(0), Fraction(2)),
            "c2": (Fraction(1), Fraction(3)),
            "b0": (Fraction(-1), Fraction(1, 2)),
            "b1": (Fraction(5, 2), Fraction(4)),
            "b2": (Fraction(7, 2), Fraction(5)),
        }
        cores = {"c1", "c2"}
        values = {"b2": 1}
        outer = _worlds(outer_intervals, cores, 2, 2, "event")
        inner = _worlds(
            {row: interval for row, interval in outer_intervals.items() if row != "b2"},
            cores,
            2,
            2,
            "event",
        )
        self.assertTrue(inner.issubset(outer))
        self.assertEqual(_mean_range(inner, cores, values), (0, 0))
        self.assertEqual(_mean_range(outer, cores, values), (0, Fraction(1, 2)))

        threshold = Fraction(1, 4)
        self.assertEqual(_decision_status(_mean_range(inner, cores, values), threshold),
                         "CERTIFIED_NEGATIVE")
        self.assertEqual(_decision_status(_mean_range(outer, cores, values), threshold),
                         "AMBIGUOUS")
        omitted_truth = frozenset({frozenset({"c1", "c2", "b1", "b2"})})
        self.assertIn(omitted_truth, outer)
        self.assertNotIn(omitted_truth, inner)

    def test_decision_certification_boundary_conventions(self):
        threshold = Fraction(1)
        self.assertEqual(_decision_status((Fraction(1), Fraction(2)), threshold),
                         "CERTIFIED_POSITIVE")
        self.assertEqual(_decision_status((Fraction(0), Fraction(1, 2)), threshold),
                         "CERTIFIED_NEGATIVE")
        self.assertEqual(_decision_status((Fraction(0), Fraction(1)), threshold),
                         "AMBIGUOUS")

    def test_anytime_bounds_and_witnesses_need_not_be_optimal(self):
        threshold = Fraction(1)
        self.assertEqual(_anytime_certificate(threshold, minimum_lower=threshold),
                         "CERTIFIED_POSITIVE")
        self.assertEqual(
            _anytime_certificate(threshold, maximum_upper=Fraction(9, 10)),
            "CERTIFIED_NEGATIVE",
        )
        self.assertEqual(
            _anytime_certificate(
                threshold,
                feasible_values=(Fraction(1, 2), Fraction(3, 2)),
            ),
            "AMBIGUOUS",
        )
        self.assertEqual(
            _anytime_certificate(threshold, feasible_values=(Fraction(3, 2),)),
            "UNRESOLVED",
        )


if __name__ == "__main__":
    unittest.main()
