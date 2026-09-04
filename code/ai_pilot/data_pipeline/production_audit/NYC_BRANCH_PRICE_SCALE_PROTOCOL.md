# NYC exact integer decomposition: predeclared scaling audit

## Question

How far can the exact branch-and-price implementation scale when the number of
focal core rows increases on a fixed public-data time regime?

## Frozen cells

The audit uses the January 3, 2023 weekday-evening scan interval
`17:00--21:00` and exact-second intervals. The same outcome-blind live cohort
selection contract used by the canonical integer audit is run at ordered core
sizes

```text
4, 8, 12, 16.
```

The live wrapper evaluates its declared capacity cells. Solver limits are fixed
before seeing results:

| Ordered core rows | Solver limit |
|---:|---:|
| 4 | 120 s |
| 8 | 300 s |
| 12 | 600 s |
| 16 | 900 s |

The driver interrogates the canonical live wrapper's argparse contract and
passes only options that wrapper declares. It does not reimplement extraction,
column generation, or branch-and-price.

## Reported quantities

For every core-size/capacity cell exposed by the source report, retain:

- root LP bound;
- integer incumbent and certified optimum when available;
- optimality gap when a time limit is reached;
- branch-node count;
- generated-column count;
- elapsed wall-clock time; and
- explicit source status.

The aggregator never infers optimality from a zero-looking gap or successful
process exit alone. A cell is called certified only when the canonical report
contains an explicit optimal/certified status and no unresolved marker.

## Interpretation boundary

This is an algorithmic scaling audit on four predeclared public-data cohorts,
not a city-wide relation reconstruction. A timeout is a measured computational
boundary, not an infeasibility certificate. No actual co-rider, vehicle run,
realized capacity, production matching rule, population frequency, or causal
effect is recovered.
