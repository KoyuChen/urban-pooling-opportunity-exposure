#!/usr/bin/env python3
"""Freeze compact-probe evidence and synchronize repository-facing metadata."""
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "code/ai_pilot/benchmarks"
AUDIT = ROOT / "code/ai_pilot/data_pipeline/production_audit"
TMP = ROOT / "tmp/compact-event-slot-audit"
OUT = BENCH / "results/compact_event_slot_audit"
PROTOCOL_PATH = BENCH / "COMPACT_EVENT_SLOT_PROTOCOL.json"
SOLVER = AUDIT / "ordered_run_disclosure_separator.py"
PROBE = AUDIT / "compact_event_slot_probe.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paired_effects(records: list[dict]) -> dict[str, int]:
    grouped: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for record in records:
        grouped[(tuple(record["cell"]), record["replicate"])][record["variant"]] = record
    effects = {
        "exact_gain": 0,
        "exact_loss": 0,
        "bound_equality_gain": 0,
        "bound_equality_loss": 0,
        "incumbent_gain": 0,
        "incumbent_loss": 0,
        "strict_lower_bound_gain": 0,
        "strict_lower_bound_loss": 0,
        "strict_gap_reduction": 0,
        "strict_gap_increase": 0,
    }
    for group in grouped.values():
        if set(group) != {"compact_probe", "probe_disabled"}:
            raise AssertionError("incomplete paired cell")
        enabled = group["compact_probe"]
        disabled = group["probe_disabled"]
        for key, gain, loss in (
            ("exact_status", "exact_gain", "exact_loss"),
            ("bound_equality", "bound_equality_gain", "bound_equality_loss"),
            ("incumbent_available", "incumbent_gain", "incumbent_loss"),
        ):
            effects[gain] += int(bool(enabled[key]) and not bool(disabled[key]))
            effects[loss] += int(bool(disabled[key]) and not bool(enabled[key]))
        if enabled["lower_rational"] and disabled["lower_rational"]:
            left = Fraction(enabled["lower_rational"])
            right = Fraction(disabled["lower_rational"])
            effects["strict_lower_bound_gain"] += int(left > right)
            effects["strict_lower_bound_loss"] += int(left < right)
        if enabled["absolute_gap_rational"] and disabled["absolute_gap_rational"]:
            left = Fraction(enabled["absolute_gap_rational"])
            right = Fraction(disabled["absolute_gap_rational"])
            effects["strict_gap_reduction"] += int(left < right)
            effects["strict_gap_increase"] += int(left > right)
    return effects


def write_checker() -> None:
    path = BENCH / "check_compact_event_slot_evidence.py"
    path.write_text(
        '''#!/usr/bin/env python3
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
'''
    )
    path.chmod(0o755)


def update_ci() -> None:
    path = ROOT / ".github/workflows/ci.yml"
    text = path.read_text()
    if "check_compact_event_slot_evidence.py" not in text:
        old = (
            "            code/ai_pilot/benchmarks/selective_disclosure_constraint_generation.py \\\n"
            "            code/ai_pilot/data_pipeline/production_audit/live_chicago_release_operator_audit_partitioned.py\n"
        )
        new = (
            "            code/ai_pilot/benchmarks/selective_disclosure_constraint_generation.py \\\n"
            "            code/ai_pilot/benchmarks/compact_event_slot_audit.py \\\n"
            "            code/ai_pilot/benchmarks/check_compact_event_slot_evidence.py \\\n"
            "            code/ai_pilot/data_pipeline/production_audit/compact_event_slot_probe.py \\\n"
            "            code/ai_pilot/data_pipeline/production_audit/live_chicago_release_operator_audit_partitioned.py\n"
        )
        if old not in text:
            raise AssertionError("CI compile anchor missing")
        text = text.replace(old, new, 1)
    if "actual=\"$(find .github/workflows" not in text:
        old = (
            "          python code/ai_pilot/benchmarks/selective_disclosure_constraint_generation.py \\\n"
            "            --self-test\n"
        )
        new = old + (
            "          python code/ai_pilot/benchmarks/compact_event_slot_audit.py --self-test\n"
            "          python code/ai_pilot/benchmarks/check_compact_event_slot_evidence.py\n"
            "          actual=\"$(find .github/workflows -maxdepth 1 -type f -printf '%f\\n' | sort)\"\n"
            "          expected=\"$(printf 'chicago-live-audits.yml\\nci.yml\\n')\"\n"
            "          test \"$actual\" = \"$expected\"\n"
        )
        if old not in text:
            raise AssertionError("CI self-test anchor missing")
        text = text.replace(old, new, 1)
    path.write_text(text)


