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
- `code/ai_pilot/benchmarks/` -- controlled-truth and disclosure validation.
- `code/ai_pilot/data_pipeline/results/` -- redacted aggregate evidence used by
  the current draft.
- `code/ai_pilot/benchmarks/results/` -- controlled exploration evidence.
- `scripts/` -- paper build, PDF checks, and the local Chicago boundary runner.
- `ARTIFACT_MANIFEST.md` -- frozen manuscript run, artifact, file-hash, and claim pins.
- `docs/REPRODUCIBILITY.md` -- local and live rerun commands.
- `docs/PROJECT_STATUS.md` -- verified manuscript versus exploration status.
- `docs/IMPLICIT_DISCLOSURE_SEPARATOR.md` -- new separator contract and bound proofs.

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
- The NYC branch-and-price lattice closes 14/18 integer cells exactly, including
  every capacity through 8 core + 24 buffer rows. The four remaining cells keep
  valid gaps of 1--4.
- The Chicago live audit is snapshot-stable and count-closed for 60 cores, 611
  temporal candidates, and 50,405 endpoint-bin contributors. Two distinct
  positive-length outer-envelope core covers differ on all 60 assignments, but
  they are not two completed operational hidden worlds.

## Disclosure exploration: implementation checkpoint, not manuscript claims

The new `ordered_run_disclosure_separator.py` supports fixed support, signed
additive row costs, event-count objectives, usage facts, and together/separate
facts. It generates columns implicitly, replays integer witnesses, and repairs
LP dual bounds in rational arithmetic. An exact hitting-set master invokes it
to compute curator/ex-post minimum decision certificates. This is not an
adaptive acquisition policy or an operational privacy guarantee.

The new local audit has 45/45 mean-certificate and 15/15 event-count-certificate
agreements with the explicit small oracle. Constructed 16/32-row stress closes
5/6 endpoints under the declared budget; the sequential 32-row minimum remains
unresolved. Easy simultaneous stress uses a disclosed deterministic warm start.
See `code/ai_pilot/benchmarks/results/selective_disclosure_branch_price/` for
source hashes, environment, exact design, and the unresolved result.

These results do not replace the frozen NYC 14/18 scale lattice. Real event-
membership truth, noise robustness, broad scale validation, and manuscript
integration remain open. The all-partitions formula audit is explicitly scoped
to an abstract singleton-allowing model or a known-buddy-bundle embedding.

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

./scripts/build_paper.sh
./scripts/check_submission_pdf.sh \
  paper/build/KDD_Research_Working_Draft.pdf
```

Only `ci.yml` and `chicago-live-audits.yml` remain active. The unified CI runs
deterministic tests and uploads the compiled paper. Expensive benchmark commands
are explicit local/manual runs, not restarted by one-off workflows on every push.

## Claim boundary

Every endpoint is conditional on the declared candidate universe, timestamp
support, capacity, support count, and solver status. The repository does not
recover operational partner identities, validate proprietary release code,
identify blank-value causes, infer realized capacity, estimate population
prevalence, or establish causal effects. A nonempty frontier is not evidence
that candidate construction retained the true latent world.
