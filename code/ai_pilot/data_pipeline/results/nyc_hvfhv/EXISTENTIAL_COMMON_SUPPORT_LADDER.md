# NYC Gate F: common-support reachability ladder

Frozen evidence date: 2026-09-02 UTC

This note holds the reduced public cohort fixed at four core rows and twelve
outcome-blind candidate buffers. The exact side fixes the released second-level
timestamps and is solved by complete feasible-run-column enumeration plus an
exact disjoint-column master. The artificial coarse side selects latent exact
pickup and drop-off times inside nearest-15-minute endpoint supports with
independent `+/-7.5` minute ranges.

## Feasibility ladder

| Selected buffers | Per core | Exact C=2 | Exact C=3 | Exact C=4 | Coarse existential C=2 | Coarse C=3 | Coarse C=4 |
|---:|---:|---|---|---|---|---|---|
| 4 | 1.00 | feasible | feasible | feasible | feasible | feasible | feasible |
| 6 | 1.50 | **proven infeasible** | feasible | feasible | feasible | feasible | feasible |
| 8 | 2.00 | **proven infeasible** | feasible | feasible | feasible | feasible | feasible |

The `q=6` exact `C=2` cell is resolved by complete enumeration, not by a
timeout. The strict CI Gate therefore treats it as certified negative evidence,
while failing only unresolved cells.

## Conditional public-outcome bounds

Whenever a row in the table above is feasible, every compared time/capacity
cell attains the same endpoint pair for this cohort:

| Selected buffers | Mean selected-buffer miles | Mean selected-buffer duration |
|---:|---:|---:|
| 4 | `9.267750--24.658000` | `49.9500--83.6000` minutes |
| 6 | `11.452667--22.987667` | `56.0944--80.5194` minutes |
| 8 | `13.501250--21.196375` | `60.6604--77.4854` minutes |

Thus the first detectable effect of artificial timestamp support in this audit
cohort is on the **extensive margin of support reachability**. Once a fixed
support cardinality is feasible, the same public-row composition extremes are
attainable here. This equality is an empirical property of this selected
cohort, not a theorem for all interval-run instances.

## Provenance

- Support-cardinality frontier: workflow `33591752562`; artifacts
  `9832042153`, `9832010646`, and `9832005876`.
- Common-support ladder: workflow `33599734797`.
- `q=1.0` artifact `9834753255`,
  digest `sha256:e2cce5dcf9e8686cdc6c53e31f7754d1cb7da502c22db3b35c1ed496b0a7f41d`.
- `q=1.5` artifact `9834834349`,
  digest `sha256:1b6f4d9b42365247692e4aa66324e189d440f0f79ade162655f50b130678d74c`.
- `q=2.0` artifact `9834814462`,
  digest `sha256:01f1309d85d80e479ea23fe94f2a1f48c1fb684b8ca266b6a6f0686413420d66`.

No raw row, row identifier, run assignment, or latent timestamp witness is
committed. These are conditional feasible-world statements under an artificial
support experiment; they do not recover actual co-riders, vehicle runs,
realized capacity, or TLC production logic.
