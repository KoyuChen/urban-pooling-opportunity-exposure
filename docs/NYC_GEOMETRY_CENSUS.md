# Outcome-blind NYC temporal geometry census

The fixed 4+12 audit found no endpoint change in 24 comparisons because all 16
intervals shared a common intersection. This census checks whether that geometry
also characterizes the full candidate universes of the existing NYC panel.
It does not choose new dates or run another outcome optimizer.

`NYC_GEOMETRY_CENSUS_PROTOCOL.json` freezes the exact historical 24-cell calendar,
recovered from source commit `a864c8a6d48da3d4d8221dd01b32c011d935f7ea`.
There are 20 distinct scan periods and four repeated evening stress periods.
Each cell keeps its original 8- or 16-core minimum and selection rule. The
source projection contains only provider, pickup/dropoff times, zone fields
used in the fixed source ordering, and the shared-match flag. Outcome fields
and their missingness do not enter selection.

Two views are reported for every qualified extraction:

1. The first 8/16 valid exact-time cores and all other valid temporal candidates.
2. The first four cores and twelve nearest temporal candidates, with remaining
   original cores made optional buffers. This time-only reduction differs from
   the earlier complete-outcome 4+12 selection and is labeled accordingly.

Indeterminate and nonpositive-duration omissions are counted. Too few valid
cores is a scientific exclusion; fractional-second timestamps are outside the
protocol and are not rounded. Each successful extraction repeats source counts
and metadata checks. These are new snapshots, not assumed copies of old inputs.

## Exact event-column geometry

For positive integer-second intervals and overlap epsilon one second, a
three-vertex induced path has two overlapping pairs and one disjoint pair.
It is connected, is not a clique, and has peak occupancy two. If it touches a
core, it is therefore an admissible non-clique event column for every C >= 2.

Conversely, take any connected non-clique event containing a core v. If v is
not adjacent to every other vertex, the first three vertices of a shortest path
from v to a nonneighbor form a core-incident induced path. If v is universal,
choose two nonadjacent vertices; together with v they form such a path.
Thus core-incident induced-path availability is equivalent to non-clique
event-column availability here. This elementary graph fact is a diagnostic
tool, not a new algorithmic contribution claim.

The implementation counts all such paths with adjacency bitsets and checks
existence independently via non-clique connected components containing a core.
A returned path is replayed directly against its intervals, and only its hash
is retained. Random tiny tests compare the count with independent enumeration
of every three-row subset.

**An available event column need not extend to a feasible full world.** An
isolated second core is a counterexample. Therefore this census does not
certify full-world feasibility, an endpoint effect at fixed q, true vehicle
events, realized capacity or population prevalence.

## Execution and recovery

The existing `nyc-bp-24h.yml` workflow now defaults to geometry when manually
dispatched and runs geometry on changes to that workflow. Historical
branch-and-price follow-ups remain available only through the explicit
`branch-price` mode, because their four formerly open cells are already closed.

The geometry campaign has at most four parallel jobs, each with a 15-minute
extraction deadline inside a 20-minute job. Every attempt writes an aggregate
checkpoint; the summary retains all 24 cells, even if reports are missing.
To resume a failed transfer, dispatch geometry with `resume_run_id` equal to the
previous run. Completed and scientifically excluded cells are reused after
protocol/code checks. An interrupted `IN_PROGRESS` record requires explicit
diagnosis; it is not silently counted as a failed scientific instance.

Local single-cell execution and aggregation:

```bash
python code/ai_pilot/data_pipeline/production_audit/nyc_geometry_census.py \
  --window-index 0 --output-dir tmp/nyc-geometry/window-0
python code/ai_pilot/data_pipeline/production_audit/nyc_geometry_census.py \
  --input-dir tmp/nyc-geometry --output-dir tmp/nyc-geometry-summary
```

`SUMMARY.json`, `WINDOWS.csv`, `REPORT.md`, `RESULTS.tex` and `MANIFEST.json`
are aggregate-only outputs. PASS requires every declared cell to terminate in
an admissible status and all completed extracts to share one release
fingerprint. Failure, unstarted and incomplete states remain HOLD. Even PASS
establishes geometry only; any outcome comparison needs its own fixed protocol
and full-world feasibility verification.
