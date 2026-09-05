#!/usr/bin/env python3
"""Frozen-source, independent-seed ablations for the disclosure separator.

The production solver is not modified. Every variant starts from the source
hash pinned in DISCLOSURE_INDEPENDENT_PROTOCOL.json. Instrumentation removes
one acceleration while preserving valid bounds. Reference partitions check
feasibility and construct truthful answers; they never seed the optimizer.
Run --self-test before --output-dir. The full run is sequential and resumable
only by explicitly choosing a new output directory; existing records are not
silently overwritten. Summary JSON, CSV and execution logs retain failures.
"""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
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
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / 'code/ai_pilot/data_pipeline/production_audit'
sys.path.insert(0, str(AUDIT))
import ordered_run_fixed_time_master as exact

PROTOCOL_PATH = Path(__file__).with_name('DISCLOSURE_INDEPENDENT_PROTOCOL.json')
PIN = 'f520a5e0d047ae0d6ebe3b3435f8577aed1a1247401cd403622e89ff2bf316f4'
VARIANTS = ('full', 'no_canonical', 'no_batch', 'no_lattice',
            'no_early_primal', 'no_infeasible_cache')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NoStoreSet(set):
    def __contains__(self, item):
        return False

    def add(self, item):
        pass


def variant_module(variant: str):
    """Construct an isolated in-memory variant; never rewrite solver files.

    Without canonical restriction, each root oracle optimizes a SUPERSET of
    its least-core class. Its repaired upper bound is therefore still valid
    for that canonical class; summing root-class corrections remains sound.
    Duplicate discovery is removed by the unchanged column-pool dictionary.
    """
    if variant not in VARIANTS:
        raise ValueError(f'unknown variant: {variant}')
    path = AUDIT / 'ordered_run_disclosure_separator.py'
    if sha(path) != PIN:
        raise ValueError('frozen source hash mismatch: audit a pinned checkout')
    source = path.read_text(encoding='utf-8')
    if variant == 'no_canonical':
        old = 'excluded | earlier'
        if source.count(old) != 1:
            raise ValueError('canonical instrumentation target is not unique')
        source = source.replace(old, 'excluded')
    name = f'_disclosure_independent_{variant}'
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module  # dataclasses resolves the declaring module.
    exec(compile(source, str(path), 'exec'), module.__dict__)
    if variant == 'no_lattice':
        module.Context.lattice_lower = lambda self, bound: bound
    elif variant == 'no_early_primal':
        module._early_primal = lambda *args, **kwargs: None
    elif variant == 'no_infeasible_cache':
        original = module.Context.__post_init__
        def initialize(self):
            original(self)
            self.infeasible_boxes = NoStoreSet()
        module.Context.__post_init__ = initialize
    return module


def generate(n: int, seed: int, regime: str):
    """Generate real-duration synthetic chains, not simultaneous cliques."""
    if n < 2 or regime not in ('none', 'mixed'):
        raise ValueError('need >=2 cores and none/mixed fact regime')
    rng = random.Random(seed + 100003*n)
    raw, groups, distractors = [], [], []
    start = 0.0
    for _ in range(n):
        start += rng.choice((2.5, 3.0, 3.5, 4.0))
        group = []
        for role, offset, duration in (('core', 0, 4), ('buffer', 2, 4),
                                      ('buffer', 4.5, 3.5)):
            group.append(len(raw))
            raw.append((role, start+offset, start+offset+duration))
        groups.append(group)
        distractors.append(len(raw))
        begin = start + rng.randrange(25)/4
        raw.append(('buffer', begin, begin+2+rng.randrange(13)/4))
    order = list(range(len(raw)))
    rng.shuffle(order)
    position = {old: new for new, old in enumerate(order)}
    rows = [exact.FixedTimeRow(new, *raw[old]) for new, old in enumerate(order)]
    reference = tuple(sum(1 << position[i] for i in group) for group in groups)
    usage, pairs = {}, {}
    if regime == 'mixed':
        usage[position[distractors[0]]] = 0
        pairs[tuple(sorted((position[groups[0][0]], position[groups[0][1]])))] = 1
        pairs[tuple(sorted((position[groups[0][0]], position[groups[1][0]])))] = 0
    return rows, reference, usage, pairs


