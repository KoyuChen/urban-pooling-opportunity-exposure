from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import resume_chicago_k2_fixed_panel as resume


class ChicagoResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        self.protocol = resume.panel.load_protocol(resume.panel.DEFAULT_PROTOCOL)
        self.protocol.update(date_start="2026-01-05", date_end="2026-01-05", expected_window_count=3)
        self.protocol_path = self.root / "protocol.json"
        resume.write_json(self.protocol_path, self.protocol)
        self.windows = resume.panel.expand_windows(self.protocol)
        self.write_window(self.seed, 0, "completed")
        self.write_window(self.seed, 1, "ineligible")
        self.write_window(self.seed, 2, "transport")
        resume.seal_checkpoint(self.seed, self.protocol_path, [{"source_run": "fixture"}])

    def write_window(self, base: Path, index: int, status: str) -> Path:
        start = self.windows[index]
        directory = base / resume.panel.window_slug(index, start)
        directory.mkdir(parents=True)
        resume.write_json(directory / "driver.json", {
            "window_index": index,
            "core_start_local": start.isoformat(),
            "command": resume.panel.target_command(self.protocol, start, directory),
            "process_exit_status": 0 if status == "completed" else 1,
        })
        if status == "completed":
            resume.write_json(directory / "report.json", {
                "extraction": {"predeclared_core_start_local": start.isoformat()},
                "cohort": {"core_rows": 2, "buffer_rows": 3, "candidate_rows": 5,
                           "public_temporal_candidate_universe_closure_status": "PASS"},
                "logical_graph": {"edge_count": 4},
                "monotonicity_audit": {"status": "PASS"},
                "sensitivity_rows": [{"endpoint_pair_certification": "CERTIFIED_OPTIMAL_PAIR"}],
            })
        else:
            resume.write_json(directory / "failure.json", {
                "error_type": "LiveDataError",
                "error_message": "no scan bin met the requirements" if status == "ineligible" else
                                 "both Socrata APIs failed: request failed: TimeoutError",
            })
        return directory

    def prepare(self) -> tuple[Path, dict]:
        out = self.root / "prepared"
        plan = resume.prepare(self.seed, self.seed / "checkpoint.json", out, self.protocol_path)
        return out, plan

    def test_only_transport_failure_is_retried(self) -> None:
        out, plan = self.prepare()
        self.assertEqual([item["index"] for item in plan["retry_windows"]], [2])
        self.assertEqual([item["status"] for item in plan["reused_windows"]],
                         ["COMPLETED", "INELIGIBLE_FIXED_CORE"])
        self.assertEqual(resume.evidence_files(self.seed), resume.evidence_files(out))

    def test_altered_or_missing_or_unpinned_files_abort(self) -> None:
        manifest = json.loads((self.seed / "checkpoint.json").read_text())
        for mutation in ("altered", "missing", "added"):
            with self.subTest(mutation=mutation):
                original = self.seed / resume.panel.window_slug(0, self.windows[0]) / "report.json"
                content = original.read_bytes()
                extra = original.with_name("untracked.json")
                if mutation == "altered":
                    original.write_bytes(content + b" ")
                elif mutation == "missing":
                    original.unlink()
                else:
                    extra.write_text("{}")
                with self.assertRaisesRegex(ValueError, "missing, altered, or unpinned"):
                    resume.verify_checkpoint(manifest, self.seed, self.protocol_path)
                original.write_bytes(content)
                if extra.exists():
                    extra.unlink()

    def test_changed_protocol_cannot_reuse_checkpoint(self) -> None:
        self.protocol["support"]["base_radius_km"] = 4
        resume.write_json(self.protocol_path, self.protocol)
        with self.assertRaisesRegex(ValueError, "protocol differs"):
            self.prepare()

    def test_merge_keeps_original_failure_and_reused_window_hashes(self) -> None:
        out, _ = self.prepare()
        initial = resume.evidence_files(out)
        retries = self.root / "retries"
        self.write_window(retries, 2, "completed")
        result = resume.merge(out, retries, self.protocol_path, {"retry_run": "fixture-retry"})
        self.assertEqual(result["completed_window_count"], 2)
        self.assertEqual(result["ineligible_window_count"], 1)
        self.assertEqual(result["failed_or_invalid_window_count"], 0)
        self.assertEqual(result["certified_endpoint_pair_count"], 2)
        for index in (0, 1):
            slug = resume.panel.window_slug(index, self.windows[index])
            for path, sha in initial.items():
                if path.startswith(slug + "/"):
                    self.assertEqual(resume.panel.sha256_file(out / path), sha)
        failed_slug = resume.panel.window_slug(2, self.windows[2])
        self.assertTrue((out / "history" / failed_slug / "0001" / "failure.json").exists())
        checkpoint = json.loads((out / "checkpoint.json").read_text())
        resume.verify_checkpoint(checkpoint, out, self.protocol_path)
        self.assertEqual(resume.recovery_plan(out, self.protocol_path)["retry_windows"], [])

    def test_retry_cannot_replace_a_successful_window(self) -> None:
        out, _ = self.prepare()
        retries = self.root / "retries"
        self.write_window(retries, 0, "completed")
        initial = resume.evidence_files(out)
        with self.assertRaisesRegex(ValueError, "replace a reusable"):
            resume.merge(out, retries, self.protocol_path, {})
        self.assertEqual(resume.evidence_files(out), initial)

    def test_driver_refuses_to_overwrite_an_existing_attempt(self) -> None:
        with self.assertRaisesRegex(ValueError, "cohort output is not empty"):
            resume.panel.run_window(self.protocol, 0, self.windows[0], self.seed)

    def test_partial_retry_is_retained_without_discarding_other_records(self) -> None:
        out, _ = self.prepare()
        result = resume.merge(out, self.root / "no-new-artifacts", self.protocol_path, {})
        self.assertEqual(result["failed_or_invalid_window_count"], 1)
        self.assertEqual(result["completed_window_count"], 1)

    def test_unclosed_retry_cannot_mutate_checkpoint(self) -> None:
        out, _ = self.prepare()
        retries = self.root / "retries"
        directory = self.write_window(retries, 2, "completed")
        report = json.loads((directory / "report.json").read_text())
        report["cohort"]["public_temporal_candidate_universe_closure_status"] = "FAIL"
        resume.write_json(directory / "report.json", report)
        initial = resume.evidence_files(out)
        with self.assertRaisesRegex(ValueError, "lacks count closure"):
            resume.merge(out, retries, self.protocol_path, {})
        self.assertEqual(resume.evidence_files(out), initial)

    def test_symlinked_cohort_is_rejected(self) -> None:
        linked = self.root / "linked"
        linked.mkdir()
        slug = resume.panel.window_slug(0, self.windows[0])
        (linked / slug).symlink_to(self.seed / slug, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "contains a symlink"):
            resume.evidence_files(linked)

    def test_compact_report_without_csv_is_invalid(self) -> None:
        directory = self.seed / resume.panel.window_slug(0, self.windows[0])
        report = json.loads((directory / "report.json").read_text())
        report.pop("sensitivity_rows")
        resume.write_json(directory / "report.json", report)
        row = resume.panel.summarize_window(index=0, start=self.windows[0], directory=directory)
        self.assertEqual(row["status"], "INVALID_MISSING_SENSITIVITY")

    def test_truncated_sensitivity_is_invalid(self) -> None:
        directory = self.seed / resume.panel.window_slug(0, self.windows[0])
        report = json.loads((directory / "report.json").read_text())
        report["monotonicity_audit"]["chain_audits"] = [{"point_count": 2}]
        resume.write_json(directory / "report.json", report)
        row = resume.panel.summarize_window(index=0, start=self.windows[0], directory=directory)
        self.assertEqual(row["status"], "INVALID_INCOMPLETE_SENSITIVITY")


if __name__ == "__main__":
    unittest.main()
