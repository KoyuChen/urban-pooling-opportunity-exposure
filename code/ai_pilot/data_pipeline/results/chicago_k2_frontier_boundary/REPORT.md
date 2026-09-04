# Chicago K=2 public temporal candidate universe and three-axis support sensitivity

Run date: 2026-09-01 UTC  
Validated workflow run: `33516268840` (run 50)  
Artifact: `chicago-k2-frontier-boundary`, ID `9804349342`  
Artifact ZIP SHA-256: `f1d1b88870c046d8feac13fe1b8fc5d884e6b81352a28594fcc58fa5ae4f4ab8`  
Numerical source commit: `bd51ed45485d4f52af433b3d5b3eb0670d6442ea`  
Dataset: City of Chicago `6dvr-xwnh`, Transportation Network Providers - Trips (2025-)  
Pinned public-view fingerprint: `52f2ff4772d94efe764a1406bacd7696ef473e7a2e626c97c04f21b6534f4190`

## Result

The live pipeline completed successfully. It constructs a metadata/count-stable,
core-incident public K=2 temporal candidate universe for one released 15-minute
core and solves three nested candidate-support families:

1. released-time boundary padding `p`;
2. released endpoint-centroid radius `r`; and
3. measured out-of-radius core-incidence budget `Gamma`.

All graph covers and every published numerical endpoint are independently
replayed. The boundary-padding endpoint identity, radius/Gamma endpoint
identities, and public temporal closure audits all pass.

This is **not** hidden-run closure. Chicago does not publish Shared Trip ID,
co-rider identity, or vehicle identity, and buffer rows' other run-mates are not
recursively reconstructed.

## Cohort and complete boundary

The adaptively selected core is the released bin
`2026-01-13T17:30:00`--`2026-01-13T17:45:00`.

| Quantity | Result |
|---|---:|
| Literal `Shared Trip Match=true, Trips Pooled=2` core rows | 60 |
| Complete boundary-buffer rows | 551 |
| Total public temporal candidates | 611 |
| Determinate timestamp rows | 611 |
| Global K=2 rows with null start or end | 0 |
| Off-grid timestamps | 0 |
| Chronology-impossible released rows | 0 |
| Duplicate or blank trip IDs | 0 |
| Metadata and server counts stable | yes |
| Core recovered exactly | yes |
| Public temporal closure audit | `PASS` |

With release-rounding half-width `delta=7.5` minutes, every determinate row that
can form a core-incident outer temporal edge must satisfy

```text
released_start <= max_core_released_end + 2 delta
released_end   >= min_core_released_start - 2 delta.
```

Thus the complete padding is `p*=2 delta=15` minutes. Timestamp-indeterminate
K=2/match rows are globally counted and retained at every padding point.

## Boundary-padding sensitivity

Because released timestamps lie on a 15-minute grid, the padding curve is a
certified step function rather than a smooth curve.

| Padding `p` | Buffer rows | Candidate edges | Miles-gap interval | Width | Duration-gap interval (min) | Width |
|---:|---:|---:|---:|---:|---:|---:|
| 0 min | 459 | 21,645 | `[0.034303, 20.193440]` | 20.159137 | `[0.126111, 46.595833]` | 46.469722 |
| 5 min | 459 | 21,645 | `[0.034303, 20.193440]` | 20.159137 | `[0.126111, 46.595833]` | 46.469722 |
| 10 min | 459 | 21,645 | `[0.034303, 20.193440]` | 20.159137 | `[0.126111, 46.595833]` | 46.469722 |
| 15 min | 551 | 24,274 | `[0.031592, 20.297733]` | 20.266142 | `[0.118333, 47.060278]` | 46.941944 |
| 30 min | 551 | 24,274 | `[0.031592, 20.297733]` | 20.266142 | `[0.118333, 47.060278]` | 46.941944 |

Moving from under-padding (`p<15`) to the complete endpoint adds **92 buffer
rows** and **2,629 edges**: candidate rows rise 17.73% and edges rise 12.15%.
Nevertheless, the miles-gap width increases only **0.107005 miles (0.53%)** and
the duration-gap width only **0.472222 minutes (1.02%)**. Hence the continuous
query ranges are empirically insensitive to boundary omission in this core even
though the graph support itself expands materially.

