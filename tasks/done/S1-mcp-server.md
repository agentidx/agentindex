# S1 — MCP Server: Make ZARQ Discoverable

**Date:** 2026-03-07
**Status:** Complete

---

## What Was Built

### 1. Three New MCP Tools Added

Added to `agentindex/crypto/zarq_mcp_server.py`:

| Tool | Purpose | Endpoint Called |
|------|---------|----------------|
| `check_token_risk` | Zero-friction risk check: verdict, trust score, crash probability, DtD | `/v1/check/{token}` |
| `get_risk_signals` | All tokens with active warnings, filterable by level | `/v1/crypto/signals` |
| `get_trust_score` | Score-only view: trust score, rating, risk level, verdict | `/v1/check/{token}` (filtered) |

Total tools now: 11 (was 8).

### 2. Server Version Updated to 1.1.0

Updated all version references:
- `server_version` in both transport configurations
- Server card version
- Health endpoint
- Smithery config
- Token count updated from 198 to 205

### 3. Server Card Made Dynamic

Changed `"tools"` field in server card from hardcoded count to dynamic list:
```python
"tools": [t.name for t in TOOLS]
```

### 4. Nerq MCP Server Fixes

Fixed `agentindex/mcp_sse_server.py`:
- Changed default `API_PORT` from `"8100"` to `"8000"` (was hitting wrong port)
- Added routing for 5 crypto tools (`nerq_crypto_rating`, `nerq_crypto_ndd`, `nerq_crypto_safety`, `nerq_crypto_signals`, `nerq_crypto_compare`) that previously fell through to "Unknown tool"

### 5. MCP Registration Guide

Created `~/agentindex/mcp-registration-guide.md` with:
- Smithery registration URL and required info
- Glama registration URL and required info
- Full manifest/server-card schema
- Cloudflare tunnel configuration details
- Claude Desktop configuration snippet
- Testing commands

---

## Test Results

### Unit Tests
```
40 passed, 81 warnings in 41.24s
```
No regressions.

### MCP Tool Tests (via Streamable HTTP at mcp.zarq.ai)

**check_token_risk(bitcoin):**
```json
{"token": "bitcoin", "verdict": "WARNING", "trust_score": 74.52, "rating": "A2",
 "distance_to_default": 3.03, "crash_probability": 0.3177, "price_usd": 70825.0}
```

**get_trust_score(ethereum):**
```json
{"token": "ethereum", "trust_score": 73.12, "rating": "A2", "risk_level": "WATCH", "verdict": "SAFE"}
```

**get_risk_signals():** Returns 500 from underlying `/v1/crypto/signals` endpoint — pre-existing bug, not caused by MCP changes.

### Public Endpoint Verification
- `https://mcp.zarq.ai/health` → `{"status":"ok","server":"zarq-crypto","version":"1.1.0"}`
- `https://mcp.zarq.ai/.well-known/mcp/server-card.json` → Full server card with 11 tools
- `tools/list` via JSON-RPC → 11 tools listed
- `tools/call` via JSON-RPC → Working (check_token_risk, get_trust_score confirmed)

---

## Files Modified

| File | Change |
|------|--------|
| `agentindex/crypto/zarq_mcp_server.py` | +3 tools, version 1.1.0, dynamic server card, 205 tokens |
| `agentindex/mcp_sse_server.py` | Fixed API_PORT, added crypto tool routing |
| `mcp-registration-guide.md` | New: Smithery/Glama/Cloudflare registration guide |

## Known Issue

`/v1/crypto/signals` returns HTTP 500 — pre-existing bug unrelated to this sprint. The `get_risk_signals` tool correctly surfaces this as an error message to the MCP client.
