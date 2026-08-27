from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np


EXTERNAL_DIR = Path(__file__).resolve().parents[1]
if str(EXTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_DIR))

from uci_all_blocks_audit import (  # noqa: E402
    BLOCK_NUMBERS,
    DEFAULT_METADATA,
    RAW_COLUMNS,
    UciAuditError,
    UciData,
    audit_all_ten_blocks,
    load_all_blocks,
    reconcile_pairs,
    rx,
    solve_dyad_frontier,
)


def pattern(
    left: int,
    right: int,
    positive: bool,
    *,
    postal: str = "1",
) -> dict[str, object]:
    return {
        "id_1": left,
        "id_2": right,
        "cmp_fname_c1": "0.8",
        "cmp_fname_c2": "?",
        "cmp_lname_c1": "1",
        "cmp_lname_c2": "?",
        "cmp_sex": "1",
        "cmp_bd": "0",
        "cmp_bm": "1",
        "cmp_by": "1",
        "cmp_plz": postal,
        "is_match": "TRUE" if positive else "FALSE",
    }


def write_block_zip(
    directory: Path,
    block: int,
    rows: list[dict[str, object]],
    *,
    member_name: str | None = None,
) -> None:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=RAW_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    path = directory / f"block_{block}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member_name or f"block_{block}.csv", text.getvalue())


def write_metadata(path: Path, *, rows: int, positives: int, records: int) -> None:
    source = json.loads(DEFAULT_METADATA.read_text(encoding="utf-8"))
    source["candidate_pair_count_as_reported"] = rows
    source["positive_pair_count_as_reported"] = positives
    source["source_record_count_as_reported"] = records
    source["observed_cached_block_manifest"] = []
    path.write_text(json.dumps(source), encoding="utf-8")


def tiny_ten_block_snapshot(root: Path) -> Path:
    rows = {
        1: [pattern(1, 2, True)],
        2: [pattern(2, 3, True)],
        3: [pattern(1, 3, True)],
        4: [pattern(4, 5, True, postal="1")],
        5: [pattern(6, 7, True, postal="1")],
        6: [pattern(4, 6, False, postal="?")],
        7: [pattern(5, 7, False, postal="0")],
        8: [pattern(8, 9, False)],
        9: [pattern(10, 11, False)],
        10: [pattern(12, 13, False)],
    }
    for block in BLOCK_NUMBERS:
        write_block_zip(root, block, rows[block])
    metadata = root / "metadata.json"
    write_metadata(metadata, rows=10, positives=5, records=13)
    return metadata


