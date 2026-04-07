#!/bin/bash
# Analytics DB retention — runs daily at 03:15 via cron
# Deletes rows older than retention period based on DB size
# VACUUM to reclaim space

DB="$HOME/agentindex/logs/analytics.db"
LOG="$HOME/agentindex/logs/analytics_retention.log"

if [ ! -f "$DB" ]; then exit 0; fi

SIZE_GB=$(du -k "$DB" | awk '{printf "%.1f", $1/1048576}')

# Aggressive retention: 30d if >5GB, 45d if >3GB, 60d otherwise
if (( $(echo "$SIZE_GB > 5" | bc -l) )); then
    DAYS=30
elif (( $(echo "$SIZE_GB > 3" | bc -l) )); then
    DAYS=45
else
    DAYS=60
fi

BEFORE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM requests;")
sqlite3 "$DB" "DELETE FROM requests WHERE ts < datetime('now', '-${DAYS} days');"
DELETED=$?
AFTER=$(sqlite3 "$DB" "SELECT COUNT(*) FROM requests;")
REMOVED=$((BEFORE - AFTER))

if [ "$REMOVED" -gt 0 ]; then
    sqlite3 "$DB" "PRAGMA incremental_vacuum(5000);"
    echo "$(date '+%Y-%m-%d %H:%M') Retention: deleted $REMOVED rows (>${DAYS}d), DB ${SIZE_GB}GB, $BEFORE→$AFTER rows" >> "$LOG"
fi

# Also clean preflight_analytics
sqlite3 "$DB" "DELETE FROM preflight_analytics WHERE ts < datetime('now', '-${DAYS} days');" 2>/dev/null
