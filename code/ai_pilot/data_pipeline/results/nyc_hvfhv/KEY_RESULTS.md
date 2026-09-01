# NYC HVFHV real-data Gate results

Frozen evidence date: 2026-09-01 UTC

## Gate A: current monthly candidate multiplicity

Source: official TLC May 2026 HVFHV Parquet.

- Public shared-match rows in the month: **222,149**.
- Provider composition among those rows: **220,904 Uber** and **1,245 Lyft**.
- Fixed smoke cohort: **200** Uber shared-match rows in `2026-05-21 19:15:00`--`2026-05-21 19:30:00`.
- At exact public interval overlap (`padding=0`), the cohort has **154,708** directed core-candidate incidences over **1,042** candidate nodes; median core degree is **786**.
- At 30-minute padding, this rises to **288,734** incidences and median degree **1439**.
- Requiring the same pickup and drop-off Taxi Zones leaves only **44** directed incidences at zero padding. This is an analyst screen, not a necessary partner rule.

Validated workflow: `33528697571`; artifact `9808787001`; artifact digest `sha256:ba6baba8d3aa9809a0a3fdde65536b973a904306555af86c02244ffc439aacdd`.

## Gate B: exact-time versus Chicago-like coarsening

Source: fixed 2023 Open Data cohort, provider `HV0005`, **38** core rows and **399** buffer rows.

Under provider-plus-time support:

| Quantity | Exact public seconds | Artificial 15-minute outer intervals | Change |
|---|---:|---:|---:|
| Candidate edges | 5,837 | 10,475 | +79.5% |
| Minimum core degree | 130 | 260 | +100.0% |
| Miles-gap identified width | 12.2846 | 13.8067 | +12.4% |
| Trip-time-gap width (min) | 38.1127 | 43.9338 | +15.3% |
| Same-dropoff-zone width | 0.7368 | 0.8421 | +14.3% |

The exact-second pairwise benchmark remains very weakly identified:
miles gap `0.0492`--`12.3337`, trip-time gap
`0.1114`--`38.2241` minutes, and same-dropoff-zone share
`0.0000`--`0.7368`.

Both provider-time covers and all six published endpoints are certified
`OPTIMAL_NUMERICAL_MILP` with zero MIP gap and zero replay residual.
The nested-support/coarsening audit is `PASS`.

Validated workflow: `33528697566`; artifact `9808875413`; artifact digest `sha256:622a1ad6c2416c26a3c6e424382f76ab88984638edb40f244cbe77613adfc1d3`.

## Gate C: unknown-capacity ordered latent runs

The pairwise `C=2` restriction has now been replaced by an ordered latent-run model on an 8-row core inside the same fixed 437-row public candidate universe. A run is a connected positive-overlap interval subgraph. Capacity `C` restricts simultaneous occupancy but not total run cardinality, so sequential `A-B-C` chains are admissible even when `A` and `C` never overlap.

The compact interval-segment MILP is exact for this declared connectivity rule and passes the capacity-nesting audit.

| C | Run count/core, exact seconds | Run count/core, 15-min outer | Max selected buffers/core, 15-min outer |
|---:|---:|---:|---:|
| 2 | `0.500`--`1.000` | `0.500`--`1.000` | `9.000` |
| 3 | `0.375`--`1.000` | `0.375`--`1.000` | `14.125` |
| 4 | `0.250`--`1.000` | `0.250`--`1.000` | `18.500` |

The run-count range widens monotonically with `C`: larger simultaneous capacity permits the same core to be consolidated into fewer connected runs. More strikingly, under coarse public time support the feasible latent membership grows much faster than the run-count range because bounded-occupancy runs may accumulate many sequential members.

The exact-second maximization problems for selected-buffer and companion mass remain computationally unresolved at the 60-second smoke limit and are deliberately unpublished. Exact-second run-count endpoints are certified; all displayed 15-minute endpoints are certified.

This gives the first non-pairwise real-data evidence for the NYC extension: **unknown capacity and sequential run composition are material identification dimensions, while finer timestamps trade a smaller feasible linkage set for a substantially harder exact optimization problem.**

Validated workflow: `33545170861`; artifact `9815675232`; artifact digest `sha256:7ecad13140f22f1aa83409d34eadfa32836995d973a2a1accb96fe90b8170506`.

## Gate D: run-invariant outcome composition at maximum support

