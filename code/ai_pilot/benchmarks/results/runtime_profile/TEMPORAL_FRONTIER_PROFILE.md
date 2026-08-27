# Temporal frontier operational scaling profile

This report is an engineering capacity profile for deterministic synthetic temporal markets. It is kept separate from scientific validation and supports no empirical or identification claim.

## Bounded execution summary

| Item | Value |
|---|---:|
| Suite | quick |
| Cases | 23 |
| Exact solver returned | 22 |
| Frontier limit | 0 |
| Wall-clock timeout | 1 |
| Harness/solver error | 0 |
| Per-case timeout | 3 s |
| Live-frontier limit | 200,000 |
| Worker RSS sampling | 10 ms |

## Schedule-constructor comparison

Each width below is certified for the listed constructor's validated action schedule. The release-aware greedy order and the adjacent order are deterministic heuristics; none of these widths is claimed globally minimum. The timed solve uses the smallest active-record bag among the three candidates, then active factors, with a fixed tie break.

No exact order-search oracle is run in this operational harness. Any small-instance order oracle belongs in a separate correctness audit.

| Case | Input width | Input factors | Adjacent width | Adjacent factors | Release-greedy width | Release-greedy factors | Selected order |
|---|---:|---:|---:|---:|---:|---:|---|
| records_n006 | 3 | 1 | 2 | 1 | 3 | 1 | temporal_adjacent |
| records_n010 | 5 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| records_n014 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| records_n018 | 9 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| degree_d01 | 7 | 1 | 1 | 1 | 1 | 1 | release_aware_greedy |
| degree_d03 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| degree_d05 | 7 | 1 | 4 | 1 | 7 | 1 | temporal_adjacent |
| factors_overlap00 | 7 | 0 | 2 | 0 | 2 | 0 | release_aware_greedy |
| factors_overlap01 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| factors_overlap02 | 7 | 2 | 2 | 2 | 4 | 1 | temporal_adjacent |
| factors_overlap03 | 7 | 3 | 2 | 3 | 4 | 1 | temporal_adjacent |
| labels_d01 | 6 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| labels_d02 | 6 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| labels_d03 | 6 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| labels_d04 | 6 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| score_none | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| score_per_core_2 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| score_per_core_3 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| score_per_core_4 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| gamma_unbounded | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| gamma_0 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| gamma_2 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |
| gamma_4 | 7 | 1 | 2 | 1 | 4 | 1 | temporal_adjacent |

## Case telemetry

`peak_active_records` and `peak_active_factors` are computed from the supplied schedule before the worker starts. Frontier telemetry is unavailable when a worker is stopped mid-solve.

