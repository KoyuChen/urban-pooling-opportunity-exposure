#!/usr/bin/env python3
"""Offline table regeneration, separate from row-level solver reproduction.

No network requests or numerical optimization occur in the default command.
The optional source-replay mode consumes an independently regenerated synthetic
report and the previously sealed Chicago ZIP, never live replacement rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path("code/ai_pilot/benchmarks")
DATA = Path("code/ai_pilot/data_pipeline/results")
NYC = DATA / "nyc_hvfhv"
AUDIT = Path("code/ai_pilot/data_pipeline/production_audit")
FROZEN = BENCH / "results/artifact_rehearsal_20260924"
CHICAGO = DATA / "chicago_k2_followup/gap_amendment_20260913"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(root, path):
    return json.loads((root / path).read_text(encoding="utf-8"))


def read_csv(root, path):
    with (root / path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def integer(value):
    value = float(value)
    require(math.isfinite(value) and abs(value - round(value)) < 1e-7,
            f"nonintegral count: {value}")
    return int(round(value))


def percent(value, places=1):
    return f"{100 * float(value):.{places}f}\\%"


def verify_pins(root, pins):
    for name, expected in pins.items():
        path = root / name
        require(path.is_file(), f"missing pinned file: {path}")
        require(digest(path) == expected, f"hash mismatch: {path}")
    return len(pins)


def chicago_counts(report, followup=False):
    """Recount windows, not just copy a report's headline totals."""
    windows = report["windows"]
    completed = [w for w in windows if w["status"] == "COMPLETED"]
    excluded = [w for w in windows if w["status"].startswith("INELIGIBLE")]
    unstarted = [w for w in windows if w["status"] == "UNSTARTED"]
    failed = len(windows) - len(completed) - len(excluded) - len(unstarted)
    keys = ["endpoint_pairs", "certified_endpoint_pairs",
            "missing_public_query_value_endpoint_pairs",
            "computationally_unresolved_endpoint_pairs"]
    totals = [sum(w[k] for w in completed) for k in keys]
    require(totals[0] == sum(totals[1:]), "Chicago endpoint denominator mismatch")
    headline_keys = ["endpoint_pair_count", "certified_endpoint_pair_count",
                     "missing_public_query_value_endpoint_pair_count",
                     "computationally_unresolved_endpoint_pair_count"]
    require(totals == [report[k] for k in headline_keys], "Chicago headline drift")
    require(len(windows) == report["declared_window_count" if followup else "predeclared_window_count"],
            "Chicago declared-window mismatch")
    require(len({w['window_index'] for w in windows}) == len(windows), "duplicate window")
    return [f"{len(windows)}", f"{len(completed)} / {len(excluded)}",
            f"{failed} / {len(unstarted)}", *[f"{v:,}" for v in totals],
            percent(totals[1] / (totals[1] + totals[3]), 2 if followup else 0)]


