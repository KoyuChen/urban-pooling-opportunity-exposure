# Projection-to-frontier theory audit

Gate: `PASS_PROJECTION_TO_FRONTIER_THEORY`.

## The distinction

For nested nonempty fixed-q event families, a selected-row additive objective
depends only on the 0--1 selected-buffer projection.  A restricted family has
the same frontier for one objective exactly when it contains a projected point
on each of the ordered family's exposed minimum and maximum faces.  It has the
same frontier for every additive row objective exactly when the two projected
0--1 sets are equal.  Equality of event-partition families is not required.

## Exact finite audit

- Fixed-cardinality projection cells: **14**
- Nested nonempty family pairs: **846**
- Integer-objective exposed-face checks: **503,310**
- Strict inclusions with constructive separators: **728**
- Mismatches: **0**

The coefficient grid is a regression audit, not the proof.  The universal
direction is proved constructively: for an omitted binary point z, coefficients
`+1` on its selected coordinates and `-1` elsewhere make z the unique maximizer.

## Minimal separation

At q=1, the restricted projection {100, 001} and ordered projection
{100, 010, 001} have the same frontier [0,2] for weights (0,1,2), while the
ordered-only point 010 has value 1 and is strictly interior.  The audit checks
that with only two buffers, no strict inclusion can have this property under
distinct weights.  A separate two-partition witness has one common projection,
showing how partition multiplicity can change without changing any selected-row
additive frontier.

## Claim boundary

This theorem does not cover partition-dependent objectives such as event count,
does not turn the frozen NYC null into family equivalence, and does not create a
post-hoc public-data query.  The frozen audit only establishes that its added
projections are interior for the two already declared objectives.
