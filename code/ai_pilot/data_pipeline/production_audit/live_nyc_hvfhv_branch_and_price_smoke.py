#!/usr/bin/env python3
"""NYC exact-time ordered-run branch-and-price audit.

The same outcome-blind four-core/twelve-buffer public audit cohort used by the
LP column-generation Gate is held fixed.  For capacities two, three, and four,
we solve the full integer support-maximization master by branch-and-price and
compare the certificate with complete small-instance run-column enumeration.
Only aggregate algorithm diagnostics are emitted.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import live_nyc_hvfhv_existential_time as existential
import live_nyc_hvfhv_existential_time_hybrid as hybrid
import live_nyc_hvfhv_ordered_run_smoke as base
import ordered_run_branch_and_price as branch_and_price
import ordered_run_column_generation as column_generation

CAPACITIES = (2, 3, 4)


def _safe_cell(result: dict[str, Any]) -> dict[str, Any]:
    """Drop any accidental witness-like fields before serialization."""

    forbidden = {
        "selected_member_masks",
        "incumbent_masks",
        "columns",
        "column_values",
        "history",
        "node",
    }
    return {key: value for key, value in result.items() if key not in forbidden}


def run(args: argparse.Namespace) -> dict[str, Any]:
    snapshot_before = base.snapshot()
    selected = base.choose_and_fetch(args)
    snapshot_after = base.snapshot()
    if snapshot_before != snapshot_after:
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
    reduced = existential.reduced_cohort(
        trips, args.existential_core, args.existential_buffers
    )
    origin = existential.support_origin(reduced)
    fixed_rows = hybrid._fixed_rows(reduced, origin)

    cells: list[dict[str, Any]] = []
    for capacity in CAPACITIES:
        started = time.perf_counter()
        result = branch_and_price.compare_with_exhaustive(
            fixed_rows,
            capacity,
            epsilon=args.overlap_epsilon_seconds,
            max_nodes=args.bp_max_nodes,
            time_limit_seconds=args.bp_time_limit_seconds,
        )
        result["elapsed_seconds"] = time.perf_counter() - started
        if result["status"] != "INTEGER_OPTIMUM_CERTIFIED":
            raise base.LiveDataError(
                f"integer branch-and-price unresolved at C={capacity}: {result}"
            )
        if abs(
            float(result["integer_maximum_selected_buffers"])
            - float(result["exhaustive_integer_maximum_selected_buffers"])
        ) > branch_and_price.TOL:
            raise base.LiveDataError(
                f"branch-and-price/exhaustive disagreement at C={capacity}"
            )
        cells.append(_safe_cell(result))

    gap = branch_and_price.compare_with_exhaustive(
        column_generation.integrality_gap_counterexample(),
        2,
        epsilon=0.1,
        max_nodes=args.bp_max_nodes,
        time_limit_seconds=args.bp_time_limit_seconds,
    )
    if gap["status"] != "INTEGER_OPTIMUM_CERTIFIED":
        raise AssertionError("locked master nonintegrality witness was not closed")
    if (
        abs(float(gap["root_lp_upper_bound"]) - 4.0) > branch_and_price.TOL
        or abs(float(gap["integer_maximum_selected_buffers"]) - 3.0)
        > branch_and_price.TOL
    ):
        raise AssertionError("locked branch-and-price witness changed")

    return {
        "report_version": "nyc-fixed-time-ordered-run-branch-and-price/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "snapshot": snapshot_after,
        "cohort": {
            "provider": selected["provider"],
            "source_core_start": selected["core_start"].isoformat(),
            "source_core_end": selected["core_end"].isoformat(),
            "source_core_rows": row_audit["core_rows"],
            "source_candidate_rows": row_audit["rows"],
            "audit_core_rows": args.existential_core,
            "audit_buffer_rows": args.existential_buffers,
            "selection": (
                "first core rows by frozen source order plus nearest complete "
                "buffers by exact temporal gap; no outcome values used"
            ),
        },
        "cells": cells,
        "master_nonintegrality_witness": _safe_cell(gap),
        "algorithm_boundary": {
            "certified": (
                "global integer optimality on the declared small exact-time "
                "masters when the branch queue closes; every node LP is closed "
                "by exact branch-compatible interval pricing"
            ),
            "branching": (
                "fractional optional-buffer usage followed by Ryan--Foster "
                "together/separate pair branching"
            ),
            "complexity_boundary": (
                "single-span interval pricing is polynomial, while pricing "
                "under accumulated branch decisions enumerates a finite number "
                "of forced-in/forced-out cases that may grow exponentially with "
                "branch depth"
            ),
            "not_claimed": (
                "polynomial-time solvability of the full integer decomposition "
                "or city-scale runtime from this small audit"
            ),
        },
        "claim_boundary": {
            "supported": (
                "exact integer algorithm validation on one small fixed public "
                "cohort and deterministic exhaustive test batteries"
            ),
            "not_supported": (
                "actual co-riders, vehicle runs, realized capacity, TLC "
                "production matching logic, partner recovery, or population "
                "runtime guarantees"
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
    cohort = report["cohort"]
    lines = [
        "# NYC exact integer ordered-run branch-and-price audit",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Audit cohort: **{cohort['audit_core_rows']} core** + "
        f"**{cohort['audit_buffer_rows']} buffers**, provider "
        f"`{cohort['provider']}`.",
        "",
        "| C | Full columns | Root LP UB | Certified IP | Root gap | Nodes | Buffer/pair branches | Max depth | Oracle LP solves | Pricing cases | Seconds |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in report["cells"]:
        lines.append(
            f"| {cell['capacity']} | {cell['full_run_column_count']} | "
            f"{cell['root_lp_upper_bound']:.3f} | "
            f"{cell['integer_maximum_selected_buffers']:.0f} | "
            f"{cell['root_integrality_gap']:.3f} | "
            f"{cell['nodes_processed']} | "
            f"{cell['buffer_branches']}/{cell['pair_branches']} | "
            f"{cell['maximum_depth']} | "
            f"{cell['total_oracle_lp_solve_count']} | "
            f"{cell['total_pricing_case_count']} | "
            f"{cell['elapsed_seconds']:.2f} |"
        )
    lines.extend(
        [
            "",
            "Every displayed integer value was independently matched by the "
            "complete small-instance run-column master. The locked nonintegral "
            "master has root LP value **4** and certified integer value **3**, "
            "so the branching layer is substantive rather than cosmetic.",
            "",
            "The result is an exact medium-instance algorithmic audit, not a "
            "claim of polynomial full-master complexity or city-scale partner "
            "recovery. No row, identifier, run column, or selected-run witness "
            "is emitted.",
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


def parser() -> argparse.ArgumentParser:
    argument_parser = existential.parser()
    argument_parser.description = __doc__
    argument_parser.set_defaults(
        output_dir=Path("tmp/nyc-hvfhv-branch-and-price"),
        existential_core=4,
        existential_buffers=12,
    )
    argument_parser.add_argument("--bp-max-nodes", type=int, default=5000)
    argument_parser.add_argument(
        "--bp-time-limit-seconds", type=float, default=900.0
    )
    return argument_parser


def validate(args: argparse.Namespace) -> None:
    existential.validate(args)
    if args.bp_max_nodes <= 0:
        raise ValueError("--bp-max-nodes must be positive")
    if args.bp_time_limit_seconds <= 0:
        raise ValueError("--bp-time-limit-seconds must be positive")


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        branch_and_price.self_test()
        return 0
    validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    write_csv(report, args.output_dir / "branch_and_price_cells.csv")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
