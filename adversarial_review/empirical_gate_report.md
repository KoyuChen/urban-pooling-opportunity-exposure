# Empirical Gate Report

## Overall status

- Chicago scientific and policy claims: **FAIL / not run**.
- KDD method artifact at reference-instance scale: **CONDITIONAL PASS**.
- Immediate submission: **FAIL** until production, full external-frontier, and natural-market gates pass.

The frozen artifact is reproducible as a software pilot. It does not yet pass
the gates needed for a Chicago structural estimate, an AI validation claim, or
a policy effect. Reproduction confirms the reported synthetic numbers; it does
not validate the generator, candidate-support assumption, score restriction,
or observation target.

## 1. Reproduction record

Evidence freeze: repository commit
`9867029b5d3e97fd1346cbd8d11a052ab7f69e53`.

The following repository-native checks were rerun without overwriting committed
outputs:

```bash
python code/ai_pilot/model/smoke_test.py
python -m unittest discover -s code/ai_pilot/bounds/tests -v
python code/ai_pilot/bounds/synthetic_validation.py \
  --output-dir /tmp/boundpool-solver-check
python code/ai_pilot/integration/run_integration_benchmark.py \
  --output-dir /tmp/boundpool-full-CJoFBK
python code/ai_pilot/integration/ablations/no_geography_equality_20260825/run_ablation.py \
  --locked-result-dir code/ai_pilot/integration/results \
  --output-dir /tmp/boundpool-ablation-9lYzrI
```

Results:

- all seven frozen exact-cover unit tests pass;
- the 20-replicate small-market coarsening check reproduces candidate recall
  and raw endpoint containment of 1.0 at 1-, 5-, 15-, and 30-minute bins;
- every selected full-model and 22-feature ablation metric below matches the
  committed output within absolute tolerance (10^{-12});
- the smoke test is not a universal positive benchmark: its transparent rule
  has Brier loss 0 and the reported relative AI improvement is strongly
  negative.

| Reproduced quantity | 28-feature diagnostic | 22-feature ablation |
|---|---:|---:|
| Held-out transparent-rule Brier | 0.0604812625 | 0.0604812625 |
| Held-out weak-score Brier | 0.0051311278 | 0.0059473799 |
| Candidate true-edge recall | 1.0000 | 1.0000 |
| Hidden-edge MRR | 0.7753125 | 0.9405208 |
| Hidden same-bin truth | 0.5625 | 0.5625 |
| Score range, nominal 0.90 | Not used as primary | [0.2875, 0.7625] |
| Score range, nominal 0.95 | [0.6125, 0.7750], excludes truth | [0.3875, 0.6875], contains truth |

The committed 20-replicate coarsening check reports raw widths of
0.0033, 0.0200, 0.0733, and 0.1500 for 1-, 5-, 15-, and 30-minute bins. The
nominal 0.95 score widths are 0.0033, 0.0067, 0.0200, and 0.0267. These are
implementation checks under the generator, not sampling confidence intervals.

## 2. Why the benchmark does not validate the scientific model

The generator deliberately separates matched and unmatched trips through trip
attributes, producing held-out node ROC AUC 1.0. It also constructs tract codes
from the synthetic income bin. In the original benchmark, tract equality agrees
with the same-income edge target on all 560 matched-node candidate edges. The
22-feature ablation removes exact geography equalities but retains continuous
coordinates whose fixed offsets still proxy synthetic income. The ablation
report itself documents this remaining risk.

The design lock specifies the original candidate/model settings and asserts
that no parameter was selected using held-out metrics. It does not predeclare
the later 22-feature choice as the untouched primary specification. The
22-feature result is therefore a useful post-hoc failure diagnosis, not an
independent primary validation.

The comparator is also asymmetric. The supposedly geography-equality-free
learned specification is compared with a transparent rule whose score still
includes pickup/drop-off area and tract equality bonuses. Equal raw `rho`
values additionally have no invariant cross-score meaning.

## 2a. Post-audit repair verification

