#!/usr/bin/env python3
"""Paired audit of objective-independent branch-price pricing caches.

Every baseline/accelerated pair uses identical constructed rows and limits.
The switch changes only exact geometry prechecking and reuse of span matrices
and boxes proved infeasible by that precheck.  Numerical LP infeasibility is
never memoized.  Runtime is descriptive; certificate equality and LP-call
counts are the deterministic outcomes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "code" / "ai_pilot" / "data_pipeline" / "production_audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))

import numpy  # noqa: E402
import ordered_run_branch_and_price as solver  # noqa: E402
import ordered_run_column_generation as column_generation  # noqa: E402
import ordered_run_fixed_time_master as exact  # noqa: E402
import scipy  # noqa: E402


PROTOCOL_PATH = Path(__file__).with_name("BRANCH_PRICE_CACHE_PROTOCOL.json")
RESULT_VERSION = "ordered-branch-price-cache-paired/v1"
COMPARE_FIELDS = (
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
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_protocol(path: Path = PROTOCOL_PATH) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("protocol_version") != RESULT_VERSION:
        raise ValueError("protocol version mismatch")
    cases = protocol.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("protocol requires a nonempty case list")
    labels = [case.get("label") for case in cases]
    if any(not isinstance(label, str) or not label for label in labels):
        raise ValueError("every case requires a label")
    if len(labels) != len(set(labels)):
        raise ValueError("case labels must be unique")
    if not isinstance(protocol.get("repetitions"), int) or protocol["repetitions"] < 2:
        raise ValueError("protocol requires at least two repetitions")
    return protocol


def regular_turnover(core_rows: int) -> list[exact.FixedTimeRow]:
    if core_rows < 2:
        raise ValueError("regular turnover requires at least two cores")
    rows: list[exact.FixedTimeRow] = []
    for role, offset in (
        ("core", 0),
        ("buffer", 1),
        ("buffer", 4),
        ("buffer", 2),
    ):
        for index in range(core_rows):
            start = 3 * index + offset
            rows.append(exact.FixedTimeRow(len(rows), role, start, start + 4))
    return rows


def case_rows(case: dict[str, Any]) -> list[exact.FixedTimeRow]:
    kind = case.get("kind")
    if kind == "integrality_gap":
        return column_generation.integrality_gap_counterexample()
    if kind == "regular_turnover":
        return regular_turnover(int(case["core_rows"]))
    raise ValueError(f"unknown case kind: {kind}")


def row_hash(rows: list[exact.FixedTimeRow]) -> str:
    payload = json.dumps(
        [row.__dict__ for row in rows], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def safe_result(result: dict[str, Any]) -> dict[str, Any]:
    fields = (
        *COMPARE_FIELDS,
        "total_generated_columns_across_nodes",
        "total_oracle_lp_solve_count",
        "total_pricing_case_count",
        "maximum_pricing_cases_for_one_root",
        "pricing_infeasible_box_cache_hits",
        "pricing_exact_box_prunes",
        "pricing_span_matrix_cache_hits",
        "elapsed_seconds",
    )
    return {field: result.get(field) for field in fields}


def certificate_view(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result.get(field) for field in COMPARE_FIELDS}


def run_variant(
    rows: list[exact.FixedTimeRow],
    capacity: int,
    protocol: dict[str, Any],
    *,
    enabled: bool,
) -> dict[str, Any]:
    result = solver.branch_and_price_max_support(
        rows,
        capacity,
        max_nodes=int(protocol["max_nodes"]),
        time_limit_seconds=float(protocol["time_limit_seconds"]),
        use_pricing_cache=enabled,
    )
    if result.get("status") != "INTEGER_OPTIMUM_CERTIFIED":
        raise RuntimeError(f"paired cell did not close exactly: {result}")
    return safe_result(result)


def assert_pair_equal(
    baseline: dict[str, Any], accelerated: dict[str, Any]
) -> None:
    left = certificate_view(baseline)
    right = certificate_view(accelerated)
    if left != right:
        raise AssertionError(
            "cache switch changed certificate path: "
            + json.dumps({"baseline": left, "accelerated": right}, sort_keys=True)
        )


def summarize(records: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    cells = []
    for case in protocol["cases"]:
        case_records = [row for row in records if row["label"] == case["label"]]
        if len(case_records) != int(protocol["repetitions"]):
            raise ValueError(f"incomplete repetitions for {case['label']}")
        for record in case_records:
            assert_pair_equal(record["baseline"], record["accelerated"])
        baseline_calls = {
            int(record["baseline"]["total_oracle_lp_solve_count"])
            for record in case_records
        }
        accelerated_calls = {
            int(record["accelerated"]["total_oracle_lp_solve_count"])
            for record in case_records
        }
        if len(baseline_calls) != 1 or len(accelerated_calls) != 1:
            raise AssertionError("LP-call counts changed across identical repetitions")
        baseline_lp = baseline_calls.pop()
        accelerated_lp = accelerated_calls.pop()
        baseline_seconds = [
            float(record["baseline"]["elapsed_seconds"])
            for record in case_records
        ]
        accelerated_seconds = [
            float(record["accelerated"]["elapsed_seconds"])
            for record in case_records
        ]
        cells.append(
            {
                "label": case["label"],
                "kind": case["kind"],
                "core_rows": sum(row["role"] == "core" for row in case_records[0]["rows"]),
                "buffer_rows": sum(row["role"] == "buffer" for row in case_records[0]["rows"]),
                "capacity": int(case["capacity"]),
                "repetitions": len(case_records),
                "certificate_equal": True,
                "integer_optimum": case_records[0]["baseline"][
                    "integer_maximum_selected_buffers"
                ],
                "nodes_processed": case_records[0]["baseline"]["nodes_processed"],
                "baseline_oracle_lp_calls": baseline_lp,
                "accelerated_oracle_lp_calls": accelerated_lp,
                "oracle_lp_call_reduction": baseline_lp - accelerated_lp,
                "oracle_lp_call_reduction_rate": (
                    (baseline_lp - accelerated_lp) / baseline_lp
                    if baseline_lp
                    else 0.0
                ),
                "infeasible_box_cache_hits": case_records[0]["accelerated"][
                    "pricing_infeasible_box_cache_hits"
                ],
                "exact_box_prunes": case_records[0]["accelerated"][
                    "pricing_exact_box_prunes"
                ],
                "span_matrix_cache_hits": case_records[0]["accelerated"][
                    "pricing_span_matrix_cache_hits"
                ],
                "baseline_median_seconds": statistics.median(baseline_seconds),
                "accelerated_median_seconds": statistics.median(accelerated_seconds),
                "median_runtime_ratio": (
                    statistics.median(accelerated_seconds)
                    / statistics.median(baseline_seconds)
                ),
            }
        )
    total_baseline_lp = sum(cell["baseline_oracle_lp_calls"] for cell in cells)
    total_accelerated_lp = sum(cell["accelerated_oracle_lp_calls"] for cell in cells)
    paired_runs = [
        (record["baseline"], record["accelerated"])
        for record in records
    ]
    return {
        "report_version": RESULT_VERSION,
        "cell_count": len(cells),
        "paired_run_count": len(records),
        "all_certificates_equal": all(cell["certificate_equal"] for cell in cells),
        "all_runs_integer_optimum_certified": all(
            left["status"] == right["status"] == "INTEGER_OPTIMUM_CERTIFIED"
            for left, right in paired_runs
        ),
        "total_baseline_oracle_lp_calls": total_baseline_lp,
        "total_accelerated_oracle_lp_calls": total_accelerated_lp,
        "total_oracle_lp_call_reduction": total_baseline_lp - total_accelerated_lp,
        "total_oracle_lp_call_reduction_rate": (
            (total_baseline_lp - total_accelerated_lp) / total_baseline_lp
        ),
        "runtime_win_pairs": sum(
            float(right["elapsed_seconds"]) < float(left["elapsed_seconds"])
            for left, right in paired_runs
        ),
        "cells": cells,
        "claim_boundary": protocol["claim_boundary"],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Ordered-event branch-and-price pricing-cache audit",
        "",
        "Every pair uses identical rows, limits, branching rules, and objectives; "
        "only the objective-independent exact geometry cache is switched.",
        "",
        "| Case | Rows | C | Optimum | Nodes | Baseline LP | Cached LP | Reduction | Baseline s | Cached s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in summary["cells"]:
        lines.append(
            f"| `{cell['label']}` | {cell['core_rows']}+{cell['buffer_rows']} | "
            f"{cell['capacity']} | {float(cell['integer_optimum']):.0f} | "
            f"{int(cell['nodes_processed'])} | {cell['baseline_oracle_lp_calls']:,} | "
            f"{cell['accelerated_oracle_lp_calls']:,} | "
            f"{100 * cell['oracle_lp_call_reduction_rate']:.1f}% | "
            f"{cell['baseline_median_seconds']:.3f} | "
            f"{cell['accelerated_median_seconds']:.3f} |"
        )
    lines.extend(
        [
            "",
            f"All **{summary['paired_run_count']}** paired runs return identical "
            "integer certificates and branch paths. Across one copy of each cell, "
            f"actual fixed-span LP calls fall from **{summary['total_baseline_oracle_lp_calls']:,}** "
            f"to **{summary['total_accelerated_oracle_lp_calls']:,}** "
            f"(**{100 * summary['total_oracle_lp_call_reduction_rate']:.1f}%**). "
            f"The cached variant is faster in **{summary['runtime_win_pairs']}/"
            f"{summary['paired_run_count']}** wall-clock pairs.",
            "",
            "The LP-call reduction is deterministic. Wall-clock measurements are "
            "descriptive and depend on the runner. No numerical LP status is cached; "
            "only exact integer-box infeasibility is memoized.",
            "",
            f"Claim boundary: {summary['claim_boundary']}.",
            "",
        ]
    )
    return "\n".join(lines)


def render_tex(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "% Generated by branch_price_cache_audit.py; do not edit by hand.",
            "\\paragraph{Paired pricing-cache audit.}",
            f"Across {summary['cell_count']} constructed exact cells and "
            f"{summary['paired_run_count']} paired runs, enabling only the "
            "objective-independent geometry cache preserves every integer certificate "
            "and branch path.  Fixed-span LP calls fall from "
            f"{summary['total_baseline_oracle_lp_calls']:,} to "
            f"{summary['total_accelerated_oracle_lp_calls']:,} "
            f"({100 * summary['total_oracle_lp_call_reduction_rate']:.1f}\\%). "
            "The result is a constructed paired audit, not a rerun of the frozen NYC "
            "cohort or a city-scale runtime claim.",
            "",
        ]
    )


def write_csv(summary: dict[str, Any], path: Path) -> None:
    fields = list(summary["cells"][0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary["cells"])


def warm_up() -> None:
    rows = [
        exact.FixedTimeRow(0, "core", 0, 2),
        exact.FixedTimeRow(1, "buffer", 0, 2),
    ]
    for enabled in (False, True):
        result = solver.branch_and_price_max_support(
            rows, 2, time_limit_seconds=10.0, use_pricing_cache=enabled
        )
        if result["status"] != "INTEGER_OPTIMUM_CERTIFIED":
            raise RuntimeError("warm-up did not close")


def run(protocol: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    warm_up()
    records = []
    for case_index, case in enumerate(protocol["cases"]):
        rows = case_rows(case)
        serialized_rows = [row.__dict__ for row in rows]
        for repetition in range(int(protocol["repetitions"])):
            order = (False, True) if (case_index + repetition) % 2 == 0 else (True, False)
            variants: dict[str, dict[str, Any]] = {}
            for enabled in order:
                label = "accelerated" if enabled else "baseline"
                variants[label] = run_variant(
                    rows,
                    int(case["capacity"]),
                    protocol,
                    enabled=enabled,
                )
            assert_pair_equal(variants["baseline"], variants["accelerated"])
            records.append(
                {
                    "label": case["label"],
                    "repetition": repetition,
                    "variant_order": ["accelerated" if value else "baseline" for value in order],
                    "input_sha256": row_hash(rows),
                    "rows": serialized_rows,
                    **variants,
                }
            )
    summary = summarize(records, protocol)
    environment = {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    }
    runs_path = output_dir / "RUNS.json"
    summary_path = output_dir / "SUMMARY.json"
    csv_path = output_dir / "PAIRED_CELLS.csv"
    report_path = output_dir / "REPORT.md"
    tex_path = output_dir / "RESULTS.tex"
    runs_path.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary_path.write_text(
        json.dumps({**summary, "environment": environment}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    write_csv(summary, csv_path)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    tex_path.write_text(render_tex(summary), encoding="utf-8")
    outputs = [runs_path, summary_path, csv_path, report_path, tex_path]
    manifest = {
        "report_version": RESULT_VERSION,
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "solver_sha256": sha256_file(Path(solver.__file__)),
        "outputs": {path.name: sha256_file(path) for path in outputs},
        "deterministic_fields": "certificates, branch paths, LP-call counts, cache counts",
        "nondeterministic_fields": "elapsed_seconds and derived runtime ratios",
    }
    (output_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def self_test() -> None:
    protocol = load_protocol()
    rows = regular_turnover(2)
    self_hash = row_hash(rows)
    if self_hash != row_hash(regular_turnover(2)):
        raise AssertionError("row generator is not deterministic")
    baseline = run_variant(rows, 2, protocol, enabled=False)
    accelerated = run_variant(rows, 2, protocol, enabled=True)
    assert_pair_equal(baseline, accelerated)
    if accelerated["total_oracle_lp_solve_count"] > baseline[
        "total_oracle_lp_solve_count"
    ]:
        raise AssertionError("cache increased LP calls")
    print("branch-price cache audit self-test: PASS")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--self-test", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    protocol = load_protocol(args.protocol)
    if args.self_test:
        self_test()
        return 0
    if args.output_dir is None:
        raise ValueError("--output-dir is required unless --self-test is used")
    summary = run(protocol, args.output_dir)
    print(render_markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
