# Conformal matching-set benchmark

This fully synthetic benchmark trains on 40 source markets,
calibrates on 49 independent target-style markets,
and evaluates 120 held-out markets. The requested matching-
set coverage is 90%. The arbitrary comparator retains only
matchings within normalized regret 0.05 without
calibration.

- `target_free`: tau=0.3406, rank=45/49.
- `query_leaking`: tau=0.5038, rank=45/49.

| scorer | test_markets | raw_coverage | raw_width | calibrated_matching_coverage | calibrated_statistic_coverage | calibrated_width | arbitrary_matching_coverage | arbitrary_statistic_coverage | arbitrary_width | point_mae | calibrated_width_reduction | arbitrary_width_reduction | calibrated_tau |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| query_leaking | 120 | 100.0% | 0.661 | 97.5% | 100.0% | 0.611 | 15.0% | 24.2% | 0.028 | 0.308 | 7.6% | 95.8% | 0.504 |
| target_free | 120 | 100.0% | 0.661 | 95.8% | 100.0% | 0.636 | 30.0% | 83.3% | 0.194 | 0.122 | 3.8% | 70.6% | 0.341 |

Both scorers are directly supervised by true edges in the disjoint source
markets. The target-free scorer uses route, time, and duration similarity. The
query-leaking diagnostic additionally sees same-SES equality, which is exactly
the edge contribution to the downstream statistic. The source generating
homophily probability is 95%, whereas the calibration
and test probability is 55%. The radius 0.05 is an
illustrative stress point, not a calibrated baseline. Results validate only
the finite-sample matching-set calibration implementation on this fixed split.
They do not validate weak supervision, privacy-count coupling, candidate
support, or exchangeability for Chicago.
