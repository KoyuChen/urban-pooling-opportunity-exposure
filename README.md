# Certified Temporal Frontiers for Hidden Relations

KDD Research-oriented working repository for certified aggregate inference when
a public release suppresses relation keys and coarsens endpoint attributes.
Chicago ride pooling is the flagship application; it is not treated as a
substitute for general method validation.

> **Status:** research build, not submission ready. The exact temporal-frontier
> solver, explicit-DNF release compiler, certified score relaxation,
> matching-level conformal safety layer, incidence-component convolution,
> all-ten-block external topology audit, and fail-closed Chicago adapter and
> production-audit interfaces are implemented. The UCI upper dyad endpoint is
> exact but its lower endpoint is unresolved. City implementation validation,
> a stabilized run-closed full-day schedule, candidate-support evidence, and
> complete Chicago endpoints remain hard gates.

## Method target

The release may preserve one row per transaction but remove the key joining
rows into events. Fine endpoint attributes may also be suppressed through
global privacy counts. We therefore optimize a query over **joint feasible
worlds** consisting of:

1. a hidden matching that covers every core record once and may use optional
   boundary-buffer records;
2. one latent endpoint attribute from each record's declared support;
3. global count and release constraints imposed by the verified observation
   operator; and
4. an optional, separately audited candidate-miss and learned-score
   restriction.

The output is a pair of attained aggregate endpoints and their witness worlds,
not one asserted relation graph. The scalar interval between the endpoints is
the convex hull of attainable values and need not itself be fully attainable.

## Learning layer

An edge scorer is a tightening device, not an identified partner probability.
For a feasible matching (M), the implementation uses normalized score regret

\[
R_s(M)=\frac{S_{\max}-S(M)}{S_{\max}-S_{\min}},
\]

which is invariant to positive affine score transformations. A split-conformal
order statistic is calibrated on independent markets with observed true
matchings. Its retention guarantee requires exchangeable augmented markets and
almost-sure membership of the true full world in the frozen reference set. At
a smaller final `Gamma`, a separate full-world eligibility error `alpha_G`
yields query coverage `1-alpha_S-alpha_G`. Synthetic calibration does not
transfer to Chicago; without independent Chicago-like partner truth, learned
restrictions remain sensitivity analyses.

The score extrema used for normalization are computed once on a predeclared
ambient candidate-omission budget and frozen across the complete `Gamma` path.
All edge contributions are rationalized before summation, and the exact
conformal floor is passed to the exact solver without another float round trip.
Recomputing the score range at each `Gamma` can make otherwise nested
restrictions non-nested.

## Exact temporal-frontier algorithm

Given a record forget order, the compiler processes every edge while both
endpoints are live and opens each count factor only from its first possible
contributor or requirement through its last. A state contains live compiled
labels, matching bits, sparse active `(capped_count, LOW/HIGH)` factors, one
global `Gamma` coordinate, and an integer score capped at the floor. For live
record width `w`, compiled support `d`, at most `r` active threshold factors of
cap `k`, omission budget `Gamma`, and score target `b`, the key bound is

\[
(2d)^w[3(k+1)]^r(\Gamma+1)(b+1).
\]

The solver returns exact attained endpoints and independently replayed witness
worlds. The dependence on `b` is pseudo-polynomial: the two-resource endpoint
decision is weakly NP-complete even on disjoint four-cycles of pathwidth two.
For a rational granularity \(\eta\), the optional outward relaxation certifies

\[
\mathcal F_B\subseteq\widehat{\mathcal F}_\eta
\subseteq\mathcal F_{B-\eta|C|}.
\]

It controls score slack, not query error, and is not described as a query
FPTAS.

`release_operator_compiler.py` accepts provenance-bearing explicit DNF clauses
over LOW/HIGH count-factor outcomes. It creates one compiled label per
substantive-label/clause pair, lifts every pair-dependent map, audits event and
factor lifecycles, and restores the selected clause from a projected solver
witness. Projection is exact, but the compiler is polynomial only in the
explicit DNF and lifted output; it does not validate the cited external rule.

## Exact component convolution

Safe decomposition uses the joint record--release-factor incidence graph, not
candidate-graph components. Candidate edges join their endpoint records, and a
record joins every factor that any supported label can contribute to or
require. Shared release factors therefore merge otherwise disconnected
candidate subgraphs. Each component is solved exactly, then its nondominated
omission, globally shifted score, and query records are convolved under the
single global `Gamma` budget and score floor.

