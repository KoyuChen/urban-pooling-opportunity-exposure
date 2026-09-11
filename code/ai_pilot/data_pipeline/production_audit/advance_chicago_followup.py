#!/usr/bin/env python3
"""Plan bounded continuation of the frozen Chicago calendar; never change evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import chicago_k2_followup as followup

MAX_TRANSPORT_RETRIES = 2


def decide(rows: list[dict], batch: int, retry: int, *, batch_size: int = 12,
           batch_count: int = 8) -> dict:
    """Advance only record-terminal batches; allow at most two transport retries."""
    if not 0 <= batch < batch_count or not 0 <= retry <= MAX_TRANSPORT_RETRIES:
        raise ValueError("batch/retry outside bounded campaign")
    if [r['window_index'] for r in rows] != list(range(batch_size * batch_count)):
        raise ValueError("missing, duplicate or unordered window denominator")
    start, end = batch * batch_size, (batch + 1) * batch_size
    if any(r['status'] not in followup.REUSABLE for r in rows[:start]):
        return {'action': 'STOP', 'reason': 'PREDECESSOR_NOT_TERMINAL'}
    pending = [r for r in rows[start:end] if r['status'] not in followup.REUSABLE]
    if pending:
        if any(not followup.is_retryable(r) for r in pending):
            return {'action': 'STOP', 'reason': 'UNSTARTED_OR_NONTRANSPORT_FAILURE'}
        if retry == MAX_TRANSPORT_RETRIES:
            return {'action': 'STOP', 'reason': 'TRANSPORT_RETRY_BUDGET_EXHAUSTED'}
        return {'action': 'DISPATCH', 'reason': 'RETRY_TRANSPORT_ONLY',
                'batch_index': batch, 'retry_attempt': retry + 1,
                'selected_indices': [r['window_index'] for r in pending]}
    if batch + 1 == batch_count:
        return {'action': 'STOP', 'reason': 'CALENDAR_EXECUTION_COMPLETE',
                'claim': 'Execution completion is not all-endpoint closure.'}
    # Refuse stale seeds that already contain later results; never overwrite them.
    if any(r['status'] != 'UNSTARTED' for r in rows[end:]):
        return {'action': 'STOP', 'reason': 'LATER_RECORDS_ALREADY_EXIST'}
    return {'action': 'DISPATCH', 'reason': 'ADVANCE_ONE_BATCH',
            'batch_index': batch + 1, 'retry_attempt': 0,
            'selected_indices': list(range(end, end + batch_size))}


def make_plan(root: Path, batch: int, retry: int) -> dict:
    followup.verify(root)
    report = followup.aggregate(root)
    decision = decide(report['windows'], batch, retry)
    if decision['action'] == 'DISPATCH':
        selected = followup.plan(root, decision['batch_index'])['selected_windows']
        if [r['index'] for r in selected] != decision['selected_indices']:
            raise ValueError('continuation differs from frozen controller selection')
    return {**decision,
            'checkpoint_sha256': hashlib.sha256((root / followup.CHECKPOINT).read_bytes()).hexdigest(),
            'execution_gate': report['gate_status'],
            'unresolved_endpoint_pairs': report['computationally_unresolved_endpoint_pair_count'],
            'missing_public_value_pairs': report['missing_public_query_value_endpoint_pair_count']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint-dir', required=True, type=Path)
    parser.add_argument('--batch-index', required=True, type=int)
    parser.add_argument('--retry-attempt', default=0, type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = make_plan(args.checkpoint_dir, args.batch_index, args.retry_attempt)
    followup.write_json(args.output, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
