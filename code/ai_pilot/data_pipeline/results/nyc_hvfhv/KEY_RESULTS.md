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

## Gate conclusion

NYC passes the **problem-existence, scale, and ordered-run modeling Gates**:

1. latent-linkage ambiguity is large even with public second-level timestamps;
2. Chicago-like time coarsening materially expands the candidate graph and identified ranges, but does not create the ambiguity by itself;
3. exact Taxi-Zone equality is far too restrictive to serve as a necessary candidate rule; and
4. replacing pairwise matching by connected bounded-occupancy runs preserves substantial partial identification and reveals a separate computational burden at exact timestamps.

The public data still do **not** identify realized pool size, actual vehicle runs, or co-rider identities. All capacity comparisons are conditional on declared `C`; they are not empirical estimates of NYC's true vehicle capacity or production matching logic.
