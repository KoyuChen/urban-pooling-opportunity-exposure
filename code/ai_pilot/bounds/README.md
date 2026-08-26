# Hidden-partner endpoint bounds

This directory implements the uncertainty-preserving step of the pilot. It
does not infer one preferred partner graph from privacy-coarsened records.
Instead, it computes attained lower and upper endpoints of a contextual pairing
statistic over every exact cover in a declared candidate graph.

Chicago's official `Shared Trip Match` field means that a customer transaction
actually shared the vehicle with a separately booked transaction at some point.
For a chain-complete `Shared Trip Match = true, Trips Pooled = 2` cohort, the
hidden partner is therefore realized co-presence. The public table does not
publish the partner/group identifier. This interpretation does not extend
pairwise to larger pooled runs.

## Inputs

The legacy-compatible `set_packing_bounds.py` accepts two CSV files:

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
matched by default. Do not remove a matched node merely because its geography
is missing: doing so can leave a feasible but entirely false exact cover.

`structured_matching_bounds.py` is the audited generic interface. It supports:

- distinct signed lower and upper edge objectives;
- independent missing-context envelopes from explicit per-node supports while
  exact-covering all target nodes;
- fixed-design FWL/OLS edge coefficients;
- a `Gamma` sensitivity budget for edges added to a declared supergraph;
- `OPTIMAL`, `NUMERICALLY_OPTIMAL`, `PROVEN_INFEASIBLE`, and `UNRESOLVED`
  states. Only exhaustive fallback optima and structurally proved
  infeasibility are exact certificates; SciPy/HiGHS results are deliberately
  marked numerical because floating-point MILP tolerances can erase small
  objective differences.

Independent missing-bin envelopes require an explicit common `all_bins` set or
per-node `support_col`; they are a correctness repair under Cartesian supports,
not a novel joint model.

`joint_label_matching.py` implements the coupled reference problem for one
categorical label and one count-cell membership per record. It supports core
degree `=1`, buffer degree `<=1`, context-only rows in counts, supplied global
count bounds, ordered per-edge `allowed_label_pairs`, Gamma and score floors,
and complete endpoint witnesses. It rejects buffer--buffer and context edges.
The exhaustive backend returns exact declared-input certificates; HiGHS
results remain numerical.

The legacy City clarification couples pickup-time/tract and dropoff-time/tract
bucket assignments and suppresses both endpoints when either bucket is small.
The NP-hardness theorem in the working paper formalizes one such paired
operator, but the current code does **not** compile that two-endpoint operator.
A production analysis still needs multiple label/cell factors, all rows
contributing to both margins, and confirmation that the historical rule
governs the target release.

## Optimization

For edge indicators \(x_e\), the exact-node constraints are

```text
sum_{e incident to i} x_e = 1       for every observed matched node i
x_e in {0, 1}
```

The lower and upper programs minimize or maximize the sum of edge-level SES
statistics. The number of selected edges is fixed by the node constraints, so
dividing by it gives attained endpoints within the supplied candidate graph.
The displayed interval is the convex hull of attainable scalar values;
interior values need not be attainable by any matching.

`--score-retention 0.95` adds a sensitivity restriction: total compatibility
score must reach at least 95% of the maximum-score feasible packing. This can
narrow the interval, but it is a model-based plausibility region, not a
frequentist confidence interval and not identified by the public data alone.
The raw fractional floor depends on the score origin and is not comparable
across score maps. `normalized_regret_floor` supplies positive-affine
invariance within one fixed graph, but still has no common coverage meaning
without independent calibration.

SciPy/HiGHS MILP is the default production backend and returns numerically
qualified optima. A deterministic exhaustive fallback handles small graphs,
returns exact declared-input optima, and is covered by tests.

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

These are endpoint ranges over **declared hidden-partner matchings**. For the
chain-complete matched two-transaction cohort, they become bounds on the
contextual composition of realized co-presence only if every true partner edge
is present and missing context is handled inside the optimization. They do not
measure platform opportunities, dispatch feasibility, rider income, or all
larger pooled runs. A selected edge remains latent, not observed.
