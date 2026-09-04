#!/usr/bin/env python3
"""Solve one NYC existential-time panel window for C=2,3,4 after one fetch.

The previous panel launched one live Socrata extraction per window-capacity cell.
That repeated the identical public-data query three times and exposed otherwise
valid cells to avoidable portal timeouts.  This wrapper fetches, audits, and
reduces one window exactly once, then solves all declared capacities offline on
that same frozen in-memory cohort.

Outputs retain the existing per-capacity layout (`C2`, `C3`, `C4`) so the panel
aggregator can consume them unchanged.  No raw rows, row identifiers, selected
runs, or latent timestamp witnesses are serialized.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import live_nyc_hvfhv_existential_support_frontier as frontier
import live_nyc_hvfhv_existential_time as existential
import live_nyc_hvfhv_existential_time_hybrid as hybrid
import live_nyc_hvfhv_ordered_run_smoke as base
import ordered_run_fixed_time_master as fixed_master

CAPACITIES = (2, 3, 4)


def prepare_once(args: argparse.Namespace) -> dict[str, Any]:
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
    origin = existential.support_origin(reduced)
    exact_rows = hybrid._fixed_rows(reduced, origin)
    exact_support_rows = existential.support_rows(
        reduced,
        "exact_singleton",
        origin,
    )
    coarse_rows = existential.support_rows(
        reduced,
        "rounded_15m_existential",
        origin,
    )
    containment = existential.support_containment_audit(
        exact_support_rows,
        coarse_rows,
    )
    if containment["status"] != "PASS":
        raise base.LiveDataError(f"support containment failed: {containment}")

    return {
        "snapshot": snapshot_after,
        "selected": selected,
        "row_audit": row_audit,
        "reduced": reduced,
        "exact_rows": exact_rows,
        "coarse_rows": coarse_rows,
        "containment": containment,
    }


def solve_capacity(
    prepared: dict[str, Any],
    args: argparse.Namespace,
    capacity: int,
) -> dict[str, Any]:
    exact_master = fixed_master.build_master(
        prepared["exact_rows"],
        capacity,
        epsilon=args.overlap_epsilon_seconds,
    )
    exact_frontier = fixed_master.support_frontier(exact_master)
    coarse_frontier = [
        frontier.coarse_feasibility(
            prepared["coarse_rows"],
            capacity,
            count,
            args.overlap_epsilon_seconds,
            args.solver_time_limit,
        )
        for count in range(args.existential_buffers + 1)
    ]

    coarse_by_count = {
        row["selected_buffer_count"]: row for row in coarse_frontier
    }
    exact_counts = set(exact_frontier["reachable_selected_buffer_counts"])
    contradictions: list[dict[str, Any]] = []
    unresolved_exact_embeddings: list[int] = []
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
    selected = prepared["selected"]
    row_audit = prepared["row_audit"]
    return {
        "report_version": "nyc-hvfhv-existential-support-frontier/v2-window-cache",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "snapshot": prepared["snapshot"],
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
            "window_fetch_reused_across_capacities": True,
        },
        "capacity": capacity,
        "positive_overlap_margin_seconds": args.overlap_epsilon_seconds,
        "support_containment_audit": prepared["containment"],
        "exact_singleton_frontier": exact_frontier,
        "coarse_existential_frontier": coarse_frontier,
        "frontier_summary": {
            "exact_feasible_counts": sorted(exact_counts),
            "coarse_certified_feasible_counts": sorted(coarse_feasible),
            "coarse_proven_infeasible_counts": sorted(coarse_infeasible),
            "coarse_unresolved_counts": sorted(coarse_unresolved),
            "newly_feasible_under_coarse_support": sorted(
                coarse_feasible - exact_counts
            ),
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


def audit_capacity_reports(reports: dict[int, dict[str, Any]]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    cohort_keys = {
        (
            report["cohort"]["provider"],
            report["cohort"]["source_core_start"],
            report["cohort"]["source_core_end"],
            report["cohort"]["audit_core_rows"],
            report["cohort"]["audit_buffer_rows"],
        )
        for report in reports.values()
    }
    snapshot_keys = {
        report["snapshot"]["revision_fingerprint_sha256"]
        for report in reports.values()
    }
    if len(cohort_keys) != 1:
        problems.append({"reason": "cohort_changed_across_capacity"})
    if len(snapshot_keys) != 1:
        problems.append({"reason": "snapshot_changed_across_capacity"})

    for left, right in zip(CAPACITIES, CAPACITIES[1:]):
        left_exact = set(
            reports[left]["frontier_summary"]["exact_feasible_counts"]
        )
        right_exact = set(
            reports[right]["frontier_summary"]["exact_feasible_counts"]
        )
        if not left_exact <= right_exact:
            problems.append(
                {
                    "reason": "exact_capacity_nesting_violation",
                    "left": left,
                    "right": right,
                    "counts": sorted(left_exact - right_exact),
                }
            )

        left_coarse = set(
            reports[left]["frontier_summary"][
                "coarse_certified_feasible_counts"
            ]
        )
        right_infeasible = set(
            reports[right]["frontier_summary"][
                "coarse_proven_infeasible_counts"
            ]
        )
        contradiction = sorted(left_coarse & right_infeasible)
        if contradiction:
            problems.append(
                {
                    "reason": "coarse_capacity_feasibility_contradiction",
                    "left": left,
                    "right": right,
                    "counts": contradiction,
                }
            )
    return {
        "status": "PASS" if not problems else "FAIL",
        "problem_count": len(problems),
        "problems": problems,
        "cohort_key_count": len(cohort_keys),
        "snapshot_key_count": len(snapshot_keys),
    }


def render_window(
    label: str,
    reports: dict[int, dict[str, Any]],
    audit: dict[str, Any],
) -> str:
    first = reports[CAPACITIES[0]]
    lines = [
        f"# NYC existential timestamp panel window: {label}",
        "",
        f"Selected public core: `{first['cohort']['source_core_start']}`--"
        f"`{first['cohort']['source_core_end']}`; provider "
        f"`{first['cohort']['provider']}`.",
        "",
        "The public extraction and outcome-blind cohort reduction were executed "
        "once and reused for C=2,3,4.",
        "",
        "| C | Exact maximum buffers | Coarse certified maximum | Gain lower bound | Coarse unresolved counts |",
        "|---:|---:|---:|---:|---|",
    ]
    for capacity in CAPACITIES:
        summary = reports[capacity]["frontier_summary"]
        exact_max = summary["maximum_exact_feasible_count"]
        coarse_max = summary["maximum_coarse_certified_feasible_count"]
        gain = (
            None
            if exact_max is None or coarse_max is None
            else max(0, coarse_max - exact_max)
        )
        lines.append(
            f"| {capacity} | {exact_max} | {coarse_max} | {gain} | "
            f"`{summary['coarse_unresolved_counts'] or 'none'}` |"
        )
    lines.extend(
        [
            "",
            f"Cross-capacity audit: `{audit['status']}`.",
            "",
            "All gains are lower bounds based on certified feasible coarse "
            "witnesses. Unresolved counts are not treated as infeasible. This is "
            "an artificial timestamp-support experiment, not a reconstruction of "
            "co-riders, vehicle runs, realized capacity, or TLC production logic.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    output_dir: Path,
    label: str,
    scan_start: str,
    scan_end: str,
    reports: dict[int, dict[str, Any]],
    audit: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for capacity, report in reports.items():
        capacity_dir = output_dir / f"C{capacity}"
        capacity_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "window_label": label,
            "scan_start": scan_start,
            "scan_end": scan_end,
            "capacity": capacity,
            "process_exit_status": 0,
            "one_fetch_per_window": True,
        }
        (capacity_dir / "panel_cell.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (capacity_dir / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (capacity_dir / "REPORT.md").write_text(
            frontier.render(report),
            encoding="utf-8",
        )
        frontier.write_csv(report, capacity_dir / "support_frontier.csv")

    window_report = {
        "report_version": "nyc-existential-support-panel-window/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "window_label": label,
        "scan_start": scan_start,
        "scan_end": scan_end,
        "capacity_audit": audit,
        "capacities": {
            str(capacity): report["frontier_summary"]
            for capacity, report in reports.items()
        },
        "claim_boundary": {
            "supported": (
                "descriptive within-window support-frontier comparison under one "
                "reused public extraction and the declared artificial supports"
            ),
            "not_supported": (
                "population prevalence, actual TLC release semantics, actual "
                "co-riders or runs, realized capacity, or causal effects"
            ),
        },
    }
    (output_dir / "window_report.json").write_text(
        json.dumps(window_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "WINDOW_REPORT.md").write_text(
        render_window(label, reports, audit),
        encoding="utf-8",
    )


def self_test() -> None:
    def report(capacity: int, exact_counts: list[int], coarse: list[int]):
        return {
            "cohort": {
                "provider": "HV0005",
                "source_core_start": "2023-01-01T00:00:00",
                "source_core_end": "2023-01-01T00:15:00",
                "audit_core_rows": 4,
                "audit_buffer_rows": 12,
            },
            "snapshot": {"revision_fingerprint_sha256": "snapshot"},
            "frontier_summary": {
                "exact_feasible_counts": exact_counts,
                "coarse_certified_feasible_counts": coarse,
                "coarse_proven_infeasible_counts": [],
                "coarse_unresolved_counts": [],
                "maximum_exact_feasible_count": max(exact_counts),
                "maximum_coarse_certified_feasible_count": max(coarse),
            },
        }

    reports = {
        2: report(2, [0, 2, 4], list(range(9))),
        3: report(3, list(range(9)), list(range(13))),
        4: report(4, list(range(13)), list(range(13))),
    }
    audit = audit_capacity_reports(reports)
    assert audit["status"] == "PASS", audit
    reports[3]["frontier_summary"]["coarse_proven_infeasible_counts"] = [4]
    audit = audit_capacity_reports(reports)
    assert audit["status"] == "FAIL", audit
    print("NYC existential panel-window self-test: PASS")


def parser() -> argparse.ArgumentParser:
    argument_parser = frontier.parser()
    argument_parser.description = __doc__
    argument_parser.set_defaults(
        output_dir=Path("tmp/nyc-existential-panel-window"),
    )
    argument_parser.add_argument("--window-label", required=False, default="window")
    return argument_parser


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    existential.validate(args)
    prepared = prepare_once(args)
    reports = {
        capacity: solve_capacity(prepared, args, capacity)
        for capacity in CAPACITIES
    }
    audit = audit_capacity_reports(reports)
    if audit["status"] != "PASS":
        raise base.LiveDataError(
            "cross-capacity panel-window audit failed: "
            + json.dumps(audit["problems"], sort_keys=True)
        )
    write_outputs(
        args.output_dir,
        args.window_label,
        args.scan_start,
        args.scan_end,
        reports,
        audit,
    )
    print(render_window(args.window_label, reports, audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
