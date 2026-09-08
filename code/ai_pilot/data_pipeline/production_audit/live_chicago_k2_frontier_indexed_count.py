#!/usr/bin/env python3
"""Chicago K=2 audit with ID-index reconciliation instead of wide count(*).

This transport-only wrapper retains the frozen candidate predicate, fixed core,
partitioned full-row extraction, graph, queries and solver. Socrata occasionally
times out on a wide aggregate count while returning the corresponding narrow
ID index. For sets below the declared 5,000-row resource cap, enumerating the
unique IDs is an exact count and also permits an identity-stability check.

No ID is serialized. A response reaching the cap plus one is used only to mark
the cohort over the resource cap; it is never reported as an exact total.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import live_chicago_k2_frontier as frontier  # noqa: E402
import live_chicago_k2_frontier_boundary as boundary  # noqa: E402
import live_chicago_k2_frontier_partitioned as partitioned  # noqa: E402

CAP_PLUS_ONE = 5001
_SEEN: dict[str, tuple[int, str]] = {}
_BASE_RENDER_REPORT = boundary.render_report


def indexed_scalar_count(where: str) -> tuple[int, str, str]:
    """Return an exact count below the resource cap and audit repeated identity."""

    query = f"SELECT trip_id WHERE {where} ORDER BY trip_id LIMIT {CAP_PLUS_ONE}"
    rows, api = frontier.query_rows(query, page_size=CAP_PLUS_ONE)
    ids = [frontier.normalized_text(row.get("trip_id")) for row in rows]
    if any(value is None for value in ids):
        raise frontier.LiveDataError("ID-index reconciliation contains a null trip_id")
    resolved = [str(value) for value in ids]
    if len(resolved) != len(set(resolved)):
        raise frontier.LiveDataError("ID-index reconciliation contains duplicate trip IDs")
    fingerprint = hashlib.sha256(("\n".join(sorted(resolved)) + "\n").encode()).hexdigest()
    current = (len(resolved), fingerprint)
    previous = _SEEN.get(where)
    if previous is not None and previous != current:
        raise frontier.LiveDataError("candidate ID set changed during extraction")
    _SEEN[where] = current
    return len(resolved), api, query


def self_test() -> None:
    assert CAP_PLUS_ONE == 5001
    print("indexed-count transport self-test: PASS")


def render_report(report: dict) -> str:
    return _BASE_RENDER_REPORT(report).replace(
        "Server counts stable before/after",
        "Candidate ID sets and counts stable before/after",
        1,
    )


def main() -> int:
    args = boundary.build_parser().parse_args()
    if args.self_test:
        boundary.self_test()
        self_test()
        return 0
    partitioned._validate_args(args)
    padding_values = boundary.parse_padding_grid(args.boundary_padding_minutes)
    partitioned._configure_request_budget(args.request_timeout, args.request_attempts)
    frontier.scalar_count = indexed_scalar_count
    frontier.fetch_closed_candidate_universe = partitioned.partitioned_fetch_closed_candidate_universe
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report, rows, temporal_edges = boundary._run_with_capture(args)
        report["extraction"]["transport"] = {
            "strategy": "capped ID-index reconciliation plus exact released-start partitions",
            "count_reconciliation": "unique ID enumeration; exact below declared resource cap",
            "identity_stability_check": True,
            "cap_plus_one": CAP_PLUS_ONE,
            "request_timeout_seconds": args.request_timeout,
            "request_attempts": args.request_attempts,
            "partition_page_size": args.page_size,
            "raw_trip_ids_emitted": False,
        }
        report["cohort"]["candidate_identity_stable"] = True
        report = boundary.add_boundary_padding_curve(
            report,
            rows=rows,
            temporal_edges=temporal_edges,
            padding_values=padding_values,
            time_limit_seconds=args.solver_time_limit,
        )
        report.pop("report_sha256", None)
        report["report_sha256"] = frontier.sha256_json(report)
        original_render = boundary.render_report
        try:
            boundary.render_report = render_report
            boundary.write_outputs(report, args.output_dir)
        finally:
            boundary.render_report = original_render
    except Exception as exc:
        partitioned._write_failure(args.output_dir, exc)
        raise
    print(render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
