from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from dataclasses import asdict
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

    def test_core_buffer_out_of_radius_edge_costs_one(self) -> None:
        rows = list(self.rows)
        rows[3] = MODULE.TripRow(**{**rows[3].__dict__, "role": "buffer"})
        edges = [(0, 1), (0, 3)]
        self.assertEqual(
            MODULE.edge_miss_costs(rows, edges, set()),
            [2, 1],
        )
        self.assertEqual(
            MODULE.edge_miss_costs(rows, edges, {(0, 3)}),
            [2, 0],
        )

    def test_forced_zero_missing_edge_does_not_poison_gamma_zero_query(self) -> None:
        rows = list(self.rows)
        rows[3] = MODULE.TripRow(**{**rows[3].__dict__, "miles": None})
        rows_by_index = {row.index: row for row in rows}
        spec = MODULE.query_specs()[0]
        lower, upper, missing = MODULE.edge_query_coefficients(
            rows_by_index,
            rows,
            [(0, 1), (2, 3)],
            spec,
            forced_zero_edges=[False, True],
        )
        self.assertEqual(missing, 0)
        assert lower is not None and upper is not None
        self.assertEqual(lower[1], 0.0)
        self.assertEqual(upper[1], 0.0)

    def test_gamma_endpoints_match_radius_endpoints_and_cost_audit_is_structural(self) -> None:
        base_edges = [(0, 1), (2, 3)]
        base_set = set(base_edges)
        costs = MODULE.edge_miss_costs(self.rows, self.edges, base_set)

        def point(
            *,
            edges: list[tuple[int, int]],
            curve_type: str,
            label: str,
            value: float | None,
            radius: float | None,
            gamma: int | None,
            point_costs: list[int] | None,
        ) -> tuple[dict, list[dict]]:
            graph_point, query_rows = MODULE.solve_curve_point(
                rows=self.rows,
                edges=edges,
                temporal_edge_count=len(self.edges),
                unmeasured_edges=0,
                curve_type=curve_type,
                parameter_label=label,
                parameter_value=value,
                radius_km=radius,
                gamma=gamma,
                miss_costs=point_costs,
                time_limit_seconds=10,
            )
            return asdict(graph_point), query_rows

        base_graph, base_rows = point(
            edges=base_edges,
            curve_type="radius",
            label="1 km",
            value=1.0,
            radius=1.0,
            gamma=None,
            point_costs=None,
        )
        temporal_graph, temporal_rows = point(
            edges=self.edges,
            curve_type="radius",
            label="temporal-only",
            value=None,
            radius=None,
            gamma=None,
            point_costs=None,
        )
        gamma_zero_point, gamma_zero_rows = MODULE.reuse_radius_endpoint_for_gamma(
            source_graph_point=base_graph,
            source_query_rows=base_rows,
            rows=self.rows,
            temporal_edges=self.edges,
            unmeasured_edges=0,
            gamma=0,
            base_radius_km=1.0,
        )
        gamma_full_point, gamma_full_rows = MODULE.reuse_radius_endpoint_for_gamma(
            source_graph_point=temporal_graph,
            source_query_rows=temporal_rows,
            rows=self.rows,
            temporal_edges=self.edges,
            unmeasured_edges=0,
            gamma=4,
            base_radius_km=1.0,
        )
        gamma_zero_graph = asdict(gamma_zero_point)
        gamma_full_graph = asdict(gamma_full_point)
        self.assertEqual(gamma_zero_graph["edge_count"], len(self.edges))
        self.assertEqual(gamma_zero_rows[0]["lower"], base_rows[0]["lower"])
        self.assertEqual(gamma_full_rows[0]["upper"], temporal_rows[0]["upper"])
        self.assertEqual(
            gamma_zero_rows[0]["endpoint_source"],
            "canonical_base_radius_identity",
        )
        self.assertEqual(
            gamma_full_rows[0]["endpoint_source"],
            "canonical_temporal_only_identity",
        )
        self.assertEqual(base_rows[0]["endpoint_source"], "direct_milp")
        sensitivity = [
            *base_rows,
            *temporal_rows,
            *gamma_zero_rows,
            *gamma_full_rows,
        ]
        graph_radius = [base_graph, temporal_graph]
        graph_gamma = [gamma_zero_graph, gamma_full_graph]
        audit = MODULE.endpoint_identity_audit(
            sensitivity,
            graph_radius,
            graph_gamma,
            model_rows=self.rows,
            temporal_edges=self.edges,
            base_edges=base_edges,
            miss_costs=costs,
            base_radius_km=1.0,
            core_count=4,
        )
        self.assertEqual(audit["status"], "PASS", audit)

        tampered = MODULE.endpoint_identity_audit(
            sensitivity,
            graph_radius,
            graph_gamma,
            model_rows=self.rows,
            temporal_edges=self.edges,
            base_edges=base_edges,
            miss_costs=[0] * len(self.edges),
            base_radius_km=1.0,
            core_count=4,
        )
        self.assertEqual(tampered["status"], "FAIL")
        self.assertTrue(
            any(
                mismatch["reason"]
                == "incorrect_measured_out_of_radius_incidence_cost"
                for mismatch in tampered["mismatches"]
            )
        )

    def test_curve_point_rejects_unpaired_gamma_and_miss_costs(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.solve_curve_point(
                rows=self.rows,
                edges=self.edges,
                temporal_edge_count=len(self.edges),
                unmeasured_edges=0,
                curve_type="gamma",
                parameter_label="0",
                parameter_value=0.0,
                radius_km=1.0,
                gamma=0,
                miss_costs=None,
                time_limit_seconds=10,
            )

    def test_radius_selector_never_coerces_temporal_only_none(self) -> None:
        self.assertTrue(MODULE.same_radius_parameter(None, None))
        self.assertFalse(MODULE.same_radius_parameter(None, 2.0))
        self.assertFalse(MODULE.same_radius_parameter(2.0, None))
        self.assertTrue(MODULE.same_radius_parameter("2.0", 2.0))
        self.assertFalse(MODULE.same_radius_parameter("bad", 2.0))

    def test_endpoint_identity_normalizes_certified_infeasibility_backends(self) -> None:
        base_edges = [(0, 1)]
        costs = MODULE.edge_miss_costs(self.rows, self.edges, set(base_edges))

        def graph(
            curve: str,
            *,
            radius: float | None,
            gamma: int | None,
            status: str,
        ) -> dict:
            return {
                "curve_type": curve,
                "radius_km": radius,
                "gamma_core_incidences": gamma,
                "cover_status": status,
            }

        def query_row(
            curve: str,
            *,
            radius: float | None,
            gamma: int | None,
            status: str,
            lower: float | None,
            upper: float | None,
        ) -> dict:
            certified = status == "OPTIMAL_NUMERICAL_MILP"
            return {
                "curve_type": curve,
                "query": "q",
                "radius_km": radius,
                "gamma_core_incidences": gamma,
                "lower_status": status,
                "upper_status": status,
                "endpoint_pair_certification": (
                    "CERTIFIED_OPTIMAL_PAIR" if certified else "UNCERTIFIED"
                ),
                "lower": lower,
                "upper": upper,
                "width": (
                    upper - lower
                    if lower is not None and upper is not None
                    else None
                ),
            }

        infeasible_radius = "PROVEN_INFEASIBLE_ISOLATED_CORE"
        infeasible_gamma = "PROVEN_INFEASIBLE_BY_HIGHS"
        optimal = "OPTIMAL_NUMERICAL_MILP"
        radius_graphs = [
            graph("radius", radius=1.0, gamma=None, status=infeasible_radius),
            graph("radius", radius=None, gamma=None, status=optimal),
        ]
        gamma_graphs = [
            graph("gamma", radius=1.0, gamma=0, status=infeasible_gamma),
            graph("gamma", radius=1.0, gamma=4, status=optimal),
        ]
        sensitivity = [
            query_row(
                "radius",
                radius=1.0,
                gamma=None,
                status=infeasible_radius,
                lower=None,
                upper=None,
            ),
            query_row(
                "radius",
                radius=None,
                gamma=None,
                status=optimal,
                lower=1.0,
                upper=2.0,
            ),
            query_row(
                "gamma",
                radius=1.0,
                gamma=0,
                status=infeasible_gamma,
                lower=None,
                upper=None,
            ),
            query_row(
                "gamma",
                radius=1.0,
                gamma=4,
                status=optimal,
                lower=1.0,
                upper=2.0,
            ),
        ]
        audit = MODULE.endpoint_identity_audit(
            sensitivity,
            radius_graphs,
            gamma_graphs,
            model_rows=self.rows,
            temporal_edges=self.edges,
            base_edges=base_edges,
            miss_costs=costs,
            base_radius_km=1.0,
            core_count=4,
        )
        self.assertEqual(audit["status"], "PASS", audit)

    def test_endpoint_identity_accepts_exact_canonical_unresolved_state(self) -> None:
        base_edges = [(0, 1), (2, 3)]
        costs = MODULE.edge_miss_costs(self.rows, self.edges, set(base_edges))

        def solved(edges: list[tuple[int, int]], radius: float | None):
            point, rows = MODULE.solve_curve_point(
                rows=self.rows,
                edges=edges,
                temporal_edge_count=len(self.edges),
                unmeasured_edges=0,
                curve_type="radius",
                parameter_label="temporal-only" if radius is None else "1 km",
                parameter_value=radius,
                radius_km=radius,
                gamma=None,
                miss_costs=None,
                time_limit_seconds=10,
            )
            return asdict(point), rows

        base_graph, base_rows = solved(base_edges, 1.0)
        temporal_graph, temporal_rows = solved(self.edges, None)
        for row in temporal_rows:
            row.update(
                lower=None,
                upper=None,
                width=None,
                lower_status="INCUMBENT_ONLY_UNRESOLVED_LIMIT",
                upper_status="INCUMBENT_ONLY_UNRESOLVED_LIMIT",
                endpoint_pair_certification="UNCERTIFIED",
                diagnostic_lower_nonoptimal_incumbent=1.0,
                diagnostic_upper_nonoptimal_incumbent=2.0,
            )
        gamma_zero, gamma_zero_rows = MODULE.reuse_radius_endpoint_for_gamma(
            source_graph_point=base_graph,
            source_query_rows=base_rows,
            rows=self.rows,
            temporal_edges=self.edges,
            unmeasured_edges=0,
            gamma=0,
            base_radius_km=1.0,
        )
        gamma_full, gamma_full_rows = MODULE.reuse_radius_endpoint_for_gamma(
            source_graph_point=temporal_graph,
            source_query_rows=temporal_rows,
            rows=self.rows,
            temporal_edges=self.edges,
            unmeasured_edges=0,
            gamma=4,
            base_radius_km=1.0,
        )
        audit = MODULE.endpoint_identity_audit(
            [*base_rows, *temporal_rows, *gamma_zero_rows, *gamma_full_rows],
            [base_graph, temporal_graph],
            [asdict(gamma_zero), asdict(gamma_full)],
            model_rows=self.rows,
            temporal_edges=self.edges,
            base_edges=base_edges,
            miss_costs=costs,
            base_radius_km=1.0,
            core_count=4,
        )
        self.assertEqual(audit["status"], "PASS", audit)
        gamma_full_rows[0]["endpoint_source"] = "direct_milp"
        tampered = MODULE.endpoint_identity_audit(
            [*base_rows, *temporal_rows, *gamma_zero_rows, *gamma_full_rows],
            [base_graph, temporal_graph],
            [asdict(gamma_zero), asdict(gamma_full)],
            model_rows=self.rows,
            temporal_edges=self.edges,
            base_edges=base_edges,
            miss_costs=costs,
            base_radius_km=1.0,
            core_count=4,
        )
        self.assertEqual(tampered["status"], "FAIL")

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
    @staticmethod
    def row(
        *,
        query: str = "q",
        label: str,
        value: float,
        lower: float | None,
        upper: float | None,
        lower_status: str = "OPTIMAL_NUMERICAL_MILP",
        upper_status: str = "OPTIMAL_NUMERICAL_MILP",
        certification: str = "CERTIFIED_OPTIMAL_PAIR",
        width: float | None = None,
    ) -> dict:
        return {
            "curve_type": "gamma",
            "query": query,
            "parameter_label": label,
            "parameter_value": value,
            "lower": lower,
            "upper": upper,
            "width": (
                upper - lower
                if width is None and lower is not None and upper is not None
                else width
            ),
            "lower_status": lower_status,
            "upper_status": upper_status,
            "endpoint_pair_certification": certification,
        }

    def test_nested_endpoint_audit_passes_and_detects_reversal(self) -> None:
        rows = [
            self.row(label="0", value=0, lower=1.0, upper=2.0),
            self.row(label="1", value=1, lower=0.5, upper=2.5),
        ]
        self.assertEqual(MODULE.monotonicity_audit(rows)["status"], "PASS")
        rows[1]["upper"] = 1.5
        rows[1]["width"] = 1.0
        audit = MODULE.monotonicity_audit(rows)
        self.assertEqual(audit["status"], "FAIL")
        self.assertEqual(audit["violation_count"], 1)

    def test_empty_all_none_and_nonoptimal_chains_fail(self) -> None:
        self.assertEqual(MODULE.monotonicity_audit([])["status"], "FAIL")
        unavailable = [
            self.row(
                label=str(value),
                value=value,
                lower=None,
                upper=None,
                lower_status="UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES",
                upper_status="UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES",
                certification="UNCERTIFIED",
            )
            for value in (0, 1)
        ]
        self.assertEqual(
            MODULE.monotonicity_audit(unavailable)["status"],
            "FAIL",
        )
        nonoptimal = [
            self.row(label="0", value=0, lower=1.0, upper=2.0),
            self.row(
                label="1",
                value=1,
                lower=0.5,
                upper=2.5,
                lower_status="INCUMBENT_ONLY_UNRESOLVED_LIMIT",
                certification="UNCERTIFIED",
            ),
        ]
        self.assertEqual(MODULE.monotonicity_audit(nonoptimal)["status"], "FAIL")

    def test_nonfinite_invalid_interval_and_stale_width_fail(self) -> None:
        valid = self.row(label="0", value=0, lower=1.0, upper=2.0)
        nonfinite = self.row(label="1", value=1, lower=0.5, upper=float("inf"))
        self.assertEqual(
            MODULE.monotonicity_audit([valid, nonfinite])["status"],
            "FAIL",
        )
        invalid = self.row(label="1", value=1, lower=3.0, upper=2.5)
        invalid_audit = MODULE.monotonicity_audit([valid, invalid])
        self.assertEqual(invalid_audit["status"], "FAIL")
        self.assertTrue(
            any(
                violation["direction"] == "lower_exceeds_upper"
                for violation in invalid_audit["violations"]
            )
        )
        stale = self.row(
            label="1",
            value=1,
            lower=0.5,
            upper=2.5,
            width=99.0,
        )
        self.assertEqual(
            MODULE.monotonicity_audit([valid, stale])["status"],
            "FAIL",
        )

    def test_partial_requires_a_whole_good_chain_and_never_masks_reversal(self) -> None:
        good = [
            self.row(query="good", label="0", value=0, lower=1.0, upper=2.0),
            self.row(query="good", label="1", value=1, lower=0.5, upper=2.5),
        ]
        incomplete = [
            self.row(query="missing", label="0", value=0, lower=1.0, upper=2.0),
            self.row(
                query="missing",
                label="1",
                value=1,
                lower=None,
                upper=None,
                lower_status="UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES",
                upper_status="UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES",
                certification="UNCERTIFIED",
            ),
        ]
        partial = MODULE.monotonicity_audit([*good, *incomplete])
        self.assertEqual(partial["status"], "PARTIAL")
        self.assertEqual(partial["fully_certified_monotone_chain_count"], 1)

        reversal = [
            self.row(query="bad", label="0", value=0, lower=1.0, upper=2.0),
            self.row(query="bad", label="1", value=1, lower=1.5, upper=2.5),
        ]
        self.assertEqual(
            MODULE.monotonicity_audit([*good, *reversal])["status"],
            "FAIL",
        )

    def test_expected_chain_completeness_prevents_vacuous_pass(self) -> None:
        rows = [
            self.row(query="present", label="0", value=0, lower=1.0, upper=2.0),
            self.row(query="present", label="1", value=1, lower=0.5, upper=2.5),
        ]
        audit = MODULE.monotonicity_audit(
            rows,
            expected_parameter_labels={"gamma": ["0", "1"]},
            expected_queries=["present", "absent"],
        )
        self.assertEqual(audit["status"], "PARTIAL")
        self.assertEqual(audit["fully_certified_monotone_chain_count"], 1)
        missing_point = MODULE.monotonicity_audit(
            rows[:1],
            expected_parameter_labels={"gamma": ["0", "1"]},
            expected_queries=["present"],
        )
        self.assertEqual(missing_point["status"], "FAIL")


class CertificationAndClosureTests(unittest.TestCase):
    @staticmethod
    def bound(status: str, value: float | None) -> object:
        return MODULE.BoundResult(status, value, "test", None, None, 0.0, 1, "")

    def test_only_ordered_optimal_pairs_are_published(self) -> None:
        certified = MODULE.certified_endpoint_payload(
            self.bound("OPTIMAL_NUMERICAL_MILP", 1.0),
            self.bound("OPTIMAL_NUMERICAL_MILP", 2.0),
        )
        self.assertEqual(certified["lower"], 1.0)
        self.assertEqual(certified["upper"], 2.0)
        self.assertEqual(certified["width"], 1.0)

        incumbent = MODULE.certified_endpoint_payload(
            self.bound("INCUMBENT_ONLY_UNRESOLVED_LIMIT", 1.0),
            self.bound("OPTIMAL_NUMERICAL_MILP", 2.0),
        )
        self.assertIsNone(incumbent["lower"])
        self.assertIsNone(incumbent["upper"])
        self.assertIsNone(incumbent["width"])
        self.assertEqual(incumbent["diagnostic_lower_nonoptimal_incumbent"], 1.0)

        reversed_pair = MODULE.certified_endpoint_payload(
            self.bound("OPTIMAL_NUMERICAL_MILP", 3.0),
            self.bound("OPTIMAL_NUMERICAL_MILP", 2.0),
        )
        self.assertEqual(reversed_pair["endpoint_pair_certification"], "UNCERTIFIED")
        self.assertIsNone(reversed_pair["width"])

    def test_closure_requires_possible_chronology_and_optimal_full_cover(self) -> None:
        kwargs = {
            "snapshot_stable": True,
            "server_counts_stable": True,
            "core_subset_verified": True,
            "candidate_rows": 4,
            "expected_candidate_rows": 4,
            "observed_indeterminate_rows": 0,
            "expected_indeterminate_rows": 0,
            "off_release_grid_rows": 0,
            "released_chronology_impossible_rows": 0,
            "context_rows": 0,
            "full_temporal_cover_status": "OPTIMAL_NUMERICAL_MILP",
        }
        self.assertEqual(
            MODULE.public_temporal_closure_audit(**kwargs)["status"],
            "PASS",
        )
        impossible = dict(kwargs, released_chronology_impossible_rows=1)
        self.assertEqual(
            MODULE.public_temporal_closure_audit(**impossible)["status"],
            "FAIL",
        )
        nonoptimal = dict(
            kwargs,
            full_temporal_cover_status="INCUMBENT_ONLY_UNRESOLVED_LIMIT",
        )
        self.assertEqual(
            MODULE.public_temporal_closure_audit(**nonoptimal)["status"],
            "FAIL",
        )


if __name__ == "__main__":
    unittest.main()
