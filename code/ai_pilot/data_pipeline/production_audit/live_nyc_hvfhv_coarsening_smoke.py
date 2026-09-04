#!/usr/bin/env python3
"""Run the NYC HVFHV exact-second versus artificial 15-minute smoke test.

The public data expose one row per shared-matched passenger trip but no co-rider
key, shared-run key, vehicle key, or realized pool size. Results are therefore
aggregate candidate-support bounds under a conditional C=2 benchmark, never
reconstructed partner claims.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from nyc_hvfhv_smoke_bounds import audits, solve_point, temporal_edges, tier_edges
from nyc_hvfhv_smoke_fetch import choose_and_fetch, count, snapshot
from nyc_hvfhv_smoke_types import (
    CERTIFIED,
    DATASET_ID,
    DATASET_NAME,
    TIERS,
    LiveDataError,
    Trip,
    model_rows,
    parse_trips,
    required_dt,
    round15,
    sha,
)


def render(report: Mapping[str, Any]) -> str:
    cohort = report["cohort"]
    lines = [
        "# NYC HVFHV exact-time versus artificial 15-minute frontier",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Dataset: `{DATASET_ID}` ({DATASET_NAME})  ",
        f"Snapshot fingerprint: `{report['snapshot']['revision_fingerprint_sha256']}`",
        "",
        "## Fixed cohort",
        "",
        f"Provider `{cohort['provider']}`, pickup core `{cohort['core_start']}`--"
        f"`{cohort['core_end']}`: **{cohort['core_rows']}** public shared-match "
        f"rows and **{cohort['buffer_rows']}** buffer rows "
        f"(**{cohort['candidate_rows']}** candidates total).",
        "",
        "The same released rows are analyzed at exact-second resolution and after "
        "artificial nearest-15-minute coarsening. All results are conditional C=2 "
        "cover benchmarks; NYC does not release the realized pool size or partner key.",
        "",
        "| Time model | Zone support | Edges | Core min degree | Cover | Miles width | Time width (min) |",
        "|---|---|---:|---:|---|---:|---:|",
    ]
    lookup: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in report["sensitivity_rows"]:
        lookup[(row["time_resolution"], row["support_tier"])][row["query"]] = row
    for point in report["graph_points"]:
        cell = lookup[(point["time_resolution"], point["support_tier"])]
        miles = cell.get("mean_absolute_trip_miles_gap_per_core", {})
        duration = cell.get("mean_absolute_trip_time_gap_per_core", {})
        miles_width = (
            "—" if miles.get("width") is None else f"{miles['width']:.4f}"
        )
        duration_width = (
            "—" if duration.get("width") is None else f"{duration['width']:.4f}"
        )
        lines.append(
            f"| {point['time_resolution']} | {point['support_tier']} | "
            f"{point['edge_count']} | {point['core_min_degree']} | "
            f"`{point['cover_status']}` | {miles_width} | {duration_width} |"
        )
    lines.extend(
        [
            "",
            "## Audit",
            "",
            f"Nested-support and coarsening audit: `{report['audit']['status']}`; "
            "certified exact-versus-rounded endpoint comparisons: "
            f"**{report['audit']['certified_exact_rounded_comparisons']}**.",
            "",
            "The candidate universe is count-reconciled and the snapshot/counts are "
            "stable for this extraction. This does not establish hidden-run closure, "
            "partner recall, a true C=2 population, or a citywide effect.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def plot(report: Mapping[str, Any], output: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for resolution in ("exact_second", "rounded_15m_outer"):
        points = sorted(
            (
                point
                for point in report["graph_points"]
                if point["time_resolution"] == resolution
            ),
            key=lambda point: point["support_rank"],
        )
        plt.plot(
            [point["support_rank"] for point in points],
            [point["edge_count"] for point in points],
            marker="o",
            label=resolution,
        )
    plt.xticks(
        [rank for _tier, rank in TIERS],
        [tier for tier, _rank in TIERS],
        rotation=20,
        ha="right",
    )
    plt.ylabel("Candidate edges")
    plt.xlabel("Zone support relaxation")
    plt.legend(frameon=False)
    plt.tight_layout()
    path = output / "nyc_candidate_edge_coarsening.svg"
    plt.savefig(path)
    plt.close()
    return [path.name]


def run(args: argparse.Namespace) -> dict[str, Any]:
    snapshot_before = snapshot()
    selected = choose_and_fetch(args)
    raw_rows = selected["candidate_rows"]
    snapshot_after = snapshot()
    if snapshot_before != snapshot_after:
        raise LiveDataError("dataset metadata/schema changed during extraction")
    determinate_after, _, _ = count(selected["where"]["determinate"])
    indeterminate_after, _, _ = count(selected["where"]["indeterminate"])
    if (
        determinate_after != selected["determinate_count"]
        or indeterminate_after != selected["indeterminate_count"]
    ):
        raise LiveDataError("candidate server counts changed during extraction")
    trips, row_audit = parse_trips(
        raw_rows,
        selected["provider"],
        selected["core_start"],
        selected["core_end"],
    )
    if row_audit["core_rows"] != len(selected["core_rows"]):
        raise LiveDataError("core row count not recovered")
    models = {
        resolution: model_rows(trips, resolution)
        for resolution in ("exact_second", "rounded_15m_outer")
    }
    temporal = {
        resolution: temporal_edges(rows)
        for resolution, rows in models.items()
    }
    edge_sets = {
        resolution: {
            tier: set(tier_edges(models[resolution], temporal[resolution], tier))
            for tier, _rank in TIERS
        }
        for resolution in models
    }
    rounded_count = len(temporal["rounded_15m_outer"])
    points: list[dict[str, Any]] = []
    sensitivity: list[dict[str, Any]] = []
    for resolution in ("exact_second", "rounded_15m_outer"):
        for tier, rank in TIERS:
            point, query_rows = solve_point(
                models[resolution],
                sorted(edge_sets[resolution][tier]),
                resolution,
                tier,
                rank,
                rounded_count,
                args.solver_time_limit,
            )
            points.append(point)
            sensitivity.extend(query_rows)
    audit = audits(edge_sets, sensitivity)
    relaxed = next(
        point
        for point in points
        if point["time_resolution"] == "rounded_15m_outer"
        and point["support_tier"] == "provider_time_only"
    )
    if relaxed["cover_status"] != CERTIFIED:
        raise LiveDataError(
            "relaxed rounded C=2 benchmark is not certified feasible"
        )
    if audit["status"] != "PASS":
        raise LiveDataError(
            "support/coarsening audit failed: "
            + json.dumps(audit["problems"][:8])
        )
    report = {
        "report_version": "nyc-hvfhv-coarsening-smoke/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "snapshot": snapshot_after,
        "extraction": {
            "scan_start": args.scan_start,
            "scan_end": args.scan_end,
            "scan_window_hours": args.scan_window_hours,
            "selection": (
                "first scan window containing the highest-count provider x "
                "15-minute pickup bin within declared caps"
            ),
            "considered_windows": selected["considered"],
            "query_sha256": selected["queries"],
            "api_paths": selected["apis"],
            "raw_candidate_rows_sha256": sha(raw_rows),
            "raw_rows_serialized": False,
        },
        "cohort": {
            "provider": selected["provider"],
            "core_start": selected["core_start"].isoformat(),
            "core_end": selected["core_end"].isoformat(),
            "core_rows": row_audit["core_rows"],
            "buffer_rows": row_audit["buffer_rows"],
            "candidate_rows": len(trips),
            "determinate_rows": selected["determinate_count"],
            "indeterminate_rows": selected["indeterminate_count"],
            "row_audit": row_audit,
            "snapshot_stable": True,
            "server_counts_stable": True,
        },
        "time_models": {
            "exact_second": "released public timestamps as written",
            "rounded_15m_outer": (
                "nearest-15-minute artificial rounding with +/-7.5-minute "
                "outer intervals"
            ),
        },
        "graph_points": points,
        "sensitivity_rows": sensitivity,
        "audit": audit,
        "claim_boundary": {
            "supported": (
                "one fixed public shared-match cohort; count-stable candidate "
                "extraction; exact-versus-coarsened conditional C=2 support "
                "sensitivity"
            ),
            "not_supported": (
                "actual partners, hidden-run closure, realized pool size, partner "
                "recall, or a NYC population effect"
            ),
        },
        "redaction": {
            "raw_rows_emitted": False,
            "row_identifiers_emitted": False,
            "cover_witnesses_emitted": False,
            "aggregate_only": True,
        },
    }
    report["report_sha256"] = sha(report)
    return report


def write_outputs(report: Mapping[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_csv(
        report["sensitivity_rows"],
        output / "candidate_support_sensitivity.csv",
    )
    write_csv(report["graph_points"], output / "candidate_graph_curve.csv")
    plot_files = plot(report, output)
    compact = dict(report)
    compact.pop("sensitivity_rows", None)
    compact["plot_files"] = plot_files
    (output / "report.json").write_text(
        json.dumps(compact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "NYC_HVFHV_COARSENING_REPORT.md").write_text(
        render(report),
        encoding="utf-8",
    )


def synthetic_trip(
    index: int,
    role: str,
    pickup: datetime,
    dropoff: datetime,
    pickup_zone: str,
    dropoff_zone: str,
) -> Trip:
    return Trip(
        index,
        "HV0003",
        role,
        pickup,
        dropoff,
        pickup_zone,
        dropoff_zone,
        float(index + 1),
        float((dropoff - pickup).total_seconds()),
        float(10 + index),
        float(7 + index),
    )


def self_test() -> None:
    base = datetime(2023, 1, 1, 12)
    trips = [
        synthetic_trip(0, "core", base, base + timedelta(minutes=20), "1", "2"),
        synthetic_trip(
            1,
            "core",
            base + timedelta(minutes=1),
            base + timedelta(minutes=21),
            "1",
            "2",
        ),
        synthetic_trip(
            2,
            "buffer",
            base + timedelta(minutes=22),
            base + timedelta(minutes=40),
            "1",
            "3",
        ),
        synthetic_trip(
            3,
            "buffer",
            base - timedelta(minutes=10),
            base + timedelta(minutes=5),
            "4",
            "2",
        ),
    ]
    exact = model_rows(trips, "exact_second")
    rounded = model_rows(trips, "rounded_15m_outer")
    exact_temporal = temporal_edges(exact)
    rounded_temporal = temporal_edges(rounded)
    assert set(exact_temporal) <= set(rounded_temporal)
    assert (0, 2) not in exact_temporal and (0, 2) in rounded_temporal
    sets = {
        "exact_second": {
            tier: set(tier_edges(exact, exact_temporal, tier))
            for tier, _rank in TIERS
        },
        "rounded_15m_outer": {
            tier: set(tier_edges(rounded, rounded_temporal, tier))
            for tier, _rank in TIERS
        },
    }
    query_rows: list[dict[str, Any]] = []
    for resolution, rows in (
        ("exact_second", exact),
        ("rounded_15m_outer", rounded),
    ):
        for tier, rank in TIERS:
            _point, cell_rows = solve_point(
                rows,
                sorted(sets[resolution][tier]),
                resolution,
                tier,
                rank,
                len(rounded_temporal),
                10,
            )
            query_rows.extend(cell_rows)
    assert audits(sets, query_rows)["status"] == "PASS"
    assert round15(base + timedelta(minutes=7, seconds=30)) == base + timedelta(
        minutes=15
    )
    print("NYC HVFHV coarsening smoke self-test: PASS")


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/nyc-hvfhv-coarsening"),
    )
    argument_parser.add_argument(
        "--scan-start",
        default="2023-01-03T17:00:00",
    )
    argument_parser.add_argument(
        "--scan-end",
        default="2023-01-04T01:00:00",
    )
    argument_parser.add_argument("--scan-window-hours", type=float, default=1.0)
    argument_parser.add_argument("--min-core-rows", type=int, default=6)
    argument_parser.add_argument("--max-core-rows", type=int, default=40)
    argument_parser.add_argument("--max-scan-rows", type=int, default=5000)
    argument_parser.add_argument(
        "--max-candidate-rows",
        type=int,
        default=2500,
    )
    argument_parser.add_argument(
        "--max-indeterminate-rows",
        type=int,
        default=200,
    )
    argument_parser.add_argument(
        "--solver-time-limit",
        type=float,
        default=30.0,
    )
    argument_parser.add_argument("--self-test", action="store_true")
    return argument_parser


def validate(args: argparse.Namespace) -> None:
    if required_dt(args.scan_start) >= required_dt(args.scan_end):
        raise SystemExit("scan start must precede scan end")
    if (
        args.scan_window_hours <= 0
        or args.min_core_rows < 2
        or args.max_core_rows < args.min_core_rows
    ):
        raise SystemExit("invalid scan/core caps")
    if (
        args.max_scan_rows < args.max_core_rows
        or args.max_candidate_rows < args.max_core_rows
        or args.max_indeterminate_rows < 0
    ):
        raise SystemExit("invalid row caps")
    if args.solver_time_limit <= 0:
        raise SystemExit("solver time must be positive")


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    validate(args)
    report = run(args)
    write_outputs(report, args.output_dir)
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
