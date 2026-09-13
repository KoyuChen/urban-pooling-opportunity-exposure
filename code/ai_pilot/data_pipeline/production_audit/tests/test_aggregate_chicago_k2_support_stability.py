from __future__ import annotations

import sys
import unittest
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

import aggregate_chicago_k2_support_stability as aggregate  # noqa: E402


def row(window: str, curve: str, label: str, value: str, width: float, query: str = "duration"):
    return {
        "window": window,
        "curve_type": curve,
        "parameter_label": label,
        "parameter_value": value,
        "query": query,
        "unit": "minutes",
        "numerical_status": "CERTIFIED",
        "width_value": width,
    }


class SupportStabilityTests(unittest.TestCase):
    def test_variable_terminal_budget_is_canonicalized_within_window(self) -> None:
        rows = [
            row("a", "candidate_omission", "0", "0", 1.0),
            row("a", "candidate_omission", "8", "8", 1.9),
            row("a", "candidate_omission", "10", "10", 2.0),
            row("b", "candidate_omission", "0", "0", 1.0),
            row("b", "candidate_omission", "8", "8", 2.98),
            row("b", "candidate_omission", "20", "20", 3.0),
        ]
        summary = aggregate.summarize_stability(rows)
        at_eight = aggregate.select(summary, "candidate_omission", "duration", "8")
        self.assertEqual(at_eight["paired_window_count"], 2)
        self.assertEqual(at_eight["within_1pct_of_full_count"], 1)

    def test_terminal_at_common_budget_counts_as_budget_and_full_support(self) -> None:
        rows = [
            row("a", "candidate_omission", "0", "0", 1.0),
            row("a", "candidate_omission", "8", "8", 2.0),
        ]
        summary = aggregate.summarize_stability(rows)
        self.assertEqual(
            aggregate.select(summary, "candidate_omission", "duration", "8")["within_1pct_of_full_count"],
            1,
        )

    def test_missing_outcomes_are_not_numerical_failures(self) -> None:
        source = {
            "endpoint_pair_certification": "UNCERTIFIED",
            "lower_status": aggregate.MISSING,
            "upper_status": aggregate.MISSING,
        }
        self.assertEqual(aggregate.numerical_status(source), "MISSING_PUBLIC_VALUE")

    def test_quantile_uses_linear_interpolation(self) -> None:
        self.assertEqual(aggregate.quantile([0.0, 10.0], 0.25), 2.5)


if __name__ == "__main__":
    unittest.main()
