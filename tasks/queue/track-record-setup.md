# GitHub Track Record Repo Setup

**Date:** 2026-03-08
**Status:** Complete — awaiting repo creation by Anders

---

## Created

### 1. `scripts/push-track-record.sh`
Automated script that:
- Reads latest entry from `track-record/daily-signals.jsonl`
- Extracts date, hash, warning count
- Clones/updates `zarq-ai/track-record` repo
- Writes daily JSON file to `signals/2026/YYYY-MM-DD.json`
- Copies master JSONL to `signals/daily-signals.jsonl`
- Commits with date, warning count, SHA-256 hash in message
- Pushes to GitHub

### 2. `track-record/README.md`
Explains:
- What: daily SHA-256 hash-chained risk signals for 205 tokens
- How to verify: Python script to recompute hash and compare
- Why: no hindsight bias, immutable, publicly verifiable from day 1
- Stats: coverage, start date, OOS performance
- Links: API, docs, Smithery, PyPI, npm

## GitHub Org Status

`zarq-ai` org **exists** on GitHub with 1 repo (`zarq-mcp-server`). Logged in as `kbanilsson-pixel`.

## Action Required (Anders)

Create the track-record repo:
```bash
gh repo create zarq-ai/track-record --public --description "ZARQ daily risk signals — SHA-256 hash-chained, publicly verifiable"
```

Then run the push script:
```bash
cd ~/agentindex && bash scripts/push-track-record.sh
```

### Optional: Add to daily cron
After the existing track record cron at 01:00:
```bash
# In crontab -e, add after the daily_track_record.py line:
15 1 * * * /bin/bash /Users/anstudio/agentindex/scripts/push-track-record.sh >> /tmp/push-track-record.log 2>&1
```

## Data Status
- 1 entry in `daily-signals.jsonl` (2026-03-07)
- Hash: `fd8574ac0258c070317e6c1ec1d76b57e9d76d6693826fdae46a7f0e64327831`
- 205 tokens, 75 warnings
