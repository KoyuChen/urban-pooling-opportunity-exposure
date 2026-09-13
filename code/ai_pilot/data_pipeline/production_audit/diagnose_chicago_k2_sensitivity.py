#!/usr/bin/env python3
"""Capture redacted sensitivity diagnostics before a Chicago audit can abort.

This is a diagnostic wrapper, not a frozen evidence producer. It preserves the
underlying indexed-count acquisition, graph, query and solver arguments while
recording the monotonicity-audit input/output without row IDs or assignments.
"""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import live_chicago_k2_frontier as frontier
import live_chicago_k2_frontier_indexed_count as indexed


BASE_AUDIT = frontier.monotonicity_audit
SAFE_FIELDS = (
    "curve_type", "parameter_label", "parameter_value", "query", "lower", "upper",
    "width", "endpoint_pair_certification", "lower_status", "upper_status",
    "lower_mip_gap", "upper_mip_gap", "endpoint_source",
    "edges_with_missing_query_values",
)


def _mip_gap_allowance(value: float, raw_gap: Any) -> float:
    """Return a conservative objective allowance for a relative MIP gap."""

    try:
        gap = float(raw_gap)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(gap) or gap <= 0.0 or gap >= 1.0:
        return 0.0
    return abs(value) * gap / (1.0 - gap)


def gap_aware_audit(
    rows: Sequence[Mapping[str, Any]], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    """Amend only reversals smaller than the current incumbent's MIP allowance.

    The frozen producer compared replayed incumbent values at an absolute
    ``1e-7`` tolerance even though HiGHS status 0 can reflect its relative MIP
    stopping gap.  This wrapper never upgrades an affected chain to PASS: an
    explained reversal becomes numerically indeterminate, while a reversal
    outside the reported gap remains a hard violation.
    """

    result = copy.deepcopy(BASE_AUDIT(rows, *args, **kwargs))
    indexed_rows: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("curve_type")),
            str(row.get("query")),
            str(row.get("parameter_label")),
        )
        indexed_rows.setdefault(key, []).append(row)

    remaining: list[dict[str, Any]] = []
    indeterminate: list[dict[str, Any]] = []
    for violation in result.get("violations", []):
        key = (
            str(violation.get("curve_type")),
            str(violation.get("query")),
            str(violation.get("parameter")),
        )
        candidates = indexed_rows.get(key, [])
        if len(candidates) != 1:
            remaining.append(violation)
            continue
        row = candidates[0]
        direction = violation.get("direction")
        if direction == "upper_decreased":
            observed = float(violation["previous"]) - float(violation["current"])
            allowance = _mip_gap_allowance(
                float(violation["current"]), row.get("upper_mip_gap")
            )
        elif direction == "lower_increased":
            observed = float(violation["current"]) - float(violation["previous"])
            allowance = _mip_gap_allowance(
                float(violation["current"]), row.get("lower_mip_gap")
            )
        elif direction == "lower_exceeds_upper":
            observed = float(violation["lower"]) - float(violation["upper"])
            allowance = _mip_gap_allowance(
                float(violation["lower"]), row.get("lower_mip_gap")
            ) + _mip_gap_allowance(
                float(violation["upper"]), row.get("upper_mip_gap")
            )
        else:
            remaining.append(violation)
            continue
        if observed > allowance + 1e-7:
            remaining.append(violation)
            continue
        indeterminate.append(
            {
                **violation,
                "observed_difference": observed,
                "mip_gap_objective_allowance": allowance,
            }
        )
        result["certification_failures"].append(
            {
                "curve_type": key[0],
                "query": key[1],
                "parameter": violation.get("parameter"),
                "reason": "monotonicity_indeterminate_within_mip_gap",
                "direction": direction,
            }
        )
        for chain in result["chain_audits"]:
            if chain["curve_type"] == key[0] and chain["query"] == key[1]:
                chain["violation_count"] -= 1
                chain["certification_failure_count"] += 1
                chain["status"] = "FAIL"
                break

    result["violations"] = remaining
    result["violation_count"] = len(remaining)
    result["certification_failure_count"] = len(result["certification_failures"])
    result["gap_indeterminate_comparison_count"] = len(indeterminate)
    result["gap_indeterminate_comparisons"] = indeterminate
    passing = sum(chain["status"] == "PASS" for chain in result["chain_audits"])
    result["fully_certified_monotone_chain_count"] = passing
    for family in result["query_family_audits"]:
        family_chains = [
            chain for chain in result["chain_audits"]
            if chain["query"] == family["query"]
        ]
        family["status"] = (
            "PASS" if family_chains and all(
                chain["status"] == "PASS" for chain in family_chains
            ) else "FAIL"
        )
    result["fully_certified_monotone_query_family_count"] = sum(
        family["status"] == "PASS" for family in result["query_family_audits"]
    )
    if remaining or result["malformed_rows"]:
        result["status"] = "FAIL"
    elif result["chain_count"] and passing == result["chain_count"]:
        result["status"] = "PASS"
    elif passing:
        result["status"] = "PARTIAL"
    else:
        result["status"] = "FAIL"
    return result


def redacted_diagnostic(rows: Sequence[Mapping[str, Any]], audit: Mapping[str, Any]) -> dict:
    safe_rows = [{key: row.get(key) for key in SAFE_FIELDS} for row in rows]
    serialized = json.dumps(safe_rows, sort_keys=True, separators=(",", ":"))
    return {
        "diagnostic_version": "chicago-k2-sensitivity-diagnostic/v1",
        "scope": "Diagnostic rerun only; not canonical evidence and no raw row IDs or matchings.",
        "sensitivity_row_count": len(safe_rows),
        "sensitivity_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
        "lower_status_counts": dict(Counter(str(row.get("lower_status")) for row in rows)),
        "upper_status_counts": dict(Counter(str(row.get("upper_status")) for row in rows)),
        "audit": dict(audit),
        "rows": safe_rows,
    }


def output_directory(argv: list[str]) -> Path:
    try:
        return Path(argv[argv.index("--output-dir") + 1])
    except (ValueError, IndexError) as error:
        raise SystemExit("diagnostic wrapper requires --output-dir") from error


def main() -> int:
    output = output_directory(sys.argv[1:])
    output.mkdir(parents=True, exist_ok=True)
    calls = 0

    def capture(rows, *args, **kwargs):
        nonlocal calls
        calls += 1
        result = gap_aware_audit(rows, *args, **kwargs)
        path = output / f"sensitivity_diagnostic_{calls:02d}.json"
        path.write_text(
            json.dumps(redacted_diagnostic(rows, result), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result

    frontier.monotonicity_audit = capture
    return indexed.main()


if __name__ == "__main__":
    raise SystemExit(main())
