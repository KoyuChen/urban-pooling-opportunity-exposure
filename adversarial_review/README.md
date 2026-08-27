# Adversarial Audit Package

This directory records the restart-from-zero audit of repository commit
`9867029b5d3e97fd1346cbd8d11a052ab7f69e53` and the subsequent KDD Research
method pivot. Prior conversational judgments were not treated as evidence. The
original Chicago manuscript remains frozen in the historical record. The
current paper is a separate method working draft; it does not convert the
missing Chicago evidence into a scientific result.

## Post-pivot decision — 2026-08-27

- Immediate KDD submission: **NO-GO**.
- KDD Research development program: **CONDITIONAL GO**.
- Strongest surviving increment: an exact score-aware temporal-frontier
  algorithm with witness recovery, a pathwidth-two weak-hardness boundary, and
  a certified outward score relaxation for a declared release-coupled world
  model.
- Unchanged blockers: no production observation-operator compiler, verified
  current Chicago suppression mechanism, complete-day width/runtime profile,
  or external relation-truth benchmark.

## Required artifacts

- `approach_registry.md`: independent approach families, blocked routes, and
  reopening conditions.
- `issue_ledger.md`: claim-level severity, counterexample, repair, and current
  status.
- `nearest_predecessors.md`: primary-source novelty audit.
- `identification_audit.md`: observation operator, formal results,
  counterexamples, and surviving conditional claims.
- `empirical_gate_report.md`: reproduction record and evidence gates.
- `venue_decision.md`: no-go/conditional-go decision and venue-specific gates.

## Executable audit evidence

- `counterexamples.py` verifies noisy-OR edge nonidentification, failure of a
  joint node-product interpretation, nonconvex attainable scalar sets,
  score-scale instability, missing-context and FWL identities, and a toy
  suppression-coupling example.
- `../code/ai_pilot/bounds/structured_matching_bounds.py` implements only the
  formal repairs that survived audit: distinct signed endpoint objectives,
  independent missing-context envelopes, fixed-design FWL weights, normalized
  within-score regret floors, and Gamma candidate-miss sensitivity.
- The bounds test suite now distinguishes exact `OPTIMAL`, floating-point
  `NUMERICALLY_OPTIMAL`, `PROVEN_INFEASIBLE`, and `UNRESOLVED`; time limits and
  numerical infeasibility reports are not promoted to exact certificates.
- `../code/ai_pilot/bounds/path_frontier_dp.py` implements the exact temporal
  frontier and outward score certificate with exact rational arithmetic and
  replayed endpoint witnesses.
- `../code/ai_pilot/benchmarks/path_frontier_benchmark.py` runs the locked
  34-case structural benchmark and records hashes, oracle agreements, state
  growth, and the relaxation inclusion check.
- `../code/ai_pilot/bounds/conformal_matching.py` now freezes the score range
  across Gamma sensitivities and uses the same declared rational scorer in
  calibration and the exact optimizer.

Run the local audit checks with:

```bash
python adversarial_review/counterexamples.py
python -m unittest discover -s code/ai_pilot/bounds/tests -v
```

The current suite contains 72 passing tests. Small-graph exhaustive solutions
are the exact audit oracle; SciPy/HiGHS results are treated as numerical.

## Decision

- Original Chicago manuscript: **NO-GO**.
- Current KDD Research working draft: **CONDITIONAL GO for development; NO-GO
  for immediate submission**.
- Primary target if the algorithm, external-truth, and production gates pass:
  **KDD Research**.
- Fallback if only a complete and material Chicago measurement result survives:
  **Data Science for Transportation**.

The currently accessible 2019 City clarification, associated with legacy
dataset IDs, describes separate pickup-time/tract and dropoff-time/tract
buckets, with paired tract removal when either bucket is small. It does not
establish an OD-tract-pair threshold, and its unchanged application to the
2025/2026 dataset has not been verified. Accordingly, Chicago
mechanism-specific claims remain a research route rather than a completed
claim; the abstract paired-threshold compiler in the method paper is explicitly
not asserted to be the current City operator.
