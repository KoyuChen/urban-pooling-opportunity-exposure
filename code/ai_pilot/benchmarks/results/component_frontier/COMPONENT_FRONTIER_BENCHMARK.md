# Exact incidence-component frontier benchmark

This is an **algorithm-engineering** result. It applies standard exact
constraint decomposition followed by a knapsack-style, pseudo-polynomial
resource convolution. It is not claimed as new relative to generic component
decomposition, dynamic programming, or knapsack convolution, and it carries no
empirical or identification implication.

## Exact condition and proof

Construct the joint incidence graph whose vertices are records and declared
count/release factors. Candidate edges join their two endpoint records. A
record is joined to every factor that any supported label can contribute to or
can require as `LOW`/`HIGH`. Only connected components of this joint graph are
split. A shared factor therefore remains one object and forces all records in
its scope into the same component.

**Proposition.** Under the declared `ExactPathProblem` semantics, let
`C_1,...,C_k` be those incidence components. The component solver returns the
same exact feasibility status and attained query endpoints as the monolithic
temporal-frontier solver for any supplied forget order, global `Gamma`, and
global additive score floor, unless either solver explicitly raises its
declared frontier limit.

**Proof.** Every matching edge, degree constraint, label restriction, count
bound, and release requirement lies in exactly one incidence component. Thus a
global structurally feasible world restricts uniquely to one feasible local
world per component, and the union of arbitrary feasible local worlds is a
global structurally feasible world. Omitted-edge use, per-core-incidence score,
and query value are additive across that bijection. The convolution retains
the nondominated triples `(gamma used, shifted score, query)`. A triple with no
more Gamma use, no less score, and no worse query can replace a dominated
triple under every remaining component; induction proves the pruning exact.
The single global score shift is valid because every core has degree one, so it
adds the same constant once per core. Finally, local witnesses are unioned and
replayed against the original unsplit problem, so both endpoints are attained.

## Why candidate-graph components alone are wrong

The locked two-record counterexample has no candidate edge, so its candidate
graph has two singleton components. One record chooses whether to contribute
zero or one to a shared release factor. The other chooses a `LOW` or `HIGH`
release label; `LOW` requires count zero and `HIGH` requires count one. Its
query contribution is 0 under `LOW` and 10 under `HIGH`, while the count source
contributes query 1 when its count is one. The true attained interval is
`[0, 11]`.
Naively duplicating and checking the factor inside the two candidate-graph
components makes `HIGH` locally impossible and reports the false upper endpoint
1. The joint incidence graph correctly has 1 component.

## Locked same-kernel cross-check

- Generator: `component-frontier-benchmark-v2`; seed `20260827`.
- Random problems: 20; each is solved at all
  8 locked `(Gamma, score floor)`
  combinations.
- Exact endpoint agreements: **160/160**
  (109 feasible;
  51 infeasible).
- Replayed monolithic/decomposed endpoint witnesses:
  **436**.
- Canonical evidence SHA-256: `1402bc2b3218cc6ea9b426fda1c02bef0e9432e7186ba50ffd190e626e839cc0`. This projection
  excludes Python/platform labels and all runtime columns, but retains every
  generator, status, endpoint, width, state-count, and witness-audit field.

These 160 comparisons are regression cross-checks, not independent-oracle
evidence: the two solvers intentionally share validated preparation and local
transition primitives. Every comparison uses exact `Fraction` endpoints.
Witness replay recomputes all labels, matching degrees, allowed label pairs,
factor counts, release requirements, Gamma use, raw score, and additive query
from the original problem.

## Independent exhaustive-oracle battery

The second battery compares the decomposed solver directly with raw label and
matching enumeration that imports no temporal-frontier state or transition
recurrence.

- Generator seed: `20260828`; random problems:
  24.
- Exact oracle agreements: **192/192**
  (123 feasible;
  69 infeasible).
- Enumeration work: 279,936 label
  assignments, 81,856 complete
  matching leaves, and 31,114 feasible
  worlds across resource configurations.
