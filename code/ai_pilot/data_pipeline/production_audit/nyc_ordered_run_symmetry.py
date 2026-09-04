#!/usr/bin/env python3
"""Exact symmetry reduction for the NYC ordered latent-run MILP.

The base formulation labels every open run by one of its core rows. A physical
partition therefore has multiple equivalent MILP representations whenever a run
contains several core rows. This module canonicalizes the label: the root of an
open run must be the smallest-index core row assigned to that run.

The restriction is exact. Every feasible unlabeled run partition has exactly one
such canonical representation, while no physical partition is removed.
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import lil_matrix, vstack

import live_nyc_hvfhv_ordered_run_smoke as base


def canonical_root_columns(program: base.Program) -> list[int]:
    """Return x-columns forbidden by the minimum-core-root convention."""
    roots = sorted(program.roots)
    forbidden: list[int] = []
    for root in roots:
        for member in roots:
            if member < root and (member, root) in program.x_col:
                forbidden.append(program.x_col[(member, root)])
    return forbidden


def canonicalize_program(program: base.Program) -> base.Program:
    """Append exact x=0 symmetry-breaking rows and return ``program``.

    The Program dataclass is mutable, so this intentionally augments the existing
    sparse matrix rather than rebuilding the interval formulation.
    """
    forbidden = canonical_root_columns(program)
    if not forbidden:
        return program

    extra = lil_matrix((len(forbidden), program.matrix.shape[1]), dtype=float)
    for row, col in enumerate(forbidden):
        extra[row, col] = 1.0
    program.matrix = vstack([program.matrix, extra.tocsr()], format="csr")
    zeros = np.zeros(len(forbidden), dtype=float)
    program.lower = np.concatenate([program.lower, zeros])
    program.upper = np.concatenate([program.upper, zeros])
    return program


def peak_core_occupancy(rows: list[base.ModelTrip]) -> int:
    """Maximum number of core intervals simultaneously active on any segment."""
    segments = base.elementary_segments(rows)
    peak = 0
    for segment in segments:
        active = sum(row.role == "core" and base.active_on(row, segment) for row in rows)
        peak = max(peak, active)
    return peak


def peak_capacity_run_lower_bound(rows: list[base.ModelTrip], capacity: int) -> float:
    """Analytic run-count/core lower bound from the peak core clique."""
    import math

    core_count = sum(row.role == "core" for row in rows)
    if core_count == 0:
        raise ValueError("no core rows")
    return math.ceil(peak_core_occupancy(rows) / capacity) / core_count


def self_test() -> None:
    rows = base.synthetic_chain()
    for capacity in (2, 3):
        raw = base.build_program(rows, capacity)
        canonical = canonicalize_program(base.build_program(rows, capacity))
        for query in base.QUERIES:
            coeff_raw = base.objective(raw, query)
            coeff_can = base.objective(canonical, query)
            for maximize in (False, True):
                left = base.solve(raw, coeff_raw, maximize, 10.0)
                right = base.solve(canonical, coeff_can, maximize, 10.0)
                assert left["status"] == right["status"] == base.CERTIFIED
                assert abs(left["value"] - right["value"]) <= 1e-8

    # Three simultaneous core intervals imply at least ceil(3/C) runs.
    from datetime import datetime, timedelta

    start = datetime(2023, 1, 1, 12, 0)
    clique = [
        base.ModelTrip(
            i,
            "HV",
            "core",
            start,
            start + timedelta(minutes=10),
            "1",
            str(i),
            1.0,
            600.0,
            10.0,
            8.0,
        )
        for i in range(3)
    ]
    assert peak_core_occupancy(clique) == 3
    assert abs(peak_capacity_run_lower_bound(clique, 2) - 2 / 3) <= 1e-12
    assert abs(peak_capacity_run_lower_bound(clique, 3) - 1 / 3) <= 1e-12
    print("NYC ordered-run canonical-root self-test: PASS")


if __name__ == "__main__":
    self_test()
