# Evidence manifest

This file is the authoritative map from repository objects to licensed
scientific claims. CI output and committed aggregate manifests are evidence;
working prose, exploratory notebooks, and archived pilots are not.

## Canonical paper and method

| Object | Canonical path | Licensed role |
|---|---|---|
| Working manuscript | `paper/main.tex` | Current EventFrontier model, theorem, algorithm, and experiment narrative |
| Fixed-time master and pricing | `code/ai_pilot/data_pipeline/production_audit/ordered_run_fixed_time_master.py`, `ordered_run_interval_oracle.py` | Exact local pricing and complete-column reference objects |
| Column generation | `code/ai_pilot/data_pipeline/production_audit/ordered_run_column_generation.py` | Full-master LP closure after exact pricing termination |
| Branch-and-price | `code/ai_pilot/data_pipeline/production_audit/ordered_run_branch_and_price.py` | Certified integer optimum when the queue closes; incumbent/open-node gap otherwise |
| Controlled truth | `code/ai_pilot/benchmarks/event_frontier_truth_benchmark.py` and committed aggregate outputs | Coverage and decision-risk validation with observed synthetic event truth |
| Public-data audits | `code/ai_pilot/data_pipeline/production_audit/` | Conditional feasible-world evidence; never partner recovery |

## Current locked evidence

### Controlled truth

- 3,000 instances across capacity values `C=2,3,4`.
- Full candidate support contains the true aggregate in every instance.
- A feasible temporal point reconstruction makes threshold errors in
  17.4--19.0% of cases; every such error is relation-ambiguous under the
  frontier.
- Candidate retention near 84% preserves the complete true event world only
  31--33% of the time.

These results license a decision-risk and candidate-retention claim. They do
not license transfer to Chicago or NYC.

### NYC public panel

- Frozen 24-window exact-second design spanning four seasons, weekday/weekend
  regimes, and multiple dayparts.
- 21 scientifically eligible windows and three outcome-blind ineligible
  windows; no technical failures in the successful frozen panel.
- 126 outcome-capacity cells, 80.2% exact endpoint-pair closure, 99.2%
  certified ambiguity at the candidate median threshold, and 19.0% point-rule
  disagreement with the certified decision.
- Latest retained successful summary: workflow
  `nyc-hvfhv-ordered-decision-panel`, run `33760441027`, artifact
  `9903823780`.

These figures are conditional on the declared public candidate universe. The
public data do not contain event-membership truth.

### NYC branch-and-price scale lattice

- Predeclared cells from 4 core + 12 buffer rows through 16 core + 48 buffer
  rows at capacities `C=2,3,4`.
- 14 of 18 cells close exactly; the remaining four retain valid incumbent and
  open-node upper bounds.
- Latest successful workflow at the cleanup pin:
  `nyc-hvfhv-branch-and-price-scale`, run `33837187046`, source commit
  `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`.

This licenses a certified medium-instance algorithmic path, not a city-scale
runtime guarantee.

### Chicago live release-operator audit

Pinned successful run:

- source commit: `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`;
- workflow run: `33837186969` (`chicago-release-operator-audit` run 164);
- artifact: `9923960043`;
- artifact ZIP SHA-256:
  `98b7117b14c3150df655d88f171be6f05d0774449af18d354fac98f639e1226b`;
- report file SHA-256:
  `26b682d967716cfc356cfc4d68a39446bdc85c941d676bb7bea5323e1f71dca3`;
- report self-hash:
  `79b8825ade529b41fbb144e44e0f6f61dec8126ed90ee87a328b8d6e43899fe6`.

The run reports:

| Quantity | Result |
|---|---:|
| Core rows | 60 |
| K=2 temporal candidates | 611 |
| All-trip endpoint-bin contributors | 50,405 |
| Candidate start shards | 14 |
| Contributor start/end shards | 14 / 13 |
| Snapshot stable during extraction | yes |
| Candidate and contributor count closure | yes |
| Positive-length graph cover multiplicity | two distinct core covers certified |
| Certified MIP gap / replay residual | 0 / 0 |

The transport strategy is
`NARROW_OVERLAP_INDEX_THEN_EXACT_START_AND_ENDPOINT_BIN_SHARDS`. Full-row
cross-column range queries and broad `OR` queries are not used.

The licensed status remains
`PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY`. This run does not validate City private
production code, infer null causes, construct complete hidden runs, or recover
partners.

### Chicago K=2 boundary audit

Committed aggregate evidence under
`code/ai_pilot/data_pipeline/results/chicago_k2_frontier_boundary/` records:

- 60 core rows, 551 boundary-complete buffers, and 24,274 temporal edges;
- 96 certified endpoint pairs with zero reported MIP gap and replay residual;
- no mathematical monotonicity violation on fully certified chains;
- 15-minute boundary completion adding 92 buffers and 2,629 edges relative to
  the unpadded extraction.

This is a candidate-support and boundary sensitivity audit, not hidden-run
closure.

## Generated artifacts

Generated PDFs, logs, temporary solver outputs, downloaded public rows, and
workflow artifacts are not committed to active source paths. Local paper builds
write to `paper/build/`; Actions uploads the PDF as an artifact. Committed
aggregate result tables and manifests must contain no raw trip identifiers,
matching witnesses, or row-level latent assignments.

## Legacy material

Earlier weak-node-score, hidden-matching, conformal-score, and release-compiler
pilots are retained under `archive/legacy-ai4science/` and
`archive/pre-eventfrontier-2026-09-04/`. Their old workflow definitions are
stored under `archive/workflows/` with `.disabled` suffixes. They document the
research path and falsified approaches but are not current paper evidence.

## Open submission gates

- integrate the frozen NYC panel, scale lattice, and Chicago run-164 evidence
  into the manuscript without changing their estimands;
- keep candidate-universe coverage separate from conditional endpoint
  correctness;
- verify every abstract/conclusion sentence against a pinned artifact or a
  proved statement;
- complete final double-blind, page-limit, bibliography, figure, and artifact
  checks;
- do not claim operational partner recovery, realized capacity, City
  implementation fidelity, population prevalence, or causal effects.
