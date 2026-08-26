# Admissible Sets for Opportunity Exposure in Privacy-Coarsened Ride-Pooling Records

Working paper and reproducible, human-experiment-free pilot for the KDD 2027
AI for Sciences Track.

> **Status:** ACM-formatted research draft, not a submission-ready empirical
> paper. The method and known-truth validation are complete. The complete-day
> Chicago estimates, policy analysis, and institutional human-subjects
> determination remain required before submission.

## Research question

Public ride-pooling records expose trip-level match outcomes but suppress the
service-chain identifier. `BoundPool` treats the suppressed grouping as a
structured, partially identified relation. It declares physically admissible
candidate pairs, learns model-indexed compatibility scores from node-level
labels, and computes the minimum and maximum neighborhood-level
opportunity-exposure statistic over all feasible exact-cover pairings. It does
not reconstruct a preferred co-rider graph.

The paper studies **admissible-set opportunity exposure**, not observed
co-rider identity, individual income, co-presence, attitude change, or an echo
chamber.

## Current pilot result

The primary synthetic benchmark removes six geography-equality features from
the weak-MIL score. On the locked held-out day it:

- improves candidate-supported node Brier loss by 90.2% over the transparent
  rule (0.06048 to 0.00595);
- raises hidden-edge mean reciprocal rank from 0.781 to 0.941 and ranks the
  hidden edge first for 90.0% of matched endpoints;
- retains all 80 hidden true pairs in the candidate graph;
- narrows the untrimmed same-income-bin range by 34.5% at `rho=0.90` and by
  58.6% at `rho=0.95`, while retaining the hidden pairing at both floors.

The original 28-feature model is retained only as a diagnostic. In the locked
generator, tract equality mechanically encodes the same-income target; its
apparently sharper `rho=0.95` interval excludes truth. Continuous coordinates still
carry residual proxy information after the six-feature ablation, so all
score-restricted bounds remain model-dependent sensitivity regions. The
untrimmed interval over every physically supported exact-cover pairing is the
primary score-free result.

All benchmark records are synthetic and explicitly labeled. These numbers are
not estimates about Chicago passengers.

## Repository map

- `paper/main.tex` — eight-page ACM main paper followed by references and an
  optional reproducibility appendix.
- `paper/Thicker_But_Narrower_Draft.pdf` — compiled review-format draft.
- `paper/figures/benchmark_summary_revised.svg` — editable vector source for
  Figure 1; the PDF twin is embedded in the manuscript.
- `code/ai_pilot/` — candidate construction, weak-MIL compatibility scoring,
  exact-cover admissible-set bounds, known-truth benchmark, and
  geography-equality ablation.
- `docs/literature/om_econ_update_2026-08-25.md` — adversarial OM/Econ
  positioning audit, six added references, and monthly search watch terms.
- `SUBMISSION_CHECKLIST.md` — direct mapping to the supplied AI4Sciences CFP.
- `ARTIFACT_MANIFEST.md` — evidence status and file-level provenance.

## Reproduce the offline pilot

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r code/ai_pilot/requirements.txt

python code/ai_pilot/model/smoke_test.py
python -m unittest discover -s code/ai_pilot/bounds/tests -v
python code/ai_pilot/bounds/synthetic_validation.py \
  --output-dir /tmp/boundpool-solver-check
python code/ai_pilot/integration/run_integration_benchmark.py \
  --output-dir /tmp/boundpool-integration
python code/ai_pilot/integration/ablations/no_geography_equality_20260825/run_ablation.py \
  --locked-result-dir code/ai_pilot/integration/results \
  --output-dir /tmp/boundpool-no-geography-equality
```

The ablation reuses the committed design lock, public-like synthetic records,
and physically admissible candidate relation. Hidden pair truth is read only
after fitting for evaluation.

## Build and check the paper

A TeX Live installation containing `acmart`, BibTeX, and `latexmk` is required.

```bash
./scripts/build_paper.sh
./scripts/check_submission_pdf.sh paper/Thicker_But_Narrower_Draft.pdf
```

The source intentionally uses:

```tex
\documentclass[sigconf,review]{acmart}
```

The current PDF has eight pages of main content. References and the optional
appendix begin on page 9. The required `Limitations and Ethical Considerations`
and `Generative AI Usage` sections are both inside the main-paper page limit.

## Claim boundary

Complete-day result cells are explicitly marked `Reserved`; they must be
replaced with measured results or the corresponding claims must be removed.
The Chicago prefix extract is used only for schema and pipeline
mechanics because identifier-prefix sampling destroys most latent service
chains.
