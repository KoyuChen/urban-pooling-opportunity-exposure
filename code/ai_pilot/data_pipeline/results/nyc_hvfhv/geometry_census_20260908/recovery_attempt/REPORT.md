# NYC geometry transport recovery audit

Recovery run `34240720735` reused all terminal records from source run
`34237155750` and retried only the 13 recorded transport failures under the
declared 120-second-request / 30-minute-window amendment.

The verified aggregate remains **HOLD**: 8 geometry-complete, 3 scientifically
ineligible, 11 transport failures and 2 transport deadlines among all 24
declared cells. All eight eligible full views contain a core-touching non-clique
event column; four of eight time-only 4+12 views are complete cliques.

Window 20 logged a completed geometry calculation, but artifact finalization
failed with HTTP 403. Because the report and replay fields are unavailable, it
is not counted as a scientific completion. The ledger retains its earlier
transport-failure record. No timeout is treated as infeasibility.

These results describe temporal candidate geometry only. They do not establish
full-world feasibility, fixed-q endpoint differences, actual ride membership,
realized capacity or population prevalence.
