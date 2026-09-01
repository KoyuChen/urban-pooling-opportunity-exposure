from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
BASE_PATH = MODULE_DIR / "live_chicago_k2_frontier.py"
BASE_SPEC = importlib.util.spec_from_file_location("live_chicago_k2_frontier", BASE_PATH)
assert BASE_SPEC is not None and BASE_SPEC.loader is not None
BASE = importlib.util.module_from_spec(BASE_SPEC)
sys.modules[BASE_SPEC.name] = BASE
BASE_SPEC.loader.exec_module(BASE)

PARTITIONED_PATH = MODULE_DIR / "live_chicago_k2_frontier_partitioned.py"
PARTITIONED_SPEC = importlib.util.spec_from_file_location(
    "live_chicago_k2_frontier_partitioned", PARTITIONED_PATH
)
assert PARTITIONED_SPEC is not None and PARTITIONED_SPEC.loader is not None
PARTITIONED = importlib.util.module_from_spec(PARTITIONED_SPEC)
sys.modules[PARTITIONED_SPEC.name] = PARTITIONED
PARTITIONED_SPEC.loader.exec_module(PARTITIONED)

CERTIFIED_PATH = MODULE_DIR / "live_chicago_k2_frontier_certified.py"
CERTIFIED_SPEC = importlib.util.spec_from_file_location(
    "live_chicago_k2_frontier_certified", CERTIFIED_PATH
)
assert CERTIFIED_SPEC is not None and CERTIFIED_SPEC.loader is not None
CERTIFIED = importlib.util.module_from_spec(CERTIFIED_SPEC)
sys.modules[CERTIFIED_SPEC.name] = CERTIFIED
CERTIFIED_SPEC.loader.exec_module(CERTIFIED)


def fixture_rows() -> list:
    start = datetime(2026, 1, 1, 12, 0)
    raw = []
    for index in range(4):
        raw.append(
            {
                "trip_id": f"fixture-{index}",
                "trip_start_timestamp": "2026-01-01T12:00:00.000",
                "trip_end_timestamp": "2026-01-01T12:30:00.000",
                "trip_seconds": str(600 + 60 * index),
                "trip_miles": str(1 + index),
                "pickup_community_area": "1",
                "dropoff_community_area": str(index % 2),
                "fare": str(10 + index),
                "shared_trip_authorized": "true",
                "shared_trip_match": "true",
                "trips_pooled": "2",
                "pickup_centroid_latitude": "41.88",
                "pickup_centroid_longitude": str(-87.63 + 0.01 * index),
                "dropoff_centroid_latitude": "41.90",
                "dropoff_centroid_longitude": str(-87.65 + 0.01 * index),
            }
        )
    rows, _ = BASE.prepare_rows(
        raw, core_start=start, core_end=start + timedelta(minutes=15)
    )
    return rows


class CertifiedGammaEndpointTests(unittest.TestCase):
    def test_gamma_zero_uses_zero_cost_subgraph_and_matches_base(self) -> None:
        rows = fixture_rows()
        temporal_edges, _ = BASE.build_temporal_edges(rows)
        base_edges = [edge for position, edge in enumerate(temporal_edges) if position < 3]
        base_set = set(base_edges)
        costs = BASE.edge_miss_costs(rows, temporal_edges, base_set)

        base_graph, base_queries = CERTIFIED._ORIGINAL_SOLVE_CURVE_POINT(
            rows=rows,
            edges=base_edges,
            temporal_edge_count=len(temporal_edges),
            unmeasured_edges=0,
            curve_type="radius",
            parameter_label="2 km",
            parameter_value=2.0,
            radius_km=2.0,
            gamma=None,
            miss_costs=None,
            time_limit_seconds=10,
        )
        gamma_graph, gamma_queries = (
            CERTIFIED.solve_curve_point_with_exact_gamma_endpoints(
                rows=rows,
                edges=temporal_edges,
                temporal_edge_count=len(temporal_edges),
                unmeasured_edges=0,
                curve_type="gamma",
                parameter_label="0",
                parameter_value=0.0,
                radius_km=2.0,
                gamma=0,
                miss_costs=costs,
                time_limit_seconds=10,
            )
        )
        self.assertEqual(gamma_graph.gamma_core_incidences, 0)
        self.assertEqual(gamma_graph.edge_count, base_graph.edge_count)
        base_by_query = {row["query"]: row for row in base_queries}
        gamma_by_query = {row["query"]: row for row in gamma_queries}
        self.assertEqual(set(base_by_query), set(gamma_by_query))
        for query in base_by_query:
            for field in ("lower", "upper", "width", "lower_status", "upper_status"):
                self.assertEqual(base_by_query[query][field], gamma_by_query[query][field])
            self.assertEqual(gamma_by_query[query]["gamma_core_incidences"], 0)

    def test_gamma_core_count_uses_unconstrained_temporal_formulation(self) -> None:
        rows = fixture_rows()
        temporal_edges, _ = BASE.build_temporal_edges(rows)
        base_set = {temporal_edges[0]}
        costs = BASE.edge_miss_costs(rows, temporal_edges, base_set)
        core_count = sum(row.role == "core" for row in rows)

        temporal_graph, temporal_queries = CERTIFIED._ORIGINAL_SOLVE_CURVE_POINT(
            rows=rows,
            edges=temporal_edges,
            temporal_edge_count=len(temporal_edges),
            unmeasured_edges=0,
            curve_type="radius",
            parameter_label="temporal-only",
            parameter_value=None,
            radius_km=None,
            gamma=None,
            miss_costs=None,
            time_limit_seconds=10,
        )
        gamma_graph, gamma_queries = (
            CERTIFIED.solve_curve_point_with_exact_gamma_endpoints(
                rows=rows,
                edges=temporal_edges,
                temporal_edge_count=len(temporal_edges),
                unmeasured_edges=0,
                curve_type="gamma",
                parameter_label=str(core_count),
                parameter_value=float(core_count),
                radius_km=2.0,
                gamma=core_count,
                miss_costs=costs,
                time_limit_seconds=10,
            )
        )
        self.assertEqual(gamma_graph.gamma_core_incidences, core_count)
        self.assertEqual(gamma_graph.edge_count, temporal_graph.edge_count)
        temporal_by_query = {row["query"]: row for row in temporal_queries}
        gamma_by_query = {row["query"]: row for row in gamma_queries}
        for query in temporal_by_query:
            for field in ("lower", "upper", "width", "lower_status", "upper_status"):
                self.assertEqual(temporal_by_query[query][field], gamma_by_query[query][field])
            self.assertEqual(
                gamma_by_query[query]["gamma_core_incidences"], core_count
            )

    def test_intermediate_gamma_keeps_budgeted_full_graph(self) -> None:
        rows = fixture_rows()
        temporal_edges, _ = BASE.build_temporal_edges(rows)
        costs = BASE.edge_miss_costs(rows, temporal_edges, {temporal_edges[0]})
        graph, query_rows = CERTIFIED.solve_curve_point_with_exact_gamma_endpoints(
            rows=rows,
            edges=temporal_edges,
            temporal_edge_count=len(temporal_edges),
            unmeasured_edges=0,
            curve_type="gamma",
            parameter_label="1",
            parameter_value=1.0,
            radius_km=2.0,
            gamma=1,
            miss_costs=costs,
            time_limit_seconds=10,
        )
        self.assertEqual(graph.gamma_core_incidences, 1)
        self.assertEqual(graph.edge_count, len(temporal_edges))
        self.assertTrue(query_rows)


if __name__ == "__main__":
    unittest.main()
