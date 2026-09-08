# NYC fixed-input event-structure audit

Verification: **PASS**.

One new retrospective 4-core/12-buffer extraction; all comparators share exact times, roles and query values.
Buffer selection requires nonmissing miles and seconds. K=2 restricts event membership; C restricts simultaneous occupancy.

Fixed-q endpoint changes: **0/24** comparisons.

| C | Family | Columns | Reachable buffer counts | Maximum |
|---|---|---:|---|---:|
| 2 | ordered | 54 | [0, 2, 4] | 4 |
| 2 | pair | 54 | [0, 2, 4] | 4 |
| 2 | clique | 54 | [0, 2, 4] | 4 |
| 3 | ordered | 394 | [0, 1, 2, 3, 4, 5, 6, 7, 8] | 8 |
| 3 | pair | 54 | [0, 2, 4] | 4 |
| 3 | clique | 394 | [0, 1, 2, 3, 4, 5, 6, 7, 8] | 8 |
| 4 | ordered | 1719 | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] | 12 |
| 4 | pair | 54 | [0, 2, 4] | 4 |
| 4 | clique | 1719 | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] | 12 |

## Equal-count outcome comparisons

Every positive q feasible in all three models is included. Different model-specific maxima are not compared as the same outcome query.

| C | q | Query | Restriction | Ordered interval | Restricted interval | Width decrease |
|---|---:|---|---|---|---|---:|
| 2 | 2 | mean_selected_buffer_miles | pair | [7.189000, 26.844500] | [7.189000, 26.844500] | 0.000000 |
| 2 | 2 | mean_selected_buffer_miles | clique | [7.189000, 26.844500] | [7.189000, 26.844500] | 0.000000 |
| 2 | 2 | mean_selected_buffer_trip_minutes | pair | [42.841667, 88.333333] | [42.841667, 88.333333] | 0.000000 |
| 2 | 2 | mean_selected_buffer_trip_minutes | clique | [42.841667, 88.333333] | [42.841667, 88.333333] | 0.000000 |
| 2 | 4 | mean_selected_buffer_miles | pair | [9.267750, 24.658000] | [9.267750, 24.658000] | 0.000000 |
| 2 | 4 | mean_selected_buffer_miles | clique | [9.267750, 24.658000] | [9.267750, 24.658000] | 0.000000 |
| 2 | 4 | mean_selected_buffer_trip_minutes | pair | [49.950000, 83.600000] | [49.950000, 83.600000] | 0.000000 |
| 2 | 4 | mean_selected_buffer_trip_minutes | clique | [49.950000, 83.600000] | [49.950000, 83.600000] | 0.000000 |
| 3 | 2 | mean_selected_buffer_miles | pair | [7.189000, 26.844500] | [7.189000, 26.844500] | 0.000000 |
| 3 | 2 | mean_selected_buffer_miles | clique | [7.189000, 26.844500] | [7.189000, 26.844500] | 0.000000 |
| 3 | 2 | mean_selected_buffer_trip_minutes | pair | [42.841667, 88.333333] | [42.841667, 88.333333] | 0.000000 |
| 3 | 2 | mean_selected_buffer_trip_minutes | clique | [42.841667, 88.333333] | [42.841667, 88.333333] | 0.000000 |
| 3 | 4 | mean_selected_buffer_miles | pair | [9.267750, 24.658000] | [9.267750, 24.658000] | 0.000000 |
| 3 | 4 | mean_selected_buffer_miles | clique | [9.267750, 24.658000] | [9.267750, 24.658000] | 0.000000 |
| 3 | 4 | mean_selected_buffer_trip_minutes | pair | [49.950000, 83.600000] | [49.950000, 83.600000] | 0.000000 |
| 3 | 4 | mean_selected_buffer_trip_minutes | clique | [49.950000, 83.600000] | [49.950000, 83.600000] | 0.000000 |
| 4 | 2 | mean_selected_buffer_miles | pair | [7.189000, 26.844500] | [7.189000, 26.844500] | 0.000000 |
| 4 | 2 | mean_selected_buffer_miles | clique | [7.189000, 26.844500] | [7.189000, 26.844500] | 0.000000 |
| 4 | 2 | mean_selected_buffer_trip_minutes | pair | [42.841667, 88.333333] | [42.841667, 88.333333] | 0.000000 |
| 4 | 2 | mean_selected_buffer_trip_minutes | clique | [42.841667, 88.333333] | [42.841667, 88.333333] | 0.000000 |
| 4 | 4 | mean_selected_buffer_miles | pair | [9.267750, 24.658000] | [9.267750, 24.658000] | 0.000000 |
| 4 | 4 | mean_selected_buffer_miles | clique | [9.267750, 24.658000] | [9.267750, 24.658000] | 0.000000 |
| 4 | 4 | mean_selected_buffer_trip_minutes | pair | [49.950000, 83.600000] | [49.950000, 83.600000] | 0.000000 |
| 4 | 4 | mean_selected_buffer_trip_minutes | clique | [49.950000, 83.600000] | [49.950000, 83.600000] | 0.000000 |

## Verification and interpretation

The input overlap graph has 120 of 120 possible edges. All-row common overlap is 14.000 seconds.

All event subsets are checked independently by time sweep and overlap connectivity. Every support-count feasibility result and outcome endpoint is cross-checked with a binary column-selection MILP and direct event-witness replay. Endpoints also retain exact rational values and witness hashes in the JSON/CSV records.

A timeout remains an unresolved verification. Public data does not reveal which admissible event grouping is true. Model exclusions are consequences of the restrictions, not evidence of actual sequential vehicle runs or mistakes in methods targeting another model.

The JSON records the protocol, input, source and code hashes. Exact reproduction requires the same private input hash; a changed live source is a new snapshot, not a replay of this result.

This input is a complete interval-overlap clique. Consequently every capacity-feasible ordered event is already a clique: this instance contains no opportunity for a connected non-clique event. Its result does not establish a distinct empirical advantage for ordered events. Pair restrictions can still exclude larger selected-buffer counts, which is a different estimand effect from changing outcomes at fixed q.

## Reproduce

Input SHA-256: `f3a5f2eb30048ff3c9004d1d1978c0ecda1cf4f481ab9b8969f86a7162c1801f`.
Protocol SHA-256: `67e148104cc2e834feebba4663c5c34a02348a94672c6bf8fb8e2ec089cb3920`.

```bash
python code/ai_pilot/data_pipeline/production_audit/run_nyc_structure_audit.py \
  --output-dir tmp/nyc-structure-replay \
  --expected-input-sha256 f3a5f2eb30048ff3c9004d1d1978c0ecda1cf4f481ab9b8969f86a7162c1801f
```

Add `--reuse-input` to replay an already fetched input. Only the `aggregate/` subdirectory is publishable; the row-level input cache must remain in ignored scratch.
