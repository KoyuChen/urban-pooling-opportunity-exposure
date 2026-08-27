#!/usr/bin/env python3
"""Run external relation-truth audits without downloading or committing data.

The executable has two deliberately distinct layers:

* UCI Krebsregister block 1 is a real, manually adjudicated boundary test.  Its
  positive relation is audited as supplied and is not forced into a matching.
  A separate truth-conditioned dyad reduction supports one score-free postal
  agreement frontier, conditional on UCI's already-blocked candidate graph.
* FEBRL4 is an external synthetic method-fit test with a complete one-to-one
  bipartite truth.  Two deterministic truth-conditioned markets use complete
  bipartite candidate graphs, coarsened public fields, no learned scorer, and
  a birth-decade agreement query.  Original/link-bearing IDs are excluded from
  candidate generation, scores, and the query.

No network operation is implemented.  UCI block 1 must already exist as an
official cached ZIP, and FEBRL4 must be bundled in ``recordlinkage==0.16``.
Only aggregate JSON/Markdown reports are written.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import recordlinkage
import recordlinkage.datasets as recordlinkage_datasets
import scipy
from recordlinkage.datasets import load_febrl4
from recordlinkage.datasets.external import get_data_home
from scipy.optimize import linear_sum_assignment
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


HERE = Path(__file__).resolve().parent
AI_PILOT_DIR = HERE.parent
BOUNDS_DIR = AI_PILOT_DIR / "bounds"
if str(BOUNDS_DIR) not in sys.path:
    sys.path.insert(0, str(BOUNDS_DIR))

from structured_matching_bounds import solve_linear_endpoints  # noqa: E402


AUDIT_DATE = "2026-08-27"
SEED = 260827
UCI_BLOCK = 1
FEBRL_MARKETS = (("small_exact", 6), ("medium_numerical", 20))
UCI_COLUMNS = (
    "cmp_firstname1",
    "cmp_firstname2",
    "cmp_lastname1",
    "cmp_lastname2",
    "cmp_sex",
    "cmp_birthday",
    "cmp_birthmonth",
    "cmp_birthyear",
    "cmp_zipcode",
    "is_match",
)
FEBRL_SCORE_FEATURES = (
    "given_soundex",
    "surname_soundex",
    "given_length_bin",
    "surname_length_bin",
    "suburb_initial",
    "address_initial",
)
FEBRL_QUERY_FEATURE = "birth_decade"
SPLIT_NAMES = ("source", "calibration", "test")


class BenchmarkError(RuntimeError):
    """Raised when an external benchmark violates its frozen contract."""


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[object, object] = {}
        self.size: dict[object, int] = {}

    def add(self, value: object) -> None:
        if value not in self.parent:
            self.parent[value] = value
            self.size[value] = 1

    def find(self, value: object) -> object:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: object, right: object) -> None:
        self.add(left)
        self.add(right)
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.size[root_left] < self.size[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        self.size[root_left] += self.size[root_right]

    def components(self) -> list[set[object]]:
        components: dict[object, set[object]] = {}
        for node in self.parent:
            components.setdefault(self.find(node), set()).add(node)
        return list(components.values())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _histogram(values: Iterable[int]) -> dict[str, int]:
    return {str(key): int(value) for key, value in sorted(Counter(values).items())}


def _component_arrays(
    left: np.ndarray, right: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    nodes, inverse = np.unique(np.concatenate((left, right)), return_inverse=True)
    edge_count = len(left)
    row = inverse[:edge_count]
    col = inverse[edge_count:]
    adjacency = coo_matrix(
        (
            np.ones(2 * edge_count, dtype=np.uint8),
            (np.concatenate((row, col)), np.concatenate((col, row))),
        ),
        shape=(len(nodes), len(nodes)),
    ).tocsr()
    component_count, labels = connected_components(adjacency, directed=False)
    if component_count <= 0:
        raise BenchmarkError("candidate graph unexpectedly has no component")
    return nodes, row, labels, np.bincount(labels, minlength=component_count)


def _uci_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise BenchmarkError(
            f"UCI block ZIP is absent: {path}. Fetch it separately from the official "
            "UCI dataset; this benchmark will not access the network."
        )
    frame = pd.read_csv(
        path,
        index_col=["id_1", "id_2"],
        na_values="?",
        compression="zip",
    )
    if frame.shape[1] != len(UCI_COLUMNS):
        raise BenchmarkError(
            f"UCI block schema drift: expected {len(UCI_COLUMNS)} columns, "
            f"found {frame.shape[1]}"
        )
    frame.columns = UCI_COLUMNS
    frame.index.names = ["id1", "id2"]
    if not frame["is_match"].isin((True, False)).all():
        raise BenchmarkError("UCI is_match contains a value outside TRUE/FALSE")
    return frame


def _positive_components(
    left: np.ndarray, right: np.ndarray, positive: np.ndarray
) -> tuple[list[set[object]], Counter]:
    union_find = _UnionFind()
    degree: Counter = Counter()
    for u, v in zip(left[positive], right[positive]):
        union_find.union(u, v)
        degree.update((u, v))
    return union_find.components(), degree


def _uci_component_split(
    component_nodes: Sequence[object], *, seed: int = SEED
) -> str:
    material = f"uci-block1-component-split-v1|{seed}|" + "|".join(
        sorted(str(node) for node in component_nodes)
    )
    bucket = int(hashlib.sha256(material.encode("utf-8")).hexdigest(), 16) % 10
    return "source" if bucket < 6 else ("calibration" if bucket < 8 else "test")


def audit_uci_block(path: Path) -> dict:
    frame = _uci_frame(path)
    left = frame.index.get_level_values("id1").to_numpy()
    right = frame.index.get_level_values("id2").to_numpy()
    positive = frame["is_match"].to_numpy(dtype=bool)

    canonical = pd.MultiIndex.from_arrays(
        (np.minimum(left, right), np.maximum(left, right))
    )
    candidate_nodes, candidate_row, candidate_labels, candidate_sizes = (
        _component_arrays(left, right)
    )
    positive_components, positive_degree = _positive_components(left, right, positive)
    positive_size_histogram = _histogram(len(nodes) for nodes in positive_components)
    positive_degree_histogram = _histogram(positive_degree.values())
    dyad_components = [nodes for nodes in positive_components if len(nodes) == 2]
    dyad_nodes = set().union(*dyad_components) if dyad_components else set()

    dyad_mask = np.fromiter(
        (u in dyad_nodes and v in dyad_nodes for u, v in zip(left, right)),
        dtype=bool,
        count=len(left),
    )
    query_missing_nodes: set[object] = set()
    for index in np.flatnonzero(positive & dyad_mask):
        if pd.isna(frame.iloc[index]["cmp_zipcode"]):
            query_missing_nodes.update((left[index], right[index]))
    eligible_nodes = dyad_nodes.difference(query_missing_nodes)
    eligible_mask = np.fromiter(
        (u in eligible_nodes and v in eligible_nodes for u, v in zip(left, right)),
        dtype=bool,
        count=len(left),
    )
    eligible_positions = np.flatnonzero(eligible_mask)
    eligible_left = left[eligible_mask]
    eligible_right = right[eligible_mask]
    eligible_positive = positive[eligible_mask]
    eligible_query = frame.iloc[eligible_positions]["cmp_zipcode"].to_numpy(dtype=float)
    if np.isnan(eligible_query).any():
        raise BenchmarkError(
            "eligible UCI dyad graph still contains missing postal comparisons"
        )

    core_nodes, core_row, core_labels, core_sizes = _component_arrays(
        eligible_left, eligible_right
    )
    core_component_count = len(core_sizes)
    core_edge_counts = np.bincount(core_labels[core_row], minlength=core_component_count)
    core_truth_counts = np.bincount(
        core_labels[core_row],
        weights=eligible_positive.astype(np.int64),
        minlength=core_component_count,
    ).astype(int)
    ambiguous = core_edge_counts > core_truth_counts

    split_rows = []
    for component in range(core_component_count):
        node_mask = core_labels == component
        split_rows.append(
            {
                "split": _uci_component_split(core_nodes[node_mask]),
                "nodes": int(core_sizes[component]),
                "edges": int(core_edge_counts[component]),
                "truth_edges": int(core_truth_counts[component]),
                "ambiguous": bool(ambiguous[component]),
            }
        )
    split_summary = {}
    for split in SPLIT_NAMES:
        rows = [row for row in split_rows if row["split"] == split]
        split_summary[split] = {
            "components": len(rows),
            "nodes": sum(row["nodes"] for row in rows),
            "edges": sum(row["edges"] for row in rows),
            "truth_edges": sum(row["truth_edges"] for row in rows),
            "ambiguous_components": sum(row["ambiguous"] for row in rows),
        }

    # Solver IDs are fresh sequential pseudonyms; source registry IDs never
    # enter the query objective and no witnesses are serialized.
    safe_node = {
        node: f"u{position:05d}" for position, node in enumerate(core_nodes.tolist())
    }
    node_frame = pd.DataFrame({"node_id": list(safe_node.values())})
    edge_frame = pd.DataFrame(
        {
            "edge_id": [f"ue{position:05d}" for position in range(len(eligible_left))],
            "u": [safe_node[node] for node in eligible_left],
            "v": [safe_node[node] for node in eligible_right],
            "postal_lower": eligible_query,
            "postal_upper": eligible_query,
        }
    )
    bounds = solve_linear_endpoints(
        node_frame,
        edge_frame,
        lower_objective_col="postal_lower",
        upper_objective_col="postal_upper",
        normalizer=len(eligible_nodes) // 2,
        backend="scipy",
        time_limit=60.0,
    )
    if bounds.lower is None or bounds.upper is None:
        raise BenchmarkError(f"UCI score-free frontier unresolved: {bounds.status}")
    truth_query = float(
        frame.iloc[np.flatnonzero(positive & eligible_mask)]["cmp_zipcode"].mean()
    )

    return {
        "role": "real adjudicated relation-topology boundary test",
        "source": {
            "dataset": "UCI Record Linkage Comparison Patterns",
            "dataset_id": 210,
            "doi": "10.24432/C51K6B",
            "block": UCI_BLOCK,
            "cached_zip_sha256": _sha256(path),
            "cached_zip_bytes": path.stat().st_size,
            "network_used_by_benchmark": False,
        },
        "candidate_graph": {
            "rows": len(frame),
            "unique_undirected_pairs": int(canonical.nunique()),
            "duplicate_undirected_pairs": int(len(canonical) - canonical.nunique()),
            "self_pairs": int(np.sum(left == right)),
            "nodes": len(candidate_nodes),
            "connected_components": len(candidate_sizes),
            "component_size_histogram": _histogram(candidate_sizes.tolist()),
            "largest_component_nodes": int(candidate_sizes.max()),
        },
        "adjudicated_positive_relation": {
            "positive_edges": int(positive.sum()),
            "positive_nodes": len(positive_degree),
            "node_degree_histogram": positive_degree_histogram,
            "nodes_with_degree_above_one": sum(
                count for degree, count in positive_degree_histogram.items() if int(degree) > 1
            ),
            "maximum_positive_degree": max(positive_degree.values()),
            "connected_components": len(positive_components),
            "component_size_histogram": positive_size_histogram,
            "largest_component_nodes": max(len(nodes) for nodes in positive_components),
            "is_matching": all(degree == 1 for degree in positive_degree.values()),
            "candidate_true_edge_eligibility": 1.0,
            "eligibility_scope": (
                "tautological within the supplied blocked pair table; UCI does not "
                "reveal true pairs omitted by its six blocking passes"
            ),
        },
        "truth_conditioned_dyad_reduction": {
            "construction_uses_truth": True,
            "two_record_positive_components": len(dyad_components),
            "dyads_dropped_for_missing_true_postal_comparison": len(
                query_missing_nodes
            )
            // 2,
            "retained_truth_dyads": int(eligible_positive.sum()),
            "retained_nodes": len(eligible_nodes),
            "retained_candidate_edges": len(eligible_left),
            "retained_negative_edges": int((~eligible_positive).sum()),
            "candidate_true_edge_eligibility": float(
                eligible_positive.sum() / (len(eligible_nodes) // 2)
            ),
            "candidate_components": core_component_count,
            "component_size_histogram": _histogram(core_sizes.tolist()),
            "largest_component_nodes": int(core_sizes.max()),
            "ambiguous_components": int(ambiguous.sum()),
            "nodes_in_ambiguous_components": int(core_sizes[ambiguous].sum()),
            "component_disjoint_split": split_summary,
            "split_warning": (
                "no record/edge overlap, but components are not asserted to be iid markets"
            ),
        },
        "coherent_aggregate_task": {
            "population": (
                "adjudicated two-record positive components in block 1 whose true "
                "edge has an observed postal-code comparison"
            ),
            "candidate_domain": (
                "all UCI-supplied candidate edges induced by the retained records"
            ),
            "query": "share of selected links with exact postal-code agreement",
            "score_restriction": None,
            "normalizer_truth_dyads": len(eligible_nodes) // 2,
            "truth": truth_query,
            "lower": bounds.lower,
            "upper": bounds.upper,
            "width": bounds.upper - bounds.lower,
            "covers_adjudicated_truth": bounds.lower <= truth_query <= bounds.upper,
            "truth_at_upper_endpoint": math.isclose(truth_query, bounds.upper),
            "solver_status": bounds.status,
            "numerically_optimal_not_exact_certificate": not bounds.certified,
        },
        "claim_boundary": [
            "The full adjudicated positive relation is a group/entity relation, not a matching.",
            "The dyad benchmark is truth-conditioned and cannot estimate the prevalence of dyads.",
            "Eligibility is conditional on UCI's supplied blocked graph; blocking recall is unobserved.",
            "Component splits prevent overlap but do not create natural exchangeable markets.",
            "The task validates a matching-only edge-additive frontier, not latent node attributes or Chicago transfer.",
        ],
    }


def _normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return "".join(character for character in str(value).lower() if character.isalnum())


def _soundex(value: object) -> str:
    text = "".join(character for character in _normalize_text(value) if character.isalpha())
    if not text:
        return "?"
    codes = {
        **dict.fromkeys("bfpv", "1"),
        **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"),
        **dict.fromkeys("l", "4"),
        **dict.fromkeys("mn", "5"),
        **dict.fromkeys("r", "6"),
    }
    result = [text[0]]
    prior = codes.get(text[0], "0")
    for character in text[1:]:
        code = codes.get(character, "0")
        if code != "0" and code != prior:
            result.append(code)
        prior = code
    return ("".join(result) + "000")[:4]


def coarsen_febrl_row(row: pd.Series) -> dict:
    """Apply the frozen analyst-created FEBRL observation operator."""

    given = _normalize_text(row.get("given_name"))
    surname = _normalize_text(row.get("surname"))
    suburb = _normalize_text(row.get("suburb"))
    address = _normalize_text(row.get("address_1"))
    birth = _normalize_text(row.get("date_of_birth"))
    birth_decade = (
        f"{birth[:3]}0s" if len(birth) >= 4 and birth[:4].isdigit() else "?"
    )
    return {
        "given_soundex": _soundex(given),
        "surname_soundex": _soundex(surname),
        "given_length_bin": min(len(given) // 3, 4),
        "surname_length_bin": min(len(surname) // 3, 4),
        "suburb_initial": suburb[:1] or "?",
        "address_initial": address[:1] or "?",
        "birth_decade": birth_decade,
    }


def _febrl_score(left: Mapping, right: Mapping) -> int:
    """Integer target-free compatibility score over public coarsened fields."""

    if FEBRL_QUERY_FEATURE in FEBRL_SCORE_FEATURES:
        raise BenchmarkError("query field leaked into the score feature allowlist")
    weights = (7, 7, 2, 2, 1, 1)
    return sum(
        weight * int(left[feature] == right[feature])
        for feature, weight in zip(FEBRL_SCORE_FEATURES, weights)
    )


def _febrl_query(left: Mapping, right: Mapping) -> int:
    value = left[FEBRL_QUERY_FEATURE]
    return int(value != "?" and value == right[FEBRL_QUERY_FEATURE])


def _exact_bipartite_frontier(
    query: np.ndarray, score: np.ndarray
) -> dict:
    pair_count = query.shape[0]
    if query.shape != (pair_count, pair_count) or score.shape != query.shape:
        raise BenchmarkError("exact frontier requires square query/score matrices")
    if pair_count > 8:
        raise BenchmarkError("exact enumeration is intentionally capped at eight pairs")
    query_sums: list[int] = []
    score_sums: list[int] = []
    for permutation in itertools.permutations(range(pair_count)):
        query_sums.append(sum(int(query[row, col]) for row, col in enumerate(permutation)))
        score_sums.append(sum(int(score[row, col]) for row, col in enumerate(permutation)))
    optimum = max(score_sums)
    optimum_queries = [
        query_sum
        for query_sum, score_sum in zip(query_sums, score_sums)
        if score_sum == optimum
    ]
    return {
        "enumerated_matchings": math.factorial(pair_count),
        "score_free_lower": min(query_sums) / pair_count,
        "score_free_upper": max(query_sums) / pair_count,
        "score_optimum": optimum,
        "score_optimal_matching_count": len(optimum_queries),
        "score_optimal_lower": min(optimum_queries) / pair_count,
        "score_optimal_upper": max(optimum_queries) / pair_count,
    }


def _febrl_market(
    data_left: pd.DataFrame,
    data_right: pd.DataFrame,
    links: pd.MultiIndex,
    selected_positions: Sequence[int],
    *,
    market_name: str,
    seed: int,
) -> dict:
    """Build one truth-conditioned market, then isolate truth from all inputs."""

    selected_links = [tuple(links[position]) for position in selected_positions]
    left_records = [
        (source_id, coarsen_febrl_row(data_left.loc[source_id]))
        for source_id, _ in selected_links
    ]
    right_records = [
        (source_id, coarsen_febrl_row(data_right.loc[source_id]))
        for _, source_id in selected_links
    ]
    pair_count = len(selected_links)
    rng = np.random.default_rng(seed)
    left_order = rng.permutation(pair_count)
    right_order = rng.permutation(pair_count)

    left_map: dict[object, str] = {}
    right_map: dict[object, str] = {}
    public_left: list[tuple[str, dict]] = []
    public_right: list[tuple[str, dict]] = []
    for public_position, source_position in enumerate(left_order):
        source_id, observation = left_records[int(source_position)]
        public_id = f"L{public_position:03d}"
        left_map[source_id] = public_id
        public_left.append((public_id, observation))
    for public_position, source_position in enumerate(right_order):
        source_id, observation = right_records[int(source_position)]
        public_id = f"R{public_position:03d}"
        right_map[source_id] = public_id
        public_right.append((public_id, observation))

    # Candidate, score, and query construction receives only public tables.
    # Hidden links are created separately and joined only for evaluation below.
    score = np.zeros((pair_count, pair_count), dtype=np.int16)
    query = np.zeros((pair_count, pair_count), dtype=np.int8)
    for left_position, (_, left_observation) in enumerate(public_left):
        for right_position, (_, right_observation) in enumerate(public_right):
            score[left_position, right_position] = _febrl_score(
                left_observation, right_observation
            )
            query[left_position, right_position] = _febrl_query(
                left_observation, right_observation
            )

    hidden_truth = {
        (left_map[source_left], right_map[source_right])
        for source_left, source_right in selected_links
    }
    if len(hidden_truth) != pair_count:
        raise BenchmarkError("FEBRL truth is not one-to-one in the selected market")
    left_position = {node: index for index, (node, _) in enumerate(public_left)}
    right_position = {node: index for index, (node, _) in enumerate(public_right)}
    truth_coordinates = [
        (left_position[left], right_position[right]) for left, right in hidden_truth
    ]
    truth_query_sum = sum(int(query[row, col]) for row, col in truth_coordinates)
    truth_score = sum(int(score[row, col]) for row, col in truth_coordinates)

    point_rows, point_cols = linear_sum_assignment(-score.astype(float))
    point_matching = {
        (public_left[row][0], public_right[col][0])
        for row, col in zip(point_rows, point_cols)
    }
    score_optimum = int(score[point_rows, point_cols].sum())
    point_query = float(query[point_rows, point_cols].sum() / pair_count)

    node_frame = pd.DataFrame(
        {"node_id": [node for node, _ in (*public_left, *public_right)]}
    )
    edge_rows = []
    for row, (left_node, _) in enumerate(public_left):
        for col, (right_node, _) in enumerate(public_right):
            edge_rows.append(
                {
                    "edge_id": f"{market_name}:e{row:03d}:{col:03d}",
                    "u": left_node,
                    "v": right_node,
                    "query_lower": int(query[row, col]),
                    "query_upper": int(query[row, col]),
                    "score": int(score[row, col]),
                }
            )
    edge_frame = pd.DataFrame(edge_rows)
    score_free = solve_linear_endpoints(
        node_frame,
        edge_frame,
        lower_objective_col="query_lower",
        upper_objective_col="query_upper",
        normalizer=pair_count,
        backend="scipy",
        time_limit=60.0,
    )
    score_optimal = solve_linear_endpoints(
        node_frame,
        edge_frame,
        lower_objective_col="query_lower",
        upper_objective_col="query_upper",
        normalizer=pair_count,
        score_col="score",
        score_floor=float(score_optimum),
        backend="scipy",
        time_limit=60.0,
    )
    if None in (
        score_free.lower,
        score_free.upper,
        score_optimal.lower,
        score_optimal.upper,
    ):
        raise BenchmarkError(f"FEBRL market {market_name} frontier was unresolved")

    exact = (
        _exact_bipartite_frontier(query, score) if pair_count <= 8 else None
    )
    if exact is not None:
        if not math.isclose(exact["score_free_lower"], score_free.lower):
            raise BenchmarkError("small exact/MILP lower endpoint disagreement")
        if not math.isclose(exact["score_free_upper"], score_free.upper):
            raise BenchmarkError("small exact/MILP upper endpoint disagreement")
        if not math.isclose(exact["score_optimal_lower"], score_optimal.lower):
            raise BenchmarkError("small exact/MILP score-optimal lower disagreement")
        if not math.isclose(exact["score_optimal_upper"], score_optimal.upper):
            raise BenchmarkError("small exact/MILP score-optimal upper disagreement")

    truth_query = truth_query_sum / pair_count
    return {
        "market": market_name,
        "truth_conditioned_construction": True,
        "pair_count": pair_count,
        "public_nodes": 2 * pair_count,
        "complete_bipartite_candidate_edges": pair_count * pair_count,
        "candidate_true_edge_eligibility": 1.0,
        "candidate_rule": "complete bipartite cross-product; no truth or feature filter",
        "score_features": list(FEBRL_SCORE_FEATURES),
        "query_feature": FEBRL_QUERY_FEATURE,
        "query_definition": (
            "share of selected links whose released, nonmissing birth decades "
            "agree; unknown is defined as non-agreement"
        ),
        "query_in_score": FEBRL_QUERY_FEATURE in FEBRL_SCORE_FEATURES,
        "source_ids_in_public_inputs": False,
        "truth": {
            "query": truth_query,
            "score": truth_score,
            "score_optimal": truth_score == score_optimum,
        },
        "point_max_score_matching": {
            "score": score_optimum,
            "true_edge_recovery": len(point_matching.intersection(hidden_truth))
            / pair_count,
            "query": point_query,
        },
        "score_free_frontier": {
            "lower": score_free.lower,
            "upper": score_free.upper,
            "width": score_free.upper - score_free.lower,
            "covers_truth": score_free.lower <= truth_query <= score_free.upper,
            "solver_status": score_free.status,
        },
        "uncalibrated_score_optimum_sensitivity": {
            "lower": score_optimal.lower,
            "upper": score_optimal.upper,
            "width": score_optimal.upper - score_optimal.lower,
            "covers_truth": score_optimal.lower <= truth_query <= score_optimal.upper,
            "truth_score_eligible": truth_score == score_optimum,
            "solver_status": score_optimal.status,
            "warning": "not a confidence set; score floor was not calibrated",
        },
        "exact_enumeration": exact,
    }


def audit_febrl4() -> dict:
    data_left, data_right, links = load_febrl4(return_links=True)
    dataset_directory = Path(recordlinkage_datasets.__file__).resolve().parent / "febrl"
    dataset_files = (
        dataset_directory / "dataset4a.csv",
        dataset_directory / "dataset4b.csv",
    )
    if not all(path.is_file() for path in dataset_files):
        raise BenchmarkError("recordlinkage==0.16 lacks the expected FEBRL4 files")
    left_truth = links.get_level_values(0)
    right_truth = links.get_level_values(1)
    left_degree = Counter(left_truth)
    right_degree = Counter(right_truth)
    identity_pattern = re.compile(r"^rec-(\d+)-(?:org|dup-0)$")
    directly_encoded = 0
    for left_id, right_id in links:
        left_match = identity_pattern.match(str(left_id))
        right_match = identity_pattern.match(str(right_id))
        if (
            left_match is not None
            and right_match is not None
            and left_match.group(1) == right_match.group(1)
        ):
            directly_encoded += 1

    if len(links) != 5000 or not all(value == 1 for value in left_degree.values()):
        raise BenchmarkError("FEBRL4 left-side truth is not the documented matching")
    if not all(value == 1 for value in right_degree.values()):
        raise BenchmarkError("FEBRL4 right-side truth is not one-to-one")

    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(links))
    market_results = []
    cursor = 0
    selected_source_ids: set[object] = set()
    for market_index, (market_name, pair_count) in enumerate(FEBRL_MARKETS):
        positions = order[cursor : cursor + pair_count]
        cursor += pair_count
        selected_links = [tuple(links[int(position)]) for position in positions]
        flat_ids = {source_id for pair in selected_links for source_id in pair}
        if selected_source_ids.intersection(flat_ids):
            raise BenchmarkError("FEBRL markets overlap in source records")
        selected_source_ids.update(flat_ids)
        market_results.append(
            _febrl_market(
                data_left,
                data_right,
                links,
                positions,
                market_name=market_name,
                seed=SEED + 100 + market_index,
            )
        )

    return {
        "role": "external synthetic complete-matching method-fit benchmark",
        "source": {
            "dataset": "FEBRL4 bundled with Python Record Linkage Toolkit",
            "recordlinkage_version": recordlinkage.__version__,
            "bundled_file_sha256": {
                path.name: _sha256(path) for path in dataset_files
            },
            "network_used_by_benchmark": False,
        },
        "topology": {
            "left_records": len(data_left),
            "right_records": len(data_right),
            "true_links": len(links),
            "unique_left_truth_nodes": len(left_degree),
            "unique_right_truth_nodes": len(right_degree),
            "maximum_left_truth_degree": max(left_degree.values()),
            "maximum_right_truth_degree": max(right_degree.values()),
            "is_complete_one_to_one_bipartite_matching": (
                len(left_degree) == len(data_left)
                and len(right_degree) == len(data_right)
                and all(value == 1 for value in left_degree.values())
                and all(value == 1 for value in right_degree.values())
            ),
        },
        "leakage_audit": {
            "truth_links_whose_source_ids_directly_encode_partner_number": directly_encoded,
            "source_ids_are_prohibited_from_public_inputs": True,
            "public_side_ids_are_independently_permuted": True,
            "soc_sec_id_released": False,
            "candidate_uses_truth": False,
            "score_uses_truth": False,
            "query_uses_truth": False,
            "market_membership_uses_truth": True,
        },
        "analyst_created_observation_operator": {
            "name": "febrl4_coarsened_v1",
            "fields": [*FEBRL_SCORE_FEATURES, FEBRL_QUERY_FEATURE],
            "description": (
                "Soundex names, capped three-character length bins, suburb/address "
                "initials, and birth decade; raw names, addresses, postcode, state, "
                "date, social-security field, and source IDs are not model inputs"
            ),
        },
        "markets_are_disjoint": True,
        "markets": market_results,
        "claim_boundary": [
            "FEBRL4 is synthetic and validates method fit, not real-world external validity.",
            "Market membership is truth-conditioned and is not an iid sampling design.",
            "The score-optimum restriction is an uncalibrated sensitivity analysis.",
            "The score-free frontier is the primary benchmark result.",
        ],
    }


def _format_float(value: float) -> str:
    return f"{value:.6f}"


def render_report(result: dict) -> str:
    uci = result["uci_krebsregister_block_1"]
    relation = uci["adjudicated_positive_relation"]
    dyad = uci["truth_conditioned_dyad_reduction"]
    task = uci["coherent_aggregate_task"]
    febrl = result["febrl4"]
    market_lines = []
    for market in febrl["markets"]:
        frontier = market["score_free_frontier"]
        sensitivity = market["uncalibrated_score_optimum_sensitivity"]
        exact = "yes" if market["exact_enumeration"] is not None else "no"
        market_lines.append(
            "| {name} | {pairs} | {edges} | {truth} | [{low}, {high}] | "
            "[{slow}, {shigh}] | {recovery} | {exact} |".format(
                name=market["market"],
                pairs=market["pair_count"],
                edges=market["complete_bipartite_candidate_edges"],
                truth=_format_float(market["truth"]["query"]),
                low=_format_float(frontier["lower"]),
                high=_format_float(frontier["upper"]),
                slow=_format_float(sensitivity["lower"]),
                shigh=_format_float(sensitivity["upper"]),
                recovery=_format_float(
                    market["point_max_score_matching"]["true_edge_recovery"]
                ),
                exact=exact,
            )
        )
    return f"""# External relation-truth benchmark result

