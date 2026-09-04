# Weakly supervised candidate-edge pilot

This component turns complete-day Chicago authorized-trip CSVs into a sparse
candidate graph and scores its edges without inventing pair labels.

## What the model learns

Each trip is a node with the observed label `shared_trip_match`. Candidate
edges are generated from rounded start/end times, pickup/dropoff centroids,
route direction, duration, and distance compatibility. For edge score
`q_ij`, the model predicts a node match probability with a noisy-OR:

`P(y_i=1) = 1 - product_j(1 - q_ij)`.

The nonlinear basis edge scorer is optimized only against these node labels.
The primary `no_geography_equality` feature set removes all community-area and
census-tract equality indicators and their two interactions. The `full`
feature set is retained only to reproduce the locked synthetic circularity
diagnostic. Neither feature set includes ACS income or another SES outcome.
The transparent comparator uses a fully disclosed weighted time/OD rule with
only an intercept and non-negative scale calibrated on the same node-level
objective. `trips_pooled`, match status, fares, and totals are excluded from
all edge features.

There is **no public edge ground truth**. Consequently:

- the evaluation unit is a held-out trip node, using Brier score, log loss,
  calibration error, ROC AUC, and average precision;
- the script does not report pair accuracy, pair recall, or a recovered
  co-rider graph;
- `scored_candidate_edges.csv.gz` contains compatibility hypotheses for
  constrained set-packing and exposure bounds, not observed co-rider links.

Rounded timestamps/centroids also create many ties. The neighbor search and
degree cap can omit a real counterpart, and this omission rate is not
identifiable from the public release. Downstream results therefore need
threshold/cap sensitivity checks; model scores cannot repair candidate-set
misspecification.

## Usage

Use complete narrow windows, not the existing hash-prefix sample. A true
counterpart is almost surely absent from a 1/256 row sample.

```bash
python code/ai_pilot/model/run_weak_edge_pilot.py \
  --input-glob 'code/ai_pilot/data_pipeline/raw/chicago_authorized_*.csv' \
  --feature-set no_geography_equality \
  --output-dir /tmp/boundpool-complete-day-model
```

With at least two dates, the latest complete date is held out by default. Use
`--test-date YYYY-MM-DD` to choose a holdout. With only one date, the final 20%
of its time range is held out and candidate construction is separated at the
cutoff to prevent graph leakage.

Important candidate controls are:

- `--max-start-delta-min` (default 30)
- `--max-pickup-km` (default 4)
- `--max-dropoff-km` (default 7)
- `--max-candidates-per-node` (default 16)
- `--neighbor-search-k` (default 96)
- `--feature-set no_geography_equality` (required for the primary scientific
  specification; the default `full` setting preserves backward-compatible
  diagnostic runs)

## Outputs

- `node_predictions.csv`: labels and held-out node probabilities
- `node_level_metrics.csv`: node-only evaluation by model and subset
- `test_supported_calibration.csv`: calibration bins for plotting
- `scored_candidate_edges.csv.gz`: physical features and rule/AI edge scores
- `model_coefficients.csv`: reproducible fitted parameters
- `model_card.json`: data/split/candidate audit, convergence, assumptions, and
  the explicit no-edge-truth warning

Dependencies: Python 3.10+, NumPy, pandas, SciPy, and scikit-learn. No GPU,
PyTorch, graph package, rider ID, vehicle ID, or human experiment is required.
