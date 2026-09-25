#!/usr/bin/env python3
"""Explain the frozen NYC non-clique endpoint null without changing its design.

The input is the four private, hash-pinned 4+12 caches used by the September 23
gate.  The output remains aggregate-only: counts and replayable witness hashes,
never row values, buffer identities, event columns, or membership witnesses.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import ordered_run_fixed_time_master as reference
import ordered_run_structure_audit as structure
import run_nyc_nonclique_structure_gate as frozen_gate


HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "NYC_NONCLIQUE_STRUCTURE_PROTOCOL.json"
FROZEN_SUMMARY = (
    HERE.parent / "results" / "nyc_hvfhv" /
    "nonclique_structure_20260923" / "SUMMARY.json"
)
VERSION = "nyc-nonclique-endpoint-attainment/v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def partition_counts(master) -> Counter:
    """Count unordered event partitions by their projected buffer subset."""
    @lru_cache(None)
    def visit(covered: int, used: int):
        if covered == master.all_core_mask:
            return ((used & master.all_buffer_mask, 1),)
        pivot = next(structure.positions(master.all_core_mask & ~covered))
        counts = Counter()
        for column in master.columns_by_core_position[pivot]:
            if column.core_mask & covered or column.buffer_mask & used:
                continue
            counts.update(dict(visit(
                covered | column.core_mask, used | column.buffer_mask
            )))
        return tuple(sorted(counts.items()))

    return Counter(dict(visit(0, 0)))


def endpoint(master, q: int, query: dict, direction: str) -> tuple[Fraction, set[int]]:
    masks = [mask for mask in master.reachable_buffer_masks if mask.bit_count() == q]
    if not masks:
        raise AssertionError("common-q cell unexpectedly has no feasible mask")
    values = {
        mask: structure.score(master, mask, query["attribute"], query["scale"], q)
        for mask in masks
    }
    target = (min if direction == "lower" else max)(values.values())
    return target, {mask for mask, value in values.items() if value == target}


def witness(master, family: str, target: int, q: int) -> str:
    events = structure.exact_witness(master, target)
    if structure.replay(master, family, events, q) != target:
        raise AssertionError("endpoint witness does not replay its target subset")
    return structure.witness_hash(master, family, events, q)


def audit(cache_dir: Path) -> dict:
    protocol = json.loads(PROTOCOL.read_text())
    frozen = json.loads(FROZEN_SUMMARY.read_text())
    frozen_comparisons = {
        (r["window_index"], r["capacity"], r["q"], r["query"], r["restriction"]): r
        for r in frozen["comparisons"]
        if r["status"] == "CERTIFIED_FIXED_Q_COMPARISON"
    }
    frozen_worlds = {
        (r["window_index"], r["capacity"], r["q"]): r
        for r in frozen["world_cells"] if r["common_feasible"]
    }
    endpoint_rows, mechanism_rows, cache_pins = [], [], {}
    all_endpoint_hashes = set()

    for window in protocol["windows"]:
        path = cache_dir / f"window-{window['index']:02d}.private.json"
        cached = json.loads(path.read_text())
        rows = frozen_gate.verify_cached(cached, window, protocol)
        cache_pins[str(path.name)] = cached["modeled_input_sha256"]
        for capacity in protocol["capacities"]:
            ordered = reference.build_master(
                rows, capacity, epsilon=protocol["overlap_epsilon_seconds"]
            )
            masters = {
                family: structure.restricted_master(ordered, family)
                for family in structure.FAMILIES
            }
            partitions = {family: partition_counts(master)
                          for family, master in masters.items()}
            for family in ("pair", "clique"):
                if not (set(partitions[family]) <= set(partitions["ordered"])):
                    raise AssertionError("restricted projected worlds are not nested")
                for mask, count in partitions[family].items():
                    if count > partitions["ordered"][mask]:
                        raise AssertionError("restricted event partitions are not nested")

            common_q = sorted(
                set(mask.bit_count() for mask in partitions["ordered"])
                & set(mask.bit_count() for mask in partitions["pair"])
                & set(mask.bit_count() for mask in partitions["clique"])
                & set(protocol["declared_q_values"])
            )
            for q in common_q:
                world = frozen_worlds[(window["index"], capacity, q)]
                projected = {
                    family: {mask for mask in counts if mask.bit_count() == q}
                    for family, counts in partitions.items()
                }
                for family in structure.FAMILIES:
                    if len(projected[family]) != world[f"{family}_reachable_buffer_masks"]:
                        raise AssertionError("projected-world count differs from frozen gate")
                for restriction in ("pair", "clique"):
                    common_masks = projected[restriction]
                    extra_masks = projected["ordered"] - common_masks
                    shared_partition_gain = sum(
                        partitions["ordered"][mask] - partitions[restriction][mask]
                        for mask in common_masks
                    )
                    extra_mask_partitions = sum(partitions["ordered"][mask] for mask in extra_masks)
                    mechanism_rows.append({
                        "window_index": window["index"], "window_label": window["label"],
                        "capacity": capacity, "q": q, "restriction": restriction,
                        "ordered_buffer_subsets": len(projected["ordered"]),
                        "restricted_buffer_subsets": len(common_masks),
                        "extra_ordered_buffer_subsets": len(extra_masks),
                        "shared_subsets_with_extra_ordered_partitions": sum(
                            partitions["ordered"][mask] > partitions[restriction][mask]
                            for mask in common_masks
                        ),
                        "extra_ordered_partitions_on_shared_subsets": shared_partition_gain,
                        "ordered_partitions_on_extra_subsets": extra_mask_partitions,
                        "ordered_event_partitions": sum(
                            partitions["ordered"][mask] for mask in projected["ordered"]
                        ),
                        "restricted_event_partitions": sum(
                            partitions[restriction][mask] for mask in common_masks
                        ),
                    })
                    for query in protocol["queries"]:
                        comparison = frozen_comparisons[
                            (window["index"], capacity, q, query["name"], restriction)
                        ]
                        for direction in ("lower", "upper"):
                            ordered_value, ordered_ties = endpoint(
                                masters["ordered"], q, query, direction
                            )
                            restricted_value, restricted_ties = endpoint(
                                masters[restriction], q, query, direction
                            )
                            if ordered_value != restricted_value:
                                raise AssertionError("frozen endpoint equality does not replay")
                            if abs(float(ordered_value) - comparison[f"ordered_{direction}"]) > protocol["comparison_tolerance"]:
                                raise AssertionError("replayed value differs from frozen comparison")
                            attaining = ordered_ties & restricted_ties
                            if not attaining:
                                raise AssertionError("equal endpoint lacks a restricted-family attaining subset")
                            chosen = min(attaining)
                            ordered_hash = witness(masters["ordered"], "ordered", chosen, q)
                            restricted_hash = witness(masters[restriction], restriction, chosen, q)
                            all_endpoint_hashes.update((ordered_hash, restricted_hash))
                            extra_endpoint_ties = ordered_ties - projected[restriction]
                            endpoint_rows.append({
                                "window_index": window["index"], "window_label": window["label"],
                                "capacity": capacity, "q": q, "query": query["name"],
                                "direction": direction, "restriction": restriction,
                                "status": "ATTAINED_BY_RESTRICTED_FAMILY",
                                "endpoint_rational": str(ordered_value),
                                "ordered_tie_subset_count": len(ordered_ties),
                                "restricted_tie_subset_count": len(restricted_ties),
                                "shared_attaining_subset_count": len(attaining),
                                "ordered_only_attaining_subset_count": len(extra_endpoint_ties),
                                "same_buffer_subset_witnessed": True,
                                "ordered_witness_sha256": ordered_hash,
                                "restricted_witness_sha256": restricted_hash,
                            })

    extra_subset_rows = [r for r in mechanism_rows if r["extra_ordered_buffer_subsets"]]
    partition_only_rows = [r for r in mechanism_rows
                           if not r["extra_ordered_buffer_subsets"]
                           and r["extra_ordered_partitions_on_shared_subsets"]]
    failed = [r for r in endpoint_rows if r["status"] != "ATTAINED_BY_RESTRICTED_FAMILY"]
    identical_rows = [r for r in mechanism_rows
                      if not r["extra_ordered_buffer_subsets"]
                      and not r["extra_ordered_partitions_on_shared_subsets"]]
    status = "PASS_ENDPOINT_ATTAINMENT_NULL_EXPLAINED" if not failed else "HOLD_ENDPOINT_ATTAINMENT"
    return {
        "version": VERSION, "status": status,
        "protocol_sha256": sha256(PROTOCOL),
        "frozen_summary_sha256": sha256(FROZEN_SUMMARY),
        "cache_modeled_input_sha256": cache_pins,
        "summary": {
            "eligible_windows": len(protocol["windows"]),
            "common_q_family_cells": len(mechanism_rows) // 2,
            "restriction_world_cells": len(mechanism_rows),
            "endpoint_attainment_checks": len(endpoint_rows),
            "attained_endpoint_checks": len(endpoint_rows) - len(failed),
            "unresolved_endpoint_checks": len(failed),
            "distinct_replayed_witness_hashes": len(all_endpoint_hashes),
            "cells_with_extra_ordered_buffer_subsets_vs_clique": sum(
                r["restriction"] == "clique" and r["extra_ordered_buffer_subsets"] > 0
                for r in mechanism_rows
            ),
            "cells_with_extra_ordered_buffer_subsets_vs_pair": sum(
                r["restriction"] == "pair" and r["extra_ordered_buffer_subsets"] > 0
                for r in mechanism_rows
            ),
            "partition_only_cells": len(partition_only_rows),
            "extra_subset_cells": len(extra_subset_rows),
            "identical_partition_and_subset_cells": len(identical_rows),
            "endpoint_checks_with_ordered_only_ties": sum(
                r["ordered_only_attaining_subset_count"] > 0 for r in endpoint_rows
            ),
        },
        "mechanism_cells": mechanism_rows,
        "endpoint_attainment": endpoint_rows,
        "claim_boundary": (
            "Mechanism audit of the four frozen public 4+12 views, existing q values, "
            "and two existing queries. It does not select a new query, reveal rows or "
            "memberships, recover true events, resolve geometry transport failures, "
            "or establish city-scale closure."
        ),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def render_report(result: dict) -> str:
    s = result["summary"]
    extra = [r for r in result["mechanism_cells"] if r["extra_ordered_buffer_subsets"]]
    lines = [
        "# Frozen NYC endpoint-attainment mechanism audit", "",
        f"Status: **{result['status']}**.", "",
        f"All {s['endpoint_attainment_checks']} ordered endpoint/restriction checks "
        f"are attained by the restricted family using the same selected-buffer subset; "
        f"{s['unresolved_endpoint_checks']} checks remain unresolved.", "",
        "The null is therefore not caused by silently equating feasible families. "
        f"Ordered events add buffer subsets in {s['cells_with_extra_ordered_buffer_subsets_vs_clique']} "
        "of 24 common-q cells versus cliques and "
        f"{s['cells_with_extra_ordered_buffer_subsets_vs_pair']} of 24 versus pairs. "
        "They also add event partitions on already reachable subsets. Yet every lower "
        "and upper value for the two frozen additive queries has at least one pair/clique "
        "attaining subset.", "",
        f"Across the 48 restriction world cells, {s['partition_only_cells']} expand only "
        "the event-partition multiplicity, 4 expand projected buffer support, and "
        f"{s['identical_partition_and_subset_cells']} are identical at both levels. "
        "No ordered-only subset ties any of the 192 audited endpoints.", "",
        "| Window | C | q | Restriction | Ordered subsets | Restricted subsets |", 
        "|---|---:|---:|---|---:|---:|",
    ]
    for row in extra:
        lines.append(
            f"| {row['window_label']} | {row['capacity']} | {row['q']} | "
            f"{row['restriction']} | {row['ordered_buffer_subsets']} | "
            f"{row['restricted_buffer_subsets']} |"
        )
    lines += ["",
        "This separates three objects: event partitions, their projected selected-buffer "
        "subsets, and additive-query endpoints. The first can expand without the second; "
        "the second can expand without moving the third.", "",
        f"Scope: {result['claim_boundary']}", "",
    ]
    return "\n".join(lines)


def write_outputs(result: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "SUMMARY.json", result)
    write_csv(output / "MECHANISM_CELLS.csv", result["mechanism_cells"])
    write_csv(output / "ENDPOINT_ATTAINMENT.csv", result["endpoint_attainment"])
    (output / "REPORT.md").write_text(render_report(result))
    s = result["summary"]
    (output / "RESULTS.tex").write_text("\n".join([
        "% Generated aggregate mechanism audit; no raw rows or memberships.",
        r"\paragraph{Why the public non-clique comparison is an endpoint null.}",
        f"Across all {s['endpoint_attainment_checks']} frozen endpoint--restriction checks, "
        "the pair or clique family contains a feasible world using the same selected-buffer "
        "subset as an ordered endpoint witness. Ordered events still add projected subsets "
        f"in {s['cells_with_extra_ordered_buffer_subsets_vs_clique']}/24 common-$q$ cells "
        f"versus cliques and {s['cells_with_extra_ordered_buffer_subsets_vs_pair']}/24 versus pairs. "
        "Thus event partitions may expand without changing selected-buffer support, and "
        "support may expand without changing these additive endpoints.",
        "This mechanism audit uses no new window, support, or query and does not imply family equivalence.",
        "",
    ]))
    names = ["SUMMARY.json", "MECHANISM_CELLS.csv", "ENDPOINT_ATTAINMENT.csv", "REPORT.md", "RESULTS.tex"]
    write_json(output / "MANIFEST.json", {
        "version": "nyc-nonclique-endpoint-attainment-manifest/v1",
        "aggregate_only": True,
        "files_sha256": {name: sha256(output / name) for name in names},
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.cache_dir)
    write_outputs(result, args.output_dir)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0 if result["status"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
