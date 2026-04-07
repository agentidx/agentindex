#!/bin/bash
# King re-enrichment — runs weekly (Sundays 04:00) via LaunchAgent
# Bumps dateModified for all Kings to signal freshness to AI bots

PSQL="/opt/homebrew/opt/postgresql@16/bin/psql"
LOGFILE="$HOME/agentindex/logs/king_refresh.log"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M")

echo "$TIMESTAMP Starting King refresh" >> "$LOGFILE"

# Bump enriched_at for all Kings (signals freshness)
UPDATED=$($PSQL -d agentindex -tAc "
SET statement_timeout = '120s';
UPDATE software_registry SET enriched_at = NOW()
WHERE is_king = true AND enriched_at IS NOT NULL;
SELECT COUNT(*) FROM software_registry WHERE is_king AND enriched_at >= NOW() - INTERVAL '1 minute';
" 2>/dev/null || echo "0")

echo "$TIMESTAMP King refresh complete: $UPDATED Kings refreshed" >> "$LOGFILE"

# Flush page cache so fresh pages are served
/opt/homebrew/bin/redis-cli -n 1 FLUSHDB > /dev/null 2>&1
echo "$TIMESTAMP Page cache flushed" >> "$LOGFILE"
