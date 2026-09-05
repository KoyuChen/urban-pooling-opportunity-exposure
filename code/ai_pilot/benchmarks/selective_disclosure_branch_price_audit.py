#!/usr/bin/env python3
"""Audited bridge from ex-post certificate cuts to implicit branch-and-price.

Explicit enumeration is used by the independent small comparator only. The
separator is called with build_master patched to raise, including all its
nested pricing calls. No published output contains relation witnesses.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import statistics
from unittest.mock import patch
import time

import event_frontier_truth_benchmark_scale as scaled
import selective_disclosure_benchmark as explicit
import ordered_run_disclosure_separator as solver
import ordered_run_fixed_time_master as exact


def run(instances_per_capacity=5, *, stress=False):
    records = []
    started = time.perf_counter()
    for capacity in (2, 3, 4):
        for offset in range(instances_per_capacity):
            seed = 20260905 + capacity * 1_000_000 + offset
            instance = scaled.generate_instance(seed, capacity)
            master = exact.build_master(instance.rows, capacity, epsilon=0.1)
            masks = tuple(mask for mask in master.reachable_buffer_masks
                          if mask.bit_count() == len(instance.true_buffer_indices))
            truth = explicit._member_mask(instance.true_buffer_indices)
            events = tuple(explicit._member_mask(event) for event in instance.true_runs)
            q = truth.bit_count()
            values = explicit._buffer_values(master)
            atoms = explicit._buffer_positions(master)
            for threshold in (0.25, 0.5, 0.75):
                expected = explicit.minimum_usage_certificate(masks, truth, values, q, threshold, atoms)['minimum_certificate_size']
                with patch.object(exact, 'build_master', side_effect=AssertionError('full enumeration inside separator')):
                    result = solver.minimum_certificate(instance.rows, capacity, q, values,
                                                        Fraction(threshold)*q, events, usage_atoms=atoms,
                                                        seconds=90, separator_limits=solver.Limits(seconds=20))
                records.append({'target': 'member_mean', 'capacity': capacity, 'seed': seed,
                                'threshold': threshold, 'oracle_size': expected,
                                'exact_size_agreement': result.get('certificate_size') == expected,
                                **result})
            expected = explicit.minimum_pair_certificate_for_event_count(master, instance)['minimum_pair_certificate_size']
            active = tuple(i for i in range(len(master.rows))
                           if master.all_core_mask & (1<<i) or truth & (1<<i))
            pairs = tuple(itertools.combinations(active, 2))
            with patch.object(exact, 'build_master', side_effect=AssertionError('full enumeration inside separator')):
                result = solver.minimum_certificate(instance.rows, capacity, q, {}, Fraction(5,2), events,
                                                    event_cost=1, pair_atoms=pairs, known_usage=atoms,
                                                    seconds=90, separator_limits=solver.Limits(seconds=20))
            records.append({'target': 'event_count', 'capacity': capacity, 'seed': seed,
                            'threshold': 2.5, 'oracle_size': expected,
                            'exact_size_agreement': result.get('certificate_size') == expected, **result})
            print(f'capacity={capacity} seed={seed} completed', flush=True)
    summary = {}
    for kind in ('member_mean', 'event_count'):
        group = [r for r in records if r['target'] == kind]
        summary[kind] = {
            'cells': len(group),
            'minimum_certificate_certified': sum(r['status']=='MINIMUM_CERTIFICATE_CERTIFIED' for r in group),
            'exact_size_agreements': sum(r['exact_size_agreement'] for r in group),
            'unresolved': sum(r['status']=='UNRESOLVED' for r in group),
            'mean_seconds': statistics.fmean(r['seconds'] for r in group),
            'max_seconds': max(r['seconds'] for r in group),
            'mean_iterations': statistics.fmean(r['iterations'] for r in group),
        }
    stress_rows = stress_run() if stress else []
    return {'report_version': 'eventfrontier-implicit-disclosure-audit/v1',
            'design': {'instances_per_capacity': instances_per_capacity, 'capacities':[2,3,4],
                       'base_seed':20260905, 'worlds_and_columns_enumerated_by_comparator_only':True,
                       'explicit_builder_blocked_inside_separator':True,
                       'certificate_is_ex_post_not_adaptive':True,
                       'timestamps':'exact; strict positive-overlap',
                       'threshold_comparator':'exact rational >=, no tolerance shift'},
            'summary':summary, 'cells':records, 'stress_cells':stress_rows,
            'total_seconds':time.perf_counter()-started,
            'claim_boundary':{'supported':'small controlled certificate agreement and declared constructed stress cells',
                              'not_supported':'city-scale runtime, real membership truth, noisy answers, adaptive query savings'}}


def stress_run():
    output=[]
    # A non-enumerable-by-reference 32-row simultaneous cohort, plus nonclique
    # sequential turnover cohorts. Stress is structural, not operational data.
    for kind, ncore, capacity in [('simultaneous',8,4), ('sequential',4,2), ('sequential',8,2)]:
        rows=[]
        if kind=='simultaneous':
            rows=[exact.FixedTimeRow(i,'core' if i<ncore else 'buffer',0,4)
                  for i in range(4*ncore)]
        else:
            rows=[exact.FixedTimeRow(i,'core',3*i,3*i+4) for i in range(ncore)]
            for offset in (1,4,2):
                for i in range(ncore):
                    rows.append(exact.FixedTimeRow(len(rows),'buffer',3*i+offset,3*i+offset+4))
        for sign in (1,-1):
            with patch.object(exact,'build_master',side_effect=AssertionError('forbidden stress enumeration')):
                result=solver.minimize(rows,capacity,2*ncore,event_cost=sign,
                                       limits=solver.Limits(seconds=10,nodes=500))
            output.append({'kind':kind,'core_rows':ncore,'buffer_rows':3*ncore,
                           'capacity':capacity,'support_count':2*ncore,
                           'event_cost':sign,**result.summary()})
            print('stress',kind,ncore,sign,result.status,flush=True)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instances-per-capacity',type=int,default=5)
    parser.add_argument('--stress',action='store_true')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.instances_per_capacity<1: parser.error('instances must be positive')
    report=run(args.instances_per_capacity,stress=args.stress)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    script=Path(__file__)
    report['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (script,Path(solver.__file__))}
    (args.output_dir/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report['summary'],indent=2))
    if any(row['minimum_certificate_certified']!=row['exact_size_agreements'] for row in report['summary'].values()):
        raise AssertionError('certified certificate does not match explicit oracle')

if __name__=='__main__': main()
