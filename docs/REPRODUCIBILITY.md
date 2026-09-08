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
python \
  code/ai_pilot/data_pipeline/production_audit/live_chicago_k2_frontier_indexed_count.py \
  --self-test
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
python code/ai_pilot/data_pipeline/production_audit/run_chicago_k2_fixed_panel.py \
  --self-test
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

## Frozen NYC artifacts

The integrated summaries are:

```text
code/ai_pilot/data_pipeline/results/nyc_hvfhv/
  ORDERED_DECISION_PANEL_REPORT.md
  ORDERED_DECISION_PANEL_SUMMARY.json
  ORDERED_DECISION_PANEL_GROUPS.csv
  ORDERED_DECISION_THRESHOLD_GROUPS.csv
  BRANCH_AND_PRICE_SCALE_REPORT.md
  BRANCH_AND_PRICE_SCALE_CELLS.csv
  BRANCH_AND_PRICE_SCALE_MANIFEST.json
```

The original panel artifact is `9903823780` from run `33760441027`; the original
scale artifact is `9897266899` from run `33837187046`. Hashes and claim licenses
are recorded in `ARTIFACT_MANIFEST.md`. Expensive frozen NYC workflows are not
run on ordinary commits.

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

The integrated run-164 report is under
`code/ai_pilot/data_pipeline/results/chicago_release_operator_audit/`.

## Chicago K=2 boundary audit

```bash
./scripts/run_chicago_k2_boundary_local.sh
```

Live jobs are also available through the manually dispatched
`chicago-live-audits` workflow. All outputs belong in ignored directories such
as `tmp/`; do not commit raw rows, identifiers, event columns, reconstructed
partners, or latent timestamps.

For a predeclared fixed-panel window whose wide `count(*)` request times out,
the transport-equivalent bounded-ID reconciliation is:

```bash
python code/ai_pilot/data_pipeline/production_audit/run_chicago_k2_fixed_panel.py \
  --window-index 12 \
  --indexed-count-transport \
  --output-dir tmp/chicago-k2-indexed-retry
```

Use a fresh output directory and merge the terminal record through
`resume_chicago_k2_fixed_panel.py`; do not overwrite the prior failed attempt.

## ATR DIAMOR annotated-relation audits

Obtain DIAMOR-1 and DIAMOR-2 directly from the ATR repository under its
research-use terms. Raw trajectories, labels, row identifiers, and detailed
witnesses must remain outside the repository. The aggregate cross-day audits
can be reproduced with:

```bash
python code/ai_pilot/benchmarks/atr_diamor_support_calibration.py \
  --pilot-trajectory /path/to/person_DIAMOR-1_all.csv \
  --pilot-groups /path/to/groups_DIAMOR-1.dat \
  --followup-trajectory /path/to/person_DIAMOR-2_all.csv \
  --followup-groups /path/to/groups_DIAMOR-2.dat \
  --output /ignored/path/support-calibration

python code/ai_pilot/benchmarks/atr_diamor_density_cap.py \
  --pilot-trajectory /path/to/person_DIAMOR-1_all.csv \
  --pilot-groups /path/to/groups_DIAMOR-1.dat \
  --followup-trajectory /path/to/person_DIAMOR-2_all.csv \
  --followup-groups /path/to/groups_DIAMOR-2.dat \
  --output /ignored/path/density-cap

python code/ai_pilot/benchmarks/atr_diamor_alternating_structure.py \
  --trajectory /path/to/person_DIAMOR-2_all.csv \
  --groups /path/to/groups_DIAMOR-2.dat \
  --output /ignored/path/alternating-structure
```

The committed `SUMMARY.json` files intentionally omit snapshot-level cells.
Their tests verify code, protocol, and upstream-summary hashes as well as the
frozen aggregate counts. Detailed local `report.json` files must not be
committed because they retain snapshot offsets and endpoint witnesses.
