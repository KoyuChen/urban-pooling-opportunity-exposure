#!/usr/bin/env python3
"""Run the frozen public non-clique fixed-q structure comparison.

The four eligible windows were selected by the outcome-blind geometry census.
This runner first reproduces its projected-row and small-geometry hashes, then
attaches miles and exact observed duration and runs the complete small-instance
event-family audit.  Raw rows remain in git-ignored scratch.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

import nyc_geometry_census as geometry_audit
import nyc_hvfhv_consistent_snapshot as consistent
import nyc_hvfhv_smoke_fetch as raw
from nyc_hvfhv_smoke_types import number
from ordered_run_fixed_time_master import FixedTimeRow
from ordered_run_structure_audit import audit


HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "NYC_NONCLIQUE_STRUCTURE_PROTOCOL.json"
GEOMETRY_PROTOCOL = HERE / "NYC_GEOMETRY_CENSUS_PROTOCOL.json"
RESULT_VERSION = "nyc-outcome-blind-nonclique-structure-result/v1"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def modeled_sha(rows: list[FixedTimeRow]) -> str:
    return geometry_audit.sha([asdict(row) for row in rows])


def _select_small_rows(selected: dict, window: dict, protocol: dict) -> dict:
    origin = datetime(1970, 1, 1)
    time_rows: list[geometry_audit.TimeRow] = []
    source_by_index: dict[int, dict] = {}
    original_cores: list[int] = []
    for index, item in enumerate(selected["candidate_rows"]):
        start = raw.dt(item.get("pickup_datetime"))
        end = raw.dt(item.get("dropoff_datetime"))
        if start is None or end is None or end <= start:
            continue
        lo = (start - origin).total_seconds()
        hi = (end - origin).total_seconds()
        if not lo.is_integer() or not hi.is_integer():
            raise ValueError("noninteger exact-second interval")
        core = selected["core_start"] <= start < selected["core_end"]
        time_rows.append(geometry_audit.TimeRow(index, core, int(lo), int(hi)))
        source_by_index[index] = dict(item)
        if core:
            original_cores.append(index)
    if len(original_cores) < window["core_count"]:
        raise ValueError("insufficient positive-duration cores")
    chosen = set(original_cores[:window["core_count"]])
    full = [replace(row, core=row.index in chosen) for row in time_rows]
    cores = sorted((row for row in full if row.core), key=lambda row: row.index)[:4]
    if len(cores) != protocol["core_rows"]:
        raise ValueError("small view does not have four cores")
    core_indices = {row.index for row in cores}

    def gap(row: geometry_audit.TimeRow) -> int:
        return min(max(core.start - row.end, row.start - core.end, 0) for core in cores)

    candidates = sorted(
        (row for row in full if row.index not in core_indices),
        key=lambda row: (gap(row), row.start, row.end, row.index),
    )[: protocol["buffer_rows"]]
    if len(candidates) != protocol["buffer_rows"]:
        raise ValueError("small view does not have twelve buffers")
    small = sorted(
        [*cores, *(replace(row, core=False) for row in candidates)],
        key=lambda row: row.index,
    )
    geometry = geometry_audit.geometry(small)
    if geometry["input_sha256"] != window["small_geometry_input_sha256"]:
        raise ValueError("small-view geometry hash differs from the frozen census")
    if (
        geometry["overlap_edges"] != window["small_overlap_edges"]
        or geometry["core_incident_induced_p3_count"]
        != window["small_core_incident_p3_count"]
        or geometry["complete_clique"]
        or not geometry["nonclique_capacity2_event_available"]
    ):
        raise ValueError("small-view geometry metrics differ from the frozen census")
    fixed = []
    for row in small:
        source = source_by_index[row.index]
        fixed.append(
            FixedTimeRow(
                index=row.index,
                role="core" if row.core else "buffer",
                start=float(row.start),
                end=float(row.end),
                miles=number(source.get("trip_miles")),
                seconds=float(row.end - row.start),
            )
        )
    return {"rows": [asdict(row) for row in fixed], "geometry": geometry}


def fetch_window(window: dict, protocol: dict) -> dict:
    extraction = protocol["extraction"]
    args = argparse.Namespace(
        **extraction,
        scan_start=window["scan_start"],
        scan_end=window["scan_end"],
        min_core_rows=window["core_count"],
    )
    before = raw.snapshot()
    selected = consistent.choose_and_fetch(args)
    after_counts = [raw.count(selected["where"][key])[0] for key in ("determinate", "indeterminate")]
    after = raw.snapshot()
    if before != after or after_counts != [selected["determinate_count"], selected["indeterminate_count"]]:
        raise raw.LiveDataError("snapshot or server counts changed")
    if selected["provider"] != window["provider"]:
        raise raw.LiveDataError("provider differs from frozen outcome-blind geometry")
    fingerprint = after["revision_fingerprint_sha256"]
    if fingerprint != protocol["expected_snapshot_revision_fingerprint_sha256"]:
        raise raw.LiveDataError("dataset revision fingerprint differs from frozen census")
    fields = protocol["projection_fields"]
    projected = [{field: row.get(field) for field in fields if field in row}
                 for row in selected["candidate_rows"]]
    projected_sha = geometry_audit.sha(sorted(raw.canon(row).decode() for row in projected))
    if projected_sha != window["projected_candidate_multiset_sha256"]:
        raise raw.LiveDataError("projected candidate multiset differs from frozen census")
    modeled = _select_small_rows(selected, window, protocol)
    rows = [FixedTimeRow(**row) for row in modeled["rows"]]
    return {
        "window": window,
        "protocol_sha256": file_sha(PROTOCOL),
        "geometry_protocol_sha256": file_sha(GEOMETRY_PROTOCOL),
        "snapshot": after,
        "source": {
            "provider": selected["provider"],
            "core_start": selected["core_start"].isoformat(),
            "core_end": selected["core_end"].isoformat(),
            "candidate_rows": len(selected["candidate_rows"]),
            "determinate_count": selected["determinate_count"],
            "indeterminate_count": selected["indeterminate_count"],
            "query_sha256": selected["queries"],
            "projected_candidate_multiset_sha256": projected_sha,
        },
        "small_geometry": modeled["geometry"],
        "modeled_input_sha256": modeled_sha(rows),
        "rows": modeled["rows"],
    }


def verify_cached(cached: dict, window: dict, protocol: dict) -> list[FixedTimeRow]:
    if cached["window"] != window or cached["protocol_sha256"] != file_sha(PROTOCOL):
        raise ValueError("private cache uses another window or protocol")
    if cached["geometry_protocol_sha256"] != file_sha(GEOMETRY_PROTOCOL):
        raise ValueError("private cache uses another geometry protocol")
    rows = [FixedTimeRow(**row) for row in cached["rows"]]
    if cached["modeled_input_sha256"] != modeled_sha(rows):
        raise ValueError("private modeled-input hash mismatch")
    if cached["small_geometry"]["input_sha256"] != window["small_geometry_input_sha256"]:
        raise ValueError("private cache does not reproduce frozen geometry")
    return rows


def stripped_support(report: dict, window: dict, protocol: dict) -> list[dict]:
    output = []
    for cell in report["support_cells"]:
        output.append({
            "window_index": window["index"],
            "window_label": window["label"],
            "capacity": cell["capacity"],
            "family": cell["family"],
            "run_column_count": cell["run_column_count"],
            "reachable_selected_buffer_counts": cell["reachable_selected_buffer_counts"],
            "maximum_selected_buffers": cell["maximum_selected_buffers"],
            "columns_excluded_from_ordered": cell["columns_excluded_from_ordered"],
            "common_positive_q": cell["common_positive_q"],
            "compared_q": [q for q in protocol["declared_q_values"]
                           if q in cell["common_positive_q"]],
        })
    return output


def aggregate(protocol: dict, windows: list[dict]) -> dict:
    support = []
    indexed_comparisons = {}
    world_counts = {}
    per_window = []
    for item in windows:
        window, report = item["window"], item["report"]
        support.extend(stripped_support(report, window, protocol))
        for row in report["comparisons"]:
            indexed_comparisons[(window["index"], row["capacity"], row["q"], row["query"], row["restriction"])] = row
        for row in report["outcome_cells"]:
            key = (window["index"], row["capacity"], row["q"], row["family"])
            world_counts.setdefault(key, row["reachable_q_buffer_masks"])
        per_window.append({
            "index": window["index"], "label": window["label"],
            "geometry_input_sha256": item["cache"]["small_geometry"]["input_sha256"],
            "modeled_input_sha256": item["cache"]["modeled_input_sha256"],
            "overlap_edges": item["cache"]["small_geometry"]["overlap_edges"],
            "possible_edges": item["cache"]["small_geometry"]["possible_edges"],
            "core_incident_p3_count": item["cache"]["small_geometry"]["core_incident_induced_p3_count"],
            "verification_status": report["summary"]["verification_status"],
            "unresolved_verification_count": report["summary"]["unresolved_verification_count"],
        })
    comparisons = []
    for window in protocol["windows"]:
        for capacity in protocol["capacities"]:
            for q in protocol["declared_q_values"]:
                for query in protocol["queries"]:
                    for restriction in ("pair", "clique"):
                        key = (window["index"], capacity, q, query["name"], restriction)
                        row = indexed_comparisons.get(key)
                        base = {"window_index": window["index"], "window_label": window["label"],
                                "capacity": capacity, "q": q, "query": query["name"],
                                "restriction": restriction}
                        if row is None:
                            comparisons.append({**base, "status": "INELIGIBLE_NOT_COMMON_FEASIBLE_Q"})
                        else:
                            comparisons.append({**base, **row})
    certified = [row for row in comparisons if row["status"] == "CERTIFIED_FIXED_Q_COMPARISON"]
    by_restriction = {}
    for restriction in ("pair", "clique"):
        rows = [row for row in comparisons if row["restriction"] == restriction]
        eligible = [row for row in rows if row["status"] == "CERTIFIED_FIXED_Q_COMPARISON"]
        by_restriction[restriction] = {
            "declared": len(rows), "certified": len(eligible),
            "changed": sum(row["endpoint_changed_exactly"] for row in eligible),
            "support_ineligible": sum(row["status"] == "INELIGIBLE_NOT_COMMON_FEASIBLE_Q" for row in rows),
            "missing_query_ineligible": sum(row["status"] == "INELIGIBLE_MISSING_PUBLIC_QUERY_VALUES" for row in rows),
        }
    world_cells = []
    for window in protocol["windows"]:
        for capacity in protocol["capacities"]:
            for q in protocol["declared_q_values"]:
                counts = {family: world_counts.get((window["index"], capacity, q, family))
                          for family in ("ordered", "pair", "clique")}
                common = all(value is not None and value > 0 for value in counts.values())
                world_cells.append({"window_index": window["index"], "window_label": window["label"],
                                    "capacity": capacity, "q": q, "common_feasible": common,
                                    **{f"{family}_reachable_buffer_masks": value for family, value in counts.items()},
                                    "ordered_exceeds_clique": common and counts["ordered"] > counts["clique"],
                                    "ordered_exceeds_pair": common and counts["ordered"] > counts["pair"]})
    unresolved = sum(item["unresolved_verification_count"] for item in per_window)
    primary_changed = by_restriction["clique"]["changed"]
    status = "HOLD_UNRESOLVED_VERIFICATION" if unresolved else (
        "PASS_PUBLIC_NONCLIQUE_ENDPOINT_EFFECT" if primary_changed else "PASS_PUBLIC_NONCLIQUE_TEST_NULL"
    )
    return {
        "version": RESULT_VERSION,
        "status": status,
        "protocol_sha256": file_sha(PROTOCOL),
        "geometry_protocol_sha256": file_sha(GEOMETRY_PROTOCOL),
        "scope_limit": protocol["scope_limit"],
        "denominator": protocol["geometry_source"],
        "summary": {
            "eligible_windows": len(per_window),
            "all_windows_verified": all(item["verification_status"] == "PASS" for item in per_window),
            "unresolved_verification_count": unresolved,
            "declared_comparisons": len(comparisons),
            "certified_comparisons": len(certified),
            "changed_comparisons": sum(row["endpoint_changed_exactly"] for row in certified),
            "by_restriction": by_restriction,
            "common_feasible_world_cells": sum(row["common_feasible"] for row in world_cells),
            "ordered_more_worlds_than_clique_cells": sum(row["ordered_exceeds_clique"] for row in world_cells),
            "ordered_more_worlds_than_pair_cells": sum(row["ordered_exceeds_pair"] for row in world_cells),
        },
        "windows": per_window,
        "support_cells": support,
        "world_cells": world_cells,
        "comparisons": comparisons,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row.get(key), sort_keys=True) if isinstance(row.get(key), (list, dict)) else row.get(key)
                             for key in keys})


def write_outputs(result: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "SUMMARY.json", result)
    write_csv(output / "SUPPORT.csv", result["support_cells"])
    write_csv(output / "WORLD_COUNTS.csv", result["world_cells"])
    write_csv(output / "COMPARISONS.csv", result["comparisons"])
    summary = result["summary"]
    pair = summary["by_restriction"]["pair"]
    clique = summary["by_restriction"]["clique"]
    lines = [
        "# NYC outcome-blind non-clique fixed-q audit", "",
        f"Status: **{result['status']}**.", "",
        "The four analyzed 4+12 views were selected solely because the earlier outcome-blind geometry census found a core-touching induced P3. The four completed clique views remain in the denominator but are geometry-ineligible for this conditional diagnostic.", "",
        f"All {summary['eligible_windows']} eligible windows replayed their frozen projection and small-geometry hashes. Complete enumeration and independent MILP replay left {summary['unresolved_verification_count']} unresolved verification cells.", "",
        "| Restriction | Declared comparisons | Certified | Endpoint changed | Support-ineligible | Missing-query ineligible |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Pair | {pair['declared']} | {pair['certified']} | {pair['changed']} | {pair['support_ineligible']} | {pair['missing_query_ineligible']} |",
        f"| Clique | {clique['declared']} | {clique['certified']} | {clique['changed']} | {clique['support_ineligible']} | {clique['missing_query_ineligible']} |", "",
        f"Among {summary['common_feasible_world_cells']} window-capacity-q cells feasible in all three families, ordered events admit more reachable buffer subsets than cliques in {summary['ordered_more_worlds_than_clique_cells']} cells and more than pairs in {summary['ordered_more_worlds_than_pair_cells']} cells.", "",
        "| Window | Edges | Possible | Core P3s | Verification |",
        "|---|---:|---:|---:|---|",
    ]
    for window in result["windows"]:
        lines.append(f"| {window['label']} | {window['overlap_edges']} | {window['possible_edges']} | {window['core_incident_p3_count']} | {window['verification_status']} |")
    lines += ["", "The primary distinctive comparison is ordered versus clique. Pair differences additionally reflect the two-member restriction. Equality is retained as a result. Public rows do not reveal the true event partition, so these are conditional identified-set effects, not accuracy or prevalence estimates.", "", f"Scope: {result['scope_limit']}"]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    tex = [
        r"% Generated aggregate fragment; inclusion in the manuscript requires claim audit.",
        r"\paragraph{Outcome-blind non-clique public diagnostic.}",
        f"Four time-only NYC $4+12$ views were fixed by a prior geometry census before query values were attached. All four reproduce their frozen non-clique geometry hashes and pass complete enumeration plus independent MILP replay.",
        f"At the predeclared common fixed supports, {clique['changed']} of {clique['certified']} certified ordered-versus-clique comparisons change an endpoint; the corresponding ordered-versus-pair count is {pair['changed']} of {pair['certified']}.",
        f"Ordered events admit more fixed-support buffer worlds than cliques in {summary['ordered_more_worlds_than_clique_cells']} of {summary['common_feasible_world_cells']} common-feasible window--capacity--support cells.",
        "This conditional audit is not true-event recovery, population prevalence, partner-recall coverage, or city-scale closure.",
    ]
    (output / "RESULTS.tex").write_text("\n".join(tex) + "\n")
    names = ("SUMMARY.json", "SUPPORT.csv", "WORLD_COUNTS.csv", "COMPARISONS.csv", "REPORT.md", "RESULTS.tex")
    write_json(output / "MANIFEST.json", {
        "version": "nyc-outcome-blind-nonclique-manifest/v1",
        "aggregate_only": True,
        "files_sha256": {name: file_sha(output / name) for name in names},
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=Path("tmp/nyc-nonclique-structure-gate"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="Reuse verified private caches and fetch only missing windows")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    args.work_dir.mkdir(parents=True, exist_ok=True)
    repository = HERE.parents[3]
    if subprocess.run(["git", "check-ignore", "--quiet", str(args.work_dir.resolve())], cwd=repository).returncode != 0:
        raise SystemExit("work-dir must be git-ignored")
    audited = []
    for window in protocol["windows"]:
        cache_path = args.work_dir / f"window-{window['index']:02d}.private.json"
        if cache_path.exists():
            if not args.resume:
                raise SystemExit(f"private cache exists for window {window['index']}; use --resume or another work-dir")
            cached = json.loads(cache_path.read_text())
        else:
            print(json.dumps({"stage": "fetch", "window": window["index"], "label": window["label"]}), flush=True)
            cached = fetch_window(window, protocol)
            write_json(cache_path, cached)
        rows = verify_cached(cached, window, protocol)
        print(json.dumps({"stage": "audit", "window": window["index"], "input_sha256": cached["modeled_input_sha256"]}), flush=True)
        report = audit(rows, protocol)
        audited.append({"window": window, "cache": cached, "report": report})
    result = aggregate(protocol, audited)
    write_outputs(result, args.output_dir)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0 if result["status"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
