"""Production audits for hidden-partner Chicago K=2 cohorts.

The package emits aggregate audit evidence only.  It deliberately does not
serialize public trip identifiers or claim that a candidate graph contains the
unobserved partner relation.
"""

from .chicago_k2_audit import (
    AuditArtifacts,
    ContractError,
    audit_rows,
    canonical_rows_sha256,
    load_contract,
    read_csv_rows,
    validate_report,
)

__all__ = [
    "AuditArtifacts",
    "ContractError",
    "audit_rows",
    "canonical_rows_sha256",
    "load_contract",
    "read_csv_rows",
    "validate_report",
]
