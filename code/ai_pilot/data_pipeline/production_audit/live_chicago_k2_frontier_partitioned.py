#!/usr/bin/env python3
"""Run the Chicago K=2 frontier with a partitioned Socrata extraction.

The base frontier runner defines the scientific object: a count-closed public
K=2 temporal candidate universe, a boundary buffer, and nested radius/Gamma
candidate-support sensitivity curves.  This wrapper changes only the live data
transport.  A single wide cross-time Socrata query can time out even when its
server-side count succeeds.  We therefore:

1. fetch a narrow ``trip_id, trip_start_timestamp`` index for the determinate
   overlap predicate;
2. partition the full-row pull by exact released 15-minute start timestamp;
3. reconcile every partition against both the narrow index and a fresh
   server-side count; and
4. fetch null-start/null-end targets in small trip-ID batches.

No trip IDs or rows are written to output artifacts.  The fetch ledger contains
only counts, timestamps, query hashes, and hashes of ID sets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import live_chicago_k2_frontier as frontier  # noqa: E402


ESSENTIAL_FIELDS = (
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
    "pickup_centroid_latitude",
    "pickup_centroid_longitude",
    "dropoff_centroid_latitude",
    "dropoff_centroid_longitude",
)

_PROGRESS: dict[str, Any] = {"stage": "not_started"}
_ORIGINAL_REQUEST_JSON = frontier._request_json


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_ids(values: Sequence[str]) -> str:
    payload = "\n".join(sorted(values)) + "\n"
    return _sha256(payload)


def _normalized_id(row: Mapping[str, Any]) -> str | None:
    value = row.get("trip_id")
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _soql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _bounded_index_query(
    *,
    fields: Sequence[str],
    where: str,
    expected_count: int,
    label: str,
) -> tuple[list[dict[str, Any]], str, str]:
    if expected_count < 0:
        raise frontier.LiveDataError(f"negative expected count for {label}")
    if expected_count == 0:
        return [], "not_needed", ""
    query = (
        f"SELECT {', '.join(fields)} WHERE {where} "
        f"LIMIT {expected_count}"
    )
    _PROGRESS.update(stage=f"index_{label}", expected_count=expected_count)
    rows, api = frontier.query_rows(query, page_size=expected_count)
    if len(rows) != expected_count:
        raise frontier.LiveDataError(
            f"{label} narrow index returned {len(rows)} rows; "
            f"server count was {expected_count}"
        )
    return rows, api, query


def _validate_unique_index_ids(
    rows: Sequence[Mapping[str, Any]], *, label: str
) -> list[str]:
    ids = [_normalized_id(row) for row in rows]
    if any(value is None for value in ids):
        raise frontier.LiveDataError(f"{label} narrow index contains a null trip_id")
    resolved = [str(value) for value in ids]
    duplicates = sum(count > 1 for count in Counter(resolved).values())
    if duplicates:
        raise frontier.LiveDataError(
            f"{label} narrow index contains {duplicates} duplicated trip-ID values"
        )
    return resolved


def _verify_partition_ids(
    rows: Sequence[Mapping[str, Any]], expected_ids: set[str], *, label: str
) -> None:
    actual = [_normalized_id(row) for row in rows]
    if any(value is None for value in actual):
        raise frontier.LiveDataError(f"{label} full-row partition contains null trip_id")
    actual_ids = [str(value) for value in actual]
    if len(actual_ids) != len(set(actual_ids)):
        raise frontier.LiveDataError(f"{label} full-row partition contains duplicate IDs")
    if set(actual_ids) != expected_ids:
        raise frontier.LiveDataError(
            f"{label} full-row partition does not match its narrow index"
        )


def _determinate_partitions(
    selected: Mapping[str, Any], *, page_size: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_total = int(selected["determinate_count"])
    index_rows, index_api, index_query = _bounded_index_query(
        fields=("trip_id", "trip_start_timestamp"),
        where=str(selected["determinate_where"]),
        expected_count=expected_total,
        label="determinate",
    )
    index_ids = _validate_unique_index_ids(index_rows, label="determinate")

    groups: dict[datetime, set[str]] = defaultdict(set)
    for row, trip_id in zip(index_rows, index_ids):
        start = frontier.parse_local_timestamp(row.get("trip_start_timestamp"))
        if start is None or not frontier.on_release_grid(start):
            raise frontier.LiveDataError(
                "determinate narrow index contains a null, malformed, or off-grid start"
            )
        groups[start].add(trip_id)
    if sum(len(values) for values in groups.values()) != expected_total:
        raise frontier.LiveDataError("determinate timestamp partition lost indexed rows")

    core_start = selected["core_start"]
    output: list[dict[str, Any]] = []
    partition_ledger: list[dict[str, Any]] = []
    for partition_number, start in enumerate(sorted(groups), start=1):
        expected_ids = groups[start]
        _PROGRESS.update(
            stage="fetch_determinate_partition",
            partition_number=partition_number,
            partition_count=len(groups),
            released_start=start.isoformat(),
            expected_count=len(expected_ids),
        )
        if start == core_start:
            rows = list(selected["core_rows"])
            _verify_partition_ids(rows, expected_ids, label="reused core partition")
            partition_ledger.append(
                {
                    "released_start": start.isoformat(),
                    "row_count": len(rows),
                    "source": "reused_integrity_checked_core_pull",
                    "id_set_sha256": _hash_ids(sorted(expected_ids)),
                    "query_sha256": _sha256(str(selected["core_base_query"])),
                    "count_query_sha256": _sha256(str(selected["core_count_query"])),
                    "page_apis": list(selected["core_page_apis"]),
                    "count_api": selected["core_count_api"],
                }
            )
            output.extend(rows)
            continue

        timestamp_literal = frontier.format_socrata_timestamp(start)
        partition_where = (
            f"({selected['determinate_where']}) AND "
            f"trip_start_timestamp = '{timestamp_literal}'"
        )
        server_count, count_api, count_query = frontier.scalar_count(partition_where)
        if server_count != len(expected_ids):
            raise frontier.LiveDataError(
                "determinate partition count disagrees with narrow index at "
                f"{start.isoformat()}: server={server_count}, index={len(expected_ids)}"
            )
        rows, apis, base_query = frontier.paged_select(
            fields=ESSENTIAL_FIELDS,
            where=partition_where,
            order_by="trip_end_timestamp, trip_id",
            expected_count=server_count,
            page_size=min(page_size, max(1, server_count)),
        )
        _verify_partition_ids(
            rows, expected_ids, label=f"determinate partition {start.isoformat()}"
        )
        output.extend(rows)
        partition_ledger.append(
            {
                "released_start": start.isoformat(),
                "row_count": len(rows),
                "source": "exact_released_start_partition",
                "id_set_sha256": _hash_ids(sorted(expected_ids)),
                "query_sha256": _sha256(base_query),
                "count_query_sha256": _sha256(count_query),
                "page_apis": apis,
                "count_api": count_api,
            }
        )

    if len(output) != expected_total:
        raise frontier.LiveDataError(
            f"determinate partitions produced {len(output)} rows; expected {expected_total}"
        )
    output_ids = [_normalized_id(row) for row in output]
    if any(value is None for value in output_ids) or set(output_ids) != set(index_ids):
        raise frontier.LiveDataError("combined determinate rows fail index reconciliation")
    return output, {
        "strategy": "narrow_id_start_index_then_exact_start_partitions",
        "index_api": index_api,
        "index_query_sha256": _sha256(index_query),
        "index_id_set_sha256": _hash_ids(index_ids),
        "partition_count": len(groups),
        "partitions": partition_ledger,
    }


def _chunked(values: Sequence[str], size: int) -> list[list[str]]:
    return [list(values[index : index + size]) for index in range(0, len(values), size)]


def _indeterminate_partitions(
    selected: Mapping[str, Any], *, page_size: int, id_batch_size: int = 50
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_total = int(selected["indeterminate_count"])
    if expected_total == 0:
        return [], {
            "strategy": "not_needed_server_count_zero",
            "index_query_sha256": None,
            "batch_count": 0,
            "batches": [],
        }
    index_rows, index_api, index_query = _bounded_index_query(
        fields=("trip_id", "trip_start_timestamp", "trip_end_timestamp"),
        where=str(selected["indeterminate_where"]),
        expected_count=expected_total,
        label="indeterminate",
    )
    index_ids = _validate_unique_index_ids(index_rows, label="indeterminate")
    output: list[dict[str, Any]] = []
    batch_ledger: list[dict[str, Any]] = []
    batches = _chunked(sorted(index_ids), min(id_batch_size, max(1, page_size)))
    for batch_number, batch_ids in enumerate(batches, start=1):
        _PROGRESS.update(
            stage="fetch_indeterminate_batch",
            batch_number=batch_number,
            batch_count=len(batches),
            expected_count=len(batch_ids),
        )
        id_clause = ", ".join(_soql_string(value) for value in batch_ids)
        batch_where = (
            f"({selected['indeterminate_where']}) AND trip_id IN ({id_clause})"
        )
        server_count, count_api, count_query = frontier.scalar_count(batch_where)
        if server_count != len(batch_ids):
            raise frontier.LiveDataError(
                "indeterminate ID batch count disagrees with narrow index: "
                f"server={server_count}, index={len(batch_ids)}"
            )
        rows, apis, base_query = frontier.paged_select(
            fields=ESSENTIAL_FIELDS,
            where=batch_where,
            order_by="trip_id",
            expected_count=server_count,
            page_size=min(page_size, max(1, server_count)),
        )
        _verify_partition_ids(rows, set(batch_ids), label="indeterminate ID batch")
        output.extend(rows)
        batch_ledger.append(
            {
                "row_count": len(rows),
                "id_set_sha256": _hash_ids(batch_ids),
                "query_sha256": _sha256(base_query),
                "count_query_sha256": _sha256(count_query),
                "page_apis": apis,
                "count_api": count_api,
            }
        )
    if len(output) != expected_total:
        raise frontier.LiveDataError(
            f"indeterminate batches produced {len(output)} rows; expected {expected_total}"
        )
    return output, {
        "strategy": "narrow_id_index_then_trip_id_batches",
        "index_api": index_api,
        "index_query_sha256": _sha256(index_query),
        "index_id_set_sha256": _hash_ids(index_ids),
        "batch_count": len(batches),
        "batches": batch_ledger,
    }


def partitioned_fetch_closed_candidate_universe(
    selected: Mapping[str, Any], *, page_size: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch the count-pinned candidate universe without one wide range query."""

    _PROGRESS.clear()
    _PROGRESS.update(
        stage="partitioned_candidate_fetch",
        determinate_expected=int(selected["determinate_count"]),
        indeterminate_expected=int(selected["indeterminate_count"]),
    )
    determinate, determinate_ledger = _determinate_partitions(
        selected, page_size=page_size
    )
    indeterminate, indeterminate_ledger = _indeterminate_partitions(
        selected, page_size=page_size
    )
    rows = [*determinate, *indeterminate]
    expected = int(selected["candidate_count"])
    if len(rows) != expected:
        raise frontier.LiveDataError(
            f"combined partitioned candidate pull has {len(rows)} rows; expected {expected}"
        )
    ids = [_normalized_id(row) for row in rows]
    if any(value is None for value in ids):
        raise frontier.LiveDataError("combined candidate pull contains a null trip_id")
    resolved_ids = [str(value) for value in ids]
    if len(resolved_ids) != len(set(resolved_ids)):
        raise frontier.LiveDataError("combined candidate pull contains duplicate trip IDs")
    rows.sort(
        key=lambda row: (
            frontier.parse_local_timestamp(row.get("trip_start_timestamp"))
            or datetime.max,
            frontier.parse_local_timestamp(row.get("trip_end_timestamp"))
            or datetime.max,
            str(row.get("trip_id", "")),
        )
    )
    _PROGRESS.update(stage="partitioned_candidate_fetch_complete", fetched=len(rows))
    return rows, {
        "fetch_strategy_version": "partitioned-index-v1",
        "essential_fields": list(ESSENTIAL_FIELDS),
        "raw_trip_ids_emitted": False,
        "determinate": determinate_ledger,
        "indeterminate": indeterminate_ledger,
        "combined_row_count": len(rows),
        "combined_id_set_sha256": _hash_ids(resolved_ids),
    }


