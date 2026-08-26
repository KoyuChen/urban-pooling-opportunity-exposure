#!/usr/bin/env python3
"""Known-truth benchmark for conformal matching-set calibration.

The benchmark separates three market families before any evaluation:

* source markets train an ordinary edge scorer with pair truth;
* calibration markets choose a split-conformal normalized-regret radius; and
* held-out test markets evaluate matching retention, downstream coverage, and
  width.

The source markets have stronger socioeconomic homophily than the target
markets.  A deliberately query-leaking diagnostic scorer includes the same-SES
edge contribution used by the downstream statistic.  It can therefore look
sharper under an illustrative tight score floor while excluding true
matchings.  Calibration is expected to enlarge that scorer's matching set.
All records are simulated and no result is evidence about Chicago.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


BENCHMARK_DIR = Path(__file__).resolve().parent
AI_PILOT_DIR = BENCHMARK_DIR.parent
BOUNDS_DIR = AI_PILOT_DIR / "bounds"
for path in (AI_PILOT_DIR, BOUNDS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from conformal_matching import (  # noqa: E402
    normalized_matching_regret,
    score_floor_from_radius,
    split_conformal_radius,
)
from structured_matching_bounds import solve_linear_endpoints  # noqa: E402


PRIMARY_FEATURES = ("route_similarity", "time_similarity", "duration_similarity")
QUERY_LEAKING_FEATURES = (*PRIMARY_FEATURES, "same_ses")


@dataclass(frozen=True)
class Design:
    seed: int = 271828
    pairs_per_market: int = 6
    source_markets: int = 40
    calibration_markets: int = 49
    test_markets: int = 120
    source_homophily: float = 0.95
    target_homophily: float = 0.55
    alpha: float = 0.10
    arbitrary_tight_radius: float = 0.05


def _edge_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((str(left), str(right))))


def generate_market(
    seed: int,
    *,
    market_id: str,
    n_pairs: int,
    homophily: float,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    """Generate a complete candidate graph with a hidden perfect matching."""

    rng = np.random.default_rng(seed)
    node_rows: list[dict] = []
    true_edges: list[tuple[str, str]] = []
    for pair_index in range(n_pairs):
        left_bin = int(rng.integers(0, 2))
        right_bin = left_bin if rng.random() < homophily else 1 - left_bin
        route_center = rng.normal(0.0, 1.0, size=3)
        time_center = float(rng.uniform(0.0, 4.0))
        duration_center = float(rng.lognormal(2.4, 0.18))
        pair_nodes: list[str] = []
        for member, ses_bin in enumerate((left_bin, right_bin)):
            node_id = f"{market_id}:p{pair_index:02d}:{member}"
            pair_nodes.append(node_id)
            # Deliberately noisy public-like features leave several plausible
            # alternatives; otherwise the maximum-score matching trivially
            # recovers every hidden pair and calibration has nothing to do.
            route = route_center + rng.normal(0.0, 0.95, size=3)
            node_rows.append(
                {
                    "node_id": node_id,
                    "ses_bin": ses_bin,
                    "route_0": route[0],
                    "route_1": route[1],
                    "route_2": route[2],
                    "start_time": time_center + rng.normal(0.0, 0.62),
                    "duration": duration_center * rng.lognormal(0.0, 0.24),
                    "true_pair": pair_index,
                }
            )
        true_edges.append(_edge_key(*pair_nodes))

    nodes = pd.DataFrame(node_rows)
    rows: list[dict] = []
    records = nodes.to_dict("records")
    truth = set(true_edges)
    for left_index in range(len(records)):
        left = records[left_index]
        left_route = np.array([left[f"route_{k}"] for k in range(3)])
        for right_index in range(left_index + 1, len(records)):
            right = records[right_index]
            right_route = np.array([right[f"route_{k}"] for k in range(3)])
            key = _edge_key(left["node_id"], right["node_id"])
            rows.append(
                {
                    "edge_id": f"{market_id}:e{left_index:02d}:{right_index:02d}",
                    "u": left["node_id"],
                    "v": right["node_id"],
                    "route_similarity": -float(np.linalg.norm(left_route - right_route)),
                    "time_similarity": -abs(float(left["start_time"] - right["start_time"])),
                    "duration_similarity": -abs(
                        math.log(float(left["duration"]) / float(right["duration"]))
                    ),
                    "same_ses": float(left["ses_bin"] == right["ses_bin"]),
                    "is_true": int(key in truth),
                }
            )
    edges = pd.DataFrame(rows)
    true_edge_ids = tuple(edges.loc[edges["is_true"].eq(1), "edge_id"].astype(str))
    if len(true_edge_ids) != n_pairs:
        raise RuntimeError("synthetic truth is not a perfect matching")
    return nodes[["node_id", "ses_bin"]], edges, true_edge_ids


def fit_scorers(markets: list[tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]]):
    frame = pd.concat([edges for _, edges, _ in markets], ignore_index=True)
    scorers = {}
    for name, features in {
        "target_free": PRIMARY_FEATURES,
        "query_leaking": QUERY_LEAKING_FEATURES,
    }.items():
        model = LogisticRegression(
            C=1.0,
            class_weight="balanced",
            max_iter=5_000,
            random_state=0,
        )
        model.fit(frame[list(features)], frame["is_true"])
        scorers[name] = (model, features)
    return scorers


def add_scores(
    edges: pd.DataFrame,
    scorers,
) -> pd.DataFrame:
    out = edges.copy()
    for name, (model, features) in scorers.items():
        out[f"score_{name}"] = model.decision_function(out[list(features)])
    return out


def score_geometry(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    true_edge_ids: tuple[str, ...],
    score_col: str,
) -> dict:
    score_edges = edges.assign(score_lower=edges[score_col], score_upper=edges[score_col])
    endpoints = solve_linear_endpoints(
        nodes,
        score_edges,
        lower_objective_col="score_lower",
        upper_objective_col="score_upper",
        backend="scipy",
        time_limit=None,
    )
    if endpoints.status not in {"OPTIMAL", "NUMERICALLY_OPTIMAL"}:
        raise RuntimeError(f"score endpoints unresolved: {endpoints.warning}")
    score_lookup = edges.set_index("edge_id")[score_col]
    true_score = float(score_lookup.loc[list(true_edge_ids)].sum())
    regret = normalized_matching_regret(true_score, endpoints.lower, endpoints.upper)
    return {
        "minimum_score": float(endpoints.lower),
        "maximum_score": float(endpoints.upper),
        "true_score": true_score,
        "true_regret": regret,
        "max_score_edges": tuple(endpoints.upper_solution.selected_edge_ids),
    }


def statistic_endpoints(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    score_col: str | None = None,
    score_floor: float | None = None,
) -> tuple[float, float]:
    prepared = edges.assign(stat_lower=edges["same_ses"], stat_upper=edges["same_ses"])
    result = solve_linear_endpoints(
        nodes,
        prepared,
        lower_objective_col="stat_lower",
        upper_objective_col="stat_upper",
        normalizer=len(nodes) / 2,
        score_col=score_col,
        score_floor=score_floor,
        backend="scipy",
        time_limit=None,
    )
    if result.status not in {"OPTIMAL", "NUMERICALLY_OPTIMAL"}:
        raise RuntimeError(f"statistic endpoints unresolved: {result.warning}")
    return float(result.lower), float(result.upper)


def _contains(lower: float, upper: float, truth: float) -> bool:
    return lower - 1e-12 <= truth <= upper + 1e-12


def evaluate_market(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    true_edge_ids: tuple[str, ...],
    *,
    scorer_name: str,
    tau: float,
    arbitrary_tau: float,
) -> dict:
    score_col = f"score_{scorer_name}"
    geometry = score_geometry(nodes, edges, true_edge_ids, score_col)
    raw_lower, raw_upper = statistic_endpoints(nodes, edges)
    true_lookup = edges.set_index("edge_id")["same_ses"]
    truth = float(true_lookup.loc[list(true_edge_ids)].mean())

    calibrated_floor = score_floor_from_radius(
        geometry["minimum_score"], geometry["maximum_score"], tau
    )
    calibrated_lower, calibrated_upper = statistic_endpoints(
        nodes,
        edges,
        score_col=score_col,
        score_floor=calibrated_floor,
    )
    arbitrary_floor = score_floor_from_radius(
        geometry["minimum_score"], geometry["maximum_score"], arbitrary_tau
    )
    arbitrary_lower, arbitrary_upper = statistic_endpoints(
        nodes,
        edges,
        score_col=score_col,
        score_floor=arbitrary_floor,
    )
    max_score_truth = float(true_lookup.loc[list(geometry["max_score_edges"])].mean())
    return {
        "scorer": scorer_name,
        "true_regret": geometry["true_regret"],
        "truth": truth,
        "raw_lower": raw_lower,
        "raw_upper": raw_upper,
        "raw_width": raw_upper - raw_lower,
        "raw_covers": _contains(raw_lower, raw_upper, truth),
        "calibrated_matching_retained": geometry["true_regret"] <= tau + 1e-12,
        "calibrated_lower": calibrated_lower,
        "calibrated_upper": calibrated_upper,
        "calibrated_width": calibrated_upper - calibrated_lower,
        "calibrated_covers": _contains(calibrated_lower, calibrated_upper, truth),
        "arbitrary_matching_retained": geometry["true_regret"] <= arbitrary_tau + 1e-12,
        "arbitrary_lower": arbitrary_lower,
        "arbitrary_upper": arbitrary_upper,
        "arbitrary_width": arbitrary_upper - arbitrary_lower,
        "arbitrary_covers": _contains(arbitrary_lower, arbitrary_upper, truth),
        "max_score_absolute_error": abs(max_score_truth - truth),
    }


def summarize(rows: pd.DataFrame, radii: dict) -> pd.DataFrame:
    summary = rows.groupby("scorer", as_index=False).agg(
        test_markets=("truth", "count"),
        raw_coverage=("raw_covers", "mean"),
        raw_width=("raw_width", "mean"),
        calibrated_matching_coverage=("calibrated_matching_retained", "mean"),
        calibrated_statistic_coverage=("calibrated_covers", "mean"),
        calibrated_width=("calibrated_width", "mean"),
        arbitrary_matching_coverage=("arbitrary_matching_retained", "mean"),
        arbitrary_statistic_coverage=("arbitrary_covers", "mean"),
        arbitrary_width=("arbitrary_width", "mean"),
        point_mae=("max_score_absolute_error", "mean"),
    )
    summary["calibrated_width_reduction"] = np.where(
        summary["raw_width"] > 0,
        1.0 - summary["calibrated_width"] / summary["raw_width"],
        0.0,
    )
    summary["arbitrary_width_reduction"] = np.where(
        summary["raw_width"] > 0,
        1.0 - summary["arbitrary_width"] / summary["raw_width"],
        0.0,
    )
    summary["calibrated_tau"] = summary["scorer"].map(
        {name: radius.tau for name, radius in radii.items()}
    )
    return summary


def write_report(summary: pd.DataFrame, radii: dict, design: Design, output: Path) -> None:
    display = summary.copy()
    percent = [
        "raw_coverage",
        "calibrated_matching_coverage",
        "calibrated_statistic_coverage",
        "calibrated_width_reduction",
        "arbitrary_matching_coverage",
        "arbitrary_statistic_coverage",
        "arbitrary_width_reduction",
    ]
    for column in percent:
        display[column] = display[column].map(lambda value: f"{value:.1%}")
    for column in ["raw_width", "calibrated_width", "arbitrary_width", "point_mae", "calibrated_tau"]:
        display[column] = display[column].map(lambda value: f"{value:.3f}")
    cells = display.astype(str)
    header = "| " + " | ".join(cells.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(cells.columns)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in cells.to_numpy().tolist()]
    markdown = "\n".join([header, separator, *body])
    radius_lines = "\n".join(
        f"- `{name}`: tau={radius.tau:.4f}, rank={radius.order_rank}/{radius.calibration_size}."
        for name, radius in radii.items()
    )
    output.write_text(
        f"""# Conformal matching-set benchmark

