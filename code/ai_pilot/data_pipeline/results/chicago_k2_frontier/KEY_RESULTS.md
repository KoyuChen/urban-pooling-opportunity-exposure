# Key results

- Core: 60 literal public K=2/match rows in the released
  2026-01-13 17:30--17:45 bin.
- Boundary buffer: 551 rows; total public temporal candidates: 611.
- Temporal graph: 24,274 edges (1,770 core--core and 22,504 core--buffer);
  full cover `OPTIMAL_NUMERICAL_MILP`.
- Spatial suppression: 11,865 edges (48.88%) lack complete released endpoint
  centroids and are retained at every radius.
- At 2 km: 11,965 edges; miles-gap interval
  `[0.168685, 19.816457]`, width 19.647772 miles; duration-gap interval
  `[0.447222, 45.423333]`, width 44.976111 minutes.
- Temporal-only: miles width 20.266142 and duration width 46.941944. Relative
  to temporal-only, the 2 km screen narrows the widths by only 3.05% and 4.19%.
- Gamma sensitivity widens monotonically and is nearly saturated by
  Gamma=15--30; Gamma=0 equals the 2 km feasible set and Gamma=60 equals the
  temporal-only feasible set.
- Endpoint identity audit: `PASS`, zero mismatches. Monotonicity:
  `PARTIAL` because 8/10 complete chains (4/5 query families) are certified;
  there are zero mathematical reversals.
- Exactly 76/95 endpoint pairs are certified optimal, all with MIP gap 0 and
  replay residual 0. The other 19 are the fare chain and publish no bounds.
- Six candidate rows lack public fare, affecting 512 temporal edges. Fare is
  fail-closed; pickup/dropoff community-area intervals remain `[0,1]`.
