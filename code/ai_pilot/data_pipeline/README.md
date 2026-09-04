# Public-data pipeline and claim boundary

This directory separates reusable adapters from live production audits.

- `chicago_release_adapter.py` is an offline, fail-closed handoff from declared
  Chicago release inputs to the generic release-constraint machinery. It does
  not perform network requests or infer semantics from blank values.
- `production_audit/` contains the current Chicago and NYC public-data
  extraction, temporal-candidate, fixed-support, column-generation, and
  branch-and-price audits.
- `LIVE_DATA_STATUS.md` records the current live Chicago transport pin and the
  remaining scientific limits.

## Chicago live extraction

The current release-operator entrypoint is:

```bash
python \
  code/ai_pilot/data_pipeline/production_audit/live_chicago_release_operator_audit_partitioned.py \
  --output-dir tmp/chicago-release-operator-audit \
  --core-start 2026-01-13T17:30:00 \
  --page-size 500 \
  --max-candidate-rows 5000 \
  --max-contributor-rows 100000 \
  --request-timeout 90 \
  --request-attempts 4 \
  --solver-time-limit 60
```

It first retrieves a narrow overlap index and then fetches complete rows through
exact released-start and endpoint-bin shards. Every shard is count-checked and
reconciled by public `trip_id`; duplicate IDs with inconsistent public payloads
fail closed. Broad `OR` pulls and full-row cross-column range queries are not
used.

The successful run-164 contract is snapshot-stable and count-closed for 60
cores, 611 K=2 temporal candidates, and 50,405 all-trip contributors.

## Release semantics

Only documented one-way implications are licensed. A visible fine tract may
imply that applicable endpoint cells are above the documented threshold. A
blank does not identify a LOW cell, because privacy coarsening, outside-city
locations, source missingness, and other null causes are not distinguished by
the public row alone.

The adapter and live audit therefore do not:

- infer a blank's cause;
- validate the City's private production implementation;
- recover Shared Trip IDs, vehicles, drivers, or partners;
- establish a finite spatial exclusion for an unmeasured centroid; or
- construct complete hidden runs.

## Candidate and boundary semantics

Core rows are covered exactly once; boundary buffers are optional. A temporal
candidate edge expresses possible compatibility under the declared released
support, not realized co-membership. Radius and omission-budget curves are
candidate-support sensitivities, not estimated partner-recall guarantees.

All committed outputs are aggregate and redacted. Raw rows and trip identifiers
must remain outside the repository.

## Tests

```bash
python -m unittest discover -s code/ai_pilot/data_pipeline/tests -v
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v
```
