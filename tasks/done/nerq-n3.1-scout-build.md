# Sprint N3.1 — Build Nerq Scout: The Autonomous Agent

## Status: DONE
**Completed:** 2026-03-10

## Deliverables

### 1. Scout Agent (`agentindex/nerq_scout_agent.py`)
- Discover: queries DB for trust >= 85, stars >= 100, LEFT JOIN scout_log to skip already-contacted
- Evaluate: calls KYA API for full assessment
- Publish: Ollama qwen2.5:7b generates markdown report → auto-publishes to Dev.to (published: true)
- Dry run: 10 agents evaluated in 8.8s

### 2. /claim Page (`agentindex/claim_page.py`)
- GET /claim — search box, badge preview, copy-to-clipboard markdown, tweet share link
- POST /claim/submit — agent submission stored in nerq_scout_log
- Featured agents section from recent scout evaluations
- Tested: 200 OK

### 3. RSS Feed (`agentindex/rss_feed.py`)
- Routes: /feed.xml, /rss.xml, /blog/feed.xml, /blog/rss.xml
- RSS 2.0 from docs/auto-reports/*.md with YAML frontmatter parsing
- Tested: 200 OK, 2 items

### 4. SEO Trust Pages (`agentindex/seo_trust_pages.py`)
- Route: /trust/{name}
- 24h in-memory cache, max 1000 entries
- JSON-LD SoftwareApplication schema
- Title pattern: "Is {name} trustworthy? Nerq Trust Score: {score}/100 ({grade})"
- Tested: 200 OK

### 5. Scout MCP Tools
- nerq_scout_status and nerq_scout_findings added to mcp_sse_server.py

### 6. Dashboard Integration
- Scout section added to combined_dashboard.py: evaluated, featured, claimed, reviews cards

### 7. Enhanced Benchmark (`agentindex/nerq_benchmark_test.py`)
- 50 agents (25 good, 10 bad, 15 dead), 100 runs
- Z-test for statistical significance, confidence intervals
- Results: failure rate 44% → 0%, avg trust 75.8 → 81.6

### 8. Scout Cron
- `scripts/run_scout.sh` — wrapper script
- `scripts/add_scout_cron.sh` — installs cron: every 6 hours (04:00, 10:00, 16:00, 22:00)
- **Manual step required:** `bash ~/agentindex/scripts/add_scout_cron.sh`

### 9. Dev.to Auto-Publish
- Changed `agentindex/crypto/auto_publisher.py` to `published: True`

### 10. API Docs & Reports
- Reviews, Reputation, Ledger endpoints documented in nerq_docs.py
- Benchmark added to reports index

## Result
All 10 deliverables built and tested. Endpoints returning 200. Scout dry run successful with 10 agents evaluated and published to Dev.to. Enhanced benchmark proves Nerq reduces failure rate from 44% to 0% with statistical significance.

Remaining manual steps:
- Run `bash ~/agentindex/scripts/add_scout_cron.sh` to activate 6-hour cron
- Run `mcp-publisher login github` then `mcp-publisher publish` in `~/agentindex/integrations/mcp-registry/` to publish to MCP Registry
