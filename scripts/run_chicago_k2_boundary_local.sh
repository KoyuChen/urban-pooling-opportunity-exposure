#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv-chicago-k2}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/tmp/chicago-k2-frontier-boundary}"
RUN_TESTS="${RUN_TESTS:-1}"
INSTALL_DEPS="${INSTALL_DEPS:-1}"

SCAN_START="${SCAN_START:-2026-01-13T17:00:00}"
SCAN_END="${SCAN_END:-2026-01-13T21:00:00}"
MIN_CORE_ROWS="${MIN_CORE_ROWS:-12}"
MAX_CORE_ROWS="${MAX_CORE_ROWS:-60}"
MAX_CANDIDATE_ROWS="${MAX_CANDIDATE_ROWS:-5000}"
PAGE_SIZE="${PAGE_SIZE:-100}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-90}"
REQUEST_ATTEMPTS="${REQUEST_ATTEMPTS:-3}"
BASE_RADIUS_KM="${BASE_RADIUS_KM:-2}"
SOLVER_TIME_LIMIT="${SOLVER_TIME_LIMIT:-60}"
BOUNDARY_PADDING_MINUTES="${BOUNDARY_PADDING_MINUTES:-0,5,10,15,30}"

ENTRY="${ROOT_DIR}/code/ai_pilot/data_pipeline/production_audit/live_chicago_k2_frontier_boundary.py"
TEST_DIR="${ROOT_DIR}/code/ai_pilot/data_pipeline/production_audit/tests"

if [[ ! -f "${ENTRY}" ]]; then
  echo "Missing entrypoint: ${ENTRY}" >&2
  exit 2
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

if [[ "${INSTALL_DEPS}" == "1" ]]; then
  "${PYTHON}" -m pip install --upgrade pip
  "${PIP}" install \
    numpy==2.3.5 \
    scipy==1.17.0 \
    matplotlib==3.10.8
fi

export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

if [[ "${RUN_TESTS}" == "1" ]]; then
  "${PYTHON}" "${ENTRY}" --self-test
  "${PYTHON}" -m unittest discover \
    -s "${TEST_DIR}" \
    -p 'test_live_chicago_k2_frontier.py' -v
  "${PYTHON}" -m unittest discover \
    -s "${TEST_DIR}" \
    -p 'test_partitioned_chicago_k2_fetch.py' -v
  "${PYTHON}" -m unittest discover \
    -s "${TEST_DIR}" \
    -p 'test_boundary_padding_chicago_k2_frontier.py' -v
fi

mkdir -p "${OUTPUT_DIR}"
rm -f "${OUTPUT_DIR}/failure.json"

"${PYTHON}" "${ENTRY}" \
  --output-dir "${OUTPUT_DIR}" \
  --scan-start "${SCAN_START}" \
  --scan-end "${SCAN_END}" \
  --min-core-rows "${MIN_CORE_ROWS}" \
  --max-core-rows "${MAX_CORE_ROWS}" \
  --max-candidate-rows "${MAX_CANDIDATE_ROWS}" \
  --page-size "${PAGE_SIZE}" \
  --request-timeout "${REQUEST_TIMEOUT}" \
  --request-attempts "${REQUEST_ATTEMPTS}" \
  --base-radius-km "${BASE_RADIUS_KM}" \
  --solver-time-limit "${SOLVER_TIME_LIMIT}" \
  --boundary-padding-minutes "${BOUNDARY_PADDING_MINUTES}" \
  "$@"

cat <<EOF

Chicago K=2 boundary-support run completed.
Output directory: ${OUTPUT_DIR}
Primary files:
  ${OUTPUT_DIR}/CHICAGO_K2_PUBLIC_TEMPORAL_FRONTIER_REPORT.md
  ${OUTPUT_DIR}/report.json
  ${OUTPUT_DIR}/candidate_support_sensitivity.csv
  ${OUTPUT_DIR}/candidate_graph_curve.csv
EOF
