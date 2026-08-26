# Adversarial Approach Registry

## Evidence freeze

- Audit restart date: 2026-08-26
- Repository HEAD: `9867029b5d3e97fd1346cbd8d11a052ab7f69e53`
- `paper/main.tex`: `c4ff40b4a0f24e66ab8577b0781d96d648d877c703c9603c9b1030085537ecd8`
- `paper/Thicker_But_Narrower_Draft.pdf`: `4341b8bf719f77ecff82838fd4384d914eb661dc851419b3660a4600b31968d9`
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
| Observation operator and target population | The public row reveals realized co-presence at the node level but does not publish partner, provider, vehicle, or group identifiers | Field-to-claim map and minimal counterexamples | Complete | Current suppression-rule continuity and a production boundary-closure audit remain unverified |
| Matching endpoint geometry | Min/max over a declared exact-cover graph gives attained endpoints, but generally not every scalar between them | Formal endpoint proposition and four-node counterexample | Complete; code terminology repaired | Manuscript terminology remains frozen pending a coherent empirical object |
| Node weak supervision | Node marginals can train a compatibility score but do not identify latent edge probabilities or a joint matching distribution | Incidence-nullspace and joint-probability counterexamples | Complete | A coherent matching-aware likelihood or independent edge truth is absent |
| Score-restricted ambiguity | A raw fractional score floor is sensitive to arbitrary score transformations | Transformation counterexamples and invariant alternative | Complete; positive-affine-invariant helper implemented | Normalized regret has no scientific calibration or cross-score coverage meaning |
| Missing-context identification | Requiring both endpoints to have ACS context changes the feasible matching population and may delete the true pairing | Missing-label completion formulation | Complete for independent supports; tested implementation added | Joint suppression coupling and production data remain absent |
| Suppression-coupled geography | The currently accessible 2019 City clarification, associated with legacy dataset IDs, documents separate pickup-time/tract and dropoff-time/tract buckets and paired removal when either count is below three | Joint endpoint-assignment/matching formulation, complexity, and small exact tests | Conditionally formulated; operator continuity unverified | Whether the rule applies unchanged in 2025/2026 and whether it completely explains internal missingness |
| Policy coefficient propagation | Daily endpoint regressions do not bound a regression coefficient; cross-block edges break factorization | Global edge-linear regression proposition | Complete algebraically; tested signed-objective implementation added | A coherent unconditional trip-level outcome, current legal encoding, and inference layer are absent |
| Candidate-support uncertainty | Raw coverage is conditional on the true hidden edge surviving heuristic screens and the global degree cap | Candidate-deletion constructions and sensitivity sets | Complete conditionally; Gamma helper implemented | No defensible supergraph or empirical bound on omitted true edges exists |
| Validation design | The generator embeds outcome-separating and SES-geographic structure; the current primary ablation was selected after inspecting the original diagnostic | Reproduction record and leakage audit | Complete; blocked as scientific validation | Independent realistic truth source or untouched generator family |
| Novelty and venue positioning | Exact-cover range queries, linkage uncertainty, MIL/noisy-OR, budgeted matching, Chicago pooled-trip analyses, and urban exposure all have predecessors | Primary-source nearest-predecessor matrix | Complete | The suppression-coupled combination clears no venue bar until the current operator, theory, algorithm, and empirical materiality are established |

## Blocked or superseded families

| Blocked route | Reason blocked | Condition for reopening |
|---|---|---|
| “Service-chain opportunity, not verified co-presence” as the observation target | The official reporting definition of `Shared Trip Match` says the passenger shared the vehicle with a separately booked passenger at some point | Reopen only if a different released field/cohort is used and its definition supports that target |
| Product noisy-OR as a joint latent-edge likelihood | Node events that share candidate edges are not independent; the product assigns mass to logically impossible node-label patterns | Reopen only with an explicit coherent matching-aware generative model and likelihood |
| Raw `rho W*` as a comparable ambiguity radius across score maps | Membership can change under affine rescaling or monotone transformation without changing edge rankings | Reopen only with an invariant definition and a declared calibration rule |
| “Sharp identified interval” as the exact attainable scalar set | A four-cycle can yield attainable values `{0,1}` while the displayed range contains `1/2` | Reopen only if “sharp” is explicitly limited to endpoints or the target includes convexification/randomization |
| Independent missing-bin sets as a standalone novelty claim | Edgewise lower/upper costs reduce immediately to ordinary weighted perfect matching | Reopen only with empirically justified coupling constraints such as the actual suppression operator |
| Chicago empirical or policy conclusion | No complete-day production run exists in the frozen evidence | Reopen only after complete-day ingestion, field audits, support diagnostics, and a predeclared policy analysis |

## Post-audit implementation record

- 30 deterministic unit tests pass.
- The exhaustive fallback and SciPy/HiGHS agree on status and endpoints across
  all 468 feasible cases in a 500-draw six-node randomized audit with signed
  objectives spanning many scales, optional score floors, and Gamma budgets
  (scale-adjusted tolerance at most \(10^{-8}\) relative to the draw scale).
- These tests establish small-instance implementation behavior only; they do
  not validate the candidate graph, the current City suppression operator, or
  any Chicago scientific conclusion.
