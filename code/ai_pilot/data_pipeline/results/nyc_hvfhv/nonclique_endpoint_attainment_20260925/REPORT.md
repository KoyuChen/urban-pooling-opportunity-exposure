# Frozen NYC endpoint-attainment mechanism audit

Status: **PASS_ENDPOINT_ATTAINMENT_NULL_EXPLAINED**.

All 192 ordered endpoint/restriction checks are attained by the restricted family using the same selected-buffer subset; 0 checks remain unresolved.

The null is therefore not caused by silently equating feasible families. Ordered events add buffer subsets in 1 of 24 common-q cells versus cliques and 3 of 24 versus pairs. They also add event partitions on already reachable subsets. Yet every lower and upper value for the two frozen additive queries has at least one pair/clique attaining subset.

Across the 48 restriction world cells, 36 expand only the event-partition multiplicity, 4 expand projected buffer support, and 8 are identical at both levels. No ordered-only subset ties any of the 192 audited endpoints.

| Window | C | q | Restriction | Ordered subsets | Restricted subsets |
|---|---:|---:|---|---:|---:|
| apr_weekday_pm_n8 | 2 | 4 | pair | 495 | 486 |
| apr_weekday_pm_n8 | 2 | 4 | clique | 495 | 486 |
| apr_weekday_pm_n8 | 3 | 4 | pair | 495 | 486 |
| apr_weekday_pm_n8 | 4 | 4 | pair | 495 | 486 |

This separates three objects: event partitions, their projected selected-buffer subsets, and additive-query endpoints. The first can expand without the second; the second can expand without moving the third.

Scope: Mechanism audit of the four frozen public 4+12 views, existing q values, and two existing queries. It does not select a new query, reveal rows or memberships, recover true events, resolve geometry transport failures, or establish city-scale closure.
