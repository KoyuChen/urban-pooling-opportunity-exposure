# NYC outcome-blind temporal geometry census

Status: **HOLD_INCOMPLETE_OR_INCONSISTENT**.

24 declared cells / 20 distinct scan windows. Status counts: `{'GEOMETRY_COMPLETE': 8, 'TRANSPORT_FAILURE': 13, 'INELIGIBLE_NO_QUALIFIED_CORE': 3}`.

| View | Eligible | Complete clique | Core-touching non-clique event available |
|---|---:|---:|---:|
| full | 8 | 0 | 8 |
| small | 8 | 4 | 4 |
| broad_full | 8 | 0 | 8 |
| stress_full | 0 | 0 | 0 |

The small view selects 4+12 using time only, without the earlier outcome-availability filter. Complete-clique cases and all failures remain in WINDOWS.csv and the JSON ledger.

A core-touching induced three-vertex path is a capacity-2 non-clique event column. Its existence does not prove that it extends to a disjoint world covering every core, changes any fixed-q endpoint, or occurred operationally. Four stress cells reuse broad scan periods; rows and cells are not independent population observations.

No miles, duration outcome, fare or pay column is requested. No outcome optimizer is run. Source and code hashes are recorded per window; all reported geometry is relative to newly extracted public snapshots.
