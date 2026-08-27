#!/usr/bin/env bash
set -euo pipefail

pdf_path="${1:-paper/KDD_Research_Working_Draft.pdf}"

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
references_page=""
for page in $(seq 1 "$page_count"); do
  page_text="$(pdftotext -f "$page" -l "$page" "$pdf_path" - 2>/dev/null || true)"
  # TeX Live and Poppler versions disagree about heading case and may leave
  # horizontal whitespace or a carriage return around an otherwise identical
  # section heading.  Match the complete normalized line, not a substring.
  if grep -Eiq '^[[:space:]]*REFERENCES[[:space:]]*$' <<<"$page_text"; then
    references_page="$page"
    break
  fi
done
if [[ -z "$references_page" ]]; then
  printf 'References heading not found.\n' >&2
  exit 1
fi
if [[ "$references_page" -gt 9 ]]; then
  printf 'Main content exceeds eight pages; references begin on page %s.\n' "$references_page" >&2
  exit 1
fi
main_end_page=$((references_page - 1))
main_text="$(pdftotext -f 1 -l "$main_end_page" "$pdf_path" -)"
if ! grep -q 'LIMITATIONS AND ETHICAL' <<<"$main_text"; then
  printf 'Mandatory limitations/ethics section is missing from pages 1-8.\n' >&2
  exit 1
fi
if ! grep -q 'GENERATIVE AI USAGE' <<<"$main_text"; then
  printf 'Generative-AI disclosure is missing from main content.\n' >&2
  exit 1
fi

printf 'PASS: %s pages; %s\n' "$page_count" "$page_size"
printf 'PASS: main content ends on page %s; references begin on page %s.\n' "$main_end_page" "$references_page"
printf 'PASS: limitations/ethics and generative-AI disclosure occur in main content.\n'
