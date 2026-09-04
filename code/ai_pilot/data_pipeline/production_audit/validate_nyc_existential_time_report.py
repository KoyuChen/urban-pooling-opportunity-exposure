#!/usr/bin/env python3
"""Validate strict resolution of an NYC existential-time report.

A strict audit should accept two kinds of mathematically resolved cells:

1. a certified feasible common-support cell with certified lower and upper
   outcome endpoints; or
2. a proven-infeasible cell with no published outcome endpoints.

The previous workflow accepted only the first kind, so an exact finite proof
that C=2 cannot select six buffers incorrectly turned the whole q=1.5 Gate red.
This validator keeps unresolved, invalid-incumbent, timeout, and error states
fail-closed while recognizing proven infeasibility as a valid certificate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FEASIBLE_STATUS = "CERTIFIED_COMMON_SUPPORT_FEASIBILITY"
OUTCOME_STATUS = "CERTIFIED_OPTIMAL_PAIR"


def is_proven_infeasible(status: str) -> bool:
    return status.startswith("PROVEN_INFEASIBLE")


def audit(report: dict[str, Any]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    containment = report.get("time_support", {}).get(
        "support_containment_audit", {}
    )
    if containment.get("status") != "PASS":
        problems.append({"reason": "support_containment_not_pass"})

    for time_model, capacity_audit in report.get("capacity_audits", {}).items():
        if capacity_audit.get("problems"):
            problems.append(
                {
                    "reason": "capacity_audit_has_problems",
                    "time_model": time_model,
                    "details": capacity_audit.get("problems"),
                }
            )
    if report.get("time_nesting_audit", {}).get("problems"):
        problems.append(
            {
                "reason": "time_nesting_audit_has_problems",
                "details": report["time_nesting_audit"].get("problems"),
            }
        )

    cells = report.get("cells_by_time", {})
    expected_time_models = {"exact_singleton", "rounded_15m_existential"}
    if set(cells) != expected_time_models:
        problems.append(
            {
                "reason": "unexpected_time_models",
                "observed": sorted(cells),
                "expected": sorted(expected_time_models),
            }
        )

    classifications: list[dict[str, Any]] = []
    for time_model, model_cells in cells.items():
        for cell in model_cells:
            status = str(cell.get("status", ""))
            outcomes = cell.get("outcomes", [])
            if status == FEASIBLE_STATUS:
                bad_outcomes = [
                    row.get("status")
                    for row in outcomes
                    if row.get("status") != OUTCOME_STATUS
                ]
                if not outcomes or bad_outcomes:
                    classification = "UNRESOLVED_OR_INVALID_FEASIBLE_CELL"
                    problems.append(
                        {
                            "reason": "feasible_cell_lacks_certified_endpoints",
                            "time_model": time_model,
                            "capacity": cell.get("capacity"),
                            "outcome_statuses": [
                                row.get("status") for row in outcomes
                            ],
                        }
                    )
                else:
                    classification = "CERTIFIED_FEASIBLE_WITH_ENDPOINTS"
            elif is_proven_infeasible(status):
                if outcomes:
                    classification = "INVALID_INFEASIBLE_CELL_WITH_OUTCOMES"
                    problems.append(
                        {
                            "reason": "infeasible_cell_publishes_outcomes",
                            "time_model": time_model,
                            "capacity": cell.get("capacity"),
                        }
                    )
                else:
                    classification = "CERTIFIED_INFEASIBLE"
            else:
                classification = "UNRESOLVED"
                problems.append(
                    {
                        "reason": "unresolved_cell",
                        "time_model": time_model,
                        "capacity": cell.get("capacity"),
                        "status": status,
                        "outcome_statuses": [
                            row.get("status") for row in outcomes
                        ],
                    }
                )
            classifications.append(
                {
                    "time_model": time_model,
                    "capacity": cell.get("capacity"),
                    "status": status,
                    "classification": classification,
                }
            )

    return {
        "status": "PASS" if not problems and classifications else "FAIL",
        "problem_count": len(problems),
        "problems": problems,
        "cell_classifications": classifications,
        "resolved_cell_count": sum(
            row["classification"]
            in {
                "CERTIFIED_FEASIBLE_WITH_ENDPOINTS",
                "CERTIFIED_INFEASIBLE",
            }
            for row in classifications
        ),
        "cell_count": len(classifications),
    }


def self_test() -> None:
    base = {
        "time_support": {"support_containment_audit": {"status": "PASS"}},
        "capacity_audits": {
            "exact_singleton": {"problems": []},
            "rounded_15m_existential": {"problems": []},
        },
        "time_nesting_audit": {"problems": []},
        "cells_by_time": {
            "exact_singleton": [
                {
                    "capacity": 2,
                    "status": "PROVEN_INFEASIBLE_EXACT_ENUMERATION",
                    "outcomes": [],
                }
            ],
            "rounded_15m_existential": [
                {
                    "capacity": 2,
                    "status": FEASIBLE_STATUS,
                    "outcomes": [
                        {"status": OUTCOME_STATUS},
                        {"status": OUTCOME_STATUS},
                    ],
                }
            ],
        },
    }
    passed = audit(base)
    assert passed["status"] == "PASS", passed
    damaged = json.loads(json.dumps(base))
    damaged["cells_by_time"]["rounded_15m_existential"][0]["status"] = (
        "UNRESOLVED_NO_INCUMBENT"
    )
    assert audit(damaged)["status"] == "FAIL"
    print("existential-time report resolution validator self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.report is None:
        parser.error("--report is required")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    result = audit(report)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
