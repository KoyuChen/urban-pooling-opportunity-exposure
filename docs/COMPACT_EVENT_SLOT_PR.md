# Compact event-slot probe integration

This integration adds a certified necessary-condition probe for the difficult
minimum-event endpoint on fixed-support sequential event worlds.

## Safety contract

- The compact labeled-slot LP contains every feasible at-most-K event world.
- A lower bound is raised only after an always-feasible phase-I problem yields a
  strictly positive lower bound under exact rational dual-residual repair.
- Compact MIP failure never proves infeasibility.
- A compact MIP solution is accepted only after replay under the original
  ordered-event semantics.
- The probe is restricted to pure minimum-event objectives and medium/larger
  instances; small certificate calls do not pay the extra cost.

## Frozen evaluation

The protocol was committed before the timed run. The same frozen solver was
run with the probe enabled and disabled on new-seed sequential nonclique
instances. All replicate-level records, exact rational bounds, timings and
work counters are committed under
`code/ai_pilot/benchmarks/results/compact_event_slot_audit/`.

`DEFAULT_DECISION.json` applies a predeclared conservative rule: default enable
only when there is no exact-status or incumbent loss and at least one exact-
status or strict-lower-bound gain. Otherwise the implementation remains opt-in.
Negative and mixed outcomes are retained.

## Boundaries

This is synthetic fixed-support evidence. It does not change the manuscript,
NYC 14/18 scale lattice, Chicago audit, real-event truth status, noise-robust
claims, privacy claims or operational query-cost claims.
