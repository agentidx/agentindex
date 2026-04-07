#!/bin/bash
# Daily backup — runs via cron at 01:30
# Retains 7 days PG dumps, 30 days SQLite
set -e
BACKUP_DIR="$HOME/backups/daily"
LOG="$HOME/agentindex/logs/backup.log"
PSQL="/opt/homebrew/Cellar/postgresql@16/16.11_1/bin"
TODAY=$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

log "=== Daily backup starting ==="

# PostgreSQL
if PGOPTIONS='-c statement_timeout=0 -c application_name=nerq_backup' $PSQL/pg_dump -U anstudio -d agentindex --compress=9 \
    --file="$BACKUP_DIR/agentindex_${TODAY}.sql.gz" 2>> "$LOG"; then
    SIZE=$(du -sh "$BACKUP_DIR/agentindex_${TODAY}.sql.gz" | cut -f1)
    log "PostgreSQL OK: $SIZE"
else
    log "ERROR: PostgreSQL dump failed!"
fi

# SQLite databases
for DB_INFO in \
    "$HOME/agentindex/logs/analytics.db:analytics" \
    "$HOME/agentindex/agentindex/crypto/crypto_trust.db:crypto_trust" \
    "$HOME/agentindex/agentindex/crypto/paper_trading.db:paper_trading" \
    "$HOME/agentindex/logs/healthcheck.db:healthcheck" \
    "$HOME/agentindex/logs/check_events.db:check_events"; do
    DB_PATH="${DB_INFO%%:*}"
    DB_NAME="${DB_INFO##*:}"
    if [ -f "$DB_PATH" ]; then
        if sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/${DB_NAME}_${TODAY}.db'" 2>> "$LOG"; then
            log "SQLite $DB_NAME OK"
        else
            log "ERROR: SQLite $DB_NAME failed!"
        fi
    fi
done

# Cleanup
find "$BACKUP_DIR" -name "agentindex_*.sql.gz" -mtime +7 -delete 2>> "$LOG"
find "$BACKUP_DIR" -name "*.db" -mtime +30 -delete 2>> "$LOG"

TOTAL=$(du -sh "$BACKUP_DIR" | cut -f1)
log "=== Backup complete: $TOTAL ==="
