# Chicago K=2 live frontier evidence

This directory contains aggregate, redacted evidence from the 2026-09-01 live
Chicago run. See `REPORT.md` for interpretation, `candidate_graph_curve.csv`
for graph/feasibility points, `query_width_curve.csv` for the two resolved
continuous-query frontiers, and `RUN_MANIFEST.json` for pinned provenance.

The complete workflow artifact additionally contains the full long-form
sensitivity table, machine-readable report, and SVG figures. No raw trip row,
raw trip identifier, or selected matching witness is committed.

The precise object is a **count-closed, core-incident public temporal candidate
universe**: a boundary-complete candidate superset for one core bin under the
declared 15-minute timestamp-release model. It is not actual hidden-run
closure. Shared Trip ID and partner identity remain unavailable; buffer rows'
other run-mates are not recursively reconstructed.

The geographic radius family is an analyst sensitivity. Missing endpoint
centroids are retained at every radius. The Gamma family counts only measured
out-of-radius core incidences; it is not a total candidate-miss budget or an
estimated recall error rate.
