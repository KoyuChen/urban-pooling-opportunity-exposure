#!/usr/bin/env python3
"""Live, aggregate Chicago release-operator and pairing-identification audit.

This audit deliberately separates three objects that are easy to conflate:

* the confidential fields TNPs report to the City;
* the transformed public trip table; and
* the hidden run pairing that the public table does not release.

For one fixed K=2 core bin, the script builds the same snapshot-relative public
temporal candidate universe used by the frontier audit.  It then fetches every
public trip contributing to any released start/end bin represented in that
universe, without filtering on shared service.  This all-trip layer is required
for even a consistency audit of the documented tract privacy cells.

The output is intentionally an identification-boundary audit.  Public blanks
are never inverted to LOW tract-count literals, no raw row or trip identifier
is serialized, and neither a full hidden-run world nor City implementation
validation is claimed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


DATASET_ID = "6dvr-xwnh"
DATASET_NAME = "Transportation Network Providers - Trips (2025-)"
DOMAIN = "https://data.cityofchicago.org"
USER_AGENT = "urban-pooling-chicago-release-operator-audit/0.1"
CHICAGO_TZ = ZoneInfo("America/Chicago")
RELEASE_BIN_MINUTES = 15
ROUNDING_HALF_MINUTES = 7.5
TARGET_PREDICATE = "shared_trip_match = true AND trips_pooled = 2"
DEFAULT_CORE_START = "2026-01-13T17:30:00"
STATUS_PARTIAL = "PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY"
STATUS_NOT_IDENTIFIED = "NOT_IDENTIFIED_FROM_PUBLIC_ROWS"
OPTIMAL_MILP = "OPTIMAL_NUMERICAL_MILP"

DOCUMENTATION = (
    {
        "id": "public_dataset",
        "url": (
            "https://data.cityofchicago.org/Transportation/"
            "Transportation-Network-Providers-Trips-2025-/6dvr-xwnh/about_data"
        ),
        "licensed_implication": (
            "released start/end timestamps are rounded to the nearest 15 minutes"
        ),
    },
    {
        "id": "public_columns",
        "url": "https://data.cityofchicago.org/api/views/6dvr-xwnh/columns.json",
        "licensed_implication": (
            "released centroid is the published tract center or, when tract detail "
            "is suppressed, the published community-area center"
        ),
    },
    {
        "id": "privacy_method",
        "url": (
            "https://data.cityofchicago.org/stories/s/"
            "How-Chicago-Protects-Privacy-in-TNP-and-Taxi-Open-/82d7-i4i2/"
        ),
        "licensed_implication": (
            "a tract-by-15-minute aggregation with two or fewer unique trips is "
            "widened to community-area level for both trip ends"
        ),
    },
    {
        "id": "tract_rule_clarification",
        "url": (
            "https://data.cityofchicago.org/stories/s/"
            "Census-Tract-Rules-for-Taxi-and-TNP-Datasets-7-29-/28mt-8asw/"
        ),
        "licensed_implication": (
            "released fine-tract counts cannot be naively read as complete latent "
            "cell counts because the paired-end rule can coarsen both ends"
        ),
    },
    {
        "id": "confidential_reporting_schema",
        "url": "https://chicago.github.io/tnp-reporting-manual/trip/",
        "licensed_implication": (
            "TNPs report a Shared Trip ID shared by every transaction in one "
            "complete empty-to-empty run; that field is absent from the public table"
        ),
    },
    {
        "id": "change_notice",
        "url": (
            "https://data.cityofchicago.org/stories/s/"
            "Change-Notice-Transportation-Network-Provider-Data/wmdt-6h9e/"
        ),
        "licensed_implication": (
            "recent periods may be published at generally 99%+ completeness and "
            "past periods can later be updated"
        ),
    },
)

PUBLIC_FIELDS = (
    "trip_id",
    "trip_start_timestamp",
    "trip_end_timestamp",
    "pickup_census_tract",
    "dropoff_census_tract",
    "pickup_community_area",
    "dropoff_community_area",
    "pickup_centroid_latitude",
    "pickup_centroid_longitude",
    "dropoff_centroid_latitude",
    "dropoff_centroid_longitude",
    "shared_trip_match",
    "trips_pooled",
)

PUBLIC_LINKAGE_FIELDS_FORBIDDEN = (
    "shared_trip_id",
    "driver_id",
    "driver_license_number",
    "vehicle_identification_number",
    "vin",
    "provider",
    "company",
    "partner_id",
)


class AuditError(RuntimeError):
    """The extraction or a fail-closed audit requirement did not hold."""


@dataclass(frozen=True)
class Snapshot:
    dataset_id: str
    rows_updated_at: Any
    view_last_modified: Any
    publication_date: Any
    schema_sha256: str
    required_column_descriptions_sha256: str
    revision_fingerprint_sha256: str
    public_column_count: int


@dataclass(frozen=True)
class ParsedRow:
    index: int
    trip_id: str
    released_start: datetime | None
    released_end: datetime | None
    matched: bool | None
    trips_pooled: int | None
    pickup_tract: str | None
    dropoff_tract: str | None
    pickup_area: str | None
    dropoff_area: str | None
    pickup_lat: float | None
    pickup_lon: float | None
    dropoff_lat: float | None
    dropoff_lon: float | None

    @property
    def target_k2(self) -> bool:
        return self.matched is True and self.trips_pooled == 2

    @property
    def route_coordinates_complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.pickup_lat,
                self.pickup_lon,
                self.dropoff_lat,
                self.dropoff_lon,
            )
        )


@dataclass(frozen=True)
class Edge:
    u: int
    v: int
    unmeasured_core_cost: int


@dataclass(frozen=True)
class CoverSolution:
    status: str
    selected_edge_indices: tuple[int, ...]
    objective_value: float | None
    mip_gap: float | None
    max_replay_residual: float | None
    message: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalized_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def finite_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_bool(value: Any) -> bool | None:
    text = normalized_text(value)
    if text is None:
        return None
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    return None


def parse_positive_integer(value: Any) -> int | None:
    number = finite_float(value)
    if number is None or number < 1 or not number.is_integer():
        return None
    return int(number)


def parse_local_timestamp(value: Any) -> datetime | None:
    text = normalized_text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(CHICAGO_TZ).replace(tzinfo=None)
    return parsed


def on_release_grid(value: datetime) -> bool:
    return (
        value.minute % RELEASE_BIN_MINUTES == 0
        and value.second == 0
        and value.microsecond == 0
    )


def ambiguous_chicago_local_time(value: datetime) -> bool:
    first = value.replace(tzinfo=CHICAGO_TZ, fold=0).utcoffset()
    second = value.replace(tzinfo=CHICAGO_TZ, fold=1).utcoffset()
    return first != second


def format_socrata_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat(timespec="seconds") + ".000"


def _request_json(
    url: str,
    *,
    timeout: int,
    attempts: int,
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
    raise AuditError(f"request failed for {url}: " + " | ".join(errors))


def query_rows(
    query: str,
    *,
    page_size: int,
    timeout: int,
    attempts: int,
) -> tuple[list[dict[str, Any]], str]:
    soda2 = f"{DOMAIN}/resource/{DATASET_ID}.json?" + urllib.parse.urlencode(
        {"$query": query}
    )
    soda3 = f"{DOMAIN}/api/v3/views/{DATASET_ID}/query.json"
    failures: list[str] = []
    for api, url, body in (
        ("soda2", soda2, None),
        (
            "soda3",
            soda3,
            {
                "query": query,
                "page": {"pageNumber": 1, "pageSize": page_size},
                "includeSynthetic": False,
            },
        ),
    ):
        try:
            payload = _request_json(
                url, timeout=timeout, attempts=attempts, json_body=body
            )
            if not isinstance(payload, list) or not all(
                isinstance(row, dict) for row in payload
            ):
                raise AuditError(f"{api} returned a non-row-list payload")
            return payload, api
        except Exception as exc:  # pragma: no cover - network dependent
            failures.append(f"{api}: {type(exc).__name__}: {exc}")
    raise AuditError("both Socrata query paths failed: " + " || ".join(failures))


def scalar_count(
    where: str, *, page_size: int, timeout: int, attempts: int
) -> tuple[int, str, str]:
    query = f"SELECT count(*) AS n WHERE {where}"
    rows, api = query_rows(
        query, page_size=min(page_size, 10), timeout=timeout, attempts=attempts
    )
    if len(rows) != 1 or "n" not in rows[0]:
        raise AuditError(f"unexpected count response for {where!r}")
    return int(rows[0]["n"]), api, query


def paged_select(
    *,
    where: str,
    expected_count: int,
    page_size: int,
    timeout: int,
    attempts: int,
) -> tuple[list[dict[str, Any]], list[str], str]:
    base = (
        f"SELECT {', '.join(PUBLIC_FIELDS)} WHERE {where} "
        "ORDER BY trip_start_timestamp, trip_end_timestamp, trip_id"
    )
    rows: list[dict[str, Any]] = []
    apis: list[str] = []
    offset = 0
    while offset < expected_count:
        limit = min(page_size, expected_count - offset)
        chunk, api = query_rows(
            f"{base} LIMIT {limit} OFFSET {offset}",
            page_size=limit,
            timeout=timeout,
            attempts=attempts,
        )
        if not chunk:
            raise AuditError(
                f"empty deterministic page at {offset}/{expected_count}"
            )
        rows.extend(chunk)
        apis.append(api)
        offset += len(chunk)
        if len(chunk) < limit and offset < expected_count:
            raise AuditError(
                f"short deterministic page at {offset}/{expected_count}"
            )
    if len(rows) != expected_count:
        raise AuditError("server count and deterministic fetch disagree")
    return rows, apis, base


def snapshot_from_metadata(metadata: Any) -> Snapshot:
    if not isinstance(metadata, dict) or metadata.get("id") != DATASET_ID:
        raise AuditError("dataset metadata id mismatch")
    columns = metadata.get("columns")
    if not isinstance(columns, list) or not columns:
        raise AuditError("dataset metadata contains no columns")
    normalized: list[dict[str, Any]] = []
    descriptions: list[dict[str, Any]] = []
    for fallback_position, column in enumerate(columns):
        if not isinstance(column, dict):
            raise AuditError("malformed column metadata")
        field = column.get("fieldName")
        if not isinstance(field, str) or not field:
            raise AuditError("column metadata lacks fieldName")
        normalized.append(
            {
                "position": column.get("position", fallback_position),
                "field_name": field,
                "data_type": column.get("dataTypeName"),
            }
        )
        if field in PUBLIC_FIELDS:
            descriptions.append(
                {
                    "field_name": field,
                    "description": column.get("description"),
                }
            )
    normalized.sort(key=lambda item: (item["position"], item["field_name"]))
    descriptions.sort(key=lambda item: item["field_name"])
    names = {item["field_name"] for item in normalized}
    missing = sorted(set(PUBLIC_FIELDS) - names)
    if missing:
        raise AuditError(f"required public fields are missing: {missing}")
    forbidden = sorted(set(PUBLIC_LINKAGE_FIELDS_FORBIDDEN) & names)
    if forbidden:
        raise AuditError(
            "public schema unexpectedly contains linkage fields; semantics need "
            f"re-audit: {forbidden}"
        )
    schema_hash = sha256_json(normalized)
    description_hash = sha256_json(descriptions)
    core = {
        "dataset_id": DATASET_ID,
        "rows_updated_at": metadata.get("rowsUpdatedAt"),
        "view_last_modified": metadata.get("viewLastModified"),
        "publication_date": metadata.get("publicationDate"),
        "schema_sha256": schema_hash,
        "required_column_descriptions_sha256": description_hash,
        "public_column_count": len(normalized),
    }
    return Snapshot(
        **core,
        revision_fingerprint_sha256=sha256_json(core),
    )


def fetch_snapshot(*, timeout: int, attempts: int) -> Snapshot:
    metadata = _request_json(
        f"{DOMAIN}/api/views/{DATASET_ID}.json",
        timeout=timeout,
        attempts=attempts,
    )
    return snapshot_from_metadata(metadata)


def parse_rows(raw_rows: Sequence[Mapping[str, Any]]) -> tuple[ParsedRow, ...]:
    parsed: list[ParsedRow] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(raw_rows):
        trip_id = normalized_text(raw.get("trip_id"))
        if trip_id is None:
            raise AuditError("blank public trip_id in a count-closed extraction")
        if trip_id in identifiers:
            raise AuditError("duplicate public trip_id in a count-closed extraction")
        identifiers.add(trip_id)
        start = parse_local_timestamp(raw.get("trip_start_timestamp"))
        end = parse_local_timestamp(raw.get("trip_end_timestamp"))
        for value in (start, end):
            if value is None:
                continue
            if not on_release_grid(value):
                raise AuditError("off-grid released timestamp")
            if ambiguous_chicago_local_time(value):
                raise AuditError("DST-ambiguous released local timestamp")
        if start is not None and end is not None and end < start:
            raise AuditError("released end precedes released start")
        parsed.append(
            ParsedRow(
                index=index,
                trip_id=trip_id,
                released_start=start,
                released_end=end,
                matched=parse_bool(raw.get("shared_trip_match")),
                trips_pooled=parse_positive_integer(raw.get("trips_pooled")),
                pickup_tract=normalized_text(raw.get("pickup_census_tract")),
                dropoff_tract=normalized_text(raw.get("dropoff_census_tract")),
                pickup_area=normalized_text(raw.get("pickup_community_area")),
                dropoff_area=normalized_text(raw.get("dropoff_community_area")),
                pickup_lat=finite_float(raw.get("pickup_centroid_latitude")),
                pickup_lon=finite_float(raw.get("pickup_centroid_longitude")),
                dropoff_lat=finite_float(raw.get("dropoff_centroid_latitude")),
                dropoff_lon=finite_float(raw.get("dropoff_centroid_longitude")),
            )
        )
    return tuple(parsed)


def endpoint_mask(row: ParsedRow, endpoint: str) -> tuple[bool, bool, bool, bool]:
    if endpoint == "pickup":
        tract, area, lat, lon = (
            row.pickup_tract,
            row.pickup_area,
            row.pickup_lat,
            row.pickup_lon,
        )
    elif endpoint == "dropoff":
        tract, area, lat, lon = (
            row.dropoff_tract,
            row.dropoff_area,
            row.dropoff_lat,
            row.dropoff_lon,
        )
    else:
        raise ValueError("endpoint must be pickup or dropoff")
    return tract is not None, area is not None, lat is not None, lon is not None


def summarize_endpoint_masks(
    rows: Sequence[ParsedRow], endpoint: str
) -> dict[str, Any]:
    cross_tab: Counter[str] = Counter()
    area_without_coordinates = 0
    coordinates_without_area = 0
    partial_coordinates = 0
    tract_without_coordinates = 0
    for row in rows:
        tract, area, lat, lon = endpoint_mask(row, endpoint)
        complete = lat and lon
        key = (
            f"tract={int(tract)}|area={int(area)}|"
            f"coordinates_complete={int(complete)}"
        )
        cross_tab[key] += 1
        area_without_coordinates += int(area and not complete)
        coordinates_without_area += int(complete and not area)
        partial_coordinates += int(lat != lon)
        tract_without_coordinates += int(tract and not complete)
    return {
        "rows": len(rows),
        "cross_tab": dict(sorted(cross_tab.items())),
        "area_without_coordinates_rows": area_without_coordinates,
        "coordinates_without_area_rows": coordinates_without_area,
        "partial_lat_lon_rows": partial_coordinates,
        "tract_without_coordinates_rows": tract_without_coordinates,
        "area_coordinate_presence_masks_equal": (
            area_without_coordinates == 0 and coordinates_without_area == 0
        ),
    }


def temporal_compatible(first: ParsedRow, second: ParsedRow, *, strict: bool) -> bool:
    if (
        first.released_start is None
        or first.released_end is None
        or second.released_start is None
        or second.released_end is None
    ):
        return True
    delta = timedelta(minutes=ROUNDING_HALF_MINUTES)
    latest_start = max(first.released_start - delta, second.released_start - delta)
    earliest_end = min(first.released_end + delta, second.released_end + delta)
    return latest_start < earliest_end if strict else latest_start <= earliest_end


def build_candidate_edges(
    rows: Sequence[ParsedRow], core_indices: Sequence[int], *, strict: bool
) -> tuple[Edge, ...]:
    core = set(core_indices)
    if not core:
        raise AuditError("candidate graph has no core rows")
    edges: list[Edge] = []
    for u in range(len(rows)):
        for v in range(u + 1, len(rows)):
            if u not in core and v not in core:
                continue
            if not temporal_compatible(rows[u], rows[v], strict=strict):
                continue
            core_endpoints = int(u in core) + int(v in core)
            unmeasured = not (
                rows[u].route_coordinates_complete
                and rows[v].route_coordinates_complete
            )
            edges.append(
                Edge(
                    u=u,
                    v=v,
                    unmeasured_core_cost=core_endpoints if unmeasured else 0,
                )
            )
    return tuple(edges)


def _validate_cover(
    edges: Sequence[Edge], core_indices: Sequence[int], selected: Sequence[int]
) -> float:
    core = set(core_indices)
    degrees: Counter[int] = Counter()
    for edge_index in selected:
        edge = edges[edge_index]
        degrees[edge.u] += 1
        degrees[edge.v] += 1
    residual = 0.0
    nodes = {endpoint for edge in edges for endpoint in (edge.u, edge.v)} | core
    for node in nodes:
        if node in core:
            residual = max(residual, abs(degrees[node] - 1.0))
        else:
            residual = max(residual, max(0.0, degrees[node] - 1.0))
    return residual


def solve_cover(
    edges: Sequence[Edge],
    core_indices: Sequence[int],
    *,
    objective: Sequence[float] | None = None,
    maximize: bool = False,
    exclude_selected: Sequence[int] | None = None,
    time_limit: float = 60.0,
) -> CoverSolution:
    core = tuple(sorted(set(core_indices)))
    if not edges:
        return CoverSolution("INFEASIBLE_EMPTY_GRAPH", (), None, None, None, "")
    nodes = sorted({endpoint for edge in edges for endpoint in (edge.u, edge.v)})
    row_by_node = {node: row for row, node in enumerate(nodes)}
    matrix = lil_matrix((len(nodes), len(edges)), dtype=float)
    for column, edge in enumerate(edges):
        matrix[row_by_node[edge.u], column] = 1.0
        matrix[row_by_node[edge.v], column] = 1.0
    lower = np.array([1.0 if node in core else 0.0 for node in nodes])
    upper = np.ones(len(nodes), dtype=float)
    constraints: list[LinearConstraint] = [
        LinearConstraint(matrix.tocsr(), lower, upper)
    ]
    if exclude_selected is not None:
        exclusion = lil_matrix((1, len(edges)), dtype=float)
        for edge_index in exclude_selected:
            exclusion[0, edge_index] = 1.0
        constraints.append(
            LinearConstraint(
                exclusion.tocsr(),
                np.array([-np.inf]),
                np.array([max(0, len(tuple(exclude_selected)) - 1)], dtype=float),
            )
        )
    costs = np.zeros(len(edges), dtype=float)
    if objective is not None:
        if len(objective) != len(edges):
            raise ValueError("objective length must equal edge count")
        costs = np.asarray(objective, dtype=float)
    signed_costs = -costs if maximize else costs
    result = milp(
        c=signed_costs,
        integrality=np.ones(len(edges), dtype=int),
        bounds=Bounds(np.zeros(len(edges)), np.ones(len(edges))),
        constraints=constraints,
        options={"time_limit": float(time_limit), "mip_rel_gap": 0.0},
    )
    if result.status == 2:
        return CoverSolution("INFEASIBLE", (), None, None, None, str(result.message))
    if result.status != 0 or result.x is None:
        return CoverSolution(
            "UNRESOLVED_NUMERICAL_MILP",
            (),
            None,
            finite_float(getattr(result, "mip_gap", None)),
            None,
            str(result.message),
        )
    selected = tuple(
        index for index, value in enumerate(result.x) if float(value) >= 0.5
    )
    residual = _validate_cover(edges, core, selected)
    if residual != 0.0:
        return CoverSolution(
            "INVALID_NUMERICAL_INCUMBENT",
            (),
            None,
            finite_float(getattr(result, "mip_gap", None)),
            residual,
            str(result.message),
        )
    raw_value = float(sum(costs[index] for index in selected))
    return CoverSolution(
        OPTIMAL_MILP,
        selected,
        raw_value,
        finite_float(getattr(result, "mip_gap", None)),
        residual,
        str(result.message),
    )


def core_assignment_hamming(
    edges: Sequence[Edge],
    core_indices: Sequence[int],
    first: Sequence[int],
    second: Sequence[int],
) -> int:
    core = set(core_indices)

    def assignments(selected: Sequence[int]) -> dict[int, int]:
        result: dict[int, int] = {}
        for edge_index in selected:
            edge = edges[edge_index]
            if edge.u in core:
                result[edge.u] = edge.v
            if edge.v in core:
                result[edge.v] = edge.u
        return result

    left = assignments(first)
    right = assignments(second)
    if set(left) != core or set(right) != core:
        raise AuditError("cover replay did not assign every core row")
    return sum(left[node] != right[node] for node in core)


def pairing_certificate(
    rows: Sequence[ParsedRow],
    core_indices: Sequence[int],
    *,
    solver_time_limit: float,
) -> dict[str, Any]:
    closed_edges = build_candidate_edges(rows, core_indices, strict=False)
    strict_edges = build_candidate_edges(rows, core_indices, strict=True)
    touch_only = len(closed_edges) - len(strict_edges)
    first = solve_cover(
        strict_edges, core_indices, time_limit=solver_time_limit
    )
    alternative = (
        solve_cover(
            strict_edges,
            core_indices,
            exclude_selected=first.selected_edge_indices,
            time_limit=solver_time_limit,
        )
        if first.status == OPTIMAL_MILP
        else CoverSolution("NOT_RUN", (), None, None, None, "")
    )
    hamming = None
    if first.status == OPTIMAL_MILP and alternative.status == OPTIMAL_MILP:
        hamming = core_assignment_hamming(
            strict_edges,
            core_indices,
            first.selected_edge_indices,
            alternative.selected_edge_indices,
        )
    unmeasured_costs = [edge.unmeasured_core_cost for edge in strict_edges]
    minimum_unmeasured = solve_cover(
        strict_edges,
        core_indices,
        objective=unmeasured_costs,
        time_limit=solver_time_limit,
    )
    maximum_unmeasured = solve_cover(
        strict_edges,
        core_indices,
        objective=unmeasured_costs,
        maximize=True,
        time_limit=solver_time_limit,
    )
    distinct = (
        first.status == OPTIMAL_MILP
        and alternative.status == OPTIMAL_MILP
        and hamming is not None
        and hamming > 0
    )
    return {
        "closed_outer_interval_edge_count": len(closed_edges),
        "strict_positive_overlap_edge_count": len(strict_edges),
        "boundary_touch_only_edge_count": touch_only,
        "strict_graph_cover_status": first.status,
        "alternative_strict_cover_status": alternative.status,
        "strict_core_cover_multiplicity_status": (
            "CERTIFIED_TWO_DISTINCT_STRICT_CORE_COVERS"
            if distinct
            else "NOT_CERTIFIED"
        ),
        "cover_a_selected_edge_count": (
            len(first.selected_edge_indices) if first.status == OPTIMAL_MILP else None
        ),
        "cover_b_selected_edge_count": (
            len(alternative.selected_edge_indices)
            if alternative.status == OPTIMAL_MILP
            else None
        ),
        "cores_changed_between_displayed_covers": hamming,
        "conditional_on_strict_released_time_envelope_graph": True,
        "release_map_pairing_invariant_under_documented_abstraction": True,
        "release_map_pairing_invariance_scope": (
            "DOCUMENTED_PUBLIC_FIELD_ABSTRACTION_NOT_FULL_CITY_IMPLEMENTATION"
        ),
        "full_hidden_worlds_constructed": False,
        "shared_exact_timestamp_witness_constructed": False,
        "remaining_buffer_run_completion_constructed": False,
        "partner_identification_status": STATUS_NOT_IDENTIFIED,
        "hidden_partner_identification_claim": "NONE",
        "release_prunable_unmeasured_edges": 0,
        "unmeasured_strict_edge_count": sum(
            edge.unmeasured_core_cost > 0 for edge in strict_edges
        ),
        "unmeasured_core_incidences_min_status": minimum_unmeasured.status,
        "unmeasured_core_incidences_min": minimum_unmeasured.objective_value,
        "unmeasured_core_incidences_max_status": maximum_unmeasured.status,
        "unmeasured_core_incidences_max": maximum_unmeasured.objective_value,
        "max_certified_mip_gap": max(
            (
                value
                for value in (
                    first.mip_gap,
                    alternative.mip_gap,
                    minimum_unmeasured.mip_gap,
                    maximum_unmeasured.mip_gap,
                )
                if value is not None
            ),
            default=None,
        ),
        "max_certified_replay_residual": max(
            (
                value
                for value in (
                    first.max_replay_residual,
                    alternative.max_replay_residual,
                    minimum_unmeasured.max_replay_residual,
                    maximum_unmeasured.max_replay_residual,
                )
                if value is not None
            ),
            default=None,
        ),
        "witnesses_serialized": False,
    }


def documentary_nonidentification_certificate() -> dict[str, Any]:
    return {
        "minimum_abstract_witness_nodes": 4,
        "scope": "ABSTRACT_FOUR_ROW_CONSTRUCTION_NOT_COHORT_COMPLETION",
        "world_a_confidential_pairing": "(c1,b1),(c2,b2)",
        "world_b_confidential_pairing": "(c1,b2),(c2,b1)",
        "fixed_between_worlds": [
            "passenger-trip exact times and locations",
            "provider identity",
            "released timestamps",
            "tract/community-area/centroid release values",
            "privacy cell counts and missingness masks",
            "Shared Trip Match=true and Trips Pooled=2",
        ],
        "confidential_linkages_allowed_to_change": [
            "Shared Trip ID assignment",
            "vehicle and driver linkage needed to realize each empty-to-empty run",
        ],
        "same_documented_public_release": True,
        "different_hidden_pairing": True,
        "full_city_implementation_validated": False,
        "logical_conclusion": (
            "DOCUMENTED_PUBLIC_FIELD_MAP_DOES_NOT_ENCODE_SHARED_TRIP_ID"
        ),
    }


def _public_id_set_sha256(rows: Sequence[ParsedRow]) -> str:
    return sha256_json(sorted(row.trip_id for row in rows))


def _raw_rows_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    return sha256_json(list(rows))


def _in_literal(values: Sequence[datetime]) -> str:
    if not values:
        raise AuditError("release-cell timestamp set must be nonempty")
    return "(" + ",".join(
        f"'{format_socrata_timestamp(value)}'" for value in sorted(set(values))
    ) + ")"


def build_report(
    *,
    snapshot_before: Snapshot,
    snapshot_after: Snapshot,
    core_start: datetime,
    core_raw: Sequence[Mapping[str, Any]],
    candidate_raw: Sequence[Mapping[str, Any]],
    contributor_raw: Sequence[Mapping[str, Any]],
    expected_candidate_count: int,
    confirmed_candidate_count: int,
    expected_contributor_count: int,
    confirmed_contributor_count: int,
    candidate_api_paths: Sequence[str],
    contributor_api_paths: Sequence[str],
    generated_at_utc: str,
    solver_time_limit: float,
) -> dict[str, Any]:
    if snapshot_before != snapshot_after:
        raise AuditError("dataset snapshot changed during extraction")
    if expected_candidate_count != confirmed_candidate_count:
        raise AuditError("candidate server count changed during extraction")
    if expected_contributor_count != confirmed_contributor_count:
        raise AuditError("all-trip contributor server count changed during extraction")
    if len(candidate_raw) != expected_candidate_count:
        raise AuditError("candidate fetch is not server-count closed")
    if len(contributor_raw) != expected_contributor_count:
        raise AuditError("all-trip contributor fetch is not server-count closed")

    core = parse_rows(core_raw)
    candidates = parse_rows(candidate_raw)
    contributors = parse_rows(contributor_raw)
    if not core or not all(row.target_k2 for row in core):
        raise AuditError("core is empty or contains a nonliteral K=2/match row")
    if not all(row.target_k2 for row in candidates):
        raise AuditError("candidate universe contains a nonliteral K=2/match row")
    core_end = core_start + timedelta(minutes=RELEASE_BIN_MINUTES)
    if any(
        row.released_start is None
        or not core_start <= row.released_start < core_end
        for row in core
    ):
        raise AuditError("core rows do not match the fixed released bin")
    core_ids = {row.trip_id for row in core}
    candidate_id_to_index = {row.trip_id: index for index, row in enumerate(candidates)}
    if not core_ids <= set(candidate_id_to_index):
        raise AuditError("candidate universe does not exactly recover every core row")
    core_indices = tuple(candidate_id_to_index[trip_id] for trip_id in core_ids)

    contributor_ids = {row.trip_id for row in contributors}
    determinate_candidate_ids = {
        row.trip_id
        for row in candidates
        if row.released_start is not None or row.released_end is not None
    }
    if not determinate_candidate_ids <= contributor_ids:
        raise AuditError("all-trip release-cell universe omits a determinate candidate")

    candidate_masks = {
        endpoint: summarize_endpoint_masks(candidates, endpoint)
        for endpoint in ("pickup", "dropoff")
    }
    contributor_masks = {
        endpoint: summarize_endpoint_masks(contributors, endpoint)
        for endpoint in ("pickup", "dropoff")
    }
    pairing = pairing_certificate(
        candidates, core_indices, solver_time_limit=solver_time_limit
    )
    null_start_or_end = sum(
        row.released_start is None or row.released_end is None for row in candidates
    )
    documentary = documentary_nonidentification_certificate()
    docs_payload = list(DOCUMENTATION)

    report = {
        "report_version": "chicago-release-operator-live-audit/v1",
        "generated_at_utc": generated_at_utc,
        "overall_status": STATUS_PARTIAL,
        "dataset": {
            "id": DATASET_ID,
            "name": DATASET_NAME,
            "snapshot": asdict(snapshot_before),
            "snapshot_stable_during_extraction": True,
            "historical_rows_may_later_change": True,
            "public_linkage_fields_present": False,
            "shared_trip_id_public": False,
        },
        "documentation": {
            "pins": docs_payload,
            "pins_sha256": sha256_json(docs_payload),
            "live_document_content_fetched": False,
            "pins_are_versioned_reference_declarations_not_content_attestations": True,
            "documented_tract_k": 3,
            "documented_low_upper": 2,
            "documented_time_rounding_minutes": 15,
            "city_implementation_validated": False,
            "converse_licensed": False,
            "low_literals_emitted": 0,
        },
        "extraction": {
            "core_start_local": core_start.isoformat(),
            "core_end_local": core_end.isoformat(),
            "core_rows": len(core),
            "candidate_rows": len(candidates),
            "candidate_null_start_or_end_rows": null_start_or_end,
            "all_trip_release_cell_contributor_rows": len(contributors),
            "candidate_count_closed": True,
            "all_public_contributors_count_closed": True,
            "snapshot_relative_only": True,
            "candidate_api_paths": sorted(set(candidate_api_paths)),
            "contributor_api_paths": sorted(set(contributor_api_paths)),
            "candidate_id_set_sha256": _public_id_set_sha256(candidates),
            "contributor_id_set_sha256": _public_id_set_sha256(contributors),
            "candidate_raw_rows_sha256": _raw_rows_sha256(candidate_raw),
            "contributor_raw_rows_sha256": _raw_rows_sha256(contributor_raw),
            "raw_rows_serialized": False,
            "raw_trip_ids_serialized": False,
        },
        "release_masks": {
            "candidate_rows": candidate_masks,
            "all_trip_contributor_rows": contributor_masks,
            "blank_cause_identified_from_public_release": False,
            "blank_to_low_inversion_permitted": False,
            "centroid_null_implies_outside_chicago": False,
            "centroid_null_licenses_finite_radius_exclusion": False,
        },
        "pairing_identification": {
            **pairing,
            "abstract_release_map_noninjectivity_witness": documentary,
            "hidden_run_closure": "NOT_IDENTIFIED_AND_NOT_CLAIMED",
            "partner_recall_identified": False,
        },
        "candidate_support_consequence": {
            "status": "NO_NEW_NECESSARY_SPATIAL_EDGE_DELETIONS",
            "release_prunable_unmeasured_edges": 0,
            "finite_radius_policy": "RETAIN_ALL_SPATIALLY_UNMEASURED_EDGES",
            "measured_centroid_radius_classification": (
                "ANALYST_CANDIDATE_SUPPORT_SENSITIVITY_NOT_NECESSARY_COMPATIBILITY"
            ),
            "recommended_next_axis": (
                "Lambda = selected core incidences through spatially unmeasured edges"
            ),
        },
        "claim_boundary": {
            "supported": (
                "snapshot-relative count closure of the public temporal candidate "
                "universe and all public rows contributing to its released endpoint "
                "bins; documented one-way release semantics; an abstract "
                "release-map noninjectivity witness; and conditional strict-graph "
                "core-cover multiplicity"
            ),
            "not_supported": (
                "City production-code fidelity, latent tract-cell reconstruction, "
                "blank-cause identification, hidden-run closure, partner identity or "
                "recall, and any finite spatial support rule for missing centroids"
            ),
        },
    }
    serialized = canonical_json_bytes(report)
    for raw in (*core, *candidates, *contributors):
        if raw.trip_id.encode("utf-8") in serialized:
            raise AuditError("raw trip identifier leaked into aggregate report")
    report["report_sha256_without_self_hash"] = hashlib.sha256(serialized).hexdigest()
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    extraction = report["extraction"]
    pairing = report["pairing_identification"]
    pickup = report["release_masks"]["candidate_rows"]["pickup"]
    dropoff = report["release_masks"]["candidate_rows"]["dropoff"]
    return f"""# Chicago public release-operator and pairing audit

