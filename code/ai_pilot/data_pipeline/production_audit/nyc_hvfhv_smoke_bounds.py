"""Nested candidate graphs and conditional C=2 query bounds for NYC HVFHV."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, lil_matrix

from nyc_hvfhv_smoke_types import Bound, CERTIFIED, ModelTrip, TIERS


def overlap(left: ModelTrip, right: ModelTrip) -> bool:
    if (
        left.start is None
        or left.end is None
        or right.start is None
        or right.end is None
    ):
        return True
    return left.start <= right.end and right.start <= left.end


def temporal_edges(rows: Sequence[ModelTrip]) -> list[tuple[int, int]]:
    by_index = {row.index: row for row in rows}
    core = [row.index for row in rows if row.role == "core"]
    edges: set[tuple[int, int]] = set()
    for left_index in core:
        for right_index, right in by_index.items():
            if (
                left_index != right_index
                and by_index[left_index].provider == right.provider
                and overlap(by_index[left_index], right)
            ):
                edges.add(
                    (min(left_index, right_index), max(left_index, right_index))
                )
    return sorted(edges)


def compatible(left: ModelTrip, right: ModelTrip, tier: str) -> bool:
    def equal_if_measured(left_value: str | None, right_value: str | None) -> bool:
        return (
            left_value is None
            or right_value is None
            or left_value == right_value
        )

    if tier == "same_od_zone":
        return equal_if_measured(
            left.pickup_zone, right.pickup_zone
        ) and equal_if_measured(left.dropoff_zone, right.dropoff_zone)
    if tier == "same_pickup_zone":
        return equal_if_measured(left.pickup_zone, right.pickup_zone)
    if tier == "provider_time_only":
        return True
    raise ValueError(tier)


def tier_edges(
    rows: Sequence[ModelTrip],
    edges: Sequence[tuple[int, int]],
    tier: str,
) -> list[tuple[int, int]]:
    by_index = {row.index: row for row in rows}
    return [
        edge
        for edge in edges
        if compatible(by_index[edge[0]], by_index[edge[1]], tier)
    ]


def graph_stats(
    rows: Sequence[ModelTrip],
    edges: Sequence[tuple[int, int]],
) -> dict[str, Any]:
    core = [row.index for row in rows if row.role == "core"]
    degree = Counter({index: 0 for index in core})
    for left, right in edges:
        degree[left] += 1
        degree[right] += 1
    values = [degree[index] for index in core]
    return {
        "core_count": len(core),
        "edge_count": len(edges),
        "core_zero_degree_count": sum(value == 0 for value in values),
        "core_min_degree": min(values) if values else None,
        "core_max_degree": max(values) if values else None,
    }


def matrix(
    rows: Sequence[ModelTrip],
    edges: Sequence[tuple[int, int]],
) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
    core = [row.index for row in rows if row.role == "core"]
    buffer = [row.index for row in rows if row.role == "buffer"]
    nodes = [*core, *buffer]
    positions = {node: index for index, node in enumerate(nodes)}
    incidence = lil_matrix((len(nodes), len(edges)), dtype=float)
    for column, (left, right) in enumerate(edges):
        incidence[positions[left], column] = 1
        incidence[positions[right], column] = 1
    lower = np.asarray(
        [1.0] * len(core) + [0.0] * len(buffer),
        dtype=float,
    )
    upper = np.ones(len(nodes))
    return incidence.tocsr(), lower, upper


def solve(
    rows: Sequence[ModelTrip],
    edges: Sequence[tuple[int, int]],
    coefficients: Sequence[float],
    maximize: bool,
    limit: float,
) -> Bound:
    stats = graph_stats(rows, edges)
    if stats["core_zero_degree_count"]:
        return Bound("PROVEN_INFEASIBLE_ISOLATED_CORE", None, None, None)
    if len(coefficients) != len(edges):
        raise ValueError("coefficient length mismatch")
    incidence, lower, upper = matrix(rows, edges)
    objective = np.asarray(coefficients, dtype=float)
    result = milp(
        c=-objective if maximize else objective,
        integrality=np.ones(len(edges), dtype=int),
        bounds=Bounds(np.zeros(len(edges)), np.ones(len(edges))),
        constraints=LinearConstraint(incidence, lower, upper),
        options={"time_limit": limit, "presolve": True},
    )
    gap = (
        float(result.mip_gap)
        if getattr(result, "mip_gap", None) is not None
        else None
    )
    if result.status == 2:
        return Bound("PROVEN_INFEASIBLE_BY_HIGHS", None, gap, None)
    if result.x is None:
        return Bound("UNRESOLVED_NO_INCUMBENT", None, gap, None)
    solution = np.asarray(result.x)
    rounded = np.rint(solution)
    row_sums = np.asarray(incidence @ rounded).reshape(-1)
    residual = max(
        float(np.max(abs(solution - rounded))),
        float(np.max(np.maximum(lower - row_sums, 0))),
        float(np.max(np.maximum(row_sums - upper, 0))),
    )
    if residual > 1e-7:
        return Bound("UNRESOLVED_INVALID_INCUMBENT", None, gap, residual)
    status = CERTIFIED if result.status == 0 else "INCUMBENT_ONLY_UNRESOLVED_LIMIT"
    return Bound(status, float(objective @ rounded), gap, residual)


def queries() -> tuple[
    tuple[
        str,
        str,
        Callable[[ModelTrip, ModelTrip], tuple[float, float] | None],
        str,
    ],
    ...,
]:
    def gap(attribute: str, scale: float = 1.0):
        def coefficient(
            left: ModelTrip,
            right: ModelTrip,
        ) -> tuple[float, float] | None:
            left_value = getattr(left, attribute)
            right_value = getattr(right, attribute)
            if left_value is None or right_value is None:
                return None
            value = abs(float(left_value) - float(right_value)) / scale
            return value, value

        return coefficient

    def same_zone(left: ModelTrip, right: ModelTrip) -> tuple[float, float]:
        if left.dropoff_zone is None or right.dropoff_zone is None:
            return 0.0, 1.0
        value = float(left.dropoff_zone == right.dropoff_zone)
        return value, value

    return (
        (
            "mean_absolute_trip_miles_gap_per_core",
            "miles",
            gap("miles"),
            "missing miles makes endpoint unresolved",
        ),
        (
            "mean_absolute_trip_time_gap_per_core",
            "minutes",
            gap("seconds", 60.0),
            "missing trip time makes endpoint unresolved",
        ),
        (
            "same_dropoff_zone_fraction_per_core",
            "fraction",
            same_zone,
            "missing zone contributes [0,1]",
        ),
    )


def coefficients(
    rows: Sequence[ModelTrip],
    edges: Sequence[tuple[int, int]],
    coefficient: Callable[[ModelTrip, ModelTrip], tuple[float, float] | None],
) -> tuple[list[float] | None, list[float] | None, int]:
    by_index = {row.index: row for row in rows}
    core = {row.index for row in rows if row.role == "core"}
    denominator = len(core)
    lower: list[float] = []
    upper: list[float] = []
    missing = 0
    for edge in edges:
        interval = coefficient(by_index[edge[0]], by_index[edge[1]])
        if interval is None:
            missing += 1
            continue
        core_incidence = int(edge[0] in core) + int(edge[1] in core)
        lower.append(interval[0] * core_incidence / denominator)
        upper.append(interval[1] * core_incidence / denominator)
    return (None, None, missing) if missing else (lower, upper, 0)


def solve_point(
    rows: Sequence[ModelTrip],
    edges: Sequence[tuple[int, int]],
    resolution: str,
    tier: str,
    rank: int,
    rounded_edges: int,
    limit: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stats = graph_stats(rows, edges)
    cover = solve(rows, edges, [0.0] * len(edges), False, limit)
    point = {
        "time_resolution": resolution,
        "support_tier": tier,
        "support_rank": rank,
        **stats,
        "retained_fraction_of_rounded_temporal": (
            len(edges) / rounded_edges if rounded_edges else 0.0
        ),
        "cover_status": cover.status,
        "cover_mip_gap": cover.mip_gap,
        "capacity_model": "PAIRWISE_C2_BENCHMARK_ONLY",
    }
    output: list[dict[str, Any]] = []
    for name, unit, coefficient, semantics in queries():
        lower_coefficients, upper_coefficients, missing = coefficients(
            rows, edges, coefficient
        )
        if lower_coefficients is None or upper_coefficients is None:
            lower = upper = Bound(
                "UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES",
                None,
                None,
                None,
            )
        else:
            lower = solve(rows, edges, lower_coefficients, False, limit)
            upper = solve(rows, edges, upper_coefficients, True, limit)
        certified = (
            lower.status == upper.status == CERTIFIED
            and lower.value is not None
            and upper.value is not None
            and lower.value <= upper.value + 1e-7
        )
        output.append(
            {
                **point,
                "query": name,
                "unit": unit,
                "lower": lower.value if certified else None,
                "upper": upper.value if certified else None,
                "width": (
                    upper.value - lower.value
                    if certified
                    and lower.value is not None
                    and upper.value is not None
                    else None
                ),
                "endpoint_pair_certification": (
                    "CERTIFIED_OPTIMAL_PAIR" if certified else "UNCERTIFIED"
                ),
                "lower_status": lower.status,
                "upper_status": upper.status,
                "lower_mip_gap": lower.mip_gap,
                "upper_mip_gap": upper.mip_gap,
                "max_replay_residual": (
                    max(
                        value
                        for value in (lower.residual, upper.residual)
                        if value is not None
                    )
                    if any(
                        value is not None
                        for value in (lower.residual, upper.residual)
                    )
                    else None
                ),
                "edges_with_missing_query_values": missing,
                "missing_semantics": semantics,
            }
        )
    return point, output


def audits(
    edge_sets: Mapping[str, Mapping[str, set[tuple[int, int]]]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    tier_names = [tier for tier, _rank in TIERS]
    for resolution, sets in edge_sets.items():
        for left, right in zip(tier_names, tier_names[1:]):
            if not sets[left] <= sets[right]:
                problems.append(
                    {
                        "reason": "zone_support_not_nested",
                        "resolution": resolution,
                        "left": left,
                        "right": right,
                    }
                )
    for tier in tier_names:
        if not edge_sets["exact_second"][tier] <= edge_sets[
            "rounded_15m_outer"
        ][tier]:
            problems.append(
                {"reason": "exact_not_subset_of_rounded", "tier": tier}
            )
    index = {
        (
            str(row["time_resolution"]),
            str(row["support_tier"]),
            str(row["query"]),
        ): row
        for row in rows
    }
    comparisons = 0
    for tier in tier_names:
        for name, _unit, _coefficient, _semantics in queries():
            exact = index[("exact_second", tier, name)]
            rounded = index[("rounded_15m_outer", tier, name)]
            if (
                exact["endpoint_pair_certification"]
                == rounded["endpoint_pair_certification"]
                == "CERTIFIED_OPTIMAL_PAIR"
            ):
                comparisons += 1
                if (
                    rounded["lower"] > exact["lower"] + 1e-7
                    or rounded["upper"] < exact["upper"] - 1e-7
                ):
                    problems.append(
                        {
                            "reason": "rounded_interval_does_not_contain_exact",
                            "tier": tier,
                            "query": name,
                        }
                    )
    chain_available = 0
    infeasible = {
        "PROVEN_INFEASIBLE_ISOLATED_CORE",
        "PROVEN_INFEASIBLE_BY_HIGHS",
    }
    for resolution in ("exact_second", "rounded_15m_outer"):
        for name, _unit, _coefficient, _semantics in queries():
            chain = sorted(
                (
                    row
                    for row in rows
                    if row["time_resolution"] == resolution
                    and row["query"] == name
                ),
                key=lambda row: row["support_rank"],
            )
            previous_lower = previous_upper = None
            seen_feasible = False
            usable = 0
            for row in chain:
                if row["cover_status"] in infeasible:
                    if seen_feasible:
                        problems.append(
                            {
                                "reason": "feasibility_lost_under_relaxation",
                                "resolution": resolution,
                                "query": name,
                                "tier": row["support_tier"],
                            }
                        )
                    continue
                if row["cover_status"] != CERTIFIED:
                    problems.append(
                        {
                            "reason": "unresolved_cover",
                            "resolution": resolution,
                            "query": name,
                            "tier": row["support_tier"],
                        }
                    )
                    continue
                seen_feasible = True
                if row["endpoint_pair_certification"] != "CERTIFIED_OPTIMAL_PAIR":
                    continue
                usable += 1
                if (
                    previous_lower is not None
                    and row["lower"] > previous_lower + 1e-7
                ):
                    problems.append(
                        {
                            "reason": "lower_increased_under_relaxation",
                            "resolution": resolution,
                            "query": name,
                        }
                    )
                if (
                    previous_upper is not None
                    and row["upper"] < previous_upper - 1e-7
                ):
                    problems.append(
                        {
                            "reason": "upper_decreased_under_relaxation",
                            "resolution": resolution,
                            "query": name,
                        }
                    )
                previous_lower = row["lower"]
                previous_upper = row["upper"]
            if usable:
                chain_available += 1
    return {
        "status": "PASS" if not problems and chain_available else "FAIL",
        "problem_count": len(problems),
        "problems": problems,
        "certified_exact_rounded_comparisons": comparisons,
        "available_query_chains": chain_available,
    }
