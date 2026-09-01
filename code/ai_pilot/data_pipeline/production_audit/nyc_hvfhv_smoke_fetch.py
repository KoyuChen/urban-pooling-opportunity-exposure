"""Count-reconciled NYC Open Data extraction for the HVFHV smoke test."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from nyc_hvfhv_smoke_types import (
    DATASET_ID,
    DOMAIN,
    FIELDS,
    TARGET,
    LiveDataError,
    canon,
    dt,
    fmt,
    required_dt,
    sha,
    text,
)


def request_json(
    url: str,
    *,
    body: Mapping[str, Any] | None = None,
    timeout: int = 120,
) -> Any:
    headers = {
        "Accept": "application/json",
        "User-Agent": "nyc-hvfhv-frontier/0.1",
    }
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    payload = canon(body) if body is not None else None
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=payload,
        headers=headers,
        method="POST" if payload else "GET",
    )
    errors: list[str] = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt < 2:
                time.sleep(2**attempt)
    raise LiveDataError("request failed: " + " | ".join(errors))


def query_rows(query: str, *, page_size: int) -> tuple[list[dict[str, Any]], str]:
    url = f"{DOMAIN}/resource/{DATASET_ID}.json?" + urllib.parse.urlencode(
        {"$query": query}
    )
    errors: list[str] = []
    try:
        rows = request_json(url)
        if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
            return rows, "soda2"
        errors.append("soda2 returned non-row payload")
    except Exception as exc:  # pragma: no cover - network dependent
        errors.append(f"soda2 {type(exc).__name__}: {exc}")
    try:
        rows = request_json(
            f"{DOMAIN}/api/v3/views/{DATASET_ID}/query.json",
            body={
                "query": query,
                "page": {"pageNumber": 1, "pageSize": page_size},
            },
        )
        if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
            return rows, "soda3"
        errors.append("soda3 returned non-row payload")
    except Exception as exc:  # pragma: no cover - network dependent
        errors.append(f"soda3 {type(exc).__name__}: {exc}")
    raise LiveDataError("both Socrata APIs failed: " + " || ".join(errors))


def count(where: str) -> tuple[int, str, str]:
    query = f"SELECT count(*) AS n WHERE {where}"
    rows, api = query_rows(query, page_size=10)
    if len(rows) != 1 or "n" not in rows[0]:
        raise LiveDataError(f"bad count response: {rows!r}")
    return int(rows[0]["n"]), api, query


def select(
    fields: Sequence[str],
    where: str,
    order: str,
    expected: int,
    cap: int,
) -> tuple[list[dict[str, Any]], str, str]:
    if expected > cap:
        raise LiveDataError(f"query count {expected} exceeds cap {cap}")
    query = (
        f"SELECT {', '.join(fields)} WHERE {where} "
        f"ORDER BY {order} LIMIT {expected}"
    )
    rows, api = query_rows(query, page_size=max(1, expected))
    if len(rows) != expected:
        raise LiveDataError(
            f"count/fetch mismatch: expected {expected}, got {len(rows)}"
        )
    return rows, api, query


def snapshot() -> dict[str, Any]:
    metadata = request_json(f"{DOMAIN}/api/views/{DATASET_ID}.json")
    if not isinstance(metadata, dict) or metadata.get("id") != DATASET_ID:
        raise LiveDataError("metadata ID mismatch")
    columns = metadata.get("columns")
    if not isinstance(columns, list):
        raise LiveDataError("metadata has no columns")
    schema = sorted(
        (str(column.get("fieldName")), str(column.get("dataTypeName")))
        for column in columns
        if isinstance(column, dict)
    )
    missing = sorted(set(FIELDS) - {field for field, _kind in schema})
    if missing:
        raise LiveDataError(f"required fields absent: {missing}")
    output = {
        "dataset_id": DATASET_ID,
        "dataset_name": metadata.get("name"),
        "rows_updated_at": metadata.get("rowsUpdatedAt"),
        "view_last_modified": metadata.get("viewLastModified"),
        "publication_date": metadata.get("publicationDate"),
        "schema_sha256": sha(schema),
    }
    output["revision_fingerprint_sha256"] = sha(output)
    return output


def windows(
    start: datetime,
    end: datetime,
    hours: float,
) -> list[tuple[datetime, datetime]]:
    result: list[tuple[datetime, datetime]] = []
    step = timedelta(hours=hours)
    cursor = start
    while cursor < end:
        upper = min(end, cursor + step)
        result.append((cursor, upper))
        cursor = upper
    return result


def multiset(rows: Sequence[Mapping[str, Any]]) -> Counter[bytes]:
    return Counter(canon(dict(row)) for row in rows)


def choose_and_fetch(args: argparse.Namespace) -> dict[str, Any]:
    start = required_dt(args.scan_start)
    end = required_dt(args.scan_end)
    order = (
        "pickup_datetime, dropoff_datetime, hvfhs_license_num, "
        "pulocationid, dolocationid"
    )
    considered: list[dict[str, Any]] = []
    for lower_window, upper_window in windows(start, end, args.scan_window_hours):
        where = (
            f"pickup_datetime >= '{fmt(lower_window)}' "
            f"AND pickup_datetime < '{fmt(upper_window)}' "
            f"AND {TARGET} "
            "AND pickup_datetime IS NOT NULL "
            "AND dropoff_datetime IS NOT NULL"
        )
        scan_count, scan_count_api, scan_count_query = count(where)
        item = {
            "start": lower_window.isoformat(),
            "end": upper_window.isoformat(),
            "rows": scan_count,
        }
        considered.append(item)
        if scan_count < args.min_core_rows or scan_count > args.max_scan_rows:
            item["status"] = "outside_scan_caps"
            continue
        scan_rows, scan_api, scan_query = select(
            FIELDS,
            where,
            order,
            scan_count,
            args.max_scan_rows,
        )
        groups: dict[tuple[str, datetime], list[dict[str, Any]]] = defaultdict(list)
        for row in scan_rows:
            provider = text(row.get("hvfhs_license_num"))
            pickup = dt(row.get("pickup_datetime"))
            dropoff = dt(row.get("dropoff_datetime"))
            if (
                provider is None
                or pickup is None
                or dropoff is None
                or dropoff < pickup
            ):
                continue
            bin_start = pickup.replace(
                minute=(pickup.minute // 15) * 15,
                second=0,
                microsecond=0,
            )
            groups[(provider, bin_start)].append(dict(row))
        ordered_groups = sorted(
            groups.items(),
            key=lambda group: (-len(group[1]), group[0][1], group[0][0]),
        )
        for (provider, core_start), provisional_core in ordered_groups:
            if not args.min_core_rows <= len(provisional_core) <= args.max_core_rows:
                continue
            core_end = core_start + timedelta(minutes=15)
            provider_literal = provider.replace("'", "''")
            core_where = (
                f"hvfhs_license_num = '{provider_literal}' "
                f"AND pickup_datetime >= '{fmt(core_start)}' "
                f"AND pickup_datetime < '{fmt(core_end)}' "
                f"AND {TARGET}"
            )
            core_count, core_count_api, core_count_query = count(core_where)
            if core_count != len(provisional_core):
                continue
            core_rows, core_api, core_query = select(
                FIELDS,
                core_where,
                order,
                core_count,
                args.max_core_rows,
            )
            pickups = [dt(row.get("pickup_datetime")) for row in core_rows]
            dropoffs = [dt(row.get("dropoff_datetime")) for row in core_rows]
            if any(value is None for value in [*pickups, *dropoffs]):
                continue
            if any(
                dropoff < pickup
                for pickup, dropoff in zip(pickups, dropoffs)
                if pickup is not None and dropoff is not None
            ):
                continue
            lower_dropoff = min(
                value for value in pickups if value is not None
            ) - timedelta(minutes=30)
            upper_pickup = max(
                value for value in dropoffs if value is not None
            ) + timedelta(minutes=30)
            determinate_where = (
                f"hvfhs_license_num = '{provider_literal}' "
                f"AND {TARGET} "
                "AND pickup_datetime IS NOT NULL "
                "AND dropoff_datetime IS NOT NULL "
                f"AND pickup_datetime <= '{fmt(upper_pickup)}' "
                f"AND dropoff_datetime >= '{fmt(lower_dropoff)}'"
            )
            indeterminate_where = (
                f"hvfhs_license_num = '{provider_literal}' "
                f"AND {TARGET} AND "
                "(pickup_datetime IS NULL OR dropoff_datetime IS NULL)"
            )
            determinate_count, determinate_count_api, determinate_count_query = count(
                determinate_where
            )
            indeterminate_count, indeterminate_count_api, indeterminate_count_query = count(
                indeterminate_where
            )
            if (
                determinate_count + indeterminate_count > args.max_candidate_rows
                or indeterminate_count > args.max_indeterminate_rows
            ):
                continue
            determinate_rows, determinate_api, determinate_query = select(
                FIELDS,
                determinate_where,
                order,
                determinate_count,
                args.max_candidate_rows,
            )
            indeterminate_rows: list[dict[str, Any]] = []
            indeterminate_api = "none"
            indeterminate_query = ""
            if indeterminate_count:
                indeterminate_rows, indeterminate_api, indeterminate_query = select(
                    FIELDS,
                    indeterminate_where,
                    order,
                    indeterminate_count,
                    args.max_indeterminate_rows,
                )
            candidates = [*determinate_rows, *indeterminate_rows]
            if multiset(core_rows) - multiset(candidates):
                raise LiveDataError(
                    "candidate universe does not contain exact core multiset"
                )
            item["status"] = "selected"
            return {
                "provider": provider,
                "core_start": core_start,
                "core_end": core_end,
                "core_rows": core_rows,
                "candidate_rows": candidates,
                "determinate_count": determinate_count,
                "indeterminate_count": indeterminate_count,
                "considered": considered,
                "queries": {
                    "scan_count": sha(scan_count_query),
                    "scan": sha(scan_query),
                    "core_count": sha(core_count_query),
                    "core": sha(core_query),
                    "determinate_count": sha(determinate_count_query),
                    "determinate": sha(determinate_query),
                    "indeterminate_count": sha(indeterminate_count_query),
                    "indeterminate": sha(indeterminate_query),
                },
                "apis": {
                    "scan_count": scan_count_api,
                    "scan": scan_api,
                    "core_count": core_count_api,
                    "core": core_api,
                    "determinate_count": determinate_count_api,
                    "determinate": determinate_api,
                    "indeterminate_count": indeterminate_count_api,
                    "indeterminate": indeterminate_api,
                },
                "where": {
                    "determinate": determinate_where,
                    "indeterminate": indeterminate_where,
                },
            }
    raise LiveDataError(
        "no scan window produced an integrity- and cap-qualified core"
    )
