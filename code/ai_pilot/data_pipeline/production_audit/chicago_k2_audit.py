#!/usr/bin/env python3
"""Audit a Chicago matched-K=2 extraction without inventing partner truth.

This module has two deliberately separate graph layers:

* ``logical_necessary`` retains every row pair that is not ruled out by the
  literal K=2/match fields, core/buffer roles, and possible temporal overlap
  after expanding the released 15-minute timestamps to outer intervals.
* ``heuristic_sensitivity`` may apply spatial radii, route direction, or a
  degree cap.  Those screens are never described as necessary conditions.

The public table omits Shared Trip ID.  Exact-cover feasibility is therefore a
property of the declared graph, not evidence that the true partner is present.
Every serialized result is aggregate and contains no trip identifiers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # Production feasibility audit; exact fallback is used for small fixtures.
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    SCIPY_MILP_AVAILABLE = True
except (ImportError, AttributeError):  # pragma: no cover - lean environments
    SCIPY_MILP_AVAILABLE = False


CONTRACT_VERSION = "chicago-k2-production-audit/v1"
REPORT_VERSION = "chicago-k2-production-audit-report/v1"
DATASET_ID = "6dvr-xwnh"
LOGICAL_RULES = (
    "both_endpoints_have_literal_match_true_and_integer_trips_pooled_2",
    "at_least_one_endpoint_has_core_role",
    "possible_closed_interval_overlap_after_timestamp_rounding",
)
HEURISTIC_RULES = (
    "pickup_centroid_radius",
    "dropoff_centroid_radius",
    "route_direction_cosine",
    "greedy_per_node_degree_cap",
)
DURATION_EVIDENCE_PROFILES = {
    "none": ("none", "none"),
    "operator_verified": (
        "city_of_chicago_or_dataset_operator",
        "all_transactions_in_dataset_revision",
    ),
    "externally_validated": (
        "independent_external_authority",
        "declared_external_target_population",
    ),
    "analyst_assumption": ("analyst", "sensitivity_only"),
}
RELEASED_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?$"
)


class ContractError(ValueError):
    """The audit contract is missing or internally inconsistent."""


class EdgeMaterializationLimit(RuntimeError):
    """The logical graph exceeded an operational limit; no trimmed graph exists."""


@dataclass(frozen=True)
class ParsedRow:
    index: int
    trip_id: str | None
    identifier_status: str
    authorized: bool | None
    authorized_status: str
    matched: bool | None
    matched_status: str
    trips_pooled: int | None
    trips_pooled_status: str
    released_start: datetime | None
    released_start_status: str
    released_end: datetime | None
    released_end_status: str
    interval_start: datetime | None
    interval_end: datetime | None
    interval_status: str
    role: str
    pickup: tuple[float, float] | None
    dropoff: tuple[float, float] | None


@dataclass(frozen=True)
class AuditArtifacts:
    """Aggregate report plus non-serialized row-index graph artifacts.

    ``logical_edges`` and ``heuristic_edges`` contain zero-based input row
    positions, never public identifiers.  Callers must not treat either edge
    set as observed partner truth.
    """

    report: dict[str, Any]
    logical_edges: tuple[tuple[int, int], ...]
    heuristic_edges: tuple[tuple[int, int], ...]
    roles: tuple[str, ...]


def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ContractError(f"missing {where}.{key}")
    return mapping[key]


def _parse_contract_datetime(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ContractError(f"{name} must be an ISO local timestamp string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{name} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is not None:
        raise ContractError(f"{name} must be timezone-naive Chicago local time")
    return parsed


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def validate_contract(contract: Mapping[str, Any]) -> None:
    """Validate the locked distinction between logic and heuristic screens."""

    if not isinstance(contract, Mapping):
        raise ContractError("contract must be a JSON object")
    if contract.get("contract_version") != CONTRACT_VERSION:
        raise ContractError(f"contract_version must be {CONTRACT_VERSION!r}")
    if not isinstance(contract.get("audit_name"), str) or not contract["audit_name"].strip():
        raise ContractError("audit_name must be a nonempty string")

    input_spec = _require(contract, "input", "contract")
    window = _require(contract, "window", "contract")
    release = _require(contract, "timestamp_release", "contract")
    closure = _require(contract, "run_closure", "contract")
    graph = _require(contract, "candidate_graph", "contract")
    columns = _require(contract, "columns", "contract")
    for name, value in (
        ("input", input_spec),
        ("window", window),
        ("timestamp_release", release),
        ("run_closure", closure),
        ("candidate_graph", graph),
        ("columns", columns),
    ):
        if not isinstance(value, Mapping):
            raise ContractError(f"contract.{name} must be an object")

    required_input_keys = {
        "dataset_id",
        "snapshot_revision_fingerprint_sha256",
        "expected_row_count",
        "expected_input_sha256",
        "input_hash_basis",
        "null_start_scope",
        "server_target_like_null_start_row_count",
        "null_start_count_evidence_sha256",
        "server_count_verified",
        "snapshot_stable_during_extraction",
        "selection_scope",
        "raw_identifiers_in_report",
    }
    missing_input_keys = required_input_keys - set(input_spec)
    if missing_input_keys:
        raise ContractError(
            "input is missing keys: " + ", ".join(sorted(missing_input_keys))
        )

    if input_spec.get("dataset_id") != DATASET_ID:
        raise ContractError(f"input.dataset_id must be {DATASET_ID!r}")
    fingerprint = input_spec.get("snapshot_revision_fingerprint_sha256")
    if not _is_sha256(fingerprint):
        raise ContractError(
            "input.snapshot_revision_fingerprint_sha256 must be 64 hex characters"
        )
    expected_rows = input_spec.get("expected_row_count")
    if expected_rows is not None and (
        isinstance(expected_rows, bool)
        or not isinstance(expected_rows, int)
        or expected_rows < 0
    ):
        raise ContractError("input.expected_row_count must be null or nonnegative int")
    expected_hash = input_spec.get("expected_input_sha256")
    if not _is_sha256(expected_hash):
        raise ContractError("input.expected_input_sha256 must be pinned SHA-256 hex")
    if input_spec.get("input_hash_basis") != "canonical_json_rows_v1":
        raise ContractError("input.input_hash_basis must be canonical_json_rows_v1")
    null_start_scope = input_spec.get("null_start_scope")
    allowed_null_start_scopes = {
        "not_verified",
        "server_verified_zero_literal_match_true_k2_null_start_rows",
        "all_literal_match_true_k2_null_start_rows_included",
    }
    if null_start_scope not in allowed_null_start_scopes:
        raise ContractError("input.null_start_scope has an unknown value")
    null_start_count = input_spec.get("server_target_like_null_start_row_count")
    null_start_evidence = input_spec.get("null_start_count_evidence_sha256")
    if null_start_scope == "not_verified":
        if null_start_count is not None or null_start_evidence is not None:
            raise ContractError(
                "not_verified null-start scope requires null count and evidence"
            )
    else:
        if (
            isinstance(null_start_count, bool)
            or not isinstance(null_start_count, int)
            or null_start_count < 0
        ):
            raise ContractError("verified null-start scope requires a nonnegative count")
        if not _is_sha256(null_start_evidence):
            raise ContractError("verified null-start scope requires an evidence SHA-256")
        if (
            null_start_scope
            == "server_verified_zero_literal_match_true_k2_null_start_rows"
            and null_start_count != 0
        ):
            raise ContractError("server-verified-zero null-start count must equal zero")
        if (
            null_start_scope
            == "all_literal_match_true_k2_null_start_rows_included"
            and null_start_count < 1
        ):
            raise ContractError("all-included null-start scope requires a positive count")
    if input_spec.get("selection_scope") not in {
        "all_public_rows_in_released_start_window_plus_null_start_evidence",
        "all_public_rows_in_extraction_window",
        "authorized_only",
        "custom",
    }:
        raise ContractError("input.selection_scope has an unknown value")
    if input_spec.get("raw_identifiers_in_report") is not False:
        raise ContractError("input.raw_identifiers_in_report must be false")
    for key in ("server_count_verified", "snapshot_stable_during_extraction"):
        if not isinstance(input_spec.get(key), bool):
            raise ContractError(f"input.{key} must be boolean")

    core_start = _parse_contract_datetime(
        _require(window, "core_start_local", "window"), "window.core_start_local"
    )
    core_end = _parse_contract_datetime(
        _require(window, "core_end_local", "window"), "window.core_end_local"
    )
    extraction_start = _parse_contract_datetime(
        _require(window, "extraction_start_local", "window"),
        "window.extraction_start_local",
    )
    extraction_end = _parse_contract_datetime(
        _require(window, "extraction_end_local", "window"),
        "window.extraction_end_local",
    )
    if not extraction_start <= core_start < core_end <= extraction_end:
        raise ContractError(
            "window must satisfy extraction_start <= core_start < core_end <= "
            "extraction_end"
        )
    if window.get("core_anchor") != "released_trip_start_timestamp":
        raise ContractError("window.core_anchor must be released_trip_start_timestamp")

    rounding = release.get("rounding_minutes")
    if isinstance(rounding, bool) or not isinstance(rounding, (int, float)):
        raise ContractError("timestamp_release.rounding_minutes must be positive")
    if not math.isfinite(float(rounding)) or float(rounding) <= 0:
        raise ContractError("timestamp_release.rounding_minutes must be positive")
    if float(rounding) != 15.0:
        raise ContractError("timestamp_release.rounding_minutes is locked to 15")
    if release.get("interpretation") != "nearest_with_closed_outer_interval":
        raise ContractError(
            "timestamp_release.interpretation must be "
            "nearest_with_closed_outer_interval"
        )

    duration = closure.get("maximum_transaction_duration_minutes")
    basis = closure.get("duration_bound_basis")
    required_closure_keys = {
        "maximum_transaction_duration_minutes",
        "duration_bound_basis",
        "duration_bound_evidence",
        "public_shared_trip_id_available",
    }
    missing_closure_keys = required_closure_keys - set(closure)
    if missing_closure_keys:
        raise ContractError(
            "run_closure is missing keys: "
            + ", ".join(sorted(missing_closure_keys))
        )
    allowed_bases = set(DURATION_EVIDENCE_PROFILES)
    if basis not in allowed_bases:
        raise ContractError("run_closure.duration_bound_basis has an unknown value")
    if duration is None:
        if basis != "none":
            raise ContractError("a null duration bound requires basis=none")
    elif (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(float(duration))
        or float(duration) <= 0
        or basis == "none"
    ):
        raise ContractError("duration bound must be positive and have a stated basis")
    evidence = closure.get("duration_bound_evidence")
    if not isinstance(evidence, Mapping):
        raise ContractError("run_closure.duration_bound_evidence must be an object")
    if set(evidence) != {"authority", "effective_scope", "artifact_sha256"}:
        raise ContractError(
            "duration_bound_evidence requires authority, effective_scope, and artifact_sha256"
        )
    expected_authority, expected_scope = DURATION_EVIDENCE_PROFILES[basis]
    if evidence.get("authority") != expected_authority:
        raise ContractError(
            f"duration evidence authority must be {expected_authority!r} for basis {basis!r}"
        )
    if evidence.get("effective_scope") != expected_scope:
        raise ContractError(
            f"duration evidence scope must be {expected_scope!r} for basis {basis!r}"
        )
    evidence_hash = evidence.get("artifact_sha256")
    if basis == "none":
        if evidence_hash is not None:
            raise ContractError("duration evidence artifact must be null when basis=none")
    elif not _is_sha256(evidence_hash):
        raise ContractError("every non-null duration bound requires a pinned artifact SHA-256")
    if closure.get("public_shared_trip_id_available") is not False:
        raise ContractError("public_shared_trip_id_available must be false for this table")

    if graph.get("logical_rules") != list(LOGICAL_RULES):
        raise ContractError(
            "candidate_graph.logical_rules must equal the locked necessary-rule list"
        )
    if graph.get("missing_timestamp_policy") != "retain_indeterminate":
        raise ContractError(
            "logical graph requires missing_timestamp_policy=retain_indeterminate"
        )
    max_edges = graph.get("max_materialized_logical_edges")
    if isinstance(max_edges, bool) or not isinstance(max_edges, int) or max_edges < 1:
        raise ContractError("max_materialized_logical_edges must be a positive integer")
    fallback_limit = graph.get("exact_fallback_max_core_nodes", 28)
    if (
        isinstance(fallback_limit, bool)
        or not isinstance(fallback_limit, int)
        or fallback_limit < 0
    ):
        raise ContractError("exact_fallback_max_core_nodes must be nonnegative")
    fallback_edge_limit = graph.get("exact_fallback_max_edges", 10_000)
    if (
        isinstance(fallback_edge_limit, bool)
        or not isinstance(fallback_edge_limit, int)
        or fallback_edge_limit < 0
    ):
        raise ContractError("exact_fallback_max_edges must be nonnegative")
    time_limit = graph.get("feasibility_time_limit_seconds", 60)
    if (
        isinstance(time_limit, bool)
        or not isinstance(time_limit, (int, float))
        or float(time_limit) <= 0
    ):
        raise ContractError("feasibility_time_limit_seconds must be positive")

    heuristics = graph.get("heuristics")
    if not isinstance(heuristics, Mapping):
        raise ContractError("candidate_graph.heuristics must be an object")
    required_heuristic_keys = {
        "pickup_radius_km",
        "dropoff_radius_km",
        "direction_cosine_min",
        "per_node_degree_cap",
        "missing_spatial_policy",
    }
    missing_heuristic_keys = required_heuristic_keys - set(heuristics)
    if missing_heuristic_keys:
        raise ContractError(
            "candidate_graph.heuristics is missing keys: "
            + ", ".join(sorted(missing_heuristic_keys))
        )
    for key in ("pickup_radius_km", "dropoff_radius_km"):
        value = heuristics.get(key)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ContractError(f"heuristics.{key} must be null or nonnegative")
    direction = heuristics.get("direction_cosine_min")
    if direction is not None and (
        isinstance(direction, bool)
        or not isinstance(direction, (int, float))
        or not math.isfinite(float(direction))
        or not -1 <= float(direction) <= 1
    ):
        raise ContractError("heuristics.direction_cosine_min must lie in [-1,1]")
    degree_cap = heuristics.get("per_node_degree_cap")
    if degree_cap is not None and (
        isinstance(degree_cap, bool) or not isinstance(degree_cap, int) or degree_cap < 1
    ):
        raise ContractError("heuristics.per_node_degree_cap must be null or positive int")
    if heuristics.get("missing_spatial_policy") not in {"retain", "drop"}:
        raise ContractError("heuristics.missing_spatial_policy must be retain or drop")

    required_columns = {
        "trip_id",
        "trip_start_timestamp",
        "trip_end_timestamp",
        "shared_trip_authorized",
        "shared_trip_match",
        "trips_pooled",
        "pickup_latitude",
        "pickup_longitude",
        "dropoff_latitude",
        "dropoff_longitude",
    }
    if set(columns) != required_columns:
        missing = sorted(required_columns - set(columns))
        extra = sorted(set(columns) - required_columns)
        raise ContractError(f"columns keys mismatch; missing={missing}, extra={extra}")
    if any(not isinstance(value, str) or not value for value in columns.values()):
        raise ContractError("all column mappings must be nonempty strings")
    if len(set(columns.values())) != len(columns):
        raise ContractError("column mappings must be pairwise distinct")


def load_contract(path: Path | str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        contract = json.load(handle)
    validate_contract(contract)
    return contract


def validate_report(report: Mapping[str, Any]) -> None:
    """Lightweight runtime parity check for the aggregate report schema."""

    required = {
        "report_version",
        "generated_at_utc",
        "audit_contract_sha256",
        "dataset",
        "input_checks",
        "row_roles",
        "identifier_audit",
        "literal_field_audit",
        "operator_consistency_audit",
        "candidate_graphs",
        "run_closure_audit",
        "redaction",
    }
    missing = required - set(report)
    if missing:
        raise ValueError("report is missing keys: " + ", ".join(sorted(missing)))
    if report.get("report_version") != REPORT_VERSION:
        raise ValueError("report_version mismatch")
    if not _is_sha256(report.get("audit_contract_sha256")):
        raise ValueError("report contract digest is not SHA-256")
    generated = report.get("generated_at_utc")
    if not isinstance(generated, str):
        raise ValueError("generated_at_utc must be a UTC timestamp")
    try:
        generated_dt = datetime.fromisoformat(generated)
    except ValueError as exc:
        raise ValueError("generated_at_utc must be a UTC timestamp") from exc
    if generated_dt.tzinfo is None or generated_dt.utcoffset() != timedelta(0):
        raise ValueError("generated_at_utc must include a zero UTC offset")

    dataset = report.get("dataset")
    if not isinstance(dataset, Mapping) or dataset.get("dataset_id") != DATASET_ID:
        raise ValueError("report dataset identity mismatch")
    if not _is_sha256(dataset.get("snapshot_revision_fingerprint_sha256")):
        raise ValueError("report snapshot digest is not SHA-256")
    input_checks = report.get("input_checks")
    if not isinstance(input_checks, Mapping):
        raise ValueError("input_checks must be an object")
    if input_checks.get("input_hash_basis") != "canonical_json_rows_v1":
        raise ValueError("report input hash basis mismatch")
    if not _is_sha256(input_checks.get("actual_input_sha256")) or not _is_sha256(
        input_checks.get("expected_input_sha256")
    ):
        raise ValueError("report input hashes must be pinned SHA-256 values")
    null_start_scope = input_checks.get("null_start_scope")
    if null_start_scope not in {
        "not_verified",
        "server_verified_zero_literal_match_true_k2_null_start_rows",
        "all_literal_match_true_k2_null_start_rows_included",
    }:
        raise ValueError("report null-start scope mismatch")
    null_start_evidence = input_checks.get("null_start_count_evidence_sha256")
    if null_start_evidence is not None and not _is_sha256(null_start_evidence):
        raise ValueError("report null-start evidence must be null or SHA-256")
    graphs = report.get("candidate_graphs")
    if not isinstance(graphs, Mapping):
        raise ValueError("candidate_graphs must be an object")
    logical = graphs.get("logical_necessary")
    heuristic = graphs.get("heuristic_sensitivity")
    if not isinstance(logical, Mapping) or not isinstance(heuristic, Mapping):
        raise ValueError("both candidate graph layers are required")
    if logical.get("partner_coverage_claim") != "NOT_ESTIMATED_FROM_PUBLIC_ROWS":
        raise ValueError("logical graph cannot claim public-row partner coverage")
    if heuristic.get("partner_coverage_claim") != "NONE":
        raise ValueError("heuristic graph cannot claim partner coverage")
    if (
        heuristic.get("classification")
        != "ANALYST_HEURISTIC_NOT_A_NECESSARY_SUPERGRAPH"
    ):
        raise ValueError("heuristic graph classification mismatch")
    closure = report.get("run_closure_audit")
    if not isinstance(closure, Mapping):
        raise ValueError("run_closure_audit must be an object")
    hidden = closure.get("public_hidden_run_closure")
    if not isinstance(hidden, Mapping) or hidden.get("status") != (
        "NOT_IDENTIFIED_FROM_PUBLIC_ROWS"
    ):
        raise ValueError("public hidden-run closure status is not locked")
    boundary = closure.get("boundary_extraction_support")
    if not isinstance(boundary, Mapping):
        raise ValueError("boundary_extraction_support must be an object")
    duration_evidence = boundary.get("duration_bound_evidence")
    if not isinstance(duration_evidence, Mapping) or set(duration_evidence) != {
        "authority",
        "effective_scope",
        "artifact_sha256",
    }:
        raise ValueError("report duration evidence must have the locked aggregate shape")
    if duration_evidence.get("authority") not in {
        profile[0] for profile in DURATION_EVIDENCE_PROFILES.values()
    }:
        raise ValueError("report duration evidence authority is invalid")
    if duration_evidence.get("effective_scope") not in {
        profile[1] for profile in DURATION_EVIDENCE_PROFILES.values()
    }:
        raise ValueError("report duration evidence scope is invalid")
    artifact_hash = duration_evidence.get("artifact_sha256")
    if artifact_hash is not None and not _is_sha256(artifact_hash):
        raise ValueError("report duration evidence artifact is not SHA-256")
    redaction = report.get("redaction")
    if redaction != {
        "raw_trip_identifiers_emitted": False,
        "edge_endpoint_identifiers_emitted": False,
        "row_level_data_emitted": False,
        "report_contains_aggregate_counts_and_hashes_only": True,
    }:
        raise ValueError("report redaction contract mismatch")


def read_csv_rows(path: Path | str) -> list[dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("input CSV has no header")
        header_counts = Counter(reader.fieldnames)
        if any(count > 1 for count in header_counts.values()):
            raise ValueError(
                "input CSV has duplicate header names; DictReader overwrite is rejected"
            )
        return list(reader)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_rows_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    """Hash normalized row content, including all columns, in input order."""

    return _canonical_sha256(list(rows))


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _parse_bool(value: Any) -> tuple[bool | None, str]:
    if _blank(value):
        return None, "null"
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True, "true"
    if normalized == "false":
        return False, "false"
    return None, "invalid_literal"


def _parse_k(value: Any) -> tuple[int | None, str]:
    if _blank(value):
        return None, "null"
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation:
        return None, "invalid_literal"
    if not parsed.is_finite():
        return None, "invalid_literal"
    integral = parsed.to_integral_value()
    if parsed != integral:
        return None, "noninteger"
    integer = int(integral)
    if integer < 1:
        return integer, "nonpositive_integer"
    return integer, "positive_integer"


def _parse_timestamp(value: Any) -> tuple[datetime | None, str]:
    if _blank(value):
        return None, "null"
    text = str(value).strip()
    if RELEASED_TIMESTAMP_PATTERN.fullmatch(text) is None:
        return None, "invalid_datetime_lexical_shape"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, "invalid_literal"
    if parsed.tzinfo is not None:
        return None, "timezone_aware_rejected"
    if parsed.minute % 15 != 0 or parsed.second != 0 or parsed.microsecond != 0:
        return None, "off_15_minute_release_grid"
    return parsed, "valid_local"


def _parse_coordinate_pair(
    latitude: Any, longitude: Any
) -> tuple[float, float] | None:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def _prepare_rows(
    raw_rows: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> tuple[list[ParsedRow], dict[str, Any]]:
    columns = contract["columns"]
    window = contract["window"]
    release = contract["timestamp_release"]
    core_start = _parse_contract_datetime(window["core_start_local"], "core_start")
    core_end = _parse_contract_datetime(window["core_end_local"], "core_end")
    extraction_start = _parse_contract_datetime(
        window["extraction_start_local"], "extraction_start"
    )
    extraction_end = _parse_contract_datetime(
        window["extraction_end_local"], "extraction_end"
    )
    half_rounding = timedelta(minutes=float(release["rounding_minutes"]) / 2.0)

    required_input_names = set(columns.values())
    for row in raw_rows:
        missing_columns = required_input_names - set(row)
        if missing_columns:
            raise ValueError(
                "input rows omit required mapped columns: "
                + ", ".join(sorted(missing_columns))
            )

    normalized_ids: list[str | None] = []
    for row in raw_rows:
        value = row[columns["trip_id"]]
        normalized_ids.append(None if _blank(value) else str(value).strip())
    id_counts = Counter(value for value in normalized_ids if value is not None)

    parsed_rows: list[ParsedRow] = []
    literal_counts: dict[str, Counter[str]] = {
        "authorized": Counter(),
        "match": Counter(),
        "trips_pooled": Counter(),
        "start_timestamp": Counter(),
        "end_timestamp": Counter(),
        "interval": Counter(),
    }
    issue_counts: Counter[str] = Counter()

    for index, (row, trip_id) in enumerate(zip(raw_rows, normalized_ids)):
        if trip_id is None:
            identifier_status = "null_or_blank"
        elif id_counts[trip_id] > 1:
            identifier_status = "duplicate"
        else:
            identifier_status = "unique_nonnull"

        authorized, authorized_status = _parse_bool(
            row[columns["shared_trip_authorized"]]
        )
        matched, matched_status = _parse_bool(row[columns["shared_trip_match"]])
        pooled, pooled_status = _parse_k(row[columns["trips_pooled"]])
        start, start_status = _parse_timestamp(row[columns["trip_start_timestamp"]])
        end, end_status = _parse_timestamp(row[columns["trip_end_timestamp"]])

        if start is not None and end is not None:
            interval_start = start - half_rounding
            interval_end = end + half_rounding
            if interval_start <= interval_end:
                interval_status = "determinate_outer_interval"
            else:
                interval_start = None
                interval_end = None
                interval_status = "released_chronology_impossible"
        else:
            interval_start = None
            interval_end = None
            interval_status = "indeterminate_timestamp"

        target_literal = matched is True and pooled == 2 and pooled_status == "positive_integer"
        identifier_usable = identifier_status == "unique_nonnull"
        if target_literal and identifier_usable:
            if start is not None and core_start <= start < core_end:
                role = "core"
            else:
                role = "buffer"
        else:
            role = "context"

        if start is not None and not extraction_start <= start < extraction_end:
            issue_counts["released_start_outside_declared_extraction"] += 1
        if target_literal and start is None:
            issue_counts["target_literal_without_usable_core_anchor"] += 1
        if target_literal and start_status == "null":
            issue_counts["target_literal_null_start"] += 1
        if target_literal and (
            start_status not in {"valid_local", "null"}
            or end_status != "valid_local"
            or interval_status == "released_chronology_impossible"
        ):
            issue_counts["target_literal_invalid_or_offgrid_timestamp"] += 1
        if target_literal and not identifier_usable:
            issue_counts["target_literal_excluded_for_identifier_failure"] += 1
        if matched is True and authorized is False:
            issue_counts["match_true_authorized_false"] += 1
        if matched is True and authorized_status in {"null", "invalid_literal"}:
            issue_counts["match_true_authorized_unknown"] += 1
        if matched is True and (
            pooled_status != "positive_integer" or pooled is None or pooled < 2
        ):
            issue_counts["match_true_k_lt_2_or_unusable"] += 1
        if authorized is False and pooled is not None and pooled >= 2:
            issue_counts["k_ge_2_authorized_false"] += 1
        if matched is False and pooled == 2:
            issue_counts["match_false_k_2_not_a_logical_contradiction"] += 1
        if matched_status in {"null", "invalid_literal"}:
            issue_counts["match_unknown"] += 1
        if pooled_status != "positive_integer":
            issue_counts["k_null_invalid_noninteger_or_nonpositive"] += 1
        if interval_status == "released_chronology_impossible":
            issue_counts["released_chronology_impossible"] += 1

        literal_counts["authorized"][authorized_status] += 1
        literal_counts["match"][matched_status] += 1
        literal_counts["trips_pooled"][pooled_status] += 1
        literal_counts["start_timestamp"][start_status] += 1
        literal_counts["end_timestamp"][end_status] += 1
        literal_counts["interval"][interval_status] += 1

        parsed_rows.append(
            ParsedRow(
                index=index,
                trip_id=trip_id,
                identifier_status=identifier_status,
                authorized=authorized,
                authorized_status=authorized_status,
                matched=matched,
                matched_status=matched_status,
                trips_pooled=pooled,
                trips_pooled_status=pooled_status,
                released_start=start,
                released_start_status=start_status,
                released_end=end,
                released_end_status=end_status,
                interval_start=interval_start,
                interval_end=interval_end,
                interval_status=interval_status,
                role=role,
                pickup=_parse_coordinate_pair(
                    row[columns["pickup_latitude"]],
                    row[columns["pickup_longitude"]],
                ),
                dropoff=_parse_coordinate_pair(
                    row[columns["dropoff_latitude"]],
                    row[columns["dropoff_longitude"]],
                ),
            )
        )

    identifier_counts = Counter(row.identifier_status for row in parsed_rows)
    role_counts = Counter(row.role for row in parsed_rows)
    duplicate_values = sum(1 for count in id_counts.values() if count > 1)
    duplicate_rows = sum(count for count in id_counts.values() if count > 1)
    preparation = {
        "roles": {
            "core_rows": role_counts["core"],
            "buffer_rows": role_counts["buffer"],
            "context_rows": role_counts["context"],
            "definitions": {
                "core": (
                    "unique nonnull ID, literal Match=true, integer K=2, and "
                    "released start in the half-open core window"
                ),
                "buffer": (
                    "unique nonnull ID and literal Match=true, integer K=2, but "
                    "released start outside the core window or unusable as an anchor"
                ),
                "context": (
                    "all other rows; retained in the audit population and available "
                    "to downstream release-count factors, but not paired here"
                ),
            },
        },
        "identifiers": {
            "unique_nonnull_rows": identifier_counts["unique_nonnull"],
            "null_or_blank_rows": identifier_counts["null_or_blank"],
            "duplicate_rows": duplicate_rows,
            "duplicate_distinct_values": duplicate_values,
            "policy": (
                "null/blank and every occurrence of a duplicate ID remain context; "
                "they are never silently deduplicated or emitted"
            ),
        },
        "literal_fields": {
            key: dict(sorted(counter.items())) for key, counter in literal_counts.items()
        },
        "operator_consistency_counts": dict(sorted(issue_counts.items())),
    }
    return parsed_rows, preparation


def _allowed_role_pair(left: ParsedRow, right: ParsedRow) -> bool:
    return (
        left.role in {"core", "buffer"}
        and right.role in {"core", "buffer"}
        and (left.role == "core" or right.role == "core")
    )


def _build_logical_edges(
    rows: Sequence[ParsedRow], max_edges: int
) -> tuple[list[tuple[int, int]], dict[str, int]]:
    eligible = [row for row in rows if row.role in {"core", "buffer"}]
    determinate = [
        row
        for row in eligible
        if row.interval_start is not None and row.interval_end is not None
    ]
    indeterminate = [
        row
        for row in eligible
        if row.interval_start is None or row.interval_end is None
    ]
    edges: list[tuple[int, int]] = []
    counts: Counter[str] = Counter()

    def append(left: ParsedRow, right: ParsedRow, provenance: str) -> None:
        if not _allowed_role_pair(left, right):
            return
        if len(edges) >= max_edges:
            raise EdgeMaterializationLimit(
                f"logical edge count reached operational limit {max_edges}"
            )
        edge = (min(left.index, right.index), max(left.index, right.index))
        edges.append(edge)
        counts[provenance] += 1
        if left.role != right.role:
            counts["core_buffer_edges"] += 1
        else:
            counts["core_core_edges"] += 1
        if (
            left.released_start is not None
            and right.released_start is not None
            and left.released_start.date() != right.released_start.date()
        ):
            counts["cross_midnight_edges"] += 1

    # Interval sweep: equality is retained because outer intervals are closed.
    determinate.sort(key=lambda row: (row.interval_start, row.index))
    active: list[ParsedRow] = []
    for current in determinate:
        active = [
            prior for prior in active if prior.interval_end >= current.interval_start
        ]
        for prior in active:
            append(prior, current, "determinate_possible_overlap_edges")
        active.append(current)

    # A missing/malformed endpoint cannot logically rule out overlap.  Retaining
    # all permitted pairs may be expensive; hitting max_edges aborts the audit
    # instead of turning the operational limit into a hidden degree cap.
    indeterminate_indices = {row.index for row in indeterminate}
    for position, left in enumerate(eligible):
        for right in eligible[position + 1 :]:
            if (
                left.index not in indeterminate_indices
                and right.index not in indeterminate_indices
            ):
                continue
            append(left, right, "indeterminate_timestamp_edges")

    edges.sort()
    core_count = sum(row.role == "core" for row in eligible)
    buffer_count = sum(row.role == "buffer" for row in eligible)
    possible_role_pairs = core_count * (core_count - 1) // 2 + core_count * buffer_count
    counts["possible_role_pairs_before_temporal_rule"] = possible_role_pairs
    counts["temporally_ruled_out_pairs"] = possible_role_pairs - len(edges)
    return edges, dict(counts)


def _graph_statistics(
    rows: Sequence[ParsedRow], edges: Sequence[tuple[int, int]]
) -> dict[str, Any]:
    eligible_indices = [row.index for row in rows if row.role in {"core", "buffer"}]
    core_indices = [row.index for row in rows if row.role == "core"]
    buffer_indices = [row.index for row in rows if row.role == "buffer"]
    degree = Counter({index: 0 for index in eligible_indices})
    parent = {index: index for index in eligible_indices}

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right in edges:
        degree[left] += 1
        degree[right] += 1
        union(left, right)

    component_sizes = Counter(find(index) for index in eligible_indices)
    core_degrees = [degree[index] for index in core_indices]
    buffer_degrees = [degree[index] for index in buffer_indices]
    return {
        "node_count": len(eligible_indices),
        "core_node_count": len(core_indices),
        "buffer_node_count": len(buffer_indices),
        "edge_count": len(edges),
        "core_zero_degree_count": sum(value == 0 for value in core_degrees),
        "core_min_degree": min(core_degrees) if core_degrees else None,
        "core_max_degree": max(core_degrees) if core_degrees else None,
        "buffer_zero_degree_count": sum(value == 0 for value in buffer_degrees),
        "buffer_max_degree": max(buffer_degrees) if buffer_degrees else None,
        "connected_component_count_including_isolates": len(component_sizes),
        "largest_component_nodes": max(component_sizes.values(), default=0),
    }


def _exact_cover_fallback(
    rows: Sequence[ParsedRow], edges: Sequence[tuple[int, int]]
) -> bool:
    core = frozenset(row.index for row in rows if row.role == "core")
    incident: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for edge in edges:
        incident[edge[0]].append(edge)
        incident[edge[1]].append(edge)
    memo: dict[frozenset[int], bool] = {}

    def recurse(used: frozenset[int]) -> bool:
        uncovered = core - used
        if not uncovered:
            return True
        if used in memo:
            return memo[used]
        choices: list[tuple[int, list[tuple[int, int]]]] = []
        for node in uncovered:
            available = [
                edge
                for edge in incident[node]
                if edge[0] not in used and edge[1] not in used
            ]
            if not available:
                memo[used] = False
                return False
            choices.append((node, available))
        _, available = min(choices, key=lambda item: (len(item[1]), item[0]))
        for left, right in available:
            if recurse(used | {left, right}):
                memo[used] = True
                return True
        memo[used] = False
        return False

    return recurse(frozenset())


def _cover_feasibility(
    rows: Sequence[ParsedRow],
    edges: Sequence[tuple[int, int]],
    *,
    exact_fallback_max_core_nodes: int,
    exact_fallback_max_edges: int,
    time_limit_seconds: float,
) -> dict[str, Any]:
    core = [row.index for row in rows if row.role == "core"]
    buffers = [row.index for row in rows if row.role == "buffer"]
    stats = _graph_statistics(rows, edges)
    if not core:
        return {
            "status": "VACUOUS_NO_CORE_ROWS",
            "certified_for_declared_graph": True,
            "backend": "structural",
            "message": "There are no core nodes to cover.",
        }
    if stats["core_zero_degree_count"]:
        return {
            "status": "PROVEN_INFEASIBLE_ISOLATED_CORE",
            "certified_for_declared_graph": True,
            "backend": "structural",
            "message": "At least one core node has no declared candidate edge.",
        }
    if (
        len(core) <= exact_fallback_max_core_nodes
        and len(edges) <= exact_fallback_max_edges
    ):
        feasible = _exact_cover_fallback(rows, edges)
        return {
            "status": "EXACT_FEASIBLE" if feasible else "EXACT_INFEASIBLE",
            "certified_for_declared_graph": True,
            "backend": "deterministic_backtracking",
            "message": (
                "A core-degree-1, buffer-degree-at-most-1 cover exists in the "
                "declared graph."
                if feasible
                else "No such cover exists in the declared graph."
            ),
        }
    if not SCIPY_MILP_AVAILABLE:
        return {
            "status": "UNRESOLVED_NO_PRODUCTION_SOLVER",
            "certified_for_declared_graph": False,
            "backend": "none",
            "message": "SciPy MILP is unavailable and the exact fallback limit was exceeded.",
        }

    constrained = core + buffers
    row_position = {node: position for position, node in enumerate(constrained)}
    matrix = lil_matrix((len(constrained), len(edges)), dtype=float)
    for column, (left, right) in enumerate(edges):
        matrix[row_position[left], column] = 1.0
        matrix[row_position[right], column] = 1.0
    lower = np.asarray([1.0] * len(core) + [0.0] * len(buffers), dtype=float)
    upper = np.ones(len(constrained), dtype=float)
    constraint_matrix = matrix.tocsr()
    try:
        result = milp(
            c=np.zeros(len(edges), dtype=float),
            integrality=np.ones(len(edges), dtype=int),
            bounds=Bounds(np.zeros(len(edges)), np.ones(len(edges))),
            constraints=LinearConstraint(constraint_matrix, lower, upper),
            options={"time_limit": float(time_limit_seconds), "presolve": True},
        )
    except Exception as exc:  # pragma: no cover - solver/environment dependent
        return {
            "status": "UNRESOLVED_SOLVER_ERROR",
            "certified_for_declared_graph": False,
            "backend": "scipy_highs_milp",
            "message": f"Solver error type: {type(exc).__name__}",
        }
    if result.status == 0 and result.x is not None:
        incumbent = np.asarray(result.x, dtype=float)
        if incumbent.shape != (len(edges),) or not np.isfinite(incumbent).all():
            return {
                "status": "UNRESOLVED_INVALID_NUMERICAL_INCUMBENT",
                "certified_for_declared_graph": False,
                "backend": "scipy_highs_milp",
                "message": "HiGHS returned a missing, malformed, or nonfinite incumbent.",
            }
        rounded = np.rint(incumbent)
        integrality_residual = float(np.max(np.abs(incumbent - rounded)))
        bound_residual = float(
            max(
                np.max(np.maximum(-rounded, 0.0)),
                np.max(np.maximum(rounded - 1.0, 0.0)),
            )
        )
        row_sums = np.asarray(constraint_matrix @ rounded).reshape(-1)
        constraint_residual = float(
            max(
                np.max(np.maximum(lower - row_sums, 0.0)),
                np.max(np.maximum(row_sums - upper, 0.0)),
            )
        )
        tolerance = 1e-7
        if max(integrality_residual, bound_residual, constraint_residual) > tolerance:
            return {
                "status": "UNRESOLVED_INVALID_NUMERICAL_INCUMBENT",
                "certified_for_declared_graph": False,
                "backend": "scipy_highs_milp",
                "max_integrality_residual": integrality_residual,
                "max_bound_residual_after_rounding": bound_residual,
                "max_constraint_residual_after_rounding": constraint_residual,
                "validation_tolerance": tolerance,
                "message": "The returned incumbent failed independent rounding replay.",
            }
        return {
            "status": "NUMERICALLY_FEASIBLE_VALIDATED_INCUMBENT",
            "certified_for_declared_graph": False,
            "backend": "scipy_highs_milp",
            "max_integrality_residual": integrality_residual,
            "max_bound_residual_after_rounding": bound_residual,
            "max_constraint_residual_after_rounding": constraint_residual,
            "validation_tolerance": tolerance,
            "message": (
                "A rounded HiGHS incumbent passed independent declared-constraint "
                "replay; this remains a numerical, uncertified feasibility result."
            ),
        }
    if result.status == 2:
        return {
            "status": "NUMERICALLY_INFEASIBLE",
            "certified_for_declared_graph": False,
            "backend": "scipy_highs_milp",
            "message": "HiGHS reported the declared cover constraints infeasible.",
        }
    return {
        "status": "UNRESOLVED_SOLVER_LIMIT",
        "certified_for_declared_graph": False,
        "backend": "scipy_highs_milp",
        "message": "HiGHS did not resolve feasibility within the declared resources.",
    }


def _haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, left)
    lat2, lon2 = map(math.radians, right)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(value)))


def _direction_cosine(left: ParsedRow, right: ParsedRow) -> float | None:
    if (
        left.pickup is None
        or left.dropoff is None
        or right.pickup is None
        or right.dropoff is None
    ):
        return None

    def vector(row: ParsedRow) -> tuple[float, float]:
        mean_lat = math.radians((row.pickup[0] + row.dropoff[0]) / 2)
        return (
            (row.dropoff[1] - row.pickup[1]) * math.cos(mean_lat),
            row.dropoff[0] - row.pickup[0],
        )

    first, second = vector(left), vector(right)
    first_norm = math.hypot(*first)
    second_norm = math.hypot(*second)
    if first_norm == 0 or second_norm == 0:
        return None
    return (first[0] * second[0] + first[1] * second[1]) / (first_norm * second_norm)


def _build_heuristic_edges(
    rows: Sequence[ParsedRow],
    logical_edges: Sequence[tuple[int, int]],
    heuristics: Mapping[str, Any],
) -> tuple[list[tuple[int, int]], dict[str, int], bool]:
    by_index = {row.index: row for row in rows}
    pickup_radius = heuristics.get("pickup_radius_km")
    dropoff_radius = heuristics.get("dropoff_radius_km")
    direction_min = heuristics.get("direction_cosine_min")
    degree_cap = heuristics.get("per_node_degree_cap")
    missing_policy = heuristics["missing_spatial_policy"]
    enabled = any(
        value is not None
        for value in (pickup_radius, dropoff_radius, direction_min, degree_cap)
    )
    retained = list(logical_edges)
    removed: Counter[str] = Counter()

    def spatial_filter(
        edges: Iterable[tuple[int, int]], attribute: str, threshold: float, label: str
    ) -> list[tuple[int, int]]:
        output = []
        for edge in edges:
            left = getattr(by_index[edge[0]], attribute)
            right = getattr(by_index[edge[1]], attribute)
            if left is None or right is None:
                keep = missing_policy == "retain"
            else:
                keep = _haversine_km(left, right) <= threshold
            if keep:
                output.append(edge)
            else:
                removed[label] += 1
        return output

    if pickup_radius is not None:
        retained = spatial_filter(
            retained, "pickup", float(pickup_radius), "pickup_radius"
        )
    if dropoff_radius is not None:
        retained = spatial_filter(
            retained, "dropoff", float(dropoff_radius), "dropoff_radius"
        )
    if direction_min is not None:
        output = []
        for edge in retained:
            cosine = _direction_cosine(by_index[edge[0]], by_index[edge[1]])
            keep = missing_policy == "retain" if cosine is None else cosine >= float(direction_min)
            if keep:
                output.append(edge)
            else:
                removed["direction_cosine"] += 1
        retained = output

    if degree_cap is not None:
        def priority(edge: tuple[int, int]) -> tuple[Any, ...]:
            left, right = by_index[edge[0]], by_index[edge[1]]
            pickup_distance = (
                _haversine_km(left.pickup, right.pickup)
                if left.pickup is not None and right.pickup is not None
                else math.inf
            )
            start_difference = (
                abs((left.released_start - right.released_start).total_seconds())
                if left.released_start is not None and right.released_start is not None
                else math.inf
            )
            return (
                pickup_distance,
                start_difference,
                left.trip_id or "",
                right.trip_id or "",
                edge,
            )

        degrees: Counter[int] = Counter()
        capped: list[tuple[int, int]] = []
        for edge in sorted(retained, key=priority):
            if degrees[edge[0]] >= degree_cap or degrees[edge[1]] >= degree_cap:
                removed["degree_cap"] += 1
                continue
            capped.append(edge)
            degrees[edge[0]] += 1
            degrees[edge[1]] += 1
        retained = sorted(capped)
    return retained, dict(removed), enabled


def _boundary_audit(
    rows: Sequence[ParsedRow], contract: Mapping[str, Any]
) -> dict[str, Any]:
    window = contract["window"]
    closure = contract["run_closure"]
    release = contract["timestamp_release"]
    extraction_start = _parse_contract_datetime(
        window["extraction_start_local"], "extraction_start"
    )
    extraction_end = _parse_contract_datetime(
        window["extraction_end_local"], "extraction_end"
    )
    core_start = _parse_contract_datetime(window["core_start_local"], "core_start")
    core_end = _parse_contract_datetime(window["core_end_local"], "core_end")
    duration = closure["maximum_transaction_duration_minutes"]
    half = timedelta(minutes=float(release["rounding_minutes"]) / 2)
    core_rows = [row for row in rows if row.role == "core"]
    before_minutes = (core_start - extraction_start).total_seconds() / 60
    after_minutes = (extraction_end - core_end).total_seconds() / 60
    if duration is None:
        return {
            "status": "NOT_EVALUATED_NO_DECLARED_DURATION_BOUND",
            "duration_bound_minutes": None,
            "duration_bound_basis": "none",
            "duration_bound_evidence": dict(closure["duration_bound_evidence"]),
            "duration_evidence_validation": "STRUCTURE_AND_DIGEST_ONLY_NOT_SEMANTIC",
            "buffer_before_core_minutes": before_minutes,
            "buffer_after_core_minutes": after_minutes,
            "rows_contradicting_declared_duration_bound": None,
            "maximum_observed_minimum_possible_duration_minutes": None,
            "core_rows_outside_supported_release_start_envelope": None,
            "interpretation": (
                "A partner may start arbitrarily earlier without a run/transaction "
                "duration bound; neighboring-day retrieval alone cannot certify closure."
            ),
        }

    duration_delta = timedelta(minutes=float(duration))
    minimum_possible_durations = []
    for row in rows:
        if (
            row.released_start is None
            or row.released_end is None
            or row.interval_status != "determinate_outer_interval"
        ):
            continue
        minimum_possible_durations.append(
            max(
                0.0,
                (row.released_end - row.released_start).total_seconds() / 60.0
                - float(release["rounding_minutes"]),
            )
        )
    duration_contradictions = sum(
        lower_bound > float(duration) + 1e-9
        for lower_bound in minimum_possible_durations
    )
    unsupported = 0
    indeterminate = 0
    for row in core_rows:
        if row.interval_start is None or row.interval_end is None:
            indeterminate += 1
            unsupported += 1
            continue
        earliest_released_partner_start = row.interval_start - duration_delta - half
        latest_released_partner_start = row.interval_end + half
        if not (
            extraction_start <= earliest_released_partner_start
            and extraction_end > latest_released_partner_start
        ):
            unsupported += 1
    basis = closure["duration_bound_basis"]
    if duration_contradictions:
        status = "FAIL_DURATION_BOUND_CONTRADICTED_BY_RELEASED_TIMES"
    elif unsupported:
        status = "FAIL_DECLARED_BUFFER_TOO_NARROW"
    elif basis == "operator_verified":
        status = "PASS_UNDER_DECLARED_OPERATOR_VERIFIED_DURATION_BOUND"
    elif basis == "externally_validated":
        status = "PASS_UNDER_DECLARED_EXTERNALLY_VALIDATED_DURATION_BOUND"
    else:
        status = "PASS_ONLY_UNDER_ANALYST_DURATION_ASSUMPTION"
    return {
        "status": status,
        "duration_bound_minutes": float(duration),
        "duration_bound_basis": basis,
        "duration_bound_evidence": dict(closure["duration_bound_evidence"]),
        "duration_evidence_validation": "STRUCTURE_AND_DIGEST_ONLY_NOT_SEMANTIC",
        "buffer_before_core_minutes": before_minutes,
        "buffer_after_core_minutes": after_minutes,
        "rows_contradicting_declared_duration_bound": duration_contradictions,
        "maximum_observed_minimum_possible_duration_minutes": max(
            minimum_possible_durations, default=None
        ),
        "core_rows_outside_supported_release_start_envelope": unsupported,
        "core_rows_with_indeterminate_service_interval": indeterminate,
        "interpretation": (
            "This tests whether the declared released-start extraction window contains "
            "every temporal partner allowed by the stated duration bound and rounding "
            "envelope. It does not observe Shared Trip ID."
        ),
    }


def audit_rows(
    raw_rows: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    *,
    generated_at_utc: str | None = None,
) -> AuditArtifacts:
    """Return a redacted, deterministic audit for a declared public snapshot."""

    validate_contract(contract)
    if generated_at_utc is None:
        generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    else:
        try:
            generated = datetime.fromisoformat(generated_at_utc)
        except (TypeError, ValueError) as exc:
            raise ValueError("generated_at_utc must be an ISO UTC timestamp") from exc
        if generated.tzinfo is None or generated.utcoffset() != timedelta(0):
            raise ValueError("generated_at_utc must include a zero UTC offset")
    input_sha256 = canonical_rows_sha256(raw_rows)

    parsed_rows, preparation = _prepare_rows(raw_rows, contract)
    input_spec = contract["input"]
    actual_rows = len(raw_rows)
    expected_rows = input_spec["expected_row_count"]
    expected_hash = input_spec["expected_input_sha256"]
    input_checks = {
        "actual_row_count": actual_rows,
        "expected_row_count": expected_rows,
        "row_count_matches": expected_rows is not None and expected_rows == actual_rows,
        "actual_input_sha256": input_sha256,
        "expected_input_sha256": expected_hash,
        "input_hash_basis": input_spec["input_hash_basis"],
        "input_sha256_pinned": True,
        "input_sha256_matches": expected_hash == input_sha256,
        "server_count_verified": bool(input_spec["server_count_verified"]),
        "snapshot_stable_during_extraction": bool(
            input_spec["snapshot_stable_during_extraction"]
        ),
        "selection_scope": input_spec["selection_scope"],
        "all_public_rows_scope": (
            input_spec["selection_scope"]
            == "all_public_rows_in_released_start_window_plus_null_start_evidence"
        ),
    }
    actual_target_like_null_starts = preparation["operator_consistency_counts"].get(
        "target_literal_null_start", 0
    )
    null_start_scope = input_spec["null_start_scope"]
    server_null_start_count = input_spec["server_target_like_null_start_row_count"]
    if null_start_scope == "not_verified":
        null_start_scope_status = "NOT_VERIFIED"
    elif server_null_start_count != actual_target_like_null_starts:
        null_start_scope_status = "SERVER_INPUT_COUNT_MISMATCH"
    else:
        null_start_scope_status = "PASS"
    input_checks.update(
        {
            "null_start_scope": null_start_scope,
            "server_target_like_null_start_row_count": server_null_start_count,
            "actual_included_target_like_null_start_row_count": (
                actual_target_like_null_starts
            ),
            "null_start_count_evidence_sha256": input_spec[
                "null_start_count_evidence_sha256"
            ],
            "null_start_scope_status": null_start_scope_status,
        }
    )
    completeness_failures = []
    if expected_rows is None or expected_rows != actual_rows:
        completeness_failures.append("server/local row count not affirmatively matched")
    if expected_hash is not None and expected_hash != input_sha256:
        completeness_failures.append("input SHA-256 mismatch")
    if not input_checks["server_count_verified"]:
        completeness_failures.append("server count was not verified")
    if not input_checks["snapshot_stable_during_extraction"]:
        completeness_failures.append("snapshot changed or stability was not verified")
    if not input_checks["all_public_rows_scope"]:
        completeness_failures.append(
            "selection did not combine the released-start window with null-start evidence"
        )
    if null_start_scope_status != "PASS":
        completeness_failures.append(
            "literal Match=true, K=2 null-start rows were not globally count-closed"
        )
    outside_declared_extraction = preparation["operator_consistency_counts"].get(
        "released_start_outside_declared_extraction", 0
    )
    if outside_declared_extraction:
        completeness_failures.append(
            "rows have released starts outside the declared extraction window"
        )

    graph_limit_error: str | None = None
    logical_edges: list[tuple[int, int]] = []
    logical_counts: dict[str, int] = {}
    try:
        logical_edges, logical_counts = _build_logical_edges(
            parsed_rows, contract["candidate_graph"]["max_materialized_logical_edges"]
        )
    except EdgeMaterializationLimit as exc:
        graph_limit_error = str(exc)

    fallback_limit = contract["candidate_graph"].get("exact_fallback_max_core_nodes", 28)
    fallback_edge_limit = contract["candidate_graph"].get(
        "exact_fallback_max_edges", 10_000
    )
    time_limit = float(
        contract["candidate_graph"].get("feasibility_time_limit_seconds", 60)
    )
    if graph_limit_error is None:
        logical_stats = _graph_statistics(parsed_rows, logical_edges)
        logical_feasibility = _cover_feasibility(
            parsed_rows,
            logical_edges,
            exact_fallback_max_core_nodes=fallback_limit,
            exact_fallback_max_edges=fallback_edge_limit,
            time_limit_seconds=time_limit,
        )
        heuristic_edges, heuristic_removed, heuristics_enabled = _build_heuristic_edges(
            parsed_rows,
            logical_edges,
            contract["candidate_graph"]["heuristics"],
        )
        heuristic_stats = _graph_statistics(parsed_rows, heuristic_edges)
        heuristic_feasibility = _cover_feasibility(
            parsed_rows,
            heuristic_edges,
            exact_fallback_max_core_nodes=fallback_limit,
            exact_fallback_max_edges=fallback_edge_limit,
            time_limit_seconds=time_limit,
        )
    else:
        logical_stats = {
            "node_count": sum(row.role in {"core", "buffer"} for row in parsed_rows),
            "core_node_count": sum(row.role == "core" for row in parsed_rows),
            "buffer_node_count": sum(row.role == "buffer" for row in parsed_rows),
            "edge_count": None,
        }
        logical_feasibility = {
            "status": "UNRESOLVED_EDGE_MATERIALIZATION_LIMIT",
            "certified_for_declared_graph": False,
            "backend": "none",
            "message": graph_limit_error,
        }
        heuristic_edges = []
        heuristic_removed = {}
        heuristics_enabled = any(
            value is not None
            for key, value in contract["candidate_graph"]["heuristics"].items()
            if key != "missing_spatial_policy"
        )
        heuristic_stats = {"edge_count": None}
        heuristic_feasibility = {
            "status": "NOT_RUN_LOGICAL_GRAPH_UNRESOLVED",
            "certified_for_declared_graph": False,
            "backend": "none",
            "message": "A heuristic graph was not substituted for an oversized logical graph.",
        }

    boundary = _boundary_audit(parsed_rows, contract)
    id_audit = preparation["identifiers"]
    consistency = preparation["operator_consistency_counts"]
    identifier_blockers = (
        id_audit["null_or_blank_rows"] > 0 or id_audit["duplicate_rows"] > 0
    )
    operator_contradictions = sum(
        consistency.get(key, 0)
        for key in (
            "match_true_authorized_false",
            "match_true_k_lt_2_or_unusable",
            "k_ge_2_authorized_false",
            "released_chronology_impossible",
        )
    )
    target_population_contradictions = consistency.get(
        "match_true_k_lt_2_or_unusable", 0
    )
    target_timestamp_integrity_rows = consistency.get(
        "target_literal_invalid_or_offgrid_timestamp", 0
    )
    unknown_match_rows = consistency.get("match_unknown", 0)
    explicit_noncontradiction = consistency.get(
        "match_false_k_2_not_a_logical_contradiction", 0
    )
    operator_issue_count = max(
        0,
        sum(consistency.values())
        - explicit_noncontradiction
        - consistency.get("target_literal_excluded_for_identifier_failure", 0)
        - consistency.get("released_start_outside_declared_extraction", 0),
    )

    if graph_limit_error is not None:
        production_status = "BLOCKED_LOGICAL_GRAPH_RESOURCE_LIMIT"
    elif null_start_scope_status != "PASS":
        production_status = "BLOCKED_NULL_START_SCOPE"
    elif completeness_failures:
        production_status = "BLOCKED_EXTRACTION_COMPLETENESS"
    elif identifier_blockers:
        production_status = "BLOCKED_IDENTIFIER_INTEGRITY"
    elif target_population_contradictions:
        production_status = "BLOCKED_MATCH_K_CONTRADICTIONS"
    elif unknown_match_rows:
        production_status = "BLOCKED_UNKNOWN_MATCH_LITERALS"
    elif target_timestamp_integrity_rows:
        production_status = "BLOCKED_TARGET_TIMESTAMP_INTEGRITY"
    elif boundary["status"].startswith("FAIL") or boundary["status"].startswith(
        "NOT_EVALUATED"
    ):
        production_status = "BLOCKED_BOUNDARY_SUPPORT"
    elif logical_feasibility["status"] not in {
        "EXACT_FEASIBLE",
        "NUMERICALLY_FEASIBLE_VALIDATED_INCUMBENT",
        "VACUOUS_NO_CORE_ROWS",
    }:
        production_status = "BLOCKED_DECLARED_GRAPH_COVER"
    elif logical_feasibility["status"] == "NUMERICALLY_FEASIBLE_VALIDATED_INCUMBENT":
        if boundary["status"] == "PASS_ONLY_UNDER_ANALYST_DURATION_ASSUMPTION":
            production_status = (
                "CONDITIONAL_NUMERICAL_UNCERTIFIED_WITH_ANALYST_DURATION_ASSUMPTION"
            )
        else:
            production_status = "CONDITIONAL_NUMERICAL_GRAPH_FEASIBILITY_UNCERTIFIED"
    elif operator_contradictions:
        production_status = "CONDITIONAL_WITH_OPERATOR_CONTRADICTIONS"
    elif boundary["status"] == "PASS_ONLY_UNDER_ANALYST_DURATION_ASSUMPTION":
        production_status = "CONDITIONAL_ON_ANALYST_DURATION_ASSUMPTION"
    else:
        production_status = "CONDITIONAL_GRAPH_READY"

    report = {
        "report_version": REPORT_VERSION,
        "generated_at_utc": generated_at_utc,
        "audit_contract_sha256": _canonical_sha256(contract),
        "dataset": {
            "dataset_id": DATASET_ID,
            "snapshot_revision_fingerprint_sha256": input_spec[
                "snapshot_revision_fingerprint_sha256"
            ],
        },
        "input_checks": {
            **input_checks,
            "completeness_status": "PASS" if not completeness_failures else "FAIL",
            "failure_reasons": completeness_failures,
        },
        "row_roles": preparation["roles"],
        "identifier_audit": id_audit,
        "literal_field_audit": preparation["literal_fields"],
        "operator_consistency_audit": {
            "counts": consistency,
            "status": (
                "PASS"
                if operator_issue_count == 0
                else "CONTRADICTIONS_OR_UNKNOWN_LITERALS_PRESENT"
            ),
            "match_false_k_2_note": (
                "K=2 with Match=false is reported separately and is not called a "
                "logical contradiction: two transactions in a run need not overlap."
            ),
        },
        "candidate_graphs": {
            "logical_necessary": {
                "rules": list(LOGICAL_RULES),
                "rules_explicitly_not_used": list(HEURISTIC_RULES)
                + ["authorization_equality_or_authorized_true_screen"],
                "timestamp_rounding_outer_half_width_minutes": float(
                    contract["timestamp_release"]["rounding_minutes"]
                )
                / 2.0,
                "edge_provenance_counts": logical_counts,
                "statistics": logical_stats,
                "cover_feasibility": logical_feasibility,
                "materialization_status": (
                    "COMPLETE" if graph_limit_error is None else "UNRESOLVED_NOT_TRIMMED"
                ),
                "partner_coverage_claim": "NOT_ESTIMATED_FROM_PUBLIC_ROWS",
            },
            "heuristic_sensitivity": {
                "enabled": heuristics_enabled,
                "rules": contract["candidate_graph"]["heuristics"],
                "sequential_edge_removals": heuristic_removed,
                "statistics": heuristic_stats,
                "cover_feasibility": heuristic_feasibility,
                "classification": "ANALYST_HEURISTIC_NOT_A_NECESSARY_SUPERGRAPH",
                "partner_coverage_claim": "NONE",
            },
        },
        "run_closure_audit": {
            "public_hidden_run_closure": {
                "status": "NOT_IDENTIFIED_FROM_PUBLIC_ROWS",
                "reason": (
                    "Shared Trip ID, vehicle ID, and partner identity are not released; "
                    "candidate degree and exact-cover feasibility cannot verify the actual run."
                ),
            },
            "boundary_extraction_support": boundary,
            "declared_graph_cover_status": logical_feasibility["status"],
            "production_status": production_status,
            "interpretation": (
                "At best, this report establishes completeness of one pinned row slice, "
                "boundary support under the declared duration basis, and structural "
                "feasibility of a necessary-condition graph. It never establishes true "
                "partner recall or observed run closure."
            ),
        },
        "redaction": {
            "raw_trip_identifiers_emitted": False,
            "edge_endpoint_identifiers_emitted": False,
            "row_level_data_emitted": False,
            "report_contains_aggregate_counts_and_hashes_only": True,
        },
    }
    validate_report(report)
    return AuditArtifacts(
        report=report,
        logical_edges=tuple(logical_edges),
        heuristic_edges=tuple(heuristic_edges),
        roles=tuple(row.role for row in parsed_rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Complete CSV slice")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    contract = load_contract(args.contract)
    rows = read_csv_rows(args.input)
    artifacts = audit_rows(rows, contract)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_suffix(args.report.suffix + ".part")
    temporary.write_text(
        json.dumps(artifacts.report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.report)
    print(
        json.dumps(
            {
                "report": str(args.report),
                "production_status": artifacts.report["run_closure_audit"][
                    "production_status"
                ],
                "raw_trip_identifiers_emitted": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
