# Dashboard Adoption Triggers + Distribution Channels

**Date:** 2026-03-08
**Status:** Complete

---

## TASK 1: Adoption Triggers Dashboard Card

Added a new prominent card at the TOP of `/zarq/dashboard` with gold border and gradient header.

### Data Function: `_adoption_triggers()`
Queries `zarq_api_log.db` with internal IP filtering (`127.0.0.1` + testclient excluded):

- **External /v1/check calls** (24h and 7d)
- **New unique IPs** calling /v1/check this week
- **Recurring integrations** (IPs with ≥10 calls in 7d, excluding Meta bot)
- **AI bot crawls today** (Claude, ChatGPT, Perplexity, Google)
- **Days live** (since 2026-03-07)
- **Auto-calculated verdicts** (week1 and week2 decisions)

### Card Layout (2-column)
**Left column:**
- External check counts (24h/7d) — green/red colored
- Unique check IPs — green/red
- Recurring integration count — green/red
- AI bot breakdown

**Right column:**
- Registration statuses (Smithery: LIVE, Glama: PENDING, LangChain Forum: POSTED)
- 1 Week Decision box (auto: signal vs no signal)
- 2 Week Decision box (auto: wedge working vs pivot)

### Overall Pill
- GREEN "TRACTION" — if check calls + recurring ≥1
- YELLOW "EARLY SIGNAL" — if check calls but no recurring
- RED "NO SIGNAL" — if no external check calls

### Current Data
```json
{
  "check_24h": 45,
  "check_7d": 45,
  "new_check_ips_7d": 34,
  "recurring_count": 27,
  "ai_bots_today": {"Claude": 11, "ChatGPT": 13, "Perplexity": 88, "Google": 167},
  "days_live": 1,
  "week1_verdict": "signal",
  "week2_verdict": "wedge_working"
}
```

### Files Modified
- `agentindex/zarq_dashboard.py` — added `_adoption_triggers()`, HTML card, JS renderer

### Verification
- Local: 200
- Tunnel: 200
- Tests: 111 passed, 4 deselected

---

## TASK 2: Distribution Channels

Created `docs/distribution-channels.md` with 8 ready-to-submit channels:

1. **awesome-mcp-servers** — PR text ready (markdown entry + PR body)
2. **awesome-langchain** — PR text ready
3. **MCP.so** — submission details ready
4. **Product Hunt** — full launch post drafted (name, tagline, description, maker comment)
5. **Hacker News Show HN** — title + body ready to post
6. **Dev.to / Hashnode** — full blog post: "How to add pre-trade risk scoring to your LangChain crypto agent in 2 lines"
7. **X/Twitter DMs** — 10 agent builder accounts listed with handles and DM template
8. **CoinGecko ecosystem** — 5-step path documented

Priority table included with effort/impact estimates.
