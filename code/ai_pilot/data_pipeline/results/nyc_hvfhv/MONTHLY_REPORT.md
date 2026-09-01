# Frozen NYC HVFHV monthly latent-linkage smoke evidence

Validated workflow run: `33528697571`  
Artifact: `nyc-hvfhv-smoke`, ID `9808787001`  
Artifact ZIP SHA-256: `ba6baba8d3aa9809a0a3fdde65536b973a904306555af86c02244ffc439aacdd`  
Source commit: `6f5c469dfde0fa4ecc6f5bb94b4f1a03836ca565`

# NYC HVFHV latent-linkage smoke test

Source cohort: **Uber** (`HV0003`), 2026-05-21 19:15:00–2026-05-21 19:30:00; **200** matched trips.

NYC publishes `shared_match_flag` but not public co-rider/run ID or pool size. Therefore this report does **not** impose K=2 matching and does **not** reconstruct partners.

| Padding (min) | Temporal edges | Candidate nodes | Mean core degree | Median | Max | Zero-degree share | Same PU+DO edges |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 154708 | 1042 | 773.54 | 786.0 | 1027 | 0.000 | 44 |
| 2 | 164978 | 1084 | 824.89 | 845.5 | 1078 | 0.000 | 45 |
| 5 | 179785 | 1130 | 898.92 | 923.5 | 1129 | 0.000 | 49 |
| 10 | 203983 | 1211 | 1019.91 | 1017.5 | 1210 | 0.000 | 55 |
| 15 | 226932 | 1298 | 1134.66 | 1130.0 | 1297 | 0.000 | 65 |
| 30 | 288734 | 1580 | 1443.67 | 1439.0 | 1579 | 0.000 | 78 |

The first Gate is whether candidate multiplicity is nontrivial yet computationally manageable. If so, NYC becomes the unknown-pool-size extension of the Chicago K=2 benchmark.