Generated: {report['generated_at_utc']}  
Overall status: `{report['overall_status']}`

## Result

The public extraction is snapshot-relative and count-closed for the K=2
temporal candidates and for every public trip contributing to their released
endpoint bins. The audit does **not** validate the City's private production
transformation. It emits zero LOW tract-count literals and never interprets a
public blank as a privacy cell without independent evidence.

| Quantity | Result |
|---|---:|
| Core rows | {extraction['core_rows']} |
| K=2 public temporal candidates | {extraction['candidate_rows']} |
| All-trip endpoint-bin contributors | {extraction['all_trip_release_cell_contributor_rows']} |
| Candidate rows with a null time endpoint | {extraction['candidate_null_start_or_end_rows']} |
| Strict-positive-overlap edges | {pairing['strict_positive_overlap_edge_count']} |
| Boundary-touch-only edges | {pairing['boundary_touch_only_edge_count']} |
| Strict graph cover | `{pairing['strict_graph_cover_status']}` |
| Alternative strict cover | `{pairing['alternative_strict_cover_status']}` |
| Core assignments changed between displayed covers | {pairing['cores_changed_between_displayed_covers']} |
| Pickup area without complete coordinates | {pickup['area_without_coordinates_rows']} |
| Dropoff area without complete coordinates | {dropoff['area_without_coordinates_rows']} |

