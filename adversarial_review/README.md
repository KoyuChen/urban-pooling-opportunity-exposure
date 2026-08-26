# Adversarial Audit Package

This directory records the restart-from-zero audit of repository commit
`9867029b5d3e97fd1346cbd8d11a052ab7f69e53`. Prior conversational judgments
were not treated as evidence. The frozen manuscript and PDF were not revised,
because the audit concludes that a coherent submission paper cannot yet be
supported by the available data and validation.

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

Run the local audit checks with:

```bash
python adversarial_review/counterexamples.py
python -m unittest discover -s code/ai_pilot/bounds/tests -v
```

The current suite contains 30 passing tests. Small-graph exhaustive solutions
are the exact audit oracle; SciPy/HiGHS results are treated as numerical.

## Decision

- Current KDD/transport manuscript: **NO-GO**.
- Research program: **CONDITIONAL GO**.
- First attainable target after repair and complete data: **Data Science for
  Transportation**.
- Strongest unimplemented route: a version-confirmed, endpoint-marginal
  suppression-aware partner/context model using all trips that contribute to
  the City's privacy buckets.

The currently accessible 2019 City clarification, associated with legacy
dataset IDs, describes separate pickup-time/tract and dropoff-time/tract
buckets, with paired tract removal when either bucket is small. It does not
establish an OD-tract-pair threshold, and its unchanged application to the
2025/2026 dataset has not been verified. Accordingly, the coupled model remains
a research route rather than a completed claim.
