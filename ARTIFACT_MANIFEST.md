# Artifact manifest

This manifest separates completed evidence from planned evidence so that a
working draft cannot be mistaken for a completed Chicago study.

## Completed and committed

| Artifact | Status | Scientific role |
|---|---|---|
| ACM review-format paper | Complete draft | Eight main pages; references and appendix follow |
| Chicago 53,241-row prefix audit | Complete, mechanics only | Schema, missingness, ACS join, and candidate-support audit |
| Candidate builder | Complete | Declared temporal, spatial, directional, and degree constraints |
| Weak-MIL edge scorer | Complete | Learns from node match labels; never receives pair labels |
| Exact-cover bound solver | Complete | Computes minimum and maximum exposure statistics |
| Twenty-replicate solver validation | Complete | Known-truth coverage under time coarsening |
| Locked end-to-end synthetic benchmark | Complete | Node calibration, hidden-edge ranking, and bound coverage |
| Geography-equality ablation | Complete | Detects target leakage and defines the 22-feature primary score |

The final PDF is `paper/Thicker_But_Narrower_Draft.pdf`. The primary ablation
report is
`code/ai_pilot/integration/ablations/no_geography_equality_20260825/results/ABLATION_REPORT.md`;
the accompanying leakage analysis is `CIRCULARITY_AUDIT.md` in the same folder.

## Not completed

| Required item | Current label |
|---|---|
| Complete-day Chicago authorized-trip extraction | `TBD` |
| Candidate-support rate on complete days | `TBD` |
| Complete-day held-out calibration | `TBD` |
| Complete-day structural exposure bounds | `TBD` |
| Chicago policy estimates and robustness suite | `TBD` |
| Institutional human-subjects/ethics determination | Required before submission |

No row-level prefix mechanics predictions are distributed in this repository.
The synthetic records and their hidden truth files are distributed because
they contain no human observations.

## Primary versus diagnostic model

The primary weak-MIL model uses 22 edge features and excludes all community-
area and census-tract equality indicators and their interactions. The
28-feature model remains committed solely to reproduce the circularity audit.
Its tighter interval is not used as scientific evidence.

The six-feature removal does not eliminate all proxy risk: deterministic
coordinate offsets in the locked generator can still encode the synthetic SES
bin. Consequently, score-restricted bounds are sensitivity regions. The
untrimmed graph interval remains the score-free primary bound.
