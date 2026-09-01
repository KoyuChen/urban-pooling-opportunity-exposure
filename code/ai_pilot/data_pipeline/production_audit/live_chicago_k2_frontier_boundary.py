#!/usr/bin/env python3
"""Add boundary-padding sensitivity to the live Chicago K=2 frontier.

This wrapper keeps the partitioned, count-reconciled Socrata transport and the
base radius/Gamma analysis unchanged.  It adds a third nested support family:
retain every core row, every timestamp-indeterminate target row, and only those
determinate buffer rows satisfying

    released_start <= max_core_released_end + p
    released_end   >= min_core_released_start - p.

Under the declared +/-7.5 minute timestamp-rounding model, p=15 minutes is the
boundary-complete endpoint because 15=2*delta.  Values below 15 deliberately
stress an under-padded candidate universe.  Values above 15 are canonically
identical to the complete endpoint: rows outside the p=15 retrieval envelope
cannot form a core-incident temporal edge under that model.  This remains a
public candidate-support analysis, not hidden-run closure or partner recall.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import live_chicago_k2_frontier as frontier  # noqa: E402
import live_chicago_k2_frontier_partitioned as partitioned  # noqa: E402


FULL_BOUNDARY_PADDING_MINUTES = 2.0 * frontier.ROUNDING_HALF_MINUTES
DEFAULT_BOUNDARY_PADDING_MINUTES = (0.0, 5.0, 10.0, 15.0, 30.0)


def parse_padding_grid(value: str | Sequence[float]) -> list[float]:
    """Parse a strict, finite padding grid containing the complete endpoint."""

    if isinstance(value, str):
        pieces = [piece.strip() for piece in value.split(",") if piece.strip()]
        try:
            parsed = [float(piece) for piece in pieces]
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "--boundary-padding-minutes must be comma-separated numbers"
            ) from exc
    else:
        parsed = [float(item) for item in value]
    if len(parsed) < 2:
        raise argparse.ArgumentTypeError(
            "boundary-padding grid must contain at least two points"
        )
    if any(not math.isfinite(item) or item < 0 for item in parsed):
        raise argparse.ArgumentTypeError(
            "boundary-padding values must be finite and nonnegative"
        )
    if len(parsed) != len(set(parsed)):
        raise argparse.ArgumentTypeError(
            "boundary-padding values must be unique"
        )
    ordered = sorted(parsed)
    if not any(
        math.isclose(
            item,
            FULL_BOUNDARY_PADDING_MINUTES,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for item in ordered
    ):
        raise argparse.ArgumentTypeError(
            f"boundary-padding grid must include {FULL_BOUNDARY_PADDING_MINUTES:g} minutes"
        )
    return ordered


def padding_label(padding_minutes: float) -> str:
    return f"{padding_minutes:g} min"


def _core_release_extrema(
    rows: Sequence[frontier.TripRow],
) -> tuple[datetime, datetime]:
    core = [row for row in rows if row.role == "core"]
    starts = [row.released_start for row in core]
    ends = [row.released_end for row in core]
    if not core or any(value is None for value in starts) or any(
        value is None for value in ends
    ):
        raise frontier.LiveDataError(
            "boundary-padding curve requires a nonempty core with released starts and ends"
        )
    return min(value for value in starts if value is not None), max(
        value for value in ends if value is not None
    )


def rows_for_boundary_padding(
    rows: Sequence[frontier.TripRow],
    *,
    padding_minutes: float,
) -> tuple[list[frontier.TripRow], dict[str, Any]]:
    """Return the nested row universe for one boundary-padding value.

    Timestamp-indeterminate buffer rows are retained at every point.  They
    cannot be safely excluded by a released-time cutoff.  Context rows are not
    model rows and are never introduced by this wrapper.
    """

    if not math.isfinite(padding_minutes) or padding_minutes < 0:
        raise ValueError("padding_minutes must be finite and nonnegative")
    core_min_start, core_max_end = _core_release_extrema(rows)
    lower_end_cutoff = core_min_start - timedelta(minutes=padding_minutes)
    upper_start_cutoff = core_max_end + timedelta(minutes=padding_minutes)
    retained: list[frontier.TripRow] = []
    dropped_buffer = 0
    retained_indeterminate_buffer = 0
    for row in rows:
        if row.role == "core":
            retained.append(row)
            continue
        if row.role != "buffer":
            continue
        if row.released_start is None or row.released_end is None:
            retained.append(row)
            retained_indeterminate_buffer += 1
            continue
        if (
            row.released_start <= upper_start_cutoff
            and row.released_end >= lower_end_cutoff
        ):
            retained.append(row)
        else:
            dropped_buffer += 1
    retained.sort(key=lambda row: row.index)
    return retained, {
        "padding_minutes": float(padding_minutes),
        "lower_released_end_cutoff": lower_end_cutoff.isoformat(),
        "upper_released_start_cutoff": upper_start_cutoff.isoformat(),
        "retained_core_rows": sum(row.role == "core" for row in retained),
        "retained_buffer_rows": sum(row.role == "buffer" for row in retained),
        "retained_indeterminate_buffer_rows": retained_indeterminate_buffer,
        "dropped_buffer_rows": dropped_buffer,
    }


def _canonical_reuse_complete_padding(
    *,
    source_graph_point: Mapping[str, Any],
    source_query_rows: Sequence[Mapping[str, Any]],
    padding_minutes: float,
    full_edge_count: int,
    full_unmeasured_edges: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reuse p=2*delta endpoints for any p>2*delta."""

    label = padding_label(padding_minutes)
    graph = frontier.GraphPoint(
        curve_type="buffer_padding",
        parameter_label=label,
        parameter_value=float(padding_minutes),
        radius_km=None,
        gamma_core_incidences=None,
        edge_count=full_edge_count,
        retained_fraction_of_temporal=1.0 if full_edge_count else 0.0,
        spatially_unmeasured_edges_retained=full_unmeasured_edges,
        core_zero_degree_count=int(source_graph_point["core_zero_degree_count"]),
        core_min_degree=source_graph_point.get("core_min_degree"),
        core_max_degree=source_graph_point.get("core_max_degree"),
        cover_status=str(source_graph_point["cover_status"]),
        cover_mip_gap=source_graph_point.get("cover_mip_gap"),
    )
    graph_payload = asdict(graph)
    query_rows = [
        {
            **dict(row),
            **graph_payload,
            "endpoint_source": "canonical_complete_boundary_identity",
        }
        for row in source_query_rows
    ]
    return graph_payload, query_rows


