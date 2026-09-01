#!/usr/bin/env python3
"""Build a boundary-complete Chicago K=2 public-release cohort and sensitivity curves.

The City of Chicago public TNP table reports ``Shared Trip Match`` and
``Trips Pooled`` but suppresses the ``Shared Trip ID`` that joins transactions
within an empty-to-empty pooled run.  This script therefore distinguishes two
claims:

1. **Public-release temporal candidate-universe closure.**  For one released
   15-minute core bin, retrieve every literal ``Match=true, K=2`` row whose
   released start/end envelopes could overlap any core row, plus every target
   row with a null released start or end.  Snapshot and server-count checks make
   this candidate universe complete for the declared public timestamp model.
2. **Hidden-run closure.**  This remains unidentified because partner/run IDs
   are absent.  Neither graph feasibility nor a narrow query range is treated
   as partner-recall evidence.

On the closed public candidate universe, the script computes two nested
candidate-support sensitivity families:

* a geographic radius expansion from strict endpoint compatibility to the full
  temporal graph; and
* a core-incidence miss budget ``Gamma`` that permits an increasing number of
  core assignments to use temporal edges outside a fixed geographic screen.

For every family point it solves min/max binary matching-cover programs for
semantic trip queries.  The denominator is the fixed number of core rows; a
core-core edge contributes twice and a core-buffer edge once.  Raw rows and
trip IDs are never written to output artifacts.
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
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, lil_matrix, vstack

DATASET_ID = "6dvr-xwnh"
DATASET_NAME = "Transportation Network Providers - Trips (2025-)"
DOMAIN = "https://data.cityofchicago.org"
USER_AGENT = "urban-pooling-chicago-k2-frontier/0.1"
RELEASE_BIN_MINUTES = 15
ROUNDING_HALF_MINUTES = 7.5
TARGET_PREDICATE = "shared_trip_match = true AND trips_pooled = 2"
DEFAULT_SCAN_START = "2026-01-13T17:00:00"
DEFAULT_SCAN_END = "2026-01-13T21:00:00"
DEFAULT_RADII_KM = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0)

FIELDS = (
    "trip_id",
    "trip_start_timestamp",
    "trip_end_timestamp",
    "trip_seconds",
    "trip_miles",
    "pickup_census_tract",
    "dropoff_census_tract",
    "pickup_community_area",
    "dropoff_community_area",
    "fare",
    "trip_total",
    "shared_trip_authorized",
    "shared_trip_match",
    "trips_pooled",
    "pickup_centroid_latitude",
    "pickup_centroid_longitude",
    "dropoff_centroid_latitude",
    "dropoff_centroid_longitude",
)


class LiveDataError(RuntimeError):
    """The live public-data extraction or its closure checks failed."""


@dataclass(frozen=True)
class Snapshot:
    dataset_id: str
    dataset_name: str | None
    rows_updated_at: Any
    view_last_modified: Any
    publication_date: Any
    schema_sha256: str
    revision_fingerprint_sha256: str


@dataclass(frozen=True)
class TripRow:
    index: int
    trip_id: str | None
    identifier_status: str
    role: str
    released_start: datetime | None
    released_end: datetime | None
    interval_start: datetime | None
    interval_end: datetime | None
    interval_status: str
    pickup: tuple[float, float] | None
    dropoff: tuple[float, float] | None
    pickup_area: str | None
    dropoff_area: str | None
    miles: float | None
    duration_seconds: float | None
    fare: float | None


@dataclass(frozen=True)
class QuerySpec:
    name: str
    unit: str
    coefficient_interval: Callable[[TripRow, TripRow], tuple[float, float] | None]
    missing_semantics: str


@dataclass(frozen=True)
class BoundResult:
    status: str
    value: float | None
    backend: str
    mip_gap: float | None
    mip_node_count: int | None
    replay_max_residual: float | None
    selected_edges: int | None
    message: str


@dataclass(frozen=True)
class GraphPoint:
    curve_type: str
    parameter_label: str
    parameter_value: float | None
    radius_km: float | None
    gamma_core_incidences: int | None
    edge_count: int
    retained_fraction_of_temporal: float
    spatially_unmeasured_edges_retained: int
    core_zero_degree_count: int
    core_min_degree: int | None
    core_max_degree: int | None
    cover_status: str
    cover_mip_gap: float | None


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request_json(url: str, *, timeout: int = 180, attempts: int = 4) -> Any:
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
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise LiveDataError(f"request failed: {url}; " + " | ".join(errors))


def _metadata_url() -> str:
    return f"{DOMAIN}/api/views/{DATASET_ID}.json"


def _soda2_url(query: str) -> str:
    return f"{DOMAIN}/resource/{DATASET_ID}.json?" + urllib.parse.urlencode(
        {"$query": query}
    )


def _soda3_url(query: str, *, page_number: int, page_size: int) -> str:
    return f"{DOMAIN}/api/v3/views/{DATASET_ID}/query.json?" + urllib.parse.urlencode(
        {"query": query, "pageNumber": page_number, "pageSize": page_size}
    )


def query_rows(query: str, *, page_size: int = 5000) -> tuple[list[dict[str, Any]], str]:
    """Run one bounded query, trying SODA2 before SODA3."""

    errors: list[str] = []
    for api_name, url in (
        ("soda2", _soda2_url(query)),
        ("soda3", _soda3_url(query, page_number=1, page_size=page_size)),
    ):
        try:
            payload = _request_json(url)
            if not isinstance(payload, list) or not all(
                isinstance(row, dict) for row in payload
            ):
                raise LiveDataError(
                    f"{api_name} returned {type(payload).__name__}, expected row list"
                )
            return payload, api_name
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"{api_name}: {type(exc).__name__}: {exc}")
    raise LiveDataError("both Socrata APIs failed: " + " || ".join(errors))


def scalar_count(where: str) -> tuple[int, str, str]:
    query = f"SELECT count(*) AS n WHERE {where}"
    rows, api = query_rows(query, page_size=10)
    if len(rows) != 1 or "n" not in rows[0]:
        raise LiveDataError(f"unexpected count response for {where!r}: {rows!r}")
    return int(rows[0]["n"]), api, query


def paged_select(
    *,
    fields: Sequence[str],
    where: str,
    order_by: str,
    expected_count: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], list[str], str]:
    """Fetch exactly ``expected_count`` rows with deterministic LIMIT/OFFSET pages."""

    rows: list[dict[str, Any]] = []
    apis: list[str] = []
    offset = 0
    base = f"SELECT {', '.join(fields)} WHERE {where} ORDER BY {order_by}"
    while offset < expected_count:
        limit = min(page_size, expected_count - offset)
        query = f"{base} LIMIT {limit} OFFSET {offset}"
        chunk, api = query_rows(query, page_size=limit)
        if not chunk:
            raise LiveDataError(
                f"empty page at offset {offset}; expected {expected_count} rows"
            )
        rows.extend(chunk)
        apis.append(api)
        offset += len(chunk)
        if len(chunk) < limit and offset < expected_count:
            raise LiveDataError(
                f"short page at offset {offset}; expected {expected_count} rows"
            )
    if len(rows) != expected_count:
        raise LiveDataError(
            f"server count was {expected_count}, deterministic fetch returned {len(rows)}"
        )
    return rows, apis, base


def dataset_snapshot(metadata: Any) -> Snapshot:
    if not isinstance(metadata, dict) or metadata.get("id") != DATASET_ID:
        raise LiveDataError("dataset metadata id mismatch")
    columns = metadata.get("columns")
    if not isinstance(columns, list) or not columns:
        raise LiveDataError("dataset metadata has no columns")
    normalized_columns: list[dict[str, Any]] = []
    for fallback_position, column in enumerate(columns):
        if not isinstance(column, dict):
            raise LiveDataError("malformed column metadata")
        field = column.get("fieldName")
        dtype = column.get("dataTypeName")
        if not isinstance(field, str) or not field:
            raise LiveDataError("column metadata lacks fieldName")
        normalized_columns.append(
            {
                "position": column.get("position", fallback_position),
                "field_name": field,
                "data_type": dtype,
            }
        )
    normalized_columns.sort(key=lambda item: (item["position"], item["field_name"]))
    names = {column["field_name"] for column in normalized_columns}
    missing = sorted(set(FIELDS) - names)
    if missing:
        raise LiveDataError(f"required public fields are absent: {missing}")
    schema_hash = sha256_json(normalized_columns)
    core = {
        "dataset_id": DATASET_ID,
        "dataset_name": metadata.get("name"),
        "rows_updated_at": metadata.get("rowsUpdatedAt"),
        "view_last_modified": metadata.get("viewLastModified"),
        "publication_date": metadata.get("publicationDate"),
        "schema_sha256": schema_hash,
    }
    return Snapshot(
        **core,
        revision_fingerprint_sha256=sha256_json(core),
    )


def parse_local_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def on_release_grid(value: datetime) -> bool:
    return (
        value.minute % RELEASE_BIN_MINUTES == 0
        and value.second == 0
        and value.microsecond == 0
    )


def format_socrata_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat(timespec="seconds") + ".000"


def finite_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalized_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def parse_bool(value: Any) -> bool | None:
    text = normalized_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def parse_k(value: Any) -> int | None:
    number = finite_float(value)
    if number is None or number < 1 or not float(number).is_integer():
        return None
    return int(number)


def parse_coordinate(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    lat = finite_float(latitude)
    lon = finite_float(longitude)
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def stable_raw_rows_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    """Hash exact raw row dictionaries without serializing them to output."""

    return sha256_json(list(rows))


def candidate_overlap_cutoffs(
    core_starts: Sequence[datetime], core_ends: Sequence[datetime]
) -> tuple[datetime, datetime]:
    """Return necessary released-time cutoffs for any determinate core partner.

    With timestamp-rounding half-width ``delta``, overlap of candidate ``j``
    with some core row ``i`` requires

    ``start_j <= end_i + 2*delta`` and ``end_j >= start_i - 2*delta``.

    Taking the maximum core end and minimum core start therefore gives a safe
    outer retrieval envelope.
    """

    if not core_starts or not core_ends or len(core_starts) != len(core_ends):
        raise ValueError("core starts and ends must be nonempty and have equal length")
    if any(end < start for start, end in zip(core_starts, core_ends)):
        raise ValueError("core released end precedes released start")
    double_delta = timedelta(minutes=2 * ROUNDING_HALF_MINUTES)
    return min(core_starts) - double_delta, max(core_ends) + double_delta


def choose_core_bin(
    *,
    scan_start: datetime,
    scan_end: datetime,
    min_core_rows: int,
    max_core_rows: int,
    max_candidate_rows: int,
    page_size: int,
) -> dict[str, Any]:
    where = (
        f"trip_start_timestamp >= '{format_socrata_timestamp(scan_start)}' "
        f"AND trip_start_timestamp < '{format_socrata_timestamp(scan_end)}' "
        f"AND {TARGET_PREDICATE}"
    )
    group_query = (
        "SELECT trip_start_timestamp, count(*) AS n "
        f"WHERE {where} GROUP BY trip_start_timestamp "
        "ORDER BY n DESC, trip_start_timestamp LIMIT 96"
    )
    grouped, api = query_rows(group_query, page_size=96)
    candidate_bins: list[dict[str, Any]] = []
    for group in grouped:
        start = parse_local_timestamp(group.get("trip_start_timestamp"))
        try:
            count = int(group["n"])
        except (KeyError, TypeError, ValueError):
            continue
        if start is None or not min_core_rows <= count <= max_core_rows:
            continue
        core_end = start + timedelta(minutes=RELEASE_BIN_MINUTES)
        core_where = (
            f"trip_start_timestamp >= '{format_socrata_timestamp(start)}' "
            f"AND trip_start_timestamp < '{format_socrata_timestamp(core_end)}' "
            f"AND {TARGET_PREDICATE}"
        )
        core_count, core_count_api, core_count_query = scalar_count(core_where)
        if core_count != count:
            continue
        core_rows, core_apis, core_base_query = paged_select(
            fields=FIELDS,
            where=core_where,
            order_by="trip_start_timestamp, trip_end_timestamp, trip_id",
            expected_count=core_count,
            page_size=page_size,
        )
        parsed_ends = [parse_local_timestamp(row.get("trip_end_timestamp")) for row in core_rows]
        raw_ids = [normalized_text(row.get("trip_id")) for row in core_rows]
        parsed_starts = [
            parse_local_timestamp(row.get("trip_start_timestamp")) for row in core_rows
        ]
        if any(value is None for value in parsed_starts) or any(
            value is None for value in parsed_ends
        ):
            continue
        if any(
            not on_release_grid(value)
            for value in [*parsed_starts, *parsed_ends]
            if value is not None
        ):
            continue
        if any(
            end_value < start_value
            for start_value, end_value in zip(parsed_starts, parsed_ends)
            if start_value is not None and end_value is not None
        ):
            continue
        if any(value is None for value in raw_ids) or len(set(raw_ids)) != len(raw_ids):
            continue
        if any(parse_bool(row.get("shared_trip_match")) is not True for row in core_rows):
            continue
        if any(parse_k(row.get("trips_pooled")) != 2 for row in core_rows):
            continue
        lower_end, upper_start = candidate_overlap_cutoffs(
            [value for value in parsed_starts if value is not None],
            [value for value in parsed_ends if value is not None],
        )
        determinate_where = (
            f"{TARGET_PREDICATE} "
            "AND trip_start_timestamp IS NOT NULL "
            "AND trip_end_timestamp IS NOT NULL "
            f"AND trip_start_timestamp <= '{format_socrata_timestamp(upper_start)}' "
            f"AND trip_end_timestamp >= '{format_socrata_timestamp(lower_end)}'"
        )
        indeterminate_where = (
            f"{TARGET_PREDICATE} AND "
            "(trip_start_timestamp IS NULL OR trip_end_timestamp IS NULL)"
        )
        determinate_count, det_api, det_query = scalar_count(determinate_where)
        indeterminate_count, ind_api, ind_query = scalar_count(indeterminate_where)
        total = determinate_count + indeterminate_count
        candidate_bins.append(
            {
                "core_start": start,
                "core_end": core_end,
                "core_count": core_count,
                "core_rows": core_rows,
                "core_count_api": core_count_api,
                "core_page_apis": core_apis,
                "core_count_query": core_count_query,
                "core_base_query": core_base_query,
                "lower_end_cutoff": lower_end,
                "upper_start_cutoff": upper_start,
                "determinate_where": determinate_where,
                "indeterminate_where": indeterminate_where,
                "determinate_count": determinate_count,
                "indeterminate_count": indeterminate_count,
                "candidate_count": total,
                "determinate_count_api": det_api,
                "indeterminate_count_api": ind_api,
                "determinate_count_query": det_query,
                "indeterminate_count_query": ind_query,
            }
        )
        if total <= max_candidate_rows:
            selected = candidate_bins[-1]
            selected["scan_group_query"] = group_query
            selected["scan_group_api"] = api
            selected["considered_bins"] = [
                {
                    "core_start": item["core_start"].isoformat(),
                    "core_count": item["core_count"],
                    "candidate_count": item["candidate_count"],
                }
                for item in candidate_bins
            ]
            return selected
    if not candidate_bins:
        raise LiveDataError(
            "no scan bin met the core-count and timestamp/id-integrity requirements"
        )
    raise LiveDataError(
        "all integrity-qualified bins exceeded max_candidate_rows="
        f"{max_candidate_rows}; smallest candidate count was "
        f"{min(item['candidate_count'] for item in candidate_bins)}"
    )


def fetch_closed_candidate_universe(
    selected: Mapping[str, Any], *, page_size: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    determinate_rows, determinate_apis, determinate_base = paged_select(
        fields=FIELDS,
        where=str(selected["determinate_where"]),
        order_by="trip_start_timestamp, trip_end_timestamp, trip_id",
        expected_count=int(selected["determinate_count"]),
        page_size=page_size,
    )
    indeterminate_rows, indeterminate_apis, indeterminate_base = paged_select(
        fields=FIELDS,
        where=str(selected["indeterminate_where"]),
        order_by="trip_id",
        expected_count=int(selected["indeterminate_count"]),
        page_size=page_size,
    ) if int(selected["indeterminate_count"]) else ([], [], "")
    rows = [*determinate_rows, *indeterminate_rows]
    if len(rows) != int(selected["candidate_count"]):
        raise LiveDataError("combined candidate rows do not match pinned counts")
    return rows, {
        "determinate_page_apis": determinate_apis,
        "indeterminate_page_apis": indeterminate_apis,
        "determinate_base_query": determinate_base,
        "indeterminate_base_query": indeterminate_base,
    }


def prepare_rows(
    raw_rows: Sequence[Mapping[str, Any]],
    *,
    core_start: datetime,
    core_end: datetime,
) -> tuple[list[TripRow], dict[str, Any]]:
    raw_ids = [normalized_text(row.get("trip_id")) for row in raw_rows]
    id_counts = Counter(value for value in raw_ids if value is not None)
    rows: list[TripRow] = []
    issues = Counter()
    for index, (raw, raw_id) in enumerate(zip(raw_rows, raw_ids)):
        if raw_id is None:
            identifier_status = "null_or_blank"
        elif id_counts[raw_id] > 1:
            identifier_status = "duplicate"
        else:
            identifier_status = "unique_nonnull"
        start = parse_local_timestamp(raw.get("trip_start_timestamp"))
        end = parse_local_timestamp(raw.get("trip_end_timestamp"))
        if start is not None and end is not None and on_release_grid(start) and on_release_grid(end):
            interval_start = start - timedelta(minutes=ROUNDING_HALF_MINUTES)
            interval_end = end + timedelta(minutes=ROUNDING_HALF_MINUTES)
            if interval_start <= interval_end:
                interval_status = "determinate_outer_interval"
            else:
                interval_start = None
                interval_end = None
                interval_status = "released_chronology_impossible"
        elif start is not None and end is not None:
            interval_start = None
            interval_end = None
            interval_status = "off_release_grid_timestamp"
        else:
            interval_start = None
            interval_end = None
            interval_status = "indeterminate_timestamp"
        target = (
            parse_bool(raw.get("shared_trip_match")) is True
            and parse_k(raw.get("trips_pooled")) == 2
        )
        if not target:
            issues["non_target_row_in_candidate_extract"] += 1
        if identifier_status == "unique_nonnull" and target:
            role = "core" if start is not None and core_start <= start < core_end else "buffer"
        else:
            role = "context"
        if interval_status == "released_chronology_impossible":
            issues["released_chronology_impossible"] += 1
        if interval_status == "off_release_grid_timestamp":
            issues["off_release_grid_timestamp"] += 1
        if role in {"core", "buffer"} and interval_status in {
            "indeterminate_timestamp",
            "off_release_grid_timestamp",
        }:
            issues["target_indeterminate_timestamp"] += 1
        if parse_bool(raw.get("shared_trip_match")) is True and parse_bool(
            raw.get("shared_trip_authorized")
        ) is False:
            issues["match_true_authorized_false"] += 1
        rows.append(
            TripRow(
                index=index,
                trip_id=raw_id,
                identifier_status=identifier_status,
                role=role,
                released_start=start,
                released_end=end,
                interval_start=interval_start,
                interval_end=interval_end,
                interval_status=interval_status,
                pickup=parse_coordinate(
                    raw.get("pickup_centroid_latitude"),
                    raw.get("pickup_centroid_longitude"),
                ),
                dropoff=parse_coordinate(
                    raw.get("dropoff_centroid_latitude"),
                    raw.get("dropoff_centroid_longitude"),
                ),
                pickup_area=normalized_text(raw.get("pickup_community_area")),
                dropoff_area=normalized_text(raw.get("dropoff_community_area")),
                miles=finite_float(raw.get("trip_miles")),
                duration_seconds=finite_float(raw.get("trip_seconds")),
                fare=finite_float(raw.get("fare")),
            )
        )
    core_ids = {row.trip_id for row in rows if row.role == "core"}
    return rows, {
        "rows": len(rows),
        "core_rows": sum(row.role == "core" for row in rows),
        "buffer_rows": sum(row.role == "buffer" for row in rows),
        "context_rows": sum(row.role == "context" for row in rows),
        "unique_nonnull_ids": sum(row.identifier_status == "unique_nonnull" for row in rows),
        "duplicate_id_rows": sum(row.identifier_status == "duplicate" for row in rows),
        "null_or_blank_id_rows": sum(row.identifier_status == "null_or_blank" for row in rows),
        "core_unique_ids": len(core_ids),
        "issues": dict(sorted(issues.items())),
        "field_completeness": {
            "pickup_coordinates": sum(row.pickup is not None for row in rows),
            "dropoff_coordinates": sum(row.dropoff is not None for row in rows),
            "pickup_area": sum(row.pickup_area is not None for row in rows),
            "dropoff_area": sum(row.dropoff_area is not None for row in rows),
            "trip_miles": sum(row.miles is not None for row in rows),
            "trip_seconds": sum(row.duration_seconds is not None for row in rows),
            "fare": sum(row.fare is not None for row in rows),
        },
    }


def possible_overlap(left: TripRow, right: TripRow) -> bool:
    if left.interval_start is None or left.interval_end is None:
        return True
    if right.interval_start is None or right.interval_end is None:
        return True
    return left.interval_start <= right.interval_end and right.interval_start <= left.interval_end


def build_temporal_edges(rows: Sequence[TripRow]) -> tuple[list[tuple[int, int]], dict[str, int]]:
    eligible = [row for row in rows if row.role in {"core", "buffer"}]
    edges: list[tuple[int, int]] = []
    provenance = Counter()
    for left_position, left in enumerate(eligible):
        for right in eligible[left_position + 1 :]:
            if left.role != "core" and right.role != "core":
                continue
            if not possible_overlap(left, right):
                provenance["temporally_ruled_out"] += 1
                continue
            edges.append((min(left.index, right.index), max(left.index, right.index)))
            if left.interval_start is None or right.interval_start is None:
                provenance["retained_indeterminate_timestamp"] += 1
            else:
                provenance["retained_determinate_overlap"] += 1
            provenance[
                "core_core" if left.role == right.role == "core" else "core_buffer"
            ] += 1
    edges.sort()
    return edges, dict(sorted(provenance.items()))


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, left)
    lat2, lon2 = map(math.radians, right)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(value)))


def edge_route_radius(rows_by_index: Mapping[int, TripRow], edge: tuple[int, int]) -> float | None:
    left = rows_by_index[edge[0]]
    right = rows_by_index[edge[1]]
    if left.pickup is None or right.pickup is None or left.dropoff is None or right.dropoff is None:
        return None
    return max(
        haversine_km(left.pickup, right.pickup),
        haversine_km(left.dropoff, right.dropoff),
    )


def radius_graph(
    temporal_edges: Sequence[tuple[int, int]],
    route_radius: Mapping[tuple[int, int], float | None],
    radius_km: float | None,
) -> tuple[list[tuple[int, int]], int]:
    if radius_km is None:
        return list(temporal_edges), sum(route_radius[edge] is None for edge in temporal_edges)
    retained = [
        edge
        for edge in temporal_edges
        if route_radius[edge] is None or route_radius[edge] <= radius_km
    ]
    return retained, sum(route_radius[edge] is None for edge in retained)


def graph_degrees(
    rows: Sequence[TripRow], edges: Sequence[tuple[int, int]]
) -> dict[str, Any]:
    core = [row.index for row in rows if row.role == "core"]
    buffer = [row.index for row in rows if row.role == "buffer"]
    degrees = Counter({index: 0 for index in [*core, *buffer]})
    for left, right in edges:
        degrees[left] += 1
        degrees[right] += 1
    core_degrees = [degrees[index] for index in core]
    buffer_degrees = [degrees[index] for index in buffer]
    return {
        "core_count": len(core),
        "buffer_count": len(buffer),
        "edge_count": len(edges),
        "core_zero_degree_count": sum(value == 0 for value in core_degrees),
        "core_min_degree": min(core_degrees) if core_degrees else None,
        "core_max_degree": max(core_degrees) if core_degrees else None,
        "buffer_zero_degree_count": sum(value == 0 for value in buffer_degrees),
        "buffer_max_degree": max(buffer_degrees) if buffer_degrees else None,
    }


def _model_matrices(
    rows: Sequence[TripRow],
    edges: Sequence[tuple[int, int]],
    *,
    miss_costs: Sequence[int] | None = None,
    gamma: int | None = None,
) -> tuple[csr_matrix, np.ndarray, np.ndarray, list[int], list[int]]:
    core = [row.index for row in rows if row.role == "core"]
    buffer = [row.index for row in rows if row.role == "buffer"]
    constrained = [*core, *buffer]
    if not core:
        raise ValueError("model requires at least one core row")
    row_position = {node: position for position, node in enumerate(constrained)}
    matrix = lil_matrix((len(constrained), len(edges)), dtype=float)
    for column, (left, right) in enumerate(edges):
        if left in row_position:
            matrix[row_position[left], column] = 1.0
        if right in row_position:
            matrix[row_position[right], column] = 1.0
    lower = np.asarray([1.0] * len(core) + [0.0] * len(buffer), dtype=float)
    upper = np.ones(len(constrained), dtype=float)
    constraint_matrix = matrix.tocsr()
    if gamma is not None:
        if miss_costs is None or len(miss_costs) != len(edges):
            raise ValueError("gamma requires one miss cost per edge")
        miss_row = csr_matrix(np.asarray(miss_costs, dtype=float).reshape(1, -1))
        constraint_matrix = vstack([constraint_matrix, miss_row], format="csr")
        lower = np.append(lower, -np.inf)
        upper = np.append(upper, float(gamma))
    return constraint_matrix, lower, upper, core, buffer


def _replay_solution(
    solution: np.ndarray,
    matrix: csr_matrix,
    lower: np.ndarray,
    upper: np.ndarray,
) -> tuple[np.ndarray, float]:
    rounded = np.rint(solution)
    if rounded.shape != solution.shape or not np.isfinite(rounded).all():
        raise ValueError("invalid incumbent")
    row_sums = np.asarray(matrix @ rounded).reshape(-1)
    residual = max(
        float(np.max(np.abs(solution - rounded))) if len(solution) else 0.0,
        float(np.max(np.maximum(lower - row_sums, 0.0))) if len(lower) else 0.0,
        float(np.max(np.maximum(row_sums - upper, 0.0))) if len(upper) else 0.0,
        float(np.max(np.maximum(-rounded, 0.0))) if len(rounded) else 0.0,
        float(np.max(np.maximum(rounded - 1.0, 0.0))) if len(rounded) else 0.0,
    )
    return rounded, residual


def solve_binary_cover_objective(
    rows: Sequence[TripRow],
    edges: Sequence[tuple[int, int]],
    coefficients: Sequence[float],
    *,
    maximize: bool,
    miss_costs: Sequence[int] | None = None,
    gamma: int | None = None,
    time_limit_seconds: float,
) -> BoundResult:
    stats = graph_degrees(rows, edges)
    if stats["core_count"] == 0:
        return BoundResult(
            "VACUOUS_NO_CORE", 0.0, "structural", None, None, 0.0, 0, "No core rows."
        )
    if stats["core_zero_degree_count"]:
        return BoundResult(
            "PROVEN_INFEASIBLE_ISOLATED_CORE",
            None,
            "structural",
            None,
            None,
            None,
            None,
            "At least one core row has no candidate edge.",
        )
    if len(edges) != len(coefficients):
        raise ValueError("one objective coefficient is required per edge")
    matrix, lower, upper, _core, _buffer = _model_matrices(
        rows, edges, miss_costs=miss_costs, gamma=gamma
    )
    c = np.asarray(coefficients, dtype=float)
    if not np.isfinite(c).all():
        raise ValueError("objective coefficients must be finite")
    objective = -c if maximize else c
    result = milp(
        c=objective,
        integrality=np.ones(len(edges), dtype=int),
        bounds=Bounds(np.zeros(len(edges)), np.ones(len(edges))),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": float(time_limit_seconds), "presolve": True},
    )
    if result.status == 2:
        return BoundResult(
            "PROVEN_INFEASIBLE_BY_HIGHS",
            None,
            "scipy_highs_milp",
            _optional_float(result, "mip_gap"),
            _optional_int(result, "mip_node_count"),
            None,
            None,
            "HiGHS reported the declared integer cover infeasible.",
        )
    if result.x is None:
        return BoundResult(
            "UNRESOLVED_NO_INCUMBENT",
            None,
            "scipy_highs_milp",
            _optional_float(result, "mip_gap"),
            _optional_int(result, "mip_node_count"),
            None,
            None,
            f"HiGHS status={result.status} without an incumbent.",
        )
    rounded, residual = _replay_solution(np.asarray(result.x, dtype=float), matrix, lower, upper)
    if residual > 1e-7:
        return BoundResult(
            "UNRESOLVED_INVALID_INCUMBENT",
            None,
            "scipy_highs_milp",
            _optional_float(result, "mip_gap"),
            _optional_int(result, "mip_node_count"),
            residual,
            int(rounded.sum()),
            "Rounded incumbent failed independent constraint replay.",
        )
    value = float(np.dot(c, rounded))
    if result.status == 0:
        status = "OPTIMAL_NUMERICAL_MILP"
        message = "HiGHS returned an optimal integer incumbent; objective replay passed."
    else:
        status = "INCUMBENT_ONLY_UNRESOLVED_LIMIT"
        message = (
            f"HiGHS status={result.status}; a replayed incumbent exists but the bound "
            "is not certified optimal."
        )
    return BoundResult(
        status,
        value,
        "scipy_highs_milp",
        _optional_float(result, "mip_gap"),
        _optional_int(result, "mip_node_count"),
        residual,
        int(rounded.sum()),
        message,
    )


def _optional_float(result: Any, name: str) -> float | None:
    value = getattr(result, name, None)
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _optional_int(result: Any, name: str) -> int | None:
    value = getattr(result, name, None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def query_specs() -> tuple[QuerySpec, ...]:
    def numeric_gap(attribute: str, scale: float = 1.0):
        def coefficients(left: TripRow, right: TripRow) -> tuple[float, float] | None:
            left_value = getattr(left, attribute)
            right_value = getattr(right, attribute)
            if left_value is None or right_value is None:
                return None
            value = abs(float(left_value) - float(right_value)) / scale
            return value, value

        return coefficients

    def equality(attribute: str):
        def coefficients(left: TripRow, right: TripRow) -> tuple[float, float]:
            left_value = getattr(left, attribute)
            right_value = getattr(right, attribute)
            if left_value is None or right_value is None:
                return 0.0, 1.0
            value = float(left_value == right_value)
            return value, value

        return coefficients

    return (
        QuerySpec(
            "mean_absolute_trip_miles_gap_per_core",
            "miles",
            numeric_gap("miles"),
            "unresolved if any retained edge lacks trip_miles",
        ),
        QuerySpec(
            "mean_absolute_duration_gap_per_core",
            "minutes",
            numeric_gap("duration_seconds", 60.0),
            "unresolved if any retained edge lacks trip_seconds",
        ),
        QuerySpec(
            "mean_absolute_fare_gap_per_core",
            "dollars",
            numeric_gap("fare"),
            "unresolved if any retained edge lacks fare",
        ),
        QuerySpec(
            "same_pickup_community_area_fraction_per_core",
            "fraction",
            equality("pickup_area"),
            "missing endpoint area contributes interval [0,1]",
        ),
        QuerySpec(
            "same_dropoff_community_area_fraction_per_core",
            "fraction",
            equality("dropoff_area"),
            "missing endpoint area contributes interval [0,1]",
        ),
    )


def edge_query_coefficients(
    rows_by_index: Mapping[int, TripRow],
    rows: Sequence[TripRow],
    edges: Sequence[tuple[int, int]],
    spec: QuerySpec,
) -> tuple[list[float] | None, list[float] | None, int]:
    core_indices = {row.index for row in rows if row.role == "core"}
    denominator = len(core_indices)
    if denominator == 0:
        raise ValueError("query requires a nonempty core")
    lower: list[float] = []
    upper: list[float] = []
    missing_edges = 0
    for edge in edges:
        left, right = rows_by_index[edge[0]], rows_by_index[edge[1]]
        interval = spec.coefficient_interval(left, right)
        if interval is None:
            missing_edges += 1
            continue
        core_incidences = int(edge[0] in core_indices) + int(edge[1] in core_indices)
        lo, hi = interval
        lower.append(float(lo) * core_incidences / denominator)
        upper.append(float(hi) * core_incidences / denominator)
    if missing_edges:
        return None, None, missing_edges
    return lower, upper, 0


def edge_miss_costs(
    rows: Sequence[TripRow],
    edges: Sequence[tuple[int, int]],
    base_edges: set[tuple[int, int]],
) -> list[int]:
    core = {row.index for row in rows if row.role == "core"}
    return [
        0
        if edge in base_edges
        else int(edge[0] in core) + int(edge[1] in core)
        for edge in edges
    ]


def solve_curve_point(
    *,
    rows: Sequence[TripRow],
    edges: Sequence[tuple[int, int]],
    temporal_edge_count: int,
    unmeasured_edges: int,
    curve_type: str,
    parameter_label: str,
    parameter_value: float | None,
    radius_km: float | None,
    gamma: int | None,
    miss_costs: Sequence[int] | None,
    time_limit_seconds: float,
) -> tuple[GraphPoint, list[dict[str, Any]]]:
    stats = graph_degrees(rows, edges)
    zero_objective = [0.0] * len(edges)
    cover = solve_binary_cover_objective(
        rows,
        edges,
        zero_objective,
        maximize=False,
        miss_costs=miss_costs,
        gamma=gamma,
        time_limit_seconds=time_limit_seconds,
    )
    graph_point = GraphPoint(
        curve_type=curve_type,
        parameter_label=parameter_label,
        parameter_value=parameter_value,
        radius_km=radius_km,
        gamma_core_incidences=gamma,
        edge_count=len(edges),
        retained_fraction_of_temporal=(len(edges) / temporal_edge_count if temporal_edge_count else 0.0),
        spatially_unmeasured_edges_retained=unmeasured_edges,
        core_zero_degree_count=stats["core_zero_degree_count"],
        core_min_degree=stats["core_min_degree"],
        core_max_degree=stats["core_max_degree"],
        cover_status=cover.status,
        cover_mip_gap=cover.mip_gap,
    )
    rows_by_index = {row.index: row for row in rows}
    query_rows: list[dict[str, Any]] = []
    for spec in query_specs():
        lower_coefficients, upper_coefficients, missing_edges = edge_query_coefficients(
            rows_by_index, rows, edges, spec
        )
        if lower_coefficients is None or upper_coefficients is None:
            lower = BoundResult(
                "UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES",
                None,
                "none",
                None,
                None,
                None,
                None,
                spec.missing_semantics,
            )
            upper = lower
        else:
            lower = solve_binary_cover_objective(
                rows,
                edges,
                lower_coefficients,
                maximize=False,
                miss_costs=miss_costs,
                gamma=gamma,
                time_limit_seconds=time_limit_seconds,
            )
            upper = solve_binary_cover_objective(
                rows,
                edges,
                upper_coefficients,
                maximize=True,
                miss_costs=miss_costs,
                gamma=gamma,
                time_limit_seconds=time_limit_seconds,
            )
        width = (
            upper.value - lower.value
            if lower.value is not None and upper.value is not None
            else None
        )
        query_rows.append(
            {
                **asdict(graph_point),
                "query": spec.name,
                "unit": spec.unit,
                "lower": lower.value,
                "upper": upper.value,
                "width": width,
                "lower_status": lower.status,
                "upper_status": upper.status,
                "lower_mip_gap": lower.mip_gap,
                "upper_mip_gap": upper.mip_gap,
                "max_replay_residual": max(
                    value
                    for value in [lower.replay_max_residual, upper.replay_max_residual]
                    if value is not None
                )
                if any(
                    value is not None
                    for value in [lower.replay_max_residual, upper.replay_max_residual]
                )
                else None,
                "edges_with_missing_query_values": missing_edges,
                "query_missing_semantics": spec.missing_semantics,
                "claim": "conditional sensitivity over a declared public candidate family; no partner-recall claim",
            }
        )
    return graph_point, query_rows


def gamma_grid(core_count: int) -> list[int]:
    candidates = [0, 1, 2, 4, 8, 16, math.ceil(core_count / 4), math.ceil(core_count / 2), core_count]
    return sorted({value for value in candidates if 0 <= value <= core_count})


def monotonicity_audit(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["curve_type"]), str(row["query"]))].append(row)
    for (curve_type, query), group in grouped.items():
        ordered = sorted(
            group,
            key=lambda row: (
                math.inf if row["parameter_value"] is None else float(row["parameter_value"])
            ),
        )
        previous_lower: float | None = None
        previous_upper: float | None = None
        for row in ordered:
            lower = row.get("lower")
            upper = row.get("upper")
            if lower is None or upper is None:
                continue
            lower = float(lower)
            upper = float(upper)
            if previous_lower is not None and lower > previous_lower + 1e-7:
                violations.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "direction": "lower_increased",
                        "previous": previous_lower,
                        "current": lower,
                        "parameter": row["parameter_label"],
                    }
                )
            if previous_upper is not None and upper < previous_upper - 1e-7:
                violations.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "direction": "upper_decreased",
                        "previous": previous_upper,
                        "current": upper,
                        "parameter": row["parameter_label"],
                    }
                )
            previous_lower = lower
            previous_upper = upper
    return {
        "expected": "lower nonincreasing and upper nondecreasing as candidate support expands",
        "violation_count": len(violations),
        "violations": violations,
        "status": "PASS" if not violations else "FAIL",
    }


def write_long_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError("cannot write an empty sensitivity table")
    columns = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def plot_curves(rows: Sequence[Mapping[str, Any]], output_dir: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    written: list[str] = []
    radius_graph_rows: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if row["curve_type"] != "radius":
            continue
        radius_graph_rows[str(row["parameter_label"])] = row
    ordered_radius = sorted(
        radius_graph_rows.values(),
        key=lambda row: math.inf
        if row["parameter_value"] is None
        else float(row["parameter_value"]),
    )
    if ordered_radius:
        x = list(range(len(ordered_radius)))
        labels = [str(row["parameter_label"]) for row in ordered_radius]
        y = [int(row["edge_count"]) for row in ordered_radius]
        fig, ax = plt.subplots(figsize=(7.2, 4.6))
        ax.plot(x, y, marker="o")
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_xlabel("Maximum endpoint radius (km); missing centroids retained")
        ax.set_ylabel("Candidate edges")
        ax.set_title("Chicago K=2 candidate graph expansion")
        fig.tight_layout()
        path = output_dir / "radius_edge_curve.svg"
        fig.savefig(path)
        plt.close(fig)
        written.append(path.name)

    for curve_type, xlabel in (
        ("radius", "Maximum endpoint radius (km)"),
        ("gamma", "Allowed out-of-screen core incidences Γ"),
    ):
        relevant = [
            row
            for row in rows
            if row["curve_type"] == curve_type and row["width"] is not None
        ]
        by_query: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in relevant:
            by_query[str(row["query"])].append(row)
        for query, query_rows in sorted(by_query.items()):
            ordered = sorted(
                query_rows,
                key=lambda row: math.inf
                if row["parameter_value"] is None
                else float(row["parameter_value"]),
            )
            if curve_type == "radius":
                x = list(range(len(ordered)))
                labels = [str(row["parameter_label"]) for row in ordered]
            else:
                x = [int(row["parameter_value"]) for row in ordered]
                labels = []
            y = [float(row["width"]) for row in ordered]
            fig, ax = plt.subplots(figsize=(7.2, 4.6))
            ax.plot(x, y, marker="o")
            if curve_type == "radius":
                ax.set_xticks(x, labels, rotation=35, ha="right")
            ax.set_xlabel(xlabel)
            unit = str(ordered[0]["unit"])
            ax.set_ylabel(f"Conditional width ({unit})")
            ax.set_title(query.replace("_", " "))
            fig.tight_layout()
            slug = query.replace("_per_core", "")
            path = output_dir / f"{curve_type}_{slug}.svg"
            fig.savefig(path)
            plt.close(fig)
            written.append(path.name)
    return written


def render_report(report: Mapping[str, Any]) -> str:
    cohort = report["cohort"]
    graph = report["logical_graph"]
    lines = [
        "# Chicago K=2 boundary-closed cohort and candidate-support sensitivity",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Dataset: City of Chicago `{DATASET_ID}`, {DATASET_NAME}  ",
        f"Snapshot fingerprint: `{report['snapshot']['revision_fingerprint_sha256']}`",
        "",
        "## Cohort closure",
        "",
        f"The selected core is the released 15-minute bin `{cohort['core_start_local']}` to "
        f"`{cohort['core_end_local']}`. It contains **{cohort['core_rows']}** literal "
        "`Shared Trip Match=true, Trips Pooled=2` rows.",
        "",
        f"The direct overlap-envelope query retrieved **{cohort['candidate_rows']}** target rows: "
        f"**{cohort['buffer_rows']}** boundary-buffer rows plus the core. The snapshot and "
        f"server counts were stable: **{cohort['public_candidate_universe_closure_status']}**.",
        "",
        "This is closure of the candidate universe under the declared public timestamp model. "
        "It is not closure of the actual pooled runs, because Shared Trip ID and partner identity "
        "are not public.",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Metadata stable before/after | `{cohort['snapshot_stable']}` |",
        f"| Server counts stable before/after | `{cohort['server_counts_stable']}` |",
        f"| Core rows recovered in candidate extract | `{cohort['core_subset_verified']}` |",
        f"| Global null-start/end K=2 targets included | `{cohort['indeterminate_timestamp_rows_included']}` ({cohort['indeterminate_timestamp_rows']}) |",
        f"| Hidden run closure | `{cohort['hidden_run_closure_status']}` |",
        "",
        "## Logical temporal graph",
        "",
        f"The logical graph has **{graph['core_nodes']}** core nodes, **{graph['buffer_nodes']}** "
        f"buffer nodes, and **{graph['edge_count']}** candidate edges. Its cover status is "
        f"`{graph['cover_status']}`. This only establishes feasibility of the declared graph.",
        "",
        "## Radius sensitivity",
        "",
        "Edges are retained when both released endpoint-centroid distances are at most the "
        "radius. An edge with missing centroid information is retained at every radius. The "
        "family is nested and ends at the full temporal graph.",
        "",
        "| Radius | Edges | Temporal fraction | Core zero-degree | Cover status |",
        "|---:|---:|---:|---:|---|",
    ]
    for point in report["radius_graph_points"]:
        lines.append(
            f"| {point['parameter_label']} | {point['edge_count']} | "
            f"{point['retained_fraction_of_temporal']:.3f} | "
            f"{point['core_zero_degree_count']} | `{point['cover_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Candidate-miss budget sensitivity",
            "",
            f"The base screen is **{report['gamma_curve']['base_radius_km']} km**. Γ counts "
            "core incidences assigned through temporal edges outside that screen; a core-core "
            "outside edge costs two and a core-buffer outside edge costs one. Γ is a sensitivity "
            "budget, not an estimated miss rate.",
            "",
            "| Γ | Cover status | Mean miles-gap width | Same-dropoff-area width |",
            "|---:|---|---:|---:|",
        ]
    )
    gamma_lookup: dict[int, dict[str, Any]] = defaultdict(dict)
    for row in report["sensitivity_rows"]:
        if row["curve_type"] == "gamma":
            gamma_lookup[int(row["gamma_core_incidences"])][str(row["query"])] = row
    for point in report["gamma_graph_points"]:
        gamma = int(point["gamma_core_incidences"])
        miles = gamma_lookup[gamma].get("mean_absolute_trip_miles_gap_per_core", {})
        dropoff = gamma_lookup[gamma].get(
            "same_dropoff_community_area_fraction_per_core", {}
        )
        miles_width = "—" if miles.get("width") is None else f"{miles['width']:.4g}"
        dropoff_width = "—" if dropoff.get("width") is None else f"{dropoff['width']:.4g}"
        lines.append(
            f"| {gamma} | `{point['cover_status']}` | {miles_width} | {dropoff_width} |"
        )
    lines.extend(
        [
            "",
            "## Audit conclusion",
            "",
            f"Nested-set monotonicity: `{report['monotonicity_audit']['status']}`.  ",
            f"Strongest supported statement: **{report['claim_boundary']['strongest_supported_statement']}**  ",
            f"Prohibited statement: **{report['claim_boundary']['prohibited_statement']}**",
            "",
            "Raw trip rows, raw trip IDs, and selected matching witnesses are not serialized.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot_before = dataset_snapshot(_request_json(_metadata_url()))
    selected = choose_core_bin(
        scan_start=parse_required_datetime(args.scan_start),
        scan_end=parse_required_datetime(args.scan_end),
        min_core_rows=args.min_core_rows,
        max_core_rows=args.max_core_rows,
        max_candidate_rows=args.max_candidate_rows,
        page_size=args.page_size,
    )
    raw_rows, fetch_ledger = fetch_closed_candidate_universe(
        selected, page_size=args.page_size
    )
    snapshot_after = dataset_snapshot(_request_json(_metadata_url()))

    determinate_count_after, _, _ = scalar_count(str(selected["determinate_where"]))
    indeterminate_count_after, _, _ = scalar_count(str(selected["indeterminate_where"]))
    counts_stable = (
        determinate_count_after == int(selected["determinate_count"])
        and indeterminate_count_after == int(selected["indeterminate_count"])
    )
    snapshot_stable = snapshot_before == snapshot_after
    if not snapshot_stable:
        raise LiveDataError("dataset snapshot changed during extraction")
    if not counts_stable:
        raise LiveDataError("candidate counts changed during extraction")

    core_start = selected["core_start"]
    core_end = selected["core_end"]
    rows, row_audit = prepare_rows(raw_rows, core_start=core_start, core_end=core_end)
    core_ids_expected = {
        normalized_text(row.get("trip_id")) for row in selected["core_rows"]
    }
    core_ids_observed = {row.trip_id for row in rows if row.role == "core"}
    core_subset_verified = core_ids_expected == core_ids_observed
    if not core_subset_verified:
        raise LiveDataError("candidate extraction did not recover the exact selected core")
    if row_audit["context_rows"]:
        raise LiveDataError("candidate extract contains unusable target identifiers or literals")

    temporal_edges, temporal_provenance = build_temporal_edges(rows)
    if not temporal_edges:
        raise LiveDataError("logical temporal graph is empty")
    rows_by_index = {row.index: row for row in rows}
    route_radius = {
        edge: edge_route_radius(rows_by_index, edge) for edge in temporal_edges
    }
    radius_values = [*DEFAULT_RADII_KM, None]
    radius_graph_points: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    radius_edge_sets: dict[float | None, list[tuple[int, int]]] = {}
    for radius in radius_values:
        edges, unmeasured = radius_graph(temporal_edges, route_radius, radius)
        radius_edge_sets[radius] = edges
        label = "temporal-only" if radius is None else f"{radius:g} km"
        graph_point, query_rows = solve_curve_point(
            rows=rows,
            edges=edges,
            temporal_edge_count=len(temporal_edges),
            unmeasured_edges=unmeasured,
            curve_type="radius",
            parameter_label=label,
            parameter_value=radius,
            radius_km=radius,
            gamma=None,
            miss_costs=None,
            time_limit_seconds=args.solver_time_limit,
        )
        radius_graph_points.append(asdict(graph_point))
        sensitivity_rows.extend(query_rows)

    base_radius = float(args.base_radius_km)
    base_edges, _ = radius_graph(temporal_edges, route_radius, base_radius)
    base_edge_set = set(base_edges)
    miss_costs = edge_miss_costs(rows, temporal_edges, base_edge_set)
    core_count = row_audit["core_rows"]
    gamma_graph_points: list[dict[str, Any]] = []
    for gamma in gamma_grid(core_count):
        unmeasured = sum(route_radius[edge] is None for edge in temporal_edges)
        graph_point, query_rows = solve_curve_point(
            rows=rows,
            edges=temporal_edges,
            temporal_edge_count=len(temporal_edges),
            unmeasured_edges=unmeasured,
            curve_type="gamma",
            parameter_label=str(gamma),
            parameter_value=float(gamma),
            radius_km=base_radius,
            gamma=gamma,
            miss_costs=miss_costs,
            time_limit_seconds=args.solver_time_limit,
        )
        gamma_graph_points.append(asdict(graph_point))
        sensitivity_rows.extend(query_rows)

    monotonicity = monotonicity_audit(sensitivity_rows)
    if monotonicity["status"] != "PASS":
        raise LiveDataError("nested sensitivity endpoints violated monotonicity")

    full_point = next(point for point in radius_graph_points if point["radius_km"] is None)
    observed_null_timestamp_rows = sum(
        row.released_start is None or row.released_end is None for row in rows
    )
    off_grid_rows = sum(
        row.interval_status == "off_release_grid_timestamp" for row in rows
    )
    closure_status = (
        "PASS_PUBLIC_RELEASE_TEMPORAL_CANDIDATE_UNIVERSE_CLOSED"
        if snapshot_stable
        and counts_stable
        and core_subset_verified
        and int(selected["indeterminate_count"]) == observed_null_timestamp_rows
        and off_grid_rows == 0
        else "FAIL"
    )
    report: dict[str, Any] = {
        "report_version": "chicago-k2-closed-cohort-frontier/v1",
        "generated_at_utc": generated,
        "snapshot": asdict(snapshot_after),
        "extraction": {
            "scan_start_local": args.scan_start,
            "scan_end_local": args.scan_end,
            "selection_algorithm": (
                "highest-count released 15-minute K=2 bin satisfying core integrity, "
                "core/candidate resource caps, and complete core end timestamps"
            ),
            "overlap_envelope_derivation": (
                "For rounding half-width delta=7.5 minutes, any determinate partner of a "
                "core row must satisfy released_start <= max_core_released_end + 2*delta "
                "and released_end >= min_core_released_start - 2*delta. All null-start "
                "or null-end literal Match=true,K=2 rows are appended globally."
            ),
            "scan_group_query_sha256": sha256_text(str(selected["scan_group_query"])),
            "determinate_query_sha256": sha256_text(str(selected["determinate_where"])),
            "indeterminate_query_sha256": sha256_text(str(selected["indeterminate_where"])),
            "fetch_ledger": fetch_ledger,
            "considered_bins": selected["considered_bins"],
            "raw_rows_sha256": stable_raw_rows_hash(raw_rows),
            "raw_rows_serialized": False,
        },
        "cohort": {
            "core_start_local": core_start.isoformat(),
            "core_end_local": core_end.isoformat(),
            "core_rows": row_audit["core_rows"],
            "buffer_rows": row_audit["buffer_rows"],
            "candidate_rows": len(rows),
            "determinate_candidate_rows": int(selected["determinate_count"]),
            "indeterminate_timestamp_rows": int(selected["indeterminate_count"]),
            "lower_released_end_cutoff": selected["lower_end_cutoff"].isoformat(),
            "upper_released_start_cutoff": selected["upper_start_cutoff"].isoformat(),
            "snapshot_stable": snapshot_stable,
            "server_counts_stable": counts_stable,
            "core_subset_verified": core_subset_verified,
            "indeterminate_timestamp_rows_included": (
                int(selected["indeterminate_count"]) == observed_null_timestamp_rows
            ),
            "off_release_grid_rows": off_grid_rows,
            "public_candidate_universe_closure_status": closure_status,
            "hidden_run_closure_status": "NOT_IDENTIFIED_FROM_PUBLIC_ROWS",
            "row_audit": row_audit,
        },
        "logical_graph": {
            "definition": (
                "literal Match=true,K=2 endpoints; at least one core endpoint; "
                "possible closed-interval overlap after +/-7.5 minute release expansion"
            ),
            "core_nodes": row_audit["core_rows"],
            "buffer_nodes": row_audit["buffer_rows"],
            "edge_count": len(temporal_edges),
            "edge_provenance": temporal_provenance,
            "spatially_unmeasured_edges": sum(
                value is None for value in route_radius.values()
            ),
            "cover_status": full_point["cover_status"],
            "partner_coverage_claim": "NOT_ESTIMATED_FROM_PUBLIC_ROWS",
        },
        "radius_graph_points": radius_graph_points,
        "gamma_curve": {
            "base_radius_km": base_radius,
            "base_edge_count": len(base_edges),
            "gamma_definition": (
                "number of core incidences assigned through logical temporal edges "
                "outside the fixed base-radius graph"
            ),
            "gamma_is_estimated_miss_rate": False,
        },
        "gamma_graph_points": gamma_graph_points,
        "sensitivity_rows": sensitivity_rows,
        "monotonicity_audit": monotonicity,
        "claim_boundary": {
            "strongest_supported_statement": (
                "The pinned public release yields a count-closed K=2 temporal candidate "
                "universe for the selected core under the declared timestamp-rounding model, "
                "and query endpoints widen monotonically as candidate support is relaxed."
            ),
            "prohibited_statement": (
                "The true Chicago pooled runs or co-rider partners have been reconstructed, "
                "or the declared candidate graph has measured partner recall."
            ),
        },
        "redaction": {
            "raw_rows_emitted": False,
            "raw_trip_ids_emitted": False,
            "matching_witnesses_emitted": False,
            "outputs_are_aggregate_only": True,
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


def parse_required_datetime(value: str) -> datetime:
    parsed = parse_local_timestamp(value)
    if parsed is None:
        raise argparse.ArgumentTypeError(f"invalid local datetime: {value}")
    return parsed


def write_outputs(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sensitivity_rows = report["sensitivity_rows"]
    write_long_csv(sensitivity_rows, output_dir / "candidate_support_sensitivity.csv")
    graph_rows = [*report["radius_graph_points"], *report["gamma_graph_points"]]
    write_long_csv(graph_rows, output_dir / "candidate_graph_curve.csv")
    plot_files = plot_curves(sensitivity_rows, output_dir)
    compact = dict(report)
    compact.pop("sensitivity_rows", None)
    compact["plot_files"] = plot_files
    (output_dir / "report.json").write_text(
        json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "CHICAGO_K2_CLOSED_COHORT_REPORT.md").write_text(
        render_report(report), encoding="utf-8"
    )


def self_test() -> None:
    now = datetime(2026, 1, 1, 12, 0)
    raw = []
    for index in range(4):
        raw.append(
            {
                "trip_id": f"raw-{index}",
                "trip_start_timestamp": "2026-01-01T12:00:00.000",
                "trip_end_timestamp": "2026-01-01T12:30:00.000",
                "trip_seconds": str(600 + index * 60),
                "trip_miles": str(1 + index),
                "pickup_community_area": "1",
                "dropoff_community_area": str(index % 2),
                "fare": str(10 + index),
                "shared_trip_authorized": "true",
                "shared_trip_match": "true",
                "trips_pooled": "2",
                "pickup_centroid_latitude": "41.88",
                "pickup_centroid_longitude": str(-87.63 + index * 0.001),
                "dropoff_centroid_latitude": "41.90",
                "dropoff_centroid_longitude": str(-87.65 + index * 0.001),
            }
        )
    rows, audit = prepare_rows(
        raw, core_start=now, core_end=now + timedelta(minutes=15)
    )
    edges, _ = build_temporal_edges(rows)
    assert len(edges) == 6
    assert audit["core_rows"] == 4
    zero = [0.0] * len(edges)
    cover = solve_binary_cover_objective(
        rows, edges, zero, maximize=False, time_limit_seconds=10
    )
    assert cover.status == "OPTIMAL_NUMERICAL_MILP"
    rows_by_index = {row.index: row for row in rows}
    miles = query_specs()[0]
    lower, upper, missing = edge_query_coefficients(rows_by_index, rows, edges, miles)
    assert missing == 0 and lower is not None and upper is not None
    minimum = solve_binary_cover_objective(
        rows, edges, lower, maximize=False, time_limit_seconds=10
    )
    maximum = solve_binary_cover_objective(
        rows, edges, upper, maximize=True, time_limit_seconds=10
    )
    assert minimum.value is not None and maximum.value is not None
    assert minimum.value <= maximum.value
    route = {edge: float(edge[1] - edge[0]) for edge in edges}
    small, _ = radius_graph(edges, route, 1.0)
    large, _ = radius_graph(edges, route, 3.0)
    assert set(small) <= set(large)
    base = set(small)
    costs = edge_miss_costs(rows, edges, base)
    full = solve_binary_cover_objective(
        rows,
        edges,
        zero,
        maximize=False,
        miss_costs=costs,
        gamma=4,
        time_limit_seconds=10,
    )
    assert full.status == "OPTIMAL_NUMERICAL_MILP"
    serialized = json.dumps(
        {
            "raw_rows_emitted": False,
            "raw_trip_ids_emitted": False,
            "raw_rows_sha256": stable_raw_rows_hash(raw),
        }
    )
    assert "raw-0" not in serialized
    print("self-test: PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/chicago-k2-frontier"))
    parser.add_argument("--scan-start", default=DEFAULT_SCAN_START)
    parser.add_argument("--scan-end", default=DEFAULT_SCAN_END)
    parser.add_argument("--min-core-rows", type=int, default=12)
    parser.add_argument("--max-core-rows", type=int, default=60)
    parser.add_argument("--max-candidate-rows", type=int, default=5000)
    parser.add_argument("--page-size", type=int, default=5000)
    parser.add_argument("--base-radius-km", type=float, default=2.0)
    parser.add_argument("--solver-time-limit", type=float, default=20.0)
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    scan_start = parse_required_datetime(args.scan_start)
    scan_end = parse_required_datetime(args.scan_end)
    if not scan_start < scan_end:
        raise SystemExit("--scan-start must precede --scan-end")
    if args.min_core_rows < 2 or args.max_core_rows < args.min_core_rows:
        raise SystemExit("invalid core-row limits")
    if args.max_candidate_rows < args.max_core_rows:
        raise SystemExit("max candidate rows must be at least max core rows")
    if args.page_size < 1 or args.page_size > 50_000:
        raise SystemExit("page size must lie in [1,50000]")
    if args.base_radius_km < 0 or args.solver_time_limit <= 0:
        raise SystemExit("radius must be nonnegative and solver time positive")
    report = run(args)
    write_outputs(report, args.output_dir)
    print(render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
