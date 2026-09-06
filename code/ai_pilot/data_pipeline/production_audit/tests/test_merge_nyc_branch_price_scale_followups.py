from __future__ import annotations

import sys
import unittest
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

import merge_nyc_branch_price_scale_followups as merger


def cell(core: int, capacity: int, value: float, *, certified: bool) -> dict:
    return {
        "core_rows": core,
        "buffer_rows": 3 * core,
        "capacity": capacity,
        "status": (
            "INTEGER_OPTIMUM_CERTIFIED"
            if certified
            else "INTEGER_BRANCH_AND_PRICE_UNRESOLVED"
        ),
        "integer_maximum_selected_buffers": value if certified else None,
        "global_lower_bound": value,
        "global_upper_bound": value if certified else value + 1,
    }


def report(cells: list[dict]) -> dict:
    return {
        "snapshot": {"revision": "fixed"},
        "cohort": {"provider": "HV0005"},
        "generated_at_utc": "2026-09-06T00:00:00+00:00",
        "cells": cells,
    }


class MergeNycBranchPriceScaleFollowupsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = report([cell(10, 4, 27, certified=False), cell(16, 4, 45, certified=False)])

    def test_merges_only_declared_certified_targets(self) -> None:
        merged = merger.merge(
            self.base,
            [report([cell(10, 4, 30, certified=True)]), report([cell(16, 4, 48, certified=True)])],
            [(10, 4), (16, 4)],
        )
        self.assertEqual(merged["summary"]["certified_integer_optimum_count"], 2)
        self.assertEqual(merged["summary"]["unresolved_with_bounds_count"], 0)
        self.assertEqual([row["global_upper_bound"] for row in merged["cells"]], [30, 48])

    def test_rejects_missing_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing follow-up"):
            merger.merge(
                self.base,
                [report([cell(10, 4, 30, certified=True)])],
                [(10, 4), (16, 4)],
            )

    def test_rejects_snapshot_drift(self) -> None:
        changed = report([cell(10, 4, 30, certified=True)])
        changed["snapshot"] = {"revision": "changed"}
        with self.assertRaisesRegex(ValueError, "snapshot"):
            merger.merge(self.base, [changed], [(10, 4)])

    def test_rejects_false_optimum_status(self) -> None:
        false_optimum = cell(10, 4, 30, certified=True)
        false_optimum["global_lower_bound"] = 29
        with self.assertRaisesRegex(ValueError, "lacks a valid"):
            merger.merge(self.base, [report([false_optimum])], [(10, 4)])


if __name__ == "__main__":
    unittest.main()
