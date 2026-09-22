# Exact-time complexity boundary audit

Gate: `PASS_TRACTABLE_BOUNDARY_WITH_HARDNESS_OPEN`.

## Result

No valid NP-hardness reduction was established. The global exact-time,
multi-core classification therefore remains open in this manuscript. This is
not a literature-wide open-problem claim.

The audit instead proves a tractable boundary. If the full exact interval
family has depth at most capacity C, each full positive-overlap component that
contains a core can be used as one event. Every buffer in such a component is
selected, and no buffer in a buffer-only component can be selected. A
singleton core-containing component makes the model infeasible because events
must have at least two rows.

If the core-induced overlap components already have at least two cores and
every buffer overlaps a core, then every fixed q from 0 through |B| is
feasible. Thus connectivity alone does not yield the missing hardness result;
a valid reduction must exploit over-capacity conflicts or failure of this
anchoring condition.

Exact-q feasibility is also not interchangeable with the maximum-support
decision. The four-row capacity-two witness in `SUMMARY.json` has feasible
support set Q = {0, 2}: support at least one is feasible, but q=1 is not.

## Exact validation

- Role/absence assignments with at least one core: **2,059**
- Low-depth capacity cases exhaustively compared: **2,956**
- Feasible / infeasible cases: **1,614 / 1,342**
- Well-anchored cases: **322**
- Fixed-q cells checked: **752**
- Mismatches: **0**

The finite audit is regression evidence for the proof, not a proof by
enumeration. It also verifies an exact capacity-two star event with overlap-
graph degree four, refuting the shortcut that every capacity-two event is a
path.

## Rejected hardness transfers

- Unrelated-machine interval scheduling supplies machine-dependent intervals
  or arbitrary eligibility that the event model does not have.
- Balanced connected k-partition fixes the number of parts and has a balance
  objective absent here.
- Same-size star partition fixes every part's shape; moreover its interval-
  graph case is polynomial.
- Induced-path/subtree variants add terminals, inducedness, or adjacency rules
  absent from freely regroupable event worlds.

## Claim boundary

`C=2 NP-hard` is **not established**. A fractional master, exponential branch
case count, and hard neighboring problems are not hardness proofs. No timeout
or numerical solver status enters this audit.
