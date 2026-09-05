# Canonical-root pricing and interruptible certified bounds

This note documents the 2026-09-05 implementation change. It is not a claim
that canonicalization, Lagrangian bounds, or objective-lattice rounding are
individually new mathematical ideas. The aggregate paired experiment does not
identify a separate performance contribution for each component.

## Disjoint root classes

Assign each event to its smallest core position. To price root r, forbid all
smaller core positions and propagate the existing together/separate facts.
This partitions rather than truncates the full event-column family. In every
feasible master, the mass of columns assigned to r is at most one because
every such column uses core r, whose total usage is one.

Let d be the dual row contribution and rho_r a valid lower bound on reduced
cost among columns assigned to r. For any feasible master solution,

    objective >= d + sum_r min(0, rho_r).

Indeed, expand the objective into dual contributions and reduced costs.
Nonpositive duals on optional-usage upper bounds lower-bound those row
contributions. Every root-class mass belongs to [0,1], so its reduced-cost
contribution is at least min(0,rho_r). Sum over the disjoint classes. No dual
optimality is needed. In phase one the bound concerns the zero objective on
physical columns, allowing positive certified lower bounds to prove infeasibility.

## Partial pricing scans

Before a root class is solved, bound its pricing value by a box relaxation:
include forced rows, exclude forbidden rows, and include every remaining
positive weight. Together/separate propagation tightens this relaxation.
Its negative, with the event-cost offset, is a valid reduced-cost lower bound.
Once a root finishes, use the residual-repaired interval-LP bound instead.
The strongest phase-two bound already established survives interruptions.
A batch of new negative-cost columns can trigger reoptimization before a
complete scan. A partial scan alone never establishes full-master LP closure.

## Exact objective lattice

If g is the rational gcd of all row and event objective coefficients, every
integer world's objective belongs to g Z. Thus any valid rational lower bound
L can be tightened to g ceil(L/g), using exact rational arithmetic. This is an
integer bound, not necessarily a fractional-master bound. It never rounds a
floating-point gap across a threshold. For an identically zero objective, zero
is a valid conditional lower bound.

## Geometric lower bound

One event's summed member durations cannot exceed C times the entire candidate
time horizon. Let M be the largest number of globally shortest candidate
durations fitting that envelope. Every event then has at most M members, so
n_core+q selected rows need at least ceil((n_core+q)/M) events. Mandatory peak
occupancy gives another lower bound ceil(peak/C). These are outer relaxations;
capacity is not treated as total membership in a sequential event.

## Implementation safeguards

Sparse exact dual evaluation omits zero multipliers. Infeasible span/box cases
are cached only after the existing exact box precheck or rational slack
certificate, independently of pricing weights. Zero-artificial restricted
solutions skip redundant phase-one pricing but do not certify an endpoint.
Early restricted integer heuristics are replayed independently and retained
on timeout. Zero budgets and incomplete pricing remain fail-closed.

The 12 new regression tests cover interrupted pricing prefixes, early-primal
retention, canonical roots with interleaved roles, signed/fractional objectives,
exact threshold distinctions, batch/full scans, and objective-independent
infeasibility caching. The old interruption test now uses a three-row nonclique
chain because the previous trivial instance legitimately no longer called the
injected pricing routine.

## Evidence and limits

See `code/ai_pilot/benchmarks/results/disclosure_pricing_acceleration/REPORT.md`.
The paired grid was declared after tuning on the prior 32-row regular case,
not as an independent held-out benchmark. Broader real-data performance,
per-component ablations, unknown support, noisy answers, and paper integration
remain open. The frozen NYC 14/18 scale result is unchanged.