def replay(rows, capacity, q, usage, pairs, events, costs=None, event_cost=1):
    """Independent replay: no call to the solver's replay or column checks."""
    costs = costs or {}
    used = set()
    for mask in events:
        assert isinstance(mask, int) and mask > 0 and not (mask >> len(rows))
        chosen = [i for i in range(len(rows)) if mask & (1 << i)]
        assert len(chosen) >= 2 and any(rows[i].role == 'core' for i in chosen)
        assert not used.intersection(chosen)
        used.update(chosen)
        for t in {rows[i].start for i in chosen}:
            assert sum(rows[i].start <= t < rows[i].end for i in chosen) <= capacity
        reach = {chosen[0]}
        while True:
            old = set(reach)
            reach |= {j for j in chosen if any(max(rows[i].start, rows[j].start)
                      < min(rows[i].end, rows[j].end) for i in reach)}
            if old == reach:
                break
        assert len(reach) == len(chosen)
    assert {i for i, row in enumerate(rows) if row.role == 'core'} <= used
    assert sum(rows[i].role == 'buffer' for i in used) == q
    assert all(int(i in used) == answer for i, answer in usage.items())
    for (i, j), answer in pairs.items():
        assert int(any(mask & (1 << i) and mask & (1 << j) for mask in events)) == answer
    return Fraction(event_cost)*len(events) + sum((Fraction(costs.get(i, 0)) for i in used), Fraction(0))


def all_worlds(master, q):
    def search(used, events):
        missing = master.all_core_mask & ~used
        if not missing:
            if (used & master.all_buffer_mask).bit_count() == q:
                yield events
            return
        i = (missing & -missing).bit_length()-1
        for column in master.columns_by_core_position[i]:
            if not (column.member_mask & used):
                new = used | column.member_mask
                if (new & master.all_buffer_mask).bit_count() <= q:
                    yield from search(new, events+(column.member_mask,))
    yield from search(0, ())


def self_test():
    checked = 0
    for seed, capacity in itertools.product((1801, 1807), (2, 3)):
        rows, reference, usage, pairs = generate(2, seed, 'mixed')
        master = exact.build_master(rows, capacity, epsilon=0.1)
        valid = []
        for events in all_worlds(master, 4):
            try:
                replay(rows, capacity, 4, usage, pairs, events)
                valid.append(events)
            except AssertionError:
                pass
        assert valid and reference
        for event_cost in (1, -1):
            optimum = min(event_cost*len(w) for w in valid)
            for variant in VARIANTS:
                s = variant_module(variant)
                with patch.object(exact, 'build_master', side_effect=AssertionError('enumeration forbidden')):
                    result = s.minimize(rows, capacity, 4, event_cost=event_cost,
                        usage_answers=usage, pair_answers=pairs,
                        limits=s.Limits(seconds=20, pricing_batch=0 if variant=='no_batch' else 32))
                assert result.lower <= optimum and result.upper == optimum, (seed, variant, result.summary())
                assert result.upper == replay(rows, capacity, 4, usage, pairs, result.witness, event_cost=event_cost)
                checked += 1
    # Signed rational objectives: rounding disabled must not change truth.
    rows, _, usage, pairs = generate(2, 1811, 'none')
    master = exact.build_master(rows, 2, epsilon=0.1)
    costs = {i: Fraction((i*3)%7-3, 11) for i in range(len(rows))}
    optimum = min(replay(rows, 2, 3, usage, pairs, w, costs, -1) for w in all_worlds(master, 3))
    for variant in VARIANTS:
        s = variant_module(variant)
        result = s.minimize(rows, 2, 3, costs, event_cost=-1,
                           limits=s.Limits(seconds=20, pricing_batch=0 if variant=='no_batch' else 32))
        assert result.lower <= optimum and result.upper == optimum
        checked += 1
    print(f'independent-ablation self-test: PASS ({checked} exact-oracle endpoint comparisons)', flush=True)
    return checked


