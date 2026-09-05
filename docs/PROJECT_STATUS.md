# Verified project status

Checkpoint: 2026-09-05, independent-seed ablations completed. This document
separates implemented code, executed experiments and manuscript claims.

## Current implementation

Implicit fixed-support disclosure branch-and-price and ex-post certificate
search were integrated through PR #3. Pricing acceleration was merged at
`faff620fe2ca867d6861b0ac3e8d0c590589fd80`, solver SHA-256
`f520a5e0d047ae0d6ebe3b3435f8577aed1a1247401cd403622e89ff2bf316f4`.
This audit leaves that production solver unchanged.

## New independent-seed audit

Protocol `2e70d1663cf6f1d427e6a470274fa5b36297dbf3` was committed before
performance evaluation. New seeded, role-permuted sequential chains are used,
not the older development grid. Evidence lives in
`code/ai_pilot/benchmarks/results/disclosure_independent_ablation/`.

- 208 local invocations: 192 primary and 16 stress, covering 24 endpoint
  problems from six seeded row sets. Two timing repeats are not new worlds.
- Full solver: 24/32 primary exact statuses and 32/32 replayed incumbents.
- No batching: 19/32 exact statuses and 22/32 incumbents.
- No lattice: 22/32 exact statuses; no early primal: 28/32 incumbents.
- No canonical restriction and no cache: 24/32 exact statuses each; no clear
  component improvement is established for either on this grid.
- 48-row stress: 6/16 exact statuses and 16/16 incumbents. All larger minima
  remain open: full solver closes 0/8 minimum runs at 32 rows and 0/8 at 48.
- Two no-canonical runs have rational lower=upper=2 but TIME_LIMIT status.
  They remain visible in raw records; secondary bound-equality count is 26/32.
- Zero technical failures; every incumbent independently replayed; rational
  intervals have nonempty intersections across common inputs.
- All six instrumented variants pass 54 small exact-oracle comparisons.

The record checker reconstructs counts, exact intervals and summary from all
208 compact records. These are local runs, not execution of the timing grid
on GitHub Actions. Eight new regression/evidence checks are included in the
unified CI test discovery. Source export is only transport, not an experiment.

## Previous evidence, not relabeled as new

The 24-cell pricing-development comparison had 5/24 -> 19/24 closures and
7/24 -> 24/24 incumbents. It was tuned, single-replicate and constructed.
The expanded implicit certificate audit had 180 mean and 60 event-count
agreements with the small exact oracle. The initial implicit audit had 45+15;
the older complete-column comparison had 900+90. Do not mix these denominators.

Earlier ex-post disclosure experiments retain 9,000 usage-threshold comparisons,
5,954 ambiguous cells and mean minimum certificate 1.5574 facts. This is not
adaptive query cost. Full usage leaves 272/300 event-count instances ambiguous.
All-partitions formulas concern the abstract singleton-allowing model or a
conditional known-buddy-bundle embedding, not unconditioned physical events.

## Frozen manuscript and public data

Paper baseline remains `10108d088f8b70efc1d8d5c483690e385546ceea`.
NYC: 24 windows, 21 eligible, 126 cells and 14/18 scale closures.
Chicago: run 164, 60 cores, 611 candidates, 50,405 contributors.
No new independent-ablation result replaces these figures. Selective-disclosure
implementation/evidence is in the repository, not yet integrated into the paper.
Earlier conversational email-Eu and learned-linkage claims remain withdrawn.

## Next scientific bottlenecks

Minimum-event lower bounds and feasible solutions on new larger sequential
instances remain weak. Canonical pricing is not uniformly better in this audit;
future tuning needs a separate evaluation set. Correct the conservative timeout
labeling separately, without changing this frozen experiment. Also open are
unknown support, nonlinear objectives, noisy-answer guarantees, real membership
and sequential-episode truth, literature audit and manuscript integration.

No city-scale, privacy, or operational query-availability/cost guarantee is
established. Only unified CI and manual Chicago audits should remain active.
