# Public-data pipeline

`production_audit/` is the only active pipeline. It contains the Chicago and NYC
extractors, ordered-event solvers, panel/scale drivers, tests, fixtures, and
protocols used by the current paper.

`results/` contains only redacted aggregate evidence. Raw public rows and trip
identifiers are never committed.

## Chicago live audit

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

The extractor obtains a narrow overlap index and then fetches complete rows in
exact released-start and endpoint-bin shards. Every shard is count-checked and
reconciled by public `trip_id`; inconsistent duplicate payloads fail closed.
Broad `OR` pulls and full-row cross-column range queries are not used.

The successful run-164 contract is snapshot-stable and count-closed for 60
cores, 611 K=2 temporal candidates, and 50,405 all-trip endpoint-bin
contributors.

## Claim boundary

Candidate edges encode possible compatibility under the declared public
support, not realized co-membership. The pipeline does not infer null causes,
validate a city's private transformation code, recover vehicles or partners,
establish hidden-run closure, or license population/causal conclusions.
