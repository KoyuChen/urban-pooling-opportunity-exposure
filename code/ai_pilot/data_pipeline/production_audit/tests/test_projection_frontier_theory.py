import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[5]
MODULE_PATH = ROOT / "code" / "ai_pilot" / "benchmarks" / "projection_frontier_theory_audit.py"
SPEC = importlib.util.spec_from_file_location("projection_frontier_theory_audit", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ProjectionFrontierTheoryTests(unittest.TestCase):
    def test_exposed_faces_are_endpoint_criterion(self):
        restricted = ((1, 0, 0), (0, 0, 1))
        ordered = restricted + ((0, 1, 0),)
        weight = (0, 1, 2)
        self.assertEqual(MODULE.frontier(restricted, weight), (0, 2))
        self.assertEqual(MODULE.frontier(ordered, weight), (0, 2))
        self.assertEqual(
            MODULE.exposed_face_intersection(restricted, ordered, weight),
            (True, True),
        )

    def test_binary_point_has_constructive_separator(self):
        point = (1, 0, 1, 0)
        weight = MODULE.separator(point)
        values = {
            candidate: MODULE.dot(weight, candidate)
            for candidate in __import__("itertools").product((0, 1), repeat=4)
        }
        self.assertEqual(max(values, key=values.get), point)
        self.assertEqual(list(values.values()).count(values[point]), 1)

    def test_minimal_interior_witness(self):
        witness = MODULE.separation_witness()
        self.assertTrue(witness["strictly_interior"])
        self.assertTrue(
            witness["three_buffers_minimal_for_strict_interior_with_distinct_weights"]
        )
        self.assertEqual(witness["two_buffer_strict_inclusions_checked"], 2)

    def test_full_audit_is_deterministic_and_manifested(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one = MODULE.run(Path(first))
            two = MODULE.run(Path(second))
            self.assertEqual(one, two)
            self.assertEqual(one["status"], "PASS_PROJECTION_TO_FRONTIER_THEORY")
            self.assertEqual(one["audit"]["mismatches"], 0)
            for name in ("SUMMARY.json", "EXHAUSTIVE_CELLS.csv", "REPORT.md", "RESULTS.tex"):
                self.assertEqual((Path(first) / name).read_bytes(), (Path(second) / name).read_bytes())
            manifest = json.loads((Path(first) / "MANIFEST.json").read_text())
            self.assertEqual(set(manifest["files"]), {
                "SUMMARY.json", "EXHAUSTIVE_CELLS.csv", "REPORT.md", "RESULTS.tex"
            })


if __name__ == "__main__":
    unittest.main()
