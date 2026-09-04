#!/usr/bin/env python3
"""Scale audit for exact integer ordered-event branch-and-price.

A single count-reconciled NYC extraction supplies a deterministic public row
universe. For each predeclared (core, buffer) size and C in {2,3,4}, the script
runs the exact branch-and-price support maximizer. The smallest cell is also
checked against complete run-column enumeration; larger cells report either a
closed integer optimum or a rigorous incumbent/upper-bound gap.

Outputs are aggregate algorithm diagnostics. They do not contain row
identifiers, run columns, selected-run witnesses, or partner assignments.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import live_nyc_hvfhv_existential_time as existential
import live_nyc_hvfhv_existential_time_hybrid as hybrid
import live_nyc_hvfhv_ordered_run_smoke as base
import ordered_run_branch_and_price as branch_and_price

CAPACITIES = (2, 3, 4)
DEFAULT_SCALE_PAIRS = ("4:12", "6:18", "8:24", "10:30", "12:36", "16:48")


def parse_scale_pairs(values: Iterable[str]) -> tuple[tuple[int, int], ...]:
    pairs: list[tuple[int, int]] = []
    for value in values:
        try:
            core_text, buffer_text = value.split(":", 1)
            core, buffers = int(core_text), int(buffer_text)
        except (ValueError, TypeError) as error:
            raise ValueError(f"invalid scale pair {value!r}; expected CORE:BUFFERS") from error
        if core < 2 or buffers < 1:
            raise ValueError("scale pairs require core >= 2 and buffers >= 1")
        pairs.append((core, buffers))
    if not pairs:
        raise ValueError("at least one scale pair is required")
    if len(set(pairs)) != len(pairs):
        raise ValueError("scale pairs must be unique")
    return tuple(pairs)


def safe_result(result: dict[str, Any]) -> dict[str, Any]:
    forbidden = {
        "selected_member_masks",
        "incumbent_masks",
        "columns",
        "column_values",
        "history",
        "node",
    }
    return {key: value for key, value in result.items() if key not in forbidden}


def audit_result(result: dict[str, Any]) -> None:
    status = result.get("status")
    if status == "INTEGER_OPTIMUM_CERTIFIED":
        value = float(result["integer_maximum_selected_buffers"])
        lower = float(result["global_lower_bound"])
        upper = float(result["global_upper_bound"])
        if abs(value - lower) > branch_and_price.TOL or abs(value - upper) > branch_and_price.TOL:
            raise AssertionError("certified integer value does not equal both global bounds")
        return
    if status == "INTEGER_BRANCH_AND_PRICE_UNRESOLVED":
        lower = result.get("global_lower_bound")
        upper = result.get("global_upper_bound")
        if lower is not None and upper is not None and float(lower) > float(upper) + branch_and_price.TOL:
            raise AssertionError("unresolved branch-and-price bounds are reversed")
        return
    if status == "INTEGER_MASTER_PROVEN_INFEASIBLE":
        return
    raise AssertionError(f"unexpected branch-and-price status: {status}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    scale_pairs = parse_scale_pairs(args.scale_pairs)
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError("dataset metadata/schema changed during extraction")
    determinate_after, _, _ = base.count(selected["where"]["determinate"])
    indeterminate_after, _, _ = base.count(selected["where"]["indeterminate"])
    if (
        determinate_after != selected["determinate_count"]
        or indeterminate_after != selected["indeterminate_count"]
    ):
        raise base.LiveDataError("candidate server counts changed during extraction")

    trips, row_audit = base.parse_trips(
        selected["candidate_rows"],
        selected["provider"],
        selected["core_start"],
        selected["core_end"],
    )

    cells: list[dict[str, Any]] = []
    for core_count, buffer_count in scale_pairs:
        try:
            reduced = existential.reduced_cohort(trips, core_count, buffer_count)
        except base.LiveDataError as error:
            for capacity in CAPACITIES:
                cells.append(
                    {
                        "core_rows": core_count,
                        "buffer_rows": buffer_count,
                        "capacity": capacity,
                        "status": "SKIPPED_INSUFFICIENT_PUBLIC_ROWS",
                        "reason": str(error),
                    }
                )
            continue
        origin = existential.support_origin(reduced)
        fixed_rows = hybrid._fixed_rows(reduced, origin)

        for capacity in CAPACITIES:
            started = time.perf_counter()
            if (core_count, buffer_count) == scale_pairs[0]:
                result = branch_and_price.compare_with_exhaustive(
                    fixed_rows,
                    capacity,
                    epsilon=args.overlap_epsilon_seconds,
                    max_nodes=args.bp_max_nodes,
                    time_limit_seconds=args.bp_time_limit_seconds,
                )
                independent_small_check = True
            else:
                result = branch_and_price.branch_and_price_max_support(
                    fixed_rows,
                    capacity,
                    max_nodes=args.bp_max_nodes,
                    time_limit_seconds=args.bp_time_limit_seconds,
                    max_pricing_cases=args.bp_max_pricing_cases,
                )
                independent_small_check = False
            elapsed = time.perf_counter() - started
            audit_result(result)
            cell = {
                "core_rows": core_count,
                "buffer_rows": buffer_count,
                "total_rows": len(fixed_rows),
                "capacity": capacity,
                "independent_complete_enumeration_check": independent_small_check,
                "elapsed_seconds_wall": elapsed,
                **safe_result(result),
            }
            cells.append(cell)

    certified = [row for row in cells if row["status"] == "INTEGER_OPTIMUM_CERTIFIED"]
    unresolved = [
        row for row in cells if row["status"] == "INTEGER_BRANCH_AND_PRICE_UNRESOLVED"
    ]
    skipped = [
        row for row in cells if row["status"] == "SKIPPED_INSUFFICIENT_PUBLIC_ROWS"
    ]
    larger_certified = [
        row
        for row in certified
        if (int(row["core_rows"]), int(row["buffer_rows"])) != scale_pairs[0]
    ]
    return {
        "report_version": "nyc-fixed-time-ordered-run-branch-and-price-scale/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "source_core_start": selected["core_start"].isoformat(),
            "source_core_end": selected["core_end"].isoformat(),
            "source_core_rows": row_audit["core_rows"],
            "source_candidate_rows": row_audit["rows"],
            "selection": (
                "one count-reconciled public extraction; first core rows by frozen "
                "source order and nearest complete buffers by exact temporal gap; "
                "no outcome values used"
            ),
        },
        "design": {
            "scale_pairs": [list(pair) for pair in scale_pairs],
            "capacities": list(CAPACITIES),
            "max_nodes_per_cell": args.bp_max_nodes,
            "time_limit_seconds_per_cell": args.bp_time_limit_seconds,
            "max_pricing_cases_per_root": args.bp_max_pricing_cases,
            "smallest_pair_checked_by_complete_enumeration": list(scale_pairs[0]),
        },
        "summary": {
            "cell_count": len(cells),
            "certified_integer_optimum_count": len(certified),
            "unresolved_with_bounds_count": len(unresolved),
            "skipped_insufficient_rows_count": len(skipped),
            "larger_than_small_audit_certified_count": len(larger_certified),
        },
        "cells": cells,
        "claim_boundary": {
            "supported": (
                "algorithmic scaling on deterministic nested-size extractions from "
                "one declared public cohort, with exact integer certificates when "
                "the branch queue closes and rigorous gaps otherwise"
            ),
            "not_supported": (
                "city-scale relation recovery, operational partner or run identity, "
                "population runtime guarantees, or polynomial full-master complexity"
            ),
        },
        "redaction": {
            "raw_rows_emitted": False,
            "row_identifiers_emitted": False,
            "run_columns_emitted": False,
            "selected_run_witnesses_emitted": False,
            "aggregate_only": True,
        },
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "# NYC exact integer branch-and-price scale audit",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Provider: `{report['cohort']['provider']}`.",
        "",
        "| Core | Buffers | C | Status | Root LP UB | Integer LB | Global UB | Gap | Nodes | Columns across nodes | Pricing cases | Seconds |",
        "|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["cells"]:
        def show(key: str, digits: int = 3) -> str:
            value = row.get(key)
            if value is None:
                return "—"
            if isinstance(value, (int, float)):
                return f"{float(value):.{digits}f}"
            return str(value)

        lower = row.get("integer_maximum_selected_buffers", row.get("global_lower_bound"))
        lines.append(
            f"| {row['core_rows']} | {row['buffer_rows']} | {row['capacity']} | "
            f"`{row['status']}` | {show('root_lp_upper_bound')} | "
            f"{'—' if lower is None else f'{float(lower):.3f}'} | "
            f"{show('global_upper_bound')} | {show('absolute_gap')} | "
            f"{show('nodes_processed', 0)} | "
            f"{show('total_generated_columns_across_nodes', 0)} | "
            f"{show('total_pricing_case_count', 0)} | "
            f"{show('elapsed_seconds_wall', 2)} |"
        )
    summary = report["summary"]
    lines.extend(
        [
            "",
            f"Certified integer optima: **{summary['certified_integer_optimum_count']} / {summary['cell_count']}**; "
            f"unresolved with bounds: **{summary['unresolved_with_bounds_count']}**; "
            f"skipped for insufficient public rows: **{summary['skipped_insufficient_rows_count']}**.",
            "",
            "A timeout is reported as an open certified gap, not converted to an optimum. "
            "The scale audit measures the exact decomposition algorithm on one deterministic "
            "public cohort and does not recover operational event memberships.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: dict[str, Any], path: Path) -> None:
    rows = report["cells"]
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    rows = [
        branch_and_price.exhaustive.FixedTimeRow(0, "core", 0.0, 2.0),
        branch_and_price.exhaustive.FixedTimeRow(1, "core", 3.0, 5.0),
        branch_and_price.exhaustive.FixedTimeRow(2, "buffer", 0.0, 1.5),
        branch_and_price.exhaustive.FixedTimeRow(3, "buffer", 3.5, 5.0),
    ]
    result = branch_and_price.compare_with_exhaustive(rows, 2)
    audit_result(result)
    assert result["integer_maximum_selected_buffers"] == 2.0
    assert parse_scale_pairs(["4:12", "8:24"]) == ((4, 12), (8, 24))
    print("NYC branch-and-price scale self-test: PASS")


def parser() -> argparse.ArgumentParser:
    p = existential.parser()
    p.description = __doc__
    p.set_defaults(
        output_dir=Path("tmp/nyc-hvfhv-branch-and-price-scale"),
        existential_core=16,
        existential_buffers=48,
    )
    p.add_argument("--scale-pairs", nargs="+", default=list(DEFAULT_SCALE_PAIRS))
    p.add_argument("--bp-max-nodes", type=int, default=3000)
    p.add_argument("--bp-time-limit-seconds", type=float, default=180.0)
    p.add_argument("--bp-max-pricing-cases", type=int, default=4096)
    p.add_argument("--require-larger-certified", action="store_true")
    return p


def validate(args: argparse.Namespace) -> None:
    existential.validate(args)
    parse_scale_pairs(args.scale_pairs)
    if args.bp_max_nodes <= 0:
        raise ValueError("--bp-max-nodes must be positive")
    if args.bp_time_limit_seconds <= 0:
        raise ValueError("--bp-time-limit-seconds must be positive")
    if args.bp_max_pricing_cases <= 0:
        raise ValueError("--bp-max-pricing-cases must be positive")


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    write_csv(report, args.output_dir / "branch_and_price_scale_cells.csv")
    print(render(report))
    if (
        args.require_larger_certified
        and report["summary"]["larger_than_small_audit_certified_count"] == 0
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
