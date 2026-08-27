# KDD Research Pivot: Hidden Relations under Privacy Coarsening

## Decision

The project now targets the **KDD Research Track** as a methods paper. Chicago
is the flagship application, not the methodological object. The working claim
is deliberately narrower than a submission claim:

> Compile privacy-coarsened hidden-relation worlds into a temporal frontier,
> compute exact or outward-certified aggregate endpoints, and use learned
> scores only through a separately calibrated safety layer.

The current evidence is not yet sufficient for submission. This repository is
the research build that must either pass the gates below or fall back to a
transportation venue without KDD branding.

## Scientific object

Let (O) denote released rows, (G=(V,E)) a declared candidate supergraph,
(C\subseteq V) core records, and (B\subseteq V) boundary-buffer records. A
feasible world is a pair ((M,a)), where (M\subseteq E) is a matching and
(a_i) is a latent categorical endpoint attribute:

\[
\mathcal F(O,G)=\left\{(M,a):
  \deg_M(i)=1\ (i\in C),\quad
  \deg_M(i)\le 1\ (i\in B),\quad
  a\text{ satisfies released supports and global coarsening constraints}
\right\}.
\]

Context-only rows may enter global privacy-cell counts without entering the
matching. The primary query is a core-incidence-weighted aggregate,

\[
Q_C(M,a)=\frac{1}{|C|}\sum_{e=\{i,j\}\in M}
|e\cap C|\,g(a_i,a_j),
\]

so core--core and core--buffer edges are handled without changing the target
denominator. The reported endpoints are attained minima and maxima over

\[
\underline Q=\min_{(M,a)\in\mathcal F(O,G)}Q_C(M,a),\qquad
\overline Q=\max_{(M,a)\in\mathcal F(O,G)}Q_C(M,a).
\]

They are conditional on the declared observation operator and candidate
supergraph. The scalar interval between them is the convex hull of attainable
values; it need not consist entirely of attainable values.

## Learning-augmented restriction

For any rationalized edge scorer fixed before calibration, let (S(M)) be its
core-incidence-weighted additive score, and let (S_{\min},S_{\max}) be its
extrema over a market's feasible matching domain. Define matching-level
nonconformity

\[
R_s(M)=\frac{S_{\max}-S(M)}{S_{\max}-S_{\min}},
\]

with (R_s=0) for a constant score map. This radius is invariant to every
positive affine transformation of the edge score. On (m) independent
calibration markets with observed true matchings, use the

\[
\left\lceil(m+1)(1-\alpha)\right\rceil
\]

order statistic of (R_s(M^\dagger)). Calibration observes the true matching
because the scorer is matching-only. Query coverage additionally assumes that
the augmented markets, including their full true worlds, are exchangeable and
that each true full world belongs almost surely to the frozen reference set.
For a smaller final `Gamma`, a separate eligibility failure probability
`alpha_G` gives coverage at least `1-alpha_S-alpha_G`; it is not absorbed into
the score error. Optimizing any downstream query over the same retained world
set inherits that one full-world membership event.

The score range is computed once over a predeclared ambient `Gamma` budget and
frozen along the entire candidate-omission path. Edge contributions are
rationalized componentwise before exact summation, and the resulting rational
floor is consumed directly by the exact solver. Recomputing the normalizer separately for each
`Gamma` can break nestedness.

This does **not** license transferring synthetic calibration to Chicago.
Without independent Chicago-like partner truth, the Chicago score restriction
remains a sensitivity analysis and the score-free endpoints remain primary.

Candidate omission is audited separately with a supplied supergraph and

\[
\sum_{e\in E_{\mathrm{super}}\setminus E_{\mathrm{base}}}z_e\le\Gamma.
\]

Calibration error and candidate-support error are distinct and must not be
hidden inside one claimed confidence level.

## What is already implemented

- Exact small-graph and numerical large-graph matching endpoint solvers with
  explicit `OPTIMAL`, `NUMERICALLY_OPTIMAL`, `PROVEN_INFEASIBLE`, and
  `UNRESOLVED` states.
- A joint categorical-label and core/buffer/context matching reference solver
  with global count bounds, attribute-conditioned edge compatibility, Gamma,
  score floors, endpoint witnesses, and distinct exact/numerical statuses.
- Signed lower/upper objectives, independent missing-context envelopes,
  fixed-design FWL weights, and supplied-supergraph \(\Gamma\) sensitivity.
- Matching-level normalized regret and finite-sample split-conformal radius.
- An exact temporal-frontier solver with sparse active factor lifetimes,
  threshold-capped LOW/HIGH automata, exact rational score/query arithmetic,
  Gamma, and independently replayed endpoint witnesses.
