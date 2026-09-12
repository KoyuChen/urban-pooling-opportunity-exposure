# Final Chicago batch recovery, September 12, 2026

The continuous campaign successfully traversed all remaining calendar batches,
including transport-only retries. Its final run was `34644324691` at source
revision `6b1b5ced901a61cc0b71b3d8725857d350b21c36`. All 12 cohort jobs ended,
but the aggregation job `103422592636` rejected the non-transport failure at
index 93. Job success alone never establishes scientific completion.

## Cause and bounded repair

Index 93, February 27 at 08:00, fetched candidates but returned:
`no complete, certified, monotone sensitivity query chain remains`.
This comes from `live_chicago_k2_frontier.run` after `monotonicity_audit`
returns FAIL. The exception lacks the detailed query-chain diagnostics, so it
does not establish whether the cause was missing query values, numerical
nonclosure, an actual nesting violation, or another audit failure. It is neither
transport failure nor evidence of infeasibility. No report was saved for it.

The controller formerly rejected such an attempt before merging any records,
discarding the rest of the batch from the cumulative ledger. The change accepts
driver-verified `EXECUTION_FAILED` records for preservation. It does not add
them to REUSABLE, permit automatic retries, or change any scientific gate.
The existing planner still stops for diagnosis on this record.

## Verification and result

- Seed artifact: `10283410153`, run `34644324691`.
- Seed archive SHA-256: `b067936665256c96e4c62e3379550413188629103875876c9dd4a5618d287442`.
- Seed checkpoint SHA-256: `c0a68b51332e8a49403a190223a85dd9191dcffa42d1f45ea1c5a9c5bd69d911`.
- Verified 1,862 pinned seed files, all 12 final cohort ZIP digests and all drivers.
- Merged checkpoint: 2,096 pinned files; frozen producer/protocol checks pass.
- Final ledger: 89 completed, 6 ineligible, 1 execution failure, 0 unstarted.
- Endpoint pairs: 10,608 numerical optimal, 2,598 missing-public-value, 34 unresolved.
- Gate: HOLD_INCOMPLETE. The failed window contributes no endpoint counts.

The aggregate snapshot, manifest, original failure and per-point unresolved
audit are stored at
`code/ai_pilot/data_pipeline/results/chicago_k2_followup/final_recovery_20260912/`.
The `[chicago-followup-recover-final]` push runs only a one-shot artifact remerge
and checkpoint upload. It neither relaunches the cohort campaign nor refetches
successful scientific records. A green recovery job is not a green science gate.

## Reproduction

Download the seed checkpoint and the 12 `cohort_*` artifacts from the source
run; extract them to the checkpoint directory and separate attempt subfolders.

```bash
python code/ai_pilot/data_pipeline/production_audit/chicago_k2_followup.py \
  --checkpoint-dir tmp/sep12-checkpoint --merge-dir tmp/sep12-attempts \
  --expected-indices-json '[84,85,86,87,88,89,90,91,92,93,94,95]' \
  --source-run 34644324691
```

Use the untouched seed before reproducing a merge; merging the same attempt
again would add another provenance/history record. Next, diagnose index 93
under the same scientific specification while capturing failure-time audit
details in a separate attempt. A new acquisition is not claimed to be identical
to the old input without matching hashes. Do not mark an unresolved or failed
cell ineligible merely to obtain PASS_EXECUTION.
