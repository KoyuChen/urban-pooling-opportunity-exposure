#!/usr/bin/env python3
"""Repair the partially merged compact-probe integration deterministically."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOLVER = ROOT / "code/ai_pilot/data_pipeline/production_audit/ordered_run_disclosure_separator.py"
AUDIT = ROOT / "code/ai_pilot/benchmarks/compact_event_slot_audit.py"
TEST = ROOT / "code/ai_pilot/data_pipeline/production_audit/tests/test_compact_event_slot_probe.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing {label} anchor")
    return text.replace(old, new, 1)


def repair_solver() -> None:
    text = SOLVER.read_text()
    if "import compact_event_slot_probe as compact_probe" not in text:
        text = replace_once(
            text,
            "import ordered_run_branch_and_price as bp\n"
            "import ordered_run_column_generation as cg\n"
            "from ordered_run_fixed_time_master import FixedTimeRow\n",
            "import ordered_run_branch_and_price as bp\n"
            "import ordered_run_column_generation as cg\n"
            "import compact_event_slot_probe as compact_probe\n"
            "from ordered_run_fixed_time_master import FixedTimeRow\n",
            "compact import",
        )

    if "compact_probe_seconds:" not in text:
        text = replace_once(
            text,
            """    pricing_batch: int = 32

    def __post_init__(self) -> None:
        if (not math.isfinite(self.seconds) or self.seconds < 0
                or any(not isinstance(x, int) or x < 0
                       for x in (self.nodes, self.iterations, self.pricing_cases, self.pricing_batch))
                or not math.isfinite(self.gap_tolerance) or self.gap_tolerance < 0):
            raise ValueError("limits must be finite and nonnegative; counts must be integers")
""",
            """    pricing_batch: int = 32
    compact_probe_seconds: float = 0.0
    compact_probe_rows_min: int = 24
    compact_probe_max_k: int = 6
    compact_probe_seek_witness: bool = True

    def __post_init__(self) -> None:
        if (not math.isfinite(self.seconds) or self.seconds < 0
                or any(not isinstance(x, int) or x < 0
                       for x in (self.nodes, self.iterations, self.pricing_cases,
                                 self.pricing_batch, self.compact_probe_rows_min,
                                 self.compact_probe_max_k))
                or not math.isfinite(self.compact_probe_seconds)
                or self.compact_probe_seconds < 0
                or not isinstance(self.compact_probe_seek_witness, bool)
                or not math.isfinite(self.gap_tolerance) or self.gap_tolerance < 0):
            raise ValueError("limits must be finite and nonnegative; counts must be integers")
""",
            "Limits",
        )

    if '"compact_probe_calls": 0' not in text:
        text = replace_once(
            text,
            '        "pricing_infeasible_cache_hits": 0, "early_integer_heuristics": 0,\n'
            '    })\n',
            '        "pricing_infeasible_cache_hits": 0, "early_integer_heuristics": 0,\n'
            '        "compact_probe_calls": 0, "compact_probe_phase_one_calls": 0,\n'
            '        "compact_probe_mip_calls": 0, "compact_probe_certified_k": 0,\n'
            '        "compact_probe_witnesses": 0,\n'
            '    })\n',
            "compact counters",
        )

    if "compact_witness: tuple[int, ...]" not in text:
        text = replace_once(
            text,
            """    trivial = _initial_lower(ctx, root)
    queue = [(trivial, 0, root)]
    serial = 0
    incumbent, witness = None, ()
""",
            """    trivial = _initial_lower(ctx, root)

    # Optional compact at-most-K outer relaxation. It is used only for pure
    # minimum-event objectives. A lower bound is strengthened solely from a
    # strictly positive rational phase-I certificate; timeout and MIP failure
    # remain inconclusive.
    compact_witness: tuple[int, ...] = ()
    if (ctx.event_cost > 0 and all(cost == 0 for cost in ctx.costs)
            and len(model.rows) >= limits.compact_probe_rows_min
            and limits.compact_probe_seconds > 0
            and limits.compact_probe_max_k >= 1):
        start_k = max(1, math.ceil(trivial / ctx.event_cost))
        max_k = min(limits.compact_probe_max_k, len(model.core_positions))
        if start_k <= max_k:
            ctx.counts["compact_probe_calls"] += 1
            probe = compact_probe.probe_minimum_events(
                model.rows,
                capacity,
                support_count,
                start_k=start_k,
                max_k=max_k,
                usage_answers=usage_answers or {},
                pair_answers=pair_answers or {},
                seconds=min(
                    limits.compact_probe_seconds,
                    max(0.0, ctx.deadline - time.perf_counter()),
                ),
                seek_witness=limits.compact_probe_seek_witness,
            )
            ctx.counts["compact_probe_phase_one_calls"] += probe.phase_one_calls
            ctx.counts["compact_probe_mip_calls"] += probe.mip_calls
            ctx.counts["compact_probe_certified_k"] += len(probe.certified_infeasible_k)
            trivial = max(trivial, ctx.event_cost * probe.lower_event_count)
            compact_witness = probe.witness
            if compact_witness:
                try:
                    replay(ctx, compact_witness, root)
                except ValueError:
                    compact_witness = ()
                else:
                    ctx.counts["compact_probe_witnesses"] += 1
                    for mask in compact_witness:
                        ctx.pool[mask] = cg.RunColumn(
                            mask,
                            mask & model.all_core_mask,
                            mask & model.all_buffer_mask,
                        )

    queue = [(trivial, 0, root)]
    serial = 0
    incumbent, witness = None, ()
""",
            "minimize compact probe",
        )

    if "if compact_witness:\n        incumbent = replay" not in text:
        text = replace_once(
            text,
            """    if initial_events:
        try:
            incumbent = replay(ctx, initial_events, root)
            witness = tuple(initial_events)
        except ValueError:
            pass  # a seed library need not be a complete partition
""",
            """    if compact_witness:
        incumbent = replay(ctx, compact_witness, root)
        witness = tuple(compact_witness)
    if initial_events:
        try:
            value = replay(ctx, initial_events, root)
            if incumbent is None or value < incumbent:
                incumbent = value
                witness = tuple(initial_events)
        except ValueError:
            pass  # a seed library need not be a complete partition
""",
            "compact witness warm start",
        )
    SOLVER.write_text(text)


def repair_audit_and_tests() -> None:
    text = AUDIT.read_text()
    text = text.replace(
        '"relation_witness_serialized": false,',
        '"relation_witness_serialized": False,',
        1,
    )
    AUDIT.write_text(text)

    text = TEST.read_text()
    text = text.replace(
        'compact.build_slot_model(rows, 3, 2, 2, pair_answers={(2, 3): 1})',
        'compact.build_slot_model(rows, 4, 2, 2, pair_answers={(2, 3): 1})',
        1,
    )
    text = text.replace(
        'max_k=min(optimum, n)',
        'max_k=max(1, min(int(optimum), n))',
        1,
    )
    TEST.write_text(text)


if __name__ == "__main__":
    repair_solver()
    repair_audit_and_tests()
    print("compact integration repair: PASS")
