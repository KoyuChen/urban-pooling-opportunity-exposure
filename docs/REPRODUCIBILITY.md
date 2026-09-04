# Reproducibility

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r code/ai_pilot/requirements.txt
```

## Deterministic checks

```bash
python -m py_compile \
  code/ai_pilot/data_pipeline/production_audit/live_chicago_release_operator_audit_partitioned.py
python \
  code/ai_pilot/data_pipeline/production_audit/live_chicago_k2_frontier_boundary.py \
  --self-test
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
python code/ai_pilot/benchmarks/event_frontier_truth_benchmark_scale.py \
  --self-test
```

## Paper

```bash
./scripts/build_paper.sh
./scripts/check_submission_pdf.sh \
  paper/build/KDD_Research_Working_Draft.pdf
```

The local build directory is ignored. CI uploads the compiled PDF instead of
committing generated binaries.

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

## Chicago K=2 boundary audit

```bash
./scripts/run_chicago_k2_boundary_local.sh
```

Live jobs are also available through the manually dispatched
`chicago-live-audits` workflow. All outputs belong in ignored directories such
as `tmp/`; do not commit raw rows, identifiers, event columns, reconstructed
partners, or latent timestamps.
