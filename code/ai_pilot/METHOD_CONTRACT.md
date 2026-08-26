# AI pilot method contract

## Scientific target

The pilot asks whether privacy-coarsened public ride-pooling records contain
enough information to bound **compatibility-weighted socioeconomic opportunity
exposure**.  It does not estimate rider identity, actual co-presence, personal
income, attitudes, or an echo chamber.

Chicago reports one row per customer trip, rounded start/end times, coarse
origin/destination geography, whether sharing was authorized and matched, and
the number of customer trips in the whole shared service chain.  It omits the
chain/group identifier.  The missing group assignment is therefore treated as
a latent constrained structure rather than filled in as if it were observed.

## Pilot estimand

For trips with `shared_trip_match = true` and `trips_pooled = 2`, let an
admissible edge connect two records that could have belonged to the same
two-trip service chain under declared temporal, spatial, directional, and
route-compatibility rules.  Each retained trip may be incident to exactly one
selected edge.  For pickup-tract ACS median income, the pilot reports the
minimum and maximum across feasible coverings of:

- the share of selected edges whose origins fall in the same income quintile;
- the mean absolute difference in log tract income.

These are **admissible-set bounds conditional on the candidate rules**, not
nonparametric identification bounds.  Both the untrimmed rule graph and an
AI-trimmed graph are reported.

## AI component

The primary learned edge score receives 22 continuous compatibility features
and excludes all community-area and census-tract equality indicators, their
interactions, and all ACS/SES variables. The original 28-feature score is
diagnostic only because tract equality mechanically reproduces the SES target
in the locked generator. There are no edge labels. Training uses trip-level
match indicators as weak supervision:
each matched trip is a positive bag that should contain at least one plausible
incident edge, while an unmatched trip is a negative bag.  The node likelihood
aggregates incident edge probabilities with a noisy-OR.  Exact one-edge
consistency for the two-trip analysis is imposed later by set-packing, not
silently treated as a training label.  A transparent hand-built compatibility
score is the baseline.

The learned score is evaluated out of day at the **node level** with Brier
score, log loss, ROC AUC, and calibration. Hidden synthetic pairs are used
after fitting for a known-truth ranking audit; a predicted edge is never
treated as an observed public-data co-rider pair.

## Validation layers

1. Complete Chicago authorized-trip days prevent the 1/256 feasibility sample
   from mechanically omitting almost every possible counterpart.  The supplied
   extractor enforces this requirement; if API access is blocked, the real
   sample is limited to a non-substantive mechanics check.
2. A known-truth synthetic market tests candidate recall, true-edge ranking,
   feasibility, bound coverage, and bound width after 15-minute/geographic
   coarsening.
3. Complete-day Chicago data are planned to produce an empirical stress test
   and opportunity-exposure bounds, with sensitivity to candidate and score
   thresholds. They are not yet available in this artifact.

## Pre-declared pilot gates

- At least 10% lower held-out node Brier score than the transparent rule.
- At least 95% synthetic true-edge recall in the candidate graph.
- At least 90% synthetic bound coverage across replications.
- At least 25% narrower Chicago SES interval than the untrimmed admissible
  graph, without breaking the exact-cover feasibility condition.

Failure is a result: the project then stays descriptive or moves to data with
an observed group identifier.  A passing pilot supports scaling the structured
inference method; it does not by itself validate a causal policy claim.
