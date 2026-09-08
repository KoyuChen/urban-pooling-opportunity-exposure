# Next EventFrontier research gate

Decision date: 2026-09-08. Baseline evidence commit:
`3e2427074797c5c48995b8bd3bcc2c91dd51f5e3`.

## D1--2 execution update, 2026-09-08

The declared 4+12 structural comparison is complete; aggregate evidence is in
`code/ai_pilot/data_pipeline/results/nyc_hvfhv/structure_audit_20260908/`.
The new, count-reconciled extraction contains 38 source cores and 437 candidate
rows before the fixed reduction. It is not asserted to be byte-identical to the
historical scale instance. All nine family/capacity cells and 36 outcome pairs
are certified, with 117 support and 72 endpoint MILP checks and witness replay.

**No fixed-q comparison changes an endpoint (0/24).** At q=2 and q=4, all
possible buffer subsets are feasible in all families. Ordered and clique
columns are identical at each capacity: 54, 394 and 1,719 columns. All 16 input
intervals share 14 seconds; the overlap graph is complete. Thus the small
instance cannot exercise the connected-non-clique aspect of the ordered model.
Larger maximum support at C=3,4 distinguishes multi-member events from pairs,
but does not demonstrate a fixed-q outcome advantage for sequential events.

Execution/verification gate: **PASS**. Public structural-advantage evidence:
**HOLD**. Preserve the null result; do not enlarge or change rows until an
effect appears. Before new endpoint solves, the next task is to freeze an
outcome-blind geometry census on the already declared NYC decision-panel
calendar: common-overlap/complete-clique status, non-clique connected-event
availability, source counts and all failure statuses. Retain every declared
window, including geometrically uninformative ones. This is a diagnostic
design update, not a fresh independent holdout. It has not been run yet.

The work packages below remain the longer plan. The geometry census now comes
immediately before further D1 endpoint comparisons. Chicago's 96-window
calendar remains fixed and unstarted; its recovery-controller work is still
pending, with no new Chicago results inferred from this NYC audit.

## Target and current boundary

Build the case that temporal-event structure changes which aggregate conclusions
are justified, and that the resulting certificates are informative under stated
support assumptions. The present evidence supports continued KDD development;
it does not yet establish a decisive novelty or utility advantage.

Chicago's pilot has 23 completed windows, one scientifically ineligible window
and zero execution failures. Its 2,744 data-complete endpoint pairs are certified;
686 additional pairs lack public query values. ATR supplies annotated dyad
relations, but the strongest public/annotated large candidate graphs are still
the two-row special case. The ordered-event branch-and-price evidence closes a
single 18-cell nested-size lattice through 16 cores plus 48 buffers.

The existing controlled benchmark already compares pair matching and connected
components. Repeating those deliberately sequential synthetic examples would
not resolve whether ordered-event structure matters on public instances.

## Work order and deliverables

Days below are work packages, not promises about live-service or queue timing.

| Order | Work | Deliverable | Decision after the result |
|---|---|---|---|
| D1--2 | Public-instance structural comparison | One table comparing ordered events, exactly-two-row events, and clique-constrained events on identical inputs | Keep ordered structure central only to the extent that its effect is demonstrated; equality or a small effect must remain visible |
| D3--4 | Recoverable 96-window Chicago follow-up | Frozen calendar, controller, first 12-window batch, then seven further fixed batches | Separate transport completion, eligibility, numerical certification and scientific informativeness |
| D5 | Aggregate informativeness analysis | Support-versus-width profiles, full missingness denominators, point disagreement and threshold sensitivity where specified | Determine whether the intervals support useful conclusions or mainly diagnose lack of identification |
| D6--7 | Align theory, literature and manuscript | Closest-work comparison, revised claim-to-evidence table, rebuilt TeX/PDF | Decide whether the evidence supports a KDD main-track submission narrative |

The original immediate research task was the D1--2 structural comparison; its
first fixed-input result and the revised next task are recorded above. The Chicago
calendar is declared so later selection cannot follow its outcomes. Its
live execution begins only after a controller represents unstarted windows
correctly; no extra user approval is needed for this implementation gate.

## D1--2: compare the structural assumptions on the same instance

1. Start with the public exact-time 4-core/12-buffer audit instance and
   capacities 2, 3 and 4. Read the canonical scale manifest for source pins;
   the old scale-protocol Markdown is not a substitute for the manifest's six
   nested sizes. Inspect whether row-level input can be faithfully recovered.
   Aggregate reports alone cannot reconstruct an instance. If a new source
   pull is necessary, compare available fingerprints, pin it as a new audit
   snapshot, and run every comparator on that same pull.
2. Hold core/buffer roles, exact times, candidate rows, positive-overlap rule,
   capacity and public query coefficients fixed. Change only permitted event
   columns: all connected capacity-feasible events; exactly two rows; or
   pairwise-overlapping clique events. In the fixed-time setting the latter
   two are restrictions of the ordered-event family. They diagnose the
   consequences of simplifying the model, not errors in methods designed for
   a different estimand.
3. Use the existing complete-column small-instance master as the reference.
   Report reachable selected-buffer counts and maximum support for all three
   families. For outcome comparisons, enumerate every positive buffer count
   feasible in all compared families. Use the same count and the same query
   on both sides; never compare at each family's own maximum and call the
   resulting difference a fixed-estimand effect.
4. Retain counts feasible only in the full family as model exclusions. An
   infeasible restricted family is not evidence that the full family is
   infeasible. A connected-components point rule, if shown, must first pass
   capacity, core coverage and buffer-use replay; invalid outputs get an
   invalid-model status rather than an accuracy score.