Generated deterministically on {result['audit_date']}. No source records,
registry IDs, FEBRL IDs, pair labels, or endpoint witnesses are stored here.
The observed end-to-end runtime was {result['runtime_seconds']['total']:.3f}
seconds ({result['runtime_seconds']['uci']:.3f} UCI,
{result['runtime_seconds']['febrl4']:.3f} FEBRL4) in the recorded environment.

## UCI Krebsregister block 1: real adjudicated boundary test

- Input hash: `{uci['source']['cached_zip_sha256']}` ({uci['source']['cached_zip_bytes']:,} bytes).
- Candidate table: {uci['candidate_graph']['rows']:,} unique pairs over
  {uci['candidate_graph']['nodes']:,} records; {uci['candidate_graph']['connected_components']:,}
  components, including one {uci['candidate_graph']['largest_component_nodes']:,}-record component.
- Adjudicated positives: {relation['positive_edges']:,} edges over
  {relation['positive_nodes']:,} records. The relation is **not a matching**:
  {relation['nodes_with_degree_above_one']:,} records have positive degree above one,
  maximum degree is {relation['maximum_positive_degree']}, and positive components
  reach {relation['largest_component_nodes']} records.
- Conditional eligibility is {relation['candidate_true_edge_eligibility']:.1%} only because labels
  are attached to rows already selected by UCI's blocking. This says nothing
  about true pairs omitted before release.

