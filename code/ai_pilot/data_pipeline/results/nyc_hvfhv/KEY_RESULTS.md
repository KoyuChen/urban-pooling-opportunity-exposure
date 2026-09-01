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

## Gate conclusion

NYC passes the **problem-existence and scale Gate**:

1. latent-linkage ambiguity is large even with public second-level timestamps;
2. Chicago-like time coarsening materially expands the candidate graph and the
   identified ranges, but does not create the ambiguity by itself; and
3. exact Taxi-Zone equality is far too restrictive to serve as a necessary
   candidate rule.

NYC does **not** yet pass the final modeling Gate because public HVFHV data do
not expose realized pool size. The pairwise program is therefore a conditional
`C=2` benchmark, not an empirical statement that these rides formed pairs.
The natural NYC extension is an unknown-capacity, temporally ordered shared-run
model rather than a direct copy of the Chicago matching model.
