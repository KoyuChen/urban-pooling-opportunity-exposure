#!/usr/bin/env python3
"""Fetch complete authorized-trip days for the Chicago AI pairing pilot.

The earlier feasibility file is a deterministic 1/256 trip-ID-prefix sample.
That sample is useful for aggregate rates but unsuitable for reconstructing a
candidate co-rider graph, because almost every possible counterpart is omitted.
This script instead downloads *all* trips for which the rider authorized
sharing on two comparable Tuesdays around the 2026-01-06 policy change.

The script uses only the Python standard library, verifies every local row
count against a fresh server-side ``count(*)``, writes files atomically, and
creates a machine-readable manifest plus a concise quality report.  No Socrata
token is required for these narrow pulls, though ``SOCRATA_APP_TOKEN`` is used
when present.  Because the City may append late reports to already published
periods, the script also fingerprints the dataset revision and schema before
and after extraction.  A revision change during the pull is a hard failure;
an unchanged pull is complete only within that pinned public snapshot.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DATASET_ID = "6dvr-xwnh"
DATASET_NAME = "Transportation Network Providers - Trips (2025-)"
DOMAIN = "https://data.cityofchicago.org"
DEFAULT_DATES = ("2025-12-16", "2026-01-13")
FIELDS = [
    "trip_id",
    "trip_start_timestamp",
    "trip_end_timestamp",
    "trip_seconds",
    "trip_miles",
    "percent_time_chicago",
    "percent_distance_chicago",
    "pickup_census_tract",
    "dropoff_census_tract",
    "pickup_community_area",
    "dropoff_community_area",
    "fare",
    "tip",
    "additional_charges",
    "trip_total",
    "shared_trip_authorized",
    "shared_trip_match",
    "trips_pooled",
    "pickup_centroid_latitude",
    "pickup_centroid_longitude",
    "dropoff_centroid_latitude",
    "dropoff_centroid_longitude",
]
LOCATION_FIELDS = [
    "pickup_census_tract",
    "dropoff_census_tract",
    "pickup_community_area",
    "dropoff_community_area",
    "pickup_centroid_latitude",
    "pickup_centroid_longitude",
    "dropoff_centroid_latitude",
    "dropoff_centroid_longitude",
]


def open_url(url: str, *, attempts: int = 4, timeout: int = 120):
    """Open a URL with exponential backoff and an optional Socrata token."""

    headers = {"User-Agent": "urban-pooling-ai-pilot/0.1"}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    request = urllib.request.Request(url, headers=headers)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            if attempt + 1 == attempts:
                break
            time.sleep(2**attempt)
    raise RuntimeError(f"Failed after {attempts} attempts: {url}") from last_error


def v3_url(
    query: str,
    *,
    page_number: int = 1,
    page_size: int = 1000,
    fmt: str = "json",
) -> str:
    params = urllib.parse.urlencode(
        {"query": query, "pageNumber": page_number, "pageSize": page_size}
    )
    return f"{DOMAIN}/api/v3/views/{DATASET_ID}/query.{fmt}?{params}"


def v2_url(
    query: str,
    *,
    page_number: int = 1,
    page_size: int = 1000,
    fmt: str = "json",
) -> str:
    """Build the legacy SODA2 URL used as a fallback for slow SODA3 pulls."""

    offset = (page_number - 1) * page_size
    params = urllib.parse.urlencode(
        {"$query": f"{query} LIMIT {page_size} OFFSET {offset}"}
    )
    return f"{DOMAIN}/resource/{DATASET_ID}.{fmt}?{params}"


def query_url(
    query: str,
    *,
    api_version: str,
    page_number: int = 1,
    page_size: int = 1000,
    fmt: str = "json",
) -> str:
    if api_version == "v3":
        return v3_url(
            query,
            page_number=page_number,
            page_size=page_size,
            fmt=fmt,
        )
    if api_version == "v2":
        return v2_url(
            query,
            page_number=page_number,
            page_size=page_size,
            fmt=fmt,
        )
    raise ValueError(f"Unknown API version: {api_version}")


def fetch_json(url: str) -> Any:
    with open_url(url) as response:
        return json.load(response)


def dataset_snapshot(metadata: Any) -> dict[str, Any]:
    """Return the revision fields needed to reproduce one public snapshot.

    Volatile portal counters are deliberately excluded.  ``rowsUpdatedAt``
    pins row publication, ``viewLastModified`` pins metadata changes, and the
    ordered column signature detects a schema drift even if the portal omits a
    revision field.  The fingerprint is evidence about the public Socrata
    view, not proof that every provider report for the period has arrived.
    """

    if not isinstance(metadata, dict):
        raise ValueError("dataset metadata must be a JSON object")
    if metadata.get("id") != DATASET_ID:
        raise ValueError(
            f"dataset metadata id must be {DATASET_ID!r}, got "
            f"{metadata.get('id')!r}"
        )
    raw_columns = metadata.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError("dataset metadata must contain a nonempty columns list")
    columns = []
    for fallback_position, column in enumerate(raw_columns):
        if not isinstance(column, dict):
            raise ValueError("dataset column metadata must be JSON objects")
        field_name = column.get("fieldName")
        data_type = column.get("dataTypeName")
        if not isinstance(field_name, str) or not field_name:
            raise ValueError("dataset column metadata lacks fieldName")
        if not isinstance(data_type, str) or not data_type:
            raise ValueError("dataset column metadata lacks dataTypeName")
        position = column.get("position", fallback_position)
        if isinstance(position, bool) or not isinstance(position, int):
            raise ValueError("dataset column position must be an integer")
        columns.append(
            {
                "position": position,
                "field_name": field_name,
                "data_type": data_type,
            }
        )
    columns.sort(key=lambda item: (item["position"], item["field_name"]))
    core = {
        "dataset_id": metadata["id"],
        "dataset_name": metadata.get("name"),
        "rows_updated_at": metadata.get("rowsUpdatedAt"),
        "view_last_modified": metadata.get("viewLastModified"),
        "publication_date": metadata.get("publicationDate"),
        "column_schema": columns,
    }
    encoded = json.dumps(
        core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        **core,
        "revision_fingerprint_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def snapshots_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Whether two extracted metadata snapshots describe the same revision."""

    return left == right


