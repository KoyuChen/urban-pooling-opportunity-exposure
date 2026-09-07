#!/usr/bin/env python3
"""Recover a frozen Chicago panel, preserving earlier attempts and cohort selection.

Only missing reports from transport failures are retried. A completed window,
including a scientifically unresolved query, is never selected using its
endpoints. Scientific ineligibility is retained. Damaged checkpoints abort;
they must not silently become new live-data pulls.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import run_chicago_k2_fixed_panel as panel

RUNNER_FILES = (
    "live_chicago_k2_frontier.py",
    "live_chicago_k2_frontier_partitioned.py",
    "live_chicago_k2_frontier_boundary.py",
)
REUSABLE = {"COMPLETED", "INELIGIBLE_FIXED_CORE", "INELIGIBLE_RESOURCE_CAP"}


def runner_hashes() -> dict[str, str]:
    return {name: panel.sha256_file(panel.HERE / name) for name in RUNNER_FILES}


def evidence_files(root: Path) -> dict[str, str]:
    files = {}
    for directory in sorted(root.iterdir()):
        if directory.is_symlink():
            raise ValueError(f"checkpoint contains a symlink: {directory.name}")
        if not directory.is_dir() or not (
            directory.name.startswith("cohort_") or directory.name == "history"
        ):
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"checkpoint contains a symlink: {path.name}")
            if path.is_file():
                files[path.relative_to(root).as_posix()] = panel.sha256_file(path)
    return files


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_checkpoint(manifest: dict[str, Any], root: Path, protocol_path: Path) -> None:
    if manifest.get("checkpoint_version") != "chicago-k2-panel-checkpoint/v1":
        raise ValueError("unsupported checkpoint version")
    if manifest.get("protocol_sha256") != panel.sha256_file(protocol_path):
        raise ValueError("checkpoint protocol differs from the requested protocol")
    if manifest.get("runner_sha256") != runner_hashes():
        raise ValueError("checkpoint solver/extraction code differs from the current runner")
    if evidence_files(root) != manifest.get("files"):
        raise ValueError("checkpoint files are missing, altered, or unpinned")


def verify_driver(directory: Path, protocol: dict[str, Any], index: int, start: Any) -> None:
    driver_path = directory / "driver.json"
    if not driver_path.exists():
        raise ValueError(f"missing driver record: {directory.name}")
    driver = json.loads(driver_path.read_text(encoding="utf-8"))
    if driver.get("window_index") != index or driver.get("core_start_local") != start.isoformat():
        raise ValueError(f"driver window mismatch: {directory.name}")
    actual = list(driver.get("command", []))
    expected = panel.target_command(protocol, start, directory)
    # Python installation and absolute checkout/output paths vary by machine.
    if len(actual) < 4 or Path(actual[1]).name != panel.TARGET.name:
        raise ValueError(f"driver entrypoint mismatch: {directory.name}")
    actual = actual[2:]
    expected = expected[2:]
    if actual[:1] != ["--output-dir"]:
        raise ValueError(f"driver output argument mismatch: {directory.name}")
    actual[1] = expected[1]
    if actual != expected:
        raise ValueError(f"driver parameters differ from the frozen protocol: {directory.name}")
    if (directory / "report.json").exists() and driver.get("process_exit_status") != 0:
        raise ValueError(f"completed report has a failed driver: {directory.name}")


def recovery_class(row: dict[str, Any], slug: str) -> str:
    if row["status"] in REUSABLE:
        if row["status"] == "COMPLETED" and row["closure_status"] != "PASS":
            raise ValueError(f"completed window lacks count closure: {slug}")
        return "reuse"
    if row["status"] == "EXECUTION_FAILED" and row.get("failure_type") == "LiveDataError" and (
        "request failed" in str(row.get("failure_message", ""))
        or "both Socrata APIs failed" in str(row.get("failure_message", ""))
    ):
        return "retry"
    raise ValueError(f"window is invalid or not a transport failure: {slug}: {row['status']}")


def recovery_plan(root: Path, protocol_path: Path) -> dict[str, Any]:
    protocol = panel.load_protocol(protocol_path)
    reused, retry = [], []
    for index, start in enumerate(panel.expand_windows(protocol)):
        slug = panel.window_slug(index, start)
        directory = root / slug
        verify_driver(directory, protocol, index, start)
        row = panel.summarize_window(index=index, start=start, directory=directory)
        if recovery_class(row, slug) == "reuse":
            reused.append({"index": index, "slug": slug, "status": row["status"]})
        else:
            retry.append({"index": index, "slug": slug})
    return {"reused_windows": reused, "retry_windows": retry, "matrix": {"include": retry}}


def seal_checkpoint(root: Path, protocol_path: Path, provenance: list[dict[str, Any]]) -> dict[str, Any]:
    checkpoint = {
        "checkpoint_version": "chicago-k2-panel-checkpoint/v1",
        "protocol_sha256": panel.sha256_file(protocol_path),
        "runner_sha256": runner_hashes(),
        "files": evidence_files(root),
        "provenance": provenance,
    }
    write_json(root / "checkpoint.json", checkpoint)
    return checkpoint


def prepare(seed_dir: Path, manifest_path: Path, output_dir: Path, protocol_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_checkpoint(manifest, seed_dir, protocol_path)
    plan = recovery_plan(seed_dir, protocol_path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("recovery output must be empty; use merge to update a prepared checkpoint")
    output_dir.mkdir(parents=True, exist_ok=True)
    for relative in manifest["files"]:
        source = seed_dir / relative
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write_json(output_dir / "checkpoint.json", manifest)
    write_json(output_dir / "recovery_plan.json", plan)
    panel.aggregate(protocol_path, output_dir, panel.expand_windows(panel.load_protocol(protocol_path)))
    return plan


def merge(root: Path, retries: Path, protocol_path: Path, provenance: dict[str, Any]) -> dict[str, Any]:
    checkpoint = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    verify_checkpoint(checkpoint, root, protocol_path)
    plan = recovery_plan(root, protocol_path)
    protocol = panel.load_protocol(protocol_path)
    windows = panel.expand_windows(protocol)
    allowed = {item["slug"] for item in plan["retry_windows"]}
    actual = {path.name for path in retries.glob("cohort_*") if path.is_dir()}
    if actual - allowed:
        raise ValueError("retry directory attempts to replace a reusable or undeclared window")
    # Validate every retry before mutating any previous attempt.
    if retries.exists():
        evidence_files(retries)
    for item in plan["retry_windows"]:
        source = retries / item["slug"]
        if not source.exists():
            continue
        verify_driver(source, protocol, item["index"], windows[item["index"]])
        row = panel.summarize_window(index=item["index"], start=windows[item["index"]], directory=source)
        recovery_class(row, item["slug"])
    applied = []
    for item in plan["retry_windows"]:
        slug = item["slug"]
        source = retries / slug
        if not source.exists():
            continue
        attempts = root / "history" / slug
        attempts.mkdir(parents=True, exist_ok=True)
        attempt = max([int(path.name) for path in attempts.iterdir() if path.name.isdigit()], default=0) + 1
        (root / slug).rename(attempts / f"{attempt:04d}")
        shutil.copytree(source, root / slug)
        applied.append(item["index"])
    provenance = {**provenance, "retried_window_indices": applied}
    seal_checkpoint(root, protocol_path, [*checkpoint.get("provenance", []), provenance])
    report = panel.aggregate(protocol_path, root, windows)
    write_json(root / "recovery_plan.json", recovery_plan(root, protocol_path))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=panel.DEFAULT_PROTOCOL)
    parser.add_argument("--seed-dir", type=Path)
    parser.add_argument("--seed-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--merge-dir", type=Path)
    parser.add_argument("--source-run-id", default="local")
    args = parser.parse_args()
    if args.merge_dir:
        result = merge(args.output_dir, args.merge_dir, args.protocol, {"retry_run": args.source_run_id})
        print(json.dumps({key: value for key, value in result.items() if key != "windows"}, sort_keys=True))
    else:
        if not args.seed_dir or not args.seed_manifest:
            parser.error("prepare requires --seed-dir and --seed-manifest")
        plan = prepare(args.seed_dir, args.seed_manifest, args.output_dir, args.protocol)
        print(json.dumps(plan, sort_keys=True))


if __name__ == "__main__":
    main()
