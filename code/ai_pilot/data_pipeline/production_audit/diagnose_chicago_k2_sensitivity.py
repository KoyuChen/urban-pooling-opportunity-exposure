#!/usr/bin/env python3
"""Capture redacted sensitivity diagnostics before a Chicago audit can abort.

This is a diagnostic wrapper, not a frozen evidence producer. It preserves the
underlying indexed-count acquisition, graph, query and solver arguments while
recording the monotonicity-audit input/output without row IDs or assignments.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
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
        result = BASE_AUDIT(rows, *args, **kwargs)
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
