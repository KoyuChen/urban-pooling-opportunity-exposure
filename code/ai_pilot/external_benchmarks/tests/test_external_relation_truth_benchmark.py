from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import recordlinkage  # noqa: F401
except ModuleNotFoundError as exc:  # pragma: no cover - lean core CI
    raise unittest.SkipTest(
        "isolated dependency recordlinkage==0.16 is not installed"
    ) from exc


EXTERNAL_DIR = Path(__file__).resolve().parents[1]
if str(EXTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_DIR))

from run_external_relation_truth_benchmark import (  # noqa: E402
    FEBRL_QUERY_FEATURE,
    FEBRL_SCORE_FEATURES,
    _exact_bipartite_frontier,
    _febrl_query,
    _febrl_score,
    _reproduction_command,
    coarsen_febrl_row,
)


class ExternalRelationTruthBenchmarkTest(unittest.TestCase):
    def test_febrl_operator_excludes_direct_identifiers_and_raw_fields(self) -> None:
        raw = pd.Series(
            {
                "given_name": "Alice",
                "surname": "Example",
                "address_1": "10 Hidden Street",
                "suburb": "Northwood",
                "date_of_birth": "19840312",
                "postcode": "2600",
                "state": "act",
                "soc_sec_id": "1234567",
            },
            name="rec-42-org",
        )
        public = coarsen_febrl_row(raw)
        self.assertEqual(set(public), {*FEBRL_SCORE_FEATURES, FEBRL_QUERY_FEATURE})
        serialized = repr(public)
        for forbidden in ("Alice", "Example", "Hidden", "1234567", "rec-42"):
            self.assertNotIn(forbidden, serialized)

    def test_query_is_not_a_score_input(self) -> None:
        left = {
            "given_soundex": "a420",
            "surname_soundex": "e251",
            "given_length_bin": 1,
            "surname_length_bin": 2,
            "suburb_initial": "n",
            "address_initial": "h",
            "birth_decade": "1980s",
        }
        right = dict(left)
        score = _febrl_score(left, right)
        right["birth_decade"] = "1970s"
        self.assertEqual(_febrl_score(left, right), score)
        self.assertEqual(_febrl_query(left, right), 0)
        self.assertNotIn(FEBRL_QUERY_FEATURE, FEBRL_SCORE_FEATURES)

    def test_exact_bipartite_frontier_and_score_tie_range(self) -> None:
        query = np.asarray([[1, 0], [0, 1]], dtype=np.int8)
        score = np.ones((2, 2), dtype=np.int8)
        result = _exact_bipartite_frontier(query, score)
        self.assertEqual(result["enumerated_matchings"], 2)
        self.assertEqual(result["score_free_lower"], 0.0)
        self.assertEqual(result["score_free_upper"], 1.0)
        self.assertEqual(result["score_optimal_matching_count"], 2)
        self.assertEqual(result["score_optimal_lower"], 0.0)
        self.assertEqual(result["score_optimal_upper"], 1.0)

    def test_reproduction_command_reflects_frontier_mode_and_fresh_outputs(self) -> None:
        skipped = _reproduction_command(
            skip_uci_frontier=True,
            uci_frontier_time_limit_seconds=None,
        )
        self.assertIn("--skip-uci-frontier", skipped)
        self.assertNotIn("--uci-frontier-time-limit-seconds", skipped)
        self.assertIn("--output-json /tmp/", skipped)
        self.assertIn("--output-report /tmp/", skipped)

        solved = _reproduction_command(
            skip_uci_frontier=False,
            uci_frontier_time_limit_seconds=37.5,
        )
        self.assertIn("--uci-frontier-time-limit-seconds 37.5", solved)
        self.assertNotIn("--skip-uci-frontier", solved)


if __name__ == "__main__":
    unittest.main()
