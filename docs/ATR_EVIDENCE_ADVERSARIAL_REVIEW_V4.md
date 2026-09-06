# ATR D1--D3 adversarial review v4

Date: 2026-09-06

## Verdict

The original v3 Gate 0 implementation did not survive adversarial review
unchanged. Two material implementation gaps and one fail-open reporting gap
were found and repaired:

1. conflicting annotation IDs were quarantined without closing quarantine over
   all partners in the affected groups;
2. witness objective replay did not compare the rounded witness with the raw
   solver vector, solver objective, or dual bound;
3. the summary generator could write a PASS narrative without first rejecting
   a HOLD or cross-protocol input pair.

After repair, v4 passes the strengthened checks. The additional conflict
closure quarantines three more IDs on each DIAMOR day but does not change any
frozen scientific headline relative to v3. Relative to the original v2,
DIAMOR-2 still loses one eligible snapshot and several q-conditioned cells.

Gate 0 is therefore **PASS at v4**, with the limitations below. This verdict is
about data-semantics hygiene and numerical evidence integrity; it is not a pass
for external validity, usefulness, novelty, or the ordered-event algorithm.

## Attack 1: quarantine closure

### Counterexample

Suppose ID 1 is reciprocally listed in dyads `{1,2}` and `{1,3}`. The ATR source
warns that the same tracking ID may refer to different pedestrians in different
groups. Quarantining only ID 1 leaves IDs 2 and 3 in the visible candidate
population even though their annotated relations are no longer interpretable.
They can then enter as apparent singletons.

### Repair

v4 forms all reciprocal positive groups, detects IDs with multiple group
memberships, and quarantines the union of every affected group. One-sided
groups are also quarantined as a whole. Regression tests verify that an
unrelated valid dyad remains usable.

The documented `-2` and `-3` mobility-aid type prefix is now parsed explicitly.
Recoverable positive group partners are quarantined. Truncated records quarantine
every recoverable ID within the declared group-member segment.

### Frozen-source effect

| Quantity | DIAMOR-1 | DIAMOR-2 |
|---|---:|---:|
| Conflicting IDs | 3 | 4 |
| Members in affected conflict groups | 15 | 10 |
| Total quarantined IDs | 407 | 430 |
| Increase from v3 | +3 | +3 |
| Scientific headline changed from v3 | No | No |

## Attack 2: rounded-witness replay

### Counterexample

The v3 replay selected every raw solver coordinate above 0.5, recomputed the
objective from those selected edges, and compared that value with the same
recomputed value. A fractional raw vector or an inconsistent solver objective
could therefore pass the rounded combinatorial witness test in isolation.

### Repair

An endpoint is published only when all of these conditions hold:

- solver status is optimal and reported relative MIP gap is at most `1e-10`;
- the rounded witness has valid edge indices, degree at most one, and exactly q
  edges;
- the raw vector has integrality, cardinality, and maximum-degree residual at
  most `1e-8`;
- the signed rounded-witness objective agrees with `result.fun` within `1e-8`;
- the solver dual bound agrees with `result.fun` within `1e-8`.

If solver status is nominally optimal but any check fails, the endpoint value is
set to `null` and its status is `UNRESOLVED`. A separately named incumbent may
be retained for diagnostics; it is never serialized as a certified frontier
endpoint.

On the frozen v4 run, maximum observed raw integrality residual is zero and the
largest solver-objective or primal--dual residual is approximately
`8.9e-16`.

## Attack 3: solver/oracle differential tests

The deterministic unit battery now includes 25 random graphs and both endpoint
directions. An additional one-off adversarial campaign checked 1,000 endpoints
on seeded random general graphs with 2--10 vertices, variable density,
cardinality, infeasibility, and signed edge weights. The MILP status/value
matched the independent subset-recursion oracle in every case.

This is meaningful implementation evidence but not a formal verification of
HiGHS. In the frozen real audit, the independent oracle runs only when there are
at most 12 visible vertices: 195/195 cells pass. Larger cells retain solver
optimality plus strengthened primal/dual and witness replay, not an independent
combinatorial optimum.

## Attack 4: fail-open summary generation

The disclosure-safe summary now rejects:

- either current report with any non-PASS computation/semantic/replay/oracle
  component;
- disagreement between serialized and declared cell counts;
- unreplayed exact endpoints or failed tiny checks;
- duplicate dataset days;
- different protocol or benchmark hashes across days.

Regression tests inject a HOLD report and cross-protocol reports and require
generation to fail.

## v4 frozen evidence

| Metric | v4 result |
|---|---:|
| Eligible snapshots | 170 |
| Radius cells | 850 |
| Replayed numerical optima | 806 |
| Candidate-graph infeasible | 44 |
| Truth-representable cells | 769 |
| Conditional truth coverage | 769/769 |
| Conditional point errors flagged | 68/68 |
| Misspecified-support unflagged wrong decisions | 16 |
| Distinct snapshots with those unflagged errors | 8 |
| Independent tiny-oracle checks | 195/195 |
| Valid-support ambiguity at 5 m | 410/495 (82.8%) |

All four report components are PASS for both days: computation, endpoint-status
consistency, witness replay, and independent tiny-oracle agreement.

## Remaining attacks that Gate 0 does not answer

1. **Annotation error.** The source uses one coder; v4 treats labels as an
   annotated reference, not error-free latent reality.
2. **Unknown q.** The true dyad count still comes from labels.
3. **Selection leakage.** Labels still determine larger/uncertain-group
   exclusion and snapshot eligibility.
4. **Support validity.** Candidate radius and angle can omit true dyads; v4
   documents the resulting failures but does not calibrate support out of sample.
5. **Decision usefulness.** 82.8% ambiguity at the widest radius may make the
   guarantee uninformative.
6. **Baseline strength.** Minimum-distance reconstruction is the lower endpoint
   of the same query, not an independently trained relation estimator.
7. **Algorithm transfer.** This experiment validates cardinality-q matching,
   not the distinctive higher-cardinality ordered-event pricing oracle.

These belong to Gates 1 and 2. More repetitions of conditional 769/769 coverage
would not resolve them.

## Scientific role after adversarial review

ATR is not a third city audit and not an external-validation claim. It is the
annotated-relation stress-test layer between controlled truth and relation-free
public releases:

| Evidence layer | What it can establish | What it cannot establish |
|---|---|---|
| Controlled generator | Logical coverage and decision-certification mechanism under exact truth | Presence of the failure mode in independently collected relations |
| ATR annotated dyads | Whether a real annotated relation survives candidate support; the coverage--ambiguity trade-off when support expands | Operational matching accuracy, unknown-q performance, or ordered-event scalability |
| Chicago/NYC releases | Release-specific ambiguity, extraction closure, and computational scale | Truth coverage, because relation identities are absent |

Accordingly, `769/769` conditional coverage and `68/68` conditional flagging are
positive controls. The non-tautological ATR evidence is that only 124/170
eligible snapshots retain the full annotated world at 1 m, that support
expansion raises this to 165/170 at 5 m while leaving 410/495 valid-support
decisions ambiguous, and that support misspecification produces 16 unflagged
wrong point decisions across eight snapshots. These quantities show why
candidate construction must be an explicit scientific gate rather than an
unreported preprocessing choice.
