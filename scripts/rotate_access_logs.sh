#!/bin/bash
# Rotate raw access logs — 14-day retention
# Run daily via cron or LaunchAgent

LOG_DIR="$HOME/agentindex/logs"
ACCESS_LOG="$LOG_DIR/access_raw.log"
RETENTION_DAYS=14

# Rotate: rename current log with date stamp
if [ -f "$ACCESS_LOG" ]; then
    DATE=$(date +%Y-%m-%d)
    mv "$ACCESS_LOG" "$ACCESS_LOG.$DATE"
    # Signal uvicorn workers to reopen file handles
    kill -USR1 $(pgrep -f "uvicorn.*discovery:app") 2>/dev/null || true
fi

# Delete old logs
find "$LOG_DIR" -name "access_raw.log.*" -mtime +$RETENTION_DAYS -delete

echo "$(date): rotated, $(find "$LOG_DIR" -name 'access_raw.log.*' | wc -l) archives kept"
