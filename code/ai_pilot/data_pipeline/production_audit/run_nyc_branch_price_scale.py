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
import hashlib
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
TOL = 1e-7


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
        "--capacities",
        *(str(value) for value in args.capacities),
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_target_report(
    report_path: Path,
    core_rows: int,
    capacities: list[int],
) -> dict[str, Any]:
    """Read the canonical report and summarize only the requested target cells."""

    if not report_path.exists():
        return {
            "source_report_present": False,
            "source_report_sha256": None,
            "target_cell_count": 0,
            "target_cells": [],
            "status": "MISSING_SOURCE_REPORT",
        }

    report = json.loads(report_path.read_text(encoding="utf-8"))
    requested = set(int(value) for value in capacities)
    target_cells = [
        cell
        for cell in report.get("cells", [])
        if int(cell.get("core_rows", -1)) == core_rows
        and int(cell.get("capacity", -1)) in requested
    ]
    observed = {int(cell["capacity"]) for cell in target_cells}
    all_present = observed == requested and len(target_cells) == len(requested)
    def certified(cell: dict[str, Any]) -> bool:
        if cell.get("status") != "INTEGER_OPTIMUM_CERTIFIED":
            return False
        values = [
            cell.get("integer_maximum_selected_buffers"),
            cell.get("global_lower_bound"),
            cell.get("global_upper_bound"),
        ]
        if any(value is None for value in values):
            return False
        objective, lower, upper = (float(value) for value in values)
        return abs(objective - lower) <= TOL and abs(objective - upper) <= TOL

    all_certified = all_present and all(certified(cell) for cell in target_cells)
    if all_certified:
        status = "TARGET_INTEGER_OPTIMUM_CERTIFIED"
    elif all_present:
        status = "TARGET_UNRESOLVED_WITH_REPORT"
    else:
        status = "MISSING_TARGET_CELL"
    return {
        "source_report_present": True,
        "source_report_sha256": sha256_file(report_path),
        "target_cell_count": len(target_cells),
        "target_cells": target_cells,
        "status": status,
    }


def self_test() -> None:
    namespace = argparse.Namespace(
        output_dir=Path("tmp/test"),
        scan_start="2023-01-03T17:00:00",
        scan_end="2023-01-03T21:00:00",
        ordered_core=8,
        solver_time_limit=30.0,
        bp_max_nodes=3000,
        bp_max_pricing_cases=4096,
        capacities=list(CAPACITIES),
    )
    cli = build_target_cli(namespace)
    assert target_scale_pairs(4) == ("4:12",)
    assert target_scale_pairs(8) == ("4:12", "8:24")
    assert cli[cli.index("--existential-core") + 1] == "8"
    assert cli[cli.index("--existential-buffers") + 1] == "24"
    start = cli.index("--scale-pairs") + 1
    stop = cli.index("--overlap-epsilon-seconds")
    assert cli[start:cli.index("--capacities")] == ["4:12", "8:24"]
    assert cli[cli.index("--capacities") + 1:stop] == ["2", "3", "4"]
    assert cli[cli.index("--bp-time-limit-seconds") + 1] == "30.0"
    assert audit_target_report(Path("does-not-exist.json"), 8, [2])["status"] == (
        "MISSING_SOURCE_REPORT"
    )
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
    p.add_argument("--capacities", nargs="+", type=int, default=list(CAPACITIES))
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
    if not args.capacities or len(set(args.capacities)) != len(args.capacities):
        raise ValueError("--capacities must be nonempty and unique")
    if any(value not in CAPACITIES for value in args.capacities):
        raise ValueError(f"--capacities must be drawn from {CAPACITIES}")
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    validate(args)
    # The target wrapper runs with ``cwd=HERE``. Resolve the user-facing output
    # directory before constructing its CLI so reports and manifests land in
    # the same artifact tree even when --output-dir is relative.
    args.output_dir = args.output_dir.resolve()
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
        report_audit = audit_target_report(
            report_path,
            args.ordered_core,
            list(args.capacities),
        )
        status = (
            report_audit["status"]
            if result.returncode == 0
            else "DRIVER_FAILURE"
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
                "capacities": list(args.capacities),
                "solver_time_limit_per_capacity": args.solver_time_limit,
                "target_wrapper": TARGET.name,
                "target_scale_pairs": list(target_scale_pairs(args.ordered_core)),
                "target_cli": cli,
                "process_exit_status": result.returncode,
                **report_audit,
                "status": status,
                "claim_boundary": (
                    "algorithmic scaling on a predeclared public-data audit cohort; "
                    "no partner, run, realized-capacity, or population claim"
                ),
            },
        )
        # Missing output is an execution failure. A valid report containing an
        # honest unresolved gap remains a successful fail-closed run.
        if result.returncode != 0:
            return int(result.returncode)
        if report_audit["status"] in {
            "TARGET_INTEGER_OPTIMUM_CERTIFIED",
            "TARGET_UNRESOLVED_WITH_REPORT",
        }:
            return 0
        return 3
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
                "capacities": list(args.capacities),
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
