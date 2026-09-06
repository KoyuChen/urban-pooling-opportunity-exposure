#!/usr/bin/env python3
"""Merge certified NYC scale follow-ups into one audited lattice report.

The long-running workflow emits one aggregate report per target cell (plus the
small complete-enumeration check).  This utility replaces only explicitly
declared cells in a frozen base report.  It fails closed on missing targets,
snapshot/cohort drift, duplicate targets, or an invalid optimum certificate.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import live_nyc_hvfhv_branch_and_price_scale as scale

TOL = 1e-7


def parse_target(value: str) -> tuple[int, int]:
    try:
        core, capacity = (int(part) for part in value.split(":", 1))
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("targets must use CORE:CAPACITY") from error
    if core < 2 or capacity not in scale.CAPACITIES:
        raise argparse.ArgumentTypeError("invalid target core or capacity")
    return core, capacity


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def certified(cell: dict[str, Any]) -> bool:
    if cell.get("status") != "INTEGER_OPTIMUM_CERTIFIED":
        return False
    values = (
        cell.get("integer_maximum_selected_buffers"),
        cell.get("global_lower_bound"),
        cell.get("global_upper_bound"),
    )
    if any(value is None for value in values):
        return False
    objective, lower, upper = (float(value) for value in values)
    return abs(objective - lower) <= TOL and abs(objective - upper) <= TOL


def merge(
    base: dict[str, Any],
    followups: list[dict[str, Any]],
    expected_targets: list[tuple[int, int]],
) -> dict[str, Any]:
    expected = set(expected_targets)
    if not expected or len(expected) != len(expected_targets):
        raise ValueError("expected targets must be nonempty and unique")

    base_cells = {
        (int(cell["core_rows"]), int(cell["capacity"])): cell
        for cell in base.get("cells", [])
    }
    if not expected.issubset(base_cells):
        raise ValueError("one or more expected targets are absent from the base report")

    replacements: dict[tuple[int, int], dict[str, Any]] = {}
    for report in followups:
        if report.get("snapshot") != base.get("snapshot"):
            raise ValueError("follow-up snapshot does not match the base report")
        if report.get("cohort") != base.get("cohort"):
            raise ValueError("follow-up cohort does not match the base report")
        matches = [
            cell
            for cell in report.get("cells", [])
            if (int(cell["core_rows"]), int(cell["capacity"])) in expected
        ]
        if len(matches) != 1:
            raise ValueError("each follow-up report must contain exactly one target cell")
        cell = matches[0]
        key = (int(cell["core_rows"]), int(cell["capacity"]))
        if key in replacements:
            raise ValueError(f"duplicate follow-up target: {key}")
        if not certified(cell):
            raise ValueError(f"target lacks a valid integer optimum certificate: {key}")
        replacements[key] = cell

    if set(replacements) != expected:
        missing = sorted(expected - set(replacements))
        raise ValueError(f"missing follow-up targets: {missing}")

    result = copy.deepcopy(base)
    result["cells"] = [
        copy.deepcopy(replacements.get((int(cell["core_rows"]), int(cell["capacity"])), cell))
        for cell in base["cells"]
    ]
    certified_cells = [cell for cell in result["cells"] if certified(cell)]
    unresolved = [
        cell
        for cell in result["cells"]
        if cell.get("status") == "INTEGER_BRANCH_AND_PRICE_UNRESOLVED"
    ]
    skipped = [
        cell
        for cell in result["cells"]
        if cell.get("status") == "SKIPPED_INSUFFICIENT_PUBLIC_ROWS"
    ]
    result["summary"] = {
        "cell_count": len(result["cells"]),
        "certified_integer_optimum_count": len(certified_cells),
        "unresolved_with_bounds_count": len(unresolved),
        "skipped_insufficient_rows_count": len(skipped),
        "larger_than_small_audit_certified_count": sum(
            (int(cell["core_rows"]), int(cell["buffer_rows"])) != (4, 12)
            for cell in certified_cells
        ),
    }
    result["generated_at_utc"] = max(
        [str(base.get("generated_at_utc", ""))]
        + [str(report.get("generated_at_utc", "")) for report in followups]
    )
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-report", type=Path, required=True)
    p.add_argument("--followup-report", type=Path, action="append", required=True)
    p.add_argument("--expected-target", type=parse_target, action="append", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    report = merge(
        load(args.base_report),
        [load(path) for path in args.followup_report],
        args.expected_target,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "REPORT.md").write_text(scale.render(report), encoding="utf-8")
    scale.write_csv(report, args.output_dir / "branch_and_price_scale_cells.csv")
    print(scale.render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
