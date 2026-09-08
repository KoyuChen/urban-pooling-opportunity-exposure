#!/usr/bin/env python3
"""Apply an explicitly recorded transport-only amendment to failed windows."""
import argparse
import json
from pathlib import Path

import nyc_geometry_census as census

AMENDMENT = census.HERE / "NYC_GEOMETRY_TRANSPORT_AMENDMENT.json"


def retry(index, output):
    protocol = json.loads(census.PROTOCOL.read_text())
    amendment = json.loads(AMENDMENT.read_text())
    if census.file_sha(census.PROTOCOL) != amendment["base_protocol_sha256"]:
        raise ValueError("base scientific protocol changed")
    if census.file_sha(Path(census.__file__)) != amendment["frozen_producer_sha256"]:
        raise ValueError("frozen geometry producer changed")
    previous = json.loads((output / "report.json").read_text())
    if previous["window"] != protocol["windows"][index] or previous["provenance"] != census.provenance():
        raise ValueError("checkpoint does not match declared window and code")
    if previous["status"] in census.TERMINAL:
        print(json.dumps({"index":index,"status":previous["status"],"reused":True}))
        return previous
    if previous["status"] not in census.RETRYABLE:
        raise ValueError("only recorded transport failures may use this amendment")
    attempt_number = len(list(output.glob("attempt_*.json"))) + 1
    overrides = amendment["execution_overrides"]
    note = {"amendment_sha256":census.file_sha(AMENDMENT),
            "retry_launcher_sha256":census.file_sha(Path(__file__)),
            "base_protocol_sha256":census.file_sha(census.PROTOCOL),
            "execution_overrides":overrides,
            "prior_report_sha256":census.sha(previous),"declared_before_retry_at":census.now()}
    census.write_json(output / f"transport_amendment_{attempt_number:03d}.json",note)
    protocol["execution"].update(overrides)
    report = census.run_window(protocol["windows"][index],protocol,output)
    report["transport_amendment"] = note
    census.write_json(output / f"attempt_{attempt_number:03d}.json",report)
    census.write_json(output / "report.json",report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-index",type=int,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    if args.window_index not in range(24):
        parser.error("window index outside declared calendar")
    result=retry(args.window_index,args.output_dir)
    return 0 if result['status'] in census.TERMINAL else 2


if __name__=='__main__':raise SystemExit(main())
