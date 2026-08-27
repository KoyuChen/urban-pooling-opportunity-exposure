#!/usr/bin/env python3
"""Leakage-aware adapter for UCI Record Linkage Comparison Patterns.

This module never downloads the dataset.  It accepts one or more extracted
CSV blocks, validates the documented schema, pseudonymizes record identifiers,
coarsens comparison values, and writes public observations separately from
pair truth.  The small checked-in fixture contains metadata only.

The UCI relation is an entity/deduplication relation and need not itself be a
matching.  ``profile`` therefore reports the positive-component structure and
the number of two-record components that can be used without inventing a true
pairing.  A full benchmark must pass that structural audit before invoking a
perfect-matching solver.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence, TextIO


HERE = Path(__file__).resolve().parent
DEFAULT_METADATA = HERE / "fixtures" / "uci_rlcp_metadata.json"

ID_COLUMNS = ("id_1", "id_2")
CONTINUOUS_COLUMNS = (
    "cmp_fname_c1",
    "cmp_fname_c2",
    "cmp_lname_c1",
    "cmp_lname_c2",
)
BINARY_COLUMNS = ("cmp_sex", "cmp_bd", "cmp_bm", "cmp_by", "cmp_plz")
LABEL_COLUMN = "is_match"
REQUIRED_COLUMNS = (*ID_COLUMNS, *CONTINUOUS_COLUMNS, *BINARY_COLUMNS, LABEL_COLUMN)
ALLOWED_INDEX_COLUMNS = ("", "X", "x", "row", "row_id")
MISSING_TOKENS = frozenset(("", "?", "NA", "NaN", "nan"))


class AdapterError(ValueError):
    """Raised when source data violate the declared adapter contract."""


@dataclass(frozen=True)
class PairPattern:
    """One validated source comparison pattern."""

    left: str
    right: str
    comparisons: Mapping[str, float | None]
    is_match: bool


@dataclass(frozen=True)
class CompileSummary:
    source_rows: int
    emitted_rows: int
    emitted_matches: int
    dropped_rows_outside_filter: int
    id_key_fingerprint: str
    public_schema: str = "uci_rlcp_public_coarsened_v1"
    truth_schema: str = "uci_rlcp_pair_truth_v1"


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.size: dict[str, int] = {}

    def add(self, value: str) -> None:
        if value not in self.parent:
            self.parent[value] = value
            self.size[value] = 1

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
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


def load_metadata(path: Path = DEFAULT_METADATA) -> dict:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if tuple(metadata.get("required_columns", ())) != REQUIRED_COLUMNS:
        raise AdapterError("fixture metadata disagrees with the adapter schema")
    if tuple(metadata.get("continuous_comparison_columns", ())) != CONTINUOUS_COLUMNS:
        raise AdapterError("fixture metadata disagrees on continuous comparisons")
    if tuple(metadata.get("binary_comparison_columns", ())) != BINARY_COLUMNS:
        raise AdapterError("fixture metadata disagrees on binary comparisons")
    return metadata


def _sniff_dialect(handle: TextIO) -> csv.Dialect:
    sample = handle.read(8192)
    handle.seek(0)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.get_dialect("excel")


def _clean_header(value: str | None) -> str:
    return "" if value is None else value.strip().lstrip("\ufeff")


def _parse_comparison(raw: str | None, column: str, row_number: int) -> float | None:
    token = "" if raw is None else raw.strip()
    if token in MISSING_TOKENS:
        return None
    try:
        value = float(token)
    except ValueError as exc:
        raise AdapterError(
            f"row {row_number}: {column} is not numeric or missing: {token!r}"
        ) from exc
    if not 0.0 <= value <= 1.0:
        raise AdapterError(f"row {row_number}: {column}={value} is outside [0, 1]")
    if column in BINARY_COLUMNS and value not in (0.0, 1.0):
        raise AdapterError(f"row {row_number}: {column}={value} is not binary")
    return value


def _parse_label(raw: str | None, row_number: int) -> bool:
    token = "" if raw is None else raw.strip().lower()
    if token in ("true", "1", "t"):
        return True
    if token in ("false", "0", "f"):
        return False
    raise AdapterError(f"row {row_number}: is_match must be TRUE/FALSE or 1/0")


def iter_patterns(path: Path) -> Iterator[PairPattern]:
    """Yield validated patterns from one extracted UCI CSV block."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        dialect = _sniff_dialect(handle)
        reader = csv.DictReader(handle, dialect=dialect)
        if reader.fieldnames is None:
            raise AdapterError(f"{path}: missing CSV header")
        original_headers = list(reader.fieldnames)
        cleaned_headers = [_clean_header(name) for name in original_headers]
        if len(set(cleaned_headers)) != len(cleaned_headers):
            raise AdapterError(f"{path}: duplicate column after header normalization")
        rename = dict(zip(original_headers, cleaned_headers))
        missing = set(REQUIRED_COLUMNS).difference(cleaned_headers)
        unexpected = set(cleaned_headers).difference(REQUIRED_COLUMNS, ALLOWED_INDEX_COLUMNS)
        if missing:
            raise AdapterError(f"{path}: missing required columns {sorted(missing)}")
        if unexpected:
            raise AdapterError(f"{path}: unexpected columns {sorted(unexpected)}")

        for row_number, raw_row in enumerate(reader, start=2):
            row = {rename[key]: value for key, value in raw_row.items() if key is not None}
            left = (row.get("id_1") or "").strip()
            right = (row.get("id_2") or "").strip()
            if not left or not right:
                raise AdapterError(f"row {row_number}: record identifiers cannot be missing")
            if left == right:
                raise AdapterError(f"row {row_number}: self-pairs are not admissible")
            comparisons = {
                column: _parse_comparison(row.get(column), column, row_number)
                for column in (*CONTINUOUS_COLUMNS, *BINARY_COLUMNS)
            }
            yield PairPattern(
                left=left,
                right=right,
                comparisons=comparisons,
                is_match=_parse_label(row.get(LABEL_COLUMN), row_number),
            )


