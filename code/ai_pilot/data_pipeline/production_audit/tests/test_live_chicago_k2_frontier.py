from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "live_chicago_k2_frontier.py"
SPEC = importlib.util.spec_from_file_location("live_chicago_k2_frontier", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ClosedEnvelopeTests(unittest.TestCase):
    def test_overlap_cutoffs_contain_every_possible_determinate_partner(self) -> None:
        core_starts = [
            datetime(2026, 1, 13, 18, 0),
            datetime(2026, 1, 13, 18, 0),
        ]
        core_ends = [
            datetime(2026, 1, 13, 18, 30),
            datetime(2026, 1, 13, 19, 0),
        ]
        lower_end, upper_start = MODULE.candidate_overlap_cutoffs(
            core_starts, core_ends
        )
        self.assertEqual(lower_end, datetime(2026, 1, 13, 17, 45))
        self.assertEqual(upper_start, datetime(2026, 1, 13, 19, 15))

        delta = timedelta(minutes=MODULE.ROUNDING_HALF_MINUTES)
        for start_minutes in range(-180, 181, 15):
            for duration_minutes in range(0, 241, 15):
                candidate_start = core_starts[0] + timedelta(minutes=start_minutes)
                candidate_end = candidate_start + timedelta(minutes=duration_minutes)
                candidate_outer = (
                    candidate_start - delta,
                    candidate_end + delta,
                )
                possible = any(
                    candidate_outer[0] <= core_end + delta
                    and core_start - delta <= candidate_outer[1]
                    for core_start, core_end in zip(core_starts, core_ends)
                )
                if possible:
                    self.assertLessEqual(candidate_start, upper_start)
                    self.assertGreaterEqual(candidate_end, lower_end)

    def test_cutoffs_reject_bad_core_intervals(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.candidate_overlap_cutoffs([], [])
        with self.assertRaises(ValueError):
            MODULE.candidate_overlap_cutoffs(
                [datetime(2026, 1, 1, 2, 0)],
                [datetime(2026, 1, 1, 1, 0)],
            )


class GraphAndOptimizationTests(unittest.TestCase):
    def setUp(self) -> None:
        now = datetime(2026, 1, 1, 12, 0)
        raw = []
        for index in range(4):
            raw.append(
                {
                    "trip_id": f"secret-{index}",
                    "trip_start_timestamp": "2026-01-01T12:00:00.000",
                    "trip_end_timestamp": "2026-01-01T12:30:00.000",
                    "trip_seconds": str(600 + index * 60),
                    "trip_miles": str(index + 1),
                    "pickup_community_area": "1",
                    "dropoff_community_area": str(index % 2),
                    "fare": str(10 + index),
                    "shared_trip_authorized": "true",
                    "shared_trip_match": "true",
                    "trips_pooled": "2",
                    "pickup_centroid_latitude": "41.88",
                    "pickup_centroid_longitude": str(-87.63 + index * 0.001),
                    "dropoff_centroid_latitude": "41.90",
                    "dropoff_centroid_longitude": str(-87.65 + index * 0.001),
                }
            )
        self.raw = raw
        self.rows, self.audit = MODULE.prepare_rows(
            raw,
            core_start=now,
            core_end=now + timedelta(minutes=15),
        )
        self.edges, _ = MODULE.build_temporal_edges(self.rows)

    def test_complete_four_core_graph_has_three_matchings_and_known_range(self) -> None:
        self.assertEqual(len(self.edges), 6)
        rows_by_index = {row.index: row for row in self.rows}
        spec = MODULE.query_specs()[0]
        lower, upper, missing = MODULE.edge_query_coefficients(
            rows_by_index, self.rows, self.edges, spec
        )
        self.assertEqual(missing, 0)
        assert lower is not None and upper is not None
        minimum = MODULE.solve_binary_cover_objective(
            self.rows,
            self.edges,
            lower,
            maximize=False,
            time_limit_seconds=10,
        )
        maximum = MODULE.solve_binary_cover_objective(
            self.rows,
            self.edges,
            upper,
            maximize=True,
            time_limit_seconds=10,
        )
        self.assertEqual(minimum.status, "OPTIMAL_NUMERICAL_MILP")
        self.assertEqual(maximum.status, "OPTIMAL_NUMERICAL_MILP")
        self.assertAlmostEqual(minimum.value, 1.0)
        self.assertAlmostEqual(maximum.value, 2.0)

    def test_radius_family_is_nested_and_missing_coordinates_are_retained(self) -> None:
        route = {edge: float(edge[1] - edge[0]) for edge in self.edges}
        first_edge = self.edges[0]
        route[first_edge] = None
        small, small_missing = MODULE.radius_graph(self.edges, route, 1.0)
        large, large_missing = MODULE.radius_graph(self.edges, route, 3.0)
        full, full_missing = MODULE.radius_graph(self.edges, route, None)
        self.assertIn(first_edge, small)
        self.assertTrue(set(small) <= set(large) <= set(full))
        self.assertEqual(small_missing, 1)
        self.assertEqual(large_missing, 1)
        self.assertEqual(full_missing, 1)

    def test_gamma_counts_core_incidences_not_deleted_edge_count(self) -> None:
        base = {self.edges[0]}
        costs = MODULE.edge_miss_costs(self.rows, self.edges, base)
        for edge, cost in zip(self.edges, costs):
            self.assertEqual(cost, 0 if edge in base else 2)
        zero = [0.0] * len(self.edges)
        infeasible = MODULE.solve_binary_cover_objective(
            self.rows,
            self.edges,
            zero,
            maximize=False,
            miss_costs=costs,
            gamma=0,
            time_limit_seconds=10,
        )
        feasible = MODULE.solve_binary_cover_objective(
            self.rows,
            self.edges,
            zero,
            maximize=False,
            miss_costs=costs,
            gamma=4,
            time_limit_seconds=10,
        )
        self.assertIn(
            infeasible.status,
            {"PROVEN_INFEASIBLE_BY_HIGHS", "PROVEN_INFEASIBLE_ISOLATED_CORE"},
        )
        self.assertEqual(feasible.status, "OPTIMAL_NUMERICAL_MILP")

    def test_categorical_missingness_uses_outer_zero_one_coefficients(self) -> None:
        rows = list(self.rows)
        first = rows[0]
        rows[0] = MODULE.TripRow(**{**first.__dict__, "dropoff_area": None})
        rows_by_index = {row.index: row for row in rows}
        spec = next(
            spec for spec in MODULE.query_specs() if spec.name.startswith("same_dropoff")
        )
        lower, upper, missing = MODULE.edge_query_coefficients(
            rows_by_index, rows, self.edges, spec
        )
        self.assertEqual(missing, 0)
        assert lower is not None and upper is not None
        incident = [position for position, edge in enumerate(self.edges) if 0 in edge]
        self.assertTrue(all(lower[position] == 0.0 for position in incident))
        self.assertTrue(
            all(upper[position] > lower[position] for position in incident)
        )

    def test_raw_identifiers_are_not_serialized_by_hash_contract(self) -> None:
        evidence = {
            "raw_rows_sha256": MODULE.stable_raw_rows_hash(self.raw),
            "raw_rows_emitted": False,
            "raw_trip_ids_emitted": False,
        }
        serialized = json.dumps(evidence)
        self.assertNotIn("secret-0", serialized)
        self.assertEqual(len(evidence["raw_rows_sha256"]), 64)


class MonotonicityTests(unittest.TestCase):
    def test_nested_endpoint_audit_passes_and_detects_reversal(self) -> None:
        rows = [
            {
                "curve_type": "gamma",
                "query": "q",
                "parameter_label": "0",
                "parameter_value": 0,
                "lower": 1.0,
                "upper": 2.0,
            },
            {
                "curve_type": "gamma",
                "query": "q",
                "parameter_label": "1",
                "parameter_value": 1,
                "lower": 0.5,
                "upper": 2.5,
            },
        ]
        self.assertEqual(MODULE.monotonicity_audit(rows)["status"], "PASS")
        rows[1]["upper"] = 1.5
        audit = MODULE.monotonicity_audit(rows)
        self.assertEqual(audit["status"], "FAIL")
        self.assertEqual(audit["violation_count"], 1)


if __name__ == "__main__":
    unittest.main()