def expected_tables(root):
    tables = {}
    inputs = set()

    def js(path):
        inputs.add(str(path))
        return read_json(root, path)

    def cs(path):
        inputs.add(str(path))
        return read_csv(root, path)

    controlled = js(FROZEN / "inputs/CONTROLLED_SUMMARY.json")
    tables["truth"] = [[str(c), f"{r['instance_count']:,}",
                        f"{r['median_frontier_width']:.3f}",
                        f"{r['mean_feasible_temporal_point_absolute_error']:.3f}",
                        percent(r['feasible_temporal_point_threshold_error_rate'])]
                       for c, r in sorted(controlled['by_capacity'].items())]
    truncated = cs(BENCH / "results/controlled_truth_joint_coverage_20260914/JOINT_COVERAGE_SUMMARY.csv")
    tables["truncation"] = [[r['capacity'], *[percent(r[k]) for k in
                            ['mean_candidate_recall', 'full_world_coverage_rate',
                             'frontier_available_rate', 'true_aggregate_coverage_rate']]]
                            for r in truncated if int(r['retained_buffer_count']) == 6]
    atr = js(BENCH / "results/atr_diamor_truth/SUMMARY.json")
    tables["atr-truth"] = []
    fields = ['eligible_snapshot_count', 'cell_count', 'representable_truth_covered_cell_count',
              'truth_representable_cell_count', 'representable_errors_flagged_ambiguous',
              'representable_point_rule_threshold_errors']
    for day in [*atr['days'], {"dataset_day": "Total", **{k: sum(d[k] for d in atr['days']) for k in fields}}]:
        a, b, c, d, e, f = [day[k] for k in fields]
        tables["atr-truth"].append([day['dataset_day'], str(a), str(b), f"{c}/{d}", f"{e}/{f}"])
    pilot = chicago_counts(js(DATA / "chicago_k2_fixed_panel/latest_panel_report.json"))
    followup = chicago_counts(js(CHICAGO / "followup_report.json"), True)
    labels = ['Declared windows', 'Completed / ineligible', 'Execution failures / unstarted',
              'Endpoint pairs', 'Numerically certified pairs', 'Missing-public-value pairs',
              'Computationally unresolved pairs', 'Complete-data rate']
    tables['chicagopanel'] = [list(t) for t in zip(labels, pilot, followup)]
    groups = cs(NYC / "ORDERED_DECISION_PANEL_GROUPS.csv")
    tables['paneldetail'] = []
    for r in sorted(groups, key=lambda r: (int(r['ordered_core_rows']), r['query'], int(r['capacity']))):
        n = int(r['cell_count'])
        tables['paneldetail'].append([r['ordered_core_rows'],
            'Miles' if r['query'] == 'mean_selected_buffer_miles' else 'Minutes',
            r['capacity'], str(n), r['exact_cell_count'],
            str(integer(n * float(r['decision_ambiguity_rate']))),
            str(integer(n * float(r['baseline_disagreement_rate']))),
            f"{float(r['median_exact_width']):.3f}" if r['median_exact_width'] else '--'])
    tables['decisionpanel'] = []
    thresholds = cs(NYC / 'ORDERED_DECISION_THRESHOLD_GROUPS.csv')
    for core in sorted({int(r['ordered_core_rows']) for r in groups}):
        rows = [r for r in tables['paneldetail'] if int(r[0]) == core]
        require(len(rows) == 6 and len({r[3] for r in rows}) == 1, "NYC panel group denominator changed")
        n, closed, ambiguous, split = [sum(int(r[k]) for r in rows) for k in [3, 4, 5, 6]]
        decisions = [r for r in thresholds if int(r['ordered_core_rows']) == core and r['threshold_rule'] == 'candidate_median']
        require(len(decisions) == 6, 'missing median-threshold groups')
        unresolved = sum(int(r['unresolved_count']) for r in decisions)
        require(sum(int(r['certified_ambiguous_count']) for r in decisions) == ambiguous,
                'threshold/group ambiguity disagreement')
        require(sum(int(r[k]) for r in decisions for k in
                    ['certified_all_above_count', 'certified_all_below_count', 'certified_ambiguous_count', 'unresolved_count']) == n,
                'threshold status denominator mismatch')
        tables['decisionpanel'].append([str(core), rows[0][3], str(n), str(closed), str(ambiguous), str(unresolved), str(split)])
    tables['decisionpanel'].append(['All', *[str(sum(int(r[k]) for r in tables['decisionpanel'])) for k in range(1, 7)]])
    panel = js(NYC / "ORDERED_DECISION_PANEL_SUMMARY.json")
    require(tables['decisionpanel'][-1][1:5] == [str(panel[k]) for k in
        ['eligible_window_count', 'outcome_cell_count', 'exact_outcome_cell_count', 'certified_ambiguous_cell_count']],
        'NYC summary/group disagreement')
    common = cs(NYC / "ORDERED_COMMON_SUPPORT.csv")
    tables['capacitydetail'] = []
    for c in sorted({int(r['capacity']) for r in common}):
        row = [str(c)]
        for query in ['mean_selected_buffer_miles_at_common_support', 'mean_selected_buffer_trip_minutes_at_common_support']:
            selected = [r for r in common if int(r['capacity']) == c and r['query'] == query]
            require(len(selected) == 1, 'duplicate/missing common-support cell')
            r = selected[0]
            require(r['status'] == 'CERTIFIED_OPTIMAL_PAIR' and integer(r['common_buffer_rows']) == 72,
                    'common-support cell not certified at frozen q')
            row += [f"{float(r['lower']):.3f}--{float(r['upper']):.3f}", f"{float(r['width']):.3f}"]
        tables['capacitydetail'].append(row)
    scale = cs(NYC / "BRANCH_AND_PRICE_SCALE_CELLS.csv")
    tables['scaledetail'] = []
    for r in sorted(scale, key=lambda r: (int(r['core_rows']), int(r['capacity']))):
        require(r['status'] == 'INTEGER_OPTIMUM_CERTIFIED', 'unclosed scale cell')
        tables['scaledetail'].append([r['core_rows'], r['buffer_rows'], r['capacity'],
            str(integer(r['root_lp_upper_bound'])), 'Certified',
            f"[{integer(r['global_lower_bound'])},{integer(r['global_upper_bound'])}]",
            r['nodes_processed'], f"{float(r['elapsed_seconds_wall']):.2f}"])
    return tables, inputs


