# Thicker but Narrower?

Working paper and reproducible, human-experiment-free pilot for the KDD 2027
AI for Sciences Track.

> **Status:** ACM-formatted research draft, not a submission-ready empirical
> paper. The method and known-truth validation are complete. The complete-day
> Chicago estimates, policy analysis, and institutional human-subjects
> determination remain required before submission.

## Research question

Public ride-pooling records expose trip-level match outcomes but suppress the
service-chain identifier. `BoundPool` treats the missing relational structure
as a partially identified object: it builds a physically admissible candidate
graph, learns edge hazards from node-level labels, and optimizes
neighborhood-level opportunity-exposure statistics over feasible exact-cover
packings.

The paper studies **compatibility-weighted opportunity exposure**, not observed
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
- narrows the untrimmed same-income-bin range by 34.5% at a 90% score floor and
  by 58.6% at a 95% score floor, while covering the hidden truth at both floors.

The original 28-feature model is retained only as a diagnostic. In the locked
generator, tract equality mechanically encodes the same-income target; its
apparently sharper 95% interval excludes truth. Continuous coordinates still
carry residual proxy information after the six-feature ablation, so all
score-restricted bounds remain model-dependent sensitivity regions. The
untrimmed candidate-graph interval is the primary score-free result.

All benchmark records are synthetic and explicitly labeled. These numbers are
not estimates about Chicago passengers.

## Repository map

- `paper/main.tex` — eight-page ACM main paper followed by references and an
  optional reproducibility appendix.
- `paper/Thicker_But_Narrower_Draft.pdf` — compiled review-format draft.
- `code/ai_pilot/` — candidate construction, weak-MIL model, exact-cover
  bounds, known-truth benchmark, and geography-equality ablation.
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
and candidate graph. Hidden pair truth is read only after fitting for
evaluation.

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

Cells marked `TBD` are empirical gates, not cosmetic placeholders. They must be
replaced with measured complete-day results or the corresponding claims must
be removed. The Chicago prefix extract is used only for schema and pipeline
mechanics because identifier-prefix sampling destroys most latent service
chains.
