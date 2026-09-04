# Chicago live release-operator audit

Status: `PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY`.

## Frozen source

- Source commit: `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`
- Workflow run: `33837186969` (run 164)
- Artifact: `9923960043`
- Artifact ZIP SHA-256: `98b7117b14c3150df655d88f171be6f05d0774449af18d354fac98f639e1226b`
- Source JSON SHA-256: `26b682d967716cfc356cfc4d68a39446bdc85c941d676bb7bea5323e1f71dca3`
- Source JSON self-hash: `79b8825ade529b41fbb144e44e0f6f61dec8126ed90ee87a328b8d6e43899fe6`

## Extraction

| Quantity | Result |
|---|---:|
| Core rows | 60 |
| K=2 temporal candidates | 611 |
| Candidate rows with a null time endpoint | 0 |
| All-trip endpoint-bin contributors | 50,405 |
| Candidate exact-start shards | 14 |
| Contributor start/end shards | 14 / 13 |
| Candidate count closed | yes |
| Contributor count closed | yes |
| Snapshot stable during extraction | yes |
| Raw rows or trip IDs serialized | no |

The transport is
`NARROW_OVERLAP_INDEX_THEN_EXACT_START_AND_ENDPOINT_BIN_SHARDS`. It first
retrieves a narrow cross-column overlap index, then fetches full candidate rows
by exact released-start bins and all release-cell contributors by exact start
or end bins. Broad `OR` pulls and full-row cross-column range queries are not
used. Duplicate public IDs with inconsistent payloads fail closed.

## Conditional graph-cover multiplicity

| Quantity | Result |
|---|---:|
| Closed outer-envelope intersections | 24,274 |
| Positive-length intersections | 18,462 |
| Boundary-touch-only intersections | 5,812 |
| Cover A selected edges | 51 |
| Cover B selected edges | 53 |
| Core assignments changed | 60 / 60 |
| Maximum reported MIP gap | 0 |
| Maximum replay residual | 0 |

The positive-length outer released-time-envelope graph admits two distinct
optimal core covers. This is a conditional graph statement. It is not a pair of
complete operational hidden-run worlds: the audit does not construct common
exact timestamp witnesses, complete the remaining buffer runs, validate
provider/vehicle feasibility, or recover partners.

## Release and spatial claim boundary

The public documentation licenses only one-way release implications. The audit
emits zero inferred LOW tract literals and does not invert a blank centroid into
a privacy-cell claim. No finite radius is imposed on spatially unmeasured rows;
radius analyses remain candidate-support sensitivities rather than necessary
compatibility rules.

Supported claims are snapshot-relative candidate/contributor count closure,
documented one-way semantics, and conditional core-cover multiplicity in the
positive-length outer-envelope graph. Not supported are private City
implementation fidelity, null-cause identification, hidden-run closure,
partner identity or recall, realized capacity, or a finite spatial support rule
for missing centroids.