def manuscript_tables(root):
    tables = {}
    for path in sorted((root / 'paper').rglob('*.tex')):
        if any(part.startswith('build') for part in path.relative_to(root / 'paper').parts):
            continue
        source = path.read_text(encoding='utf-8')
        for match in re.finditer(r'\\begin\{table\*?\}(.*?)\\end\{table\*?\}', source, re.S):
            block = match.group(1)
            labels = re.findall(r'\\label\{tab:([^}]+)\}', block)
            require(len(labels) == 1, f'table missing unique registry label: {path}')
            name = labels[0]
            require(name not in tables, f'duplicate table label: {name}')
            require('\\midrule' in block and '\\bottomrule' in block, f'unsupported table format: {name}')
            body = block.split('\\midrule', 1)[1].split('\\bottomrule', 1)[0].replace('\\midrule', '')
            tables[name] = [[" ".join(cell.split()) for cell in row.strip().split('&')]
                            for row in body.split('\\\\') if row.strip()]
    return tables


def check_tables(actual, expected):
    require(set(actual) == set(expected), f'table registry mismatch: {set(actual) ^ set(expected)}')
    for name, rows in expected.items():
        require(actual[name] == rows, f'manuscript table drift: {name}\nactual={actual[name]}\nexpected={rows}')


def replay_fragments(root, output):
    """Recompute aggregates from public aggregates; not a new solver certificate."""
    sys.path[:0] = [str(root / AUDIT), str(root / BENCH)]
    import profile_nyc_branch_price_scale as profile
    import run_nyc_nonclique_structure_gate as nonclique

    def replay_nonclique(destination):
        result = read_json(root, NYC / 'nonclique_structure_20260923/SUMMARY.json')
        # JSON objects are sorted on disk; restore the originally published
        # column order without importing any cell values from the target CSV.
        schemas = {
            'support_cells': 'window_index window_label capacity family run_column_count reachable_selected_buffer_counts maximum_selected_buffers columns_excluded_from_ordered common_positive_q compared_q',
            'world_cells': 'window_index window_label capacity q common_feasible ordered_reachable_buffer_masks pair_reachable_buffer_masks clique_reachable_buffer_masks ordered_exceeds_clique ordered_exceeds_pair',
            'comparisons': 'window_index window_label capacity q query restriction status ordered_lower ordered_upper restricted_lower restricted_upper lower_increase upper_decrease width_decrease endpoint_changed_exactly',
        }
        for key, fields in schemas.items():
            fields = fields.split()
            require(all(set(row) <= set(fields) for row in result[key]), f'nonclique schema drift: {key}')
            result[key] = [{k: row[k] for k in fields if k in row} for row in result[key]]
        nonclique.write_outputs(result, destination)

    replays = []
    for name, folder, command in [
        ('profile', NYC / 'branch_price_profile_20260917',
         lambda p: profile.run(root / NYC / 'BRANCH_AND_PRICE_SCALE_CELLS.csv', p)),
        ('ledger', NYC / 'evidence_ledger_20260915',
         lambda p: subprocess.run([sys.executable, str(root / AUDIT / 'audit_nyc_claim_ledger.py'),
             '--results-dir', str(root / NYC), '--output-dir', str(p)], check=True, capture_output=True)),
        ('nonclique', NYC / 'nonclique_structure_20260923',
         replay_nonclique),
    ]:
        destination = output / name
        destination.mkdir(parents=True, exist_ok=True)
        command(destination)
        for path in sorted(destination.iterdir()):
            if path.is_file():
                require(path.read_bytes() == (root / folder / path.name).read_bytes(), f'fragment drift: {folder / path.name}')
                replays.append(str(folder / path.name))
    return replays


