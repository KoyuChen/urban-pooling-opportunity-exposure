#!/usr/bin/env python3
"""Replay compact frozen experimental metrics, not expensive timing runs."""
from __future__ import annotations
import hashlib
import itertools
import json
import math
from fractions import Fraction
from pathlib import Path

import disclosure_independent_ablation as audit

RESULTS = Path(__file__).with_name('results') / 'disclosure_independent_ablation'


def outward(value: Fraction | None, lower: bool):
    if value is None:
        return None
    result = float(value)
    if (lower and Fraction(result) > value) or (not lower and Fraction(result) < value):
        result = math.nextafter(result, -math.inf if lower else math.inf)
    return result


def decode(packed):
    records = []
    for index, row in enumerate(packed['rows']):
        assert len(row) == len(packed['columns'])
        values = dict(zip(packed['columns'], row))
        cell = packed['cells'][values.pop('cell_id')]
        record = {**packed['common'], **cell, **values, 'run_index': index}
        for key in ('variant', 'status', 'reason'):
            record[key] = packed['statuses' if key=='status' else key+'s'][record.pop(key+'_id')]
        lo = Fraction(record['lower_rational'])
        hi = None if record['upper_rational'] is None else Fraction(record['upper_rational'])
        record.update(lower_bound=outward(lo, True), upper_bound=outward(hi, False),
                      absolute_gap=outward(hi-lo, False) if hi is not None else None)
        records.append(record)
    return records


def check(result_dir=RESULTS):
    summary = json.loads((result_dir/'SUMMARY.json').read_text())
    raw = (result_dir/'RUNS.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == summary['run_records_sha256']
    packed = json.loads(raw)
    assert packed['source_report_sha256'] == summary['full_local_report_sha256']
    records = decode(packed)
    assert len(records) == summary['record_count'] == 208
    p = summary['protocol']
    assert hashlib.sha256(audit.PROTOCOL_PATH.read_bytes()).hexdigest() == summary['protocol_sha256']
    assert json.loads(audit.PROTOCOL_PATH.read_text()) == p
    assert audit.sha(Path(audit.__file__)) == summary['runner_sha256']
    assert packed['common']['source_sha256'] == p['separator_sha256']
    expected = set()
    for stratum, sizes in [('primary', p['primary_core_counts']), ('stress', p['stress_core_counts'])]:
        variants = p['variants'] if stratum == 'primary' else ['full']
        for n, c, (seed, regime), sign, variant, rep in itertools.product(
            sizes, p['capacities'], p['seed_regimes'], p['event_costs'], variants, range(p['replicates'])):
            expected.add((stratum, (n,c,seed,regime,sign), variant,rep))
    observed = {(r['stratum'], tuple(r['cell']),r['variant'],r['replicate']) for r in records}
    assert observed == expected and len(observed) == len(records)
    audit.validate_intersections(records)
    assert audit.summarize(records) == summary['summary']
    mismatch = []
    for r in records:
        assert r['status'] != 'TECHNICAL_FAILURE'
        assert r['all_event_columns_enumerated'] is False
        assert r['all_worlds_enumerated'] is False and r['reference_used_by_solver'] is False
        lo, hi = Fraction(r['lower_rational']), r['upper_rational']
        assert lo <= r['known_reference_value']
        assert r['witness_replayed'] == (hi is not None)
        if hi is not None:
            hi = Fraction(hi)
            assert lo <= hi
            if r['status'] == 'EXACT_BOUND_CLOSED':
                assert lo == hi
            elif lo == hi:
                mismatch.append(r['run_index'])
    assert mismatch == summary['conservative_status_mismatches'] == [16,27]
    assert summary['distinct_endpoint_problems'] == len(packed['cells']) == 24
    print('independent disclosure evidence: PASS (208 complete records; 2 conservative status mismatches retained)')
    return records


if __name__ == '__main__':
    check()
