# Synthetic known-truth validation

This experiment creates 30 latent co-rider pairs per replicate, then
rounds their timestamps before candidate generation. It evaluates the share of
selected pairs in the same SES bin. The score-constrained interval contains
only packings with at least 95% of the maximum compatibility
score; it is a sensitivity region, not a confidence interval.

| time_bin_minutes | replicates | candidate_recall | candidate_multiplier_mean | raw_coverage | raw_width_mean | score_coverage | score_width_mean | width_reduction_fraction | point_mae |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 20 | 100.0% | 1.038 | 100.0% | 0.003 | 100.0% | 0.003 | 0.0% | 0.000 |
| 5 | 20 | 100.0% | 1.197 | 100.0% | 0.020 | 100.0% | 0.007 | 66.7% | 0.000 |
| 15 | 20 | 100.0% | 1.563 | 100.0% | 0.073 | 100.0% | 0.020 | 72.7% | 0.000 |
| 30 | 20 | 100.0% | 2.107 | 100.0% | 0.150 | 100.0% | 0.027 | 82.2% | 0.000 |

## Interpretation

- Raw set-packing bounds should cover truth whenever every latent pair remains
  in the candidate graph. This is the implementation's primary coverage check.
- Coarser public time bins admit more alternative pairings and should widen the
  raw identified interval.
- Score restriction can shorten intervals, but coverage is an empirical model
  diagnostic. It must not be described as data-identified without assumptions.
- The maximum-score matching is a point reconstruction for diagnostics only.
  The pilot's estimand is the interval over feasible compatibility packings.
