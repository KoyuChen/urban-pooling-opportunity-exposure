# Reproducibility

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r code/ai_pilot/requirements.txt
```

## Deterministic checks

### Projection-to-frontier theorem audit (September 26)

```bash
python code/ai_pilot/benchmarks/projection_frontier_theory_audit.py \
  --output-dir tmp/projection-frontier-audit
```

The audit enumerates every nested nonempty fixed-cardinality projection family
with at most four buffers. It checks 503,310 exact integer-objective cases
against the exposed-face criterion and constructs a separating additive
objective for all 728 strict inclusions. Outputs are deterministic JSON, CSV,
Markdown, TeX and a hash manifest. This is regression evidence for the proof,
not a proof by enumeration or a public-data effect. It applies only to outcomes
that factor through selected-row incidence; event-count and other
partition-dependent outcomes are excluded.

### Clean-checkout aggregate rehearsal (September 24)

```bash
python scripts/rehearse_submission_artifacts.py \
  --output-dir tmp/submission-rehearsal
python scripts/audit_submission_claims.py
```

The first command reads only repository files, makes no network requests and
runs no optimization. It independently renders all eight manuscript tables
(53 rows, 345 cells), compares every formatted cell to the paper, verifies 34
historical/recovery file pins, and re-renders 17 NYC profile/ledger/non-clique
files including their manifests byte for byte. A new unregistered table, a
missing dependency, a changed pin or a numeric drift fails closed. The second
command includes the same rehearsal in the existing CI claim audit.

The initial clean-checkout exercise discovered two missing machine-readable
inputs. `artifact_rehearsal_20260924/inputs/CONTROLLED_SUMMARY.json` was extracted
from a full rerun of the frozen generator; the final Chicago
`gap_amendment_20260913/followup_report.json` was recovered byte for byte from
artifact `10308489958`, run `34731708395`. The recovery provenance and hashes
are in `artifact_rehearsal_20260924/SOURCE_REPLAY.json`. Neither contains raw
trip or pedestrian records.

To independently repeat the stronger synthetic and Chicago source replay:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/event_frontier_truth_benchmark_scale.py \
  --instances-per-capacity 1000 --base-seed 20260902 \
  --output-dir tmp/rehearsal-controlled
# Download the original sealed artifact ZIP from run 34731708395 separately.
# Do not substitute a fresh live pull or a later checkpoint.
python scripts/rehearse_submission_artifacts.py \
  --controlled-report tmp/rehearsal-controlled/report.json \
  --chicago-zip tmp/chicago-amended.zip \
  --output-dir tmp/submission-source-replay
```

The required ZIP SHA-256 is
`27727eb911ba17941beee9e46f531c37bd594ec898a553e4247befe3fe7b5c1b`.
This mode verifies all 2,121 sealed file pins, reaggregates 90 Chicago
sensitivity files (13,390 endpoint rows), and compares 9,000 freshly computed
synthetic truncation cells. Eight source-replay CSV/Markdown/TeX outputs must
match byte for byte. JSON serialization sorts dictionary keys, so the replay
explicitly restores each published CSV schema before comparing bytes.

**Reproduction levels must not be conflated.** ATR's released aggregate tables
can be rendered offline; its research-use trajectories, annotations and detailed
witnesses are intentionally not bundled and are not independently replayed by
this command. NYC summary/fragment regeneration is not a rerun of row-level
solves. The full Chicago sensitivity replay depends on an external sealed ZIP
whose availability/retention is separate from repository availability. If it
expires, default table checks still work, but source replay must remain blocked
until the identical archive is recovered. Historical runtimes are rendered,
not remeasured. Geometry transport HOLD, computationally unresolved endpoints,
snapshot-consistent reconstruction caveats and the public endpoint null remain
unchanged. No all-raw-inputs-public or city-scale closure claim is made.

### Solver and invariant checks

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

### Outcome-blind non-clique fixed-q diagnostic

The protocol selects only the four previously frozen small views whose
geometry has a core-touching induced path. A live rerun first reproduces the
old projected-row and geometry hashes, stores row-level caches only under the
ignored work directory, and publishes aggregate evidence:

```bash
python \
  code/ai_pilot/data_pipeline/production_audit/run_nyc_nonclique_structure_gate.py \
  --work-dir tmp/nyc-nonclique-structure-gate \
  --output-dir \
    code/ai_pilot/data_pipeline/results/nyc_hvfhv/nonclique_structure_20260923
```

After a transport interruption, add `--resume`; validated completed caches are
reused and only missing windows are fetched. A timeout or interruption remains
unresolved and is never converted to infeasibility.

### Endpoint-attainment mechanism audit

The September 25 audit requires the same four ignored private caches produced
by the outcome-blind non-clique run. It verifies their protocol, geometry and
modeled-input hashes before use, and emits only aggregate counts and witness
hashes:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/data_pipeline/production_audit/audit_nyc_nonclique_endpoint_attainment.py \
  --cache-dir tmp/nyc-nonclique-structure-gate \
  --output-dir \
    code/ai_pilot/data_pipeline/results/nyc_hvfhv/nonclique_endpoint_attainment_20260925
```

The cache directory must contain the four `window-*.private.json` files from
the frozen run. The audit reconstructs complete event columns and counts event
partitions by selected-buffer subset; every reported endpoint is scored with
exact rational arithmetic and its event witness is replayed. It also compares
all projected-world counts and endpoint values against the September 23
aggregate. Run twice, all JSON, CSV, Markdown, TeX and manifest bytes are
identical.

The committed result deliberately cannot reconstruct row-level inputs from its
hashes. Those caches retain public-row payloads and remain git-ignored. Absence
of an identical cache blocks source replay; it must not be replaced by a new
live pull and must not be relabeled infeasible. The aggregate result does not
resolve the geometry census's 13 transport failures or identify true events.

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
