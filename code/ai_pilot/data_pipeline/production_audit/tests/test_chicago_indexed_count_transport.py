from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_chicago_k2_frontier as frontier
import live_chicago_k2_frontier_indexed_count as indexed


class IndexedCountTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        indexed._SEEN.clear()
        indexed._INDEX_CACHE.clear()

    def test_unique_id_enumeration_is_an_exact_below_cap_count(self) -> None:
        rows = [{"trip_id": "b"}, {"trip_id": "a"}]
        with patch.object(indexed, "_BASE_QUERY_ROWS", return_value=(rows, "fixture")):
            count, api, query = indexed.indexed_scalar_count("x = 1")
        self.assertEqual(count, 2)
        self.assertEqual(api, "fixture")
        self.assertIn("ORDER BY trip_id LIMIT 5001", query)

    def test_same_predicate_requires_stable_identities_not_only_count(self) -> None:
        with patch.object(
            indexed,
            "_BASE_QUERY_ROWS",
            side_effect=[([{"trip_id": "a"}], "fixture"), ([{"trip_id": "b"}], "fixture")],
        ):
            indexed.indexed_scalar_count("x = 1")
            with self.assertRaisesRegex(frontier.LiveDataError, "ID set changed"):
                indexed.indexed_scalar_count("x = 1")

    def test_null_and_duplicate_ids_fail_closed(self) -> None:
        for rows, message in [
            ([{"trip_id": None}], "null trip_id"),
            ([{"trip_id": "a"}, {"trip_id": "a"}], "duplicate trip IDs"),
        ]:
            with self.subTest(message=message):
                indexed._SEEN.clear()
                with patch.object(indexed, "_BASE_QUERY_ROWS", return_value=(rows, "fixture")):
                    with self.assertRaisesRegex(frontier.LiveDataError, message):
                        indexed.indexed_scalar_count("x = 1")

    def test_partition_index_reuses_the_just_counted_rows(self) -> None:
        rows = [{"trip_id": "a", "trip_start_timestamp": "2026-01-01T00:00:00"}]
        with patch.object(indexed, "_BASE_QUERY_ROWS", return_value=(rows, "fixture")) as base:
            indexed.indexed_scalar_count("x = 1")
            reused, api = indexed.cached_query_rows(
                "SELECT trip_id, trip_start_timestamp WHERE x = 1 LIMIT 1",
                page_size=1,
            )
        self.assertEqual(reused, rows)
        self.assertEqual(api, "fixture")
        self.assertEqual(base.call_count, 1)


if __name__ == "__main__":
    unittest.main()
