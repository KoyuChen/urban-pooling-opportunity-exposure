# Chicago public release-operator identification-boundary audit

Generated: 2026-09-01T06:55:48+00:00  
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
| Positive-length outer released-time-envelope intersections | 18462 |
| Outer released-time envelopes touching only at the boundary | 5812 |
| Positive-length outer-envelope graph cover | `OPTIMAL_NUMERICAL_MILP` |
| Alternative graph cover | `OPTIMAL_NUMERICAL_MILP` |
| Core assignments changed between displayed covers | 60 |
| Pickup area without complete coordinates | 0 |
| Dropoff area without complete coordinates | 0 |

## Identification boundary

An edge in the positive-length graph means only that the two outer activity
envelopes intersect with positive length; it does not establish actual trip
overlap. Conditional on that graph, the certificate is
`CERTIFIED_TWO_DISTINCT_CORE_COVERS_IN_POSITIVE_LENGTH_OUTER_RELEASED_TIME_ENVELOPE_GRAPH`. The
two displayed covers differ on 60
of 60 core assignments. This is graph-cover multiplicity,
not two fully constructed Chicago hidden-run worlds: the audit does not
construct common exact timestamp witnesses, vehicle/provider feasibility, or a
complete pairing of the remaining buffer rows.

A separate abstract four-row construction shows that the documented public
field map can remain unchanged while confidential run/vehicle linkage changes.
That abstraction does not validate the City's private implementation or prove
a cohort-level full-world completion, and it is not linked to the displayed
graph covers. The operational recovery status is
`NOT_RECOVERED_FROM_PUBLIC_ROWS`; cohort identification is
`NOT_ADJUDICATED_NO_FULL_WORLD_CERTIFICATE`. No hidden-partner
identification or nonidentification theorem is claimed.

## Spatial consequence

Release suppression does not license any new deletion of an edge with
unmeasured centroid distance. A centroid blank can reflect an outside-Chicago
endpoint or unavailable source data; tract coarsening usually publishes a
community-area centroid instead. The fail-closed finite-radius policy is to
retain every spatially unmeasured edge. Radius and Gamma remain
candidate-support sensitivities, not necessary partner-compatibility rules.
Any Community Area/coordinate mask equality is descriptive of the extracted
snapshot subset only; it is not inferred to be a Chicago release rule.

## Claim boundary

Supported: snapshot-relative count closure of the public temporal candidate universe and all public rows contributing to its released endpoint bins; documented one-way release semantics; an abstract release-map noninjectivity witness; and conditional core-cover multiplicity in the positive-length outer released-time-envelope graph.

Not supported: City production-code fidelity, latent tract-cell reconstruction, blank-cause identification, hidden-run closure, partner identity or recall, hidden-partner identification or nonidentification, and any finite spatial support rule for missing centroids.
