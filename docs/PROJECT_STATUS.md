# Verified project status

Latest verified evidence checkpoint: 2026-09-09, Chicago follow-up batch 0 recorded.
The next-stage plan is in `docs/NEXT_RESEARCH_GATE.md`. A separate 96-window
Chicago calendar is declared in `CHICAGO_K2_FOLLOWUP_PROTOCOL.json`; its interim
results do not change the closed 24-window pilot's evidence counts.

Chicago run `34298803324` has 10 completed windows, 2 fixed-core exclusions,
and 84 unstarted windows across the frozen 96-window denominator. It has
1,192 numerically certified endpoint pairs, 300 missing-public-value pairs,
and 8 computationally unresolved pairs (1,500 total; 99.33% certification among
the 1,200 data-complete pairs). All eight unresolved lower endpoints concern
duration gap in the January 15 evening window. The source ZIP and all 235
checkpoint files have been hash-verified; a durable aggregate-only snapshot is
in `results/chicago_k2_followup/batch0_20260909/` under the data pipeline.
Batch 1 is eligible for dispatch under the record-terminal protocol; this is
not a claim that all batch-0 endpoints are exact. The follow-up Gate is HOLD.

The September 9 manuscript rewrite centers temporal-event feasibility and
the fixed-time additive pricing oracle, explicitly credits prior aggregate
bounds and interval decomposition, and preserves the NYC structural null.
It corrects the matching-cardinality normalization and distinguishes
positive-overlap tolerance in continuous MILP from unrestricted strict overlap.

The new NYC structural comparison fixes one 4-core/12-buffer input at capacities
2, 3 and 4. All 36 outcome endpoint pairs close; 117 support-feasibility checks
and 72 endpoint MILP checks agree with complete enumeration and witness replay.
At the common positive buffer counts (2 and 4), **0/24 restricted-versus-ordered
comparisons change any endpoint**. Ordered and clique event columns coincide
at every capacity. Maximum support is 4/8/12 for ordered and clique, and 4/4/4
for exactly-two-row events; those maxima are not fixed-q outcome differences.

The reason is visible in the input geometry: all 16 intervals have a common
14-second overlap, so the graph is a complete 120-edge clique. Every buffer
subset of sizes 2 and 4 is feasible under all three models. This diagnostic is
computationally PASS, but the proposed public-data structural-advantage claim
remains HOLD. It supplies no evidence about actual sequential vehicle runs or
general model equivalence. The result and a TeX fragment are in
`code/ai_pilot/data_pipeline/results/nyc_hvfhv/structure_audit_20260908/`.

The outcome-blind temporal-geometry census completed its first 24-cell attempt
on 2026-09-08 (run `34237155750`): **8 geometry-complete, 3 protocol-ineligible,
13 transport failures**. All eight full candidate views contain core-incident
non-clique event columns; four of their eight time-only 4+12 reductions are
complete cliques. These are partial descriptive counts, not 24-cell prevalence
or evidence of fixed-q outcome changes. The census gate remains **HOLD**.
Aggregate records, artifact digests and TeX are preserved in
`code/ai_pilot/data_pipeline/results/nyc_hvfhv/geometry_census_20260908/first_attempt/`.

A transport-only amendment was declared before recovery: 120-second requests,
30-minute window deadlines and two concurrent workers. Run `34240720735`
restored all source checkpoints, reused terminal records and retried only the
13 transport failures; it did not refetch completed scientific records. The
verified recovery artifact (`10067398726`, ZIP SHA-256
`daaf81f8fcd57e07996e48f98e3348306804a52c40135b97b0a026992ab1888d`)
still reports **8 geometry-complete, 3 protocol-ineligible, 11 transport
failures and 2 transport deadlines**. Window 20 reached geometry completion in
the job log, but artifact finalization returned HTTP 403; without its report
and replay fields it remains the prior transport failure in the scientific
ledger. The recovery Gate therefore remains **HOLD**.

