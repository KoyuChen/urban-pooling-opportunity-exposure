# Reproducibility

## Deterministic CI-equivalent checks

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r code/ai_pilot/requirements-ci.txt

python -m py_compile \
  code/ai_pilot/data_pipeline/production_audit/live_chicago_release_operator_audit_partitioned.py
python \
  code/ai_pilot/data_pipeline/production_audit/live_chicago_k2_frontier_boundary.py \
  --self-test

python -m unittest discover -s code/ai_pilot/bounds/tests -v
python -m unittest discover -s code/ai_pilot/data_pipeline/tests -v
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
python -m unittest discover -s code/ai_pilot/external_benchmarks/tests -v
python -m unittest discover \
  -s code/ai_pilot/benchmarks/runtime_profile -p 'test_*.py' -v
python adversarial_review/counterexamples.py
```

## Paper

```bash
./scripts/build_paper.sh
./scripts/check_submission_pdf.sh \
  paper/build/KDD_Research_Working_Draft.pdf
```

The local build directory is ignored. The `ci` workflow uploads the authoritative
compiled PDF artifact.

## Chicago live release audit

```bash
python \
  code/ai_pilot/data_pipeline/production_audit/live_chicago_release_operator_audit_partitioned.py \
  --output-dir tmp/chicago-release-operator-audit \
  --core-start 2026-01-13T17:30:00 \
  --page-size 500 \
  --max-candidate-rows 5000 \
  --max-contributor-rows 100000 \
  --request-timeout 90 \
  --request-attempts 4 \
  --solver-time-limit 60
```

The command is also available through the manually dispatched
`chicago-live-audits` workflow. Use a Socrata app token when available.

## Chicago K=2 boundary and support curves

```bash
python \
  code/ai_pilot/data_pipeline/production_audit/live_chicago_k2_frontier_boundary.py \
  --output-dir tmp/chicago-k2-frontier-boundary \
  --scan-start 2026-01-13T17:00:00 \
  --scan-end 2026-01-13T21:00:00 \
  --min-core-rows 12 \
  --max-core-rows 60 \
  --max-candidate-rows 5000 \
  --page-size 100 \
  --request-timeout 90 \
  --request-attempts 3 \
  --base-radius-km 2 \
  --solver-time-limit 60 \
  --boundary-padding-minutes 0,5,10,15,30
```

## Frozen NYC panels

The exact YAML used for the 24-window decision panel, fixed-support audits,
coarsening/capacity studies, column generation, and branch-and-price scale runs
is retained under `archive/workflows/` with a `.disabled` suffix. Restore a
workflow only for an explicit rerun with the same estimand; do not launch those
panels on ordinary paper commits.

All public-data outputs must remain aggregate and redacted. Do not commit raw
rows, trip IDs, partner assignments, event columns, or latent timestamps.
