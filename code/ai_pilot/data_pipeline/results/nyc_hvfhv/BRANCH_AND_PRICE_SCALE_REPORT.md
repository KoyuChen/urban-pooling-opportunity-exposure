# NYC exact integer branch-and-price scale audit

Generated UTC: `2026-09-03T14:11:55+00:00`  
Provider: `HV0005`.

| Core | Buffers | C | Status | Root LP UB | Integer LB | Global UB | Gap | Nodes | Columns across nodes | Pricing cases | Seconds |
|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 12 | 2 | `INTEGER_OPTIMUM_CERTIFIED` | 4.000 | 4.000 | 4.000 | — | 1 | 54 | 8 | 0.48 |
| 4 | 12 | 3 | `INTEGER_OPTIMUM_CERTIFIED` | 8.000 | 8.000 | 8.000 | — | 4 | 303 | 127 | 6.98 |
| 4 | 12 | 4 | `INTEGER_OPTIMUM_CERTIFIED` | 12.000 | 12.000 | 12.000 | — | 2 | 208 | 96 | 6.22 |
| 6 | 18 | 2 | `INTEGER_OPTIMUM_CERTIFIED` | 8.000 | 8.000 | 8.000 | — | 1 | 115 | 30 | 4.04 |
| 6 | 18 | 3 | `INTEGER_OPTIMUM_CERTIFIED` | 14.000 | 14.000 | 14.000 | — | 8 | 1215 | 478 | 56.32 |
| 6 | 18 | 4 | `INTEGER_OPTIMUM_CERTIFIED` | 18.000 | 18.000 | 18.000 | — | 1 | 205 | 108 | 15.26 |
| 8 | 24 | 2 | `INTEGER_OPTIMUM_CERTIFIED` | 12.000 | 12.000 | 12.000 | — | 1 | 206 | 48 | 12.21 |
| 8 | 24 | 3 | `INTEGER_OPTIMUM_CERTIFIED` | 20.000 | 20.000 | 20.000 | — | 3 | 836 | 224 | 62.05 |
| 8 | 24 | 4 | `INTEGER_OPTIMUM_CERTIFIED` | 24.000 | 24.000 | 24.000 | — | 4 | 1123 | 336 | 79.94 |
| 10 | 30 | 2 | `INTEGER_OPTIMUM_CERTIFIED` | 16.000 | 16.000 | 16.000 | — | 1 | 332 | 110 | 52.47 |
| 10 | 30 | 3 | `INTEGER_OPTIMUM_CERTIFIED` | 26.000 | 26.000 | 26.000 | — | 1 | 427 | 160 | 86.36 |
| 10 | 30 | 4 | `INTEGER_BRANCH_AND_PRICE_UNRESOLVED` | 30.000 | 27.000 | 30.000 | 3.000 | 4 | 1623 | 359 | 180.50 |
| 12 | 36 | 2 | `INTEGER_OPTIMUM_CERTIFIED` | 20.000 | 20.000 | 20.000 | — | 1 | 493 | 156 | 145.94 |
| 12 | 36 | 3 | `INTEGER_OPTIMUM_CERTIFIED` | 32.000 | 32.000 | 32.000 | — | 1 | 580 | 192 | 198.91 |
| 12 | 36 | 4 | `INTEGER_BRANCH_AND_PRICE_UNRESOLVED` | 36.000 | 32.000 | 36.000 | 4.000 | 1 | 570 | 180 | 188.41 |
| 16 | 48 | 2 | `INTEGER_OPTIMUM_CERTIFIED` | 28.000 | 28.000 | 28.000 | — | 1 | 832 | 192 | 415.59 |
| 16 | 48 | 3 | `INTEGER_BRANCH_AND_PRICE_UNRESOLVED` | 44.000 | 43.000 | 44.000 | 1.000 | 1 | 960 | 272 | 640.17 |
| 16 | 48 | 4 | `INTEGER_BRANCH_AND_PRICE_UNRESOLVED` | 48.000 | 45.000 | 48.000 | 3.000 | 1 | 1008 | 320 | 758.75 |

Certified integer optima: **14 / 18**; unresolved with bounds: **4**; skipped for insufficient public rows: **0**.

A timeout is reported as an open certified gap, not converted to an optimum. The scale audit measures the exact decomposition algorithm on one deterministic public cohort and does not recover operational event memberships.
