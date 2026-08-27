# Adversarial Approach Registry

## Evidence freeze

- Audit restart date: 2026-08-26
- Repository HEAD: `9867029b5d3e97fd1346cbd8d11a052ab7f69e53`
- `paper/main.tex`: `c4ff40b4a0f24e66ab8577b0781d96d648d877c703c9603c9b1030085537ecd8`
- Historical `paper/Thicker_But_Narrower_Draft.pdf` (retained in Git history only): `4341b8bf719f77ecff82838fd4384d914eb661dc851419b3660a4600b31968d9`
- `code/ai_pilot/integration/DESIGN_LOCK.json`: `b32a2a97d7bb4196ee756bfde6aba6835a51a7f44dbd2485892674a793ee6b68`
- `code/ai_pilot/integration/results/benchmark_results.json`: `863608a291373c09053bd076721a69a6b0719f3995fc7b1a39b3e90b85caeeee`
- Worktree at restart: clean.
- Existing submission-format check: passed (11 total pages, main content pages 1--8, references begin on page 9, both mandatory disclosure sections in the main paper).
- Repository-native unit-test invocation: reproduced; all seven exact-cover tests pass.
- Locked benchmark: independently rerun outside the repository and reproduced to the reported numerical precision.
- Later 22-feature ablation: independently rerun outside the repository and reproduced to the reported numerical precision.

Prior conversational evaluations are not evidence for this audit. Entries below will be populated from independent reconstruction and verified sources.

## Active families

| Family | Central claim under audit | Required concrete output | Status | Exact unresolved gap |
|---|---|---|---|---|
| Observation operator and target population | The public row reveals realized co-presence at the node level but does not publish partner, provider, vehicle, or group identifiers | Field-to-claim map, declared adapter, synthetic production harness, and minimal counterexamples | Declared interfaces implemented; high-level documentation complete | Real run closure, implementation/null causes, live rows, and partner recall remain unverified |
| Matching endpoint geometry | Min/max over a declared exact-cover graph gives attained endpoints, but generally not every scalar between them | Formal endpoint proposition and four-node counterexample | Complete; code terminology repaired | Manuscript terminology remains frozen pending a coherent empirical object |
| Node weak supervision | Node marginals can train a compatibility score but do not identify latent edge probabilities or a joint matching distribution | Incidence-nullspace and joint-probability counterexamples | Complete | A coherent matching-aware likelihood or independent edge truth is absent |
| Score-restricted ambiguity | A raw fractional score floor is sensitive to arbitrary score transformations | Transformation counterexamples and invariant alternative | Method repair complete for declared score maps: fixed-reference normalization, exact rational calibration, and directed rounding implemented | Chicago exchangeability, true-world membership, and scientific calibration remain unverified |
| Missing-context identification | Requiring both endpoints to have ACS context changes the feasible matching population and may delete the true pairing | Missing-label completion formulation | Complete for independent supports; tested implementation added | Joint suppression coupling and production data remain absent |
| Suppression-coupled geography | Current-linked City documentation describes an at-most-two threshold with paired endpoint coarsening; the clarification gives separate pickup/start and dropoff/end cells | Joint endpoint-assignment/matching formulation, explicit-DNF compiler, fail-closed Chicago handoff, and exact tests | Declared direction and adapter contracts implemented | City transformation, implementation partitions, blank causes, late-row recomputation, DST, live support, and tract vintage |
| Policy coefficient propagation | Daily endpoint regressions do not bound a regression coefficient; cross-block edges break factorization | Global edge-linear regression proposition | Complete algebraically; tested signed-objective implementation added | A coherent unconditional trip-level outcome, current legal encoding, and inference layer are absent |
| Candidate-support uncertainty | Raw coverage is conditional on the true hidden edge surviving heuristic screens and the global degree cap | Candidate-deletion constructions and sensitivity sets | Complete conditionally; Gamma helper implemented | No defensible supergraph or empirical bound on omitted true edges exists |
| Validation design | The generator embeds outcome-separating and SES-geographic structure; the current primary ablation was selected after inspecting the original diagnostic | Reproduction, leakage audit, all-ten UCI topology, exact-upper audit, and FEBRL4 method-fit test | Partial external repair | UCI lower/full frontier, realistic candidate recall, and natural calibration markets |
| Novelty and venue positioning | Linkage ranges, budgeted matching, conformal matching, bounded-width CSP, component convolution, knowledge compilation, and Chicago pooling all have predecessors | Primary-source matrix plus DNF/OBDD/component counterexamples | Conditional integrated increment survives: release-coupled frontier, weak-hardness boundary, witnesses, and outward certificate | Run-closed production scaling, natural external markets, and full endpoint evidence remain submission gates |

## Blocked or superseded families

| Blocked route | Reason blocked | Condition for reopening |
|---|---|---|
| “Service-chain opportunity, not verified co-presence” as the observation target | The official reporting definition of `Shared Trip Match` says the passenger shared the vehicle with a separately booked passenger at some point | Reopen only if a different released field/cohort is used and its definition supports that target |
| Product noisy-OR as a joint latent-edge likelihood | Node events that share candidate edges are not independent; the product assigns mass to logically impossible node-label patterns | Reopen only with an explicit coherent matching-aware generative model and likelihood |
| Raw `rho W*` as a comparable ambiguity radius across score maps | Membership can change under affine rescaling or monotone transformation without changing edge rankings | Reopen only with an invariant definition and a declared calibration rule |
| “Sharp identified interval” as the exact attainable scalar set | A four-cycle can yield attainable values `{0,1}` while the displayed range contains `1/2` | Reopen only if “sharp” is explicitly limited to endpoints or the target includes convexification/randomization |
| Independent missing-bin sets as a standalone novelty claim | Edgewise lower/upper costs reduce immediately to ordinary weighted perfect matching | Reopen only with empirically justified coupling constraints such as the actual suppression operator |
| Generic circuit/OBDD release compiler as a headline | Schedule-aligned monitors are known knowledge compilation; compact formulas can still induce exponential residual width, while Chicago's two-endpoint rule has no DNF bottleneck | Reopen only with a verified high-arity operator and benchmark showing a material DNF-to-monitor state reduction |
| Chicago empirical or policy conclusion | No complete-day production run exists in the frozen evidence | Reopen only after complete-day ingestion, field audits, support diagnostics, and a predeclared policy analysis |

