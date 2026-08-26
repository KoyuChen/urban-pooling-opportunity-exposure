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
  --exclude '*.pdf' \
  "$paper_dir/" "$build_dir/"

(
  cd "$build_dir"
  latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
)

cp "$build_dir/main.pdf" "$paper_dir/Thicker_But_Narrower_Draft.pdf"
cp "$build_dir/main.log" "$paper_dir/latex-build.log"
printf 'Built %s\n' "$paper_dir/Thicker_But_Narrower_Draft.pdf"
