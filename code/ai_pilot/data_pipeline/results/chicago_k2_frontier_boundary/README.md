# Chicago K=2 public temporal frontier

This directory contains aggregate, redacted evidence from the successful live
Chicago K=2 run at numerical source commit
`bd51ed45485d4f52af433b3d5b3eb0670d6442ea`.

Read `KEY_RESULTS.md` for the numerical takeaway, `REPORT.md` for the audited
interpretation, `CLAIM_BOUNDARY.md` for supported and prohibited statements,
and `RUN_MANIFEST.json` plus the CSV/JSON files for machine-readable provenance.
The generated workflow report is retained verbatim as
`CHICAGO_K2_PUBLIC_TEMPORAL_FRONTIER_REPORT.md`.

The support analysis has three axes: released-time boundary padding, released
endpoint-centroid radius, and measured out-of-radius core-incidence budget
Gamma. The complete `p=15=2 delta` boundary adds 12.15% more temporal edges than
`p<15`, while the miles- and duration-gap widths change by only 0.53% and 1.02%.

This is a count-closed, core-incident public temporal candidate universe. It is
not hidden-run closure, partner reconstruction, recursive closure over buffer
rows, a partner-recall curve, or a Chicago-population estimate.

Local or server reproduction is documented in
`../../production_audit/BOUNDARY_PADDING_PROTOCOL.md` and runs from the repo
root with:

```bash
bash scripts/run_chicago_k2_boundary_local.sh
```

No raw trip rows, raw trip identifiers, or selected matching witnesses are
included.
