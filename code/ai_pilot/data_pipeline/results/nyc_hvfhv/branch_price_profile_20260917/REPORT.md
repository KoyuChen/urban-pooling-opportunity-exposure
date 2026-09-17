# NYC branch-and-price frozen-lattice performance profile

Profile version: `nyc-branch-price-scale-profile/v1`.

## Result

All 18 input cells retain `INTEGER_OPTIMUM_CERTIFIED`. Together they used **2.64 solver-hours**, **2,389,799 fixed-span oracle LP solves**, and only **59 processed branch nodes** (maximum **11** in one cell).

The four slowest cells account for **88.0%** of observed runtime. On log1p scales, runtime correlates **0.986** with oracle-LP volume, versus **0.544** with processed nodes. The primary observed scaling signal is therefore repeated fixed-span pricing work, not a large branch tree.

## Slowest cells

| Core | Buffer | C | Seconds | Runtime share | Nodes | Oracle LP solves |
|---:|---:|---:|---:|---:|---:|---:|
| 16 | 48 | 4 | 4193.20 | 44.1% | 7 | 744,622 |
| 12 | 36 | 4 | 2075.49 | 21.8% | 11 | 544,203 |
| 16 | 48 | 3 | 1068.73 | 11.2% | 3 | 242,650 |
| 10 | 30 | 4 | 1031.00 | 10.8% | 8 | 349,152 |

## Capacity totals

| C | Cells | Seconds | Runtime share | Oracle LP solves | Nodes |
|---:|---:|---:|---:|---:|---:|
| 2 | 6 | 630.72 | 6.6% | 231,962 | 6 |
| 3 | 6 | 1479.35 | 15.6% | 453,435 | 20 |
| 4 | 6 | 7401.12 | 77.8% | 1,704,402 | 33 |

## Interpretation boundary

Descriptive attribution on one deterministic 18-cell lattice; not a causal ablation, population runtime guarantee, or complexity theorem.
The next optimization target is to reduce repeated rooted fixed-span LP work (through exact reuse, screening, or batching) while preserving exact branch-compatible pricing. Enlarging the search lattice before such an ablation would not isolate the bottleneck.
