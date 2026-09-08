# Chicago K=2 fixed-panel protocol

The panel is the Cartesian product of eight weekdays from 2026-01-05 through
2026-01-14 and three local start times (08:00, 12:00, 17:30), producing 24
released 15-minute core bins. The rule is fixed before row counts, feasibility,
runtime, or frontier outcomes are inspected. A failed or ineligible window is
reported and never replaced.

Each cohort uses `--core-start`, the boundary-complete public temporal envelope,
the declared radius curve, measured-spatial Gamma, boundary padding at 0 and 15
minutes, and a generic candidate-omission Gamma. The latter counts selected
core incidence through edges excluded at padding zero but admitted by the
complete 15-minute envelope. It includes edges with missing geography and is
therefore distinct from the measured out-of-radius curve.

The workflow stores one fail-closed artifact per cohort and a panel aggregate.
Only endpoints with two replayed optimal MILP solutions are certified. Missing
reports, fixed-core drift, time limits, and resource-cap exclusions retain
separate statuses.

This is a public-data certification panel, not a probability sample, hidden-run
recovery study, partner-recall benchmark, or Chicago population estimate.

## Verified initial checkpoint, 2026-09-07

The first panel run, `34048658431` at source commit
`a8a3f4cb3861d30612bcd1db9145134e9b1b566d`, produced 19 completed windows,
one scientifically ineligible fixed core (index 21), and four transport
failures (indices 0, 12, 20, 23). Reaggregating its compact JSON reports with
their companion sensitivity CSVs gives 2,830 endpoint pairs: 2,264 certified,
566 ineligible because a public query value is missing, and zero
computationally unresolved. The data-complete endpoint rate is 100%.
These are the initial 19-window results, not new results from a retry.

`code/ai_pilot/data_pipeline/results/chicago_k2_fixed_panel/INITIAL_CHECKPOINT.json`
pins the original 24 artifact IDs and archive digests, 447 extracted file
hashes, the protocol, and all three extraction/solver runner files. The
archive digests were checked against GitHub's artifact metadata before this
manifest was created. The accompanying `initial_panel_*` files contain the
corrected aggregate; they do not replace the frozen manuscript evidence.

At that checkpoint the pilot was **PARTIAL / HOLD** because four
transport-failed windows lacked terminal scientific records. The broader scale
gate also remained open: 19 completed windows do not establish a benchmark
with hundreds of cohorts.

## Three recovered windows through 2026-09-08

The local retry of index 0 (`2026-01-05T08:00`) completed with 47 core rows,
445 buffer rows and 18,334 temporal edges. Count closure is PASS; the 150
endpoint pairs comprise 120 certified and 30 missing-public-value pairs,
with zero computationally unresolved. It used the same pinned extraction and
solver source and the same metadata fingerprint as the initial records.

`local_retry_20260907/` preserves the unmodified report, endpoint CSV and driver
with a checkpoint manifest. The compact record excludes only derived plots.
GitHub recovery run `34074653956` independently completed index 23
(`2026-01-14T17:30`): 74 core rows, 590 buffer rows and 33,777 temporal edges,
with count closure PASS. Its 150 endpoint pairs comprise 120 certified and 30
missing-public-value pairs, again with zero computationally unresolved. The
record and artifact digest are pinned under `github_retry_34074653956/`.
Indices 0, 12 and 20 remained transport failures in that GitHub checkpoint;
workflow-level success does not relabel them as scientific success.

GitHub recovery run `34175478785` then completed index 20
(`2026-01-13T17:30`): 60 core rows, 551 buffer rows and 24,274 temporal edges,
with count closure PASS. Its 150 endpoint pairs again comprise 120 certified,
30 missing-public-value and zero computationally unresolved pairs. The record
and artifact digest are pinned under `github_retry_34175478785/`.

The committed `latest_panel_*` aggregate and `LATEST_CHECKPOINT.json` now give
22 completed, one ineligible and one still failed; 2,624/3,280 certified pairs,
656 missing public values, and zero computationally unresolved. All earlier
completed and ineligible records retain their hashes. Original failure records
remain in attempt history. This is still **PARTIAL / HOLD**.

