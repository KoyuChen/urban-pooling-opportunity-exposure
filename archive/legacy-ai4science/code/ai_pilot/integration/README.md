# Synthetic integration benchmark

This directory contains the known-truth integration layer for the urban
ride-pooling AI pilot. It is entirely **human-experiment-free** and uses only
offline synthetic records with Chicago-like coordinates. No result here is an
estimate about Chicago passengers, real co-riders, individual income,
preference homophily, or echo chambers.

## Model status

The **primary specification** is the 22-feature
no-geography-equality weak-MIL model in
`ablations/no_geography_equality_20260825/`. It removes:

```text
pickup_area_same
dropoff_area_same
pickup_tract_same
dropoff_tract_same
same_area_both
same_tract_both
```

The original 28-feature weak-MIL model run by
`run_integration_benchmark.py` is **diagnostic-only**. In the locked synthetic
bound graph, pickup- and dropoff-tract equality exactly reproduce the
`same_income_bin` edge outcome, so the full feature map is circular for the
same-income bound. The transparent rule is retained as a comparator, not as the
preferred scientific specification. Because that disclosed rule also retains
fixed same-area/tract bonuses, its score-retention bounds are diagnostic only;
its node Brier and ranking remain useful invariant baselines.

The 22-feature model still uses continuous time and spatial-distance features.
Because the synthetic generator gives income bins fixed coordinate offsets,
its score-restricted intervals remain model-dependent sensitivity regions, not
fully SES-blind identification intervals. The untrimmed candidate-graph bound
is the score-free reference.

## Reproduce without overwriting locked outputs

Run from `code/ai_pilot`. The commands below write new artifacts to `/tmp`.

### 1. Diagnostic-only 28-feature benchmark

```bash
python integration/run_integration_benchmark.py \
  --output-dir /tmp/urban_pooling_full_mil_diagnostic
```

This command reads the pre-declared `DESIGN_LOCK.json`, generates two
public-like authorized-trip days, holds out the second day, invokes weak-MIL,
audits candidate recovery against hidden pair truth that was never supplied to
training, and solves the set-packing bounds.

### 2. Primary 22-feature no-geography-equality benchmark

```bash
python integration/ablations/no_geography_equality_20260825/run_ablation.py \
  --output-dir /tmp/urban_pooling_no_equality_primary
```

The ablation reuses the locked synthetic CSVs, split, candidate thresholds,
regularization, and optimizer settings. It verifies that the 2,640-edge
candidate graph is identical before changing only the weak-MIL feature matrix.
Hidden income bins and pair IDs are read only after fitting for evaluation.

### 3. Revised paper figure

```bash
python integration/ablations/no_geography_equality_20260825/make_revised_benchmark_figure.py \
  --output /tmp/benchmark_summary_revised.png
```

## Locked synthetic results

| Metric | Transparent rule | 28-feature MIL (diagnostic) | **22-feature MIL (primary)** |
|---|---:|---:|---:|
| Held-out node Brier ↓ | 0.060481 | 0.005131 | **0.005947** |
| Brier improvement vs rule | — | 91.5% | **90.2%** |
| Hidden true-edge MRR ↑ | 0.7815 | 0.7753 | **0.9405** |
| Hidden true-edge Top-1 ↑ | 67.5% | 64.4% | **90.0%** |
| Hidden true-edge Top-3 ↑ | 85.6% | 90.0% | **98.1%** |

The held-out candidate graph recalls all 80 hidden true pairs. Ranking metrics
use 160 matched endpoints and are conditional on candidate recall.

For the primary model, the hidden same-income-bin truth is 0.5625:

| Score-retention set | Primary interval | Width reduction vs untrimmed | Covers truth | Hidden true packing score-eligible |
|---|---:|---:|---:|---:|
| Untrimmed graph | [0.0500, 0.7750] | — | yes | not applicable |
| `\(\rho=.90\)` | **[0.2875, 0.7625]** | **34.5%** | **yes** | **yes** |
| `\(\rho=.95\)` | **[0.3875, 0.6875]** | **58.6%** | **yes** | **yes** |

The hidden true packing attains 0.9964999 of the primary model's optimal score.
By contrast, the diagnostic 28-feature model gives [0.6125, 0.7750] at
`\(\rho=.95\)`, excludes truth, and makes the true packing score-ineligible.

## Go/No-Go

- **GO, synthetic method validation:** primary node Brier improves 90.2%; true
  candidate recall is 100%; both primary score-retention intervals shrink by
  more than 25%, cover truth, and retain the true packing.
- **DIAGNOSTIC ONLY:** the 28-feature model is preserved to document
  target-aligned geography-feature circularity; it must not supply the headline
  bound.
- **HOLD, Chicago empirical claims:** complete-day City data have not been
  obtained in this environment. The available 1/256 trip-ID-prefix sample
  destroys most latent groups and supports only a schema/mechanics check.
- **NOT IDENTIFIED:** public records do not reveal actual co-rider IDs or
  individual income. Never interpret a high-scoring edge as an observed pair,
  and never describe these synthetic bounds as a Chicago estimate.

See `../AI_PILOT_REPORT.md` for the full audit, metrics, limitations, and
updated research gates.