- Replayed decomposed endpoint witnesses:
  **246**.

## Interleaved-component operational profile

The deterministic family has disconnected four-core cycles. It reports both
the supplied time order interleaved across components and a legal monolithic
baseline whose order concatenates complete components. Each local and
concatenated schedule has width two; only the interleaved monolithic schedule
accumulates live records from several components. The score floor and Gamma
budget are global and bind how many components use their high-score matching.
The live-frontier limit is 10,000.

| Components | Records | Interleaved width | Interleaved max | Concatenated width | Concatenated max | Max local width | Decomposed max | Terminal total | Endpoints |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 2 | 8 | 4 | 6 | 2 | 5 | 2 | 3 | 4 | [1, 2] |
| 4 | 16 | 8 | 24 | 2 | 8 | 2 | 3 | 8 | [3, 7] |
| 6 | 24 | 12 | 88 | 2 | 8 | 2 | 3 | 12 | [3, 11] |
| 8 | 32 | 16 | 374 | 2 | 11 | 2 | 4 | 16 | [6, 21] |
| 10 | 40 | 20 | 1524 | 2 | 14 | 2 | 5 | 20 | [10, 34] |
| 12 | 48 | 24 | 5778 | 2 | 14 | 2 | 5 | 24 | [10, 42] |
| 13 | 52 | 26 | 12183 | 2 | 17 | 2 | 6 | 26 | [15, 55] |

Every `max` column is the largest number of records in any **single** live
frontier, not a memory peak. `Terminal total` sums the component-terminal
frontier records retained before convolution. Records contain variable-sized
complete witnesses, so neither count is a heap/RSS estimate.

| Components | Interleaved status | Interleaved ms | Concatenated status | Concatenated ms | Decomposed status | Decomposed ms |
|---:|:---|---:|:---|---:|:---|---:|
| 2 | EXACT_OPTIMAL | 1.0 | EXACT_OPTIMAL | 1.0 | EXACT_OPTIMAL | 1.1 |
| 4 | EXACT_OPTIMAL | 5.5 | EXACT_OPTIMAL | 2.4 | EXACT_OPTIMAL | 2.3 |
| 6 | EXACT_OPTIMAL | 17.7 | EXACT_OPTIMAL | 4.2 | EXACT_OPTIMAL | 4.1 |
| 8 | EXACT_OPTIMAL | 94.8 | EXACT_OPTIMAL | 7.1 | EXACT_OPTIMAL | 4.6 |
| 10 | EXACT_OPTIMAL | 556.1 | EXACT_OPTIMAL | 13.0 | EXACT_OPTIMAL | 6.4 |
| 12 | EXACT_OPTIMAL | 2305.8 | EXACT_OPTIMAL | 13.9 | EXACT_OPTIMAL | 6.7 |
| 13 | FRONTIER_LIMIT | 601.4 | EXACT_OPTIMAL | 17.6 | EXACT_OPTIMAL | 7.6 |

Runtime is one machine-local Python run and is diagnostic only. The exact state
counters, width, status, and endpoints are the reproducible evidence. A
`FRONTIER_LIMIT` row is not an infeasibility or approximate answer.
The concatenated baseline shows that a caller who is free to reorder complete
components can recover much of the same structural benefit in the monolithic
solver. The component layer automates that safe separation and makes the
global resource convolution explicit; the table is not evidence of a universal
speedup over the best possible monolithic order.

## Boundary and maintenance contract

This layer does not help a single joint incidence component. Local work remains
exponential in component path width and label support. The global convolution
is pseudo-polynomial in the capped integer score target and Gamma and can itself
be the bottleneck; this is not a removal of the score-resource hardness. The
implementation is pinned to `path_frontier_dp-internal-layout-2026-08-27` and checks
selected reused callable/dataclass layouts before solving. Selected layout
drift therefore fails explicitly; semantic changes with the same layout still
require the same-kernel and independent-oracle tests above.
