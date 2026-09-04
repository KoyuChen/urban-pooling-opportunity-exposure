# Visible Rows, Hidden Events

Research repository for **EventFrontier**, a method for certified aggregate
inference when every transaction row is visible but the relation joining rows
into bounded-capacity temporal events is not.

The repository is organized around one current paper and one current scientific
object. Earlier hidden-matching, weak-node-score, and release-compiler pilots are
preserved under `archive/` and are not headline evidence.

## Current status

As of 2026-09-04:

- the canonical manuscript is `paper/main.tex`;
- controlled-truth experiments cover 3,000 instances, with feasible point
  reconstructions making threshold errors in 17.4--19.0% of cases;
- retaining about 84% of true candidate members preserves the complete true
  event world only 31--33% of the time;
- the predeclared NYC decision panel covers 24 windows, of which 21 are
  scientifically eligible, with 126 outcome-capacity cells;
- the NYC branch-and-price scale lattice closes 14 of 18 cells exactly and
  reports valid incumbent/upper-bound gaps for the rest;
- the Chicago live release-operator audit is green at commit
  `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`: 60 core rows, 611 temporal
  candidates, and 50,405 all-trip endpoint-bin contributors are count-closed
  under a snapshot-stable, exact-time-bin sharded extraction.

The project is **not yet submission-frozen**. The remaining work is claim
integration and evidence packaging, not another model pivot. Candidate-support
coverage, public-release semantics, and hidden-run closure remain explicit
boundaries.

## Scientific target

For released rows with exact or set-valued timestamps, EventFrontier considers
all ordered event decompositions satisfying:

1. every core row is assigned exactly once;
2. each optional buffer row is used at most once;
3. each event is connected through positive temporal overlap;
4. simultaneous occupancy does not exceed a declared capacity; and
5. the selected support and downstream query are evaluated on the same latent
   world.

The output is a pair of attained aggregate endpoints, together with
certificates or valid lower/upper bounds. It is not a recovered partner graph.

## Canonical repository map

- `paper/main.tex` -- anonymous ACM/KDD working manuscript.
- `paper/sections/` -- only sections imported by `main.tex`.
- `code/ai_pilot/bounds/` -- reference endpoint and decomposition algorithms.
- `code/ai_pilot/benchmarks/` -- controlled truth, exact-oracle, and scale
  validation.
- `code/ai_pilot/data_pipeline/production_audit/` -- Chicago and NYC public-data
  audits, fixed-support frontiers, column generation, and branch-and-price.
- `code/ai_pilot/external_benchmarks/` -- external relation-topology boundary
  checks.
- `adversarial_review/` -- executable counterexamples and historical issue
  ledger.
- `ARTIFACT_MANIFEST.md` -- authoritative evidence pins and claim licenses.
- `SUBMISSION_CHECKLIST.md` -- current KDD go/no-go gates.
- `docs/REPRODUCIBILITY.md` -- local and live rerun commands.
- `docs/REPOSITORY_POLICY.md` -- source, evidence, generated-output, and archive
  policy.
- `archive/` -- superseded material retained for provenance only.

The historical directory name `code/ai_pilot/` is retained to avoid a large,
non-scientific path migration. It does not imply that the current paper is an
AI-pilot paper.

## Reproduce the current build

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r code/ai_pilot/requirements-ci.txt

python -m unittest discover -s code/ai_pilot/bounds/tests -v
python -m unittest discover -s code/ai_pilot/data_pipeline/tests -v
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
python -m unittest discover -s code/ai_pilot/external_benchmarks/tests -v
python adversarial_review/counterexamples.py

./scripts/build_paper.sh
./scripts/check_submission_pdf.sh \
  paper/build/KDD_Research_Working_Draft.pdf
```

`build_paper.sh` writes only to the ignored `paper/build/` directory. The
compiled PDF uploaded by the `ci` workflow is the authoritative generated
paper artifact; GitHub Actions no longer commits PDFs back into the branch.

## Workflow policy

Only two active workflows remain:

- `ci` runs deterministic tests, locked solver checks, and the paper build on
  pushes and pull requests;
- `chicago-live-audits` is manually dispatched for the live release-operator
  and K=2 boundary audits.

The exact YAML used for earlier one-off NYC and Chicago runs is retained as
`.disabled` provenance under `archive/workflows/`. Expensive frozen panels do
not restart on every manuscript commit.

## Claim boundary

The artifact supports conclusions conditional on the declared candidate
universe, timestamp support, capacity bound, and solver status. It does not
recover operational partner identities, validate a city's private production
code, infer a blank's cause, identify realized capacity, establish population
prevalence, or support a causal policy effect.

A nonempty frontier does not prove that the true latent world survived candidate
construction. Every manuscript claim must distinguish endpoint correctness
conditional on support from evidence about support coverage.
