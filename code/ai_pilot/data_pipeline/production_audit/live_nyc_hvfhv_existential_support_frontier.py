#!/usr/bin/env python3
"""Support-cardinality frontier for NYC existential timestamp completions.

For one fixed small audit cohort and one declared capacity, this Gate enumerates
the exact-time reachable selected-buffer counts and tests every corresponding
count under artificial nearest-15-minute timestamp supports with existential
latent exact completions. It separates a release effect on *which support
cardinalities are feasible* from outcome composition conditional on a fixed
cardinality.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import live_nyc_hvfhv_existential_time as existential
import live_nyc_hvfhv_existential_time_hybrid as hybrid
import live_nyc_hvfhv_ordered_run_smoke as base
import ordered_run_fixed_time_master as fixed_master
from ordered_run_existential_time import CERTIFIED, build_program, solve


FEASIBLE_STATUSES = {CERTIFIED, "INCUMBENT_ONLY_UNRESOLVED_LIMIT"}


def coarse_feasibility(
    rows,
    capacity: int,
    selected_buffer_count: int,
    epsilon: float,
    time_limit: float,
) -> dict[str, Any]:
    program = build_program(
        rows,
        capacity,
        selected_buffer_count,
        epsilon=epsilon,
    )
    result = solve(
        program,
        np.zeros(program.matrix.shape[1], dtype=float),
        maximize=False,
        time_limit=time_limit,
    )
    if result["status"] in FEASIBLE_STATUSES and result.get("replay") is not None:
        classification = "CERTIFIED_FEASIBLE_WITNESS"
    elif result["status"] == "PROVEN_INFEASIBLE_BY_HIGHS":
        classification = "PROVEN_INFEASIBLE"
    else:
        classification = "UNRESOLVED"
    return {
        "selected_buffer_count": selected_buffer_count,
        "selected_buffers_per_core": selected_buffer_count
        / sum(row.role == "core" for row in rows),
        "classification": classification,
        "solver_status": result["status"],
        "mip_gap": result["mip_gap"],
        "replay": result.get("replay"),
        "variable_count": program.matrix.shape[1],
        "constraint_count": program.matrix.shape[0],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
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
    reduced = existential.reduced_cohort(
        trips,
        args.existential_core,
        args.existential_buffers,
    )
    origin = existential.support_origin(reduced)
    exact_rows = hybrid._fixed_rows(reduced, origin)
    coarse_rows = existential.support_rows(
        reduced,
        "rounded_15m_existential",
        origin,
    )
    exact_support_rows = existential.support_rows(
        reduced,
        "exact_singleton",
        origin,
    )
    containment = existential.support_containment_audit(
        exact_support_rows,
        coarse_rows,
    )
    if containment["status"] != "PASS":
        raise base.LiveDataError(f"support containment failed: {containment}")

    exact_master = fixed_master.build_master(
        exact_rows,
        args.frontier_capacity,
        epsilon=args.overlap_epsilon_seconds,
    )
    exact_frontier = fixed_master.support_frontier(exact_master)
    coarse_frontier = [
        coarse_feasibility(
            coarse_rows,
            args.frontier_capacity,
            count,
            args.overlap_epsilon_seconds,
            args.solver_time_limit,
        )
        for count in range(args.existential_buffers + 1)
    ]

    coarse_by_count = {
        row["selected_buffer_count"]: row for row in coarse_frontier
    }
    contradictions: list[dict[str, Any]] = []
    unresolved_exact_embeddings: list[int] = []
    exact_counts = set(exact_frontier["reachable_selected_buffer_counts"])
    for count in sorted(exact_counts):
        classification = coarse_by_count[count]["classification"]
        if classification == "PROVEN_INFEASIBLE":
            contradictions.append(
                {
                    "reason": "coarse_support_excludes_exact_feasible_count",
                    "selected_buffer_count": count,
                }
            )
        elif classification == "UNRESOLVED":
            unresolved_exact_embeddings.append(count)
    if contradictions:
        raise base.LiveDataError(
            "existential support containment contradiction: "
            + json.dumps(contradictions, sort_keys=True)
        )

    coarse_feasible = {
        row["selected_buffer_count"]
        for row in coarse_frontier
        if row["classification"] == "CERTIFIED_FEASIBLE_WITNESS"
    }
    coarse_infeasible = {
        row["selected_buffer_count"]
        for row in coarse_frontier
        if row["classification"] == "PROVEN_INFEASIBLE"
    }
    coarse_unresolved = {
        row["selected_buffer_count"]
        for row in coarse_frontier
        if row["classification"] == "UNRESOLVED"
    }
    newly_feasible = sorted(coarse_feasible - exact_counts)

    return {
        "report_version": "nyc-hvfhv-existential-support-frontier/v1",
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
            "audit_core_rows": args.existential_core,
            "audit_buffer_rows": args.existential_buffers,
            "selection": (
                "first core rows by frozen source order plus nearest complete "
                "buffers by exact temporal gap; no outcome values used"
            ),
        },
        "capacity": args.frontier_capacity,
        "positive_overlap_margin_seconds": args.overlap_epsilon_seconds,
        "support_containment_audit": containment,
        "exact_singleton_frontier": exact_frontier,
        "coarse_existential_frontier": coarse_frontier,
        "frontier_summary": {
            "exact_feasible_counts": sorted(exact_counts),
            "coarse_certified_feasible_counts": sorted(coarse_feasible),
            "coarse_proven_infeasible_counts": sorted(coarse_infeasible),
            "coarse_unresolved_counts": sorted(coarse_unresolved),
            "newly_feasible_under_coarse_support": newly_feasible,
            "maximum_exact_feasible_count": (
                max(exact_counts) if exact_counts else None
            ),
            "maximum_coarse_certified_feasible_count": (
                max(coarse_feasible) if coarse_feasible else None
            ),
            "exact_feasible_counts_with_unresolved_coarse_embedding": (
                unresolved_exact_embeddings
            ),
        },
        "claim_boundary": {
            "supported": (
                "small-cohort support-cardinality feasibility under exact public "
                "timestamps and a declared artificial existential rounding support"
            ),
            "not_supported": (
                "actual co-riders, actual runs, realized capacity, TLC matching "
                "logic, an actual TLC release operator, or population prevalence"
            ),
        },
        "redaction": {
            "raw_rows_emitted": False,
            "row_identifiers_emitted": False,
            "latent_timestamp_witnesses_emitted": False,
            "aggregate_only": True,
        },
    }


def render(report: dict[str, Any]) -> str:
    summary = report["frontier_summary"]
    lines = [
        "# NYC existential-time support-cardinality frontier",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Capacity: **C={report['capacity']}**.  ",
        f"Audit cohort: **{report['cohort']['audit_core_rows']} core** + "
        f"**{report['cohort']['audit_buffer_rows']} candidate buffers**.",
        "",
        "| Selected buffers | Per core | Exact singleton | Coarse existential |",
        "|---:|---:|---|---|",
    ]
    exact_counts = set(summary["exact_feasible_counts"])
    for row in report["coarse_existential_frontier"]:
        count = row["selected_buffer_count"]
        exact_status = (
            "EXACT_FEASIBLE" if count in exact_counts else "EXACT_INFEASIBLE"
        )
        lines.append(
            f"| {count} | {row['selected_buffers_per_core']:.2f} | "
            f"`{exact_status}` | `{row['classification']}` |"
        )
    lines.extend(
        [
            "",
            f"Exact feasible counts: `{summary['exact_feasible_counts']}`.  ",
            "Coarse-support counts with certified feasible witnesses: "
            f"`{summary['coarse_certified_feasible_counts']}`.  ",
            "Newly feasible under artificial coarse supports: "
            f"`{summary['newly_feasible_under_coarse_support']}`.  ",
            f"Unresolved coarse counts: `{summary['coarse_unresolved_counts']}`.",
            "",
            "The existential model chooses one latent exact timestamp completion "
            "inside each support. It does not treat the full outer envelope as the "
            "realized occupancy interval.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: dict[str, Any], path: Path) -> None:
    exact_counts = set(report["frontier_summary"]["exact_feasible_counts"])
    rows = [
        {
            "capacity": report["capacity"],
            "selected_buffer_count": row["selected_buffer_count"],
            "selected_buffers_per_core": row["selected_buffers_per_core"],
            "exact_classification": (
                "EXACT_FEASIBLE"
                if row["selected_buffer_count"] in exact_counts
                else "EXACT_INFEASIBLE"
            ),
            "coarse_classification": row["classification"],
            "coarse_solver_status": row["solver_status"],
            "coarse_mip_gap": row["mip_gap"],
            "variable_count": row["variable_count"],
            "constraint_count": row["constraint_count"],
        }
        for row in report["coarse_existential_frontier"]
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    rows = [
        fixed_master.FixedTimeRow(0, "core", 0, 2),
        fixed_master.FixedTimeRow(1, "core", 1, 3),
        fixed_master.FixedTimeRow(2, "buffer", 0, 1),
        fixed_master.FixedTimeRow(3, "buffer", 2, 3),
    ]
    exact = fixed_master.support_frontier(
        fixed_master.build_master(rows, 2, epsilon=0.1)
    )
    assert exact["maximum_selected_buffers"] == 2
    print("existential support-cardinality frontier self-test: PASS")


def parser() -> argparse.ArgumentParser:
    argument_parser = existential.parser()
    argument_parser.description = __doc__
    argument_parser.set_defaults(
        output_dir=Path("tmp/nyc-hvfhv-existential-support-frontier"),
    )
    argument_parser.add_argument(
        "--frontier-capacity",
        type=int,
        choices=(2, 3, 4),
        default=2,
    )
    return argument_parser


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        fixed_master.self_test()
        self_test()
        return 0
    existential.validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        render(report),
        encoding="utf-8",
    )
    write_csv(report, args.output_dir / "support_frontier.csv")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
