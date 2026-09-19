# NYC dominant-cell pricing-cache reconstruction

| Cell | Baseline LP | Cached LP | Reduction | Baseline s | Cached s |
|---|---:|---:|---:|---:|---:|
| 10+30, C=4 | 349,152 | 238,154 | 31.8% | 1081.10 | 579.02 |
| 12+36, C=4 | 544,203 | 369,886 | 32.0% | 1653.71 | 866.29 |
| 16+48, C=3 | 242,650 | 188,849 | 22.2% | 1095.80 | 595.50 |
| 16+48, C=4 | 744,622 | 527,952 | 29.1% | 4232.09 | 2191.40 |

All four cache-off runs reproduce the historical integer certificate and branch-path diagnostics; all cache-on pairs preserve them. Actual fixed-span LP calls fall from **1,880,627** to **1,324,841** (**29.6%**).
The cached variant is faster in **4/4** runner-specific pairs; aggregate elapsed time falls by **47.5%**.

The source metadata and deterministic cohort counts match the frozen report, but old artifacts contain neither rows nor an input hash. This is therefore a snapshot-consistent reconstruction, not a byte-identical replay. Runtime is runner-specific.
