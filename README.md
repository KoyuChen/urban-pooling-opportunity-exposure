# EventFrontier

Research code and manuscript for **Visible Rows, Hidden Events: Certified
Aggregates for Relation-Incomplete Event Streams**.

EventFrontier does not guess one missing event relation. It minimizes and
maximizes downstream aggregate queries over every temporally ordered event
world compatible with released rows, timestamp supports, a declared candidate
universe, and a simultaneous-capacity bound.

## Repository map

- `paper/` — the only active manuscript source.
- `code/ai_pilot/data_pipeline/production_audit/` — ordered-event solvers,
  Chicago/NYC extraction, public-data audits, tests, fixtures, and protocols.
- `code/ai_pilot/benchmarks/` — the controlled-truth generator and evaluation.
- `code/ai_pilot/data_pipeline/results/` — redacted aggregate evidence used by
  the current draft.
- `scripts/` — paper build, PDF checks, and the local Chicago boundary runner.
- `ARTIFACT_MANIFEST.md` — frozen run, artifact, and claim pins.
- `docs/REPRODUCIBILITY.md` — local and live rerun commands.

The historical path name `code/ai_pilot/` is retained to avoid a non-scientific
mass rename. No legacy AI/weak-linkage pipeline remains in the active tree.

## Current evidence

- 3,000 controlled-truth instances across `C=2,3,4`; full candidate support
  covers the generated truth in every instance, while a feasible point world
  makes threshold errors in 17.4–19.0% of comparisons.
- Retaining about 84% of true candidate members preserves the complete true
  event world only 31–33% of the time.
- A frozen 24-window NYC panel contains 21 scientifically eligible windows and
  126 outcome-capacity cells; 80.2% of endpoint pairs close exactly and the
  point rule disagrees with the certified decision in 19.0% of cells.
- The NYC branch-and-price scale lattice closes 14 of 18 cells exactly and
  retains valid incumbent/open-node bounds for the rest.
- The Chicago live audit is snapshot-stable and count-closed for 60 core rows,
  611 temporal candidates, and 50,405 all-trip endpoint-bin contributors.

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