This layer is standard exact constraint decomposition plus
pseudo-polynomial knapsack-style Pareto convolution. It is algorithm
engineering, not a standalone novelty or a universal speedup. Its locked audit
has 160/160 same-kernel agreements, 192/192 independent exhaustive-oracle
agreements, and 682 replayed decomposed endpoint witnesses. A shared-factor
counterexample shows why candidate-graph-only splitting is invalid: it reports
an upper endpoint of 1 when the correct joint-incidence endpoint is 11.

## Current controlled benchmark

The deterministic benchmark separates source, calibration, and held-out test
markets. Source scorers are directly supervised by true edges; no node-label
learner is evaluated. Source homophily has generating probability 95%, while
calibration and test use 55%. This deliberately shifts a query-leaking
diagnostic that sees the same-SES edge contribution defining the downstream
statistic.

Across 120 held-out test markets at nominal 90% matching-set coverage:

| Scorer | Calibrated true-matching retention | Downstream coverage | Mean width reduction | Arbitrary tight-radius retention | Arbitrary downstream coverage | Arbitrary width reduction |
|---|---:|---:|---:|---:|---:|---:|
| Target-free | 95.8% | 100% | 3.8% | 30.0% | 83.3% | 70.6% |
| Query-leaking diagnostic | 97.5% | 100% | 7.6% | 15.0% | 24.2% | 95.8% |

The query-leaking stress model appears much sharper at the illustrative radius
0.05 precisely because it removes truth. Calibration exposes the cost:
coverage returns, but most apparent precision disappears. These are
single-seed, six-pair synthetic implementation results. They are not Chicago
estimates, a weak-supervision validation, a coupled-attribute benchmark, or
evidence that exchangeability holds in another domain.

## External relation-truth boundary

The all-ten-block UCI Krebsregister audit reconciles 5,749,132 unique candidate
pairs and 20,931 adjudicated positives over 99,788 observed records. Its truth
is not a matching: 8,675 records have positive degree above one, maximum degree
is eight, and the 12,925 positive entity components have size up to nine. The
ten files are heavily overlapping edge partitions, not independent markets or
folds; 82,846 records occur in every block.

A disclosed truth-conditioned reduction retains 10,297 global two-record
positive components with observed true postal comparison. Their induced graph
has 249,048 candidate edges and one component containing 93.94% of retained
dyads. Truth is `9922/10297 = 0.963581626`; verified integer-weight Blossom
optimization gives the exact upper endpoint
`9924/10297 = 0.963775857`. The lower endpoint exceeded the predeclared
120-second limit and remains `UNRESOLVED`, so no complete frontier, width, or
containment claim is made. UCI does not validate blocking recall or supply
natural calibration markets. FEBRL4 remains a small synthetic one-to-one
method-fit check; neither benchmark validates Chicago transfer.

## Chicago claim boundary

For a boundary-complete, internally consistent cohort with
`Shared Trip Match = true` and `Trips Pooled = 2`, the public field reports
realized co-presence while partner identity remains hidden. The eventual
application targets the neighborhood-context composition of those customer
transactions. It does not identify rider income, race, preference, durable
ties, platform opportunity, or an echo chamber.

The committed prefix sample is useful only for schema and pipeline checks. Its
identifier sampling omits almost every hidden counterpart, so no Chicago
matching, composition, or policy estimate is computed from it.

The current dataset metadata links the live release to the City's
at-most-two-trip, 15-minute tract-cell threshold with paired endpoint
coarsening. This licenses the one-way implication from visible fine geography
to HIGH applicable endpoint cells. It does not license inferring LOW from a
blank tract, because source missingness and outside-city locations are also
documented. The City can append late provider reports, so a complete slice is
complete only for its pinned public revision until a later stabilization check.

The committed Chicago adapter is a fail-closed declared-input handoff. It
validates metadata, contributor-universe, label-support, evidence, role, and
factor contracts; rejects preloaded Chicago factors; and replays a
content-addressed contract before compilation. Its support-completeness flag
applies only to per-record latent labels and never licenses candidate-edge
coverage. Diagnostics always retain
`city_implementation_validated = false` and
`live_extraction_performed = false`.

The separate `K=2` production harness audits literal match/run fields,
core--buffer--context roles, closed timestamp envelopes, cross-midnight
candidates, pinned all-row counts, and logical versus heuristic graphs. It
does not reconstruct true partners. Partner recall and hidden-run closure stay
`NOT_IDENTIFIED_FROM_PUBLIC_ROWS`; a real all-row snapshot and independently
reviewed operator evidence are still required.

## Repository map

- `KDD_RESEARCH_PIVOT.md` — formal target, claim removals, work packages, and
  KDD go/no-go rule.
