import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import temporal_frontier_profile as profile  # noqa: E402


class TemporalFrontierProfileTests(unittest.TestCase):
    def test_quick_matrix_covers_every_declared_axis(self):
        specs = profile.workload_specs("quick")
        self.assertEqual(len(specs), 23)
        self.assertEqual(
            {spec.axis for spec in specs},
            {
                "records",
                "candidate_degree",
                "factor_overlap",
                "label_support",
                "score_threshold",
                "gamma",
            },
        )
        self.assertEqual(len({spec.case_id for spec in specs}), len(specs))

    def test_three_order_constructors_are_deterministic_permutations(self):
        spec = next(
            item
            for item in profile.workload_specs("quick")
            if item.case_id == "factors_overlap03"
        )
        problem = profile.build_temporal_market(spec)
        first = profile.construct_schedule_candidates(problem)
        second = profile.construct_schedule_candidates(problem)
        expected_nodes = {node.node_id for node in problem.nodes}
        self.assertEqual(tuple(item.name for item in first), profile.ORDER_NAMES)
        self.assertEqual(
            tuple(item.forget_order for item in first),
            tuple(item.forget_order for item in second),
        )
        for candidate in first:
            self.assertEqual(set(candidate.forget_order), expected_nodes)
            self.assertEqual(len(candidate.forget_order), len(expected_nodes))

    def test_constructor_widths_and_factor_load_are_auditable(self):
        spec = next(
            item
            for item in profile.workload_specs("quick")
            if item.case_id == "factors_overlap03"
        )
        compiled = profile.compile_case(spec)
        candidates = {
            candidate.name: candidate for candidate in compiled.schedule_candidates
        }
        self.assertGreater(
            candidates["input_natural"].schedule.schedule_width,
            candidates["temporal_adjacent"].schedule.schedule_width,
        )
        self.assertLess(
            candidates["release_aware_greedy"].schedule.max_active_factor_count,
            candidates["temporal_adjacent"].schedule.max_active_factor_count,
        )
        self.assertEqual(compiled.selected_order_name, "temporal_adjacent")

    def test_requested_factor_overlap_is_realized_by_adjacent_order(self):
        for overlap in range(4):
            spec = next(
                item
                for item in profile.workload_specs("quick")
                if item.case_id == f"factors_overlap{overlap:02d}"
            )
            compiled = profile.compile_case(spec)
            adjacent = next(
                item
                for item in compiled.schedule_candidates
                if item.name == "temporal_adjacent"
            )
            self.assertEqual(
                adjacent.schedule.max_active_factor_count,
                overlap,
            )


if __name__ == "__main__":
    unittest.main()
