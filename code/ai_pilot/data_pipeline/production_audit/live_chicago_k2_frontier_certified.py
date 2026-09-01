#!/usr/bin/env python3
"""Live Chicago K=2 runner with exact Gamma-endpoint reductions.

The public-data frontier has two algebraic endpoint identities:

* ``Gamma = 0`` is exactly the base-radius graph, because every edge outside
  that graph has positive core-incidence cost; and
* ``Gamma = |C|`` is exactly the temporal-only graph, because every feasible
  core cover uses exactly ``|C|`` core incidences and every miss cost is at
  most the corresponding core incidence.

Solving the two endpoint formulations on the full 24k-edge temporal graph is
unnecessarily slower and can create solver-status asymmetry relative to the
identical radius formulations.  This runner enforces the identities by solving
their equivalent reduced formulations: the base graph at Gamma zero and the
unconstrained temporal graph at Gamma ``|C|``.  Intermediate Gamma values keep
the original budgeted MILP.

The transport, redaction, public temporal closure, and scientific claim
boundaries are inherited from ``live_chicago_k2_frontier_partitioned``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import live_chicago_k2_frontier_partitioned as partitioned  # noqa: E402

frontier = partitioned.frontier
_ORIGINAL_SOLVE_CURVE_POINT = frontier.solve_curve_point
_ORIGINAL_ENDPOINT_IDENTITY_AUDIT = frontier.endpoint_identity_audit
_CAPTURED_IDENTITY_AUDIT: dict[str, Any] = {}


def _rewrite_gamma_result(
    graph_point: Any,
    query_rows: list[dict[str, Any]],
    *,
    gamma: int,
) -> tuple[Any, list[dict[str, Any]]]:
    rewritten_graph = replace(graph_point, gamma_core_incidences=gamma)
    rewritten_rows: list[dict[str, Any]] = []
    for row in query_rows:
        rewritten = dict(row)
        rewritten["gamma_core_incidences"] = gamma
        rewritten_rows.append(rewritten)
    return rewritten_graph, rewritten_rows


def solve_curve_point_with_exact_gamma_endpoints(
    *,
    rows: Sequence[Any],
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
) -> tuple[Any, list[dict[str, Any]]]:
    """Use equivalent graph formulations at the two Gamma endpoints."""

    if curve_type != "gamma" or gamma is None:
        return _ORIGINAL_SOLVE_CURVE_POINT(
            rows=rows,
            edges=edges,
            temporal_edge_count=temporal_edge_count,
            unmeasured_edges=unmeasured_edges,
            curve_type=curve_type,
            parameter_label=parameter_label,
            parameter_value=parameter_value,
            radius_km=radius_km,
            gamma=gamma,
            miss_costs=miss_costs,
            time_limit_seconds=time_limit_seconds,
        )
    if miss_costs is None or len(miss_costs) != len(edges):
        raise ValueError("Gamma endpoint reduction requires one miss cost per edge")

    core_count = sum(getattr(row, "role", None) == "core" for row in rows)
    if gamma == 0:
        retained_positions = [
            position for position, cost in enumerate(miss_costs) if int(cost) == 0
        ]
        reduced_edges = [edges[position] for position in retained_positions]
        graph_point, query_rows = _ORIGINAL_SOLVE_CURVE_POINT(
            rows=rows,
            edges=reduced_edges,
            temporal_edge_count=temporal_edge_count,
            unmeasured_edges=unmeasured_edges,
            curve_type=curve_type,
            parameter_label=parameter_label,
            parameter_value=parameter_value,
            radius_km=radius_km,
            gamma=None,
            miss_costs=None,
            time_limit_seconds=time_limit_seconds,
        )
        return _rewrite_gamma_result(graph_point, query_rows, gamma=gamma)

    if gamma == core_count:
        graph_point, query_rows = _ORIGINAL_SOLVE_CURVE_POINT(
            rows=rows,
            edges=edges,
            temporal_edge_count=temporal_edge_count,
            unmeasured_edges=unmeasured_edges,
            curve_type=curve_type,
            parameter_label=parameter_label,
            parameter_value=parameter_value,
            radius_km=radius_km,
            gamma=None,
            miss_costs=None,
            time_limit_seconds=time_limit_seconds,
        )
        return _rewrite_gamma_result(graph_point, query_rows, gamma=gamma)

    return _ORIGINAL_SOLVE_CURVE_POINT(
        rows=rows,
        edges=edges,
        temporal_edge_count=temporal_edge_count,
        unmeasured_edges=unmeasured_edges,
        curve_type=curve_type,
        parameter_label=parameter_label,
        parameter_value=parameter_value,
        radius_km=radius_km,
        gamma=gamma,
        miss_costs=miss_costs,
        time_limit_seconds=time_limit_seconds,
    )


def capture_endpoint_identity_audit(*args: Any, **kwargs: Any) -> dict[str, Any]:
    result = _ORIGINAL_ENDPOINT_IDENTITY_AUDIT(*args, **kwargs)
    _CAPTURED_IDENTITY_AUDIT.clear()
    _CAPTURED_IDENTITY_AUDIT.update(result)
    return result


def _write_failure(output_dir: Path, exc: Exception) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    failure = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "failed",
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "progress": dict(partitioned._PROGRESS),
        "endpoint_identity_audit": (
            dict(_CAPTURED_IDENTITY_AUDIT) if _CAPTURED_IDENTITY_AUDIT else None
        ),
        "raw_rows_emitted": False,
        "raw_trip_ids_emitted": False,
    }
    (output_dir / "failure.json").write_text(
        json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = partitioned.build_parser().parse_args()
    if args.self_test:
        frontier.self_test()
        print("certified Gamma endpoint reduction self-test: PASS")
        return 0

    partitioned._validate_args(args)
    partitioned._configure_request_budget(
        args.request_timeout, args.request_attempts
    )
    frontier.fetch_closed_candidate_universe = (
        partitioned.partitioned_fetch_closed_candidate_universe
    )
    frontier.solve_curve_point = solve_curve_point_with_exact_gamma_endpoints
    frontier.endpoint_identity_audit = capture_endpoint_identity_audit
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = frontier.run(args)
        report["extraction"]["transport"] = {
            "strategy": "narrow index plus exact released-start partitions",
            "request_timeout_seconds": args.request_timeout,
            "request_attempts": args.request_attempts,
            "partition_page_size": args.page_size,
        }
        report["gamma_curve"]["endpoint_formulations"] = {
            "gamma_zero": "exact equivalent base-radius graph formulation",
            "gamma_core_count": "exact equivalent unconstrained temporal formulation",
            "intermediate_gamma": "full temporal graph with measured out-of-radius incidence budget",
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
