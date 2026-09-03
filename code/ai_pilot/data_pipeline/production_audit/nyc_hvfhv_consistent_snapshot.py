"""Consistent candidate-snapshot extraction for NYC HVFHV decision audits.

The legacy extractor fetched a provisional core and a candidate universe through
separate queries, then re-counted the same universe after extraction. Public
API timeouts and tie-level response changes could therefore create a technical
core/candidate mismatch even though no scientific assumption had changed.

This module chooses a provider-time core from one scan response, fetches one
candidate row snapshot, verifies that the provisional core multiset is contained
in that snapshot, and derives all later count checks from the frozen snapshot.
It does not change the candidate predicate, ordering, or outcome-blind selection
rule.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import nyc_hvfhv_smoke_fetch as raw


def choose_and_fetch(args: Any) -> dict[str, Any]:
    start = raw.required_dt(args.scan_start)
    end = raw.required_dt(args.scan_end)
    order = (
        "pickup_datetime, dropoff_datetime, hvfhs_license_num, "
        "pulocationid, dolocationid"
    )
    considered: list[dict[str, Any]] = []
    for lower_window, upper_window in raw.windows(start, end, args.scan_window_hours):
        where = (
            f"pickup_datetime >= '{raw.fmt(lower_window)}' "
            f"AND pickup_datetime < '{raw.fmt(upper_window)}' "
            f"AND {raw.TARGET} "
            "AND pickup_datetime IS NOT NULL "
            "AND dropoff_datetime IS NOT NULL"
        )
        scan_count, scan_count_api, scan_count_query = raw.count(where)
        item: dict[str, Any] = {
            "start": lower_window.isoformat(),
            "end": upper_window.isoformat(),
            "rows": scan_count,
        }
        considered.append(item)
        if scan_count < args.min_core_rows or scan_count > args.max_scan_rows:
            item["status"] = "outside_scan_caps"
            continue
        scan_rows, scan_api, scan_query = raw.select(
            raw.FIELDS,
            where,
            order,
            scan_count,
            args.max_scan_rows,
        )
        groups: dict[tuple[str, datetime], list[dict[str, Any]]] = defaultdict(list)
        for row in scan_rows:
            provider = raw.text(row.get("hvfhs_license_num"))
            pickup = raw.dt(row.get("pickup_datetime"))
            dropoff = raw.dt(row.get("dropoff_datetime"))
            if provider is None or pickup is None or dropoff is None or dropoff < pickup:
                continue
            bin_start = pickup.replace(
                minute=(pickup.minute // 15) * 15,
                second=0,
                microsecond=0,
            )
            groups[(provider, bin_start)].append(dict(row))
        ordered_groups = sorted(
            groups.items(),
            key=lambda group: (-len(group[1]), group[0][1], group[0][0]),
        )
        for (provider, core_start), provisional_core in ordered_groups:
            if not args.min_core_rows <= len(provisional_core) <= args.max_core_rows:
                continue
            core_end = core_start + timedelta(minutes=15)
            pickups = [raw.dt(row.get("pickup_datetime")) for row in provisional_core]
            dropoffs = [raw.dt(row.get("dropoff_datetime")) for row in provisional_core]
            if any(value is None for value in [*pickups, *dropoffs]):
                continue
            if any(
                dropoff < pickup
                for pickup, dropoff in zip(pickups, dropoffs)
                if pickup is not None and dropoff is not None
            ):
                continue
            lower_dropoff = min(value for value in pickups if value is not None) - timedelta(
                minutes=30
            )
            upper_pickup = max(value for value in dropoffs if value is not None) + timedelta(
                minutes=30
            )
            provider_literal = provider.replace("'", "''")
            determinate_where = (
                f"hvfhs_license_num = '{provider_literal}' "
                f"AND {raw.TARGET} "
                "AND pickup_datetime IS NOT NULL "
                "AND dropoff_datetime IS NOT NULL "
                f"AND pickup_datetime <= '{raw.fmt(upper_pickup)}' "
                f"AND dropoff_datetime >= '{raw.fmt(lower_dropoff)}'"
            )
            indeterminate_where = (
                f"hvfhs_license_num = '{provider_literal}' "
                f"AND {raw.TARGET} AND "
                "(pickup_datetime IS NULL OR dropoff_datetime IS NULL)"
            )
            determinate_count, determinate_count_api, determinate_count_query = raw.count(
                determinate_where
            )
            indeterminate_count, indeterminate_count_api, indeterminate_count_query = raw.count(
                indeterminate_where
            )
            if (
                determinate_count + indeterminate_count > args.max_candidate_rows
                or indeterminate_count > args.max_indeterminate_rows
            ):
                continue
            determinate_rows, determinate_api, determinate_query = raw.select(
                raw.FIELDS,
                determinate_where,
                order,
                determinate_count,
                args.max_candidate_rows,
            )
            indeterminate_rows: list[dict[str, Any]] = []
            indeterminate_api = "none"
            indeterminate_query = ""
            if indeterminate_count:
                indeterminate_rows, indeterminate_api, indeterminate_query = raw.select(
                    raw.FIELDS,
                    indeterminate_where,
                    order,
                    indeterminate_count,
                    args.max_indeterminate_rows,
                )
            candidates = [*determinate_rows, *indeterminate_rows]
            missing_core = raw.multiset(provisional_core) - raw.multiset(candidates)
            if missing_core:
                item["status"] = "candidate_snapshot_missing_provisional_core"
                item["missing_core_multiplicity"] = sum(missing_core.values())
                continue
            item["status"] = "selected"
            return {
                "provider": provider,
                "core_start": core_start,
                "core_end": core_end,
                "core_rows": provisional_core,
                "candidate_rows": candidates,
                "determinate_count": determinate_count,
                "indeterminate_count": indeterminate_count,
                "candidate_snapshot_sha256": raw.sha(candidates),
                "core_snapshot_sha256": raw.sha(provisional_core),
                "considered": considered,
                "queries": {
                    "scan_count": raw.sha(scan_count_query),
                    "scan": raw.sha(scan_query),
                    "core_count": raw.sha("derived from frozen scan snapshot"),
                    "core": raw.sha("provisional core retained from frozen scan snapshot"),
                    "determinate_count": raw.sha(determinate_count_query),
                    "determinate": raw.sha(determinate_query),
                    "indeterminate_count": raw.sha(indeterminate_count_query),
                    "indeterminate": raw.sha(indeterminate_query),
                },
                "apis": {
                    "scan_count": scan_count_api,
                    "scan": scan_api,
                    "core_count": "derived_from_scan_snapshot",
                    "core": "derived_from_scan_snapshot",
                    "determinate_count": determinate_count_api,
                    "determinate": determinate_api,
                    "indeterminate_count": indeterminate_count_api,
                    "indeterminate": indeterminate_api,
                },
                "where": {
                    "determinate": determinate_where,
                    "indeterminate": indeterminate_where,
                },
            }
    raise raw.LiveDataError(
        "no scan window produced an integrity- and cap-qualified core"
    )
