# Key results

- Core: 60 literal public K=2/match rows in the released
  `2026-01-13 17:30--17:45` bin.
- Complete temporal boundary: 551 buffer rows, 611 candidates, and 24,274
  core-incident edges; full cover `OPTIMAL_NUMERICAL_MILP`.
- Boundary padding is a grid-induced step: `p=0,5,10` retain 459 buffers and
  21,645 edges; `p=15=2 delta` retains all 551 buffers and 24,274 edges;
  `p=30` is endpoint-identical to `p=15`.
- Completing the boundary adds 92 buffers (+20.04%), 92 total candidates
  (+17.73%), and 2,629 edges (+12.15%).
- Despite that graph expansion, miles-gap width rises only from 20.159137 to
  20.266142 (+0.107005, **0.53%**) and duration-gap width from 46.469722 to
  46.941944 minutes (+0.472222, **1.02%**).
- At 2 km: 11,965 edges; miles-gap interval `[0.168685, 19.816457]` and
  duration-gap interval `[0.447222, 45.423333]`. Relative to temporal-only,
  widths are only 3.05% and 4.19% narrower.
- Spatial suppression remains decisive: 11,865 edges (48.88%) lack complete
  released endpoint centroids and are retained at every radius.
- Gamma sensitivity is nearly saturated by `Gamma=15--30`; `Gamma=0` equals
  the 2 km feasible set and `Gamma=60` equals temporal-only.
- Public temporal closure, boundary endpoint identity, and radius/Gamma
  endpoint identity audits all `PASS` with zero mismatches.
- Monotonicity is `PARTIAL`: 12/15 complete chains across 4/5 query families
  are certified, with zero reversals.
- Exactly 96/120 endpoint pairs are certified optimal; all have MIP gap 0 and
  replay residual 0. The 24 unresolved pairs are fare chains and publish no
  bounds because six public rows lack fare.
- Main reading: **boundary-support robustness is strong, but absolute
  identification is weak**. Community-area intervals remain `[0,1]`.
