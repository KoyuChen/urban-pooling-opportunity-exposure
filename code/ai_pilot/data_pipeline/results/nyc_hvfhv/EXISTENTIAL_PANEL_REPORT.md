# NYC existential timestamp support panel

Generated UTC: `2026-09-02T07:23:24+00:00`

This is a predeclared purposive audit panel. It is not a probability sample and does not support NYC population prevalence statements.

| Window | C | Exact max buffers | Coarse certified max | Certified gain lower bound | Coarse unresolved counts |
|---|---:|---:|---:|---:|---|
| apr_weekday_pm | 2 | 7 | 8 | 1 | `9;10;11;12` |
| apr_weekday_pm | 3 | 11 | 12 | 1 | `none` |
| apr_weekday_pm | 4 | 12 | 12 | 0 | `none` |
| jan_weekday_am | 2 | 5 | 8 | 3 | `9;10;11;12` |
| jan_weekday_am | 3 | 9 | 12 | 3 | `none` |
| jan_weekday_am | 4 | 12 | 12 | 0 | `none` |
| jan_weekday_pm | 2 | 4 | 8 | 4 | `7;9;10;11;12` |
| jan_weekday_pm | 3 | 8 | 12 | 4 | `none` |
| jan_weekday_pm | 4 | 12 | 12 | 0 | `none` |
| jan_weekend_pm | 2 | 4 | 11 | 7 | `12` |
| jan_weekend_pm | 3 | 8 | 12 | 4 | `10` |
| jan_weekend_pm | 4 | 12 | 12 | 0 | `none` |
| jul_weekday_pm | 2 | 6 | 8 | 2 | `9;10;11;12` |
| jul_weekday_pm | 3 | 10 | 12 | 2 | `none` |
| jul_weekday_pm | 4 | 12 | 12 | 0 | `none` |
| oct_weekday_pm | 2 | 5 | 8 | 3 | `9;10;11;12` |
| oct_weekday_pm | 3 | 9 | 12 | 3 | `none` |
| oct_weekday_pm | 4 | 12 | 12 | 0 | `none` |

## Panel diagnostics

- Complete capacity triplets: **6 / 6**.
- Positive certified support-gain lower bound at C=2: **6** windows.
- Positive certified support-gain lower bound at C=3: **6** windows.
- Artificial coarse C=2 reaches the exact C=3 maximum in **2** complete windows.
- Artificial coarse C=3 reaches the exact C=4 maximum in **6** complete windows.
- Window-capacity cells with unresolved coarse counts: **7**.

Panel audit status: `PASS` with **0** problems.

Every gain is a lower bound based only on certified feasible coarse witnesses. Unresolved counts are not treated as infeasible. The supports are an artificial nearest-15-minute experiment, not the TLC observation operator. No co-rider, run, realized-capacity, or population claim is made.