def worker(spec, protocol):
    n, capacity, seed, regime, sign = spec['cell']
    variant = spec['variant']
    rows, reference, usage, pairs = generate(n, seed, regime)
    ref_value = replay(rows, capacity, 2*n, usage, pairs, reference, event_cost=sign)
    serialized = {'rows': [r.__dict__ for r in rows], 'capacity': capacity,
                  'q': 2*n, 'usage': sorted(usage.items()),
                  'pairs': [(list(pair), answer) for pair, answer in sorted(pairs.items())]}
    input_hash = hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest()
    s = variant_module(variant)
    limits = s.Limits(seconds=protocol['seconds_per_endpoint'], nodes=protocol['node_limit'],
        iterations=protocol['iteration_limit'], pricing_cases=protocol['pricing_case_limit'],
        pricing_batch=0 if variant == 'no_batch' else 32)
    with patch.object(exact, 'build_master', side_effect=AssertionError('full enumeration forbidden')):
        endpoint = s.minimize(rows, capacity, 2*n, event_cost=sign, usage_answers=usage,
                              pair_answers=pairs, limits=limits)
    assert endpoint.status != 'INFEASIBLE', 'known feasible reference contradicts infeasibility'
    assert endpoint.lower is not None and endpoint.lower <= ref_value
    if endpoint.witness:
        assert endpoint.upper == replay(rows, capacity, 2*n, usage, pairs,
                                         endpoint.witness, event_cost=sign)
    assert endpoint.upper is None or endpoint.lower <= endpoint.upper
    import numpy, scipy
    return {**spec, **endpoint.summary(), 'input_sha256': input_hash,
            'lower_rational': str(endpoint.lower),
            'upper_rational': None if endpoint.upper is None else str(endpoint.upper),
            'known_reference_value': int(ref_value), 'reference_used_by_solver': False,
            'witness_replayed': bool(endpoint.witness), 'source_sha256': PIN,
            'environment': {'python': platform.python_version(), 'numpy': numpy.__version__,
                            'scipy': scipy.__version__}}


def summarize(records):
    out = {}
    for stratum, variant in itertools.product(('primary', 'stress'), VARIANTS):
        cells = [r for r in records if r['stratum']==stratum and r['variant']==variant]
        if not cells:
            continue
        good = [r for r in cells if r['status'] != 'TECHNICAL_FAILURE']
        out[f'{stratum}:{variant}'] = {
            'runs': len(cells), 'exact_closed': sum(r['status']=='EXACT_BOUND_CLOSED' for r in good),
            'within_tolerance': sum(r['status']=='OPTIMAL_WITHIN_TOLERANCE' for r in good),
            'bounded_unresolved': sum(r['status']=='BOUNDED_UNRESOLVED' for r in good),
            'technical_failures': len(cells)-len(good),
            'replayed_incumbents': sum(r['witness_replayed'] for r in good),
            'median_seconds': statistics.median(r['seconds'] for r in good) if good else None,
            'total_seconds': sum(r['seconds'] for r in good),
            'pricing_lp_calls': sum(r['pricing_lp_calls'] for r in good),
            'median_gap': statistics.median(r['absolute_gap'] for r in good
                        if r['absolute_gap'] is not None) if any(r.get('absolute_gap') is not None for r in good) else None,
        }
    return out


