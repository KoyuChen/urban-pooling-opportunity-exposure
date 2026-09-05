#!/usr/bin/env python3
"""Reconstruct and validate compact event-slot audit evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
BENCH = HERE.parent
RESULTS = BENCH / "results" / "compact_event_slot_audit"
sys.path.insert(0, str(BENCH))

import compact_event_slot_audit as audit


def _forbid_witnesses(value, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            if lowered in {"witness", "events", "event_masks", "selected_columns"}:
                raise AssertionError(f"relation witness field published at {path}.{key}")
            _forbid_witnesses(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _forbid_witnesses(child, f"{path}[{index}]")


def check() -> dict:
    protocol = json.loads(audit.PROTOCOL_PATH.read_text(encoding="utf-8"))
    records = json.loads((RESULTS / "RUNS.json").read_text(encoding="utf-8"))
    stored = json.loads((RESULTS / "SUMMARY.json").read_text(encoding="utf-8"))
    decision = json.loads(
        (RESULTS / "DEFAULT_DECISION.json").read_text(encoding="utf-8")
    )

    _forbid_witnesses(records)
    _forbid_witnesses(stored)
    _forbid_witnesses(decision)

    reconstructed = audit.summarize(protocol, records)
    for key, value in reconstructed.items():
        if stored.get(key) != value:
            raise AssertionError(f"stored summary mismatch for {key}")

    if len(records) != protocol["primary_run_count"]:
        raise AssertionError("frozen run count differs from protocol")
    if stored["unique_paired_cells"] * 2 != stored["record_count"]:
        raise AssertionError("paired-cell accounting is inconsistent")

    expected_decision = {
        "beneficial_under_rule": stored["beneficial_under_predeclared_rule"],
        "default_compact_probe_seconds": stored[
            "recommended_default_compact_probe_seconds"
        ],
        "paired_effects": stored["paired_effects"],
        "disabled_variant": stored["variants"]["disabled"],
        "compact_variant": stored["variants"]["probe"],
        "rule_source": "COMPACT_EVENT_SLOT_PROTOCOL.json",
    }
    if decision != expected_decision:
        raise AssertionError("default decision does not follow frozen rule")

    solver_path = (
        HERE.parents[1]
        / "data_pipeline"
        / "production_audit"
        / "ordered_run_disclosure_separator.py"
    )
    source = solver_path.read_text(encoding="utf-8")
    expected_field = (
        "    compact_probe_seconds: float = "
        f"{decision['default_compact_probe_seconds']}\n"
    )
    if expected_field not in source:
        raise AssertionError("production default does not match frozen decision")

    for record in records:
        lower = record["lower_rational"]
        upper = record["upper_rational"]
        if record["incumbent_available"] != (upper is not None):
            raise AssertionError("incumbent flag does not match upper bound")
        if record["reference_used_as_warm_start"] is not False:
            raise AssertionError("reference world was used as a warm start")
        if record["counts"].get("all_event_columns_enumerated") is True:
            raise AssertionError("complete columns were enumerated")
        if record["counts"].get("all_worlds_enumerated") is True:
            raise AssertionError("complete worlds were enumerated")
        if lower is not None and upper is not None:
            from fractions import Fraction
            if Fraction(lower) > Fraction(upper):
                raise AssertionError("invalid exact interval")

    return {
        "record_count": len(records),
        "paired_cells": stored["unique_paired_cells"],
        "beneficial": decision["beneficial_under_rule"],
        "default_seconds": decision["default_compact_probe_seconds"],
    }


if __name__ == "__main__":
    print(json.dumps(check(), indent=2, sort_keys=True))