| Case | Axis value | Records | Max degree | Peak active records | Peak active factors | Labels | Floor | Gamma | Status | Peak frontier | Runtime ms | Python heap MiB | Worker RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| records_n006 | 6 | 6 | 3 | 3 | 1 | 2 | 9 | 2 | RESOLVED | 96 | 173.4 | 0.21 | 26.14 |
| records_n010 | 10 | 10 | 3 | 3 | 1 | 2 | 15 | 2 | RESOLVED | 128 | 300.9 | 0.54 | 26.14 |
| records_n014 | 14 | 14 | 3 | 3 | 1 | 2 | 21 | 2 | RESOLVED | 128 | 414.7 | 0.84 | 26.14 |
| records_n018 | 18 | 18 | 3 | 3 | 1 | 2 | 27 | 2 | RESOLVED | 128 | 601.4 | 1.24 | 26.14 |
| degree_d01 | 1 | 14 | 1 | 2 | 1 | 2 | 21 | 2 | RESOLVED | 8 | 132.7 | 0.09 | 26.14 |
| degree_d03 | 3 | 14 | 3 | 3 | 1 | 2 | 21 | 2 | RESOLVED | 128 | 422.2 | 0.84 | 26.14 |
| degree_d05 | 5 | 14 | 5 | 5 | 1 | 2 | 21 | 2 | TIMEOUT | -- | 3003.0 | 2.91 | 30.62 |
| factors_overlap00 | 0 | 14 | 3 | 3 | 0 | 2 | 21 | 2 | RESOLVED | 64 | 270.1 | 0.42 | 26.32 |
| factors_overlap01 | 1 | 14 | 3 | 3 | 1 | 2 | 21 | 2 | RESOLVED | 128 | 415.9 | 0.84 | 26.32 |
| factors_overlap02 | 2 | 14 | 3 | 3 | 2 | 2 | 21 | 2 | RESOLVED | 256 | 620.7 | 1.24 | 26.82 |
| factors_overlap03 | 3 | 14 | 3 | 3 | 3 | 2 | 21 | 2 | RESOLVED | 512 | 744.2 | 1.59 | 26.82 |
| labels_d01 | 1 | 12 | 3 | 3 | 1 | 1 | 18 | 2 | RESOLVED | 8 | 133.3 | 0.13 | 26.82 |
| labels_d02 | 2 | 12 | 3 | 3 | 1 | 2 | 18 | 2 | RESOLVED | 128 | 357.4 | 0.67 | 26.82 |
| labels_d03 | 3 | 12 | 3 | 3 | 1 | 3 | 18 | 2 | RESOLVED | 432 | 902.3 | 1.70 | 26.92 |
| labels_d04 | 4 | 12 | 3 | 3 | 1 | 4 | 18 | 2 | RESOLVED | 1024 | 1970.7 | 2.46 | 28.63 |
| score_none | none | 14 | 3 | 3 | 1 | 2 | -- | 2 | RESOLVED | 128 | 431.9 | 0.84 | 26.82 |
| score_per_core_2 | per_core_2 | 14 | 3 | 3 | 1 | 2 | 14 | 2 | RESOLVED | 128 | 469.0 | 0.84 | 26.82 |
| score_per_core_3 | per_core_3 | 14 | 3 | 3 | 1 | 2 | 21 | 2 | RESOLVED | 128 | 449.7 | 0.84 | 26.82 |
| score_per_core_4 | per_core_4 | 14 | 3 | 3 | 1 | 2 | 28 | 2 | RESOLVED | 128 | 403.5 | 0.84 | 26.82 |
| gamma_unbounded | unbounded | 14 | 3 | 3 | 1 | 2 | 21 | -- | RESOLVED | 272 | 470.1 | 0.99 | 26.82 |
| gamma_0 | 0 | 14 | 3 | 3 | 1 | 2 | 21 | 0 | RESOLVED | 32 | 181.2 | 0.30 | 26.82 |
| gamma_2 | 2 | 14 | 3 | 3 | 1 | 2 | 21 | 2 | RESOLVED | 128 | 394.3 | 0.84 | 26.82 |
| gamma_4 | 4 | 14 | 3 | 3 | 1 | 2 | 21 | 4 | RESOLVED | 240 | 567.9 | 1.22 | 26.82 |

## How to read the profile

The market has one core and one buffer record per synthetic time index. Candidate edges are temporal bands, diagonal edges guarantee feasibility, and off-diagonal edges consume Gamma. Nested privacy factor scopes control factor overlap. The score floor is the integer threshold used by the exact score coordinate.

`schedule_width` in the CSV/JSON is exactly one less than the selected schedule's peak active-record count (with a floor at zero). It describes that supplied record schedule; selecting among three constructors does not establish a globally minimum width.

`peak_python_heap_mib` is traced during the solve. `peak_worker_rss_mib` is a process high-water proxy from child resource usage, augmented by parent sampling when procfs exposes the child. It includes Python startup and imports. Runtime and both memory measures are machine-specific diagnostics, not speed or memory guarantees.

The table's runtime is isolated case wall time, including fresh-worker startup but excluding parent-side schedule compilation. CSV/JSON also retain solver-only wall/CPU time and schedule compilation time.

Status `RESOLVED` means both exact endpoint runs returned (optimal or infeasible as shown by `solver_status` in CSV/JSON). `FRONTIER_LIMIT` and `TIMEOUT` are explicit unresolved outcomes.

## Interpretation boundary

Synthetic operational capacity profile only; it does not validate candidate coverage, observation assumptions, identification, or empirical conclusions. Runtime and memory proxies are machine-specific.

Generator `temporal-frontier-runtime-profile-v2`; Python 3.12.13; platform `Linux-6.18.35-x86_64-with-glibc2.39`.
