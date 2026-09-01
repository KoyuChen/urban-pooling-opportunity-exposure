# Chicago K=2 public temporal candidate universe and support sensitivity

Run date: 2026-09-01 UTC  
Validated workflow run: `33472377443` (run 36)  
Artifact: `chicago-k2-frontier`, ID `9787210996`  
Artifact ZIP SHA-256: `3b78dcfbe8737201a3fd042bde758ac17ea4df87eca00bc766679fea0ba4311a`  
Numerical source commit: `d17d555c71162c4e753e64fe12ffc1dd8d8c5513`  
Dataset: City of Chicago `6dvr-xwnh`, Transportation Network Providers - Trips (2025-)  
Pinned public-view fingerprint: `52f2ff4772d94efe764a1406bacd7696ef473e7a2e626c97c04f21b6534f4190`

## Result

The live pipeline completed successfully. It constructs a count-closed,
core-incident public K=2 temporal candidate universe, adds the complete public
boundary buffer for the selected core under the declared timestamp-rounding
model, and solves nested radius and Gamma candidate-support sensitivity curves.

This is not actual hidden-run closure. Shared Trip ID and co-rider identity are
not public; buffer rows' other run-mates are not recursively reconstructed.

## Cohort and boundary buffer

The selected core is the released 15-minute bin
`2026-01-13T17:30:00`--`2026-01-13T17:45:00`.

| Quantity | Result |
|---|---:|
| Literal `Shared Trip Match=true, Trips Pooled=2` core rows | 60 |
| Boundary-buffer rows | 551 |
| Total public temporal candidates | 611 |
| Determinate timestamp rows | 611 |
| Global K=2 rows with null start or end | 0 |
| Off-grid timestamps | 0 |
| Chronology-impossible released rows | 0 |
| Duplicate or blank trip IDs | 0 |
| Metadata and server counts stable | yes |
| Core recovered exactly | yes |
| Public temporal closure audit | `PASS` |

With release-rounding half-width \(\delta=7.5\) minutes, any determinate
partner candidate for a core row must obey

\[
\widehat s_j \le \max_{i\in C}\widehat e_i+2\delta,
\qquad
\widehat e_j \ge \min_{i\in C}\widehat s_i-2\delta.
\]

The extractor also globally counts and appends literal K=2/match rows with a
null released start or end. The 611-row pull was reconciled through a narrow
ID/start index and 14 exact released-start partitions. No raw row or trip ID is
serialized.

## Logical graph

| Quantity | Result |
|---|---:|
| Core nodes | 60 |
| Buffer nodes | 551 |
| Core--core candidate edges | 1,770 |
| Core--buffer candidate edges | 22,504 |
| Total temporal candidate edges | 24,274 |
| Role-compatible pairs ruled out by time | 10,556 |
| Edges without complete endpoint centroids | 11,865 (48.88%) |
| Full temporal cover | `OPTIMAL_NUMERICAL_MILP` |

The matching-cover model enforces core degree one and buffer degree at most
one. A core--core selected edge contributes two core incidences; a core--buffer
edge contributes one. Feasibility establishes only that the declared graph can
cover the core, not that any edge is an observed co-rider pair.

## Radius sensitivity

An edge is retained when both released pickup-centroid and dropoff-centroid
distances are within the radius. Missing centroid information is retained at
every radius.

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

At 2 km, the certified intervals are `[0.168685, 19.816457]` miles and
`[0.447222, 45.423333]` minutes. Relative to temporal-only support, this screen
narrows their widths by only 3.05% and 4.19%. The main limitation is public
spatial suppression: 48.88% of temporal edges cannot be screened by centroid
distance and must remain under the conservative policy.

## Measured out-of-radius incidence sensitivity

The base radius is 2 km. Gamma counts selected **core incidences** on
measured-distance edges outside that base: a core--core outside edge costs two
and a core--buffer outside edge costs one. Unmeasured-distance edges cost zero.
Gamma is therefore neither a total candidate-miss budget nor an estimated
partner-miss rate.

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

The curve is nearly saturated by Gamma=15--30. Gamma=0 is the 2 km feasible
set and Gamma=60 is the temporal-only feasible set. Those identities are
implemented by canonical reuse of the certified radius endpoints and also
checked structurally; the endpoint-identity audit is `PASS` with zero
mismatches.

## Certification and fail-closed results

There are 95 curve/query rows. Exactly 76 endpoint pairs publish a numeric
interval; every published pair has two `OPTIMAL_NUMERICAL_MILP` endpoints,
MIP gap zero, replay residual zero, finite ordered values, and a consistent
width. No uncertified pair publishes a lower bound, upper bound, or width.

The monotonicity audit is `PARTIAL`: 8/10 entire curve/query chains and 4/5
query families are fully certified and monotone, with zero mathematical
reversals. The two unresolved chains are fare. Six of 611 rows lack public
fare, affecting 512 temporal edges; no imputation or unaudited support bound is
introduced. Pickup and dropoff community-area fractions retain `[0,1]` across
the curve and are not identified by these constraints.

## Interpretation boundary

The strongest supported statement is one-bin and conditional: under the
declared release-rounding model, the public extraction is count-closed for
core-incident temporal candidates, and the four fully certified query families
widen monotonically as candidate support is relaxed.

It does not show that true Chicago pooled runs or partners were reconstructed,
that the buffer is recursively run-closed, that the radius has measured
partner recall, or that the selected bin identifies a Chicago-population
effect. Stable metadata and counts provide extraction consistency, not an
immutable transaction-level snapshot.
