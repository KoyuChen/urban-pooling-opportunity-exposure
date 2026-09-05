"""Ensure the frozen default decision matches the predeclared rule."""
import json
from pathlib import Path
import sys
import unittest

AUDIT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parents[3] / "benchmarks"
sys.path.insert(0, str(AUDIT))
import ordered_run_disclosure_separator as solver


class CompactDefaultDecisionTests(unittest.TestCase):
    def test_default_matches_frozen_decision(self):
        decision = json.loads(
            (BENCH / "results" / "compact_event_slot_audit" / "DEFAULT_DECISION.json").read_text()
        )
        self.assertEqual(
            solver.Limits().compact_probe_seconds,
            decision["default_compact_probe_seconds"],
        )
        effects = decision["paired_effects"]
        expected = (
            effects["exact_loss"] == 0
            and effects["incumbent_loss"] == 0
            and (
                effects["exact_gain"] > 0
                or effects["strict_lower_bound_gain"] > 0
            )
        )
        self.assertEqual(decision["beneficial_under_rule"], expected)
        self.assertEqual(
            decision["default_compact_probe_seconds"],
            0.75 if expected else 0.0,
        )


if __name__ == "__main__":
    unittest.main()
