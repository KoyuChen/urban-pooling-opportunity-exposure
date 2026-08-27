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
import sqlite3
import sys
import tempfile
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
    source_order_label_transitions: int
    compiled_order_label_transitions: int
    output_order: str = "ascending_hmac_edge_id"
    pseudonymization: str = "HMAC-SHA256 with 96-bit public truncation"
    key_fingerprint_stored: bool = False
    node_pseudonym_collisions: int = 0
    edge_pseudonym_collisions_or_duplicate_pairs: int = 0
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


def _full_pseudonym_digest(kind: str, value: str, key: bytes) -> str:
    return hmac.new(
        key, f"{kind}\0{value}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


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
    """Compile label-order-safe public/truth JSONL with exception-safe cleanup.

    The UCI source blocks are label-sorted.  Streaming them unchanged would
    reveal truth through public row position even if ``is_match`` lived in a
    separate file.  Rows are therefore staged in a private SQLite database and
    emitted in ascending HMAC edge-ID order, which depends on the uncommitted
    key and canonical pair identity but not on the label.  Temporary output
    files are installed only after the full parse, collision audit, sort, and
    serialization succeed. The paired installation is not claimed crash-atomic
    against process kill or power loss.
    """

    if len(key) < 16:
        raise AdapterError("the HMAC key must contain at least 16 bytes")
    if public_output.resolve() == truth_output.resolve():
        raise AdapterError("public and truth output paths must differ")
    if public_output.exists() or truth_output.exists():
        existing = public_output if public_output.exists() else truth_output
        raise AdapterError(f"refusing to overwrite existing output: {existing}")
    public_output.parent.mkdir(parents=True, exist_ok=True)
    truth_output.parent.mkdir(parents=True, exist_ok=True)

    public_temp_handle = tempfile.NamedTemporaryFile(
        prefix=f".{public_output.name}.",
        suffix=".tmp",
        dir=public_output.parent,
        delete=False,
    )
    truth_temp_handle = tempfile.NamedTemporaryFile(
        prefix=f".{truth_output.name}.",
        suffix=".tmp",
        dir=truth_output.parent,
        delete=False,
    )
    public_temp = Path(public_temp_handle.name)
    truth_temp = Path(truth_temp_handle.name)
    public_temp_handle.close()
    truth_temp_handle.close()

    source_rows = emitted_rows = emitted_matches = dropped = 0
    source_transitions = compiled_transitions = 0
    prior_source_label: bool | None = None
    node_digests: dict[str, str] = {}
    node_collisions = 0
    installed: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix="uci-rlcp-compile-") as directory:
            database = Path(directory) / "rows.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA journal_mode=OFF")
                connection.execute("PRAGMA synchronous=OFF")
                connection.execute("PRAGMA temp_store=FILE")
                connection.execute(
                    "CREATE TABLE compiled ("
                    "edge_id TEXT PRIMARY KEY, "
                    "public_json TEXT NOT NULL, "
                    "truth_json TEXT NOT NULL, "
                    "is_match INTEGER NOT NULL) WITHOUT ROWID"
                )
                buffer: list[tuple[str, str, str, int]] = []

                def flush() -> None:
                    if not buffer:
                        return
                    try:
                        connection.executemany(
                            "INSERT INTO compiled VALUES (?, ?, ?, ?)", buffer
                        )
                    except sqlite3.IntegrityError as exc:
                        raise AdapterError(
                            "duplicate source edge or 96-bit edge-pseudonym collision"
                        ) from exc
                    buffer.clear()

                for path in paths:
                    for pattern in iter_patterns(path):
                        source_rows += 1
                        if prior_source_label is not None:
                            source_transitions += int(
                                pattern.is_match != prior_source_label
                            )
                        prior_source_label = pattern.is_match
                        if allowed_nodes is not None and not {
                            pattern.left,
                            pattern.right,
                        }.issubset(allowed_nodes):
                            dropped += 1
                            continue

                        for value in (pattern.left, pattern.right):
                            full_digest = _full_pseudonym_digest("r", value, key)
                            short = f"r_{full_digest[:24]}"
                            prior = node_digests.setdefault(short, full_digest)
                            if prior != full_digest:
                                node_collisions += 1
                                raise AdapterError(
                                    "96-bit node-pseudonym collision detected"
                                )

                        public = public_observation(pattern, key)
                        truth = truth_observation(pattern, key)
                        if public["edge_id"] != truth["edge_id"]:
                            raise AdapterError("public/truth edge pseudonyms disagree")
                        buffer.append(
                            (
                                public["edge_id"],
                                json.dumps(public, sort_keys=True),
                                json.dumps(truth, sort_keys=True),
                                int(pattern.is_match),
                            )
                        )
                        emitted_rows += 1
                        emitted_matches += int(pattern.is_match)
                        if len(buffer) >= 10_000:
                            flush()
                flush()
                connection.commit()

                prior_compiled_label: bool | None = None
                with public_temp.open(
                    "w", encoding="utf-8", newline="\n"
                ) as public_handle, truth_temp.open(
                    "w", encoding="utf-8", newline="\n"
                ) as truth_handle:
                    cursor = connection.execute(
                        "SELECT public_json, truth_json, is_match "
                        "FROM compiled ORDER BY edge_id"
                    )
                    emitted_from_database = 0
                    for public_json, truth_json, is_match in cursor:
                        label = bool(is_match)
                        if prior_compiled_label is not None:
                            compiled_transitions += int(
                                label != prior_compiled_label
                            )
                        prior_compiled_label = label
                        public_handle.write(public_json + "\n")
                        truth_handle.write(truth_json + "\n")
                        emitted_from_database += 1
                    if emitted_from_database != emitted_rows:
                        raise AdapterError("staged row count changed during compilation")
                    public_handle.flush()
                    truth_handle.flush()
                    os.fsync(public_handle.fileno())
                    os.fsync(truth_handle.fileno())
            finally:
                connection.close()

        # The temporary files live beside their destinations. Hard-linking is
        # atomic and refuses to overwrite a path created by another process.
        os.link(public_temp, public_output)
        installed.append(public_output)
        os.link(truth_temp, truth_output)
        installed.append(truth_output)
    except Exception:
        for path in installed:
            path.unlink(missing_ok=True)
        raise
    finally:
        public_temp.unlink(missing_ok=True)
        truth_temp.unlink(missing_ok=True)

    return CompileSummary(
        source_rows=source_rows,
        emitted_rows=emitted_rows,
        emitted_matches=emitted_matches,
        dropped_rows_outside_filter=dropped,
        source_order_label_transitions=source_transitions,
        compiled_order_label_transitions=compiled_transitions,
        node_pseudonym_collisions=node_collisions,
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
        if args.manifest_output.exists():
            raise AdapterError(
                f"refusing to overwrite existing output: {args.manifest_output}"
            )
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
        try:
            with _open_new(args.manifest_output) as handle:
                handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        except Exception:
            # compile_csvs created these paths in this invocation and refused
            # any pre-existing output, so cleanup cannot remove caller data.
            args.public_output.unlink(missing_ok=True)
            args.truth_output.unlink(missing_ok=True)
            raise
        return 0
    except (AdapterError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
