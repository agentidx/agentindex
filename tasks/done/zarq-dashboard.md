# ZARQ Operations Dashboard

**Date:** 2026-03-08
**Status:** Complete — 85/85 tests passing

---

## Overview

Single-page operations dashboard at `/zarq/dashboard` for founder monitoring. Shows real-time operational data across 6 sections with ZARQ design language, 60-second auto-refresh, and bearer token authentication.

## Route & Auth

- **HTML Dashboard:** `GET /zarq/dashboard` — full dashboard page
- **JSON Data API:** `GET /zarq/dashboard/data` — raw data for programmatic access
- **Auth:** Bearer token (`ZARQ_METRICS_TOKEN`) or `?token=...` query param
- Unauthorized requests return 401

## Sections

### 1. KPI Bar (top)
- Tokens Rated, Agents Indexed, Requests (24h), Crash Shield Saves, P50 Latency

### 2. System Health
- LaunchAgent status (nerq_api, zarq_mcp, nerq_mcp) with running/loaded/not loaded indicators
- Redis connectivity (PONG check)
- PostgreSQL status + agent count
- Circuit breaker states (from circuit_breaker module)
- Disk usage (total/used/free GB + percentage)

### 3. API Traffic (24h)
- Requests (1h / 24h), unique IPs, P50/P95 latency, error rate
- Hourly bar chart visualization
- Top 10 endpoints table
- Tier distribution (open/signal/degraded/blocked)

### 4. ZARQ Risk Intelligence
- Tokens rated, latest run date
- Active warnings and critical alerts
- Crash Shield saves count + max save drop
- Investment grade vs speculative distribution

### 5. Nerq Agent Index
- Total agents, new (24h), trust-scored count
- Top 8 categories

### 6. Sprint Progress
- Tasks in queue/done/failed with counts
- Task list with color-coded status indicators

### 7. Paper Trading NAVs
- ALPHA, DYNAMIC, CONSERVATIVE portfolio NAVs
- Color-coded (green if > 100, red if < 100)

## Design

- ZARQ design language: DM Serif Display, DM Sans, JetBrains Mono
- Color palette: --warm (#c2956b), green/red/yellow indicators
- Responsive grid layout (2-column desktop, 1-column mobile)
- Light theme with card-based layout
- Auto-refresh every 60 seconds via `setInterval`
- No external JS dependencies

## Files

| File | Change |
|------|--------|
| `agentindex/zarq_dashboard.py` | New: dashboard data collection + HTML rendering |
| `agentindex/api/discovery.py` | Mount `router_dashboard` |
| `tests/test_api_basic.py` | +10 tests for dashboard auth, HTML, data, sections |

## Test Results

```
85 passed, 143 warnings in 76.60s
```

New tests (+10):
- `TestZARQDashboard::test_dashboard_requires_auth`
- `TestZARQDashboard::test_dashboard_returns_html_with_auth`
- `TestZARQDashboard::test_dashboard_has_title`
- `TestZARQDashboard::test_dashboard_has_sections`
- `TestZARQDashboard::test_dashboard_token_query_param`
- `TestZARQDashboard::test_dashboard_data_requires_auth`
- `TestZARQDashboard::test_dashboard_data_returns_json`
- `TestZARQDashboard::test_dashboard_data_has_launchagents`
- `TestZARQDashboard::test_dashboard_data_has_disk`
- `TestZARQDashboard::test_dashboard_auto_refresh`

## Live Verification

- `GET /zarq/dashboard` → 401 without auth, 200 with auth
- `GET /zarq/dashboard/data` → JSON with all 5 data sections
- Real data: 28,364 requests/24h, 390 unique IPs, 4.9M agents, 205 tokens rated
- LaunchAgents: nerq_api running, zarq_mcp running
- Redis: connected, PostgreSQL: ok
- Disk: 210.1/1858.2 GB used (11.3%)
