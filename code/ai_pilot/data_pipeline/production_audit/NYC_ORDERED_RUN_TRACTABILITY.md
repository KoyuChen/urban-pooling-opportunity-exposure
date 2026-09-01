# Ordered latent runs: interval structure and tractable single-run subproblems

## Scope

This note isolates the algorithmic structure created by the ordered-interval model. It does **not** claim that the full multi-run decomposition is polynomial-time solvable, and it does not make a hardness claim. The result below is for one rooted latent run with a fixed released temporal span and linear row weights.

Each public trip is a positive-length half-open interval \(I_i=[s_i,e_i)\), with all endpoints drawn from a finite ordered grid

\[
t_0<t_1<\cdots<t_T.
\]

Let the elementary open segments be \(\tau_k=(t_{k-1},t_k)\), \(k=1,\ldots,T\). For every internal boundary \(t_k\), say interval \(i\) bridges it when \(s_i<t_k<e_i\).

For a selected set \(R\), positive-overlap connectivity means that the graph with an edge \(ij\) whenever \(\max(s_i,s_j)<\min(e_i,e_j)\) is connected. Simultaneous occupancy is bounded by \(C\).

## Lemma 1: connectivity as segment coverage plus bridge coverage

Fix two grid indices \(a<b\). A selected set \(R\) has temporal union exactly \((t_a,t_b)\) and a connected positive-overlap graph if and only if:

1. every segment \(\tau_k\), \(k=a+1,\ldots,b\), is covered by at least one selected interval;
2. every internal boundary \(t_k\), \(k=a+1,\ldots,b-1\), is bridged by at least one selected interval; and
3. no selected interval is active on a segment outside \((t_a,t_b)\).

The first condition removes temporal gaps. The second excludes the endpoint-touch counterexample in which one interval ends exactly when another begins. The third fixes the declared span rather than allowing the selected union to extend beyond it.

**Proof.** Necessity follows from connectedness of the positive-overlap graph and the fact that a path of positively overlapping intervals cannot cross a temporal gap or an internal boundary using endpoint touching alone. Conversely, the selected intervals active on any one elementary segment form a clique. A bridging interval belongs to the cliques on both adjacent segments, so the consecutive segment cliques are linked into a connected graph. Conditions 1 and 3 make the union exactly the declared span. \(\square\)

## Lemma 2: the augmented interval-incidence matrix has the consecutive-ones property

Interleave segment positions and internal boundaries in temporal order:

\[
\tau_1,\ t_1,\ \tau_2,\ t_2,\ldots,\ t_{T-1},\ \tau_T.
\]

For each trip \(i\), put a 1 in a segment row when \(I_i\) covers that elementary segment and a 1 in a boundary row when \(I_i\) bridges that boundary. Then the 1s in every trip column are consecutive in the interleaved row order.

Therefore the augmented 0--1 incidence matrix is an interval matrix and is totally unimodular.

**Reason.** Once interval \(I_i\) becomes active, it covers every elementary segment until it ends; it bridges every strictly interior grid boundary between those segments. There cannot be a 0 between two 1s in the interleaved order. A binary matrix with consecutive 1s in every column is totally unimodular. \(\square\)

## Proposition: fixed-span rooted single-run linear optimization is polynomial

Fix:

- a root trip \(r\) that must be selected;
- a released temporal span \((t_a,t_b)\);
- capacity \(C\ge 1\); and
- arbitrary rational weights \(w_i\).

Consider the problem

\[
\max \sum_i w_i x_i
\]

subject to:

- \(x_r=1\);
- selected intervals do not extend the active union outside \((t_a,t_b)\);
- every elementary segment inside the span has occupancy between 1 and \(C\);
- every internal boundary inside the span has at least one selected bridging interval; and
- \(0\le x_i\le 1\).

The LP relaxation has an integral optimum. Hence the fixed-span rooted single-run problem with a linear objective is solvable in polynomial time by linear programming (equivalently, by a network-flow representation of an interval matrix).

**Proof.** After removing intervals that would extend the active union outside the fixed span, the remaining segment and bridge constraints have the augmented interval-incidence matrix from Lemma 2. This matrix is totally unimodular. Adding the unit equality \(x_r=1\) and variable bounds preserves total unimodularity. With integral right-hand sides, every extreme point is integral, so an LP optimum can be chosen binary. \(\square\)

## Corollary: the at-least-two-members rule remains polynomial

The ordered-run definition requires at least two members. For a fixed root, this can be handled without adding a potentially TU-breaking cardinality row: enumerate one forced companion \(j\ne r\), add \(x_j=1\), solve the LP above, and take the best feasible value. There are only \(O(n)\) such companion choices.

If the run span is not fixed, enumerate \((a,b)\). There are \(O(T^2)\) spans. Thus a rooted single-run linear oracle remains polynomial under the model's positive-overlap connectivity and occupancy-capacity constraints.

## What this result does and does not buy us

This proposition explains why the interval structure is more than a modeling convenience. For one run, the connectivity and capacity constraints collapse to a totally-unimodular interval system rather than a generic graph-connectivity MILP.

The **full decomposition** is different. Core rows must be partitioned across multiple runs and buffer rows can be used by at most one run. Those cross-run assignment constraints couple several otherwise tractable single-run polytopes. The present note therefore makes no claim that the full decomposition is polynomial, and it makes no NP-hardness claim.

The practical implication is a decomposition route:

1. use the exact LP oracle to optimize or price one candidate run;
2. use column generation / branch-and-price or a master set-partitioning model for the multi-run decomposition; and
3. compare this against the current compact root-indexed MILP on the same smoke cohort.

That is a concrete algorithmic next step for the KDD version because it separates the interval-specific tractable subproblem from the combinatorial coupling across latent runs.

## Claim boundary

The theorem is about the declared public interval model only. It does not recover actual co-rider identities, actual vehicle runs, realized vehicle capacity, or TLC/provider matching logic. It also does not imply that the current full identification problem is polynomial-time solvable.
