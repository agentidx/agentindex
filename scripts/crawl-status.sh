#!/bin/bash
# crawl-status.sh — Show status of all Nerq crawlers
# Usage: ./scripts/crawl-status.sh

PSQL="/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"
DB="postgresql://localhost/agentindex"
SQLITE="/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db"
LOG="/Users/anstudio/agentindex/logs/crawlers.log"

echo "============================================================"
echo "  Nerq Crawler Status — $(date '+%Y-%m-%d %H:%M')"
echo "============================================================"

echo ""
echo "=== PostgreSQL: Entries by source (new crawler sources) ==="
$PSQL "$DB" -c "
SELECT source, COUNT(*) as total,
       COUNT(*) FILTER (WHERE is_active) as active,
       ROUND(AVG(trust_score_v2)::numeric, 1) as avg_trust,
       MAX(first_indexed)::date as last_indexed
FROM agents
WHERE source IN ('pulsemcp','mcp_registry','agentverse','openrouter','lobehub','erc8004','olas')
GROUP BY source ORDER BY COUNT(*) DESC
" 2>/dev/null

echo ""
echo "=== PostgreSQL: Active totals ==="
$PSQL "$DB" -c "
SELECT agent_type, COUNT(*) as active_count
FROM agents WHERE is_active = true AND agent_type IN ('agent','tool','mcp_server','model')
GROUP BY agent_type ORDER BY COUNT(*) DESC
" 2>/dev/null

echo ""
echo "=== SQLite staging: Entries by source ==="
sqlite3 "$SQLITE" "SELECT source, COUNT(*) as count FROM agent_crypto_profile GROUP BY source ORDER BY count DESC;" 2>/dev/null

echo ""
echo "=== Last crawler run ==="
if [ -f "$LOG" ]; then
    echo "Log file: $LOG"
    echo "Last modified: $(stat -f '%Sm' "$LOG" 2>/dev/null || stat -c '%y' "$LOG" 2>/dev/null)"
    echo ""
    echo "--- Last 20 lines ---"
    tail -20 "$LOG"
else
    echo "No crawler log found at $LOG"
fi

echo ""
echo "=== Cron schedule ==="
crontab -l 2>/dev/null | grep -i 'crawl\|spider\|expansion'

echo ""
echo "=== Errors in last log ==="
if [ -f "$LOG" ]; then
    errors=$(grep -i 'error\|FAILED\|traceback' "$LOG" | tail -10)
    if [ -z "$errors" ]; then
        echo "No errors found."
    else
        echo "$errors"
    fi
fi
