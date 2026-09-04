# NYC HVFHV claim boundary

## Supported

- Public HVFHV rows expose exact-second pickup/drop-off timestamps, Taxi Zones,
  trip outcomes, and shared-match flags, but no public co-rider or run key in the
  audited schema.
- Conditional on a declared candidate universe and `C in {2,3,4}`, feasible
  worlds are connected positive-overlap interval runs with simultaneous
  occupancy bounded by `C`; sequential membership can exceed `C`.
- The 24-window panel predeclares its windows and applies an outcome-blind
  eligibility screen. It reports 21 eligible and three ineligible windows, with
  zero technical failures and no missing terminal reports.
- Of 126 outcome-capacity cells, 101 have exact endpoint pairs, 125 have
  certified ambiguity at the candidate-median threshold, and one decision is
  unresolved.
- Four feasible deterministic point methods disagree with one another in 24
  cells. Across capacities, 494/498 point decisions occur inside
  certified-ambiguous cells.
- The branch-and-price scale lattice certifies 14/18 integer optima and reports
  valid incumbent/open-node intervals for all four unresolved cells.
- Artificial 15-minute supports, same-zone screens, common-support capacity
  comparisons, and fixed thresholds are explicitly labeled sensitivity or
  reference analyses.

## Not supported

- Actual co-rider, vehicle, or shared-run reconstruction.
- Point-method accuracy or error on public NYC data, because membership truth is
  absent.
- Hidden-run closure or partner recall outside the declared candidate universe.
- Any assertion that a public shared trip had realized pool size or occupancy
  two, three, four, or another value.
- Treating declared `C` as an estimate of a provider's true capacity.
- TLC or provider production matching logic, implementation fidelity, or an
  assertion that artificial 15-minute supports are the actual release operator.
- NYC population prevalence, sampling inference, causal effects, or policy
  effects.

## Interpretation

The strongest current public-data statement is conditional:

> Under the declared candidate, support, and capacity contracts, almost every
> candidate-median outcome cell admits feasible relation completions on both
> sides of the decision threshold, while deterministic feasible point methods
> sometimes choose different sides.

This is a result about relation-dependent aggregate knowledge, not evidence that
any particular latent event world occurred.
