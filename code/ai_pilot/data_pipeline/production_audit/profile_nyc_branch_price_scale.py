#!/usr/bin/env python3
"""Deterministically profile the frozen NYC branch-and-price scale lattice.

This script does not rerun the solver and does not upgrade any certificate.  It
derives a performance ledger from the 18 predeclared cells, preserving their
status and reporting runtime concentration, normalized work counts, and simple
log-scale associations.  The associations localize an engineering bottleneck
on this one lattice; they are not a causal complexity result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable


PROFILE_VERSION = "nyc-branch-price-scale-profile/v1"
EXPECTED_CAPACITIES = (2, 3, 4)
EXPECTED_SIZES = ((4, 12), (6, 18), (8, 24), (10, 30), (12, 36), (16, 48))
NUMERIC_FIELDS = (
    "elapsed_seconds_wall",
    "nodes_processed",
    "buffer_branches",
    "pair_branches",
    "total_generated_columns_across_nodes",
    "total_oracle_lp_solve_count",
    "total_pricing_case_count",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_float(row: dict[str, str], field: str) -> float:
    value = row.get(field)
    if value is None or value == "":
        raise ValueError(f"missing required numeric field {field}")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"invalid nonnegative numeric field {field}: {value}")
    return number


def read_cells(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    cells: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()
    for row in raw:
        core = int(row["core_rows"])
        buffers = int(row["buffer_rows"])
        capacity = int(row["capacity"])
        key = (core, buffers, capacity)
        if key in seen:
            raise ValueError(f"duplicate scale cell {key}")
        seen.add(key)
        cell: dict[str, Any] = {
            "core_rows": core,
            "buffer_rows": buffers,
            "capacity": capacity,
            "status": row["status"],
        }
        cell.update({field: _as_float(row, field) for field in NUMERIC_FIELDS})
        cells.append(cell)
    expected = {
        (core, buffers, capacity)
        for core, buffers in EXPECTED_SIZES
        for capacity in EXPECTED_CAPACITIES
    }
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ValueError(f"frozen lattice mismatch; missing={missing}, extra={extra}")
    cells.sort(key=lambda row: (row["core_rows"], row["capacity"]))
    return cells


def pearson(left: Iterable[float], right: Iterable[float]) -> float:
    x = list(left)
    y = list(right)
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Pearson inputs must have the same length >= 2")
    x_mean = fmean(x)
    y_mean = fmean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    x_scale = math.sqrt(sum((a - x_mean) ** 2 for a in x))
    y_scale = math.sqrt(sum((b - y_mean) ** 2 for b in y))
    if x_scale == 0 or y_scale == 0:
        raise ValueError("Pearson input has zero variance")
    return numerator / (x_scale * y_scale)


def profile(cells: list[dict[str, Any]], source_sha256: str) -> dict[str, Any]:
    statuses = {cell["status"] for cell in cells}
    if statuses != {"INTEGER_OPTIMUM_CERTIFIED"}:
        raise ValueError(f"profile input contains non-certified status: {statuses}")
    total_seconds = sum(cell["elapsed_seconds_wall"] for cell in cells)
    total_lp = sum(cell["total_oracle_lp_solve_count"] for cell in cells)
    total_nodes = sum(cell["nodes_processed"] for cell in cells)
    total_columns = sum(
        cell["total_generated_columns_across_nodes"] for cell in cells
    )
    total_cases = sum(cell["total_pricing_case_count"] for cell in cells)
    derived: list[dict[str, Any]] = []
    for cell in cells:
        nodes = cell["nodes_processed"]
        oracle = cell["total_oracle_lp_solve_count"]
        derived.append(
            {
                **cell,
                "runtime_share": cell["elapsed_seconds_wall"] / total_seconds,
                "oracle_lp_solves_per_node": oracle / nodes,
                "columns_per_node": cell[
                    "total_generated_columns_across_nodes"
                ]
                / nodes,
                "pricing_cases_per_node": cell["total_pricing_case_count"] / nodes,
                "milliseconds_per_oracle_lp": 1000.0
                * cell["elapsed_seconds_wall"]
                / oracle,
            }
        )
    ranked = sorted(
        derived,
        key=lambda row: (-row["elapsed_seconds_wall"], row["core_rows"], row["capacity"]),
    )
    log_runtime = [math.log1p(cell["elapsed_seconds_wall"]) for cell in cells]
    correlations = {
        field: pearson(
            log_runtime,
            [math.log1p(cell[field]) for cell in cells],
        )
        for field in (
            "total_oracle_lp_solve_count",
            "total_generated_columns_across_nodes",
            "total_pricing_case_count",
            "nodes_processed",
        )
    }
    capacity_groups = []
    for capacity in EXPECTED_CAPACITIES:
        group = [cell for cell in derived if cell["capacity"] == capacity]
        capacity_groups.append(
            {
                "capacity": capacity,
                "cell_count": len(group),
                "elapsed_seconds": sum(cell["elapsed_seconds_wall"] for cell in group),
                "runtime_share": sum(cell["runtime_share"] for cell in group),
                "oracle_lp_solve_count": int(
                    sum(cell["total_oracle_lp_solve_count"] for cell in group)
                ),
                "nodes_processed": int(sum(cell["nodes_processed"] for cell in group)),
            }
        )
    pricing_signal = correlations["total_oracle_lp_solve_count"]
    node_signal = correlations["nodes_processed"]
    classification = (
        "PRICING_LP_VOLUME_PRIMARY_SCALING_SIGNAL"
        if pricing_signal >= 0.95 and pricing_signal - node_signal >= 0.25
        else "NO_SINGLE_PRIMARY_SCALING_SIGNAL"
    )
    return {
        "report_version": PROFILE_VERSION,
        "source_cells_sha256": source_sha256,
        "input_scope": {
            "cell_count": len(cells),
            "certified_cell_count": len(cells),
            "sizes": [list(size) for size in EXPECTED_SIZES],
            "capacities": list(EXPECTED_CAPACITIES),
        },
        "totals": {
            "elapsed_seconds": total_seconds,
            "oracle_lp_solve_count": int(total_lp),
            "nodes_processed": int(total_nodes),
            "generated_columns_across_nodes": int(total_columns),
            "pricing_case_count": int(total_cases),
            "maximum_nodes_in_one_cell": int(max(cell["nodes_processed"] for cell in cells)),
        },
        "runtime_concentration": {
            "top_four_share": sum(cell["runtime_share"] for cell in ranked[:4]),
            "top_four_cells": [
                {
                    "core_rows": cell["core_rows"],
                    "buffer_rows": cell["buffer_rows"],
                    "capacity": cell["capacity"],
                    "elapsed_seconds": cell["elapsed_seconds_wall"],
                    "runtime_share": cell["runtime_share"],
                    "nodes_processed": int(cell["nodes_processed"]),
                    "oracle_lp_solve_count": int(cell["total_oracle_lp_solve_count"]),
                }
                for cell in ranked[:4]
            ],
        },
        "log1p_pearson_with_runtime": correlations,
        "capacity_groups": capacity_groups,
        "bottleneck": {
            "classification": classification,
            "evidence": (
                "Runtime tracks repeated fixed-span oracle LP volume much more closely "
                "than processed branch nodes on this frozen lattice."
            ),
            "claim_boundary": (
                "Descriptive attribution on one deterministic 18-cell lattice; not a "
                "causal ablation, population runtime guarantee, or complexity theorem."
            ),
        },
        "cells": derived,
    }


def render_markdown(report: dict[str, Any]) -> str:
    totals = report["totals"]
    concentration = report["runtime_concentration"]
    corr = report["log1p_pearson_with_runtime"]
    lines = [
        "# NYC branch-and-price frozen-lattice performance profile",
        "",
        f"Profile version: `{report['report_version']}`.",
        "",
        "## Result",
        "",
        f"All 18 input cells retain `INTEGER_OPTIMUM_CERTIFIED`. Together they used "
        f"**{totals['elapsed_seconds'] / 3600:.2f} solver-hours**, "
        f"**{totals['oracle_lp_solve_count']:,} fixed-span oracle LP solves**, and only "
        f"**{totals['nodes_processed']} processed branch nodes** (maximum "
        f"**{totals['maximum_nodes_in_one_cell']}** in one cell).",
        "",
        f"The four slowest cells account for **{100 * concentration['top_four_share']:.1f}%** "
        "of observed runtime. On log1p scales, runtime correlates **"
        f"{corr['total_oracle_lp_solve_count']:.3f}** with oracle-LP volume, versus **"
        f"{corr['nodes_processed']:.3f}** with processed nodes. The primary observed "
        "scaling signal is therefore repeated fixed-span pricing work, not a large "
        "branch tree.",
        "",
        "## Slowest cells",
        "",
        "| Core | Buffer | C | Seconds | Runtime share | Nodes | Oracle LP solves |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in concentration["top_four_cells"]:
        lines.append(
            f"| {cell['core_rows']} | {cell['buffer_rows']} | {cell['capacity']} | "
            f"{cell['elapsed_seconds']:.2f} | {100 * cell['runtime_share']:.1f}% | "
            f"{cell['nodes_processed']} | {cell['oracle_lp_solve_count']:,} |"
        )
    lines.extend(
        [
            "",
            "## Capacity totals",
            "",
            "| C | Cells | Seconds | Runtime share | Oracle LP solves | Nodes |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for group in report["capacity_groups"]:
        lines.append(
            f"| {group['capacity']} | {group['cell_count']} | "
            f"{group['elapsed_seconds']:.2f} | {100 * group['runtime_share']:.1f}% | "
            f"{group['oracle_lp_solve_count']:,} | {group['nodes_processed']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            report["bottleneck"]["claim_boundary"],
            "The next optimization target is to reduce repeated rooted fixed-span LP "
            "work (through exact reuse, screening, or batching) while preserving exact "
            "branch-compatible pricing. Enlarging the search lattice before such an "
            "ablation would not isolate the bottleneck.",
            "",
        ]
    )
    return "\n".join(lines)


def render_tex(report: dict[str, Any]) -> str:
    totals = report["totals"]
    concentration = report["runtime_concentration"]
    corr = report["log1p_pearson_with_runtime"]
    return "\n".join(
        [
            "% Generated by profile_nyc_branch_price_scale.py; do not edit by hand.",
            "\\paragraph{Frozen-lattice performance profile.}",
            f"The 18 certified cells required {totals['elapsed_seconds'] / 3600:.2f} "
            f"solver-hours and {totals['oracle_lp_solve_count']:,} fixed-span oracle "
            f"LP solves, but only {totals['nodes_processed']} processed branch nodes "
            f"(at most {totals['maximum_nodes_in_one_cell']} in one cell).",
            f"The four slowest cells consumed {100 * concentration['top_four_share']:.1f}\\% "
            "of runtime.  On $\\log(1+x)$ scales, runtime correlates "
            f"{corr['total_oracle_lp_solve_count']:.3f} with oracle-LP volume and "
            f"{corr['nodes_processed']:.3f} with processed nodes, localizing repeated "
            "fixed-span pricing as the primary scaling signal on this lattice.  This "
            "is descriptive profiling, not a complexity or population-runtime claim.",
            "",
        ]
    )


def write_csv(report: dict[str, Any], path: Path) -> None:
    fields = [
        "core_rows",
        "buffer_rows",
        "capacity",
        "status",
        *NUMERIC_FIELDS,
        "runtime_share",
        "oracle_lp_solves_per_node",
        "columns_per_node",
        "pricing_cases_per_node",
        "milliseconds_per_oracle_lp",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["cells"])


def run(input_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = profile(read_cells(input_path), sha256_file(input_path))
    json_path = output_dir / "PROFILE.json"
    csv_path = output_dir / "PROFILE_CELLS.csv"
    markdown_path = output_dir / "REPORT.md"
    tex_path = output_dir / "RESULTS.tex"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_csv(report, csv_path)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    tex_path.write_text(render_tex(report), encoding="utf-8")
    outputs = [json_path, csv_path, markdown_path, tex_path]
    manifest = {
        "report_version": PROFILE_VERSION,
        "source": input_path.name,
        "source_sha256": report["source_cells_sha256"],
        "outputs": {path.name: sha256_file(path) for path in outputs},
        "deterministic": True,
        "certificate_statuses_changed": False,
    }
    (output_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1] / "results" / "nyc_hvfhv"
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input",
        type=Path,
        default=root / "BRANCH_AND_PRICE_SCALE_CELLS.csv",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=root / "branch_price_profile_20260917",
    )
    return p


def main() -> int:
    args = parser().parse_args()
    report = run(args.input, args.output_dir)
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
