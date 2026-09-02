#!/usr/bin/env python3
"""Hybrid exact/coarse solver for the NYC existential timestamp Gate.

The exact-singleton side uses the existing compact interval-segment ordered-run
formulation. Only the artificial coarse-support side needs the continuous-time
existential completion MILP. This removes unnecessary seat/order symmetry from
exact public timestamps while leaving the estimand, cohort, and claim boundary
unchanged.
"""

from __future__ import annotations

import json
from datetime import timezone, datetime
from pathlib import Path
from typing import Any

import live_nyc_hvfhv_existential_time as existential
import live_nyc_hvfhv_ordered_common_support as deterministic_common
import live_nyc_hvfhv_ordered_run_smoke as base


def run(args) -> dict[str, Any]:
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
        trips,
        args.existential_core,
        args.existential_buffers,
    )

    common_buffer_float = args.common_buffers_per_core * args.existential_core
    common_buffer_count = int(round(common_buffer_float))
    if abs(common_buffer_float - common_buffer_count) > existential.TOL:
        raise base.LiveDataError(
            "common buffers/core times core count must be an integer"
        )
    if common_buffer_count <= 0:
        raise base.LiveDataError("common selected-buffer count must be positive")

    origin = existential.support_origin(reduced)
    exact_support = existential.support_rows(
        reduced,
        "exact_singleton",
        origin,
    )
    coarse_support = existential.support_rows(
        reduced,
        "rounded_15m_existential",
        origin,
    )
    containment = existential.support_containment_audit(
        exact_support,
        coarse_support,
    )
    if containment["status"] != "PASS":
        raise base.LiveDataError(f"support containment failed: {containment}")

    # Singleton exact times do not need continuous endpoint, seat-order, or
    # overlap-edge binaries. The compact deterministic formulation is exact for
    # these fixed intervals and already carries replay/capacity audits.
    exact_rows = base.model_rows(reduced, "exact_second")
    exact_cells = [
        deterministic_common.solve_common_cell(
            exact_rows,
            capacity,
            args.common_buffers_per_core,
            args.solver_time_limit,
        )
        for capacity in existential.CAPACITIES
    ]

    # Coarse released supports require choosing one latent exact completion.
    coarse_cells = [
        existential.solve_cell(
            coarse_support,
            capacity,
            common_buffer_count,
            args.overlap_epsilon_seconds,
            args.solver_time_limit,
        )
        for capacity in existential.CAPACITIES
    ]
    cells_by_time = {
        "exact_singleton": exact_cells,
        "rounded_15m_existential": coarse_cells,
    }

    capacity_audits = {
        time_model: existential.capacity_audit(cells)
        for time_model, cells in cells_by_time.items()
    }
    time_audit = existential.time_nesting_audit(cells_by_time)
    for time_model, audit in capacity_audits.items():
        if audit["problems"]:
            raise base.LiveDataError(
                f"capacity nestedness failed for {time_model}: {audit}"
            )
    if time_audit["problems"]:
        raise base.LiveDataError(
            f"existential time nestedness failed: {time_audit}"
        )

    if args.require_all_certified:
        unresolved = [
            {
                "time_model": time_model,
                "capacity": cell["capacity"],
                "status": cell["status"],
                "outcome_statuses": [
                    row["status"] for row in cell.get("outcomes", [])
                ],
            }
            for time_model, cells in cells_by_time.items()
            for cell in cells
            if cell["status"] != "CERTIFIED_COMMON_SUPPORT_FEASIBILITY"
            or any(
                row["status"] != "CERTIFIED_OPTIMAL_PAIR"
                for row in cell.get("outcomes", [])
            )
        ]
        if unresolved:
            raise base.LiveDataError(
                "not every existential-time cell was certified: "
                + json.dumps(unresolved[:8], sort_keys=True)
            )

    return {
        "report_version": "nyc-hvfhv-ordered-existential-time/v2-hybrid-exact",
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
            "existential_core_rows": args.existential_core,
            "existential_buffer_rows": args.existential_buffers,
            "reduced_rows": len(reduced),
            "selection": (
                "first core rows by frozen source order plus nearest complete "
                "buffer rows by exact temporal gap; no outcome values used for ranking"
            ),
        },
        "common_support": {
            "selected_buffers_per_core": args.common_buffers_per_core,
            "selected_buffer_count": common_buffer_count,
        },
        "time_support": {
            "exact_singleton": "public exact pickup/drop-off times fixed",
            "rounded_15m_existential": (
                "latent pickup and drop-off independently selected inside "
                "nearest-15-minute +/-7.5-minute supports"
            ),
            "positive_overlap_margin_seconds": args.overlap_epsilon_seconds,
            "support_containment_audit": containment,
        },
        "solver_assignment": {
            "exact_singleton": (
                "compact deterministic interval-segment ordered-run MILP"
            ),
            "rounded_15m_existential": (
                "continuous-time support-completion MILP with exact interval "
                "coloring capacity and rooted overlap connectivity"
            ),
        },
        "cells_by_time": cells_by_time,
        "capacity_audits": capacity_audits,
        "time_nesting_audit": time_audit,
        "estimand": (
            "mean public miles or trip duration among one common number of "
            "selected buffer rows across exact and existential coarse-time worlds"
        ),
        "claim_boundary": {
            "supported": (
                "small-cohort feasible-world bounds under a declared artificial "
                "independent rounding-support model"
            ),
            "not_supported": (
                "actual TLC timestamp coarsening, actual co-rider identities, "
                "actual vehicle runs, realized capacity, production matching "
                "logic, or a NYC population estimate"
            ),
        },
        "redaction": {
            "raw_rows_emitted": False,
            "row_identifiers_emitted": False,
            "latent_timestamp_witnesses_emitted": False,
            "aggregate_only": True,
        },
    }


def main() -> int:
    args = existential.parser().parse_args()
    if args.self_test:
        existential.self_test()
        return 0
    existential.validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        existential.render(report),
        encoding="utf-8",
    )
    existential.write_csv(
        report,
        args.output_dir / "existential_time_bounds.csv",
    )
    print(existential.render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