- `adversarial_review/` — restart-from-zero identification, novelty,
  empirical-gate, and venue audit.
- `paper/main.tex` — anonymous ACM Research-track working manuscript.
- `code/ai_pilot/bounds/joint_label_matching.py` — exact small-world and
  numerical joint matching--label endpoints with core/buffer/context roles.
- `code/ai_pilot/bounds/structured_matching_bounds.py` — audited fixed-graph
  endpoint baseline.
- `code/ai_pilot/bounds/conformal_matching.py` — matching-level split-conformal
  calibration.
- `code/ai_pilot/bounds/path_frontier_dp.py` — exact sparse temporal frontier,
  witness replay, and certified outward score relaxation.
- `code/ai_pilot/bounds/component_frontier.py` — exact joint-incidence
  decomposition and global resource convolution.
- `code/ai_pilot/bounds/release_operator_compiler.py` — explicit-DNF release
  compilation, lifecycle audit, and exact witness projection/restoration.
- `code/ai_pilot/benchmarks/conformal_set_benchmark.py` — deterministic
  source/calibration/test benchmark.
- `code/ai_pilot/benchmarks/exact_conformal_frontier.py` — exhaustive
  10,395-matchings-per-market audit and radius frontier.
- `code/ai_pilot/benchmarks/joint_solver_audit.py` — 250-instance exact versus
  numerical agreement audit.
- `code/ai_pilot/benchmarks/path_frontier_benchmark.py` — locked 34-case
  structural, exhaustive, numerical, and relaxation benchmark.
- `code/ai_pilot/benchmarks/component_frontier_benchmark.py` — same-kernel,
  independent-oracle, shared-factor, and operational decomposition audit.
- `code/ai_pilot/benchmarks/runtime_profile/` — bounded operational profile
  across record, degree, factor, label, score, and Gamma axes.
- `code/ai_pilot/external_benchmarks/` — UCI real-topology audit and FEBRL4
  external synthetic method-fit test; no raw external data are committed.
- `code/ai_pilot/data_pipeline/chicago_release_adapter.py` — declared-input,
  fail-closed Chicago-to-generic-compiler handoff.
- `code/ai_pilot/data_pipeline/production_audit/` — synthetic-tested `K=2`
  extraction, boundary, and graph-contract audit.
- `code/ai_pilot/integration/` — earlier weak-node-score pilot, retained as
  failure analysis rather than headline evidence.
- `SUBMISSION_CHECKLIST.md` — KDD Research format and scientific gates.
- `ARTIFACT_MANIFEST.md` — file-level evidence provenance.

## Reproduce the audited code

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r code/ai_pilot/requirements.txt

python adversarial_review/counterexamples.py
python -m unittest discover -s code/ai_pilot/bounds/tests -v
python -m unittest discover -s code/ai_pilot/data_pipeline/tests -v
python -m unittest discover -s code/ai_pilot/data_pipeline/production_audit/tests -v
python -m unittest discover -s code/ai_pilot/external_benchmarks/tests -v
python code/ai_pilot/benchmarks/conformal_set_benchmark.py
python code/ai_pilot/benchmarks/exact_conformal_frontier.py
python code/ai_pilot/benchmarks/joint_solver_audit.py
python code/ai_pilot/benchmarks/path_frontier_benchmark.py
python code/ai_pilot/benchmarks/component_frontier_benchmark.py
python code/ai_pilot/benchmarks/runtime_profile/temporal_frontier_profile.py \
  --suite quick --case-timeout-seconds 3 --max-frontier-records 200000
MPLCONFIGDIR=tmp/matplotlib \
  python code/ai_pilot/benchmarks/plot_conformal_tradeoff.py
```

The all-ten UCI audit is intentionally outside the default/CI path because it
requires ten pinned external cache archives and a predeclared endpoint time
limit. Its dedicated README gives the cache contract and writes reproduction
outputs to fresh paths; no raw UCI rows or links are committed.

The benchmark's hidden pair truth is used for source training, market-level
calibration, and held-out evaluation according to the fixed three-way split.
No benchmark result licenses a real-data coverage claim.

## Build and inspect the paper

```bash
./scripts/build_paper.sh
./scripts/check_submission_pdf.sh paper/KDD_Research_Working_Draft.pdf
```

The working source uses the double-blind Research-track form:

```tex
\documentclass[sigconf,anonymous,review]{acmart}
```

The first KDD 2027 cycle has passed. The project targets the next official
Research-track cycle; this repository does not assume an unpublished deadline.
