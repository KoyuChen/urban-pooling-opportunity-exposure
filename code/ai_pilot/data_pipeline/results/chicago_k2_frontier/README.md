# Chicago K=2 public temporal frontier

This directory contains the aggregate, redacted output of the live Chicago
K=2 cohort run. The scientific object is a **count-closed, core-incident public
temporal candidate universe** and a boundary-complete candidate superset for
one selected core bin under the declared timestamp-rounding model.

Start with `REPORT.md`. Machine-readable evidence is in `report.json`,
`candidate_graph_curve.csv`, and `candidate_support_sensitivity.csv`;
`query_width_curve.csv` is a compact certified view of the miles and duration
frontiers. The generated report and SVG plots are retained verbatim from the
workflow artifact.

This is not hidden-run closure, partner reconstruction, recursive closure over
buffer rows, a measured partner-recall curve, or a Chicago-population estimate.
Gamma counts only measured out-of-radius core incidences. Edges with unmeasured
endpoint distance remain available and cost zero, so Gamma is not a total miss
budget or miss-rate estimate.

No raw trip row, raw trip identifier, or selected matching witness is included.
