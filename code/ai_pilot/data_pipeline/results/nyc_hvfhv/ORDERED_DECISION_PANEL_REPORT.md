# NYC ordered outcome and decision panel

Panel audit: `PASS`; manuscript gate: `PASS`.

Predeclared windows: **24**; eligible: **21**; ineligible: **3**; unresolved: **0**.
Outcome cells: **126**; exact endpoint pairs: **80.2%**; certified decision ambiguity: **99.2%**.
Point-method decision disagreement: **19.0%** of outcome-capacity cells.

| Core | Outcome | C | Cells | Exact | Ambiguous at candidate median | Baselines disagree | Median width | Width / candidate IQR | Max candidates | Max vars | Max sec. |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | mean_selected_buffer_miles | 2 | 17 | 76.5% | 100.0% | 11.8% | 19.291 | 3.752 | 562 | 21832 | 138.4 |
| 8 | mean_selected_buffer_miles | 3 | 17 | 94.1% | 100.0% | 11.8% | 20.441 | 3.866 | 562 | 21832 | 106.9 |
| 8 | mean_selected_buffer_miles | 4 | 17 | 100.0% | 100.0% | 11.8% | 20.058 | 3.972 | 562 | 21832 | 133.2 |
| 8 | mean_selected_buffer_trip_minutes | 2 | 17 | 82.4% | 100.0% | 35.3% | 60.879 | 3.153 | 562 | 21832 | 154.2 |
| 8 | mean_selected_buffer_trip_minutes | 3 | 17 | 82.4% | 100.0% | 35.3% | 62.657 | 3.161 | 562 | 21832 | 192.9 |
| 8 | mean_selected_buffer_trip_minutes | 4 | 17 | 100.0% | 100.0% | 35.3% | 62.881 | 3.177 | 562 | 21832 | 118.0 |
| 16 | mean_selected_buffer_miles | 2 | 4 | 50.0% | 75.0% | 0.0% | 19.626 | 4.033 | 562 | 43664 | 490.4 |
| 16 | mean_selected_buffer_miles | 3 | 4 | 0.0% | 100.0% | 0.0% | — | — | 562 | 43664 | 481.5 |
| 16 | mean_selected_buffer_miles | 4 | 4 | 50.0% | 100.0% | 0.0% | 17.889 | 4.082 | 562 | 43664 | 396.3 |
| 16 | mean_selected_buffer_trip_minutes | 2 | 4 | 50.0% | 100.0% | 0.0% | 68.202 | 3.131 | 562 | 43664 | 462.9 |
| 16 | mean_selected_buffer_trip_minutes | 3 | 4 | 50.0% | 100.0% | 0.0% | 68.321 | 3.137 | 562 | 43664 | 484.3 |
| 16 | mean_selected_buffer_trip_minutes | 4 | 4 | 50.0% | 100.0% | 0.0% | 68.321 | 3.137 | 562 | 43664 | 483.9 |

## Predeclared ineligible windows

- `jul_weekend_pm_n8`: `no scan window produced an integrity- and cap-qualified core`
- `oct_weekend_am_n8`: `no scan window produced an integrity- and cap-qualified core`
- `oct_weekend_pm_n8`: `no scan window produced an integrity- and cap-qualified core`

A deterministic point method always returns a side of the threshold. The frontier reports whether that side is invariant to every admissible relation completion. No accuracy claim is made on public data because operational memberships are absent.

## Denominator and execution audit

The design predeclared **24** windows; **24** terminal reports were observed. Technical failures: **0**; missing terminal reports: **0**.

## Threshold sensitivity

Candidate quartiles test whether median-threshold ambiguity is mechanical. The 5-mile and 30-minute cutoffs are transparent post-hoc references, not claimed operational policy thresholds. Full grouped sensitivity is stored in `ORDERED_DECISION_THRESHOLD_GROUPS.csv`.
