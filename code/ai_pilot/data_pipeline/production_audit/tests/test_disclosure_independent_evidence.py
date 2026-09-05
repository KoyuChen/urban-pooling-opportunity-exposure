"""Check frozen records without rerunning hardware-dependent performance tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'benchmarks'))
import check_disclosure_independent_evidence as evidence


class IndependentEvidenceTests(unittest.TestCase):
    def test_frozen_records_and_summary(self):
        self.assertEqual(len(evidence.check()), 208)


if __name__ == '__main__':
    unittest.main()
