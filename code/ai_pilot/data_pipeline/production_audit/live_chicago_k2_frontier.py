#!/usr/bin/env python3
"""Build a Chicago K=2 public temporal candidate universe and sensitivity curves.

The City of Chicago public TNP table reports ``Shared Trip Match`` and
``Trips Pooled`` but suppresses the ``Shared Trip ID`` that joins transactions
within an empty-to-empty pooled run.  This script therefore distinguishes two
claims:

1. **Public temporal candidate-universe closure.**  For one released 15-minute
   core bin, retrieve every literal ``Match=true, K=2`` row whose released
   start/end envelopes could overlap any core row, plus every target row with a
   null released start or end.  Snapshot and server-count checks make this a
   count-closed, core-incident public temporal candidate universe: a
   boundary-complete candidate superset for the core under the declared public
   timestamp model.
2. **Hidden-run closure is not claimed.**  It remains unidentified because
   partner/run IDs are absent.  Buffer rows' other run-mates are not recursively
   fetched, graph feasibility is not partner-recall evidence, and this object is
   not a union of reconstructed complete pooled runs.

On this public candidate universe, the script computes two nested
candidate-support sensitivity families:

* a geographic radius expansion from strict endpoint compatibility to the full
  temporal graph; and
* a core-incidence budget ``Gamma`` that permits an increasing number of core
  assignments to use measured-distance edges outside a fixed radius.  Edges
  with unmeasured endpoint distance remain in the base graph and cost zero, so
  ``Gamma`` is not a total candidate-miss budget or estimated miss rate.

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
CERTIFIED_ENDPOINT_STATUS = "OPTIMAL_NUMERICAL_MILP"

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


def _request_json(
    url: str,
    *,
    timeout: int = 180,
    attempts: int = 4,
    json_body: Mapping[str, Any] | None = None,
) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    data = canonical_json_bytes(json_body) if json_body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST" if data is not None else "GET",
    )
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


def _soda3_url() -> str:
    return f"{DOMAIN}/api/v3/views/{DATASET_ID}/query.json"


def query_rows(query: str, *, page_size: int = 5000) -> tuple[list[dict[str, Any]], str]:
    """Run one bounded query, trying SODA2 before SODA3."""

    errors: list[str] = []
    for api_name, url, json_body in (
        ("soda2", _soda2_url(query), None),
        (
            "soda3",
            _soda3_url(),
            {
                "query": query,
                "page": {"pageNumber": 1, "pageSize": page_size},
                "includeSynthetic": False,
            },
        ),
    ):
        try:
            payload = _request_json(url, json_body=json_body)
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
    *,
    forced_zero_edges: Sequence[bool] | None = None,
) -> tuple[list[float] | None, list[float] | None, int]:
    core_indices = {row.index for row in rows if row.role == "core"}
    denominator = len(core_indices)
    if denominator == 0:
        raise ValueError("query requires a nonempty core")
    lower: list[float] = []
    upper: list[float] = []
    missing_edges = 0
    if forced_zero_edges is not None and len(forced_zero_edges) != len(edges):
        raise ValueError("forced-zero mask must have one entry per edge")
    for position, edge in enumerate(edges):
        left, right = rows_by_index[edge[0]], rows_by_index[edge[1]]
        interval = spec.coefficient_interval(left, right)
        if interval is None:
            if forced_zero_edges is not None and forced_zero_edges[position]:
                lower.append(0.0)
                upper.append(0.0)
                continue
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
    """Count measured out-of-radius core incidences.

    ``base_edges`` comes from :func:`radius_graph`, which retains every edge
    with unmeasured route radius.  Such an edge therefore costs zero.  A
    measured edge outside the base radius costs two for core-core incidence and
    one for core-buffer incidence.
    """

    core = {row.index for row in rows if row.role == "core"}
    return [
        0
        if edge in base_edges
        else int(edge[0] in core) + int(edge[1] in core)
        for edge in edges
    ]


def certified_endpoint_payload(
    lower: BoundResult, upper: BoundResult
) -> dict[str, Any]:
    """Publish an interval only when both optimization endpoints are certified.

    A replayed incumbent from a time-limited or otherwise unresolved solve is
    useful diagnostic information, but it is not an identified endpoint.  It
    is therefore kept only under an explicitly diagnostic field.
    """

    statuses_certified = (
        lower.status == CERTIFIED_ENDPOINT_STATUS
        and upper.status == CERTIFIED_ENDPOINT_STATUS
    )
    values_finite = (
        lower.value is not None
        and upper.value is not None
        and math.isfinite(float(lower.value))
        and math.isfinite(float(upper.value))
    )
    values_ordered = (
        values_finite and float(lower.value) <= float(upper.value)
    )
    pair_certified = statuses_certified and values_finite and values_ordered
    published_lower = float(lower.value) if pair_certified else None
    published_upper = float(upper.value) if pair_certified else None
    return {
        "lower": published_lower,
        "upper": published_upper,
        "width": (
            published_upper - published_lower
            if published_lower is not None and published_upper is not None
            else None
        ),
        "endpoint_pair_certification": (
            "CERTIFIED_OPTIMAL_PAIR" if pair_certified else "UNCERTIFIED"
        ),
        "diagnostic_lower_nonoptimal_incumbent": (
            float(lower.value)
            if lower.status != CERTIFIED_ENDPOINT_STATUS
            and lower.value is not None
            and math.isfinite(float(lower.value))
            else None
        ),
        "diagnostic_upper_nonoptimal_incumbent": (
            float(upper.value)
            if upper.status != CERTIFIED_ENDPOINT_STATUS
            and upper.value is not None
            and math.isfinite(float(upper.value))
            else None
        ),
    }


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
    if (gamma is None) != (miss_costs is None):
        raise ValueError("gamma and miss_costs must be supplied together")
    stats = graph_degrees(rows, edges)
    zero_objective = [0.0] * len(edges)
    optimization_gamma = gamma
    cover = solve_binary_cover_objective(
        rows,
        edges,
        zero_objective,
        maximize=False,
        miss_costs=miss_costs,
        gamma=optimization_gamma,
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
    forced_zero_edges = (
        [cost > optimization_gamma for cost in miss_costs]
        if miss_costs is not None and optimization_gamma is not None
        else None
    )
    query_rows: list[dict[str, Any]] = []
    for spec in query_specs():
        lower_coefficients, upper_coefficients, missing_edges = edge_query_coefficients(
            rows_by_index,
            rows,
            edges,
            spec,
            forced_zero_edges=forced_zero_edges,
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
                gamma=optimization_gamma,
                time_limit_seconds=time_limit_seconds,
            )
            upper = solve_binary_cover_objective(
                rows,
                edges,
                upper_coefficients,
                maximize=True,
                miss_costs=miss_costs,
                gamma=optimization_gamma,
                time_limit_seconds=time_limit_seconds,
            )
        endpoints = certified_endpoint_payload(lower, upper)
        query_rows.append(
            {
                **asdict(graph_point),
                "query": spec.name,
                "unit": spec.unit,
                **endpoints,
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
                "claim": (
                    "conditional sensitivity over a count-closed, core-incident public "
                    "temporal candidate universe; no hidden-run or partner-recall claim"
                ),
            }
        )
    return graph_point, query_rows


def gamma_grid(core_count: int) -> list[int]:
    candidates = [0, 1, 2, 4, 8, 16, math.ceil(core_count / 4), math.ceil(core_count / 2), core_count]
    return sorted({value for value in candidates if 0 <= value <= core_count})


def monotonicity_audit(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_parameter_labels: Mapping[str, Sequence[str]] | None = None,
    expected_queries: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Audit complete certified endpoint chains, never just available values.

    ``PASS`` means every curve/query chain is nonempty, fully certified at every
    point, finite, internally ordered, and monotone.  ``PARTIAL`` means at least
    one *entire* chain passes those checks while another chain does not.  Empty
    input, all-unavailable endpoints, or a collection with no completely
    certified monotone chain is ``FAIL``.
    """

    violations: list[dict[str, Any]] = []
    certification_failures: list[dict[str, Any]] = []
    malformed_rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    expected_query_set = (
        {str(query) for query in expected_queries}
        if expected_queries is not None
        else None
    )
    expected_curve_set = (
        {str(curve) for curve in expected_parameter_labels}
        if expected_parameter_labels is not None
        else None
    )
    for position, row in enumerate(rows):
        curve_type = row.get("curve_type")
        query = row.get("query")
        if curve_type is None or query is None:
            malformed_rows.append(
                {
                    "row_index": position,
                    "reason": "missing_curve_type_or_query",
                }
            )
            continue
        curve_key = str(curve_type)
        query_key = str(query)
        if expected_curve_set is not None and curve_key not in expected_curve_set:
            malformed_rows.append(
                {
                    "row_index": position,
                    "reason": "unexpected_curve_type",
                    "curve_type": curve_key,
                }
            )
        if expected_query_set is not None and query_key not in expected_query_set:
            malformed_rows.append(
                {
                    "row_index": position,
                    "reason": "unexpected_query",
                    "query": query_key,
                }
            )
        grouped[(curve_key, query_key)].append(row)

    if expected_curve_set is not None and expected_query_set is not None:
        for curve_type in sorted(expected_curve_set):
            for query in sorted(expected_query_set):
                grouped.setdefault((curve_type, query), [])

    def parameter_sort_key(row: Mapping[str, Any]) -> tuple[int, float, str]:
        value = row.get("parameter_value")
        if value is None:
            return 1, math.inf, str(row.get("parameter_label", ""))
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 2, math.inf, str(row.get("parameter_label", ""))
        if not math.isfinite(numeric):
            return 2, math.inf, str(row.get("parameter_label", ""))
        return 0, numeric, str(row.get("parameter_label", ""))

    chain_audits: list[dict[str, Any]] = []
    for (curve_type, query), group in grouped.items():
        ordered = sorted(group, key=parameter_sort_key)
        previous_lower: float | None = None
        previous_upper: float | None = None
        chain_failure_count_before = len(certification_failures)
        chain_violation_count_before = len(violations)
        labels = [str(row.get("parameter_label")) for row in ordered]
        if len(ordered) < 2:
            certification_failures.append(
                {
                    "curve_type": curve_type,
                    "query": query,
                    "reason": "chain_has_fewer_than_two_points",
                    "point_count": len(ordered),
                }
            )
        if len(labels) != len(set(labels)):
            certification_failures.append(
                {
                    "curve_type": curve_type,
                    "query": query,
                    "reason": "duplicate_parameter_label",
                }
            )
        if expected_parameter_labels is not None and curve_type in expected_parameter_labels:
            expected_labels = {
                str(label) for label in expected_parameter_labels[curve_type]
            }
            observed_labels = set(labels)
            if observed_labels != expected_labels:
                certification_failures.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "reason": "incomplete_or_unexpected_parameter_chain",
                        "missing_labels": sorted(expected_labels - observed_labels),
                        "unexpected_labels": sorted(observed_labels - expected_labels),
                    }
                )
        parameter_keys: list[tuple[str, float | None]] = []
        for row in ordered:
            raw_parameter = row.get("parameter_value")
            if raw_parameter is None:
                parameter_keys.append(("none", None))
            else:
                try:
                    parameter_keys.append(("number", float(raw_parameter)))
                except (TypeError, ValueError):
                    parameter_keys.append(("invalid", None))
        if len(parameter_keys) != len(set(parameter_keys)):
            certification_failures.append(
                {
                    "curve_type": curve_type,
                    "query": query,
                    "reason": "duplicate_parameter_value",
                }
            )

        for row in ordered:
            parameter = row.get("parameter_label")
            parameter_value = row.get("parameter_value")
            if parameter_value is not None:
                try:
                    numeric_parameter = float(parameter_value)
                except (TypeError, ValueError):
                    numeric_parameter = math.nan
                if not math.isfinite(numeric_parameter):
                    certification_failures.append(
                        {
                            "curve_type": curve_type,
                            "query": query,
                            "parameter": parameter,
                            "reason": "nonfinite_or_invalid_parameter",
                        }
                    )

            lower = row.get("lower")
            upper = row.get("upper")
            lower_status = row.get("lower_status")
            upper_status = row.get("upper_status")
            if (
                lower_status != CERTIFIED_ENDPOINT_STATUS
                or upper_status != CERTIFIED_ENDPOINT_STATUS
            ):
                certification_failures.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "parameter": parameter,
                        "reason": "nonoptimal_or_missing_solver_status",
                        "lower_status": lower_status,
                        "upper_status": upper_status,
                    }
                )
            if row.get("endpoint_pair_certification") != "CERTIFIED_OPTIMAL_PAIR":
                certification_failures.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "parameter": parameter,
                        "reason": "endpoint_pair_not_marked_certified",
                    }
                )
            if lower is None or upper is None:
                certification_failures.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "parameter": parameter,
                        "reason": "missing_certified_endpoint",
                    }
                )
                continue
            try:
                lower = float(lower)
                upper = float(upper)
            except (TypeError, ValueError):
                certification_failures.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "parameter": parameter,
                        "reason": "nonnumeric_endpoint",
                    }
                )
                continue
            if not math.isfinite(lower) or not math.isfinite(upper):
                certification_failures.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "parameter": parameter,
                        "reason": "nonfinite_endpoint",
                    }
                )
                continue
            width = row.get("width")
            try:
                width = float(width)
            except (TypeError, ValueError):
                certification_failures.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "parameter": parameter,
                        "reason": "missing_or_nonnumeric_width",
                    }
                )
                continue
            if not math.isfinite(width) or not math.isclose(
                width,
                upper - lower,
                rel_tol=1e-7,
                abs_tol=1e-7,
            ):
                certification_failures.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "parameter": parameter,
                        "reason": "nonfinite_or_inconsistent_width",
                    }
                )
                continue
            if lower > upper + 1e-7:
                violations.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "direction": "lower_exceeds_upper",
                        "lower": lower,
                        "upper": upper,
                        "parameter": parameter,
                    }
                )
            if previous_lower is not None and lower > previous_lower + 1e-7:
                violations.append(
                    {
                        "curve_type": curve_type,
                        "query": query,
                        "direction": "lower_increased",
                        "previous": previous_lower,
                        "current": lower,
                        "parameter": parameter,
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
                        "parameter": parameter,
                    }
                )
            previous_lower = lower
            previous_upper = upper

        chain_failure_count = len(certification_failures) - chain_failure_count_before
        chain_violation_count = len(violations) - chain_violation_count_before
        chain_status = (
            "PASS"
            if ordered and chain_failure_count == 0 and chain_violation_count == 0
            else "FAIL"
        )
        chain_audits.append(
            {
                "curve_type": curve_type,
                "query": query,
                "point_count": len(ordered),
                "certification_failure_count": chain_failure_count,
                "violation_count": chain_violation_count,
                "status": chain_status,
            }
        )

    passing_chains = sum(item["status"] == "PASS" for item in chain_audits)
    total_chains = len(chain_audits)
    query_family_audits: list[dict[str, Any]] = []
    for query in sorted({str(item["query"]) for item in chain_audits}):
        family = [item for item in chain_audits if item["query"] == query]
        family_status = (
            "PASS"
            if family and all(item["status"] == "PASS" for item in family)
            else "FAIL"
        )
        query_family_audits.append(
            {
                "query": query,
                "curve_chain_count": len(family),
                "status": family_status,
            }
        )
    passing_query_families = sum(
        item["status"] == "PASS" for item in query_family_audits
    )
    if violations or malformed_rows:
        status = "FAIL"
    elif (
        total_chains > 0
        and passing_chains == total_chains
    ):
        status = "PASS"
    elif passing_chains > 0:
        status = "PARTIAL"
    else:
        status = "FAIL"
    return {
        "expected": (
            "every curve/query chain fully certified; lower nonincreasing and upper "
            "nondecreasing as candidate support expands"
        ),
        "chain_count": total_chains,
        "fully_certified_monotone_chain_count": passing_chains,
        "chain_audits": chain_audits,
        "query_family_count": len(query_family_audits),
        "fully_certified_monotone_query_family_count": passing_query_families,
        "query_family_audits": query_family_audits,
        "certification_failure_count": len(certification_failures),
        "certification_failures": certification_failures,
        "malformed_row_count": len(malformed_rows),
        "malformed_rows": malformed_rows,
        "violation_count": len(violations),
        "violations": violations,
        "status": status,
    }


