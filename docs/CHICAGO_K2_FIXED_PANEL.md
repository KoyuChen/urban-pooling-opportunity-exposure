# Chicago K=2 fixed-panel protocol

The panel is the Cartesian product of eight weekdays from 2026-01-05 through
2026-01-14 and three local start times (08:00, 12:00, 17:30), producing 24
released 15-minute core bins. The rule is fixed before row counts, feasibility,
runtime, or frontier outcomes are inspected. A failed or ineligible window is
reported and never replaced.

Each cohort uses `--core-start`, the boundary-complete public temporal envelope,
the declared radius curve, measured-spatial Gamma, boundary padding at 0 and 15
minutes, and a generic candidate-omission Gamma. The latter counts selected
core incidence through edges excluded at padding zero but admitted by the
complete 15-minute envelope. It includes edges with missing geography and is
therefore distinct from the measured out-of-radius curve.

The workflow stores one fail-closed artifact per cohort and a panel aggregate.
Only endpoints with two replayed optimal MILP solutions are certified. Missing
reports, fixed-core drift, time limits, and resource-cap exclusions retain
separate statuses.

This is a public-data certification panel, not a probability sample, hidden-run
recovery study, partner-recall benchmark, or Chicago population estimate.
