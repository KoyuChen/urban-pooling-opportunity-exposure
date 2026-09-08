# EventFrontier

Research code and manuscript for **Visible Rows, Hidden Events: Certified
Aggregates for Relation-Incomplete Event Streams**.

EventFrontier does not guess one missing event relation. It minimizes and
maximizes downstream aggregate queries over every temporally ordered event
world compatible with released rows, timestamp supports, a declared candidate
universe, and a simultaneous-capacity bound.

## Repository map

- `paper/` -- the active manuscript source.
- `code/ai_pilot/data_pipeline/production_audit/` -- ordered-event solvers,
  Chicago/NYC extraction, public-data audits, tests, fixtures, and protocols.
- `code/ai_pilot/benchmarks/` -- controlled-truth, disclosure, and ATR
  pedestrian-group truth validation.
- `code/ai_pilot/data_pipeline/results/` -- redacted aggregate evidence used by
  the current draft.
- `code/ai_pilot/benchmarks/results/` -- controlled exploration evidence.
- `scripts/` -- paper build, PDF checks, and the local Chicago boundary runner.
- `ARTIFACT_MANIFEST.md` -- frozen manuscript run, artifact, file-hash, and claim pins.
- `docs/REPRODUCIBILITY.md` -- local and live rerun commands.
- `docs/ATR_DIAMOR_TRUTH_AUDIT.md` -- real annotated-relation stress-test protocol.
- `code/ai_pilot/benchmarks/results/atr_diamor_unknown_q/` -- disclosure-safe
  cardinality-uncertainty evidence.
- `code/ai_pilot/benchmarks/results/atr_diamor_multiquery/` -- frozen cross-day
  multi-query and point-reconstruction evidence.
- `code/ai_pilot/benchmarks/results/atr_diamor_support_calibration/` -- frozen
  pilot-selected candidate-support follow-up evidence.
- `code/ai_pilot/benchmarks/results/atr_diamor_density_cap/` -- frozen post-hoc
  local-degree-cap mechanism audit.
- `code/ai_pilot/benchmarks/results/atr_diamor_alternating_structure/` -- frozen
  endpoint-witness alternating-structure audit.
- `docs/PROJECT_STATUS.md` -- verified manuscript versus exploration status.
- `docs/NEXT_RESEARCH_GATE.md` -- next structural comparison, Chicago follow-up
  calendar, execution gates and manuscript decision criteria.
- `docs/NYC_GEOMETRY_CENSUS.md` -- outcome-blind census on the original 24 NYC
  cells, exact non-clique event-column diagnostic and resumable execution.
- `code/ai_pilot/data_pipeline/results/nyc_hvfhv/structure_audit_20260908/` --
  fixed-input ordered/pair/clique diagnostic: 36 exact endpoint pairs and
  no changes in 24 common-count comparisons; the input is a complete clique.
- `docs/IMPLICIT_DISCLOSURE_SEPARATOR.md` -- separator contract and bound proofs.
- `docs/COMPACT_EVENT_SLOT_PROBE.md` -- compact lower-bound contract and audit.
- `docs/MANUSCRIPT_SCOPE_DECISION.md` -- current paper-scope decision.

The historical path name `code/ai_pilot/` is retained to avoid a non-scientific
mass rename. No legacy AI/weak-linkage pipeline remains in the active tree.

## Frozen manuscript evidence

- 3,000 controlled-truth instances across `C=2,3,4`; full candidate support
  covers the generated truth in every instance, while a feasible point world
  makes threshold errors in 17.4--19.0% of comparisons.
- Retaining about 84% of true candidate members preserves the complete true
  event world only 31--33% of the time.
- The frozen NYC decision panel contains 24 predeclared windows, 21 eligible
  windows, and 126 outcome-capacity cells. Exact endpoints close in 101 cells;
  125 are certified ambiguous at the candidate-median threshold and one is
  unresolved.
- Four feasible deterministic point methods disagree with one another in
  24/126 cells (19.0%). Across capacities they make 498 decisions, 494 (99.2%)
  inside certified-ambiguous cells. This is instability, not public-data
  accuracy, because memberships are absent.
- The NYC branch-and-price lattice closes all 18/18 predeclared integer cells
  exactly, through 16 core + 48 buffer rows at `C=2,3,4`. This is closure of one
  deterministic nested-size lattice, not city-scale event recovery.
