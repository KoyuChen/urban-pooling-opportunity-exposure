# Evidence manifest

Only current EventFrontier evidence is listed here. Historical pilots,
superseded workflows, generated PDFs, and raw public rows are not retained in
the repository.

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
  17.4–19.0% of comparisons; every such error is relation-ambiguous under the
  frontier.
- Retaining six of eight candidates preserves roughly 84% of true members but
  the complete true event world only 31–33% of the time.

These results validate the declared generator and method, not transfer to an
operational city dataset.

## NYC

### Frozen decision panel

- 24 predeclared exact-second windows; 21 scientifically eligible and three
  outcome-blind ineligible.
- 126 outcome-capacity cells.
- 80.2% exact endpoint-pair closure.
- 99.2% certified ambiguity at the candidate-median threshold.
- 19.0% point-rule disagreement with the certified decision.
- Workflow: `nyc-hvfhv-ordered-decision-panel`, run `33760441027`.
- Artifact: `9903823780`.

### Branch-and-price scale lattice

- Cells range from 4 core + 12 buffer rows through 16 core + 48 buffer rows at
  `C=2,3,4`.
- 14/18 cells close exactly; the other four retain valid incumbent and open-node
  upper bounds.
- Workflow run: `33837187046`.
- Source commit: `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`.

NYC public rows contain no event-membership truth. All results are conditional
on the declared candidate and event-world contracts.

## Chicago

### Live release-operator audit

- Source commit: `b2e549e7e4cc674a7a880dc7789ee5f3c960d2b0`.
- Workflow run: `33837186969` (run 164).
- Artifact: `9923960043`.
- Artifact ZIP SHA-256:
  `98b7117b14c3150df655d88f171be6f05d0774449af18d354fac98f639e1226b`.
- Report SHA-256:
  `26b682d967716cfc356cfc4d68a39446bdc85c941d676bb7bea5323e1f71dca3`.
- Report self-hash:
  `79b8825ade529b41fbb144e44e0f6f61dec8126ed90ee87a328b8d6e43899fe6`.

| Quantity | Result |
|---|---:|
| Core rows | 60 |
| K=2 temporal candidates | 611 |
| All-trip endpoint-bin contributors | 50,405 |
| Candidate start shards | 14 |
| Contributor start/end shards | 14 / 13 |
| Snapshot stable during extraction | yes |
| Candidate and contributor count closure | yes |
| Distinct positive-length graph covers | certified |
| Certified MIP gap / replay residual | 0 / 0 |

Transport uses a narrow overlap index followed by exact released-start and
endpoint-bin full-row shards. Broad `OR` pulls and full-row cross-column range
queries are not used.

The licensed status is `PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY`. It does not
validate private City code, infer null causes, construct complete hidden runs,
or recover partners.

### K=2 boundary audit

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
