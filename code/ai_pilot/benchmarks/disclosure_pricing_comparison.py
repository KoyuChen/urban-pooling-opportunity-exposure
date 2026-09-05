#!/usr/bin/env python3
"""Reproduce the fixed paired pricing grid against a separate baseline checkout.

Example:
  git worktree add --detach tmp/disclosure-baseline 23963d5dfb6600a20bf63a773a410ac200bf711b
  python code/ai_pilot/benchmarks/disclosure_pricing_comparison.py \
    --baseline-root tmp/disclosure-baseline --output-dir tmp/pricing-comparison

Workers isolate imports, forbid the complete-column builder, and replay every
returned world independently. Only aggregate metrics and input hashes are
serialized. The input grid is constructed, not real event-membership truth.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from unittest.mock import patch

BASELINE = '23963d5dfb6600a20bf63a773a410ac200bf711b'


def worker(root: Path, shape: str, n: int, capacity: int, sign: int) -> dict:
    sys.path.insert(0, str(root/'code/ai_pilot/data_pipeline/production_audit'))
    import ordered_run_disclosure_separator as solver
    import ordered_run_fixed_time_master as exact
    import numpy
    import scipy
    rng = random.Random(20260905+n*101)
    rows = []
    for role, offset in [('core', 0), ('buffer', 1), ('buffer', 4), ('buffer', 2)]:
        for i in range(n):
            start, duration = 3*i+offset, 4
            if shape == 'jittered_turnover':
                start += rng.choice([-0.25, 0, 0.25])
                duration = rng.choice([3, 3.5, 4, 4.5, 5])
            rows.append(exact.FixedTimeRow(len(rows), role, start, start+duration))
    row_hash = hashlib.sha256(json.dumps([r.__dict__ for r in rows], sort_keys=True).encode()).hexdigest()
    with patch.object(exact, 'build_master', side_effect=AssertionError('full enumeration forbidden')):
        result = solver.minimize(rows, capacity, 2*n, event_cost=sign,
                                 limits=solver.Limits(seconds=5, nodes=500))
    used = set()
    for mask in result.witness:
        chosen = [i for i in range(len(rows)) if mask & (1 << i)]
        assert len(chosen) >= 2 and any(rows[i].role == 'core' for i in chosen)
        assert not used.intersection(chosen)
        used.update(chosen)
        assert max(sum(rows[i].start <= t < rows[i].end for i in chosen)
                   for t in {rows[i].start for i in chosen}) <= capacity
        reach = {chosen[0]}
        while True:
            previous = set(reach)
            reach |= {j for j in chosen if any(max(rows[i].start, rows[j].start)
                      < min(rows[i].end, rows[j].end) for i in reach)}
            if reach == previous:
                break
        assert len(reach) == len(chosen)
    if result.witness:
        assert all(i in used for i in range(n))
        assert sum(i >= n for i in used) == 2*n
        assert result.upper == sign*len(result.witness)
    return {
        'shape': shape, 'core_rows': n, 'buffer_rows': 3*n, 'capacity': capacity,
        'event_cost': sign, 'support_count': 2*n, 'input_sha256': row_hash,
        'source_sha256': hashlib.sha256(Path(solver.__file__).read_bytes()).hexdigest(),
        'witness_replayed': bool(result.witness),
        'environment': {'python': platform.python_version(), 'numpy': numpy.__version__,
                        'scipy': scipy.__version__}, **result.summary(),
    }


def summarize(cells: list[dict]) -> dict:
    summary = {}
    for variant in ('baseline', 'accelerated'):
        rows = [c[variant] for c in cells]
        good = [r for r in rows if r['status'] != 'TECHNICAL_FAILURE']
        summary[variant] = {
            'cells': len(rows),
            'exact_closed': sum(r['status'] == 'EXACT_BOUND_CLOSED' for r in good),
            'within_tolerance': sum(r['status'] == 'OPTIMAL_WITHIN_TOLERANCE' for r in good),
            'bounded_unresolved': sum(r['status'] == 'BOUNDED_UNRESOLVED' for r in good),
            'infeasible': sum(r['status'] == 'INFEASIBLE' for r in good),
            'technical_failures': len(rows)-len(good),
            'has_replayed_incumbent': sum(r['witness_replayed'] for r in good),
            'median_seconds': statistics.median(r['seconds'] for r in good) if good else None,
            'total_seconds': sum(r['seconds'] for r in good),
            'total_pricing_lp_calls': sum(r['pricing_lp_calls'] for r in good),
        }
    summary['closure_gains'] = [c['cell_index'] for c in cells
        if c['baseline']['status'] != 'EXACT_BOUND_CLOSED' and c['accelerated']['status'] == 'EXACT_BOUND_CLOSED']
    summary['closure_regressions'] = [c['cell_index'] for c in cells
        if c['baseline']['status'] == 'EXACT_BOUND_CLOSED' and c['accelerated']['status'] != 'EXACT_BOUND_CLOSED']
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--worker-root', type=Path)
    parser.add_argument('--worker-cell', help='JSON [shape, core count, capacity, event-cost sign]')
    parser.add_argument('--worker-output', type=Path)
    args = parser.parse_args()
    if args.worker_root:
        result = worker(args.worker_root, *json.loads(args.worker_cell))
        args.worker_output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        return
    if args.baseline_root is None or args.output_dir is None:
        parser.error('--baseline-root and --output-dir are required')
    script = Path(__file__).resolve()
    root = script.parents[3]
    baseline_root = args.baseline_root.resolve()
    required = baseline_root/'code/ai_pilot/data_pipeline/production_audit/ordered_run_disclosure_separator.py'
    if not required.is_file():
        parser.error('baseline checkout is missing ordered_run_disclosure_separator.py')
    protocol = json.loads(script.with_name('DISCLOSURE_PRICING_PROTOCOL.json').read_text(encoding='utf-8'))
    grid = list(itertools.product(protocol['shapes'], protocol['core_counts'],
                                  protocol['capacities'], protocol['event_costs']))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({key: '1' for key in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS',
                                   'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']})
    env['PYTHONHASHSEED'] = '0'
    cells = []
    for index, spec in enumerate(grid):
        cell = {'cell_index': index}
        order = ('baseline', 'accelerated') if index % 2 == 0 else ('accelerated', 'baseline')
        for variant in order:
            output = args.output_dir/f'{index:02d}_{variant}.json'
            source = baseline_root if variant == 'baseline' else root
            try:
                proc = subprocess.run([sys.executable, str(script), '--worker-root', str(source),
                       '--worker-cell', json.dumps(spec), '--worker-output', str(output)],
                       env=env, capture_output=True, text=True, timeout=20)
                if proc.returncode:
                    raise RuntimeError(proc.stderr[-3000:])
                record = json.loads(output.read_text(encoding='utf-8'))
            except (subprocess.TimeoutExpired, RuntimeError) as error:
                record = {'status': 'TECHNICAL_FAILURE', 'detail': str(error)}
            cell[variant] = record
            print(index, variant, record['status'], flush=True)
        if all(cell[v]['status'] != 'TECHNICAL_FAILURE' for v in order):
            a, b = cell['baseline'], cell['accelerated']
            assert a['input_sha256'] == b['input_sha256']
            if a['lower_bound'] is not None and b['upper_bound'] is not None:
                assert a['lower_bound'] <= b['upper_bound']
            if b['lower_bound'] is not None and a['upper_bound'] is not None:
                assert b['lower_bound'] <= a['upper_bound']
        cells.append(cell)
    report = {'report_version': 'disclosure-pricing-paired/v1', 'protocol': protocol,
              'summary': summarize(cells), 'cells': cells,
              'execution': 'local subprocesses; hardware-dependent single paired run',
              'runner_sha256': hashlib.sha256(script.read_bytes()).hexdigest()}
    (args.output_dir/'report.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
