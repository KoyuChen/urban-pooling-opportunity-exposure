# Chicago batch-1 audit and batch-2 launch: September 11, 2026

## Verified predecessor

- Source commit: `c73704227bbffdd37d6bd11842f986b6a46d44a7`.
- Successful source run: https://github.com/KoyuChen/urban-pooling-opportunity-exposure/actions/runs/34423799714
- Successful CI: https://github.com/KoyuChen/urban-pooling-opportunity-exposure/actions/runs/34423799606
- Checkpoint artifact: `10132962606`, `chicago-k2-followup-checkpoint`.
- Archive SHA-256: `8986a0bc56797b0275cc4e72c5746a73b738e0dfbcc78e7a56f459436ee7bda9`.
- Checkpoint SHA-256: `835f7712b052f7c47ac051df620766025c03cba35506eac362990facdc01a196`.
- All 490 evidence pins, producer pins and protocol pins verified locally.
- Regenerated aggregate equals the downloaded report, including all 96 windows.

The aggregate-only archive lives at
`code/ai_pilot/data_pipeline/results/chicago_k2_followup/batch1_20260911/`.
It includes JSON, CSV, Markdown, TeX, an unresolved-point audit and a manifest.
There are 21 completed, 3 fixed-core-ineligible and 72 unstarted windows; no
transport/artifact failures remain. Of 3,130 endpoint pairs, 2,492 are numerical
optimal pairs, 626 lack public query values, and 12 remain computationally open.
The data-complete numerical certification rate is 99.52%, not 100%.

## Unresolved audit

The eight earlier open points are index 2, January 15 evening, duration gap.
The four newly open points are index 17, January 22 evening, trip-miles gap:

| Curve | Parameter | Lower relative MIP gap | Source |
|---|---|---:|---|
| Radius | 32 km | 0.6603773585 | Direct MILP |
| Radius | temporal only | 0.7837837838 | Direct MILP |
| Gamma | 69 core incidences | 0.7837837838 | Temporal-only identity reuse |
| Buffer padding | 15 minutes | 0.7837837838 | Direct MILP |

All lower statuses are `INCUMBENT_ONLY_UNRESOLVED_LIMIT`, all upper statuses
are `OPTIMAL_NUMERICAL_MILP`. The public CSV lower/upper/width fields remain
blank for each open pair; the nonoptimal incumbent is diagnostic only.
These are four curve points, not four distinct optimization instances.
This audit does not improve any bound, rerun a solver or prove infeasibility.

## Frozen next batch

Indices 24--35 are January 27, 28, 29 and 30 at 08:00, 12:00 and 17:30.
The existing controller selects exactly these 12 indices and preserves all
earlier records. Its gate requires record-terminal predecessors, not numerical
closure of every query endpoint. The 12 unresolved pairs remain in the ledger.

There is no change to the protocol, producer, endpoint time budget, solver,
eligibility rule, radius grid, omitted-incidence grid or four-worker limit.
This connection has no workflow-dispatch operation; the existing push trigger
requires the explicit `[chicago-followup-batch-2]` marker. Ordinary edits and
older markers do not launch computation. The marked push verifies the pinned
seed checkpoint before planning. Manual dispatch still accepts explicit inputs.

Launch configuration is not evidence that workers have started or completed.
After launch, verify the remote prepare job and matrix before reporting running
status. The next task is to collect this batch, verify its checkpoint, and retry
only transport or artifact failures before advancing to batch 3.

## Reproduce

Extract the source artifact into `tmp/batch1-checkpoint`, then run:

```bash
python code/ai_pilot/data_pipeline/production_audit/chicago_k2_followup.py \
  --checkpoint-dir tmp/batch1-checkpoint --aggregate-only
python code/ai_pilot/data_pipeline/production_audit/chicago_k2_followup.py \
  --checkpoint-dir tmp/batch1-checkpoint --batch-index 2 \
  --plan-output tmp/chicago-batch2-plan.json
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests \
  -p 'test_chicago_k2_followup.py' -v
```

Gate: **HOLD_INCOMPLETE**. These numerical certificates concern the declared
public-envelope graph, not hidden-run recovery or city-scale identification.
