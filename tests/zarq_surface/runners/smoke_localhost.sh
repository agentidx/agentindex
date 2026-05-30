#!/bin/bash
# Fast localhost smoke. Run after code changes. ~1 minute.
set -e
cd /Users/anstudio/agentindex
exec venv/bin/pytest tests/zarq_surface/ \
    --zarq-target localhost \
    -v --tb=short --no-header \
    "$@"