The current suites discover 150 tests: 149 are cache independent and one uses
the pinned official UCI cache. With that cache present all 150 pass; hosted CI
records the one expected skip. In addition to the generic signed-endpoint,
missing-support, FWL, numerical-status, and Gamma repairs, they test an exact
temporal-frontier solver that jointly
tracks core/buffer matching, compiled latent labels, active capped-count release
automata, an omitted-edge budget, and an exact rational score floor. It also
tests fixed-reference score normalization and exact edge-by-edge scorer
rationalization from calibration through the dynamic program.

The locked temporal benchmark has 34 cases: 32 applicable exhaustive-oracle
agreements, 24 analytic agreements, 16 resolved numerical HiGHS agreements,
and one certified outward-relaxation check. The committed unit suite includes
80 seeded exact-DP brute-force instances and 40 seeded relaxation
inclusion/witness checks. The separate joint-solver audit agrees on status for
250/250 instances and endpoints for all 185 feasible instances.

The controlled matching-set benchmark still uses direct edge truth in synthetic
source/calibration markets. Its primary evaluator uses exact decimal-rational
membership over all 10,395 perfect matchings per market; a separate
reconstruction reproduces its 44 radius/scorer frontier rows and headline counts.
The explicit-DNF LOW/HIGH release compiler additionally passes exact
projection/restoration and lifecycle tests; an independent 1,000-instance
randomized lifecycle-parity probe found no mismatch. A bounded 23-case capacity
profile resolves 22 cases and retains one degree-five timeout as unresolved.
The exact component layer agrees in 160/160 same-kernel and 192/192 independent
exhaustive-oracle configurations, replays 682 decomposed endpoint witnesses,
and rejects candidate-graph-only splitting with a shared-factor counterexample
(false upper 1 versus correct upper 11). The Chicago adapter and synthetic
production harness contribute 14 and 23 fail-closed contract tests,
respectively.
These checks verify declared finite-instance behavior only. They do not
establish a truth-containing Chicago graph, City implementation fidelity, a
production temporal order, or transfer of synthetic calibration.

The external audit executes two deliberately different roles. The all-ten UCI
Krebsregister audit reconciles 5,749,132 unique candidate pairs and 20,931
positives. Its adjudicated entity relation is not a matching: 8,675 records
have positive degree above one. The ten files are overlapping edge partitions,
not markets. A disclosed truth-conditioned reduction retains 10,297 global
dyads and 249,048 induced candidate edges. Its postal truth is
`9922/10297`; verified Blossom gives the exact upper endpoint `9924/10297`,
but the lower endpoint exceeds the predeclared 120-second limit and remains
unresolved. No complete frontier, width, or containment claim is reported.
FEBRL4 supplies external synthetic one-to-one mechanics; six-pair exhaustive
and 20-pair numerical score-free frontiers both contain truth. UCI blocking
recall and natural exchangeable markets remain open.

## 3. Real-data evidence

The only committed Chicago rows are a deterministic 1/256 trip-ID-prefix
sample spanning December 9, 2025 through February 2, 2026:

| Prefix audit item | Result | Permitted use |
|---|---:|---|
| All trips | 53,241 | Schema and aggregate diagnostics |
| Authorized shared service | 3,048 (5.72%) | Node-label/software check |
| Matched transactions | 2,146 (4.03%) | Aggregate field check only |
| Missing pickup tract | 38.05% | Suppression audit |
| Candidate edges in prefix | 151 | Negative support check |
| Supported authorized nodes | 246 / 3,048 (8.1%) | Demonstrates unusability for pairing |

Under independent prefix sampling, the other member of a two-transaction run
is absent with probability approximately 255/256. The prefix therefore cannot
be used to calibrate a candidate graph, reconstruct partners, estimate an
endpoint range, or validate edge scores.

No complete-day Chicago matching output, missing-context bound, production
runtime, or policy coefficient is present. External relation truth is now
present only in the all-ten-UCI/FEBRL roles described above; it does not supply
Chicago partner truth.

## 4. Gate matrix

