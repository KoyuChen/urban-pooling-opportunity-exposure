# Weak-MIL geography-equality feature ablation

This is a known-truth synthetic robustness check, not a Chicago estimate. The
locked public-record CSVs, train/test dates, candidate configuration, candidate
graph, regularization, and optimizer settings are unchanged. Only six weak-MIL
features were removed: `pickup_area_same, dropoff_area_same, pickup_tract_same, dropoff_tract_same, same_area_both, same_tract_both`.
The transparent-rule baseline is intentionally unchanged.

## Held-out results

- Candidate graph equality check: **True** (2,640 total
  candidate edges; 1,320 held out).
- Weak-MIL node Brier: **0.005947**; log loss
  **0.047319**; ECE **0.043804**;
  ROC AUC **1.000**; AP **1.000**.
- Hidden true-edge ranking (160 matched endpoints): MRR
  **0.940521**, top-1
  **90.00%**, top-3 **98.12%**.
- AI score-retention 0.90 bound: **[0.2875,
  0.7625]**; truth 0.5625;
  coverage **True**.
- AI score-retention 0.95 bound: **[0.3875,
  0.6875]**; truth 0.5625;
  coverage **True**.

## Circularity assessment

In the locked generator, pickup census tract equals a corridor-specific code
plus the synthetic income bin. Therefore `pickup_tract_same` can mechanically
encode the same-income-bin target; retaining it while narrowing same-income
bounds is circular. Community-area equality is a coarser opportunity proxy, not
an algebraic copy of the target. This ablation removes those exact equalities,
but it is not a complete de-circularization because income bins also generate
fixed spatial coordinate offsets. The score-retention bounds must therefore be
described as model-dependent sensitivity regions. The untrimmed candidate-graph
bounds are score-free, although their estimand remains conditional on spatial
opportunity.
