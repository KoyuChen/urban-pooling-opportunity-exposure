#!/usr/bin/env python3
"""Declared-input adapter for Chicago tract-release compiler inputs.

This module translates a *caller-declared* Chicago count universe into the
generic inputs consumed by ``release_operator_compiler``.  It implements only
the documentary, one-way implications used by the project:

* if any fine tract is visible, every applicable pickup/start or dropoff/end
  marginal cell for that row must be ``HIGH``;
* independently pinned evidence can either verify the paired-threshold rule,
  identify specific LOW endpoints, or establish privacy only without any LOW
  implication; and
* every other blank has a TRUE clause and is never inverted to ``LOW``.

Pickup/start and dropoff/end are different factor namespaces.  Every supplied
trip, including buffer and context-only trips, is emitted as a
``ReleaseRowSpec`` and contributes one unit at each endpoint.  Outside-city,
source-missing, other-null, and unknown-null buckets are retained as ordinary
count factors without privacy thresholds.

The adapter verifies declared-universe, tract-support, and per-row label-support
hashes.  ``compile_chicago_release_problem`` is the only supported handoff: it
sanitizes a source problem before invoking the generic compiler.  These checks
do not establish that a declaration is substantively complete, that the
documentary rule matches the City's production transformation, or that a live
extraction was performed.  Those limitations remain explicit diagnostics.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import sys
from types import MappingProxyType
from typing import Hashable, Literal, Mapping, Sequence


# The repository runs these modules as standalone scripts rather than as one
# installed package.  Follow the same import convention as the benchmark code.
BOUNDS_DIR = Path(__file__).resolve().parents[1] / "bounds"
if str(BOUNDS_DIR) not in sys.path:
    sys.path.insert(0, str(BOUNDS_DIR))

from path_frontier_dp import (  # noqa: E402
    CountConstraint,
    EdgeSpec,
    ExactPathProblem,
    NodeSpec,
)
from release_operator_compiler import (  # noqa: E402
    EndpointRequirement,
    ObservationImplication,
    ReleaseClause,
    ReleaseCompilation,
    ReleaseOperatorSpec,
    ReleaseRowSpec,
    compile_release_operator,
    validate_release_compilation,
)


DATASET_ID = "6dvr-xwnh"
PICKUP_START = "pickup_start"
DROPOFF_END = "dropoff_end"
ENDPOINTS = (PICKUP_START, DROPOFF_END)

INTERNAL_TRACT = "internal_tract"
OUTSIDE_CITY = "outside_city"
SOURCE_MISSING = "source_missing"
OTHER_NULL = "other_null"
UNKNOWN_NULL = "unknown_null"
FACTOR_KINDS = frozenset(
    {
        INTERNAL_TRACT,
        OUTSIDE_CITY,
        SOURCE_MISSING,
        OTHER_NULL,
        UNKNOWN_NULL,
    }
)

PRIVACY_COARSENING = "privacy_coarsening"
BLANK_CAUSES = frozenset(
    {
        PRIVACY_COARSENING,
        OUTSIDE_CITY,
        SOURCE_MISSING,
        OTHER_NULL,
        UNKNOWN_NULL,
    }
)

AnalysisRole = Literal["core", "buffer", "context_only"]
EndpointRole = Literal["pickup_start", "dropoff_end"]
FactorKind = Literal[
    "internal_tract",
    "outside_city",
    "source_missing",
    "other_null",
    "unknown_null",
]
BlankCause = Literal[
    "privacy_coarsening",
    "outside_city",
    "source_missing",
    "other_null",
    "unknown_null",
]
ImplicationMode = Literal[
    "visible_all_applicable_high",
    "paired_threshold_low_disjunction",
    "known_low_endpoints",
    "privacy_only_no_low",
    "uninformative_blank",
]
PrivacyEvidenceState = Literal[
    "paired_threshold_verified",
    "known_low_endpoints",
    "privacy_only_no_low",
]
SupportCompleteness = Literal[
    "externally_verified",
    "analyst_declared_conditional",
]

PRIVACY_EVIDENCE_STATES = frozenset(
    {
        "paired_threshold_verified",
        "known_low_endpoints",
        "privacy_only_no_low",
    }
)
SUPPORT_COMPLETENESS_STATES = frozenset(
    {"externally_verified", "analyst_declared_conditional"}
)


_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _nonblank(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")
    if any(character in value for character in ("\n", "\r", "\x00")):
        raise ValueError(f"{name} must not contain line breaks or NUL bytes")
    return value


def _sha256(value: object, name: str) -> str:
    value = _nonblank(value, name)
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256")
    return value


def _literal_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def canonical_string_set_sha256(values: tuple[str, ...]) -> str:
    """Hash a nonempty set of unambiguous strings in canonical order."""

    if not values:
        raise ValueError("canonical string set must be nonempty")
    checked = tuple(_nonblank(value, "canonical set member") for value in values)
    if len(set(checked)) != len(checked):
        raise ValueError("canonical string set members must be distinct")
    payload = json.dumps(
        sorted(checked), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _text_sha256(value: str, name: str) -> str:
    return hashlib.sha256(_nonblank(value, name).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TractSupportPin:
    """Pinned support over which internal fine-tract labels are allowed."""

    vintage: str
    support_id: str
    tract_ids: tuple[str, ...]
    tract_ids_sha256: str


@dataclass(frozen=True)
class DeclaredTripUniversePin:
    """Caller declaration of the complete set of count-contributing nodes."""

    universe_id: str
    node_count: int
    node_ids_sha256: str
    all_cell_contributors_declared: bool


@dataclass(frozen=True)
class PrivacyEvidenceAuthorityContract:
    """Pinned authority contract allowed to support privacy-cause evidence."""

    authority_id: str
    contract_reference: str
    contract_sha256: str
    permitted_states: tuple[PrivacyEvidenceState, ...]
    independent_of_released_tract: bool


@dataclass(frozen=True)
class SupportEvidenceAuthorityContract:
    """Pinned authority contract allowed to certify complete label support."""

    authority_id: str
    contract_reference: str
    contract_sha256: str
    certifies_complete_label_support: bool
    independent_of_candidate_builder: bool


@dataclass(frozen=True)
class PrivacyCauseEvidencePin:
    """Content-addressed row evidence under one declared authority contract."""

    subject_node_id: str
    authority_id: str
    evidence_id: str
    evidence_sha256: str
    state: PrivacyEvidenceState
    known_low_endpoints: tuple[EndpointRole, ...] = ()


@dataclass(frozen=True)
class LabelSupportDeclaration:
    """Digest and completeness status for one row's full label bindings."""

    bindings_sha256: str
    completeness: SupportCompleteness
    authority_id: str | None = None
    evidence_reference: str | None = None
    evidence_sha256: str | None = None


@dataclass(frozen=True)
class ChicagoReleaseMetadata:
    """Versioned semantics required before any City-specific compilation."""

    dataset_id: str
    dataset_snapshot_sha256: str
    operator_id: str
    methodology_reference: str
    endpoint_clarification_reference: str
    tract_support: TractSupportPin
    trip_universe: DeclaredTripUniversePin
    partition_ids: tuple[str, ...]
    partition_definition: str
    time_bin_definition: str
    privacy_evidence_authorities: tuple[
        PrivacyEvidenceAuthorityContract, ...
    ] = ()
    support_evidence_authorities: tuple[
        SupportEvidenceAuthorityContract, ...
    ] = ()
    time_zone: str = "America/Chicago"
    cell_minutes: int = 15
    count_unit: str = "unique_trip"
    low_upper: int = 2
    high_lower: int = 3


@dataclass(frozen=True)
class EndpointReleaseObservation:
    """Normalized released value and explicit reason for any blank.

    Empty strings are deliberately not normalized here: callers must map a raw
    value to either a nonblank tract or ``None`` plus one declared cause.
    """

    released_tract: str | None
    blank_cause: BlankCause | None


@dataclass(frozen=True)
class ChicagoReleaseContext:
    """Version namespace embedded in every Chicago count-factor identity."""

    dataset_id: str
    dataset_snapshot_sha256: str
    operator_id: str
    tract_vintage: str
    tract_support_sha256: str
    partition_definition_sha256: str
    time_bin_definition_sha256: str


@dataclass(frozen=True)
class ChicagoCountFactor:
    """One endpoint-marginal cell or a nonprivacy null-cause bucket."""

    release_context: ChicagoReleaseContext
    endpoint: EndpointRole
    factor_kind: FactorKind
    time_bin_id: str
    partition_id: str
    tract_id: str | None = None


