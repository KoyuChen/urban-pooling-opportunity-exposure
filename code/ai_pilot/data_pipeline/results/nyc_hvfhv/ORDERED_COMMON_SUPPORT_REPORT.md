# NYC HVFHV ordered-run common-support outcome bounds

Frozen evidence date: 2026-09-01 UTC  
Validated workflow: `33556633111`  
Artifact: `9819681582`  
Artifact digest: `sha256:33a96ea9e8eb6a21426b8a903b04c2f82b8ec7c68ae42efbb873bf9b2eb69a50`

Time model: `rounded_15m_outer`  
Ordered core: **8**; candidate rows: **437**.

Common selected-buffer cardinality: **72 rows** (**9.0000/core**), defined by the certified `C=2` maximum and then held fixed for `C=2,3,4`.

| C | Outcome | Lower | Upper | Width | Status |
|---:|---|---:|---:|---:|---|
| 2 | mean selected-buffer miles | 3.4402 | 9.6792 | 6.2391 | `CERTIFIED_OPTIMAL_PAIR` |
| 2 | mean selected-buffer trip minutes | 17.7794 | 37.1475 | 19.3681 | `CERTIFIED_OPTIMAL_PAIR` |
| 3 | mean selected-buffer miles | 3.1315 | 15.4480 | 12.3165 | `CERTIFIED_OPTIMAL_PAIR` |
| 3 | mean selected-buffer trip minutes | 15.9829 | 55.7116 | 39.7287 | `CERTIFIED_OPTIMAL_PAIR` |
| 4 | mean selected-buffer miles | 3.1163 | 16.1659 | 13.0496 | `CERTIFIED_OPTIMAL_PAIR` |
| 4 | mean selected-buffer trip minutes | 15.9236 | 58.9056 | 42.9819 | `CERTIFIED_OPTIMAL_PAIR` |

Capacity nestedness audit: `PASS` over **4** certified adjacent-capacity comparisons. Every reported endpoint has zero reported MIP gap.

With support cardinality fixed, capacity is a pure feasible-set relaxation. The miles width rises by **97.4%** from `C=2` to `C=3` and by only **6.0%** from `C=3` to `C=4`; **89.2%** of the total `C=2` to `C=4` widening occurs in the first capacity relaxation. Trip-duration width rises by **105.1%** from `C=2` to `C=3` and by only **8.2%** from `C=3` to `C=4`; **86.2%** of its total widening occurs in the first relaxation.

This is the clean capacity-comparison Gate missing from the capacity-specific maximum-support analysis: once the estimand is held fixed, larger declared capacity weakly enlarges the identified set exactly as feasible-set nesting predicts. The empirical geometry is strongly front-loaded at `C=2 -> 3` in this smoke cohort.

Claim boundary: these are conditional feasible-world bounds under the declared coarse public-time model. They do **not** recover actual co-riders, realized vehicle runs, true capacity, or production matching logic.
