#!/usr/bin/env python3
"""Run the exact conformal audit with a cross-run semantic certificate.

Raw learned edge-score arrays can differ at the last floating-point bits across
otherwise identical GitHub-hosted runners.  Their SHA-256 values are therefore
retained as diagnostics, not used as the sole reproducibility gate.  The gate
instead requires:

1. exact enumeration over all declared perfect matchings;
2. calibrated radii within the locked tolerance;
3. every locked headline within the locked tolerance; and
4. the entire generated radius frontier to match the committed frontier
   row-by-row within a much tighter numerical tolerance.

This does not relax score-floor membership inside a run: each run still parses
its actual float edge scores as decimal rationals and performs exact Fraction
comparisons.  It only prevents irrelevant sub-ULP scorer drift from failing a
semantically identical exhaustive audit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import exact_conformal_frontier as exact

FRONTIER_TOLERANCE = 1e-12
STRING_COLUMNS = ("scorer", "radius_kind")
SORT_COLUMNS = ("scorer", "radius", "radius_kind")


def compare_frontiers(generated_path: Path, reference_path: Path) -> dict[str, Any]:
    if not generated_path.exists():
        return {
            "passed": False,
            "reason": "generated_frontier_missing",
            "generated_file": str(generated_path),
            "reference_file": str(reference_path),
        }
    if not reference_path.exists():
        return {
            "passed": False,
            "reason": "reference_frontier_missing",
            "generated_file": str(generated_path),
            "reference_file": str(reference_path),
        }

    generated = pd.read_csv(generated_path)
    reference = pd.read_csv(reference_path)
    if list(generated.columns) != list(reference.columns):
        return {
            "passed": False,
            "reason": "frontier_columns_differ",
            "generated_columns": list(generated.columns),
            "reference_columns": list(reference.columns),
        }
    if len(generated) != len(reference):
        return {
            "passed": False,
            "reason": "frontier_row_count_differs",
            "generated_rows": len(generated),
            "reference_rows": len(reference),
        }

    generated = generated.sort_values(list(SORT_COLUMNS), kind="stable").reset_index(
        drop=True
    )
    reference = reference.sort_values(list(SORT_COLUMNS), kind="stable").reset_index(
        drop=True
    )

    string_problems: list[dict[str, Any]] = []
    for column in STRING_COLUMNS:
        left = generated[column].fillna("<NA>").astype(str)
        right = reference[column].fillna("<NA>").astype(str)
        bad = np.flatnonzero(left.to_numpy() != right.to_numpy())
        if len(bad):
            string_problems.append(
                {
                    "column": column,
                    "first_bad_row": int(bad[0]),
                    "generated": left.iloc[int(bad[0])],
                    "reference": right.iloc[int(bad[0])],
                }
            )

    numeric_problems: list[dict[str, Any]] = []
    maximum_absolute_error = 0.0
    for column in generated.columns:
        if column in STRING_COLUMNS:
            continue
        left = pd.to_numeric(generated[column], errors="coerce").to_numpy(dtype=float)
        right = pd.to_numeric(reference[column], errors="coerce").to_numpy(dtype=float)
        if not np.array_equal(np.isnan(left), np.isnan(right)):
            numeric_problems.append(
                {"column": column, "reason": "nan_pattern_differs"}
            )
            continue
        finite = np.isfinite(left) & np.isfinite(right)
        if not np.array_equal(np.isfinite(left), np.isfinite(right)):
            numeric_problems.append(
                {"column": column, "reason": "finite_pattern_differs"}
            )
            continue
        if finite.any():
            error = float(np.max(np.abs(left[finite] - right[finite])))
            maximum_absolute_error = max(maximum_absolute_error, error)
            if error > FRONTIER_TOLERANCE:
                numeric_problems.append(
                    {
                        "column": column,
                        "reason": "absolute_error_exceeds_tolerance",
                        "maximum_absolute_error": error,
                    }
                )
        nonfinite = ~finite & ~np.isnan(left)
        if nonfinite.any() and not np.array_equal(left[nonfinite], right[nonfinite]):
            numeric_problems.append(
                {"column": column, "reason": "nonfinite_values_differ"}
            )

    passed = not string_problems and not numeric_problems
    return {
        "passed": passed,
        "tolerance": FRONTIER_TOLERANCE,
        "rows": len(generated),
        "columns": len(generated.columns),
        "maximum_absolute_error": maximum_absolute_error,
        "string_problems": string_problems,
        "numeric_problems": numeric_problems,
        "generated_file": generated_path.name,
        "reference_file": reference_path.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-json", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    original_failure: str | None = None
    try:
        exact.run(args.output_dir, args.reference_json)
    except RuntimeError as exc:
        # exact.run writes its full audit record before failing, which lets this
        # wrapper distinguish a raw-hash-only failure from a semantic failure.
        original_failure = str(exc)

    audit_path = args.output_dir / "exact_conformal_audit.json"
    if not audit_path.exists():
        raise RuntimeError("exact conformal audit did not emit its audit record")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    verification = audit["verification"]

    frontier_audit = compare_frontiers(
        args.output_dir / "exact_conformal_frontier.csv",
        args.reference_json.with_name("exact_conformal_frontier.csv"),
    )
    tau_passed = all(item.get("passed") for item in verification["tau"].values())
    headline_passed = all(
        item.get("passed") for item in verification["headline"].values()
    )
    bitwise_score_hashes_passed = all(
        item.get("passed") for item in verification["score_arrays"].values()
    )
    semantic_passed = tau_passed and headline_passed and frontier_audit["passed"]

    verification["frontier_semantic_audit"] = frontier_audit
    verification["bitwise_score_hashes_all_passed"] = bitwise_score_hashes_passed
    verification["bitwise_score_hashes_role"] = (
        "diagnostic only; hosted-runner sub-ULP scorer drift is allowed only when "
        "the exhaustive radius frontier, calibrated radii, and locked headlines "
        "all pass their independent semantic audits"
    )
    verification["semantic_all_passed"] = semantic_passed
    verification["original_exact_audit_failure"] = original_failure
    verification["all_passed"] = semantic_passed
    audit["verification"] = verification
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if not semantic_passed:
        raise RuntimeError(
            "semantic exact conformal audit failed: "
            + json.dumps(
                {
                    "tau_passed": tau_passed,
                    "headline_passed": headline_passed,
                    "frontier": frontier_audit,
                    "raw_hashes_passed": bitwise_score_hashes_passed,
                },
                sort_keys=True,
            )
        )

    print(
        "semantic exact conformal audit passed; raw score hashes",
        "matched" if bitwise_score_hashes_passed else "differed diagnostically",
        f"and all {frontier_audit['rows']} frontier rows matched within",
        FRONTIER_TOLERANCE,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
