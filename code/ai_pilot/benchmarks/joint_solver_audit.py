#!/usr/bin/env python3
"""Deterministic small-world agreement audit for the joint solver.

The exact exhaustive backend is treated as the certificate.  SciPy/HiGHS is
only checked for numerical agreement; agreement does not convert it into an
exact mathematical oracle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
BOUNDS = HERE.parent / "bounds"
if str(BOUNDS) not in sys.path:
    sys.path.insert(0, str(BOUNDS))

from joint_label_matching import (  # noqa: E402
    SCIPY_MILP_AVAILABLE,
    solve_joint_label_matching_endpoints,
)


def _instance(rng: np.random.Generator, index: int):
    node_count = int(rng.choice([4, 6]))
    node_ids = [f"m{index:03d}:n{i}" for i in range(node_count)]
    values = ("A", "B", "C")
    support_rows = []
    for _ in node_ids:
        mask = rng.random(len(values)) < 0.72
        if not mask.any():
            mask[int(rng.integers(0, len(values)))] = True
        support_rows.append([value for value, keep in zip(values, mask) if keep])
    nodes = pd.DataFrame(
        {
            "node_id": node_ids,
            "role": ["core"] * node_count,
            "cell": ["g"] * node_count,
            "label_support": support_rows,
        }
    )

    edge_rows = []
    for left in range(node_count):
        for right in range(left + 1, node_count):
            allowed = [
                [u, v]
                for u in support_rows[left]
                for v in support_rows[right]
                if rng.random() < 0.72
            ]
            edge_rows.append(
                {
                    "edge_id": f"m{index:03d}:e{left}:{right}",
                    "u": node_ids[left],
                    "v": node_ids[right],
                    "allowed_label_pairs": allowed,
                    "omitted": int(rng.random() < 0.20),
                }
            )
    edges = pd.DataFrame(edge_rows)

    lower = int(rng.integers(0, node_count + 1))
    upper = int(rng.integers(lower, node_count + 1))
    counts = pd.DataFrame(
        {"cell": ["g"], "value": ["A"], "lower": [lower], "upper": [upper]}
    )
    gamma = int(rng.integers(0, node_count // 2 + 1))
    return nodes, edges, counts, gamma


def run(seed: int, instances: int) -> dict:
    if not SCIPY_MILP_AVAILABLE:
        raise RuntimeError("SciPy milp/HiGHS is required for the agreement audit")
    rng = np.random.default_rng(seed)
    resolved = feasible = infeasible = endpoint_agreements = 0
    for index in range(instances):
        nodes, edges, counts, gamma = _instance(rng, index)
        kwargs = {
            "nodes": nodes,
            "edges": edges,
            "label_catalog": {"A": 0, "B": 1, "C": 1},
            "count_bounds": counts,
            "omitted_col": "omitted",
            "gamma": gamma,
        }
        exact = solve_joint_label_matching_endpoints(**kwargs, backend="fallback")
        numeric = solve_joint_label_matching_endpoints(**kwargs, backend="scipy")
        exact_feasible = exact.status == "EXACT_OPTIMAL"
        numeric_feasible = numeric.status == "NUMERICALLY_OPTIMAL"
        exact_infeasible = exact.status == "PROVEN_INFEASIBLE"
        numeric_infeasible = numeric.status in {
            "PROVEN_INFEASIBLE",
            "NUMERICALLY_INFEASIBLE",
        }
        if not ((exact_feasible and numeric_feasible) or (exact_infeasible and numeric_infeasible)):
            raise AssertionError(
                f"feasibility disagreement at instance {index}: "
                f"{exact.status} versus {numeric.status}"
            )
        resolved += 1
        if exact_feasible:
            feasible += 1
            if not (
                np.isclose(exact.lower, numeric.lower, atol=1e-9, rtol=0)
                and np.isclose(exact.upper, numeric.upper, atol=1e-9, rtol=0)
            ):
                raise AssertionError(
                    f"endpoint disagreement at instance {index}: "
                    f"{(exact.lower, exact.upper)} versus {(numeric.lower, numeric.upper)}"
                )
            endpoint_agreements += 1
        else:
            infeasible += 1
    return {
        "seed": seed,
        "instances": instances,
        "resolved_agreements": resolved,
        "feasible_instances": feasible,
        "infeasible_instances": infeasible,
        "endpoint_agreements_on_feasible_instances": endpoint_agreements,
        "exact_backend": "fallback exhaustive enumeration",
        "numerical_backend": "SciPy milp/HiGHS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=314159)
    parser.add_argument("--instances", type=int, default=250)
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "results" / "joint_solver_audit.json",
    )
    args = parser.parse_args()
    result = run(args.seed, args.instances)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
