# Chicago release-operator audit evidence

This directory freezes the aggregate output of the live Chicago public
release-operator and pairing-identification Gate. It is a supplement to the
K=2 temporal frontier, not a reconstruction of hidden pooled runs.

## Decisive results

- The 611-row K=2 candidate universe was reconciled against 50,405 **all-trip**
  rows contributing to its released pickup/start and dropoff/end bins.
- Removing 5,812 boundary-touch-only edges leaves 18,462 strict-positive-
  overlap edges and an optimal core cover.
- A second optimal strict cover changes the partner assignment of all 60 core
  rows while every released row field remains fixed. Partner identity is
  therefore nonidentified.
- Of the strict edges, 9,339 have unmeasured spatial distance. Every strict
  cover needs at least 15 and can use as many as 60 unmeasured core incidences.
- In the 611 candidates, Community Area presence equals coordinate presence
  row-for-row at both endpoints. There is no candidate with a known Community
  Area but missing released coordinates to recover through a polygon fallback.
- The release rule prunes zero unmeasured-distance edges. Public blanks emit
  zero LOW tract-count literals and do not validate the City's private
  production implementation.

Files:

- `REPORT.md`: readable result and claim boundary.
- `release_operator_audit.json`: complete machine-readable aggregate audit.
- `RUN_MANIFEST.json`: workflow, artifact, snapshot, and file provenance.

The next informative candidate-support axis is
\(\Lambda\), the number of selected core incidences through spatially
unmeasured edges. It is distinct from \(\Gamma\), which costs measured edges
outside the analyst's radius.
