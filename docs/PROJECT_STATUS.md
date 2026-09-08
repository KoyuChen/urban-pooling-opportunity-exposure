# Verified project status

Checkpoint: 2026-09-06, NYC scale follow-up evidence captured and audited.

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
manual `nyc-bp-24h.yml` follow-up are active workflows. CI verifies compact hashes/default consistency,
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
`34074653956`) and index 20 (GitHub run `34175478785`) raise the current merged
total to 22 completed windows, one ineligible and one outstanding, with
2,624/3,280 certified pairs, 656 missing-public-value pairs and zero
computationally unresolved. The original reports and all retry records are
pinned separately.
This is **PARTIAL / HOLD**, not a hundreds-of-cohorts scale result.

Recovery pins the 24 original artifacts and 447 extracted files, reuses the 19
completed windows and the ineligible window, and retries only indices 0, 12,
20 and 23. Hash/protocol checks run before reuse; attempt history survives
merging and the resulting full checkpoint can seed another run. GitHub run
`34074653956` verified restore and closed index 23. Run `34175478785` then
merged the pinned local index 0 and closed index 20; index 12 remained a
transport failure. The next recovery uses that checkpoint and retries only 12. See
`docs/CHICAGO_K2_FIXED_PANEL.md` and the committed initial checkpoint manifest.
A live bounded-index probe returned 612 and 611 unique rows for the two
predicates where wide `count(*)` had timed out. A separately hash-pinned
ID-index reconciliation transport is implemented and tested; this does not
change either window's status until complete retry artifacts are captured.
The first indexed attempt, run `34177343252`, still timed out when redundantly
pulling the same narrow index at 90 seconds. Its checkpoint is retained. The
next attempt reuses that in-memory index within extraction, independently
rechecks it afterward, and allows 240 seconds per transport request.
A separate generic omission budget expands from the declared under-padded
support to the boundary-complete temporal envelope without exempting edges
whose geography is missing. These pilot records are not manuscript claims.