def boundary_padding_identity_audit(
    *,
    padding_values: Sequence[float],
    node_sets: Mapping[float, set[int]],
    edge_sets: Mapping[float, set[tuple[int, int]]],
    full_temporal_edges: set[tuple[int, int]],
    sensitivity_rows: Sequence[Mapping[str, Any]],
    tolerance: float = 1e-7,
) -> dict[str, Any]:
    """Fail closed on nesting and the p>=2*delta endpoint identity."""

    mismatches: list[dict[str, Any]] = []
    ordered = sorted(float(value) for value in padding_values)
    if ordered != list(padding_values):
        mismatches.append({"reason": "padding_grid_not_sorted"})
    if len(ordered) != len(set(ordered)):
        mismatches.append({"reason": "padding_grid_not_unique"})
    full_points = [
        value
        for value in ordered
        if math.isclose(
            value,
            FULL_BOUNDARY_PADDING_MINUTES,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ]
    if len(full_points) != 1:
        mismatches.append(
            {
                "reason": "complete_padding_endpoint_missing_or_duplicated",
                "expected": FULL_BOUNDARY_PADDING_MINUTES,
                "observed": full_points,
            }
        )
    for left, right in zip(ordered, ordered[1:]):
        if left not in node_sets or right not in node_sets:
            mismatches.append(
                {
                    "reason": "missing_node_set",
                    "left_padding": left,
                    "right_padding": right,
                }
            )
        elif not node_sets[left] <= node_sets[right]:
            mismatches.append(
                {
                    "reason": "row_universe_not_nested",
                    "left_padding": left,
                    "right_padding": right,
                }
            )
        if left not in edge_sets or right not in edge_sets:
            mismatches.append(
                {
                    "reason": "missing_edge_set",
                    "left_padding": left,
                    "right_padding": right,
                }
            )
        elif not edge_sets[left] <= edge_sets[right]:
            mismatches.append(
                {
                    "reason": "edge_universe_not_nested",
                    "left_padding": left,
                    "right_padding": right,
                }
            )
    full_padding = FULL_BOUNDARY_PADDING_MINUTES
    if full_padding in edge_sets and edge_sets[full_padding] != full_temporal_edges:
        mismatches.append(
            {
                "reason": "complete_padding_does_not_equal_full_temporal_graph",
                "complete_edge_count": len(edge_sets[full_padding]),
                "full_edge_count": len(full_temporal_edges),
            }
        )
    for value in ordered:
        if value + 1e-9 < full_padding:
            continue
        if value in edge_sets and edge_sets[value] != full_temporal_edges:
            mismatches.append(
                {
                    "reason": "post_complete_padding_changed_edge_set",
                    "padding_minutes": value,
                    "edge_count": len(edge_sets[value]),
                    "full_edge_count": len(full_temporal_edges),
                }
            )

    def rows_at(padding: float) -> dict[str, Mapping[str, Any]]:
        selected: dict[str, Mapping[str, Any]] = {}
        for row in sensitivity_rows:
            if row.get("curve_type") != "buffer_padding":
                continue
            try:
                value = float(row.get("parameter_value"))
            except (TypeError, ValueError):
                continue
            if math.isclose(value, padding, rel_tol=0.0, abs_tol=1e-9):
                query = str(row.get("query"))
                if query in selected:
                    mismatches.append(
                        {
                            "reason": "duplicate_query_at_padding",
                            "padding_minutes": padding,
                            "query": query,
                        }
                    )
                selected[query] = row
        return selected

    complete_rows = rows_at(full_padding)
    comparisons = 0
    for value in ordered:
        if value <= full_padding + 1e-9:
            continue
        candidate_rows = rows_at(value)
        if set(candidate_rows) != set(complete_rows) or not complete_rows:
            mismatches.append(
                {
                    "reason": "post_complete_query_set_mismatch_or_empty",
                    "padding_minutes": value,
                }
            )
            continue
        for query in sorted(complete_rows):
            comparisons += 1
            left = complete_rows[query]
            right = candidate_rows[query]
            if right.get("endpoint_source") != "canonical_complete_boundary_identity":
                mismatches.append(
                    {
                        "reason": "post_complete_endpoint_not_canonical",
                        "padding_minutes": value,
                        "query": query,
                    }
                )
            for field in (
                "endpoint_pair_certification",
                "lower_status",
                "upper_status",
                "edges_with_missing_query_values",
                "query_missing_semantics",
            ):
                if left.get(field) != right.get(field):
                    mismatches.append(
                        {
                            "reason": f"post_complete_{field}_mismatch",
                            "padding_minutes": value,
                            "query": query,
                        }
                    )
            for field in (
                "lower",
                "upper",
                "width",
                "lower_mip_gap",
                "upper_mip_gap",
                "max_replay_residual",
            ):
                left_value = left.get(field)
                right_value = right.get(field)
                if left_value is None or right_value is None:
                    equal = left_value is None and right_value is None
                else:
                    try:
                        equal = math.isclose(
                            float(left_value),
                            float(right_value),
                            rel_tol=tolerance,
                            abs_tol=tolerance,
                        )
                    except (TypeError, ValueError):
                        equal = False
                if not equal:
                    mismatches.append(
                        {
                            "reason": f"post_complete_{field}_mismatch",
                            "padding_minutes": value,
                            "query": query,
                            "complete": left_value,
                            "candidate": right_value,
                        }
                    )
    return {
        "expected": (
            "row and edge universes are nested in padding; p=2*delta equals the "
            "full temporal graph; every p>2*delta reuses the same certified endpoint"
        ),
        "rounding_half_width_minutes": frontier.ROUNDING_HALF_MINUTES,
        "complete_padding_minutes": FULL_BOUNDARY_PADDING_MINUTES,
        "post_complete_query_comparison_count": comparisons,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "status": "PASS" if not mismatches else "FAIL",
    }


def add_boundary_padding_curve(
    report: dict[str, Any],
    *,
    rows: Sequence[frontier.TripRow],
    temporal_edges: Sequence[tuple[int, int]],
    padding_values: Sequence[float],
    time_limit_seconds: float,
) -> dict[str, Any]:
    """Append the third sensitivity family and recompute all chain audits."""

    ordered_values = parse_padding_grid(padding_values)
    rows_by_index = {row.index: row for row in rows}
    route_radius = {
        edge: frontier.edge_route_radius(rows_by_index, edge) for edge in temporal_edges
    }
    full_edge_set = set(temporal_edges)
    full_unmeasured = sum(route_radius[edge] is None for edge in temporal_edges)
    graph_points: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    node_sets: dict[float, set[int]] = {}
    edge_sets: dict[float, set[tuple[int, int]]] = {}
    direct_graph_by_padding: dict[float, dict[str, Any]] = {}
    direct_rows_by_padding: dict[float, list[dict[str, Any]]] = {}

    for padding in ordered_values:
        subset_rows, subset_audit = rows_for_boundary_padding(
            rows, padding_minutes=padding
        )
        node_sets[padding] = {row.index for row in subset_rows}
        if padding > FULL_BOUNDARY_PADDING_MINUTES + 1e-9:
            source_graph = direct_graph_by_padding[FULL_BOUNDARY_PADDING_MINUTES]
            source_rows = direct_rows_by_padding[FULL_BOUNDARY_PADDING_MINUTES]
            graph_payload, point_rows = _canonical_reuse_complete_padding(
                source_graph_point=source_graph,
                source_query_rows=source_rows,
                padding_minutes=padding,
                full_edge_count=len(temporal_edges),
                full_unmeasured_edges=full_unmeasured,
            )
            edge_sets[padding] = set(temporal_edges)
            subset_audit = {
                **subset_audit,
                "identity_basis": (
                    "canonical reuse of p=2*delta; rows outside that retrieval "
                    "envelope cannot form a core-incident temporal edge"
                ),
            }
        else:
            point_edges, _ = frontier.build_temporal_edges(subset_rows)
            point_edge_set = set(point_edges)
            if not point_edge_set <= full_edge_set:
                raise frontier.LiveDataError(
                    f"padding {padding:g} produced an edge outside the closed universe"
                )
            unmeasured = sum(route_radius[edge] is None for edge in point_edges)
            graph_point, point_rows = frontier.solve_curve_point(
                rows=subset_rows,
                edges=point_edges,
                temporal_edge_count=len(temporal_edges),
                unmeasured_edges=unmeasured,
                curve_type="buffer_padding",
                parameter_label=padding_label(padding),
                parameter_value=float(padding),
                radius_km=None,
                gamma=None,
                miss_costs=None,
                time_limit_seconds=time_limit_seconds,
            )
            graph_payload = asdict(graph_point)
            edge_sets[padding] = point_edge_set
            direct_graph_by_padding[padding] = graph_payload
            direct_rows_by_padding[padding] = point_rows
        graph_points.append(
            {
                **graph_payload,
                **subset_audit,
                "endpoint_source": (
                    "direct_milp"
                    if padding <= FULL_BOUNDARY_PADDING_MINUTES + 1e-9
                    else "canonical_complete_boundary_identity"
                ),
            }
        )
        query_rows.extend(point_rows)

    audit = boundary_padding_identity_audit(
        padding_values=ordered_values,
        node_sets=node_sets,
        edge_sets=edge_sets,
        full_temporal_edges=full_edge_set,
        sensitivity_rows=query_rows,
    )
    if audit["status"] != "PASS":
        raise frontier.LiveDataError(
            "boundary-padding endpoint identity audit failed: "
            + json.dumps(audit["mismatches"][:8], sort_keys=True)
        )

    report["sensitivity_rows"] = [*report["sensitivity_rows"], *query_rows]
    expected_labels = {
        "radius": [str(point["parameter_label"]) for point in report["radius_graph_points"]],
        "gamma": [str(point["parameter_label"]) for point in report["gamma_graph_points"]],
        "buffer_padding": [padding_label(value) for value in ordered_values],
    }
    monotonicity = frontier.monotonicity_audit(
        report["sensitivity_rows"],
        expected_parameter_labels=expected_labels,
        expected_queries=[spec.name for spec in frontier.query_specs()],
    )
    if monotonicity["status"] == "FAIL":
        raise frontier.LiveDataError(
            "no complete, certified, monotone support-sensitivity query chain remains "
            "after adding boundary padding"
        )

    report["report_version"] = "chicago-k2-public-temporal-candidate-universe/v3"
    report["boundary_padding_curve"] = {
        "parameter": "released-time boundary padding p in minutes",
        "rounding_half_width_minutes": frontier.ROUNDING_HALF_MINUTES,
        "complete_padding_minutes": FULL_BOUNDARY_PADDING_MINUTES,
        "grid_minutes": ordered_values,
        "indeterminate_timestamp_buffers_retained_at_every_point": True,
        "below_complete_endpoint_interpretation": (
            "intentional under-padding stress test; not a closed candidate universe"
        ),
        "at_complete_endpoint_interpretation": (
            "boundary-complete for core-incident public temporal edges under the "
            "declared +/-7.5 minute release model"
        ),
        "above_complete_endpoint_interpretation": (
            "same feasible set by endpoint identity; canonical reuse rather than a "
            "claim of recursively closed hidden runs"
        ),
    }
    report["boundary_padding_graph_points"] = graph_points
    report["boundary_padding_identity_audit"] = audit
    report["monotonicity_audit"] = monotonicity
    if monotonicity["status"] == "PASS":
        statement = "Every declared curve/query chain is fully certified and monotone."
        clause = "all certified intervals widen monotonically along all three support axes"
    else:
        statement = (
            f"Only {monotonicity['fully_certified_monotone_chain_count']} of "
            f"{monotonicity['chain_count']} entire curve/query chains are fully "
            "certified and monotone, covering "
            f"{monotonicity['fully_certified_monotone_query_family_count']} of "
            f"{monotonicity['query_family_count']} complete query families; no universal "
            "monotonicity claim is made."
        )
        clause = (
            "monotonic widening is supported only for the complete certified chains "
            "identified by the audit across padding, radius, and Gamma"
        )
    report["claim_boundary"]["monotonicity_statement"] = statement
    report["claim_boundary"]["strongest_supported_statement"] = (
        "For one adaptively selected 15-minute smoke-test core, this metadata/count-"
        "stable extraction yields a count-closed, core-incident K=2 public temporal "
        "candidate universe under the declared timestamp-rounding model; the p=15 "
        "minute endpoint is boundary-complete, p>15 is endpoint-identical, and "
        f"{clause}."
    )
    report["claim_boundary"]["prohibited_statement"] = (
        "The true Chicago pooled runs or co-rider partners have been reconstructed; "
        "the buffer is recursively hidden-run closed; padding below 15 minutes has "
        "partner-recall validity; the radius/Gamma axes estimate partner misses; or "
        "this selected bin establishes a Chicago-population effect."
    )
    report.pop("report_sha256", None)
    report["report_sha256"] = frontier.sha256_json(report)
    return report


def _write_union_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError("cannot write an empty table")
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def plot_boundary_padding_curves(
    report: Mapping[str, Any], output_dir: Path
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    points = list(report["boundary_padding_graph_points"])
    points.sort(key=lambda point: float(point["parameter_value"]))
    written: list[str] = []
    x = [float(point["parameter_value"]) for point in points]
    y = [int(point["edge_count"]) for point in points]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(x, y, marker="o")
    ax.axvline(FULL_BOUNDARY_PADDING_MINUTES, linestyle="--")
    ax.set_xlabel("Released-time boundary padding p (minutes)")
    ax.set_ylabel("Core-incident temporal candidate edges")
    ax.set_title("Chicago K=2 boundary-padding support expansion")
    fig.tight_layout()
    path = output_dir / "buffer_padding_edge_curve.svg"
    fig.savefig(path)
    plt.close(fig)
    written.append(path.name)

    by_query: dict[str, list[Mapping[str, Any]]] = {}
    for row in report["sensitivity_rows"]:
        if row.get("curve_type") != "buffer_padding" or row.get("width") is None:
            continue
        by_query.setdefault(str(row["query"]), []).append(row)
    for query, query_rows in sorted(by_query.items()):
        ordered = sorted(query_rows, key=lambda row: float(row["parameter_value"]))
        fig, ax = plt.subplots(figsize=(7.2, 4.6))
        ax.plot(
            [float(row["parameter_value"]) for row in ordered],
            [float(row["width"]) for row in ordered],
            marker="o",
        )
        ax.axvline(FULL_BOUNDARY_PADDING_MINUTES, linestyle="--")
        ax.set_xlabel("Released-time boundary padding p (minutes)")
        ax.set_ylabel(f"Conditional width ({ordered[0]['unit']})")
        ax.set_title(query.replace("_", " "))
        fig.tight_layout()
        slug = query.replace("_per_core", "")
        path = output_dir / f"buffer_padding_{slug}.svg"
        fig.savefig(path)
        plt.close(fig)
        written.append(path.name)
    return written


def _boundary_report_section(report: Mapping[str, Any]) -> str:
    lookup: dict[float, dict[str, Mapping[str, Any]]] = {}
    for row in report["sensitivity_rows"]:
        if row.get("curve_type") != "buffer_padding":
            continue
        padding = float(row["parameter_value"])
        lookup.setdefault(padding, {})[str(row["query"])] = row
    lines = [
        "## Boundary-padding sensitivity",
        "",
        "The boundary-padding axis retains the core and every timestamp-indeterminate "
        "target row, then expands the determinate buffer using released-time padding "
        "`p`. Under the declared rounding model, `p=15` minutes is the complete "
        "endpoint (`2δ`); larger values reuse that endpoint by identity.",
        "",
        "| Padding p | Buffer rows | Edges | Miles-gap width | Duration-gap width (min) | Source |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for point in report["boundary_padding_graph_points"]:
        padding = float(point["parameter_value"])
        miles = lookup.get(padding, {}).get(
            "mean_absolute_trip_miles_gap_per_core", {}
        )
        duration = lookup.get(padding, {}).get(
            "mean_absolute_duration_gap_per_core", {}
        )
        miles_width = "—" if miles.get("width") is None else f"{float(miles['width']):.4f}"
        duration_width = (
            "—"
            if duration.get("width") is None
            else f"{float(duration['width']):.4f}"
        )
        lines.append(
            f"| {point['parameter_label']} | {point['retained_buffer_rows']} | "
            f"{point['edge_count']} | {miles_width} | {duration_width} | "
            f"`{point['endpoint_source']}` |"
        )
    lines.extend(
        [
            "",
            "Padding below 15 minutes is deliberately under-complete and has no partner-"
            "recall interpretation. Padding at or above 15 minutes does not establish "
            "hidden-run closure; it closes only the declared core-incident public temporal "
            "candidate universe.",
            "",
            f"Boundary endpoint identity audit: `{report['boundary_padding_identity_audit']['status']}`.",
        ]
    )
    return "\n".join(lines)


def render_report(report: Mapping[str, Any]) -> str:
    base = frontier.render_report(report)
    marker = "## Measured out-of-radius incidence sensitivity"
    section = _boundary_report_section(report)
    if marker not in base:
        return base + "\n\n" + section + "\n"
    return base.replace(marker, section + "\n\n" + marker, 1)


def write_outputs(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frontier.write_long_csv(
        report["sensitivity_rows"],
        output_dir / "candidate_support_sensitivity.csv",
    )
    graph_rows = [
        *report["radius_graph_points"],
        *report["boundary_padding_graph_points"],
        *report["gamma_graph_points"],
    ]
    _write_union_csv(graph_rows, output_dir / "candidate_graph_curve.csv")
    plot_files = frontier.plot_curves(report["sensitivity_rows"], output_dir)
    plot_files.extend(plot_boundary_padding_curves(report, output_dir))
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


def _run_with_capture(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], list[frontier.TripRow], list[tuple[int, int]]]:
    capture: dict[str, Any] = {}
    original_prepare = frontier.prepare_rows
    original_build = frontier.build_temporal_edges

    def capturing_prepare(*call_args: Any, **call_kwargs: Any):
        prepared = original_prepare(*call_args, **call_kwargs)
        capture["rows"] = list(prepared[0])
        return prepared

    def capturing_build(model_rows: Sequence[frontier.TripRow]):
        built = original_build(model_rows)
        capture["temporal_edges"] = list(built[0])
        return built

    frontier.prepare_rows = capturing_prepare
    frontier.build_temporal_edges = capturing_build
    try:
        report = frontier.run(args)
    finally:
        frontier.prepare_rows = original_prepare
        frontier.build_temporal_edges = original_build
    if "rows" not in capture or "temporal_edges" not in capture:
        raise frontier.LiveDataError(
            "internal capture failed before boundary-padding construction"
        )
    return report, capture["rows"], capture["temporal_edges"]


def _synthetic_trip(
    index: int,
    role: str,
    released_start: datetime | None,
    released_end: datetime | None,
) -> frontier.TripRow:
    if released_start is None or released_end is None:
        interval_start = None
        interval_end = None
        status = "indeterminate_timestamp"
    else:
        interval_start = released_start - timedelta(
            minutes=frontier.ROUNDING_HALF_MINUTES
        )
        interval_end = released_end + timedelta(
            minutes=frontier.ROUNDING_HALF_MINUTES
        )
        status = "determinate_outer_interval"
    return frontier.TripRow(
        index=index,
        trip_id=f"synthetic-{index}",
        identifier_status="unique_nonnull",
        role=role,
        released_start=released_start,
        released_end=released_end,
        interval_start=interval_start,
        interval_end=interval_end,
        interval_status=status,
        pickup=(41.88, -87.63),
        dropoff=(41.90, -87.65),
        pickup_area="1",
        dropoff_area="2",
        miles=float(index + 1),
        duration_seconds=float(600 + index * 60),
        fare=float(10 + index),
    )


def self_test() -> None:
    frontier.self_test()
    base = datetime(2026, 1, 1, 12, 0)
    rows = [
        _synthetic_trip(0, "core", base, base + timedelta(minutes=30)),
        _synthetic_trip(1, "core", base, base + timedelta(minutes=30)),
        _synthetic_trip(
            2,
            "buffer",
            base + timedelta(minutes=45),
            base + timedelta(minutes=60),
        ),
        _synthetic_trip(
            3,
            "buffer",
            base - timedelta(minutes=30),
            base - timedelta(minutes=15),
        ),
        _synthetic_trip(4, "buffer", None, None),
    ]
    zero_rows, _ = rows_for_boundary_padding(rows, padding_minutes=0)
    full_rows, _ = rows_for_boundary_padding(
        rows, padding_minutes=FULL_BOUNDARY_PADDING_MINUTES
    )
    wide_rows, _ = rows_for_boundary_padding(rows, padding_minutes=30)
    assert {row.index for row in zero_rows} == {0, 1, 4}
    assert {row.index for row in full_rows} == {0, 1, 2, 3, 4}
    assert {row.index for row in wide_rows} == {0, 1, 2, 3, 4}
    zero_edges, _ = frontier.build_temporal_edges(zero_rows)
    full_edges, _ = frontier.build_temporal_edges(full_rows)
    assert set(zero_edges) <= set(full_edges)
    assert parse_padding_grid("0,5,10,15,30") == [0.0, 5.0, 10.0, 15.0, 30.0]
    print("boundary-padding self-test: PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = partitioned.build_parser()
    parser.description = __doc__
    parser.set_defaults(output_dir=Path("tmp/chicago-k2-frontier-boundary"))
    parser.add_argument(
        "--boundary-padding-minutes",
        default=",".join(f"{value:g}" for value in DEFAULT_BOUNDARY_PADDING_MINUTES),
        help=(
            "comma-separated nonnegative minutes; must include 15=2*delta "
            "(default: 0,5,10,15,30)"
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    partitioned._validate_args(args)
    padding_values = parse_padding_grid(args.boundary_padding_minutes)
    partitioned._configure_request_budget(
        args.request_timeout, args.request_attempts
    )
    frontier.fetch_closed_candidate_universe = (
        partitioned.partitioned_fetch_closed_candidate_universe
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report, rows, temporal_edges = _run_with_capture(args)
        report["extraction"]["transport"] = {
            "strategy": "narrow index plus exact released-start partitions",
            "request_timeout_seconds": args.request_timeout,
            "request_attempts": args.request_attempts,
            "partition_page_size": args.page_size,
        }
        report = add_boundary_padding_curve(
            report,
            rows=rows,
            temporal_edges=temporal_edges,
            padding_values=padding_values,
            time_limit_seconds=args.solver_time_limit,
        )
        report.pop("report_sha256", None)
        report["report_sha256"] = frontier.sha256_json(report)
        write_outputs(report, args.output_dir)
    except Exception as exc:
        partitioned._write_failure(args.output_dir, exc)
        raise
    print(render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
