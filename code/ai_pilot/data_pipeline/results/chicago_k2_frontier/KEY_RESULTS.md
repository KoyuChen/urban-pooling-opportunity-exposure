# Key numerical results

- Core: 60 public `Shared Trip Match=true, Trips Pooled=2` rows in the
  2026-01-13 17:30--17:45 released bin.
- Boundary buffer: 551 additional K=2 rows not ruled out by the expanded public
  timestamp intervals.
- Candidate universe: 611 rows, 24,274 temporal edges, zero null endpoint rows,
  stable snapshot and stable server counts.
- Conservative spatial missingness: 11,865 edges (48.88%) have incomplete
  public endpoint centroids and remain in every radius graph.
- At 2 km, the candidate screen retains 11,965 edges (49.29% of temporal) and
  reduces the trip-mile-gap width by 3.05% and duration-gap width by 4.19%
  relative to temporal-only support.
- Under the 2 km base graph, relaxing the candidate-miss budget from Gamma=0
  to Gamma=60 widens the trip-mile-gap interval from 19.6478 to 20.2661 and the
  duration-gap interval from 44.9761 to 46.9419 minutes.
- Radius and Gamma curves pass the automated nested-set monotonicity audit with
  zero violations. Every resolved endpoint has numerical MILP status optimal
  and MIP gap zero.
- Pickup/dropoff community-area composition remains `[0,1]` at every point.
- Fare-gap endpoints fail closed because 6 candidate rows have missing fare,
  affecting 512 temporal edges; no unaudited support bound or imputation is
  introduced.
