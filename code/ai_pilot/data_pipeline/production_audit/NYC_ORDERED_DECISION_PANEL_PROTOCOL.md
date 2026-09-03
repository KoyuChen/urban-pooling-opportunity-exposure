# Predeclared NYC outcome and point-decision panel

## Question

The run-count panel shows that seconds-level public timestamps can leave the
number of hidden ordered events identified only by physical capacity bounds.
This stage asks the downstream question: **which aggregate outcome conclusions
survive every event decomposition, and which are artifacts of one point
reconstruction?**

## Frozen windows

The panel reuses the 24 scan windows declared for the exact-second ordered-run
panel: four seasons, weekday/weekend regimes, morning/midday/evening dayparts,
20 eight-core cells, and four sixteen-core weekday-evening stress cells. A scan
window that contains no integrity- and cap-qualified cohort is retained in the
predeclared denominator as `INELIGIBLE_NO_QUALIFIED_CORE`; it is not replaced
post hoc.

## Fixed-support estimand

For each eligible window, the target support is one selected buffer row per
ordered core. Starting from that target and using no outcome values, the
pipeline searches downward under the strictest capacity, `C=2`, until it
certifies a positive feasible selected-buffer count `q`. The same `q` is then
held fixed for `C=2,3,4`. Thus capacity comparisons relax only the feasible
relation world; they do not change the support cardinality or the estimand.

The two headline queries are:

1. mean public trip miles among the `q` selected buffer rows; and
2. mean public trip minutes among the `q` selected buffer rows.

For each query, the decision threshold is the median public attribute among all
eligible buffer candidates in that window. This threshold rule is declared
before frontier optimization and does not use a reconstructed event relation.

## Point reconstructions

Four deterministic point methods are evaluated on the same public rows:

- one-to-one core-buffer matching minimizing midpoint distance;
- one-to-one core-buffer matching lexicographically favoring zone agreement and
  overlap;
- a feasible ordered-event world maximizing an additive temporal score; and
- a feasible ordered-event world maximizing a zone-plus-overlap score.

The pair baselines are reported only when the fixed support equals the number of
cores and a positive-overlap perfect core-buffer matching exists. The ordered
baselines are solved under the full `C=2` event model and are therefore feasible
under all larger capacities. Every certified point value is replayed and must
lie inside the corresponding certified outer frontier enclosure.

## Reported knowledge-discovery diagnostics

For every outcome-capacity cell, the pipeline reports:

- exact endpoints when both integer solves close;
- otherwise a rigorous outer endpoint enclosure and inner feasible witnesses;
- whether all feasible worlds lie above the candidate-median threshold, all lie
  below it, or certified worlds occur on both sides;
- whether deterministic point methods disagree on the threshold decision; and
- frontier width relative to the candidate interquartile range.

A point method always returns a side of the threshold. `EventFrontier` answers
the different question of whether that side is invariant to all admissible
relation completions.

## Claim boundary

This is a public-data feasible-world audit. It does not recover actual
co-riders, vehicle runs, referral members, household identities, realized
capacity, proprietary matching logic, or population prevalence. Public-data
point methods cannot be assigned an accuracy rate because operational event
membership is absent. Candidate-universe recall remains an assumption-indexed
quantity and is evaluated separately in the controlled-truth benchmark.
