#!/usr/bin/env python3
"""Retry-safe launcher for one NYC ordered outcome/decision window.

The scientific optimizer is unchanged. Extraction uses one frozen candidate
row snapshot per attempt; post-extraction count checks are served from that
snapshot rather than issuing new Socrata queries. Bounded retries address
transient public-API failures. A technical failure remains a failed CI cell and
is never recoded as scientific ineligibility.
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from typing import Any

import live_nyc_hvfhv_ordered_decision_panel_window as legacy
import nyc_hvfhv_consistent_snapshot as consistent

TECHNICAL = "TECHNICAL_FAILURE"


def technical_report(args: Any, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "report_version": legacy.REPORT_VERSION,
        "status": TECHNICAL,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "window_label": args.window_label,
        "scan_start": args.scan_start,
        "scan_end": args.scan_end,
        "reason": attempts[-1]["error"] if attempts else "unknown technical failure",
        "technical_attempts": attempts,
        "cells": [],
        "baselines": [],
        "audit": {
            "status": "HOLD",
            "problem_count": 1,
            "problems": [{"reason": "technical_failure"}],
        },
        "redaction": legacy.redaction_contract(),
        "claim_boundary": legacy.claim_boundary(),
    }


def write_report(args: Any, report: dict[str, Any]) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        legacy.render(report), encoding="utf-8"
    )
    legacy.write_csv(
        report.get("cells", []), args.output_dir / "decision_cells.csv"
    )


def run_once(args: Any) -> dict[str, Any]:
    cache: dict[str, Any] = {}
    original_choose = legacy.base.choose_and_fetch
    original_count = legacy.base.count

    def choose(current_args: Any) -> dict[str, Any]:
        selected = consistent.choose_and_fetch(current_args)
        cache["selected"] = selected
        return selected

    def count(where: str) -> tuple[int, str, str]:
        selected = cache.get("selected")
        if selected is not None:
            if where == selected["where"]["determinate"]:
                return (
                    int(selected["determinate_count"]),
                    "frozen_candidate_snapshot",
                    "cached determinate count",
                )
            if where == selected["where"]["indeterminate"]:
                return (
                    int(selected["indeterminate_count"]),
                    "frozen_candidate_snapshot",
                    "cached indeterminate count",
                )
        return original_count(where)

    legacy.base.choose_and_fetch = choose
    legacy.base.count = count
    try:
        report = legacy.run(args)
    finally:
        legacy.base.choose_and_fetch = original_choose
        legacy.base.count = original_count

    selected = cache.get("selected")
    if selected is not None:
        report["extraction"] = {
            "mode": "frozen_candidate_snapshot",
            "candidate_snapshot_sha256": selected.get("candidate_snapshot_sha256"),
            "core_snapshot_sha256": selected.get("core_snapshot_sha256"),
            "candidate_row_count": len(selected.get("candidate_rows", [])),
            "post_fetch_server_recounts": 0,
        }
    return report


def self_test() -> None:
    legacy.self_test()

    class Args:
        window_label = "synthetic"
        scan_start = "a"
        scan_end = "b"

    report = technical_report(Args(), [{"attempt": 1, "error": "timeout"}])
    assert report["status"] == TECHNICAL
    assert report["redaction"]["aggregate_only"] is True
    print("NYC ordered decision retry launcher self-test: PASS")


def main() -> int:
    parser = legacy.parser()
    parser.add_argument("--fetch-attempts", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=10.0)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.fetch_attempts < 1:
        parser.error("--fetch-attempts must be positive")
    legacy.base.validate(args)
    attempts: list[dict[str, Any]] = []
    report: dict[str, Any] | None = None
    for attempt in range(1, args.fetch_attempts + 1):
        try:
            report = run_once(args)
            report["execution_attempt_count"] = attempt
            report["retry_diagnostics"] = attempts
            break
        except legacy.base.LiveDataError as exc:
            message = str(exc)
            attempts.append(
                {
                    "attempt": attempt,
                    "error": message,
                    "recorded_at_utc": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat(),
                }
            )
            if "no scan window produced an integrity- and cap-qualified core" in message:
                report = legacy.ineligible_report(args, message)
                report["execution_attempt_count"] = attempt
                report["retry_diagnostics"] = attempts[:-1]
                break
            if attempt < args.fetch_attempts:
                time.sleep(args.retry_sleep_seconds * attempt)
                continue
            report = technical_report(args, attempts)
        except Exception:
            traceback.print_exc()
            raise

    assert report is not None
    write_report(args, report)
    print(legacy.render(report))
    return 2 if report["status"] == TECHNICAL else 0


if __name__ == "__main__":
    raise SystemExit(main())
