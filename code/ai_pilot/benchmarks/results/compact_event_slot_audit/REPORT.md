# Compact event-slot lower-bound audit

Executed in GitHub Actions run `33951594827`. The frozen
protocol contains 24 endpoint problems,
2 timing repeats and 96 total solver
invocations on synthetic sequential nonclique instances.

| Variant | Exact status | Equal bounds | Incumbent | Median seconds | Pricing LP calls |
|---|---:|---:|---:|---:|---:|
| Compact probe | 38/48 | 40/48 | 48/48 | 0.417 | 11,594 |
| Probe disabled | 16/48 | 16/48 | 48/48 | 3.001 | 30,639 |

Paired exact gains/losses are **22 / 0**;
incumbent gains/losses are **0 / 0**;
strict lower-bound gains/losses are **10 / 0**.
The predeclared rule makes the production probe **enabled by default**
with `compact_probe_seconds=0.75`.

Every incumbent is replayed. A lower bound is strengthened only by a strictly
positive rationally repaired phase-I certificate. Timeout, MIP failure and
solver status alone remain inconclusive. All records and unresolved cases are
retained without relation witnesses.

This audit does not establish real membership truth, universal acceleration,
city-scale performance, noisy-answer robustness, privacy utility or operational
availability of disclosure facts. The paper and frozen Chicago/NYC results are
unchanged.
