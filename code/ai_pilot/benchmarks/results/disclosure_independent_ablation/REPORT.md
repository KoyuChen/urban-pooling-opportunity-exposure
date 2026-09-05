# Independent-seed disclosure-pricing audit

Executed locally on 2026-09-05, using frozen solver commit
`faff620fe2ca867d6861b0ac3e8d0c590589fd80`. Protocol commit
`2e70d1663cf6f1d427e6a470274fa5b36297dbf3` preceded performance evaluation;
runner commit `847b0e867be9346abd8adc645d6bc80958d8aab3` is byte-verified.
No production solver was tuned or changed after looking at these results.
This is not a GitHub Actions benchmark execution or real membership truth.

## Design and complete accounting

Six seeded candidate row sets produce 24 min/max endpoint problems across
capacities 2 and 3. The primary 16/32-row stratum has 16 endpoint problems,
each run twice with six solver variants (192 invocations). The 48-row stress
stratum has eight endpoint problems, run twice with the full solver (16 more).
All 208 invocations finished without a technical failure. Repeats are timing
replicates, not independent worlds. Seed and disclosure regime are paired,
so their separate effects are not identified. Each solve has a declared
3-second budget; stopping is cooperative, not an exact wall-clock cutoff.

Reference triples are connected through positive overlap but are not cliques.
Their maximum simultaneous occupancy is two. Planted worlds are used only to
construct truthful answers and validate bounds, never as solver warm starts.
Every returned incumbent was independently replayed. Exact rational intervals
intersect for every common input across variants/repeats. No full-column
builder is allowed inside an experimental solve. These checks are not a
substitute for mathematical validity of the bounds on nonenumerated cases.

## Primary results: 32 replicate runs per variant

| Variant | Exact status | Replayed incumbent | Median seconds | Pricing LP calls |
|---|---:|---:|---:|---:|
| Full | 24/32 | 32/32 | 0.396 | 10,367 |
| No canonical restriction | 24/32 | 32/32 | 0.454 | 10,551 |
| No batch reoptimization | 19/32 | 22/32 | 2.469 | 17,210 |
| No objective-lattice tightening | 22/32 | 32/32 | 0.409 | 11,414 |
| No early primal heuristic | 24/32 | 28/32 | 0.366 | 11,932 |
| No infeasibility cache | 24/32 | 32/32 | 0.391 | 9,722 |

The numbers are frozen raw statuses, including two conservative reporting
mismatches described below. Time-censored calls and two repeats do not justify
a universal or statistically established speedup claim. Omitting a component
measures its effect conditional on the other components, not interactions.

Batching has the clearest benefit on this grid: disabling it loses five exact
status closures and ten incumbents relative to the full solver. Early primal
search preserves four additional incumbents but does not improve the closure
count here. Lattice tightening adds two closures. This grid does not establish
a benefit from caching or canonical restriction; disabling the latter even
finds equal rational bounds on a minimum the full solver leaves open.

## Full solver: difficulty is not uniform

Each entry below is four distinct endpoint problems, with two repeats each.

| Candidate rows | Minimum event count closed | Maximum event count closed | Incumbents |
|---|---:|---:|---:|
| 16 | 8/8 | 8/8 | 16/16 |
| 32 | 0/8 | 8/8 | 16/16 |
| 48 | 0/8 | 6/8 | 16/16 |

The 48-row stress closes 6/16 replicate runs, all maximum-event problems.
The eight minimum runs retain intervals [2,9], [2,7], [1,5] or [1,6]. The two
open maximum runs retain a maximum-count interval [11,12]. A feasible output
on every full-solver run is useful, but none of the 32/48-row minima closes
under this budget. The old tuned 32-row success did not generalize uniformly.

## Conservative status mismatches, not rewritten results

RUNS rows 16 and 27 are both no-canonical solves for 8 cores, capacity 2,
seed 730019, mixed facts, minimum count. They report TIME_LIMIT and
BOUNDED_UNRESOLVED even though their exact rational lower and upper bounds
are both 2. Independent incumbent replay passes. Therefore the secondary
bound-equality count for no-canonical is 26/32, versus its raw-status 24/32.
This discrepancy is a conservative labeling issue, not a false certificate.
The frozen solver and primary table have not been changed to hide it.

## Reproduction and provenance

`SUMMARY.json` records protocol, exact hashes, environment and stratification.
`RUNS.json` stores all 208 endpoint records, statuses, exact bounds, timings,
node/pricing counts and input hashes compactly, without relation witnesses.
The original detailed local report SHA-256 is
`980fb4ba0f42b19f2966cd53f9095044cfee39f06c50dff4285350cc3eebaf70`.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/disclosure_independent_ablation.py --self-test
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/disclosure_independent_ablation.py \
  --output-dir tmp/disclosure-independent
python code/ai_pilot/benchmarks/check_disclosure_independent_evidence.py
```

The audit requires the pinned solver, protocol and runner; it fails closed on
source drift. All six variants pass 54 tiny exact-oracle comparisons, including
signed rational objectives. Regression tests also check interruption, zero
budgets and exact interval contradictions below floating-point resolution.
GitHub CI replays tests and committed-record consistency, not the timing grid.

No paper source, Chicago result or NYC 14/18 scale result changes. Unknown
support, nonlinear targets, noisy audit answers, real sequential membership
truth and manuscript integration remain open.
