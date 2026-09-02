# Exact integer decomposition for ordered latent runs

## Master problem

Let `R_C` be the family of feasible exact-time, capacity-`C` run columns. Each
column contains at least one core row, at least two total rows, a connected
positive-overlap graph, and simultaneous occupancy at most `C`. The integer
support master is

```math
\max \sum_{R\in\mathcal R_C}|R\cap B_0|\lambda_R
```

subject to exact coverage of every core, at-most-one use of every buffer, and
`lambda_R` binary. The single-run pricing oracle is integral, but the master is
not: the locked capacity-two witness has LP value four and integer value three.

## Branching rule

The exact algorithm uses two levels of finite branching.

1. **Optional-buffer usage.** If a buffer has fractional aggregate usage, branch
   on usage zero versus one. The zero child deletes every column containing the
   row; the one child turns its at-most-one constraint into an equality.
2. **Ryan--Foster pair branching.** Once all row usages are integral but the
   column solution remains fractional, choose two active rows with fractional
   co-membership. The together child requires them in the same selected run;
   the separate child forbids any run containing both.

For exact-cover items, these two pair branches partition all integer solutions.
If every active pair co-membership is integral, the induced event partition is
integral, so a fractional node always supplies a valid branch unless it is
already closed numerically.

## Branch-compatible pricing

A together condition `x_i=x_j` is the union of the cases `(x_i,x_j)=(0,0)` and
`(1,1)`. A separate condition `x_i+x_j<=1` is the union of `x_i=0` and `x_j=0`.
At a branch node, the implementation recursively expands these disjunctions,
propagates forced memberships, and solves each surviving case by the same
fixed-span interval LP with additional unit rows and variable bounds.

Adding unit rows and fixing variable bounds preserve total unimodularity of the
interleaved segment/boundary interval matrix. Thus every pricing case still has
an integral LP optimum. Taking the best case gives the exact minimum reduced
cost over all run columns compatible with the node.

The number of cases may grow exponentially in branch depth. Consequently:

- fixed-span branch-compatible pricing is exact;
- every node LP is certified when no negative reduced-cost case remains;
- closing the finite branch queue certifies the global integer optimum;
- the implementation is an exact medium-instance algorithm, not a polynomial
  algorithm for the full integer decomposition.

## Correctness statement

**Proposition.** Assume every branch-compatible pricing case is solved exactly,
phase one either proves node infeasibility or removes all artificial mass, and
the branch queue terminates. Then the incumbent returned by the algorithm is a
global optimum of the ordered-run integer master.

**Argument.** Exact pricing makes each node bound equal to the full node LP,
not merely the current restricted master. Buffer branches and Ryan--Foster
branches are exhaustive and disjoint over integer decompositions. Standard
branch-and-bound pruning therefore removes only nodes whose full LP upper bound
cannot exceed the incumbent. When no open node remains, no feasible integer
decomposition can improve the incumbent.

## Audits

The deterministic battery compares branch-and-price with complete run-column
enumeration on random small interval libraries and on the locked nonintegrality
witness. The public NYC audit fixes four core rows and twelve outcome-blind
nearest temporal buffers. Capacities two, three, and four are solved both by
branch-and-price and the exhaustive small-instance master; all three integer
values agree.

The live aggregate results are frozen in:

- `results/nyc_hvfhv/BRANCH_AND_PRICE_REPORT.md`;
- `results/nyc_hvfhv/BRANCH_AND_PRICE_CELLS.csv`;
- `results/nyc_hvfhv/BRANCH_AND_PRICE_MANIFEST.json`.

No output contains raw rows, row identifiers, run columns, or selected-run
witnesses. The audit does not recover actual partners or vehicle runs and does
not identify realized capacity or production matching logic.
