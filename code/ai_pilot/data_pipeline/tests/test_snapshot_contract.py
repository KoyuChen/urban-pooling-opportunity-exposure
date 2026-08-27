import sys
import unittest
from copy import deepcopy
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from fetch_complete_authorized_days import (  # noqa: E402
    DATASET_ID,
    dataset_snapshot,
    snapshots_match,
)


def fixture_metadata():
    return {
        "id": DATASET_ID,
        "name": "Transportation Network Providers - Trips (2025-)",
        "rowsUpdatedAt": 1780000000,
        "viewLastModified": 1780000100,
        "publicationDate": 1740000000,
        "viewCount": 10,
        "columns": [
            {
                "position": 2,
                "fieldName": "shared_trip_match",
                "dataTypeName": "checkbox",
            },
            {
                "position": 1,
                "fieldName": "trip_id",
                "dataTypeName": "text",
            },
        ],
    }


class DatasetSnapshotContractTests(unittest.TestCase):
    def test_volatile_portal_counters_do_not_change_revision(self):
        first = fixture_metadata()
        second = deepcopy(first)
        second["viewCount"] = 999
        self.assertTrue(
            snapshots_match(dataset_snapshot(first), dataset_snapshot(second))
        )

    def test_row_revision_and_schema_drift_are_detected(self):
        base = fixture_metadata()
        row_drift = deepcopy(base)
        row_drift["rowsUpdatedAt"] += 1
        self.assertFalse(
            snapshots_match(dataset_snapshot(base), dataset_snapshot(row_drift))
        )

        schema_drift = deepcopy(base)
        schema_drift["columns"][0]["dataTypeName"] = "text"
        self.assertFalse(
            snapshots_match(dataset_snapshot(base), dataset_snapshot(schema_drift))
        )

    def test_column_order_is_canonical_but_positions_are_not_discarded(self):
        base = fixture_metadata()
        reordered = deepcopy(base)
        reordered["columns"].reverse()
        self.assertEqual(dataset_snapshot(base), dataset_snapshot(reordered))

        moved = deepcopy(base)
        moved["columns"][0]["position"] = 3
        self.assertNotEqual(dataset_snapshot(base), dataset_snapshot(moved))

    def test_wrong_dataset_and_malformed_columns_are_rejected(self):
        wrong = fixture_metadata()
        wrong["id"] = "wrong-id"
        with self.assertRaisesRegex(ValueError, "metadata id"):
            dataset_snapshot(wrong)

        malformed = fixture_metadata()
        malformed["columns"] = []
        with self.assertRaisesRegex(ValueError, "columns"):
            dataset_snapshot(malformed)


if __name__ == "__main__":
    unittest.main()
