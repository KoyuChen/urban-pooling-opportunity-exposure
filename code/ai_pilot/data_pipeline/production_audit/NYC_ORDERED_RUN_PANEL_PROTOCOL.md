# Predeclared NYC ordered-run scale panel

## Purpose

The single-window NYC audit is an integrity and formulation smoke test. It is
not a sufficient empirical panel for a KDD paper. This protocol expands the
public-data evidence without changing the estimand or pretending that public
HVFHV rows reveal actual co-riders or vehicle runs.

The panel asks a narrower question at scale:

> Across predeclared seasonal and day-part cells, how wide is the feasible
> normalized run-count frontier under connected interval runs and declared
> simultaneous capacities C in {2,3,4}, and how often can its endpoints be
> certified at larger model sizes?

## Frozen panel

The workflow contains 24 deterministic cells.

### Broad tier: 20 cells

For January, April, July, and October 2023, use five blocks per season:

1. weekday morning, 06:00--10:00;
2. weekday midday, 11:00--15:00;
3. weekday evening, 17:00--21:00;
4. weekend morning, 09:00--13:00;
5. weekend evening, 18:00--22:00.

Each broad cell uses an ordered core of 8 public rows.

### Stress tier: 4 cells

Reuse the four seasonal weekday-evening scan blocks with an ordered core of 16
public rows. These are nested computational stress cells, not additional
independent observations.

## Deterministic extraction

Within each declared four-hour block, the shared extraction code scans one-hour
windows in chronological order. It accepts the first count- and integrity-
qualified hour and then orders provider/15-minute groups by group size,
calendar time, and provider code. The ordered core is the first requested number
of core rows under the frozen public sort. The candidate universe is the full
count-reconciled determinate universe returned by the declared temporal support
screen. Outcome values do not enter window, provider, core, or candidate
selection.

Every cell snapshots the NYC Open Data metadata before and after extraction,
reconciles server counts after extraction, and emits no raw rows or identifiers.
The aggregate job requires a common release fingerprint across the panel.

## Fixed estimand and solver contract

The broad panel uses exact public seconds only. Artificial time coarsening is
kept in the separate lattice experiment so that sample expansion is not
confounded with a changed observation operator.

For each cell and C in {2,3,4}, solve the minimum and maximum normalized number
of connected interval runs. Capacity bounds simultaneous occupancy, not total
run membership. Minimum-index canonical roots remove label symmetry.

A cell is called certified only when both integer endpoints close. When a time
or numerical limit intervenes, the workflow records:

- the primal feasible endpoint values, when available;
- the global MIP dual bounds;
- the resulting outer enclosure for the unidentified frontier;
- an inner range witnessed by feasible integer solutions.

Open endpoints are never reported as exact identified intervals.

## Predeclared summaries

The aggregate report will show:

1. completed and fully certified window counts;
2. certification rates by core size and capacity;
3. median exact frontier width among certified cells;
4. median rigorous outer width across all cells;
5. capacity-nesting audits for exact endpoints and open bound intervals;
6. sharpness of the peak-occupancy analytic lower bound;
7. variables, binary variables, constraints, and runtime by scale tier;
8. ordered-core and candidate-row **appearances**, explicitly not deduplicated
   people, vehicles, or runs.

The broad tier is considered computationally closed for manuscript use if at
least 80% of its capacity cells certify and every remaining cell has a finite,
noncontradictory outer enclosure. The stress tier is diagnostic: unresolved
cells remain useful as an empirical tractability frontier and are not relabeled
as failures of identification.

## Claim boundary

This panel supports descriptive statements about conditional feasible-world
geometry and computational certification on predeclared public-data cells. It
does not identify actual partners, actual pooled trips, realized vehicle/run
membership, realized pool size, true platform capacity, TLC production matching
logic, population prevalence, or causal effects. Stress cells can reuse source
rows from broad cells, so panel-cell row appearances are not a unique-rider
sample size.
