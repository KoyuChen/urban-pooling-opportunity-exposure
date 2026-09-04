#!/usr/bin/env python3
"""Sharded live Chicago release-operator audit.

The scientific object is unchanged from ``live_chicago_release_operator_audit``.
This entrypoint changes only Socrata transport:

* the cross-column temporal overlap predicate is used only for a narrow
  ``trip_id, trip_start_timestamp`` index;
* full candidate rows are fetched in exact released-start partitions;
* null-time candidate rows are fetched in small public-trip-ID batches; and
* all-trip contributors are fetched one exact released endpoint bin at a time.

Every shard is count-closed before and after retrieval. Shard unions are
deduplicated by public ``trip_id`` and fail closed on inconsistent payloads.
No raw row or identifier is serialized.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import live_chicago_release_operator_audit as base


FETCH_STRATEGY = (
    "NARROW_OVERLAP_INDEX_THEN_EXACT_START_AND_ENDPOINT_BIN_SHARDS"
)
ID_BATCH_SIZE = 50


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _trip_id(row: Mapping[str, Any], *, label: str) -> str:
    value = base.normalized_text(row.get("trip_id"))
    if value is None:
        raise base.AuditError(f"{label} returned a row without trip_id")
    return value


def _soql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _merge_rows(
    target: dict[str, dict[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    *,
    label: str,
    max_unique_rows: int,
) -> None:
    for raw_row in rows:
        row = dict(raw_row)
        trip_id = _trip_id(row, label=label)
        previous = target.get(trip_id)
        if previous is not None and previous != row:
            raise base.AuditError(
                f"{label} duplicate trip_id has inconsistent public payload"
            )
        target[trip_id] = row
        if len(target) > max_unique_rows:
            raise base.AuditError(
                f"{label} union exceeds max {max_unique_rows} unique rows"
            )


def _verify_ids(
    rows: Sequence[Mapping[str, Any]],
    expected_ids: set[str],
    *,
    label: str,
) -> None:
    actual_ids = [_trip_id(row, label=label) for row in rows]
    if len(actual_ids) != len(set(actual_ids)):
        raise base.AuditError(f"{label} returned duplicate trip_id values")
    if set(actual_ids) != expected_ids:
        raise base.AuditError(f"{label} does not match its narrow public-ID index")


def _count_closed_full_fetch(
    *,
    where: str,
    expected_ids: set[str] | None,
    page_size: int,
    timeout: int,
    attempts: int,
    label: str,
) -> tuple[list[dict[str, Any]], list[str], int, str]:
    request = {
        "page_size": page_size,
        "timeout": timeout,
        "attempts": attempts,
    }
    before, _before_api, before_query = base.scalar_count(where, **request)
    if expected_ids is not None and before != len(expected_ids):
        raise base.AuditError(
            f"{label} server count {before} disagrees with narrow index "
            f"{len(expected_ids)}"
        )
    if before == 0:
        rows: list[dict[str, Any]] = []
        apis: list[str] = []
    else:
        rows, apis, _base_query = base.paged_select(
            where=where,
            expected_count=before,
            **request,
        )
    after, _after_api, _after_query = base.scalar_count(where, **request)
    if after != before:
        raise base.AuditError(
            f"{label} count changed during extraction: {before} -> {after}"
        )
    if expected_ids is not None:
        _verify_ids(rows, expected_ids, label=label)
    return rows, apis, before, _sha256_text(before_query)


def _narrow_index(
    *,
    fields: Sequence[str],
    where: str,
    expected_count: int,
    timeout: int,
    attempts: int,
    label: str,
) -> tuple[list[dict[str, Any]], str, str]:
    if expected_count < 0:
        raise base.AuditError(f"{label} has a negative expected count")
    if expected_count == 0:
        return [], "not_needed", _sha256_text("")
    query = (
        f"SELECT {', '.join(fields)} WHERE {where} "
        f"LIMIT {expected_count}"
    )
    rows, api = base.query_rows(
        query,
        page_size=expected_count,
        timeout=timeout,
        attempts=attempts,
    )
    if len(rows) != expected_count:
        raise base.AuditError(
            f"{label} narrow index returned {len(rows)} rows; "
            f"server count was {expected_count}"
        )
    ids = [_trip_id(row, label=label) for row in rows]
    if len(ids) != len(set(ids)):
        raise base.AuditError(f"{label} narrow index contains duplicate trip IDs")
    return rows, api, _sha256_text(query)


def _fetch_id_batches(
    *,
    branch_where: str,
    index_rows: Sequence[Mapping[str, Any]],
    page_size: int,
    timeout: int,
    attempts: int,
    label: str,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    ids = sorted(_trip_id(row, label=label) for row in index_rows)
    output: list[dict[str, Any]] = []
    apis: list[str] = []
    ledger: list[dict[str, Any]] = []
    batch_size = min(ID_BATCH_SIZE, max(1, page_size))
    for batch_number, offset in enumerate(range(0, len(ids), batch_size), start=1):
        batch = ids[offset : offset + batch_size]
        id_clause = ", ".join(_soql_string(value) for value in batch)
        where = f"({branch_where}) AND trip_id IN ({id_clause})"
        rows, branch_apis, count, count_query_hash = _count_closed_full_fetch(
            where=where,
            expected_ids=set(batch),
            page_size=min(page_size, len(batch)),
            timeout=timeout,
            attempts=attempts,
            label=f"{label} batch {batch_number}",
        )
        output.extend(rows)
        apis.extend(branch_apis)
        ledger.append(
            {
                "batch_number": batch_number,
                "row_count": count,
                "count_query_sha256": count_query_hash,
            }
        )
    _verify_ids(output, set(ids), label=label)
    return output, apis, ledger


def _fetch_candidates(
    *,
    determinate_where: str,
    null_start_where: str,
    null_end_where: str,
    lower_end: datetime,
    core_start: datetime,
    max_unique_rows: int,
    page_size: int,
    timeout: int,
    attempts: int,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    request = {
        "page_size": page_size,
        "timeout": timeout,
        "attempts": attempts,
    }
    determinate_count, _api, _query = base.scalar_count(
        determinate_where, **request
    )
    if determinate_count > max_unique_rows:
        raise base.AuditError(
            f"candidate determinate count {determinate_count} exceeds max "
            f"{max_unique_rows}"
        )
    index_rows, index_api, index_query_hash = _narrow_index(
        fields=("trip_id", "trip_start_timestamp"),
        where=determinate_where,
        expected_count=determinate_count,
        timeout=timeout,
        attempts=attempts,
        label="candidate determinate",
    )

    groups: dict[datetime, set[str]] = defaultdict(set)
    for row in index_rows:
        start = base.parse_local_timestamp(row.get("trip_start_timestamp"))
        if start is None or not base.on_release_grid(start):
            raise base.AuditError(
                "candidate determinate index contains a null, malformed, "
                "or off-grid released start"
            )
        groups[start].add(_trip_id(row, label="candidate determinate"))
    if sum(len(values) for values in groups.values()) != determinate_count:
        raise base.AuditError("candidate exact-start partitioning lost indexed rows")

    rows_by_id: dict[str, dict[str, Any]] = {}
    apis: list[str] = []
    start_ledger: list[dict[str, Any]] = []
    lower_end_literal = base.format_socrata_timestamp(lower_end)
    for partition_number, start in enumerate(sorted(groups), start=1):
        expected_ids = groups[start]
        start_literal = base.format_socrata_timestamp(start)
        # The narrow index has fixed the exact start bin, so the full-row query
        # no longer contains a cross-column range predicate.
        where = (
            f"{base.TARGET_PREDICATE} "
            f"AND trip_start_timestamp = '{start_literal}' "
            "AND trip_end_timestamp IS NOT NULL "
            f"AND trip_end_timestamp >= '{lower_end_literal}'"
        )
        rows, branch_apis, count, count_query_hash = _count_closed_full_fetch(
            where=where,
            expected_ids=expected_ids,
            page_size=min(page_size, max(1, len(expected_ids))),
            timeout=timeout,
            attempts=attempts,
            label=f"candidate start partition {start.isoformat()}",
        )
        _merge_rows(
            rows_by_id,
            rows,
            label="candidate determinate",
            max_unique_rows=max_unique_rows,
        )
        apis.extend(branch_apis)
        start_ledger.append(
            {
                "partition_number": partition_number,
                "released_start": start.isoformat(),
                "row_count": count,
                "is_core_start": start == core_start,
                "count_query_sha256": count_query_hash,
            }
        )

    null_ledger: list[dict[str, Any]] = []
    for branch_name, branch_where in (
        ("null_start", null_start_where),
        ("null_end", null_end_where),
    ):
        count, _count_api, count_query = base.scalar_count(branch_where, **request)
        if count > max_unique_rows:
            raise base.AuditError(
                f"candidate {branch_name} count {count} exceeds max "
                f"{max_unique_rows}"
            )
        null_index, null_index_api, null_index_query_hash = _narrow_index(
            fields=("trip_id", "trip_start_timestamp", "trip_end_timestamp"),
            where=branch_where,
            expected_count=count,
            timeout=timeout,
            attempts=attempts,
            label=f"candidate {branch_name}",
        )
        branch_rows, branch_apis, batches = _fetch_id_batches(
            branch_where=branch_where,
            index_rows=null_index,
            page_size=page_size,
            timeout=timeout,
            attempts=attempts,
            label=f"candidate {branch_name}",
        )
        confirmed, _api2, _query2 = base.scalar_count(branch_where, **request)
        if confirmed != count:
            raise base.AuditError(
                f"candidate {branch_name} count changed during extraction: "
                f"{count} -> {confirmed}"
            )
        _merge_rows(
            rows_by_id,
            branch_rows,
            label=f"candidate {branch_name}",
            max_unique_rows=max_unique_rows,
        )
        apis.extend(branch_apis)
        null_ledger.append(
            {
                "branch": branch_name,
                "row_count": count,
                "count_query_sha256": _sha256_text(count_query),
                "index_api": null_index_api,
                "index_query_sha256": null_index_query_hash,
                "batch_count": len(batches),
            }
        )

    expected_determinate_ids = {
        _trip_id(row, label="candidate determinate") for row in index_rows
    }
    if not expected_determinate_ids <= set(rows_by_id):
        raise base.AuditError("candidate union omits determinate indexed rows")

    ordered = sorted(
        rows_by_id.values(),
        key=lambda row: (
            base.normalized_text(row.get("trip_start_timestamp")) or "",
            base.normalized_text(row.get("trip_end_timestamp")) or "",
            _trip_id(row, label="candidate"),
        ),
    )
    return ordered, apis, {
        "determinate_count": determinate_count,
        "determinate_index_api": index_api,
        "determinate_index_query_sha256": index_query_hash,
        "exact_start_partition_count": len(start_ledger),
        "exact_start_partitions": start_ledger,
        "null_branches": null_ledger,
        "unique_candidate_rows": len(ordered),
    }


def _fetch_contributors(
    *,
    starts: Sequence[datetime],
    ends: Sequence[datetime],
    max_unique_rows: int,
    page_size: int,
    timeout: int,
    attempts: int,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    rows_by_id: dict[str, dict[str, Any]] = {}
    apis: list[str] = []
    ledger: list[dict[str, Any]] = []
    raw_partition_row_sum = 0

    for field, values in (
        ("trip_start_timestamp", sorted(set(starts))),
        ("trip_end_timestamp", sorted(set(ends))),
    ):
        for partition_number, value in enumerate(values, start=1):
            literal = base.format_socrata_timestamp(value)
            where = f"{field} = '{literal}'"
            rows, branch_apis, count, count_query_hash = _count_closed_full_fetch(
                where=where,
                expected_ids=None,
                page_size=page_size,
                timeout=timeout,
                attempts=attempts,
                label=f"contributor {field} partition {value.isoformat()}",
            )
            raw_partition_row_sum += count
            _merge_rows(
                rows_by_id,
                rows,
                label="contributor",
                max_unique_rows=max_unique_rows,
            )
            apis.extend(branch_apis)
            ledger.append(
                {
                    "field": field,
                    "partition_number": partition_number,
                    "released_timestamp": value.isoformat(),
                    "row_count": count,
                    "count_query_sha256": count_query_hash,
                }
            )

    ordered = sorted(
        rows_by_id.values(),
        key=lambda row: (
            base.normalized_text(row.get("trip_start_timestamp")) or "",
            base.normalized_text(row.get("trip_end_timestamp")) or "",
            _trip_id(row, label="contributor"),
        ),
    )
    return ordered, apis, {
        "start_partition_count": len(set(starts)),
        "end_partition_count": len(set(ends)),
        "raw_partition_row_sum_before_deduplication": raw_partition_row_sum,
        "unique_contributor_rows": len(ordered),
        "partitions": ledger,
    }


def run_live(args: Any) -> dict[str, Any]:
    core_start = datetime.fromisoformat(args.core_start)
    if core_start.tzinfo is not None or not base.on_release_grid(core_start):
        raise base.AuditError(
            "core-start must be a timezone-naive 15-minute grid value"
        )
    if base.ambiguous_chicago_local_time(core_start):
        raise base.AuditError("core-start is DST ambiguous")
    core_end = core_start + timedelta(minutes=base.RELEASE_BIN_MINUTES)

    request = {
        "page_size": args.page_size,
        "timeout": args.request_timeout,
        "attempts": args.request_attempts,
    }
    snapshot_before = base.fetch_snapshot(
        timeout=args.request_timeout,
        attempts=args.request_attempts,
    )

    core_where = (
        f"trip_start_timestamp >= '{base.format_socrata_timestamp(core_start)}' "
        f"AND trip_start_timestamp < '{base.format_socrata_timestamp(core_end)}' "
        f"AND {base.TARGET_PREDICATE}"
    )
    core_count, _core_count_api, _core_count_query = base.scalar_count(
        core_where, **request
    )
    if core_count <= 0:
        raise base.AuditError("fixed core bin contains no literal K=2/match rows")
    core_raw, _core_apis, _core_base = base.paged_select(
        where=core_where,
        expected_count=core_count,
        **request,
    )
    parsed_core = base.parse_rows(core_raw)
    if any(
        row.released_start is None or row.released_end is None
        for row in parsed_core
    ):
        raise base.AuditError("core contains null released time endpoints")

    lower_end = min(
        row.released_start
        for row in parsed_core
        if row.released_start is not None
    ) - timedelta(minutes=2 * base.ROUNDING_HALF_MINUTES)
    upper_start = max(
        row.released_end
        for row in parsed_core
        if row.released_end is not None
    ) + timedelta(minutes=2 * base.ROUNDING_HALF_MINUTES)

    determinate_where = (
        f"{base.TARGET_PREDICATE} "
        "AND trip_start_timestamp IS NOT NULL "
        "AND trip_end_timestamp IS NOT NULL "
        f"AND trip_start_timestamp <= "
        f"'{base.format_socrata_timestamp(upper_start)}' "
        f"AND trip_end_timestamp >= "
        f"'{base.format_socrata_timestamp(lower_end)}'"
    )
    null_start_where = (
        f"{base.TARGET_PREDICATE} AND trip_start_timestamp IS NULL"
    )
    null_end_where = f"{base.TARGET_PREDICATE} AND trip_end_timestamp IS NULL"

    candidate_raw, candidate_apis, candidate_ledger = _fetch_candidates(
        determinate_where=determinate_where,
        null_start_where=null_start_where,
        null_end_where=null_end_where,
        lower_end=lower_end,
        core_start=core_start,
        max_unique_rows=args.max_candidate_rows,
        page_size=args.page_size,
        timeout=args.request_timeout,
        attempts=args.request_attempts,
    )
    candidates = base.parse_rows(candidate_raw)
    starts = sorted(
        {row.released_start for row in candidates if row.released_start is not None}
    )
    ends = sorted(
        {row.released_end for row in candidates if row.released_end is not None}
    )
    if not starts or not ends:
        raise base.AuditError(
            "candidate union has no determinate released endpoint bins"
        )

    contributor_raw, contributor_apis, contributor_ledger = _fetch_contributors(
        starts=starts,
        ends=ends,
        max_unique_rows=args.max_contributor_rows,
        page_size=args.page_size,
        timeout=args.request_timeout,
        attempts=args.request_attempts,
    )

    snapshot_after = base.fetch_snapshot(
        timeout=args.request_timeout,
        attempts=args.request_attempts,
    )
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report = base.build_report(
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        core_start=core_start,
        core_raw=core_raw,
        candidate_raw=candidate_raw,
        contributor_raw=contributor_raw,
        expected_candidate_count=len(candidate_raw),
        confirmed_candidate_count=len(candidate_raw),
        expected_contributor_count=len(contributor_raw),
        confirmed_contributor_count=len(contributor_raw),
        candidate_api_paths=candidate_apis,
        contributor_api_paths=contributor_apis,
        generated_at_utc=generated_at,
        solver_time_limit=args.solver_time_limit,
    )
    extraction = report["extraction"]
    extraction["fetch_strategy"] = FETCH_STRATEGY
    extraction["candidate_fetch_ledger"] = candidate_ledger
    extraction["contributor_fetch_ledger"] = contributor_ledger
    extraction["broad_or_query_used"] = False
    extraction["full_row_cross_column_range_query_used"] = False
    extraction["narrow_cross_column_index_query_used"] = True
    extraction["exact_endpoint_bin_full_row_shards_used"] = True

    report.pop("report_sha256_without_self_hash", None)
    report["report_sha256_without_self_hash"] = hashlib.sha256(
        base.canonical_json_bytes(report)
    ).hexdigest()
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = base.parse_args(argv)
    try:
        report = run_live(args)
    except Exception as exc:
        print(
            f"release-operator audit failed closed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "release_operator_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        base.render_markdown(report),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "overall_status": report["overall_status"],
                "candidate_rows": report["extraction"]["candidate_rows"],
                "all_trip_contributors": report["extraction"][
                    "all_trip_release_cell_contributor_rows"
                ],
                "fetch_strategy": report["extraction"]["fetch_strategy"],
                "candidate_start_partitions": report["extraction"][
                    "candidate_fetch_ledger"
                ]["exact_start_partition_count"],
                "contributor_start_partitions": report["extraction"][
                    "contributor_fetch_ledger"
                ]["start_partition_count"],
                "contributor_end_partitions": report["extraction"][
                    "contributor_fetch_ledger"
                ]["end_partition_count"],
                "outer_envelope_graph_cover_multiplicity": report[
                    "released_time_envelope_graph_sensitivity"
                ][
                    "outer_released_time_envelope_graph_core_cover_multiplicity_status"
                ],
                "output_dir": str(args.output_dir),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
