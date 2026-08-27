from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


EXTERNAL_DIR = Path(__file__).resolve().parents[1]
if str(EXTERNAL_DIR) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_DIR))

from uci_rlcp_adapter import (  # noqa: E402
    AdapterError,
    REQUIRED_COLUMNS,
    compile_csvs,
    load_metadata,
    positive_component_profile,
)


KEY = b"fixture-only-key-with-32-bytes!!"


def write_block(path: Path, rows: list[dict], *, delimiter: str = ",") -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def row(left: str, right: str, match: bool, **overrides: str) -> dict:
    result = {
        "id_1": left,
        "id_2": right,
        "cmp_fname_c1": "0.83",
        "cmp_fname_c2": "?",
        "cmp_lname_c1": "1",
        "cmp_lname_c2": "0.25",
        "cmp_sex": "1",
        "cmp_bd": "0",
        "cmp_bm": "1",
        "cmp_by": "1",
        "cmp_plz": "?",
        "is_match": "TRUE" if match else "FALSE",
    }
    result.update(overrides)
    return result


class UciRlcpAdapterTest(unittest.TestCase):
    def test_metadata_fixture_contains_no_rows_and_matches_contract(self) -> None:
        metadata = load_metadata()
        self.assertEqual(metadata["dataset_id"], 210)
        self.assertEqual(metadata["license"], "CC BY 4.0")
        self.assertEqual(metadata["candidate_pair_count_as_reported"], 5_749_132)
        self.assertIsNone(metadata["archive_sha256"])
        self.assertNotIn("rows", metadata)

    def test_compile_coarsens_and_keeps_truth_out_of_public_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "block.csv"
            public = root / "public.jsonl"
            truth = root / "truth.jsonl"
            write_block(
                source,
                [
                    row("100", "101", True),
                    row("100", "200", False, cmp_fname_c1="0.49", cmp_plz="0"),
                    row("200", "201", True, cmp_fname_c1="1", cmp_plz="1"),
                    row("101", "201", False, cmp_fname_c1="0", cmp_plz="0"),
                ],
                delimiter=";",
            )

            summary = compile_csvs(
                [source], public_output=public, truth_output=truth, key=KEY
            )
            public_rows = [json.loads(line) for line in public.read_text().splitlines()]
            truth_rows = [json.loads(line) for line in truth.read_text().splitlines()]

            self.assertEqual(summary.source_rows, 4)
            self.assertEqual(summary.emitted_matches, 2)
            self.assertEqual(len(public_rows), len(truth_rows))
            self.assertEqual(public_rows[0]["fname_c1_bin"], "high")
            self.assertEqual(public_rows[0]["fname_c2_bin"], "unknown")
            self.assertEqual(public_rows[0]["postal_agreement_support"], [0, 1])
            self.assertEqual(public_rows[1]["fname_c1_bin"], "low")
            self.assertEqual(public_rows[2]["fname_c1_bin"], "exact")
            self.assertEqual(public_rows[3]["fname_c1_bin"], "zero")
            self.assertNotIn("is_match", public_rows[0])
            self.assertEqual({item["is_match"] for item in truth_rows}, {True, False})
            self.assertEqual(
                {item["edge_id"] for item in public_rows},
                {item["edge_id"] for item in truth_rows},
            )
            serialized_public = public.read_text(encoding="utf-8")
            for raw_id in ('"100"', '"101"', '"200"', '"201"'):
                self.assertNotIn(raw_id, serialized_public)

    def test_profile_identifies_dyads_without_pairing_larger_components(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "block.csv"
            write_block(
                source,
                [
                    row("a", "b", True, cmp_plz="1"),
                    row("b", "c", True, cmp_plz="1"),
                    row("d", "e", True, cmp_plz="?"),
                    row("a", "d", False),
                ],
            )
            profile, dyad_nodes = positive_component_profile([source])
            self.assertEqual(profile["component_size_histogram"], {"2": 1, "3": 1})
            self.assertEqual(profile["two_record_components"], 1)
            self.assertFalse(profile["positive_relation_is_matching"])
            self.assertEqual(dyad_nodes, frozenset(("d", "e")))
            self.assertEqual(
                profile["two_record_components_with_observed_true_edge_field"]["cmp_plz"],
                0,
            )

    def test_rejects_nonbinary_documented_binary_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.csv"
            write_block(source, [row("a", "b", True, cmp_sex="0.5")])
            with self.assertRaisesRegex(AdapterError, "not binary"):
                list(__import__("uci_rlcp_adapter").iter_patterns(source))

    def test_refuses_to_overwrite_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "block.csv"
            public = root / "public.jsonl"
            truth = root / "truth.jsonl"
            write_block(source, [row("a", "b", True)])
            public.write_text("owned by caller\n", encoding="utf-8")
            with self.assertRaisesRegex(AdapterError, "refusing to overwrite"):
                compile_csvs(
                    [source], public_output=public, truth_output=truth, key=KEY
                )


if __name__ == "__main__":
    unittest.main()
