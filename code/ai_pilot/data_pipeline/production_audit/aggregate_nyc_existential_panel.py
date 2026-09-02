#!/usr/bin/env python3
"""Aggregate a predeclared NYC existential-support audit panel.

The input directory contains one artifact directory per window/capacity cell,
with `panel_cell.json` and, when successful, the support-frontier `report.json`.
The aggregator verifies that all capacities for a window used the same selected
cohort, audits capacity nesting where statuses permit, and reports support-gain
lower bounds without converting unresolved cells to infeasibility.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CAPACITIES = (2, 3, 4)


def load_cells(input_dir: Path) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for metadata_path in sorted(input_dir.rglob("panel_cell.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        report_path = metadata_path.with_name("report.json")
        cells.append(
            {
                "metadata": metadata,
                "metadata_path": str(metadata_path.relative_to(input_dir)),
                "report_path": (
                    str(report_path.relative_to(input_dir))
                    if report_path.exists()
                    else None
                ),
                "report": (
                    json.loads(report_path.read_text(encoding="utf-8"))
                    if report_path.exists()
                    else None
                ),
            }
        )
    return cells


def summarize(cells: list[dict[str, Any]]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    by_window: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    declared_windows: dict[str, dict[str, Any]] = {}

    for cell in cells:
        metadata = cell["metadata"]
        label = str(metadata["window_label"])
        capacity = int(metadata["capacity"])
        declared_windows[label] = {
            "window_label": label,
            "scan_start": metadata["scan_start"],
            "scan_end": metadata["scan_end"],
        }
        if capacity in by_window[label]:
            problems.append(
                {
                    "reason": "duplicate_window_capacity_cell",
                    "window": label,
                    "capacity": capacity,
                }
            )
        by_window[label][capacity] = cell

    rows: list[dict[str, Any]] = []
    window_summaries: list[dict[str, Any]] = []
    for label in sorted(declared_windows):
        capacity_cells = by_window.get(label, {})
        missing = [capacity for capacity in CAPACITIES if capacity not in capacity_cells]
        if missing:
            problems.append(
                {
                    "reason": "missing_capacity_artifacts",
                    "window": label,
                    "capacities": missing,
                }
            )

        successful_reports = {
            capacity: capacity_cells[capacity]["report"]
            for capacity in CAPACITIES
            if capacity in capacity_cells
            and capacity_cells[capacity]["report"] is not None
        }
        failed = [capacity for capacity in CAPACITIES if capacity not in successful_reports]
        if failed:
            problems.append(
                {
                    "reason": "missing_successful_report",
                    "window": label,
                    "capacities": failed,
                }
            )

        cohort_keys = set()
        snapshot_keys = set()
        for report in successful_reports.values():
            cohort = report["cohort"]
            cohort_keys.add(
                (
                    cohort["provider"],
                    cohort["source_core_start"],
                    cohort["source_core_end"],
                    cohort["audit_core_rows"],
                    cohort["audit_buffer_rows"],
                )
            )
            snapshot_keys.add(report["snapshot"]["revision_fingerprint_sha256"])
            if report["support_containment_audit"]["status"] != "PASS":
                problems.append(
                    {
                        "reason": "support_containment_failed",
                        "window": label,
                        "capacity": report["capacity"],
                    }
                )
        if len(cohort_keys) > 1:
            problems.append({"reason": "cohort_changed_across_capacity", "window": label})
        if len(snapshot_keys) > 1:
            problems.append({"reason": "snapshot_changed_across_capacity", "window": label})

        exact_sets: dict[int, set[int]] = {}
        coarse_feasible_sets: dict[int, set[int]] = {}
        coarse_infeasible_sets: dict[int, set[int]] = {}
        exact_maxima: dict[int, int | None] = {}
        coarse_certified_maxima: dict[int, int | None] = {}

        for capacity in CAPACITIES:
            report = successful_reports.get(capacity)
            if report is None:
                continue
            summary = report["frontier_summary"]
            exact_set = set(summary["exact_feasible_counts"])
            coarse_feasible = set(summary["coarse_certified_feasible_counts"])
            coarse_infeasible = set(summary["coarse_proven_infeasible_counts"])
            exact_sets[capacity] = exact_set
            coarse_feasible_sets[capacity] = coarse_feasible
            coarse_infeasible_sets[capacity] = coarse_infeasible
            exact_max = summary["maximum_exact_feasible_count"]
            coarse_max = summary["maximum_coarse_certified_feasible_count"]
            exact_maxima[capacity] = exact_max
            coarse_certified_maxima[capacity] = coarse_max
            gain_lower_bound = (
                None
                if exact_max is None or coarse_max is None
                else max(0, int(coarse_max) - int(exact_max))
            )
            rows.append(
                {
                    "window_label": label,
                    "scan_start": declared_windows[label]["scan_start"],
                    "scan_end": declared_windows[label]["scan_end"],
                    "capacity": capacity,
                    "provider": report["cohort"]["provider"],
                    "selected_core_start": report["cohort"]["source_core_start"],
                    "selected_core_end": report["cohort"]["source_core_end"],
                    "source_core_rows": report["cohort"]["source_core_rows"],
                    "source_candidate_rows": report["cohort"]["source_candidate_rows"],
                    "exact_feasible_counts": ";".join(map(str, sorted(exact_set))),
                    "exact_max_selected_buffers": exact_max,
                    "coarse_certified_feasible_counts": ";".join(
                        map(str, sorted(coarse_feasible))
                    ),
                    "coarse_certified_max_selected_buffers": coarse_max,
                    "coarse_unresolved_counts": ";".join(
                        map(str, summary["coarse_unresolved_counts"])
                    ),
                    "coarse_proven_infeasible_counts": ";".join(
                        map(str, sorted(coarse_infeasible))
                    ),
                    "certified_support_gain_lower_bound": gain_lower_bound,
                    "exact_run_column_count": report["exact_singleton_frontier"][
                        "run_column_count"
                    ],
                    "exact_master_state_count": report["exact_singleton_frontier"][
                        "explored_master_state_count"
                    ],
                    "max_exact_run_column_size": report["exact_singleton_frontier"][
                        "max_members_in_one_feasible_run_column"
                    ],
                }
            )

        for left, right in zip(CAPACITIES, CAPACITIES[1:]):
            if (
                left in exact_sets
                and right in exact_sets
                and not exact_sets[left] <= exact_sets[right]
            ):
                problems.append(
                    {
                        "reason": "exact_capacity_nesting_violation",
                        "window": label,
                        "left": left,
                        "right": right,
                    }
                )
            if left in coarse_feasible_sets and right in coarse_infeasible_sets:
                contradiction = sorted(
                    coarse_feasible_sets[left] & coarse_infeasible_sets[right]
                )
                if contradiction:
                    problems.append(
                        {
                            "reason": "coarse_capacity_feasibility_contradiction",
                            "window": label,
                            "left": left,
                            "right": right,
                            "counts": contradiction,
                        }
                    )

        c2_reaches_c3 = (
            coarse_certified_maxima.get(2) is not None
            and exact_maxima.get(3) is not None
            and coarse_certified_maxima[2] >= exact_maxima[3]
        )
        c3_reaches_c4 = (
            coarse_certified_maxima.get(3) is not None
            and exact_maxima.get(4) is not None
            and coarse_certified_maxima[3] >= exact_maxima[4]
        )
        window_summaries.append(
            {
                **declared_windows[label],
                "complete_capacity_triplet": not missing and not failed,
                "coarse_C2_reaches_exact_C3_max": c2_reaches_c3,
                "coarse_C3_reaches_exact_C4_max": c3_reaches_c4,
                "capacity_equivalent_step_count": int(c2_reaches_c3)
                + int(c3_reaches_c4),
                "cohort_key_count": len(cohort_keys),
                "snapshot_key_count": len(snapshot_keys),
            }
        )

    complete_windows = [
        row for row in window_summaries if row["complete_capacity_triplet"]
    ]
    panel_summary = {
        "declared_window_count": len(declared_windows),
        "complete_window_count": len(complete_windows),
        "C2_windows_with_positive_certified_gain": sum(
            row["capacity"] == 2
            and (row["certified_support_gain_lower_bound"] or 0) > 0
            for row in rows
        ),
        "C3_windows_with_positive_certified_gain": sum(
            row["capacity"] == 3
            and (row["certified_support_gain_lower_bound"] or 0) > 0
            for row in rows
        ),
        "windows_where_coarse_C2_reaches_exact_C3_max": sum(
            row["coarse_C2_reaches_exact_C3_max"] for row in complete_windows
        ),
        "windows_where_coarse_C3_reaches_exact_C4_max": sum(
            row["coarse_C3_reaches_exact_C4_max"] for row in complete_windows
        ),
        "coarse_unresolved_cell_count": sum(
            bool(row["coarse_unresolved_counts"]) for row in rows
        ),
    }
    return {
        "status": "PASS" if not problems and complete_windows else "FAIL",
        "problem_count": len(problems),
        "problems": problems,
        "rows": rows,
        "windows": window_summaries,
        "panel_summary": panel_summary,
    }


def render(result: dict[str, Any]) -> str:
    summary = result["panel_summary"]
    lines = [
        "# NYC existential timestamp support panel",
        "",
        f"Generated UTC: `{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}`",
        "",
        "This is a predeclared purposive audit panel. It is not a probability sample "
        "and does not support NYC population prevalence statements.",
        "",
        "| Window | C | Exact max buffers | Coarse certified max | Certified gain lower bound | Coarse unresolved counts |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in sorted(
        result["rows"],
        key=lambda item: (item["window_label"], item["capacity"]),
    ):
        lines.append(
            f"| {row['window_label']} | {row['capacity']} | "
            f"{row['exact_max_selected_buffers']} | "
            f"{row['coarse_certified_max_selected_buffers']} | "
            f"{row['certified_support_gain_lower_bound']} | "
            f"`{row['coarse_unresolved_counts'] or 'none'}` |"
        )
    lines.extend(
        [
            "",
            "## Panel diagnostics",
            "",
            f"- Complete capacity triplets: **{summary['complete_window_count']} / {summary['declared_window_count']}**.",
            f"- Positive certified support-gain lower bound at C=2: **{summary['C2_windows_with_positive_certified_gain']}** windows.",
            f"- Positive certified support-gain lower bound at C=3: **{summary['C3_windows_with_positive_certified_gain']}** windows.",
            "- Artificial coarse C=2 reaches the exact C=3 maximum in "
            f"**{summary['windows_where_coarse_C2_reaches_exact_C3_max']}** complete windows.",
            "- Artificial coarse C=3 reaches the exact C=4 maximum in "
            f"**{summary['windows_where_coarse_C3_reaches_exact_C4_max']}** complete windows.",
            f"- Window-capacity cells with unresolved coarse counts: **{summary['coarse_unresolved_cell_count']}**.",
            "",
            f"Panel audit status: `{result['status']}` with **{result['problem_count']}** problems.",
            "",
            "Every gain is a lower bound based only on certified feasible coarse "
            "witnesses. Unresolved counts are not treated as infeasible. The supports "
            "are an artificial nearest-15-minute experiment, not the TLC observation "
            "operator. No co-rider, run, realized-capacity, or population claim is made.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    fixture = {
        "metadata": {
            "window_label": "w",
            "scan_start": "2023-01-01T00:00:00",
            "scan_end": "2023-01-01T04:00:00",
        }
    }
    cells = []
    for capacity, exact_max, coarse_max in ((2, 4, 8), (3, 8, 12), (4, 12, 12)):
        report = {
            "capacity": capacity,
            "cohort": {
                "provider": "HV0005",
                "source_core_start": "2023-01-01T00:00:00",
                "source_core_end": "2023-01-01T00:15:00",
                "source_core_rows": 10,
                "source_candidate_rows": 100,
                "audit_core_rows": 4,
                "audit_buffer_rows": 12,
            },
            "snapshot": {"revision_fingerprint_sha256": "x"},
            "support_containment_audit": {"status": "PASS"},
            "frontier_summary": {
                "exact_feasible_counts": list(range(exact_max + 1)),
                "coarse_certified_feasible_counts": list(range(coarse_max + 1)),
                "coarse_proven_infeasible_counts": [],
                "coarse_unresolved_counts": [],
                "maximum_exact_feasible_count": exact_max,
                "maximum_coarse_certified_feasible_count": coarse_max,
            },
            "exact_singleton_frontier": {
                "run_column_count": capacity,
                "explored_master_state_count": capacity,
                "max_members_in_one_feasible_run_column": capacity,
            },
        }
        cells.append(
            {
                "metadata": {**fixture["metadata"], "capacity": capacity},
                "report": report,
            }
        )
    result = summarize(cells)
    assert result["status"] == "PASS", result
    assert (
        result["panel_summary"][
            "windows_where_coarse_C2_reaches_exact_C3_max"
        ]
        == 1
    )
    print("NYC existential support panel aggregator self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input_dir is None or args.output_dir is None:
        parser.error("--input-dir and --output-dir are required")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = summarize(load_cells(args.input_dir))
    report = {
        "report_version": "nyc-existential-support-panel/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        **result,
        "claim_boundary": {
            "supported": "descriptive replication across predeclared purposive audit windows under the declared artificial timestamp-support model",
            "not_supported": "NYC population prevalence, actual TLC release semantics, actual co-riders or runs, realized capacity, or causal effects",
        },
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "PANEL_REPORT.md").write_text(
        render(result),
        encoding="utf-8",
    )
    write_csv(result["rows"], args.output_dir / "panel_cells.csv")
    (args.output_dir / "panel_windows.json").write_text(
        json.dumps(result["windows"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(render(result))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
