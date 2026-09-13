#!/usr/bin/env python3
"""Build a sealed cross-version Chicago checkpoint for the index-93 audit fix.

The source checkpoint is never mutated.  The original failure is retained in
history, the amended diagnostic result is pinned with explicit provenance, and
the ordinary frozen runner hashes remain unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

import chicago_k2_followup as followup
import run_chicago_k2_fixed_panel as panel


INDEX = 93
EXPECTED_START = "2026-02-27T08:00:00"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_amended_result(directory: Path) -> dict[str, Any]:
    report_path = directory / "report.json"
    sensitivity_path = directory / "candidate_support_sensitivity.csv"
    diagnostics = sorted(directory.glob("sensitivity_diagnostic_*.json"))
    if not report_path.is_file() or not sensitivity_path.is_file() or len(diagnostics) < 2:
        raise ValueError("amended artifact lacks the full report, CSV or two audits")
    report = read_json(report_path)
    if report.get("extraction", {}).get("predeclared_core_start_local") != EXPECTED_START:
        raise ValueError("amended artifact changed the declared window")
    if report.get("cohort", {}).get(
        "public_temporal_candidate_universe_closure_status"
    ) != "PASS":
        raise ValueError("amended artifact lacks candidate-universe closure")
    audit = report.get("monotonicity_audit", {})
    if audit.get("status") != "PARTIAL" or audit.get("violation_count") != 0:
        raise ValueError("amended result must be partial with no hard reversal")
    if int(audit.get("gap_indeterminate_comparison_count", 0)) < 1:
        raise ValueError("amended result lacks the declared gap-indeterminate comparison")
    for item in audit.get("gap_indeterminate_comparisons", []):
        if float(item["observed_difference"]) > float(
            item["mip_gap_objective_allowance"]
        ) + 1e-7:
            raise ValueError("amendment excused a reversal outside the MIP-gap allowance")
    raw_hash = str(report.get("extraction", {}).get("raw_rows_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", raw_hash):
        raise ValueError("amended result lacks a raw-row hash")
    summary = panel.summarize_window(
        index=INDEX,
        start=panel.expand_windows(panel.load_protocol(followup.PROTOCOL))[INDEX],
        directory=directory,
    )
    if summary.get("status") != "COMPLETED":
        raise ValueError("amended artifact is not a complete window record")
    return {"report": report, "summary": summary, "diagnostics": diagnostics}


def apply(
    source: Path,
    amended: Path,
    output: Path,
    *,
    source_run: str,
    artifact_digest: str,
    commit_sha: str,
) -> dict[str, Any]:
    checkpoint = followup.verify(source)
    if output.exists():
        raise ValueError("output directory already exists")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest):
        raise ValueError("artifact digest must be a sha256 digest")
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ValueError("amendment commit must be a full Git SHA")
    validated = validate_amended_result(amended)
    protocol = panel.load_protocol(followup.PROTOCOL)
    windows = panel.expand_windows(protocol)
    slug = panel.window_slug(INDEX, windows[INDEX])
    original = source / slug
    if panel.summarize_window(
        index=INDEX, start=windows[INDEX], directory=original
    ).get("status") != "EXECUTION_FAILED":
        raise ValueError("source checkpoint no longer contains the declared failure")

    shutil.copytree(source, output)
    target = output / slug
    history = output / "history" / slug / "gap_amendment_original"
    history.parent.mkdir(parents=True, exist_ok=True)
    target.rename(history)
    shutil.copytree(amended, target)
    record = {
        "amendment_version": "chicago-k2-gap-aware-audit/v1",
        "window_index": INDEX,
        "core_start_local": EXPECTED_START,
        "source_checkpoint_sha256": panel.sha256_file(source / followup.CHECKPOINT),
        "source_run": source_run,
        "source_artifact_digest": artifact_digest,
        "amendment_commit": commit_sha,
        "original_failure_sha256": panel.sha256_file(history / "failure.json"),
        "amended_report_sha256": panel.sha256_file(target / "report.json"),
        "amended_sensitivity_sha256": panel.sha256_file(
            target / "candidate_support_sensitivity.csv"
        ),
        "raw_rows_sha256": validated["report"]["extraction"]["raw_rows_sha256"],
        "rule": (
            "A reversal no larger than the current incumbent's conservative "
            "reported MIP-gap objective allowance is indeterminate, never PASS; "
            "a larger reversal remains FAIL."
        ),
        "input_identity_limitation": (
            "The original abort emitted no raw-row hash, so identical inputs cannot "
            "be proven; the amended acquisition retains the declared timestamp and "
            "records its own raw-row hash."
        ),
    }
    followup.write_json(target / "AMENDMENT.json", record)
    observations = followup.read_json(output / followup.OBSERVATIONS)
    observations.append(
        {
            "window_index": INDEX,
            "status": "COMPLETED_BY_DECLARED_AUDIT_AMENDMENT",
            "source_run": source_run,
            "artifact_digest": artifact_digest,
            "commit": commit_sha,
        }
    )
    followup.write_json(output / followup.OBSERVATIONS, observations)
    followup.seal(
        output,
        [
            *checkpoint.get("provenance", []),
            {
                "event": "GAP_AWARE_AUDIT_AMENDMENT",
                "window_index": INDEX,
                "source_run": source_run,
                "artifact_digest": artifact_digest,
                "commit": commit_sha,
            },
        ],
    )
    aggregate = followup.aggregate(output)
    if aggregate["gate_status"] != "PASS_EXECUTION":
        raise ValueError("amended checkpoint did not close the execution ledger")
    followup.verify(output)
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkpoint", type=Path, required=True)
    parser.add_argument("--amended-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    report = apply(
        args.source_checkpoint,
        args.amended_artifact,
        args.output_dir,
        source_run=args.source_run,
        artifact_digest=args.artifact_digest,
        commit_sha=args.commit,
    )
    print(json.dumps({key: value for key, value in report.items() if key != "windows"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
