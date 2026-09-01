#!/usr/bin/env python3
"""Bounded Chicago/NYC real-data smoke test.

Checks official public schemas, downloads rows reporting an actual shared ride,
forms *illustrative* candidate graphs from released timestamps/zones, and
computes exact semantic-query endpoints on one small market. It does not
reconstruct co-rider identity, certify candidate recall, or validate conformal
coverage against hidden truth.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, sys, time
import urllib.parse, urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

@dataclass(frozen=True)
class Config:
    slug: str; name: str; domain: str; dataset_id: str; dataset_name: str
    start: str; end: str; start_field: str; end_field: str
    pickup_field: str; dropoff_field: str; miles_field: str
    duration_field: str; fare_field: str; fields: tuple[str, ...]
    predicate: str; order_by: str; padding_minutes: int
    pair_size_known: bool; interpretation: str

CHICAGO = Config(
    "chicago", "Chicago", "https://data.cityofchicago.org", "6dvr-xwnh",
    "Transportation Network Providers - Trips (2025-)",
    "2026-01-13T17:00:00.000", "2026-01-13T21:00:00.000",
    "trip_start_timestamp", "trip_end_timestamp",
    "pickup_community_area", "dropoff_community_area", "trip_miles",
    "trip_seconds", "fare",
    ("trip_id", "trip_start_timestamp", "trip_end_timestamp", "trip_seconds",
     "trip_miles", "pickup_community_area", "dropoff_community_area", "fare",
     "shared_trip_authorized", "shared_trip_match", "trips_pooled"),
    "shared_trip_match = true AND trips_pooled = 2",
    "trip_start_timestamp, trip_id", 15, True,
    "The public row reports an actual shared match and a two-customer run, "
    "but omits the Shared Trip ID that would reveal the partner.",
)
NYC = Config(
    "nyc", "New York City", "https://data.cityofnewyork.us", "u253-aew4",
    "2023 High Volume FHV Trip Data",
    "2023-06-07T17:00:00.000", "2023-06-07T21:00:00.000",
    "pickup_datetime", "dropoff_datetime", "pulocationid", "dolocationid",
    "trip_miles", "trip_time", "base_passenger_fare",
    ("hvfhs_license_num", "dispatching_base_num", "pickup_datetime",
     "dropoff_datetime", "pulocationid", "dolocationid", "trip_miles",
     "trip_time", "base_passenger_fare", "shared_request_flag",
     "shared_match_flag"),
    "shared_match_flag = 'Y'", "pickup_datetime, dispatching_base_num", 2, False,
    "The public row reports sharing with another separately booked passenger, "
    "but does not release pool size or partner identity.",
)

@dataclass(frozen=True)
class Trip:
    node_id: str; start: datetime; end: datetime; pickup: str; dropoff: str
    miles: float; duration_seconds: float; fare: float

class LiveFetchError(RuntimeError): pass

def sha256_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()

def fetch_json(url: str, attempts: int = 4, timeout: int = 120) -> Any:
    headers = {"User-Agent": "urban-pooling-real-data-smoke/0.4"}
    if os.environ.get("SOCRATA_APP_TOKEN"):
        headers["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]
    errors = []
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:  # pragma: no cover - live network
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt + 1 < attempts: time.sleep(2**attempt)
    raise LiveFetchError(" | ".join(errors))

def metadata_url(c: Config) -> str:
    return f"{c.domain}/api/views/{c.dataset_id}.json"

def resource_url(c: Config, query: str) -> str:
    return f"{c.domain}/resource/{c.dataset_id}.json?" + urllib.parse.urlencode({"$query": query})

def where(c: Config) -> str:
    return f"{c.start_field} >= '{c.start}' AND {c.start_field} < '{c.end}' AND {c.predicate}"

def sample_query(c: Config, limit: int) -> str:
    return f"SELECT {', '.join(c.fields)} WHERE {where(c)} ORDER BY {c.order_by} LIMIT {limit}"

def count_query(c: Config) -> str:
    return f"SELECT count(*) AS n WHERE {where(c)}"

def inspect_schema(c: Config, metadata: Mapping[str, Any]) -> dict[str, Any]:
    if metadata.get("id") != c.dataset_id: raise ValueError("dataset id mismatch")
    columns = metadata.get("columns")
    if not isinstance(columns, list): raise ValueError("missing columns metadata")
    names = {x.get("fieldName") for x in columns if isinstance(x, Mapping) and x.get("fieldName")}
    missing = sorted(set(c.fields) - names)
    if missing: raise ValueError(f"required fields absent: {missing}")
    partner_keys = {"shared_trip_id", "shared_ride_id", "pooled_trip_id", "pool_id", "partner_id", "co_rider_id"}
    return {"required_fields_present": True, "field_count": len(names),
            "partner_key_candidates_present": sorted(names & partner_keys),
            "rows_updated_at": metadata.get("rowsUpdatedAt"),
            "view_last_modified": metadata.get("viewLastModified")}

def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value: return None
    try: result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError: return None
    return result.astimezone(timezone.utc).replace(tzinfo=None) if result.tzinfo else result

def finite_float(value: Any) -> float | None:
    try: number = float(value)
    except (TypeError, ValueError): return None
    return number if math.isfinite(number) else None

def deidentified_id(c: Config, row: Mapping[str, Any], index: int) -> str:
    source = str(row["trip_id"]) if c.slug == "chicago" and row.get("trip_id") else json.dumps([row.get(f) for f in c.fields]) + f"|{index}"
    return f"{c.slug}-" + hashlib.sha256(f"{c.slug}|{source}".encode()).hexdigest()[:16]

def normalize(c: Config, rows: Sequence[Mapping[str, Any]]) -> tuple[list[Trip], dict[str, Any]]:
    missing, trips, invalid = Counter(), [], 0
    for index, row in enumerate(rows):
        missing.update(f for f in c.fields if row.get(f) in (None, ""))
        start, end = parse_datetime(row.get(c.start_field)), parse_datetime(row.get(c.end_field))
        pickup, dropoff = str(row.get(c.pickup_field, "")).strip(), str(row.get(c.dropoff_field, "")).strip()
        miles, duration, fare = finite_float(row.get(c.miles_field)), finite_float(row.get(c.duration_field)), finite_float(row.get(c.fare_field))
        if start is None or end is None or end < start: invalid += 1; continue
        if not pickup or not dropoff or None in (miles, duration, fare): continue
        trips.append(Trip(deidentified_id(c, row, index), start, end, pickup, dropoff, float(miles), float(duration), float(fare)))
    n = len(rows)
    return trips, {"raw_rows": n, "usable_rows": len(trips),
                   "usable_rate": len(trips) / n if n else None,
                   "invalid_intervals": invalid,
                   "missingness": {f: {"rows": missing[f], "rate": missing[f] / n if n else None} for f in c.fields}}

def time_bin(value: datetime) -> str:
    return value.replace(minute=value.minute - value.minute % 15, second=0, microsecond=0).isoformat()

def group_by_time(trips: Sequence[Trip]) -> dict[str, list[Trip]]:
    groups: dict[str, list[Trip]] = defaultdict(list)
    for trip in trips: groups[time_bin(trip.start)].append(trip)
    for group in groups.values(): group.sort(key=lambda x: (x.start, x.end, x.node_id))
    return dict(groups)

def candidate_edges(trips: Sequence[Trip], padding_minutes: int, route_filter: bool) -> set[tuple[int, int]]:
    """Illustrative candidate graph; partner recall is not identified."""
    edges, padding = set(), timedelta(minutes=padding_minutes)
    for i, j in combinations(range(len(trips)), 2):
        a, b = trips[i], trips[j]
        if not (a.start <= b.end + padding and b.start <= a.end + padding): continue
        if route_filter and not (a.pickup == b.pickup or a.dropoff == b.dropoff or abs(a.miles - b.miles) <= 1.5): continue
        edges.add((i, j))
    return edges

def matching_endpoint(trips: Sequence[Trip], edges: set[tuple[int, int]], weight: Callable[[Trip, Trip], float]) -> tuple[int, float | None, float | None]:
    n = len(trips)
    if n % 2: return 0, None, None
    adjacency, weights = [[False] * n for _ in range(n)], {}
    for i, j in edges:
        a, b = min(i, j), max(i, j); adjacency[a][b] = adjacency[b][a] = True; weights[(a, b)] = weight(trips[a], trips[b])
    @lru_cache(maxsize=None)
    def solve(mask: int) -> tuple[int, float, float]:
        if not mask: return 1, 0.0, 0.0
        bit = mask & -mask; i = bit.bit_length() - 1; remainder = mask ^ bit
        count, minimum, maximum, candidates = 0, math.inf, -math.inf, remainder
        while candidates:
            partner = candidates & -candidates; j = partner.bit_length() - 1; candidates ^= partner
            if not adjacency[i][j]: continue
            child_count, child_min, child_max = solve(remainder ^ partner)
            if not child_count: continue
            edge_weight = weights[(min(i, j), max(i, j))]
            count += child_count; minimum = min(minimum, edge_weight + child_min); maximum = max(maximum, edge_weight + child_max)
        return (0, math.inf, -math.inf) if not count else (count, minimum, maximum)
    count, minimum, maximum = solve((1 << n) - 1)
    return (0, None, None) if not count else (count, minimum / (n / 2), maximum / (n / 2))

def endpoints(trips: Sequence[Trip], edges: set[tuple[int, int]]) -> dict[str, dict[str, Any]]:
    queries = {
        "mean_absolute_trip_miles_gap": lambda a, b: abs(a.miles - b.miles),
        "mean_absolute_duration_gap_minutes": lambda a, b: abs(a.duration_seconds - b.duration_seconds) / 60,
        "mean_absolute_fare_gap": lambda a, b: abs(a.fare - b.fare),
        "same_dropoff_zone_fraction": lambda a, b: float(a.dropoff == b.dropoff),
    }
    return {name: dict(zip(("worlds", "minimum", "maximum"), matching_endpoint(trips, edges, query))) for name, query in queries.items()}

def choose_market(c: Config, groups: Mapping[str, Sequence[Trip]], max_nodes: int) -> dict[str, Any]:
    for key, group in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        n = min(max_nodes, len(group)); n -= n % 2
        if n < 4: continue
        trips = list(group[:n]); temporal = candidate_edges(trips, c.padding_minutes, False)
        worlds, _, _ = matching_endpoint(trips, temporal, lambda _a, _b: 0.0)
        if not worlds: continue
        route = candidate_edges(trips, c.padding_minutes, True)
        route_worlds, _, _ = matching_endpoint(trips, route, lambda _a, _b: 0.0)
        return {"released_start_bin": key, "nodes": n,
                "temporal_candidate_edges": len(temporal), "temporal_candidate_worlds": worlds,
                "route_candidate_edges": len(route), "route_candidate_worlds": route_worlds,
                "temporal_candidate_endpoints": endpoints(trips, temporal),
                "route_candidate_endpoints": endpoints(trips, route) if route_worlds else None,
                "deidentified_nodes": [{**trip.__dict__, "start": trip.start.isoformat(), "end": trip.end.isoformat()} for trip in trips]}
    raise ValueError("no small even time bin admits a perfect matching")

def run_city(c: Config, limit: int, max_nodes: int) -> dict[str, Any]:
    started = time.monotonic(); schema = inspect_schema(c, fetch_json(metadata_url(c)))
    cohort_rows, count_error = None, None
    try: cohort_rows = int(fetch_json(resource_url(c, count_query(c)))[0]["n"])
    except Exception as exc: count_error = f"{type(exc).__name__}: {exc}"
    raw = fetch_json(resource_url(c, sample_query(c, limit)))
    if not isinstance(raw, list) or not raw: raise ValueError("sample query returned no rows")
    trips, quality = normalize(c, raw); groups = group_by_time(trips); selected = choose_market(c, groups, max_nodes)
    result = {"status": "ok", "city": c.name, "slug": c.slug,
              "dataset": {"id": c.dataset_id, "name": c.dataset_name, "window": [c.start, c.end],
                          "predicate": c.predicate, "pair_size_known": c.pair_size_known,
                          "partner_identity_known": False, "interpretation": c.interpretation},
              "schema": schema, "cohort_rows_in_window": cohort_rows, "count_error": count_error,
              "bounded_rows_fetched": len(raw), "quality": quality, "time_bins": len(groups),
              "maximum_time_bin_size": max(map(len, groups.values())), "selected_market": selected,
              "limitations": ["the sample is not a run-closed cohort", "candidate-edge recall is not identified",
                              "the public partner key is absent", "reported endpoints are conditional on an illustrative graph"],
              "elapsed_seconds": time.monotonic() - started}
    result["sha256"] = sha256_json(result); return result

def render_markdown(summary: Mapping[str, Any]) -> str:
    lines = ["# Real mobility data smoke test", "", f"Generated UTC: `{summary['generated_at_utc']}`", "",
             "This is a bounded schema/API/conditional-endpoint test, not partner reconstruction or a coverage evaluation.", "",
             "| City | Status | Cohort rows | Fetched | Usable | Max 15-min bin | Pair size known | Exact temporal worlds |",
             "|---|---|---:|---:|---:|---:|---|---:|"]
    for city in summary["cities"]:
        if city["status"] != "ok": lines.append(f"| {city['city']} | FAIL | — | — | — | — | — | — |"); continue
        count = city["cohort_rows_in_window"]; count_text = "—" if count is None else f"{count:,}"
        lines.append(f"| {city['city']} | PASS | {count_text} | {city['bounded_rows_fetched']:,} | {city['quality']['usable_rows']:,} | {city['maximum_time_bin_size']:,} | {'yes' if city['dataset']['pair_size_known'] else 'no'} | {city['selected_market']['temporal_candidate_worlds']:,} |")
    for city in summary["cities"]:
        lines += ["", f"## {city['city']}", ""]
        if city["status"] != "ok": lines.append(f"`{city['error']}`"); continue
        lines += [city["dataset"]["interpretation"], "", "| Query | Conditional minimum | Conditional maximum |", "|---|---:|---:|"]
        for name, endpoint in city["selected_market"]["temporal_candidate_endpoints"].items():
            lines.append(f"| `{name}` | {endpoint['minimum']:.6g} | {endpoint['maximum']:.6g} |")
    lines += ["", "## Gate", "", "Chicago is the method-fit candidate because the release reports `trips_pooled = 2`; NYC is an independent real-covariate diagnostic because its public shared-match flag does not reveal run size.", "", f"Summary SHA-256: `{summary['sha256']}`", ""]
    return "\n".join(lines)

def write_outputs(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (output_dir / "REPORT.md").write_text(render_markdown(summary))
    with (output_dir / "city_summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(["city", "status", "cohort_rows", "fetched", "usable", "max_bin", "pair_size_known", "worlds"])
        for city in summary["cities"]:
            writer.writerow([city["city"], city["status"]] + ([city["cohort_rows_in_window"], city["bounded_rows_fetched"], city["quality"]["usable_rows"], city["maximum_time_bin_size"], city["dataset"]["pair_size_known"], city["selected_market"]["temporal_candidate_worlds"]] if city["status"] == "ok" else ["", "", "", "", "", ""]))

def self_test() -> None:
    now = datetime(2026, 1, 1, 12); trips = [Trip(f"n{i}", now, now + timedelta(minutes=30), "1", str(i % 2), float(i + 1), 600 + i * 60, 10 + i) for i in range(4)]
    assert matching_endpoint(trips, set(combinations(range(4), 2)), lambda a, b: abs(a.miles - b.miles)) == (3, 1.0, 2.0)
    assert NYC.dataset_id == "u253-aew4"; print("self-test: PASS")

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, default=Path("tmp/real-city-smoke")); parser.add_argument("--max-rows", type=int, default=5000); parser.add_argument("--max-market-nodes", type=int, default=12); parser.add_argument("--cities", nargs="+", choices=("chicago", "nyc"), default=["chicago", "nyc"]); parser.add_argument("--require-all", action="store_true"); parser.add_argument("--self-test", action="store_true"); args = parser.parse_args()
    if args.self_test: self_test(); return 0
    if not 10 <= args.max_rows <= 50000 or not 4 <= args.max_market_nodes <= 18: parser.error("unsafe smoke-test bounds")
    results = []
    for slug in args.cities:
        c = {"chicago": CHICAGO, "nyc": NYC}[slug]
        try: results.append(run_city(c, args.max_rows, args.max_market_nodes))
        except Exception as exc: results.append({"status": "failed", "city": c.name, "slug": c.slug, "error_type": type(exc).__name__, "error": str(exc)})
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "parameters": vars(args) | {"output_dir": str(args.output_dir)}, "cities": results}; summary["sha256"] = sha256_json(summary); write_outputs(summary, args.output_dir); print(render_markdown(summary))
    failures = sum(x["status"] != "ok" for x in results); return 1 if args.require_all and failures else (2 if failures == len(results) else 0)

if __name__ == "__main__": sys.exit(main())