The matching reduction is explicitly truth-conditioned. It starts from
{dyad['two_record_positive_components']:,} two-record positive components,
drops {dyad['dyads_dropped_for_missing_true_postal_comparison']} whose true edge
lacks the predeclared query value, and retains {dyad['retained_truth_dyads']:,}
truth dyads plus {dyad['retained_negative_edges']:,} negative alternative edges.
The induced candidate graph has {dyad['ambiguous_components']:,} ambiguous
components; its deterministic source/calibration/test partition has no record
or edge overlap, but those components are not claimed iid.

The coherent matching-only query is the share of selected links with exact
postal-code agreement. The score-free numerical frontier is
**[{_format_float(task['lower'])}, {_format_float(task['upper'])}]**; adjudicated
truth is **{_format_float(task['truth'])}** and lies at the upper endpoint.
`{task['solver_status']}` is a numerical HiGHS result, not an exact certificate.

## FEBRL4: external synthetic positive method-fit test

FEBRL4 has {febrl['topology']['left_records']:,} originals,
{febrl['topology']['right_records']:,} duplicates, and a complete one-to-one
truth. All {febrl['leakage_audit']['truth_links_whose_source_ids_directly_encode_partner_number']:,}
source ID pairs directly encode their partner number, so source IDs and returned
links are isolated before public candidate, score, or query construction.
Market membership is truth-conditioned and disclosed.

