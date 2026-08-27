#!/usr/bin/env python3
"""Exact-enumeration audit and radius frontier for the conformal benchmark.

The controlled benchmark has twelve nodes per market and a complete candidate
graph.  There are only ``11!! = 10,395`` perfect matchings, so this audit does
not call a MILP solver: it enumerates every feasible matching, recomputes the
calibration regrets, and evaluates every downstream endpoint directly.  The
result uses the benchmark's declared score semantics end to end: each stored
float edge score is parsed from its decimal spelling before termwise rational
summation, and score-floor membership is an exact rational comparison with no
tolerance.  Integer same-SES counts are also compared exactly.  Floats are
used only for learned edge outputs and serialized summaries.

The script intentionally reconstructs the deterministic source/calibration/test split
from :class:`conformal_set_benchmark.Design`.  It fails if exact enumeration no
longer agrees with the benchmark's stored conformal radii or headline summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd

from conformal_set_benchmark import (
    BENCHMARK_DIR,
    Design,
    add_scores,
    exact_matching_score_sums,
    fit_scorers,
    generate_market,
    statistic_counts,
)
from conformal_matching import (  # noqa: E402
    exact_score_floor_from_radius,
    normalized_matching_regret,
    split_conformal_radius,
)


RESULTS_DIR = BENCHMARK_DIR / "results" / "conformal_matching"
GRID_RADII = tuple(float(value) / 20.0 for value in range(21))
TAU_AUDIT_TOLERANCE = 1e-12
HEADLINE_AUDIT_TOLERANCE = 1e-9


@dataclass
class FrontierAccumulator:
    """Sufficient statistics for one scorer-radius frontier point."""

    markets: int = 0
    retained: int = 0
    covered: int = 0
    admissible_matchings: int = 0
    lower_sum: float = 0.0
    upper_sum: float = 0.0
    width_sum: float = 0.0

    def update(
        self,
        *,
        retained: bool,
        covered: bool,
        admissible: int,
        lower: float,
        upper: float,
    ) -> None:
        self.markets += 1
        self.retained += int(retained)
        self.covered += int(covered)
        self.admissible_matchings += int(admissible)
        self.lower_sum += float(lower)
        self.upper_sum += float(upper)
        self.width_sum += float(upper - lower)


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
    """Return one row of complete-graph edge indices per perfect matching."""

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


def _validate_complete_graph_edge_order(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
) -> None:
    """Independently verify the positional edge-index convention."""

    node_ids = nodes["node_id"].astype(str).tolist()
    expected = [
        (node_ids[left], node_ids[right])
        for left in range(len(node_ids))
        for right in range(left + 1, len(node_ids))
    ]
    actual = list(zip(edges["u"].astype(str), edges["v"].astype(str)))
    if actual != expected:
        raise ValueError(
            "edge rows do not match the audit's complete-graph index convention"
        )


def _score_array_sha256(markets, scorer_names) -> str:
    """Hash every declared calibration/test edge score in stable order."""

    digest = hashlib.sha256()
    for _, edges, _ in markets:
        for row in edges.itertuples(index=False):
            edge_id = str(row.edge_id)
            for scorer_name in sorted(scorer_names):
                declared = str(float(getattr(row, f"score_{scorer_name}")))
                digest.update(
                    f"{edge_id}\t{scorer_name}\t{declared}\n".encode("utf-8")
                )
    return digest.hexdigest()


def _reconstruct_split(design: Design):
    seed_sequence = np.random.SeedSequence(design.seed)
    children = seed_sequence.spawn(
        design.source_markets + design.calibration_markets + design.test_markets
    )
    seeds = [int(child.generate_state(1)[0]) for child in children]
    offset = 0

    def markets(count: int, prefix: str, homophily: float):
        nonlocal offset
        generated = [
            generate_market(
                seeds[offset + index],
                market_id=f"{prefix}{index:03d}",
                n_pairs=design.pairs_per_market,
                homophily=homophily,
            )
            for index in range(count)
        ]
        offset += count
        return generated

    source = markets(design.source_markets, "source", design.source_homophily)
    calibration = markets(
        design.calibration_markets, "cal", design.target_homophily
    )
    test = markets(design.test_markets, "test", design.target_homophily)
    return source, calibration, test


def _true_matching_index(
    edges: pd.DataFrame,
    true_edge_ids: tuple[str, ...],
    matching_edge_rows: np.ndarray,
) -> int:
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


def _score_geometry(
    edges: pd.DataFrame,
    matching_edge_rows: np.ndarray,
    true_index: int,
    score_col: str,
) -> tuple[tuple[Fraction, ...], Fraction, Fraction, float]:
    score_sums = exact_matching_score_sums(
        edges[score_col].tolist(), matching_edge_rows
    )
    minimum = min(score_sums)
    maximum = max(score_sums)
    true_score = score_sums[true_index]
    regret = normalized_matching_regret(true_score, minimum, maximum)
    return score_sums, minimum, maximum, regret


def _frontier_points(calibrated_tau: float) -> list[tuple[str, float]]:
    points = [("grid", radius) for radius in GRID_RADII]
    if not any(abs(calibrated_tau - radius) <= 1e-15 for radius in GRID_RADII):
        points.append(("calibrated", float(calibrated_tau)))
    else:
        points = [
            ("grid+calibrated" if abs(calibrated_tau - radius) <= 1e-15 else kind, radius)
            for kind, radius in points
        ]
    return sorted(points, key=lambda item: (item[1], item[0]))


def _numeric_headline(
    *,
    scorer: str,
    test_markets: int,
    raw_coverage: float,
    raw_width: float,
    calibrated_row: dict,
    arbitrary_row: dict,
    point_mae: float,
    calibrated_tau: float,
) -> dict:
    return {
        "scorer": scorer,
        "test_markets": int(test_markets),
        "raw_coverage": raw_coverage,
        "raw_width": raw_width,
        "calibrated_matching_coverage": calibrated_row["matching_coverage"],
        "calibrated_statistic_coverage": calibrated_row["statistic_coverage"],
        "calibrated_width": calibrated_row["mean_width"],
        "arbitrary_matching_coverage": arbitrary_row["matching_coverage"],
        "arbitrary_statistic_coverage": arbitrary_row["statistic_coverage"],
        "arbitrary_width": arbitrary_row["mean_width"],
        "point_mae": point_mae,
        "calibrated_width_reduction": (
            0.0
            if raw_width == 0.0
            else 1.0 - calibrated_row["mean_width"] / raw_width
        ),
        "arbitrary_width_reduction": (
            0.0
            if raw_width == 0.0
            else 1.0 - arbitrary_row["mean_width"] / raw_width
        ),
        "calibrated_tau": calibrated_tau,
    }


def run(output_dir: Path, reference_json: Path) -> dict:
    design = Design()
    source, calibration, test = _reconstruct_split(design)
    scorers = fit_scorers(source)
    node_count = 2 * design.pairs_per_market
    matching_edge_rows = enumerate_matching_edge_rows(node_count)
    matchings_per_market = int(len(matching_edge_rows))
    calibration_scored = [
        (nodes, add_scores(edges, scorers), true_edge_ids)
        for nodes, edges, true_edge_ids in calibration
    ]
    test_scored = [
        (nodes, add_scores(edges, scorers), true_edge_ids)
        for nodes, edges, true_edge_ids in test
    ]

    calibration_regrets: dict[str, list[float]] = {name: [] for name in scorers}
    for nodes, scored, true_edge_ids in calibration_scored:
        _validate_complete_graph_edge_order(nodes, scored)
        true_index = _true_matching_index(scored, true_edge_ids, matching_edge_rows)
        for scorer in scorers:
            _, minimum, maximum, regret = _score_geometry(
                scored,
                matching_edge_rows,
                true_index,
                f"score_{scorer}",
            )
            if minimum > maximum:
                raise RuntimeError("enumerated score range is reversed")
            calibration_regrets[scorer].append(regret)

    radii = {
        scorer: split_conformal_radius(regrets, design.alpha)
        for scorer, regrets in calibration_regrets.items()
    }
    points = {
        scorer: _frontier_points(radius.tau) for scorer, radius in radii.items()
    }
    accumulators = {
        scorer: {
            (kind, radius): FrontierAccumulator() for kind, radius in points[scorer]
        }
        for scorer in scorers
    }
    raw_widths: list[float] = []
    raw_covers: list[bool] = []
    point_errors: dict[str, list[float]] = {name: [] for name in scorers}

    for nodes, scored, true_edge_ids in test_scored:
        _validate_complete_graph_edge_order(nodes, scored)
        true_index = _true_matching_index(scored, true_edge_ids, matching_edge_rows)
        counts = statistic_counts(scored, matching_edge_rows)
        pair_count = matching_edge_rows.shape[1]
        truth_count = int(counts[true_index])
        raw_lower_count = int(counts.min())
        raw_upper_count = int(counts.max())
        truth = truth_count / pair_count
        raw_lower = raw_lower_count / pair_count
        raw_upper = raw_upper_count / pair_count
        raw_widths.append(raw_upper - raw_lower)
        raw_covers.append(raw_lower_count <= truth_count <= raw_upper_count)

        for scorer in scorers:
            score_sums, minimum, maximum, _ = _score_geometry(
                scored,
                matching_edge_rows,
                true_index,
                f"score_{scorer}",
            )
            maximizing = tuple(
                index
                for index, score in enumerate(score_sums)
                if score == maximum
            )
            maximizing_counts = {int(counts[index]) for index in maximizing}
            if len(maximizing_counts) != 1:
                raise RuntimeError("the point comparator is ambiguous under a score tie")
            point_errors[scorer].append(
                abs(next(iter(maximizing_counts)) - truth_count) / pair_count
            )

            for kind, radius in points[scorer]:
                floor = exact_score_floor_from_radius(minimum, maximum, radius)
                admissible = tuple(
                    index
                    for index, score in enumerate(score_sums)
                    if score >= floor
                )
                admissible_count = len(admissible)
                if admissible_count == 0:
                    raise RuntimeError("a regret ball excluded every feasible matching")
                lower_count = min(int(counts[index]) for index in admissible)
                upper_count = max(int(counts[index]) for index in admissible)
                lower = lower_count / pair_count
                upper = upper_count / pair_count
                accumulators[scorer][(kind, radius)].update(
                    retained=score_sums[true_index] >= floor,
                    covered=lower_count <= truth_count <= upper_count,
                    admissible=admissible_count,
                    lower=lower,
                    upper=upper,
                )

    mean_raw_width = float(np.mean(raw_widths))
    mean_raw_coverage = float(np.mean(raw_covers))
    frontier_rows: list[dict] = []
    for scorer in sorted(scorers):
        for kind, radius in points[scorer]:
            accumulator = accumulators[scorer][(kind, radius)]
            mean_width = accumulator.width_sum / accumulator.markets
            frontier_rows.append(
                {
                    "scorer": scorer,
                    "radius_kind": kind,
                    "radius": radius,
                    "calibration_alpha": design.alpha if "calibrated" in kind else np.nan,
                    "test_markets": accumulator.markets,
                    "matchings_per_market": matchings_per_market,
                    "mean_admissible_matchings": (
                        accumulator.admissible_matchings / accumulator.markets
                    ),
                    "mean_admissible_fraction": (
                        accumulator.admissible_matchings
                        / (accumulator.markets * matchings_per_market)
                    ),
                    "matching_coverage": accumulator.retained / accumulator.markets,
                    "statistic_coverage": accumulator.covered / accumulator.markets,
                    "mean_lower": accumulator.lower_sum / accumulator.markets,
                    "mean_upper": accumulator.upper_sum / accumulator.markets,
                    "mean_width": mean_width,
                    "mean_raw_width": mean_raw_width,
                    "mean_width_reduction": (
                        0.0
                        if mean_raw_width == 0.0 or mean_width == mean_raw_width
                        else 1.0 - mean_width / mean_raw_width
                    ),
                }
            )
    frontier = pd.DataFrame(frontier_rows)

    computed_headlines: dict[str, dict] = {}
    for scorer in sorted(scorers):
        scorer_rows = frontier.loc[frontier["scorer"].eq(scorer)]
        calibrated_row = scorer_rows.loc[
            scorer_rows["radius_kind"].str.contains("calibrated")
        ].iloc[0].to_dict()
        arbitrary_row = scorer_rows.loc[
            scorer_rows["radius"].sub(design.arbitrary_tight_radius).abs().le(1e-15)
        ].iloc[0].to_dict()
        computed_headlines[scorer] = _numeric_headline(
            scorer=scorer,
            test_markets=design.test_markets,
            raw_coverage=mean_raw_coverage,
            raw_width=mean_raw_width,
            calibrated_row=calibrated_row,
            arbitrary_row=arbitrary_row,
            point_mae=float(np.mean(point_errors[scorer])),
            calibrated_tau=radii[scorer].tau,
        )

    reference_bytes = reference_json.read_bytes()
    reference = json.loads(reference_bytes)
    reference_radii = reference["radii"]
    reference_headlines = {row["scorer"]: row for row in reference["summary"]}
    computed_score_hashes = {
        "calibration_score_array_sha256": _score_array_sha256(
            calibration_scored, scorers
        ),
        "test_score_array_sha256": _score_array_sha256(test_scored, scorers),
    }
    reference_score_hashes = {
        key: reference["reproducibility"][key] for key in computed_score_hashes
    }
    score_hash_audit = {
        key: {
            "computed": value,
            "reference": reference_score_hashes[key],
            "passed": value == reference_score_hashes[key],
        }
        for key, value in computed_score_hashes.items()
    }
    tau_audit: dict[str, dict] = {}
    headline_audit: dict[str, dict] = {}
    all_passed = all(item["passed"] for item in score_hash_audit.values())
    for scorer in sorted(scorers):
        expected_tau = float(reference_radii[scorer]["tau"])
        tau_error = abs(radii[scorer].tau - expected_tau)
        tau_passed = tau_error <= TAU_AUDIT_TOLERANCE
        tau_audit[scorer] = {
            "enumerated": radii[scorer].tau,
            "reference": expected_tau,
            "absolute_error": tau_error,
            "passed": tau_passed,
        }

        computed = computed_headlines[scorer]
        expected = reference_headlines[scorer]
        numeric_fields = sorted(set(computed) - {"scorer"})
        errors = {
            field: abs(float(computed[field]) - float(expected[field]))
            for field in numeric_fields
        }
        max_error = max(errors.values(), default=0.0)
        headline_passed = max_error <= HEADLINE_AUDIT_TOLERANCE
        headline_audit[scorer] = {
            "max_absolute_error": max_error,
            "passed": headline_passed,
            "enumerated": computed,
            "reference": expected,
        }
        all_passed = all_passed and tau_passed and headline_passed

    output_dir.mkdir(parents=True, exist_ok=True)
    frontier_path = output_dir / "exact_conformal_frontier.csv"
    audit_path = output_dir / "exact_conformal_audit.json"
    frontier.to_csv(frontier_path, index=False, float_format="%.15g")
    audit = {
        "schema_version": 2,
        "design": asdict(design),
        "enumeration": {
            "nodes_per_market": node_count,
            "pairs_per_matching": design.pairs_per_market,
            "perfect_matchings_per_market": matchings_per_market,
            "calibration_market_scorer_audits": design.calibration_markets * len(scorers),
            "test_market_scorer_audits": design.test_markets * len(scorers),
        },
        "semantics": {
            "feasible_set": "all perfect matchings of each generated complete 12-node graph",
            "endpoint_method": "direct exhaustive enumeration; no optimization solver",
            "arithmetic": (
                "termwise decimal-rational edge-score sums and integer query counts; "
                "float only at learned-score input and serialization"
            ),
            "score_floor_membership": "exact Fraction comparison without tolerance",
            "edge_row_order": "validated independently against node-row order",
            "score_multiplicity": (
                "one per selected edge; exactly half the all-core incidence score"
            ),
            "matching_coverage": "the hidden matching satisfies the actual exact score floor",
            "statistic_coverage": "the hidden same-SES fraction lies between attainable extrema",
        },
        "calibrated_radii": {name: radius.to_dict() for name, radius in radii.items()},
        "frontier": {
            "file": frontier_path.name,
            "rows": len(frontier),
            "grid": list(GRID_RADII),
        },
        "verification": {
            "reference_file": reference_json.name,
            "reference_sha256": hashlib.sha256(reference_bytes).hexdigest(),
            "tau_absolute_tolerance": TAU_AUDIT_TOLERANCE,
            "headline_absolute_tolerance": HEADLINE_AUDIT_TOLERANCE,
            "score_arrays": score_hash_audit,
            "tau": tau_audit,
            "headline": headline_audit,
            "all_passed": all_passed,
        },
    }
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not all_passed:
        raise RuntimeError(f"exact audit failed; inspect {audit_path}")
    return audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--reference-json",
        type=Path,
        default=RESULTS_DIR / "conformal_matching_benchmark.json",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    audit = run(args.output_dir, args.reference_json)
    print(
        "exact audit passed:",
        audit["enumeration"]["perfect_matchings_per_market"],
        "perfect matchings per market;",
        audit["frontier"]["rows"],
        "frontier rows",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
