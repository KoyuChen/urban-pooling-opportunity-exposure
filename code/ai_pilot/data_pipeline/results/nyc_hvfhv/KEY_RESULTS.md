# NYC HVFHV real-data Gate results

Frozen evidence date: 2026-09-02 UTC

## Gate A: current monthly candidate multiplicity

The official May 2026 HVFHV Parquet contains **222,149** public
`shared_match_flag=Y` rows: **220,904 Uber** and **1,245 Lyft**. In a fixed
200-row Uber pickup core, exact public interval overlap yields **154,708**
directed core-candidate incidences over **1,042** candidate nodes, with median
core degree **786**. Thirty minutes of temporal padding raises the incidence
count to **288,734**. Requiring identical pickup and drop-off Taxi Zones leaves
only 44 incidences and is therefore retained only as an aggressive analyst
screen.

Validated workflow `33528697571`; artifact `9808787001`.

## Gate B: exact seconds versus artificial outer envelopes

On a fixed 38-core, 399-buffer 2023 public cohort, replacing exact released
seconds by artificial nearest-15-minute outer intervals increases the
provider-time candidate graph from **5,837** to **10,475** edges. Conditional
pair-cover identified widths increase by 12.4% for miles, 15.3% for trip time,
and 14.3% for same-dropoff-zone share. This is a deterministic graph
sensitivity benchmark, not a claim about realized pool size.

Validated workflow `33528697566`; artifact `9808875413`.

## Gate C: unknown-capacity ordered latent runs

NYC is modeled as a partition into connected positive-overlap interval runs.
Declared capacity `C` restricts simultaneous occupancy, not total run
cardinality, so sequential `A-B-C` chains are admissible even if `A` and `C`
never overlap.

| C | Run count/core, exact seconds | Run count/core, outer model | Max selected buffers/core, outer model |
|---:|---:|---:|---:|
| 2 | `0.500--1.000` | `0.500--1.000` | `9.000` |
| 3 | `0.375--1.000` | `0.375--1.000` | `14.125` |
| 4 | `0.250--1.000` | `0.250--1.000` | `18.500` |

The compact interval-segment formulation passes the within-time capacity
nesting audit. Exact-second membership-mass maxima at the larger 8-core smoke
scale remain unpublished when they exceed the short numerical limit.

Validated workflow `33545170861`; artifact `9815675232`.

## Gate D: run-invariant outcomes at capacity-specific maximum support

| C | Max buffers/core | Mean selected-buffer miles | Mean selected-buffer minutes |
|---:|---:|---:|---:|
| 2 | 9.000 | `3.440--9.679` | `17.779--37.147` |
| 3 | 14.125 | `4.148--8.514` | `20.329--34.155` |
| 4 | 18.500 | `4.615--8.411` | `21.999--33.812` |

All endpoint pairs are certified. Their visual contraction with `C` is not a
nested-set result because each capacity conditions on a different maximum
support cardinality.

Validated workflow `33551028665`; artifact `9817489639`.

## Gate E: common-support capacity geometry

Holding support fixed at 72 selected buffers makes capacity a pure nested
feasible-set relaxation:

| C | Miles interval | Width | Minutes interval | Width |
|---:|---:|---:|---:|---:|
| 2 | `3.440--9.679` | 6.239 | `17.779--37.147` | 19.368 |
| 3 | `3.131--15.448` | 12.317 | `15.983--55.712` | 39.729 |
| 4 | `3.116--16.166` | 13.050 | `15.924--58.906` | 42.982 |

Of the total `C=2` to `C=4` widening, **89.2%** for miles and **86.2%** for
duration occurs already at `C=2 -> 3`.

Validated workflow `33556633111`; artifact `9819681582`.

## Gate F: correct existential timestamp completion

Using the whole outer envelope as the realized active interval is not monotone:
it creates possible overlap bridges but can also create artificial simultaneous
occupancy. The corrected release world selects one latent exact timestamp
completion inside each public support and then imposes connectivity and
capacity on that completion.

For one fixed four-core, twelve-buffer audit cohort:

| C | Exact maximum buffers | Coarse existential certified maximum | Certified gain lower bound |
|---:|---:|---:|---:|
| 2 | 4 | 8 | at least 4 |
| 3 | 8 | 12 | at least 4 |
| 4 | 12 | 12 | 0 at the audit ceiling |

At fixed support counts `q=4,6,8`, all feasible exact/coarse cells attain the
same public miles and duration endpoints. Exact `C=2` is proven infeasible at
`q=6` and `q=8`, while coarse existential `C=2` is certified feasible. The
first detected time-support effect in this cohort is therefore support
reachability rather than conditional composition.

Support workflow `33591752562`; common-support workflow `33599734797`.

## Gate G: predeclared six-window replication panel

Each window is fetched once, reduced without using outcome values, and reused
for `C=2,3,4`. All six capacity triplets completed and the aggregate audit
passed with zero problems.

| Window | Gain lower bound at C=2 | Gain lower bound at C=3 | Coarse C=2 reaches exact C=3 max |
|---|---:|---:|---|
| April weekday PM | 1 | 1 | no |
| January weekday AM | 3 | 3 | no |
| January weekday PM | 4 | 4 | yes |
| January weekend PM | 7 | 4 | yes |
| July weekday PM | 2 | 2 | no |
| October weekday PM | 3 | 3 | no |

Artificial timestamp support expands the certified reachable support at both
`C=2` and `C=3` in **6/6** windows. At `C=2`, the gain lower bound has mean
**3.33** buffers and median **3**. Relative to the exact one-step capacity
increment `M_3-M_2=4`, the local substitution-ratio lower bound ranges from
0.25 to 1.75, with mean 0.83 and median 0.75; it reaches or exceeds one in 2/6
windows.

Coarse `C=3` reaches the exact `C=4` maximum in 6/6 windows, but every exact
`C=4` maximum equals the twelve-buffer audit ceiling, so this comparison is
right-censored and must not be described as universal saturation. Seven
window-capacity cells retain unresolved larger coarse counts; all reported
gains are lower bounds, not sharp maxima.

The defensible conclusion is **regime-dependent capacity substitution**:
timestamp uncertainty and simultaneous-capacity relaxation both enlarge
latent-run support, but their exchange rate varies with local temporal
structure.

Validated workflow `33599734813`; summary artifact `9836005918`;
digest `sha256:8bbe75bd2c14c298d6c060efbbe6235bd859dec4859660b721d3e8454e144b33`.

## Current Gate conclusion

NYC now passes the problem-existence, ordered-run modeling, correct
existential-time semantics, common-estimand outcome, and small-panel
replication Gates. The evidence supports a method claim about certified
feasible-world frontiers under declared release supports.

It still does **not** identify actual co-riders, actual vehicle runs, realized
pool size or capacity, TLC production matching logic, the true TLC timestamp
release operator, a NYC population frequency, or a causal/policy effect.