The source protocol and geometry producer stayed frozen. The recovery manifest,
all four output hashes and the 24-cell denominator replay correctly. Fifteen
targeted tests pass, covering independent triple counts, full denominators and
predecessor validation. A concise recovery audit and TeX fragment are under
`geometry_census_20260908/recovery_attempt/`.
`docs/NYC_GEOMETRY_CENSUS.md` documents the design and claim boundary.
No further wait-budget expansion is justified without a transport redesign.

The frozen Chicago 96-window follow-up now has a fail-closed staged controller.
It distinguishes unstarted windows, missing artifacts, transport failures,
scientific exclusions and complete records across the full denominator. Batches
contain 12 consecutive indices and cannot advance until all earlier windows are
record-terminal. The first batch started from an empty hash-pinned checkpoint
and its interim aggregate is reported above. The next batch remains the
highest-priority execution Gate; manuscript work does not launch or complete it.

The adversarially repaired ATR v4 dyad audit has 170 eligible fixed snapshots and 850 radius
cells. All are computationally closed: 806 have replayed numerical MILP optima
and 44 are candidate-graph infeasible. A separate subset-recursion oracle agrees
on all 195 cells within its size limit. Conditional on candidate support
representing the annotated dyads, the frontier covers 769/769 cells and flags
68/68 minimum-distance point-rule errors; these are implementation implications
of valid support, not independent evidence of unconditional safety. Under
misspecified support, 16 wrong point decisions remain unflagged across eight
snapshots. At 5 m under valid support, 410/495 (82.8%) threshold decisions are
ambiguous. DIAMOR-1 is pilot and DIAMOR-2 a predeclared follow-up, not a pristine
holdout. Labels assist exclusion, eligibility, and the true `q`; this is an
oracle-assisted q-conditioned audit, not a population group estimate.

The follow-on unknown-cardinality audit is closed on both days. Unioning over
all positive dyad counts increases exact-feasible cells from 806 to 826, but
widens the mean frontier from 1.176 m to 1.297 m and lowers certified threshold
decisions from 53.2% to 45.8%. This is not improved truth coverage: every false
certificate remains confined to candidate-support misspecification.

A separate cross-day multi-query audit trains a transparent logistic edge
scorer on DIAMOR-1 and freezes it for DIAMOR-2. On 381 representable exact
cells, its mean dyad recall (89.24%) is close to closest-distance matching
(89.62%), but its distance/speed/heading threshold errors are 44/70/35 versus
32/44/38. All are frontier-ambiguous. This shows that similar relation recall
does not imply similar downstream decision reliability; it does not establish
state-of-the-art relation prediction.

A pilot-only candidate-support calibration searches a fixed radius--angle grid
and selects 3 m/120 degrees as the sparsest rule meeting 95% DIAMOR-1 relational
coverage (85/88 snapshots, 4.52 mean edges). Frozen on DIAMOR-2, it covers 81/82
snapshots but expands to 12.17 mean edges and certifies only 29/246 threshold
decisions. Coverage transfers in this comparison; sparsity and informativeness
do not, so this is not claimed as a universal support rule.

A post-hoc local-degree-cap audit tests one simple response to that density
shift. Selecting `k=2` on DIAMOR-1 preserves the fixed rule's pilot coverage;
on DIAMOR-2 it also preserves 81/82 coverage while removing 80/998 candidate
edges (8.0%). The frontier nevertheless certifies exactly the same 29/246
decisions. Thus trimming high-degree edges does not repair informativeness;
the remaining ambiguity is structural under this audit, not merely graph bulk.

The follow-on endpoint-witness audit localizes that structure. All 82 fixed
graphs have positive width and distinct endpoint witnesses; 73 require multiple
disconnected alternating components in the returned solutions. Components are
small (at most four edges) and overwhelmingly paths. The degree cap leaves all
lower endpoints unchanged and contracts 21 upper endpoints by 0.177 m on
average among changed cells, yet changes no threshold-ambiguity count. Thus
graph compression and decision identification separate empirically here.
The manuscript now formalizes this distinction with an alternating-component
decomposition for equal-cardinality K=2 endpoint matchings and an exact
threshold-invariance condition under nested support contraction.

