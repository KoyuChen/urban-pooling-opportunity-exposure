#!/usr/bin/env python3
"""Run one predeclared NYC branch-and-price scale cell.

The canonical live scale wrapper performs a count-reconciled public extraction,
then solves all requested capacities. This driver maps one matrix cell with
``n`` core rows to the single target scale pair ``n:3n``. For ``n>4`` it also
passes the small ``4:12`` pair so the wrapper can retain its independent
complete-enumeration check without ever exhaustively enumerating the target
medium instance.

Every invocation writes a driver manifest. Timeouts, missing reports, and open
branch-and-price gaps remain unresolved; no missing certificate is converted to
an optimum.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

HERE = Path(__file__).resolve().parent
TARGET = HERE / "live_nyc_hvfhv_branch_and_price_scale.py"
SMALL_CHECK_PAIR = "4:12"
CAPACITIES = (2, 3, 4)


def target_scale_pairs(core_rows: int) -> tuple[str, ...]:
    target = f"{core_rows}:{3 * core_rows}"
    return (SMALL_CHECK_PAIR,) if target == SMALL_CHECK_PAIR else (SMALL_CHECK_PAIR, target)


def build_target_cli(args: argparse.Namespace) -> list[str]:
    core_rows = int(args.ordered_core)
    buffer_rows = 3 * core_rows
    scale_pairs = target_scale_pairs(core_rows)
    return [
        "--output-dir",
        str(args.output_dir),
        "--scan-start",
        str(args.scan_start),
        "--scan-end",
        str(args.scan_end),
        "--scan-window-hours",
        "1",
        "--min-core-rows",
        str(core_rows),
        "--max-core-rows",
        str(max(40, core_rows)),
        "--max-scan-rows",
        "5000",
        "--max-candidate-rows",
        "2500",
        "--existential-core",
        str(core_rows),
        "--existential-buffers",
        str(buffer_rows),
        "--scale-pairs",
        *scale_pairs,
        "--overlap-epsilon-seconds",
        "1.0",
        "--bp-max-nodes",
        str(args.bp_max_nodes),
        "--bp-time-limit-seconds",
        str(args.solver_time_limit),
        "--bp-max-pricing-cases",
        str(args.bp_max_pricing_cases),
    ]


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def self_test() -> None:
    namespace = argparse.Namespace(
        output_dir=Path("tmp/test"),
        scan_start="2023-01-03T17:00:00",
        scan_end="2023-01-03T21:00:00",
        ordered_core=8,
        solver_time_limit=30.0,
        bp_max_nodes=3000,
        bp_max_pricing_cases=4096,
    )
    cli = build_target_cli(namespace)
    assert target_scale_pairs(4) == ("4:12",)
    assert target_scale_pairs(8) == ("4:12", "8:24")
    assert cli[cli.index("--existential-core") + 1] == "8"
    assert cli[cli.index("--existential-buffers") + 1] == "24"
    start = cli.index("--scale-pairs") + 1
    stop = cli.index("--overlap-epsilon-seconds")
    assert cli[start:stop] == ["4:12", "8:24"]
    assert cli[cli.index("--bp-time-limit-seconds") + 1] == "30.0"
    print("NYC branch-and-price scaling driver self-test: PASS")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--window-label", required=True)
    p.add_argument("--scan-start", required=True)
    p.add_argument("--scan-end", required=True)
    p.add_argument("--ordered-core", type=int, required=True)
    p.add_argument("--solver-time-limit", type=float, required=True)
    p.add_argument("--bp-max-nodes", type=int, default=3000)
    p.add_argument("--bp-max-pricing-cases", type=int, default=4096)
    p.add_argument("--self-test", action="store_true")
    return p


def validate(args: argparse.Namespace) -> None:
    if args.output_dir is None:
        raise ValueError("--output-dir is required")
    if args.ordered_core < 4:
        raise ValueError("--ordered-core must be at least four")
    if args.solver_time_limit <= 0:
        raise ValueError("--solver-time-limit must be positive")
    if args.bp_max_nodes <= 0 or args.bp_max_pricing_cases <= 0:
        raise ValueError("branch-and-price limits must be positive")
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "driver_manifest.json"
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    clock = time.monotonic()
    cli = build_target_cli(args)
    command = [sys.executable, str(TARGET), *cli]
    try:
        result = subprocess.run(command, cwd=HERE, check=False)
        elapsed = time.monotonic() - clock
        report_path = args.output_dir / "report.json"
        status = (
            "SUCCESS"
            if result.returncode == 0 and report_path.exists()
            else "FAILED_OR_UNRESOLVED"
        )
        write_manifest(
            manifest_path,
            {
                "report_version": "nyc-branch-price-scale-driver/v2-single-target",
                "started_at_utc": started,
                "finished_at_utc": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "elapsed_seconds": elapsed,
                "window_label": args.window_label,
                "scan_start": args.scan_start,
                "scan_end": args.scan_end,
                "ordered_core": args.ordered_core,
                "ordered_buffers": 3 * args.ordered_core,
                "capacities": list(CAPACITIES),
                "solver_time_limit_per_capacity": args.solver_time_limit,
                "target_wrapper": TARGET.name,
                "target_scale_pairs": list(target_scale_pairs(args.ordered_core)),
                "target_cli": cli,
                "process_exit_status": result.returncode,
                "source_report_present": report_path.exists(),
                "status": status,
                "claim_boundary": (
                    "algorithmic scaling on a predeclared public-data audit cohort; "
                    "no partner, run, realized-capacity, or population claim"
                ),
            },
        )
        return int(result.returncode)
    except Exception as error:
        write_manifest(
            manifest_path,
            {
                "report_version": "nyc-branch-price-scale-driver/v2-single-target",
                "started_at_utc": started,
                "finished_at_utc": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "elapsed_seconds": time.monotonic() - clock,
                "window_label": args.window_label,
                "ordered_core": args.ordered_core,
                "ordered_buffers": 3 * args.ordered_core,
                "capacities": list(CAPACITIES),
                "solver_time_limit_per_capacity": args.solver_time_limit,
                "process_exit_status": 2,
                "status": "DRIVER_FAILURE",
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