def source_replay(root, report_path, zip_path, destination, prepare=False):
    """Check original sealed inputs before exposing only aggregate snapshots."""
    sys.path[:0] = [str(root / AUDIT), str(root / BENCH)]
    import controlled_truth_joint_panel as joint
    import aggregate_chicago_k2_support_stability as stability
    manifest = read_json(root, CHICAGO / 'MANIFEST.json')
    require('sha256:' + digest(zip_path) == manifest['artifact_digest'], 'wrong sealed Chicago ZIP')
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        checkpoint = json.loads(archive.read('checkpoint.json'))
        require(hashlib.sha256(archive.read('checkpoint.json')).hexdigest() == manifest['checkpoint_sha256'], 'checkpoint hash mismatch')
        pins = checkpoint['files']
        for name, expected in pins.items():
            require(hashlib.sha256(archive.read(name)).hexdigest() == expected, f'checkpoint member drift: {name}')
        followup_bytes = archive.read('followup_report.json')
        followup = json.loads(followup_bytes)
        chicago_counts(followup, True)
        rows, sensitivity_pins = [], {}
        expected_pins = read_json(root, DATA / 'chicago_k2_followup/support_stability_20260913/MANIFEST.json')['input_sensitivity_files']
        for name in sorted(n for n in archive.namelist() if n.endswith('/candidate_support_sensitivity.csv')):
            content = archive.read(name)
            sensitivity_pins[name] = hashlib.sha256(content).hexdigest()
            for row in csv.DictReader(content.decode().splitlines()):
                row['window'] = name.split('/')[0]
                row['numerical_status'] = stability.numerical_status(row)
                if row['numerical_status'] == 'CERTIFIED':
                    row['width_value'] = float(row['width'])
                rows.append(row)
        require(sensitivity_pins == expected_pins, 'Chicago sensitivity source pins differ')
        points, paired = stability.summarize_points(rows), stability.summarize_stability(rows)
        chicago_out = destination / 'chicago'
        chicago_out.mkdir(exist_ok=True)
        stability.write_csv(chicago_out / 'SUPPORT_POINT_SUMMARY.csv', points)
        stability.write_csv(chicago_out / 'PAIRED_STABILITY_SUMMARY.csv', paired)
        (chicago_out / 'SUPPORT_STABILITY_REPORT.md').write_text(stability.render_report(points, paired))
        (chicago_out / 'SUPPORT_STABILITY_RESULTS.tex').write_text(stability.render_tex(points, paired))
    report = json.loads(report_path.read_text())
    require(len(report['instances']) == 3000 and len(report['candidate_truncation_cells']) == 9000, 'wrong synthetic design')
    controlled_out = destination / 'controlled'
    controlled_out.mkdir(exist_ok=True)
    cells = joint.enrich(report)
    summary = joint.summarize(cells)
    # scale's JSON writer sorts object keys; restore the published CSV schema
    # after loading it. Values are freshly computed, never read from the CSV.
    cell_fields = (
        'seed', 'capacity', 'retained_buffer_count', 'true_selected_buffer_count',
        'true_member_recall', 'true_world_representable', 'frontier_available_at_true_support',
        'aggregate_value_covered', 'frontier_available_but_true_world_omitted',
        'aggregate_value_covered_despite_world_omission', 'frontier_lower', 'frontier_upper',
        'frontier_width', 'candidate_recall', 'full_world_covered', 'true_aggregate_covered',
        'threshold_count', 'threshold_certified_count', 'threshold_false_certificate_count',
        'threshold_unresolved_count')
    require(all(set(row) == set(cell_fields) for row in cells), 'truncation schema drift')
    cells = [{key: row[key] for key in cell_fields} for row in cells]
    joint.write_csv(controlled_out / 'JOINT_TRUNCATION_CELLS.csv', cells)
    joint.write_csv(controlled_out / 'JOINT_COVERAGE_SUMMARY.csv', summary)
    (controlled_out / 'REPORT.md').write_text(joint.render_report(summary, len(report['instances'])))
    (controlled_out / 'RESULTS.tex').write_text(joint.render_tex(summary))
    replayed = []
    for current, frozen in [(chicago_out, DATA / 'chicago_k2_followup/support_stability_20260913'),
                            (controlled_out, BENCH / 'results/controlled_truth_joint_coverage_20260914')]:
        for path in sorted(current.iterdir()):
            require(path.read_bytes() == (root / frozen / path.name).read_bytes(), f'source replay drift: {path.name}')
            replayed.append(str(frozen / path.name))
    snapshot = {'design': report['design'], 'by_capacity': report['summary']['by_capacity']}
    provenance = {
        'version': 'submission-table-source-recovery/v1',
        'chicago_artifact_id': manifest['artifact_id'], 'chicago_zip_sha256': digest(zip_path),
        'chicago_verified_checkpoint_files': len(pins), 'chicago_sensitivity_files': len(sensitivity_pins),
        'chicago_endpoint_rows': len(rows), 'synthetic_instances': len(report['instances']),
        'synthetic_truncation_cells': len(cells), 'synthetic_report_sha256': digest(report_path),
        'replayed_files': replayed,
        'boundary': 'Aggregate-only recovery. No ATR raw-data replay, public row re-extraction, or new solver certificates.'}
    if prepare:
        write_json(root / FROZEN / 'inputs/CONTROLLED_SUMMARY.json', snapshot)
        (root / CHICAGO / 'followup_report.json').write_bytes(followup_bytes)
        provenance['recovered_sha256'] = {str(p): digest(root / p) for p in
            [FROZEN / 'inputs/CONTROLLED_SUMMARY.json', CHICAGO / 'followup_report.json']}
        write_json(root / FROZEN / 'SOURCE_REPLAY.json', provenance)
    else:
        frozen_provenance = read_json(root, FROZEN / 'SOURCE_REPLAY.json')
        require(provenance == {k: v for k, v in frozen_provenance.items() if k != 'recovered_sha256'}, 'source provenance drift')
        require(snapshot == read_json(root, FROZEN / 'inputs/CONTROLLED_SUMMARY.json'), 'synthetic summary drift')
        require(followup_bytes == (root / CHICAGO / 'followup_report.json').read_bytes(), 'followup summary drift')
    return provenance


