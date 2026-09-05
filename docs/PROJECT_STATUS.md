# Verified project status

Checkpoint: 2026-09-05, pricing acceleration. Implementation/evidence and
manuscript claims remain separate.

## Completed implementation

PR #3 previously integrated the fixed-support implicit disclosure separator
at `b38b9e33902b92f8f9e8ac1c59c040c297490dc7`. The next implementation adds
canonical-core root classes, interruptible reduced-cost bounds, exact rational
objective-lattice tightening, duration/occupancy initial bounds, early replayed
incumbents, batched pricing, sparse dual repair, and certified infeasibility reuse.
No complete-column builder or full-world enumeration is used inside the solver.

The acceleration source SHA-256 is
`f520a5e0d047ae0d6ebe3b3435f8577aed1a1247401cd403622e89ff2bf316f4`.
Mathematical justification is in `docs/DISCLOSURE_PRICING_ACCELERATION.md`.

## New executed evidence

Results: `code/ai_pilot/benchmarks/results/disclosure_pricing_acceleration/`.
All benchmark execution was local, with GitHub source hashes verified; GitHub
CI separately runs tests. Do not call a source-export job a benchmark execution.

- 24 paired constructed endpoints, 5 seconds each: exact closure 5/24 -> 19/24;
  replayed incumbent availability 7/24 -> 24/24; zero closure regressions.
- Pricing LP calls 20,937 -> 9,900 in that run. Single-replicate elapsed times
  are hardware-dependent, not a statistical or universal speedup guarantee.
- The old regular 32-row minimum-event development case now closes at two
  events. Five other minimum-event cells remain unresolved with valid intervals.
- Expanded implicit audit: 180/180 mean and 60/60 event-count certificates
  certified and matching the exact small oracle. This reuses/extends earlier
  seeds; it is not 240 new independent event worlds.
- The 113-test production/regression suite passed before adding one evidence
  consistency check. Twelve new algorithm tests target interruption, lattice,
  sparse exact bounds, role interleaving, and batch/full-scan equivalence.

The constructed grid was declared after tuning on the regular 32-row case and
before the grid run. It is not held-out and not real membership truth.

## Earlier controlled evidence, preserved

9,000 usage-threshold comparisons, 5,954 initially ambiguous, mean minimum
ex-post certificate 1.5574 facts; 272/300 event-count instances ambiguous even
with full usage known. Complete-column constraint generation had 900+90 small
oracle agreements; implicit PR #3 had 45+15. Keep these experiments distinct.
The all-partitions formulas are abstract singleton-allowing or conditional
known-buddy-bundle results, not unconditioned physical-event results.

## Frozen paper and public evidence

Paper baseline remains `10108d088f8b70efc1d8d5c483690e385546ceea`.
NYC: 24 windows, 21 eligible, 126 outcome-capacity cells, 14/18 scale closures.
Chicago: run 164, 60 cores, 611 candidates, 50,405 contributors.
No manuscript source or frozen city result is changed by the pricing work.
The new 19/24 constructed result must not replace the NYC 14/18 result.

## Open work

Per-component ablations and independent larger/separate-seed performance;
the five unresolved constructed minima; unknown support and nonlinear targets;
real event-membership and sequential-episode truth; noise-robust auditing;
selective-disclosure paper integration and literature audit.

Earlier conversational email-Eu/learned-linkage claims remain withdrawn.
No privacy, operational-query availability/cost, or city-scale guarantee exists.
Only unified CI and manual Chicago audits remain active after transfer cleanup.
