import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[5]
SPEC = importlib.util.spec_from_file_location(
    'submission_artifact_rehearsal', ROOT / 'scripts/rehearse_submission_artifacts.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class SubmissionArtifactRehearsalTest(unittest.TestCase):
    def test_all_eight_tables_recomputed(self):
        expected, _ = audit.expected_tables(ROOT)
        actual = audit.manuscript_tables(ROOT)
        audit.check_tables(actual, expected)
        self.assertEqual(len(expected), 8)
        self.assertEqual(sum(len(r) for rows in expected.values() for r in rows), 345)

    def test_numeric_drift_rejected(self):
        expected, _ = audit.expected_tables(ROOT)
        actual = copy.deepcopy(expected)
        actual['truth'][0][2] = '0.447'
        with self.assertRaisesRegex(ValueError, 'table drift: truth'):
            audit.check_tables(actual, expected)

    def test_unregistered_table_rejected(self):
        expected, _ = audit.expected_tables(ROOT)
        with self.assertRaisesRegex(ValueError, 'registry mismatch'):
            audit.check_tables({**expected, 'unregistered': [['1']]}, expected)

    def test_missing_and_changed_pins_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'missing pinned file'):
                audit.verify_pins(root, {'absent': '0' * 64})
            (root / 'present').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                audit.verify_pins(root, {'present': '0' * 64})

    def test_timeout_remains_failure(self):
        report = audit.read_json(ROOT, audit.CHICAGO / 'followup_report.json')
        # A failed window has no endpoint output; it is not an exclusion.
        report['windows'][0] = {'window_index': 0, 'status': 'EXECUTION_FAILED'}
        report['endpoint_pair_count'] -= 150
        report['certified_endpoint_pair_count'] -= 120
        report['missing_public_query_value_endpoint_pair_count'] -= 30
        counts = audit.chicago_counts(report, True)
        self.assertEqual(counts[1:3], ['89 / 6', '1 / 0'])

    def test_missing_pairs_excluded_not_unresolved(self):
        report = audit.read_json(ROOT, audit.CHICAGO / 'followup_report.json')
        counts = audit.chicago_counts(report, True)
        self.assertEqual(counts[-3:], ['2,628', '34', r'99.68\%'])

    def test_nonintegral_count_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonintegral'):
            audit.integer(3.5)

    def test_replay_is_deterministic_and_limited(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = audit.run(ROOT, Path(tmp) / 'one')
            second = audit.run(ROOT, Path(tmp) / 'two')
            self.assertEqual(first, second)
            self.assertEqual(len(first['byte_identical_fragment_files']), 17)
            self.assertIn('RAW_REPLAY_LIMITS', first['status'])
            self.assertTrue(any('ATR' in line for line in first['limitations']))


if __name__ == '__main__':
    unittest.main()