- The Chicago live audit is snapshot-stable and count-closed for 60 cores, 611
  temporal candidates, and 50,405 endpoint-bin contributors. Two distinct
  positive-length outer-envelope core covers differ on all 60 assignments, but
  they are not two completed operational hidden worlds.

## Disclosure exploration: implementation and validation, not paper claims

The implicit separator supports fixed support, signed additive row costs,
event-count objectives, truthful usage and together/separate facts. Integer
witnesses are replayed and residual-repaired bounds use rational arithmetic.
The outer hitting-set procedure computes curator/ex-post minimum certificates,
not the unknown-answer cost of an adaptive acquisition policy.

The initial 45+15 certificate audit was expanded to 180 mean and 60 event-count
agreements with the small exact oracle. Pricing acceleration at `faff620`
closed 19/24 endpoints on a constructed development grid, versus 5/24 before.
That development grid is not independent validation.

The subsequent frozen-source, independent-seed ablation has 208 local runs:
192 primary (16 endpoint problems, six variants, two repeats) and 16 stress.
Full-solver primary closure is 24/32 with 32/32 replayed incumbents; without
batch reoptimization these are 19/32 and 22/32. The 48-row stress closes 6/16,
but none of the full-solver 32/48-row minimum-event runs closes in its budget.
Canonical restriction and caching do not show a uniform advantage. Two
no-canonical timeouts retain exact equal bounds, documented without relabeling
the raw statuses. No production tuning followed these observations.

See `code/ai_pilot/benchmarks/results/disclosure_independent_ablation/` for all
208 compact endpoint records, hashes, denominators and the full report, and
`docs/DISCLOSURE_INDEPENDENT_ABLATION.md` for the variant-validity arguments.
The six seeded candidate row sets and timing repeats are not 208 independent
worlds. These are local benchmark executions; CI checks tests and records.

None of these figures replaces the NYC 18/18 scale lattice. Real membership
truth, unknown support, noise robustness and selective-disclosure manuscript
integration remain open. Abstract all-partitions formulas require their stated
singleton-allowing model or conditional known-buddy-bundle interpretation.

## Compact event-slot evidence

The minimum-event solver includes an optional compact at-most-K event-slot
outer relaxation. Its 96-run paired audit is committed under
`code/ai_pilot/benchmarks/results/compact_event_slot_audit/`: exact status is
38/48 with the probe and
16/48 without it. Paired
exact gains/losses are 22/0; the
predeclared rule sets the default probe budget to `0.75` seconds. These are
synthetic implementation results, not manuscript or city-data claims.

## Reproduce

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r code/ai_pilot/requirements.txt

python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
python code/ai_pilot/benchmarks/event_frontier_truth_benchmark_scale.py \
  --self-test

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/selective_disclosure_branch_price_audit.py \
  --instances-per-capacity 5 --stress --output-dir tmp/disclosure-bp-audit

python code/ai_pilot/benchmarks/check_disclosure_independent_evidence.py

./scripts/build_paper.sh
./scripts/check_submission_pdf.sh \
  paper/build/KDD_Research_Working_Draft.pdf
```

Only `ci.yml`, `chicago-live-audits.yml`, `chicago-k2-fixed-panel.yml`, and the
manual `nyc-bp-24h.yml` follow-up remain active. The unified CI runs
deterministic tests and uploads the compiled paper. The Chicago panel retains
24 fixed outcome-blind date/time cells. Its initial checkpoint contains 19
completed windows, one ineligible window and four transport failures; recovery
verifies the checkpoint, retries only failed transfers and preserves attempt
history. See `docs/CHICAGO_K2_FIXED_PANEL.md` for the corrected endpoint counts
and resume commands. Four recovered windows raise the current merged count to
23 completed, one scientifically ineligible and zero failed windows. The
24-window pilot execution is closed with 2,744/3,430 certified endpoint pairs,
686 missing-public-value pairs and zero computationally unresolved pairs. The
full scale gate remains open because this is not a hundreds-of-cohorts
benchmark. The NYC follow-up isolates the four formerly open scale
cells in separate fail-closed jobs; it is not restarted by ordinary manuscript
commits.

## Claim boundary

Every endpoint is conditional on the declared candidate universe, timestamp
support, capacity, support count, and solver status. The repository does not
recover operational partner identities, validate proprietary release code,
identify blank-value causes, infer realized capacity, estimate population
prevalence, or establish causal effects. A nonempty frontier is not evidence
that candidate construction retained the true latent world.
