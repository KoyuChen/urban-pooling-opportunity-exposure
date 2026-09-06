# ATR DIAMOR cardinality-uncertainty audit v1

Status: **PASS** for both frozen days and all three cardinality regimes.

The all-positive-q regime removes group labels from endpoint cardinality, but labels still determine cohort eligibility, exclusions, and truth evaluation. The mean-distance query conditions on at least one dyad because it is undefined at q=0.

| Cardinality information | Exact feasible cells | Proved infeasible | Mean width (m) | Certified decisions | False certificates |
|---|---:|---:|---:|---:|---:|
| Oracle q | 806 | 44 | 1.176 | 1286/2418 (53.2%) | 16 |
| q +/- 1 | 825 | 25 | 1.245 | 1179/2475 (47.6%) | 21 |
| All positive q | 826 | 24 | 1.297 | 1136/2478 (45.8%) | 20 |

Allowing unknown cardinality makes 20 additional cells appear feasible relative to oracle q, because a smaller matching may exist when the annotated cardinality does not. This is not improved relational coverage. It widens the mean frontier from 1.176 m to 1.297 m and lowers certified-decision yield from 53.2% to 45.8%.

Every false certificate occurs when candidate support omits the annotated world; none occurs in a truth-representable cell. Unknown q therefore compounds candidate-support uncertainty but does not invalidate conditional coverage when the annotated world remains admissible.
