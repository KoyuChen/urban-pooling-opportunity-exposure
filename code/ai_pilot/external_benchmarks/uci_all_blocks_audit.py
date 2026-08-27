#!/usr/bin/env python3
"""Deterministic, privacy-safe audit of all ten UCI Krebsregister blocks.

The UCI labels describe an entity relation, not a one-to-one matching.  This
module therefore keeps two objects separate:

* an unconditional audit of the complete released candidate/positive
  topology; and
* an explicitly truth-conditioned matching sensitivity analysis restricted
  to global two-record positive components.

Only aggregate counts, hashes, endpoint values, and witness-replay summaries
are returned. Registry identifiers, source rows, truth edges, and raw endpoint
edge lists are never serialized; a witness-derived digest is disclosed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import queue
import sys
import time
import zipfile
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import scipy
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

try:
    import rustworkx as rx
except ModuleNotFoundError:  # pragma: no cover - topology-only lean CI
    rx = None


HERE = Path(__file__).resolve().parent
DEFAULT_METADATA = HERE / "fixtures" / "uci_rlcp_metadata.json"
AUDIT_DATE = "2026-08-27"
BLOCK_NUMBERS = tuple(range(1, 11))
RAW_COLUMNS = (
    "id_1",
    "id_2",
    "cmp_fname_c1",
    "cmp_fname_c2",
    "cmp_lname_c1",
    "cmp_lname_c2",
    "cmp_sex",
    "cmp_bd",
    "cmp_bm",
    "cmp_by",
    "cmp_plz",
    "is_match",
)
CONTINUOUS_COLUMNS = (
    "cmp_fname_c1",
    "cmp_fname_c2",
    "cmp_lname_c1",
    "cmp_lname_c2",
)
BINARY_COLUMNS = ("cmp_sex", "cmp_bd", "cmp_bm", "cmp_by", "cmp_plz")
MISSINGNESS_COLUMNS = (*CONTINUOUS_COLUMNS, *BINARY_COLUMNS)
UINT32_MAX = np.iinfo(np.uint32).max


class UciAuditError(RuntimeError):
    """Raised when a cached UCI snapshot violates the frozen audit contract."""


@dataclass(frozen=True)
class UciData:
    """In-memory arrays used by the audit; never directly serialized."""

    pair_code: np.ndarray
    positive: np.ndarray
    postal: np.ndarray
    block: np.ndarray
    reversed_orientation: np.ndarray
    block_nodes: tuple[np.ndarray, ...]
    per_block: tuple[dict, ...]
    source_manifest: tuple[dict, ...]
    missingness: Mapping[str, int]


def _load_metadata(path: Path = DEFAULT_METADATA) -> dict:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if tuple(metadata.get("required_columns", ())) != RAW_COLUMNS:
        raise UciAuditError("metadata required_columns do not match the audit schema")
    return metadata


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(member) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ancillary_cache_manifest(
    block_directory: Path,
    metadata: Mapping[str, object],
    *,
    enforce_pinned_snapshot: bool,
) -> list[dict]:
    pinned = {
        str(row["file"]): row
        for row in metadata.get("observed_cached_ancillary_manifest", [])
    }
    rows = []
    for name in sorted(pinned):
        path = block_directory / name
        if not path.is_file():
            if enforce_pinned_snapshot:
                raise UciAuditError(f"missing pinned ancillary cache file: {name}")
            continue
        row = {
            "file": name,
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        row["matches_checked_in_cache_manifest"] = all(
            row[field] == pinned[name].get(field) for field in ("bytes", "sha256")
        )
        if enforce_pinned_snapshot and not row["matches_checked_in_cache_manifest"]:
            raise UciAuditError(f"ancillary cache file differs from pinned snapshot: {name}")
        rows.append(row)
    return rows


def _histogram(values: Iterable[int]) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in sorted(Counter(int(item) for item in values).items())
    }


def _canonical_code(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    left64 = left.astype(np.uint64, copy=False)
    right64 = right.astype(np.uint64, copy=False)
    low = np.minimum(left64, right64)
    high = np.maximum(left64, right64)
    return (low << np.uint64(32)) | high


def _decode_code(code: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    left = (code >> np.uint64(32)).astype(np.uint32)
    right = (code & np.uint64(UINT32_MAX)).astype(np.uint32)
    return left, right


def _component_arrays(
    left: np.ndarray, right: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(left) == 0:
        raise UciAuditError("a graph audit requires at least one edge")
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
    count, labels = connected_components(adjacency, directed=False)
    sizes = np.bincount(labels, minlength=count)
    return nodes, row, labels, sizes


def _bipartite_audit(left: np.ndarray, right: np.ndarray) -> dict:
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
    component_count, component = connected_components(adjacency, directed=False)
    component_sizes = np.bincount(component, minlength=component_count)
    component_bipartite = np.ones(component_count, dtype=bool)
    color = np.full(len(nodes), -1, dtype=np.int8)
    parent = np.full(len(nodes), -1, dtype=np.int64)
    conflict_directed = 0
    odd_cycle: list[int] | None = None

    def reconstruct(first: int, second: int) -> list[int]:
        first_path = []
        cursor = first
        while cursor >= 0:
            first_path.append(cursor)
            cursor = int(parent[cursor])
        first_position = {node: index for index, node in enumerate(first_path)}
        second_path = []
        cursor = second
        while cursor not in first_position:
            second_path.append(cursor)
            cursor = int(parent[cursor])
            if cursor < 0:
                raise UciAuditError("BFS conflict paths unexpectedly lack a common root")
        first_prefix = first_path[: first_position[cursor] + 1]
        return first_prefix + list(reversed(second_path))

    for root in range(len(nodes)):
        if color[root] >= 0:
            continue
        color[root] = 0
        frontier = deque([root])
        while frontier:
            current = frontier.popleft()
            for neighbor in adjacency.indices[
                adjacency.indptr[current] : adjacency.indptr[current + 1]
            ]:
                neighbor = int(neighbor)
                if color[neighbor] < 0:
                    color[neighbor] = 1 - color[current]
                    parent[neighbor] = current
                    frontier.append(neighbor)
                elif color[neighbor] == color[current]:
                    conflict_directed += 1
                    component_bipartite[component[current]] = False
                    if odd_cycle is None:
                        odd_cycle = reconstruct(current, neighbor)
    conflict_edges = conflict_directed // 2
    evidence = None
    if odd_cycle is not None:
        if len(odd_cycle) % 2 != 1:
            raise UciAuditError("reconstructed same-color conflict cycle is not odd")
        digest = hashlib.sha256()
        for node in odd_cycle:
            digest.update(f"{node}\n".encode("ascii"))
        evidence = {
            "cycle_edges": len(odd_cycle),
            "sequential_node_cycle_sha256": digest.hexdigest(),
            "raw_registry_ids_serialized": False,
        }
    is_bipartite = bool(component_bipartite.all())
    return {
        "is_bipartite": is_bipartite,
        "bipartite_components": int(component_bipartite.sum()),
        "nonbipartite_components": int((~component_bipartite).sum()),
        "nodes_in_nonbipartite_components": int(
            component_sizes[~component_bipartite].sum()
        ),
        "same_color_conflict_edges_in_deterministic_bfs_coloring": conflict_edges,
        "odd_cycle_evidence": evidence,
        "implication": (
            "a bipartite assignment formulation is structurally available"
            if is_bipartite
            else "a bipartite assignment shortcut is invalid; endpoints require "
            "a general-graph matching method"
        ),
    }


def _validate_numeric_columns(frame: pd.DataFrame, block: int) -> None:
    for column in CONTINUOUS_COLUMNS:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if (frame[column].notna() & numeric.isna()).any():
            raise UciAuditError(f"block {block}: {column} is not numeric or missing")
        values = numeric.to_numpy(dtype=float)
        observed = values[~np.isnan(values)]
        if ((observed < 0.0) | (observed > 1.0)).any():
            raise UciAuditError(f"block {block}: {column} contains a value outside [0,1]")
    for column in BINARY_COLUMNS:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if (frame[column].notna() & numeric.isna()).any():
            raise UciAuditError(f"block {block}: {column} is not numeric or missing")
        values = numeric.to_numpy(dtype=float)
        observed = values[~np.isnan(values)]
        if not np.isin(observed, (0.0, 1.0)).all():
            raise UciAuditError(f"block {block}: {column} is not binary")


def _inspect_and_load_block(
    path: Path,
    block: int,
    *,
    pinned: Mapping[str, object] | None,
    enforce_pinned_snapshot: bool,
) -> tuple[dict, dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not path.is_file():
        raise UciAuditError(f"missing UCI block ZIP: {path}")
    expected_member = f"block_{block}.csv"
    with zipfile.ZipFile(path) as archive:
        corrupt_member = archive.testzip()
        if corrupt_member is not None:
            raise UciAuditError(f"block {block}: ZIP CRC failed for {corrupt_member}")
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != expected_member:
            raise UciAuditError(
                f"block {block}: expected exactly one member named {expected_member}"
            )
        member = members[0]
        member_sha256 = _sha256_member(archive, member)

    zip_sha256 = _sha256_file(path)
    manifest = {
        "block": block,
        "zip_file": path.name,
        "zip_bytes": path.stat().st_size,
        "zip_sha256": zip_sha256,
        "member": expected_member,
        "member_bytes": member.file_size,
        "member_compressed_bytes": member.compress_size,
        "member_crc32": f"{member.CRC:08x}",
        "member_sha256": member_sha256,
    }
    if pinned is not None:
        pinned_fields = (
            "zip_sha256",
            "zip_bytes",
            "member",
            "member_bytes",
            "member_crc32",
            "member_sha256",
        )
        matches = all(manifest[field] == pinned.get(field) for field in pinned_fields)
        manifest["matches_checked_in_cache_manifest"] = matches
        if enforce_pinned_snapshot and not matches:
            raise UciAuditError(f"block {block}: cached bytes differ from pinned snapshot")
    else:
        manifest["matches_checked_in_cache_manifest"] = None

    frame = pd.read_csv(path, na_values="?", compression="zip")
    if tuple(frame.columns) != RAW_COLUMNS:
        raise UciAuditError(
            f"block {block}: exact 12-column UCI header/order check failed"
        )
    if frame[["id_1", "id_2"]].isna().any().any():
        raise UciAuditError(f"block {block}: record identifiers cannot be missing")
    for column in ("id_1", "id_2"):
        numeric = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(numeric).all() or (numeric != np.floor(numeric)).any():
            raise UciAuditError(f"block {block}: {column} must contain integers")
        if (numeric < 0).any() or (numeric > UINT32_MAX).any():
            raise UciAuditError(f"block {block}: {column} exceeds uint32 range")
    _validate_numeric_columns(frame, block)
    if not frame["is_match"].isin((True, False)).all():
        raise UciAuditError(f"block {block}: is_match is not TRUE/FALSE")

    left = frame["id_1"].to_numpy(dtype=np.uint32)
    right = frame["id_2"].to_numpy(dtype=np.uint32)
    positive = frame["is_match"].to_numpy(dtype=bool)
    postal = pd.to_numeric(frame["cmp_plz"], errors="coerce").to_numpy(dtype=float)
    pair_code = _canonical_code(left, right)
    unique_pairs = np.unique(pair_code)
    nodes = np.unique(np.concatenate((left, right)))
    transitions = int(np.count_nonzero(positive[1:] != positive[:-1]))
    per_block = {
        "block": block,
        "rows": len(frame),
        "positive_rows": int(positive.sum()),
        "negative_rows": int((~positive).sum()),
        "candidate_nodes": len(nodes),
        "unique_undirected_pairs": len(unique_pairs),
        "duplicate_occurrences": len(pair_code) - len(unique_pairs),
        "self_pairs": int(np.count_nonzero(left == right)),
        "label_transitions_in_source_order": transitions,
        "source_order_label_sorted": bool(transitions <= 1 and positive.any() and (~positive).any()),
    }
    missingness = {
        column: int(frame[column].isna().sum()) for column in MISSINGNESS_COLUMNS
    }
    return (
        manifest,
        per_block,
        pair_code,
        positive,
        postal,
        np.full(len(frame), block, dtype=np.uint8),
        nodes,
    ), missingness, left > right


def load_all_blocks(
    block_directory: Path,
    *,
    metadata_path: Path = DEFAULT_METADATA,
    enforce_pinned_snapshot: bool = True,
) -> UciData:
    """Load, validate, and concatenate exactly block_1.zip through block_10.zip."""

    metadata = _load_metadata(metadata_path)
    if not block_directory.is_dir():
        raise UciAuditError(f"UCI block directory does not exist: {block_directory}")
    expected_paths = [block_directory / f"block_{block}.zip" for block in BLOCK_NUMBERS]
    missing = [path.name for path in expected_paths if not path.is_file()]
    if missing:
        raise UciAuditError(f"all ten UCI block ZIPs are required; missing {missing}")
    unexpected = sorted(
        path.name
        for path in block_directory.glob("block_*.zip")
        if path.name not in {item.name for item in expected_paths}
    )
    if unexpected:
        raise UciAuditError(f"unexpected block ZIP names: {unexpected}")

    pinned_by_block = {
        int(row["block"]): row
        for row in metadata.get("observed_cached_block_manifest", [])
    }
    if enforce_pinned_snapshot and set(pinned_by_block) != set(BLOCK_NUMBERS):
        raise UciAuditError("checked-in cache manifest must identify all ten blocks")

    codes: list[np.ndarray] = []
    positives: list[np.ndarray] = []
    postals: list[np.ndarray] = []
    blocks: list[np.ndarray] = []
    orientations: list[np.ndarray] = []
    block_nodes: list[np.ndarray] = []
    manifests: list[dict] = []
    per_block: list[dict] = []
    missingness = Counter()
    for block, path in zip(BLOCK_NUMBERS, expected_paths):
        loaded, block_missingness, reversed_orientation = _inspect_and_load_block(
            path,
            block,
            pinned=pinned_by_block.get(block),
            enforce_pinned_snapshot=enforce_pinned_snapshot,
        )
        manifest, summary, code, positive, postal, block_index, nodes = loaded
        manifests.append(manifest)
        per_block.append(summary)
        codes.append(code)
        positives.append(positive)
        postals.append(postal)
        blocks.append(block_index)
        orientations.append(reversed_orientation)
        block_nodes.append(nodes)
        missingness.update(block_missingness)
    return UciData(
        pair_code=np.concatenate(codes),
        positive=np.concatenate(positives),
        postal=np.concatenate(postals),
        block=np.concatenate(blocks),
        reversed_orientation=np.concatenate(orientations),
        block_nodes=tuple(block_nodes),
        per_block=tuple(per_block),
        source_manifest=tuple(manifests),
        missingness=dict(missingness),
    )


def _same_optional_number(values: np.ndarray) -> bool:
    if np.isnan(values).all():
        return True
    if np.isnan(values).any():
        return False
    return bool(np.all(values == values[0]))


def reconcile_pairs(data: UciData, *, reject_duplicates: bool = False) -> tuple[dict, dict]:
    """Canonicalize all candidate pairs and explicitly reconcile duplicates."""

    order = np.argsort(data.pair_code, kind="mergesort")
    codes = data.pair_code[order]
    positive = data.positive[order]
    postal = data.postal[order]
    blocks = data.block[order]
    orientations = data.reversed_orientation[order]
    starts = np.concatenate(
        (np.array([0]), np.flatnonzero(codes[1:] != codes[:-1]) + 1)
    )
    ends = np.concatenate((starts[1:], np.array([len(codes)])))
    sizes = ends - starts
    duplicate_group_indices = np.flatnonzero(sizes > 1)
    cross_block_pairs = 0
    reversed_pairs = 0
    label_conflicts = 0
    postal_conflicts = 0
    for group_index in duplicate_group_indices:
        start = int(starts[group_index])
        end = int(ends[group_index])
        cross_block_pairs += int(len(np.unique(blocks[start:end])) > 1)
        reversed_pairs += int(
            bool(orientations[start:end].any())
            and bool((~orientations[start:end]).any())
        )
        label_conflicts += int(positive[start:end].min() != positive[start:end].max())
        postal_conflicts += int(not _same_optional_number(postal[start:end]))

    duplicate_pairs = len(duplicate_group_indices)
    duplicate_occurrences = int(np.sum(sizes - 1))
    duplicate_audit = {
        "raw_rows": len(codes),
        "unique_undirected_pairs": len(starts),
        "duplicate_pair_groups": duplicate_pairs,
        "duplicate_occurrences": duplicate_occurrences,
        "within_block_duplicate_pair_groups": duplicate_pairs - cross_block_pairs,
        "cross_block_duplicate_pair_groups": cross_block_pairs,
        "reversed_orientation_duplicate_pair_groups": reversed_pairs,
        "label_conflict_pair_groups": label_conflicts,
        "postal_comparison_conflict_pair_groups": postal_conflicts,
        "reconciliation_rule": (
            "canonicalize endpoint order; identical duplicates may be collapsed, "
            "but label/query conflicts are fatal"
        ),
    }
    if label_conflicts:
        raise UciAuditError("duplicate candidate pairs have conflicting labels")
    if postal_conflicts:
        raise UciAuditError("duplicate candidate pairs have conflicting postal comparisons")
    if reject_duplicates and duplicate_pairs:
        raise UciAuditError("official ten-block snapshot must be an edge partition without duplicates")

    first = starts
    unique = {
        "code": codes[first],
        "positive": positive[first],
        "postal": postal[first],
        "block": blocks[first],
    }
    return duplicate_audit, unique


def _block_overlap_profile(block_nodes: Sequence[np.ndarray]) -> dict:
    memberships = Counter()
    for nodes in block_nodes:
        memberships.update(int(node) for node in nodes)
    intersections: list[int] = []
    jaccards: list[float] = []
    for first in range(len(block_nodes)):
        for second in range(first + 1, len(block_nodes)):
            intersection = len(np.intersect1d(block_nodes[first], block_nodes[second]))
            union = len(block_nodes[first]) + len(block_nodes[second]) - intersection
            intersections.append(intersection)
            jaccards.append(intersection / union)
    return {
        "record_block_membership_histogram": _histogram(memberships.values()),
        "records_present_in_all_ten_blocks": sum(value == 10 for value in memberships.values()),
        "records_present_in_exactly_one_block": sum(value == 1 for value in memberships.values()),
        "pairwise_node_intersection_min": min(intersections),
        "pairwise_node_intersection_max": max(intersections),
        "pairwise_node_jaccard_min": min(jaccards),
        "pairwise_node_jaccard_max": max(jaccards),
        "interpretation": (
            "blocks are edge partitions over heavily overlapping records, not "
            "independent markets or valid train/calibration/test folds"
        ),
    }


def _positive_relation_profile(
    candidate_code: np.ndarray,
    positive: np.ndarray,
    edge_block: np.ndarray,
) -> tuple[dict, dict]:
    positive_code = candidate_code[positive]
    positive_left, positive_right = _decode_code(positive_code)
    nodes, row, labels, sizes = _component_arrays(positive_left, positive_right)
    edge_component = labels[row]
    edge_counts = np.bincount(edge_component, minlength=len(sizes))
    degree = np.bincount(
        np.concatenate((row, np.searchsorted(nodes, positive_right))),
        minlength=len(nodes),
    )
    expected_clique_edges = sizes * (sizes - 1) // 2
    clique_components = edge_counts == expected_clique_edges

    candidate_left, candidate_right = _decode_code(candidate_code)
    left_index = np.searchsorted(nodes, candidate_left)
    right_index = np.searchsorted(nodes, candidate_right)
    left_present = (left_index < len(nodes)) & (nodes[np.minimum(left_index, len(nodes) - 1)] == candidate_left)
    right_present = (right_index < len(nodes)) & (nodes[np.minimum(right_index, len(nodes) - 1)] == candidate_right)
    both = left_present & right_present
    within = np.zeros(len(candidate_code), dtype=bool)
    within[both] = labels[left_index[both]] == labels[right_index[both]]
    negative_within = int(np.count_nonzero(within & ~positive))

    component_blocks: list[set[int]] = [set() for _ in range(len(sizes))]
    for component, block in zip(edge_component, edge_block[positive]):
        component_blocks[int(component)].add(int(block))
    spanning = sum(len(blocks) > 1 for blocks in component_blocks)
    profile = {
        "unique_positive_pairs": len(positive_code),
        "positive_nodes": len(nodes),
        "positive_components": len(sizes),
        "component_size_histogram": _histogram(sizes.tolist()),
        "largest_component_nodes": int(sizes.max()),
        "node_degree_histogram": _histogram(degree.tolist()),
        "maximum_positive_degree": int(degree.max()),
        "nodes_with_degree_above_one": int(np.count_nonzero(degree > 1)),
        "is_matching": bool(np.all(degree == 1)),
        "complete_clique_components": int(np.count_nonzero(clique_components)),
        "all_positive_components_are_complete_cliques": bool(clique_components.all()),
        "negative_edges_within_positive_components": negative_within,
        "components_spanning_multiple_blocks": spanning,
        "candidate_true_edge_eligibility": 1.0,
        "eligibility_scope": (
            "tautological within the released blocked pair table; omitted real-world "
            "same-entity pairs are unobserved"
        ),
    }
    internals = {
        "positive_code": positive_code,
        "positive_left": positive_left,
        "positive_right": positive_right,
        "positive_nodes": nodes,
        "positive_row": row,
        "positive_labels": labels,
        "positive_sizes": sizes,
        "positive_edge_component": edge_component,
    }
    return profile, internals


def _local_dyad_diagnostics(
    candidate_code: np.ndarray,
    positive: np.ndarray,
    postal: np.ndarray,
    edge_block: np.ndarray,
    positive_internals: Mapping[str, np.ndarray],
) -> dict:
    global_nodes = positive_internals["positive_nodes"]
    global_labels = positive_internals["positive_labels"]
    global_sizes = positive_internals["positive_sizes"]
    rows = []
    total_local = total_absorbed = total_global = total_eligible = 0
    for block in BLOCK_NUMBERS:
        mask = (edge_block == block) & positive
        code = candidate_code[mask]
        if len(code) == 0:
            rows.append(
                {
                    "block": block,
                    "block_local_two_record_components": 0,
                    "remain_global_two_record_components": 0,
                    "remain_global_and_true_postal_observed": 0,
                    "absorbed_into_larger_global_entity": 0,
                }
            )
            continue
        left, right = _decode_code(code)
        nodes, row, labels, sizes = _component_arrays(left, right)
        edge_components = labels[row]
        local_dyad_code = code[sizes[edge_components] == 2]
        local_left, local_right = _decode_code(local_dyad_code)
        global_left = np.searchsorted(global_nodes, local_left)
        global_right = np.searchsorted(global_nodes, local_right)
        remains = (
            (global_labels[global_left] == global_labels[global_right])
            & (global_sizes[global_labels[global_left]] == 2)
        )
        eligible = remains & ~np.isnan(postal[mask][sizes[edge_components] == 2])
        local_count = len(local_dyad_code)
        global_count = int(np.count_nonzero(remains))
        eligible_count = int(np.count_nonzero(eligible))
        rows.append(
            {
                "block": block,
                "block_local_two_record_components": local_count,
                "remain_global_two_record_components": global_count,
                "remain_global_and_true_postal_observed": eligible_count,
                "absorbed_into_larger_global_entity": local_count - global_count,
            }
        )
        total_local += local_count
        total_global += global_count
        total_eligible += eligible_count
        total_absorbed += local_count - global_count
    return {
        "per_block": rows,
        "sum_block_local_apparent_dyads": total_local,
        "local_dyads_absorbed_into_larger_global_entities": total_absorbed,
        "local_dyads_absorbed_share": total_absorbed / total_local,
        "sum_local_dyads_that_remain_global": total_global,
        "sum_local_dyads_that_remain_global_and_postal_observed": total_eligible,
        "warning": (
            "block-local dyad reductions are invalid for the all-ten estimand because "
            "positive paths frequently cross block boundaries"
        ),
    }


def _matching_digest(matching: set[tuple[int, int]]) -> str:
    digest = hashlib.sha256()
    for left, right in sorted(tuple(sorted(edge)) for edge in matching):
        digest.update(f"{left}:{right}\n".encode("ascii"))
    return digest.hexdigest()


def _solve_blossom_endpoint(
    graph: rx.PyGraph,
    *,
    required_nodes: int,
    endpoint: str,
) -> tuple[int, dict]:
    if endpoint == "upper":
        optimization_weight = lambda value: int(value) & 1
        endpoint_weight = optimization_weight
    elif endpoint == "lower":
        optimization_weight = lambda value: 1 - (int(value) >> 1)
        endpoint_weight = lambda value: int(value) >> 1
    else:
        raise UciAuditError(f"unsupported endpoint {endpoint!r}")
    matching = rx.max_weight_matching(
        graph,
        max_cardinality=True,
        weight_fn=optimization_weight,
        verify_optimum=True,
    )
    covered = [node for edge in matching for node in edge]
    perfect = len(matching) * 2 == required_nodes and len(set(covered)) == required_nodes
    if not perfect:
        raise UciAuditError(f"{endpoint} Blossom result is not a perfect matching")
    optimization_sum = int(
        sum(optimization_weight(graph.get_edge_data(u, v)) for u, v in matching)
    )
    endpoint_sum = int(
        sum(endpoint_weight(graph.get_edge_data(u, v)) for u, v in matching)
    )
    replay = {
        "selected_edges": len(matching),
        "distinct_matched_nodes": len(set(covered)),
        "every_required_node_matched_once": perfect,
        "selected_edges_exist_in_candidate_graph": all(
            graph.has_edge(u, v) for u, v in matching
        ),
        "optimization_weight_sum": optimization_sum,
        "postal_objective_sum": endpoint_sum,
        "sequential_node_witness_sha256": _matching_digest(matching),
        "raw_ids_or_edges_serialized": False,
    }
    return endpoint_sum, replay


def _endpoint_worker(
    result_queue,
    graph: rx.PyGraph,
    required_nodes: int,
    endpoint: str,
) -> None:
    try:
        value, replay = _solve_blossom_endpoint(
            graph,
            required_nodes=required_nodes,
            endpoint=endpoint,
        )
        result_queue.put(
            {
                "status": "OPTIMAL",
                "certified": True,
                "verify_optimum": True,
                "sum": value,
                "replay": replay,
            }
        )
    except BaseException as exc:  # pragma: no cover - defensive child boundary
        result_queue.put(
            {
                "status": "UNRESOLVED",
                "reason": f"{type(exc).__name__}: {exc}",
            }
        )


def _solve_endpoint_with_optional_timeout(
    graph: rx.PyGraph,
    *,
    required_nodes: int,
    endpoint: str,
    time_limit_seconds: float | None,
) -> dict:
    if time_limit_seconds is None:
        value, replay = _solve_blossom_endpoint(
            graph,
            required_nodes=required_nodes,
            endpoint=endpoint,
        )
        return {
            "status": "OPTIMAL",
            "certified": True,
            "verify_optimum": True,
            "sum": value,
            "replay": replay,
        }
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise UciAuditError("frontier time limit must be finite and positive")
    if "fork" not in multiprocessing.get_all_start_methods():
        raise UciAuditError(
            "a finite Blossom time limit requires multiprocessing fork support"
        )
    context = multiprocessing.get_context("fork")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_endpoint_worker,
        args=(result_queue, graph, required_nodes, endpoint),
    )
    process.start()
    process.join(time_limit_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        result_queue.close()
        return {
            "status": "UNRESOLVED",
            "reason": (
                f"Verified Blossom {endpoint} endpoint exceeded the predeclared "
                f"{time_limit_seconds:g}-second limit"
            ),
            "time_limit_seconds": time_limit_seconds,
        }
    try:
        result = result_queue.get(timeout=5.0)
    except queue.Empty as exc:
        raise UciAuditError(
            f"Blossom {endpoint} worker exited without a result"
        ) from exc
    finally:
        result_queue.close()
    result["time_limit_seconds"] = time_limit_seconds
    return result


def solve_dyad_frontier(
    left: np.ndarray,
    right: np.ndarray,
    postal: np.ndarray,
    *,
    time_limit_seconds: float | None = None,
) -> dict:
    """Solve exact general-graph postal endpoints with a verified Blossom oracle."""

    if rx is None:
        raise UciAuditError(
            "exact frontier requires the pinned optional dependency rustworkx"
        )
    left = np.asarray(left)
    right = np.asarray(right)
    try:
        postal = np.asarray(postal, dtype=float)
    except (TypeError, ValueError) as exc:
        raise UciAuditError("postal endpoint weights must be numeric or missing") from exc
    if left.ndim != 1 or right.ndim != 1 or postal.ndim != 1:
        raise UciAuditError("left, right, and postal arrays must be one-dimensional")
    if not (len(left) == len(right) == len(postal)):
        raise UciAuditError("left, right, and postal arrays must have equal length")
    if len(left) == 0:
        raise UciAuditError("dyad frontier requires at least one candidate edge")
    if np.any(left == right):
        raise UciAuditError("dyad frontier does not admit self-edges")

    nodes, inverse = np.unique(np.concatenate((left, right)), return_inverse=True)
    edge_count = len(left)
    row = inverse[:edge_count]
    col = inverse[edge_count:]
    observed = postal[~np.isnan(postal)]
    if not np.isfinite(observed).all() or not np.isin(observed, (0.0, 1.0)).all():
        raise UciAuditError(
            "observed postal endpoint weights must be finite and binary before casting"
        )
    lower = np.where(np.isnan(postal), 0, postal).astype(np.int8)
    upper = np.where(np.isnan(postal), 1, postal).astype(np.int8)
    if not np.isin(lower, (0, 1)).all() or not np.isin(upper, (0, 1)).all():
        raise UciAuditError("postal endpoint weights must be binary")
    graph = rx.PyGraph(multigraph=False)
    graph.add_nodes_from([None] * len(nodes))
    # Packed edge data: bit 1 = lower, bit 0 = upper.
    packed = (2 * lower + upper).astype(np.int8)
    graph.add_edges_from(
        (int(u), int(v), int(value)) for u, v, value in zip(row, col, packed)
    )
    if graph.num_edges() != edge_count:
        raise UciAuditError("dyad candidate graph unexpectedly contains parallel edges")
    pair_count = len(nodes) // 2
    upper_result = _solve_endpoint_with_optional_timeout(
        graph,
        required_nodes=len(nodes),
        endpoint="upper",
        time_limit_seconds=time_limit_seconds,
    )
    lower_result = _solve_endpoint_with_optional_timeout(
        graph,
        required_nodes=len(nodes),
        endpoint="lower",
        time_limit_seconds=time_limit_seconds,
    )
    complete = (
        lower_result["status"] == "OPTIMAL"
        and upper_result["status"] == "OPTIMAL"
    )
    result = {
        "status": "OPTIMAL" if complete else "UNRESOLVED",
        "certified": complete,
        "algorithm": "Edmonds/Galil blossom via rustworkx.max_weight_matching",
        "rustworkx_version": rx.__version__,
        "max_cardinality_enforced": True,
        "verify_optimum_enabled": True,
        "normalizer_truth_dyads": pair_count,
        "endpoint_time_limit_seconds": time_limit_seconds,
        "lower_endpoint": lower_result,
        "upper_endpoint": upper_result,
    }
    if lower_result["status"] == "OPTIMAL":
        result["lower_sum"] = lower_result["sum"]
        result["lower"] = lower_result["sum"] / pair_count
        result["lower_witness_replay"] = lower_result["replay"]
    else:
        result["lower_sum"] = None
        result["lower"] = None
    if upper_result["status"] == "OPTIMAL":
        result["upper_sum"] = upper_result["sum"]
        result["upper"] = upper_result["sum"] / pair_count
        result["upper_witness_replay"] = upper_result["replay"]
    else:
        result["upper_sum"] = None
        result["upper"] = None
    result["width"] = (
        (result["upper_sum"] - result["lower_sum"]) / pair_count
        if complete
        else None
    )
    return result


def audit_all_ten_blocks(
    block_directory: Path,
    *,
    metadata_path: Path = DEFAULT_METADATA,
    enforce_pinned_snapshot: bool = True,
    solve_frontier: bool = True,
    frontier_time_limit_seconds: float | None = None,
) -> dict:
    """Return the complete aggregate all-ten topology and optional dyad frontier."""

    metadata = _load_metadata(metadata_path)
    data = load_all_blocks(
        block_directory,
        metadata_path=metadata_path,
        enforce_pinned_snapshot=enforce_pinned_snapshot,
    )
    duplicate_audit, unique = reconcile_pairs(data, reject_duplicates=True)
    code = unique["code"]
    positive = unique["positive"]
    postal = unique["postal"]
    edge_block = unique["block"]

    expected_rows = int(metadata["candidate_pair_count_as_reported"])
    expected_positive = int(metadata["positive_pair_count_as_reported"])
    if len(data.pair_code) != expected_rows or len(code) != expected_rows:
        raise UciAuditError("all-ten candidate-pair total disagrees with UCI metadata")
    if int(positive.sum()) != expected_positive:
        raise UciAuditError("all-ten positive-pair total disagrees with UCI metadata")
    if any(row["self_pairs"] for row in data.per_block):
        raise UciAuditError("official snapshot contains a self-pair")

    candidate_left, candidate_right = _decode_code(code)
    candidate_nodes, _, _, candidate_sizes = _component_arrays(
        candidate_left, candidate_right
    )
    candidate_profile = {
        "raw_rows": len(data.pair_code),
        "unique_undirected_pairs": len(code),
        "negative_pairs": int((~positive).sum()),
        "candidate_nodes": len(candidate_nodes),
        "reported_source_records": int(metadata["source_record_count_as_reported"]),
        "reported_source_records_absent_from_released_candidate_graph": (
            int(metadata["source_record_count_as_reported"]) - len(candidate_nodes)
        ),
        "connected_components": len(candidate_sizes),
        "component_size_histogram": _histogram(candidate_sizes.tolist()),
        "largest_component_nodes": int(candidate_sizes.max()),
        "self_pairs": 0,
    }
    positive_profile, positive_internals = _positive_relation_profile(
        code, positive, edge_block
    )
    local_diagnostics = _local_dyad_diagnostics(
        code, positive, postal, edge_block, positive_internals
    )

    positive_code = positive_internals["positive_code"]
    positive_edge_components = positive_internals["positive_edge_component"]
    positive_sizes = positive_internals["positive_sizes"]
    dyad_edge_mask = positive_sizes[positive_edge_components] == 2
    dyad_code = positive_code[dyad_edge_mask]
    truth_positions = np.searchsorted(code, dyad_code)
    if not np.array_equal(code[truth_positions], dyad_code):
        raise UciAuditError("a positive dyad edge is absent from the candidate table")
    truth_postal = postal[truth_positions]
    observed_truth = ~np.isnan(truth_postal)
    eligible_dyad_code = dyad_code[observed_truth]
    eligible_left, eligible_right = _decode_code(eligible_dyad_code)
    eligible_nodes = np.unique(np.concatenate((eligible_left, eligible_right)))
    induced_mask = np.isin(candidate_left, eligible_nodes) & np.isin(
        candidate_right, eligible_nodes
    )
    induced_left = candidate_left[induced_mask]
    induced_right = candidate_right[induced_mask]
    induced_positive = positive[induced_mask]
    induced_postal = postal[induced_mask]
    core_nodes, core_row, core_labels, core_sizes = _component_arrays(
        induced_left, induced_right
    )
    component_count = len(core_sizes)
    component_edges = np.bincount(core_labels[core_row], minlength=component_count)
    component_truth = np.bincount(
        core_labels[core_row],
        weights=induced_positive.astype(np.int64),
        minlength=component_count,
    ).astype(int)
    with_alternatives = component_edges > component_truth
    giant = int(np.argmax(core_sizes))

    truth_sum = int(truth_postal[observed_truth].sum())
    truth_count = len(eligible_dyad_code)
    dyad_reduction = {
        "construction_uses_truth": True,
        "global_two_record_positive_components": len(dyad_code),
        "dyads_dropped_for_missing_true_postal_comparison": int(
            np.count_nonzero(~observed_truth)
        ),
        "retained_truth_dyads": truth_count,
        "retained_nodes": len(core_nodes),
        "retained_candidate_edges": len(induced_left),
        "retained_truth_edges": int(induced_positive.sum()),
        "retained_negative_edges": int((~induced_positive).sum()),
        "candidate_edges_with_missing_postal_comparison": int(
            np.count_nonzero(np.isnan(induced_postal))
        ),
        "missing_candidate_postal_support": [0, 1],
        "candidate_true_edge_eligibility": float(induced_positive.sum() / truth_count),
        "candidate_components": component_count,
        "component_size_histogram": _histogram(core_sizes.tolist()),
        "largest_component_nodes": int(core_sizes.max()),
        "bipartite_audit": _bipartite_audit(induced_left, induced_right),
        "components_with_nontruth_alternative_edges": int(with_alternatives.sum()),
        "nodes_in_components_with_nontruth_alternative_edges": int(
            core_sizes[with_alternatives].sum()
        ),
        "giant_component": {
            "nodes": int(core_sizes[giant]),
            "truth_dyads": int(component_truth[giant]),
            "candidate_edges": int(component_edges[giant]),
            "share_of_retained_dyads": float(component_truth[giant] / truth_count),
            "share_of_retained_candidate_edges": float(
                component_edges[giant] / len(induced_left)
            ),
        },
        "component_split_status": "NOT_FORMED",
        "component_split_reason": (
            "the giant connected component contains almost all retained dyads, so "
            "a component-disjoint split would be structurally unbalanced and does "
            "not create independent markets"
        ),
    }

    frontier = {
        "status": "NOT_RUN",
        "reason": "frontier solving disabled; unconditional topology remains complete",
    }
    if solve_frontier:
        frontier = solve_dyad_frontier(
            induced_left,
            induced_right,
            induced_postal,
            time_limit_seconds=frontier_time_limit_seconds,
        )
        covered = (
            frontier["lower_sum"] is not None
            and frontier["upper_sum"] is not None
            and frontier["lower_sum"] <= truth_sum <= frontier["upper_sum"]
        )
        frontier.update(
            {
                "population": (
                    "global two-record adjudicated positive components whose true "
                    "postal comparison is observed"
                ),
                "candidate_domain": (
                    "all UCI-supplied candidate edges induced by retained records"
                ),
                "query": "share of selected links with exact postal-code agreement",
                "score_restriction": None,
                "truth_sum": truth_sum,
                "truth": truth_sum / truth_count,
                "covers_adjudicated_truth": covered if frontier["status"] == "OPTIMAL" else None,
                "truth_conditioned_construction": True,
            }
        )

    if not solve_frontier:
        reproduction_frontier_args = " --skip-frontier"
    elif frontier_time_limit_seconds is not None:
        reproduction_frontier_args = (
            f" --frontier-time-limit-seconds {frontier_time_limit_seconds:g}"
        )
    else:
        reproduction_frontier_args = ""
    result = {
        "schema": "uci_krebsregister_all_ten_audit_v2",
        "audit_date": AUDIT_DATE,
        "reproduction_command": (
            "python code/ai_pilot/external_benchmarks/uci_all_blocks_audit.py "
            "--uci-block-dir /secure/uci_rlcp"
            + reproduction_frontier_args
            + " --output-json /tmp/uci_all_blocks_results.json"
            + " --output-report /tmp/UCI_ALL_BLOCKS_REPORT.md"
        ),
        "time_limited_status_may_depend_on_hardware": (
            solve_frontier and frontier_time_limit_seconds is not None
        ),
        "source": {
            "dataset": metadata["title"],
            "dataset_id": metadata["dataset_id"],
            "doi": metadata["doi"],
            "official_page": metadata["official_page"],
            "license": metadata["license"],
            "official_outer_archive": metadata["archive_display_name"],
            "official_outer_archive_sha256": metadata.get("archive_sha256"),
            "outer_archive_retained_in_cache": False,
            "outer_archive_provenance_limit": (
                "the installed recordlinkage loader extracted donation.zip and did "
                "not retain its bytes; the outer archive hash cannot be reconstructed"
            ),
            "cached_snapshot_identity": (
                "ten pinned inner ZIP/member hashes plus exact official row/positive "
                "totals and exact schema"
            ),
            "ancillary_cache_manifest": _ancillary_cache_manifest(
                block_directory,
                metadata,
                enforce_pinned_snapshot=enforce_pinned_snapshot,
            ),
            "block_zip_manifest": list(data.source_manifest),
            "network_used_by_audit": False,
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "rustworkx": rx.__version__ if rx is not None else None,
        },
        "per_block": list(data.per_block),
        "source_order_leakage_audit": {
            "all_blocks_label_sorted_in_source_order": all(
                row["source_order_label_sorted"] for row in data.per_block
            ),
            "warning": (
                "raw source row order reveals labels and must never be preserved in "
                "a public compiled edge table"
            ),
        },
        "missingness": {key: int(value) for key, value in sorted(data.missingness.items())},
        "duplicate_and_cross_block_pair_audit": duplicate_audit,
        "block_record_overlap": _block_overlap_profile(data.block_nodes),
        "candidate_graph": candidate_profile,
        "adjudicated_positive_relation": positive_profile,
        "block_local_dyad_invalidity": local_diagnostics,
        "truth_conditioned_dyad_reduction": dyad_reduction,
        "truth_conditioned_dyad_frontier": frontier,
        "privacy_audit": {
            "aggregate_counts_hashes_and_metadata_only": True,
            "no_row_level_payload_serialized": True,
            "raw_registry_ids_serialized": False,
            "source_rows_serialized": False,
            "pair_labels_serialized": False,
            "truth_edges_serialized": False,
            "raw_endpoint_witness_edge_lists_serialized": False,
            "aggregate_witness_replay_and_digest_serialized": True,
        },
        "claim_boundary": [
            "The full adjudicated positive relation is an entity relation, not a matching.",
            "The matching frontier is truth-conditioned and does not estimate dyad prevalence.",
            "Eligibility is conditional on UCI blocking; omitted true pairs are unobserved.",
            "The ten blocks are edge partitions over overlapping records, not markets or folds.",
            "The benchmark does not validate latent node attributes, calibration coverage, or Chicago transfer.",
        ],
    }
    return result


def _format_float(value: float) -> str:
    return f"{value:.6f}"


def render_report(result: Mapping[str, object]) -> str:
    candidate = result["candidate_graph"]
    relation = result["adjudicated_positive_relation"]
    dyad = result["truth_conditioned_dyad_reduction"]
    frontier = result["truth_conditioned_dyad_frontier"]
    duplicate = result["duplicate_and_cross_block_pair_audit"]
    overlap = result["block_record_overlap"]
    bipartite = dyad["bipartite_audit"]
    if bipartite["is_bipartite"]:
        bipartite_text = (
            "The induced graph is bipartite, so a bipartite assignment "
            "formulation is structurally available."
        )
    else:
        bipartite_text = (
            f"The induced graph is nonbipartite in "
            f"{bipartite['nonbipartite_components']:,} components; a "
            f"{bipartite['odd_cycle_evidence']['cycle_edges']}-edge odd-cycle "
            f"commitment rules out a Hungarian/assignment shortcut without "
            f"releasing its nodes."
        )
    if frontier["status"] == "OPTIMAL":
        frontier_text = (
            f"The exact score-free postal-agreement frontier is "
            f"**[{_format_float(frontier['lower'])}, "
            f"{_format_float(frontier['upper'])}]**.  Adjudicated truth is "
            f"**{_format_float(frontier['truth'])}** and is covered.  Both endpoints "
            f"were solved as general-graph maximum-weight perfect matchings with "
            f"verified Blossom optimality; only aggregate witness replays and digests "
            f"are retained."
        )
    else:
        lower_text = (
            _format_float(frontier["lower"])
            if frontier.get("lower") is not None
            else frontier.get("lower_endpoint", {}).get("status", "unavailable")
        )
        upper_text = (
            _format_float(frontier["upper"])
            if frontier.get("upper") is not None
            else frontier.get("upper_endpoint", {}).get("status", "unavailable")
        )
        reasons = "; ".join(
            endpoint.get("reason", "")
            for endpoint in (
                frontier.get("lower_endpoint", {}),
                frontier.get("upper_endpoint", {}),
            )
            if endpoint.get("reason")
        )
        reason_text = str(frontier.get("reason", reasons)).strip().rstrip(".")
        if reason_text:
            reason_text += "."
        frontier_text = (
            f"The dyad frontier status is **{frontier['status']}**. "
            f"Lower endpoint: **{lower_text}**; upper endpoint: **{upper_text}**. "
            f"{reason_text} This does not affect the completed "
            f"topology audit, and no partial endpoint is described as a full frontier."
        )
    return f"""# UCI Krebsregister all-ten-block audit

