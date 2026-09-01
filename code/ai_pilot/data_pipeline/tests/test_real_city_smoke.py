import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "real_city_smoke.py"
spec = importlib.util.spec_from_file_location("real_city_smoke", MODULE_PATH)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smoke
spec.loader.exec_module(smoke)


class MatchingEndpointTests(unittest.TestCase):
    def setUp(self):
        now = datetime(2026, 1, 1, 12, 0)
        self.trips = [
            smoke.Trip(
                node_id=f"n{i}",
                start=now + timedelta(minutes=i),
                end=now + timedelta(minutes=20 + i),
                pickup="1",
                dropoff=str(i % 2),
                miles=float(i + 1),
                duration_seconds=float(600 + 60 * i),
                fare=float(10 + i),
            )
            for i in range(4)
        ]

    def test_complete_four_node_graph_has_three_worlds(self):
        result = smoke.matching_endpoint(
            self.trips,
            set(combinations(range(4), 2)),
            lambda left, right: abs(left.miles - right.miles),
        )
        self.assertEqual(result, (3, 1.0, 2.0))

    def test_sparse_graph_can_have_unique_world(self):
        result = smoke.matching_endpoint(
            self.trips, {(0, 1), (2, 3)}, lambda _left, _right: 0.0
        )
        self.assertEqual(result, (1, 0.0, 0.0))

    def test_odd_node_market_has_no_perfect_world(self):
        result = smoke.matching_endpoint(
            self.trips[:3], {(0, 1), (0, 2), (1, 2)}, lambda _left, _right: 0.0
        )
        self.assertEqual(result, (0, None, None))


class FixturePipelineTests(unittest.TestCase):
    def test_chicago_fixture_runs_without_exporting_raw_trip_ids(self):
        metadata = {
            "id": smoke.CHICAGO.dataset_id,
            "name": smoke.CHICAGO.dataset_name,
            "columns": [
                {"fieldName": field, "dataTypeName": "text", "position": index}
                for index, field in enumerate(smoke.CHICAGO.fields)
            ],
        }
        rows = [
            {
                "trip_id": f"raw-secret-{index}",
                "trip_start_timestamp": "2026-01-13T17:00:00.000",
                "trip_end_timestamp": "2026-01-13T17:30:00.000",
                "trip_seconds": str(1200 + index * 10),
                "trip_miles": str(3 + index / 10),
                "pickup_community_area": str(1 + index % 3),
                "dropoff_community_area": str(10 + index % 4),
                "fare": str(10 + index),
                "shared_trip_authorized": "true",
                "shared_trip_match": "true",
                "trips_pooled": "2",
            }
            for index in range(12)
        ]

        def fake_fetch(url, attempts=4, timeout=120):
            del attempts, timeout
            if "/api/views/" in url:
                return metadata
            if "count%28%2A%29" in url:
                return [{"n": str(len(rows))}]
            return rows

        with patch.object(smoke, "fetch_json", side_effect=fake_fetch):
            result = smoke.run_city(smoke.CHICAGO, limit=12, max_nodes=12)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            result["selected_market"]["temporal_candidate_worlds"], 10395
        )
        encoded = json.dumps(result)
        self.assertNotIn("raw-secret", encoded)
        self.assertEqual(result["schema"]["partner_key_candidates_present"], [])

    def test_nyc_schema_uses_full_2023_release(self):
        self.assertEqual(smoke.NYC.dataset_id, "u253-aew4")
        self.assertIn("shared_match_flag", smoke.NYC.fields)
        self.assertIn("trip_miles", smoke.NYC.fields)
        self.assertFalse(smoke.NYC.pair_size_known)

    def test_candidate_graph_is_explicitly_not_certified_outer_support(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("Illustrative candidate graph", source)
        self.assertIn("candidate-edge recall is not identified", source)
        self.assertNotIn('"outer_perfect_matching_worlds"', source)


if __name__ == "__main__":
    unittest.main()
