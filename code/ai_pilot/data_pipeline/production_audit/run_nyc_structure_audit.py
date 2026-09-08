#!/usr/bin/env python3
"""Fetch one pinned NYC audit input and compare event restrictions on it."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess

import numpy
import scipy

import live_nyc_hvfhv_existential_time as existential
import live_nyc_hvfhv_existential_time_hybrid as hybrid
import live_nyc_hvfhv_ordered_run_smoke as base
from nyc_hvfhv_smoke_types import canon, sha
from ordered_run_fixed_time_master import FixedTimeRow

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "NYC_STRUCTURE_AUDIT_PROTOCOL.json"


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_input(protocol):
    extraction = dict(protocol["extraction"])
    args = argparse.Namespace(**extraction)
    before = base.snapshot()
    selected = base.choose_and_fetch(args)
    determinate, _, _ = base.count(selected["where"]["determinate"])
    indeterminate, _, _ = base.count(selected["where"]["indeterminate"])
    after = base.snapshot()
    if before != after:
        raise base.LiveDataError("metadata changed during extraction")
    if (determinate, indeterminate) != (
        selected["determinate_count"], selected["indeterminate_count"]
    ):
        raise base.LiveDataError("candidate counts changed during extraction")
    if selected["provider"] != extraction["expected_provider"]:
        raise base.LiveDataError("unexpected provider; do not silently change cohort")
    trips, row_audit = base.parse_trips(
        selected["candidate_rows"], selected["provider"],
        selected["core_start"], selected["core_end"],
    )
    reduced = existential.reduced_cohort(
        trips, protocol["core_rows"], protocol["buffer_rows"]
    )
    rows = hybrid._fixed_rows(reduced, existential.support_origin(reduced))
    serialized = [asdict(row) for row in rows]
    return {
        "protocol_sha256": file_sha(PROTOCOL),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": serialized,
        "input_sha256": sha(serialized),
        "source": {
            "dataset_url": "https://data.cityofnewyork.us/resource/u253-aew4.json",
            "snapshot": after,
            "provider": selected["provider"],
            "core_window_start": selected["core_start"].isoformat(),
            "core_window_end": selected["core_end"].isoformat(),
            "source_core_rows": row_audit["core_rows"],
            "source_candidate_rows": row_audit["rows"],
            "determinate_rows": determinate,
            "indeterminate_rows": indeterminate,
            "query_sha256": selected["queries"],
            "source_candidate_multiset_sha256": sha(sorted(
                canon(row).decode() for row in selected["candidate_rows"]
            )),
            "count_reconciled": True,
            "new_extraction": True,
            "byte_identity_with_old_scale_instance": "NOT_ESTABLISHED",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/nyc-structure-audit"))
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--reuse-input", action="store_true")
    parser.add_argument("--expected-input-sha256", help="Require byte-identical modeled input for a replay")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = args.output_dir / "input.private.json"
    # Refuse to put a row-level cache in a tracked results directory.
    repository = HERE.parents[3]
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", str(cache_path.resolve())],
        cwd=repository, check=False,
    )
    if ignored.returncode != 0:
        raise SystemExit("output-dir must be git-ignored; input cache is private scratch")
    if args.reuse_input:
        cached = json.loads(cache_path.read_text())
    else:
        if cache_path.exists():
            raise SystemExit("input already exists; use --reuse-input or a new output directory")
        print("Fetching one count-reconciled NYC snapshot", flush=True)
        cached = fetch_input(protocol)
        cache_path.write_text(json.dumps(cached, indent=2) + "\n")
    if cached["protocol_sha256"] != file_sha(PROTOCOL):
        raise SystemExit("cached input uses a different protocol")
    if cached["input_sha256"] != sha(cached["rows"]):
        raise SystemExit("cached input hash mismatch")
    if args.expected_input_sha256 and cached["input_sha256"] != args.expected_input_sha256:
        raise SystemExit("live input differs from requested replay; it is a new snapshot")
    print(json.dumps({"input_sha256": cached["input_sha256"],
                      "row_count": len(cached["rows"]),
                      "source": cached["source"]}), flush=True)
    if args.fetch_only:
        return 0
    from ordered_run_structure_audit import audit, write_report
    rows = [FixedTimeRow(**row) for row in cached["rows"]]
    report = audit(rows, protocol)
    report["provenance"] = {
        "source": cached["source"],
        "fetched_at_utc": cached["fetched_at_utc"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": file_sha(PROTOCOL),
        "input_sha256": cached["input_sha256"],
        "source_code_sha256": {
            name: file_sha(HERE / name) for name in (
                Path(__file__).name, "ordered_run_structure_audit.py",
                "ordered_run_fixed_time_master.py", "nyc_hvfhv_smoke_fetch.py",
                "nyc_hvfhv_smoke_types.py", "live_nyc_hvfhv_existential_time.py",
                "live_nyc_hvfhv_existential_time_hybrid.py",
                "live_nyc_hvfhv_ordered_run_smoke.py",
            )
        },
        "versions": {"python": platform.python_version(),
                     "numpy": numpy.__version__, "scipy": scipy.__version__},
    }
    write_report(report, args.output_dir / "aggregate")
    print(json.dumps(report["summary"], indent=2), flush=True)
    return 0 if report["summary"]["verification_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
