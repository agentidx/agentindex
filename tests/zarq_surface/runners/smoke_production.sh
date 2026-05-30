#!/bin/bash
# Production smoke via Cloudflare. Use sparingly — every request hits the
# live edge and the live API. ~2 minutes.
set -e
cd /Users/anstudio/agentindex
exec venv/bin/pytest tests/zarq_surface/ \
    --zarq-target production \
    -v --tb=short --no-header \
    "$@"
