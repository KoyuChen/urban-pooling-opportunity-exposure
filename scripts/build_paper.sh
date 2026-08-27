#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
paper_dir="$repo_root/paper"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/boundpool-paper-build-XXXXXX")"

cleanup() {
  rm -rf "$build_dir"
}
trap cleanup EXIT

rsync -a \
  --exclude build \
  --exclude build_acm \
  --exclude '/KDD_Research_Working_Draft.pdf' \
  "$paper_dir/" "$build_dir/"

(
  cd "$build_dir"
  TEXMFHOME="$repo_root/texmf" \
  TEXMFVAR="$repo_root/texmf-var" \
  TEXMFCONFIG="$repo_root/texmf-config" \
    latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
)

cp "$build_dir/main.pdf" "$paper_dir/KDD_Research_Working_Draft.pdf"
cp "$build_dir/main.log" "$paper_dir/latex-build.log"
printf 'Built %s\n' "$paper_dir/KDD_Research_Working_Draft.pdf"
