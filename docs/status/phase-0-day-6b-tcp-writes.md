# Phase 0 Day 6b — Write-Path Switched to TCP

Date: 2026-04-14
Status: COMPLETE — all writes use TCP via Tailscale, zero errors

## Changes

### pg_hba.conf (Mac Studio)

Added Tailscale mesh access:
```
host all anstudio 100.64.0.0/10 trust
host replication anstudio 100.64.0.0/10 trust
```
Reloaded (not restarted).

### Code changes

| File | Before | After |
|---|---|---|
| dual_write.py | `host=/tmp` (hardcoded socket) | `ZARQ_PG_DSN` env var, default TCP 100.90.152.88 |
| dual_read.py | `host=/tmp` (hardcoded fallback) | Default TCP 100.90.152.88 |

### LaunchAgents updated (15 total)

**Dual-write plists (10) — added ZARQ_PG_DSN + DATABASE_URL:**
com.nerq.crypto-daily, community-signals, compat-matrix, dashboard-data,
dex-volumes, openssf-crawler, osv-crawler, com.zarq.vitality-recalc,
vitality-report, mcp-sse

**DATABASE_URL plists (5) — localhost → TCP:**
com.nerq.chrome-users, firefox-users, go-github-stars, npm-bulk-enricher,
nuget-downloads

All backups at `~/Library/LaunchAgents/.bak-day6b/`.

## Verification

| Check | Result |
|---|---|
| API /safe/nordvpn | 200 ✅ |
| Replication Nbg | streaming, 0 lag ✅ |
| Replication Hel | streaming, 0 lag ✅ |
| dual_write_errors.log | 0 lines ✅ |
| TCP via Tailscale (psql -h 100.90.152.88) | SELECT 1 OK ✅ |

## Why this matters for Day 6c

When Nbg becomes primary, only the DSN value changes:
- `100.90.152.88` (Mac Studio) → `100.119.193.70` (Nbg)

No code changes needed. Just update env vars in LaunchAgent plists.

## Rollback

```bash
# Restore plists
cp ~/Library/LaunchAgents/.bak-day6b/* ~/Library/LaunchAgents/
for f in ~/Library/LaunchAgents/com.nerq.*.plist ~/Library/LaunchAgents/com.zarq.*.plist; do
  launchctl unload "$f" 2>/dev/null; launchctl load "$f" 2>/dev/null
done

# Code reverts via git
git revert HEAD  # reverts dual_write.py + dual_read.py
```
