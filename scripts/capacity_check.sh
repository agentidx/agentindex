#!/bin/bash
# Nerq capacity monitoring — runs via LaunchAgent at 07:00 and 19:00
# Logs to ~/agentindex/logs/capacity.log

HOME_DIR=$(eval echo ~)
LOGFILE="${HOME_DIR}/agentindex/logs/capacity.log"
PSQL="/opt/homebrew/opt/postgresql@16/bin/psql"
DB="${HOME_DIR}/agentindex/logs/analytics.db"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M")

# Create header if file doesn't exist
if [ ! -f "$LOGFILE" ]; then
    echo "timestamp,requests_24h,p50_ms,p95_ms,error_pct,load_avg,pg_connections,enriched,disk_pct,ai_citations" > "$LOGFILE"
fi

# Requests 24h
REQ_24H=$(sqlite3 "$DB" "SELECT COUNT(*) FROM requests WHERE ts >= datetime('now', '-24 hours');" 2>/dev/null || echo "0")

# Latency (P50/P95 for /safe/* only — our core product pages)
P50=$(sqlite3 "$DB" "SELECT COALESCE(duration_ms, 0) FROM requests WHERE ts >= datetime('now', '-1 hour') AND status = 200 AND duration_ms > 0 AND path LIKE '/safe/%' ORDER BY duration_ms LIMIT 1 OFFSET (SELECT COUNT(*)/2 FROM requests WHERE ts >= datetime('now', '-1 hour') AND status = 200 AND duration_ms > 0 AND path LIKE '/safe/%');" 2>/dev/null || echo "0")
P95=$(sqlite3 "$DB" "SELECT COALESCE(duration_ms, 0) FROM requests WHERE ts >= datetime('now', '-1 hour') AND status = 200 AND duration_ms > 0 AND path LIKE '/safe/%' ORDER BY duration_ms LIMIT 1 OFFSET (SELECT COUNT(*)*95/100 FROM requests WHERE ts >= datetime('now', '-1 hour') AND status = 200 AND duration_ms > 0 AND path LIKE '/safe/%');" 2>/dev/null || echo "0")

# Error rate
ERRORS=$(sqlite3 "$DB" "SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1), 0) FROM requests WHERE ts >= datetime('now', '-24 hours');" 2>/dev/null || echo "0")

# System load
LOAD=$(uptime | grep -oE 'load averages?: [0-9.]+' | grep -oE '[0-9.]+$' || echo "0")

# PostgreSQL connections
PG_CONN=$($PSQL -d agentindex -tAc "SELECT COUNT(*) FROM pg_stat_activity;" 2>/dev/null || echo "0")

# Enriched entities
ENRICHED=$($PSQL -d agentindex -tAc "SELECT COUNT(enriched_at) FROM software_registry;" 2>/dev/null || echo "0")

# Disk usage
DISK_PCT=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')

# AI citations
CITATIONS=$(sqlite3 "$DB" "SELECT COALESCE(SUM(CASE WHEN is_ai_bot=1 AND status=200 THEN 1 ELSE 0 END), 0) FROM requests WHERE ts >= datetime('now', '-24 hours');" 2>/dev/null || echo "0")

# Log
echo "$TIMESTAMP,$REQ_24H,$P50,$P95,$ERRORS,$LOAD,$PG_CONN,$ENRICHED,$DISK_PCT,$CITATIONS" >> "$LOGFILE"

# Alerts
ALERT_FILE="${LOGFILE%.log}_alerts.log"
if [ "$P95" -gt 1000 ] 2>/dev/null; then
    echo "$TIMESTAMP ALERT: P95 ${P95}ms > 1000ms" >> "$ALERT_FILE"
fi
if [ "${LOAD%%.*}" -gt 15 ] 2>/dev/null; then
    echo "$TIMESTAMP ALERT: Load $LOAD > 15" >> "$ALERT_FILE"
fi
if [ "$DISK_PCT" -gt 80 ] 2>/dev/null; then
    echo "$TIMESTAMP ALERT: Disk ${DISK_PCT}% > 80%" >> "$ALERT_FILE"
fi