def upsert_readme(protocol: dict, enabled: dict, disabled: dict, effects: dict, default: float) -> None:
    path = ROOT / "README.md"
    text = path.read_text()
    start = "## Compact event-slot evidence\n"
    end = "## Reproduce\n"
    if start in text:
        before, tail = text.split(start, 1)
        if end not in tail:
            raise AssertionError("README compact section has no reproduce boundary")
        _, after = tail.split(end, 1)
        text = before.rstrip() + "\n\n" + end + after
    block = f'''## Compact event-slot evidence

The minimum-event solver includes an optional compact at-most-K event-slot
outer relaxation. Its {protocol["run_count"]}-run paired audit is committed under
`code/ai_pilot/benchmarks/results/compact_event_slot_audit/`: exact status is
{enabled["exact_status_count"]}/{enabled["run_count"]} with the probe and
{disabled["exact_status_count"]}/{disabled["run_count"]} without it. Paired
exact gains/losses are {effects["exact_gain"]}/{effects["exact_loss"]}; the
predeclared rule sets the default probe budget to `{default}` seconds. These are
synthetic implementation results, not manuscript or city-data claims.

'''
    if end not in text:
        raise AssertionError("README reproduce anchor missing")
    text = text.replace(end, block + end, 1)
    old = "- `docs/IMPLICIT_DISCLOSURE_SEPARATOR.md` -- new separator contract and bound proofs.\n"
    new = (
        "- `docs/IMPLICIT_DISCLOSURE_SEPARATOR.md` -- separator contract and bound proofs.\n"
        "- `docs/COMPACT_EVENT_SLOT_PROBE.md` -- compact lower-bound contract and audit.\n"
        "- `docs/MANUSCRIPT_SCOPE_DECISION.md` -- current paper-scope decision.\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
    path.write_text(text)


def main() -> None:
    protocol = json.loads(PROTOCOL_PATH.read_text())
    records = json.loads((TMP / "RUNS.json").read_text())
    summary = json.loads((TMP / "SUMMARY.json").read_text())
    effects = paired_effects(records)
    beneficial = effects["exact_loss"] == 0 and effects["incumbent_loss"] == 0 and (effects["exact_gain"] > 0 or effects["strict_lower_bound_gain"] > 0)
    default = 0.75 if beneficial else 0.0

    solver_text = SOLVER.read_text()
    anchor = "    compact_probe_seconds: float = 0.0\n"
    if anchor not in solver_text:
        raise AssertionError("unexpected predecision compact default")
    timed_solver_sha = sha(SOLVER)
    SOLVER.write_text(solver_text.replace(anchor, f"    compact_probe_seconds: float = {default}\n", 1))

    summary["timed_solver_sha256"] = timed_solver_sha
    summary["solver_sha256"] = sha(SOLVER)
    summary["timed_variants_override_default_explicitly"] = True
    summary["paired_effects"] = effects
    summary["production_default_compact_probe_seconds"] = default
    summary["beneficial_under_predeclared_rule"] = beneficial
    summary["workflow_run_id"] = int(os.environ["GITHUB_RUN_ID"])
    summary["workflow_source_commit"] = os.environ["GITHUB_SHA"]
    summary["run_record_sha256"] = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    decision = {
        "rule": "default_on iff exact_loss=0, incumbent_loss=0, and (exact_gain>0 or strict_lower_bound_gain>0)",
        "beneficial_under_rule": beneficial,
        "default_compact_probe_seconds": default,
        "paired_effects": effects,
        "compact_variant": summary["variants"]["compact_probe"],
        "disabled_variant": summary["variants"]["probe_disabled"],
        "workflow_run_id": int(os.environ["GITHUB_RUN_ID"]),
        "claim_boundary": summary["claim_boundary"],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RUNS.json").write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (OUT / "DEFAULT_DECISION.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")

    enabled = summary["variants"]["compact_probe"]
    disabled = summary["variants"]["probe_disabled"]
    (OUT / "REPORT.md").write_text(f'''# Compact event-slot lower-bound audit

Executed in GitHub Actions run `{os.environ["GITHUB_RUN_ID"]}`. The frozen
protocol contains {protocol["endpoint_problem_count"]} endpoint problems,
{protocol["replicates"]} timing repeats and {protocol["run_count"]} total solver
invocations on synthetic sequential nonclique instances.

| Variant | Exact status | Equal bounds | Incumbent | Median seconds | Pricing LP calls |
|---|---:|---:|---:|---:|---:|
| Compact probe | {enabled["exact_status_count"]}/{enabled["run_count"]} | {enabled["bound_equality_count"]}/{enabled["run_count"]} | {enabled["incumbent_count"]}/{enabled["run_count"]} | {enabled["median_elapsed_seconds"]:.3f} | {enabled["total_pricing_lp_calls"]:,} |
| Probe disabled | {disabled["exact_status_count"]}/{disabled["run_count"]} | {disabled["bound_equality_count"]}/{disabled["run_count"]} | {disabled["incumbent_count"]}/{disabled["run_count"]} | {disabled["median_elapsed_seconds"]:.3f} | {disabled["total_pricing_lp_calls"]:,} |

Paired exact gains/losses are **{effects["exact_gain"]} / {effects["exact_loss"]}**;
incumbent gains/losses are **{effects["incumbent_gain"]} / {effects["incumbent_loss"]}**;
strict lower-bound gains/losses are **{effects["strict_lower_bound_gain"]} / {effects["strict_lower_bound_loss"]}**.
The predeclared rule makes the production probe **{"enabled by default" if beneficial else "opt-in only"}**
with `compact_probe_seconds={default}`.

Every incumbent is replayed. A lower bound is strengthened only by a strictly
positive rationally repaired phase-I certificate. Timeout, MIP failure and
solver status alone remain inconclusive. All records and unresolved cases are
retained without relation witnesses.

This audit does not establish real membership truth, universal acceleration,
city-scale performance, noisy-answer robustness, privacy utility or operational
availability of disclosure facts. The paper and frozen Chicago/NYC results are
unchanged.
''')
    (OUT / "CLAIM_BOUNDARY.md").write_text('''# Claim boundary

This audit supports only the correctness and measured behavior of the compact
necessary-condition lower-bound probe on the frozen synthetic fixed-support
grid. It does not support universal speedup, city-scale performance, real
event-membership accuracy, unknown-support identification, nonlinear-target
certification, noisy-answer robustness, privacy guarantees, adaptive acquisition
cost, or operational availability of queried relation facts.

All raw statuses, losses, unresolved cells and timing variation remain in the
committed records. The manuscript and frozen Chicago/NYC evidence are unchanged.
''')

    write_checker()
    update_ci()
    upsert_readme(protocol, enabled, disabled, effects, default)

    (ROOT / "docs/COMPACT_EVENT_SLOT_PROBE.md").write_text(f'''# Compact event-slot lower-bound probe

For pure fixed-support minimum-event objectives, the solver may spend `{default}`
seconds by default on an at-most-K labeled event-slot outer relaxation. Every
physical world using at most K events maps into this relaxation. Only a strictly
positive rationally repaired phase-I lower bound can certify that K physical
events are impossible; feasibility of the relaxation has no converse meaning.

The frozen paired audit has {protocol["run_count"]} invocations. Exact status is
{enabled["exact_status_count"]}/{enabled["run_count"]} with the probe and
{disabled["exact_status_count"]}/{disabled["run_count"]} without it. See the
result directory for complete records, hashes and limitations. The probe remains
an implementation extension, not a manuscript contribution.
''')
    (ROOT / "docs/MANUSCRIPT_SCOPE_DECISION.md").write_text('''# Manuscript scope decision

As of 2026-09-05, the KDD manuscript remains centered on EventFrontier.
Selective disclosure and the compact probe are retained as audited research
extensions but are not inserted into the paper yet.

The extension has exact small-instance validation and synthetic sequential
stress tests, but still lacks real membership truth, noisy-answer guarantees and
evidence that the queried facts are operationally available. The scope decision
should be revisited after either a real event-membership benchmark or a closed
unknown-support/noisy-answer extension.
''')
    (ROOT / "docs/PROJECT_STATUS.md").write_text(f'''# Verified project status

Checkpoint: 2026-09-05, compact evidence repaired and repository converged.

The EventFrontier manuscript and frozen city evidence are unchanged: NYC has 24
windows, 21 eligible windows, 126 outcome-capacity cells and 14/18 scale
closures; Chicago run 164 has 60 cores, 611 candidates and 50,405 contributors.

The repository contains fixed-support implicit disclosure branch-and-price,
ex-post minimum certificate search, pricing acceleration, independent-seed
ablations and the compact event-slot lower-bound probe. The repaired compact
package contains {protocol["run_count"]} complete paired records. Probe exact
status is {enabled["exact_status_count"]}/{enabled["run_count"]}; disabled exact
status is {disabled["exact_status_count"]}/{disabled["run_count"]}. The frozen
rule sets the default budget to `{default}` seconds.

Only `ci.yml` and `chicago-live-audits.yml` are active workflows. CI verifies
compact hashes/default consistency, deterministic tests and the paper build.
Selective disclosure remains outside the manuscript pending real membership
truth or unknown-support/noisy-answer closure.
''')

    manifest = ROOT / "ARTIFACT_MANIFEST.md"
    text = manifest.read_text()
    heading = "## Compact event-slot lower-bound audit\n"
    if heading in text:
        text = text.split(heading)[0].rstrip() + "\n"
    hashes = {name: sha(OUT / name) for name in ("RUNS.json", "SUMMARY.json", "DEFAULT_DECISION.json", "REPORT.md")}
    text += f'''\n\n## Compact event-slot lower-bound audit

Separate implementation evidence, not frozen manuscript evidence:

- workflow run: `{os.environ["GITHUB_RUN_ID"]}`;
- protocol SHA-256: `{summary["protocol_sha256"]}`;
- final solver SHA-256: `{summary["solver_sha256"]}`;
- timed pre-default solver SHA-256: `{timed_solver_sha}`;
- compact probe SHA-256: `{summary["compact_probe_sha256"]}`;
- RUNS/SUMMARY/DEFAULT/REPORT SHA-256: `{hashes["RUNS.json"]}`, `{hashes["SUMMARY.json"]}`, `{hashes["DEFAULT_DECISION.json"]}`, `{hashes["REPORT.md"]}`.

The package retains all {protocol["run_count"]} records and selects
`compact_probe_seconds={default}` under the predeclared no-loss rule. It licenses
only synthetic fixed-support lower-bound behavior.
'''
    manifest.write_text(text)

    checklist = ROOT / "SUBMISSION_CHECKLIST.md"
    text = checklist.read_text()
    block = '''## Extension and repository hygiene

- [x] Compact code, paired records, summary, default decision and claim boundary
  are mutually hash-checked.
- [x] Only unified CI and manual Chicago auditing remain active workflows.
- [x] Selective disclosure is explicitly separated from the frozen manuscript.
- [ ] Revisit integration only after real membership truth or a closed
  unknown-support/noisy-answer extension.

'''
    if "## Extension and repository hygiene\n" not in text:
        text = text.replace("## Submission decision\n", block + "## Submission decision\n", 1)
    checklist.write_text(text)

    print(json.dumps({"beneficial": beneficial, "default": default, "effects": effects}, sort_keys=True))


if __name__ == "__main__":
    main()
