from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

MODULE_DIR = Path(__file__).resolve().parents[1]
BASE_PATH = MODULE_DIR / "live_chicago_k2_frontier.py"
BASE_SPEC = importlib.util.spec_from_file_location("live_chicago_k2_frontier", BASE_PATH)
assert BASE_SPEC is not None and BASE_SPEC.loader is not None
BASE = importlib.util.module_from_spec(BASE_SPEC)
sys.modules[BASE_SPEC.name] = BASE
BASE_SPEC.loader.exec_module(BASE)

WRAPPER_PATH = MODULE_DIR / "live_chicago_k2_frontier_partitioned.py"
WRAPPER_SPEC = importlib.util.spec_from_file_location(
    "live_chicago_k2_frontier_partitioned", WRAPPER_PATH
)
assert WRAPPER_SPEC is not None and WRAPPER_SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(WRAPPER_SPEC)
sys.modules[WRAPPER_SPEC.name] = WRAPPER
WRAPPER_SPEC.loader.exec_module(WRAPPER)


def full_row(trip_id: str, start: str, end: str) -> dict[str, str]:
    return {
        "trip_id": trip_id,
        "trip_start_timestamp": start,
        "trip_end_timestamp": end,
        "trip_seconds": "1200",
        "trip_miles": "3.5",
        "pickup_community_area": "8",
        "dropoff_community_area": "32",
        "fare": "12.50",
        "shared_trip_authorized": "true",
        "shared_trip_match": "true",
        "trips_pooled": "2",
        "pickup_centroid_latitude": "41.89",
        "pickup_centroid_longitude": "-87.63",
        "dropoff_centroid_latitude": "41.88",
        "dropoff_centroid_longitude": "-87.62",
    }


