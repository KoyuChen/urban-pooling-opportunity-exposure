#!/usr/bin/env python3
"""Exact-enumeration audit and radius frontier for the conformal benchmark.

The controlled benchmark has twelve nodes per market and a complete candidate
graph.  There are only ``11!! = 10,395`` perfect matchings, so this audit does
not call a MILP solver: it enumerates every feasible matching, recomputes the
calibration regrets, and evaluates every downstream endpoint directly.  The
result is exact with respect to the generated candidate set and the stored
double-precision model scores (it is not a symbolic-arithmetic claim).

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
from pathlib import Path

import numpy as np
import pandas as pd

from conformal_set_benchmark import (
    BENCHMARK_DIR,
    Design,
    add_scores,
    fit_scorers,
    generate_market,
)
from conformal_matching import normalized_matching_regret, split_conformal_radius


RESULTS_DIR = BENCHMARK_DIR / "results" / "conformal_matching"
GRID_RADII = tuple(float(value) / 20.0 for value in range(21))
SCORE_TOLERANCE = 1e-12
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
) -> tuple[np.ndarray, float, float, float]:
    edge_scores = edges[score_col].to_numpy(dtype=float)
    score_sums = edge_scores[matching_edge_rows].sum(axis=1)
    minimum = float(score_sums.min())
    maximum = float(score_sums.max())
    true_score = float(score_sums[true_index])
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


def _contains(lower: float, upper: float, truth: float) -> bool:
    return lower - SCORE_TOLERANCE <= truth <= upper + SCORE_TOLERANCE


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

    calibration_regrets: dict[str, list[float]] = {name: [] for name in scorers}
    for nodes, edges, true_edge_ids in calibration:
        del nodes
        scored = add_scores(edges, scorers)
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

    for nodes, edges, true_edge_ids in test:
        del nodes
        scored = add_scores(edges, scorers)
        true_index = _true_matching_index(scored, true_edge_ids, matching_edge_rows)
        statistic = scored["same_ses"].to_numpy(dtype=float)[matching_edge_rows].mean(axis=1)
        truth = float(statistic[true_index])
        raw_lower = float(statistic.min())
        raw_upper = float(statistic.max())
        raw_widths.append(raw_upper - raw_lower)
        raw_covers.append(_contains(raw_lower, raw_upper, truth))

        for scorer in scorers:
            score_sums, minimum, maximum, true_regret = _score_geometry(
                scored,
                matching_edge_rows,
                true_index,
                f"score_{scorer}",
            )
            maximizing = np.flatnonzero(score_sums == maximum)
            maximizing_statistics = statistic[maximizing]
            if float(maximizing_statistics.max() - maximizing_statistics.min()) > SCORE_TOLERANCE:
                raise RuntimeError("the point comparator is ambiguous under a score tie")
            point_errors[scorer].append(abs(float(maximizing_statistics[0]) - truth))

            score_scale = max(1.0, abs(minimum), abs(maximum))
            for kind, radius in points[scorer]:
                floor = maximum - radius * (maximum - minimum)
                admissible = score_sums >= floor - SCORE_TOLERANCE * score_scale
                admissible_count = int(admissible.sum())
                if admissible_count == 0:
                    raise RuntimeError("a regret ball excluded every feasible matching")
                lower = float(statistic[admissible].min())
                upper = float(statistic[admissible].max())
                accumulators[scorer][(kind, radius)].update(
                    retained=true_regret <= radius + SCORE_TOLERANCE,
                    covered=_contains(lower, upper, truth),
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
                        if mean_raw_width == 0.0
                        or abs(mean_width - mean_raw_width) <= SCORE_TOLERANCE
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
    tau_audit: dict[str, dict] = {}
    headline_audit: dict[str, dict] = {}
    all_passed = True
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
        "schema_version": 1,
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
            "arithmetic": "exact combinatorial enumeration with IEEE-754 model scores",
            "matching_coverage": "the hidden matching lies in the normalized-regret ball",
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
