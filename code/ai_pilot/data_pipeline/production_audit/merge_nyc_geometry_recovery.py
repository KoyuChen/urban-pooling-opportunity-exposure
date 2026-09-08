#!/usr/bin/env python3
"""Merge a transport-only recovery without discarding original attempt records."""
import argparse
import json
from pathlib import Path

import nyc_geometry_census as census
import retry_nyc_geometry_transport as transport


def discover(root):
    reports = {}
    for path in root.rglob('report.json'):
        report = json.loads(path.read_text())
        i = report['window']['index']
        if i in reports:
            raise ValueError('duplicate window in source campaign')
        reports[i] = report
    return reports


def merge(base, retries, protocol):
    # Validate both source sets against the same frozen scientific producer.
    census.aggregate(protocol, list(base.values()))
    census.aggregate(protocol, list(retries.values()))
    combined = dict(base)
    amendment = json.loads(transport.AMENDMENT.read_text())
    for index, report in retries.items():
        if index not in base:
            raise ValueError('retry has no prior failed or reusable record')
        previous = base[index]
        if census.sha(previous) == census.sha(report):
            continue
        if previous['status'] not in census.RETRYABLE:
            raise ValueError('recovery changed a completed scientific record')
        note = report.get('transport_amendment', {})
        if (note.get('prior_report_sha256') != census.sha(previous) or
                note.get('amendment_sha256') != census.file_sha(transport.AMENDMENT) or
                note.get('execution_overrides') != amendment['execution_overrides'] or
                note.get('retry_launcher_sha256') != census.file_sha(Path(transport.__file__))):
            raise ValueError('retry amendment or predecessor hash mismatch')
        combined[index] = report
    return census.aggregate(protocol, list(combined.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-dir',type=Path,required=True)
    parser.add_argument('--retry-dir',type=Path,required=True)
    parser.add_argument('--base-run-id',type=int,required=True)
    parser.add_argument('--retry-run-id',type=int,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    protocol = json.loads(census.PROTOCOL.read_text())
    report = merge(discover(args.base_dir), discover(args.retry_dir), protocol)
    attempts = {}
    for root, run_id in ((args.base_dir,args.base_run_id),(args.retry_dir,args.retry_run_id)):
        for path in root.rglob('attempt_*.json'):
            attempt = json.loads(path.read_text())
            fingerprint = census.sha(attempt)
            if fingerprint not in attempts:
                attempts[fingerprint] = {
                    'window_index':attempt['window']['index'],'status':attempt['status'],
                    'started_at':attempt.get('started_at'),'completed_at':attempt.get('completed_at'),
                    'reason_type':attempt.get('reason_type'),'reason_sha256':attempt.get('reason_sha256'),
                    'report_sha256':fingerprint,'observed_in_runs':[],
                }
            attempts[fingerprint]['observed_in_runs'].append(run_id)
    report['attempt_history'] = sorted(attempts.values(),key=lambda a:(a['window_index'],a['started_at'] or ''))
    report['recovery_source'] = {
        'base_run_id':args.base_run_id,'retry_run_id':args.retry_run_id,
        'amendment_sha256':census.file_sha(transport.AMENDMENT),
        'merger_sha256':census.file_sha(Path(__file__)),
        'retained_unique_attempts':len(attempts),
        'missing_retry_records':sorted(set(discover(args.base_dir))-set(discover(args.retry_dir))),
    }
    census.write_summary(report,args.output_dir)
    print(json.dumps(report['summary'],indent=2))
    return 0 if report['summary']['status']=='PASS_GEOMETRY_CENSUS' else 2


if __name__=='__main__':raise SystemExit(main())