The 30-minute point is not a new data claim. It canonically reuses the
15-minute feasible set because rows outside the `2 delta` envelope cannot form
a core-incident outer temporal edge. The boundary endpoint-identity audit is
`PASS` with zero mismatches.

## Radius sensitivity

The complete temporal graph has 24,274 edges. An edge is retained at radius `r`
when both released pickup- and dropoff-centroid distances are no larger than
`r`; edges with missing centroid information remain at every radius.

| Radius | Edges | Miles-gap width | Duration-gap width (min) |
|---:|---:|---:|---:|
| 0 km | 11,865 | 19.1009 | 44.1086 |
| 0.25 km | 11,865 | 19.1009 | 44.1086 |
| 0.5 km | 11,869 | 19.4758 | 44.7933 |
| 1 km | 11,894 | 19.4880 | 44.8375 |
| 2 km | 11,965 | 19.6478 | 44.9761 |
| 4 km | 12,137 | 19.6925 | 45.1900 |
| 8 km | 13,318 | 19.8087 | 45.7725 |
| 16 km | 18,450 | 20.2495 | 46.8222 |
| 32 km | 23,838 | 20.2661 | 46.9419 |
| Temporal only | 24,274 | 20.2661 | 46.9419 |

At 2 km, the intervals are `[0.168685, 19.816457]` miles and
`[0.447222, 45.423333]` minutes. Relative to temporal-only support, the screen
narrows widths by only 3.05% and 4.19%. The main limitation is public spatial
suppression: 11,865 temporal edges (48.88%) lack complete released endpoint
centroids and cannot be deleted conservatively.

## Measured out-of-radius incidence sensitivity

At the 2 km base, `Gamma` counts selected **core incidences** on
measured-distance edges outside the radius: a core--core edge costs two, a
core--buffer edge costs one, and an unmeasured-distance edge costs zero.

| Gamma | Miles-gap width | Duration-gap width (min) |
|---:|---:|---:|
| 0 | 19.6478 | 44.9761 |
| 1 | 19.7376 | 45.2517 |
| 2 | 19.8172 | 45.4883 |
| 4 | 19.9539 | 45.8694 |
| 8 | 20.1535 | 46.4042 |
| 15 | 20.2519 | 46.8858 |
| 16 | 20.2542 | 46.9014 |
| 30 | 20.2660 | 46.9408 |
| 60 | 20.2661 | 46.9419 |

The curve is nearly saturated by `Gamma=15--30`. `Gamma=0` equals the certified
2 km endpoint and `Gamma=60` equals the temporal-only endpoint. `Gamma` is not a
total candidate-miss budget or estimated miss rate.

## Certification and fail-closed results

There are **120** curve/query rows. Exactly **96** endpoint pairs publish
numeric intervals. Every published pair has two
`OPTIMAL_NUMERICAL_MILP` endpoints, MIP gap zero, replay residual zero, finite
ordered values, and an internally consistent width. The remaining 24 pairs are
the fare chains and publish no numerical endpoints: six of 611 rows lack public
fare, affecting 512 full-temporal edges, and no imputation is introduced.

The monotonicity audit is `PARTIAL`: **12/15** complete curve/query chains,
covering **4/5** query families, are fully certified and monotone, with zero
mathematical reversals. Pickup and dropoff community-area fractions remain
`[0,1]` throughout, so they are not identified by these constraints.

## Interpretation

The useful robustness result is narrow: the complete temporal boundary changes
the candidate graph materially but changes the two continuous identification
widths by only about 0.5--1.0% in this selected core. The broader identification
result remains weak: the absolute ranges are large and the categorical ranges
are vacuous.

Supported language is therefore **robustness to public candidate-support
construction**, not recovered partners, hidden runs, or point identification.
This one adaptively selected core is a smoke test, not a Chicago-population
estimate or policy-effect claim.
