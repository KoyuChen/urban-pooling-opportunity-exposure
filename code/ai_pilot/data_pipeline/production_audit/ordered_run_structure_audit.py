#!/usr/bin/env python3
"""Exact small-instance comparison of ordered, pair and clique event families.

The reference enumerator supplies the ordered columns. Restricted columns use
the same rows and capacity. A separate sweep/graph predicate verifies the whole
column universe; binary column-selection MILPs verify every support count and
outcome endpoint. Only aggregate records and witness hashes are serialized.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, replace
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, vstack

import ordered_run_fixed_time_master as reference

FAMILIES = ("ordered", "pair", "clique")


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def positions(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def event_valid(rows, mask, capacity, epsilon, family):
    """Independent event replay using a time sweep and a graph traversal."""
    if family not in FAMILIES or mask <= 0 or mask >= 1 << len(rows):
        return False
    selected = [rows[p] for p in positions(mask)]
    if len(selected) < 2 or not any(row.role == "core" for row in selected):
        return False
    if family == "pair" and len(selected) != 2:
        return False
    active = 0
    changes = sorted(
        [(row.start, 1) for row in selected] +
        [(row.end, -1) for row in selected]
    )
    for _, change in changes:
        active += change  # Departures precede arrivals at a shared endpoint.
        if active > capacity:
            return False
    adjacency = [set() for _ in selected]
    for i, left in enumerate(selected):
        for j in range(i + 1, len(selected)):
            right = selected[j]
            overlap = min(left.end, right.end) - max(left.start, right.start)
            if overlap + reference.TOL >= epsilon:
                adjacency[i].add(j)
                adjacency[j].add(i)
            elif family == "clique":
                return False
    reached, pending = {0}, [0]
    while pending:
        for neighbour in adjacency[pending.pop()] - reached:
            reached.add(neighbour)
            pending.append(neighbour)
    return len(reached) == len(selected)


def restricted_master(master, family):
    if family == "ordered":
        return master
    if family not in FAMILIES:
        raise ValueError("unknown event family")
    columns = [column for column in master.columns if event_valid(
        master.rows, column.member_mask, master.capacity, master.epsilon, family
    )]
    by_core = {p: [] for p in positions(master.all_core_mask)}
    for column in columns:
        for p in positions(column.core_mask):
            by_core[p].append(column)
    seen, pending, terminal = {(0, 0)}, [(0, 0)], set()
    while pending:
        covered, used = pending.pop()
        if covered == master.all_core_mask:
            terminal.add(used)
            continue
        pivot = next(positions(master.all_core_mask & ~covered))
        for column in by_core[pivot]:
            if column.core_mask & covered or column.buffer_mask & used:
                continue
            state = (covered | column.core_mask, used | column.buffer_mask)
            if state not in seen:
                seen.add(state)
                pending.append(state)
    return replace(
        master, columns=columns, columns_by_core_position=by_core,
        reachable_buffer_masks=terminal, explored_state_count=len(seen),
        max_column_size=max((c.member_mask.bit_count() for c in columns), default=0),
    )


def replay(master, family, masks, q):
    used = 0
    for mask in masks:
        if used & mask or not event_valid(
            master.rows, mask, master.capacity, master.epsilon, family
        ):
            raise AssertionError("invalid or overlapping event witness")
        used |= mask
    if used & master.all_core_mask != master.all_core_mask:
        raise AssertionError("witness fails compulsory core coverage")
    if (used & master.all_buffer_mask).bit_count() != q:
        raise AssertionError("witness fails fixed buffer-count constraint")
    return used & master.all_buffer_mask


def exact_witness(master, target):
    @lru_cache(None)
    def visit(covered, used):
        if covered == master.all_core_mask:
            return () if used == target else None
        pivot = next(positions(master.all_core_mask & ~covered))
        for column in master.columns_by_core_position[pivot]:
            if (column.core_mask & covered or column.buffer_mask & used or
                    column.buffer_mask & ~target):
                continue
            tail = visit(covered | column.core_mask, used | column.buffer_mask)
            if tail is not None:
                return (column.member_mask, *tail)
        return None
    answer = visit(0, 0)
    if answer is None:
        raise AssertionError("reachable buffer mask has no event witness")
    return answer


def witness_hash(master, family, masks, q):
    replay(master, family, masks, q)
    return digest({
        "input_sha256": digest([asdict(row) for row in master.rows]),
        "capacity": master.capacity, "epsilon": master.epsilon,
        "family": family, "q": q, "events": sorted(masks),
    })


def score(master, mask, attribute, scale, q):
    return sum((Fraction(str(getattr(master.rows[p], attribute)))
                for p in positions(mask)), Fraction()) / (Fraction(str(scale)) * q)


def exact_bounds(master, q, query):
    masks = sorted(mask for mask in master.reachable_buffer_masks if mask.bit_count() == q)
    if not masks:
        return {"status": "PROVEN_INFEASIBLE_EXACT_ENUMERATION"}
    selectable = 0
    for mask in masks:
        selectable |= mask
    if any(getattr(master.rows[p], query["attribute"]) is None
           for p in positions(selectable)):
        return {"status": "INELIGIBLE_MISSING_PUBLIC_QUERY_VALUES"}
    values = [(score(master, mask, query["attribute"], query["scale"], q), mask)
              for mask in masks]
    lower, lower_mask = min(values)
    upper, upper_mask = max(values, key=lambda item: (item[0], -item[1]))
    return {"status": "CERTIFIED_EXACT_FINITE_FRONTIER", "lower": lower,
            "upper": upper, "lower_mask": lower_mask, "upper_mask": upper_mask}


def verify_milp(master, family, q, seconds, query=None, maximize=False):
    """Independent binary set-partitioning master, followed by direct replay."""
    if not master.columns:
        return {"status": "PROVEN_INFEASIBLE_EMPTY_COLUMN_SET"}
    n, m = len(master.rows), len(master.columns)
    row_indices, col_indices = [], []
    for j, column in enumerate(master.columns):
        for p in positions(column.member_mask):
            row_indices.append(p)
            col_indices.append(j)
    incidence = csr_matrix((np.ones(len(row_indices)), (row_indices, col_indices)), shape=(n, m))
    buffer_counts = np.array([c.buffer_mask.bit_count() for c in master.columns], dtype=float)
    matrix = vstack([incidence, csr_matrix(buffer_counts.reshape(1, -1))], format="csr")
    lower = np.array([1.0 if row.role == "core" else 0.0 for row in master.rows] + [float(q)])
    upper = np.array([1.0] * n + [float(q)])
    coeff = np.zeros(m)
    if query is not None:
        # Missing attributes on columns that cannot occur at this q need not
        # invalidate the query. exact_bounds checked every reachable mask;
        # direct replay below rejects any unexpectedly selected missing value.
        values = [0.0 if getattr(row, query["attribute"]) is None else
                  float(getattr(row, query["attribute"])) / query["scale"] / q
                  for row in master.rows]
        coeff = np.array([sum(values[p] for p in positions(c.buffer_mask)) for c in master.columns])
    result = milp(
        -coeff if maximize else coeff,
        integrality=np.ones(m), bounds=Bounds(np.zeros(m), np.ones(m)),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": seconds, "mip_rel_gap": 0.0},
    )
    if result.status == 2:
        return {"status": "PROVEN_INFEASIBLE_NUMERICAL_MILP"}
    if result.status != 0:
        return {"status": "UNRESOLVED_MILP_VERIFICATION", "solver_status_code": int(result.status)}
    if result.x is None or np.max(np.abs(result.x - np.rint(result.x))) > 1e-7:
        raise AssertionError("MILP witness is not integral")
    masks = [c.member_mask for c, x in zip(master.columns, result.x) if round(x) == 1]
    selected = replay(master, family, masks, q)
    verified = {"status": "OPTIMAL_NUMERICAL_MILP_REPLAYED",
                "witness_sha256": witness_hash(master, family, masks, q)}
    if query is not None:
        value = score(master, selected, query["attribute"], query["scale"], q)
        if abs(float(value) - (-result.fun if maximize else result.fun)) > 1e-7:
            raise AssertionError("MILP objective disagrees with direct witness replay")
        verified["exact_replayed_value"] = value
    return verified


def audit(rows, protocol):
    started = time.perf_counter()
    rows = sorted(rows, key=lambda row: row.index)
    epsilon = protocol["overlap_epsilon_seconds"]
    if len(rows) > 20:
        raise ValueError("structural diagnostic is capped at 20 rows")
    if sum(row.role == "core" for row in rows) != protocol["core_rows"] or sum(
        row.role == "buffer" for row in rows
    ) != protocol["buffer_rows"]:
        raise ValueError("input role counts differ from protocol")
    for row in rows:
        if (not math.isfinite(row.start) or not math.isfinite(row.end) or
                row.end - row.start < max(epsilon, protocol["minimum_interval_duration_seconds"])):
            raise ValueError("nonfinite or sub-epsilon interval is outside this protocol")
        for attribute in ("miles", "seconds"):
            value = getattr(row, attribute)
            if value is not None and not math.isfinite(value):
                raise ValueError("query values must be finite or explicitly missing")
    cells, outcomes, comparisons, unresolved = [], [], [], []
    overlap_edges = sum(
        min(left.end, right.end) - max(left.start, right.start) + reference.TOL >= epsilon
        for i, left in enumerate(rows) for right in rows[i + 1:]
    )
    possible_edges = len(rows) * (len(rows) - 1) // 2
    geometry = {
        "row_count": len(rows), "overlap_edges": overlap_edges,
        "possible_pair_edges": possible_edges,
        "complete_overlap_graph": overlap_edges == possible_edges,
        "all_rows_common_overlap_seconds": max(0.0, min(row.end for row in rows) - max(row.start for row in rows)),
    }
    for capacity in protocol["capacities"]:
        enum_started = time.perf_counter()
        full = reference.build_master(rows, capacity, epsilon=epsilon)
        independent = {mask for mask in range(1, 1 << len(rows))
                       if event_valid(rows, mask, capacity, epsilon, "ordered")}
        if independent != {c.member_mask for c in full.columns}:
            raise AssertionError("independent complete column-universe check failed")
        enumeration_seconds = time.perf_counter() - enum_started
        masters = {family: restricted_master(full, family) for family in FAMILIES}
        supports = {family: sorted({mask.bit_count() for mask in master.reachable_buffer_masks})
                    for family, master in masters.items()}
        if not (masters["pair"].reachable_buffer_masks <= masters["clique"].reachable_buffer_masks
                <= full.reachable_buffer_masks):
            raise AssertionError("feasible-world projections violate family nesting")
        common = sorted(set(supports["ordered"]) & set(supports["pair"]) & set(supports["clique"]) - {0})
        for family, master in masters.items():
            family_started = time.perf_counter()
            checks = []
            for q in range(protocol["buffer_rows"] + 1):
                result = verify_milp(master, family, q, protocol["milp_seconds_per_solve"])
                feasible = q in supports[family]
                status = result["status"]
                agrees = (status == "OPTIMAL_NUMERICAL_MILP_REPLAYED" if feasible
                          else status.startswith("PROVEN_INFEASIBLE"))
                if status == "UNRESOLVED_MILP_VERIFICATION":
                    unresolved.append({"capacity": capacity, "family": family, "q": q, "type": "support"})
                elif not agrees:
                    raise AssertionError("support feasibility differs between enumeration and MILP")
                checks.append({"q": q, "enumeration_feasible": feasible, **result, "agreement": agrees})
            cells.append({
                "capacity": capacity, "family": family,
                **reference.support_frontier(master),
                "columns_excluded_from_ordered": len(full.columns) - len(master.columns),
                "ordered_support_counts_excluded": sorted(set(supports["ordered"]) - set(supports[family])),
                "common_positive_q": common,
                "full_column_universe_independently_checked": True,
                "support_checks": checks,
                "ordered_enumeration_and_column_check_seconds": enumeration_seconds,
                "support_verification_seconds": time.perf_counter() - family_started,
            })
        for q in common:
            for query in protocol["queries"]:
                exact = {}
                for family, master in masters.items():
                    endpoint_started = time.perf_counter()
                    bounds = exact_bounds(master, q, query)
                    cell = {"capacity": capacity, "family": family, "q": q, "query": query["name"],
                            "status": bounds["status"],
                            "reachable_q_buffer_masks": sum(mask.bit_count() == q for mask in master.reachable_buffer_masks),
                            "all_possible_q_buffer_subsets": math.comb(protocol["buffer_rows"], q)}
                    if bounds["status"] != "CERTIFIED_EXACT_FINITE_FRONTIER":
                        outcomes.append(cell)
                        continue
                    exact[family] = bounds
                    legacy = reference.solve_attribute(master, q, query["attribute"], scale=query["scale"])
                    for direction in ("lower", "upper"):
                        value = bounds[direction]
                        if abs(legacy[direction] - float(value)) > protocol["comparison_tolerance"]:
                            raise AssertionError("rational endpoints disagree with reference scan")
                        witness = exact_witness(master, bounds[direction + "_mask"])
                        cell[direction] = float(value)
                        cell[direction + "_rational"] = str(value)
                        cell[direction + "_witness_sha256"] = witness_hash(master, family, witness, q)
                        check = verify_milp(master, family, q, protocol["milp_seconds_per_solve"],
                                            query, maximize=direction == "upper")
                        cell[direction + "_milp_status"] = check["status"]
                        if check["status"] == "OPTIMAL_NUMERICAL_MILP_REPLAYED":
                            if abs(float(check["exact_replayed_value"] - value)) > protocol["comparison_tolerance"]:
                                raise AssertionError("exact and independently replayed MILP endpoints differ")
                            cell[direction + "_milp_witness_sha256"] = check["witness_sha256"]
                        elif check["status"] == "UNRESOLVED_MILP_VERIFICATION":
                            unresolved.append({"capacity": capacity, "family": family, "q": q,
                                               "query": query["name"], "direction": direction, "type": "endpoint"})
                        else:
                            raise AssertionError("MILP rejects enumeration-certified endpoint")
                    cell["width"] = float(bounds["upper"] - bounds["lower"])
                    cell["width_rational"] = str(bounds["upper"] - bounds["lower"])
                    cell["elapsed_seconds"] = time.perf_counter() - endpoint_started
                    outcomes.append(cell)
                for family in ("pair", "clique"):
                    row = {"capacity": capacity, "q": q, "query": query["name"], "restriction": family}
                    if "ordered" not in exact or family not in exact:
                        comparisons.append({**row, "status": "INELIGIBLE_MISSING_PUBLIC_QUERY_VALUES"})
                        continue
                    full_lower, full_upper = exact["ordered"]["lower"], exact["ordered"]["upper"]
                    lower, upper = exact[family]["lower"], exact[family]["upper"]
                    if not full_lower <= lower <= upper <= full_upper:
                        raise AssertionError("restricted frontier violates nesting")
                    comparisons.append({
                        **row, "status": "CERTIFIED_FIXED_Q_COMPARISON",
                        "ordered_lower": float(full_lower), "ordered_upper": float(full_upper),
                        "restricted_lower": float(lower), "restricted_upper": float(upper),
                        "lower_increase": float(lower - full_lower), "upper_decrease": float(full_upper - upper),
                        "width_decrease": float((full_upper - full_lower) - (upper - lower)),
                        "endpoint_changed_exactly": full_lower != lower or full_upper != upper,
                    })
    certified = [row for row in comparisons if row["status"] == "CERTIFIED_FIXED_Q_COMPARISON"]
    return {
        "report_version": "nyc-fixed-time-structure-audit/v1",
        "design": protocol,
        "input_geometry": geometry,
        "summary": {
            "verification_status": "PASS" if not unresolved else "HOLD_UNRESOLVED_VERIFICATION",
            "family_capacity_cells": len(cells),
            "outcome_endpoint_pairs": len(outcomes),
            "certified_endpoint_pairs": sum(row["status"] == "CERTIFIED_EXACT_FINITE_FRONTIER" for row in outcomes),
            "missing_query_value_pairs": sum(row["status"] == "INELIGIBLE_MISSING_PUBLIC_QUERY_VALUES" for row in outcomes),
            "fixed_q_comparisons": len(certified),
            "changed_fixed_q_comparisons": sum(row["endpoint_changed_exactly"] for row in certified),
            "comparisons_by_restriction": {
                family: {"total": sum(row["restriction"] == family for row in certified),
                         "changed": sum(row["restriction"] == family and row["endpoint_changed_exactly"] for row in certified)}
                for family in ("pair", "clique")
            },
            "unresolved_verification_count": len(unresolved),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "support_cells": cells, "outcome_cells": outcomes,
        "comparisons": comparisons, "unresolved_verifications": unresolved,
        "claim_boundary": {
            "supported": "Conditional effects of restricting event families on one fixed small public exact-time input.",
            "not_supported": "True run recovery, candidate-world coverage, population prevalence, city-scale certification, or proof of novelty relative to prior work.",
        },
        "redaction": {"aggregate_only": True, "raw_rows_emitted": False,
                      "event_columns_emitted": False, "witnesses_emitted": False},
    }


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tables = {"SUPPORT.csv": report["support_cells"], "OUTCOMES.csv": report["outcome_cells"],
              "COMPARISONS.csv": report["comparisons"]}
    for name, rows in tables.items():
        keys = list(dict.fromkeys(key for row in rows for key in row if key != "support_checks"))
        with (output / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: json.dumps(row[key]) if isinstance(row.get(key), (dict, list)) else row.get(key)
                                 for key in keys})
    lines = ["# NYC fixed-input event-structure audit", "",
             f"Verification: **{report['summary']['verification_status']}**.", "",
             "One new retrospective 4-core/12-buffer extraction; all comparators share exact times, roles and query values.",
             "Buffer selection requires nonmissing miles and seconds. K=2 restricts event membership; C restricts simultaneous occupancy.", "",
             f"Fixed-q endpoint changes: **{report['summary']['changed_fixed_q_comparisons']}/{report['summary']['fixed_q_comparisons']}** comparisons.", "",
             "| C | Family | Columns | Reachable buffer counts | Maximum |",
             "|---|---|---:|---|---:|"]
    for cell in report["support_cells"]:
        lines.append(f"| {cell['capacity']} | {cell['family']} | {cell['run_column_count']} | "
                     f"{cell['reachable_selected_buffer_counts']} | {cell['maximum_selected_buffers']} |")
    lines += ["", "## Equal-count outcome comparisons", "",
              "Every positive q feasible in all three models is included. Different model-specific maxima are not compared as the same outcome query.", "",
              "| C | q | Query | Restriction | Ordered interval | Restricted interval | Width decrease |",
              "|---|---:|---|---|---|---|---:|"]
    for row in report["comparisons"]:
        if row["status"] != "CERTIFIED_FIXED_Q_COMPARISON":
            lines.append(f"| {row['capacity']} | {row['q']} | {row['query']} | {row['restriction']} | missing | missing | n/a |")
            continue
        lines.append(f"| {row['capacity']} | {row['q']} | {row['query']} | {row['restriction']} | "
                     f"[{row['ordered_lower']:.6f}, {row['ordered_upper']:.6f}] | "
                     f"[{row['restricted_lower']:.6f}, {row['restricted_upper']:.6f}] | {row['width_decrease']:.6f} |")
    lines += ["", "## Verification and interpretation", "",
              f"The input overlap graph has {report['input_geometry']['overlap_edges']} of {report['input_geometry']['possible_pair_edges']} possible edges. All-row common overlap is {report['input_geometry']['all_rows_common_overlap_seconds']:.3f} seconds.", "",
              "All event subsets are checked independently by time sweep and overlap connectivity. Every support-count feasibility result and outcome endpoint is cross-checked with a binary column-selection MILP and direct event-witness replay. Endpoints also retain exact rational values and witness hashes in the JSON/CSV records.", "",
              "A timeout remains an unresolved verification. Public data does not reveal which admissible event grouping is true. Model exclusions are consequences of the restrictions, not evidence of actual sequential vehicle runs or mistakes in methods targeting another model.", "",
              "The JSON records the protocol, input, source and code hashes. Exact reproduction requires the same private input hash; a changed live source is a new snapshot, not a replay of this result."]
    if report["input_geometry"]["complete_overlap_graph"]:
        lines += ["", "This input is a complete interval-overlap clique. Consequently every capacity-feasible ordered event is already a clique: this instance contains no opportunity for a connected non-clique event. Its result does not establish a distinct empirical advantage for ordered events. Pair restrictions can still exclude larger selected-buffer counts, which is a different estimand effect from changing outcomes at fixed q."]
    if "provenance" in report:
        provenance = report["provenance"]
        lines += ["", "## Reproduce", "",
                  f"Input SHA-256: `{provenance['input_sha256']}`.",
                  f"Protocol SHA-256: `{provenance['protocol_sha256']}`.", "",
                  "```bash",
                  "python code/ai_pilot/data_pipeline/production_audit/run_nyc_structure_audit.py \\",
                  "  --output-dir tmp/nyc-structure-replay \\",
                  f"  --expected-input-sha256 {provenance['input_sha256']}",
                  "```", "",
                  "Add `--reuse-input` to replay an already fetched input. Only the `aggregate/` subdirectory is publishable; the row-level input cache must remain in ignored scratch."]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n")
    tex = [r"% Generated aggregate fragment; not yet included in the manuscript.",
           r"\paragraph{Fixed-input event-structure diagnostic.}",
           "A retrospective NYC audit fixes four core and twelve buffer rows,",
           "exact public times and query values, and compares ordered events,",
           r"exactly-two-row events, and clique events at $C\in\{2,3,4\}$.",
           "Only positive buffer counts feasible in all three families are used",
           "for outcome comparisons, with the same count on each side.",
           f"The audit certifies {report['summary']['certified_endpoint_pairs']} endpoint pairs;",
           f"{report['summary']['changed_fixed_q_comparisons']} of {report['summary']['fixed_q_comparisons']} fixed-count comparisons change an endpoint.",
           r"\begin{table}[t]", r"\centering", r"\begin{tabular}{c|rrr}",
           r"$C$ & Ordered & Two-row & Clique \\", r"\hline"]
    for capacity in report["design"]["capacities"]:
        maxima = {cell["family"]: cell["maximum_selected_buffers"]
                  for cell in report["support_cells"] if cell["capacity"] == capacity}
        tex.append(f"{capacity} & {maxima['ordered']} & {maxima['pair']} & {maxima['clique']} " + r"\\")
    tex += [r"\end{tabular}",
            r"\caption{Maximum selected-buffer counts on one fixed NYC small audit input. These model-specific maxima are not fixed-count outcome comparisons.}",
            r"\label{tab:nyc-structure-diagnostic}", r"\end{table}"]
    if report["input_geometry"]["complete_overlap_graph"]:
        tex += [f"All sixteen intervals share {report['input_geometry']['all_rows_common_overlap_seconds']:g} seconds of common overlap.",
                "Thus every admissible ordered event is already a clique; this",
                "instance does not test the value of connected non-clique events.",
                "The result establishes neither a distinct public-data outcome",
                "advantage for ordered structure nor a general equivalence of the models."]
    tex += ["Buffer selection requires complete public miles and trip-time values.",
            "No true-event recovery, true-world coverage or population claim follows."]
    (output / "RESULTS.tex").write_text("\n".join(tex) + "\n")
    files = ("REPORT.json", "REPORT.md", "RESULTS.tex", *tables)
    manifest = {"report_version": "nyc-structure-artifact-manifest/v1",
                "files_sha256": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in files},
                "aggregate_only": True}
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
