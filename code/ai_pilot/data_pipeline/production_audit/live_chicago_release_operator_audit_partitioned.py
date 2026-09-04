#!/usr/bin/env python3
"""Partitioned live Chicago release-operator audit.

This is a network-robust entrypoint for the v2 release-operator audit.  It keeps
exactly the same scientific candidate semantics as
``live_chicago_release_operator_audit.py`` but avoids broad Socrata ``OR``
queries that can force full-table scans.

The candidate universe is fetched as the union of three count-closed branches:
(1) determinate released times whose outer envelopes can intersect the core,
(2) target K=2 rows with a null released start, and (3) target K=2 rows with a
null released end.  All-trip endpoint-bin contributors are likewise fetched as
the union of start-bin and end-bin branches.  Branch unions are deduplicated by
public ``trip_id`` and fail closed if duplicate payloads disagree.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import live_chicago_release_operator_audit as base


def _union_rows(
    branch_wheres: Sequence[str],
    *,
    page_size: int,
    timeout: int,
    attempts: int,
    max_unique_rows: int,
    label: str,
) -> tuple[list[dict[str, Any]], list[str], list[int]]:
    """Fetch a deterministic union from individually count-closed branches."""
    rows_by_id: dict[str, dict[str, Any]] = {}
    apis: list[str] = []
    counts: list[int] = []
    request = {
        "page_size": page_size,
        "timeout": timeout,
        "attempts": attempts,
    }
    for branch_index, where in enumerate(branch_wheres):
        count, _count_api, _count_query = base.scalar_count(where, **request)
        counts.append(count)
        if count > max_unique_rows:
            raise base.AuditError(
                f"{label} branch {branch_index} count {count} exceeds max "
                f"{max_unique_rows}"
            )
        if count == 0:
            continue
        branch_rows, branch_apis, _base_query = base.paged_select(
            where=where,
            expected_count=count,
            **request,
        )
        apis.extend(branch_apis)
        for row in branch_rows:
            trip_id = base.normalized_text(row.get("trip_id"))
            if trip_id is None:
                raise base.AuditError(f"{label} branch returned row without trip_id")
            previous = rows_by_id.get(trip_id)
            if previous is not None and previous != row:
                raise base.AuditError(
                    f"{label} duplicate trip_id has inconsistent public payload"
                )
            rows_by_id[trip_id] = row
            if len(rows_by_id) > max_unique_rows:
                raise base.AuditError(
                    f"{label} union exceeds max {max_unique_rows} unique rows"
                )

    # Recheck every branch count before accepting the union.  The dataset-level
    # revision fingerprint is checked again after all extraction by build_report.
    for branch_index, (where, expected) in enumerate(zip(branch_wheres, counts)):
        confirmed, _api, _query = base.scalar_count(where, **request)
        if confirmed != expected:
            raise base.AuditError(
                f"{label} branch {branch_index} count changed during extraction: "
                f"{expected} -> {confirmed}"
            )

    ordered = sorted(
        rows_by_id.values(),
        key=lambda row: (
            base.normalized_text(row.get("trip_start_timestamp")) or "",
            base.normalized_text(row.get("trip_end_timestamp")) or "",
            base.normalized_text(row.get("trip_id")) or "",
        ),
    )
    return ordered, apis, counts


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
        row.released_start for row in parsed_core if row.released_start is not None
    ) - timedelta(minutes=2 * base.ROUNDING_HALF_MINUTES)
    upper_start = max(
        row.released_end for row in parsed_core if row.released_end is not None
    ) + timedelta(minutes=2 * base.ROUNDING_HALF_MINUTES)

    # Scientific semantics are identical to the original broad OR predicate,
    # but each branch is independently count-closed and index-friendlier.
    candidate_branches = (
        (
            f"{base.TARGET_PREDICATE} "
            "AND trip_start_timestamp IS NOT NULL "
            "AND trip_end_timestamp IS NOT NULL "
            f"AND trip_start_timestamp <= '{base.format_socrata_timestamp(upper_start)}' "
            f"AND trip_end_timestamp >= '{base.format_socrata_timestamp(lower_end)}'"
        ),
        f"{base.TARGET_PREDICATE} AND trip_start_timestamp IS NULL",
        f"{base.TARGET_PREDICATE} AND trip_end_timestamp IS NULL",
    )
    candidate_raw, candidate_apis, candidate_branch_counts = _union_rows(
        candidate_branches,
        max_unique_rows=args.max_candidate_rows,
        label="candidate",
        **request,
    )
    candidate_count = len(candidate_raw)
    candidates = base.parse_rows(candidate_raw)

    starts = sorted(
        {row.released_start for row in candidates if row.released_start is not None}
    )
    ends = sorted(
        {row.released_end for row in candidates if row.released_end is not None}
    )
    if not starts or not ends:
        raise base.AuditError("candidate union has no determinate released endpoint bins")

    contributor_branches = (
        f"trip_start_timestamp IN {base._in_literal(starts)}",
        f"trip_end_timestamp IN {base._in_literal(ends)}",
    )
    contributor_raw, contributor_apis, contributor_branch_counts = _union_rows(
        contributor_branches,
        max_unique_rows=args.max_contributor_rows,
        label="contributor",
        **request,
    )
    contributor_count = len(contributor_raw)

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
        expected_candidate_count=candidate_count,
        confirmed_candidate_count=candidate_count,
        expected_contributor_count=contributor_count,
        confirmed_contributor_count=contributor_count,
        candidate_api_paths=candidate_apis,
        contributor_api_paths=contributor_apis,
        generated_at_utc=generated_at,
        solver_time_limit=args.solver_time_limit,
    )
    report["extraction"]["fetch_strategy"] = (
        "PARTITIONED_COUNT_CLOSED_BRANCH_UNION_WITH_PUBLIC_TRIP_ID_DEDUPLICATION"
    )
    report["extraction"]["candidate_branch_counts"] = candidate_branch_counts
    report["extraction"]["contributor_branch_counts"] = contributor_branch_counts
    report["extraction"]["broad_or_query_used"] = False
    # Refresh self-hash after adding extraction metadata.
    report.pop("report_sha256_without_self_hash", None)
    report["report_sha256_without_self_hash"] = base.hashlib.sha256(
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
    report_path = args.output_dir / "release_operator_audit.json"
    markdown_path = args.output_dir / "REPORT.md"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(base.render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "overall_status": report["overall_status"],
                "candidate_rows": report["extraction"]["candidate_rows"],
                "all_trip_contributors": report["extraction"][
                    "all_trip_release_cell_contributor_rows"
                ],
                "candidate_branch_counts": report["extraction"][
                    "candidate_branch_counts"
                ],
                "contributor_branch_counts": report["extraction"][
                    "contributor_branch_counts"
                ],
                "outer_envelope_graph_cover_multiplicity": report[
                    "released_time_envelope_graph_sensitivity"
                ]["outer_released_time_envelope_graph_core_cover_multiplicity_status"],
                "output_dir": str(args.output_dir),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
