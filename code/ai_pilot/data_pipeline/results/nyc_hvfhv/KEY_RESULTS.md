# NYC HVFHV current evidence

Frozen evidence integrated on 2026-09-04.

## Exact-second decision panel

The design predeclares 24 windows: 20 eight-core windows across seasons,
dayparts, and weekday/weekend regimes, plus four 16-core weekday-evening stress
windows. All 24 return terminal reports. Twenty-one are scientifically eligible;
three are ineligible under the outcome-blind integrity/cap screen; technical
failures and missing reports are zero.

| Quantity | Result |
|---|---:|
| Outcome-capacity cells | 126 |
| Exact endpoint pairs | 101 (80.2%) |
| Candidate-median certified ambiguous | 125 (99.2%) |
| Candidate-median unresolved | 1 |
| Cells where four point methods disagree | 24 (19.0%) |
| Capacity-indexed point decisions | 498 |
| Point decisions inside ambiguous cells | 494 (99.2%) |

The point-method statistic is disagreement among feasible deterministic point
summaries. It is not an accuracy estimate: public NYC rows contain no event
membership truth.

## Branch-and-price scale lattice

The predeclared lattice contains six sizes and three capacities, from 4 core +
12 buffer rows through 16 core + 48 buffer rows. All nine cells through 8+24
close exactly. Overall, 14/18 integer optima are certified. The four open cells
retain valid intervals:

- 10+30, `C=4`: `[27,30]`;
- 12+36, `C=4`: `[32,36]`;
- 16+48, `C=3`: `[43,44]`;
- 16+48, `C=4`: `[45,48]`.

No timeout is converted to optimality or infeasibility.

## Supporting public diagnostics

The current manuscript also retains:

- May 2026 candidate multiplicity on a fixed 200-row cohort;
- a 38-core/399-buffer exact-second versus artificial 15-minute coarsening
  comparison; and
- a common-support capacity comparison at 72 selected buffers.

These are fixed-cohort feasible-world diagnostics, not population or partner
recovery estimates.

## Pins

Exact workflow, artifact, and SHA-256 pins are in the repository-level
`ARTIFACT_MANIFEST.md`. Machine-readable panel and scale summaries are stored in
this directory.
