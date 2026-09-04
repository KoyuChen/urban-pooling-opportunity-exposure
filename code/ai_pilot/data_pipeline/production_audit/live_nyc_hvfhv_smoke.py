#!/usr/bin/env python3
"""NYC HVFHV public-data smoke test for latent shared-ride linkage.

This is deliberately a Gate-0/1 diagnostic, not a partner reconstruction.
NYC publishes one row per passenger trip plus shared_request_flag and
shared_match_flag, but no public co-rider/run identifier or pool size. The
script therefore measures candidate multiplicity under nested public support
rules and never imposes K=2 or degree-one matching.

Default source is the official TLC monthly Parquet file. DuckDB uses HTTP
range reads so the workflow does not need to materialize the full month.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import duckdb

DEFAULT_URL = (
    "https://d37ci6vzurychx.cloudfront.net/trip-data/"
    "fhvhv_tripdata_2026-05.parquet"
)
PROVIDERS = {
    "HV0003": "Uber",
    "HV0004": "Via",
    "HV0005": "Lyft",
    "HV0002": "Juno",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def scalar(connection: duckdb.DuckDBPyConnection, sql: str) -> Any:
    row = connection.execute(sql).fetchone()
    return None if row is None else row[0]


def qstr(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run(args: argparse.Namespace) -> dict[str, Any]:
    connection = duckdb.connect()
    connection.execute("INSTALL httpfs; LOAD httpfs")
    url = qstr(args.url)
    schema = connection.execute(
        f"DESCRIBE SELECT * FROM read_parquet({url})"
    ).fetchall()
    fields = [str(row[0]).lower() for row in schema]
    required = {
        "hvfhs_license_num",
        "request_datetime",
        "pickup_datetime",
        "dropoff_datetime",
        "pulocationid",
        "dolocationid",
        "trip_miles",
        "trip_time",
        "base_passenger_fare",
        "driver_pay",
        "shared_request_flag",
        "shared_match_flag",
    }
    missing = sorted(required - set(fields))
    if missing:
        raise RuntimeError(f"missing required HVFHV fields: {missing}")

    provider_filter = (
        ""
        if args.provider == "all"
        else f"AND hvfhs_license_num={qstr(args.provider)}"
    )
    base_where = f"shared_match_flag='Y' {provider_filter}"
    total = int(
        scalar(
            connection,
            f"SELECT count(*) FROM read_parquet({url}) WHERE {base_where}",
        )
    )
    provider_counts = connection.execute(
        f"SELECT hvfhs_license_num, count(*) n FROM read_parquet({url}) "
        "WHERE shared_match_flag='Y' GROUP BY 1 ORDER BY n DESC"
    ).fetchall()
    flag_counts = connection.execute(
        f"SELECT shared_request_flag, shared_match_flag, count(*) n "
        f"FROM read_parquet({url}) GROUP BY 1,2 ORDER BY n DESC"
    ).fetchall()

    bins = connection.execute(
        f"""
        SELECT date_trunc('minute', pickup_datetime)
               - (extract(minute from pickup_datetime)::INTEGER % 15)
                 * INTERVAL 1 MINUTE AS bin_start,
               hvfhs_license_num,
               count(*) AS n
        FROM read_parquet({url})
        WHERE shared_match_flag='Y'
        GROUP BY 1,2
        HAVING count(*) BETWEEN {args.min_core} AND {args.max_core}
        ORDER BY n DESC, bin_start, hvfhs_license_num
        LIMIT 50
        """
    ).fetchall()
    if not bins:
        raise RuntimeError("no moderate-size matched 15-minute cohort found")
    bin_start, provider, core_n = bins[0]
    bin_end = bin_start + timedelta(minutes=15)

    pad = int(args.max_padding_minutes)
    connection.execute(
        f"""
        CREATE TEMP TABLE candidate AS
        SELECT row_number() OVER () AS rid,
               hvfhs_license_num,
               request_datetime,
               pickup_datetime,
               dropoff_datetime,
               PULocationID,
               DOLocationID,
               trip_miles,
               trip_time,
               base_passenger_fare,
               driver_pay,
               shared_request_flag,
               shared_match_flag
        FROM read_parquet({url})
        WHERE shared_match_flag='Y'
          AND hvfhs_license_num={qstr(provider)}
          AND pickup_datetime < TIMESTAMP {qstr(str(bin_end + timedelta(minutes=pad)))}
          AND dropoff_datetime > TIMESTAMP {qstr(str(bin_start - timedelta(minutes=pad)))}
        """
    )
    candidate_n = int(scalar(connection, "SELECT count(*) FROM candidate"))
    core_n_check = int(
        scalar(
            connection,
            f"SELECT count(*) FROM candidate "
            f"WHERE pickup_datetime >= TIMESTAMP {qstr(str(bin_start))} "
            f"AND pickup_datetime < TIMESTAMP {qstr(str(bin_end))}",
        )
    )
    if core_n_check != int(core_n):
        raise RuntimeError(
            f"core count mismatch: grouped={core_n}, materialized={core_n_check}"
        )

    paddings = [0, 2, 5, 10, 15, 30]
    rows = []
    for padding in paddings:
        if padding > pad:
            continue
        stats = connection.execute(
            f"""
            WITH core AS (
              SELECT * FROM candidate
              WHERE pickup_datetime >= TIMESTAMP {qstr(str(bin_start))}
                AND pickup_datetime < TIMESTAMP {qstr(str(bin_end))}
            ), edges AS (
              SELECT c.rid AS core_id,
                     x.rid AS candidate_id,
                     (c.PULocationID=x.PULocationID) AS same_pu,
                     (c.DOLocationID=x.DOLocationID) AS same_do
              FROM core c JOIN candidate x
                ON c.rid <> x.rid
               AND x.pickup_datetime < c.dropoff_datetime
                   + INTERVAL {padding} MINUTE
               AND x.dropoff_datetime > c.pickup_datetime
                   - INTERVAL {padding} MINUTE
            ), degree AS (
              SELECT c.rid,
                     count(e.candidate_id) AS degree
              FROM core c LEFT JOIN edges e ON c.rid=e.core_id
              GROUP BY c.rid
            ), totals AS (
              SELECT count(*) AS edges,
                     count(DISTINCT candidate_id) AS candidate_nodes
              FROM edges
            )
            SELECT totals.edges,
                   totals.candidate_nodes,
                   avg(degree.degree) AS mean_degree,
                   median(degree.degree) AS median_degree,
                   max(degree.degree) AS max_degree,
                   avg(CASE WHEN degree.degree=0 THEN 1 ELSE 0 END)
                     AS zero_degree_share
            FROM degree CROSS JOIN totals
            GROUP BY totals.edges, totals.candidate_nodes
            """
        ).fetchone()
        if stats is None:
            raise RuntimeError(f"empty candidate statistics at padding={padding}")
        strict = connection.execute(
            f"""
            WITH core AS (
              SELECT * FROM candidate
              WHERE pickup_datetime >= TIMESTAMP {qstr(str(bin_start))}
                AND pickup_datetime < TIMESTAMP {qstr(str(bin_end))}
            )
            SELECT count(*)
            FROM core c JOIN candidate x
              ON c.rid<>x.rid
             AND x.pickup_datetime < c.dropoff_datetime
                 + INTERVAL {padding} MINUTE
             AND x.dropoff_datetime > c.pickup_datetime
                 - INTERVAL {padding} MINUTE
             AND c.PULocationID=x.PULocationID
             AND c.DOLocationID=x.DOLocationID
            """
        ).fetchone()[0]
        rows.append(
            {
                "padding_minutes": padding,
                "temporal_edges": int(stats[0]),
                "candidate_nodes": int(stats[1]),
                "mean_core_degree": float(stats[2]),
                "median_core_degree": float(stats[3]),
                "max_core_degree": int(stats[4]),
                "zero_degree_share": float(stats[5]),
                "same_pu_do_edges": int(strict),
            }
        )

    return {
        "report_version": "nyc-hvfhv-latent-linkage-smoke/v1",
        "source": {
            "official_tlc_parquet": args.url,
            "url_sha256": sha256_text(args.url),
        },
        "schema_fields": fields,
        "matched_trip_count_month": total,
        "matched_trip_counts_by_provider": [
            {
                "license": license_number,
                "provider": PROVIDERS.get(license_number, "unknown"),
                "n": int(count_value),
            }
            for license_number, count_value in provider_counts
        ],
        "shared_flag_joint_counts": [
            {
                "shared_request_flag": request_flag,
                "shared_match_flag": match_flag,
                "n": int(count_value),
            }
            for request_flag, match_flag, count_value in flag_counts
        ],
        "cohort": {
            "provider_license": provider,
            "provider": PROVIDERS.get(provider, "unknown"),
            "pickup_bin_start": str(bin_start),
            "pickup_bin_end": str(bin_end),
            "core_rows": int(core_n),
            "candidate_rows_at_max_padding": candidate_n,
        },
        "candidate_support_curve": rows,
        "identification_boundary": {
            "public_partner_or_run_id_present": False,
            "public_pool_size_present": False,
            "k2_matching_claimed": False,
            "partner_recovery_claimed": False,
            "interpretation": (
                "candidate multiplicity under public temporal/zone support only"
            ),
        },
    }


def render(report: dict[str, Any]) -> str:
    cohort = report["cohort"]
    lines = [
        "# NYC HVFHV latent-linkage smoke test",
        "",
        f"Source cohort: **{cohort['provider']}** "
        f"(`{cohort['provider_license']}`), {cohort['pickup_bin_start']}–"
        f"{cohort['pickup_bin_end']}; **{cohort['core_rows']}** matched trips.",
        "",
        "NYC publishes `shared_match_flag` but not public co-rider/run ID or "
        "pool size. Therefore this report does **not** impose K=2 matching and "
        "does **not** reconstruct partners.",
        "",
        "| Padding (min) | Temporal edges | Candidate nodes | Mean core degree | Median | Max | Zero-degree share | Same PU+DO edges |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["candidate_support_curve"]:
        lines.append(
            f"| {row['padding_minutes']} | {row['temporal_edges']} | "
            f"{row['candidate_nodes']} | {row['mean_core_degree']:.2f} | "
            f"{row['median_core_degree']:.1f} | {row['max_core_degree']} | "
            f"{row['zero_degree_share']:.3f} | {row['same_pu_do_edges']} |"
        )
    lines.extend(
        [
            "",
            "The first Gate is whether candidate multiplicity is nontrivial yet "
            "computationally manageable. If so, NYC becomes the unknown-pool-size "
            "extension of the Chicago K=2 benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--provider", default="all")
    parser.add_argument("--min-core", type=int, default=20)
    parser.add_argument("--max-core", type=int, default=200)
    parser.add_argument("--max-padding-minutes", type=int, default=30)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tmp/nyc-hvfhv-smoke"),
    )
    args = parser.parse_args()
    report = run(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "REPORT.md").write_text(
        render(report),
        encoding="utf-8",
    )
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
