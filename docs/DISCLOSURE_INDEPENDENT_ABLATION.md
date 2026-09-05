# Independent-seed disclosure-pricing ablations

The solver is frozen at `faff620fe2ca867d6861b0ac3e8d0c590589fd80`, SHA-256
`f520a5e0d047ae0d6ebe3b3435f8577aed1a1247401cd403622e89ff2bf316f4`.
Protocol commit `2e70d1663cf6f1d427e6a470274fa5b36297dbf3` precedes performance
evaluation. The runner refuses a different source hash. Reproduction requires
a checkout retaining that solver; it must not silently substitute a newer one.

## Purpose and design

The previous 24-cell grid followed tuning on one of its cases. This experiment
changes seeds, generator, row ordering and some disclosure constraints without
retuning the production implementation. It is still constructed data, not real
membership truth and not an independent third-party replication.

Each station contributes a core interval [s,s+4), a buffer [s+2,s+6), a buffer
[s+4.5,s+8), and one optional distractor. The first three form a positive-overlap
chain of peak occupancy two: the first and last intervals do not overlap.
Station increments, distractor intervals and the ordering of core/buffer rows
are randomized by `Random(seed+100003*n_core)`. These complete feasible reference
worlds generate truthful answers and validate output bounds; they are never
passed as optimizer warm starts. At each tested capacity 2 or 3, q=2*n_core.

The primary grid has 16 endpoint problems (4/8 cores, two capacities, two
seed/fact regimes, and min/max event count). Each of six variants runs twice:
192 local solver invocations. An additional 8 endpoint problems with 12 cores
and 36 buffers run twice with the full solver only. The total is 208 invocations,
not 208 independent worlds. Seed and fact regime are paired, so a fact-regime
effect cannot be separated from a seed effect. Both repeats use identical rows.

All invocations have the same 3-second endpoint budget, 500-node cap and
single-thread numerical libraries; isolated child processes execute sequentially
in a prespecified shuffled order. A 20-second parent limit records technical
failure instead of allowing an unbounded run. Both near-optimal and unresolved
statuses are distinct from exact equality, and every failed invocation remains.

## Why each instrumentation is safe

**No canonical restriction.** Remove only `earlier` from the root oracle's
forbidden-core set. This prices a superset of each least-core class. In the
proof, continue assigning every event to its least core. A valid oracle upper
bound U_r for the larger family also bounds the assigned class, so

    dual_row_term + sum_r min(0, event_offset - U_r)

remains a valid lower bound. The change may weaken the bound or repeat work;
it does not exclude a feasible column. Pool deduplication is unchanged.

**No batches.** Set the existing `pricing_batch` limit to zero, requiring a
complete pricing scan before master reoptimization. No feasibility or bound
arithmetic changes.

**No objective lattice.** Return the rational lower bound without raising it to
the objective coefficient lattice. A lower bound remains valid when tightening
is omitted. Capacity/geometry inequalities are unchanged. This ablation may
change exact versus within-tolerance closure without changing a feasible optimum.

**No early primal heuristic.** Suppress only calls made before a complete
node pricing result. The final restricted integer solve remains. A missing
incumbent is recorded, never replaced by the planted reference.

**No infeasibility cache.** Use an empty non-storing cache. The exact box tests
and rational infeasibility checks execute again; the omitted object only saves
computation. Sparse rational arithmetic and all witness checks remain active.

## Interpretation

These are one-component-removed comparisons conditional on all other components;
interactions are not estimated. Two timing repeats are insufficient for a broad
statistical speedup claim. Min/max counts and easy/hard sizes must be shown
separately. Local timings are not GitHub Actions execution times. A status marked
unresolved with equal rational bounds should be shown explicitly as a reporting
edge case, not silently relabeled in the frozen performance table.

The tests compare all six variants to exhaustive small-world optima, validate
nonclique reference construction, interrupt noncanonical pricing, check exact
bound intersection below floating-point resolution, and fail closed on a changed
source hash. No complete-column builder is allowed during performance solves.

## Commands

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/disclosure_independent_ablation.py --self-test
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/disclosure_independent_ablation.py \
  --output-dir tmp/disclosure-independent
```

This audit does not change any paper source or the frozen NYC 14/18 result.