NYC has 24 windows, 21 eligible windows, 126 outcome-capacity cells and 18/18
exact closures on the predeclared nested-size scale lattice; Chicago run 164 has
60 cores, 611 candidates and 50,405 contributors. The NYC outcome panel still
has one unresolved decision cell and retains its anytime-bound language.

The repository contains fixed-support implicit disclosure branch-and-price,
ex-post minimum certificate search, pricing acceleration, independent-seed
ablations and the compact event-slot lower-bound probe. The repaired compact
package contains 96 complete paired records. Probe exact
status is 38/48; disabled exact
status is 16/48. The frozen
rule sets the default budget to `0.75` seconds.

Only `ci.yml`, `chicago-live-audits.yml`, `chicago-k2-fixed-panel.yml`, and the
`nyc-bp-24h.yml` NYC campaign are active workflows. Its geometry mode executes
the new census; historical branch-price reruns require explicit mode selection.
CI verifies compact hashes/default consistency,
deterministic tests and the paper build. The NYC follow-up assigned 20,700
solver seconds independently to each of the four formerly open scale cells and
certified all four exactly. Its artifact capture is fail-closed and every future
timeout remains an unresolved interval. Selective disclosure remains outside
the manuscript pending real membership truth or unknown-support/noisy-answer
closure.

The Chicago K=2 fixed-panel protocol predeclares 24 weekday/date-time cells
before public row counts or frontier outcomes are inspected. The verified
initial run has 19 completed windows, one scientifically ineligible fixed core,
and four transport failures. Corrected aggregation of the original sensitivity
CSVs gives 2,264/2,830 certified endpoint pairs, 566 missing-public-value pairs,
and zero computationally unresolved pairs (100% exact among data-complete
pairs). Completed retries at index 0 (local), index 23 (GitHub run
`34074653956`), index 20 (run `34175478785`) and index 12 (run
`34178831936`) close all 23 scientifically eligible windows. The final aggregate
has 2,744/3,430 certified endpoint pairs, 686 missing-public-value pairs and
zero computationally unresolved pairs; the data-complete exact rate is 100%.
The original reports and all retry records are pinned separately. The
**24-window pilot execution is closed**, but the broader Chicago scale gate is
still **PARTIAL / HOLD** because this is not a hundreds-of-cohorts result.

Recovery pins the 24 original artifacts and 447 extracted files, reuses the 19
completed windows and the ineligible window, and retries only indices 0, 12,
20 and 23. Hash/protocol checks run before reuse; attempt history survives
merging and the resulting full checkpoint can seed another run. GitHub run
`34074653956` verified restore and closed index 23. Run `34175478785` then
merged the pinned local index 0 and closed index 20. Run `34178831936` closed
the final index 12 through the identity-reconciled fallback; its recovery plan
is empty. See
`docs/CHICAGO_K2_FIXED_PANEL.md` and the committed initial checkpoint manifest.
A live bounded-index probe returned 612 and 611 unique rows for the two
predicates where wide `count(*)` had timed out. A separately hash-pinned
ID-index reconciliation transport is implemented, tested and now evidenced by
the successful index-12 artifact.
The first indexed attempt, run `34177343252`, still timed out when redundantly
pulling the same narrow index at 90 seconds. Its checkpoint is retained. The
successful attempt reuses that in-memory index within extraction, independently
rechecks it afterward, and allows 240 seconds per transport request. This is a
transport repair, not a change to candidate support.
A separate generic omission budget expands from the declared under-padded
support to the boundary-complete temporal envelope without exempting edges
whose geography is missing. These pilot records are not manuscript claims.
