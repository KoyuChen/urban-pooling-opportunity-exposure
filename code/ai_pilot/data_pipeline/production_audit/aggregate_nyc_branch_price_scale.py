#!/usr/bin/env python3
"""Aggregate the predeclared NYC branch-and-price scale lattice.

Each driver artifact corresponds to one target core size and contains three
source cells, one for each C in {2,3,4}. The aggregator reads the canonical
source schema directly, verifies certified bounds, and preserves unresolved
gaps. It never infers optimality from a successful process exit alone.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

CAPACITIES = (2, 3, 4)
TOL = 1e-7


def load_driver_artifacts(input_dir: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for manifest_path in sorted(input_dir.rglob("driver_manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        report_path = manifest_path.with_name("report.json")
        report = (
            json.loads(report_path.read_text(encoding="utf-8"))
            if report_path.exists()
            else None
        )
        artifacts.append(
            {
                "manifest": manifest,
                "manifest_path": str(manifest_path.relative_to(input_dir)),
                "report": report,
                "report_path": (
                    str(report_path.relative_to(input_dir))
                    if report_path.exists()
                    else None
                ),
            }
        )
    return artifacts


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _certified(cell: dict[str, Any]) -> bool:
    if cell.get("status") != "INTEGER_OPTIMUM_CERTIFIED":
        return False
    objective = _number(cell.get("integer_maximum_selected_buffers"))
    lower = _number(cell.get("global_lower_bound"))
    upper = _number(cell.get("global_upper_bound"))
    return (
        objective is not None
        and lower is not None
        and upper is not None
        and abs(objective - lower) <= TOL
        and abs(objective - upper) <= TOL
    )


def summarize(
    artifacts: list[dict[str, Any]], expected_driver_count: int
) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    seen_drivers: set[tuple[str, int]] = set()

    for artifact in artifacts:
        manifest = artifact["manifest"]
        label = str(manifest.get("window_label"))
        core = int(manifest.get("ordered_core"))
        driver_key = (label, core)
        if driver_key in seen_drivers:
            problems.append(
                {"reason": "duplicate_driver_cell", "label": label, "core": core}
            )
        seen_drivers.add(driver_key)

        report = artifact["report"]
        source_cells: list[dict[str, Any]] = []
        if report is not None:
            if (
                report.get("report_version")
                != "nyc-fixed-time-ordered-run-branch-and-price-scale/v1"
            ):
                problems.append(
                    {"reason": "unexpected_source_schema", "label": label, "core": core}
                )
            source_cells = [
                cell
                for cell in report.get("cells", [])
                if int(cell.get("core_rows", -1)) == core
            ]

        by_capacity = {
            int(cell["capacity"]): cell
            for cell in source_cells
            if "capacity" in cell
        }
        if len(by_capacity) != len(source_cells):
            problems.append(
                {"reason": "duplicate_source_capacity", "label": label, "core": core}
            )

        for capacity in CAPACITIES:
            cell = by_capacity.get(capacity)
            if cell is None:
                rows.append(
                    {
                        "window_label": label,
                        "core_rows": core,
                        "buffer_rows": int(
                            manifest.get("ordered_buffers", 3 * core)
                        ),
                        "capacity": capacity,
                        "status": manifest.get("status", "MISSING_SOURCE_CELL"),
                        "certified_integer_optimum": False,
                        "root_lp_upper_bound": None,
                        "integer_lower_bound": None,
                        "global_upper_bound": None,
                        "absolute_gap": None,
                        "relative_gap": None,
                        "nodes_processed": None,
                        "generated_columns_across_nodes": None,
                        "pricing_cases": None,
                        "elapsed_seconds_wall": None,
                        "driver_elapsed_seconds": manifest.get("elapsed_seconds"),
                        "source_report_present": report is not None,
                        "manifest_path": artifact["manifest_path"],
                        "report_path": artifact["report_path"],
                    }
                )
                continue

            lower = cell.get(
                "integer_maximum_selected_buffers",
                cell.get("global_lower_bound"),
            )
            row = {
                "window_label": label,
                "core_rows": core,
                "buffer_rows": int(cell.get("buffer_rows", 3 * core)),
                "capacity": capacity,
                "status": cell.get("status"),
                "certified_integer_optimum": _certified(cell),
                "root_lp_upper_bound": cell.get("root_lp_upper_bound"),
                "integer_lower_bound": lower,
                "global_upper_bound": cell.get("global_upper_bound"),
                "absolute_gap": cell.get("absolute_gap"),
                "relative_gap": cell.get("relative_gap"),
                "nodes_processed": cell.get("nodes_processed"),
                "generated_columns_across_nodes": cell.get(
                    "total_generated_columns_across_nodes"
                ),
                "pricing_cases": cell.get("total_pricing_case_count"),
                "elapsed_seconds_wall": cell.get("elapsed_seconds_wall"),
                "driver_elapsed_seconds": manifest.get("elapsed_seconds"),
                "source_report_present": True,
                "manifest_path": artifact["manifest_path"],
                "report_path": artifact["report_path"],
            }
            lo = _number(row["integer_lower_bound"])
            hi = _number(row["global_upper_bound"])
            if lo is not None and hi is not None and lo > hi + TOL:
                problems.append(
                    {
                        "reason": "reversed_certified_bounds",
                        "label": label,
                        "core": core,
                        "capacity": capacity,
                    }
                )
            if (
                cell.get("status") == "INTEGER_OPTIMUM_CERTIFIED"
                and not row["certified_integer_optimum"]
            ):
                problems.append(
                    {
                        "reason": "invalid_optimum_certificate",
                        "label": label,
                        "core": core,
                        "capacity": capacity,
                    }
                )
            rows.append(row)

    if len(artifacts) != expected_driver_count:
        problems.append(
            {
                "reason": "unexpected_driver_count",
                "expected": expected_driver_count,
                "observed": len(artifacts),
            }
        )

    expected_algorithm_cells = expected_driver_count * len(CAPACITIES)
    if len(rows) != expected_algorithm_cells:
        problems.append(
            {
                "reason": "unexpected_algorithm_cell_count",
                "expected": expected_algorithm_cells,
                "observed": len(rows),
            }
        )

    certified = sum(bool(row["certified_integer_optimum"]) for row in rows)
    unresolved = sum(
        row["status"] == "INTEGER_BRANCH_AND_PRICE_UNRESOLVED" for row in rows
    )
    missing = sum(not bool(row["source_report_present"]) for row in rows)
    return {
        "status": "PASS" if not problems else "FAIL",
        "problem_count": len(problems),
        "problems": problems,
        "rows": rows,
        "summary": {
            "expected_driver_count": expected_driver_count,
            "observed_driver_count": len(artifacts),
            "expected_algorithm_cell_count": expected_algorithm_cells,
            "observed_algorithm_cell_count": len(rows),
            "certified_integer_optimum_count": certified,
            "unresolved_with_bounds_count": unresolved,
            "missing_source_report_cell_count": missing,
        },
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        "# NYC exact branch-and-price scaling lattice",
        "",
        f"Generated UTC: `{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}`",
        "",
        "| Core | Buffers | C | Status | Root LP UB | Integer LB | Global UB | Gap | Nodes | Columns | Pricing cases | Seconds |",
        "|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def show(value: Any, digits: int = 3) -> str:
        if value is None:
            return "—"
        if isinstance(value, (int, float)):
            return f"{float(value):.{digits}f}"
        return str(value)

    for row in sorted(
        result["rows"],
        key=lambda item: (int(item["core_rows"]), int(item["capacity"])),
    ):
        lines.append(
            f"| {row['core_rows']} | {row['buffer_rows']} | {row['capacity']} | "
            f"`{row['status']}` | {show(row['root_lp_upper_bound'])} | "
            f"{show(row['integer_lower_bound'])} | {show(row['global_upper_bound'])} | "
            f"{show(row['absolute_gap'])} | {show(row['nodes_processed'], 0)} | "
            f"{show(row['generated_columns_across_nodes'], 0)} | "
            f"{show(row['pricing_cases'], 0)} | {show(row['elapsed_seconds_wall'], 2)} |"
        )

    summary = result["summary"]
    lines.extend(
        [
            "",
            "## Audit summary",
            "",
            f"- Driver artifacts: **{summary['observed_driver_count']} / {summary['expected_driver_count']}**.",
            f"- Algorithm cells: **{summary['observed_algorithm_cell_count']} / {summary['expected_algorithm_cell_count']}**.",
            f"- Certified integer optima: **{summary['certified_integer_optimum_count']}**.",
            f"- Unresolved cells with honest bounds: **{summary['unresolved_with_bounds_count']}**.",
            f"- Missing source-report cells: **{summary['missing_source_report_cell_count']}**.",
            f"- Structural aggregation status: `{result['status']}` with **{result['problem_count']}** problems.",
            "",
            "Unresolved cells remain open certified gaps. The lattice is an "
            "algorithmic audit on one deterministic public cohort; it does not "
            "recover actual event memberships, realized capacity, or a city-level "
            "runtime distribution.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = (
        sorted({key for row in rows for key in row})
        if rows
        else ["core_rows"]
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    artifacts: list[dict[str, Any]] = []
    for core in (4, 8):
        cells = []
        for capacity in CAPACITIES:
            cells.append(
                {
                    "core_rows": core,
                    "buffer_rows": 3 * core,
                    "capacity": capacity,
                    "status": "INTEGER_OPTIMUM_CERTIFIED",
                    "integer_maximum_selected_buffers": float(core),
                    "global_lower_bound": float(core),
                    "global_upper_bound": float(core),
                    "root_lp_upper_bound": float(core),
                    "absolute_gap": 0.0,
                    "nodes_processed": 1,
                }
            )
        artifacts.append(
            {
                "manifest": {
                    "window_label": f"n{core}",
                    "ordered_core": core,
                    "ordered_buffers": 3 * core,
                    "status": "SUCCESS",
                    "elapsed_seconds": 1.0,
                },
                "manifest_path": f"n{core}/driver_manifest.json",
                "report_path": f"n{core}/report.json",
                "report": {
                    "report_version": "nyc-fixed-time-ordered-run-branch-and-price-scale/v1",
                    "cells": cells,
                },
            }
        )
    result = summarize(artifacts, expected_driver_count=2)
    assert result["status"] == "PASS", result
    assert result["summary"]["certified_integer_optimum_count"] == 6
    print("NYC branch-and-price scale aggregator self-test: PASS")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--expected-driver-count", type=int, default=4)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input_dir is None or args.output_dir is None:
        p.error("--input-dir and --output-dir are required")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = summarize(
        load_driver_artifacts(args.input_dir), args.expected_driver_count
    )
    report = {
        "report_version": "nyc-branch-price-scale/v2-source-cell-aware",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        **result,
        "claim_boundary": {
            "supported": "algorithmic scaling and exact certification status for the declared public-data audit cells",
            "not_supported": "partner recovery, actual event IDs, realized capacity, population prevalence, or causal effects",
        },
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        render(result), encoding="utf-8"
    )
    write_csv(result["rows"], args.output_dir / "scaling_cells.csv")
    print(render(result))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