def endpoint_identity_audit(
    sensitivity_rows: Sequence[Mapping[str, Any]],
    radius_graph_points: Sequence[Mapping[str, Any]],
    gamma_graph_points: Sequence[Mapping[str, Any]],
    *,
    model_rows: Sequence[TripRow],
    temporal_edges: Sequence[tuple[int, int]],
    base_edges: Sequence[tuple[int, int]],
    miss_costs: Sequence[int],
    base_radius_km: float,
    core_count: int,
    tolerance: float = 1e-7,
) -> dict[str, Any]:
    """Verify the two Gamma-family endpoint identities against radius points."""

    mismatches: list[dict[str, Any]] = []
    core_indices = {row.index for row in model_rows if row.role == "core"}
    temporal_edge_set = set(temporal_edges)
    base_edge_set = set(base_edges)
    if len(temporal_edge_set) != len(temporal_edges):
        mismatches.append(
            {
                "identity": "structural_gamma_endpoint_identity",
                "reason": "duplicate_temporal_edges",
            }
        )
    if not base_edge_set <= temporal_edge_set:
        mismatches.append(
            {
                "identity": "structural_gamma_endpoint_identity",
                "reason": "base_edges_not_subset_of_temporal_edges",
            }
        )
    if len(miss_costs) != len(temporal_edges):
        mismatches.append(
            {
                "identity": "structural_gamma_endpoint_identity",
                "reason": "miss_cost_length_mismatch",
                "edge_count": len(temporal_edges),
                "cost_count": len(miss_costs),
            }
        )
    else:
        for edge, observed_cost in zip(temporal_edges, miss_costs):
            core_incidences = int(edge[0] in core_indices) + int(
                edge[1] in core_indices
            )
            expected_cost = 0 if edge in base_edge_set else core_incidences
            if core_incidences not in {1, 2} or observed_cost != expected_cost:
                mismatches.append(
                    {
                        "identity": "structural_gamma_endpoint_identity",
                        "reason": "incorrect_measured_out_of_radius_incidence_cost",
                        "edge": list(edge),
                        "observed_cost": observed_cost,
                        "expected_cost": expected_cost,
                        "core_incidences": core_incidences,
                    }
                )
    if len(core_indices) != core_count:
        mismatches.append(
            {
                "identity": "structural_gamma_endpoint_identity",
                "reason": "core_count_mismatch",
                "observed": len(core_indices),
                "declared": core_count,
            }
        )

    def numeric_equal(left: Any, right: Any) -> bool:
        if left is None or right is None:
            return left is None and right is None
        try:
            left_number = float(left)
            right_number = float(right)
        except (TypeError, ValueError):
            return False
        return (
            math.isfinite(left_number)
            and math.isfinite(right_number)
            and math.isclose(
                left_number,
                right_number,
                rel_tol=tolerance,
                abs_tol=tolerance,
            )
        )

    def unique_point(
        points: Sequence[Mapping[str, Any]],
        predicate: Callable[[Mapping[str, Any]], bool],
        label: str,
    ) -> Mapping[str, Any] | None:
        selected = [point for point in points if predicate(point)]
        if len(selected) != 1:
            mismatches.append(
                {
                    "identity": label,
                    "reason": "expected_exactly_one_graph_point",
                    "observed": len(selected),
                }
            )
            return None
        return selected[0]

    base_graph = unique_point(
        radius_graph_points,
        lambda point: point.get("radius_km") is not None
        and numeric_equal(point.get("radius_km"), base_radius_km),
        "gamma_0_equals_base_radius",
    )
    temporal_graph = unique_point(
        radius_graph_points,
        lambda point: point.get("radius_km") is None,
        "gamma_core_count_equals_temporal_only",
    )
    gamma_zero_graph = unique_point(
        gamma_graph_points,
        lambda point: point.get("gamma_core_incidences") == 0,
        "gamma_0_equals_base_radius",
    )
    gamma_full_graph = unique_point(
        gamma_graph_points,
        lambda point: point.get("gamma_core_incidences") == core_count,
        "gamma_core_count_equals_temporal_only",
    )

    certified_cover_statuses = {
        CERTIFIED_ENDPOINT_STATUS,
        "PROVEN_INFEASIBLE_ISOLATED_CORE",
        "PROVEN_INFEASIBLE_BY_HIGHS",
    }

    def status_class(status: Any) -> str:
        if status in {
            "PROVEN_INFEASIBLE_ISOLATED_CORE",
            "PROVEN_INFEASIBLE_BY_HIGHS",
        }:
            return "CERTIFIED_INFEASIBLE"
        return str(status)

    for identity, left_graph, right_graph in (
        (
            "gamma_0_equals_base_radius",
            base_graph,
            gamma_zero_graph,
        ),
        (
            "gamma_core_count_equals_temporal_only",
            temporal_graph,
            gamma_full_graph,
        ),
    ):
        if left_graph is None or right_graph is None:
            continue
        left_status = left_graph.get("cover_status")
        right_status = right_graph.get("cover_status")
        if (
            status_class(left_status) != status_class(right_status)
            or left_status not in certified_cover_statuses
            or right_status not in certified_cover_statuses
        ):
            mismatches.append(
                {
                    "identity": identity,
                    "reason": "cover_status_mismatch_or_uncertified",
                    "left": left_status,
                    "right": right_status,
                }
            )

    def indexed_rows(
        curve_type: str,
        predicate: Callable[[Mapping[str, Any]], bool],
        label: str,
    ) -> dict[str, Mapping[str, Any]]:
        selected = [
            row
            for row in sensitivity_rows
            if row.get("curve_type") == curve_type and predicate(row)
        ]
        indexed: dict[str, Mapping[str, Any]] = {}
        duplicates: list[str] = []
        for row in selected:
            query = str(row.get("query"))
            if query in indexed:
                duplicates.append(query)
            indexed[query] = row
        if duplicates:
            mismatches.append(
                {
                    "identity": label,
                    "reason": "duplicate_query_rows",
                    "queries": sorted(set(duplicates)),
                }
            )
        return indexed

    base_rows = indexed_rows(
        "radius",
        lambda row: row.get("radius_km") is not None
        and numeric_equal(row.get("radius_km"), base_radius_km),
        "gamma_0_equals_base_radius",
    )
    temporal_rows = indexed_rows(
        "radius",
        lambda row: row.get("radius_km") is None,
        "gamma_core_count_equals_temporal_only",
    )
    gamma_zero_rows = indexed_rows(
        "gamma",
        lambda row: row.get("gamma_core_incidences") == 0,
        "gamma_0_equals_base_radius",
    )
    gamma_full_rows = indexed_rows(
        "gamma",
        lambda row: row.get("gamma_core_incidences") == core_count,
        "gamma_core_count_equals_temporal_only",
    )

    acceptable_unavailable_statuses = {
        "UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES",
        "PROVEN_INFEASIBLE_ISOLATED_CORE",
        "PROVEN_INFEASIBLE_BY_HIGHS",
    }
    comparisons = 0
    for identity, left_rows, right_rows in (
        ("gamma_0_equals_base_radius", base_rows, gamma_zero_rows),
        (
            "gamma_core_count_equals_temporal_only",
            temporal_rows,
            gamma_full_rows,
        ),
    ):
        if set(left_rows) != set(right_rows) or not left_rows:
            mismatches.append(
                {
                    "identity": identity,
                    "reason": "query_set_mismatch_or_empty",
                    "left_queries": sorted(left_rows),
                    "right_queries": sorted(right_rows),
                }
            )
            continue
        for query in sorted(left_rows):
            comparisons += 1
            left = left_rows[query]
            right = right_rows[query]
            left_statuses = (left.get("lower_status"), left.get("upper_status"))
            right_statuses = (right.get("lower_status"), right.get("upper_status"))
            status_pair_certified = (
                left_statuses
                == (
                    CERTIFIED_ENDPOINT_STATUS,
                    CERTIFIED_ENDPOINT_STATUS,
                )
                and right_statuses
                == (
                    CERTIFIED_ENDPOINT_STATUS,
                    CERTIFIED_ENDPOINT_STATUS,
                )
                and left.get("endpoint_pair_certification")
                == "CERTIFIED_OPTIMAL_PAIR"
                and right.get("endpoint_pair_certification")
                == "CERTIFIED_OPTIMAL_PAIR"
            )
            status_pair_comparably_unavailable = (
                tuple(status_class(status) for status in left_statuses)
                == tuple(status_class(status) for status in right_statuses)
                and all(
                    status in acceptable_unavailable_statuses
                    for status in (*left_statuses, *right_statuses)
                )
            )
            if not (
                status_pair_certified or status_pair_comparably_unavailable
            ):
                mismatches.append(
                    {
                        "identity": identity,
                        "query": query,
                        "reason": "endpoint_status_mismatch_or_uncertified",
                        "left": left_statuses,
                        "right": right_statuses,
                    }
                )
                continue
            for field in ("lower", "upper", "width"):
                if not numeric_equal(left.get(field), right.get(field)):
                    mismatches.append(
                        {
                            "identity": identity,
                            "query": query,
                            "reason": f"{field}_mismatch",
                            "left": left.get(field),
                            "right": right.get(field),
                        }
                    )

    return {
        "expected": (
            "Gamma=0 equals the base-radius feasible set; Gamma=core_count "
            "equals the unconstrained temporal-only feasible set"
        ),
        "base_radius_km": base_radius_km,
        "core_count": core_count,
        "structural_basis": (
            "cost zero iff an edge is in the base-radius graph; otherwise cost "
            "equals its one or two core endpoints. Core cover equalities fix total "
            "selected core incidence at core_count, so Gamma=core_count is redundant."
        ),
        "query_comparison_count": comparisons,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "status": "PASS" if not mismatches else "FAIL",
    }


