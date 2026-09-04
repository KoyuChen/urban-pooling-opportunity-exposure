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
- `code/ai_pilot/benchmarks/` -- the controlled-truth generator and evaluation.
- `code/ai_pilot/data_pipeline/results/` -- redacted aggregate evidence used by
  the current draft.
- `scripts/` -- paper build, PDF checks, and the local Chicago boundary runner.
- `ARTIFACT_MANIFEST.md` -- frozen run, artifact, file-hash, and claim pins.
- `docs/REPRODUCIBILITY.md` -- local and live rerun commands.

The historical path name `code/ai_pilot/` is retained to avoid a non-scientific
mass rename. No legacy AI/weak-linkage pipeline remains in the active tree.

## Current evidence

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
- The NYC branch-and-price lattice closes 14/18 integer cells exactly, including
  every capacity through 8 core + 24 buffer rows. The four remaining cells keep
  valid gaps of 1--4.
- The Chicago live audit is snapshot-stable and count-closed for 60 cores, 611
  temporal candidates, and 50,405 endpoint-bin contributors. Two distinct
  positive-length outer-envelope core covers differ on all 60 assignments, but
  they are not two completed operational hidden worlds.

Compact reports and machine-readable summaries are committed beside the older
supporting coarsening and common-support audits under
`code/ai_pilot/data_pipeline/results/`.

## Reproduce

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r code/ai_pilot/requirements.txt

python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
python code/ai_pilot/benchmarks/event_frontier_truth_benchmark_scale.py \
  --self-test

./scripts/build_paper.sh
./scripts/check_submission_pdf.sh \
  paper/build/KDD_Research_Working_Draft.pdf
```

The `ci` workflow runs the same deterministic checks and uploads the compiled
paper. Live Chicago audits are manual so ordinary manuscript commits do not
re-query public APIs.

## Claim boundary

Every endpoint is conditional on the declared candidate universe, timestamp
support, capacity, support count, and solver status. The repository does not
recover operational partner identities, validate proprietary release code,
identify blank-value causes, infer realized capacity, estimate population
prevalence, or establish causal effects. A nonempty frontier is not evidence
that candidate construction retained the true latent world.
