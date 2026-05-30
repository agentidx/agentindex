#!/bin/bash
# Full ZARQ surface audit: both targets + freshness + templates + MCP +
# cloudflared parity. The complete picture. ~4-5 minutes serial. The output
# JSON lands at docs/status/zarq_surface_test_run.json; per-failure raw
# response excerpts at docs/status/zarq_test_failures_20260530/<id>.txt.
set -e
cd /Users/anstudio/agentindex
exec venv/bin/pytest tests/zarq_surface/ \
    -v --tb=short --no-header \
    "$@"
