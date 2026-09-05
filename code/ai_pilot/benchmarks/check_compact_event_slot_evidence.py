#!/usr/bin/env python3
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "compact_event_slot_audit"
P = json.loads((HERE / "COMPACT_EVENT_SLOT_PROTOCOL.json").read_text())
S = json.loads((OUT / "SUMMARY.json").read_text())
R = json.loads((OUT / "RUNS.json").read_text())
D = json.loads((OUT / "DEFAULT_DECISION.json").read_text())
SOLVER = HERE.parent / "data_pipeline" / "production_audit" / "ordered_run_disclosure_separator.py"
PROBE = HERE.parent / "data_pipeline" / "production_audit" / "compact_event_slot_probe.py"

assert len(R) == P["run_count"] == 96
assert S["design"] == P
assert S["protocol_sha256"] == hashlib.sha256((HERE / "COMPACT_EVENT_SLOT_PROTOCOL.json").read_bytes()).hexdigest()
assert S["solver_sha256"] == hashlib.sha256(SOLVER.read_bytes()).hexdigest()
assert S["compact_probe_sha256"] == hashlib.sha256(PROBE.read_bytes()).hexdigest()
assert S["run_record_sha256"] == hashlib.sha256(json.dumps(R, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
assert all(not r["relation_witness_serialized"] for r in R)
assert all(r["status"] != "TECHNICAL_FAILURE" for r in R)

groups = defaultdict(dict)
for r in R:
    groups[(tuple(r["cell"]), r["replicate"])][r["variant"]] = r
assert len(groups) == P["endpoint_problem_count"] * P["replicates"]
for group in groups.values():
    assert set(group) == {"compact_probe", "probe_disabled"}
    lows = [Fraction(r["lower_rational"]) for r in group.values() if r["lower_rational"]]
    highs = [Fraction(r["upper_rational"]) for r in group.values() if r["upper_rational"]]
    if lows and highs:
        assert max(lows) <= min(highs)

E = S["paired_effects"]
expected = E["exact_loss"] == 0 and E["incumbent_loss"] == 0 and (E["exact_gain"] > 0 or E["strict_lower_bound_gain"] > 0)
assert D["beneficial_under_rule"] == expected
assert D["default_compact_probe_seconds"] == (0.75 if expected else 0.0)
assert S["production_default_compact_probe_seconds"] == D["default_compact_probe_seconds"]
print("compact event-slot frozen evidence: PASS")
