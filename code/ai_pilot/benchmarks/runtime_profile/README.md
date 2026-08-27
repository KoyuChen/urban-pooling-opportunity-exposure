# Temporal frontier runtime profile

This directory contains the operational scaling harness for the exact temporal
frontier solver. It is intentionally separate from `path_frontier_benchmark.py`,
which performs correctness and claim checks.

The default quick matrix varies record count, maximum temporal candidate
degree, overlapping privacy-factor scopes, joint-label support, score floor,
and Gamma. Each case runs in a fresh process under a hard timeout and a live
frontier-record limit.

Before timing, the harness constructs and validates three deterministic forget
orders: declared input order, temporal-adjacent order, and a release-aware
greedy order. It reports the exact live-record schedule width and active-factor
count for every resulting schedule, then times the smallest-width candidate
(active factors and a fixed name priority break ties). This comparison is not
an exact order search, and none of the heuristic widths is claimed globally
minimum. No exact small-instance order oracle is run here; such an oracle
belongs in a separate correctness audit.

```bash
python code/ai_pilot/benchmarks/runtime_profile/temporal_frontier_profile.py \
  --suite quick \
  --case-timeout-seconds 3 \
  --max-frontier-records 200000
```

Outputs are written to `benchmarks/results/runtime_profile/` by default. The
CSV is convenient for plotting, the JSON retains run metadata, and the
Markdown file is a compact human-readable report. Timeout and frontier-limit
rows are retained as first-class unresolved outcomes rather than dropped.

The generated workloads and timings are synthetic engineering diagnostics.
They do not test empirical identification, observation assumptions, candidate
coverage, or any scientific conclusion.