- `dataset4a.csv` SHA-256: `{febrl['source']['bundled_file_sha256']['dataset4a.csv']}`
- `dataset4b.csv` SHA-256: `{febrl['source']['bundled_file_sha256']['dataset4b.csv']}`

| Market | True pairs | Complete candidate edges | True same-known-decade share | Score-free frontier | Uncalibrated score-optimum frontier | Point true-edge recovery | Exhaustive oracle |
|---|---:|---:|---:|---:|---:|---:|:---:|
{chr(10).join(market_lines)}

The score uses only coarsened Soundex/length/initial fields and excludes the
birth-decade query. The score-optimum column is a sensitivity analysis, not a
confidence set. The six-pair result exhausts all 720 bipartite matchings and
agrees with the numerical solver; the 20-pair result is numerical.

## Claim boundary

- UCI validates real adjudicated relation topology and a conditional dyad
  frontier; it does not validate UCI blocking recall or independent markets.
- FEBRL4 validates a clean complete-matching path, but it is synthetic and its
  two markets are constructed using truth.
- Neither benchmark calibrates a learned restriction, validates latent node
  attributes, or licenses transfer to Chicago.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    default_uci = Path(get_data_home()) / "krebsregister" / "block_1.zip"
    parser.add_argument("--uci-block-zip", type=Path, default=default_uci)
    parser.add_argument(
        "--output-json", type=Path, default=HERE / "results" / "benchmark_results.json"
    )
    parser.add_argument(
        "--output-report", type=Path, default=HERE / "results" / "BENCHMARK_REPORT.md"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output_json.exists() or args.output_report.exists():
        raise BenchmarkError("refusing to overwrite an existing benchmark result")
    total_start = time.perf_counter()
    uci_start = time.perf_counter()
    uci_result = audit_uci_block(args.uci_block_zip)
    uci_seconds = time.perf_counter() - uci_start
    febrl_start = time.perf_counter()
    febrl_result = audit_febrl4()
    febrl_seconds = time.perf_counter() - febrl_start
    total_seconds = time.perf_counter() - total_start
    result = {
        "schema": "external_relation_truth_benchmark_v1",
        "audit_date": AUDIT_DATE,
        "seed": SEED,
        "reproduction_command": (
            "python code/ai_pilot/external_benchmarks/"
            "run_external_relation_truth_benchmark.py --uci-block-zip "
            "/secure/uci_rlcp/block_1.zip"
        ),
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "recordlinkage": recordlinkage.__version__,
        },
        "runtime_seconds": {
            "uci": round(uci_seconds, 6),
            "febrl4": round(febrl_seconds, 6),
            "total": round(total_seconds, 6),
        },
        "uci_krebsregister_block_1": uci_result,
        "febrl4": febrl_result,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.output_report.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"json": str(args.output_json), "report": str(args.output_report)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
