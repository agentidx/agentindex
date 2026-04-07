#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# ZARQ + Nerq — Backup to External Disk
# ═══════════════════════════════════════════════════════════════
# Usage: ./backup-to-disk.sh /Volumes/BACKUP
# Backs up: SQLite DBs, PostgreSQL (compressed), code, LaunchAgents, docs
#
set -euo pipefail

MOUNT="${1:-}"
if [ -z "$MOUNT" ]; then
    echo "Usage: $0 /Volumes/BACKUP"
    exit 1
fi

if [ ! -d "$MOUNT" ]; then
    echo "ERROR: Mount point $MOUNT does not exist"
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$MOUNT/zarq-backup-$TIMESTAMP"
mkdir -p "$BACKUP_DIR"

echo "═══════════════════════════════════════════"
echo "  ZARQ + Nerq Backup — $TIMESTAMP"
echo "  Target: $BACKUP_DIR"
echo "═══════════════════════════════════════════"
echo ""

# ── 1. SQLite databases ──────────────────────────
echo "[1/5] SQLite databases..."
mkdir -p "$BACKUP_DIR/sqlite"

CRYPTO_DB="$HOME/agentindex/agentindex/crypto/crypto_trust.db"
API_LOG_DB="$HOME/agentindex/agentindex/crypto/zarq_api_log.db"

if [ -f "$CRYPTO_DB" ]; then
    echo "  Copying crypto_trust.db..."
    cp "$CRYPTO_DB" "$BACKUP_DIR/sqlite/"
    echo "  $(du -h "$BACKUP_DIR/sqlite/crypto_trust.db" | cut -f1)"
fi

if [ -f "$API_LOG_DB" ]; then
    echo "  Copying zarq_api_log.db..."
    cp "$API_LOG_DB" "$BACKUP_DIR/sqlite/"
    echo "  $(du -h "$BACKUP_DIR/sqlite/zarq_api_log.db" | cut -f1)"
fi

# ── 2. PostgreSQL dump (compressed) ──────────────
echo ""
echo "[2/5] PostgreSQL dump (compressed)..."
mkdir -p "$BACKUP_DIR/postgres"

PG_DUMP=$(which pg_dump 2>/dev/null || echo "/opt/homebrew/bin/pg_dump")
if [ -x "$PG_DUMP" ]; then
    echo "  Dumping agentindex database..."
    $PG_DUMP -Fc -Z6 -d agentindex -f "$BACKUP_DIR/postgres/agentindex.dump" 2>/dev/null || {
        echo "  WARNING: pg_dump failed, trying without compression..."
        $PG_DUMP -d agentindex | gzip > "$BACKUP_DIR/postgres/agentindex.sql.gz" 2>/dev/null || {
            echo "  ERROR: pg_dump failed entirely. Skipping PostgreSQL backup."
        }
    }
    if [ -f "$BACKUP_DIR/postgres/agentindex.dump" ]; then
        echo "  $(du -h "$BACKUP_DIR/postgres/agentindex.dump" | cut -f1)"
    elif [ -f "$BACKUP_DIR/postgres/agentindex.sql.gz" ]; then
        echo "  $(du -h "$BACKUP_DIR/postgres/agentindex.sql.gz" | cut -f1)"
    fi
else
    echo "  WARNING: pg_dump not found. Skipping PostgreSQL backup."
fi

# ── 3. Code (tar, excluding venv and caches) ─────
echo ""
echo "[3/5] Code archive..."
mkdir -p "$BACKUP_DIR/code"

echo "  Archiving agentindex repo..."
tar czf "$BACKUP_DIR/code/agentindex.tar.gz" \
    -C "$HOME" \
    --exclude='agentindex/venv' \
    --exclude='agentindex/.venv' \
    --exclude='agentindex/__pycache__' \
    --exclude='agentindex/**/__pycache__' \
    --exclude='agentindex/node_modules' \
    --exclude='agentindex/*.db' \
    --exclude='agentindex/crash_analysis_*' \
    --exclude='agentindex/semantic_index' \
    agentindex/ 2>/dev/null || echo "  WARNING: Some files could not be archived"

echo "  $(du -h "$BACKUP_DIR/code/agentindex.tar.gz" | cut -f1)"

# ── 4. LaunchAgents ──────────────────────────────
echo ""
echo "[4/5] LaunchAgents..."
mkdir -p "$BACKUP_DIR/launchagents"

for plist in "$HOME/Library/LaunchAgents"/com.nerq.*.plist "$HOME/Library/LaunchAgents"/com.zarq.*.plist; do
    if [ -f "$plist" ]; then
        cp "$plist" "$BACKUP_DIR/launchagents/"
        echo "  $(basename "$plist")"
    fi
done

# ── 5. Key docs ──────────────────────────────────
echo ""
echo "[5/5] Documentation..."
mkdir -p "$BACKUP_DIR/docs"

for doc in CLAUDE.md agent.md README.md OPERATIONSPLAN.md SYSTEM_ARCHITECTURE.md; do
    src="$HOME/agentindex/$doc"
    if [ -f "$src" ]; then
        cp "$src" "$BACKUP_DIR/docs/"
    fi
done

# Also back up .env (encrypted reference only)
if [ -f "$HOME/agentindex/.env" ]; then
    cp "$HOME/agentindex/.env" "$BACKUP_DIR/docs/.env"
    echo "  .env copied"
fi

# ── Summary ──────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════"
echo "  BACKUP COMPLETE"
echo "═══════════════════════════════════════════"
echo ""
echo "  Location: $BACKUP_DIR"
echo ""
du -sh "$BACKUP_DIR"/* 2>/dev/null | while read -r size dir; do
    echo "  $size  $(basename "$dir")"
done
echo ""
TOTAL=$(du -sh "$BACKUP_DIR" | cut -f1)
echo "  TOTAL: $TOTAL"
echo ""
echo "  To restore PostgreSQL:"
echo "    pg_restore -d agentindex $BACKUP_DIR/postgres/agentindex.dump"
echo ""
