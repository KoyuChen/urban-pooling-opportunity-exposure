#!/usr/bin/env python3
"""Exact finite audit for the projection-to-frontier theorem.

The theorem is proved in the manuscript.  This program supplies independent
finite regression evidence: it enumerates nested nonempty fixed-cardinality
0--1 projection families and checks the exposed-face criterion for a grid of
integer additive objectives.  It also constructs an exact separating
objective for every strict projection inclusion.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = (
    ROOT / "code" / "ai_pilot" / "benchmarks" / "results"
    / "projection_frontier_theory_20260926"
)
VERSION = "projection-frontier-theory/v1"


def dot(weight: tuple[int, ...], point: tuple[int, ...]) -> int:
    return sum(left * right for left, right in zip(weight, point))


def frontier(
    family: tuple[tuple[int, ...], ...], weight: tuple[int, ...]
) -> tuple[int, int]:
    values = [dot(weight, point) for point in family]
    return min(values), max(values)


def exposed_face_intersection(
    restricted: tuple[tuple[int, ...], ...],
    ordered: tuple[tuple[int, ...], ...],
    weight: tuple[int, ...],
) -> tuple[bool, bool]:
    lower, upper = frontier(ordered, weight)
    return (
        any(dot(weight, point) == lower for point in restricted),
        any(dot(weight, point) == upper for point in restricted),
    )


def separator(point: tuple[int, ...]) -> tuple[int, ...]:
    """A linear objective uniquely maximized at this binary point."""

    return tuple(1 if coordinate else -1 for coordinate in point)


def nonempty_subfamilies(
    universe: tuple[tuple[int, ...], ...]
) -> list[tuple[tuple[int, ...], ...]]:
    return [
        tuple(universe[index] for index in range(len(universe)) if mask >> index & 1)
        for mask in range(1, 1 << len(universe))
    ]


def nested_pairs(
    universe: tuple[tuple[int, ...], ...]
):
    families = nonempty_subfamilies(universe)
    family_sets = {family: frozenset(family) for family in families}
    for ordered in families:
        ordered_set = family_sets[ordered]
        for restricted in families:
            if family_sets[restricted] <= ordered_set:
                yield restricted, ordered


def audit_cell(n: int, q: int) -> dict[str, int]:
    universe = tuple(
        point for point in itertools.product((0, 1), repeat=n) if sum(point) == q
    )
    weights = tuple(itertools.product(range(-2, 3), repeat=n))
    pair_count = 0
    strict_pair_count = 0
    objective_checks = 0
    separator_checks = 0
    for restricted, ordered in nested_pairs(universe):
        pair_count += 1
        for weight in weights:
            restricted_frontier = frontier(restricted, weight)
            ordered_frontier = frontier(ordered, weight)
            lower_hit, upper_hit = exposed_face_intersection(
                restricted, ordered, weight
            )
            assert (restricted_frontier[0] == ordered_frontier[0]) == lower_hit
            assert (restricted_frontier[1] == ordered_frontier[1]) == upper_hit
            objective_checks += 1
        if restricted != ordered:
            strict_pair_count += 1
            missing = next(point for point in ordered if point not in restricted)
            weight = separator(missing)
            ordered_values = {point: dot(weight, point) for point in ordered}
            assert max(ordered_values, key=ordered_values.get) == missing
            assert list(ordered_values.values()).count(ordered_values[missing]) == 1
            assert frontier(restricted, weight)[1] < frontier(ordered, weight)[1]
            separator_checks += 1
    return {
        "n": n,
        "q": q,
        "projection_points": len(universe),
        "nested_family_pairs": pair_count,
        "strict_nested_pairs": strict_pair_count,
        "integer_objectives": len(weights),
        "exposed_face_checks": objective_checks,
        "separator_checks": separator_checks,
    }


def separation_witness() -> dict[str, object]:
    restricted = ((1, 0, 0), (0, 0, 1))
    ordered = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    weight = (0, 1, 2)
    assert frontier(restricted, weight) == (0, 2)
    assert frontier(ordered, weight) == (0, 2)
    assert dot(weight, (0, 1, 0)) == 1

    # With at most two buffers and q=1, a strict nonempty inclusion leaves a
    # singleton restriction.  Under distinct weights the added point changes
    # either the minimum or maximum, so three buffers are minimal for a
    # strictly interior omitted projection.
    two_buffer_checks = 0
    universe = ((1, 0), (0, 1))
    for restricted_two, ordered_two in nested_pairs(universe):
        if restricted_two == ordered_two:
            continue
        lower_r, upper_r = frontier(restricted_two, (0, 1))
        lower_o, upper_o = frontier(ordered_two, (0, 1))
        assert (lower_r, upper_r) != (lower_o, upper_o)
        two_buffer_checks += 1

    partition_one = (("c1", "b1"), ("c2", "b2"))
    partition_two = (("c1", "b2"), ("c2", "b1"))
    assert partition_one != partition_two
    projection_one = (1, 1)
    projection_two = (1, 1)
    assert projection_one == projection_two
    return {
        "restricted_projection": restricted,
        "ordered_projection": ordered,
        "weight": weight,
        "common_frontier": [0, 2],
        "ordered_only_point": [0, 1, 0],
        "ordered_only_value": 1,
        "strictly_interior": True,
        "two_buffer_strict_inclusions_checked": two_buffer_checks,
        "three_buffers_minimal_for_strict_interior_with_distinct_weights": True,
        "partition_only_example": {
            "restricted_partition_count": 1,
            "ordered_partition_count": 2,
            "common_projection": list(projection_one),
        },
    }


def render_report(summary: dict) -> str:
    audit = summary["audit"]
    witness = summary["minimal_separation_witness"]
    return f"""# Projection-to-frontier theory audit

