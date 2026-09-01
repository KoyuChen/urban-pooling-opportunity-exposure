# NYC HVFHV claim boundary

## Supported

- The official May 2026 HVFHV Parquet contains public shared-match flags,
  second-level pickup/drop-off timestamps, Taxi Zones, and trip outcomes.
- For the frozen smoke cohorts, the extraction and aggregate calculations
  completed successfully.
- Candidate multiplicity under provider/time overlap is large.
- On the fixed 2023 cohort, replacing exact public seconds by artificial
  nearest-15-minute outer intervals nests and enlarges the candidate graph.
- Conditional on a declared pairwise `C=2` cover benchmark, the published
  lower and upper query endpoints are numerically optimal with zero reported
  MIP gap and zero replay residual.
- Same-zone restrictions are reported only as analyst sensitivity screens.

## Not supported

- Actual co-rider or shared-run reconstruction.
- Hidden-run closure or partner recall.
- The assertion that NYC shared rides have realized pool size two.
- Treating equal pickup or drop-off Taxi Zones as a necessary partner rule.
- A representative NYC population estimate from either adaptively selected
  smoke cohort.
- A causal or policy effect.
- Validation of provider-submitted records beyond the public release.

## Required next model

NYC should be formulated as a temporally ordered latent-run decomposition with
unknown capacity, with `C=2,3,4` treated as an explicit sensitivity or bounded
capacity assumption. Chicago remains the exact public `K=2` benchmark.
