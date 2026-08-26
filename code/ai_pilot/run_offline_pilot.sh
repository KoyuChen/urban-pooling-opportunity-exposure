#!/usr/bin/env bash
set -euo pipefail

PILOT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PILOT_OUTPUT_ROOT="${PILOT_OUTPUT_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/boundpool-offline-XXXXXX")}"
mkdir -p "$PILOT_OUTPUT_ROOT"

python "$PILOT_ROOT/model/smoke_test.py"
python -m unittest discover -s "$PILOT_ROOT/bounds/tests" -v
MPLCONFIGDIR=/tmp/matplotlib-ai-pilot-bounds \
  python "$PILOT_ROOT/bounds/synthetic_validation.py" \
  --output-dir "$PILOT_OUTPUT_ROOT/solver"
MPLCONFIGDIR=/tmp/matplotlib-ai-pilot-integration \
  python "$PILOT_ROOT/integration/run_integration_benchmark.py" \
  --output-dir "$PILOT_OUTPUT_ROOT/integration"
MPLCONFIGDIR=/tmp/matplotlib-ai-pilot-ablation \
  python "$PILOT_ROOT/integration/ablations/no_geography_equality_20260825/run_ablation.py" \
  --locked-result-dir "$PILOT_OUTPUT_ROOT/integration" \
  --output-dir "$PILOT_OUTPUT_ROOT/no_geography_equality"

echo "Offline AI pilot completed: $PILOT_OUTPUT_ROOT"
