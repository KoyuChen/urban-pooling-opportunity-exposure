# KDD 2027 Research Track checklist

The live KDD website and submission form remain authoritative. This checklist
records the current Research-track pivot and must be revalidated before
submission.

## Format

- [x] Full paper in English.
- [x] ACM `acmart` review layout.
- [x] Double-blind source uses
  `\documentclass[sigconf,anonymous,review]{acmart}`.
- [x] Author names, affiliations, acknowledgments, repository URLs, and other
  direct identifiers removed from the review PDF.
- [x] Main content occupies pages 1--7; references begin on page 8 and the
  appendix on page 9.
- [x] No overfull boxes, missing citations, undefined references, Type-3
  fonts, clipped objects, or unreadable figures in the final visual audit.
- [ ] Live template, dates, artifact policy, disclosure requirements, and
  supplementary-material rules rechecked immediately before submission.

## Research-track fit

- [x] General object is aggregate inference over hidden relations and
  privacy-coarsened attributes, not one Chicago analysis.
- [x] Chicago is framed as a flagship application.
- [x] Point linkage, node classification, ordinary exact cover, and generic
  MILP are explicitly treated as baselines rather than novelty.
- [x] Learning is an optional, coverage-audited restriction rather than a
  claim that the hidden graph has been recovered.
- [x] Paired-suppression feasibility boundary has a complete adversarially
  audited NP-completeness proof, with operator and compatibility limits stated.
- [ ] Scalable certified algorithm goes beyond the reference MILP and is
  evaluated on production-scale graphs.
- [ ] At least one non-Chicago benchmark with independently observed relation
  truth is included.

## Method correctness gates

- [ ] Current 2025/2026 privacy operator is verified from version-specific
  official documentation.
- [ ] Core/buffer/context-only population is boundary complete.
- [x] Joint matching--label reference solver enforces supplied global count
  bounds and attribute-conditioned compatibility. (The current Chicago
  operator is still unverified and is not compiled.)
- [x] Independent-support degeneration agrees with weighted matching on exact
  declared-input tests.
- [x] Exact small-instance oracle agrees with the numerical reference solver
  on the deterministic 250-instance audit.
- [x] Every result distinguishes attained endpoints, their convex-hull range,
  and any sampling uncertainty.
- [ ] Candidate graph is a necessary-condition supergraph or its omissions are
  separately quantified; support is never inferred from node degree alone.
- [x] Controlled score calibration uses complete markets with observed true
  relations, separated from scorer training. (No Chicago transfer is claimed.)
- [x] Candidate-support and score-calibration errors are reported separately.

## Experiment gates

- [x] Controlled source/calibration/test split is deterministic and
  reproducible; its directly edge-supervised and query-leaking design is
  disclosed.
- [x] Proxy-shift diagnostic shows the coverage cost of arbitrary sharpening.
- [ ] Controlled benchmark varies rounding, suppression, boundary edges,
  candidate omissions, proxy leakage, and graph scale.
- [ ] Ground-truth relational benchmark reports true-world retention, query
  coverage, width, runtime, gaps, and certificate status.
- [ ] Baselines include maximum-score point matching, complete cases,
  independent supports, single imputation, linkage-range queries, DBSCAN proxy
  grouping, and score-free coupled endpoints.
- [ ] Full-day Chicago extraction and all-trip privacy cells pass the locked
  audit protocol.
- [ ] Chicago results are limited to customer-transaction neighborhood
  context; no rider-level or social-network interpretation remains.

## Submission decision

- [ ] **GO only if:** operator verification, method theorem, scalable certified
  algorithm, independent matching-level calibration, multi-benchmark evidence,
  and complete Chicago application all pass.
- [ ] If the method gates fail but the Chicago evidence is complete and
  material, remove KDD branding and use the transportation fallback.
- [ ] If prefix/incomplete data, unverified suppression rules, or node fit are
  still carrying the central claim, do not submit.
