# Live public-data status

Last updated: 2026-09-04.

## Chicago release-operator audit

- Source commit: `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`
- Workflow run: `33837186969` (run 164)
- Artifact: `9923960043`
- Status: `PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY`
- Core / candidate / all-trip contributor rows: `60 / 611 / 50,405`
- Candidate and contributor counts: closed
- Dataset snapshot: stable during extraction
- Transport: narrow overlap index, 14 exact candidate-start shards, and
  14/13 exact contributor start/end shards

The run passed the live extraction, fail-closed claim assertions, and artifact
upload. It certifies the declared public extraction and conditional graph-cover
multiplicity. It does not validate private City production code, null causes,
hidden-run closure, or partner identity.

## Chicago K=2 boundary audit

The committed aggregate manifest under
`data_pipeline/results/chicago_k2_frontier_boundary/` records the current
boundary-complete sensitivity evidence. It is conditional on the declared
public temporal candidate universe.

## NYC

The frozen 24-window decision panel and branch-and-price scale lattice are
retained as pinned workflow artifacts and aggregate repository results. Their
public rows contain no event-membership truth; results are conditional on the
candidate and event-world contracts.
