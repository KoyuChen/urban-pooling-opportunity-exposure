# Artifact manifest — Learning-Augmented Aggregate Bounds over Hidden Matchings

This manifest separates current KDD Research evidence, legacy pilot provenance,
and open submission gates. No synthetic or prefix-sample result is presented as
a Chicago estimate.

## Current KDD Research artifacts

| Artifact | Status | Licensed scientific role |
|---|---|---|
| Anonymous ACM manuscript | Working draft | Theory, reference implementation, calibrated-set result, and explicit evidence gates |
| Joint matching--label solver | Implemented | Exact small-world and numerical endpoints for one label/cell, core/buffer/context roles, count bounds, compatibility, Gamma, and score floors |
| Joint solver unit suite | 46/46 passing overall | Declared-input behavior; not an external observation-operator validation |
| Seeded solver agreement audit | 250/250 statuses agree | Exact fallback versus numerical HiGHS; endpoints agree on all 185 feasible instances |
| Matching-level conformal module | Implemented | Positive-affine-invariant regret and finite-sample market-level radius |
| Deterministic conformal benchmark | Implemented | Directly edge-supervised calibration stress test on six-pair synthetic markets |
| Exact conformal frontier | 10,395 matchings/market | Reproduces all radii and headline metrics without MILP; 44 radius/scorer rows |
| Query-leaking diagnostic | Stress test only | Uses the exact same-SES edge contribution; demonstrates circular false precision under shift |
| Exact/adversarial checks | Implemented | Node nonidentification, incoherent marginal products, score-origin instability, discrete ranges, and count coupling |
| Vector trade-off figure | Generated from exact frontier CSV | Editable SVG and Type-42 PDF; no manually entered results |

The current compiled paper is `paper/KDD_Research_Working_Draft.pdf`. The
joint reference solver is `code/ai_pilot/bounds/joint_label_matching.py`; its
tests are in `code/ai_pilot/bounds/tests/test_joint_label_matching.py`. The
calibration benchmark and generated outputs are under
`code/ai_pilot/benchmarks/`.

## Theory versus implementation boundary

The paired pickup/drop-off suppression NP-completeness theorem is proved for
an explicit abstract operator. The reference solver currently models one
categorical label and one release-cell membership per row; it does not yet
compile that two-endpoint operator. The bounded-treewidth result is a generic
tractability parameterization, not an implemented production decomposition.

## Legacy pilot provenance

The earlier weak-node-score pipeline, two-day synthetic validation,
geography-equality ablation, and `paper/Thicker_But_Narrower_Draft.pdf` remain
in the repository to document the failed AI4Sciences route. They are not the
headline KDD evidence. In particular, that Weak-MIL scorer receives node match
labels, whereas the current conformal benchmark directly supervises source
edge scores with synthetic pair truth. These are different experiments and
must not be conflated.

## Open gates

| Required item | Current status |
|---|---|
| Version-specific 2025/2026 Chicago observation operator | Unverified |
| Two-endpoint operator compiler and production certified decomposition | Not implemented |
| Necessary-condition candidate supergraph and omission audit | Not completed |
| Independent non-Chicago relation-truth benchmark | Not completed |
| Multi-seed/size/sparsity/coarsening benchmark sweeps | Not completed |
| Complete-day, boundary-safe Chicago extraction and privacy cells | Not completed |
| Institutional and data-terms determination | Required before nonpublic-data use |

No row-level imputed partner link, trip identifier, or extremal fine-geography
assignment is distributed. Synthetic hidden truth is distributed because it
contains no human observations.
