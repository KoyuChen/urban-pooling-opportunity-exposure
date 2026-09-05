#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runner="$repo_root/code/ai_pilot/data_pipeline/production_audit/run_nyc_branch_price_scale.py"
campaign_root="${1:-$repo_root/tmp/nyc-bp-24h-$(date -u +%Y%m%dT%H%M%SZ)}"
cell_budget_seconds=20700

mkdir -p "$campaign_root"
exec > >(tee -a "$campaign_root/campaign.log") 2>&1

printf 'campaign_started_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'campaign_root=%s\n' "$campaign_root"
printf 'cell_budget_seconds=%s\n' "$cell_budget_seconds"

run_cell() {
  local core="$1"
  local capacity="$2"
  local label="core${core}_capacity${capacity}"
  local output_dir="$campaign_root/$label"

  printf 'cell_started label=%s utc=%s\n' "$label" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set +e
  timeout --signal=INT --kill-after=5m "$((cell_budget_seconds + 600))" \
    python "$runner" \
      --output-dir "$output_dir" \
      --window-label "jan_weekday_evening_24h_followup" \
      --scan-start "2023-01-03T17:00:00" \
      --scan-end "2023-01-03T21:00:00" \
      --ordered-core "$core" \
      --capacities "$capacity" \
      --solver-time-limit "$cell_budget_seconds" \
      --bp-max-nodes 1000000 \
      --bp-max-pricing-cases 65536
  local status=$?
  set -e
  printf 'cell_finished label=%s exit=%s utc=%s\n' \
    "$label" "$status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

# Frozen open cells from the 14/18 scale lattice. Each receives 5h45m;
# the outer 24h watchdog leaves one hour for extraction and shutdown overhead.
export -f run_cell
export runner campaign_root cell_budget_seconds
timeout --signal=INT --kill-after=5m 24h bash -c \
  'run_cell 10 4; run_cell 12 4; run_cell 16 3; run_cell 16 4' \
  2>&1 || true

printf 'campaign_finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
