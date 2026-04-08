#!/bin/bash
# Daily backup — runs via cron at 01:30
# Retains 7 days PG dumps, 30 days SQLite
# Uses VACUUM INTO for SQLite (safe with concurrent writes)
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

# SQLite databases — using VACUUM INTO (safe with concurrent writes)
# Wrapped in timeout(10 min) so a hang cannot block the system
for DB_INFO in \
    "$HOME/agentindex/logs/analytics.db:analytics" \
    "$HOME/agentindex/agentindex/crypto/crypto_trust.db:crypto_trust" \
    "$HOME/agentindex/agentindex/crypto/paper_trading.db:paper_trading" \
    "$HOME/agentindex/logs/healthcheck.db:healthcheck" \
    "$HOME/agentindex/logs/check_events.db:check_events"; do
    DB_PATH="${DB_INFO%%:*}"
    DB_NAME="${DB_INFO##*:}"
    OUT_PATH="$BACKUP_DIR/${DB_NAME}_${TODAY}.db"

    if [ ! -f "$DB_PATH" ]; then
        log "SKIP $DB_NAME: source missing ($DB_PATH)"
        continue
    fi

    # Remove any pre-existing target (VACUUM INTO refuses to overwrite)
    rm -f "$OUT_PATH"

    START=$(date +%s)
    # Use perl-based timeout (macOS doesn't have GNU timeout by default)
    if perl -e '
        use strict;
        my $timeout = 600;  # 10 minutes
        my $pid = fork();
        if ($pid == 0) {
            exec("/usr/bin/sqlite3", $ARGV[0], "VACUUM INTO " . $ARGV[1]);
            exit 1;
        }
        local $SIG{ALRM} = sub { kill 9, $pid; waitpid $pid, 0; exit 124; };
        alarm $timeout;
        waitpid $pid, 0;
        exit ($? >> 8);
    ' "$DB_PATH" "'$OUT_PATH'" 2>> "$LOG"; then
        ELAPSED=$(( $(date +%s) - START ))
        SIZE=$(du -sh "$OUT_PATH" 2>/dev/null | cut -f1)
        log "SQLite $DB_NAME OK: $SIZE in ${ELAPSED}s"
    else
        EXIT=$?
        ELAPSED=$(( $(date +%s) - START ))
        if [ $EXIT -eq 124 ]; then
            log "ERROR: SQLite $DB_NAME timed out after ${ELAPSED}s (max 600s)"
        else
            log "ERROR: SQLite $DB_NAME failed with exit $EXIT after ${ELAPSED}s"
        fi
        rm -f "$OUT_PATH"  # remove partial file
    fi
done

# Cleanup
find "$BACKUP_DIR" -name "agentindex_*.sql.gz" -mtime +7 -delete 2>> "$LOG"
find "$BACKUP_DIR" -name "*.db" -mtime +30 -delete 2>> "$LOG"

TOTAL=$(du -sh "$BACKUP_DIR" | cut -f1)
log "=== Backup complete: $TOTAL ==="
