#!/usr/bin/env python3
"""Archive census evidence with actual workflow states for unobserved records.

The standalone reducer has no scheduling information. This collector prevents
an undownloaded or queued job from being reported as an unstarted experiment.
It does not alter the frozen producer, selected windows or geometry metrics.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re

import nyc_geometry_census as census


def annotate(report, jobs):
    report = deepcopy(report)
    states = {}
    for job in jobs:
        match = re.fullmatch(r"geometry-window \((\d+)\)", job["name"])
        if match:
            index = int(match[1])
            if index in states:
                raise ValueError("duplicate latest-attempt workflow job")
            states[index] = job
    for row in report["ledger"]:
        job = states.get(row["window"]["index"])
        if job:
            row["workflow_job"] = {key: job.get(key) for key in ("id", "status", "conclusion")}
        if row["status"] != "NOT_STARTED":
            continue
        if job is None:
            row["status"] = "NO_OBSERVED_RECORD_OR_JOB"
        elif job["status"] in {"queued", "waiting", "pending", "requested"}:
            row["status"] = "QUEUED"
        elif job["status"] == "in_progress":
            row["status"] = "IN_PROGRESS_REMOTE"
        elif job.get("conclusion") == "success":
            row["status"] = "AWAITING_ARTIFACT_RETRIEVAL"
        else:
            row["status"] = "MISSING_REPORT_AFTER_JOB"
    report["summary"]["status_counts"] = dict(Counter(row["status"] for row in report["ledger"]))
    report["provenance"]["collector_sha256"] = census.file_sha(Path(__file__).resolve())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--jobs-json", type=Path, required=True)
    parser.add_argument("--artifacts-json", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--local-retries-json", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(census.PROTOCOL.read_text())
    reports = [json.loads(p.read_text()) for p in sorted(args.input_dir.rglob("report.json"))]
    report = annotate(census.aggregate(protocol, reports), json.loads(args.jobs_json.read_text()))
    report["workflow_source"] = {
        "run_id": args.run_id, "source_commit": args.source_commit,
        "url": f"https://github.com/KoyuChen/urban-pooling-opportunity-exposure/actions/runs/{args.run_id}",
        "artifacts": [{k:a.get(k) for k in ("id","name","digest")} for a in json.loads(args.artifacts_json.read_text())],
        "window_report_sha256": {r["window"]["label"]:census.sha(r) for r in reports},
        "job_states_sha256": census.file_sha(args.jobs_json),
    }
    if args.local_retries_json:
        recoveries = json.loads(args.local_retries_json.read_text())
        by_index = {row["window"]["index"]: row for row in reports}
        for recovery in recoveries:
            i = recovery["window_index"]
            if recovery["replayed_report_sha256"] != census.sha(by_index[i]):
                raise ValueError("local retry provenance disagrees with imported report")
            report["ledger"][i]["local_retry"] = recovery
        report["local_retries"] = recoveries
    census.write_summary(report, args.output_dir)
    counts = report["summary"]["status_counts"]
    transport = sum(counts.get(s, 0) for s in census.RETRYABLE)
    excluded = sum(n for s, n in counts.items() if s.startswith("INELIGIBLE_"))
    with (args.output_dir / "RESULTS.tex").open("a") as handle:
        handle.write(f"This checkpoint retains {transport} transport failures and {excluded} protocol exclusions; "
                     f"the census gate is {report['summary']['status'].replace('_', ' ')}.\n")
    manifest_path = args.output_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files_sha256"]["RESULTS.tex"] = census.file_sha(args.output_dir / "RESULTS.tex")
    census.write_json(manifest_path, manifest)
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["status"] == "PASS_GEOMETRY_CENSUS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
