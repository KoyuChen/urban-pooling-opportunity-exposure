#!/usr/bin/env python3
"""Aggregate predeclared NYC branch-and-price scaling cells.

The aggregator is deliberately schema-tolerant about the canonical live
wrapper's report while remaining claim-strict: it never labels a cell optimal
unless the source report explicitly contains an optimal/certified status.  Raw
reports and driver manifests remain the source of truth.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable


def _walk(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk(child, name)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{prefix}[{index}]")
    else:
        yield prefix, value


def _find(flat: list[tuple[str, Any]], suffixes: tuple[str, ...]) -> Any:
    for suffix in suffixes:
        matches = [value for key, value in flat if key.lower().endswith(suffix)]
        if matches:
            return matches[0]
    return None


def _status_text(flat: list[tuple[str, Any]]) -> str:
    values = [
        str(value)
        for key, value in flat
        if any(token in key.lower() for token in ("status", "conclusion", "certificate"))
    ]
    return " | ".join(values[:12])


def _explicitly_certified(text: str) -> bool:
    upper = text.upper()
    positive = any(token in upper for token in ("CERTIFIED", "OPTIMAL", "PASS"))
    unresolved = any(
        token in upper
        for token in ("UNRESOLVED", "TIMEOUT", "FAILED", "ERROR", "INVALID")
    )
    return positive and not unresolved


def load_cells(input_dir: Path) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for manifest_path in sorted(input_dir.rglob("driver_manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        report_paths = [
            path
            for path in manifest_path.parent.rglob("report.json")
            if path != manifest_path
        ]
        reports = [
            json.loads(path.read_text(encoding="utf-8")) for path in report_paths
        ]
        cells.append(
            {
                "manifest": manifest,
                "manifest_path": str(manifest_path.relative_to(input_dir)),
                "report_paths": [str(path.relative_to(input_dir)) for path in report_paths],
                "reports": reports,
            }
        )
    return cells


def summarize(cells: list[dict[str, Any]], expected_count: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for cell in cells:
        manifest = cell["manifest"]
        flattened: list[tuple[str, Any]] = []
        for report in cell["reports"]:
            flattened.extend(_walk(report))
        status_text = _status_text(flattened)
        source_certified = _explicitly_certified(status_text)
        driver_success = manifest.get("status") == "SUCCESS"
        if driver_success and not cell["reports"]:
            problems.append(
                {
                    "window_label": manifest.get("window_label"),
                    "ordered_core": manifest.get("ordered_core"),
                    "reason": "driver_success_without_report",
                }
            )
        rows.append(
            {
                "window_label": manifest.get("window_label"),
                "ordered_core": manifest.get("ordered_core"),
                "solver_time_limit": manifest.get("solver_time_limit"),
                "driver_status": manifest.get("status"),
                "process_exit_status": manifest.get("process_exit_status"),
                "elapsed_seconds": manifest.get("elapsed_seconds"),
                "report_count": len(cell["reports"]),
                "source_status_text": status_text,
                "source_explicitly_certified": source_certified,
                "objective": _find(
                    flattened,
                    (
                        ".integer_objective",
                        ".integer_optimum",
                        ".objective",
                        ".value",
                    ),
                ),
                "root_lp_bound": _find(
                    flattened,
                    (".root_lp_bound", ".lp_objective", ".lp_optimum"),
                ),
                "branch_nodes": _find(
                    flattened,
                    (".branch_nodes", ".nodes_processed", ".node_count"),
                ),
                "generated_columns": _find(
                    flattened,
                    (".generated_columns", ".column_count", ".columns"),
                ),
                "optimality_gap": _find(
                    flattened,
                    (".optimality_gap", ".relative_gap", ".gap"),
                ),
                "manifest_path": cell["manifest_path"],
                "report_paths": ";".join(cell["report_paths"]),
            }
        )

    if len(cells) != expected_count:
        problems.append(
            {
                "reason": "unexpected_cell_count",
                "expected": expected_count,
                "observed": len(cells),
            }
        )
    labels = [(row["window_label"], row["ordered_core"]) for row in rows]
    if len(labels) != len(set(labels)):
        problems.append({"reason": "duplicate_window_core_cell"})

    certified = sum(bool(row["source_explicitly_certified"]) for row in rows)
    driver_successes = sum(row["driver_status"] == "SUCCESS" for row in rows)
    return {
        "status": "PASS" if not problems and len(cells) == expected_count else "FAIL",
        "problem_count": len(problems),
        "problems": problems,
        "rows": rows,
        "summary": {
            "expected_cell_count": expected_count,
            "observed_cell_count": len(cells),
            "driver_success_count": driver_successes,
            "source_explicitly_certified_count": certified,
            "unresolved_or_failed_count": len(rows) - certified,
        },
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        "# NYC branch-and-price scaling audit",
        "",
        f"Generated UTC: `{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}`",
        "",
        "| Window | Core rows | Driver | Certified in source | Elapsed (s) | Objective | Root LP | Nodes | Columns | Gap |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(result["rows"], key=lambda item: (str(item["window_label"]), int(item["ordered_core"] or 0))):
        lines.append(
            f"| {row['window_label']} | {row['ordered_core']} | `{row['driver_status']}` | "
            f"{row['source_explicitly_certified']} | {row['elapsed_seconds']} | "
            f"{row['objective']} | {row['root_lp_bound']} | {row['branch_nodes']} | "
            f"{row['generated_columns']} | {row['optimality_gap']} |"
        )
    summary = result["summary"]
    lines.extend(
        [
            "",
            "## Audit summary",
            "",
            f"- Cells observed: **{summary['observed_cell_count']} / {summary['expected_cell_count']}**.",
            f"- Driver successes: **{summary['driver_success_count']}**.",
            f"- Source reports with an explicit optimal/certified status and no unresolved marker: **{summary['source_explicitly_certified_count']}**.",
            f"- Unresolved or failed cells: **{summary['unresolved_or_failed_count']}**.",
            f"- Aggregation status: `{result['status']}` with **{result['problem_count']}** structural problems.",
            "",
            "The table is an algorithmic audit over predeclared public-data cohorts. "
            "Timeouts and missing certificates remain unresolved. It does not recover "
            "actual partners, vehicle runs, or realized capacity.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = sorted({key for row in rows for key in row}) if rows else ["window_label"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    cells = []
    for core in (4, 8):
        cells.append(
            {
                "manifest": {
                    "window_label": "w",
                    "ordered_core": core,
                    "solver_time_limit": 10,
                    "status": "SUCCESS",
                    "process_exit_status": 0,
                    "elapsed_seconds": 1.0,
                },
                "manifest_path": f"w/{core}/driver_manifest.json",
                "report_paths": [f"w/{core}/report.json"],
                "reports": [{"status": "CERTIFIED_OPTIMAL", "objective": core}],
            }
        )
    result = summarize(cells, expected_count=2)
    assert result["status"] == "PASS", result
    assert result["summary"]["source_explicitly_certified_count"] == 2
    print("NYC branch-and-price scale aggregator self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-cell-count", type=int, default=4)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input_dir is None or args.output_dir is None:
        parser.error("--input-dir and --output-dir are required")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = summarize(load_cells(args.input_dir), args.expected_cell_count)
    report = {
        "report_version": "nyc-branch-price-scale/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        **result,
        "claim_boundary": {
            "supported": "algorithmic scaling and certification status for the declared public-data audit cells",
            "not_supported": "partner recovery, actual event IDs, realized capacity, population prevalence, or causal effects",
        },
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(render(result), encoding="utf-8")
    write_csv(result["rows"], args.output_dir / "scaling_cells.csv")
    print(render(result))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