To reconstruct this exact intermediate checkpoint after the initial prepare
command below, merge
`code/ai_pilot/data_pipeline/results/chicago_k2_fixed_panel/local_retry_20260907`
as the retry directory. Verify that directory's `checkpoint.json` with
`verify_checkpoint` before merging. It is a local completed attempt; do not
attribute it to GitHub run `34074653956`. To reconstruct the current combined
checkpoint, download the `chicago-k2-panel-checkpoint` artifact from run
`34175478785`; it already incorporates the local retry through its audited
prepare step. Remaining duplicate local attempts were stopped
or cancelled; their execution records in `handoff.json` are not scientific
results.

## Resume without reselecting or overwriting cohorts

The workflow now restores a verified checkpoint, creates a dynamic matrix
containing only transport-failed windows, then merges available retry records.
It preserves completed windows byte-for-byte, including any unresolved
scientific endpoints, and retains scientific ineligibility. Recovery does not
select a window based on its frontier or replace its declared start time.

For the original checkpoint:

```bash
gh run download 34048658431 \
  --repo KoyuChen/urban-pooling-opportunity-exposure \
  --pattern 'cohort_*' --dir tmp/chicago-seed
python code/ai_pilot/data_pipeline/production_audit/resume_chicago_k2_fixed_panel.py \
  --seed-dir tmp/chicago-seed \
  --seed-manifest code/ai_pilot/data_pipeline/results/chicago_k2_fixed_panel/INITIAL_CHECKPOINT.json \
  --output-dir tmp/chicago-recovered
```

Run only the indices in `tmp/chicago-recovered/recovery_plan.json`, writing
each attempt to a fresh retry directory with the existing fixed-panel driver.
Then merge:

```bash
python code/ai_pilot/data_pipeline/production_audit/resume_chicago_k2_fixed_panel.py \
  --output-dir tmp/chicago-recovered \
  --merge-dir tmp/chicago-retries \
  --source-run-id LOCAL_ATTEMPT_LABEL
```

Each replaced transport-failure record moves to `history/<cohort>/<attempt>/`
before the new record is installed. A failed transfer remains a transfer
failure. An absent retry artifact leaves the previous failure in place.
Missing or altered evidence, changed protocol/runner code, a mismatched driver,
an incomplete sensitivity file, or missing count closure stops recovery before
the old records are replaced. A non-transport error requires investigation;
it is not automatically retried. Source artifact expiration also stops restore.

The Actions run uploads `chicago-k2-panel-checkpoint`, including all 24 active
records, the retained attempt history, hashes and provenance. For the next
manual run, set `resume_run_id` to the latest run containing that verified
checkpoint. Run `34175478785` is now the default; the initial run remains an
explicit bootstrap option. Checkpoint artifacts have 90-day retention. The
prepare job also merges the independently pinned local index 0 if it is still
absent. The dynamic matrix now contains only index 12. Workflow edits trigger a recovery run;
ordinary code or manuscript commits do not launch live data pulls. A new run
supersedes an older queued run in the same concurrency group.

Each newly successful retry must satisfy the runner's own before/after
snapshot check. Reusing an earlier window does not claim that all windows were
downloaded simultaneously or that the public source never changes. Snapshot
revision evidence remains in each report.

### Indexed-count transport fallback

Repeated attempts at indices 12 and 20 showed that their failures were in the
wide Socrata `count(*)` request, not infeasibility certificates. Index 20 later
completed through the original transport; index 12 remains open. A bounded
live probe of the identical predicates returned 612 and 611 unique-ID index
rows, respectively, without serializing the IDs. The fallback entrypoint
`live_chicago_k2_frontier_indexed_count.py` therefore replaces only aggregate
count transport with `trip_id` enumeration capped at 5,001 rows.

For a selected cohort the declared resource cap is 5,000, so any response below
5,001 is an exact enumeration. Reaching 5,001 is used only to reject the cohort
as over-cap, never as its exact population count. The same predicate is
enumerated before and after extraction; both the count and an in-memory ID-set
hash must agree. Null or duplicate IDs fail closed. Raw IDs and hashes of
individual IDs are not written. Full rows are still fetched and reconciled by
exact released-start partitions, and the graph, sensitivity queries, MILP and
protocol are unchanged.

This fallback is a transport equivalence, not a new candidate universe. Its
entrypoint hash is written into each new driver record and verified during
checkpoint merge. Existing reports retain their original runner hashes. Until
the fallback job produces a terminal artifact, index 12 remains a transport
failure rather than feasible, infeasible, or exact result.
