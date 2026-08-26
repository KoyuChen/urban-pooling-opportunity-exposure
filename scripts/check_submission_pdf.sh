#!/usr/bin/env bash
set -euo pipefail

pdf_path="${1:-paper/Thicker_But_Narrower_Draft.pdf}"

for command_name in pdfinfo pdftotext; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$command_name" >&2
    exit 2
  fi
done

if [[ ! -f "$pdf_path" ]]; then
  printf 'PDF not found: %s\n' "$pdf_path" >&2
  exit 2
fi

page_count="$(pdfinfo "$pdf_path" | awk '/^Pages:/ {print $2}')"
page_size="$(pdfinfo "$pdf_path" | awk -F': +' '/^Page size:/ {print $2}')"
page_nine="$(pdftotext -f 9 -l 9 "$pdf_path" - 2>/dev/null || true)"
main_text="$(pdftotext -f 1 -l 8 "$pdf_path" -)"

if [[ "$page_count" -lt 9 ]]; then
  printf 'Expected at least 9 total pages; found %s.\n' "$page_count" >&2
  exit 1
fi
if ! grep -q 'REFERENCES' <<<"$page_nine"; then
  printf 'References do not begin on page 9.\n' >&2
  exit 1
fi
if ! grep -q 'LIMITATIONS AND ETHICAL' <<<"$main_text"; then
  printf 'Mandatory limitations/ethics section is missing from pages 1-8.\n' >&2
  exit 1
fi
if ! grep -q 'GENERATIVE AI USAGE' <<<"$main_text"; then
  printf 'Mandatory generative-AI section is missing from pages 1-8.\n' >&2
  exit 1
fi

printf 'PASS: %s pages; %s\n' "$page_count" "$page_size"
printf 'PASS: main content is pages 1-8; references begin on page 9.\n'
printf 'PASS: both mandatory disclosure sections occur within pages 1-8.\n'