## Historical pre-pivot implementation record

- 30 deterministic unit tests pass.
- The exhaustive fallback and SciPy/HiGHS agree on status and endpoints across
  all 468 feasible cases in a 500-draw six-node randomized audit with signed
  objectives spanning many scales, optional score floors, and Gamma budgets
  (scale-adjusted tolerance at most \(10^{-8}\) relative to the draw scale).
- These tests establish small-instance implementation behavior only; they do
  not validate the candidate graph, the current City suppression operator, or
  any Chicago scientific conclusion.

## KDD Research pivot record — 2026-08-27

| Family | Central claim | Concrete derivation or counterexample | Required assumptions | Nearest prior work | Current status | Exact unresolved gap |
|---|---|---|---|---|---|---|
| Exact temporal frontier | A declared temporal schedule admits exact lower/upper query endpoints and witness worlds while jointly tracking matching, latent labels, active threshold-release factors, omitted-edge budget, and a rational score floor | Inductive live-state invariant; capped threshold automata; exact `Fraction` implementation; locked benchmark | Valid compiled schedule; audited release implications; finite label supports; pair-additive query; constant core incidence for score shifting | Bounded-width CSP/bucket elimination; budgeted matching | Viable and implemented as a reference algorithm | No run-closed complete-day schedule/resource evidence |
| Explicit-DNF release compiler | One label copy per accepting clause gives an exact projected world set and preserves topology, score, query, and record-bag width for the same forget order; factor lifetimes and active-factor width may grow | Soundness/completeness proof, clause witness restoration, lifecycle audit, eight tests, 1,000 randomized parity cases | Explicit positive LOW/HIGH DNF; correct factor bindings and external semantics | Standard CSP compilation and knowledge compilation | Viable enabling layer; implemented | Exponential DNF expansion is disclosed; City null-cause/operator truth remains open despite a declared-input adapter |
| Incidence-component convolution | Only genuine joint record--release-factor components can be solved independently; local frontiers can be exactly convolved over global Gamma, score, and query resources | Shared-factor counterexample (naive upper 1 versus correct 11), 160 same-kernel and 192 independent-oracle checks, replayed witnesses | Additive global resources; exact local frontiers; one global score shift; shared factors merge components | Standard CSP/factor decomposition and knapsack/Pareto DP | Viable enabling engineering; implemented, not a novelty claim | Production benefit is unknown; one giant incidence component receives no structural speedup |
| Temporal-locality certificate | Chronological order has bag size equal to forward vertex separation plus one, bounded by maximum density in an edge-span window; active factors equal lifecycle-interval depth | Direct action-sequence identity and bounded capacity profile | Necessary edge span, pinned order, audited factor scopes | Kinnersley pathwidth/vertex separation; interval overlap | Valid supporting corollary, not novelty | Full-day density/factor distribution not measured |
| External relation-truth boundary | Real linkage truth need not satisfy matching topology; forcing it would fabricate the model fit | All-ten UCI topology reconciliation, exact upper/unresolved lower truth-conditioned dyad audit, and FEBRL4 complete-matching audit | Pinned official cache/package, isolated IDs/truth, disclosed truth-conditioned reduction | Record-linkage benchmark practice | Partial pass | UCI lower/full frontier, blocking recall, and natural market sampling remain |
| Score-aware complexity | The associated two-threshold decision problem under an additive score floor is weakly NP-complete at pathwidth two | SUBSET-SUM reduction using disjoint four-cycles; pseudo-polynomial score coordinate matches the weak-hardness boundary | Nonnegative binary-encoded integer score/query contributions; exact endpoint decision problem | Budgeted matching hardness and approximation | Viable; theorem independently checked | Must not be inflated into generic matching hardness or a “first” claim |
| Certified outward score relaxation | Rounding shifted scores down yields an outer world set between the exact floor and a floor relaxed by at most `eta*N`; endpoints contain the exact endpoints | Two-sided score inequalities, original-score witness revaluation, and 40 seeded random inclusion/witness checks | Constant total core incidence `N`; rationalized fixed scorer; structural constraints unchanged | Budgeted matching approximation; resource rounding | Viable; bicriteria certificate implemented | It is not a query FPTAS; query width can jump under arbitrarily small score slack |
| Fixed-reference conformal safety layer | Freezing one score range at a predeclared reference Gamma restores nested score-restricted sets and gives finite-sample retention only under full true-world exchangeability/membership | Four-cycle nestedness counterexample to per-Gamma renormalization; exact calibration-to-DP tests | Scorer/operator/graph/reference budget fixed before calibration; exchangeable augmented markets; true matching observed to score calibration; full true world belongs to the frozen reference set | Cauchois et al. structured/weak-supervision conformal prediction | Repairable method layer; code complete | No suitable Chicago calibration markets or verified candidate/release coverage |

The new counts supersede neither the historical freeze nor its scientific
blockers. The current suites discover 150 tests (149 cache independent plus one
pinned-UCI integration test); the locked temporal benchmark has 34 cases, and
the component audit has 160 same-kernel plus 192 independent-oracle
configurations. These committed checks validate declared-world software only;
the capacity profile and external audits retain their narrower evidence
boundaries.
