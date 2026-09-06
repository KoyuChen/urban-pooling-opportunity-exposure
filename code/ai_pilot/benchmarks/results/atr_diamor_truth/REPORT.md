# ATR DIAMOR dyad evidence audit v4

Status: **PASS for computation, endpoint consistency, witness replay, and the independent tiny oracle.**

This remains an oracle-assisted, q-conditioned audit. Candidate edge scoring is label-blind, but annotations are used for cohort exclusion, eligibility, the true dyad count q, and final evaluation.

## Frozen result

- 170 eligible snapshots and 850 radius cells.
- 806 cells have replayed numerical MILP optima; 44 are candidate-graph infeasible.
- Truth is representable in 769 cells and covered in 769 of those cells.
- The minimum-distance point rule makes 68 threshold errors under valid support; all are ambiguous by construction.
- Under misspecified support, 16 wrong point decisions are not flagged, across 8 snapshots.
- At 5 m under valid support, 410/495 (82.8%) threshold decisions are ambiguous.
- 195 cells are cross-checked by an independent subset-recursion oracle.

The conditional coverage and conditional error flagging are implementation checks implied by optimizing over a feasible set that contains truth. They are not independent evidence of transfer or unconditional safety.

## Version change

The v4 parser understands the documented record layout sufficiently to quarantine all recoverable positive IDs in partial/nonpositive, mobility-aid, multiple-ID, one-sided, or conflicting annotations. Conflict quarantine closes over every affected group, so uncertain partners cannot re-enter as presumed singletons. DIAMOR-1 headline counts are unchanged. Relative to v2, DIAMOR-2 loses one eligible snapshot and changes several q-conditioned cells; the exact deltas are in `VERSION_DIFF.json`.

The v4 replay additionally checks the raw solver vector, objective, dual bound, cardinality, degree, and integrality residuals. Full local reports contain index-based witnesses and solver diagnostics. Raw pedestrian IDs and relation assignments are not published in this summary.