class UciAllBlocksAuditTest(unittest.TestCase):
    def test_ten_block_topology_globalizes_positive_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = tiny_ten_block_snapshot(root)
            result = audit_all_ten_blocks(
                root,
                metadata_path=metadata,
                enforce_pinned_snapshot=False,
                solve_frontier=False,
            )
            relation = result["adjudicated_positive_relation"]
            self.assertEqual(relation["component_size_histogram"], {"2": 2, "3": 1})
            self.assertFalse(relation["is_matching"])
            self.assertEqual(relation["complete_clique_components"], 3)
            self.assertEqual(relation["negative_edges_within_positive_components"], 0)
            local = result["block_local_dyad_invalidity"]
            self.assertEqual(local["sum_block_local_apparent_dyads"], 5)
            self.assertEqual(local["local_dyads_absorbed_into_larger_global_entities"], 3)
            dyad = result["truth_conditioned_dyad_reduction"]
            self.assertEqual(dyad["global_two_record_positive_components"], 2)
            self.assertEqual(dyad["retained_truth_dyads"], 2)
            self.assertEqual(dyad["candidate_edges_with_missing_postal_comparison"], 1)
            self.assertTrue(dyad["bipartite_audit"]["is_bipartite"])
            self.assertIn(
                "structurally available", dyad["bipartite_audit"]["implication"]
            )
            self.assertEqual(result["truth_conditioned_dyad_frontier"]["status"], "NOT_RUN")
            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn('"truth_edges": [', serialized)
            self.assertNotIn('"source_rows": [', serialized)
            self.assertTrue(
                result["privacy_audit"]["no_row_level_payload_serialized"]
            )

    @unittest.skipIf(rx is None, "rustworkx optional exact backend is not installed")
    def test_blossom_frontier_handles_missing_candidate_query_and_replays(self) -> None:
        left = np.asarray([1, 3, 1, 2], dtype=np.uint32)
        right = np.asarray([2, 4, 3, 4], dtype=np.uint32)
        postal = np.asarray([1.0, 1.0, np.nan, 0.0])
        result = solve_dyad_frontier(left, right, postal)
        self.assertEqual(result["status"], "OPTIMAL")
        self.assertTrue(result["certified"])
        self.assertEqual(result["lower_sum"], 0)
        self.assertEqual(result["upper_sum"], 2)
        self.assertEqual(result["lower"], 0.0)
        self.assertEqual(result["upper"], 1.0)
        for endpoint in ("lower_witness_replay", "upper_witness_replay"):
            replay = result[endpoint]
            self.assertEqual(replay["selected_edges"], 2)
            self.assertEqual(replay["distinct_matched_nodes"], 4)
            self.assertTrue(replay["every_required_node_matched_once"])
            self.assertTrue(replay["selected_edges_exist_in_candidate_graph"])
            self.assertFalse(replay["raw_ids_or_edges_serialized"])

    @unittest.skipIf(rx is None, "rustworkx optional exact backend is not installed")
    def test_blossom_rejects_nonbinary_before_integer_cast(self) -> None:
        left = np.asarray([1], dtype=np.uint32)
        right = np.asarray([2], dtype=np.uint32)
        for invalid in (256.0, 257.0, float("inf"), -256.0, 0.5):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                UciAuditError, "finite and binary before casting"
            ):
                solve_dyad_frontier(left, right, np.asarray([invalid]))

    @unittest.skipIf(rx is None, "rustworkx optional exact backend is not installed")
    def test_blossom_rejects_empty_mismatched_and_self_edge_inputs(self) -> None:
        with self.assertRaisesRegex(UciAuditError, "at least one"):
            solve_dyad_frontier(np.asarray([]), np.asarray([]), np.asarray([]))
        with self.assertRaisesRegex(UciAuditError, "equal length"):
            solve_dyad_frontier(
                np.asarray([1]), np.asarray([2, 3]), np.asarray([1.0])
            )
        with self.assertRaisesRegex(UciAuditError, "self-edges"):
            solve_dyad_frontier(
                np.asarray([1]), np.asarray([1]), np.asarray([1.0])
            )

    def test_reconciliation_counts_reversed_cross_block_duplicate(self) -> None:
        code = (np.uint64(1) << np.uint64(32)) | np.uint64(2)
        data = UciData(
            pair_code=np.asarray([code, code], dtype=np.uint64),
            positive=np.asarray([True, True]),
            postal=np.asarray([1.0, 1.0]),
            block=np.asarray([1, 2], dtype=np.uint8),
            reversed_orientation=np.asarray([False, True]),
            block_nodes=(np.asarray([1, 2]),) * 10,
            per_block=tuple(),
            source_manifest=tuple(),
            missingness={},
        )
        duplicate, unique = reconcile_pairs(data)
        self.assertEqual(duplicate["duplicate_pair_groups"], 1)
        self.assertEqual(duplicate["cross_block_duplicate_pair_groups"], 1)
        self.assertEqual(duplicate["reversed_orientation_duplicate_pair_groups"], 1)
        self.assertEqual(len(unique["code"]), 1)
        with self.assertRaisesRegex(UciAuditError, "edge partition"):
            reconcile_pairs(data, reject_duplicates=True)

    def test_reconciliation_rejects_label_and_query_conflicts(self) -> None:
        code = (np.uint64(1) << np.uint64(32)) | np.uint64(2)
        common = dict(
            pair_code=np.asarray([code, code], dtype=np.uint64),
            block=np.asarray([1, 2], dtype=np.uint8),
            reversed_orientation=np.asarray([False, False]),
            block_nodes=(np.asarray([1, 2]),) * 10,
            per_block=tuple(),
            source_manifest=tuple(),
            missingness={},
        )
        with self.assertRaisesRegex(UciAuditError, "conflicting labels"):
            reconcile_pairs(
                UciData(
                    positive=np.asarray([True, False]),
                    postal=np.asarray([1.0, 1.0]),
                    **common,
                )
            )
        with self.assertRaisesRegex(UciAuditError, "conflicting postal"):
            reconcile_pairs(
                UciData(
                    positive=np.asarray([True, True]),
                    postal=np.asarray([1.0, 0.0]),
                    **common,
                )
            )

    def test_missing_block_and_wrong_member_identity_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = tiny_ten_block_snapshot(root)
            (root / "block_10.zip").unlink()
            with self.assertRaisesRegex(UciAuditError, "all ten"):
                load_all_blocks(
                    root,
                    metadata_path=metadata,
                    enforce_pinned_snapshot=False,
                )
            write_block_zip(root, 10, [pattern(12, 13, False)], member_name="wrong.csv")
            with self.assertRaisesRegex(UciAuditError, "exactly one member"):
                load_all_blocks(
                    root,
                    metadata_path=metadata,
                    enforce_pinned_snapshot=False,
                )

    def test_same_width_wrong_header_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = tiny_ten_block_snapshot(root)
            row = pattern(1, 2, True)
            row["not_id_1"] = row.pop("id_1")
            headers = ("not_id_1", *RAW_COLUMNS[1:])
            text = io.StringIO(newline="")
            writer = csv.DictWriter(text, fieldnames=headers)
            writer.writeheader()
            writer.writerow(row)
            with zipfile.ZipFile(
                root / "block_1.zip", "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("block_1.csv", text.getvalue())
            with self.assertRaisesRegex(UciAuditError, "header/order"):
                load_all_blocks(
                    root,
                    metadata_path=metadata,
                    enforce_pinned_snapshot=False,
                )

    def test_nonnumeric_comparison_is_not_silently_treated_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = tiny_ten_block_snapshot(root)
            write_block_zip(
                root,
                1,
                [pattern(1, 2, True, postal="not-a-number")],
            )
            with self.assertRaisesRegex(UciAuditError, "not numeric or missing"):
                load_all_blocks(
                    root,
                    metadata_path=metadata,
                    enforce_pinned_snapshot=False,
                )


class UciAllBlocksCachedIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(
        (Path.home() / "rl_data" / "krebsregister" / "block_10.zip").is_file(),
        "official all-ten cache not present",
    )
    def test_cached_all_ten_aggregate_contract(self) -> None:
        result = audit_all_ten_blocks(
            Path.home() / "rl_data" / "krebsregister",
            solve_frontier=False,
        )
        self.assertEqual(result["candidate_graph"]["unique_undirected_pairs"], 5_749_132)
        self.assertEqual(result["adjudicated_positive_relation"]["unique_positive_pairs"], 20_931)
        duplicate = result["duplicate_and_cross_block_pair_audit"]
        self.assertEqual(duplicate["duplicate_pair_groups"], 0)
        self.assertEqual(duplicate["cross_block_duplicate_pair_groups"], 0)
        relation = result["adjudicated_positive_relation"]
        self.assertEqual(relation["component_size_histogram"]["2"], 10_313)
        self.assertEqual(relation["maximum_positive_degree"], 8)
        self.assertTrue(
            result["source_order_leakage_audit"][
                "all_blocks_label_sorted_in_source_order"
            ]
        )
        self.assertEqual(result["missingness"]["cmp_plz"], 12_843)
        self.assertEqual(
            result["block_local_dyad_invalidity"][
                "local_dyads_absorbed_into_larger_global_entities"
            ],
            7_597,
        )
        dyad = result["truth_conditioned_dyad_reduction"]
        self.assertEqual(dyad["retained_truth_dyads"], 10_297)
        self.assertEqual(dyad["retained_candidate_edges"], 249_048)
        self.assertEqual(dyad["giant_component"]["nodes"], 19_346)
        bipartite = dyad["bipartite_audit"]
        self.assertFalse(bipartite["is_bipartite"])
        self.assertEqual(bipartite["nonbipartite_components"], 46)
        self.assertEqual(bipartite["nodes_in_nonbipartite_components"], 19_554)
        self.assertEqual(bipartite["odd_cycle_evidence"]["cycle_edges"] % 2, 1)


if __name__ == "__main__":
    unittest.main()