5. Output model status, reachable counts, lower/upper endpoints, differences,
   number of columns excluded by each restriction, elapsed time, independent
   reference agreement and source/code hashes. Derive all headline differences
   from this table. Public data cannot support point-error or truth-coverage
   rates because event membership is unobserved.
6. Before broadening to the 6-core/18-buffer reference instance or larger
   lattice cells, assess whether full and restricted models differ on the
   declared queries. Preserve an equality result. If larger diagnostic solves
   are warranted, freeze their budgets before execution and retain valid
   anytime bounds. The existing 18/18 maximum-support certificates do not
   automatically certify new outcome comparisons.

The small diagnostic is retrospective relative to the original NYC work.
It is neither a new independent test set nor a claim about the frequency of
sequential vehicle runs. Its purpose is to connect the paper's structural
assumptions to observable changes in the feasible answers.

## D3--4: Chicago calendar and recovery contract

`CHICAGO_K2_FOLLOWUP_PROTOCOL.json` declares all 32 weekdays from January 15
through February 27, 2026 at 08:00, 12:00 and 17:30 Chicago local time: 96
windows, disjoint from the 24-window pilot. The first batch is indices 0--11,
and the remaining seven batches follow consecutive indices. All dates are
chosen after the pilot; this is a calendar extension, not a pristine holdout.
It retains the pilot's eligibility caps, support curves, query definitions
and 60-second endpoint budget, using the verified indexed-count transport.

The current single-window driver accepts this protocol, for example:

```bash
python code/ai_pilot/data_pipeline/production_audit/run_chicago_k2_fixed_panel.py \
  --protocol code/ai_pilot/data_pipeline/production_audit/CHICAGO_K2_FOLLOWUP_PROTOCOL.json \
  --window-index 0 --indexed-count-transport \
  --output-dir tmp/chicago-k2-followup/batch-00-attempt-01
```

The command is an execution entrypoint, not a record that it has been run.
The old recovery workflow is tied to the completed 24-window pilot and must
not be silently redirected to this new panel. A staged controller must first:

- verify the declared calendar and protocol/code hashes;
- distinguish unstarted windows from attempted failures and scientific exclusions;
- retain independent per-window reports and every failed attempt;
- leave completed scientific results untouched, including unresolved endpoints;
- retry only failed transfers at the same date/time; and
- produce a complete panel ledger after each batch, with all 96 windows present.

Batch pauses may address data integrity, access or compute failures. They must
not select dates or suppress results based on frontier width or a preferred
scientific outcome. Any protocol revision receives a new version and explicit
deviation record. Combining pilot and follow-up gives 120 declared windows,
not automatically 100 eligible cohorts or hundreds of independent cohorts.

## D5: usefulness and dependence

Report every fixed query/support curve separately, with per-window widths and
endpoint changes. Missing fares remain an explicit missing-value family;
certification among complete cases must not be reported as certification of all
requested queries. Keep pilot and follow-up summaries separate before pooling.
Thousands of query/radius cells are repeated evaluations on a small number of
windows, not thousands of independent datasets. Display date/time strata.

Additional threshold analyses require a frozen specification before viewing
the follow-up outcomes. Use either a documented substantive threshold or a
complete prespecified threshold profile. Candidate-median results can remain
descriptive, but cannot alone establish operational usefulness. Do not choose
the thresholds that maximize either ambiguity or certification after solving.
On ATR, evaluate wrong certificates only against the annotated reference and
retain the support-misspecification, oracle-cardinality and touched-day caveats.

## D6--7: the paper's defensible increment

The closest direct comparison is Turkcapar and Krishnan (2023),
[Quantifying Uncertainty in Aggregate Queries over Integrated Datasets](https://arxiv.org/abs/2309.05178).
Aggregate lower/upper answers over uncertain matchings already exist. Also
compare the possible-worlds perspective to Hua and Pei (2012),
[Aggregate Queries on Probabilistic Record Linkages](https://www.openproceedings.org/2012/conf/edbt/HuaP12.pdf).
These are not identical problem settings; state what transfers, what requires
a structural adapter, and what the original method does not claim to solve.

Emphasize the specific ordered-event formulation and integral rooted pricing
primitive if their modeling and computational value is established. Keep the
fixed-exact-time oracle distinct from the continuous timestamp-completion
model. Matching equivalence, set nesting, threshold crossing and the basic
alternating-path identity are foundations and explanatory tools; theorem labels
alone do not make them independent novelty claims.

Use a claim-to-evidence table: controlled truth checks logic; ATR audits
annotated support failure and transfer; Chicago checks public temporal
candidate closure and sensitivity; NYC checks ordered-event computation and
timestamp/capacity effects. In particular, neither ATR dyads nor Chicago's
two-row matching panel validates general ordered-event city-scale performance.

## Stop or refocus criteria

- If structural restrictions barely change the declared public answers, reduce
  their empirical headline weight and report the null result.
- If complete-support frontiers remain largely uninformative across the fixed
  threshold profile, retain the non-identification finding; a practical decision
  advantage then needs additional evidence, not more successful solver runs.
- If support transfer only works with annotation-assisted exclusions or fixed
  cardinality, describe that dependence. Do not transfer ATR coverage guarantees
  to Chicago/NYC candidate construction.
- If direct comparison leaves only standard matching plus familiar bounds,
  narrow the contribution and reassess the main-track narrative before adding
  cities, model variants or long branch-and-price campaigns.

At this declaration the new 96-window panel has no experiment results. The
existing paper and frozen evidence remain the baseline for assessment.