class PartitionedFetchTests(unittest.TestCase):
    def selected_fixture(self) -> dict:
        core_start = datetime(2026, 1, 13, 18, 0)
        core_rows = [
            full_row("core-a", "2026-01-13T18:00:00.000", "2026-01-13T18:30:00.000"),
            full_row("core-b", "2026-01-13T18:00:00.000", "2026-01-13T18:45:00.000"),
        ]
        return {
            "determinate_count": 4,
            "indeterminate_count": 0,
            "candidate_count": 4,
            "determinate_where": "shared_trip_match = true AND trips_pooled = 2",
            "indeterminate_where": (
                "shared_trip_match = true AND trips_pooled = 2 AND "
                "(trip_start_timestamp IS NULL OR trip_end_timestamp IS NULL)"
            ),
            "core_start": core_start,
            "core_rows": core_rows,
            "core_base_query": "SELECT core rows",
            "core_count_query": "SELECT count core rows",
            "core_page_apis": ["mock"],
            "core_count_api": "mock",
        }

    def test_narrow_index_is_partitioned_and_core_pull_is_reused(self) -> None:
        selected = self.selected_fixture()
        buffer_rows = [
            full_row("buffer-a", "2026-01-13T17:45:00.000", "2026-01-13T18:15:00.000"),
            full_row("buffer-b", "2026-01-13T17:45:00.000", "2026-01-13T18:30:00.000"),
        ]
        index_rows = [
            {"trip_id": "buffer-a", "trip_start_timestamp": "2026-01-13T17:45:00.000"},
            {"trip_id": "core-b", "trip_start_timestamp": "2026-01-13T18:00:00.000"},
            {"trip_id": "buffer-b", "trip_start_timestamp": "2026-01-13T17:45:00.000"},
            {"trip_id": "core-a", "trip_start_timestamp": "2026-01-13T18:00:00.000"},
        ]

        with patch.object(WRAPPER.frontier, "query_rows", return_value=(index_rows, "mock")) as query_rows, patch.object(
            WRAPPER.frontier,
            "scalar_count",
            return_value=(2, "mock", "SELECT count buffer"),
        ) as scalar_count, patch.object(
            WRAPPER.frontier,
            "paged_select",
            return_value=(buffer_rows, ["mock"], "SELECT buffer fields"),
        ) as paged_select:
            rows, ledger = WRAPPER.partitioned_fetch_closed_candidate_universe(
                selected, page_size=100
            )

        self.assertEqual(len(rows), 4)
        self.assertEqual(ledger["determinate"]["partition_count"], 2)
        sources = {
            partition["source"] for partition in ledger["determinate"]["partitions"]
        }
        self.assertEqual(
            sources,
            {"reused_integrity_checked_core_pull", "exact_released_start_partition"},
        )
        query_rows.assert_called_once()
        scalar_count.assert_called_once()
        paged_select.assert_called_once()
        serialized = json.dumps(ledger, sort_keys=True)
        for raw_id in ("core-a", "core-b", "buffer-a", "buffer-b"):
            self.assertNotIn(raw_id, serialized)

    def test_duplicate_index_identifier_fails_closed(self) -> None:
        selected = self.selected_fixture()
        duplicate_index = [
            {"trip_id": "same", "trip_start_timestamp": "2026-01-13T18:00:00.000"},
            {"trip_id": "same", "trip_start_timestamp": "2026-01-13T18:00:00.000"},
            {"trip_id": "x", "trip_start_timestamp": "2026-01-13T17:45:00.000"},
            {"trip_id": "y", "trip_start_timestamp": "2026-01-13T17:45:00.000"},
        ]
        with patch.object(
            WRAPPER.frontier, "query_rows", return_value=(duplicate_index, "mock")
        ):
            with self.assertRaises(WRAPPER.frontier.LiveDataError):
                WRAPPER.partitioned_fetch_closed_candidate_universe(
                    selected, page_size=100
                )

    def test_partition_count_mismatch_fails_closed(self) -> None:
        selected = self.selected_fixture()
        index_rows = [
            {"trip_id": "buffer-a", "trip_start_timestamp": "2026-01-13T17:45:00.000"},
            {"trip_id": "buffer-b", "trip_start_timestamp": "2026-01-13T17:45:00.000"},
            {"trip_id": "core-a", "trip_start_timestamp": "2026-01-13T18:00:00.000"},
            {"trip_id": "core-b", "trip_start_timestamp": "2026-01-13T18:00:00.000"},
        ]
        with patch.object(WRAPPER.frontier, "query_rows", return_value=(index_rows, "mock")), patch.object(
            WRAPPER.frontier,
            "scalar_count",
            return_value=(1, "mock", "SELECT bad count"),
        ):
            with self.assertRaises(WRAPPER.frontier.LiveDataError):
                WRAPPER.partitioned_fetch_closed_candidate_universe(
                    selected, page_size=100
                )

    def test_indeterminate_rows_are_fetched_in_small_id_batches(self) -> None:
        selected = self.selected_fixture()
        selected["determinate_count"] = 2
        selected["candidate_count"] = 4
        selected["indeterminate_count"] = 2
        determinate_index = [
            {"trip_id": "core-a", "trip_start_timestamp": "2026-01-13T18:00:00.000"},
            {"trip_id": "core-b", "trip_start_timestamp": "2026-01-13T18:00:00.000"},
        ]
        indeterminate_index = [
            {"trip_id": "null-a", "trip_start_timestamp": None, "trip_end_timestamp": "2026-01-13T18:30:00.000"},
            {"trip_id": "null-b", "trip_start_timestamp": "2026-01-13T17:45:00.000", "trip_end_timestamp": None},
        ]
        null_rows = [
            full_row("null-a", "", "2026-01-13T18:30:00.000"),
            full_row("null-b", "2026-01-13T17:45:00.000", ""),
        ]
        query_results = [
            (determinate_index, "mock"),
            (indeterminate_index, "mock"),
        ]
        with patch.object(
            WRAPPER.frontier, "query_rows", side_effect=query_results
        ), patch.object(
            WRAPPER.frontier,
            "scalar_count",
            return_value=(2, "mock", "SELECT count null batch"),
        ), patch.object(
            WRAPPER.frontier,
            "paged_select",
            return_value=(null_rows, ["mock"], "SELECT null rows"),
        ):
            rows, ledger = WRAPPER.partitioned_fetch_closed_candidate_universe(
                selected, page_size=100
            )
        self.assertEqual(len(rows), 4)
        self.assertEqual(ledger["indeterminate"]["batch_count"], 1)
        self.assertNotIn("null-a", json.dumps(ledger, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
