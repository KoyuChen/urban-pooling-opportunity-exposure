# Finish the frozen Chicago follow-up calendar

The current `HOLD_INCOMPLETE` is an execution gate: 60 of 96 declared windows
have no attempt record. It is not a statement that the 12 open endpoint pairs
are infeasible. The predecessor is run `34549243865`, artifact `10181281467`.
The downloaded ZIP, all 724 file pins, frozen producer/protocol hashes and
regenerated aggregate have been verified. The aggregate-only snapshot is in
`code/ai_pilot/data_pipeline/results/chicago_k2_followup/batch2_20260911/`.

## Evidence retained

The first 36 records comprise 31 completed and five scientifically ineligible
windows, with no execution failures. There are 4,630 endpoint pairs: 3,692
numerical optimal pairs, 926 missing-public-value pairs and 12 unresolved
pairs. Those categories and the full 96-window denominator are retained.
The original 24-window pilot remains a separate experiment.

## Continuous execution

The marked launch `[chicago-followup-complete]` resumes batch 3, indices 36--47,
from the pinned predecessor checkpoint. The next four batches cover 48--95.
All existing cohort, solver and transport budgets remain frozen; four cohort
jobs run concurrently. No result-dependent date replacement is permitted.

After each aggregate job has succeeded and uploaded its checkpoint, a separate
continuation job downloads it and verifies it again. The pure continuation
planner then either:

1. advances exactly one batch when all earlier records are terminal;
2. retries only recorded transport or missing-artifact failures, at most twice
   per batch, preserving completed/ineligible records and attempt history;
3. stops for diagnosis after non-transport failures, stale/later records,
   missing denominators, hash mismatches, or exhausted retry budgets; or
4. stops after batch 7 and reports calendar execution completion.

Each decision is uploaded before dispatch. Only the continuation job receives
`actions: write`, to invoke this same workflow with explicit batch, retry,
source-run and expected-checkpoint digest inputs. The job rejects a changed
main revision; it makes only one POST and does not retry ambiguous responses.
Workflow reruns do not auto-dispatch, and ordinary pushes do not start campaigns.
Concurrency does not cancel a running predecessor when its successor is queued.
No additional scheduled task is created.

Manual recovery uses workflow dispatch with `mode=followup`, the last verified
`resume_run_id`, the current unfinished `batch_index`, and
`continue_campaign=true`; inspect the cause before resetting a retry budget.

## Interpretation of completion

The existing gate becomes `PASS_EXECUTION` only after the complete 96-window
ledger is terminal. This does not certify every endpoint: numerical limits and
missing public values remain explicit. The current 12 limits are not rerun or
improved by this campaign. Solving them requires a separately recorded numerical
repair, with the original instance verified; the redacted checkpoints do not
contain a full reusable raw candidate-row dump. A fresh acquisition must be
matched to the original hashes before any repair can be compared or merged.

Calendar completion is also not city-scale closure, 100 eligible cohorts, or
evidence that the event model changes a real scientific conclusion. The field
model-comparison claim still requires its separate empirical gate.

## Reproduce the launch preflight

Extract artifact `10181281467` into `tmp/batch2-checkpoint`, then run:

```bash
python code/ai_pilot/data_pipeline/production_audit/advance_chicago_followup.py \
  --checkpoint-dir tmp/batch2-checkpoint --batch-index 2 \
  --output tmp/continuation-preflight.json
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests \
  -p 'test_advance_chicago_followup.py' -v
```

Expected decision: `ADVANCE_ONE_BATCH`, batch 3, indices 36--47, retry 0.
The seed digest is
`ca1b939c8d28ad5d2e01cb58a1dc03b0526bd43159c865e268b41a2172256816`.
Six continuation tests and eight existing follow-up tests pass. Workflow YAML
and embedded Python compile checks pass. A deployed configuration is not a
completed campaign; inspect actual job and artifact states before updating counts.
