# Chicago K=2 public temporal candidate universe and support sensitivity

Run date: 2026-09-01 UTC  
Validated live workflow run: `33468343107`  
Artifact: `chicago-k2-frontier`, ID `9785811599`  
Artifact ZIP SHA-256: `bcd9bfa5186cee322fa2fae954dc90d42dab2adda67311d607ee11ca97fdb460`  
Numerical-run source commit: `f573379b5e452712a52fec497f622ad888e84dd9`  
Dataset: City of Chicago `6dvr-xwnh`, Transportation Network Providers - Trips (2025-)  
Pinned public-view fingerprint: `52f2ff4772d94efe764a1406bacd7696ef473e7a2e626c97c04f21b6534f4190`

This run uses real Chicago TNP records. It constructs a count-reconciled,
core-incident public K=2 temporal candidate universe, includes every public
boundary-buffer row that can overlap the selected core after accounting for
15-minute timestamp rounding, and solves nested geographic-radius and Gamma
sensitivity curves. It does not reconstruct Shared Trip ID or validate true
partner recall.

## 1. Cohort and public temporal closure

The selected core is the released 15-minute bin
`2026-01-13T17:30:00`--`2026-01-13T17:45:00`.

| Quantity | Result |
|---|---:|
| Literal `Shared Trip Match=true, Trips Pooled=2` core rows | 60 |
| Boundary-buffer rows | 551 |
| Total K=2 temporal candidate rows | 611 |
| Determinate timestamp rows | 611 |
| Global K=2 rows with null start or end | 0 |
| Off-grid timestamps | 0 |
| Duplicate or blank trip IDs | 0 |
| Snapshot stable before/after | yes |
| Server counts stable before/after | yes |
| Core recovered exactly in final extract | yes |

For rounding half-width \(\delta=7.5\) minutes, every determinate public row
that can overlap at least one core trip must satisfy

\[
\widehat s_j \le \max_{i\in C}\widehat e_i+2\delta,
\qquad
\widehat e_j \ge \min_{i\in C}\widehat s_i-2\delta.
\]

The resulting released-timestamp cutoffs are 17:15 and 19:15. The extraction
used a narrow ID/start index followed by 14 exact start-time partitions. Every
partition was reconciled against a fresh server-side count and an ID-set hash.

**Supported status:** a count-closed, core-incident public temporal candidate
universe and boundary-complete core candidate superset under the released
15-minute timestamp model.

**Not supported:** actual hidden pooled-run closure. Shared Trip ID and partner
identity are not public, buffer rows' other run-mates are not recursively
reconstructed, and the object is not a union of recovered complete pooled runs.
This is also one adaptively selected bin rather than a city-population estimate.

## 2. Logical temporal graph

| Quantity | Result |
|---|---:|
| Core nodes | 60 |
| Buffer nodes | 551 |
| Core--core edges | 1,770 |
| Core--buffer edges | 22,504 |
| Total temporal candidate edges | 24,274 |
| Role-compatible pairs ruled out by time | 10,556 |
| Edges lacking complete endpoint centroids | 11,865 |
| Cover status | `OPTIMAL_NUMERICAL_MILP` |
| Cover MIP gap | 0 |

The graph only encodes literal K=2/match status, core/buffer incidence, and
possible closed-interval overlap after timestamp expansion. Feasibility means
that the declared graph admits a cover of every core row; it is not evidence
that any selected edge is an observed Chicago co-rider pair.

## 3. Nested route-radius sensitivity

An edge is retained when both released pickup-centroid and dropoff-centroid
distances are at most the radius. Missing centroid information is retained, not
silently treated as incompatibility. The sequence is nested and ends at the
full temporal graph.

