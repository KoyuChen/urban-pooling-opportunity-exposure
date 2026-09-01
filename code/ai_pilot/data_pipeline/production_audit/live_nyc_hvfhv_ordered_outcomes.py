#!/usr/bin/env python3
"""Run-invariant outcome bounds for the NYC ordered latent-run model.

This stage deliberately starts with the computationally certified 15-minute
outer-time model. For each C in {2,3,4}, it first certifies the maximum number
of selected buffer rows. Conditional on that maximum-support cardinality, it
bounds the mean public trip miles and trip duration of the selected buffer rows.

Because cardinality is fixed inside each outcome optimization, the average is a
linear objective up to a known constant. The estimands are invariant to the
canonical root label of each run.

These are public-data feasible-world bounds, not recovered co-rider outcomes.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix, vstack

import live_nyc_hvfhv_ordered_run_smoke as base
import nyc_ordered_run_symmetry as symmetry

TIME_MODEL = "rounded_15m_outer"


def canonical_program(rows, capacity):
    return symmetry.canonicalize_program(base.build_program(rows, capacity))


def append_equality(program: base.Program, coeff: np.ndarray, target: float) -> base.Program:
    row = csr_matrix(coeff.reshape(1, -1))
    program.matrix = vstack([program.matrix, row], format="csr")
    program.lower = np.concatenate([program.lower, np.array([target], dtype=float)])
    program.upper = np.concatenate([program.upper, np.array([target], dtype=float)])
    return program


def buffer_attribute_objective(program: base.Program, attribute: str, scale: float = 1.0) -> tuple[np.ndarray, list[int]]:
    coeff = np.zeros(program.matrix.shape[1], dtype=float)
    core_count = len(program.roots)
    by_index = {row.index: row for row in program.rows}
    missing: set[int] = set()
    for (member, _root), col in program.x_col.items():
        row = by_index[member]
        if row.role != "buffer":
            continue
        value = getattr(row, attribute)
        if value is None:
            missing.add(member)
            continue
        coeff[col] = float(value) / scale / core_count
    return coeff, sorted(missing)


def solve_capacity(rows, capacity: int, time_limit: float) -> dict[str, Any]:
    program = canonical_program(rows, capacity)
    count_coeff = base.objective(program, "selected_buffer_rows_per_core")
    count_upper = base.solve(program, count_coeff, True, time_limit)
    if count_upper["status"] != base.CERTIFIED or count_upper["value"] is None:
        return {
            "capacity": capacity,
            "status": "UNRESOLVED_MAX_BUFFER_CARDINALITY",
            "max_buffer_rows_per_core": None,
            "outcomes": [],
            "count_upper_status": count_upper["status"],
            "count_upper_mip_gap": count_upper["mip_gap"],
        }

    max_per_core = float(count_upper["value"])
    if max_per_core <= 0:
        return {
            "capacity": capacity,
            "status": "DEGENERATE_ZERO_BUFFER_MAX",
            "max_buffer_rows_per_core": max_per_core,
            "outcomes": [],
            "count_upper_status": count_upper["status"],
            "count_upper_mip_gap": count_upper["mip_gap"],
        }

    core_count = len(program.roots)
    max_count = max_per_core * core_count
    output: list[dict[str, Any]] = []
    for query, attribute, scale, unit in (
        ("mean_selected_buffer_miles_at_max_support", "miles", 1.0, "miles"),
        ("mean_selected_buffer_trip_minutes_at_max_support", "seconds", 60.0, "minutes"),
    ):
        p = canonical_program(rows, capacity)
        count = base.objective(p, "selected_buffer_rows_per_core")
        append_equality(p, count, max_per_core)
        attr_coeff, missing = buffer_attribute_objective(p, attribute, scale)
        if missing:
            output.append(
                {
                    "query": query,
                    "unit": unit,
                    "lower": None,
                    "upper": None,
                    "width": None,
                    "status": "UNRESOLVED_MISSING_PUBLIC_VALUES",
                    "missing_buffer_rows": len(missing),
                }
            )
            continue
        lo = base.solve(p, attr_coeff, False, time_limit)
        hi = base.solve(p, attr_coeff, True, time_limit)
        certified = lo["status"] == hi["status"] == base.CERTIFIED
        if not certified:
            output.append(
                {
                    "query": query,
                    "unit": unit,
                    "lower": None,
                    "upper": None,
                    "width": None,
                    "status": "UNRESOLVED_ENDPOINT_PAIR",
                    "lower_status": lo["status"],
                    "upper_status": hi["status"],
                    "lower_mip_gap": lo["mip_gap"],
                    "upper_mip_gap": hi["mip_gap"],
                }
            )
            continue
        # attr objective is total attribute mass per core. Divide by the fixed
        # selected-buffer rows/core to obtain the mean attribute per selected row.
        lower_mean = float(lo["value"]) / max_per_core
        upper_mean = float(hi["value"]) / max_per_core
        output.append(
            {
                "query": query,
                "unit": unit,
                "lower": lower_mean,
                "upper": upper_mean,
                "width": upper_mean - lower_mean,
                "status": "CERTIFIED_OPTIMAL_PAIR",
                "lower_mip_gap": lo["mip_gap"],
                "upper_mip_gap": hi["mip_gap"],
                "fixed_buffer_rows": max_count,
            }
        )

    return {
        "capacity": capacity,
        "status": "CERTIFIED_MAX_BUFFER_CARDINALITY",
        "max_buffer_rows_per_core": max_per_core,
        "outcomes": output,
        "count_upper_status": count_upper["status"],
        "count_upper_mip_gap": count_upper["mip_gap"],
    }


def run(args) -> dict[str, Any]:
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError("dataset metadata/schema changed during extraction")
    determinate_after, _, _ = base.count(selected["where"]["determinate"])
    indeterminate_after, _, _ = base.count(selected["where"]["indeterminate"])
    if determinate_after != selected["determinate_count"] or indeterminate_after != selected["indeterminate_count"]:
        raise base.LiveDataError("candidate server counts changed during extraction")

    trips, audit_rows = base.parse_trips(
        selected["candidate_rows"],
        selected["provider"],
        selected["core_start"],
        selected["core_end"],
    )
    ordered = base.ordered_subcohort(base.model_rows(trips, TIME_MODEL), args.ordered_core)
    cells = [solve_capacity(ordered, capacity, args.solver_time_limit) for capacity in base.CAPACITIES]

    return {
        "report_version": "nyc-hvfhv-ordered-outcomes/v1-max-support",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "core_start": selected["core_start"].isoformat(),
            "core_end": selected["core_end"].isoformat(),
            "source_core_rows": audit_rows["core_rows"],
            "source_candidate_rows": audit_rows["rows"],
            "ordered_core_rows": args.ordered_core,
            "ordered_candidate_rows": len(ordered),
            "time_model": TIME_MODEL,
        },
        "cells": cells,
        "estimand": "mean public attribute among selected buffer rows, conditional on maximum feasible selected-buffer cardinality for each declared C",
        "claim_boundary": {
            "supported": "root-invariant outcome composition bounds in maximum-support latent worlds under the declared coarse public-time model",
            "not_supported": "actual co-rider composition, realized vehicle run, true capacity, or production matching logic",
        },
    }


def render(report) -> str:
    lines = [
        "# NYC HVFHV ordered-run outcome bounds",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Time model: `{report['cohort']['time_model']}`  ",
        f"Ordered core: **{report['cohort']['ordered_core_rows']}**; candidate rows: **{report['cohort']['ordered_candidate_rows']}**.",
        "",
        "Each outcome interval conditions on the maximum feasible number of selected buffer rows for that C, then varies only their public composition.",
        "",
        "| C | Max buffers/core | Outcome | Lower | Upper | Width | Status |",
        "|---:|---:|---|---:|---:|---:|---|",
    ]
    for cell in report["cells"]:
        maxbuf = "—" if cell["max_buffer_rows_per_core"] is None else f"{cell['max_buffer_rows_per_core']:.4f}"
        if not cell["outcomes"]:
            lines.append(f"| {cell['capacity']} | {maxbuf} | — | — | — | — | `{cell['status']}` |")
            continue
        for outcome in cell["outcomes"]:
            lo = "—" if outcome["lower"] is None else f"{outcome['lower']:.4f}"
            hi = "—" if outcome["upper"] is None else f"{outcome['upper']:.4f}"
            width = "—" if outcome["width"] is None else f"{outcome['width']:.4f}"
            lines.append(
                f"| {cell['capacity']} | {maxbuf} | {outcome['query']} | {lo} | {hi} | {width} | `{outcome['status']}` |"
            )
    lines.extend(
        [
            "",
            "These are conditional feasible-world bounds. They do not recover actual NYC co-riders or realized pooling composition.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report, path: Path) -> None:
    rows = []
    for cell in report["cells"]:
        for outcome in cell["outcomes"]:
            rows.append(
                {
                    "capacity": cell["capacity"],
                    "max_buffer_rows_per_core": cell["max_buffer_rows_per_core"],
                    **outcome,
                }
            )
    fields = sorted({key for row in rows for key in row}) if rows else ["capacity"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    rows = base.synthetic_chain()
    # On the chain, C=2 can select its one buffer; miles are therefore point identified.
    result = solve_capacity(rows, 2, 10.0)
    assert result["status"] == "CERTIFIED_MAX_BUFFER_CARDINALITY"
    assert abs(result["max_buffer_rows_per_core"] - 0.5) <= 1e-8
    miles = next(x for x in result["outcomes"] if "miles" in x["query"])
    assert miles["status"] == "CERTIFIED_OPTIMAL_PAIR"
    assert abs(miles["lower"] - 3.0) <= 1e-8
    assert abs(miles["upper"] - 3.0) <= 1e-8
    print("NYC ordered-run outcome self-test: PASS")


def parser() -> argparse.ArgumentParser:
    p = base.parser()
    return p


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    base.validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    write_csv(report, args.output_dir / "ordered_outcomes.csv")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
