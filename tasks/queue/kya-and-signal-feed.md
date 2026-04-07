# KYA + Signal Feed — Two Major Features

**Date:** 2026-03-08
**Status:** Complete

---

## TASK 1: KYA — Know Your Agent

### API Endpoint
`GET /v1/agent/kya/{name_or_id}` — Zero auth, zero rate limit, 5min cache.

**Response:**
```json
{
  "agent_id": "uuid",
  "agent_name": "autogpt",
  "description": "...",
  "platform": "github",
  "category": "coding",
  "trust_score": 53.7,
  "trust_grade": "D",
  "compliance_score": 100.0,
  "eu_risk_class": "minimal",
  "risk_level": "CAUTION",
  "days_active": 14,
  "stars": 1234,
  "zarq_risk_check": null,
  "verdict": "This agent has been indexed for 14 days with a trust score of 54/100 [CAUTION]."
}
```

**Risk Level Logic:**
- TRUSTED: trust_score >= 60 AND compliance_score >= 40
- CAUTION: trust_score >= 35
- UNTRUSTED: trust_score < 35

**Agent Lookup:** UUID exact match, then name exact (case-insensitive), then ILIKE fuzzy.
**Trust Score:** Uses COALESCE(trust_score_v2, trust_score) to get best available score.
**ZARQ Cross-reference:** If agent name contains crypto keywords, includes ZARQ risk data.

### HTML Page
- `/kya` — Search page with input box
- `/kya/{name}` — Pre-loaded report
- `/know-your-agent` — Alias
- ZARQ design (DM Serif Display, warm palette)
- OpenGraph meta tags for sharing
- Auto-loads report from URL path

### MCP Tool
`kya_check_agent(agent)` — Added to MCP server, available via mcp.zarq.ai

### Test Results
```
crewai: trust=64.5, grade=C, risk=TRUSTED
langchain: trust=54.5, grade=D, risk=CAUTION
autogpt: trust=53.7, grade=D, risk=CAUTION
```

## TASK 2: The ZARQ Signal — Predictive Feed

### API Endpoints

**`GET /v1/signal/feed`** — Live feed, 5min cache.
```json
{
  "signal_date": "2026-03-08",
  "summary": {
    "total_tokens_monitored": 205,
    "active_warnings": 47,
    "active_criticals": 24,
    "safe_tokens": 134,
    "new_signals_24h": 1,
    "resolved_24h": 1,
    "market_risk_summary": "24 tokens in structural collapse, 47 in stress, 134 stable"
  },
  "signals": [...],
  "new_signals_24h": [...],
  "resolved_24h": [...]
}
```

Each signal: token_id, name, symbol, verdict, risk_level, trust_score, rating, crash_probability, distance_to_default, structural_weakness, drawdown_90d, price_change_24h/7d, in_collapse, is_new.

**`GET /v1/signal/feed/history?days=30`** — Daily snapshots with token counts, avg trust, avg NDD.

**`GET /v1/signal/subscribe`** — Info endpoint.
**`POST /v1/signal/subscribe`** — Register email/webhook (stores in signal_subscribers table, no notifications sent yet).

### HTML Page
- `/signal` and `/zarq-signal` — Live dashboard
- Auto-refreshes every 60s
- Filterable by severity (All/Critical/Warning/Safe)
- Summary cards: tokens monitored, criticals, warnings, stable, new/resolved
- Risk summary bar
- Signal table: token, verdict, trust, rating, DtD, crash %, 24h change
- NEW badge on signals that changed severity
- COLLAPSE badge on structurally collapsed tokens
- ZARQ design (DM Serif Display, warm palette)
- OpenGraph meta tags

### MCP Tool
`get_signal_feed()` — Added to MCP server, available via mcp.zarq.ai

## Integration Updates

### Files Created
- `agentindex/kya_api.py` — KYA endpoint + HTML page
- `agentindex/signal_feed.py` — Signal feed endpoints + HTML page

### Files Modified
- `agentindex/api/discovery.py` — Mounted router_kya and router_signal
- `agentindex/crypto/zarq_mcp_server.py` — Added 2 new tools (13 total)
- `agentindex/zarq_docs.py` — Added KYA + Signal sections to endpoints table
- `agentindex/exports/llms.txt` — Added KYA + Signal endpoints and pages
- `docs/operations-log.md` — Updated with all changes

### Verification
- All endpoints: 200 locally and via Cloudflare tunnel
- MCP server: 13 tools (was 11)
- Tests: 115 passed, 0 failed
- Pages: /kya, /kya/autogpt, /signal all render correctly
