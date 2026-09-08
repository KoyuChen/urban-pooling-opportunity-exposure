#!/usr/bin/env python3
"""Outcome-blind interval geometry on a fixed, fully accounted NYC calendar."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import signal
import time

import nyc_hvfhv_smoke_fetch as raw
import nyc_hvfhv_consistent_snapshot as consistent

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "NYC_GEOMETRY_CENSUS_PROTOCOL.json"
RETRYABLE = {"TRANSPORT_FAILURE", "TRANSPORT_DEADLINE"}
TERMINAL = {"GEOMETRY_COMPLETE", "INELIGIBLE_NO_QUALIFIED_CORE", "INELIGIBLE_VALID_CORE_COUNT", "OUT_OF_PROTOCOL_TIME"}


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


@dataclass(frozen=True)
class TimeRow:
    index: int
    core: bool
    start: int
    end: int


def bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def geometry(rows):
    """Count every induced P3 touching a core with integer bitset operations.

    Exact integer seconds and epsilon=1 imply nonedges have no positive overlap.
    Thus each induced P3 has peak occupancy two. This is event-column existence,
    not existence of a disjoint world covering all remaining core rows.
    """
    n = len(rows)
    if not n or len({row.index for row in rows}) != n:
        raise ValueError("nonempty input with unique indices is required")
    if any(row.end <= row.start or int(row.start) != row.start or int(row.end) != row.end for row in rows):
        raise ValueError("positive integer-second intervals required")
    adjacency = [0] * n
    cores = sum(1 << i for i, row in enumerate(rows) if row.core)
    if not cores:
        raise ValueError("at least one compulsory core is required")
    for i, left in enumerate(rows):
        for j in range(i + 1, n):
            right = rows[j]
            if min(left.end, right.end) - max(left.start, right.start) >= 1:
                adjacency[i] |= 1 << j
                adjacency[j] |= 1 << i
    p3_count, witness = 0, None
    for center, neighbors in enumerate(adjacency):
        for left in bits(neighbors):
            right_candidates = neighbors & ~adjacency[left] & ~((1 << (left + 1)) - 1)
            if not rows[center].core and not rows[left].core:
                right_candidates &= cores
            p3_count += right_candidates.bit_count()
            if witness is None and right_candidates:
                witness = (left, center, next(bits(right_candidates)))
    unseen, components = (1 << n) - 1, []
    while unseen:
        root = unseen & -unseen
        reached, frontier = root, root
        while frontier:
            bit = frontier & -frontier
            frontier ^= bit
            new = adjacency[bit.bit_length() - 1] & ~reached
            reached |= new
            frontier |= new
        unseen &= ~reached
        size = reached.bit_count()
        edge_count = sum((adjacency[p] & reached).bit_count() for p in bits(reached)) // 2
        components.append({"rows": size, "cores": (reached & cores).bit_count(),
                           "clique": edge_count == size * (size - 1) // 2})
    # Independently check P3 existence by inspecting core-containing components.
    structural_nonclique = any(c["cores"] and not c["clique"] for c in components)
    if structural_nonclique != bool(p3_count):
        raise AssertionError("P3 count disagrees with connected-component characterization")
    witness_hash = None
    if witness:
        a, b, c = [rows[i] for i in witness]
        if not (max(a.start, b.start) < min(a.end, b.end) and
                max(b.start, c.start) < min(b.end, c.end) and
                max(a.start, c.start) >= min(a.end, c.end) and any(r.core for r in (a, b, c))):
            raise AssertionError("independent temporal P3 witness replay failed")
        witness_hash = sha({"input": [asdict(row) for row in rows], "witness_positions": witness})
    edges = sum(mask.bit_count() for mask in adjacency) // 2
    return {
        "status": "GEOMETRY_COMPLETE", "row_count": n, "core_count": cores.bit_count(),
        "buffer_count": n - cores.bit_count(), "input_sha256": sha([asdict(r) for r in rows]),
        "overlap_edges": edges, "possible_edges": n * (n - 1) // 2,
        "complete_clique": edges == n * (n - 1) // 2,
        "common_overlap_seconds": max(0, min(r.end for r in rows) - max(r.start for r in rows)),
        "component_count": len(components),
        "core_component_count": sum(c["cores"] > 0 for c in components),
        "nonclique_core_component_count": sum(c["cores"] > 0 and not c["clique"] for c in components),
        "largest_component_rows": max(c["rows"] for c in components),
        "core_incident_induced_p3_count": p3_count,
        "nonclique_capacity2_event_available": bool(p3_count),
        "p3_witness_sha256": witness_hash, "p3_witness_replayed": witness_hash is not None,
        "full_world_extendability_checked": False,
    }


def small_view(rows):
    cores = sorted((r for r in rows if r.core), key=lambda r: r.index)[:4]
    if len(cores) != 4:
        return {"status": "INELIGIBLE_SMALL_CORE_COUNT"}
    indices = {r.index for r in cores}
    def gap(row):
        return min(max(core.start - row.end, row.start - core.end, 0) for core in cores)
    candidates = sorted((r for r in rows if r.index not in indices),
                        key=lambda r: (gap(r), r.start, r.end, r.index))[:12]
    if len(candidates) != 12:
        return {"status": "INELIGIBLE_SMALL_BUFFER_COUNT"}
    selected = sorted([*cores, *(replace(r, core=False) for r in candidates)], key=lambda r: r.index)
    return geometry(selected)


class FetchDeadline(BaseException):
    pass


class InvalidTime(ValueError):
    pass


class InsufficientCore(ValueError):
    pass


def fetch_rows(window, protocol):
    spec = protocol["extraction"]
    args = argparse.Namespace(**{k: v for k, v in spec.items() if k != "rule"},
                              scan_start=window["scan_start"], scan_end=window["scan_end"],
                              min_core_rows=window["core_count"])
    original_fields, original_request = raw.FIELDS, raw.request_json
    def request(url, **kwargs):
        print(json.dumps({"stage": "request", "request_sha256": sha({"url": url, "body": kwargs.get("body")})}), flush=True)
        return original_request(url, **{**kwargs, "timeout": protocol["execution"]["request_timeout_seconds"]})
    raw.FIELDS = tuple(protocol["fields"])
    raw.request_json = request
    try:
        before = raw.snapshot()
        selected = consistent.choose_and_fetch(args)
        after_counts = [raw.count(selected["where"][key])[0] for key in ("determinate", "indeterminate")]
        after = raw.snapshot()
        if before != after or after_counts != [selected["determinate_count"], selected["indeterminate_count"]]:
            raise raw.LiveDataError("snapshot or server counts changed")
    finally:
        raw.FIELDS, raw.request_json = original_fields, original_request
    allowed = set(protocol["fields"])
    if any(set(row) - allowed for row in selected["candidate_rows"]):
        raise AssertionError("source response contains undeclared fields")
    rows, original_cores, excluded = [], [], Counter()
    origin = datetime(1970, 1, 1)
    for i, item in enumerate(selected["candidate_rows"]):
        if raw.text(item.get("hvfhs_license_num")) != selected["provider"] or raw.text(item.get("shared_match_flag")) != "Y":
            raise AssertionError("source predicate violated")
        start, end = raw.dt(item.get("pickup_datetime")), raw.dt(item.get("dropoff_datetime"))
        if start is None or end is None:
            excluded["indeterminate_time"] += 1
            continue
        if end <= start:
            excluded["nonpositive_duration"] += 1
            continue
        lo, hi = (start - origin).total_seconds(), (end - origin).total_seconds()
        if not lo.is_integer() or not hi.is_integer():
            raise InvalidTime("noninteger exact-second interval")
        core = selected["core_start"] <= start < selected["core_end"]
        rows.append(TimeRow(i, core, int(lo), int(hi)))
        if core:
            original_cores.append(i)
    if len(original_cores) < window["core_count"]:
        raise InsufficientCore("too few valid positive-duration cores")
    chosen = set(original_cores[:window["core_count"]])
    rows = [replace(row, core=row.index in chosen) for row in rows]
    source = {"snapshot": after, "provider": selected["provider"],
              "source_core_start": selected["core_start"].isoformat(),
              "source_core_end": selected["core_end"].isoformat(),
              "source_candidate_rows": len(selected["candidate_rows"]),
              "source_core_rows": len(selected["core_rows"]), "excluded_time_rows": dict(excluded),
              "query_sha256": selected["queries"],
              "projected_candidate_multiset_sha256": sha(sorted(raw.canon(r).decode() for r in selected["candidate_rows"])),
              "server_counts_rechecked": True, "outcome_columns_requested": False,
              "historical_instance_identity": "NOT_ESTABLISHED_NEW_SNAPSHOT"}
    return rows, source


def provenance():
    return {"protocol_sha256": file_sha(PROTOCOL),
            "code_sha256": {name: file_sha(HERE / name) for name in
                            (Path(__file__).name, "nyc_hvfhv_smoke_fetch.py", "nyc_hvfhv_consistent_snapshot.py", "nyc_hvfhv_smoke_types.py")}}


def run_window(window, protocol, output):
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "report.json"
    pins = provenance()
    if report_path.exists():
        previous = json.loads(report_path.read_text())
        if previous["provenance"] != pins or previous["window"] != window:
            raise ValueError("existing checkpoint differs from pinned protocol/code/window")
        if previous["status"] in TERMINAL:
            return previous
        if previous["status"] == "IN_PROGRESS":
            raise ValueError("attempt still marked IN_PROGRESS; verify interruption before recovery")
        if previous["status"] not in RETRYABLE:
            raise ValueError("only declared transport failures can be retried")
    attempts = sorted(output.glob("attempt_*.json"))
    attempt_path = output / f"attempt_{len(attempts) + 1:03d}.json"
    report = {"version": protocol["version"], "window": window, "status": "IN_PROGRESS",
              "started_at": now(), "provenance": pins, "aggregate_only": True}
    write_json(report_path, report)
    write_json(attempt_path, report)
    start_time = time.monotonic()
    def deadline(*_):
        raise FetchDeadline()
    old_handler = signal.signal(signal.SIGALRM, deadline)
    signal.alarm(protocol["execution"]["window_deadline_seconds"])
    try:
        rows, source = fetch_rows(window, protocol)
        report.update(status="GEOMETRY_COMPLETE", source=source, full=geometry(rows), small=small_view(rows))
    except FetchDeadline:
        report.update(status="TRANSPORT_DEADLINE", reason="window extraction exceeded declared hard deadline")
    except InvalidTime:
        report.update(status="OUT_OF_PROTOCOL_TIME", reason="noninteger timestamps; no rounding applied")
    except InsufficientCore:
        report.update(status="INELIGIBLE_VALID_CORE_COUNT", reason="insufficient positive-duration core rows")
    except raw.LiveDataError as error:
        if str(error) == "no scan window produced an integrity- and cap-qualified core":
            report.update(status="INELIGIBLE_NO_QUALIFIED_CORE", reason=str(error))
        else:
            report.update(status="TRANSPORT_FAILURE", reason_type=type(error).__name__, reason_sha256=sha(str(error)))
    except Exception as error:
        report.update(status="AUDIT_FAILURE", reason_type=type(error).__name__, reason_sha256=sha(str(error)))
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
    report.update(completed_at=now(), elapsed_seconds=time.monotonic() - start_time)
    write_json(attempt_path, report)
    write_json(report_path, report)
    print(json.dumps({"label": window["label"], "status": report["status"],
                      "full_p3": report.get("full", {}).get("core_incident_induced_p3_count"),
                      "small_clique": report.get("small", {}).get("complete_clique")}), flush=True)
    return report


def aggregate(protocol, reports):
    indexed = {}
    pins = provenance()
    for report in reports:
        i = report["window"]["index"]
        if i in indexed or i not in range(len(protocol["windows"])) or report["window"] != protocol["windows"][i]:
            raise ValueError("duplicate or undeclared window")
        if report["provenance"] != pins or report.get("aggregate_only") is not True:
            raise ValueError("mismatched protocol/code or redaction contract")
        if report["status"] not in TERMINAL | RETRYABLE | {"IN_PROGRESS", "AUDIT_FAILURE"}:
            raise ValueError("unknown execution status")
        if report["status"] == "GEOMETRY_COMPLETE":
            if (report["source"].get("outcome_columns_requested") is not False or
                    report["full"]["core_count"] != report["window"]["core_count"] or
                    report["full"].get("full_world_extendability_checked") is not False):
                raise ValueError("completed geometry violates the declared scope")
        indexed[i] = report
    ledger = []
    for window in protocol["windows"]:
        item = indexed.get(window["index"], {"window": window, "status": "NOT_STARTED"})
        ledger.append(item)
    statuses = Counter(item["status"] for item in ledger)
    completed = [r for r in ledger if r["status"] == "GEOMETRY_COMPLETE"]
    fingerprints = {r["source"]["snapshot"]["revision_fingerprint_sha256"] for r in completed}
    accounted = all(r["status"] in TERMINAL for r in ledger)
    clean = accounted and not statuses["OUT_OF_PROTOCOL_TIME"] and len(fingerprints) == 1
    def stats(items, key):
        valid = [r[key] for r in items if r[key]["status"] == "GEOMETRY_COMPLETE"]
        return {"eligible_views": len(valid), "complete_clique_views": sum(r["complete_clique"] for r in valid),
                "nonclique_event_available_views": sum(r["nonclique_capacity2_event_available"] for r in valid)}
    summary = {"status": "PASS_GEOMETRY_CENSUS" if clean else "HOLD_INCOMPLETE_OR_INCONSISTENT",
               "declared_cells": len(ledger), "distinct_scan_windows": len({(w['scan_start'],w['scan_end']) for w in protocol['windows']}),
               "status_counts": dict(statuses), "common_fingerprint_count": len(fingerprints),
               "full": stats(completed, "full"), "small": stats(completed, "small"),
               "broad_full": stats([r for r in completed if r['window']['core_count']==8], "full"),
               "stress_full": stats([r for r in completed if r['window']['core_count']==16], "full")}
    return {"version": protocol["version"], "generated_at": now(), "provenance": pins,
            "summary": summary, "ledger": ledger, "aggregate_only": True,
            "claim_boundary": protocol["scope"], "denominator": protocol["denominator"]}


def write_summary(report, output):
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "SUMMARY.json", report)
    columns = ["index", "label", "core_count", "status", "full_rows", "full_clique", "full_core_p3", "small_status", "small_clique", "small_core_p3"]
    with (output / "WINDOWS.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for r in report["ledger"]:
            f, s = r.get("full", {}), r.get("small", {})
            writer.writerow({**{k: r["window"][k] for k in ("index", "label", "core_count")}, "status": r["status"],
                             "full_rows": f.get("row_count"), "full_clique": f.get("complete_clique"),
                             "full_core_p3": f.get("core_incident_induced_p3_count"), "small_status": s.get("status"),
                             "small_clique": s.get("complete_clique"), "small_core_p3": s.get("core_incident_induced_p3_count")})
    summary = report["summary"]
    lines = ["# NYC outcome-blind temporal geometry census", "", f"Status: **{summary['status']}**.", "",
             f"24 declared cells / 20 distinct scan windows. Status counts: `{summary['status_counts']}`.", "",
             "| View | Eligible | Complete clique | Core-touching non-clique event available |",
             "|---|---:|---:|---:|"]
    for key in ("full", "small", "broad_full", "stress_full"):
        item = summary[key]
        lines.append(f"| {key} | {item['eligible_views']} | {item['complete_clique_views']} | {item['nonclique_event_available_views']} |")
    lines += ["", "The small view selects 4+12 using time only, without the earlier outcome-availability filter. Complete-clique cases and all failures remain in WINDOWS.csv and the JSON ledger.", "",
              "A core-touching induced three-vertex path is a capacity-2 non-clique event column. Its existence does not prove that it extends to a disjoint world covering every core, changes any fixed-q endpoint, or occurred operationally. Four stress cells reuse broad scan periods; rows and cells are not independent population observations.", "",
              "No miles, duration outcome, fare or pay column is requested. No outcome optimizer is run. Source and code hashes are recorded per window; all reported geometry is relative to newly extracted public snapshots."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    tex = [r"% Aggregate diagnostic fragment; not automatically included in the paper.",
           r"\paragraph{Outcome-blind temporal geometry census.}",
           f"The declared calendar has 24 cells and 20 distinct scan periods. {summary['full']['eligible_views']} full views have completed geometry.",
           f"Among these, {summary['full']['nonclique_event_available_views']} contain a core-incident induced three-row path, hence an admissible non-clique event column of capacity two.",
           f"The time-only 4+12 reduction has {summary['small']['complete_clique_views']} complete-clique views among {summary['small']['eligible_views']} eligible reductions.",
           "All unstarted, failed and ineligible cells remain in the declared denominator.",
           "Event-column availability is not full-world extendability, an outcome-endpoint difference, or true vehicle-event identification."]
    (output / "RESULTS.tex").write_text("\n".join(tex) + "\n")
    write_json(output / "MANIFEST.json", {"aggregate_only": True, "files_sha256": {
        name: file_sha(output / name) for name in ("SUMMARY.json", "WINDOWS.csv", "REPORT.md", "RESULTS.tex")}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-index", type=int)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    if args.window_index is not None:
        if args.window_index not in range(len(protocol["windows"])):
            parser.error("window-index outside fixed calendar")
        result = run_window(protocol["windows"][args.window_index], protocol, args.output_dir)
        return 0 if result["status"] in TERMINAL else 2
    reports = [] if args.input_dir is None else [json.loads(p.read_text()) for p in sorted(args.input_dir.rglob("report.json"))]
    report = aggregate(protocol, reports)
    write_summary(report, args.output_dir)
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["summary"]["status"] == "PASS_GEOMETRY_CENSUS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
