# NYC ordered-run time-capacity semantics Gate

This Gate holds the outcome estimand fixed while varying:

1. **capacity**: `C=2 -> 3 -> 4`; and
2. **deterministic time representation**: exact public seconds versus artificial nearest-15-minute outer envelopes.

The selected-buffer support is fixed at a predeclared **4.0 rows/core** (32 rows for the 8-core smoke cohort). It is not selected from outcome values and is below the previously certified coarse `C=2` maximum of 9.0/core.

## Capacity remains a genuine nested relaxation

For either fixed deterministic time model `t`, let `F(t,C,q)` be the feasible ordered-run worlds at capacity `C` and exactly `q` selected buffer rows/core. Then

```text
F(t, 2, q) subseteq F(t, 3, q) subseteq F(t, 4, q).
```

Therefore lower endpoints must weakly fall and upper endpoints must weakly rise with `C`. The implementation continues to audit and fail closed on a certified capacity reversal.

## Outer-envelope substitution is not a release relaxation

The previous draft incorrectly asserted

```text
F(exact_second, C, q) subseteq F(rounded_15m_outer, C, q).
```

That statement is false when each outer envelope is treated as the trip's realized active interval. Expanding intervals has two opposing effects:

- it creates additional positive-overlap bridges, which relaxes connectivity; but
- it can create artificial simultaneous occupancy, which tightens the capacity constraint.

A simple `C=2` counterexample is the exact chain

```text
[0,2), [1,3), [2,4)
```

whose positive-overlap graph is connected and whose maximum simultaneous occupancy is two. Expanding these intervals to

```text
[-1,3), [0,4), [1,5)
```

creates depth three and makes the envelope set infeasible at `C=2`, even though the original exact completion remains feasible.

Thus the outer-envelope model is a deterministic robust sensitivity model, not a monotone partial-identification relaxation.

## Correct release-consistent quantifier

For coarsened timestamps, the release-consistent feasible-world set must select latent exact endpoints inside each released support and then impose connectivity and occupancy on that selected completion:

```text
there exists a latent timestamp completion consistent with the release
such that the ordered-run constraints hold.
```

If every fine timestamp support is contained in its coarse support, this **existential-completion** world set is nested by construction. Enforcing occupancy directly on the outer envelopes instead corresponds to a stronger universal/robust requirement and can delete valid exact worlds.

## Current interpretation

The current two-time-model computation therefore reports:

- certified capacity frontiers within each fixed time model; and
- a cross-time deterministic-model diagnostic with no feasible-set containment claim.

The next methodological Gate is an existential latent-time completion formulation. None of these models recover actual co-riders, realized vehicle runs, true capacity, or TLC production matching logic. The 15-minute intervals remain an artificial stress test rather than an assertion about TLC's actual release operator.
