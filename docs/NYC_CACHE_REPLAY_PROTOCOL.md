# NYC cache replay protocol

The September 4 scale artifact and four September 6 follow-up artifacts were
downloaded and inspected before defining this experiment. They contain only
aggregate reports, cell tables, and driver manifests. Consistent with their
redaction declarations, they contain neither row-level inputs nor a fixed-row
hash. A byte-identical replay is therefore unavailable.

The paired experiment uses a narrower, auditable claim. It reruns the original
deterministic selection rule only if all of the following match the frozen
report exactly:

- TLC dataset identity, schema hash, revision fingerprint, and update times;
- provider and selected core window;
- 38 source-core rows and 437 candidate rows;
- the historical cache-off optimum, bounds, processed nodes, branch counts,
  maximum depth, selected-column count, generated-column count, pricing-case
  count. The historical `oracle_lp_solve_count` is not compared because the
  old instrumentation also incremented on cases rejected before `linprog`;
  the paired experiment counts only actual LP calls on both sides.

Only after these checks pass is cache-on compared with cache-off. The only
primary acceleration outcome is the deterministic reduction in actual
fixed-span LP calls. Wall-clock time is descriptive. A timeout, source drift,
historical diagnostic mismatch, or certificate/path mismatch fails the cell;
none is relabeled infeasible.

The four predeclared targets are `10+30,C=4`, `12+36,C=4`, `16+48,C=3`, and
`16+48,C=4`, which accounted for the dominant runtime in the frozen lattice.
Even if all pass, the result remains a snapshot-consistent reconstruction, not
a byte-identical historical replay or a city-scale runtime claim.
