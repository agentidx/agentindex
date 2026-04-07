#!/bin/bash
# ZARQ Daily Track Record — cron wrapper
# Runs daily at 01:00 UTC via crontab
# Generates hash-chained signal snapshot, then commits and pushes to GitHub
set -euo pipefail

REPO_DIR="/Users/anstudio/agentindex"
TRACK_RECORD_DIR="${REPO_DIR}/track-record"
LOG_FILE="${REPO_DIR}/logs/daily_track_record.log"
PYTHON="${REPO_DIR}/venv/bin/python"
DATE=$(date -u +"%Y-%m-%d")

# Ensure log directory exists
mkdir -p "${REPO_DIR}/logs"

{
    echo "=== Track Record Run: $(date -u) ==="

    # Step 1: Generate today's signal snapshot
    PYTHON_EXIT=0
    "${PYTHON}" "${REPO_DIR}/scripts/daily_track_record.py" || PYTHON_EXIT=$?

    if [ $PYTHON_EXIT -ne 0 ]; then
        echo "ERROR: daily_track_record.py exited with code ${PYTHON_EXIT}. Skipping git push."
        exit $PYTHON_EXIT
    fi

    # Step 2: Commit and push to GitHub
    cd "${TRACK_RECORD_DIR}"

    # Check if there are changes to commit
    if git diff --quiet daily-signals.jsonl 2>/dev/null; then
        echo "No changes to daily-signals.jsonl. Nothing to commit."
        exit 0
    fi

    # Count tokens in today's entry for the commit message
    TOKEN_COUNT=$(tail -1 daily-signals.jsonl | "${PYTHON}" -c "import sys,json; print(json.loads(sys.stdin.read()).get('total_tokens','?'))" 2>/dev/null || echo "?")

    git add daily-signals.jsonl
    git commit -m "daily: ${DATE} signal snapshot (${TOKEN_COUNT} tokens)"
    git push origin main

    echo "Committed and pushed track record for ${DATE} (${TOKEN_COUNT} tokens)."

} >> "${LOG_FILE}" 2>&1
