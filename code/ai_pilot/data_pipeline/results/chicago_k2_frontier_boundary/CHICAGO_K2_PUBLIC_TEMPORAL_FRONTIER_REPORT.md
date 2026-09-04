# Chicago K=2 public temporal candidate-universe closure and sensitivity

Generated UTC: `2026-09-01T13:55:12+00:00`  
Dataset: City of Chicago `6dvr-xwnh`, Transportation Network Providers - Trips (2025-)  
Snapshot fingerprint: `52f2ff4772d94efe764a1406bacd7696ef473e7a2e626c97c04f21b6534f4190`

## Public temporal candidate-universe closure

The selected core is the released 15-minute bin `2026-01-13T17:30:00` to `2026-01-13T17:45:00`. It contains **60** literal `Shared Trip Match=true, Trips Pooled=2` rows.

The direct overlap-envelope query retrieved **611** target rows: **551** boundary-buffer rows plus the core. This is a boundary-complete candidate superset for core-incident public temporal edges. Closure status: **PASS**.

The object is count-closed under the declared released-timestamp model. It is explicitly not hidden-run closure: Shared Trip ID and partner identity are not public, buffer rows' other run-mates are not recursively fetched, and the candidate set is not a union of reconstructed complete pooled runs.

| Check | Result |
|---|---|
| Metadata stable before/after | `True` |
| Server counts stable before/after | `True` |
| Core rows recovered in candidate extract | `True` |
| Global null-start/end K=2 targets included | `True` (0) |
| Released chronology impossible rows | `0` |
| Full temporal cover optimal | `True` |
| Hidden run closure | `NOT_IDENTIFIED_AND_NOT_CLAIMED` |

This is a one-bin, adaptively selected smoke test, not evidence for the Chicago trip population. Stable metadata and counts protect extraction consistency but do not create an immutable transaction-level snapshot. Query coefficients are computed from released public fields and are not latent exact trip attributes.

## Logical temporal graph

The logical graph has **60** core nodes, **551** buffer nodes, and **24274** candidate edges. Its cover status is `OPTIMAL_NUMERICAL_MILP`. This only establishes feasibility of the declared graph.

## Radius sensitivity

Edges are retained when both released endpoint-centroid distances are at most the radius. An edge with missing centroid information is retained at every radius. The family is nested and ends at the full temporal graph.

| Radius | Edges | Temporal fraction | Core zero-degree | Cover status |
|---:|---:|---:|---:|---|
| 0 km | 11865 | 0.489 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| 0.25 km | 11865 | 0.489 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| 0.5 km | 11869 | 0.489 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| 1 km | 11894 | 0.490 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| 2 km | 11965 | 0.493 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| 4 km | 12137 | 0.500 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| 8 km | 13318 | 0.549 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| 16 km | 18450 | 0.760 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| 32 km | 23838 | 0.982 | 0 | `OPTIMAL_NUMERICAL_MILP` |
| temporal-only | 24274 | 1.000 | 0 | `OPTIMAL_NUMERICAL_MILP` |

## Boundary-padding sensitivity

The boundary-padding axis retains the core and every timestamp-indeterminate target row, then expands the determinate buffer using released-time padding `p`. Under the declared rounding model, `p=15` minutes is the complete endpoint (`2δ`); larger values reuse that endpoint by identity.

| Padding p | Buffer rows | Edges | Miles-gap width | Duration-gap width (min) | Source |
|---:|---:|---:|---:|---:|---|
| 0 min | 459 | 21645 | 20.1591 | 46.4697 | `direct_milp` |
| 5 min | 459 | 21645 | 20.1591 | 46.4697 | `direct_milp` |
| 10 min | 459 | 21645 | 20.1591 | 46.4697 | `direct_milp` |
| 15 min | 551 | 24274 | 20.2661 | 46.9419 | `direct_milp` |
| 30 min | 551 | 24274 | 20.2661 | 46.9419 | `canonical_complete_boundary_identity` |

Padding below 15 minutes is deliberately under-complete and has no partner-recall interpretation. Padding at or above 15 minutes does not establish hidden-run closure; it closes only the declared core-incident public temporal candidate universe.

Boundary endpoint identity audit: `PASS`.

## Measured out-of-radius incidence sensitivity

The base radius is **2.0 km**. Γ counts core incidences assigned through edges whose measured endpoint distance exceeds that radius; a measured out-of-radius core-core edge costs two and a core-buffer edge costs one. Edges with unmeasured endpoint distance are retained at every radius and cost zero. Therefore Γ is neither a total candidate-miss budget nor an estimated miss rate.

| Γ | Cover status | Mean miles-gap width | Same-dropoff-area width |
|---:|---|---:|---:|
| 0 | `OPTIMAL_NUMERICAL_MILP` | 19.65 | 1 |
| 1 | `OPTIMAL_NUMERICAL_MILP` | 19.74 | 1 |
| 2 | `OPTIMAL_NUMERICAL_MILP` | 19.82 | 1 |
| 4 | `OPTIMAL_NUMERICAL_MILP` | 19.95 | 1 |
| 8 | `OPTIMAL_NUMERICAL_MILP` | 20.15 | 1 |
| 15 | `OPTIMAL_NUMERICAL_MILP` | 20.25 | 1 |
| 16 | `OPTIMAL_NUMERICAL_MILP` | 20.25 | 1 |
| 30 | `OPTIMAL_NUMERICAL_MILP` | 20.27 | 1 |
| 60 | `OPTIMAL_NUMERICAL_MILP` | 20.27 | 1 |

## Audit conclusion

Nested-set monotonicity: `PARTIAL`.  
Endpoint identities: `PASS`.  
Monotonicity claim: **Only 12 of 15 entire curve/query chains are fully certified and monotone, covering 4 of 5 complete query families; no universal monotonicity claim is made.**  
Strongest supported statement: **For one adaptively selected 15-minute smoke-test core, this metadata/count-stable extraction yields a count-closed, core-incident K=2 public temporal candidate universe under the declared timestamp-rounding model; the p=15 minute endpoint is boundary-complete, p>15 is endpoint-identical, and monotonic widening is supported only for the complete certified chains identified by the audit across padding, radius, and Gamma.**  
Prohibited statement: **The true Chicago pooled runs or co-rider partners have been reconstructed; the buffer is recursively hidden-run closed; padding below 15 minutes has partner-recall validity; the radius/Gamma axes estimate partner misses; or this selected bin establishes a Chicago-population effect.**

Raw trip rows, raw trip IDs, and selected matching witnesses are not serialized.
