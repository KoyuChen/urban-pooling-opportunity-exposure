# Chicago release-operator identification-boundary evidence

This directory freezes the aggregate v2 output of the live Chicago public
release-operator identification-boundary Gate. It supplements the K=2 temporal
frontier; it does not reconstruct hidden pooled runs.

## Decisive results

- The 611-row K=2 candidate universe was reconciled against 50,405 **all-trip**
  rows contributing to its released pickup/start and dropoff/end bins.
- The closed outer released-time-envelope graph has 24,274 intersections.
  Of these, 5,812 touch only at the boundary and 18,462 have positive-length
  outer-envelope intersection. These are release-envelope relations, not
  evidence of actual trip overlap.
- Conditional on the 18,462-edge graph, two certified core covers exist and
  the displayed pair differs on all 60 core assignments. This is graph-cover
  multiplicity only; it is not a construction of two complete latent Chicago
  worlds and does not certify hidden-partner nonidentification.
- Over the same graph-cover feasible set, the sharp numbers of spatially
  unmeasured core incidences are 15 and 60. Of the graph's edges, 9,339 are
  spatially unmeasured.
- A separate abstract four-row witness shows that the documented public-field
  map does not encode Shared Trip ID. It does not apply to the observed cohort,
  is not linked to the displayed covers, and does not validate the City's full
  implementation.
- No partner is recovered from the public rows. Cohort partner identification
  is `NOT_ADJUDICATED_NO_FULL_WORLD_CERTIFICATE`; no identification or
  nonidentification theorem is claimed.
- Community Area and complete-coordinate presence happen to agree row-for-row
  in the 611 candidates, but not in the 50,405 contributor rows. The equality
  is snapshot-subset descriptive only and is not inferred to be a Chicago
  release rule.
- The release rule prunes zero spatially unmeasured edges. Public blanks emit
  zero LOW tract-count literals, and City implementation validation remains
  false.

Files:

- `REPORT.md`: readable result and claim boundary.
- `release_operator_audit.json`: complete machine-readable aggregate audit.
- `RUN_MANIFEST.json`: workflow, artifact, snapshot, and file provenance.

The next informative candidate-support axis is
\(\Lambda\), the number of selected core incidences through spatially
unmeasured edges. It is distinct from \(\Gamma\), which costs measured edges
outside the analyst's radius.
