#!/usr/bin/env python3
"""NYC HVFHV existential latent-time completion Gate.

The public exact timestamps are artificially rounded to nearest 15 minutes.
Instead of treating +/-7.5-minute outer envelopes as realized trip intervals,
this Gate selects one latent exact pickup and drop-off inside every released
support and imposes ordered-run connectivity and occupancy on that selected
completion. The exact singleton model is therefore nested inside the artificial
coarse-support model by construction.

The live Gate uses a small, predeclared, time-selected audit cohort. It reports
aggregate feasible-world bounds only and does not recover actual co-riders,
vehicle runs, realized capacity, or TLC production matching logic.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

import live_nyc_hvfhv_ordered_run_smoke as base
from nyc_hvfhv_smoke_types import ROUNDING_HALF_MINUTES, Trip, round15
from ordered_run_existential_time import (
    CERTIFIED,
    TOL,
    TimeSupportRow,
    attribute_objective,
    build_program,
    solve,
)

CAPACITIES = (2, 3, 4)
TIME_MODELS = ("exact_singleton", "rounded_15m_existential")


def exact_temporal_gap_seconds(row: Trip, cores: Sequence[Trip]) -> float:
    if row.pickup is None or row.dropoff is None:
        return float("inf")
    best = float("inf")
    for core in cores:
        if core.pickup is None or core.dropoff is None:
            continue
        if row.pickup < core.dropoff and core.pickup < row.dropoff:
            return 0.0
        if row.dropoff <= core.pickup:
            best = min(best, (core.pickup - row.dropoff).total_seconds())
        elif core.dropoff <= row.pickup:
            best = min(best, (row.pickup - core.dropoff).total_seconds())
    return best


def reduced_cohort(
    trips: Sequence[Trip],
    core_limit: int,
    buffer_limit: int,
) -> list[Trip]:
    complete_time = [
        trip
        for trip in trips
        if trip.pickup is not None and trip.dropoff is not None
    ]
    original_core = sorted(
        (trip for trip in complete_time if trip.role == "core"),
        key=lambda trip: trip.index,
    )
    if len(original_core) < core_limit:
        raise base.LiveDataError(
            f"existential core limit {core_limit} exceeds available {len(original_core)}"
        )
    selected_core = original_core[:core_limit]
    selected_indices = {trip.index for trip in selected_core}
    candidates = [
        trip
        for trip in complete_time
        if trip.index not in selected_indices
        and trip.miles is not None
        and trip.seconds is not None
    ]
    candidates.sort(
        key=lambda trip: (
            exact_temporal_gap_seconds(trip, selected_core),
            trip.pickup,
            trip.dropoff,
            trip.index,
        )
    )
    selected_buffers = candidates[:buffer_limit]
    if len(selected_buffers) < buffer_limit:
        raise base.LiveDataError(
            f"only {len(selected_buffers)} complete buffer candidates for requested {buffer_limit}"
        )

    output: list[Trip] = []
    for trip in [*selected_core, *selected_buffers]:
        output.append(
            Trip(
                index=trip.index,
                provider=trip.provider,
                role="core" if trip.index in selected_indices else "buffer",
                pickup=trip.pickup,
                dropoff=trip.dropoff,
                pickup_zone=trip.pickup_zone,
                dropoff_zone=trip.dropoff_zone,
                miles=trip.miles,
                seconds=trip.seconds,
                fare=trip.fare,
                driver_pay=trip.driver_pay,
            )
        )
    output.sort(key=lambda trip: trip.index)
    return output


def support_origin(trips: Sequence[Trip]) -> datetime:
    lower_values: list[datetime] = []
    for trip in trips:
        if trip.pickup is None or trip.dropoff is None:
            raise ValueError("support rows require determinate timestamps")
        lower_values.extend(
            [
                round15(trip.pickup)
                - timedelta(minutes=ROUNDING_HALF_MINUTES),
                round15(trip.dropoff)
                - timedelta(minutes=ROUNDING_HALF_MINUTES),
                trip.pickup,
                trip.dropoff,
            ]
        )
    return min(lower_values).replace(microsecond=0)


def support_rows(
    trips: Sequence[Trip],
    time_model: str,
    origin: datetime,
) -> list[TimeSupportRow]:
    output: list[TimeSupportRow] = []
    for trip in trips:
        if trip.pickup is None or trip.dropoff is None:
            raise ValueError("support rows require determinate timestamps")
        if time_model == "exact_singleton":
            start_lower = start_upper = (trip.pickup - origin).total_seconds()
            end_lower = end_upper = (trip.dropoff - origin).total_seconds()
        elif time_model == "rounded_15m_existential":
            released_start = round15(trip.pickup)
            released_end = round15(trip.dropoff)
            start_lower = (
                released_start
                - timedelta(minutes=ROUNDING_HALF_MINUTES)
                - origin
            ).total_seconds()
            start_upper = (
                released_start
                + timedelta(minutes=ROUNDING_HALF_MINUTES)
                - origin
            ).total_seconds()
            end_lower = (
                released_end
                - timedelta(minutes=ROUNDING_HALF_MINUTES)
                - origin
            ).total_seconds()
            end_upper = (
                released_end
                + timedelta(minutes=ROUNDING_HALF_MINUTES)
                - origin
            ).total_seconds()
        else:
            raise ValueError(time_model)
        output.append(
            TimeSupportRow(
                index=trip.index,
                role=trip.role,
                start_lower=start_lower,
                start_upper=start_upper,
                end_lower=end_lower,
                end_upper=end_upper,
                miles=trip.miles,
                seconds=trip.seconds,
            )
        )
    return output


def support_containment_audit(
    exact: Sequence[TimeSupportRow],
    coarse: Sequence[TimeSupportRow],
) -> dict[str, Any]:
    coarse_by_index = {row.index: row for row in coarse}
    problems: list[dict[str, Any]] = []
    max_start_half_width = 0.0
    max_end_half_width = 0.0
    for exact_row in exact:
        coarse_row = coarse_by_index.get(exact_row.index)
        if coarse_row is None:
            problems.append(
                {"reason": "row_missing_from_coarse_support", "row": exact_row.index}
            )
            continue
        if not (
            coarse_row.start_lower - TOL
            <= exact_row.start_lower
            <= coarse_row.start_upper + TOL
        ):
            problems.append(
                {"reason": "exact_start_not_contained", "row": exact_row.index}
            )
        if not (
            coarse_row.end_lower - TOL
            <= exact_row.end_lower
            <= coarse_row.end_upper + TOL
        ):
            problems.append(
                {"reason": "exact_end_not_contained", "row": exact_row.index}
            )
        max_start_half_width = max(
            max_start_half_width,
            (coarse_row.start_upper - coarse_row.start_lower) / 2.0,
        )
        max_end_half_width = max(
            max_end_half_width,
            (coarse_row.end_upper - coarse_row.end_lower) / 2.0,
        )
    return {
        "status": "PASS" if not problems else "FAIL",
        "row_count": len(exact),
        "problem_count": len(problems),
        "problems": problems,
        "max_start_half_width_seconds": max_start_half_width,
        "max_end_half_width_seconds": max_end_half_width,
    }


def solve_cell(
    rows: Sequence[TimeSupportRow],
    capacity: int,
    common_buffer_count: int,
    epsilon: float,
    time_limit: float,
) -> dict[str, Any]:
    program = build_program(
        rows,
        capacity,
        common_buffer_count,
        epsilon=epsilon,
    )
    feasibility = solve(
        program,
        np.zeros(program.matrix.shape[1], dtype=float),
        maximize=False,
        time_limit=time_limit,
    )
    if feasibility["status"] != CERTIFIED:
        return {
            "capacity": capacity,
            "status": "UNRESOLVED_COMMON_SUPPORT_FEASIBILITY",
            "feasibility_status": feasibility["status"],
            "feasibility_mip_gap": feasibility["mip_gap"],
            "outcomes": [],
            "variable_count": program.matrix.shape[1],
            "constraint_count": program.matrix.shape[0],
        }

    outcomes: list[dict[str, Any]] = []
    for query, attribute, scale, unit in (
        (
            "mean_selected_buffer_miles_at_common_support",
            "miles",
            1.0,
            "miles",
        ),
        (
            "mean_selected_buffer_trip_minutes_at_common_support",
            "seconds",
            60.0,
            "minutes",
        ),
    ):
        objective, missing = attribute_objective(program, attribute)
        if objective is None:
            outcomes.append(
                {
                    "query": query,
                    "unit": unit,
                    "status": "UNRESOLVED_MISSING_PUBLIC_VALUES",
                    "lower": None,
                    "upper": None,
                    "width": None,
                    "missing_buffer_rows": len(missing),
                }
            )
            continue
        objective = objective / scale
        lower = solve(
            program,
            objective,
            maximize=False,
            time_limit=time_limit,
        )
        upper = solve(
            program,
            objective,
            maximize=True,
            time_limit=time_limit,
        )
        certified = (
            lower["status"] == upper["status"] == CERTIFIED
            and lower["value"] is not None
            and upper["value"] is not None
            and lower["value"] <= upper["value"] + TOL
        )
        outcomes.append(
            {
                "query": query,
                "unit": unit,
                "status": (
                    "CERTIFIED_OPTIMAL_PAIR"
                    if certified
                    else "UNRESOLVED_ENDPOINT_PAIR"
                ),
                "lower": lower["value"] if certified else None,
                "upper": upper["value"] if certified else None,
                "width": (
                    upper["value"] - lower["value"]
                    if certified
                    and lower["value"] is not None
                    and upper["value"] is not None
                    else None
                ),
                "lower_status": lower["status"],
                "upper_status": upper["status"],
                "lower_mip_gap": lower["mip_gap"],
                "upper_mip_gap": upper["mip_gap"],
                "lower_replay": lower["replay"],
                "upper_replay": upper["replay"],
            }
        )
    return {
        "capacity": capacity,
        "status": "CERTIFIED_COMMON_SUPPORT_FEASIBILITY",
        "feasibility_status": feasibility["status"],
        "feasibility_mip_gap": feasibility["mip_gap"],
        "feasibility_replay": feasibility["replay"],
        "outcomes": outcomes,
        "variable_count": program.matrix.shape[1],
        "constraint_count": program.matrix.shape[0],
    }


def outcome_map(cell: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["query"]: row for row in cell.get("outcomes", [])}


def capacity_audit(cells: Sequence[dict[str, Any]]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    comparisons = 0
    by_capacity = {int(cell["capacity"]): cell for cell in cells}
    for query in (
        "mean_selected_buffer_miles_at_common_support",
        "mean_selected_buffer_trip_minutes_at_common_support",
    ):
        previous: dict[str, Any] | None = None
        for capacity in CAPACITIES:
            row = outcome_map(by_capacity[capacity]).get(query)
            if row is None or row.get("status") != "CERTIFIED_OPTIMAL_PAIR":
                previous = None
                continue
            if previous is not None:
                comparisons += 1
                if row["lower"] > previous["lower"] + TOL:
                    problems.append(
                        {
                            "reason": "lower_increased_with_capacity",
                            "query": query,
                            "capacity": capacity,
                        }
                    )
                if row["upper"] < previous["upper"] - TOL:
                    problems.append(
                        {
                            "reason": "upper_decreased_with_capacity",
                            "query": query,
                            "capacity": capacity,
                        }
                    )
            previous = row
    return {
        "status": "PASS" if comparisons and not problems else "FAIL",
        "comparisons": comparisons,
        "problems": problems,
    }


def time_nesting_audit(
    cells_by_time: dict[str, Sequence[dict[str, Any]]],
) -> dict[str, Any]:
    exact = {
        int(cell["capacity"]): cell
        for cell in cells_by_time["exact_singleton"]
    }
    coarse = {
        int(cell["capacity"]): cell
        for cell in cells_by_time["rounded_15m_existential"]
    }
    problems: list[dict[str, Any]] = []
    comparisons = 0
    for capacity in CAPACITIES:
        exact_outcomes = outcome_map(exact[capacity])
        coarse_outcomes = outcome_map(coarse[capacity])
        for query in (
            "mean_selected_buffer_miles_at_common_support",
            "mean_selected_buffer_trip_minutes_at_common_support",
        ):
            exact_row = exact_outcomes.get(query)
            coarse_row = coarse_outcomes.get(query)
            if (
                exact_row is None
                or coarse_row is None
                or exact_row.get("status") != "CERTIFIED_OPTIMAL_PAIR"
                or coarse_row.get("status") != "CERTIFIED_OPTIMAL_PAIR"
            ):
                continue
            comparisons += 1
            if coarse_row["lower"] > exact_row["lower"] + TOL:
                problems.append(
                    {
                        "reason": "coarse_lower_exceeds_exact_lower",
                        "capacity": capacity,
                        "query": query,
                        "exact": exact_row["lower"],
                        "coarse": coarse_row["lower"],
                    }
                )
            if coarse_row["upper"] < exact_row["upper"] - TOL:
                problems.append(
                    {
                        "reason": "coarse_upper_below_exact_upper",
                        "capacity": capacity,
                        "query": query,
                        "exact": exact_row["upper"],
                        "coarse": coarse_row["upper"],
                    }
                )
    return {
        "status": "PASS" if comparisons and not problems else "FAIL",
        "comparisons": comparisons,
        "problems": problems,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    after = base.snapshot()
    if before != after:
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
    reduced = reduced_cohort(
        trips,
        args.existential_core,
        args.existential_buffers,
    )
    common_buffer_float = args.common_buffers_per_core * args.existential_core
    common_buffer_count = int(round(common_buffer_float))
    if abs(common_buffer_float - common_buffer_count) > TOL:
        raise base.LiveDataError(
            "common buffers/core times core count must be an integer"
        )
    if common_buffer_count <= 0:
        raise base.LiveDataError("common selected-buffer count must be positive")

    origin = support_origin(reduced)
    supports = {
        time_model: support_rows(reduced, time_model, origin)
        for time_model in TIME_MODELS
    }
    containment = support_containment_audit(
        supports["exact_singleton"],
        supports["rounded_15m_existential"],
    )
    if containment["status"] != "PASS":
        raise base.LiveDataError(f"support containment failed: {containment}")

    cells_by_time = {
        time_model: [
            solve_cell(
                supports[time_model],
                capacity,
                common_buffer_count,
                args.overlap_epsilon_seconds,
                args.solver_time_limit,
            )
            for capacity in CAPACITIES
        ]
        for time_model in TIME_MODELS
    }
    capacity_audits = {
        time_model: capacity_audit(cells)
        for time_model, cells in cells_by_time.items()
    }
    time_audit = time_nesting_audit(cells_by_time)
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
                "outcome_statuses": [row["status"] for row in cell["outcomes"]],
            }
            for time_model, cells in cells_by_time.items()
            for cell in cells
            if cell["status"] != "CERTIFIED_COMMON_SUPPORT_FEASIBILITY"
            or any(
                row["status"] != "CERTIFIED_OPTIMAL_PAIR"
                for row in cell["outcomes"]
            )
        ]
        if unresolved:
            raise base.LiveDataError(
                "not every existential-time cell was certified: "
                + json.dumps(unresolved[:8], sort_keys=True)
            )

    return {
        "report_version": "nyc-hvfhv-ordered-existential-time/v1",
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "snapshot": after,
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
        "cells_by_time": cells_by_time,
        "capacity_audits": capacity_audits,
        "time_nesting_audit": time_audit,
        "estimand": (
            "mean public miles or trip duration among one common number of "
            "selected buffer rows across exact and existential coarse-time worlds"
        ),
        "claim_boundary": {
            "supported": (
                "small-cohort continuous-time feasible-world bounds under a declared "
                "artificial independent rounding-support model"
            ),
            "not_supported": (
                "actual TLC timestamp coarsening, actual co-rider identities, actual "
                "vehicle runs, realized capacity, production matching logic, or a "
                "NYC population estimate"
            ),
        },
        "redaction": {
            "raw_rows_emitted": False,
            "row_identifiers_emitted": False,
            "latent_timestamp_witnesses_emitted": False,
            "aggregate_only": True,
        },
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "# NYC HVFHV existential latent-time completion Gate",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Reduced audit cohort: **{report['cohort']['existential_core_rows']} core** + "
        f"**{report['cohort']['existential_buffer_rows']} candidate buffers**.  ",
        "Common selected support: "
        f"**{report['common_support']['selected_buffer_count']} buffers** "
        f"(**{report['common_support']['selected_buffers_per_core']:.2f}/core**).",
        "",
        "| Time support | C | Outcome | Lower | Upper | Width | Status |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for time_model in TIME_MODELS:
        for cell in report["cells_by_time"][time_model]:
            if not cell["outcomes"]:
                lines.append(
                    f"| {time_model} | {cell['capacity']} | — | — | — | — | "
                    f"`{cell['status']}` |"
                )
                continue
            for row in cell["outcomes"]:
                lower = "—" if row["lower"] is None else f"{row['lower']:.4f}"
                upper = "—" if row["upper"] is None else f"{row['upper']:.4f}"
                width = "—" if row["width"] is None else f"{row['width']:.4f}"
                lines.append(
                    f"| {time_model} | {cell['capacity']} | {row['query']} | "
                    f"{lower} | {upper} | {width} | `{row['status']}` |"
                )
    lines.extend(
        [
            "",
            "Support containment: "
            f"`{report['time_support']['support_containment_audit']['status']}`.  ",
            "Capacity audits: "
            + ", ".join(
                f"`{time_model}={report['capacity_audits'][time_model]['status']}`"
                for time_model in TIME_MODELS
            )
            + ".  ",
            "Exact-to-coarse existential nesting: "
            f"`{report['time_nesting_audit']['status']}` over "
            f"**{report['time_nesting_audit']['comparisons']}** certified comparisons.",
            "",
            "Unlike outer-envelope substitution, this model imposes connectivity and "
            "capacity on one selected latent timestamp completion. Exact singleton "
            "worlds are therefore contained in the artificial coarse-support worlds.",
            "",
            "These are conditional feasible-world bounds, not reconstructed NYC "
            "co-riders or realized vehicle runs.",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(report: dict[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for time_model in TIME_MODELS:
        for cell in report["cells_by_time"][time_model]:
            for row in cell["outcomes"]:
                rows.append(
                    {
                        "time_model": time_model,
                        "capacity": cell["capacity"],
                        "cell_status": cell["status"],
                        **{
                            key: value
                            for key, value in row.items()
                            if key not in {"lower_replay", "upper_replay"}
                        },
                    }
                )
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def self_test() -> None:
    base_time = datetime(2023, 1, 1, 12, 0)
    trips = [
        Trip(0, "HV0003", "core", base_time, base_time + timedelta(minutes=4), "1", "2", 1.0, 240.0, 10.0, 7.0),
        Trip(1, "HV0003", "core", base_time + timedelta(minutes=3), base_time + timedelta(minutes=6), "1", "2", 2.0, 180.0, 11.0, 8.0),
        Trip(2, "HV0003", "buffer", base_time, base_time + timedelta(minutes=2), "1", "2", 1.0, 120.0, 9.0, 6.0),
        Trip(3, "HV0003", "buffer", base_time + timedelta(minutes=7), base_time + timedelta(minutes=8), "1", "2", 10.0, 60.0, 20.0, 15.0),
    ]
    origin = support_origin(trips)
    exact = support_rows(trips, "exact_singleton", origin)
    coarse = support_rows(trips, "rounded_15m_existential", origin)
    containment = support_containment_audit(exact, coarse)
    assert containment["status"] == "PASS", containment
    cells = {
        "exact_singleton": [solve_cell(exact, 2, 1, 1.0, 10.0)],
        "rounded_15m_existential": [solve_cell(coarse, 2, 1, 1.0, 10.0)],
    }
    exact_row = outcome_map(cells["exact_singleton"][0])[
        "mean_selected_buffer_miles_at_common_support"
    ]
    coarse_row = outcome_map(cells["rounded_15m_existential"][0])[
        "mean_selected_buffer_miles_at_common_support"
    ]
    assert exact_row["status"] == coarse_row["status"] == "CERTIFIED_OPTIMAL_PAIR"
    assert coarse_row["lower"] <= exact_row["lower"] + TOL
    assert coarse_row["upper"] >= exact_row["upper"] - TOL
    print("NYC existential latent-time Gate self-test: PASS")


def parser() -> argparse.ArgumentParser:
    argument_parser = base.parser()
    argument_parser.description = __doc__
    argument_parser.set_defaults(
        output_dir=Path("tmp/nyc-hvfhv-existential-time"),
        ordered_core=4,
    )
    argument_parser.add_argument("--existential-core", type=int, default=4)
    argument_parser.add_argument("--existential-buffers", type=int, default=12)
    argument_parser.add_argument(
        "--common-buffers-per-core",
        type=float,
        default=1.0,
    )
    argument_parser.add_argument(
        "--overlap-epsilon-seconds",
        type=float,
        default=1.0,
    )
    argument_parser.add_argument(
        "--require-all-certified",
        action="store_true",
    )
    return argument_parser


def validate(args: argparse.Namespace) -> None:
    base.validate(args)
    if args.existential_core < 2:
        raise SystemExit("existential core must be at least two")
    if args.existential_buffers < 1:
        raise SystemExit("existential buffers must be positive")
    if args.common_buffers_per_core <= 0:
        raise SystemExit("common buffers/core must be positive")
    if args.overlap_epsilon_seconds <= 0:
        raise SystemExit("overlap epsilon must be positive")


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    validate(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        render(report),
        encoding="utf-8",
    )
    write_csv(report, args.output_dir / "existential_time_bounds.csv")
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
