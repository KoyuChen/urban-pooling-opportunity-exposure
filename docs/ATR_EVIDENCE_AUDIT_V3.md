# ATR evidence audit v3

> Superseded by `ATR_EVIDENCE_ADVERSARIAL_REVIEW_V4.md`. This file preserves
> the first Gate 0 decision and must not be cited as the current evidence audit.

Date: 2026-09-06

## Decision

Gate 0 passes for the frozen DIAMOR dyad computation after a versioned repair.
The revised parser changes the DIAMOR-2 analysis, so v3 supersedes v2 for
scientific claims. The v2 files remain the comparison baseline and are not
silently rewritten as if their semantics had been unchanged.

This pass establishes source-format handling within the stated quarantine
policy, numerical endpoint witness replay, fail-closed status handling, and an
independent tiny-instance check. It does not establish label-free estimation,
candidate-support validity, a general ordered-event algorithm, or useful
decision yield.

## Source-semantics repair

The ATR format documents unknown/non-person negative IDs and a special
multiple-ID record grammar. The former parser skipped an entire group whenever
one listed member was nonpositive. Its documentation nevertheless said that all
larger-group members were excluded. The v3 parser instead:

- accepts only complete reciprocal positive-ID groups as dyad truth;
- excludes members of complete groups larger than two;
- quarantines every recoverable positive ID in partial/nonpositive and
  multiple-ID records;
- quarantines one-sided or conflicting memberships;
- reports every source category separately.

The known DIAMOR-1 partial-group example occurs before the frozen grid and does
not alter that day's results. On DIAMOR-2, conservative quarantine removes one
eligible snapshot and changes the true q or candidate cohort in additional
snapshots. This is a local but scientifically material revision.

## Certificate contract

For a feasible endpoint, v3 requires all of the following:

1. HiGHS returns optimal status rather than only a generic success flag.
2. The reported relative MIP gap is zero within `1e-10`.
3. The selected edge indices are unique and valid.
4. Replayed vertex degrees are at most one.
5. Replayed matching cardinality equals q.
6. The replayed objective matches the reported endpoint within `1e-8`.

Both endpoint witnesses, their hashes, solver status/message, primal/dual
diagnostics, node counts, software versions, and replay residuals are retained
in the controlled full report. A timeout with an incumbent and a nominal
success with nonzero gap both remain `UNRESOLVED` in regression tests.

For at most 12 visible vertices, an implementation-independent subset-recursion
oracle computes the exact cardinality-q matching endpoint or infeasibility.
All 195 eligible cells in this size range agree. This does not independently
check the larger cells, whose evidence consists of HiGHS optimality plus
witness replay.

## Revised frozen result

| Quantity | v2 | v3 | Delta |
|---|---:|---:|---:|
| Eligible snapshots | 171 | 170 | -1 |
| Radius cells | 855 | 850 | -5 |
| Solver-optimal / v3 replayed cells | 811 | 806 | -5 |
| Candidate-graph infeasible cells | 44 | 44 | 0 |
| Truth-representable cells | 774 | 769 | -5 |
| Conditional truth coverage | 774/774 | 769/769 | -5/-5 |
| Conditional point errors flagged | 64/64 | 68/68 | +4/+4 |
| Misspecified-support unflagged wrong decisions | 15 | 16 | +1 |
| Distinct snapshots with such unflagged errors | 7 | 8 | +1 |

At 5 m under valid support, v3 yields 410 ambiguous decisions among 495
predeclared threshold decisions (82.8%). Candidate support represents the
annotated world in 124/170 snapshots at 1 m, 157/170 at 1.5 m, and 165/170 at
5 m.

The 769/769 coverage and 68/68 conditional flagging are expected implications
of correct endpoint optimization when the annotated world belongs to the
feasible set. They are implementation checks, not independent evidence of
unconditional safety. The 16 unflagged wrong decisions under misspecified
support and the 82.8% ambiguity rate motivate Gate 1.

## Evidence locations

Disclosure-safe tracked artifacts:

- `code/ai_pilot/benchmarks/results/atr_diamor_truth/SUMMARY.json`
- `code/ai_pilot/benchmarks/results/atr_diamor_truth/REPORT.md`
- `code/ai_pilot/benchmarks/results/atr_diamor_truth/VERSION_DIFF.json`

Controlled local full reports:

- `/tmp/eventfrontier-atr/v3-diamor1/report.json`
- `/tmp/eventfrontier-atr/v3-diamor2/report.json`

The tracked summary records the full-report, source-data, protocol, and
benchmark hashes. Raw ATR rows, pedestrian IDs, and recovered relation
assignments are not committed.

## Next gate

Gate 1 must evaluate useful uncertainty rather than repeat conditional coverage:
query-independent point baselines, at least one non-objective-aligned query,
unknown-q regimes, radius-by-angle support diagnostics, false-certificate risk,
and certificate yield on a coherent denominator.
