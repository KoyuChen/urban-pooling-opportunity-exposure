# Minimal theory reinforcement, September 9, 2026

This revision answers the mathematical review of the KDD working draft. It
does not add public-data observations or establish a global hardness result.

## What is now proved

| Question | Result and location | Verification |
|---|---|---|
| Does changing event structure change an answer at fixed support? | `prop:modelcontainment`, main model section and appendix: pair is contained in clique, which is contained in event; two strict selected-buffer-mean witnesses | Exact rational complete partition enumeration |
| When should the public structural comparison return no event/clique difference? | Same proposition: equality whenever the exact overlap graph is a disjoint union of cliques, for every capacity | Common-intersection examples at capacities 2, 3, 4, 6 |
| What makes interval connectivity different from touching or a clique? | `lem:connectivity`, main algorithm section: segment coverage plus a crossing interval at every internal boundary is equivalent to positive-overlap connectivity | Two-direction proof; endpoint-touching tests |
| Which aggregates preserve local pricing? | `prop:aggregateclass`: fixed-q row sums plus a constant per event, divided by a known positive denominator | Direct column coefficient and dual substitution |
| Does the uncertain-time MILP describe the declared object? | `prop:epsilon`, main statement and appendix two-direction proof | Twelve geometric MILP boundary cases with witness replay |
| How does positive epsilon relate to strict overlap? | Strict worlds are the union over positive margins; all feasible partitions and partition-only extrema stabilize at a sufficiently small positive margin | Finite spanning-tree and finite-partition argument |
| Is exact-time support maximization NP-hard at capacity two? | Not established. Only NP membership and polynomial single-core support are asserted | Hardness transfer audit below |

## Fixed-q strict witnesses

Every event contains at least two rows and a core. Cores are assigned exactly
once, buffers at most once. All three models use identical input rows, exact
times, capacity and q. The query is the mean value of selected buffers.

1. Capacity 2, q=2. Cores are c1=[0,2), c2=[1,3). Buffers are
   b0=[-1,1/2), b1=[5/2,4), b2=[7/2,5), with values 0,0,1.
   Pair/clique has one partition, selecting b0,b1, with range [0,0].
   Event has three partitions and range [0,1/2]; the four-member event
   {c1,c2,b1,b2} attains its upper endpoint.
2. Capacity 3, q=3. The first clique c1,a1,a2 has interval [0,1);
   the second clique c2,c3,b1,b2 has interval [2,3). Values of a1,a2 are
   one, and values of b1,b2 are zero. Pair has four partitions and range
   [1/3,1/3]. Clique/event has six partitions and range [1/3,2/3].

The first example changes an answer using an aggregate inside the stated
additive-pricing class. Neither example relies on an empty comparator or a
different selected-buffer denominator. They demonstrate possible strict
differences, not an assertion that every query or public instance must differ.

The observed NYC common 14-second intersection is a collapse instance.
Containment explains why event and clique coincide there, but alone does not
explain pair equality at capacities above two or equality for every fixed-q
query; those additional observations remain empirical checks of that input.

## Exact scope of the epsilon bridge

The supports are bounded rectangular start/end boxes intersected with positive
duration. The implementation enforces duration >= epsilon for every row,
including unused buffers. Selected connectivity edges have overlap length
>= epsilon; only a connected spanning subgraph is needed. Capacity is ordinary
half-open occupancy, not clique number in the thresholded epsilon graph.
Same-seat intervals may touch at endpoints.

Canonical roots and flow give one common completion and a connected event.
Conversely, any declared world supplies a spanning tree, a greedy interval
coloring into C seats and a satisfying MILP assignment. The implementation's
Big-M is sufficient to deactivate unused disjunctions. This is equivalence of
mathematical feasible sets, distinct from floating-point solver certification.

At any fixed positive epsilon, some strictly feasible worlds can be excluded.
For each strictly feasible world, the minimum positive duration and spanning-
tree overlap gives a retaining margin. The union over positive margins is
therefore exactly the strict world set. Finitely many possible partitions give
an instance-dependent positive margin retaining all feasible partitions and
their partition-only aggregate extrema. The audit's chosen epsilon has not
automatically been proved to be below that margin. Substituting epsilon=0 can
admit touching chains and zero-duration completions.

## Complexity: retained gap and rejected shortcuts

For exact intervals, support decision belongs to NP: a row partition has
polynomial size and core coverage, connectivity and capacity are checked by
sorting endpoints. With one core, all selected rows must form one event, so
the rooted single-event oracle solves the optimization in polynomial time.
There are O(n^2) endpoint spans; span enumeration is not exponential.

No reduction to the unrestricted multi-core model has been verified. In
particular, the fractional master witness proves only a relaxation gap.
The following nearby literature does not supply the missing reduction:

- Hermelin, Itzhaki, Molter and Shabtay, *Hardness of Interval Scheduling on
  Unrelated Machines*, IPEC 2022, DOI
  https://doi.org/10.4230/LIPIcs.IPEC.2022.18. Machine-dependent processing
  intervals or arbitrary eligible-machine sets are additional input structure
  absent from the current event model.
- Golovach, Paulusma and van Leeuwen, *Induced Disjoint Paths in Circular-Arc
  Graphs in Linear Time*, https://arxiv.org/abs/1403.0789. Terminal pairings
  and restrictions on adjacency between paths differ from freely regroupable
  cores and our lack of cross-event constraints.
- van Bevern et al., *Partitioning Perfect Graphs into Stars*,
  https://arxiv.org/abs/1402.2589, journal DOI
  https://doi.org/10.1002/jgt.22062. Interval-graph cases include polynomial
  algorithms; hardness on larger graph classes cannot be imported.
- Heggernes, van 't Hof and Milanic, *Induced Subtrees in Interval Graphs*,
  https://pimvanthof.github.io/inducedsubtrees.pdf. A capacity-two event need
  not be a path: a long interval with disjoint short leaves is a valid star.
  Induced and non-induced subtree problems also have different complexities.

The draft says the general complexity is not settled **here**, rather than
claiming it is an established open problem throughout the literature.
An approximation scheme, a general-H complexity taxonomy and statistical
inference are outside this revision.

## Reproduction

```
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests \
  -p 'test_event_*' -v
python scripts/audit_tex_references.py
```

Result: 16 focused tests PASS; 39 labels, 23 referenced labels and 18 citation
keys PASS. Production solvers are unchanged. The reference audit now excludes
generated standalone TeX copies in `paper/build/` and checks canonical modular
sources, avoiding duplicate-label false positives after packaging.