def _configure_request_budget(timeout_seconds: int, attempts: int) -> None:
    def bounded_request(url: str, *, timeout: int = 180, attempts: int = 4) -> Any:
        del timeout, attempts
        return _ORIGINAL_REQUEST_JSON(
            url,
            timeout=timeout_seconds,
            attempts=attempts_count,
        )

    attempts_count = attempts
    frontier._request_json = bounded_request


def _validate_args(args: argparse.Namespace) -> None:
    scan_start = frontier.parse_required_datetime(args.scan_start)
    scan_end = frontier.parse_required_datetime(args.scan_end)
    if not scan_start < scan_end:
        raise SystemExit("--scan-start must precede --scan-end")
    if args.min_core_rows < 2 or args.max_core_rows < args.min_core_rows:
        raise SystemExit("invalid core-row limits")
    if args.max_candidate_rows < args.max_core_rows:
        raise SystemExit("max candidate rows must be at least max core rows")
    if args.page_size < 1 or args.page_size > 5000:
        raise SystemExit("partition page size must lie in [1,5000]")
    if args.base_radius_km < 0 or args.solver_time_limit <= 0:
        raise SystemExit("radius must be nonnegative and solver time positive")
    if not 10 <= args.request_timeout <= 300:
        raise SystemExit("request timeout must lie in [10,300] seconds")
    if not 1 <= args.request_attempts <= 6:
        raise SystemExit("request attempts must lie in [1,6]")


