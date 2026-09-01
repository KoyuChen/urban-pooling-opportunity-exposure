# NYC ordered latent-run model

## Goal

NYC HVFHV does not publish a co-rider ID, run ID, vehicle ID, or realized pool size. A valid shared vehicle run can therefore contain more total riders than the maximum simultaneous occupancy: rider A may leave before rider C joins, while A--B and B--C overlaps keep the run temporally connected.

The pairwise and anchored-group models are retained as benchmarks. This note defines the next object: a connected interval-run decomposition with bounded simultaneous occupancy.

## Public objects

Each public matched trip i has an interval I_i=[s_i,e_i), provider, pickup/drop-off Taxi Zones, and trip outcomes. For a fixed core C0 and a declared finite candidate universe V, let G=(V,E) be the positive-overlap interval graph,

E={ {i,j}: max(s_i,s_j) < min(e_i,e_j) }.

Only runs intersecting C0 are modeled; unused buffer rows remain outside the displayed decomposition.

## Ordered latent run

A run R subseteq V is admissible at capacity C when:

1. R intersects C0;
2. |R| >= 2;
3. the induced overlap graph G[R] is connected; and
4. for every elementary time segment tau between consecutive released endpoints,

   sum_{i in R} 1{I_i covers tau} <= C.

Condition 3 allows sequential chains. In particular, A--B--C may form one run even if A and C never overlap. Condition 4 constrains simultaneous occupancy, not total run cardinality.

A decomposition is a collection of disjoint admissible runs such that every core row belongs to exactly one run; a buffer row belongs to at most one run.

## Flow-MILP

Use every selected core row r as a possible run root. Binary x_ir indicates that row i is assigned to run r, and y_r indicates that run r is open. Root identity is x_rr=y_r. Core rows satisfy sum_r x_ir=1; buffers satisfy sum_r x_ir<=1. Every open run has at least two members.

Connectivity is imposed with a single-commodity flow on the directed version of E. For every root r, non-root selected member i consumes one unit of flow; r supplies sum_i x_ir-y_r units. Flow is allowed only on positive-overlap edges and only between rows assigned to r. Hence the selected rows for each open root form a connected interval subgraph.

For every elementary segment tau and root r,

sum_{i active on tau} x_ir <= C y_r.

This is a polynomial-size MILP in the declared candidate universe. It avoids exponential enumeration of connected subsets.

## Structural sharp endpoints

The first live gate optimizes three linear structural quantities under C in {2,3,4}:

- run count per core: sum_r y_r / |C0|;
- selected buffer rows per core: sum_{i in buffer,r} x_ir / |C0|;
- companion mass per core: (sum_{i,r} x_ir - sum_r y_r) / |C0|.

The feasible sets are nested in capacity,

F_2 subseteq F_3 subseteq F_4,

so every minimum must weakly decrease and every maximum weakly increase with C. This is a fail-closed audit.

## Claim boundary

This model is still conditional on the declared public candidate universe and released intervals. It does not recover actual vehicle runs, establish partner recall, validate TLC/provider production data, or assert a true NYC capacity. The roots are formulation devices and are not interpreted as first riders or vehicle identifiers.

The next statistical layer should add run-invariant outcome functionals, such as within-run pairwise dispersion or exposure, after the structural ordered-run gate is computationally stable.
