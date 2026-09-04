# Evidence manifest

Only current EventFrontier evidence is listed here. Generated PDFs, raw public
rows, and superseded experiments are excluded from the active tree. Repository
JSON files are normalized summaries checked by CI; the SHA-256 values below pin
the original workflow artifacts from which they were transcribed.

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
