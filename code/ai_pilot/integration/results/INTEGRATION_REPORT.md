# AI pilot integration benchmark

> **Diagnostic-only full feature map.** These locked outputs use the original
> 28-feature weak-MIL model. A post-lock audit found that tract-equality
> features mechanically encode the synthetic same-income target. Do not use
> the apparent sharpness below as the primary result. The primary 22-feature
> no-equality rerun is reported in
> `../ablations/no_geography_equality_20260825/results/ABLATION_REPORT.md`.

## Result

This is a **known-truth synthetic integration test**, not a Chicago finding.
The model was trained on 2026-01-20 and evaluated once on the locked
holdout day 2026-01-27.  Public-like timestamps were rounded to
15 minutes; hidden pair IDs and income bins were never supplied to model fitting.

- Held-out supported-node Brier: transparent rule **0.0605**;
  weak-MIL AI **0.0051**; relative improvement
  **91.5%** (PASS against the 10% gate).
- Hidden true-edge candidate recall: **100.0%**
  (PASS against the 95% gate).
- Conditional true-edge ranking: AI MRR **0.775** and
  top-1 **64.4%**, versus rule MRR
  **0.781** and top-1
  **67.5%**.
- Hidden same-income-bin pair share on the holdout was **0.562**.

## Set-packing bounds

| Candidate restriction | Interval | Width | Width reduction | Contains truth | True packing meets score floor |
|---|---:|---:|---:|---:|---:|
| untrimmed_candidate_graph | [0.050, 0.775] | 0.725 | 0.0% | True | True |
| transparent_rule_retention_0.90 | [0.338, 0.775] | 0.438 | 39.7% | True | True |
| weak_mil_ai_retention_0.90 | [0.525, 0.775] | 0.250 | 65.5% | True | True |
| transparent_rule_retention_0.95 | [0.438, 0.750] | 0.312 | 56.9% | True | False |
| weak_mil_ai_retention_0.95 | [0.613, 0.775] | 0.162 | 77.6% | False | False |

The untrimmed interval is conditional on the physical candidate rules.  The 90% and
95% intervals add an explicit model-score-retention restriction; they are sensitivity
sets, not confidence intervals.  “Contains truth” is meaningful here only because the
synthetic generator stored the true matching out of model view.

Two negative checks matter.  First, despite much better node calibration, the AI did
**not** improve top-1 true-edge ranking over the rule (64.4% vs
67.5%); the weak node objective is not a pair-ranking guarantee.
Second, the 95% AI score restriction excluded the hidden truth because the true
packing achieved less than 95% of the model-optimal score.  The 90% sensitivity set
retained truth, while narrowing the untrimmed interval.  A hard high-score cutoff
therefore cannot be treated as identified without repeated coverage validation.

## What this establishes—and what it does not

The run verifies that the actual weak-MIL and MILP components interoperate, that a
held-out node benchmark can be computed without pair-label leakage, and that synthetic
pair recovery and SES-bound coverage can be audited.  It does **not** establish true
co-rider links, personal income, social homophily, or an echo chamber in Chicago.  A
complete real authorized-trip day and ACS join are still required for an empirical
opportunity-exposure result.

The synthetic generator intentionally makes matched and unmatched compatibility
patterns separable enough to test software behavior.  Its large node-level gain is
not a transportable performance estimate for City of Chicago data.

Design parameters were fixed in `DESIGN_LOCK.json` before the held-out run.  No
holdout-driven tuning was performed.
