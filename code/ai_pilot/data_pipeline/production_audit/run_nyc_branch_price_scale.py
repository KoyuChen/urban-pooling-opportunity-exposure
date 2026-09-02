#!/usr/bin/env python3
"""Run the existing live NYC integer audit on a predeclared core-size grid.

The repository already contains the canonical live branch-and-price wrapper.
This driver discovers that wrapper, interrogates its argparse contract, and
passes only options the wrapper explicitly declares.  It therefore avoids a
second implementation of data extraction or integer optimization.

Every invocation writes a driver manifest even when the live job times out or
fails.  A failed cell remains failed/unresolved; the driver never converts a
missing certificate into an optimum.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

HERE = Path(__file__).resolve().parent
ALGORITHM_BASENAME = "ordered_run_branch_and_price.py"


def _live_candidates() -> list[Path]:
    preferred = [
        HERE / "live_nyc_hvfhv_branch_and_price.py",
        HERE / "live_nyc_hvfhv_ordered_run_branch_and_price.py",
        HERE / "live_nyc_hvfhv_column_generation.py",
        HERE / "live_nyc_hvfhv_ordered_run_column_generation.py",
    ]
    candidates: list[Path] = []
    for path in preferred:
        if path.exists():
            candidates.append(path)
    for path in sorted(HERE.glob("live_nyc_hvfhv*.py")):
        if path in candidates or path.name == ALGORITHM_BASENAME:
            continue
        text = path.read_text(encoding="utf-8")
        if "branch_and_price" in text and "def main" in text:
            candidates.append(path)
    return candidates


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("_live_bp_scale_target", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HERE))
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path and sys.path[0] == str(HERE):
            sys.path.pop(0)
    return module


def discover_wrapper() -> tuple[Path, Any, argparse.ArgumentParser]:
    errors: list[str] = []
    for path in _live_candidates():
        try:
            module = _load(path)
            parser_factory = getattr(module, "parser", None)
            if parser_factory is None or not callable(parser_factory):
                errors.append(f"{path.name}: no parser()")
                continue
            parser = parser_factory()
            if not isinstance(parser, argparse.ArgumentParser):
                errors.append(f"{path.name}: parser() is not ArgumentParser")
                continue
            dests = {action.dest for action in parser._actions}
            if "output_dir" not in dests or "ordered_core" not in dests:
                errors.append(
                    f"{path.name}: missing output_dir/ordered_core contract"
                )
                continue
            source = path.read_text(encoding="utf-8")
            if "branch_and_price" not in source:
                errors.append(f"{path.name}: no branch_and_price call")
                continue
            return path, module, parser
        except Exception as error:  # fail closed with an auditable message
            errors.append(f"{path.name}: {type(error).__name__}: {error}")
    raise RuntimeError("no live branch-and-price wrapper found; " + " | ".join(errors))


def _option(action: argparse.Action) -> str:
    long_options = [value for value in action.option_strings if value.startswith("--")]
    if not long_options:
        raise RuntimeError(f"no long option for argparse destination {action.dest}")
    return long_options[0]


def build_cli(parser: argparse.ArgumentParser, args: argparse.Namespace) -> list[str]:
    actions = {action.dest: action for action in parser._actions}
    values: dict[str, Any] = {
        "output_dir": args.output_dir,
        "scan_start": args.scan_start,
        "scan_end": args.scan_end,
        "scan_window_hours": 1,
        "min_core_rows": args.ordered_core,
        "max_core_rows": max(40, args.ordered_core),
        "max_scan_rows": 5000,
        "max_candidate_rows": 2500,
        "ordered_core": args.ordered_core,
        "solver_time_limit": args.solver_time_limit,
        "window_label": args.window_label,
        "time_model": "exact_second",
        "time_models": ["exact_second"],
        "overlap_epsilon_seconds": 1.0,
    }
    cli: list[str] = []
    for dest, value in values.items():
        action = actions.get(dest)
        if action is None:
            continue
        option = _option(action)
        if isinstance(value, list):
            cli.append(option)
            cli.extend(str(item) for item in value)
        else:
            cli.extend([option, str(value)])

    unsupported_required = [
        action.dest
        for action in parser._actions
        if getattr(action, "required", False)
        and action.dest not in values
        and action.dest != "help"
    ]
    if unsupported_required:
        raise RuntimeError(
            "live wrapper added unsupported required arguments: "
            + ", ".join(sorted(unsupported_required))
        )
    return cli


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_test() -> None:
    path, _module, parser = discover_wrapper()
    namespace = argparse.Namespace(
        output_dir=Path("tmp/test"),
        scan_start="2023-01-03T17:00:00",
        scan_end="2023-01-03T21:00:00",
        ordered_core=4,
        solver_time_limit=30.0,
        window_label="self_test",
    )
    cli = build_cli(parser, namespace)
    assert "--ordered-core" in cli or any("ordered" in value for value in cli)
    print(f"NYC branch-and-price scaling driver self-test: PASS ({path.name})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--window-label", required=True)
    parser.add_argument("--scan-start", required=True)
    parser.add_argument("--scan-end", required=True)
    parser.add_argument("--ordered-core", type=int, required=True)
    parser.add_argument("--solver-time-limit", type=float, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output_dir is None:
        parser.error("--output-dir is required")
    if args.ordered_core <= 0 or args.solver_time_limit <= 0:
        parser.error("core size and time limit must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "driver_manifest.json"
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    clock = time.monotonic()
    try:
        target, _module, target_parser = discover_wrapper()
        target_cli = build_cli(target_parser, args)
        command = [sys.executable, str(target), *target_cli]
        result = subprocess.run(command, cwd=HERE, check=False)
        elapsed = time.monotonic() - clock
        write_manifest(
            manifest_path,
            {
                "report_version": "nyc-branch-price-scale-driver/v1",
                "started_at_utc": started,
                "finished_at_utc": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "elapsed_seconds": elapsed,
                "window_label": args.window_label,
                "scan_start": args.scan_start,
                "scan_end": args.scan_end,
                "ordered_core": args.ordered_core,
                "solver_time_limit": args.solver_time_limit,
                "target_wrapper": str(target.relative_to(HERE)),
                "target_cli": target_cli,
                "process_exit_status": result.returncode,
                "status": "SUCCESS" if result.returncode == 0 else "FAILED_OR_UNRESOLVED",
                "claim_boundary": (
                    "algorithmic scaling on a predeclared public-data audit cohort; "
                    "no partner, run, realized-capacity, or population claim"
                ),
            },
        )
        return int(result.returncode)
    except Exception as error:
        elapsed = time.monotonic() - clock
        write_manifest(
            manifest_path,
            {
                "report_version": "nyc-branch-price-scale-driver/v1",
                "started_at_utc": started,
                "finished_at_utc": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "elapsed_seconds": elapsed,
                "window_label": args.window_label,
                "scan_start": args.scan_start,
                "scan_end": args.scan_end,
                "ordered_core": args.ordered_core,
                "solver_time_limit": args.solver_time_limit,
                "process_exit_status": 2,
                "status": "DRIVER_FAILURE",
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