| Radius | Edges | Temporal fraction | Miles-gap width | Duration-gap width (min) | Cover |
|---:|---:|---:|---:|---:|---|
| 0 km | 11,865 | 0.4888 | 19.1009 | 44.1086 | optimal, gap 0 |
| 0.25 km | 11,865 | 0.4888 | 19.1009 | 44.1086 | optimal, gap 0 |
| 0.5 km | 11,869 | 0.4890 | 19.4758 | 44.7933 | optimal, gap 0 |
| 1 km | 11,894 | 0.4900 | 19.4880 | 44.8375 | optimal, gap 0 |
| 2 km | 11,965 | 0.4929 | 19.6478 | 44.9761 | optimal, gap 0 |
| 4 km | 12,137 | 0.5000 | 19.6925 | 45.1900 | optimal, gap 0 |
| 8 km | 13,318 | 0.5487 | 19.8087 | 45.7725 | optimal, gap 0 |
| 16 km | 18,450 | 0.7601 | 20.2495 | 46.8222 | optimal, gap 0 |
| 32 km | 23,838 | 0.9820 | 20.2661 | 46.9419 | optimal, gap 0 |
| Temporal only | 24,274 | 1.0000 | 20.2661 | 46.9419 | optimal, gap 0 |

Relative to the full temporal graph, the 2 km screen reduces the trip-mile-gap
width by only **3.05%** and the duration-gap width by **4.19%**. Even the zero
radius sensitivity reduces those widths by only 5.75% and 6.04%. The main
reason is public-data suppression: 11,865 edges, 48.88% of the temporal graph,
lack complete endpoint centroids and must remain at every radius under the
conservative missing-spatial policy.

Both same-pickup-area and same-dropoff-area queries retain the full interval
\([0,1]\) at every radius. Public area fields and temporal cover constraints
alone therefore do not identify those composition queries in this cohort.

## 4. Measured out-of-radius incidence sensitivity

The base graph uses a 2 km endpoint-radius screen. \(\Gamma\) counts core
incidences assigned through **measured-distance** temporal edges outside that
screen; a core--core outside edge costs two and a core--buffer outside edge
costs one. Edges with unmeasured endpoint distance are already retained in the
base graph and cost zero. Thus \(\Gamma\) is not a total candidate-miss budget
and is not an estimated recall error rate.

| Gamma | Miles-gap width | Duration-gap width (min) | Cover |
|---:|---:|---:|---|
| 0 | 19.6478 | 44.9761 | optimal, gap 0 |
| 1 | 19.7376 | 45.2517 | optimal, gap 0 |
| 2 | 19.8172 | 45.4883 | optimal, gap 0 |
| 4 | 19.9539 | 45.8694 | optimal, gap 0 |
| 8 | 20.1535 | 46.4042 | optimal, gap 0 |
| 15 | 20.2519 | 46.8858 | optimal, gap 0 |
| 16 | 20.2542 | 46.9014 | optimal, gap 0 |
| 30 | 20.2660 | 46.9408 | optimal, gap 0 |
| 60 | 20.2661 | 46.9419 | optimal, gap 0 |

The curve saturates near the temporal-only range by about \(\Gamma=30\). All
reported lower endpoints are nonincreasing and all upper endpoints are
nondecreasing as the declared feasible set expands.

## 5. Fail-closed outcomes

Six of the 611 candidate rows have a missing public fare. Those rows induce 512
temporal edges with an undefined fare-gap coefficient. Because no audited
finite support bound was supplied for missing fares, the fare-gap frontier is
reported as `UNRESOLVED_MISSING_PUBLIC_QUERY_VALUES`; missing values are not
imputed or replaced by observed extrema.

The successful numerical run returned an integer incumbent for every resolved
program with independent constraint replay, status `OPTIMAL_NUMERICAL_MILP`,
and MIP gap zero. These are solver-qualified numerical endpoints, not exact
rational certificates. A later hardening pass added fail-closed chain-level
certification and endpoint-identity audits; result provenance remains pinned to
the immutable workflow artifact above.

## 6. Empirical conclusion

The real-data pipeline and boundary extraction pass. Chicago can replace the
earlier wholly simulated Chicago-like geography as a real-record application
environment with semantic distance, duration, fare, and area queries.

The result is deliberately negative about identification. Public geographic
suppression leaves almost half of temporal edges spatially unmeasured; the 2 km
screen only modestly narrows the two resolved continuous queries; categorical
composition remains unidentified; and fare fails closed. The next application
gain must come from an audited release operator, independently defensible
candidate support, or restricted partner truth. It cannot be manufactured by
treating missing geography as a non-edge.

Raw rows, raw trip IDs, and matching witnesses were never serialized.
