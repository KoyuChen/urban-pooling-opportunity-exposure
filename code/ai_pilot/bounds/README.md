# Pair-packing exposure bounds

This directory implements the uncertainty-preserving step of the AI pilot. It
does not infer a single "true" co-rider graph from privacy-coarsened records.
Instead, it computes the minimum and maximum SES pairing statistic over every
node-disjoint candidate pairing consistent with the observed match flags.

## Inputs

`set_packing_bounds.py` accepts two CSV files:

- Nodes: `node_id`, an optional 0/1 observed-match column, and either
  `ses_bin` or `ses_value`.
- Candidate edges: `edge_id`, `u`, `v`, and a nonnegative `edge_score`.

For `same_bin`, the bounded statistic is the fraction of selected pairs whose
two SES bins are equal. This is a transparent assortative-pairing share, not
Newman's degree-corrected assortativity coefficient. For `ses_gap`, it is the
mean absolute difference in the supplied SES value. Pass log income as
`ses_value` if proportional rather than dollar gaps are desired.

With `--matched-col`, every node equal to one must have exactly one selected
incident edge; zero-valued nodes are excluded. Without it, all nodes are
matched by default. Candidate edges are pair edges only in this pilot.

## Optimization

For edge indicators \(x_e\), the exact-node constraints are

```text
sum_{e incident to i} x_e = 1       for every observed matched node i
x_e in {0, 1}
```

The lower and upper programs minimize or maximize the sum of edge-level SES
statistics. The number of selected edges is fixed by the node constraints, so
dividing by it gives a sharp mean bound within the supplied candidate graph.

`--score-retention 0.95` adds a sensitivity restriction: total compatibility
score must reach at least 95% of the maximum-score feasible packing. This can
narrow the interval, but it is a model-based plausibility region, not a
frequentist confidence interval and not identified by the public data alone.

SciPy/HiGHS MILP is the default backend. A deterministic exhaustive fallback
handles small graphs and is covered by tests.

## Run

```bash
python urban_pooling_data/ai_pilot/bounds/set_packing_bounds.py \
  --nodes nodes.csv \
  --edges scored_candidate_edges.csv \
  --matched-col shared_trip_match \
  --metric same_bin \
  --score-retention 0.95 \
  --output bounds.json \
  --selected-output extremal_packings.csv
```

Run the known-truth simulation and unit tests with:

```bash
python urban_pooling_data/ai_pilot/bounds/synthetic_validation.py
python -m unittest discover \
  -s urban_pooling_data/ai_pilot/bounds/tests -v
```

Generated validation outputs live in `results/`:

- `synthetic_validation_instances.csv`: one row per replicate and time bin.
- `synthetic_validation_summary.csv` and `.json`: aggregated coverage and
  interval width.
- `synthetic_bounds.png`: ambiguity and bound width as timestamps coarsen.
- `SYNTHETIC_RESULTS.md`: concise, reproducible interpretation.

## Scope and claim discipline

These are bounds over **candidate compatibility packings**. They become bounds
on realized co-rider exposure only if the candidate-generation assumptions are
credible and all true pairs are retained. Chicago's `trips_pooled` field may
also describe a service chain rather than simultaneous occupancy. Accordingly,
the pilot should use "opportunity exposure" or "compatibility pairing" and must
not label a selected edge as an observed rider relationship.