## Identification boundary

Conditional on the strict released-time-envelope core-cover graph, the graph
certificate is `{pairing['strict_core_cover_multiplicity_status']}`. The two
displayed covers differ on
{pairing['cores_changed_between_displayed_covers']} of 60 core assignments.
This establishes substantial graph-model ambiguity, not two fully constructed
Chicago hidden-run worlds: the audit does not construct common exact timestamp
witnesses, vehicle/provider feasibility, or a complete pairing of the remaining
buffer rows.

A separate abstract four-row construction shows that the documented public
field map can remain unchanged while confidential run/vehicle linkage changes.
That abstraction does not validate the City's private implementation or prove
a cohort-level full-world completion. Hidden partner identity remains
`{pairing['partner_identification_status']}` rather than recovered.

## Spatial consequence

Release suppression does not license any new deletion of an edge with
unmeasured centroid distance. A centroid blank can reflect an outside-Chicago
endpoint or unavailable source data; tract coarsening usually publishes a
community-area centroid instead. The fail-closed finite-radius policy is to
retain every spatially unmeasured edge. Radius and Gamma remain
candidate-support sensitivities, not necessary partner-compatibility rules.

## Claim boundary

Supported: {report['claim_boundary']['supported']}.

Not supported: {report['claim_boundary']['not_supported']}.
"""


def run_live(args: argparse.Namespace) -> dict[str, Any]:
    core_start = datetime.fromisoformat(args.core_start)
    if core_start.tzinfo is not None or not on_release_grid(core_start):
        raise AuditError("core-start must be a timezone-naive 15-minute grid value")
    if ambiguous_chicago_local_time(core_start):
        raise AuditError("core-start is DST ambiguous")
    core_end = core_start + timedelta(minutes=RELEASE_BIN_MINUTES)

    request = {
        "page_size": args.page_size,
        "timeout": args.request_timeout,
        "attempts": args.request_attempts,
    }
    snapshot_before = fetch_snapshot(
        timeout=args.request_timeout, attempts=args.request_attempts
    )
    core_where = (
        f"trip_start_timestamp >= '{format_socrata_timestamp(core_start)}' "
        f"AND trip_start_timestamp < '{format_socrata_timestamp(core_end)}' "
        f"AND {TARGET_PREDICATE}"
    )
    core_count, _core_count_api, _core_count_query = scalar_count(
        core_where, **request
    )
    if core_count <= 0:
        raise AuditError("fixed core bin contains no literal K=2/match rows")
    core_raw, _core_apis, _core_base = paged_select(
        where=core_where, expected_count=core_count, **request
    )
    parsed_core = parse_rows(core_raw)
    if any(
        row.released_start is None or row.released_end is None for row in parsed_core
    ):
        raise AuditError("core contains null released time endpoints")
    lower_end = min(row.released_start for row in parsed_core if row.released_start) - timedelta(
        minutes=2 * ROUNDING_HALF_MINUTES
    )
    upper_start = max(row.released_end for row in parsed_core if row.released_end) + timedelta(
        minutes=2 * ROUNDING_HALF_MINUTES
    )
    candidate_where = (
        f"{TARGET_PREDICATE} AND (("
        "trip_start_timestamp IS NOT NULL AND trip_end_timestamp IS NOT NULL "
        f"AND trip_start_timestamp <= '{format_socrata_timestamp(upper_start)}' "
        f"AND trip_end_timestamp >= '{format_socrata_timestamp(lower_end)}') "
        "OR trip_start_timestamp IS NULL OR trip_end_timestamp IS NULL)"
    )
    candidate_count, _candidate_count_api, _candidate_count_query = scalar_count(
        candidate_where, **request
    )
    if candidate_count > args.max_candidate_rows:
        raise AuditError(
            f"candidate count {candidate_count} exceeds max {args.max_candidate_rows}"
        )
    candidate_raw, candidate_apis, _candidate_base = paged_select(
        where=candidate_where, expected_count=candidate_count, **request
    )
    candidates = parse_rows(candidate_raw)
    starts = sorted(
        {row.released_start for row in candidates if row.released_start is not None}
    )
    ends = sorted(
        {row.released_end for row in candidates if row.released_end is not None}
    )
    contributor_where = (
        f"trip_start_timestamp IN {_in_literal(starts)} OR "
        f"trip_end_timestamp IN {_in_literal(ends)}"
    )
    contributor_count, _contributor_count_api, _contributor_count_query = scalar_count(
        contributor_where, **request
    )
    if contributor_count > args.max_contributor_rows:
        raise AuditError(
            f"contributor count {contributor_count} exceeds max "
            f"{args.max_contributor_rows}"
        )
    contributor_raw, contributor_apis, _contributor_base = paged_select(
        where=contributor_where, expected_count=contributor_count, **request
    )
    confirmed_candidate_count, _api, _query = scalar_count(
        candidate_where, **request
    )
    confirmed_contributor_count, _api2, _query2 = scalar_count(
        contributor_where, **request
    )
    snapshot_after = fetch_snapshot(
        timeout=args.request_timeout, attempts=args.request_attempts
    )
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return build_report(
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        core_start=core_start,
        core_raw=core_raw,
        candidate_raw=candidate_raw,
        contributor_raw=contributor_raw,
        expected_candidate_count=candidate_count,
        confirmed_candidate_count=confirmed_candidate_count,
        expected_contributor_count=contributor_count,
        confirmed_contributor_count=confirmed_contributor_count,
        candidate_api_paths=candidate_apis,
        contributor_api_paths=contributor_apis,
        generated_at_utc=generated_at,
        solver_time_limit=args.solver_time_limit,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/chicago-release-operator-audit"))
    parser.add_argument("--core-start", default=DEFAULT_CORE_START)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-candidate-rows", type=int, default=5000)
    parser.add_argument("--max-contributor-rows", type=int, default=100000)
    parser.add_argument("--request-timeout", type=int, default=90)
    parser.add_argument("--request-attempts", type=int, default=3)
    parser.add_argument("--solver-time-limit", type=float, default=60.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_live(args)
    except Exception as exc:
        print(f"release-operator audit failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "release_operator_audit.json"
    markdown_path = args.output_dir / "REPORT.md"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "overall_status": report["overall_status"],
        "candidate_rows": report["extraction"]["candidate_rows"],
        "all_trip_contributors": report["extraction"]["all_trip_release_cell_contributor_rows"],
        "strict_cover_multiplicity": report["pairing_identification"]["strict_core_cover_multiplicity_status"],
        "output_dir": str(args.output_dir),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