def build_parser() -> argparse.ArgumentParser:
    parser = frontier.build_parser()
    parser.description = __doc__
    parser.set_defaults(page_size=100)
    parser.add_argument("--request-timeout", type=int, default=90)
    parser.add_argument("--request-attempts", type=int, default=3)
    return parser


def _write_failure(output_dir: Path, exc: Exception) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    failure = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "failed",
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "progress": dict(_PROGRESS),
        "raw_rows_emitted": False,
        "raw_trip_ids_emitted": False,
    }
    (output_dir / "failure.json").write_text(
        json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        frontier.self_test()
        print("partitioned transport self-test: PASS")
        return 0
    _validate_args(args)
    _configure_request_budget(args.request_timeout, args.request_attempts)
    frontier.fetch_closed_candidate_universe = (
        partitioned_fetch_closed_candidate_universe
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = frontier.run(args)
        report["extraction"]["transport"] = {
            "strategy": "narrow index plus exact released-start partitions",
            "request_timeout_seconds": args.request_timeout,
            "request_attempts": args.request_attempts,
            "partition_page_size": args.page_size,
        }
        report["report_sha256"] = frontier.sha256_json(report)
        frontier.write_outputs(report, args.output_dir)
    except Exception as exc:
        _write_failure(args.output_dir, exc)
        raise
    print(frontier.render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
