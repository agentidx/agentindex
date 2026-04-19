#!/usr/bin/env bash
# 404-driven /token/<slug> coverage backfill runner.
# See agentindex/crypto/token_coverage_backfill.py for details.
#
# Cron suggestion: once daily at 04:20 Europe/Stockholm, after the
# crypto_rating_daily pipeline finishes.

set -euo pipefail

REPO="/Users/anstudio/agentindex"
PY="${REPO}/venv/bin/python3"
ENV_FILE="/Users/anstudio/smedjan/config/.env"
LOG_DIR="${REPO}/logs"
LOG_FILE="${LOG_DIR}/token_coverage_backfill.log"

mkdir -p "${LOG_DIR}"

if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck disable=SC1090
    . "${ENV_FILE}"
    set +a
fi

export PYTHONPATH="${REPO}"

exec "${PY}" "${REPO}/agentindex/crypto/token_coverage_backfill.py" "$@" \
    >> "${LOG_FILE}" 2>&1
