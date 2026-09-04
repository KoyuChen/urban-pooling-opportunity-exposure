#!/usr/bin/env python3
"""NYC fixed-time ordered-run column-generation audit.

One public four-core/twelve-buffer audit cohort is held fixed. For each declared
capacity, the Dantzig--Wolfe column-generation LP is compared with complete
run-column enumeration, and the generated restricted integer master is compared
with the exact small-instance integer support maximum. Outputs are aggregate
algorithm diagnostics only.
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
import ordered_run_column_generation as column_generation

CAPACITIES = (2, 3, 4)


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
        cell = column_generation.compare_with_exhaustive(
            fixed_rows, capacity, epsilon=args.overlap_epsilon_seconds
        )
        cell["elapsed_seconds"] = time.perf_counter() - started
        if cell["column_generation_status"] != "FULL_MASTER_LP_CERTIFIED_OPTIMAL":
            raise base.LiveDataError(
                f"column generation unresolved at C={capacity}: {cell}"
            )
        if abs(
            float(cell["column_generation_lp_maximum_selected_buffers"])
            - float(cell["full_lp_maximum_selected_buffers"])
        ) > column_generation.TOL:
            raise base.LiveDataError(
                f"column-generation/full-LP disagreement at C={capacity}"
            )
        cells.append(cell)

    gap = column_generation.compare_with_exhaustive(
        column_generation.integrality_gap_counterexample(), 2, epsilon=0.1
    )
    if abs(float(gap["full_master_lp_integrality_gap"]) - 1.0) > column_generation.TOL:
        raise AssertionError("locked master nonintegrality witness changed")

    return {
        "report_version": "nyc-fixed-time-ordered-run-column-generation/v1",
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
        "master_nonintegrality_witness": gap,
        "algorithm_boundary": {
            "certified": (
                "the full fixed-time Dantzig--Wolfe LP relaxation is optimal "
                "when exact rooted pricing returns no negative reduced-cost column"
            ),
            "integer_result": (
                "the generated restricted binary master is a feasible lower "
                "bound; exactness is asserted only where complete small-instance "
                "enumeration agrees"
            ),
            "not_claimed": (
                "a polynomial-time exact algorithm for the full integer "
                "decomposition or a proved complexity classification"
            ),
        },
        "claim_boundary": {
            "supported": (
                "algorithmic validation on one small exact-time public audit "
                "cohort plus deterministic synthetic batteries"
            ),
            "not_supported": (
                "actual co-riders, actual vehicle runs, realized capacity, TLC "
                "production matching logic, or population runtime guarantees"
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
        "# NYC fixed-time ordered-run column-generation audit",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Audit cohort: **{cohort['audit_core_rows']} core** + "
        f"**{cohort['audit_buffer_rows']} buffers**, provider "
        f"`{cohort['provider']}`.",
        "",
        "| C | Full columns | Generated columns | Generated share | Full LP support | Exact integer support | Restricted integer | LP gap | Phase I/II iterations | Oracle LP solves | Seconds |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in report["cells"]:
        restricted = cell["restricted_integer_maximum_selected_buffers"]
        lines.append(
            f"| {cell['capacity']} | {cell['full_run_column_count']} | "
            f"{cell['generated_column_count']} | "
            f"{cell['column_fraction_generated']:.3f} | "
            f"{cell['full_lp_maximum_selected_buffers']:.3f} | "
            f"{cell['exact_integer_maximum_selected_buffers']} | "
            f"{restricted if restricted is not None else '—'} | "
            f"{cell['full_master_lp_integrality_gap']:.3f} | "
            f"{cell['phase_one_iterations']}/{cell['phase_two_iterations']} | "
            f"{cell['total_oracle_lp_solve_count']} | "
            f"{cell['elapsed_seconds']:.2f} |"
        )
    lines.extend(
        [
            "",
            "The exact pricing oracle does not make the coupling master integral. "
            "The locked C=2 counterexample has LP support **4** and exact integer "
            "support **3**, so an exact production solver still needs branching "
            "or another integer-master argument.",
            "",
            "No public row, identifier, generated run column, or selected run "
            "witness is emitted.",
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
        output_dir=Path("tmp/nyc-hvfhv-column-generation"),
        existential_core=4,
        existential_buffers=12,
    )
    return argument_parser


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        column_generation.self_test()
        return 0
    existential.validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    write_csv(report, args.output_dir / "column_generation_cells.csv")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
