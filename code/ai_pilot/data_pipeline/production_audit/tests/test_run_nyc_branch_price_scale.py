import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR.parent))

from production_audit import run_nyc_branch_price_scale  # noqa: E402


class RunNycBranchPriceScaleTest(unittest.TestCase):
    def test_relative_output_dir_is_shared_with_child_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stub = root / "target_stub.py"
            stub.write_text(
                """\
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser(add_help=False)
p.add_argument('--output-dir', type=Path, required=True)
p.add_argument('--existential-core', type=int, required=True)
p.add_argument('--capacities', nargs='+', type=int, required=True)
args, _ = p.parse_known_args()
args.output_dir.mkdir(parents=True, exist_ok=True)
cells = []
for capacity in args.capacities:
    cells.append({
        'core_rows': args.existential_core,
        'capacity': capacity,
        'status': 'INTEGER_OPTIMUM_CERTIFIED',
        'integer_maximum_selected_buffers': 30.0,
        'global_lower_bound': 30.0,
        'global_upper_bound': 30.0,
    })
(args.output_dir / 'report.json').write_text(
    json.dumps({'cells': cells}), encoding='utf-8'
)
""",
                encoding="utf-8",
            )
            argv = [
                "run_nyc_branch_price_scale.py",
                "--output-dir",
                "relative-output",
                "--window-label",
                "test",
                "--scan-start",
                "2023-01-03T17:00:00",
                "--scan-end",
                "2023-01-03T21:00:00",
                "--ordered-core",
                "10",
                "--capacities",
                "4",
                "--solver-time-limit",
                "1",
            ]
            previous = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.object(run_nyc_branch_price_scale, "TARGET", stub):
                    with mock.patch.object(sys, "argv", argv):
                        exit_status = run_nyc_branch_price_scale.main()
            finally:
                os.chdir(previous)

            output = root / "relative-output"
            self.assertEqual(exit_status, 0)
            self.assertTrue((output / "report.json").exists())
            manifest = json.loads(
                (output / "driver_manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(manifest["source_report_present"])
            self.assertEqual(
                manifest["status"], "TARGET_INTEGER_OPTIMUM_CERTIFIED"
            )

    def test_audit_target_report_certifies_only_requested_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "cells": [
                            {
                                "core_rows": 10,
                                "capacity": 3,
                                "status": "INTEGER_BRANCH_AND_PRICE_UNRESOLVED",
                            },
                            {
                                "core_rows": 10,
                                "capacity": 4,
                                "status": "INTEGER_OPTIMUM_CERTIFIED",
                                "integer_maximum_selected_buffers": 30.0,
                                "global_lower_bound": 30.0,
                                "global_upper_bound": 30.0,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            audit = run_nyc_branch_price_scale.audit_target_report(
                report_path, 10, [4]
            )

            self.assertTrue(audit["source_report_present"])
            self.assertEqual(audit["target_cell_count"], 1)
            self.assertEqual(audit["target_cells"][0]["capacity"], 4)
            self.assertEqual(
                audit["status"], "TARGET_INTEGER_OPTIMUM_CERTIFIED"
            )
            self.assertEqual(len(audit["source_report_sha256"]), 64)

    def test_audit_target_report_preserves_unresolved_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "cells": [
                            {
                                "core_rows": 16,
                                "capacity": 3,
                                "status": "INTEGER_BRANCH_AND_PRICE_UNRESOLVED",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            audit = run_nyc_branch_price_scale.audit_target_report(
                report_path, 16, [3]
            )

            self.assertEqual(audit["status"], "TARGET_UNRESOLVED_WITH_REPORT")

    def test_audit_target_report_rejects_missing_target_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_text(json.dumps({"cells": []}), encoding="utf-8")

            audit = run_nyc_branch_price_scale.audit_target_report(
                report_path, 12, [4]
            )

            self.assertEqual(audit["status"], "MISSING_TARGET_CELL")

    def test_certification_requires_equal_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "cells": [
                            {
                                "core_rows": 10,
                                "capacity": 4,
                                "status": "INTEGER_OPTIMUM_CERTIFIED",
                                "integer_maximum_selected_buffers": 30.0,
                                "global_lower_bound": 30.0,
                                "global_upper_bound": 31.0,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            audit = run_nyc_branch_price_scale.audit_target_report(
                report_path, 10, [4]
            )

            self.assertEqual(audit["status"], "TARGET_UNRESOLVED_WITH_REPORT")


if __name__ == "__main__":
    unittest.main()
