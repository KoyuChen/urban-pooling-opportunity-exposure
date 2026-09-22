import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[5]
MODULE_PATH = ROOT / "code" / "ai_pilot" / "benchmarks" / "complexity_boundary_audit.py"
SPEC = importlib.util.spec_from_file_location("complexity_boundary_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class ComplexityBoundaryAuditTest(unittest.TestCase):
    def test_half_open_touching_does_not_raise_depth(self) -> None:
        rows = [
            audit.ExactRow("left", 0, 1, "core"),
            audit.ExactRow("right", 1, 2, "buffer"),
        ]
        self.assertEqual(audit.maximum_depth(rows), 1)
        self.assertFalse(audit.positive_overlap(rows[0], rows[1]))

    def test_capacity_two_event_need_not_be_a_path(self) -> None:
        witness = audit.validate_star_witness()
        self.assertEqual(witness["maximum_depth"], 2)
        self.assertEqual(witness["maximum_overlap_graph_degree"], 4)
        self.assertTrue(witness["path_claim_refuted"])

    def test_fixed_q_feasibility_can_have_a_gap(self) -> None:
        witness = audit.validate_fixed_q_gap_witness()
        self.assertEqual(witness["feasible_q_values"], [0, 2])
        self.assertTrue(witness["q_one_infeasible"])

    def test_component_formula_selects_only_core_components(self) -> None:
        rows = [
            audit.ExactRow("c0", 0, 3, "core"),
            audit.ExactRow("b0", 2, 4, "buffer"),
            audit.ExactRow("b1", 6, 7, "buffer"),
        ]
        certificate = audit.low_depth_support_certificate(rows, 2)
        self.assertEqual(certificate["status"], "MAXIMUM_SUPPORT_CERTIFIED")
        self.assertEqual(certificate["maximum_selected_buffers"], 1)
        self.assertEqual(audit.brute_force_q_values(rows, 2), frozenset({1}))

    def test_singleton_core_component_is_infeasible(self) -> None:
        rows = [
            audit.ExactRow("c0", 0, 1, "core"),
            audit.ExactRow("b0", 2, 3, "buffer"),
        ]
        certificate = audit.low_depth_support_certificate(rows, 2)
        self.assertEqual(
            certificate["status"], "INFEASIBLE_SINGLETON_CORE_COMPONENT"
        )
        self.assertEqual(audit.brute_force_q_values(rows, 2), frozenset())

    def test_exhaustive_boundary_has_no_mismatch(self) -> None:
        validation = audit.run_exhaustive_audit()
        self.assertGreater(validation["low_depth_capacity_cases_checked"], 1000)
        self.assertGreater(validation["fixed_q_cells_checked"], 100)
        self.assertEqual(validation["component_formula_mismatches"], 0)
        self.assertEqual(validation["well_anchored_fixed_q_mismatches"], 0)

    def test_report_generation_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            audit.write_outputs(Path(first))
            audit.write_outputs(Path(second))
            for name in ("SUMMARY.json", "REPORT.md", "MANIFEST.json"):
                self.assertEqual(
                    (Path(first) / name).read_bytes(),
                    (Path(second) / name).read_bytes(),
                )


if __name__ == "__main__":
    unittest.main()
