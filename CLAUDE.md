# ZARQ + Nerq — Project Context for Claude Code

## What is this?
ZARQ (zarq.ai) is a crypto risk intelligence platform — "Moody's for crypto". Trust Score, Distance-to-Default, crash probability.
Nerq (nerq.ai) is an AI asset search engine indexing 5M+ AI assets (204K agents & tools, 4.7M models & datasets) with Trust Scores.
Both run on the same FastAPI backend.

## Critical paths
- Main app: ~/agentindex/agentindex/api/discovery.py (mounts as agentindex.api.discovery:app on port 8000)
- SQLite DB (ratings/pipeline): ~/agentindex/agentindex/crypto/crypto_trust.db (379MB)
- SQLite DB (SEO): ~/agentindex/data/crypto_trust.db (20MB)
- Templates: ~/agentindex/agentindex/crypto/templates/
- LaunchAgent: ~/Library/LaunchAgents/com.nerq.api.plist
- Healthcheck: ~/agentindex/system_healthcheck.py
- Autoheal: ~/agentindex/system_autoheal.py
- Redis: /opt/homebrew/bin/redis-cli (full path required)
- Cloudflare Tunnel ID: a17d8bfb-9596-4700-848a-df481dc171ad

## Key conventions — READ THESE
1. All shell commands MUST be wrapped in heredoc: bash << 'EOF' ... EOF
2. LaunchAgents: Use launchctl stop/start com.nerq.api — NEVER pkill (auto-restarts)
3. PostgreSQL pool: max pool_size=5, max_overflow=5
4. ZARQ design: light theme, DM Serif Display, JetBrains Mono, DM Sans, --warm: #c2956b

## Database tables (important)
- nerq_risk_signals: 205 tokens. Columns: token_id, risk_level, structural_weakness, trust_score, ndd_current, sig6_structure, trust_p3. Does NOT have token_symbol, crash_probability or chain — requires joins.
- crash_model_v3_predictions
- crypto_rating_daily
- defi_protocol_tokens

## Task system
- New tasks: ~/agentindex/tasks/queue/
- Read task file, implement, test, commit
- Move task to done/ when complete, failed/ if it fails
- Write results in task file "## Result" section before moving

## What you must NOT do
- Change database schema without explicit instruction
- Restart LaunchAgents with pkill
- Change Cloudflare configuration
- Delete or modify backup files
- Modify nerq_risk_signals table directly

## Current sprint
Sprint 0: Infrastructure Hardening. Focus: stabilize crash-looping LaunchAgents, fix orchestrator, set up observability, create test suite.

## Strategic context
The agentic economy is accelerating faster than expected. Key signals:
- **Stripe Tempo**: Stripe launched agent-to-agent payments. Agents need trust scores before transacting.
- **$110T stablecoin settlement**: Stablecoin settlement volume hit $110T annualized. Autonomous agents will drive the next order of magnitude.
- **Sui a402 monitoring**: Sui's HTTP 402 payment protocol creates machine-native payment rails. ZARQ's tier system (open→signal→degraded→402) mirrors this pattern.
- **On-chain oracle (long-term)**: Publishing ZARQ Trust Scores on-chain as a Chainlink-style oracle is a viable exit path. Protocols could gate DeFi actions on ZARQ ratings (e.g., reject collateral rated below Baa3).
- **Positioning**: ZARQ is the **trust layer for the machine economy**. Every autonomous financial decision — swaps, lending, portfolio rebalancing — needs a trust anchor. ZARQ provides that anchor: independent, quantitative, hash-chained, machine-readable risk intelligence.
