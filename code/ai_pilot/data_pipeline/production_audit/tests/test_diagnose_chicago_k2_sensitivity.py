from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnose_chicago_k2_sensitivity as diagnostic


class DiagnosticTests(unittest.TestCase):
    def test_redaction_and_failure_details_are_preserved(self):
        rows = [{"curve_type": "radius", "parameter_label": "2 km",
                 "parameter_value": 2.0, "query": "q", "lower": 2.0, "upper": 1.0,
                 "width": -1.0, "lower_status": "OPTIMAL_NUMERICAL_MILP",
                 "upper_status": "OPTIMAL_NUMERICAL_MILP",
                 "endpoint_pair_certification": "CERTIFIED_OPTIMAL_PAIR",
                 "trip_id": "must-not-leak", "matching_witness": [1, 2]}]
        audit = diagnostic.BASE_AUDIT(rows)
        result = diagnostic.redacted_diagnostic(rows, audit)
        self.assertEqual(result["audit"]["status"], "FAIL")
        self.assertEqual(result["audit"]["violation_count"], 1)
        self.assertNotIn("trip_id", result["rows"][0])
        self.assertNotIn("matching_witness", result["rows"][0])

    def test_output_directory_is_explicit(self):
        self.assertEqual(diagnostic.output_directory(["--output-dir", "x"]), Path("x"))
        with self.assertRaises(SystemExit):
            diagnostic.output_directory([])
