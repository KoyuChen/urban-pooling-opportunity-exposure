#!/usr/bin/env python3
"""Small end-to-end test; synthetic pair truth is not passed to the model."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


def make_day(day: str, seed: int, n_groups: int = 35, n_unmatched: int = 45) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    base = pd.Timestamp(day)
    for group in range(n_groups):
        start_min = rng.integers(6 * 60, 22 * 60)
        plat = 41.88 + rng.normal(0, 0.025)
        plon = -87.68 + rng.normal(0, 0.035)
        dlat = plat + rng.normal(0.035, 0.010)
        dlon = plon + rng.normal(0.030, 0.012)
        for member in range(2):
            rows.append(
                {
                    "trip_id": f"{day}-g{group}-m{member}",
                    "trip_start_timestamp": base + pd.Timedelta(minutes=int(start_min + rng.integers(-5, 6))),
                    "trip_end_timestamp": base + pd.Timedelta(minutes=int(start_min + 35 + rng.integers(-5, 6))),
                    "trip_seconds": int(2100 + rng.normal(0, 180)),
                    "trip_miles": float(7 + rng.normal(0, 0.6)),
                    "pickup_centroid_latitude": plat + rng.normal(0, 0.002),
                    "pickup_centroid_longitude": plon + rng.normal(0, 0.002),
                    "dropoff_centroid_latitude": dlat + rng.normal(0, 0.003),
                    "dropoff_centroid_longitude": dlon + rng.normal(0, 0.003),
                    "pickup_community_area": group % 12,
                    "dropoff_community_area": (group + 3) % 12,
                    "pickup_census_tract": 1000 + group % 20,
                    "dropoff_census_tract": 2000 + group % 20,
                    "shared_trip_authorized": True,
                    "shared_trip_match": True,
                    "trips_pooled": 2,
                }
            )
    for index in range(n_unmatched):
        start_min = rng.integers(6 * 60, 22 * 60)
        plat = 41.88 + rng.normal(0, 0.05)
        plon = -87.68 + rng.normal(0, 0.07)
        rows.append(
            {
                "trip_id": f"{day}-u{index}",
                "trip_start_timestamp": base + pd.Timedelta(minutes=int(start_min)),
                "trip_end_timestamp": base + pd.Timedelta(minutes=int(start_min + rng.integers(10, 65))),
                "trip_seconds": int(rng.integers(600, 3900)),
                "trip_miles": float(rng.uniform(1, 16)),
                "pickup_centroid_latitude": plat,
                "pickup_centroid_longitude": plon,
                "dropoff_centroid_latitude": plat + rng.normal(0, 0.06),
                "dropoff_centroid_longitude": plon + rng.normal(0, 0.06),
                "pickup_community_area": index % 12,
                "dropoff_community_area": (index + 5) % 12,
                "pickup_census_tract": 3000 + index,
                "dropoff_census_tract": 4000 + index,
                "shared_trip_authorized": True,
                "shared_trip_match": False,
                "trips_pooled": 1,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    script = Path(__file__).with_name("run_weak_edge_pilot.py")
    with tempfile.TemporaryDirectory(prefix="weak-edge-smoke-") as raw_tmp:
        tmp = Path(raw_tmp)
        for day, seed in [("2026-01-13", 7), ("2026-01-14", 11)]:
            make_day(day, seed).to_csv(tmp / f"authorized_{day}.csv", index=False)
        output = tmp / "out"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "--input-glob",
                str(tmp / "authorized_*.csv"),
                "--output-dir",
                str(output),
                "--max-candidates-per-node",
                "10",
                "--neighbor-search-k",
                "48",
                "--max-iter",
                "60",
            ],
            check=True,
        )
        required = {
            "node_predictions.csv",
            "node_level_metrics.csv",
            "test_supported_calibration.csv",
            "scored_candidate_edges.csv.gz",
            "model_coefficients.csv",
            "model_card.json",
        }
        missing = sorted(name for name in required if not (output / name).is_file())
        if missing:
            raise AssertionError(f"Missing outputs: {missing}")
        metrics = pd.read_csv(output / "node_level_metrics.csv")
        assert {"prevalence", "transparent_rule", "weak_mil_ai"} <= set(metrics["model"])
        print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