def run(root, output):
    recovered = read_json(root, FROZEN / 'SOURCE_REPLAY.json')
    count = verify_pins(root, recovered['recovered_sha256'])
    # Verify historical manifest outputs, not freshly calculated replacements.
    for folder in [BENCH / 'results/controlled_truth_joint_coverage_20260914',
                   NYC / 'evidence_ledger_20260915', NYC / 'branch_price_profile_20260917',
                   NYC / 'nonclique_structure_20260923']:
        manifest = read_json(root, folder / 'MANIFEST.json')
        pins = manifest.get('output_sha256', manifest.get('outputs', manifest.get('files_sha256')))
        require(isinstance(pins, dict) and bool(pins), f'empty manifest: {folder}')
        count += verify_pins(root / folder, pins)
        if 'input_sha256' in manifest:
            count += verify_pins(root / NYC, manifest['input_sha256'])
        if folder.name == 'branch_price_profile_20260917':
            count += verify_pins(root / NYC, {manifest['source']: manifest['source_sha256']})
        if folder.name == 'controlled_truth_joint_coverage_20260914':
            count += verify_pins(root / BENCH, manifest['source_sha256'])
    expected, inputs = expected_tables(root)
    check_tables(manuscript_tables(root), expected)
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in expected.items():
        (output / f'{name}.tex').write_text(''.join(' & '.join(row) + ' \\\\\n' for row in rows), encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='eventfrontier-fragments-') as temporary:
        replays = replay_fragments(root, Path(temporary))
    result = {
        'version': 'submission-artifact-rehearsal/v1',
        'status': 'PASS_AGGREGATE_REHEARSAL_WITH_RAW_REPLAY_LIMITS',
        'table_count': len(expected), 'table_rows': sum(len(v) for v in expected.values()),
        'table_cells': sum(len(row) for rows in expected.values() for row in rows),
        'verified_file_pins': count, 'byte_identical_fragment_files': replays,
        'source_sha256': {p: digest(root / p) for p in sorted(inputs)},
        'code_sha256': {str(p): digest(root / p) for p in [
            Path('scripts/rehearse_submission_artifacts.py'),
            AUDIT / 'profile_nyc_branch_price_scale.py', AUDIT / 'audit_nyc_claim_ledger.py',
            AUDIT / 'run_nyc_nonclique_structure_gate.py']},
        'table_sha256': {f'{name}.tex': digest(output / f'{name}.tex') for name in sorted(expected)},
        'limitations': [
            'ATR tables are rendered from released aggregate summaries; research-use trajectories, labels and detailed witnesses are not bundled or replayed.',
            'NYC aggregate rendering does not rerun original row-level solves or remove the 13 transport-unresolved cells.',
            'Chicago source replay requires the separately pinned sealed ZIP; default offline mode recounts recovered window aggregates, not raw trips.',
            'Runtime entries reproduce historical measurements; they are not fresh speed measurements.',
            'This does not certify city-scale closure, new endpoint optima, or public structural advantage.'],
    }
    write_json(output / 'REHEARSAL.json', result)
    (output / 'REPORT.md').write_text(
        '# Clean-checkout aggregate artifact rehearsal\n\n'
        f"Gate: **{result['status']}**.\n\n"
        f"All {result['table_count']} manuscript tables, {result['table_rows']} data rows and "
        f"{result['table_cells']} cells match independently rendered frozen aggregates. "
        f"Verified {count} historical/recovery file pins and regenerated {len(replays)} "
        'NYC ledger/profile/non-clique files byte for byte. No manuscript numerical changes.\n\n'
        '## Scope boundaries\n\n' + ''.join(f'- {line}\n' for line in result['limitations']) +
        '\nThe separate SOURCE_REPLAY.json records full synthetic regeneration and sealed Chicago sensitivity reaggregation. '
        'A matching aggregate is not a replay of private source data.\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'tmp/submission-rehearsal')
    parser.add_argument('--controlled-report', type=Path)
    parser.add_argument('--chicago-zip', type=Path)
    parser.add_argument('--prepare-recovered-inputs', action='store_true')
    args = parser.parse_args()
    require(bool(args.controlled_report) == bool(args.chicago_zip), 'source replay requires both inputs')
    require(not args.prepare_recovered_inputs or args.controlled_report, 'prepare requires source replay')
    if args.controlled_report:
        source_replay(args.root, args.controlled_report, args.chicago_zip,
                      args.output_dir / 'source-replay', args.prepare_recovered_inputs)
    result = run(args.root, args.output_dir)
    print(json.dumps({k: result[k] for k in ['status', 'table_count', 'table_rows', 'table_cells', 'verified_file_pins']}, sort_keys=True))


if __name__ == '__main__':
    main()
