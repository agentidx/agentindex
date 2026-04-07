# Nerq AI Assets Rebrand

## Task
Rebrand Nerq from "4.9M agents" to accurate segmented numbers using "AI Assets" umbrella term.

## Status: DONE

## Result

Rebranded all Nerq-facing content across ~25 files. New terminology:
- **AI assets** = everything (5M+)
- **Agents & tools** = 173K actual agents, tools, MCP servers
- **Models & datasets** = 4.7M HuggingFace entries
- Zero remaining "4.9M agents" in any active served file

### Files updated:
- `agentindex/api/discovery.py` — FastAPI description, comments
- `agentindex/seo_pages.py` — llms.txt generator, agent pages, methodology, best-in-class, footer, citations (12 edits)
- `agentindex/zarq_docs.py` — API docs description
- `agentindex/kya_api.py` — KYA meta + header ("173K agents & tools")
- `agentindex/mcp_server.py`, `mcp_server_v2.py`, `mcp_sse_server.py`, `mcp_sse_server_v2.py` — all MCP tool descriptions
- `agentindex/zarq_dashboard.py` — KPI label "AI Assets", comment
- `agentindex/analytics.py` — comment
- `agentindex/exports/llms.txt`, `llms-full.txt` — Nerq descriptions
- `agentindex/crypto/zarq_mcp_server.py` — KYA tool desc
- `agentindex/crypto/zarq_machine_discovery.py` — apis.json
- `agentindex/crypto/templates/nerq_api_docs.html` — meta, subtitle, stats, footer
- `agentindex/crypto/templates/zarq_landing.html` — KYA card
- `agentindex/crypto/templates/zarq_agent_intelligence.html` — stat label
- `agentindex/templates/checker.html` — badge pill
- `CLAUDE.md`, `agent.md`, `docs/operations-log.md` — project descriptions

### Dynamic count function fixed:
`_agent_count_text()` in seo_pages.py now outputs "5M+" instead of "4.9M+" (changed `.1f` to `.0f` format).

### Verified clean:
- `/agent/{uuid}` pages: no "4.9M"
- `/kya`: shows "173K agents & tools"
- `/docs` (nerq host): shows "5M+ AI assets"
- `/methodology`: clean
- `/llms.txt`: clean
- All MCP server cards: clean