def public_temporal_closure_audit(
    *,
    snapshot_stable: bool,
    server_counts_stable: bool,
    core_subset_verified: bool,
    candidate_rows: int,
    expected_candidate_rows: int,
    observed_indeterminate_rows: int,
    expected_indeterminate_rows: int,
    off_release_grid_rows: int,
    released_chronology_impossible_rows: int,
    context_rows: int,
    full_temporal_cover_status: str,
) -> dict[str, Any]:
    """Certify the declared public temporal universe, failing every check closed."""

    checks = {
        "snapshot_stable": bool(snapshot_stable),
        "server_counts_stable": bool(server_counts_stable),
        "core_subset_verified": bool(core_subset_verified),
        "candidate_count_matches_pinned_count": (
            candidate_rows == expected_candidate_rows
        ),
        "global_null_start_or_end_targets_included": (
            observed_indeterminate_rows == expected_indeterminate_rows
        ),
        "no_off_release_grid_rows": off_release_grid_rows == 0,
        "no_released_chronology_impossible_rows": (
            released_chronology_impossible_rows == 0
        ),
        "no_unusable_context_rows": context_rows == 0,
        "full_temporal_cover_optimal": (
            full_temporal_cover_status == CERTIFIED_ENDPOINT_STATUS
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "definition": (
            "count-closed, core-incident public temporal candidate universe; "
            "boundary-complete core candidate superset under released timestamps"
        ),
        "checks": checks,
        "failed_checks": failed,
        "status": "PASS" if not failed else "FAIL",
        "hidden_run_closure_claimed": False,
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
        ax.set_title("Chicago K=2 public temporal candidate graph expansion")
        fig.tight_layout()
        path = output_dir / "radius_edge_curve.svg"
        fig.savefig(path)
        plt.close(fig)
        written.append(path.name)

    for curve_type, xlabel in (
        ("radius", "Maximum endpoint radius (km)"),
        ("gamma", "Allowed measured out-of-radius core incidences Γ"),
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
        "# Chicago K=2 public temporal candidate-universe closure and sensitivity",
        "",
        f"Generated UTC: `{report['generated_at_utc']}`  ",
        f"Dataset: City of Chicago `{DATASET_ID}`, {DATASET_NAME}  ",
        f"Snapshot fingerprint: `{report['snapshot']['revision_fingerprint_sha256']}`",
        "",
        "## Public temporal candidate-universe closure",
        "",
        f"The selected core is the released 15-minute bin `{cohort['core_start_local']}` to "
        f"`{cohort['core_end_local']}`. It contains **{cohort['core_rows']}** literal "
        "`Shared Trip Match=true, Trips Pooled=2` rows.",
        "",
        f"The direct overlap-envelope query retrieved **{cohort['candidate_rows']}** target rows: "
        f"**{cohort['buffer_rows']}** boundary-buffer rows plus the core. This is a "
        "boundary-complete candidate superset for core-incident public temporal edges. "
        f"Closure status: **{cohort['public_temporal_candidate_universe_closure_status']}**.",
        "",
        "The object is count-closed under the declared released-timestamp model. It is "
        "explicitly not hidden-run closure: Shared Trip ID and partner identity are not public, "
        "buffer rows' other run-mates are not recursively fetched, and the candidate set is not "
        "a union of reconstructed complete pooled runs.",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Metadata stable before/after | `{cohort['snapshot_stable']}` |",
        f"| Server counts stable before/after | `{cohort['server_counts_stable']}` |",
        f"| Core rows recovered in candidate extract | `{cohort['core_subset_verified']}` |",
        f"| Global null-start/end K=2 targets included | `{cohort['indeterminate_timestamp_rows_included']}` ({cohort['indeterminate_timestamp_rows']}) |",
        f"| Released chronology impossible rows | `{cohort['released_chronology_impossible_rows']}` |",
        f"| Full temporal cover optimal | `{cohort['closure_audit']['checks']['full_temporal_cover_optimal']}` |",
        f"| Hidden run closure | `{cohort['hidden_run_closure_status']}` |",
        "",
        "This is a one-bin, adaptively selected smoke test, not evidence for the Chicago "
        "trip population. Stable metadata and counts protect extraction consistency but do "
        "not create an immutable transaction-level snapshot. Query coefficients are computed "
        "from released public fields and are not latent exact trip attributes.",
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
        "## Measured out-of-radius incidence sensitivity",
        "",
        f"The base radius is **{report['gamma_curve']['base_radius_km']} km**. Γ counts "
        "core incidences assigned through edges whose measured endpoint distance exceeds that "
        "radius; a measured out-of-radius core-core edge costs two and a core-buffer edge costs "
        "one. Edges with unmeasured endpoint distance are retained at every radius and cost zero. "
        "Therefore Γ is neither a total candidate-miss budget nor an estimated miss rate.",
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
            f"Endpoint identities: `{report['endpoint_identity_audit']['status']}`.  ",
            f"Monotonicity claim: **{report['claim_boundary']['monotonicity_statement']}**  ",
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
    off_grid_rows = sum(
        row.interval_status == "off_release_grid_timestamp" for row in rows
    )
    released_chronology_impossible_rows = sum(
        row.interval_status == "released_chronology_impossible" for row in rows
    )
    if off_grid_rows:
        raise LiveDataError("public temporal closure failed: off-grid released timestamps")
    if released_chronology_impossible_rows:
        raise LiveDataError(
            "public temporal closure failed: released chronology is impossible"
        )

    temporal_edges, temporal_provenance = build_temporal_edges(rows)
    if not temporal_edges:
        raise LiveDataError("logical temporal graph is empty")
    rows_by_index = {row.index: row for row in rows}
    route_radius = {
        edge: edge_route_radius(rows_by_index, edge) for edge in temporal_edges
    }
    base_radius = float(args.base_radius_km)
    radius_values: list[float | None] = [
        *sorted({*DEFAULT_RADII_KM, base_radius}),
        None,
    ]
    radius_graph_points: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    for radius in radius_values:
        edges, unmeasured = radius_graph(temporal_edges, route_radius, radius)
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

    base_edges, _ = radius_graph(temporal_edges, route_radius, base_radius)
    base_edge_set = set(base_edges)
    miss_costs = edge_miss_costs(rows, temporal_edges, base_edge_set)
    core_count = row_audit["core_rows"]
    gamma_graph_points: list[dict[str, Any]] = []
    gamma_values = gamma_grid(core_count)
    for gamma in gamma_values:
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

    full_point = next(point for point in radius_graph_points if point["radius_km"] is None)
    observed_null_timestamp_rows = sum(
        row.released_start is None or row.released_end is None for row in rows
    )
    closure_audit = public_temporal_closure_audit(
        snapshot_stable=snapshot_stable,
        server_counts_stable=counts_stable,
        core_subset_verified=core_subset_verified,
        candidate_rows=len(rows),
        expected_candidate_rows=int(selected["candidate_count"]),
        observed_indeterminate_rows=observed_null_timestamp_rows,
        expected_indeterminate_rows=int(selected["indeterminate_count"]),
        off_release_grid_rows=off_grid_rows,
        released_chronology_impossible_rows=released_chronology_impossible_rows,
        context_rows=int(row_audit["context_rows"]),
        full_temporal_cover_status=str(full_point["cover_status"]),
    )
    if closure_audit["status"] != "PASS":
        raise LiveDataError(
            "public temporal candidate-universe closure failed: "
            + ", ".join(closure_audit["failed_checks"])
        )

    endpoint_identities = endpoint_identity_audit(
        sensitivity_rows,
        radius_graph_points,
        gamma_graph_points,
        model_rows=rows,
        temporal_edges=temporal_edges,
        base_edges=base_edges,
        miss_costs=miss_costs,
        base_radius_km=base_radius,
        core_count=core_count,
    )
    if endpoint_identities["status"] != "PASS":
        raise LiveDataError("Gamma/radius endpoint identity audit failed")

    monotonicity = monotonicity_audit(
        sensitivity_rows,
        expected_parameter_labels={
            "radius": [
                "temporal-only" if radius is None else f"{radius:g} km"
                for radius in radius_values
            ],
            "gamma": [str(gamma) for gamma in gamma_values],
        },
        expected_queries=[spec.name for spec in query_specs()],
    )
    if monotonicity["status"] == "FAIL":
        raise LiveDataError(
            "no complete, certified, monotone sensitivity query chain remains"
        )

    if monotonicity["status"] == "PASS":
        monotonicity_statement = (
            "Every declared curve/query chain is fully certified and monotone."
        )
        sensitivity_clause = (
            "all certified query intervals widen monotonically as candidate support "
            "is relaxed"
        )
    else:
        monotonicity_statement = (
            f"Only {monotonicity['fully_certified_monotone_chain_count']} of "
            f"{monotonicity['chain_count']} entire curve/query chains are fully "
            "certified and monotone, covering "
            f"{monotonicity['fully_certified_monotone_query_family_count']} of "
            f"{monotonicity['query_family_count']} complete query families; no "
            "universal monotonicity claim is made."
        )
        sensitivity_clause = (
            "monotonic widening is supported only for the complete certified chains "
            "identified by the audit"
        )
    report: dict[str, Any] = {
        "report_version": "chicago-k2-public-temporal-candidate-universe/v2",
        "generated_at_utc": generated,
        "snapshot": asdict(snapshot_after),
        "extraction": {
            "scan_start_local": args.scan_start,
            "scan_end_local": args.scan_end,
            "selection_algorithm": (
                "adaptive smoke-test selection of the highest-count released 15-minute "
                "K=2 bin satisfying core integrity, core/candidate resource caps, and "
                "complete core end timestamps; not a population-representative sample"
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
            "released_chronology_impossible_rows": (
                released_chronology_impossible_rows
            ),
            "public_temporal_candidate_universe_closure_status": closure_audit[
                "status"
            ],
            "closure_audit": closure_audit,
            "hidden_run_closure_status": "NOT_IDENTIFIED_AND_NOT_CLAIMED",
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
            "partner_coverage_claim": "NOT_ESTIMATED_OR_IDENTIFIED_FROM_PUBLIC_ROWS",
        },
        "radius_graph_points": radius_graph_points,
        "gamma_curve": {
            "base_radius_km": base_radius,
            "base_edge_count": len(base_edges),
            "gamma_definition": (
                "number of core incidences assigned through temporal edges whose "
                "measured endpoint distance exceeds the fixed base radius"
            ),
            "unmeasured_distance_edges_retained_and_cost_zero": True,
            "gamma_is_total_candidate_miss_budget": False,
            "gamma_is_estimated_miss_rate": False,
        },
        "gamma_graph_points": gamma_graph_points,
        "sensitivity_rows": sensitivity_rows,
        "monotonicity_audit": monotonicity,
        "endpoint_identity_audit": endpoint_identities,
        "claim_boundary": {
            "monotonicity_statement": monotonicity_statement,
            "strongest_supported_statement": (
                "For one adaptively selected 15-minute smoke-test core, this metadata/count-"
                "stable extraction yields a count-closed, core-incident K=2 public temporal "
                "candidate universe under the declared timestamp-rounding model; "
                f"{sensitivity_clause}."
            ),
            "prohibited_statement": (
                "The true Chicago pooled runs or co-rider partners have been reconstructed; "
                "the boundary buffer is recursively run-closed; the graph has measured "
                "partner recall; or this one selected bin establishes a Chicago-population "
                "effect."
            ),
            "released_field_scope": (
                "Query coefficients use released public trip fields and their missing-data "
                "semantics; they are not claims about latent exact fare, duration, distance, "
                "or location values."
            ),
            "snapshot_scope": (
                "Stable metadata and server counts pin extraction consistency; they do not "
                "constitute a transaction-level immutable snapshot guarantee."
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
    (output_dir / "CHICAGO_K2_PUBLIC_TEMPORAL_FRONTIER_REPORT.md").write_text(
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
    if (
        not math.isfinite(args.base_radius_km)
        or not math.isfinite(args.solver_time_limit)
        or args.base_radius_km < 0
        or args.solver_time_limit <= 0
    ):
        raise SystemExit("radius must be nonnegative and solver time positive")
    report = run(args)
    write_outputs(report, args.output_dir)
    print(render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
