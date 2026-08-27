# Empirical Gate Report

## Overall status

- Chicago scientific and policy claims: **FAIL / not run**.
- KDD method artifact at reference-instance scale: **CONDITIONAL PASS**.
- Immediate submission: **FAIL** until production and external-truth gates pass.

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

The current bounds suite contains 72 passing deterministic tests. In addition
to the generic signed-endpoint, missing-support, FWL, numerical-status, and
Gamma repairs, it now tests an exact temporal-frontier solver that jointly
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
These checks verify declared finite-instance behavior only. They do not
establish a truth-containing Chicago graph, the current privacy operator, a
production temporal order, or transfer of synthetic calibration.

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
runtime, policy coefficient, or edge-truth dataset is present in the frozen
evidence.

## 4. Gate matrix

| Gate | Required evidence | Current status | Consequence |
|---|---|---|---|
| Field semantics | Target agrees with official definitions | **Fail** | Reframe from opportunity/service-chain compatibility to hidden partner identity within realized (Y=1,K=2) co-presence |
| Chain-complete node population | Boundary-buffered rows contain both members of every included run | **Fail** | No valid exact-cover population yet |
| Candidate outer support | Every true edge satisfies necessary public-data constraints | **Fail** | Current min/max is graph-conditional sensitivity only |
| Candidate recall validation | Independent real or realistic pair truth | **Fail** | Synthetic recall 1.0 is generator-specific |
| Exact-cover solver correctness | Exhaustive agreement on small instances | **Pass** | Small-instance optimization logic is supported |
| Endpoint terminology | Distinguish attained endpoints from exact attainable set | **Pass in current method draft** | Paper states attained endpoints and denies scalar interpolation |
| Missing context | Exact-cover all target nodes before handling SES suppression | **Fail** | Complete-case results can be entirely falsely paired |
| Node score objective | Coherent likelihood or explicit composite loss | **Fail** | No edge-probability claim |
| Score ambiguity radius | Invariant definition plus calibration | **Pass conditionally in method/code** | Fixed-reference matching regret is exact and nested; Chicago calibration markets are absent |
| Independent score validation | Untouched markets and edge truth | **Fail** | AI can only be presented as optional sensitivity scoring |
| Temporal algorithm correctness | Exact endpoints/witnesses and explicit complexity boundary | **Pass on declared small instances** | Reference implementation and weak-hardness boundary are supported |
| Production computation | Complete-day compiler, runtime, memory, frontier size, and fallback policy | **Fail** | Scalability and real schedule width are untested |
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

- Exact temporal method artifact: **PASS on declared small instances**.
- Certified outward score relaxation: **PASS as a bicriteria certificate; not a query FPTAS**.
- Software pilot: **PASS with documented counterexamples**.
- Synthetic scientific validation: **FAIL**.
- Chicago structural estimate: **FAIL / not run**.
- AI sharpening claim for Chicago: **FAIL / uncalibrated**.
- Policy effect: **FAIL / not run and current estimand invalid**.
- KDD Research development: **CONDITIONAL GO**; production compilation,
  external relation truth, multi-size validation, and Chicago operator
  verification remain indispensable.

## Status

The frozen numerical outputs and the post-audit exact temporal implementation
have been independently reproduced and audited as described above. The new
algorithmic result changes the venue-development decision but not the Chicago
evidence decision. Data completeness, candidate coverage, real-market score
calibration, current suppression-rule continuity, production scalability, and
every Chicago scientific or policy gate remain unresolved.
