# NYC HVFHV claim boundary

## Supported

- The official May 2026 HVFHV Parquet contains public shared-match flags,
  second-level pickup/drop-off timestamps, Taxi Zones, and trip outcomes.
- For the frozen smoke cohorts, the extraction and aggregate calculations
  completed successfully.
- Candidate multiplicity under provider/time overlap is large.
- On the fixed 2023 cohort, replacing exact public seconds by artificial
  nearest-15-minute outer intervals nests and enlarges the public candidate graph.
- Conditional on declared capacity `C in {2,3,4}`, connected positive-overlap
  interval runs with simultaneous occupancy bounded by `C` can be optimized with
  the exact compact interval-segment MILP used by the ordered-run Gate.
- Exact-second run-count endpoints and the published 15-minute ordered-run
  endpoints are numerically certified under the recorded smoke limits.
- Under the 15-minute outer model, root-invariant public-attribute composition
  bounds are certified both at each `C`-specific maximum support and at one
  common fixed support cardinality across `C=2,3,4`.
- For the common-support Gate, capacity nestedness is explicitly audited: lower
  endpoints weakly fall and upper endpoints weakly rise as `C` increases.
- Same-zone restrictions are reported only as analyst sensitivity screens.

## Not supported

- Actual co-rider or shared-run reconstruction.
- Hidden-run closure or partner recall outside the declared candidate universe.
- The assertion that NYC shared rides have realized pool size two, three, four,
  or any other value.
- Treating equal pickup or drop-off Taxi Zones as a necessary partner rule.
- Interpreting declared `C` as an estimate of true vehicle capacity.
- Production matching logic or vehicle/provider implementation fidelity.
- A representative NYC population estimate from either adaptively selected
  smoke cohort.
- A causal or policy effect.
- Validation of provider-submitted records beyond the public release.

## Current model boundary

NYC is analyzed as a temporally ordered latent-run decomposition with declared
capacity sensitivity `C=2,3,4`. Capacity restricts simultaneous occupancy, not
total run cardinality, so sequential members can accumulate in one connected
run. Chicago remains the exact public `K=2` benchmark.

The strongest clean comparison currently available is the common-support Gate:
72 selected buffer rows are held fixed across `C`, so capacity acts only as a
nested feasible-set relaxation. Exact-second membership-mass maximization is
still computationally unresolved at the short smoke limit and remains
unpublished unless separately certified.
