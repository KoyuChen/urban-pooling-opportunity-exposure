#!/usr/bin/env python3
"""Bounded real-data smoke test for hidden-relation mobility markets.

The script queries two official public releases:

* Chicago TNP trips (2025+), restricted to rows reporting an actual shared
  match with ``trips_pooled = 2``; and
* NYC 2019 High Volume FHV trips, restricted to rows reporting an actual
  shared match.

It verifies live schema and API access, profiles real trip records, forms
small public-information candidate graphs, and computes exact feasible-world
endpoints for semantic trip queries.  It does *not* reconstruct co-rider
identity or claim pair-level coverage: neither public release exposes the
hidden partner key.

Only aggregate summaries and de-identified small-market fixtures are written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

USER_AGENT = "urban-pooling-real-data-smoke/0.1"


@dataclass(frozen=True)
class CityConfig:
    slug: str
    name: str
    domain: str
    dataset_id: str
    dataset_label: str
    start: str
    end: str
    start_field: str
    end_field: str
    pickup_zone_field: str
    dropoff_zone_field: str
    miles_field: str
    duration_field: str
    fare_field: str
    fields: tuple[str, ...]
    predicate: str
    order_by: str
    released_time_bin_minutes: int
    overlap_padding_minutes: int
    pair_size_observed: bool
    interpretation: str


CHICAGO = CityConfig(
    slug="chicago",
    name="Chicago",
    domain="https://data.cityofchicago.org",
    dataset_id="6dvr-xwnh",
    dataset_label="Transportation Network Providers - Trips (2025-)",
    start="2026-01-13T17:00:00.000",
    end="2026-01-13T21:00:00.000",
    start_field="trip_start_timestamp",
    end_field="trip_end_timestamp",
    pickup_zone_field="pickup_community_area",
    dropoff_zone_field="dropoff_community_area",
    miles_field="trip_miles",
    duration_field="trip_seconds",
    fare_field="fare",
    fields=(
        "trip_id",
        "trip_start_timestamp",
        "trip_end_timestamp",
        "trip_seconds",
        "trip_miles",
        "pickup_community_area",
        "dropoff_community_area",
        "fare",
        "shared_trip_authorized",
        "shared_trip_match",
        "trips_pooled",
    ),
    predicate="shared_trip_match = true AND trips_pooled = 2",
    order_by="trip_start_timestamp, trip_id",
    released_time_bin_minutes=15,
    overlap_padding_minutes=15,
    pair_size_observed=True,
    interpretation=(
        "Rows report an actual shared match and exactly two customer trips in "
        "the pooled run, while the public release omits the partner key."
    ),
)

NYC = CityConfig(
    slug="nyc",
    name="New York City",
    domain="https://data.cityofnewyork.us",
    dataset_id="4p5c-cbgn",
    dataset_label="2019 High Volume FHV Trip Records",
    start="2019-06-07T17:00:00.000",
    end="2019-06-07T21:00:00.000",
    start_field="pickup_datetime",
    end_field="dropoff_datetime",
    pickup_zone_field="pulocationid",
    dropoff_zone_field="dolocationid",
    miles_field="trip_miles",
    duration_field="trip_time",
    fare_field="base_passenger_fare",
    fields=(
        "hvfhs_license_num",
        "dispatching_base_num",
        "pickup_datetime",
        "dropoff_datetime",
        "pulocationid",
        "dolocationid",
        "trip_miles",
        "trip_time",
        "base_passenger_fare",
        "shared_request_flag",
        "shared_match_flag",
    ),
    predicate="shared_match_flag = 'Y'",
    order_by="pickup_datetime, dispatching_base_num",
    released_time_bin_minutes=15,
    overlap_padding_minutes=2,
    pair_size_observed=False,
    interpretation=(
        "Rows report an actual shared ride, but the release provides neither a "
        "pooled-run cardinality nor a partner key. NYC is therefore a real-"
        "covariate topology/query diagnostic, not a one-to-one truth benchmark."
    ),
)


@dataclass(frozen=True)
class Trip:
    node_id: str
    start: datetime
    end: datetime
    pickup_zone: str
    dropoff_zone: str
    miles: float
    duration_seconds: float
    fare: float


@dataclass(frozen=True)
class Endpoint:
    perfect_matching_count: int
    minimum: float | None
    maximum: float | None


class LiveFetchError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def open_json(url: str, *, attempts: int = 4, timeout: int = 120) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    request = urllib.request.Request(url, headers=headers)
    errors: list[str] = []
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:  # pragma: no cover - live network
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise LiveFetchError(f"failed to fetch {url}: " + " | ".join(errors))


def metadata_url(config: CityConfig) -> str:
    return f"{config.domain}/api/views/{config.dataset_id}.json"


def soda2_url(config: CityConfig, query: str) -> str:
    return (
        f"{config.domain}/resource/{config.dataset_id}.json?"
        + urllib.parse.urlencode({"$query": query})
    )


def soda3_url(config: CityConfig, query: str, page_size: int) -> str:
    return (
        f"{config.domain}/api/v3/views/{config.dataset_id}/query.json?"
        + urllib.parse.urlencode(
            {"query": query, "pageNumber": 1, "pageSize": page_size}
        )
    )


def query_live(
    config: CityConfig, query: str, *, page_size: int
) -> tuple[list[dict[str, Any]], str]:
    errors: list[str] = []
    for api, url in (
        ("soda2", soda2_url(config, query)),
        ("soda3", soda3_url(config, query, page_size)),
    ):
        try:
            payload = open_json(url)
            if not isinstance(payload, list) or not all(
                isinstance(row, dict) for row in payload
            ):
                raise LiveFetchError(
                    f"{api} returned {type(payload).__name__}, expected row list"
                )
            return payload, api
        except Exception as exc:  # pragma: no cover - live network
            errors.append(f"{api}: {type(exc).__name__}: {exc}")
    raise LiveFetchError("both Socrata query APIs failed: " + " || ".join(errors))


def inspect_schema(config: CityConfig, metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict) or metadata.get("id") != config.dataset_id:
        raise ValueError("metadata object or dataset id is invalid")
    raw_columns = metadata.get("columns")
    if not isinstance(raw_columns, list):
        raise ValueError("metadata has no columns list")
    columns: list[dict[str, Any]] = []
    for column in raw_columns:
        if not isinstance(column, dict) or not column.get("fieldName"):
            continue
        columns.append(
            {
                "field_name": column["fieldName"],
                "data_type": column.get("dataTypeName"),
                "position": column.get("position"),
            }
        )
    names = {column["field_name"] for column in columns}
    missing = sorted(set(config.fields) - names)
    if missing:
        raise ValueError(f"required public fields are absent: {missing}")
    partner_candidates = sorted(
        names
        & {
            "shared_trip_id",
            "shared_ride_id",
            "pooled_trip_id",
            "pool_id",
            "partner_id",
            "co_rider_id",
            "corider_id",
        }
    )
    return {
        "dataset_name": metadata.get("name"),
        "rows_updated_at": metadata.get("rowsUpdatedAt"),
        "view_last_modified": metadata.get("viewLastModified"),
        "schema_sha256": sha256_json(columns),
        "field_count": len(names),
        "required_fields_present": True,
        "partner_key_candidates_present": partner_candidates,
    }


def where_clause(config: CityConfig) -> str:
    return (
        f"{config.start_field} >= '{config.start}' "
        f"AND {config.start_field} < '{config.end}' "
        f"AND {config.predicate}"
    )


def count_query(config: CityConfig) -> str:
    return f"SELECT count(*) AS n WHERE {where_clause(config)}"


def sample_query(config: CityConfig, max_rows: int) -> str:
    return (
        f"SELECT {', '.join(config.fields)} WHERE {where_clause(config)} "
        f"ORDER BY {config.order_by} LIMIT {max_rows}"
    )


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def deidentified_node_id(config: CityConfig, row: Mapping[str, Any], ordinal: int) -> str:
    if config.slug == "chicago" and row.get("trip_id"):
        source = str(row["trip_id"])
    else:
        source = canonical_json([row.get(field) for field in config.fields]).decode(
            "utf-8"
        ) + f"|{ordinal}"
    digest = hashlib.sha256(f"{config.slug}|{source}".encode("utf-8")).hexdigest()
    return f"{config.slug}-{digest[:16]}"


def normalize(
    config: CityConfig, rows: Sequence[Mapping[str, Any]]
) -> tuple[list[Trip], dict[str, Any]]:
    missing = Counter()
    usable: list[Trip] = []
    invalid_interval = 0
    seen: set[str] = set()
    duplicate_ids = 0
    for ordinal, row in enumerate(rows):
        for field in config.fields:
            if row.get(field) in (None, ""):
                missing[field] += 1
        start = parse_datetime(row.get(config.start_field))
        end = parse_datetime(row.get(config.end_field))
        pickup = str(row.get(config.pickup_zone_field, "")).strip()
        dropoff = str(row.get(config.dropoff_zone_field, "")).strip()
        miles = finite_float(row.get(config.miles_field))
        duration = finite_float(row.get(config.duration_field))
        fare = finite_float(row.get(config.fare_field))
        node_id = deidentified_node_id(config, row, ordinal)
        if node_id in seen:
            duplicate_ids += 1
        seen.add(node_id)
        if start is None or end is None or end < start:
            invalid_interval += 1
            continue
        if not pickup or not dropoff or None in (miles, duration, fare):
            continue
        usable.append(
            Trip(
                node_id=node_id,
                start=start,
                end=end,
                pickup_zone=pickup,
                dropoff_zone=dropoff,
                miles=float(miles),
                duration_seconds=float(duration),
                fare=float(fare),
            )
        )
    n = len(rows)
    return usable, {
        "raw_rows": n,
        "usable_rows": len(usable),
        "usable_rate": len(usable) / n if n else None,
        "invalid_intervals": invalid_interval,
        "duplicate_deidentified_ids": duplicate_ids,
        "missingness": {
            field: {
                "rows": missing[field],
                "rate": missing[field] / n if n else None,
            }
            for field in config.fields
        },
    }


def floor_time(value: datetime, minutes: int) -> datetime:
    return value.replace(
        minute=value.minute - value.minute % minutes, second=0, microsecond=0
    )


def group_markets(
    config: CityConfig, trips: Sequence[Trip]
) -> dict[str, list[Trip]]:
    groups: dict[str, list[Trip]] = defaultdict(list)
    for trip in trips:
        key = floor_time(trip.start, config.released_time_bin_minutes).isoformat()
        groups[key].append(trip)
    for group in groups.values():
        group.sort(key=lambda trip: (trip.start, trip.end, trip.node_id))
    return dict(groups)


def quantile(values: Sequence[int], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    lo, hi = math.floor(position), math.ceil(position)
    if lo == hi:
        return float(ordered[lo])
    return ordered[lo] + (position - lo) * (ordered[hi] - ordered[lo])


def overlap(left: Trip, right: Trip, padding_minutes: int) -> bool:
    padding = timedelta(minutes=padding_minutes)
    return left.start <= right.end + padding and right.start <= left.end + padding


def candidate_edges(
    trips: Sequence[Trip], *, padding_minutes: int, heuristic: bool
) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for i, j in combinations(range(len(trips)), 2):
        left, right = trips[i], trips[j]
        if not overlap(left, right, padding_minutes):
            continue
        if heuristic:
            route_signal = (
                left.pickup_zone == right.pickup_zone
                or left.dropoff_zone == right.dropoff_zone
                or abs(left.miles - right.miles) <= 1.5
            )
            if not route_signal:
                continue
        result.add((i, j))
    return result


def matching_endpoint(
    trips: Sequence[Trip],
    edges: set[tuple[int, int]],
    pair_weight: Callable[[Trip, Trip], float],
) -> Endpoint:
    n = len(trips)
    if n % 2:
        return Endpoint(0, None, None)
    adjacency = [[False] * n for _ in range(n)]
    weights: dict[tuple[int, int], float] = {}
    for i, j in edges:
        a, b = min(i, j), max(i, j)
        adjacency[a][b] = adjacency[b][a] = True
        weights[(a, b)] = float(pair_weight(trips[a], trips[b]))

    @lru_cache(maxsize=None)
    def solve(mask: int) -> tuple[int, float, float]:
        if mask == 0:
            return 1, 0.0, 0.0
        low_bit = mask & -mask
        i = low_bit.bit_length() - 1
        remainder = mask ^ (1 << i)
        total = 0
        minimum = math.inf
        maximum = -math.inf
        candidates = remainder
        while candidates:
            bit = candidates & -candidates
            j = bit.bit_length() - 1
            candidates ^= bit
            if not adjacency[i][j]:
                continue
            count, child_min, child_max = solve(remainder ^ (1 << j))
            if count == 0:
                continue
            weight = weights[(min(i, j), max(i, j))]
            total += count
            minimum = min(minimum, weight + child_min)
            maximum = max(maximum, weight + child_max)
        return (0, math.inf, -math.inf) if total == 0 else (total, minimum, maximum)

    count, minimum, maximum = solve((1 << n) - 1)
    if count == 0:
        return Endpoint(0, None, None)
    pairs = n / 2
    return Endpoint(count, minimum / pairs, maximum / pairs)


def endpoint_bundle(
    trips: Sequence[Trip], edges: set[tuple[int, int]]
) -> dict[str, dict[str, Any]]:
    queries: dict[str, Callable[[Trip, Trip], float]] = {
        "mean_absolute_trip_miles_gap": lambda a, b: abs(a.miles - b.miles),
        "mean_absolute_duration_gap_minutes": lambda a, b: abs(
            a.duration_seconds - b.duration_seconds
        )
        / 60.0,
        "mean_absolute_fare_gap": lambda a, b: abs(a.fare - b.fare),
        "same_dropoff_zone_fraction": lambda a, b: float(
            a.dropoff_zone == b.dropoff_zone
        ),
    }
    return {
        name: asdict(matching_endpoint(trips, edges, function))
        for name, function in queries.items()
    }


def choose_small_market(
    config: CityConfig,
    groups: Mapping[str, Sequence[Trip]],
    max_nodes: int,
) -> dict[str, Any] | None:
    for key, original in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        n = min(max_nodes, len(original))
        if n % 2:
            n -= 1
        if n < 4:
            continue
        trips = list(original[:n])
        outer = candidate_edges(
            trips, padding_minutes=config.overlap_padding_minutes, heuristic=False
        )
        outer_endpoint = matching_endpoint(trips, outer, lambda _a, _b: 0.0)
        if outer_endpoint.perfect_matching_count == 0:
            continue
        heuristic = candidate_edges(
            trips, padding_minutes=config.overlap_padding_minutes, heuristic=True
        )
        heuristic_count = matching_endpoint(
            trips, heuristic, lambda _a, _b: 0.0
        ).perfect_matching_count
        complete_edge_count = n * (n - 1) // 2
        return {
            "released_start_bin": key,
            "nodes": n,
            "outer_edges": len(outer),
            "outer_density": len(outer) / complete_edge_count,
            "outer_perfect_matching_worlds": outer_endpoint.perfect_matching_count,
            "heuristic_edges": len(heuristic),
            "heuristic_density": len(heuristic) / complete_edge_count,
            "heuristic_perfect_matching_worlds": heuristic_count,
            "outer_query_endpoints": endpoint_bundle(trips, outer),
            "heuristic_query_endpoints": endpoint_bundle(trips, heuristic)
            if heuristic_count
            else None,
            "deidentified_nodes": [
                {
                    "node_id": trip.node_id,
                    "start": trip.start.isoformat(),
                    "end": trip.end.isoformat(),
                    "pickup_zone": trip.pickup_zone,
                    "dropoff_zone": trip.dropoff_zone,
                    "miles": trip.miles,
                    "duration_seconds": trip.duration_seconds,
                    "fare": trip.fare,
                }
                for trip in trips
            ],
            "outer_edge_list": [
                [trips[i].node_id, trips[j].node_id] for i, j in sorted(outer)
            ],
            "heuristic_edge_list": [
                [trips[i].node_id, trips[j].node_id]
                for i, j in sorted(heuristic)
            ],
        }
    return None


def run_city(config: CityConfig, *, max_rows: int, max_nodes: int) -> dict[str, Any]:
    started = time.monotonic()
    schema = inspect_schema(config, open_json(metadata_url(config)))

    cohort_count: int | None = None
    count_api: str | None = None
    count_error: str | None = None
    try:
        rows, count_api = query_live(config, count_query(config), page_size=10)
        if len(rows) != 1 or "n" not in rows[0]:
            raise ValueError(f"unexpected count response: {rows!r}")
        cohort_count = int(rows[0]["n"])
    except Exception as exc:  # count is informative, not a smoke hard gate
        count_error = f"{type(exc).__name__}: {exc}"

    raw_rows, sample_api = query_live(
        config, sample_query(config, max_rows), page_size=max_rows
    )
    if not raw_rows:
        raise ValueError("bounded sample returned no rows")
    trips, quality = normalize(config, raw_rows)
    if len(trips) < 4:
        raise ValueError("fewer than four fully usable rows")
    groups = group_markets(config, trips)
    sizes = [len(group) for group in groups.values()]
    selected = choose_small_market(config, groups, max_nodes)
    if selected is None:
        raise ValueError("no even small market admitted a perfect matching")

    result: dict[str, Any] = {
        "status": "ok",
        "city": config.name,
        "slug": config.slug,
        "dataset": {
            "id": config.dataset_id,
            "label": config.dataset_label,
            "landing_page": f"{config.domain}/d/{config.dataset_id}",
            "start_inclusive": config.start,
            "end_exclusive": config.end,
            "predicate": config.predicate,
            "pair_size_observed": config.pair_size_observed,
            "partner_identity_observed": False,
            "interpretation": config.interpretation,
        },
        "schema": schema,
        "query_audit": {
            "count_soql": count_query(config),
            "count_api": count_api,
            "count_error": count_error,
            "sample_soql": sample_query(config, max_rows),
            "sample_api": sample_api,
        },
        "cohort_rows_in_window": cohort_count,
        "bounded_rows_fetched": len(raw_rows),
        "quality": quality,
        "market_profile": {
            "definition": (
                f"{config.released_time_bin_minutes}-minute released pickup-time bin"
            ),
            "markets": len(groups),
            "max_size": max(sizes),
            "p50_size": quantile(sizes, 0.50),
            "p90_size": quantile(sizes, 0.90),
            "p99_size": quantile(sizes, 0.99),
            "top_sizes": sorted(sizes, reverse=True)[:20],
        },
        "selected_market": selected,
        "scientific_status": (
            "real-record pair-size-known feasible-world smoke"
            if config.pair_size_observed
            else "real-record shared-ride topology/query diagnostic"
        ),
        "elapsed_seconds": time.monotonic() - started,
    }
    result["result_sha256"] = sha256_json(result)
    return result


def render_report(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Real mobility data smoke test",
        "",
        f"Generated UTC: `{summary['generated_at_utc']}`",
        "",
        "This bounded test verifies live public-data access, schema, real-record",
        "market construction, and exact semantic-query endpoints. It does not",
        "reconstruct partners or evaluate conformal coverage against hidden truth.",
        "",
        "## Summary",
        "",
        "| City | Status | Window cohort | Fetched | Usable | Markets | Max bin | Pair size known | Exact outer worlds |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for city in summary["cities"]:
        if city["status"] != "ok":
            lines.append(f"| {city['city']} | FAIL | — | — | — | — | — | — | — |")
            continue
        selected = city["selected_market"]
        count = city["cohort_rows_in_window"]
        count_text = "—" if count is None else f"{count:,}"
        lines.append(
            f"| {city['city']} | PASS | {count_text} | "
            f"{city['bounded_rows_fetched']:,} | {city['quality']['usable_rows']:,} | "
            f"{city['market_profile']['markets']:,} | {city['market_profile']['max_size']:,} | "
            f"{'yes' if city['dataset']['pair_size_observed'] else 'no'} | "
            f"{selected['outer_perfect_matching_worlds']:,} |"
        )

    lines.extend(["", "## Details", ""])
    for city in summary["cities"]:
        lines.extend([f"### {city['city']}", ""])
        if city["status"] != "ok":
            lines.extend([f"**FAIL:** `{city['error']}`", ""])
            continue
        lines.extend(
            [
                f"- Dataset `{city['dataset']['id']}`: {city['dataset']['label']}.",
                f"- Required schema fields present: `{city['schema']['required_fields_present']}`; "
                f"public partner-key candidates: `{city['schema']['partner_key_candidates_present']}`.",
                f"- Scientific status: **{city['scientific_status']}**.",
                f"- Interpretation: {city['dataset']['interpretation']}",
                f"- Selected market: {city['selected_market']['nodes']} nodes, "
                f"{city['selected_market']['outer_edges']} outer edges, "
                f"{city['selected_market']['outer_perfect_matching_worlds']:,} exact worlds.",
                "",
                "| Semantic query | Exact outer minimum | Exact outer maximum |",
                "|---|---:|---:|",
            ]
        )
        for query, endpoint in city["selected_market"]["outer_query_endpoints"].items():
            lo = endpoint["minimum"]
            hi = endpoint["maximum"]
            lines.append(
                f"| `{query}` | {'—' if lo is None else f'{lo:.6g}'} | "
                f"{'—' if hi is None else f'{hi:.6g}'} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation gate",
            "",
            "Chicago can support a real-record, pair-size-known feasible-world",
            "experiment because `trips_pooled = 2` is released. The smoke test",
            "does not prove candidate recall, run closure, or coverage because the",
            "shared-trip identifier is not public. NYC remains a useful cross-city",
            "real-covariate diagnostic, but its public shared-match flag alone does",
            "not identify one-to-one pooling worlds.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "python code/ai_pilot/data_pipeline/real_city_smoke.py \\",
            "  --output-dir tmp/real-city-smoke --max-rows 5000 --require-all",
            "```",
            "",
            f"Summary SHA-256: `{summary['summary_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(summary: Mapping[str, Any], path: Path) -> None:
    columns = [
        "city",
        "status",
        "dataset_id",
        "cohort_rows",
        "fetched_rows",
        "usable_rows",
        "markets",
        "max_market_size",
        "pair_size_observed",
        "selected_nodes",
        "outer_edges",
        "outer_worlds",
        "elapsed_seconds",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for city in summary["cities"]:
            if city["status"] != "ok":
                writer.writerow({"city": city["city"], "status": "failed"})
                continue
            selected = city["selected_market"]
            writer.writerow(
                {
                    "city": city["city"],
                    "status": "ok",
                    "dataset_id": city["dataset"]["id"],
                    "cohort_rows": city["cohort_rows_in_window"],
                    "fetched_rows": city["bounded_rows_fetched"],
                    "usable_rows": city["quality"]["usable_rows"],
                    "markets": city["market_profile"]["markets"],
                    "max_market_size": city["market_profile"]["max_size"],
                    "pair_size_observed": city["dataset"]["pair_size_observed"],
                    "selected_nodes": selected["nodes"],
                    "outer_edges": selected["outer_edges"],
                    "outer_worlds": selected["outer_perfect_matching_worlds"],
                    "elapsed_seconds": city["elapsed_seconds"],
                }
            )


def self_test() -> None:
    now = datetime(2026, 1, 1, 12, 0)
    trips = [
        Trip(
            node_id=f"n{i}",
            start=now + timedelta(minutes=i),
            end=now + timedelta(minutes=20 + i),
            pickup_zone="1",
            dropoff_zone=str(i % 2),
            miles=float(i + 1),
            duration_seconds=float(600 + 60 * i),
            fare=float(10 + i),
        )
        for i in range(4)
    ]
    complete = set(combinations(range(4), 2))
    endpoint = matching_endpoint(trips, complete, lambda a, b: abs(a.miles - b.miles))
    assert endpoint.perfect_matching_count == 3
    assert endpoint.minimum == 1.0
    assert endpoint.maximum == 2.0
    assert matching_endpoint(trips, {(0, 1), (2, 3)}, lambda _a, _b: 0).perfect_matching_count == 1
    assert parse_datetime("2026-01-01T00:00:00.000") is not None
    assert floor_time(now.replace(minute=14), 15).minute == 0
    print("self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/real-city-smoke"))
    parser.add_argument("--max-rows", type=int, default=5000)
    parser.add_argument("--max-market-nodes", type=int, default=12)
    parser.add_argument(
        "--cities", nargs="+", choices=("chicago", "nyc"), default=["chicago", "nyc"]
    )
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not 10 <= args.max_rows <= 50_000:
        parser.error("--max-rows must be between 10 and 50000")
    if not 4 <= args.max_market_nodes <= 18:
        parser.error("--max-market-nodes must be between 4 and 18")

    configs = {"chicago": CHICAGO, "nyc": NYC}
    city_results: list[dict[str, Any]] = []
    for slug in args.cities:
        config = configs[slug]
        try:
            city_results.append(
                run_city(config, max_rows=args.max_rows, max_nodes=args.max_market_nodes)
            )
        except Exception as exc:  # pragma: no cover - live network
            city_results.append(
                {
                    "status": "failed",
                    "city": config.name,
                    "slug": config.slug,
                    "dataset_id": config.dataset_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    summary: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "cities": args.cities,
            "max_rows": args.max_rows,
            "max_market_nodes": args.max_market_nodes,
        },
        "cities": city_results,
    }
    summary["summary_sha256"] = sha256_json(summary)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REAL_DATA_SMOKE_REPORT.md").write_text(
        render_report(summary), encoding="utf-8"
    )
    write_csv(summary, args.output_dir / "city_summary.csv")
    selected = {
        city["slug"]: city.get("selected_market")
        for city in city_results
        if city["status"] == "ok"
    }
    (args.output_dir / "selected_markets.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(render_report(summary))
    failures = [city for city in city_results if city["status"] != "ok"]
    if args.require_all and failures:
        return 1
    if len(failures) == len(city_results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