def scalar_query(
    query: str, *, api_version: str
) -> tuple[dict[str, str], str]:
    """Run a scalar query, optionally falling back from SODA3 to SODA2."""

    versions = ("v3", "v2") if api_version == "auto" else (api_version,)
    errors: list[str] = []
    for version in versions:
        try:
            result = fetch_json(
                query_url(query, api_version=version, page_size=10)
            )
            if not isinstance(result, list) or len(result) != 1:
                raise RuntimeError(f"Unexpected scalar response: {result!r}")
            return result[0], version
        except Exception as exc:  # pragma: no cover - network dependent
            errors.append(f"{version}: {type(exc).__name__}: {exc}")
    raise RuntimeError(
        f"All requested Socrata API backends failed for {query!r}: "
        + " | ".join(errors)
    )


def window_for(day_text: str) -> tuple[str, str]:
    day = date.fromisoformat(day_text)
    next_day = day + timedelta(days=1)
    return f"{day.isoformat()}T00:00:00", f"{next_day.isoformat()}T00:00:00"


def where_for(day_text: str) -> str:
    start, end = window_for(day_text)
    return (
        f'trip_start_timestamp >= "{start}" '
        f'AND trip_start_timestamp < "{end}" '
        "AND shared_trip_authorized = true"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_csv_row_count(path: Path) -> int:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def download_day(
    output_dir: Path,
    *,
    day_text: str,
    page_size: int,
    force: bool,
    api_version: str,
) -> dict[str, Any]:
    """Download and validate one complete authorized-trip day."""

    where = where_for(day_text)
    count_result, selected_api = scalar_query(
        f"SELECT count(*) AS n WHERE {where}", api_version=api_version
    )
    expected = int(count_result["n"])
    output = output_dir / f"chicago_authorized_{day_text}.csv"

    if output.exists() and not force:
        cached_rows = local_csv_row_count(output)
        if cached_rows == expected:
            return {
                "date": day_text,
                "start_inclusive": window_for(day_text)[0],
                "end_exclusive": window_for(day_text)[1],
                "server_expected_rows": expected,
                "downloaded_rows": cached_rows,
                "cache_reused": True,
                "api_version": selected_api,
                "relative_path": str(output.relative_to(output_dir.parent)),
                "bytes": output.stat().st_size,
                "sha256": sha256_file(output),
                "query": build_query(where),
            }

    query = build_query(where)
    temporary = output.with_suffix(output.suffix + ".part")
    written = 0
    page = 1
    keep: list[int] | None = None
    try:
        with temporary.open("w", newline="", encoding="utf-8") as out_handle:
            writer = csv.writer(out_handle)
            while written < expected:
                url = query_url(
                    query,
                    api_version=selected_api,
                    page_number=page,
                    page_size=page_size,
                    fmt="csv",
                )
                with open_url(url) as response:
                    text = response.read().decode("utf-8-sig")
                rows = csv.reader(io.StringIO(text))
                current_header = next(rows, None)
                if current_header is None:
                    raise RuntimeError(f"Empty response on page {page} for {day_text}")
                if keep is None:
                    missing = [field for field in FIELDS if field not in current_header]
                    if missing:
                        raise RuntimeError(
                            f"API response omitted requested fields for {day_text}: {missing}"
                        )
                    keep = [current_header.index(field) for field in FIELDS]
                    writer.writerow(FIELDS)
                page_rows = 0
                for row in rows:
                    if not row:
                        continue
                    writer.writerow([row[index] for index in keep])
                    page_rows += 1
                written += page_rows
                if page_rows == 0 or page_rows < page_size:
                    break
                page += 1
        if written != expected:
            raise RuntimeError(
                f"Incomplete {day_text} pull: server count {expected:,}, wrote {written:,}"
            )
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    return {
        "date": day_text,
        "start_inclusive": window_for(day_text)[0],
        "end_exclusive": window_for(day_text)[1],
        "server_expected_rows": expected,
        "downloaded_rows": written,
        "cache_reused": False,
        "api_version": selected_api,
        "relative_path": str(output.relative_to(output_dir.parent)),
        "bytes": output.stat().st_size,
        "sha256": sha256_file(output),
        "query": query,
    }


def build_query(where: str) -> str:
    return (
        f"SELECT {', '.join(FIELDS)} WHERE {where} "
        "ORDER BY trip_start_timestamp, trip_id"
    )


def as_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def missing(value: str) -> bool:
    return value.strip() == ""


def as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def audit_day(path: Path, day_text: str) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    missing_counts: Counter[str] = Counter()
    trip_ids: set[str] = set()
    start_bins: set[str] = set()

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise RuntimeError(f"Unexpected local schema in {path}: {reader.fieldnames}")
        for row in reader:
            counts["rows"] += 1
            trip_id = row["trip_id"]
            if trip_id in trip_ids:
                counts["duplicate_trip_ids"] += 1
            trip_ids.add(trip_id)

            start_text = row["trip_start_timestamp"]
            if not start_text.startswith(day_text):
                counts["outside_requested_day"] += 1
            if start_text:
                start_bins.add(start_text)

            authorized = as_bool(row["shared_trip_authorized"])
            matched = as_bool(row["shared_trip_match"])
            if authorized is not True:
                counts["not_authorized_true"] += 1
            if matched is True:
                counts["matched_rows"] += 1
            elif matched is False:
                counts["unmatched_rows"] += 1
            else:
                counts["missing_match_flag"] += 1

            pooled = as_float(row["trips_pooled"])
            if matched is True and (pooled is None or pooled < 2):
                counts["matched_with_trips_pooled_lt_2_or_missing"] += 1
            if matched is False and pooled is not None and pooled >= 2:
                counts["unmatched_with_trips_pooled_ge_2"] += 1

            for field in FIELDS:
                if missing(row[field]):
                    missing_counts[field] += 1

            pickup_centroid = (
                not missing(row["pickup_centroid_latitude"])
                and not missing(row["pickup_centroid_longitude"])
            )
            dropoff_centroid = (
                not missing(row["dropoff_centroid_latitude"])
                and not missing(row["dropoff_centroid_longitude"])
            )
            if pickup_centroid and dropoff_centroid:
                counts["complete_od_centroids"] += 1
            if row["pickup_census_tract"] and row["dropoff_census_tract"]:
                counts["complete_od_tracts"] += 1

    n = counts["rows"]
    rate = lambda numerator: (numerator / n if n else None)
    return {
        "date": day_text,
        "rows": n,
        "matched_rows": counts["matched_rows"],
        "unmatched_rows": counts["unmatched_rows"],
        "matched_rate_among_authorized": rate(counts["matched_rows"]),
        "duplicate_trip_ids": counts["duplicate_trip_ids"],
        "outside_requested_day": counts["outside_requested_day"],
        "not_authorized_true": counts["not_authorized_true"],
        "missing_match_flag": counts["missing_match_flag"],
        "matched_with_trips_pooled_lt_2_or_missing": counts[
            "matched_with_trips_pooled_lt_2_or_missing"
        ],
        "unmatched_with_trips_pooled_ge_2": counts[
            "unmatched_with_trips_pooled_ge_2"
        ],
        "complete_od_centroids_rows": counts["complete_od_centroids"],
        "complete_od_centroids_rate": rate(counts["complete_od_centroids"]),
        "complete_od_tracts_rows": counts["complete_od_tracts"],
        "complete_od_tracts_rate": rate(counts["complete_od_tracts"]),
        "distinct_released_start_timestamps": len(start_bins),
        "missingness": {
            field: {
                "missing_rows": missing_counts[field],
                "missing_rate": rate(missing_counts[field]),
            }
            for field in FIELDS
        },
    }


def combine_days(
    paths: Iterable[tuple[str, Path]], output: Path
) -> tuple[int, str]:
    """Create a compact combined file with a provenance date column."""

    temporary = output.with_suffix(output.suffix + ".part")
    written = 0
    try:
        with gzip.open(temporary, "wt", newline="", encoding="utf-8") as out_handle:
            writer = csv.writer(out_handle)
            writer.writerow(["source_date", *FIELDS])
            for day_text, path in paths:
                with path.open("r", newline="", encoding="utf-8-sig") as in_handle:
                    reader = csv.DictReader(in_handle)
                    for row in reader:
                        writer.writerow([day_text, *(row[field] for field in FIELDS)])
                        written += 1
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return written, sha256_file(output)


def render_quality_report(
    manifest: dict[str, Any], quality: dict[str, Any], path: Path
) -> None:
    day_rows = []
    for entry in quality["days"]:
        day_rows.append(
            "| {date} | {rows:,} | {matched:,} | {rate:.2%} | {centroids:.2%} | "
            "{tracts:.2%} | {inconsistent:,} |".format(
                date=entry["date"],
                rows=entry["rows"],
                matched=entry["matched_rows"],
                rate=entry["matched_rate_among_authorized"],
                centroids=entry["complete_od_centroids_rate"],
                tracts=entry["complete_od_tracts_rate"],
                inconsistent=entry["matched_with_trips_pooled_lt_2_or_missing"],
            )
        )
    failures = quality["hard_check_failures"]
    hard_check_text = "PASS" if not failures else "FAIL: " + "; ".join(failures)
    combined = manifest["combined_file"]
    snapshot = manifest["source_snapshot_after"]
    snapshot_status = (
        "stable during extraction"
        if manifest["snapshot_stable_during_extraction"]
        else "CHANGED during extraction"
    )
    report = f"""# Chicago complete-day data quality report

Generated: {manifest['created_at_utc']}

Dataset: City of Chicago `{DATASET_ID}`, {DATASET_NAME}

Selection: every row with `shared_trip_authorized = true` on two comparable
Tuesdays, one before and one after the 2026-01-06 policy change.

## Completeness result

**{hard_check_text}.** Each day-level file was checked against a fresh
server-side `count(*)`. The combined gzip file contains
**{combined['rows']:,} rows**.

The public Socrata view was **{snapshot_status}**. Its pinned revision
fingerprint is `{snapshot['revision_fingerprint_sha256']}`
(`rowsUpdatedAt={snapshot['rows_updated_at']}`,
`viewLastModified={snapshot['view_last_modified']}`). This certifies a complete
slice of that one public revision, not that every provider report had arrived
or that the same historical rows will remain unchanged after a later release.

| Date | Authorized rows | Matched rows | Matched / authorized | Complete OD centroids | Complete OD tracts | Matched but pooled <2/missing |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(day_rows)}

## Modeling implications

- These are complete authorized-trip day slices, not a trip-ID-prefix sample;
  therefore another authorized same-day component is not mechanically excluded
  by identifier sampling. This does not establish run closure: a partner can
  cross the day boundary or have inconsistent released authorization/run
  fields, so these files are a capacity pilot rather than a production outer
  candidate set.
- Released start/end timestamps are rounded to 15-minute bins. Candidate edges
  must therefore rely jointly on time, origin/destination compatibility, route
  direction, and detour constraints rather than treating equal timestamps as a
  pair label.
- A complete OD centroid is much more common than a complete OD census-tract
  pair. Use centroids for candidate generation and treat tract/ACS analyses as
  a missing-data sensitivity layer.
- `shared_trip_match` and `trips_pooled` are node-level outcomes. The data do not
  contain a shared-trip group ID, vehicle ID, or rider ID; reconstructed edges
  remain latent compatibility hypotheses, never observed co-rider truth.

## Files

- `raw/chicago_authorized_2025-12-16.csv`
- `raw/chicago_authorized_2026-01-13.csv`
- `derived/chicago_authorized_complete_days.csv.gz`
- `manifest.json`: exact queries, source counts, SHA-256 hashes, and schema.
- `quality_summary.json`: detailed field missingness and invariant checks.
"""
    path.write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dates",
        nargs="+",
        default=list(DEFAULT_DATES),
        help="Complete local dates to download (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=5_000,
        help="Rows per page; 5,000 is conservative for unauthenticated requests.",
    )
    parser.add_argument(
        "--api-version",
        choices=("auto", "v3", "v2"),
        default="auto",
        help="Use SODA3, SODA2, or automatically fall back from v3 to v2.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    for day_text in args.dates:
        date.fromisoformat(day_text)
    if len(set(args.dates)) != len(args.dates):
        raise SystemExit("Duplicate dates are not allowed")
    if args.page_size < 1:
        raise SystemExit("--page-size must be positive")

    root = Path(__file__).resolve().parent
    raw_dir = root / "raw"
    derived_dir = root / "derived"
    raw_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)

    metadata_url = f"{DOMAIN}/api/views/{DATASET_ID}"
    snapshot_before = dataset_snapshot(fetch_json(metadata_url))

    day_manifests = []
    day_audits = []
    day_paths: list[tuple[str, Path]] = []
    for day_text in args.dates:
        entry = download_day(
            raw_dir,
            day_text=day_text,
            page_size=args.page_size,
            force=args.force,
            api_version=args.api_version,
        )
        path = root / entry["relative_path"]
        audit = audit_day(path, day_text)
        if audit["rows"] != entry["server_expected_rows"]:
            raise RuntimeError(
                f"Audit count mismatch for {day_text}: {audit['rows']} vs "
                f"{entry['server_expected_rows']}"
            )
        day_manifests.append(entry)
        day_audits.append(audit)
        day_paths.append((day_text, path))
        print(
            f"{day_text}: {audit['rows']:,} authorized, "
            f"{audit['matched_rows']:,} matched "
            f"({audit['matched_rate_among_authorized']:.2%})"
        )

    combined_path = derived_dir / "chicago_authorized_complete_days.csv.gz"
    combined_rows, combined_sha256 = combine_days(day_paths, combined_path)
    hard_check_failures = []
    for entry, audit in zip(day_manifests, day_audits):
        if entry["server_expected_rows"] != entry["downloaded_rows"]:
            hard_check_failures.append(f"{entry['date']} server/local row mismatch")
        if audit["duplicate_trip_ids"]:
            hard_check_failures.append(f"{entry['date']} duplicate trip IDs")
        if audit["outside_requested_day"]:
            hard_check_failures.append(f"{entry['date']} out-of-window rows")
        if audit["not_authorized_true"]:
            hard_check_failures.append(f"{entry['date']} non-authorized rows")
        if audit["missing_match_flag"]:
            hard_check_failures.append(f"{entry['date']} missing match flags")
    if combined_rows != sum(entry["downloaded_rows"] for entry in day_manifests):
        hard_check_failures.append("combined-file row mismatch")

    snapshot_after = dataset_snapshot(fetch_json(metadata_url))
    snapshot_stable = snapshots_match(snapshot_before, snapshot_after)
    if not snapshot_stable:
        hard_check_failures.append("dataset revision changed during extraction")

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "created_at_utc": created_at,
        "dataset_id": DATASET_ID,
        "dataset_name": DATASET_NAME,
        "source_endpoint": f"{DOMAIN}/api/v3/views/{DATASET_ID}/query.csv",
        "metadata_url": metadata_url,
        "source_snapshot_before": snapshot_before,
        "source_snapshot_after": snapshot_after,
        "snapshot_stable_during_extraction": snapshot_stable,
        "snapshot_completeness_definition": (
            "Every selected row present in one pinned public Socrata revision; "
            "provider-report completeness and later historical stability require "
            "a subsequent re-fetch."
        ),
        "api_foundry_url": (
            f"https://dev.socrata.com/foundry/data.cityofchicago.org/{DATASET_ID}"
        ),
        "selection": "complete local-day slices where shared_trip_authorized = true",
        "date_rationale": (
            "Comparable Tuesdays four weeks apart, one before and one after the "
            "2026-01-06 policy change; both avoid the year-end holiday weeks."
        ),
        "timestamp_note": (
            "City timestamps are floating Chicago-local times released in 15-minute bins."
        ),
        "fields": FIELDS,
        "days": day_manifests,
        "combined_file": {
            "relative_path": str(combined_path.relative_to(root)),
            "rows": combined_rows,
            "bytes": combined_path.stat().st_size,
            "sha256": combined_sha256,
        },
        "limitations": [
            "No shared-trip group ID, vehicle ID, provider ID, or stable rider ID.",
            "A complete authorized slice preserves candidate counterparts but does not reveal them.",
            "Spatial suppression is material, especially for census tracts.",
            "The City may append late reports to published periods; this manifest "
            "certifies only one stable extraction snapshot.",
            "The two dates are a computational pilot, not a causal estimation window.",
        ],
    }
    quality = {
        "created_at_utc": created_at,
        "hard_checks_pass": not hard_check_failures,
        "hard_check_failures": hard_check_failures,
        "days": day_audits,
        "combined_rows": combined_rows,
    }

    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "quality_summary.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    render_quality_report(manifest, quality, root / "QUALITY_REPORT.md")

    if hard_check_failures:
        raise SystemExit("Hard data-quality checks failed: " + "; ".join(hard_check_failures))
    print(combined_path)


if __name__ == "__main__":
    main()
