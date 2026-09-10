# Chicago follow-up batch 1: September 10, 2026

## Frozen launch

- Parent code revision: `160b7ebfc3e7cec9575c1886cc277fe4d24410e8`.
- Parent CI: https://github.com/KoyuChen/urban-pooling-opportunity-exposure/actions/runs/34328127844 (success, checked September 10).
- Seed run: `34298803324`; artifact `10084804589`,
  `chicago-k2-followup-checkpoint` (not expired when checked).
- Seed archive SHA-256:
  `6d616909ae04d963aa801a593c6f0cef20fcc23478f7f5eecf92a4fe720c6fcf`.
- Seed `checkpoint.json` SHA-256:
  `6f6f67a0a1939dbbad7f5d4b3e56f47222eef2b98c16131ced73598078bd1caa`.
- All 235 pinned files, the protocol and producer hashes were verified locally.
- Selected indices: 12 through 23, in the existing frozen calendar. These are
  January 21, 22, 23 and 26 at 08:00, 12:00 and 17:30 local time.
- No eligibility, query, candidate-support, endpoint budget or solver change.
- Four concurrent workers; the existing 180-minute per-job limit is unchanged.

The first batch's 10 completed and two ineligible records are carried forward.
Its eight unresolved duration-gap endpoint pairs remain unresolved. A
record-terminal predecessor gate does not imply all its numerical endpoints
are certified. Ineligible windows are never replaced by other dates.

## Trigger and safeguards

The current connection has no workflow-dispatch operation. This launch uses
the repository's existing workflow-file push trigger with the explicit commit
marker `[chicago-followup-batch-1]`. The marked push restores the pinned seed,
checks its hash, then invokes the existing sequential batch controller.
Ordinary later workflow edits without the marker do not launch computation.
Manual workflow dispatch remains available with explicit batch and resume inputs.

The controller must return exactly indices 12--23 for this seed. It aborts if
any earlier window lacks a reusable terminal record or if frozen code/evidence
has changed. Each cohort uploads its attempt independently; aggregation keeps
the entire 96-window denominator and records missing artifacts as failures.

No new completion count or scientific Gate improvement is asserted by this
launch note. Queued/running jobs are not completed evidence. The next priority
is to verify the resulting aggregate checkpoint and retry only transport or
artifact failures before advancing to batch 2.

## Reproduce the preflight

With the original checkpoint archive extracted to `tmp/batch0-checkpoint`:

```
python code/ai_pilot/data_pipeline/production_audit/chicago_k2_followup.py \
  --checkpoint-dir tmp/batch0-checkpoint --batch-index 1 \
  --plan-output tmp/chicago-batch1-plan.json
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests \
  -p 'test_chicago_k2_followup.py' -v
```

Preflight returns 12 selected windows and no reused windows within batch 1.
The prior 12 windows are preserved by checkpoint restoration, not refetched.
