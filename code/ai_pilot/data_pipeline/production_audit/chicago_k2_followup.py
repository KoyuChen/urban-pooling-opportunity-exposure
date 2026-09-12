#!/usr/bin/env python3
"""Stage and audit the frozen 96-window Chicago K=2 follow-up.

The controller distinguishes windows that have not been started from failed,
scientifically ineligible and completed windows.  Batches are consecutive and
may advance only after every earlier window has a terminal scientific record.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import shutil
from pathlib import Path
from typing import Any

import resume_chicago_k2_fixed_panel as resume
import run_chicago_k2_fixed_panel as panel


PROTOCOL = panel.HERE / "CHICAGO_K2_FOLLOWUP_PROTOCOL.json"
OBSERVATIONS = "attempt_observations.json"
CHECKPOINT = "checkpoint.json"
REUSABLE = {"COMPLETED", "INELIGIBLE_FIXED_CORE", "INELIGIBLE_RESOURCE_CAP"}
RUNNER_FILES = (
    "run_chicago_k2_fixed_panel.py",
    "live_chicago_k2_frontier.py",
    "live_chicago_k2_frontier_partitioned.py",
    "live_chicago_k2_frontier_boundary.py",
    "live_chicago_k2_frontier_indexed_count.py",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def runner_hashes() -> dict[str, str]:
    return {name: panel.sha256_file(panel.HERE / name) for name in RUNNER_FILES}


def evidence_files(root: Path) -> dict[str, str]:
    files = resume.evidence_files(root)
    observations = root / OBSERVATIONS
    if not observations.exists() or observations.is_symlink():
        raise ValueError("checkpoint lacks an ordinary attempt-observation ledger")
    files[OBSERVATIONS] = panel.sha256_file(observations)
    return files


def verify_runner_pins(protocol: dict[str, Any]) -> None:
    declared = protocol.get("runner_sha256")
    if declared != runner_hashes():
        raise ValueError("follow-up runner files differ from the frozen declaration")


def seal(root: Path, provenance: list[dict[str, Any]]) -> dict[str, Any]:
    checkpoint = {
        "checkpoint_version": "chicago-k2-followup-checkpoint/v1",
        "protocol_sha256": panel.sha256_file(PROTOCOL),
        "runner_sha256": runner_hashes(),
        "files": evidence_files(root),
        "provenance": provenance,
    }
    write_json(root / CHECKPOINT, checkpoint)
    return checkpoint


def verify(root: Path) -> dict[str, Any]:
    checkpoint = read_json(root / CHECKPOINT)
    protocol = panel.load_protocol(PROTOCOL)
    verify_runner_pins(protocol)
    if checkpoint.get("checkpoint_version") != "chicago-k2-followup-checkpoint/v1":
        raise ValueError("unsupported follow-up checkpoint")
    if checkpoint.get("protocol_sha256") != panel.sha256_file(PROTOCOL):
        raise ValueError("follow-up checkpoint uses a different protocol")
    if checkpoint.get("runner_sha256") != runner_hashes():
        raise ValueError("follow-up checkpoint uses different runner files")
    if checkpoint.get("files") != evidence_files(root):
        raise ValueError("follow-up evidence is missing, changed or unpinned")
    return checkpoint


def initialize(root: Path) -> dict[str, Any]:
    if root.exists() and any(root.iterdir()):
        raise ValueError("initial follow-up checkpoint directory is not empty")
    root.mkdir(parents=True, exist_ok=True)
    protocol = panel.load_protocol(PROTOCOL)
    verify_runner_pins(protocol)
    if len(panel.expand_windows(protocol)) != 96:
        raise ValueError("follow-up calendar is not the declared 96-window calendar")
    write_json(root / OBSERVATIONS, [])
    return seal(root, [{"event": "INITIALIZED_BEFORE_LIVE_FOLLOWUP"}])


def observations_by_index(root: Path) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for item in read_json(root / OBSERVATIONS):
        index = int(item["window_index"])
        grouped.setdefault(index, []).append(item)
    return grouped


def summarize(root: Path, index: int, start: Any) -> dict[str, Any]:
    directory = root / panel.window_slug(index, start)
    if directory.exists():
        return panel.summarize_window(index=index, start=start, directory=directory)
    observed = observations_by_index(root).get(index, [])
    if observed:
        return {
            "window_index": index,
            "core_start_local": start.isoformat(),
            "status": observed[-1]["status"],
            "attempt_count": len(observed),
        }
    return {
        "window_index": index,
        "core_start_local": start.isoformat(),
        "status": "UNSTARTED",
    }


def is_retryable(row: dict[str, Any]) -> bool:
    if row["status"] == "ATTEMPTED_NO_ARTIFACT":
        return True
    return (
        row["status"] == "EXECUTION_FAILED"
        and row.get("failure_type") == "LiveDataError"
        and (
            "request failed" in str(row.get("failure_message", ""))
            or "both Socrata APIs failed" in str(row.get("failure_message", ""))
        )
    )


def plan(root: Path, batch_index: int) -> dict[str, Any]:
    verify(root)
    protocol = panel.load_protocol(PROTOCOL)
    windows = panel.expand_windows(protocol)
    batch_count = int(protocol["execution_plan"]["batch_count"])
    batch_size = int(protocol["execution_plan"]["batch_size"])
    if not 0 <= batch_index < batch_count:
        raise ValueError("batch index is outside the frozen execution plan")
    prior = [summarize(root, i, windows[i]) for i in range(batch_index * batch_size)]
    if any(row["status"] not in REUSABLE for row in prior):
        raise ValueError("an earlier batch is not scientifically terminal")
    selected, reused = [], []
    for index in range(batch_index * batch_size, (batch_index + 1) * batch_size):
        row = summarize(root, index, windows[index])
        item = {"index": index, "slug": panel.window_slug(index, windows[index])}
        if row["status"] == "UNSTARTED" or is_retryable(row):
            selected.append(item)
        elif row["status"] in REUSABLE:
            reused.append({**item, "status": row["status"]})
        else:
            raise ValueError(f"non-transport failure requires diagnosis: {item['slug']}")
    return {
        "batch_index": batch_index,
        "batch_size": batch_size,
        "selected_windows": selected,
        "reused_windows": reused,
        "matrix": {"include": selected},
    }


def aggregate(root: Path) -> dict[str, Any]:
    verify(root)
    protocol = panel.load_protocol(PROTOCOL)
    windows = panel.expand_windows(protocol)
    rows = [summarize(root, i, start) for i, start in enumerate(windows)]
    counts = Counter(row["status"] for row in rows)
    completed = [row for row in rows if row["status"] == "COMPLETED"]
    total = sum(int(row["endpoint_pairs"]) for row in completed)
    certified = sum(int(row["certified_endpoint_pairs"]) for row in completed)
    missing = sum(int(row["missing_public_query_value_endpoint_pairs"]) for row in completed)
    unresolved = sum(int(row["computationally_unresolved_endpoint_pairs"]) for row in completed)
    data_complete = total - missing
    report = {
        "report_version": "chicago-k2-followup-summary/v1",
        "protocol_sha256": panel.sha256_file(PROTOCOL),
        "declared_window_count": len(rows),
        "status_counts": dict(counts),
        "completed_window_count": len(completed),
        "scientifically_ineligible_window_count": sum(
            count for status, count in counts.items() if status.startswith("INELIGIBLE_")
        ),
        "execution_failure_window_count": sum(
            count for status, count in counts.items()
            if status in {"EXECUTION_FAILED", "ATTEMPTED_NO_ARTIFACT"}
        ),
        "unstarted_window_count": counts["UNSTARTED"],
        "endpoint_pair_count": total,
        "certified_endpoint_pair_count": certified,
        "missing_public_query_value_endpoint_pair_count": missing,
        "computationally_unresolved_endpoint_pair_count": unresolved,
        "data_complete_endpoint_pair_count": data_complete,
        "data_complete_exact_endpoint_rate": certified / data_complete if data_complete else None,
        "all_completed_windows_count_closed": all(row.get("closure_status") == "PASS" for row in completed),
        "gate_status": "PASS_EXECUTION" if counts["UNSTARTED"] == 0 and not any(
            status not in REUSABLE for status in counts
        ) else "HOLD_INCOMPLETE",
        "windows": rows,
        "claim_boundary": protocol["claim_boundary"],
    }
    write_json(root / "followup_report.json", report)
    columns = sorted({key for row in rows for key in row})
    with (root / "followup_windows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (root / "FOLLOWUP_REPORT.md").write_text(
        "# Chicago K=2 96-window follow-up\n\n"
        f"Status: **{report['gate_status']}**.\n\n"
        f"Declared/completed/ineligible/failed/unstarted: 96/{len(completed)}/"
        f"{report['scientifically_ineligible_window_count']}/"
        f"{report['execution_failure_window_count']}/{counts['UNSTARTED']}.\n\n"
        f"Certified endpoint pairs: {certified}/{total}; missing public values: {missing}; "
        f"computationally unresolved: {unresolved}.\n\n"
        "Cells within a window are repeated queries, not independent cohorts. "
        "Timeouts and missing artifacts are not infeasibility.\n",
        encoding="utf-8",
    )
    (root / "FOLLOWUP_RESULTS.tex").write_text(
        "% Aggregate follow-up fragment; include only after gate review.\n"
        "\\paragraph{Chicago $K=2$ follow-up.} "
        f"Of 96 declared windows, {len(completed)} completed, "
        f"{report['scientifically_ineligible_window_count']} were scientifically ineligible, "
        f"{report['execution_failure_window_count']} had execution failures, and "
        f"{counts['UNSTARTED']} were unstarted. "
        f"Among {data_complete} data-complete endpoint pairs, {certified} were exactly certified; "
        f"{missing} further pairs lacked public query values and {unresolved} remained computationally unresolved. "
        "These windows are a fixed calendar extension, not a probability sample or hidden-partner recovery study.\n",
        encoding="utf-8",
    )
    return report


def merge(root: Path, attempts: Path, expected: list[int], source_run: str) -> dict[str, Any]:
    checkpoint = verify(root)
    protocol = panel.load_protocol(PROTOCOL)
    windows = panel.expand_windows(protocol)
    expected_set = set(expected)
    actual: dict[int, Path] = {}
    for directory in attempts.rglob("cohort_*") if attempts.exists() else []:
        if not directory.is_dir():
            continue
        try:
            index = int(directory.name.split("_", 2)[1])
        except (IndexError, ValueError) as error:
            raise ValueError("attempt directory has an invalid cohort slug") from error
        if index not in expected_set or directory.name != panel.window_slug(index, windows[index]):
            raise ValueError("attempt is undeclared for this batch")
        actual[index] = directory
    for index, directory in actual.items():
        resume.verify_driver(directory, protocol, index, windows[index])
        row = panel.summarize_window(index=index, start=windows[index], directory=directory)
        # Preserve diagnosed/non-transport failures in the ledger too. They are
        # not reusable or automatically retryable; plan() still blocks on them.
        # Rejecting their whole batch would discard other completed records and
        # misreport attempted windows as UNSTARTED.
        if row["status"] not in REUSABLE and row["status"] != "EXECUTION_FAILED":
            raise ValueError("attempt has an unsupported scientific status")
    observations = read_json(root / OBSERVATIONS)
    applied = []
    for index in expected:
        source = actual.get(index)
        if source is None:
            observations.append({
                "window_index": index,
                "status": "ATTEMPTED_NO_ARTIFACT",
                "source_run": source_run,
            })
            continue
        target = root / source.name
        if target.exists():
            history = root / "history" / source.name
            history.mkdir(parents=True, exist_ok=True)
            number = max((int(p.name) for p in history.iterdir() if p.name.isdigit()), default=0) + 1
            target.rename(history / f"{number:04d}")
        shutil.copytree(source, target)
        applied.append(index)
    write_json(root / OBSERVATIONS, observations)
    seal(root, [*checkpoint.get("provenance", []), {
        "event": "BATCH_MERGE",
        "source_run": source_run,
        "expected_indices": expected,
        "artifact_indices": sorted(actual),
        "applied_indices": applied,
    }])
    return aggregate(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--batch-index", type=int)
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--merge-dir", type=Path)
    parser.add_argument("--expected-indices-json")
    parser.add_argument("--source-run", default="local")
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args()
    if args.initialize:
        initialize(args.checkpoint_dir)
    if args.merge_dir is not None:
        if args.expected_indices_json is None:
            parser.error("merge requires --expected-indices-json")
        report = merge(
            args.checkpoint_dir,
            args.merge_dir,
            [int(value) for value in json.loads(args.expected_indices_json)],
            args.source_run,
        )
        print(json.dumps({key: value for key, value in report.items() if key != "windows"}, sort_keys=True))
        return 0
    if args.batch_index is not None:
        result = plan(args.checkpoint_dir, args.batch_index)
        if args.plan_output:
            write_json(args.plan_output, result)
        print(json.dumps(result, sort_keys=True))
    if args.aggregate_only or args.initialize:
        aggregate(args.checkpoint_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
