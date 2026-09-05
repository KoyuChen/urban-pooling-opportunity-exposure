# Disclosure pricing acceleration: local paired audit

Date: 2026-09-05. Baseline: `23963d5dfb6600a20bf63a773a410ac200bf711b`.
The tested separator SHA-256 is
`f520a5e0d047ae0d6ebe3b3435f8577aed1a1247401cd403622e89ff2bf316f4`.
This is a local benchmark, not a full benchmark executed by GitHub Actions.
GitHub independently reruns the regression suite. Full-record hashes and
execution details are in `SUMMARY.json`; all paired endpoints and certificate
sizes are retained in the adjacent CSV files. Relation witnesses are omitted.

## Paired constructed grid

Two turnover shapes (regular and deterministic jitter), 4/6/8 cores with three
times as many buffers, capacities 2/3, fixed support q=2*n_core, and both
minimum/maximum event-count objectives give 24 endpoint cells. Baseline and
accelerated implementations receive the same inputs, one thread, a 5-second
per-endpoint budget, and 500-node cap. Run ordering alternates. No external
warm start is supplied; each implementation keeps its internal heuristics.

| Metric | Baseline | Accelerated |
|---|---:|---:|
| Exact endpoint closure | 5/24 | 19/24 |
| Replayed incumbent available | 7/24 | 24/24 |
| Bounded unresolved | 19 | 5 |
| Technical failures | 0 | 0 |
| Median elapsed seconds | 5.0024 | 0.5055 |
| Total elapsed seconds | 108.3437 | 43.2405 |
| Pricing LP calls | 20,937 | 9,900 |

There are 14 closure gains and no closure regressions in this one paired run.
All returned partitions passed independent core/support/connectivity/capacity
and objective replay. The complete-column builder was blocked during solves.
`event_cost=-1` means minimizing negative event count; negate and reverse its
reported objective bounds when interpreting maximum event count.

The five accelerated open cells are all minimum-event objectives:

| Shape | Core + buffer | C | Valid interval |
|---|---|---:|---|
| Regular | 6 + 18 | 3 | [2,3] |
| Regular | 8 + 24 | 3 | [2,4] |
| Jittered | 6 + 18 | 3 | [2,3] |
| Jittered | 8 + 24 | 2 | [2,3] |
| Jittered | 8 + 24 | 3 | [1,2] |

The previous development case (regular 8+24, C=2, q=16) now closes its minimum
at 2 events, without an external warm start: about 3.85 seconds in the diagnostic
run and 4.12 seconds in the paired grid. Baseline diagnostic execution used its
10-second budget without obtaining an incumbent. This case informed the changes
and must not be described as held-out. The full grid was fixed after that tuning
and before the paired run. Timings are hardware-dependent, single-replicate,
and can exceed the nominal budget slightly while returning certificates.

## Expanded implicit-certificate audit

The existing `selective_disclosure_branch_price_audit.py` was rerun with
20 seeds per capacity at C=2,3,4 and the exact rational threshold comparator.

| Target | Cells | Certified minimum | Exact oracle agreement | Unresolved |
|---|---:|---:|---:|---:|
| Member mean | 180 | 180 | 180 | 0 |
| Event count | 60 | 60 | 60 | 0 |

The complete-column builder is blocked inside every separator/certificate call;
explicit enumeration is used only by the independent small comparator. Each
row of `CERTIFICATE_COUNTS.csv` contains the four target certificate sizes for
one seed. These are curator/ex-post certificates, not adaptive acquisition
costs. This is an expanded rerun of the prior design, not 240 independent
worlds and not 240 extra disjoint cases beyond the earlier 60-cell audit.

The production suite passed 113 tests before the additional frozen-evidence
consistency check. Twelve algorithm regression tests are new.

## Reproduce

```bash
git worktree add --detach tmp/disclosure-baseline 23963d5dfb6600a20bf63a773a410ac200bf711b
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/disclosure_pricing_comparison.py \
  --baseline-root tmp/disclosure-baseline --output-dir tmp/pricing-comparison
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/selective_disclosure_branch_price_audit.py \
  --instances-per-capacity 20 --output-dir tmp/disclosure-certificates
python -m unittest discover -s code/ai_pilot/data_pipeline/production_audit/tests -v
```

The paired run used the initial local harness; the committed portable wrapper
was consolidated afterward with the same generator, limits, import isolation,
and replay logic. Full original logs and harness accompany the evidence bundle.

## Claim boundary

The joint implementation improves this declared constructed grid. No component
ablation, universal speedup, real membership truth, noisy-audit guarantee,
unknown-support guarantee, city-scale runtime, or operational query cost is
established. The paper and frozen Chicago/NYC results are unchanged, including
14/18 exact NYC scale closures.
