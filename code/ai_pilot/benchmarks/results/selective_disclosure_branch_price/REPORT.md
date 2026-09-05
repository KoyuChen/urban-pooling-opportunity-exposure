# Implicit disclosure branch-and-price audit

Run date: 2026-09-05. Source: `07c4ccdd77930b80966a270b3a7f147bba5fa326`.
Execution was local, with the two source blobs checked against GitHub; this is
not described as a GitHub Actions benchmark run. Source SHA-256, environment,
seeds, counts, and constructed stress endpoints are in `report.json`.

## Certificate comparison

| Target | Cells | Minimum certificates certified | Exact agreement | Unresolved |
|---|---:|---:|---:|---:|
| Selected-member mean | 45 | 45 | 45 | 0 |
| Event count | 15 | 15 | 15 | 0 |

These are new implicit branch-and-price comparisons, not the older complete-column
900+90 audit. They use 5 independent seeds per capacity at C=2,3,4. The complete
column builder is patched to raise during every separator/certificate call.
Known full usage is conditioned on for the event-count target. Certificate size
is curator/ex-post information, not the cost of an adaptive acquisition policy.

## Constructed stress, fixed support

| Instance | Capacity | q | Minimum event count | Maximum event count |
|---|---:|---:|---|---|
| Simultaneous, 8 core + 24 buffer | 4 | 16 | 6, closed | 8, closed |
| Sequential turnover, 4 core + 12 buffer | 2 | 8 | 2, closed | 4, closed |
| Sequential turnover, 8 core + 24 buffer | 2 | 16 | unresolved | 8, closed |

Five of six endpoints close under the declared 10-second per-endpoint budget.
For the unresolved minimum, the individual solve returns only a lower bound of
1 and no incumbent before timeout. Do not convert that into infeasibility.
The simultaneous special case uses a deterministic clique warm start; its
maximum closes against a direct bound without processing a branch node. It is
not evidence of general 32-row scalability.

The existing production test suite plus 21 new tests passes 101 tests locally.
The new tests include 64 independent random endpoint comparisons, actual
fractional-master branching, exact threshold ties, inconsistent facts, absent
optional endpoints, no-singleton/nonclique semantics, and interrupted-node bounds.

## Reproduce

```bash
python -m unittest discover -s code/ai_pilot/data_pipeline/production_audit/tests -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python \
  code/ai_pilot/benchmarks/selective_disclosure_branch_price_audit.py \
  --instances-per-capacity 5 --stress --output-dir tmp/disclosure-bp-audit
```

The runner writes complete cell-level metrics as well as the summary. Runtime
and time-limited stress closure depend on hardware. The frozen NYC 14/18 scale
result and all Chicago/NYC manuscript numbers are unchanged.
