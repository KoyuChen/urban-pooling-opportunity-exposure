# KDD method build and legacy Chicago AI pilot

This folder contains both the current certified hidden-relation method and the
earlier weak-node-score Chicago pilot. The two must not be conflated. Current
KDD evidence lives in `bounds/`, `benchmarks/`, `external_benchmarks/`, and the
snapshot-aware parts of `data_pipeline/`; `model/` and the original
`integration/` runs are retained as failure-analysis provenance.

## What is implemented

1. `bounds/` provides exact and numerical joint matching--label endpoints, the
   exact temporal frontier, explicit-DNF release compilation, certified score
   relaxation, exact incidence-component convolution, and matching-level
   calibration.
2. `benchmarks/` provides exhaustive correctness checks, controlled conformal
   stress tests, and a bounded operational profile. Timeout is unresolved, not
   infeasibility.
3. `external_benchmarks/` reconciles all ten pinned UCI edge blocks, reports
   their nonmatching relation topology and a truth-conditioned exact upper /
   unresolved lower dyad result, and retains a synthetic FEBRL4 method-fit
   audit without committing raw external rows or truth links.
4. `data_pipeline/` fingerprints the public Socrata revision, provides a
   fail-closed declared Chicago compiler handoff, and audits synthetic `K=2`
   production contracts. These interfaces do not prove a live extraction is
   run closed or that true partner edges are covered.
5. `model/` and `integration/` retain the earlier noisy-OR/weak-node-score
   experiment. Node labels do not identify partner edges; those runs are not
   the current learning claim.

The current methodological contract is in the repository-level
`KDD_RESEARCH_PIVOT.md`; legacy claims and diagnostics remain documented in
`METHOD_CONTRACT.md` and `AI_PILOT_REPORT.md`.

## Current execution status

The 150 declared-input tests and external cached-data audit run in this
workspace. Hosted CI executes 149 cache-independent tests and records one
expected skip when the official UCI cache is absent.
The City API remains blocked to the local runtime, so no complete-day Chicago
file is fabricated or inferred. `data_pipeline/ACCESS_BLOCKER.md` records the
diagnostics, snapshot contract, and rerun command. The existing 1/256 real
sample remains schema/mechanics evidence only.

## Legacy rerun (not the KDD headline)

```bash
# 1. In an environment that can reach data.cityofchicago.org
python code/ai_pilot/data_pipeline/fetch_complete_authorized_days.py

# 2. Train on the verified complete-day files
python code/ai_pilot/model/run_weak_edge_pilot.py \
  --input-glob 'code/ai_pilot/data_pipeline/raw/chicago_authorized_*.csv' \
  --feature-set no_geography_equality \
  --output-dir /tmp/boundpool-complete-days

# 3. Validate the exact-cover solver
python code/ai_pilot/bounds/synthetic_validation.py \
  --output-dir /tmp/boundpool-solver-check

# 4. Run the locked diagnostic benchmark
python code/ai_pilot/integration/run_integration_benchmark.py \
  --output-dir /tmp/boundpool-full-diagnostic

# 5. Run the primary no-geography-equality specification
python code/ai_pilot/integration/ablations/no_geography_equality_20260825/run_ablation.py \
  --locked-result-dir code/ai_pilot/integration/results \
  --output-dir /tmp/boundpool-no-geography-equality
```

Core dependencies are NumPy, pandas, SciPy, scikit-learn, Matplotlib, the
pinned Record Linkage Toolkit, and the pinned Rustworkx Blossom backend used by
the external benchmark.
No GPU, rider ID, vehicle ID, private platform data, human recruitment, or
human-subject experiment is required.