Generated for the frozen observed run on {result['audit_date']}. This artifact stores no
registry identifier, source row, pair label, truth edge, or raw endpoint edge
list. It discloses only aggregate witness replay counts and a SHA-256 digest.
Topology/count aggregation is deterministic; the recorded time-limit status
may depend on hardware and scheduling.

## Snapshot and exact reconciliation

All ten pinned cached inner ZIPs passed CRC, exact member-name, member-hash,
schema, and value-domain checks.  The cache does not retain the outer
`donation.zip`, so no outer-archive SHA-256 is claimed.

- Rows: {candidate['raw_rows']:,}; unique undirected pairs: {candidate['unique_undirected_pairs']:,}.
- Positive pairs: {relation['unique_positive_pairs']:,}; negative pairs: {candidate['negative_pairs']:,}.
- Duplicate pair groups: {duplicate['duplicate_pair_groups']:,}; cross-block duplicates: {duplicate['cross_block_duplicate_pair_groups']:,}; label conflicts: {duplicate['label_conflict_pair_groups']:,}; self-pairs: {candidate['self_pairs']:,}.
- Candidate graph: {candidate['candidate_nodes']:,} observed records in {candidate['connected_components']:,} components; the largest has {candidate['largest_component_nodes']:,} records.

The blocks are edge partitions, not markets.  Every pair of blocks shares
between {overlap['pairwise_node_intersection_min']:,} and
{overlap['pairwise_node_intersection_max']:,} records, and
{overlap['records_present_in_all_ten_blocks']:,} records occur in all ten.

