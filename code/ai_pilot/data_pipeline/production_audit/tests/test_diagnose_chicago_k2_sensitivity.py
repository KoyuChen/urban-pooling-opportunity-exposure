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

    @staticmethod
    def row(query, label, value, lower, upper, upper_gap=0.0):
        return {
            "curve_type": "radius", "query": query,
            "parameter_label": label, "parameter_value": value,
            "lower": lower, "upper": upper, "width": upper - lower,
            "lower_status": "OPTIMAL_NUMERICAL_MILP",
            "upper_status": "OPTIMAL_NUMERICAL_MILP",
            "lower_mip_gap": 0.0, "upper_mip_gap": upper_gap,
            "endpoint_pair_certification": "CERTIFIED_OPTIMAL_PAIR",
        }

    def test_gap_explains_small_reversal_without_upgrading_chain(self):
        good = [
            self.row("good", "16 km", 16, 1.0, 2.0),
            self.row("good", "32 km", 32, 0.5, 2.5),
        ]
        numerical = [
            self.row("numerical", "16 km", 16, 1.0, 44.72147435897436),
            self.row(
                "numerical", "32 km", 32, 0.5, 44.72083333333333,
                upper_gap=2.1500906621567433e-5,
            ),
        ]
        audit = diagnostic.gap_aware_audit([*good, *numerical])
        self.assertEqual(audit["status"], "PARTIAL")
        self.assertEqual(audit["violation_count"], 0)
        self.assertEqual(audit["gap_indeterminate_comparison_count"], 1)
        self.assertEqual(audit["fully_certified_monotone_chain_count"], 1)

        numerical[1]["upper"] = 44.70
        numerical[1]["width"] = numerical[1]["upper"] - numerical[1]["lower"]
        outside = diagnostic.gap_aware_audit([*good, *numerical])
        self.assertEqual(outside["status"], "FAIL")
        self.assertEqual(outside["violation_count"], 1)
