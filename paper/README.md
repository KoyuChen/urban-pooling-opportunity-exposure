# EventFrontier manuscript

Working research draft, rewritten September 9, 2026:
**EventFrontier: Aggregate Identification from Logs with Hidden Event Membership and Coarsened Time**.

Build from this directory with `latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex`
in a full TeX Live installation containing `acmart`, Libertine, NewTX,
Inconsolata, TikZ and xurl. On Overleaf, upload this directory and select
`main.tex` as the root document. No external figure files are needed.

The target is the KDD 2027 Research Track working format: anonymous,
double-column ACM, at most eight main-content pages, followed by references
and appendix. Format source checked September 9, 2026:
https://kdd2027.kdd.org/research-track-call-for-papers/
This is a working draft, not a claim of submission or scientific readiness.

## What changed

- Adds fixed-q pair/clique/event containment, exact collapse conditions, and
  two strictly different selected-buffer-mean examples with nonempty models.
- Promotes the coverage-plus-bridges connectivity equivalence into the main text.
- States the row-additive-plus-event-count aggregate class preserved by pricing;
  general within-event dispersion is explicitly outside that local oracle.
- Proves the declared epsilon-MILP equivalence and the positive-epsilon union
  bridge to strict overlap. A sufficiently small instance-dependent margin
  preserves all partition-only endpoints; the chosen audit margin is not
  automatically certified small enough.
- Records the remaining complexity gap: support decision is in NP and the
  one-core case is polynomial, but no C=2 NP-hardness result is established.
  See `docs/THEORY_REINFORCEMENT.md` for the proof and verification map.
- Centers joint temporal-event feasibility, sequential membership, and the
  fixed-time integral event-pricing primitive.
- Credits prior aggregate bounds, candidate-omission sensitivity, interval
  total unimodularity, and branch-and-price explicitly.
- Distinguishes selected-buffer count q from matching cardinality m, including
  the alternating-component normalization.
- Limits efficient pricing to fixed exact intervals and additive weights;
  separates the rectangular timestamp-support MILP and its positive margin.
- Retains the 0/24 public fixed-q structural null and both incomplete campaigns.
- Updates Chicago from an extraction-only illustration to separate pilot and
  interim follow-up aggregates. No new scientific experiment was run for this rewrite.

## Headline evidence mapping

Paths below are relative to the repository root.

| Manuscript evidence | Source |
|---|---|
| Controlled truth, 3,000 instances | `code/ai_pilot/benchmarks/` and `ARTIFACT_MANIFEST.md` |
| ATR 170 snapshots, 850 cells | `code/ai_pilot/benchmarks/results/atr_diamor_truth/` |
| ATR support transfer and degree cap | `code/ai_pilot/benchmarks/results/atr_diamor_support_calibration/` and `atr_diamor_density_cap/` |
| Chicago pilot 23 complete, 1 ineligible | `code/ai_pilot/data_pipeline/results/chicago_k2_fixed_panel/latest_panel_report.json` |
| Chicago interim 10 complete, 2 ineligible, 84 unstarted | `code/ai_pilot/data_pipeline/results/chicago_k2_followup/batch0_20260909/MANIFEST.json` |
| NYC 101 numerically closed endpoint pairs, 125 witnessed ambiguous cells, 126 total | `code/ai_pilot/data_pipeline/results/nyc_hvfhv/ORDERED_DECISION_PANEL_SUMMARY.json` |
| NYC structural comparison 0/24 changes | `code/ai_pilot/data_pipeline/results/nyc_hvfhv/structure_audit_20260908/REPORT.md` |
| NYC geometry 8 complete, 3 excluded, 13 transport unresolved | `code/ai_pilot/data_pipeline/results/nyc_hvfhv/geometry_census_20260908/recovery_attempt/REPORT.md` |
| NYC 18/18 support-maximization closures | `code/ai_pilot/data_pipeline/results/nyc_hvfhv/BRANCH_AND_PRICE_SCALE_REPORT.md` |

Numerical optimality, exact enumeration, witness-certified ambiguity, and
unresolved endpoints are different certificate classes. Public graph and
temporal-model certificates are conditional on the declared model and do not
identify realized vehicle runs. The new illustrative counterexamples are
mathematical constructions, not public-data observations.
