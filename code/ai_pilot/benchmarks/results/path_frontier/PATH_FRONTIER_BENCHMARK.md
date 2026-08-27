# Exact temporal-path frontier benchmark

**Gate:** PASS

The exact temporal-path DP agrees with every locked exact or analytic reference and every resolved HiGHS numerical comparator; its practical cost is governed by live-record width, active release factors, Gamma, and the exact score frontier. This is not a general MILP replacement.

| Check | Result |
|---|---:|
| Independent exhaustive agreement | 32/32 |
| Closed-form/analytic agreement | 24/24 |
| Resolved HiGHS numerical agreement | 16/16 |
| Certified outward-relaxation agreement | 1/1 |
| Locked cases | 34 |

## Parameter isolation

- **Exact score frontier:** the largest binary-weight disjoint-C4 case uses schedule width 2, integer floor target 2048, and peak live frontier 4098. Unit- and binary-encoded families separate ordinary size growth from the weakly NP-hard score coordinate.
- **Release-factor locality:** the same largest local-factor world has active-factor width 1 under grouped order and 3 under interleaving; its exact endpoints are unchanged.
- **Temporal width is not degree:** the same degree-one graph has supplied-schedule width 1 under adjacent order and 16 under nested long edges; its graph pathwidth remains one.
- **Gamma:** the locked sweep expands the upper endpoint from 0 at Gamma=0 to 8 at Gamma=8, matching the analytic interval.
- **Certified score relaxation:** at eta=1/5, the exact interval [0,0] is contained in [-5,0]. The observed score shortfall 2/5 is below the eta*N certificate 4/5; lower/upper endpoint exactness is witnessed as false/true.

## Interpretation boundary

The exhaustive oracle is independent of the DP implementation. HiGHS is a floating-point numerical comparator, not an exact certificate. Peak memory is Python heap measured by `tracemalloc`; native HiGHS memory is not compared. All candidate sets, labels, factors, and schedules are declared synthetic inputs, so the benchmark says nothing about true-edge coverage or Chicago observation-operator validity.

Certified outward score relaxation is checked for exact-set containment, eta*N score slack, and sufficient endpoint-exactness witnesses; it is a bicriteria certificate, not a query FPTAS.

Timing protocol: One tracemalloc-instrumented run per DP case; timings are machine-specific and are not used for a speedup claim.
