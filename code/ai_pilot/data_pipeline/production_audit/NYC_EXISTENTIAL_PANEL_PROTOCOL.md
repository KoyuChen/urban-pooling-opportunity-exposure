# NYC existential timestamp support: predeclared audit panel

## Purpose

The single-cohort Gate shows that artificial timestamp uncertainty can expand
the feasible selected-buffer support in a way that resembles a capacity
relaxation. This panel asks whether that geometry recurs across several
predeclared time regimes. It is a replication audit, not a population design.

## Frozen panel

Each cell uses four core rows and the twelve nearest complete buffer rows under
the same outcome-blind temporal selection rule. Capacities `C=2,3,4` are run on
the same selected cohort. The six scan windows are fixed before observing their
support frontiers:

| Label | Scan interval |
|---|---|
| `jan_weekday_am` | 2023-01-03 06:00--10:00 |
| `jan_weekday_pm` | 2023-01-03 17:00--21:00 |
| `jan_weekend_pm` | 2023-01-07 18:00--22:00 |
| `apr_weekday_pm` | 2023-04-04 17:00--21:00 |
| `jul_weekday_pm` | 2023-07-05 17:00--21:00 |
| `oct_weekday_pm` | 2023-10-03 17:00--21:00 |

Within a scan interval, the existing fail-closed extractor chooses the first
one-hour subwindow containing a provider-by-15-minute core within the declared
row caps. No trip outcome value is used to rank candidate buffers.

## Cell estimands

For every window and capacity, the exact fixed-time column master enumerates all
reachable selected-buffer counts. The artificial nearest-15-minute support model
then tests every count using existential latent timestamp completion.

The reported coarse maximum is only the largest count with a certified feasible
witness. If larger counts are unresolved, the difference from the exact maximum
is a **certified support-gain lower bound**, not the sharp gain.

## Panel diagnostics

The primary descriptive diagnostics are:

1. the number of windows with a positive certified support-gain lower bound at
   `C=2` and `C=3`;
2. whether artificial coarse `C=2` reaches the exact `C=3` maximum;
3. whether artificial coarse `C=3` reaches the exact `C=4` maximum; and
4. the unresolved-cell count.

The aggregator verifies cohort identity across capacities, exact capacity
nesting, support containment, and the absence of a certified coarse-capacity
contradiction.

## Claim boundary

The panel is purposive and tiny. It does not estimate a NYC frequency or causal
effect. The nearest-15-minute supports are artificial and are not attributed to
TLC. No actual co-rider, vehicle run, production matching rule, or realized
capacity is reconstructed. Unresolved counts are never classified as
infeasible.
