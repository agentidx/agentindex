# Fix Adoption Triggers Card — Strict Filtering

**Date:** 2026-03-08
**Status:** Complete

---

## Problem
Adoption metrics were inflated by bots, scanners, and internal traffic. Raw count showed 45 /v1/check calls but most were bots.

## Changes

### 1. Strict IP Exclusion (`_get_excluded_ips`)
Now excludes:
- `127.0.0.1` + testclient (hardcoded hashes)
- Any IP that accessed `/zarq/dashboard`, `/zarq/dashboard/data`, `/internal/metrics` (that's us)
- Any IP with >1000 calls/day (scanner/bot)
- Any IP that probed WordPress/scanner endpoints (`wp-admin`, `wp-includes`, `wlwmanifest`, `setup-config`, `.env`, `.git`, `xmlrpc`)

Result: 18 IPs excluded (was 2)

### 2. Bot UA Filtering (`BOT_UA_PATTERNS`)
Added to exclusion list:
- Social bots: `twitterbot`, `linkedinbot`, `discordbot`, `slackbot`, `whatsapp`
- Disguised Googlebot: `nexus 5x` (Googlebot mobile user agent)
- All patterns applied to /v1/check queries AND recurring integration counts

### 3. Dashboard Card Updated
- **Targets table**: shows Current | Week 1 Target | Week 2 Target | Status emoji
- **Raw vs Filtered note**: "Raw: 180 | After filtering: 26"
- **Days since launch counter**: Day 1 (from 2026-03-08)
- **Verdicts** based on FILTERED data only
- Overall pill: TRACTION / EARLY SIGNAL / NO SIGNAL YET

### 4. Current Numbers (Day 1, filtered)
```
Raw /v1/check 24h: 180
Filtered 24h:      26  (real browser users clicking shared links)
Human check IPs:   24
Recurring:          4  (IPs with ≥10 non-bot calls in 7d)
Excluded IPs:      18
```

## Files Modified
- `agentindex/zarq_dashboard.py`

## Verification
- Local: 200
- Tunnel: 200
