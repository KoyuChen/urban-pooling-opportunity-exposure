# Complete-day download status

Status checked: 2026-08-25/26 in the provided execution environment.

## Result

The complete-day source extraction could not be executed from this sandbox.
No complete-day file or row count is claimed. The zero-byte `.part` file
created during the blocked attempt was removed; no partial download is retained
or presented as data.

## Reproducible diagnostics

1. The same official City of Chicago source and schema already used by the
   feasibility audit were verified: dataset `6dvr-xwnh`, **Transportation
   Network Providers - Trips (2025-)**.
2. A command-line request to the SODA3 query endpoint stalled before returning
   even the server-side `count(*)`; the sandbox reports restricted network
   access for `data.cityofchicago.org`.
3. A direct Cloud Browser request to the SODA3 endpoint returned
   `net::ERR_BLOCKED_BY_CLIENT`.
4. The requested SODA2 `/resource/6dvr-xwnh.json` fallback produced the same
   `net::ERR_BLOCKED_BY_CLIENT` result.
5. The public dataset's human-readable page was accessible and confirmed that
   the table was last updated on July 24, 2026, but its Data grid remained at
   `Loading...`, consistent with the API request being blocked in this browser.

This is an execution-environment egress restriction, not evidence that the
City dataset is unavailable.

## Prepared extraction

`fetch_complete_authorized_days.py` is ready to run in an environment that can
reach the City API. It:

- requests every `shared_trip_authorized = true` row for 2025-12-16 and
  2026-01-13;
- uses a conservative 5,000-row page size;
- tries SODA3 first and automatically falls back to SODA2;
- verifies each file against a fresh server-side `count(*)`;
- writes files atomically and refuses incomplete downloads;
- produces per-day CSVs, a combined gzipped CSV, `manifest.json`,
  `quality_summary.json`, and `QUALITY_REPORT.md`;
- audits duplicate trip IDs, requested-day boundaries, authorization and match
  flags, `trips_pooled` inconsistencies, and OD-location missingness.

Run from the project root:

```bash
python urban_pooling_data/ai_pilot/data_pipeline/fetch_complete_authorized_days.py
```

Optionally set `SOCRATA_APP_TOKEN` to reduce unauthenticated API throttling.

## Safe interim use

The existing `chicago/raw/tnp_policy_window_prefix_00.csv` can be used only for
schema/unit-test smoke tests and aggregate-rate checks. It must **not** be
relabeled as a complete-day candidate graph: sampling by one two-character
trip-ID prefix omits almost every possible co-rider counterpart.
