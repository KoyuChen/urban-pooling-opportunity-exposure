# Evidence manifest

Only current EventFrontier evidence is listed here. Generated PDFs, raw public
rows, and superseded experiments are excluded from the active tree. Manuscript
JSON files are normalized summaries checked by CI; the manuscript SHA-256 pins
refer to their original workflow artifacts. The final section separately
identifies local exploration provenance and does not label it as workflow execution.

## Canonical source

| Object | Path |
|---|---|
| Manuscript | `paper/main.tex` |
| Ordered-event algorithms and public audits | `code/ai_pilot/data_pipeline/production_audit/` |
| Controlled-truth benchmark | `code/ai_pilot/benchmarks/event_frontier_truth_benchmark_scale.py` |
| Aggregate public evidence | `code/ai_pilot/data_pipeline/results/` |
| Deterministic verification | `.github/workflows/ci.yml` |

## Controlled truth

- 3,000 instances over `C=2,3,4`.
- Full candidate support covers the generated true aggregate in every instance.
- A feasible outcome-blind temporal point world makes threshold errors in
  17.4--19.0% of comparisons; every such error is relation-ambiguous under the
  frontier.
- Retaining six of eight candidates preserves roughly 84% of true members but
  the complete true event world only 31--33% of the time.

These results validate the declared generator and method, not transfer to an
operational city dataset.

## NYC frozen decision panel

Repository summaries:

- `code/ai_pilot/data_pipeline/results/nyc_hvfhv/ORDERED_DECISION_PANEL_REPORT.md`
- `code/ai_pilot/data_pipeline/results/nyc_hvfhv/ORDERED_DECISION_PANEL_SUMMARY.json`
- `code/ai_pilot/data_pipeline/results/nyc_hvfhv/ORDERED_DECISION_PANEL_GROUPS.csv`
- `code/ai_pilot/data_pipeline/results/nyc_hvfhv/ORDERED_DECISION_THRESHOLD_GROUPS.csv`

Original source pins:

- workflow: `nyc-hvfhv-ordered-decision-panel`;
- run: `33760441027`;
- artifact: `9903823780`;
- artifact ZIP SHA-256:
  `f0b074b618c76b72a2d0a7c5d930f13e99d819d1fc4f335cd2f5e686b1a66ad9`;
- source artifact `report.json` SHA-256:
  `40871c2a19c34602209378e2a57f966302095b5062ab26ac173f378a8e2bb8ef`;
- source artifact `REPORT.md` SHA-256:
  `bc7fae39c5c3554ef5fada2d569f773f9bdf26a1c5e4b89b20285d6eeda66b98`.

Results:

- 24 predeclared windows; 21 eligible, three outcome-blind ineligible, zero
  technical failures, and zero missing terminal reports;
- 126 outcome--capacity cells;
- 101/126 (80.2%) exact endpoint pairs;
- 125/126 (99.2%) certified ambiguous candidate-median decisions and one
  unresolved decision;
- four feasible point methods disagree with one another in 24/126 cells
  (19.0%);
- 494/498 capacity-indexed point decisions (99.2%) occur inside
  certified-ambiguous cells.

The 19.0% statistic is disagreement among point methods, not disagreement with
observed truth or with a certified direction. NYC public rows contain no event
membership truth.

## NYC branch-and-price scale lattice

Repository summaries:

- `code/ai_pilot/data_pipeline/results/nyc_hvfhv/BRANCH_AND_PRICE_SCALE_REPORT.md`
- `code/ai_pilot/data_pipeline/results/nyc_hvfhv/BRANCH_AND_PRICE_SCALE_CELLS.csv`
- `code/ai_pilot/data_pipeline/results/nyc_hvfhv/BRANCH_AND_PRICE_SCALE_MANIFEST.json`

Original source pins:

- workflow run: `33837187046`;
- source commit: `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`;
- artifact: `9897266899`;
- artifact ZIP SHA-256:
  `603fd059d600176e178ddcbdd6d1d40c36cf2d59d9c11e9c3130a81eae32a4cf`;
- source artifact `report.json` SHA-256:
  `1056ee441a4cd91b518b43f7c0565f5e4f349c3206d3ba9a027d64ce5c6800ed`;
- source artifact `REPORT.md` SHA-256:
  `53055ec7b2a0f2093a1c00db29dacfe3173438c28175dc157be0a8613748a60d`.

Cells range from 4 core + 12 buffer rows through 16 core + 48 buffer rows at
`C=2,3,4`. Fourteen of 18 cells close exactly. The open cells retain valid
intervals `[27,30]`, `[32,36]`, `[43,44]`, and `[45,48]`; no timeout is promoted
to optimality.

## Chicago live release-operator audit

Repository summaries:

- `code/ai_pilot/data_pipeline/results/chicago_release_operator_audit/REPORT.md`
- `code/ai_pilot/data_pipeline/results/chicago_release_operator_audit/release_operator_audit.json`

Original source pins:

