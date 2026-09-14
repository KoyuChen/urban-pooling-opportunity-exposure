# Joint controlled-truth candidate and decision coverage

Status: **PASS_CONTROLLED** over **3,000** frozen synthetic instances.

Candidate recall counts retained true members. Full-world coverage requires every true member and its feasible relational world to remain representable. True-aggregate coverage only asks whether the scalar truth lies inside the truncated frontier. Threshold certification is evaluated at the three frozen thresholds; a missing frontier is unresolved, not certified.

| C | Kept | Candidate recall | Full-world coverage | True aggregate coverage | Median width | Threshold certified | False / certified |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 4/8 | 55.0% | 2.6% | 2.6% | 0.000 | 46.0% | 19.3% |
| 2 | 6/8 | 83.4% | 31.4% | 69.2% | 0.196 | 64.0% | 7.2% |
| 2 | 8/8 | 100.0% | 100.0% | 100.0% | 0.446 | 35.6% | 0.0% |
| 3 | 4/8 | 55.4% | 2.7% | 2.7% | 0.000 | 48.6% | 21.3% |
| 3 | 6/8 | 83.8% | 31.9% | 71.1% | 0.196 | 63.4% | 6.9% |
| 3 | 8/8 | 100.0% | 100.0% | 100.0% | 0.459 | 33.8% | 0.0% |
| 4 | 4/8 | 56.0% | 3.0% | 3.0% | 0.000 | 52.5% | 21.3% |
| 4 | 6/8 | 83.8% | 32.6% | 71.7% | 0.270 | 63.4% | 7.7% |
| 4 | 8/8 | 100.0% | 100.0% | 100.0% | 0.473 | 32.1% | 0.0% |

At six of eight retained buffers, mean candidate recall is 83.4--83.8%, but full-world coverage is only 31.4--32.6%. Scalar coverage is higher (69.2--71.7%), showing that an aggregate can remain covered after the relational truth has been removed. The false-certificate column reports the additional danger: narrowing a misspecified frontier can increase apparent decisiveness without restoring truth.

This is controlled method validation under the declared generator, not evidence about operational partner recovery or population-level coverage.
