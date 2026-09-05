#!/usr/bin/env python3
"""Predeclared paired audit of the compact event-slot lower-bound probe."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent / "data_pipeline" / "production_audit"
sys.path.insert(0, str(AUDIT))
sys.path.insert(0, str(HERE))

import disclosure_independent_ablation as source
import ordered_run_disclosure_separator as solver

PROTOCOL_PATH = HERE / "COMPACT_EVENT_SLOT_PROTOCOL.json"
EXACT = {"EXACT_BOUND_CLOSED", "OPTIMAL_WITHIN_TOLERANCE"}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rational_text(value: Fraction | None) -> str | None:
    return None if value is None else str(value)


def input_hash(rows, capacity, q, usage, pairs) -> str:
    payload = {
        "rows": [[r.index, r.role, float(r.start), float(r.end)] for r in rows],
        "capacity": capacity,
        "q": q,
        "usage": sorted([int(i), int(v)] for i, v in usage.items()),
        "pairs": sorted([int(i), int(j), int(v)] for (i, j), v in pairs.items()),
    }
    return sha_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def limits(protocol: dict[str, Any], variant: str) -> solver.Limits:
    compact_seconds = protocol["compact_probe_seconds"] if variant == "compact_probe" else 0.0
    return solver.Limits(
        seconds=protocol["seconds_per_endpoint"],
        nodes=protocol["node_limit"],
        iterations=protocol["pricing_iteration_limit"],
        pricing_cases=protocol["pricing_case_limit"],
        pricing_batch=protocol["pricing_batch"],
        compact_probe_seconds=compact_seconds,
        compact_probe_rows_min=protocol["compact_probe_rows_min"],
        compact_probe_max_k=protocol["compact_probe_max_k"],
        compact_probe_seek_witness=protocol["compact_probe_seek_witness"],
    )


def replay(rows, capacity, q, usage, pairs, events) -> int:
    return source.replay(rows, capacity, q, usage, pairs, events)


def run_one(protocol, core_count, capacity, seed, regime, variant, replicate):
    rows, _reference, usage, pairs = source.generate(core_count, seed, regime)
    q = protocol["support_multiplier"] * core_count
    started = time.perf_counter()
    endpoint = solver.minimize(
        rows,
        capacity,
        q,
        event_cost=protocol["event_cost"],
        usage_answers=usage,
        pair_answers=pairs,
        limits=limits(protocol, variant),
    )
    elapsed = time.perf_counter() - started
    replay_value = None
    if endpoint.witness:
        replay_value = replay(rows, capacity, q, usage, pairs, endpoint.witness)
        if endpoint.upper != replay_value:
            raise AssertionError("replayed objective differs from solver upper bound")
    if endpoint.lower is not None and endpoint.upper is not None and endpoint.lower > endpoint.upper:
        raise AssertionError("lower bound exceeds replayed incumbent")
    return {
        "cell": [core_count, capacity, seed, regime],
        "variant": variant,
        "replicate": replicate,
        "input_sha256": input_hash(rows, capacity, q, usage, pairs),
        "row_count": len(rows),
        "support_count": q,
        "status": endpoint.status,
        "reason": endpoint.reason,
        "lower_rational": rational_text(endpoint.lower),
        "upper_rational": rational_text(endpoint.upper),
        "absolute_gap_rational": None if endpoint.lower is None or endpoint.upper is None else str(endpoint.upper - endpoint.lower),
        "exact_status": endpoint.status in EXACT,
        "bound_equality": endpoint.lower is not None and endpoint.lower == endpoint.upper,
        "incumbent_available": endpoint.upper is not None,
        "replayed_event_count": None if replay_value is None else int(replay_value),
        "elapsed_seconds": elapsed,
        "solver_seconds": endpoint.seconds,
        "nodes": endpoint.counts.get("nodes", 0),
        "pricing_lp_calls": endpoint.counts.get("pricing_lp_calls", 0),
        "master_lp_calls": endpoint.counts.get("master_lp_calls", 0),
        "compact_probe_calls": endpoint.counts.get("compact_probe_calls", 0),
        "compact_probe_phase_one_calls": endpoint.counts.get("compact_probe_phase_one_calls", 0),
        "compact_probe_mip_calls": endpoint.counts.get("compact_probe_mip_calls", 0),
        "compact_probe_certified_k": endpoint.counts.get("compact_probe_certified_k", 0),
        "compact_probe_witnesses": endpoint.counts.get("compact_probe_witnesses", 0),
        "relation_witness_serialized": False,
    }


def validate_intersections(records):
    grouped = {}
    for record in records:
        grouped.setdefault((tuple(record["cell"]), record["replicate"]), []).append(record)
    for group in grouped.values():
        lowers = [Fraction(r["lower_rational"]) for r in group if r["lower_rational"]]
        uppers = [Fraction(r["upper_rational"]) for r in group if r["upper_rational"]]
        if lowers and uppers and max(lowers) > min(uppers):
            raise AssertionError("variant bounds have empty exact intersection")


def summarize_variant(records, variant):
    rows = [r for r in records if r["variant"] == variant]
    elapsed = [r["elapsed_seconds"] for r in rows]
    gaps = [float(Fraction(r["absolute_gap_rational"])) for r in rows if r["absolute_gap_rational"] is not None]
    return {
        "run_count": len(rows),
        "exact_status_count": sum(r["exact_status"] for r in rows),
        "bound_equality_count": sum(r["bound_equality"] for r in rows),
        "incumbent_count": sum(r["incumbent_available"] for r in rows),
        "technical_failure_count": sum(r["status"] == "TECHNICAL_FAILURE" for r in rows),
        "median_elapsed_seconds": statistics.median(elapsed),
        "total_elapsed_seconds": sum(elapsed),
        "median_gap": statistics.median(gaps) if gaps else None,
        "total_pricing_lp_calls": sum(r["pricing_lp_calls"] for r in rows),
        "total_compact_probe_calls": sum(r["compact_probe_calls"] for r in rows),
        "total_compact_certified_k": sum(r["compact_probe_certified_k"] for r in rows),
        "total_compact_witnesses": sum(r["compact_probe_witnesses"] for r in rows),
    }


def run(output_dir: Path) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text())
    expected = len(protocol["core_counts"]) * len(protocol["capacities"]) * len(protocol["seed_regimes"])
    if expected != protocol["endpoint_problem_count"]:
        raise AssertionError("protocol endpoint count mismatch")
    records = []
    for replicate in range(protocol["replicates"]):
        cells = [(n, c, seed, regime) for n in protocol["core_counts"] for c in protocol["capacities"] for seed, regime in protocol["seed_regimes"]]
        for ordinal, (n, c, seed, regime) in enumerate(cells):
            variants = list(protocol["variants"])
            if (ordinal + replicate) % 2:
                variants.reverse()
            for variant in variants:
                records.append(run_one(protocol, n, c, seed, regime, variant, replicate))
    if len(records) != protocol["run_count"]:
        raise AssertionError("protocol run count mismatch")
    validate_intersections(records)
    summary = {
        "report_version": protocol["report_version"],
        "protocol_sha256": sha_bytes(PROTOCOL_PATH.read_bytes()),
        "solver_sha256": sha_bytes((AUDIT / "ordered_run_disclosure_separator.py").read_bytes()),
        "compact_probe_sha256": sha_bytes((AUDIT / "compact_event_slot_probe.py").read_bytes()),
        "environment": {
            "python": sys.version,
            "numpy": __import__("numpy").__version__,
            "scipy": __import__("scipy").__version__,
            "openblas_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
            "omp_threads": os.environ.get("OMP_NUM_THREADS"),
        },
        "design": protocol,
        "variants": {variant: summarize_variant(records, variant) for variant in protocol["variants"]},
        "run_record_sha256": sha_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()),
        "claim_boundary": protocol["claim_boundary"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "RUNS.json").write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")
    (output_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def self_test() -> int:
    protocol = json.loads(PROTOCOL_PATH.read_text())
    rows, _, usage, pairs = source.generate(2, 991, "mixed")
    q = 4
    exact_master = source.exact.build_master(rows, 2, epsilon=0.1)
    exact_values = []
    for world in source.all_worlds(exact_master, q):
        try:
            exact_values.append(replay(rows, 2, q, usage, pairs, world))
        except AssertionError:
            pass
    optimum = min(exact_values)
    for variant in protocol["variants"]:
        endpoint = solver.minimize(
            rows,
            2,
            q,
            event_cost=1,
            usage_answers=usage,
            pair_answers=pairs,
            limits=solver.Limits(seconds=5, nodes=500, compact_probe_seconds=(1.0 if variant == "compact_probe" else 0.0), compact_probe_rows_min=0, compact_probe_max_k=4),
        )
        if endpoint.lower > optimum or endpoint.upper < optimum:
            raise AssertionError("self-test endpoint misses exact optimum")
    if protocol["run_count"] != 96:
        raise AssertionError("unexpected frozen protocol")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/compact-slot-audit"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps({"self_test_comparisons": self_test()}))
        return 0
    print(json.dumps(run(args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
