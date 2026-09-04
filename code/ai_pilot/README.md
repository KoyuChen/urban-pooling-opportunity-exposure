# EventFrontier implementation

This directory contains the current reference implementation and reproducible
audits for the EventFrontier paper. The path name `ai_pilot` is historical and
is retained only to avoid a broad import/workflow migration.

## Current directories

- `bounds/` -- exact and numerical endpoint solvers, interval/path frontiers,
  release constraints, component decomposition, and supporting tests.
- `benchmarks/` -- controlled truth, exhaustive comparators, solver audits, and
  bounded runtime profiles.
- `data_pipeline/` -- public-data adapters and production audits. The current
  Chicago and NYC event-frontier runners live in `data_pipeline/production_audit/`.
- `external_benchmarks/` -- external relation-topology and method-boundary
  checks; no raw external data are committed.

The earlier weak-node-score model and integration pipeline were moved to
`archive/legacy-ai4science/`. They are provenance and failure analysis, not
current paper code. See `LEGACY.md`.

## Deterministic tests

```bash
python -m unittest discover -s code/ai_pilot/bounds/tests -v
python -m unittest discover -s code/ai_pilot/data_pipeline/tests -v
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
python -m unittest discover -s code/ai_pilot/external_benchmarks/tests -v
python -m unittest discover \
  -s code/ai_pilot/benchmarks/runtime_profile -p 'test_*.py' -v
```

The `ci` workflow additionally replays locked solver audits and compiles the
paper. A timeout is recorded as unresolved; it is never converted to
infeasibility or optimality.

## Current public-data boundary

The Chicago release-operator audit has a successful live, snapshot-stable,
count-closed run for 60 core rows, 611 candidates, and 50,405 all-trip
endpoint-bin contributors. It uses a narrow overlap index followed by exact
released-time shards. This validates the declared public extraction contract,
not the City's private transformation code or hidden partner identities.

NYC public audits use exact public timestamps and declared candidate universes.
They provide conditional feasible-world evidence; the public release does not
supply event-membership truth.

## Outputs

Write local and live outputs to ignored directories such as `tmp/` or
`paper/build/`. Only aggregate, redacted, content-addressed evidence may be
committed. Raw public identifiers, row-level latent assignments, and matching
witnesses must not be serialized into repository artifacts.
