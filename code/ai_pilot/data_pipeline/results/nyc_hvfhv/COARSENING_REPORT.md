# Frozen NYC HVFHV exact-time/coarsening evidence

Validated workflow run: `33528697566`  
Artifact: `nyc-hvfhv-coarsening`, ID `9808875413`  
Artifact ZIP SHA-256: `622a1ad6c2416c26a3c6e424382f76ab88984638edb40f244cbe77613adfc1d3`  
Source commit: `6f5c469dfde0fa4ecc6f5bb94b4f1a03836ca565`

# NYC HVFHV exact-time versus artificial 15-minute frontier

Generated UTC: `2026-09-01T15:57:41+00:00`  
Dataset: `u253-aew4` (2023 High Volume FHV Trip Data)  
Snapshot fingerprint: `0041ce9fa9edf98f5075978a94468c41ca6679a11d4ca6dca48f2671fb4907d1`

## Fixed cohort

Provider `HV0005`, pickup core `2023-01-03T17:45:00`--`2023-01-03T18:00:00`: **38** public shared-match rows and **399** buffer rows (**437** candidates total).

The same released rows are analyzed at exact-second resolution and after artificial nearest-15-minute coarsening. All results are conditional C=2 cover benchmarks; NYC does not release the realized pool size or partner key.

| Time model | Zone support | Edges | Core min degree | Cover | Miles width | Time width (min) |
|---|---|---:|---:|---|---:|---:|
| exact_second | same_od_zone | 3 | 0 | `PROVEN_INFEASIBLE_ISOLATED_CORE` | — | — |
| exact_second | same_pickup_zone | 67 | 0 | `PROVEN_INFEASIBLE_ISOLATED_CORE` | — | — |
| exact_second | provider_time_only | 5837 | 130 | `OPTIMAL_NUMERICAL_MILP` | 12.2846 | 38.1127 |
| rounded_15m_outer | same_od_zone | 5 | 0 | `PROVEN_INFEASIBLE_ISOLATED_CORE` | — | — |
| rounded_15m_outer | same_pickup_zone | 114 | 0 | `PROVEN_INFEASIBLE_ISOLATED_CORE` | — | — |
| rounded_15m_outer | provider_time_only | 10475 | 260 | `OPTIMAL_NUMERICAL_MILP` | 13.8067 | 43.9338 |

## Audit

Nested-support and coarsening audit: `PASS`; certified exact-versus-rounded endpoint comparisons: **3**.

The candidate universe is count-reconciled and the snapshot/counts are stable for this extraction. This does not establish hidden-run closure, partner recall, a true C=2 population, or a citywide effect.
