#!/usr/bin/env python3
"""Build a reproducibility manifest for the AI pilot artifact."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/boundpool_manifest_mplconfig")

import matplotlib
import numpy
import pandas
import scipy
import sklearn


ROOT = Path(__file__).resolve().parent
EXCLUDED_PARTS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".part"}
EXCLUDED_RELATIVE_PREFIXES = {"results/prefix_mechanics/"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    integration = json.loads(
        (ROOT / "integration/results/benchmark_results.json").read_text(encoding="utf-8")
    )
    ablation = json.loads(
        (
            ROOT
            / "integration/ablations/no_geography_equality_20260825/results/ablation_results.json"
        ).read_text(encoding="utf-8")
    )
    bound_summary = pandas.read_csv(
        ROOT / "bounds/results/synthetic_validation_summary.csv"
    )
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == "PILOT_MANIFEST.json":
            continue
        if EXCLUDED_PARTS.intersection(path.parts) or path.suffix in EXCLUDED_SUFFIXES:
            continue
        relative = str(path.relative_to(ROOT))
        if any(relative.startswith(prefix) for prefix in EXCLUDED_RELATIVE_PREFIXES):
            continue
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    diagnostic_node = integration["node_benchmark"]
    primary_node = ablation["weak_mil_ai_held_out"]
    primary_edge = ablation["true_edge_recovery"]
    primary_rank = ablation["weak_mil_ai_true_edge_ranking"]
    primary_ai90 = ablation["weak_mil_ai_bounds"]["0.90"]
    primary_ai95 = ablation["weak_mil_ai_bounds"]["0.95"]
    rule_brier = diagnostic_node["transparent_rule_brier"]
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "artifact": "privacy-coarsened urban pooling AI pilot",
        "human_experiment": False,
        "empirical_status": (
            "complete-day City extraction blocked in this workspace; real prefix data used "
            "only for a non-substantive mechanics check"
        ),
        "primary_locked_benchmark": {
            "specification": "22-feature weak-MIL with six geography-equality features removed",
            "transparent_rule_brier": rule_brier,
            "weak_mil_ai_brier": primary_node["brier"],
            "relative_brier_improvement": (
                rule_brier - primary_node["brier"]
            ) / rule_brier,
            "candidate_true_edge_recall": primary_edge["candidate_true_edge_recall"],
            "hidden_true_edge_mrr": primary_rank["mean_reciprocal_rank"],
            "hidden_true_edge_top_1": primary_rank["top_1_rate"],
            "ai_90_bound_lower": primary_ai90["lower"],
            "ai_90_bound_upper": primary_ai90["upper"],
            "ai_90_width_reduction": primary_ai90["width_reduction_vs_untrimmed"],
            "ai_90_covers_truth": primary_ai90["covers_truth"],
            "ai_90_truth_score_eligible": primary_ai90["truth_score_eligible"],
            "ai_95_bound_lower": primary_ai95["lower"],
            "ai_95_bound_upper": primary_ai95["upper"],
            "ai_95_width_reduction": primary_ai95["width_reduction_vs_untrimmed"],
            "ai_95_covers_truth": primary_ai95["covers_truth"],
            "ai_95_truth_score_eligible": primary_ai95["truth_score_eligible"],
        },
        "diagnostic_locked_benchmark": {
            "specification": "original 28-feature weak-MIL; diagnostic only",
            "reason": "tract-equality features mechanically encode the locked synthetic target",
            "weak_mil_ai_brier": diagnostic_node["weak_mil_ai_brier"],
            "relative_brier_improvement": diagnostic_node[
                "relative_brier_improvement_ai_vs_rule"
            ],
            "ai_95_covers_truth": integration["bounds"]["scenarios"][
                "weak_mil_ai_retention_0.95"
            ]["covers_truth"],
        },
        "score_bound_warning": (
            "The primary ablation removes exact geography equalities but continuous coordinates "
            "still proxy the synthetic SES bin. Score-restricted bounds are model-dependent "
            "sensitivity regions; the untrimmed graph is the score-free reference."
        ),
        "solver_validation": bound_summary.to_dict(orient="records"),
        "environment": {
            "python": platform.python_version(),
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "file_count": len(files),
        "files": files,
    }
    (ROOT / "PILOT_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(files)} file records to {ROOT / 'PILOT_MANIFEST.json'}")


if __name__ == "__main__":
    main()
