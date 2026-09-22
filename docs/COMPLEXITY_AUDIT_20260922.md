# Exact-time fixed-support complexity audit, September 22, 2026

## Decision

Gate: `PASS_TRACTABLE_BOUNDARY_WITH_HARDNESS_OPEN`.

No complete NP-hardness reduction was verified for the exact-time, multi-core
EventFrontier world problem, including fixed capacity two. The paper therefore
continues to say only that the classification is not settled **here**. It does
not call the problem polynomial, NP-hard, or a literature-wide open problem.

## Problems that must not be conflated

For rational exact intervals and a fixed capacity C:

1. `EXACT-Q-EVENT-WORLD(C)` asks whether a world using exactly q buffers
   exists.
2. `EVENT-SUPPORT(C)` asks whether some world uses at least k buffers.
3. The endpoint problem fixes a feasible q and optimizes an aggregate over
   those worlds.

All three have polynomial-size partition certificates. The first two are not
interchangeable without a no-gap theorem. At capacity two, the four rows

- cores c0=[0,7), c1=[3,5);
- buffers b0=[2,4), b1=[4,6)

have Q={0,2}. With no buffers the cores form one event; with both buffers use
events {c0,b0} and {c1,b1}. With exactly one buffer, putting both cores with it
creates triple occupancy, while separating the cores leaves one in a
forbidden singleton event. Thus support at least one is true although exact
q=1 is infeasible.

## New tractable boundary

Let the full positive-overlap graph have connected components K. If the
maximum simultaneous occupancy of the full exact interval family is at most
C, capacity is automatic for every subset.

- A component containing a core can be used whole as one event if it has at
  least two rows.
- A singleton core component makes every world infeasible.
- A buffer in a component without a core cannot enter an event.

Therefore, whenever a world exists,

`M = sum over core-containing K of |K intersect B0|`.

If every component of the core-induced overlap graph contains at least two
cores and every buffer overlaps a core, begin with those core components as
events and attach any desired subset of buffers to an overlapping core's
event. Hence every q in {0,...,|B0|} is feasible. Any future hardness proof
must leave this boundary by using over-capacity conflicts or a failure of the
anchoring condition.

## Exhaustive verification

`code/ai_pilot/benchmarks/complexity_boundary_audit.py` independently builds
all feasible event columns and all disjoint core-covering worlds over a
seven-interval exact catalog.

- 2,059 role/absence assignments with at least one core;
- 2,956 low-depth capacity cases at C in {2,3};
- 1,614 feasible and 1,342 infeasible cases;
- 322 well-anchored cases and 752 individual fixed-q cells;
- zero component-formula or fixed-q mismatches.

This enumeration is regression evidence for the proof, not a proof by finite
testing. A separate exact witness confirms that a capacity-two event may be a
star of overlap-graph degree four, so it need not be a path.

## Why nearby hardness does not transfer

| Source problem | Primary source | Missing preservation step |
|---|---|---|
| Interval scheduling on unrelated machines | Hermelin et al., IPEC 2022, https://doi.org/10.4230/LIPIcs.IPEC.2022.18 | Jobs have machine-dependent processing intervals or arbitrary eligible-machine sets. EventFrontier supplies neither. |
| Balanced connected k-partition on interval graphs | Miyazawa et al., https://arxiv.org/abs/1911.05723 | It fixes the number of parts, assigns every vertex, and optimizes minimum part weight. Our parts are core-anchored, unbalanced, and buffers are optional. |
| Same-size star partition | van Bevern et al., https://arxiv.org/abs/1402.2589 | It fixes every part's size and star shape; the cited paper reports the interval-graph case as polynomial. |
| Induced disjoint paths / induced subtrees | Golovach et al., https://arxiv.org/abs/1403.0789; Heggernes et al., https://pimvanthof.github.io/inducedsubtrees.pdf | Terminal pairings, induced-adjacency restrictions, or forced shapes are absent. Capacity-two events can be stars. |

A valid reduction must preserve all of the following without adding side
constraints: exact intervals; core/buffer roles; events of at least two rows;
positive-overlap connectivity; instantaneous capacity; exact core cover;
buffer nonreuse; and the declared exact q or support threshold. None of the
audited transfers supplies that map.

The fractional event-column witness proves only LP nonintegrality. Exponential
branch-compatible case counts prove only a worst-case search form. Solver
timeouts and numerical statuses prove neither infeasibility nor hardness.

## Reproduction

```bash
python code/ai_pilot/benchmarks/complexity_boundary_audit.py
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests \
  -p 'test_complexity_boundary_audit.py' -v
```

Frozen outputs are in
`code/ai_pilot/benchmarks/results/complexity_boundary_20260922/`.