This fully synthetic benchmark trains on {design.source_markets} source markets,
calibrates on {design.calibration_markets} independent target-style markets,
and evaluates {design.test_markets} held-out markets. The requested matching-
set coverage is {1-design.alpha:.0%}. The arbitrary comparator retains only
matchings within normalized regret {design.arbitrary_tight_radius:.2f} without
calibration.

{radius_lines}

{markdown}

Both scorers are directly supervised by true edges in the disjoint source
markets. The target-free scorer uses route, time, and duration similarity. The
query-leaking diagnostic additionally sees same-SES equality, which is exactly
the edge contribution to the downstream statistic. The source generating
homophily probability is {design.source_homophily:.0%}, whereas the calibration
and test probability is {design.target_homophily:.0%}. The radius 0.05 is an
illustrative stress point, not a calibrated baseline. Results validate only
the finite-sample matching-set calibration implementation on this fixed split.
They do not validate weak supervision, privacy-count coupling, candidate
support, or exchangeability for Chicago.
""",
        encoding="utf-8",
    )


def run(design: Design, output_dir: Path) -> dict:
    seed_sequence = np.random.SeedSequence(design.seed)
    children = seed_sequence.spawn(
        design.source_markets + design.calibration_markets + design.test_markets
    )
    seeds = [int(child.generate_state(1)[0]) for child in children]
    offset = 0

    def markets(count: int, prefix: str, homophily: float):
        nonlocal offset
        generated = []
        for index in range(count):
            generated.append(
                generate_market(
                    seeds[offset + index],
                    market_id=f"{prefix}{index:03d}",
                    n_pairs=design.pairs_per_market,
                    homophily=homophily,
                )
            )
        offset += count
        return generated

    source = markets(design.source_markets, "source", design.source_homophily)
    calibration = markets(
        design.calibration_markets, "cal", design.target_homophily
    )
    test = markets(design.test_markets, "test", design.target_homophily)
    scorers = fit_scorers(source)
    calibration_scored = [
        (nodes, add_scores(edges, scorers), truth) for nodes, edges, truth in calibration
    ]
    test_scored = [
        (nodes, add_scores(edges, scorers), truth) for nodes, edges, truth in test
    ]

    radii = {}
    for scorer_name in scorers:
        regrets = [
            score_geometry(nodes, edges, truth, f"score_{scorer_name}")["true_regret"]
            for nodes, edges, truth in calibration_scored
        ]
        radii[scorer_name] = split_conformal_radius(regrets, design.alpha)

    rows: list[dict] = []
    for market_index, (nodes, edges, truth) in enumerate(test_scored):
        for scorer_name in scorers:
            row = evaluate_market(
                nodes,
                edges,
                truth,
                scorer_name=scorer_name,
                tau=radii[scorer_name].tau,
                arbitrary_tau=design.arbitrary_tight_radius,
            )
            row["market_index"] = market_index
            rows.append(row)
    instances = pd.DataFrame(rows)
    summary = summarize(instances, radii)

    output_dir.mkdir(parents=True, exist_ok=True)
    instances.to_csv(output_dir / "conformal_matching_instances.csv", index=False)
    summary.to_csv(output_dir / "conformal_matching_summary.csv", index=False)
    payload = {
        "design": asdict(design),
        "radii": {name: radius.to_dict() for name, radius in radii.items()},
        "models": {
            name: {
                "features": list(features),
                "coefficients": model.coef_.reshape(-1).tolist(),
                "intercept": float(model.intercept_[0]),
            }
            for name, (model, features) in scorers.items()
        },
        "summary": summary.to_dict("records"),
    }
    (output_dir / "conformal_matching_benchmark.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    write_report(summary, radii, design, output_dir / "CONFORMAL_RESULTS.md")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BENCHMARK_DIR / "results" / "conformal_matching",
    )
    parser.add_argument("--test-markets", type=int, default=Design.test_markets)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    design = Design(test_markets=args.test_markets)
    if min(design.source_markets, design.calibration_markets, design.test_markets) <= 0:
        raise ValueError("all market counts must be positive")
    payload = run(design, args.output_dir)
    print(pd.DataFrame(payload["summary"]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
