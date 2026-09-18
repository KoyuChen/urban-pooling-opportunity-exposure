# Ordered-event branch-and-price pricing-cache audit

Every pair uses identical rows, limits, branching rules, and objectives; only the objective-independent exact geometry cache is switched.

| Case | Rows | C | Optimum | Nodes | Baseline LP | Cached LP | Reduction | Baseline s | Cached s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `fractional_master` | 4+5 | 2 | 3 | 17 | 1,030 | 573 | 44.4% | 1.576 | 1.007 |
| `regular_n3_c2` | 3+9 | 2 | 9 | 3 | 960 | 866 | 9.8% | 1.493 | 1.345 |
| `regular_n3_c3` | 3+9 | 3 | 9 | 1 | 396 | 396 | 0.0% | 0.642 | 0.636 |
| `regular_n4_c2` | 4+12 | 2 | 12 | 7 | 6,520 | 4,941 | 24.2% | 10.534 | 7.879 |
| `regular_n4_c3` | 4+12 | 3 | 12 | 1 | 994 | 994 | 0.0% | 1.718 | 1.668 |

All **10** paired runs return identical integer certificates and branch paths. Across one copy of each cell, actual fixed-span LP calls fall from **9,900** to **7,770** (**21.5%**). The cached variant is faster in **10/10** wall-clock pairs.

The LP-call reduction is deterministic. Wall-clock measurements are descriptive and depend on the runner. No numerical LP status is cached; only exact integer-box infeasibility is memoized.

Claim boundary: constructed fixed-time paired audit; not the frozen NYC public cohort, a city-scale runtime claim, or a complexity result.