def validate_intersections(records):
    groups = {}
    for r in records:
        if r['status'] != 'TECHNICAL_FAILURE':
            groups.setdefault(tuple(r['cell']), []).append(r)
    for key, group in groups.items():
        assert len({r['input_sha256'] for r in group}) == 1
        lower = max(Fraction(r['lower_rational']) for r in group)
        uppers = [Fraction(r['upper_rational']) for r in group if r['upper_rational'] is not None]
        assert not uppers or lower <= min(uppers), (key, 'disjoint rigorous endpoint bounds')


def run(output):
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding='utf-8'))
    if sha(AUDIT/'ordered_run_disclosure_separator.py') != protocol['separator_sha256']:
        raise ValueError('solver no longer matches predeclared source')
    if output.exists() and any(output.iterdir()):
        raise ValueError('output directory is not empty; preserve previous execution records')
    output.mkdir(parents=True, exist_ok=True)
    plan = []
    for stratum, sizes in (('primary', protocol['primary_core_counts']), ('stress', protocol['stress_core_counts'])):
        variants = VARIANTS if stratum=='primary' else ('full',)
        for n, cap, (seed, regime), sign in itertools.product(sizes, protocol['capacities'],
                            protocol['seed_regimes'], protocol['event_costs']):
            for variant, replicate in itertools.product(variants, range(protocol['replicates'])):
                plan.append({'stratum': stratum, 'cell': [n, cap, seed, regime, sign],
                             'variant': variant, 'replicate': replicate})
    assert len(plan) == protocol['primary_run_count'] + protocol['stress_run_count']
    random.Random(990731).shuffle(plan)
    (output/'EXECUTION_PLAN.json').write_text(json.dumps(plan, indent=2)+'\n')
    env = dict(os.environ)
    env.update({key:'1' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')})
    env['PYTHONHASHSEED']='0'
    records = []
    for index, spec in enumerate(plan):
        target = output/f'run_{index:03d}.json'
        try:
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                 json.dumps(spec), '--worker-output', str(target)], env=env, capture_output=True,
                 text=True, timeout=20)
            if proc.returncode:
                raise RuntimeError(proc.stderr[-4000:])
            record = json.loads(target.read_text(encoding='utf-8'))
        except (subprocess.TimeoutExpired, RuntimeError, ValueError, OSError) as error:
            record = {**spec, 'status':'TECHNICAL_FAILURE', 'detail': str(error)}
            target.write_text(json.dumps(record, indent=2)+'\n')
        record['run_index']=index
        records.append(record)
        print(f"{index+1}/{len(plan)} {spec['stratum']} {spec['cell']} {spec['variant']} "
              f"r{spec['replicate']} {record['status']} [{record.get('lower_bound')},{record.get('upper_bound')}]", flush=True)
    validate_intersections(records)
    report = {'report_version':protocol['protocol_version'], 'protocol':protocol,
              'protocol_commit':'2e70d1663cf6f1d427e6a470274fa5b36297dbf3',
              'protocol_sha256':sha(PROTOCOL_PATH), 'runner_sha256':sha(Path(__file__)),
              'execution':'local isolated processes; not GitHub Actions benchmark execution',
              'summary':summarize(records), 'bound_intersection_check':'PASS', 'records':records}
    (output/'report.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    keys=['run_index','stratum','variant','replicate','cell','status','lower_bound','upper_bound',
          'absolute_gap','seconds','pricing_lp_calls','nodes','witness_replayed','reason','input_sha256']
    with (output/'ENDPOINTS.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(records)
    print(json.dumps(report['summary'],indent=2), flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--worker'); parser.add_argument('--worker-output', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args=parser.parse_args()
    if args.self_test:
        self_test()
    elif args.worker:
        protocol=json.loads(PROTOCOL_PATH.read_text(encoding='utf-8'))
        record=worker(json.loads(args.worker),protocol)
        args.worker_output.write_text(json.dumps(record,indent=2)+'\n')
    elif args.output_dir:
        run(args.output_dir)
    else:
        parser.error('choose --self-test or --output-dir')


if __name__=='__main__':
    main()