def _pseudonym(kind: str, value: str, key: bytes) -> str:
    digest = hmac.new(key, f"{kind}\0{value}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{kind}_{digest[:24]}"


def _edge_identity(left: str, right: str, key: bytes) -> tuple[str, str, str]:
    u = _pseudonym("r", left, key)
    v = _pseudonym("r", right, key)
    u, v = sorted((u, v))
    edge_id = _pseudonym("e", f"{u}\0{v}", key)
    return edge_id, u, v


def _continuous_bin(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value == 0.0:
        return "zero"
    if value < 0.5:
        return "low"
    if value < 0.8:
        return "medium"
    if value < 1.0:
        return "high"
    return "exact"


def _binary_support(value: float | None) -> list[int]:
    if value is None:
        return [0, 1]
    return [int(value)]


def public_observation(pattern: PairPattern, key: bytes) -> dict:
    """Apply the declared coarsening operator and remove relation truth."""

    if len(key) < 16:
        raise AdapterError("the HMAC key must contain at least 16 bytes")
    edge_id, u, v = _edge_identity(pattern.left, pattern.right, key)
    comparisons = pattern.comparisons
    return {
        "schema": "uci_rlcp_public_coarsened_v1",
        "edge_id": edge_id,
        "u": u,
        "v": v,
        "fname_c1_bin": _continuous_bin(comparisons["cmp_fname_c1"]),
        "fname_c2_bin": _continuous_bin(comparisons["cmp_fname_c2"]),
        "lname_c1_bin": _continuous_bin(comparisons["cmp_lname_c1"]),
        "lname_c2_bin": _continuous_bin(comparisons["cmp_lname_c2"]),
        "sex_agreement_support": _binary_support(comparisons["cmp_sex"]),
        "birth_day_agreement_support": _binary_support(comparisons["cmp_bd"]),
        "birth_month_agreement_support": _binary_support(comparisons["cmp_bm"]),
        "birth_year_agreement_support": _binary_support(comparisons["cmp_by"]),
        "postal_agreement_support": _binary_support(comparisons["cmp_plz"]),
    }


def truth_observation(pattern: PairPattern, key: bytes) -> dict:
    """Return evaluation truth keyed to, but separated from, the public edge."""

    edge_id, u, v = _edge_identity(pattern.left, pattern.right, key)
    return {
        "schema": "uci_rlcp_pair_truth_v1",
        "edge_id": edge_id,
        "u": u,
        "v": v,
        "is_match": pattern.is_match,
    }


def positive_component_profile(paths: Sequence[Path]) -> tuple[dict, frozenset[str]]:
    """Scan all pair labels and report the positive relation's topology.

    The returned node set contains only vertices in positive components of
    exactly two records.  Filtering to this set turns the adjudicated positive
    relation into a true matching without arbitrarily pairing larger entities.
    """

    union_find = _UnionFind()
    positive_pairs: set[tuple[str, str]] = set()
    positive_degrees: Counter[str] = Counter()
    query_observed: dict[tuple[str, str], set[str]] = {}
    source_rows = 0
    for path in paths:
        for pattern in iter_patterns(path):
            source_rows += 1
            if not pattern.is_match:
                continue
            pair = tuple(sorted((pattern.left, pattern.right)))
            if pair in positive_pairs:
                raise AdapterError(f"duplicate positive pair encountered: {pair}")
            positive_pairs.add(pair)
            positive_degrees.update(pair)
            union_find.union(*pair)
            query_observed[pair] = {
                column for column, value in pattern.comparisons.items() if value is not None
            }

    components: dict[str, set[str]] = {}
    for node in union_find.parent:
        components.setdefault(union_find.find(node), set()).add(node)
    size_histogram = Counter(len(nodes) for nodes in components.values())
    dyad_nodes: set[str] = set()
    observable_dyads = Counter()
    for nodes in components.values():
        if len(nodes) != 2:
            continue
        pair = tuple(sorted(nodes))
        if pair not in positive_pairs:
            raise AdapterError("two-node positive component lacks its positive edge")
        dyad_nodes.update(nodes)
        observable_dyads.update(query_observed[pair])

    profile = {
        "source_rows": source_rows,
        "unique_positive_pairs": len(positive_pairs),
        "positive_nodes": len(union_find.parent),
        "positive_components": len(components),
        "component_size_histogram": {
            str(size): count for size, count in sorted(size_histogram.items())
        },
        "two_record_components": size_histogram.get(2, 0),
        "positive_relation_is_matching": all(
            degree == 1 for degree in positive_degrees.values()
        ),
        "two_record_components_with_observed_true_edge_field": {
            column: observable_dyads.get(column, 0)
            for column in (*CONTINUOUS_COLUMNS, *BINARY_COLUMNS)
        },
    }
    return profile, frozenset(dyad_nodes)


def _open_new(path: Path) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return path.open("x", encoding="utf-8", newline="\n")
    except FileExistsError as exc:
        raise AdapterError(f"refusing to overwrite existing output: {path}") from exc


def compile_csvs(
    paths: Sequence[Path],
    *,
    public_output: Path,
    truth_output: Path,
    key: bytes,
    allowed_nodes: frozenset[str] | None = None,
) -> CompileSummary:
    """Stream extracted blocks into strictly separated public/truth JSONL."""

    if len(key) < 16:
        raise AdapterError("the HMAC key must contain at least 16 bytes")
    if public_output.resolve() == truth_output.resolve():
        raise AdapterError("public and truth output paths must differ")
    source_rows = emitted_rows = emitted_matches = dropped = 0
    with _open_new(public_output) as public_handle, _open_new(truth_output) as truth_handle:
        for path in paths:
            for pattern in iter_patterns(path):
                source_rows += 1
                if allowed_nodes is not None and not {
                    pattern.left,
                    pattern.right,
                }.issubset(allowed_nodes):
                    dropped += 1
                    continue
                public_handle.write(
                    json.dumps(public_observation(pattern, key), sort_keys=True) + "\n"
                )
                truth_handle.write(
                    json.dumps(truth_observation(pattern, key), sort_keys=True) + "\n"
                )
                emitted_rows += 1
                emitted_matches += int(pattern.is_match)
    return CompileSummary(
        source_rows=source_rows,
        emitted_rows=emitted_rows,
        emitted_matches=emitted_matches,
        dropped_rows_outside_filter=dropped,
        id_key_fingerprint=hashlib.sha256(key).hexdigest(),
    )


def _paths(values: Iterable[str]) -> list[Path]:
    paths = [Path(value) for value in values]
    if not paths:
        raise AdapterError("at least one extracted CSV block is required")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise AdapterError(f"input paths do not exist: {missing}")
    return paths


def _key_from_env(name: str) -> bytes:
    value = os.environ.get(name)
    if value is None:
        raise AdapterError(f"required HMAC key environment variable is unset: {name}")
    key = value.encode("utf-8")
    if len(key) < 16:
        raise AdapterError(f"{name} must contain at least 16 UTF-8 bytes")
    return key


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser("profile", help="audit positive relation topology")
    profile.add_argument("inputs", nargs="+", help="extracted UCI CSV blocks")
    profile.add_argument("--output", type=Path, help="optional JSON report path")

    compile_parser = subparsers.add_parser(
        "compile", help="write coarsened public and isolated truth JSONL"
    )
    compile_parser.add_argument("inputs", nargs="+", help="extracted UCI CSV blocks")
    compile_parser.add_argument("--public-output", required=True, type=Path)
    compile_parser.add_argument("--truth-output", required=True, type=Path)
    compile_parser.add_argument("--manifest-output", required=True, type=Path)
    compile_parser.add_argument(
        "--id-key-env",
        default="UCI_RLCP_ID_KEY",
        help="environment variable holding the uncommitted HMAC key",
    )
    compile_parser.add_argument(
        "--truth-dyads-only",
        action="store_true",
        help="retain only nodes in two-record positive components (two-pass scan)",
    )

    subparsers.add_parser("metadata", help="validate and print fixture metadata")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "metadata":
            print(json.dumps(load_metadata(), indent=2, sort_keys=True))
            return 0
        paths = _paths(args.inputs)
        if args.command == "profile":
            profile, _ = positive_component_profile(paths)
            rendered = json.dumps(profile, indent=2, sort_keys=True) + "\n"
            if args.output:
                with _open_new(args.output) as handle:
                    handle.write(rendered)
            else:
                print(rendered, end="")
            return 0
        key = _key_from_env(args.id_key_env)
        relation_profile = None
        allowed_nodes = None
        if args.truth_dyads_only:
            relation_profile, allowed_nodes = positive_component_profile(paths)
        summary = compile_csvs(
            paths,
            public_output=args.public_output,
            truth_output=args.truth_output,
            key=key,
            allowed_nodes=allowed_nodes,
        )
        manifest = {
            "compile_summary": asdict(summary),
            "dataset_metadata": load_metadata(),
            "relation_profile": relation_profile,
        }
        with _open_new(args.manifest_output) as handle:
            handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return 0
    except (AdapterError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
