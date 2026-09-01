# Chicago public release-operator and pairing audit

Generated: 2026-09-01T06:13:03+00:00  
Overall status: `PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY`

## Result

The public extraction is snapshot-relative and count-closed for the K=2
temporal candidates and for every public trip contributing to their released
endpoint bins. The audit does **not** validate the City's private production
transformation. It emits zero LOW tract-count literals and never interprets a
public blank as a privacy cell without independent evidence.

| Quantity | Result |
|---|---:|
| Core rows | 60 |
| K=2 public temporal candidates | 611 |
| All-trip endpoint-bin contributors | 50405 |
| Candidate rows with a null time endpoint | 0 |
| Strict-positive-overlap edges | 18462 |
| Boundary-touch-only edges | 5812 |
| Strict graph cover | `OPTIMAL_NUMERICAL_MILP` |
| Alternative strict cover | `OPTIMAL_NUMERICAL_MILP` |
| Core assignments changed between covers | 60 |
| Pickup area without complete coordinates | 0 |
| Dropoff area without complete coordinates | 0 |

## Non-identification certificate

The certificate status is
`CERTIFIED_TWO_DISTINCT_PUBLICLY_COMPATIBLE_COVERS`. Two distinct strict-overlap covers
produce different core partner assignments while every public per-trip field
is fixed. This is possible because the confidential Shared Trip ID is omitted
from the public schema and the tract privacy rule operates on rows/cells, not
on run identity. Therefore the public release operator is pairing-invariant and
partner identity remains `NONIDENTIFIED`.

## Spatial consequence

Release suppression does not license any new deletion of an edge with
unmeasured centroid distance. A centroid blank can reflect an outside-Chicago
endpoint or unavailable source data; tract coarsening usually publishes a
community-area centroid instead. The fail-closed finite-radius policy is to
retain every spatially unmeasured edge. Radius and Gamma remain
candidate-support sensitivities, not necessary partner-compatibility rules.

## Claim boundary

Supported: snapshot-relative count closure of the public temporal candidate universe and all public rows contributing to its released endpoint bins; documented one-way release semantics; public pairing non-identification.

Not supported: City production-code fidelity, latent tract-cell reconstruction, blank-cause identification, hidden-run closure, partner identity or recall, and any finite spatial support rule for missing centroids.