- source commit: `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`;
- workflow run: `33837186969` (run 164);
- artifact: `9923960043`;
- artifact ZIP SHA-256:
  `98b7117b14c3150df655d88f171be6f05d0774449af18d354fac98f639e1226b`;
- source artifact JSON SHA-256:
  `26b682d967716cfc356cfc4d68a39446bdc85c941d676bb7bea5323e1f71dca3`;
- source artifact JSON self-hash:
  `79b8825ade529b41fbb144e44e0f6f61dec8126ed90ee87a328b8d6e43899fe6`;
- source artifact Markdown SHA-256:
  `64adf8d544125433436b30fbc6e7c03e340c976b9f281e8327bea74e5fadaaad`.

The audit count-closes 60 core rows, 611 K=2 temporal candidates, and 50,405
all-trip endpoint-bin contributors through a narrow overlap index followed by
exact released-start and endpoint-bin shards. The positive-length outer-envelope
graph has two distinct optimal core covers differing on all 60 assignments,
with zero reported MIP gap and replay residual.

The licensed status is `PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY`. The two covers
are not two complete Chicago hidden-run worlds. The audit does not validate
private City code, infer null causes, construct common exact timestamp
witnesses, pair all buffers, or recover partners.

## Chicago K=2 boundary audit

The committed aggregate evidence under
`code/ai_pilot/data_pipeline/results/chicago_k2_frontier_boundary/` records 60
core rows, 551 boundary-complete buffers, 24,274 temporal edges, and 96
certified endpoint pairs with zero reported MIP gap and replay residual. A
15-minute complete boundary adds 92 buffers and 2,629 edges relative to the
under-padded extraction.

## Artifact policy

Committed evidence is aggregate and redacted. Raw identifiers, public-row
extracts, event columns, reconstructed partners, matching witnesses, latent
timestamps, generated PDFs, caches, and workflow ZIPs are excluded from the
active tree.


## Separate local disclosure exploration (not frozen manuscript evidence)

The independent-seed ablation is recorded under
`code/ai_pilot/benchmarks/results/disclosure_independent_ablation/`.
Unlike the manuscript artifacts above, these measurements were executed locally,
not in GitHub Actions. A source-export workflow was transport only and is removed.

- Frozen solver commit: `faff620fe2ca867d6861b0ac3e8d0c590589fd80`.
- Solver SHA-256: `f520a5e0d047ae0d6ebe3b3435f8577aed1a1247401cd403622e89ff2bf316f4`.
- Pre-performance protocol commit: `2e70d1663cf6f1d427e6a470274fa5b36297dbf3`.
- Runner commit: `847b0e867be9346abd8adc645d6bc80958d8aab3`.
- Protocol SHA-256: `7190914c7b106128f8fc548dc3d6f1eeb5b17224113d7c832f4a96e02ea69e46`.
- Runner SHA-256: `57cde6160ce4f6ef44bbf4e3b5433e2b0d6c430026f569b3172a6743a9affcc4`.
- Committed RUNS.json SHA-256: `0672c8f1dbacf77d7ef62827bdb1886291e43791650a49546fd7451f30405c47`.
- Original detailed local report SHA-256: `980fb4ba0f42b19f2966cd53f9095044cfee39f06c50dff4285350cc3eebaf70`.

All 208 endpoint records are retained in compact form. SUMMARY.json is derived
from these records, not from selected successful runs. The full solver closes
24/32 primary and 6/16 larger stress replicate runs, with incumbents in all
48 full-solver invocations. Two no-canonical records retain equal exact bounds
but an unresolved timeout label; raw labels are preserved. This licenses a
small seeded synthetic, conditional component comparison, not a universal
speedup, city-scale, real-truth, operational-query or privacy guarantee.


## Compact event-slot lower-bound audit

Separate implementation evidence, not frozen manuscript evidence:

- workflow run: `33951594827`;
- protocol SHA-256: `73276660d440342ce818dcbf00d0cb30aa8b9ffb2ba4a1cb16904c52f0077b8a`;
- final solver SHA-256: `9b9c47ec2e5261ea09f5c2871dcfa39c4e51fa055ccdcd6ac117ba763a5c0a61`;
- timed pre-default solver SHA-256: `8442dbcd55a39cdf3679dd890562086bb1dc16fda38d20fe76451e76f4361207`;
- compact probe SHA-256: `35672478815ac8de36de1982df0a68035660bc7f0a553c684c55d1bb69d47d52`;
- RUNS/SUMMARY/DEFAULT/REPORT SHA-256: `9460bd40ce95eb6f8f46686c883ff55d951e9828d5f1fe848408154c81fe592c`, `a4d25be6f490040174b248f4fac5775b8ade0879ec1dfa86136490f177f6b321`, `8ad50d535d48489bdd18e5fb7665d7d9427b8bb40722dd8392f9955fc44689e9`, `677fc54a97b06304d195c7e9b53dd054bf46c869a2630a4901430b7352b096c9`.

The package retains all 96 records and selects
`compact_probe_seconds=0.75` under the predeclared no-loss rule. It licenses
only synthetic fixed-support lower-bound behavior.