@dataclass(frozen=True)
class DeclaredChicagoTrip:
    """One supplied contributing trip and its label-dependent endpoint cells."""

    node_id: str
    analysis_role: AnalysisRole
    pickup: EndpointReleaseObservation
    dropoff: EndpointReleaseObservation
    endpoint_factors_by_label: Mapping[
        str, Mapping[EndpointRole, ChicagoCountFactor]
    ]
    label_support: LabelSupportDeclaration
    privacy_cause_evidence: PrivacyCauseEvidencePin | None = None


@dataclass(frozen=True)
class ChicagoReleaseObservation:
    """Hashable semantic state passed to the generic release compiler."""

    mode: ImplicationMode
    applicable_endpoints: tuple[EndpointRole, ...]
    known_low_endpoints: tuple[EndpointRole, ...] = ()


@dataclass(frozen=True)
class ChicagoRowAudit:
    node_id: str
    analysis_role: AnalysisRole
    observation: ChicagoReleaseObservation
    visible_endpoints: tuple[EndpointRole, ...]
    blank_causes: tuple[tuple[EndpointRole, BlankCause], ...]
    label_support: tuple[str, ...]
    label_support_sha256: str
    support_completeness: SupportCompleteness
    support_authority_id: str | None
    support_authority_contract_sha256: str | None
    support_evidence_reference: str | None
    support_evidence_sha256: str | None
    distinct_label_count: int
    endpoint_factor_bindings: int


@dataclass(frozen=True)
class PrivacyEvidenceAudit:
    node_id: str
    authority_id: str
    authority_contract_sha256: str
    evidence_id: str
    evidence_sha256: str
    state: PrivacyEvidenceState
    known_low_endpoints: tuple[EndpointRole, ...]


@dataclass(frozen=True)
class ChicagoAdapterDiagnostics:
    """Immutable audit record; it intentionally carries negative claims."""

    dataset_id: str
    dataset_snapshot_sha256: str
    declared_universe_id: str
    declared_trip_count: int
    emitted_release_row_count: int
    input_universe_pin_verified: bool
    all_supplied_trips_bound: bool
    declared_all_cell_contributors: bool
    analysis_role_counts: tuple[tuple[str, int], ...]
    visible_endpoint_count: int
    blank_cause_counts: tuple[tuple[str, int], ...]
    factor_binding_kind_counts: tuple[tuple[str, int], ...]
    distinct_factor_count: int
    distinct_internal_factor_count: int
    tract_vintage: str
    tract_support_id: str
    tract_support_sha256: str
    tract_support_size: int
    release_context: ChicagoReleaseContext
    label_support_scope: SupportCompleteness
    label_support_outer_claim_licensed: bool
    privacy_evidence_audits: tuple[PrivacyEvidenceAudit, ...]
    row_audits: tuple[ChicagoRowAudit, ...]
    city_implementation_validated: bool
    live_extraction_performed: bool
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ChicagoCompilerInputs:
    """Generic compiler inputs plus their City-specific audit diagnostics."""

    metadata: ChicagoReleaseMetadata
    operator: ReleaseOperatorSpec
    rows: tuple[ReleaseRowSpec, ...]
    count_constraints: tuple[CountConstraint, ...]
    diagnostics: ChicagoAdapterDiagnostics
    contract_sha256: str


@dataclass(frozen=True)
class ChicagoHandoffAudit:
    source_node_count: int
    exact_node_set_verified: bool
    exact_roles_verified: bool
    exact_label_supports_verified: bool
    source_chicago_factor_maps_absent: bool
    source_chicago_constraints_absent: bool
    declared_non_chicago_factor_count: int
    adapter_constraint_count: int
    preserved_non_chicago_constraint_count: int
    compiler_input_contract_sha256: str


@dataclass(frozen=True)
class ChicagoSanitizedHandoff:
    source_problem: ExactPathProblem
    compilation: ReleaseCompilation
    audit: ChicagoHandoffAudit


def _canonicalize_metadata(
    metadata: ChicagoReleaseMetadata,
) -> ChicagoReleaseMetadata:
    if not isinstance(metadata, ChicagoReleaseMetadata):
        raise ValueError("metadata must be ChicagoReleaseMetadata")
    if not isinstance(metadata.tract_support, TractSupportPin):
        raise ValueError("tract_support must be TractSupportPin")
    if not isinstance(metadata.trip_universe, DeclaredTripUniversePin):
        raise ValueError("trip_universe must be DeclaredTripUniversePin")
    authorities = []
    for authority in metadata.privacy_evidence_authorities:
        if not isinstance(authority, PrivacyEvidenceAuthorityContract):
            raise ValueError(
                "privacy_evidence_authorities must contain authority contracts"
            )
        authorities.append(
            replace(
                authority,
                permitted_states=tuple(authority.permitted_states),
            )
        )
    support_authorities = []
    for authority in metadata.support_evidence_authorities:
        if not isinstance(authority, SupportEvidenceAuthorityContract):
            raise ValueError(
                "support_evidence_authorities must contain authority contracts"
            )
        support_authorities.append(authority)
    return replace(
        metadata,
        tract_support=replace(
            metadata.tract_support,
            tract_ids=tuple(metadata.tract_support.tract_ids),
        ),
        partition_ids=tuple(metadata.partition_ids),
        privacy_evidence_authorities=tuple(authorities),
        support_evidence_authorities=tuple(support_authorities),
    )


def chicago_release_context(
    metadata: ChicagoReleaseMetadata,
) -> ChicagoReleaseContext:
    """Derive the exact namespace required on every emitted factor."""

    return ChicagoReleaseContext(
        dataset_id=metadata.dataset_id,
        dataset_snapshot_sha256=metadata.dataset_snapshot_sha256,
        operator_id=metadata.operator_id,
        tract_vintage=metadata.tract_support.vintage,
        tract_support_sha256=metadata.tract_support.tract_ids_sha256,
        partition_definition_sha256=_text_sha256(
            metadata.partition_definition, "partition_definition"
        ),
        time_bin_definition_sha256=_text_sha256(
            metadata.time_bin_definition, "time_bin_definition"
        ),
    )


def _context_payload(context: ChicagoReleaseContext) -> dict[str, object]:
    return {
        "dataset_id": context.dataset_id,
        "dataset_snapshot_sha256": context.dataset_snapshot_sha256,
        "operator_id": context.operator_id,
        "tract_vintage": context.tract_vintage,
        "tract_support_sha256": context.tract_support_sha256,
        "partition_definition_sha256": context.partition_definition_sha256,
        "time_bin_definition_sha256": context.time_bin_definition_sha256,
    }


def _factor_payload(factor: ChicagoCountFactor) -> dict[str, object]:
    return {
        "release_context": _context_payload(factor.release_context),
        "endpoint": factor.endpoint,
        "factor_kind": factor.factor_kind,
        "time_bin_id": factor.time_bin_id,
        "partition_id": factor.partition_id,
        "tract_id": factor.tract_id,
    }


