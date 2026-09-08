#!/usr/bin/env python3
"""Run and audit an outcome-blind fixed Chicago K=2 cohort panel.

The protocol expands a date/time Cartesian product before any public row,
feasibility, runtime, or frontier outcome is inspected.  Every requested window
is retained in the aggregate report.  Failed and ineligible windows remain
explicit; they are never replaced by a more convenient bin.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_PROTOCOL = HERE / "CHICAGO_K2_PANEL_PROTOCOL.json"
TARGET = HERE / "live_chicago_k2_frontier_boundary.py"
INDEXED_COUNT_TARGET = HERE / "live_chicago_k2_frontier_indexed_count.py"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_protocol(path: Path) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "protocol_version",
        "date_start",
        "date_end",
        "local_start_times",
        "expected_window_count",
        "eligibility",
        "support",
        "solver",
        "claim_boundary",
    }
    missing = sorted(required - set(protocol))
    if missing:
        raise ValueError(f"protocol missing keys: {missing}")
    return protocol


def expand_windows(protocol: dict[str, Any]) -> list[datetime]:
    first = date.fromisoformat(str(protocol["date_start"]))
    last = date.fromisoformat(str(protocol["date_end"]))
    if first > last:
        raise ValueError("protocol date_start must not exceed date_end")
    times = [datetime.strptime(str(value), "%H:%M").time() for value in protocol["local_start_times"]]
    if len(times) != len(set(times)) or not times:
        raise ValueError("local_start_times must be nonempty and unique")
    windows: list[datetime] = []
    current = first
    while current <= last:
        if not protocol.get("weekdays_only") or current.weekday() < 5:
            windows.extend(datetime.combine(current, value) for value in sorted(times))
        current += timedelta(days=1)
    if len(windows) != int(protocol["expected_window_count"]):
        raise ValueError(
            "expanded window count differs from expected_window_count: "
            f"{len(windows)} != {protocol['expected_window_count']}"
        )
    return windows


def window_slug(index: int, start: datetime) -> str:
    return f"cohort_{index:03d}_{start:%Y%m%dT%H%M}"


def target_command(
    protocol: dict[str, Any], start: datetime, output_dir: Path,
    *, indexed_count_transport: bool = False,
) -> list[str]:
    eligibility = protocol["eligibility"]
    support = protocol["support"]
    solver = protocol["solver"]
    padding = ",".join(str(value) for value in support["boundary_padding_grid_minutes"])
    return [
        sys.executable,
        str(INDEXED_COUNT_TARGET if indexed_count_transport else TARGET),
        "--output-dir",
        str(output_dir.resolve()),
        "--core-start",
        start.isoformat(),
        "--min-core-rows",
        str(eligibility["min_core_rows"]),
        "--max-core-rows",
        str(eligibility["max_core_rows"]),
        "--max-candidate-rows",
        str(eligibility["max_candidate_rows"]),
        "--page-size",
        "100",
        "--request-timeout",
        "240" if indexed_count_transport else "90",
        "--request-attempts",
        "3",
        "--base-radius-km",
        str(support["base_radius_km"]),
        "--solver-time-limit",
        str(solver["endpoint_time_limit_seconds"]),
        "--boundary-padding-minutes",
        padding,
    ]


def failure_status(failure: dict[str, Any] | None) -> str:
    message = "" if not failure else str(failure.get("error_message", ""))
    if "no scan bin met" in message:
        return "INELIGIBLE_FIXED_CORE"
    if "exceeded max_candidate_rows" in message:
        return "INELIGIBLE_RESOURCE_CAP"
    return "EXECUTION_FAILED"


def summarize_window(
    *, index: int, start: datetime, directory: Path
) -> dict[str, Any]:
    report_path = directory / "report.json"
    failure_path = directory / "failure.json"
    if not report_path.exists():
        failure = (
            json.loads(failure_path.read_text(encoding="utf-8"))
            if failure_path.exists()
            else None
        )
        return {
            "window_index": index,
            "core_start_local": start.isoformat(),
            "status": failure_status(failure),
            "failure_type": None if failure is None else failure.get("error_type"),
            "failure_message": None if failure is None else failure.get("error_message"),
        }
    report = json.loads(report_path.read_text(encoding="utf-8"))
    declared = report.get("extraction", {}).get("predeclared_core_start_local")
    if declared != start.isoformat():
        return {
            "window_index": index,
            "core_start_local": start.isoformat(),
            "status": "INVALID_CORE_DRIFT",
            "observed_core_start_local": declared,
        }
    sensitivity = report.get("sensitivity_rows")
    if sensitivity is None:
        sensitivity_path = directory / "candidate_support_sensitivity.csv"
        if sensitivity_path.exists():
            with sensitivity_path.open(encoding="utf-8", newline="") as handle:
                sensitivity = list(csv.DictReader(handle))
        else:
            sensitivity = []
    if not sensitivity:
        return {
            "window_index": index,
            "core_start_local": start.isoformat(),
            "status": "INVALID_MISSING_SENSITIVITY",
        }
    chains = report.get("monotonicity_audit", {}).get("chain_audits", [])
    if chains and len(sensitivity) != sum(int(chain["point_count"]) for chain in chains):
        return {
            "window_index": index,
            "core_start_local": start.isoformat(),
            "status": "INVALID_INCOMPLETE_SENSITIVITY",
        }
    certified = sum(
        row.get("endpoint_pair_certification") == "CERTIFIED_OPTIMAL_PAIR"
        for row in sensitivity
    )
    missing_public_values = sum(
        row.get("lower_status") == "UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES"
        or row.get("upper_status") == "UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES"
        for row in sensitivity
    )
    computationally_unresolved = len(sensitivity) - certified - missing_public_values
    return {
        "window_index": index,
        "core_start_local": start.isoformat(),
        "status": "COMPLETED",
        "core_rows": report["cohort"]["core_rows"],
        "buffer_rows": report["cohort"]["buffer_rows"],
        "candidate_rows": report["cohort"]["candidate_rows"],
        "temporal_edges": report["logical_graph"]["edge_count"],
        "endpoint_pairs": len(sensitivity),
        "certified_endpoint_pairs": certified,
        "uncertified_endpoint_pairs": len(sensitivity) - certified,
        "missing_public_query_value_endpoint_pairs": missing_public_values,
        "computationally_unresolved_endpoint_pairs": computationally_unresolved,
        "monotonicity_status": report["monotonicity_audit"]["status"],
        "closure_status": report["cohort"]["public_temporal_candidate_universe_closure_status"],
        "report_sha256": sha256_file(report_path),
        "sensitivity_sha256": (
            sha256_file(directory / "candidate_support_sensitivity.csv")
            if (directory / "candidate_support_sensitivity.csv").exists()
            else None
        ),
    }


def aggregate(
    protocol_path: Path, output_dir: Path, windows: list[datetime]
) -> dict[str, Any]:
    rows = [
        summarize_window(
            index=index,
            start=start,
            directory=output_dir / window_slug(index, start),
        )
        for index, start in enumerate(windows)
    ]
    completed = [row for row in rows if row["status"] == "COMPLETED"]
    total_pairs = sum(int(row["endpoint_pairs"]) for row in completed)
    certified_pairs = sum(int(row["certified_endpoint_pairs"]) for row in completed)
    missing_public_pairs = sum(
        int(row["missing_public_query_value_endpoint_pairs"]) for row in completed
    )
    computationally_unresolved_pairs = sum(
        int(row["computationally_unresolved_endpoint_pairs"]) for row in completed
    )
    data_complete_pairs = total_pairs - missing_public_pairs
    report = {
        "report_version": "chicago-k2-fixed-panel-summary/v2",
        "protocol_file": protocol_path.name,
        "protocol_sha256": sha256_file(protocol_path),
        "predeclared_window_count": len(windows),
        "completed_window_count": len(completed),
        "ineligible_window_count": sum(row["status"].startswith("INELIGIBLE") for row in rows),
        "failed_or_invalid_window_count": sum(
            row["status"] not in {"COMPLETED", "INELIGIBLE_FIXED_CORE", "INELIGIBLE_RESOURCE_CAP"}
            for row in rows
        ),
        "endpoint_pair_count": total_pairs,
        "certified_endpoint_pair_count": certified_pairs,
        "exact_endpoint_rate": certified_pairs / total_pairs if total_pairs else None,
        "missing_public_query_value_endpoint_pair_count": missing_public_pairs,
        "computationally_unresolved_endpoint_pair_count": computationally_unresolved_pairs,
        "data_complete_endpoint_pair_count": data_complete_pairs,
        "data_complete_exact_endpoint_rate": (
            certified_pairs / data_complete_pairs if data_complete_pairs else None
        ),
        "all_completed_windows_count_closed": all(
            row.get("closure_status") == "PASS" for row in completed
        ),
        "windows": rows,
        "claim_boundary": load_protocol(protocol_path)["claim_boundary"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "panel_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    columns = sorted({key for row in rows for key in row})
    with (output_dir / "panel_windows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Chicago K=2 fixed-panel audit",
        "",
        f"- Predeclared windows: {len(windows)}",
        f"- Completed: {len(completed)}",
        f"- Ineligible: {report['ineligible_window_count']}",
        f"- Failed or invalid: {report['failed_or_invalid_window_count']}",
        f"- Certified endpoint pairs: {certified_pairs}/{total_pairs}",
        f"- Missing-public-value endpoint pairs: {missing_public_pairs}",
        f"- Computationally unresolved endpoint pairs: {computationally_unresolved_pairs}",
        "- Data-complete exact endpoint rate: "
        + (
            f"{report['data_complete_exact_endpoint_rate']:.1%}"
            if report["data_complete_exact_endpoint_rate"] is not None
            else "not applicable"
        ),
        f"- Claim boundary: {report['claim_boundary']}",
        "",
    ]
    (output_dir / "PANEL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def run_window(
    protocol: dict[str, Any], index: int, start: datetime, output_dir: Path,
    *, indexed_count_transport: bool = False,
) -> int:
    directory = output_dir / window_slug(index, start)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("cohort output is not empty; write retries separately and merge the checkpoint")
    directory.mkdir(parents=True, exist_ok=True)
    command = target_command(
        protocol, start, directory,
        indexed_count_transport=indexed_count_transport,
    )
    result = subprocess.run(command, cwd=HERE, check=False)
    (directory / "driver.json").write_text(
        json.dumps(
            {
                "window_index": index,
                "core_start_local": start.isoformat(),
                "command": command,
                "process_exit_status": result.returncode,
                "entrypoint_sha256": sha256_file(Path(command[1])),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return int(result.returncode)


def self_test() -> None:
    protocol = load_protocol(DEFAULT_PROTOCOL)
    windows = expand_windows(protocol)
    assert len(windows) == 24
    assert windows[0].isoformat() == "2026-01-05T08:00:00"
    assert windows[-1].isoformat() == "2026-01-14T17:30:00"
    command = target_command(protocol, windows[0], Path("tmp/panel-test"))
    assert command[command.index("--core-start") + 1] == windows[0].isoformat()
    assert "--scan-start" not in command
    print("Chicago fixed-panel driver self-test: PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/chicago-k2-fixed-panel"))
    parser.add_argument("--window-index", type=int)
    parser.add_argument("--aggregate-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--indexed-count-transport",
        action="store_true",
        help="replace timeout-prone wide count(*) calls with capped ID-index reconciliation",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    protocol = load_protocol(args.protocol)
    windows = expand_windows(protocol)
    if args.aggregate_only:
        aggregate(args.protocol, args.output_dir, windows)
        return 0
    if args.window_index is not None:
        if not 0 <= args.window_index < len(windows):
            raise SystemExit("--window-index is outside the predeclared panel")
        run_window(
            protocol, args.window_index, windows[args.window_index], args.output_dir,
            indexed_count_transport=args.indexed_count_transport,
        )
        return 0
    for index, start in enumerate(windows):
        run_window(
            protocol, index, start, args.output_dir,
            indexed_count_transport=args.indexed_count_transport,
        )
    aggregate(args.protocol, args.output_dir, windows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
