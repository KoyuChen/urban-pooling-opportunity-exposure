import argparse
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import live_chicago_k2_frontier as frontier  # noqa: E402
import live_chicago_k2_frontier_boundary as boundary  # noqa: E402


class BoundaryPaddingFrontierTests(unittest.TestCase):
    def setUp(self):
        base = datetime(2026, 1, 1, 12, 0)
        self.rows = [
            boundary._synthetic_trip(
                0, "core", base, base + timedelta(minutes=30)
            ),
            boundary._synthetic_trip(
                1, "core", base, base + timedelta(minutes=30)
            ),
            boundary._synthetic_trip(
                2,
                "buffer",
                base + timedelta(minutes=45),
                base + timedelta(minutes=60),
            ),
            boundary._synthetic_trip(
                3,
                "buffer",
                base - timedelta(minutes=30),
                base - timedelta(minutes=15),
            ),
            boundary._synthetic_trip(4, "buffer", None, None),
        ]

    def test_padding_grid_requires_complete_endpoint(self):
        self.assertEqual(
            boundary.parse_padding_grid("30,0,15,5,10"),
            [0.0, 5.0, 10.0, 15.0, 30.0],
        )
        with self.assertRaises(argparse.ArgumentTypeError):
            boundary.parse_padding_grid("0,5,10,30")
        with self.assertRaises(argparse.ArgumentTypeError):
            boundary.parse_padding_grid("0,15,15,30")
        with self.assertRaises(argparse.ArgumentTypeError):
            boundary.parse_padding_grid("-1,15")

    def test_under_padding_is_nested_and_indeterminate_is_always_retained(self):
        zero_rows, zero_audit = boundary.rows_for_boundary_padding(
            self.rows, padding_minutes=0
        )
        ten_rows, _ = boundary.rows_for_boundary_padding(
            self.rows, padding_minutes=10
        )
        full_rows, full_audit = boundary.rows_for_boundary_padding(
            self.rows,
            padding_minutes=boundary.FULL_BOUNDARY_PADDING_MINUTES,
        )
        self.assertEqual({row.index for row in zero_rows}, {0, 1, 4})
        self.assertEqual({row.index for row in ten_rows}, {0, 1, 4})
        self.assertEqual({row.index for row in full_rows}, {0, 1, 2, 3, 4})
        self.assertEqual(zero_audit["retained_indeterminate_buffer_rows"], 1)
        self.assertEqual(full_audit["dropped_buffer_rows"], 0)

    def test_complete_padding_recovers_full_temporal_graph(self):
        full_rows, _ = boundary.rows_for_boundary_padding(
            self.rows,
            padding_minutes=boundary.FULL_BOUNDARY_PADDING_MINUTES,
        )
        wide_rows, _ = boundary.rows_for_boundary_padding(
            self.rows, padding_minutes=30
        )
        all_edges, _ = frontier.build_temporal_edges(self.rows)
        full_edges, _ = frontier.build_temporal_edges(full_rows)
        wide_edges, _ = frontier.build_temporal_edges(wide_rows)
        self.assertEqual(set(full_edges), set(all_edges))
        self.assertEqual(set(wide_edges), set(all_edges))

    def test_identity_audit_accepts_canonical_post_complete_endpoint(self):
        complete_row = {
            "curve_type": "buffer_padding",
            "parameter_value": 15.0,
            "query": "q",
            "endpoint_source": "direct_milp",
            "endpoint_pair_certification": "CERTIFIED_OPTIMAL_PAIR",
            "lower_status": frontier.CERTIFIED_ENDPOINT_STATUS,
            "upper_status": frontier.CERTIFIED_ENDPOINT_STATUS,
            "edges_with_missing_query_values": 0,
            "query_missing_semantics": "none",
            "lower": 0.0,
            "upper": 1.0,
            "width": 1.0,
            "lower_mip_gap": 0.0,
            "upper_mip_gap": 0.0,
            "max_replay_residual": 0.0,
        }
        wide_row = {
            **complete_row,
            "parameter_value": 30.0,
            "endpoint_source": "canonical_complete_boundary_identity",
        }
        audit = boundary.boundary_padding_identity_audit(
            padding_values=[0.0, 15.0, 30.0],
            node_sets={0.0: {0, 1}, 15.0: {0, 1, 2}, 30.0: {0, 1, 2}},
            edge_sets={
                0.0: {(0, 1)},
                15.0: {(0, 1), (0, 2)},
                30.0: {(0, 1), (0, 2)},
            },
            full_temporal_edges={(0, 1), (0, 2)},
            sensitivity_rows=[complete_row, wide_row],
        )
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["post_complete_query_comparison_count"], 1)

    def test_identity_audit_rejects_post_complete_expansion(self):
        audit = boundary.boundary_padding_identity_audit(
            padding_values=[0.0, 15.0, 30.0],
            node_sets={0.0: {0, 1}, 15.0: {0, 1}, 30.0: {0, 1, 2}},
            edge_sets={
                0.0: {(0, 1)},
                15.0: {(0, 1)},
                30.0: {(0, 1), (0, 2)},
            },
            full_temporal_edges={(0, 1)},
            sensitivity_rows=[],
        )
        self.assertEqual(audit["status"], "FAIL")
        reasons = {item["reason"] for item in audit["mismatches"]}
        self.assertIn("post_complete_padding_changed_edge_set", reasons)


if __name__ == "__main__":
    unittest.main()