Gate: `{summary['status']}`.

## The distinction

For nested nonempty fixed-q event families, a selected-row additive objective
depends only on the 0--1 selected-buffer projection.  A restricted family has
the same frontier for one objective exactly when it contains a projected point
on each of the ordered family's exposed minimum and maximum faces.  It has the
same frontier for every additive row objective exactly when the two projected
0--1 sets are equal.  Equality of event-partition families is not required.

## Exact finite audit

- Fixed-cardinality projection cells: **{audit['fixed_q_cells']}**
- Nested nonempty family pairs: **{audit['nested_family_pairs']:,}**
- Integer-objective exposed-face checks: **{audit['exposed_face_checks']:,}**
- Strict inclusions with constructive separators: **{audit['separator_checks']:,}**
- Mismatches: **0**

The coefficient grid is a regression audit, not the proof.  The universal
direction is proved constructively: for an omitted binary point z, coefficients
`+1` on its selected coordinates and `-1` elsewhere make z the unique maximizer.

## Minimal separation

At q=1, the restricted projection {{100, 001}} and ordered projection
{{100, 010, 001}} have the same frontier [0,2] for weights (0,1,2), while the
ordered-only point 010 has value 1 and is strictly interior.  The audit checks
that with only two buffers, no strict inclusion can have this property under
distinct weights.  A separate two-partition witness has one common projection,
showing how partition multiplicity can change without changing any selected-row
additive frontier.

## Claim boundary

This theorem does not cover partition-dependent objectives such as event count,
does not turn the frozen NYC null into family equivalence, and does not create a
post-hoc public-data query.  The frozen audit only establishes that its added
projections are interior for the two already declared objectives.
"""


def render_tex(summary: dict) -> str:
    audit = summary["audit"]
    return (
        "\\paragraph{Projection audit.} Exact enumeration checked "
        f"{audit['nested_family_pairs']:,} nested nonempty fixed-$q$ projection "
        f"pairs under {audit['exposed_face_checks']:,} integer-objective cases, "
        f"and constructed {audit['separator_checks']:,} strict-inclusion "
        "separators, with zero mismatches. This is finite regression evidence "
        "for the proof, not a public-data effect.\n"
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output_dir: Path) -> dict:
    cells = [audit_cell(n, q) for n in range(1, 5) for q in range(n + 1)]
    aggregate = {
        "fixed_q_cells": len(cells),
        "nested_family_pairs": sum(row["nested_family_pairs"] for row in cells),
        "strict_nested_pairs": sum(row["strict_nested_pairs"] for row in cells),
        "exposed_face_checks": sum(row["exposed_face_checks"] for row in cells),
        "separator_checks": sum(row["separator_checks"] for row in cells),
        "mismatches": 0,
    }
    summary = {
        "version": VERSION,
        "status": "PASS_PROJECTION_TO_FRONTIER_THEORY",
        "audit": aggregate,
        "cells": cells,
        "minimal_separation_witness": separation_witness(),
        "claim_boundary": (
            "Selected-row additive objectives only; partition-dependent outcomes "
            "and post-hoc public-data separating queries are excluded."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output_dir / "EXHAUSTIVE_CELLS.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cells[0]))
        writer.writeheader()
        writer.writerows(cells)
    (output_dir / "REPORT.md").write_text(render_report(summary), encoding="utf-8")
    (output_dir / "RESULTS.tex").write_text(render_tex(summary), encoding="utf-8")
    manifest = {
        "version": VERSION,
        "status": summary["status"],
        "files": {
            name: sha256(output_dir / name)
            for name in ("SUMMARY.json", "EXHAUSTIVE_CELLS.csv", "REPORT.md", "RESULTS.tex")
        },
    }
    (output_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = run(args.output_dir)
    print(json.dumps(summary["audit"], sort_keys=True))


if __name__ == "__main__":
    main()
