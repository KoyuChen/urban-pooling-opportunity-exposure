# Certified Temporal Frontiers for Hidden Relations

KDD Research-oriented working repository for certified aggregate inference when
a public release suppresses relation keys and coarsens endpoint attributes.
Chicago ride pooling is the flagship application; it is not treated as a
substitute for general method validation.

> **Status:** research build, not submission ready. The exact temporal-frontier
> solver, certified score relaxation, matching-level conformal safety layer,
> and locked structural benchmark are implemented. A verified 2025/2026
> Chicago observation operator, a production compiler and full-day width
> profile, independent external relation-truth validation, and complete-day
> Chicago evidence remain hard gates.

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
- `code/ai_pilot/benchmarks/conformal_set_benchmark.py` — deterministic
  source/calibration/test benchmark.
- `code/ai_pilot/benchmarks/exact_conformal_frontier.py` — exhaustive
  10,395-matchings-per-market audit and radius frontier.
- `code/ai_pilot/benchmarks/joint_solver_audit.py` — 250-instance exact versus
  numerical agreement audit.
- `code/ai_pilot/benchmarks/path_frontier_benchmark.py` — locked 34-case
  structural, exhaustive, numerical, and relaxation benchmark.
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
python code/ai_pilot/benchmarks/conformal_set_benchmark.py
python code/ai_pilot/benchmarks/exact_conformal_frontier.py
python code/ai_pilot/benchmarks/joint_solver_audit.py
python code/ai_pilot/benchmarks/path_frontier_benchmark.py
MPLCONFIGDIR=tmp/matplotlib \
  python code/ai_pilot/benchmarks/plot_conformal_tradeoff.py
```

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
