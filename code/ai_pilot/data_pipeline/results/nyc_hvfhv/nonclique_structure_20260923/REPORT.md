# NYC outcome-blind non-clique fixed-q audit

Status: **PASS_PUBLIC_NONCLIQUE_TEST_NULL**.

The four analyzed 4+12 views were selected solely because the earlier outcome-blind geometry census found a core-touching induced P3. The four completed clique views remain in the denominator but are geometry-ineligible for this conditional diagnostic.

All 4 eligible windows replayed their frozen projection and small-geometry hashes. Complete enumeration and independent MILP replay left 0 unresolved verification cells.

| Restriction | Declared comparisons | Certified | Endpoint changed | Support-ineligible | Missing-query ineligible |
|---|---:|---:|---:|---:|---:|
| Pair | 96 | 48 | 0 | 48 | 0 |
| Clique | 96 | 48 | 0 | 48 | 0 |

Among 24 window-capacity-q cells feasible in all three families, ordered events admit more reachable buffer subsets than cliques in 1 cells and more than pairs in 3 cells.

| Window | Edges | Possible | Core P3s | Verification |
|---|---:|---:|---:|---|
| jan_weekday_am_n8 | 118 | 120 | 26 | PASS |
| jan_weekend_am_n8 | 118 | 120 | 26 | PASS |
| apr_weekday_am_n8 | 115 | 120 | 58 | PASS |
| apr_weekday_pm_n8 | 113 | 120 | 76 | PASS |

The primary distinctive comparison is ordered versus clique. Pair differences additionally reflect the two-member restriction. Equality is retained as a result. Public rows do not reveal the true event partition, so these are conditional identified-set effects, not accuracy or prevalence estimates.

Scope: Conditional diagnostic on four outcome-blind non-clique small views from one frozen public calendar. It is not true event recovery, partner recall, population prevalence, city-scale closure or an independent holdout.
