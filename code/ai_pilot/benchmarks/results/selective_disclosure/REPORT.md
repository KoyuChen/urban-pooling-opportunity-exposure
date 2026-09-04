# Decision-focused selective disclosure

The benchmark asks for the smallest truthful relation certificate that rules out every feasible world with the opposite downstream decision. It does not try to reconstruct the entire latent event partition.

## Selected-member mean decisions

Across **9000** capacity-threshold comparisons, **5954** (66.2%) are initially ambiguous. Conditional on ambiguity, the minimum row-usage certificate has mean **1.56**, median **1**, 90th percentile **3**, and maximum **4** facts.

One fact suffices in 55.8%; two facts suffice in 89.3%; three facts suffice in 99.2%.

| C | Threshold | Ambiguity | Mean cert. | Median | P90 | Max | <=1 | <=2 | <=3 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0.25 | 56.5% | 1.23 | 1 | 2 | 2 | 77.2% | 100.0% | 100.0% |
| 2 | 0.50 | 90.6% | 1.89 | 2 | 3 | 4 | 34.8% | 77.9% | 98.8% |
| 2 | 0.75 | 46.0% | 1.17 | 1 | 2 | 2 | 83.0% | 100.0% | 100.0% |
| 3 | 0.25 | 58.4% | 1.28 | 1 | 2 | 2 | 71.9% | 100.0% | 100.0% |
| 3 | 0.50 | 90.5% | 1.91 | 2 | 3 | 4 | 34.1% | 77.2% | 97.7% |
| 3 | 0.75 | 49.7% | 1.26 | 1 | 2 | 2 | 73.8% | 100.0% | 100.0% |
| 4 | 0.25 | 61.1% | 1.31 | 1 | 2 | 2 | 68.6% | 100.0% | 100.0% |
| 4 | 0.50 | 92.0% | 1.95 | 2 | 3 | 4 | 32.0% | 74.6% | 98.6% |
| 4 | 0.75 | 50.6% | 1.25 | 1 | 2 | 2 | 74.7% | 100.0% | 100.0% |

## Adaptive audit interface

On the adaptive subset, the optimal minimax policy uses a median of **3** realized queries; its median worst-case depth is **4** and maximum is **5**.

## Partition-dependent event count

Even after revealing the complete selected-row set, event count remains ambiguous in 90.7% of **300** instances. Row-usage facts cannot resolve these cells. Same-event pair facts do: the minimum pair certificate has median **2** and maximum **3**.

| C | Instances | Event-count ambiguity | Mean width | Mean pair cert. | Median | Max |
|---:|---:|---:|---:|---:|---:|---:|
| 2 | 100 | 72.0% | 0.72 | 1.15 | 1 | 2 |
| 3 | 100 | 100.0% | 1.14 | 2.15 | 2 | 3 |
| 4 | 100 | 100.0% | 1.77 | 2.50 | 2.5 | 3 |

The certificate problem is an exact hitting set over opposite-world disagreement sets. An implicit large-instance implementation can alternate between a hitting-set master and an EventFrontier separation solve that searches for an opposite-decision world consistent with the queried facts.

These are controlled-truth audit costs, not claims that city releases or platforms currently expose the queried facts.