- A weak-NP-hardness boundary on disjoint pathwidth-two four-cycles, explaining
  why exact score tracking is pseudo-polynomial even at constant graph width.
- A certified bicriteria score relaxation satisfying
  \(\mathcal F_B\subseteq\widehat{\mathcal F}_\eta
  \subseteq\mathcal F_{B-\eta|C|}\); it is not a query FPTAS.
- A locked 34-case frontier benchmark: 32 exhaustive agreements, 24 analytic
  agreements, 16 resolved numerical agreements, and one certified relaxation
  check.
- A complete NP-completeness proof for an explicitly defined paired
  threshold-release operator, audited with the endpoint-independent and
  metric-compatibility limitations stated. The theorem is not asserted to be
  the current Chicago operator.
- A deterministic three-way source/calibration/test benchmark with directly
  edge-supervised target-free and deliberately query-leaking scorers under a
  homophily shift.
- A second solver-free frontier audit over all 10,395 perfect matchings per
  synthetic test market; it shares the locked generator and score utilities,
  separately reaggregates the results, and evaluates radii from 0 to 1.
- Executable counterexamples showing why node marginals do not identify edge
  ranks, a product of noisy-OR marginals is not a coherent joint matching
  model, raw fractional score floors are scale dependent, and endpoint ranges
  are not generally fully attainable intervals.

In the current conformal benchmark, both calibrated scorers exceed the nominal
90% true-matching retention rate on 120 held-out markets. At the illustrative
radius 0.05, the query-leaking stress scorer retains only 15.0% of true
matchings and covers the downstream statistic in 24.2% of markets despite
reducing width by 95.8%. After calibration its true-matching retention is 97.5%
and observed downstream coverage is 120/120, but width reduction falls to
7.6%. This is the intended scientific lesson: calibration exposes, rather than
rewards, query-derived false precision. These numbers validate only the
matching-set calibration implementation on one synthetic design.

## Claims removed from the KDD version

- Chicago does not lack node-level realized co-presence: `Shared Trip Match`
  reports it. The hidden object is partner identity.
- The application is not rider-level opportunity, income, preference,
  friendship, or an echo chamber. It is the neighborhood-context composition
  of a precisely defined set of customer transactions.
- Node noisy-OR fit is not an edge likelihood and is not the main AI
  contribution.
- A degree-capped spatial screen is not a coverage graph.
- Complete-case geography is not a valid repair for suppression-coupled
  attributes.
- A fixed raw score fraction is not a confidence level and is not comparable
  across score maps.
- The January 2026 policy design is not a traveler ITT and will not occupy the
  methods paper unless a globally optimized, legally verified result survives
  all causal gates.
- The locked two-day synthetic pilot and its 90.2% node-Brier improvement are
  failure-analysis evidence, not the KDD headline result.

## KDD work packages and hard gates

| Work package | Deliverable | KDD gate |
|---|---|---|
| Observation operator | Version-specific 2025/2026 documentation, all rows contributing to privacy cells, boundary-safe extraction | No Chicago aggregate claim before verification |
| Coupled method | Joint matching--attribute feasible-world solver; independent-support reduction; correctness proof | Must exceed an application-specific MILP description |
| Complexity and algorithm | Exact temporal frontier, weak-hardness boundary, and score-slack relaxation implemented; production compiler/order and full-day width profile remain | Required before a production scalability claim |
| Learning | Matching-level calibration on independent markets with observed relation truth | Required for any calibrated AI-sharpening claim |
| Candidate support | Necessary-condition supergraph, omitted-edge stress tests, and calibrated or externally audited support | Raw endpoints remain graph-conditional otherwise |
| Benchmarks | Untouched controlled family plus at least one non-Chicago relational benchmark with hidden ground truth | Required for generality |
| Chicago | Full-day, boundary-complete (K=2) cohort; all-trip privacy cells; production certificates | Required as flagship evidence, not as a substitute for method validation |
| Baselines | Point matching, complete cases, independent supports, single imputation, linkage-range queries, DBSCAN proxy grouping, score-free coupled bounds | Required for empirical credibility |

## Submission decision rule

- **KDD Research GO:** verified operator; nontrivial theory; production-scale
  certified algorithm; independently calibrated matching-level learning;
  multi-benchmark evidence; complete Chicago application.
- **Transportation fallback:** complete, suppression-aware Chicago result with
  material transportation implications, but no general algorithmic advance.
- **NO-GO:** incomplete-day/prefix evidence, unverified operator, or sharpening
  justified only by node prediction.

KDD 2027's first cycle has passed. The repository targets the next official
Research-track cycle; no unannounced deadline is assumed.
