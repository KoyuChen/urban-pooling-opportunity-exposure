# Real mobility data smoke test

Run date: 2026-09-01 UTC  
Workflow run: `33464670227`  
Artifact: `real-city-smoke`, ID `9784462075`  
Artifact ZIP SHA-256: `1b98232f51e5a3f0cfb8ff9e399f0ddd0cd33568897e9a56227101eac0523187`  
Result SHA-256: `b664abc1b39678d15c107eb5644627ac98dfb74c8c6192da926505300493739d`

This is a bounded schema/API/conditional-endpoint test, not partner
reconstruction, candidate-recall certification, or a conformal coverage
evaluation against hidden truth.

| City | Status | Cohort rows | Fetched | Usable | Max 15-min bin | Pair size known | Exact temporal worlds |
|---|---|---:|---:|---:|---:|---|---:|
| Chicago | PASS | 853 | 853 | 619 | 52 | yes | 10,395 |
| New York City | PASS | 823 | 823 | 823 | 70 | no | 10,395 |

## Chicago

Source: City of Chicago dataset `6dvr-xwnh`, Transportation Network Providers
-- Trips (2025-). The bounded cohort uses 2026-01-13 17:00--21:00 and retains
rows with `shared_trip_match = true` and `trips_pooled = 2`.

The live schema contained all 11 required fields and no public field whose name
looked like a partner or pooled-run identifier. Of 853 returned rows, 619
(72.57%) had usable released time, community-area, distance, duration, and fare
values. Pickup and dropoff community area were missing in 13.25% and 13.60% of
rows, respectively; fare was missing in 0.94%.

For one de-identified 12-node released time bin, temporal compatibility alone
left the complete graph: 66 candidate edges and 10,395 perfect matching worlds.
The exact conditional semantic-query endpoints were:

| Query | Conditional minimum | Conditional maximum |
|---|---:|---:|
| Mean absolute trip-mile gap | 0.469533 | 2.07063 |
| Mean absolute duration gap, minutes | 1.83333 | 7.48333 |
| Mean absolute fare gap | 0.833333 | 5.00000 |
| Same-dropoff-area fraction | 0.000000 | 0.500000 |

An explicitly heuristic route screen reduced that selected graph to 34 edges
and 135 perfect matching worlds. Those narrower endpoints are sensitivity
results only: the public release does not identify candidate-edge recall.

## New York City

Source: NYC Open Data dataset `u253-aew4`, 2023 High Volume FHV Trip Data. The
bounded cohort uses 2023-06-07 17:00--21:00 and retains rows with
`shared_match_flag = 'Y'`.

The live schema contained all 11 required fields and no public field whose name
looked like a partner or pooled-run identifier. All 823 returned rows had the
fields required by this smoke test. The selected 12-node time bin again had 66
temporal candidate edges and 10,395 perfect matching worlds. Its exact
conditional endpoints were:

| Query | Conditional minimum | Conditional maximum |
|---|---:|---:|
| Mean absolute trip-mile gap | 0.981667 | 2.81833 |
| Mean absolute duration gap, minutes | 1.54722 | 17.1861 |
| Mean absolute fare gap | 3.57500 | 14.6850 |
| Same-dropoff-zone fraction | 0.000000 | 0.000000 |

The naive route screen left 30 edges but no perfect matching. This is a useful
negative smoke result: an intuitive compatibility filter can destroy the
feasible set and cannot be promoted to a support restriction without an
independent recall argument.

## Gate decision

The smoke test passes for both official releases. Chicago is the stronger
method-fit candidate because `trips_pooled = 2` exposes the size of the hidden
pooled run. NYC is useful as an independent real-covariate and semantic-query
diagnostic, but `shared_match_flag` alone does not justify modeling the public
rows as disjoint pairs.

The next empirical gate is therefore not API availability. It is construction
of a run-closed Chicago cohort and a defensible candidate-support contract.
Until that is available, these endpoints remain conditional sensitivity
objects rather than population or coverage claims.
