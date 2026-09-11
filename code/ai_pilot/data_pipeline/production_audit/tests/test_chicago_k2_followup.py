import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chicago_k2_followup as followup


class ChicagoFollowupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "checkpoint"
        followup.initialize(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_frozen_runner_hashes_and_full_unstarted_denominator(self):
        protocol = followup.panel.load_protocol(followup.PROTOCOL)
        self.assertEqual(followup.runner_hashes(), protocol["runner_sha256"])
        report = followup.aggregate(self.root)
        self.assertEqual(report["declared_window_count"], 96)
        self.assertEqual(report["unstarted_window_count"], 96)
        self.assertEqual(report["execution_failure_window_count"], 0)
        self.assertEqual(report["gate_status"], "HOLD_INCOMPLETE")

    def test_first_batch_is_fixed_and_later_batch_cannot_jump_ahead(self):
        plan = followup.plan(self.root, 0)
        self.assertEqual([row["index"] for row in plan["selected_windows"]], list(range(12)))
        with self.assertRaisesRegex(ValueError, "earlier batch"):
            followup.plan(self.root, 1)

    def test_missing_artifacts_are_attempted_failures_not_unstarted(self):
        followup.merge(self.root, self.root.parent / "absent", [0, 1], "fixture-run")
        report = followup.aggregate(self.root)
        self.assertEqual(report["status_counts"]["ATTEMPTED_NO_ARTIFACT"], 2)
        self.assertEqual(report["unstarted_window_count"], 94)
        self.assertEqual(report["execution_failure_window_count"], 2)
        self.assertEqual(
            [row["index"] for row in followup.plan(self.root, 0)["selected_windows"]],
            list(range(12)),
        )

    def test_downloaded_transport_failure_is_retained_and_retryable(self):
        attempts = self.root.parent / "attempts"
        protocol = followup.panel.load_protocol(followup.PROTOCOL)
        start = followup.panel.expand_windows(protocol)[0]
        directory = attempts / followup.panel.window_slug(0, start)
        directory.mkdir(parents=True)
        command = followup.panel.target_command(
            protocol, start, directory, indexed_count_transport=True
        )
        followup.write_json(directory / "driver.json", {
            "window_index": 0,
            "core_start_local": start.isoformat(),
            "command": command,
            "process_exit_status": 1,
            "entrypoint_sha256": followup.panel.sha256_file(followup.panel.INDEXED_COUNT_TARGET),
        })
        followup.write_json(directory / "failure.json", {
            "error_type": "LiveDataError",
            "error_message": "request failed after retries",
        })
        report = followup.merge(self.root, attempts, [0], "fixture-run")
        self.assertEqual(report["status_counts"]["EXECUTION_FAILED"], 1)
        self.assertEqual(report["unstarted_window_count"], 95)
        self.assertIn(0, [row["index"] for row in followup.plan(self.root, 0)["selected_windows"]])

    def test_changed_evidence_and_nonsequential_batch_abort(self):
        (self.root / followup.OBSERVATIONS).write_text("[] \n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing, changed or unpinned"):
            followup.verify(self.root)
        followup.seal(self.root, [{"event": "TEST_RESEAL"}])
        with self.assertRaisesRegex(ValueError, "outside"):
            followup.plan(self.root, 8)

    def test_tex_retains_all_status_denominators(self):
        followup.aggregate(self.root)
        tex = (self.root / "FOLLOWUP_RESULTS.tex").read_text(encoding="utf-8")
        self.assertIn("Of 96 declared windows, 0 completed", tex)
        self.assertIn("96 were unstarted", tex)
        self.assertIn("not a probability sample", tex)

    def test_archived_batch1_hashes_and_complete_denominators(self):
        root = followup.panel.HERE.parent / "results/chicago_k2_followup/batch1_20260911"
        manifest = followup.read_json(root / "MANIFEST.json")
        for name, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest)
        report = followup.read_json(root / "followup_report.json")
        self.assertEqual([w["window_index"] for w in report["windows"]], list(range(96)))
        self.assertEqual(report["status_counts"], {
            "COMPLETED": 21, "INELIGIBLE_FIXED_CORE": 3, "UNSTARTED": 72,
        })
        self.assertEqual(report["endpoint_pair_count"], 2492 + 626 + 12)
        self.assertEqual(report["gate_status"], "HOLD_INCOMPLETE")

    def test_archived_batch1_limits_are_not_infeasibility_or_full_intervals(self):
        root = followup.panel.HERE.parent / "results/chicago_k2_followup/batch1_20260911"
        records = followup.read_json(root / "UNRESOLVED_AUDIT.json")["records"]
        self.assertEqual(len(records), 12)
        new = [r for r in records if r["window_index"] == 17]
        self.assertEqual(len(new), 4)
        self.assertEqual({r["query"] for r in new}, {"mean_absolute_trip_miles_gap_per_core"})
        self.assertEqual(sum(r["endpoint_source"] == "canonical_temporal_only_identity" for r in new), 1)
        for row in records:
            self.assertEqual((row["lower"], row["upper"]), ("", ""))
            self.assertEqual(row["lower_status"], "INCUMBENT_ONLY_UNRESOLVED_LIMIT")
            self.assertEqual(row["upper_status"], "OPTIMAL_NUMERICAL_MILP")


if __name__ == "__main__":
    unittest.main()
