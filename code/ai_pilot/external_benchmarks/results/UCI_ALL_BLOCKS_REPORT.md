# UCI Krebsregister all-ten-block audit

Generated for the frozen observed run on 2026-08-27. This artifact stores no
registry identifier, source row, pair label, truth edge, or raw endpoint edge
list. It discloses only aggregate witness replay counts and a SHA-256 digest.
Topology/count aggregation is deterministic; the recorded time-limit status
may depend on hardware and scheduling.

## Snapshot and exact reconciliation

All ten pinned cached inner ZIPs passed CRC, exact member-name, member-hash,
schema, and value-domain checks.  The cache does not retain the outer
`donation.zip`, so no outer-archive SHA-256 is claimed.

- Rows: 5,749,132; unique undirected pairs: 5,749,132.
- Positive pairs: 20,931; negative pairs: 5,728,201.
- Duplicate pair groups: 0; cross-block duplicates: 0; label conflicts: 0; self-pairs: 0.
- Candidate graph: 99,788 observed records in 52 components; the largest has 99,666 records.

The blocks are edge partitions, not markets.  Every pair of blocks shares
between 91,624 and
91,873 records, and
82,846 records occur in all ten.

## Relation topology

The 20,931 adjudicated positive edges form
12,925 entity components over
29,301 records.  The largest entity has
9 records and maximum positive degree is
8.  Therefore the released positive
relation is **not a matching**.  The audit does not split larger entities into
invented pairs.  All observed positive components are complete cliques and no
released negative edge lies inside one of them.

## Explicitly truth-conditioned dyad sensitivity

There are 10,313 global two-record
positive components.  Removing 16
whose true postal comparison is missing leaves 10,297
truth dyads.  Their induced candidate graph has 249,048
edges, of which 238,751 are alternatives.  One
component contains 19,346 records and
93.94% of retained dyads, so
no component-based source/calibration/test split is reported.
The induced graph is nonbipartite in 46 components; a 3-edge odd-cycle commitment rules out a Hungarian/assignment shortcut without releasing its nodes.

The dyad frontier status is **UNRESOLVED**. Lower endpoint: **UNRESOLVED**; upper endpoint: **0.963776**. Verified Blossom lower endpoint exceeded the predeclared 120-second limit. This does not affect the completed topology audit, and no partial endpoint is described as a full frontier.

## Claim boundary

- UCI validates real relation topology conditional on its released blocking graph.
- The dyad frontier is a truth-conditioned matching sensitivity, not a prevalence estimate or calibrated confidence set.
- Blocks are neither independent observations nor empirical markets.
- The audit does not validate blocking recall, latent node attributes, or transfer to Chicago.
