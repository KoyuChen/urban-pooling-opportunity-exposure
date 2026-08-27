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
All score-set operations enumerate the 10,395 perfect matchings and use exact
termwise decimal-rational scorer values.  Floats appear only in learned edge
outputs and serialized summaries, never in score-floor membership.  All
records are simulated and no result is evidence about Chicago.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression


BENCHMARK_DIR = Path(__file__).resolve().parent
AI_PILOT_DIR = BENCHMARK_DIR.parent
BOUNDS_DIR = AI_PILOT_DIR / "bounds"
for path in (AI_PILOT_DIR, BOUNDS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from conformal_matching import (  # noqa: E402
    exact_additive_score,
    exact_score_floor_from_radius,
    normalized_matching_regret,
    split_conformal_radius,
)


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


def _perfect_matching_pairs(remaining: tuple[int, ...]):
    """Yield all perfect matchings of ``remaining`` exactly once."""

    if not remaining:
        yield ()
        return
    first = remaining[0]
    for partner_position in range(1, len(remaining)):
        partner = remaining[partner_position]
        rest = remaining[1:partner_position] + remaining[partner_position + 1 :]
        for suffix in _perfect_matching_pairs(rest):
            yield ((first, partner),) + suffix


def enumerate_matching_edge_rows(node_count: int) -> np.ndarray:
    """Return complete-graph edge indices for every perfect matching."""

    if node_count <= 0 or node_count % 2:
        raise ValueError("node_count must be a positive even integer")
    edge_index: dict[tuple[int, int], int] = {}
    cursor = 0
    for left in range(node_count):
        for right in range(left + 1, node_count):
            edge_index[(left, right)] = cursor
            cursor += 1
    rows = [
        [edge_index[(min(left, right), max(left, right))] for left, right in matching]
        for matching in _perfect_matching_pairs(tuple(range(node_count)))
    ]
    result = np.asarray(rows, dtype=np.int16)
    expected = math.prod(range(1, node_count, 2))
    if result.shape != (expected, node_count // 2):
        raise RuntimeError("perfect-matching enumeration has the wrong shape")
    canonical = {tuple(sorted(int(edge) for edge in row)) for row in result}
    if len(canonical) != expected:
        raise RuntimeError("perfect-matching enumeration contains duplicates")
    return result


def validate_complete_graph_edge_order(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
) -> None:
    """Reject a row order that disagrees with the enumerator's edge indices."""

    node_ids = nodes["node_id"].astype(str).tolist()
    expected = [
        (node_ids[left], node_ids[right])
        for left in range(len(node_ids))
        for right in range(left + 1, len(node_ids))
    ]
    actual = list(zip(edges["u"].astype(str), edges["v"].astype(str)))
    if actual != expected:
        raise ValueError(
            "edge rows must follow the node-row lexicographic complete-graph order"
        )


def true_matching_index(
    edges: pd.DataFrame,
    true_edge_ids: tuple[str, ...],
    matching_edge_rows: np.ndarray,
) -> int:
    """Locate the hidden matching in a complete-graph enumeration."""

    edge_position = {
        str(edge_id): position
        for position, edge_id in enumerate(edges["edge_id"].astype(str))
    }
    target = tuple(sorted(edge_position[str(edge_id)] for edge_id in true_edge_ids))
    matches = np.flatnonzero(
        np.all(np.sort(matching_edge_rows, axis=1) == np.asarray(target), axis=1)
    )
    if len(matches) != 1:
        raise RuntimeError("hidden truth did not identify one enumerated matching")
    return int(matches[0])


def exact_matching_score_sums(
    edge_scores: list | tuple | np.ndarray | pd.Series,
    matching_edge_rows: np.ndarray,
) -> tuple[Fraction, ...]:
    """Parse each score's decimal spelling, then sum each matching exactly."""

    declared = tuple(exact_additive_score((value,)) for value in edge_scores)
    return tuple(
        sum((declared[int(index)] for index in row), Fraction(0))
        for row in matching_edge_rows
    )


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
    matching_edge_rows: np.ndarray | None = None,
) -> dict:
    """Return the exact score geometry of one complete-graph market."""

    validate_complete_graph_edge_order(nodes, edges)
    if matching_edge_rows is None:
        matching_edge_rows = enumerate_matching_edge_rows(len(nodes))
    true_index = true_matching_index(edges, true_edge_ids, matching_edge_rows)
    score_sums = exact_matching_score_sums(
        edges[score_col].tolist(), matching_edge_rows
    )
    minimum_score_exact = min(score_sums)
    maximum_score_exact = max(score_sums)
    true_score_exact = score_sums[true_index]
    regret = normalized_matching_regret(
        true_score_exact,
        minimum_score_exact,
        maximum_score_exact,
    )
    maximizing_indices = tuple(
        index
        for index, score in enumerate(score_sums)
        if score == maximum_score_exact
    )
    return {
        "minimum_score": minimum_score_exact,
        "maximum_score": maximum_score_exact,
        "true_score": true_score_exact,
        "true_regret": regret,
        "true_index": true_index,
        "score_sums": score_sums,
        "maximizing_indices": maximizing_indices,
    }


def statistic_counts(
    edges: pd.DataFrame,
    matching_edge_rows: np.ndarray,
) -> np.ndarray:
    """Return exact integer same-SES counts for every matching."""

    contributions = pd.to_numeric(edges["same_ses"], errors="raise").to_numpy()
    if not np.isin(contributions, [0, 1]).all():
        raise ValueError("same_ses must contain only exact 0/1 values")
    return contributions.astype(np.int16)[matching_edge_rows].sum(axis=1)


def exact_restricted_query(
    score_sums: tuple[Fraction, ...],
    query_counts: np.ndarray,
    score_floor: Fraction,
    true_index: int,
) -> dict:
    """Evaluate one score halfspace with no numeric membership tolerance."""

    admissible = tuple(
        index for index, score in enumerate(score_sums) if score >= score_floor
    )
    if not admissible:
        raise RuntimeError("an exact regret ball excluded every feasible matching")
    lower_count = int(min(query_counts[index] for index in admissible))
    upper_count = int(max(query_counts[index] for index in admissible))
    true_count = int(query_counts[true_index])
    return {
        "matching_retained": score_sums[true_index] >= score_floor,
        "lower_count": lower_count,
        "upper_count": upper_count,
        "query_covered": lower_count <= true_count <= upper_count,
        "admissible_count": len(admissible),
    }


def evaluate_market(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    true_edge_ids: tuple[str, ...],
    *,
    scorer_name: str,
    tau: float,
    arbitrary_tau: float,
    matching_edge_rows: np.ndarray | None = None,
) -> dict:
    if matching_edge_rows is None:
        matching_edge_rows = enumerate_matching_edge_rows(len(nodes))
    score_col = f"score_{scorer_name}"
    geometry = score_geometry(
        nodes,
        edges,
        true_edge_ids,
        score_col,
        matching_edge_rows,
    )
    counts = statistic_counts(edges, matching_edge_rows)
    pair_count = matching_edge_rows.shape[1]
    true_count = int(counts[geometry["true_index"]])
    raw_lower_count = int(counts.min())
    raw_upper_count = int(counts.max())

    calibrated_floor = exact_score_floor_from_radius(
        geometry["minimum_score"], geometry["maximum_score"], tau
    )
    calibrated = exact_restricted_query(
        geometry["score_sums"],
        counts,
        calibrated_floor,
        geometry["true_index"],
    )
    arbitrary_floor = exact_score_floor_from_radius(
        geometry["minimum_score"], geometry["maximum_score"], arbitrary_tau
    )
    arbitrary = exact_restricted_query(
        geometry["score_sums"],
        counts,
        arbitrary_floor,
        geometry["true_index"],
    )
    maximizing_counts = {
        int(counts[index]) for index in geometry["maximizing_indices"]
    }
    if len(maximizing_counts) != 1:
        raise RuntimeError("the point comparator is ambiguous under an exact score tie")
    max_score_count = next(iter(maximizing_counts))

    truth = true_count / pair_count
    raw_lower = raw_lower_count / pair_count
    raw_upper = raw_upper_count / pair_count
    calibrated_lower = calibrated["lower_count"] / pair_count
    calibrated_upper = calibrated["upper_count"] / pair_count
    arbitrary_lower = arbitrary["lower_count"] / pair_count
    arbitrary_upper = arbitrary["upper_count"] / pair_count
    return {
        "scorer": scorer_name,
        "true_regret": geometry["true_regret"],
        "truth": truth,
        "raw_lower": raw_lower,
        "raw_upper": raw_upper,
        "raw_width": raw_upper - raw_lower,
        "raw_covers": raw_lower_count <= true_count <= raw_upper_count,
        "calibrated_matching_retained": calibrated["matching_retained"],
        "calibrated_lower": calibrated_lower,
        "calibrated_upper": calibrated_upper,
        "calibrated_width": calibrated_upper - calibrated_lower,
        "calibrated_covers": calibrated["query_covered"],
        "arbitrary_matching_retained": arbitrary["matching_retained"],
        "arbitrary_lower": arbitrary_lower,
        "arbitrary_upper": arbitrary_upper,
        "arbitrary_width": arbitrary_upper - arbitrary_lower,
        "arbitrary_covers": arbitrary["query_covered"],
        "max_score_absolute_error": abs(max_score_count - true_count) / pair_count,
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
    numeric_columns = [
        "raw_width",
        "calibrated_width",
        "arbitrary_width",
        "point_mae",
        "calibrated_tau",
    ]
    for column in numeric_columns:
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
Every matching score parses each float edge score through its shortest decimal
spelling before termwise Fraction summation; exact score floors determine
membership without a tolerance. The benchmark counts each selected edge once,
which differs from the paper's all-core incidence score by a constant factor of
two and therefore leaves normalized regrets and admissible sets unchanged.
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
    matching_edge_rows = enumerate_matching_edge_rows(2 * design.pairs_per_market)

    radii = {}
    for scorer_name in scorers:
        regrets = [
            score_geometry(
                nodes,
                edges,
                truth,
                f"score_{scorer_name}",
                matching_edge_rows,
            )["true_regret"]
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
                matching_edge_rows=matching_edge_rows,
            )
            row["market_index"] = market_index
            rows.append(row)
    instances = pd.DataFrame(rows)
    summary = summarize(instances, radii)

    def score_array_sha256(markets) -> str:
        digest = hashlib.sha256()
        for _, edges, _ in markets:
            for row in edges.itertuples(index=False):
                edge_id = str(row.edge_id)
                for scorer_name in sorted(scorers):
                    declared = str(float(getattr(row, f"score_{scorer_name}")))
                    digest.update(
                        f"{edge_id}\t{scorer_name}\t{declared}\n".encode("utf-8")
                    )
        return digest.hexdigest()

    output_dir.mkdir(parents=True, exist_ok=True)
    instances.to_csv(output_dir / "conformal_matching_instances.csv", index=False)
    summary.to_csv(output_dir / "conformal_matching_summary.csv", index=False)
    payload = {
        "schema_version": 2,
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
        "reproducibility": {
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
            "scikit_learn_version": sklearn.__version__,
            "calibration_score_array_sha256": score_array_sha256(calibration_scored),
            "test_score_array_sha256": score_array_sha256(test_scored),
        },
        "score_semantics": {
            "matching_domain": (
                f"all {len(matching_edge_rows):,} perfect matchings of each "
                f"complete {2 * design.pairs_per_market}-node graph"
            ),
            "rationalization": (
                "each float edge score is parsed from its shortest decimal spelling "
                "before termwise Fraction summation"
            ),
            "floor_membership": "exact Fraction comparison without tolerance",
            "edge_row_order": (
                "validated node-row lexicographic complete-graph order"
            ),
            "score_multiplicity": (
                "one per selected edge; the all-core paper incidence score is exactly "
                "twice this value and induces the same normalized-regret set"
            ),
        },
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
