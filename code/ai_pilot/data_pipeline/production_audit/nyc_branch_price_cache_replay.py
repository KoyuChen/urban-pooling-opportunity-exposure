#!/usr/bin/env python3
"""Paired cache audit on a snapshot-consistent reconstruction of NYC scale cells.

The 2026-09-04 scale artifacts intentionally redacted row-level inputs and did
not record a fixed-row hash.  Therefore this program never calls its input a
byte-identical replay.  It rebuilds the declared deterministic cohort only if
the public dataset fingerprint, selected provider/window, and source counts
exactly match the frozen report.  The cache-off run must also reproduce the
historical certificate and branch-path diagnostics before the cache-on result
is interpreted as an acceleration.

Raw rows, identifiers, run columns, and selected witnesses are never emitted.
Timeouts and numerical failures remain unresolved.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import live_nyc_hvfhv_branch_and_price_scale as scale  # noqa: E402
import live_nyc_hvfhv_existential_time as existential  # noqa: E402
import live_nyc_hvfhv_existential_time_hybrid as hybrid  # noqa: E402
import live_nyc_hvfhv_ordered_run_smoke as base  # noqa: E402
import ordered_run_branch_and_price as solver  # noqa: E402


VERSION = "nyc-branch-price-cache-reconstruction/v1"
TARGETS = {(10, 4), (12, 4), (16, 3), (16, 4)}
FROZEN_CELLS = (
    ROOT
    / "code"
    / "ai_pilot"
    / "data_pipeline"
    / "results"
    / "nyc_hvfhv"
    / "BRANCH_AND_PRICE_SCALE_CELLS.csv"
)
FROZEN_SNAPSHOT = {
    "dataset_id": "u253-aew4",
    "dataset_name": "2023 High Volume FHV Trip Data",
    "publication_date": 1719935304,
    "revision_fingerprint_sha256": (
        "0041ce9fa9edf98f5075978a94468c41ca6679a11d4ca6dca48f2671fb4907d1"
    ),
    "rows_updated_at": 1721064543,
    "schema_sha256": (
        "b3375715369026ce50c2d7a3501e4bed773f309ea510a45e00937bd436a25710"
    ),
    "view_last_modified": 1721155212,
}
FROZEN_COHORT = {
    "provider": "HV0005",
    "source_core_start": "2023-01-03T17:45:00",
    "source_core_end": "2023-01-03T18:00:00",
    "source_core_rows": 38,
    "source_candidate_rows": 437,
}
PATH_FIELDS = (
    "status",
    "integer_maximum_selected_buffers",
    "global_lower_bound",
    "global_upper_bound",
    "root_lp_upper_bound",
    "nodes_processed",
    "nodes_infeasible",
    "nodes_bound_pruned",
    "nodes_integral",
    "buffer_branches",
    "pair_branches",
    "maximum_depth",
    "selected_column_count",
    "total_generated_columns_across_nodes",
    "total_pricing_case_count",
    "maximum_pricing_cases_for_one_root",
)
INTEGER_HISTORICAL_FIELDS = (
    "nodes_processed",
    "nodes_infeasible",
    "nodes_bound_pruned",
    "nodes_integral",
    "buffer_branches",
    "pair_branches",
    "maximum_depth",
    "selected_column_count",
    "total_generated_columns_across_nodes",
    "total_pricing_case_count",
    "maximum_pricing_cases_for_one_root",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


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


def certificate_view(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result.get(field) for field in PATH_FIELDS}


def assert_pair_equal(
    baseline: dict[str, Any], accelerated: dict[str, Any]
) -> None:
    if certificate_view(baseline) != certificate_view(accelerated):
        raise AssertionError("cache switch changed certificate or branch path")


def frozen_cell(core_rows: int, capacity: int) -> dict[str, str]:
    import csv

    with FROZEN_CELLS.open(encoding="utf-8", newline="") as handle:
        matches = [
            row
            for row in csv.DictReader(handle)
            if int(row["core_rows"]) == core_rows
            and int(row["capacity"]) == capacity
        ]
    if len(matches) != 1:
        raise ValueError("frozen cell table does not contain exactly one target")
    return matches[0]


def historical_path_matches(
    baseline: dict[str, Any], historical: dict[str, str]
) -> bool:
    if baseline.get("status") != historical["status"]:
        return False
    for field in INTEGER_HISTORICAL_FIELDS:
        if int(baseline.get(field, -1)) != int(historical[field]):
            return False
    for field in (
        "integer_maximum_selected_buffers",
        "global_lower_bound",
        "global_upper_bound",
        "root_lp_upper_bound",
    ):
        if abs(float(baseline[field]) - float(historical[field])) > 1e-7:
            return False
    return True


def assert_frozen_source(
    snapshot: dict[str, Any], selected: dict[str, Any], row_audit: dict[str, Any]
) -> None:
    if snapshot != FROZEN_SNAPSHOT:
        raise ValueError("public dataset fingerprint differs from frozen scale report")
    observed = {
        "provider": selected["provider"],
        "source_core_start": selected["core_start"].isoformat(),
        "source_core_end": selected["core_end"].isoformat(),
        "source_core_rows": int(row_audit["core_rows"]),
        "source_candidate_rows": int(row_audit["rows"]),
    }
    if observed != FROZEN_COHORT:
        raise ValueError("deterministic source cohort differs from frozen scale report")


def run_variant(
    rows: list[Any], capacity: int, args: argparse.Namespace, *, cache: bool
) -> dict[str, Any]:
    result = solver.branch_and_price_max_support(
        rows,
        capacity,
        max_nodes=args.bp_max_nodes,
        time_limit_seconds=args.solver_time_limit,
        max_pricing_cases=args.bp_max_pricing_cases,
        use_pricing_cache=cache,
    )
    scale.audit_result(result)
    return safe_result(result)


def run_live(args: argparse.Namespace) -> dict[str, Any]:
    target = (args.target_core, args.capacity)
    if target not in TARGETS:
        raise ValueError(f"target must be one of {sorted(TARGETS)}")

    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError("dataset metadata changed during extraction")
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
    assert_frozen_source(after, selected, row_audit)

    reduced = existential.reduced_cohort(
        trips, args.target_core, 3 * args.target_core
    )
    origin = existential.support_origin(reduced)
    rows = hybrid._fixed_rows(reduced, origin)
    input_sha256 = sha256_bytes(stable_json([asdict(row) for row in rows]))
    historical = frozen_cell(args.target_core, args.capacity)

    order = [args.first, "accelerated" if args.first == "baseline" else "baseline"]
    variants: dict[str, dict[str, Any]] = {}
    for label in order:
        variants[label] = run_variant(
            rows, args.capacity, args, cache=(label == "accelerated")
        )
    assert_pair_equal(variants["baseline"], variants["accelerated"])
    historical_match = historical_path_matches(variants["baseline"], historical)
    if not historical_match:
        raise AssertionError(
            "snapshot-consistent baseline did not reproduce historical diagnostics"
        )

    baseline_lp = int(variants["baseline"]["total_oracle_lp_solve_count"])
    accelerated_lp = int(variants["accelerated"]["total_oracle_lp_solve_count"])
    return {
        "report_version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "target": {
            "core_rows": args.target_core,
            "buffer_rows": 3 * args.target_core,
            "capacity": args.capacity,
        },
        "source": {
            "snapshot": after,
            "cohort": dict(FROZEN_COHORT),
            "snapshot_matches_frozen_report": True,
            "cohort_counts_match_frozen_report": True,
            "byte_identical_old_input_claim": False,
            "reason": (
                "historical artifacts contain no row payload or fixed-row hash"
            ),
        },
        "reconstructed_fixed_input_sha256": input_sha256,
        "variant_order": order,
        "certificate_and_branch_path_equal": True,
        "baseline_matches_historical_diagnostics": historical_match,
        "baseline": variants["baseline"],
        "accelerated": variants["accelerated"],
        "oracle_lp_call_reduction": baseline_lp - accelerated_lp,
        "oracle_lp_call_reduction_rate": (
            (baseline_lp - accelerated_lp) / baseline_lp if baseline_lp else 0.0
        ),
        "redaction": {
            "raw_rows_emitted": False,
            "row_identifiers_emitted": False,
            "run_columns_emitted": False,
            "selected_witnesses_emitted": False,
        },
        "claim_boundary": (
            "snapshot-consistent deterministic cohort reconstruction with exact "
            "historical diagnostic replay; not byte-identical old input, city-scale "
            "runtime, operational run recovery, or population prevalence"
        ),
        "historical_lp_counter_comparable": False,
        "historical_lp_counter_note": (
            "the old counter incremented on pre-LP rejects; the paired audit counts "
            "only actual linprog calls"
        ),
    }


def render_cell(report: dict[str, Any]) -> str:
    target = report["target"]
    baseline = report["baseline"]
    accelerated = report["accelerated"]
    reduction = 100 * report["oracle_lp_call_reduction_rate"]
    return "\n".join(
        [
            "# NYC branch-and-price cache reconstruction",
            "",
            f"Target: **{target['core_rows']} core + {target['buffer_rows']} buffer, "
            f"C={target['capacity']}**.",
            "",
            "The public snapshot fingerprint, deterministic window/provider, and source "
            "counts match the frozen scale report. The cache-off run also reproduces "
            "its historical certificate and branch-path diagnostics.",
            "",
            f"- Baseline fixed-span LP calls: **{baseline['total_oracle_lp_solve_count']:,}**",
            f"- Cached fixed-span LP calls: **{accelerated['total_oracle_lp_solve_count']:,}**",
            f"- Reduction: **{reduction:.1f}%**",
            f"- Baseline seconds: **{baseline['elapsed_seconds']:.3f}**",
            f"- Cached seconds: **{accelerated['elapsed_seconds']:.3f}**",
            "- Certificate and branch path equal: **yes**",
            "",
            "This is not called a byte-identical replay: the historical artifacts "
            "redacted rows and did not record a fixed-row hash. Runtime is descriptive.",
            "",
        ]
    )


def aggregate_reports(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(reports)
    observed = {
        (int(row["target"]["core_rows"]), int(row["target"]["capacity"]))
        for row in rows
    }
    if observed != TARGETS or len(rows) != len(TARGETS):
        raise ValueError("aggregate requires exactly the four predeclared targets")
    if not all(row["report_version"] == VERSION for row in rows):
        raise ValueError("report version mismatch")
    if not all(row["certificate_and_branch_path_equal"] for row in rows):
        raise ValueError("at least one cache pair changed its certificate")
    if not all(row["baseline_matches_historical_diagnostics"] for row in rows):
        raise ValueError("at least one reconstruction missed historical diagnostics")
    rows.sort(key=lambda row: (row["target"]["core_rows"], row["target"]["capacity"]))
    baseline_lp = sum(
        int(row["baseline"]["total_oracle_lp_solve_count"]) for row in rows
    )
    accelerated_lp = sum(
        int(row["accelerated"]["total_oracle_lp_solve_count"]) for row in rows
    )
    baseline_seconds = sum(float(row["baseline"]["elapsed_seconds"]) for row in rows)
    accelerated_seconds = sum(
        float(row["accelerated"]["elapsed_seconds"]) for row in rows
    )
    return {
        "report_version": VERSION,
        "cell_count": len(rows),
        "all_certificates_and_branch_paths_equal": True,
        "all_baselines_match_historical_diagnostics": True,
        "all_sources_match_frozen_snapshot_and_cohort_counts": True,
        "byte_identical_old_input_claim": False,
        "total_baseline_oracle_lp_calls": baseline_lp,
        "total_accelerated_oracle_lp_calls": accelerated_lp,
        "total_oracle_lp_call_reduction": baseline_lp - accelerated_lp,
        "total_oracle_lp_call_reduction_rate": (
            (baseline_lp - accelerated_lp) / baseline_lp if baseline_lp else 0.0
        ),
        "total_baseline_elapsed_seconds": baseline_seconds,
        "total_accelerated_elapsed_seconds": accelerated_seconds,
        "descriptive_elapsed_time_reduction_rate": (
            (baseline_seconds - accelerated_seconds) / baseline_seconds
            if baseline_seconds
            else 0.0
        ),
        "runtime_win_cells": sum(
            float(row["accelerated"]["elapsed_seconds"])
            < float(row["baseline"]["elapsed_seconds"])
            for row in rows
        ),
        "cells": rows,
        "claim_boundary": (
            "four dominant cells on a snapshot-consistent deterministic reconstruction; "
            "not byte-identical historical inputs, city-scale runtime, operational run "
            "recovery, or population prevalence"
        ),
    }


def render_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# NYC dominant-cell pricing-cache reconstruction",
        "",
        "| Cell | Baseline LP | Cached LP | Reduction | Baseline s | Cached s |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary["cells"]:
        target = row["target"]
        baseline = row["baseline"]
        accelerated = row["accelerated"]
        lines.append(
            f"| {target['core_rows']}+{target['buffer_rows']}, C={target['capacity']} "
            f"| {baseline['total_oracle_lp_solve_count']:,} "
            f"| {accelerated['total_oracle_lp_solve_count']:,} "
            f"| {100 * row['oracle_lp_call_reduction_rate']:.1f}% "
            f"| {baseline['elapsed_seconds']:.2f} | {accelerated['elapsed_seconds']:.2f} |"
        )
    lines.extend(
        [
            "",
            "All four cache-off runs reproduce the historical integer certificate and "
            "branch-path diagnostics; all cache-on pairs preserve them. Actual fixed-span "
            f"LP calls fall from **{summary['total_baseline_oracle_lp_calls']:,}** to "
            f"**{summary['total_accelerated_oracle_lp_calls']:,}** "
            f"(**{100 * summary['total_oracle_lp_call_reduction_rate']:.1f}%**).",
            f"The cached variant is faster in **{summary['runtime_win_cells']}/"
            f"{summary['cell_count']}** runner-specific pairs; aggregate elapsed time "
            f"falls by **{100 * summary['descriptive_elapsed_time_reduction_rate']:.1f}%**.",
            "",
            "The source metadata and deterministic cohort counts match the frozen report, "
            "but old artifacts contain neither rows nor an input hash. This is therefore a "
            "snapshot-consistent reconstruction, not a byte-identical replay. Runtime is "
            "runner-specific.",
            "",
        ]
    )
    return "\n".join(lines)


def render_tex(summary: dict[str, Any]) -> str:
    reduction = 100 * summary["total_oracle_lp_call_reduction_rate"]
    runtime_reduction = 100 * summary["descriptive_elapsed_time_reduction_rate"]
    return "\n".join(
        [
            "% Generated by nyc_branch_price_cache_replay.py; do not edit by hand.",
            "\\paragraph{Dominant-cell pricing-cache reconstruction.}",
            "The four cells responsible for 88.0\\% of the frozen lattice runtime ",
            "were reconstructed from the matching public snapshot, provider, window, ",
            "and source counts.  Every cache-off run reproduced the historical integer ",
            "certificate and branch-path diagnostics, and every cache-on run preserved ",
            "them.  Actual fixed-span LP calls fell from ",
            f"{summary['total_baseline_oracle_lp_calls']:,} to ",
            f"{summary['total_accelerated_oracle_lp_calls']:,} ({reduction:.1f}\\%).  ",
            f"The cached variant was faster in {summary['runtime_win_cells']}/"
            f"{summary['cell_count']} runner-specific pairs (aggregate elapsed-time ",
            f"reduction {runtime_reduction:.1f}\\%).  Historical artifacts retained ",
            "neither row payloads nor a fixed-input hash, so this is a snapshot-consistent ",
            "deterministic reconstruction rather than a byte-identical replay or a ",
            "city-scale runtime claim.",
            "",
        ]
    )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_cell_outputs(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / "report.json", report)
    (output_dir / "REPORT.md").write_text(render_cell(report), encoding="utf-8")
    write_json(
        output_dir / "MANIFEST.json",
        {
            "report_version": VERSION,
            "report_sha256": sha256_file(output_dir / "report.json"),
            "solver_sha256": sha256_file(HERE / "ordered_run_branch_and_price.py"),
            "runner_sha256": sha256_file(Path(__file__)),
            "frozen_cell_table_sha256": sha256_file(FROZEN_CELLS),
        },
    )


def aggregate_directory(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    paths = sorted(input_dir.rglob("report.json"))
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    summary = aggregate_reports(reports)
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / "SUMMARY.json", summary)
    (output_dir / "REPORT.md").write_text(
        render_summary(summary), encoding="utf-8"
    )
    (output_dir / "RESULTS.tex").write_text(render_tex(summary), encoding="utf-8")
    write_json(
        output_dir / "MANIFEST.json",
        {
            "report_version": VERSION,
            "input_report_sha256": {
                f"{row['target']['core_rows']}:{row['target']['capacity']}":
                sha256_bytes(stable_json(row))
                for row in summary["cells"]
            },
            "summary_sha256": sha256_file(output_dir / "SUMMARY.json"),
            "report_sha256": sha256_file(output_dir / "REPORT.md"),
            "tex_sha256": sha256_file(output_dir / "RESULTS.tex"),
            "runner_sha256": sha256_file(Path(__file__)),
        },
    )
    return summary


def self_test() -> None:
    rows = [
        solver.exhaustive.FixedTimeRow(0, "core", 0, 3),
        solver.exhaustive.FixedTimeRow(1, "core", 2, 5),
        solver.exhaustive.FixedTimeRow(2, "buffer", 1, 4),
        solver.exhaustive.FixedTimeRow(3, "buffer", 3, 6),
    ]
    baseline = solver.branch_and_price_max_support(
        rows, 2, time_limit_seconds=30, use_pricing_cache=False
    )
    accelerated = solver.branch_and_price_max_support(
        rows, 2, time_limit_seconds=30, use_pricing_cache=True
    )
    assert_pair_equal(baseline, accelerated)
    try:
        assert_frozen_source({}, {}, {})
    except ValueError:
        pass
    else:
        raise AssertionError("source mismatch must fail closed")
    assert frozen_cell(16, 4)["status"] == "INTEGER_OPTIMUM_CERTIFIED"
    print("NYC branch-price cache reconstruction self-test: PASS")


def parser() -> argparse.ArgumentParser:
    p = scale.parser()
    p.description = __doc__
    p.set_defaults(
        output_dir=None,
        scan_start="2023-01-03T17:00:00",
        scan_end="2023-01-03T21:00:00",
        scan_window_hours=1.0,
        min_core_rows=10,
        max_core_rows=40,
        max_scan_rows=5000,
        max_candidate_rows=2500,
        overlap_epsilon_seconds=1.0,
        solver_time_limit=9000.0,
    )
    p.add_argument("--target-core", type=int)
    p.add_argument("--capacity", type=int)
    p.add_argument("--first", choices=("baseline", "accelerated"), default="baseline")
    p.add_argument("--aggregate-input-dir", type=Path)
    return p


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output_dir is None:
        raise ValueError("--output-dir is required")
    if args.aggregate_input_dir is not None:
        summary = aggregate_directory(args.aggregate_input_dir, args.output_dir)
        print(render_summary(summary))
        return 0
    if args.target_core is None or args.capacity is None:
        raise ValueError("live mode requires --target-core and --capacity")
    if args.solver_time_limit <= 0:
        raise ValueError("--solver-time-limit must be positive")
    args.bp_max_nodes = int(args.bp_max_nodes)
    args.bp_max_pricing_cases = int(args.bp_max_pricing_cases)
    report = run_live(args)
    write_cell_outputs(args.output_dir, report)
    print(render_cell(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
