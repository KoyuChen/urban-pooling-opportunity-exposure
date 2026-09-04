#!/usr/bin/env python3
"""Run one predeclared NYC exact-time ordered-run panel cell.

For each C in {2,3,4}, this script computes the normalized run-count frontier
on a deterministic ordered core and its full count-reconciled candidate
universe. Optimal cells report exact endpoints; time-limited cells report only
valid primal/dual enclosures. Outputs are aggregate and contain no row or run
witnesses.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import LinearConstraint, milp

import live_nyc_hvfhv_ordered_run_smoke as base
import nyc_ordered_run_symmetry as symmetry

CAPACITIES = tuple(map(int, base.CAPACITIES))
TOL = 1e-7


def finite(value: Any) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def endpoint(program: base.Program, coeff: np.ndarray, maximize: bool, limit: float) -> dict[str, Any]:
    started = time.perf_counter()
    result = milp(
        c=-coeff if maximize else coeff,
        integrality=program.integrality,
        bounds=program.bounds,
        constraints=LinearConstraint(program.matrix, program.lower, program.upper),
        options={"time_limit": limit, "presolve": True},
    )
    elapsed = time.perf_counter() - started
    if int(result.status) == 2:
        raise base.LiveDataError("ordered-run master unexpectedly infeasible")

    incumbent = residual = None
    if result.x is not None:
        raw = np.asarray(result.x, dtype=float)
        binary = np.flatnonzero(program.integrality == 1)
        replay = raw.copy()
        replay[binary] = np.rint(replay[binary])
        values = np.asarray(program.matrix @ replay).reshape(-1)
        residual = max(
            float(np.max(np.abs(raw[binary] - replay[binary]))) if len(binary) else 0.0,
            float(np.max(np.maximum(program.lower - values, 0.0))),
            float(np.max(np.maximum(values - program.upper, 0.0))),
        )
        if residual <= TOL:
            incumbent = float(coeff @ replay)

    dual = finite(getattr(result, "mip_dual_bound", None))
    optimal = int(result.status) == 0 and incumbent is not None
    if optimal:
        lower = upper = incumbent
    elif maximize:
        lower, upper = incumbent, None if dual is None else -dual
    else:
        lower, upper = dual, incumbent

    return {
        "direction": "maximum" if maximize else "minimum",
        "status": "CERTIFIED_OPTIMAL" if optimal else "UNRESOLVED_LIMIT_OR_NUMERICAL",
        "solver_status": int(result.status),
        "solver_message": str(result.message),
        "incumbent_value": incumbent,
        "objective_lower_bound": lower,
        "objective_upper_bound": upper,
        "mip_gap": finite(getattr(result, "mip_gap", None)),
        "mip_node_count": (
            None if getattr(result, "mip_node_count", None) is None
            else int(result.mip_node_count)
        ),
        "replay_residual": residual,
        "elapsed_seconds": elapsed,
    }


def solve_cell(rows: Sequence[base.ModelTrip], time_model: str, capacity: int, limit: float) -> dict[str, Any]:
    program = symmetry.canonicalize_program(base.build_program(rows, capacity))
    coeff = base.objective(program, "run_count_per_core")
    low = endpoint(program, coeff, False, limit)
    high = endpoint(program, coeff, True, limit)
    n = len(program.roots)
    physical_low, physical_high = 1.0 / n, 1.0
    analytic = symmetry.peak_capacity_run_lower_bound(list(rows), capacity)

    min_lb = max(analytic, physical_low, low["objective_lower_bound"] or -math.inf)
    min_ub = min(physical_high, low["objective_upper_bound"] or physical_high)
    max_lb = max(physical_low, high["objective_lower_bound"] or physical_low)
    max_ub = min(physical_high, high["objective_upper_bound"] or physical_high)
    if min_lb > min_ub + 1e-6 or max_lb > max_ub + 1e-6:
        raise base.LiveDataError("invalid solver endpoint enclosure")

    exact = low["status"] == high["status"] == "CERTIFIED_OPTIMAL"
    lower = float(low["incumbent_value"]) if exact else None
    upper = float(high["incumbent_value"]) if exact else None
    if exact and lower > upper + TOL:
        raise base.LiveDataError("certified frontier is reversed")
    inner_low, inner_high = low["incumbent_value"], high["incumbent_value"]
    inner_width = (
        inner_high - inner_low
        if inner_low is not None and inner_high is not None and inner_low <= inner_high + TOL
        else None
    )
    return {
        "time_model": time_model,
        "capacity": capacity,
        "query": "run_count_per_core",
        "status": "CERTIFIED_OPTIMAL_PAIR" if exact else "RIGOROUS_OPEN_ENDPOINTS",
        "lower": lower,
        "upper": upper,
        "width": None if not exact else upper - lower,
        "minimum_endpoint_lower_bound": min_lb,
        "minimum_endpoint_upper_bound": min_ub,
        "maximum_endpoint_lower_bound": max_lb,
        "maximum_endpoint_upper_bound": max_ub,
        "solver_outer_frontier_lower": min_lb,
        "solver_outer_frontier_upper": max_ub,
        "solver_outer_width": max_ub - min_lb,
        "solver_inner_frontier_lower": inner_low,
        "solver_inner_frontier_upper": inner_high,
        "solver_inner_width": inner_width,
        "peak_core_occupancy": symmetry.peak_core_occupancy(list(rows)),
        "analytic_minimum_run_bound": analytic,
        "analytic_bound_sharp": bool(exact and abs(lower - analytic) <= TOL),
        "minimum_solve": low,
        "maximum_solve": high,
        "variables": int(program.matrix.shape[1]),
        "binary_variables": int(np.count_nonzero(program.integrality)),
        "constraints": int(program.matrix.shape[0]),
        "overlap_edges": int(program.overlap_edge_count),
        "elementary_segments": int(program.segment_count),
        "bridge_constraints": int(program.bridge_count),
    }


def audit(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    certified = bounded = 0
    for time_model in sorted({str(row["time_model"]) for row in cells}):
        ordered = sorted(
            (row for row in cells if row["time_model"] == time_model),
            key=lambda row: int(row["capacity"]),
        )
        for left, right in zip(ordered, ordered[1:]):
            bounded += 1
            if right["minimum_endpoint_lower_bound"] > left["minimum_endpoint_upper_bound"] + TOL:
                problems.append({"reason": "minimum_capacity_contradiction", "time_model": time_model})
            if right["maximum_endpoint_upper_bound"] + TOL < left["maximum_endpoint_lower_bound"]:
                problems.append({"reason": "maximum_capacity_contradiction", "time_model": time_model})
            if left["status"] == right["status"] == "CERTIFIED_OPTIMAL_PAIR":
                certified += 1
                if right["lower"] > left["lower"] + TOL:
                    problems.append({"reason": "certified_lower_increased", "time_model": time_model})
                if right["upper"] < left["upper"] - TOL:
                    problems.append({"reason": "certified_upper_decreased", "time_model": time_model})
    return {
        "status": "PASS" if not problems else "FAIL",
        "problem_count": len(problems),
        "problems": problems,
        "bounded_capacity_comparisons": bounded,
        "certified_capacity_comparisons": certified,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError("dataset metadata/schema changed during extraction")
    determinate, _, _ = base.count(selected["where"]["determinate"])
    indeterminate, _, _ = base.count(selected["where"]["indeterminate"])
    if (determinate, indeterminate) != (
        selected["determinate_count"], selected["indeterminate_count"]
    ):
        raise base.LiveDataError("candidate server counts changed during extraction")

    trips, row_audit = base.parse_trips(
        selected["candidate_rows"], selected["provider"],
        selected["core_start"], selected["core_end"],
    )
    cells: list[dict[str, Any]] = []
    sizes: dict[str, int] = {}
    for time_model in args.time_models:
        rows = base.ordered_subcohort(base.model_rows(trips, time_model), args.ordered_core)
        sizes[time_model] = len(rows)
        cells.extend(solve_cell(rows, time_model, c, args.solver_time_limit) for c in CAPACITIES)
    checked = audit(cells)
    if checked["status"] != "PASS":
        raise base.LiveDataError("capacity nesting audit failed: " + json.dumps(checked["problems"]))

    return {
        "report_version": "nyc-hvfhv-ordered-run-panel-window/v1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "window_label": args.window_label,
        "scan_start": args.scan_start,
        "scan_end": args.scan_end,
        "snapshot": after,
        "cohort": {
            "provider": selected["provider"],
            "source_core_start": selected["core_start"].isoformat(),
            "source_core_end": selected["core_end"].isoformat(),
            "source_core_rows": row_audit["core_rows"],
            "source_candidate_rows": row_audit["rows"],
            "ordered_core_rows": args.ordered_core,
            "ordered_candidate_rows": sizes,
            "selection": (
                "first qualifying provider-window under count-reconciled scan; "
                "first core rows by frozen source order; no outcome values used"
            ),
        },
        "time_models": list(args.time_models),
        "capacities": list(CAPACITIES),
        "cells": cells,
        "audit": checked,
        "redaction": {
            "raw_rows_emitted": False,
            "row_identifiers_emitted": False,
            "run_assignments_emitted": False,
            "partner_witnesses_emitted": False,
            "aggregate_only": True,
        },
        "claim_boundary": {
            "supported": "within-window endpoint certificates or rigorous open solver enclosures under the declared interval-run model",
            "not_supported": "actual runs, co-riders, partner recall, realized pool size or capacity, production logic, population prevalence, or causal effects",
        },
    }


def render(report: Mapping[str, Any]) -> str:
    cohort = report["cohort"]
    lines = [
        f"# NYC ordered-run panel window: {report['window_label']}", "",
        f"Selected core: `{cohort['source_core_start']}`--`{cohort['source_core_end']}`; provider `{cohort['provider']}`.", "",
        "| Time | C | Status | Exact interval | Outer enclosure | Inner witnesses | Vars | Seconds |",
        "|---|---:|---|---|---|---|---:|---:|",
    ]
    for cell in report["cells"]:
        exact = "—" if cell["lower"] is None else f"[{cell['lower']:.4f}, {cell['upper']:.4f}]"
        outer = f"[{cell['solver_outer_frontier_lower']:.4f}, {cell['solver_outer_frontier_upper']:.4f}]"
        inner = "—" if cell["solver_inner_width"] is None else f"[{cell['solver_inner_frontier_lower']:.4f}, {cell['solver_inner_frontier_upper']:.4f}]"
        seconds = cell["minimum_solve"]["elapsed_seconds"] + cell["maximum_solve"]["elapsed_seconds"]
        lines.append(f"| {cell['time_model']} | {cell['capacity']} | `{cell['status']}` | {exact} | {outer} | {inner} | {cell['variables']} | {seconds:.2f} |")
    lines += [
        "", f"Capacity audit: `{report['audit']['status']}`.", "",
        "Outer enclosures are not exact identified intervals. Results are conditional feasible-world statements and do not recover operational relationships.", "",
    ]
    return "\n".join(lines)


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for cell in report["cells"]:
        row = {k: v for k, v in cell.items() if k not in {"minimum_solve", "maximum_solve"}}
        for prefix in ("minimum", "maximum"):
            row.update({f"{prefix}_{k}": v for k, v in cell[f"{prefix}_solve"].items()})
        rows.append(row)
    fields = sorted({k for row in rows for k in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    cells = [solve_cell(base.synthetic_chain(), "exact_second", c, 10.0) for c in CAPACITIES]
    assert all(row["status"] == "CERTIFIED_OPTIMAL_PAIR" for row in cells)
    assert audit(cells)["status"] == "PASS"
    print("NYC ordered-run panel window self-test: PASS")


def parser() -> argparse.ArgumentParser:
    p = base.parser()
    p.description = __doc__
    p.set_defaults(output_dir=Path("tmp/nyc-hvfhv-ordered-panel-window"), ordered_core=8, solver_time_limit=90.0)
    p.add_argument("--window-label")
    p.add_argument("--time-models", nargs="+", choices=base.TIME_MODELS, default=["exact_second"])
    p.add_argument("--require-all-certified", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    base.validate(args)
    if not args.window_label:
        raise SystemExit("--window-label is required")
    if len(set(args.time_models)) != len(args.time_models):
        raise SystemExit("--time-models must not contain duplicates")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "REPORT.md").write_text(render(report), encoding="utf-8")
    write_csv(report, args.output_dir / "ordered_run_panel_cells.csv")
    print(render(report))
    return 2 if args.require_all_certified and any(row["status"] != "CERTIFIED_OPTIMAL_PAIR" for row in report["cells"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
