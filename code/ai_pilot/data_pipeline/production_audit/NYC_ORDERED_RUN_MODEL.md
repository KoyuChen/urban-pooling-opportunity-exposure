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

## Compact interval connectivity characterization

The first implementation used a generic single-commodity flow on overlap edges. That formulation is correct but unnecessarily large for interval graphs: with |R| candidate roots and |E| overlap edges it creates O(|R||E|) flow variables. The first eight-core live smoke therefore hit the 45-minute CI wall before emitting evidence. The current formulation removes edge-flow variables entirely.

Let tau_1,...,tau_T be the elementary open time segments induced by all released endpoints. For a candidate run R define

z_t(R)=1{some i in R is active on tau_t}.

For two adjacent segments tau_t=(a,b) and tau_{t+1}=(b,c), say that boundary b is bridged by R when at least one selected interval satisfies s_i < b < e_i.

### Proposition: exact segment characterization

For any nonempty set R of positive-length intervals, the positive-overlap graph G[R] is connected if and only if:

1. the active segment indicators z_1(R),...,z_T(R) form one consecutive block; and
2. every adjacent pair of active segments is bridged by at least one interval in R.

**Proof.** If G[R] is connected, take any path of positively overlapping intervals. Positive overlap prevents a path from crossing an internal released endpoint only by endpoint touching, so the union of the path has no inactive elementary segment and every internal active boundary is crossed by an interval. Taking the union over the connected graph gives conditions 1--2.

Conversely, within a fixed active elementary segment all selected intervals active there pairwise overlap and hence form a clique. At each adjacent active boundary, a selected interval crosses the boundary and belongs to the cliques on both sides. These crossing intervals link the consecutive segment cliques into one connected graph, so G[R] is connected. QED.

The implementation exhaustively checks this equivalence on a small interval library, including endpoint-touch counterexamples.

## Compact MILP

Use every selected core row r as a possible formulation root. Binary x_ir indicates that row i is assigned to run r, and y_r indicates that run r is open. Root identity is x_rr=y_r. Core rows satisfy sum_r x_ir=1; buffers satisfy sum_r x_ir<=1. Every open run has at least two members.

For every root r and elementary segment tau_t, binary z_tr records whether the run is active on that segment. Occupancy activation is enforced by

z_tr <= sum_{i active on tau_t} x_ir <= C z_tr.

Connectivity uses the proposition above. The z_tr sequence may have at most one 0-to-1 start, so its active entries form one block. For every adjacent active pair tau_t,tau_{t+1},

sum_{i: s_i < b_t < e_i} x_ir >= z_tr + z_{t+1,r} - 1,

where b_t is the shared endpoint. Thus endpoint-touch alone cannot join two pieces of a run.

This formulation has O(|R|(|V|+T)) assignment/segment variables and constraints after connected-component pruning, rather than O(|R||E|) flow variables. It is exact for the declared interval-connectivity rule; the improvement is computational, not a relaxation of the model.

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

The next statistical layer should add run-invariant outcome functionals, such as within-run pairwise dispersion or exposure, after the compact structural ordered-run gate is computationally stable.