def canonical_label_support_sha256(
    bindings: Mapping[str, Mapping[EndpointRole, ChicagoCountFactor]],
) -> str:
    """Hash the complete label-to-two-endpoint binding declaration."""

    if not bindings:
        raise ValueError("label bindings must be nonempty")
    rows: list[dict[str, object]] = []
    for label, endpoint_map in bindings.items():
        label = _nonblank(label, "substantive label")
        if set(endpoint_map) != set(ENDPOINTS):
            raise ValueError(
                f"label {label!r} must bind exactly pickup_start and dropoff_end"
            )
        factors: dict[str, object] = {}
        for endpoint in ENDPOINTS:
            factor = endpoint_map[endpoint]
            if not isinstance(factor, ChicagoCountFactor):
                raise ValueError("label support factors must be ChicagoCountFactor")
            factors[endpoint] = _factor_payload(factor)
        rows.append({"label": label, "factors": factors})
    if len({row["label"] for row in rows}) != len(rows):
        raise ValueError("substantive labels must be distinct")
    payload = json.dumps(
        sorted(rows, key=lambda row: str(row["label"])),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_support(pin: TractSupportPin) -> set[str]:
    _nonblank(pin.vintage, "tract vintage")
    _nonblank(pin.support_id, "tract support_id")
    expected = _sha256(pin.tract_ids_sha256, "tract support SHA-256")
    actual = canonical_string_set_sha256(pin.tract_ids)
    if actual != expected:
        raise ValueError("tract support SHA-256 does not match tract_ids")
    return set(pin.tract_ids)


def _validate_metadata(metadata: ChicagoReleaseMetadata) -> set[str]:
    if metadata.dataset_id != DATASET_ID:
        raise ValueError(
            f"dataset_id must be the pinned Chicago release {DATASET_ID!r}"
        )
    _sha256(metadata.dataset_snapshot_sha256, "dataset snapshot SHA-256")
    _nonblank(metadata.operator_id, "operator_id")
    _nonblank(metadata.methodology_reference, "methodology_reference")
    _nonblank(
        metadata.endpoint_clarification_reference,
        "endpoint_clarification_reference",
    )
    _nonblank(metadata.partition_definition, "partition_definition")
    _nonblank(metadata.time_bin_definition, "time_bin_definition")
    if metadata.time_zone != "America/Chicago":
        raise ValueError("time_zone must be explicitly pinned to America/Chicago")
    if _literal_integer(metadata.cell_minutes, "cell_minutes") != 15:
        raise ValueError("the declared City tract cell must use 15-minute bins")
    if metadata.count_unit != "unique_trip":
        raise ValueError("the declared City threshold counts unique trips")
    thresholds = (
        _literal_integer(metadata.low_upper, "low_upper"),
        _literal_integer(metadata.high_lower, "high_lower"),
    )
    if thresholds != (2, 3):
        raise ValueError(
            "the documented at-most-two rule requires LOW <= 2 and HIGH >= 3"
        )
    if not metadata.partition_ids:
        raise ValueError("partition_ids must explicitly declare at least one cell partition")
    partition_ids = tuple(
        _nonblank(value, "partition_id") for value in metadata.partition_ids
    )
    if len(set(partition_ids)) != len(partition_ids):
        raise ValueError("partition_ids must be distinct")
    authority_ids: set[str] = set()
    for authority in metadata.privacy_evidence_authorities:
        authority_id = _nonblank(
            authority.authority_id, "privacy evidence authority_id"
        )
        if authority_id in authority_ids:
            raise ValueError("privacy evidence authority_ids must be distinct")
        authority_ids.add(authority_id)
        _nonblank(
            authority.contract_reference,
            f"privacy authority contract_reference for {authority_id!r}",
        )
        _sha256(
            authority.contract_sha256,
            f"privacy authority contract SHA-256 for {authority_id!r}",
        )
        if not authority.permitted_states:
            raise ValueError(
                f"privacy authority {authority_id!r} must permit at least one state"
            )
        if len(set(authority.permitted_states)) != len(
            authority.permitted_states
        ):
            raise ValueError(
                f"privacy authority {authority_id!r} repeats a permitted state"
            )
        if any(
            state not in PRIVACY_EVIDENCE_STATES
            for state in authority.permitted_states
        ):
            raise ValueError(
                f"privacy authority {authority_id!r} has an unknown evidence state"
            )
        if authority.independent_of_released_tract is not True:
            raise ValueError(
                f"privacy authority {authority_id!r} must contractually be "
                "independent of the released tract value"
            )
    support_authority_ids: set[str] = set()
    for authority in metadata.support_evidence_authorities:
        authority_id = _nonblank(
            authority.authority_id, "support evidence authority_id"
        )
        if authority_id in support_authority_ids:
            raise ValueError("support evidence authority_ids must be distinct")
        support_authority_ids.add(authority_id)
        _nonblank(
            authority.contract_reference,
            f"support authority contract_reference for {authority_id!r}",
        )
        _sha256(
            authority.contract_sha256,
            f"support authority contract SHA-256 for {authority_id!r}",
        )
        if authority.certifies_complete_label_support is not True:
            raise ValueError(
                f"support authority {authority_id!r} must contractually certify "
                "complete label support"
            )
        if authority.independent_of_candidate_builder is not True:
            raise ValueError(
                f"support authority {authority_id!r} must be independent of the "
                "candidate builder"
            )
    universe = metadata.trip_universe
    _nonblank(universe.universe_id, "trip universe_id")
    if _literal_integer(universe.node_count, "trip universe node_count") <= 0:
        raise ValueError("trip universe node_count must be positive")
    _sha256(universe.node_ids_sha256, "trip universe node_ids SHA-256")
    if universe.all_cell_contributors_declared is not True:
        raise ValueError(
            "trip universe must explicitly declare that all cell contributors "
            "are included"
        )
    tract_support = _validate_support(metadata.tract_support)
    context = chicago_release_context(metadata)
    _sha256(
        context.dataset_snapshot_sha256,
        "release-context dataset snapshot SHA-256",
    )
    _sha256(
        context.tract_support_sha256,
        "release-context tract support SHA-256",
    )
    _sha256(
        context.partition_definition_sha256,
        "release-context partition definition SHA-256",
    )
    _sha256(
        context.time_bin_definition_sha256,
        "release-context time-bin definition SHA-256",
    )
    return tract_support


def _validate_endpoint_observation(
    endpoint: EndpointRole,
    observation: EndpointReleaseObservation,
    tract_support: set[str],
) -> None:
    if observation.released_tract is not None:
        tract = _nonblank(
            observation.released_tract, f"released tract at {endpoint}"
        )
        if observation.blank_cause is not None:
            raise ValueError(
                f"visible released tract at {endpoint} cannot also have a blank cause"
            )
        if tract not in tract_support:
            raise ValueError(
                f"released tract {tract!r} at {endpoint} is outside the pinned support"
            )
        return
    if observation.blank_cause not in BLANK_CAUSES:
        raise ValueError(
            f"blank released tract at {endpoint} requires one explicit blank cause"
        )


def _validate_factor(
    factor: ChicagoCountFactor,
    *,
    expected_endpoint: EndpointRole,
    metadata: ChicagoReleaseMetadata,
    tract_support: set[str],
) -> None:
    expected_context = chicago_release_context(metadata)
    if factor.release_context != expected_context:
        raise ValueError(
            "Chicago factor release context does not match the pinned snapshot, "
            "operator, tract vintage/support, or cell definitions"
        )
    if factor.endpoint != expected_endpoint:
        raise ValueError(
            f"factor endpoint {factor.endpoint!r} does not match binding "
            f"{expected_endpoint!r}"
        )
    if factor.factor_kind not in FACTOR_KINDS:
        raise ValueError(f"unknown factor_kind {factor.factor_kind!r}")
    _nonblank(factor.time_bin_id, "time_bin_id")
    if factor.partition_id not in set(metadata.partition_ids):
        raise ValueError(
            f"factor partition {factor.partition_id!r} is not in the pinned partitions"
        )
    if factor.factor_kind == INTERNAL_TRACT:
        tract = _nonblank(factor.tract_id, "internal factor tract_id")
        if tract not in tract_support:
            raise ValueError(
                f"internal factor tract {tract!r} is outside the pinned support"
            )
    elif factor.tract_id is not None:
        raise ValueError("non-tract cause factors must not carry a tract_id")


def _observation_for_trip(
    trip: DeclaredChicagoTrip,
    applicable_by_label: tuple[tuple[EndpointRole, ...], ...],
    metadata: ChicagoReleaseMetadata,
) -> tuple[ChicagoReleaseObservation, PrivacyEvidenceAudit | None]:
    visible = tuple(
        endpoint
        for endpoint, value in (
            (PICKUP_START, trip.pickup),
            (DROPOFF_END, trip.dropoff),
        )
        if value.released_tract is not None
    )
    privacy_causes = tuple(
        endpoint
        for endpoint, value in (
            (PICKUP_START, trip.pickup),
            (DROPOFF_END, trip.dropoff),
        )
        if value.blank_cause == PRIVACY_COARSENING
    )

    evidence = trip.privacy_cause_evidence
    evidence_audit: PrivacyEvidenceAudit | None = None
    known_low_endpoints: tuple[EndpointRole, ...] = ()
    if evidence is None:
        if privacy_causes:
            raise ValueError(
                f"trip {trip.node_id!r} declares privacy_coarsening without an "
                "authority-contracted evidence pin"
            )
    else:
        if not isinstance(evidence, PrivacyCauseEvidencePin):
            raise ValueError("privacy evidence must be PrivacyCauseEvidencePin")
        if not privacy_causes:
            raise ValueError(
                f"trip {trip.node_id!r} pins privacy evidence but declares no "
                "privacy_coarsening blank"
            )
        if visible:
            raise ValueError(
                f"trip {trip.node_id!r} cannot combine a visible fine tract "
                "with privacy-cause evidence"
            )
        if evidence.subject_node_id != trip.node_id:
            raise ValueError(
                f"privacy evidence subject does not match trip {trip.node_id!r}"
            )
        _nonblank(evidence.evidence_id, "privacy evidence_id")
        _sha256(evidence.evidence_sha256, "privacy evidence SHA-256")
        if evidence.state not in PRIVACY_EVIDENCE_STATES:
            raise ValueError("privacy evidence has an unknown state")
        authority_by_id = {
            authority.authority_id: authority
            for authority in metadata.privacy_evidence_authorities
        }
        authority = authority_by_id.get(evidence.authority_id)
        if authority is None:
            raise ValueError(
                f"privacy evidence authority {evidence.authority_id!r} is not "
                "declared in metadata"
            )
        if evidence.state not in authority.permitted_states:
            raise ValueError(
                f"privacy evidence authority {evidence.authority_id!r} does not "
                f"permit state {evidence.state!r}"
            )
        known_low_endpoints = tuple(evidence.known_low_endpoints)
        if len(set(known_low_endpoints)) != len(known_low_endpoints):
            raise ValueError("known LOW endpoints must be distinct")
        if any(endpoint not in ENDPOINTS for endpoint in known_low_endpoints):
            raise ValueError("known LOW evidence references an unknown endpoint")
        if evidence.state == "known_low_endpoints":
            if not known_low_endpoints:
                raise ValueError(
                    "known_low_endpoints evidence must name at least one endpoint"
                )
        elif known_low_endpoints:
            raise ValueError(
                f"privacy evidence state {evidence.state!r} must not name known "
                "LOW endpoints"
            )
        evidence_audit = PrivacyEvidenceAudit(
            node_id=trip.node_id,
            authority_id=authority.authority_id,
            authority_contract_sha256=authority.contract_sha256,
            evidence_id=evidence.evidence_id,
            evidence_sha256=evidence.evidence_sha256,
            state=evidence.state,
            known_low_endpoints=known_low_endpoints,
        )

    evidence_state = None if evidence is None else evidence.state
    informative = bool(visible) or evidence_state in {
        "paired_threshold_verified",
        "known_low_endpoints",
    }
    if informative and len(set(applicable_by_label)) != 1:
        raise ValueError(
            f"trip {trip.node_id!r} has label-dependent endpoint applicability; "
            "the one-way release clause would be ambiguous"
        )
    applicable = applicable_by_label[0] if informative else ()

    if visible:
        return (
            ChicagoReleaseObservation(
                "visible_all_applicable_high", applicable
            ),
            evidence_audit,
        )
    if evidence_state == "paired_threshold_verified":
        if not applicable:
            raise ValueError(
                f"trip {trip.node_id!r} has paired-threshold evidence but no "
                "applicable internal endpoint cell"
            )
        return (
            ChicagoReleaseObservation(
                "paired_threshold_low_disjunction", applicable
            ),
            evidence_audit,
        )
    if evidence_state == "known_low_endpoints":
        assert evidence is not None
        if any(endpoint not in applicable for endpoint in known_low_endpoints):
            raise ValueError(
                "known LOW endpoint is not an applicable internal cell for every label"
            )
        return (
            ChicagoReleaseObservation(
                "known_low_endpoints",
                applicable,
                known_low_endpoints,
            ),
            evidence_audit,
        )
    if evidence_state == "privacy_only_no_low":
        return (
            ChicagoReleaseObservation("privacy_only_no_low", ()),
            evidence_audit,
        )
    return ChicagoReleaseObservation("uninformative_blank", ()), None


def _implication_for_observation(
    observation: ChicagoReleaseObservation,
) -> ObservationImplication:
    if observation.mode == "visible_all_applicable_high":
        if not observation.applicable_endpoints:
            raise ValueError("a visible tract must have an applicable endpoint cell")
        alternatives = (
            ReleaseClause(
                "visible-all-applicable-high",
                tuple(
                    EndpointRequirement(endpoint, "HIGH")
                    for endpoint in observation.applicable_endpoints
                ),
            ),
        )
    elif observation.mode == "paired_threshold_low_disjunction":
        if not observation.applicable_endpoints:
            raise ValueError("paired-threshold evidence needs an applicable cell")
        alternatives = tuple(
            ReleaseClause(
                f"paired-threshold-{endpoint}-low",
                (EndpointRequirement(endpoint, "LOW"),),
            )
            for endpoint in observation.applicable_endpoints
        )
    elif observation.mode == "known_low_endpoints":
        if not observation.known_low_endpoints:
            raise ValueError("known-low observation must name at least one endpoint")
        if any(
            endpoint not in observation.applicable_endpoints
            for endpoint in observation.known_low_endpoints
        ):
            raise ValueError("known LOW endpoint must be applicable")
        alternatives = (
            ReleaseClause(
                "known-low-endpoints",
                tuple(
                    EndpointRequirement(endpoint, "LOW")
                    for endpoint in observation.known_low_endpoints
                ),
            ),
        )
    elif observation.mode in {"privacy_only_no_low", "uninformative_blank"}:
        if observation.applicable_endpoints:
            raise ValueError("no-LOW observation must use a TRUE clause")
        clause_id = (
            "privacy-only-no-low"
            if observation.mode == "privacy_only_no_low"
            else "blank-not-inverted"
        )
        alternatives = (ReleaseClause(clause_id, ()),)
    else:  # pragma: no cover - guarded by the literal constructor and tests
        raise ValueError(f"unknown Chicago observation mode {observation.mode!r}")
    return ObservationImplication(observation, alternatives)


def _validate_label_support_declaration(
    trip: DeclaredChicagoTrip,
    computed_sha256: str,
    metadata: ChicagoReleaseMetadata,
) -> tuple[str | None, str | None]:
    declaration = trip.label_support
    if not isinstance(declaration, LabelSupportDeclaration):
        raise ValueError("trip label_support must be LabelSupportDeclaration")
    declared_digest = _sha256(
        declaration.bindings_sha256,
        f"label-support bindings SHA-256 for trip {trip.node_id!r}",
    )
    if declared_digest != computed_sha256:
        raise ValueError(
            f"trip {trip.node_id!r} label-support digest does not match its bindings"
        )
    if declaration.completeness not in SUPPORT_COMPLETENESS_STATES:
        raise ValueError(
            f"trip {trip.node_id!r} has unknown support completeness status"
        )
    if declaration.completeness == "externally_verified":
        authority_id = _nonblank(
            declaration.authority_id,
            f"support authority_id for trip {trip.node_id!r}",
        )
        authority_by_id = {
            authority.authority_id: authority
            for authority in metadata.support_evidence_authorities
        }
        authority = authority_by_id.get(authority_id)
        if authority is None:
            raise ValueError(
                f"support evidence authority {authority_id!r} is not declared "
                "in metadata"
            )
        _nonblank(
            declaration.evidence_reference,
            f"support evidence_reference for trip {trip.node_id!r}",
        )
        _sha256(
            declaration.evidence_sha256,
            f"support evidence SHA-256 for trip {trip.node_id!r}",
        )
        return authority_id, authority.contract_sha256
    elif (
        declaration.authority_id is not None
        or declaration.evidence_reference is not None
        or declaration.evidence_sha256 is not None
    ):
        raise ValueError(
            "analyst-declared conditional support must not masquerade as "
            "externally verified evidence"
        )
    return None, None


def _freeze_endpoint_bindings(
    bindings: Mapping[str, Mapping[EndpointRole, ChicagoCountFactor]],
) -> Mapping[str, Mapping[EndpointRole, ChicagoCountFactor]]:
    return MappingProxyType(
        {
            label: MappingProxyType(dict(endpoint_map))
            for label, endpoint_map in bindings.items()
        }
    )


def _compiler_contract_sha256(
    *,
    metadata: ChicagoReleaseMetadata,
    operator: ReleaseOperatorSpec,
    rows: tuple[ReleaseRowSpec, ...],
    count_constraints: tuple[CountConstraint, ...],
    diagnostics: ChicagoAdapterDiagnostics,
) -> str:
    row_payloads: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row.observation, ChicagoReleaseObservation):
            raise ValueError("Chicago compiler row has a foreign observation")
        bindings = []
        for label, endpoint_map in row.endpoint_factors_by_label.items():
            if not isinstance(label, str):
                raise ValueError("Chicago compiler labels must be strings")
            bindings.append(
                {
                    "label": label,
                    "pickup_start": _factor_payload(
                        endpoint_map[PICKUP_START]
                    ),
                    "dropoff_end": _factor_payload(
                        endpoint_map[DROPOFF_END]
                    ),
                }
            )
        row_payloads.append(
            {
                "node_id": row.node_id,
                "observation": {
                    "mode": row.observation.mode,
                    "applicable_endpoints": row.observation.applicable_endpoints,
                    "known_low_endpoints": row.observation.known_low_endpoints,
                },
                "bindings": bindings,
            }
        )
    implication_payloads = []
    for implication in operator.implications:
        if not isinstance(implication.observation, ChicagoReleaseObservation):
            raise ValueError("Chicago operator has a foreign observation")
        implication_payloads.append(
            {
                "observation": {
                    "mode": implication.observation.mode,
                    "applicable_endpoints": (
                        implication.observation.applicable_endpoints
                    ),
                    "known_low_endpoints": (
                        implication.observation.known_low_endpoints
                    ),
                },
                "alternatives": [
                    {
                        "clause_id": clause.clause_id,
                        "requirements": [
                            (atom.endpoint, atom.requirement)
                            for atom in clause.requirements
                        ],
                    }
                    for clause in implication.alternatives
                ],
            }
        )
    constraint_payloads = []
    for constraint in count_constraints:
        if not isinstance(constraint.factor, ChicagoCountFactor):
            raise ValueError("adapter count constraints must use Chicago factors")
        constraint_payloads.append(
            {
                "factor": _factor_payload(constraint.factor),
                "lower": constraint.lower,
                "upper": constraint.upper,
                "low_upper": constraint.low_upper,
                "high_lower": constraint.high_lower,
            }
        )
    payload = {
        "metadata": {
            "dataset_id": metadata.dataset_id,
            "snapshot": metadata.dataset_snapshot_sha256,
            "operator_id": metadata.operator_id,
            "trip_universe": metadata.trip_universe.node_ids_sha256,
            "tract_support": metadata.tract_support.tract_ids_sha256,
            "release_context": _context_payload(
                chicago_release_context(metadata)
            ),
        },
        "operator": {
            "operator_id": operator.operator_id,
            "audit_reference": operator.audit_reference,
            "endpoints": operator.endpoints,
            "implications": implication_payloads,
        },
        "rows": row_payloads,
        "constraints": constraint_payloads,
        "row_contracts": [
            {
                "node_id": audit.node_id,
                "role": audit.analysis_role,
                "label_support": audit.label_support,
                "label_support_sha256": audit.label_support_sha256,
                "support_completeness": audit.support_completeness,
                "support_authority_id": audit.support_authority_id,
                "support_authority_contract_sha256": (
                    audit.support_authority_contract_sha256
                ),
                "support_evidence_reference": audit.support_evidence_reference,
                "support_evidence_sha256": audit.support_evidence_sha256,
            }
            for audit in diagnostics.row_audits
        ],
        "privacy_evidence": [
            {
                "node_id": audit.node_id,
                "authority_id": audit.authority_id,
                "authority_contract_sha256": audit.authority_contract_sha256,
                "evidence_id": audit.evidence_id,
                "evidence_sha256": audit.evidence_sha256,
                "state": audit.state,
                "known_low_endpoints": audit.known_low_endpoints,
            }
            for audit in diagnostics.privacy_evidence_audits
        ],
        "support_scope": diagnostics.label_support_scope,
        "label_support_outer_claim_licensed": (
            diagnostics.label_support_outer_claim_licensed
        ),
        "diagnostic_summary": {
            "dataset_id": diagnostics.dataset_id,
            "dataset_snapshot_sha256": diagnostics.dataset_snapshot_sha256,
            "declared_universe_id": diagnostics.declared_universe_id,
            "declared_trip_count": diagnostics.declared_trip_count,
            "emitted_release_row_count": diagnostics.emitted_release_row_count,
            "input_universe_pin_verified": (
                diagnostics.input_universe_pin_verified
            ),
            "all_supplied_trips_bound": diagnostics.all_supplied_trips_bound,
            "declared_all_cell_contributors": (
                diagnostics.declared_all_cell_contributors
            ),
            "analysis_role_counts": diagnostics.analysis_role_counts,
            "visible_endpoint_count": diagnostics.visible_endpoint_count,
            "blank_cause_counts": diagnostics.blank_cause_counts,
            "factor_binding_kind_counts": (
                diagnostics.factor_binding_kind_counts
            ),
            "distinct_factor_count": diagnostics.distinct_factor_count,
            "distinct_internal_factor_count": (
                diagnostics.distinct_internal_factor_count
            ),
            "tract_vintage": diagnostics.tract_vintage,
            "tract_support_id": diagnostics.tract_support_id,
            "tract_support_sha256": diagnostics.tract_support_sha256,
            "tract_support_size": diagnostics.tract_support_size,
            "release_context": _context_payload(
                diagnostics.release_context
            ),
            "city_implementation_validated": (
                diagnostics.city_implementation_validated
            ),
            "live_extraction_performed": diagnostics.live_extraction_performed,
            "limitations": diagnostics.limitations,
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_chicago_compiler_inputs(
    *,
    metadata: ChicagoReleaseMetadata,
    trips: tuple[DeclaredChicagoTrip, ...],
) -> ChicagoCompilerInputs:
    """Validate declarations and emit generic release-compiler inputs.

    ``trips`` must be the caller's pinned all-contributor universe.  The
    function binds every supplied node; it never selects only core or matched
    records.  Pass the returned inputs to
    :func:`compile_chicago_release_problem`; directly attaching the count
    constraints and calling the generic compiler is unsupported.
    """

    metadata = _canonicalize_metadata(metadata)
    tract_support = _validate_metadata(metadata)
    if not trips:
        raise ValueError("at least one declared contributing trip is required")

    node_ids = tuple(_nonblank(trip.node_id, "trip node_id") for trip in trips)
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("declared contributing trip node_ids must be distinct")
    universe = metadata.trip_universe
    if len(trips) != universe.node_count:
        raise ValueError(
            "declared trip count does not match the pinned contributor universe"
        )
    if canonical_string_set_sha256(node_ids) != universe.node_ids_sha256:
        raise ValueError(
            "declared trip node_ids do not match the pinned contributor universe"
        )

    release_rows: list[ReleaseRowSpec] = []
    row_audits: list[ChicagoRowAudit] = []
    privacy_evidence_audits: list[PrivacyEvidenceAudit] = []
    observations: set[ChicagoReleaseObservation] = set()
    all_factors: set[ChicagoCountFactor] = set()
    role_counts: Counter[str] = Counter()
    blank_cause_counts: Counter[str] = Counter()
    factor_kind_counts: Counter[str] = Counter()
    visible_count = 0

    for trip in trips:
        if trip.analysis_role not in {"core", "buffer", "context_only"}:
            raise ValueError(
                f"trip {trip.node_id!r} has unknown analysis_role "
                f"{trip.analysis_role!r}"
            )
        role_counts[trip.analysis_role] += 1
        _validate_endpoint_observation(
            PICKUP_START, trip.pickup, tract_support
        )
        _validate_endpoint_observation(
            DROPOFF_END, trip.dropoff, tract_support
        )
        endpoint_observations = {
            PICKUP_START: trip.pickup,
            DROPOFF_END: trip.dropoff,
        }
        visible_count += sum(
            value.released_tract is not None
            for value in endpoint_observations.values()
        )
        for value in endpoint_observations.values():
            if value.blank_cause is not None:
                blank_cause_counts[value.blank_cause] += 1

        if not trip.endpoint_factors_by_label:
            raise ValueError(
                f"trip {trip.node_id!r} must bind at least one substantive label"
            )
        copied_bindings: dict[
            str, dict[EndpointRole, ChicagoCountFactor]
        ] = {}
        applicable_by_label: list[tuple[EndpointRole, ...]] = []
        for label, endpoint_map in trip.endpoint_factors_by_label.items():
            label = _nonblank(
                label, f"substantive label for trip {trip.node_id!r}"
            )
            if set(endpoint_map) != set(ENDPOINTS):
                raise ValueError(
                    f"trip {trip.node_id!r}/{label!r} must bind exactly "
                    "pickup_start and dropoff_end"
                )
            copied_endpoint_map: dict[EndpointRole, ChicagoCountFactor] = {}
            applicable: list[EndpointRole] = []
            for endpoint in ENDPOINTS:
                factor = endpoint_map[endpoint]
                if not isinstance(factor, ChicagoCountFactor):
                    raise ValueError(
                        f"trip {trip.node_id!r}/{label!r}/{endpoint} factor "
                        "must be ChicagoCountFactor"
                    )
                _validate_factor(
                    factor,
                    expected_endpoint=endpoint,
                    metadata=metadata,
                    tract_support=tract_support,
                )
                released = endpoint_observations[endpoint]
                if released.released_tract is not None:
                    if factor.factor_kind != INTERNAL_TRACT:
                        raise ValueError(
                            f"visible tract at {endpoint} must bind an internal "
                            "tract factor"
                        )
                    if factor.tract_id != released.released_tract:
                        raise ValueError(
                            f"visible tract at {endpoint} does not match its "
                            "declared factor"
                        )
                elif released.blank_cause == PRIVACY_COARSENING:
                    if factor.factor_kind != INTERNAL_TRACT:
                        raise ValueError(
                            f"confirmed privacy blank at {endpoint} must bind an "
                            "internal tract factor"
                        )
                elif released.blank_cause in {
                    OUTSIDE_CITY,
                    SOURCE_MISSING,
                    OTHER_NULL,
                }:
                    if factor.factor_kind != released.blank_cause:
                        raise ValueError(
                            f"blank cause {released.blank_cause!r} at {endpoint} "
                            "must bind the matching cause factor"
                        )
                # UNKNOWN_NULL intentionally permits internal and cause-bucket
                # alternatives.  Its release implication is always TRUE.
                if factor.factor_kind == INTERNAL_TRACT:
                    applicable.append(endpoint)
                copied_endpoint_map[endpoint] = factor
                all_factors.add(factor)
                factor_kind_counts[factor.factor_kind] += 1
            if copied_endpoint_map[PICKUP_START] == copied_endpoint_map[DROPOFF_END]:
                raise ValueError(
                    f"trip {trip.node_id!r}/{label!r} aliases pickup and dropoff "
                    "factors; endpoint marginal cells must remain separate"
                )
            copied_bindings[label] = copied_endpoint_map
            applicable_by_label.append(tuple(applicable))

        support_digest = canonical_label_support_sha256(copied_bindings)
        support_authority_id, support_contract_sha256 = (
            _validate_label_support_declaration(
                trip, support_digest, metadata
            )
        )
        observation, evidence_audit = _observation_for_trip(
            trip, tuple(applicable_by_label), metadata
        )
        if evidence_audit is not None:
            privacy_evidence_audits.append(evidence_audit)
        observations.add(observation)
        frozen_bindings = _freeze_endpoint_bindings(copied_bindings)
        release_rows.append(
            ReleaseRowSpec(
                node_id=trip.node_id,
                observation=observation,
                endpoint_factors_by_label=frozen_bindings,
            )
        )
        blank_causes = tuple(
            (endpoint, value.blank_cause)
            for endpoint, value in endpoint_observations.items()
            if value.blank_cause is not None
        )
        row_audits.append(
            ChicagoRowAudit(
                node_id=trip.node_id,
                analysis_role=trip.analysis_role,
                observation=observation,
                visible_endpoints=tuple(
                    endpoint
                    for endpoint, value in endpoint_observations.items()
                    if value.released_tract is not None
                ),
                blank_causes=blank_causes,  # type: ignore[arg-type]
                label_support=tuple(copied_bindings),
                label_support_sha256=support_digest,
                support_completeness=trip.label_support.completeness,
                support_authority_id=support_authority_id,
                support_authority_contract_sha256=(
                    support_contract_sha256
                ),
                support_evidence_reference=(
                    trip.label_support.evidence_reference
                ),
                support_evidence_sha256=trip.label_support.evidence_sha256,
                distinct_label_count=len(copied_bindings),
                endpoint_factor_bindings=2 * len(copied_bindings),
            )
        )

    implications = tuple(
        _implication_for_observation(observation)
        for observation in sorted(
            observations,
            key=lambda item: (
                item.mode,
                item.applicable_endpoints,
                item.known_low_endpoints,
            ),
        )
    )
    audit_reference = json.dumps(
        {
            "dataset_snapshot_sha256": metadata.dataset_snapshot_sha256,
            "methodology_reference": metadata.methodology_reference,
            "endpoint_clarification_reference": (
                metadata.endpoint_clarification_reference
            ),
            "tract_vintage": metadata.tract_support.vintage,
            "tract_support_id": metadata.tract_support.support_id,
            "tract_support_sha256": metadata.tract_support.tract_ids_sha256,
            "trip_universe_sha256": metadata.trip_universe.node_ids_sha256,
            "partition_ids": sorted(metadata.partition_ids),
            "partition_definition": metadata.partition_definition,
            "time_bin_definition": metadata.time_bin_definition,
            "time_zone": metadata.time_zone,
            "cell_minutes": metadata.cell_minutes,
            "low_upper": metadata.low_upper,
            "high_lower": metadata.high_lower,
            "release_context": _context_payload(
                chicago_release_context(metadata)
            ),
            "label_supports": [
                {
                    "node_id": audit.node_id,
                    "bindings_sha256": audit.label_support_sha256,
                    "completeness": audit.support_completeness,
                    "authority_id": audit.support_authority_id,
                    "authority_contract_sha256": (
                        audit.support_authority_contract_sha256
                    ),
                    "evidence_reference": audit.support_evidence_reference,
                    "evidence_sha256": audit.support_evidence_sha256,
                }
                for audit in row_audits
            ],
            "privacy_evidence": [
                {
                    "node_id": audit.node_id,
                    "authority_id": audit.authority_id,
                    "authority_contract_sha256": (
                        audit.authority_contract_sha256
                    ),
                    "evidence_id": audit.evidence_id,
                    "evidence_sha256": audit.evidence_sha256,
                    "state": audit.state,
                    "known_low_endpoints": audit.known_low_endpoints,
                }
                for audit in privacy_evidence_audits
            ],
            "status": "declared-documentary-input-only",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    operator = ReleaseOperatorSpec(
        operator_id=metadata.operator_id,
        audit_reference=audit_reference,
        endpoints=ENDPOINTS,
        implications=implications,
    )

    count_constraints = tuple(
        CountConstraint(
            factor=factor,
            lower=0,
            upper=len(trips),
            low_upper=(metadata.low_upper if factor.factor_kind == INTERNAL_TRACT else None),
            high_lower=(
                metadata.high_lower if factor.factor_kind == INTERNAL_TRACT else None
            ),
        )
        for factor in sorted(
            all_factors,
            key=lambda item: (
                item.endpoint,
                item.factor_kind,
                item.time_bin_id,
                item.partition_id,
                item.tract_id or "",
            ),
        )
    )

    all_supports_verified = all(
        audit.support_completeness == "externally_verified"
        for audit in row_audits
    )
    support_scope: SupportCompleteness = (
        "externally_verified"
        if all_supports_verified
        else "analyst_declared_conditional"
    )
    limitations = [
        "The contributor-universe flag and hash verify the supplied declaration, "
        "not City-source completeness.",
        "Documentary one-way implications do not validate the City's production "
        "partitioning, null causes, DST handling, or recomputation code.",
        "Evidence hashes and authority contracts pin declarations; this adapter "
        "does not authenticate their substantive validity.",
        "No live City extraction is performed by this adapter.",
    ]
    if not all_supports_verified:
        limitations.append(
            "At least one label support is analyst-declared conditional; no "
            "complete label-support claim is licensed. Candidate-edge coverage "
            "is outside this adapter's support contract regardless of status."
        )
    else:
        limitations.append(
            "Verified label support licenses only the declared per-node label "
            "supports; candidate-edge coverage is outside this adapter's support "
            "contract."
        )
    diagnostics = ChicagoAdapterDiagnostics(
        dataset_id=metadata.dataset_id,
        dataset_snapshot_sha256=metadata.dataset_snapshot_sha256,
        declared_universe_id=universe.universe_id,
        declared_trip_count=len(trips),
        emitted_release_row_count=len(release_rows),
        input_universe_pin_verified=True,
        all_supplied_trips_bound=len(release_rows) == len(trips),
        declared_all_cell_contributors=universe.all_cell_contributors_declared,
        analysis_role_counts=tuple(sorted(role_counts.items())),
        visible_endpoint_count=visible_count,
        blank_cause_counts=tuple(sorted(blank_cause_counts.items())),
        factor_binding_kind_counts=tuple(sorted(factor_kind_counts.items())),
        distinct_factor_count=len(all_factors),
        distinct_internal_factor_count=sum(
            factor.factor_kind == INTERNAL_TRACT for factor in all_factors
        ),
        tract_vintage=metadata.tract_support.vintage,
        tract_support_id=metadata.tract_support.support_id,
        tract_support_sha256=metadata.tract_support.tract_ids_sha256,
        tract_support_size=len(metadata.tract_support.tract_ids),
        release_context=chicago_release_context(metadata),
        label_support_scope=support_scope,
        label_support_outer_claim_licensed=all_supports_verified,
        privacy_evidence_audits=tuple(privacy_evidence_audits),
        row_audits=tuple(row_audits),
        city_implementation_validated=False,
        live_extraction_performed=False,
        limitations=tuple(limitations),
    )
    contract_sha256 = _compiler_contract_sha256(
        metadata=metadata,
        operator=operator,
        rows=tuple(release_rows),
        count_constraints=count_constraints,
        diagnostics=diagnostics,
    )
    return ChicagoCompilerInputs(
        metadata=metadata,
        operator=operator,
        rows=tuple(release_rows),
        count_constraints=count_constraints,
        diagnostics=diagnostics,
        contract_sha256=contract_sha256,
    )


def _revalidate_compiler_inputs(inputs: ChicagoCompilerInputs) -> None:
    _validate_metadata(inputs.metadata)
    if inputs.operator.operator_id != inputs.metadata.operator_id:
        raise ValueError("Chicago operator_id disagrees with pinned metadata")
    if tuple(inputs.operator.endpoints) != ENDPOINTS:
        raise ValueError("Chicago operator endpoints must remain pickup/start and dropoff/end")
    if inputs.diagnostics.city_implementation_validated is not False:
        raise ValueError("adapter diagnostics cannot claim City implementation validation")
    if inputs.diagnostics.live_extraction_performed is not False:
        raise ValueError("adapter diagnostics cannot claim a live extraction")
    if inputs.diagnostics.release_context != chicago_release_context(
        inputs.metadata
    ):
        raise ValueError("diagnostic release context disagrees with metadata")
    expected_contract = _compiler_contract_sha256(
        metadata=inputs.metadata,
        operator=inputs.operator,
        rows=inputs.rows,
        count_constraints=inputs.count_constraints,
        diagnostics=inputs.diagnostics,
    )
    if _sha256(inputs.contract_sha256, "compiler-input contract SHA-256") != (
        expected_contract
    ):
        raise ValueError("Chicago compiler inputs changed after adapter validation")

    row_ids = tuple(row.node_id for row in inputs.rows)
    audits = inputs.diagnostics.row_audits
    audit_ids = tuple(audit.node_id for audit in audits)
    if row_ids != audit_ids or len(set(row_ids)) != len(row_ids):
        raise ValueError("release rows and row audits must have the same unique order")
    if len(row_ids) != inputs.metadata.trip_universe.node_count:
        raise ValueError("release rows do not cover the pinned contributor count")
    if canonical_string_set_sha256(row_ids) != (
        inputs.metadata.trip_universe.node_ids_sha256
    ):
        raise ValueError("release rows do not cover the pinned contributor IDs")

    authority_by_id = {
        authority.authority_id: authority
        for authority in inputs.metadata.privacy_evidence_authorities
    }
    support_authority_by_id = {
        authority.authority_id: authority
        for authority in inputs.metadata.support_evidence_authorities
    }
    evidence_node_ids: set[str] = set()
    row_by_id = {row.node_id: row for row in inputs.rows}
    expected_mode_by_state = {
        "paired_threshold_verified": "paired_threshold_low_disjunction",
        "known_low_endpoints": "known_low_endpoints",
        "privacy_only_no_low": "privacy_only_no_low",
    }
    for evidence in inputs.diagnostics.privacy_evidence_audits:
        if evidence.node_id in evidence_node_ids:
            raise ValueError("privacy evidence audits must have unique node IDs")
        evidence_node_ids.add(evidence.node_id)
        authority = authority_by_id.get(evidence.authority_id)
        if authority is None:
            raise ValueError("privacy evidence audit lost its authority contract")
        if authority.contract_sha256 != evidence.authority_contract_sha256:
            raise ValueError("privacy evidence authority contract digest drifted")
        if evidence.state not in authority.permitted_states:
            raise ValueError("privacy evidence state is no longer authority-permitted")
        row = row_by_id.get(evidence.node_id)
        if row is None or not isinstance(
            row.observation, ChicagoReleaseObservation
        ):
            raise ValueError("privacy evidence audit references no Chicago row")
        if row.observation.mode != expected_mode_by_state[evidence.state]:
            raise ValueError("privacy evidence state disagrees with row implication")
        if (
            evidence.state == "known_low_endpoints"
            and row.observation.known_low_endpoints
            != evidence.known_low_endpoints
        ):
            raise ValueError("known LOW endpoints drifted from evidence audit")

    all_factors: set[ChicagoCountFactor] = set()
    for row, audit in zip(inputs.rows, audits):
        labels = tuple(row.endpoint_factors_by_label)
        if labels != audit.label_support:
            raise ValueError(
                f"release-row support for {row.node_id!r} disagrees with its audit"
            )
        digest = canonical_label_support_sha256(
            row.endpoint_factors_by_label  # type: ignore[arg-type]
        )
        if digest != audit.label_support_sha256:
            raise ValueError(
                f"release-row support for {row.node_id!r} fails digest replay"
            )
        if audit.support_completeness == "externally_verified":
            authority = support_authority_by_id.get(
                audit.support_authority_id
            )
            if authority is None:
                raise ValueError(
                    "support audit lost its independent authority contract"
                )
            if authority.contract_sha256 != (
                audit.support_authority_contract_sha256
            ):
                raise ValueError("support authority contract digest drifted")
            _nonblank(
                audit.support_evidence_reference,
                f"support evidence_reference for {row.node_id!r}",
            )
            _sha256(
                audit.support_evidence_sha256,
                f"support evidence SHA-256 for {row.node_id!r}",
            )
        elif audit.support_completeness == "analyst_declared_conditional":
            if (
                audit.support_authority_id is not None
                or audit.support_authority_contract_sha256 is not None
                or audit.support_evidence_reference is not None
                or audit.support_evidence_sha256 is not None
            ):
                raise ValueError(
                    "conditional support audit cannot carry verification evidence"
                )
        else:
            raise ValueError("row audit has unknown support completeness")
        for endpoint_map in row.endpoint_factors_by_label.values():
            if set(endpoint_map) != set(ENDPOINTS):
                raise ValueError("release row lost an endpoint binding")
            for endpoint in ENDPOINTS:
                factor = endpoint_map[endpoint]
                _validate_factor(
                    factor,
                    expected_endpoint=endpoint,
                    metadata=inputs.metadata,
                    tract_support=set(inputs.metadata.tract_support.tract_ids),
                )
                all_factors.add(factor)

    expected_constraints = tuple(
        CountConstraint(
            factor=factor,
            lower=0,
            upper=len(inputs.rows),
            low_upper=(
                inputs.metadata.low_upper
                if factor.factor_kind == INTERNAL_TRACT
                else None
            ),
            high_lower=(
                inputs.metadata.high_lower
                if factor.factor_kind == INTERNAL_TRACT
                else None
            ),
        )
        for factor in sorted(
            all_factors,
            key=lambda item: (
                item.endpoint,
                item.factor_kind,
                item.time_bin_id,
                item.partition_id,
                item.tract_id or "",
            ),
        )
    )
    if inputs.count_constraints != expected_constraints:
        raise ValueError("adapter Chicago count constraints do not replay exactly")

    expected_implications = tuple(
        _implication_for_observation(observation)
        for observation in sorted(
            {row.observation for row in inputs.rows},
            key=lambda item: (
                item.mode,
                item.applicable_endpoints,
                item.known_low_endpoints,
            ),
        )
    )
    if tuple(inputs.operator.implications) != expected_implications:
        raise ValueError("Chicago operator implications do not replay from rows")
    all_supports_verified = all(
        audit.support_completeness == "externally_verified"
        for audit in audits
    )
    expected_scope = (
        "externally_verified"
        if all_supports_verified
        else "analyst_declared_conditional"
    )
    if (
        inputs.diagnostics.label_support_scope != expected_scope
        or inputs.diagnostics.label_support_outer_claim_licensed
        is not all_supports_verified
    ):
        raise ValueError("label-support scope diagnostics are not conservative")


def _freeze_nested_map(
    raw: Mapping[Hashable, Mapping[Hashable, object]] | None,
) -> Mapping[Hashable, Mapping[Hashable, object]] | None:
    if raw is None:
        return None
    return MappingProxyType(
        {
            label: MappingProxyType(dict(factor_map))
            for label, factor_map in raw.items()
        }
    )


def _freeze_source_node(node: NodeSpec) -> NodeSpec:
    return NodeSpec(
        node_id=node.node_id,
        role=node.role,
        label_support=tuple(node.label_support),
        factor_contributions=_freeze_nested_map(
            node.factor_contributions  # type: ignore[arg-type]
        ),
        factor_requirements=_freeze_nested_map(
            node.factor_requirements  # type: ignore[arg-type]
        ),
        label_query=(
            None
            if node.label_query is None
            else MappingProxyType(dict(node.label_query))
        ),
    )


def _freeze_source_edge(edge: EdgeSpec) -> EdgeSpec:
    return EdgeSpec(
        edge_id=edge.edge_id,
        u=edge.u,
        v=edge.v,
        score=edge.score,
        query=edge.query,
        omitted=edge.omitted,
        allowed_label_pairs=(
            None
            if edge.allowed_label_pairs is None
            else tuple(edge.allowed_label_pairs)
        ),
        score_by_label_pair=(
            None
            if edge.score_by_label_pair is None
            else MappingProxyType(dict(edge.score_by_label_pair))
        ),
        query_by_label_pair=(
            None
            if edge.query_by_label_pair is None
            else MappingProxyType(dict(edge.query_by_label_pair))
        ),
    )


def compile_chicago_release_problem(
    source_problem: ExactPathProblem,
    *,
    inputs: ChicagoCompilerInputs,
    forget_order: Sequence[str],
    allowed_source_factors: Sequence[Hashable] = (),
) -> ChicagoSanitizedHandoff:
    """Sanitize the source problem and perform the supported compiler handoff.

    The source node set, roles, and ordered label supports must exactly replay
    the adapter declaration.  Source nodes and constraints may carry unrelated
    factors only when they appear in ``allowed_source_factors``, and never a
    ``ChicagoCountFactor``: only this adapter may add Chicago contributions,
    requirements, or constraints.
    """

    _revalidate_compiler_inputs(inputs)
    allowed_factors = tuple(allowed_source_factors)
    try:
        allowed_factor_set = set(allowed_factors)
    except TypeError as exc:
        raise ValueError(
            "allowed_source_factors must be distinct and hashable"
        ) from exc
    if len(allowed_factor_set) != len(allowed_factors):
        raise ValueError("allowed_source_factors must be distinct and hashable")
    if any(isinstance(factor, ChicagoCountFactor) for factor in allowed_factors):
        raise ValueError("allowed_source_factors cannot authorize Chicago factors")
    source_nodes: dict[str, NodeSpec] = {}
    for node in source_problem.nodes:
        if node.node_id in source_nodes:
            raise ValueError(f"duplicate source node_id {node.node_id!r}")
        source_nodes[node.node_id] = node
    audit_by_node = {
        audit.node_id: audit for audit in inputs.diagnostics.row_audits
    }
    if set(source_nodes) != set(audit_by_node):
        missing = sorted(set(audit_by_node) - set(source_nodes))
        rogue = sorted(set(source_nodes) - set(audit_by_node))
        raise ValueError(
            "source node set must equal the declared contributor universe; "
            f"missing={missing!r}, rogue={rogue!r}"
        )

    for node_id, node in source_nodes.items():
        audit = audit_by_node[node_id]
        if node.role != audit.analysis_role:
            raise ValueError(
                f"source role for {node_id!r} disagrees with declared role"
            )
        if isinstance(node.label_support, (str, bytes)):
            raise ValueError(f"source label support for {node_id!r} must be a sequence")
        if tuple(node.label_support) != audit.label_support:
            raise ValueError(
                f"source label support for {node_id!r} must exactly match the "
                "declared ordered support"
            )
        for map_name, raw in (
            ("factor_contributions", node.factor_contributions),
            ("factor_requirements", node.factor_requirements),
        ):
            for factor_map in (raw or {}).values():
                for factor in factor_map:
                    if isinstance(factor, ChicagoCountFactor):
                        raise ValueError(
                            f"source node {node_id!r} preloads a Chicago factor in "
                            f"{map_name}; only the adapter may add it"
                        )
                    if factor not in allowed_factor_set:
                        raise ValueError(
                            f"source node {node_id!r} uses undeclared source factor "
                            f"{factor!r} in {map_name}"
                        )

    for constraint in source_problem.count_constraints:
        if isinstance(constraint.factor, ChicagoCountFactor):
            raise ValueError(
                "source problem preloads a Chicago count constraint; only the "
                "adapter may add Chicago constraints"
            )
        if constraint.factor not in allowed_factor_set:
            raise ValueError(
                f"source problem uses undeclared count factor "
                f"{constraint.factor!r}"
            )

    sanitized = ExactPathProblem(
        nodes=tuple(_freeze_source_node(node) for node in source_problem.nodes),
        edges=tuple(_freeze_source_edge(edge) for edge in source_problem.edges),
        count_constraints=(
            tuple(source_problem.count_constraints) + inputs.count_constraints
        ),
    )
    compilation = compile_release_operator(
        sanitized,
        rows=inputs.rows,
        operator=inputs.operator,
        forget_order=tuple(forget_order),
    )
    validate_release_compilation(compilation)
    frozen_compiled_problem = ExactPathProblem(
        nodes=tuple(
            _freeze_source_node(node) for node in compilation.problem.nodes
        ),
        edges=tuple(
            _freeze_source_edge(edge) for edge in compilation.problem.edges
        ),
        count_constraints=tuple(compilation.problem.count_constraints),
    )
    compilation = replace(compilation, problem=frozen_compiled_problem)
    validate_release_compilation(compilation)
    audit = ChicagoHandoffAudit(
        source_node_count=len(source_nodes),
        exact_node_set_verified=True,
        exact_roles_verified=True,
        exact_label_supports_verified=True,
        source_chicago_factor_maps_absent=True,
        source_chicago_constraints_absent=True,
        declared_non_chicago_factor_count=len(allowed_factors),
        adapter_constraint_count=len(inputs.count_constraints),
        preserved_non_chicago_constraint_count=len(
            source_problem.count_constraints
        ),
        compiler_input_contract_sha256=inputs.contract_sha256,
    )
    return ChicagoSanitizedHandoff(
        source_problem=sanitized,
        compilation=compilation,
        audit=audit,
    )


__all__ = [
    "BLANK_CAUSES",
    "DATASET_ID",
    "DROPOFF_END",
    "ENDPOINTS",
    "INTERNAL_TRACT",
    "OTHER_NULL",
    "OUTSIDE_CITY",
    "PICKUP_START",
    "PRIVACY_COARSENING",
    "SOURCE_MISSING",
    "UNKNOWN_NULL",
    "ChicagoAdapterDiagnostics",
    "ChicagoCompilerInputs",
    "ChicagoCountFactor",
    "ChicagoHandoffAudit",
    "ChicagoReleaseContext",
    "ChicagoReleaseMetadata",
    "ChicagoReleaseObservation",
    "ChicagoRowAudit",
    "ChicagoSanitizedHandoff",
    "DeclaredChicagoTrip",
    "DeclaredTripUniversePin",
    "EndpointReleaseObservation",
    "LabelSupportDeclaration",
    "PrivacyCauseEvidencePin",
    "PrivacyEvidenceAudit",
    "PrivacyEvidenceAuthorityContract",
    "SupportEvidenceAuthorityContract",
    "TractSupportPin",
    "build_chicago_compiler_inputs",
    "canonical_label_support_sha256",
    "canonical_string_set_sha256",
    "chicago_release_context",
    "compile_chicago_release_problem",
]
