from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

import live_chicago_k2_frontier as frontier  # noqa: E402
import live_chicago_k2_frontier_partitioned as partitioned  # noqa: E402
import live_chicago_k2_frontier_boundary as boundary  # noqa: E402
import run_chicago_k2_fixed_panel as panel  # noqa: E402


class FixedPanelProtocolTests(unittest.TestCase):
    def test_protocol_is_outcome_blind_and_has_24_unique_windows(self) -> None:
        protocol = panel.load_protocol(panel.DEFAULT_PROTOCOL)
        windows = panel.expand_windows(protocol)
        self.assertEqual(len(windows), 24)
        self.assertEqual(len(set(windows)), 24)
        self.assertEqual(windows[0].isoformat(), "2026-01-05T08:00:00")
        self.assertEqual(windows[-1].isoformat(), "2026-01-14T17:30:00")
        self.assertIn("No window is replaced", protocol["replacement_rule"])

    def test_fixed_core_parser_and_partitioned_validation(self) -> None:
        args = partitioned.build_parser().parse_args(
            ["--core-start", "2026-01-05T08:00:00"]
        )
        partitioned._validate_args(args)
        self.assertEqual(args.core_start, "2026-01-05T08:00:00")

    def test_target_command_uses_fixed_core_not_scan(self) -> None:
        protocol = panel.load_protocol(panel.DEFAULT_PROTOCOL)
        start = panel.expand_windows(protocol)[0]
        command = panel.target_command(protocol, start, Path("tmp/test"))
        self.assertEqual(command[command.index("--core-start") + 1], start.isoformat())
        self.assertNotIn("--scan-start", command)

    def test_summary_fails_closed_on_core_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.json").write_text(
                json.dumps(
                    {
                        "extraction": {"predeclared_core_start_local": "2026-01-06T08:00:00"},
                        "cohort": {},
                    }
                ),
                encoding="utf-8",
            )
            start = panel.expand_windows(panel.load_protocol(panel.DEFAULT_PROTOCOL))[0]
            row = panel.summarize_window(index=0, start=start, directory=root)
            self.assertEqual(row["status"], "INVALID_CORE_DRIFT")

    def test_missing_report_is_never_completed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            start = panel.expand_windows(panel.load_protocol(panel.DEFAULT_PROTOCOL))[0]
            row = panel.summarize_window(
                index=0, start=start, directory=Path(directory)
            )
            self.assertEqual(row["status"], "EXECUTION_FAILED")

    def test_generic_omission_budget_has_exact_base_and_full_endpoints(self) -> None:
        base = datetime(2026, 1, 1, 12, 0)
        rows = [
            boundary._synthetic_trip(0, "core", base, base + timedelta(minutes=30)),
            boundary._synthetic_trip(1, "core", base, base + timedelta(minutes=30)),
            boundary._synthetic_trip(2, "buffer", base, base + timedelta(minutes=30)),
            boundary._synthetic_trip(3, "buffer", base, base + timedelta(minutes=30)),
        ]
        full_edges = [(0, 1), (0, 2), (1, 3)]
        base_edges = {(0, 1)}
        costs = boundary.candidate_omission_costs(rows, full_edges, base_edges)
        self.assertEqual(costs, [0, 1, 1])
        zero = [0.0] * len(full_edges)
        gamma_zero = frontier.solve_binary_cover_objective(
            rows,
            full_edges,
            zero,
            maximize=False,
            miss_costs=costs,
            gamma=0,
            time_limit_seconds=5,
        )
        gamma_full = frontier.solve_binary_cover_objective(
            rows,
            full_edges,
            zero,
            maximize=False,
            miss_costs=costs,
            gamma=2,
            time_limit_seconds=5,
        )
        self.assertEqual(gamma_zero.status, frontier.CERTIFIED_ENDPOINT_STATUS)
        self.assertEqual(gamma_full.status, frontier.CERTIFIED_ENDPOINT_STATUS)


if __name__ == "__main__":
    unittest.main()
