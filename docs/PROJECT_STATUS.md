# Verified project status

Checkpoint: 2026-09-05. Checked-in implementation and experimental evidence are
separate from manuscript claims.

## Current main integration

PR #3 merged as `b38b9e33902b92f8f9e8ac1c59c040c297490dc7`.
The implicit disclosure separator, exact certificate master, regression tests,
controlled audit, scope corrections, and README are now on main, not only on
the former exploration branch. PR CI `33940938983` passed both tests and paper.

The source implementation pin is `07c4ccdd77930b80966a270b3a7f147bba5fa326`.
The final local benchmark used exactly the source SHA-256 values recorded in
`code/ai_pilot/benchmarks/results/selective_disclosure_branch_price/report.json`.
It is a local experiment, not a full GitHub Actions benchmark execution.

## New implementation and actual validation

- Fixed-support implicit branch-and-price supports signed additive row costs,
  event-count objectives, and truthful usage/together/separate facts.
- Rational residual corrections produce valid pricing/master bounds; integer
  witnesses are replayed and exact threshold comparisons do not round away a
  gap. An incomplete separator cannot certify absence from an incumbent alone.
- Exact outer hitting-set search computes curator/ex-post minimum certificates.
- 101 production/regression tests pass locally and the PR test job is green;
  21 tests are new, including 64 random small endpoint comparisons.
- 45/45 mean certificates and 15/15 event-count certificates agree with the
  explicit small oracle. Full-column construction is blocked inside the solver.
- Constructed 16/32-row stress closes 5/6 endpoints under the stated budget.
  The 32-row sequential minimum remains unresolved. Simultaneous stress uses a
  declared deterministic warm start and is not a general scale claim.

## Follow-on experiment: warm-starting the unresolved case

A feasible partition from the 32-row sequential maximum-event solve was reused
as the minimum-event warm start. Both runs used the existing public constructed
rows, not hidden membership truth. The maximum closed at eight events; the
minimum remained unresolved after its separate 10-second budget, but now
retained the valid interval [1,8] rather than having no incumbent. This is a
useful fallback, not improved exact closure. Source hash and timings are in
`code/ai_pilot/benchmarks/results/selective_disclosure_branch_price/WARM_START_FOLLOWUP.json`.

## Earlier exploration, now retained on main

- 9,000 usage-threshold comparisons; 5,954 initially ambiguous; mean ex-post
  minimum decision certificate 1.5574 facts. This is not adaptive query cost.
- 272/300 ambiguous event-count instances after conditioning on complete row
  usage; minimum pair certificate mean 2.0147 facts.
- The older complete-column constraint-generation audit has 900 usage and 90
  pair agreements. Do not relabel these as the new implicit audit's sample size.
- The all-partitions formulas concern an abstract singleton-allowing model or
  a conditional known-buddy-bundle embedding, not unconditioned physical events.
  The enumerator tests one balanced truth representative per K, not every truth.

## Frozen manuscript, unchanged

The paper/evidence baseline remains `10108d088f8b70efc1d8d5c483690e385546ceea`.
It includes NYC 24 windows (21 eligible; 126 outcome-capacity cells), 14/18
closed NYC scale cells, and Chicago run 164 (60 cores, 611 candidates, 50,405
contributors). NYC point-method disagreement is not membership-truth error.
Selective-disclosure source and evidence integration does not mean paper
integration; no manuscript source was changed by PR #3.

## Open work

The next algorithmic bottleneck is the root pricing/certified-bound cost in the
32-row sequential minimum: inspect and improve pricing reuse and intermediate
valid bounds, then measure on a predeclared larger battery, not only one case.
Also open: unknown-support and nonlinear targets, noise-robust audit guarantees,
external real event-membership truth, real sequential-episode truth, and
selective-disclosure manuscript integration.

Earlier conversational claims of committed email-Eu/learned-linkage results are
unsupported by the repository and remain withdrawn. No operational disclosure
availability, cost, privacy guarantee, or city-scale runtime is established.

## Repository and evidence policy

Only unified `ci.yml` and manually dispatched `chicago-live-audits.yml` remain.
Old exploratory commits remain in Git history, not as active one-off workflows.
Preserve source pins, solver statuses, unresolved cases, and the distinction
between a new experiment and a rerun of an old CI check.