## Relation topology

The {relation['unique_positive_pairs']:,} adjudicated positive edges form
{relation['positive_components']:,} entity components over
{relation['positive_nodes']:,} records.  The largest entity has
{relation['largest_component_nodes']} records and maximum positive degree is
{relation['maximum_positive_degree']}.  Therefore the released positive
relation is **not a matching**.  The audit does not split larger entities into
invented pairs.  All observed positive components are complete cliques and no
released negative edge lies inside one of them.

## Explicitly truth-conditioned dyad sensitivity

There are {dyad['global_two_record_positive_components']:,} global two-record
positive components.  Removing {dyad['dyads_dropped_for_missing_true_postal_comparison']:,}
whose true postal comparison is missing leaves {dyad['retained_truth_dyads']:,}
truth dyads.  Their induced candidate graph has {dyad['retained_candidate_edges']:,}
edges, of which {dyad['retained_negative_edges']:,} are alternatives.  One
component contains {dyad['giant_component']['nodes']:,} records and
{dyad['giant_component']['share_of_retained_dyads']:.2%} of retained dyads, so
no component-based source/calibration/test split is reported.
{bipartite_text}

{frontier_text}

## Claim boundary

- UCI validates real relation topology conditional on its released blocking graph.
- The dyad frontier is a truth-conditioned matching sensitivity, not a prevalence estimate or calibrated confidence set.
- Blocks are neither independent observations nor empirical markets.
- The audit does not validate blocking recall, latent node attributes, or transfer to Chicago.
"""


def _write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise UciAuditError(f"refusing to overwrite existing output: {path}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uci-block-dir",
        type=Path,
        default=Path.home() / "rl_data" / "krebsregister",
    )
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument(
        "--skip-frontier",
        action="store_true",
        help="complete topology only; record the truth-conditioned frontier as NOT_RUN",
    )
    parser.add_argument(
        "--frontier-time-limit-seconds",
        type=float,
        default=120.0,
        help="per-endpoint Blossom limit; partial exact endpoints remain separately labeled",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=HERE / "results" / "uci_all_blocks_results.json",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=HERE / "results" / "UCI_ALL_BLOCKS_REPORT.md",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output_json.exists() or args.output_report.exists():
        raise UciAuditError("refusing to overwrite an existing audit result")
    started = time.perf_counter()
    result = audit_all_ten_blocks(
        args.uci_block_dir,
        metadata_path=args.metadata,
        solve_frontier=not args.skip_frontier,
        frontier_time_limit_seconds=args.frontier_time_limit_seconds,
    )
    _write_new(
        args.output_json,
        json.dumps(result, indent=2, sort_keys=True) + "\n",
    )
    _write_new(args.output_report, render_report(result))
    print(
        json.dumps(
            {
                "json": str(args.output_json),
                "report": str(args.output_report),
                "observed_runtime_seconds_not_stored": round(
                    time.perf_counter() - started, 3
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