| Gate | Required evidence | Current status | Consequence |
|---|---|---|---|
| Field semantics | Target agrees with official definitions | **Pass in method draft** | Hidden object is partner identity within conditionally run-closed realized K=2 co-presence |
| Chain-complete node population | Boundary-buffered rows contain both members of every included run | **Fail** | No valid exact-cover population yet |
| Candidate outer support | Every true edge satisfies necessary public-data constraints | **Fail** | Current min/max is graph-conditional sensitivity only |
| Candidate recall validation | Independent real or realistic pair truth | **Partial** | All-ten UCI supplies real topology but not blocking recall; FEBRL4 is synthetic |
| Exact-cover solver correctness | Exhaustive agreement on small instances | **Pass** | Small-instance optimization logic is supported |
| Endpoint terminology | Distinguish attained endpoints from exact attainable set | **Pass in current method draft** | Paper states attained endpoints and denies scalar interpolation |
| Missing context | Exact-cover all target nodes before handling suppression | **Method pass / Chicago fail** | Generic DNF/count coupling exists; production null causes and rows are absent |
| Node score objective | Coherent likelihood or explicit composite loss | **Fail** | No edge-probability claim |
| Score ambiguity radius | Invariant definition plus calibration | **Pass conditionally in method/code** | Fixed-reference matching regret is exact and nested; Chicago calibration markets are absent |
| Independent score validation | Untouched markets and edge truth | **Fail** | AI can only be presented as optional sensitivity scoring |
| Temporal algorithm correctness | Exact endpoints/witnesses and explicit complexity boundary | **Pass on declared small instances** | Reference implementation and weak-hardness boundary are supported |
| Production computation | Complete-day compiler, runtime, memory, frontier size, and fallback policy | **Partial** | Generic compiler, exact component engineering, declared Chicago handoff, synthetic production harness, and bounded profile pass; real schedule width is untested |
| All-trip policy denominator | Download contains all completed TNP trips | **Fail** | Current authorized-only downloader cannot estimate `/all` rates |
| Policy treatment encoding | Pickup or drop-off, day-of-week schedule, correct zone transition | **Fail** | Current proposed treatment requires repair |
| Global coefficient propagation | Optimize the actual signed linear contrast over one global matching | **Fail, theorem available** | Day/block endpoint regressions are invalid |
| Causal identification | Fixed target population, pretrends, spillovers, inference, robust support | **Fail** | No ITT or DDD conclusion |
| Submission layout | Eight-page main text, disclosures, references after page 8 | **Pass** | Format does not cure scientific gaps |

## 5. Minimum production evidence package

The following are necessary before any substantive empirical claim:

1. all-trip extracts for policy denominators and separate boundary-buffered,
   chain-complete authorized/matched extracts for linkage;
2. a verified (Y=1,K=2) cohort with duplicate, consistency, midnight, and
   outer-boundary audits;
3. a necessary-condition coverage graph and separately declared spatial/cap
   sensitivities;
4. all-node exact cover with missing-context bounds;
5. solver certificates separating optimal, feasible-with-gap, infeasible,
   timeout, and error;
6. independent realistic or real edge truth for candidate and score coverage;
7. a new frozen validation suite not used to choose the 22-feature repair;
8. a fixed all-trip policy design and global coefficient optimization;
9. descriptive language unless the separate causal assumptions and diagnostics
   pass;
10. privacy review that releases only aggregate endpoint ranges and diagnostics.

## 6. Empirical disposition

- Exact temporal method artifact: **PASS on declared finite instances**.
- Generic release compiler: **PASS for explicit DNF inputs; external semantics not certified**.
- External validation: **PARTIAL PASS** (all-ten UCI topology and exact upper endpoint; lower/full frontier, blocking recall, and natural markets open; FEBRL4 method fit).
- Certified outward score relaxation: **PASS as a bicriteria certificate; not a query FPTAS**.
- Software pilot: **PASS with documented counterexamples**.
- Synthetic scientific validation: **FAIL**.
- Chicago structural estimate: **FAIL / not run**.
- AI sharpening claim for Chicago: **FAIL / uncalibrated**.
- Policy effect: **FAIL / not run and current estimand invalid**.
- KDD Research development: **CONDITIONAL GO**; run-closed production
  compilation, a complete external frontier and natural market units,
  multi-size validation, and Chicago implementation verification remain
  indispensable.

## Status

The frozen numerical outputs and post-audit method implementation have been
independently reproduced and audited as described above. Current-linked City
documentation now supports the high-level suppression rule, while snapshot
stability, implementation/null-cause fidelity, candidate coverage,
real-market calibration, production scalability, and every Chicago scientific
or policy result remain unresolved.