The next stage fixes, for each declared `C`, that capacity's certified maximum number of selected buffer rows and then bounds the mean public miles and trip duration of those selected rows. The estimands are invariant to the canonical run-root label.

| C | Max buffers/core | Mean selected-buffer miles | Mean selected-buffer minutes |
|---:|---:|---:|---:|
| 2 | 9.000 | `3.440`--`9.679` | `17.779`--`37.147` |
| 3 | 14.125 | `4.148`--`8.514` | `20.329`--`34.155` |
| 4 | 18.500 | `4.615`--`8.411` | `21.999`--`33.812` |

All six endpoint pairs are certified with zero reported MIP gap. The maximum-support requirement expands from 72 selected buffers at `C=2` to 113 at `C=3` and 148 at `C=4`. Conditional on those different support maxima, the miles interval width falls by **39.2%** and the duration width by **39.0%** between `C=2` and `C=4`.

This contraction is **not** a nested-set result: the conditioning event changes with capacity. Larger `C` expands the feasible latent-world set but also raises the C-specific maximum-support cardinality, forcing maximum-support worlds to include more public rows and reducing the ability to select only outcome extremes.

Validated workflow: `33551028665`; artifact `9817489639`; artifact digest `sha256:cf4f16f590deababc74ecad20be99d18e1e62994bb9acfa7e09ace6923475806`.

## Gate E: common-support capacity geometry

To isolate the pure effect of relaxing capacity, the support cardinality is now held fixed at the certified `C=2` maximum: **72 selected buffers**, or **9.0/core**, for all `C=2,3,4`. Under this common estimand the feasible worlds are nested in `C`, so lower endpoints must weakly fall and upper endpoints must weakly rise.

| C | Mean selected-buffer miles | Width | Mean selected-buffer minutes | Width |
|---:|---:|---:|---:|---:|
| 2 | `3.440`--`9.679` | 6.239 | `17.779`--`37.147` | 19.368 |
| 3 | `3.131`--`15.448` | 12.317 | `15.983`--`55.712` | 39.729 |
| 4 | `3.116`--`16.166` | 13.050 | `15.924`--`58.906` | 42.982 |

All six endpoint pairs are certified with zero reported MIP gap and the four adjacent-capacity nestedness checks pass. Once the moving-conditioning effect is removed, the capacity effect reverses the Gate-D visual contraction exactly as theory requires: identified intervals expand sharply with `C`.

The widening is strongly front-loaded. From `C=2` to `C=3`, the miles width rises **97.4%** and the duration width rises **105.1%**. Moving from `C=3` to `C=4` adds only **6.0%** and **8.2%**, respectively. Thus **89.2%** of the total `C=2` to `C=4` miles widening and **86.2%** of the duration widening occurs at the first capacity relaxation in this smoke cohort.

This establishes a clean decomposition: `C=2 -> 3` is the dominant capacity-uncertainty margin here, while `C=3 -> 4` is comparatively close to saturation. It is a property of the declared feasible-world model and selected cohort, not an estimate of the platform's realized capacity.

Validated workflow: `33556633111`; artifact `9819681582`; artifact digest `sha256:33a96ea9e8eb6a21426b8a903b04c2f82b8ec7c68ae42efbb873bf9b2eb69a50`.

## Gate conclusion

NYC passes the **problem-existence, scale, ordered-run modeling, and common-estimand outcome-composition Gates**:

1. latent-linkage ambiguity is large even with public second-level timestamps;
2. Chicago-like time coarsening materially expands the candidate graph and identified ranges, but does not create the ambiguity by itself;
3. exact Taxi-Zone equality is far too restrictive to serve as a necessary candidate rule;
4. replacing pairwise matching by connected bounded-occupancy runs preserves substantial partial identification and reveals a separate computational burden at exact timestamps;
5. outcome uncertainty has two distinct margins: feasible-support expansion with `C`, and composition restrictions induced by conditioning on C-specific maximum support; and
6. with support cardinality fixed, capacity becomes a pure nested feasible-set relaxation, and most of the observed `C=2` to `C=4` uncertainty expansion occurs already at `C=3`.

The public data still do **not** identify realized pool size, actual vehicle runs, or co-rider identities. All capacity comparisons are conditional on declared `C`; they are not empirical estimates of NYC's true vehicle capacity or production matching logic.
