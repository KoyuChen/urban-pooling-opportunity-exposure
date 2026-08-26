# Admissible Sets for Opportunity Exposure in Privacy-Coarsened Ride-Pooling Records — AI pilot

This folder contains a fully offline, human-experiment-free pilot for learning
and bounding latent ride-pooling compatibility structure when the public data
release omits group identifiers.

## What is implemented

1. `data_pipeline/` requests complete Chicago authorized-trip days and refuses
   partial downloads.  Complete slices are mandatory because the earlier
   one-prefix sample almost always omits the other trip in a pooled chain.
2. `model/` builds a sparse time–OD candidate graph and learns compatibility scores
   from node-level `shared_trip_match` labels with a noisy-OR multiple-instance
   likelihood.  It compares against a disclosed-rule baseline on held-out
   days and never creates public-data pair labels.
3. `bounds/` uses binary exact-cover optimization to minimize and maximize SES
   pairing statistics over the declared admissible set of feasible pairings.
   It does not select a reconstructed co-rider graph as the scientific result.
   A score-retention option gives a clearly labeled model-based sensitivity
   region.
4. `integration/` is a known-truth end-to-end benchmark. It keeps latent pair
   IDs outside training, includes unmatched authorized trips, and checks both
   weak-supervision prediction and exposure-bound coverage. The production
   specification is the 22-feature no-geography-equality ablation; the locked
   28-feature run is retained only as a target-leakage diagnostic.

The methodological contract and allowed claims are in
`METHOD_CONTRACT.md`.  The consolidated measured result is in
`AI_PILOT_REPORT.md`.

## Current execution status

The code and synthetic validation run in this workspace.  The City of Chicago
API is blocked by the workspace's egress policy, so no complete-day file is
fabricated or inferred.  `data_pipeline/ACCESS_BLOCKER.md` records the exact
diagnostics and the one-command rerun.  The existing 1/256 real sample is used
only for schema and mechanics checks; its output is explicitly labeled as
non-substantive.

## Minimal rerun

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

Dependencies are limited to NumPy, pandas, SciPy, scikit-learn, and Matplotlib.
No GPU, rider ID, vehicle ID, private platform data, human recruitment, or
human-subject experiment is required.
