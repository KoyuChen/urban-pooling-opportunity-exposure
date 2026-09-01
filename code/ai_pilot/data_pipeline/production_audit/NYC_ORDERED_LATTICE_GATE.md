# NYC ordered-run time-capacity lattice Gate

This Gate isolates two distinct public-data relaxations while holding the outcome estimand fixed:

1. **capacity relaxation**: `C=2 -> 3 -> 4`; and
2. **timestamp coarsening**: exact public seconds -> artificial 15-minute outer intervals.

The selected-buffer support is fixed at a predeclared **4.0 rows/core** (32 rows for the 8-core smoke cohort). It is not chosen from the outcome values and is below the previously certified coarse `C=2` maximum of 9.0/core.

Let `F(t,C,q)` be the feasible ordered latent-run worlds under public-time model `t`, declared capacity `C`, and exactly `q` selected buffer rows/core. For the two declared time models,

```text
F(exact_second, C, q) subseteq F(rounded_15m_outer, C, q)
```

because the outer release model only expands public intervals. For fixed `t`,

```text
F(t, 2, q) subseteq F(t, 3, q) subseteq F(t, 4, q).
```

Therefore any root-invariant linear public-attribute outcome has a two-dimensional monotonicity lattice:

- lower endpoints weakly fall under either relaxation;
- upper endpoints weakly rise under either relaxation.

The implementation audits both directions and fails closed on any certified reversal.

This is a conditional partial-identification result. It does not recover actual co-riders, realized vehicle runs, true capacity, or production matching logic. The 15-minute intervals are an artificial coarsening experiment, not an assertion about TLC's actual release operator.
