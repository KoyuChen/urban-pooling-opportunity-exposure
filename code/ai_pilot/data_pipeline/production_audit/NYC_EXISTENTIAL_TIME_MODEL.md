# NYC ordered latent runs with existential timestamp completion

## Why this Gate is needed

Replacing a released timestamp by its full outer envelope is not a monotone
relaxation when the same interval is used for both connectivity and simultaneous
occupancy. A wider envelope can create useful overlap bridges, but it can also
create artificial triple overlap and violate a capacity bound. The correct
release-consistent quantifier is instead:

> choose one latent exact pickup and drop-off inside each released support, and
> impose ordered-run constraints on that selected completion.

This Gate implements that existential quantifier exactly for a small continuous-
time audit cohort.

## Feasible worlds

For every public trip `i`, let

```text
s_i in [s_i^L, s_i^U],   e_i in [e_i^L, e_i^U],   e_i - s_i >= epsilon.
```

The exact model uses singleton supports. The artificial 15-minute model rounds
each public endpoint to the nearest 15 minutes and supplies an independent
`+/-7.5` minute support. The public exact timestamp is contained in that support.

Core trips are partitioned across latent runs and buffer trips are optional. A
run must contain at least two selected rows. The smallest-index core in a run is
its canonical formulation root; this removes only root-label symmetry.

## Connectivity

For a selected overlap edge `ij` in run `r`, the latent completion must satisfy

```text
s_i + epsilon <= e_j,
s_j + epsilon <= e_i.
```

A rooted single-commodity flow on selected overlap edges connects every member
of an open run to its canonical core root. The flow is a formulation device; it
is not interpreted as a vehicle route.

## Simultaneous capacity

Each selected interval is assigned to one of `C` seat tracks. Two rows assigned
to the same track must be temporally nonoverlapping. This is exact for interval
occupancy because interval graphs are perfect:

```text
maximum simultaneous occupancy <= C
```

if and only if the selected intervals admit a proper `C`-coloring. The seat
variables encode such a coloring with pairwise disjunctive nonoverlap
constraints.

## Monotonicity statements

For fixed timestamp supports and common selected-buffer cardinality `q`,

```text
F(t, 2, q) subseteq F(t, 3, q) subseteq F(t, 4, q).
```

For the artificial rounding experiment, singleton exact supports are contained
row by row in the coarse supports. Hence

```text
F(exact_singleton, C, q)
    subseteq
F(rounded_15m_existential, C, q).
```

Thus any root-invariant linear public-attribute query has weakly decreasing
lower endpoints and weakly increasing upper endpoints along both declared
relaxations. The implementation audits these implications and fails closed on a
certified reversal.

## Computational scope

This is a continuous-time mixed-integer formulation for a small audit cohort,
not the production-scale algorithm. The initial live Gate uses four core rows,
twelve candidate buffers, one selected buffer per core, and `C in {2,3,4}`.
Rows are selected by frozen source order and exact temporal proximity before
outcome optimization.

The formulation does not imply that the full multi-run problem is polynomial.
The previously derived totally-unimodular LP oracle applies to a fixed-span,
fixed-root single run. The present model solves the coupled multi-run and latent-
time problem directly at small scale; a decomposition algorithm remains a later
Gate.

## Claim boundary

The 15-minute supports are artificially generated from NYC public exact
timestamps. They are not asserted to be the TLC release mechanism. The model
selects feasible latent timestamp completions, but it does not recover actual
co-rider identities, vehicle runs, realized capacity, production matching logic,
or a NYC population estimand. Aggregate endpoint witnesses are replay-audited;
raw rows, row identifiers, and latent timestamp witnesses are not emitted.
