# Citation Dashboard Launched — 2026-04-13

**URL:** `/citation-dashboard`
**File:** `agentindex/citation_dashboard.py`
**Mounted in:** `discovery.py:1381-1382`

## What it shows

| Section | Content |
|---|---|
| 1. User-Triggered Citations | Daily volume per bot (ChatGPT-User, Perplexity-User, etc.), 7d rolling avg, concentration risk widget |
| 2. Search-Index Crowd | OAI-SearchBot, Applebot, etc. + index→citation conversion ratios |
| 3. Active Pilots | /was-X-hacked progress bar (0/50), freshness pipeline status, M5.1 countdown |
| 4. Growth Trajectory | ChatGPT-User full history with 7d rolling avg |
| 5. Known Unknowns | ClaudeBot value, manual verification, data depth — explicitly shown |
| 6. AI Referral Traffic | Google/ChatGPT/Perplexity referrals with low-volume caveats |

## What it does NOT show

- No "total AI citations" that mixes training + user_triggered
- No human visit counts (known to be 3-30x overcounted)
- No vanity metrics

## Technical

- Pure HTML + inline SVG charts (no external JS/CDN)
- 5-minute cache
- Mobile-friendly
- ~20 KB rendered
- Linked from flywheel and analytics dashboards
