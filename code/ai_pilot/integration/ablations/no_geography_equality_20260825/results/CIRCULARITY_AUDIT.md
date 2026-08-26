# Circularity audit for same-income-bin bounds

This audit joins the held-out locked candidate graph to the hidden synthetic
income-bin file **after** model fitting. Hidden income bins remain absent from
candidate construction and weak-MIL training.

For the 560 held-out candidate edges whose two endpoints are reported matched
(the graph passed to the set-packing bound solver), the equality indicators
have the following relationship with the bound outcome.

| Feature | Feature = 1 | Same-income edges among feature = 1 | Exact agreement with `same_income_bin` |
|---|---:|---:|---:|
| `pickup_community_area_same` | 560 / 560 | 136 / 560 | 136 / 560 (24.29%) |
| `dropoff_community_area_same` | 560 / 560 | 136 / 560 | 136 / 560 (24.29%) |
| `pickup_tract_same` | 136 / 560 | 136 / 136 | 560 / 560 (100%) |
| `dropoff_tract_same` | 136 / 560 | 136 / 136 | 560 / 560 (100%) |

Thus the community-area indicators are constants in this synthetic bound
graph and add no pair-level discrimination. More importantly, both tract
equality indicators are exact copies of the same-income-bin edge outcome. This
follows from the generator: pickup tract is constructed from corridor and
income bin, while destination bin is a deterministic transformation of those
same quantities. A score-retention set learned with these tract indicators can
therefore narrow a same-income-bin bound mechanically.

Removing the exact equality indicators is necessary but not sufficient for a
clean robustness check. The generator's income-specific coordinate offsets
still allow continuous pickup/dropoff distances to proxy income equality. The
ablation results should therefore be interpreted as a less circular
model-dependent sensitivity analysis, not as a fully SES-blind reconstruction.
The untrimmed candidate-graph interval remains the score-free reference.
