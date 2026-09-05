"""Check frozen local evidence consistency; do not rerun hardware-dependent budgets."""
import csv
import hashlib
import json
from pathlib import Path
import unittest


class AccelerationEvidenceTests(unittest.TestCase):
    def test_frozen_counts_and_input_pairs(self):
        root = Path(__file__).resolve().parents[3]
        folder = root / 'benchmarks/results/disclosure_pricing_acceleration'
        report = json.loads((folder/'SUMMARY.json').read_text())
        table = folder/'PAIRED_CELLS.csv'
        self.assertEqual(hashlib.sha256(table.read_bytes()).hexdigest(),
                         report['full_record_sha256']['PAIRED_CELLS.csv'])
        rows = list(csv.DictReader(table.open()))
        self.assertEqual(len(rows), 48)
        for variant in ('baseline', 'accelerated'):
            part = [r for r in rows if r['variant'] == variant]
            expected = report['paired_summary'][variant]
            self.assertEqual(len(part), expected['cells'])
            self.assertEqual(sum(r['status']=='EXACT_BOUND_CLOSED' for r in part), expected['exact_closed'])
            self.assertEqual(sum(r['status']=='BOUNDED_UNRESOLVED' for r in part), expected['bounded_unresolved'])
            self.assertEqual(sum(r['witness_replayed']=='True' for r in part), expected['has_replayed_incumbent'])
            self.assertEqual(sum(int(r['pricing_lp_calls']) for r in part), expected['total_pricing_lp_calls'])
            for r in part:
                if r['upper_bound']:
                    self.assertLessEqual(float(r['lower_bound']),float(r['upper_bound']))
                if r['status']=='EXACT_BOUND_CLOSED':
                    self.assertEqual(r['lower_bound'], r['upper_bound'])
        for i in range(24):
            pair = [r for r in rows if int(r['cell_index']) == i]
            self.assertEqual(len(pair),2)
            self.assertEqual(pair[0]['input_sha256'], pair[1]['input_sha256'])
        certs = list(csv.DictReader((folder/'CERTIFICATE_COUNTS.csv').open()))
        self.assertEqual(len(certs),60)
        self.assertEqual(sum(int(r['certified_count']) for r in certs),240)
        self.assertEqual(sum(int(r['exact_oracle_agreement_count']) for r in certs),240)
        self.assertEqual({int(r['capacity']) for r in certs},{2,3,4})
        for r in certs:
            for name in ('mean_0.25_size','mean_0.50_size','mean_0.75_size','event_count_size'):
                self.assertGreaterEqual(int(r[name]),0)


if __name__ == '__main__':
    unittest.main()
