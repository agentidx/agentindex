#!/usr/bin/env bash
# Smedjan analytics-mirror exporter — runs on Mac Studio (where analytics.db
# lives). Produces CSVs + rsyncs to smedjan:/home/smedjan/analytics-import/.
#
# Scheduler target: daily 03:00 local via LaunchAgent
# com.nerq.smedjan.analytics_export (installed separately; NOT yet loaded).
#
# Filter on requests is kept in sync with:
#   agentindex/smedjan/schema_analytics_mirror.sql  (documentation)
#   ~/smedjan/scripts/analytics-mirror-import.sh    (COPY target columns)
#
# Idempotent: safe to run more than once per day.
set -euo pipefail

DB=${SMEDJAN_ANALYTICS_DB:-/Users/anstudio/agentindex/logs/analytics.db}
OUT=${SMEDJAN_EXPORT_DIR:-/Users/anstudio/smedjan/analytics-export}
RSYNC_TARGET=${SMEDJAN_RSYNC_TARGET:-smedjan:/home/smedjan/analytics-import/}
WINDOW_DAYS=${SMEDJAN_WINDOW_DAYS:-30}
LOG=${SMEDJAN_LOG:-/Users/anstudio/smedjan/worker-logs/analytics-export-$(date +%Y-%m-%d).log}

mkdir -p "$OUT" "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "$(date -u +%FT%TZ) export start (window=${WINDOW_DAYS}d)"

CUTOFF=$(date -u -v-${WINDOW_DAYS}d +%Y-%m-%dT%H:%M:%S)

dump() {
    local name=$1 query=$2
    /usr/bin/sqlite3 "$DB" <<SQL > "$OUT/$name.csv"
.headers off
.mode csv
.nullvalue \N
${query};
SQL
    local rows=$(wc -l <"$OUT/$name.csv" | tr -d ' ')
    /usr/bin/shasum -a 256 "$OUT/$name.csv" | awk '{print $1}' > "$OUT/$name.sha256"
    echo "$(date -u +%FT%TZ) dumped $name rows=$rows sha=$(cat "$OUT/$name.sha256" | cut -c1-12)…"
}

dump preflight_analytics "
SELECT id, ts, target, bot_name, ip, status, duration_ms, country
  FROM preflight_analytics
 WHERE ts > '${CUTOFF}'"

dump requests "
SELECT id, ts, method, path, status, duration_ms, ip, user_agent, bot_name,
       is_bot, is_ai_bot, referrer, referrer_domain, query_string,
       search_query, country, ai_source, visitor_type, bot_purpose
  FROM requests
 WHERE ts > '${CUTOFF}'
   AND (is_ai_bot = 1
        OR path LIKE '/safe/%'
        OR path LIKE '/compare/%'
        OR path LIKE '/best/%'
        OR path LIKE '/alternatives/%'
        OR path LIKE '/search%'
        OR status >= 400)"

dump requests_daily "
SELECT day, bot_name, is_ai_bot, is_bot, status, is_gptbot, is_preflight,
       visitor_type, country, lang, count
  FROM requests_daily"

# search_events (FU-QUERY-20260418-08) — full window, unfiltered; rows are
# cheap (one per /search hit). Populates analytics_mirror.search_events so
# the weekly AUDIT-QUERY cut can answer "top search queries" and
# "top zero-result queries".
dump search_events "
SELECT id, ts, q, q_normalized, result_count, duration_ms, ip, user_agent,
       referrer, bot_name, is_bot, is_ai_bot, visitor_type, country, source
  FROM search_events
 WHERE ts > '${CUTOFF}'"

# Also ship a simple ready-marker so the importer waits for complete data.
echo "$(date -u +%FT%TZ)" > "$OUT/READY"

echo "$(date -u +%FT%TZ) rsync → $RSYNC_TARGET"
/usr/bin/rsync -az --delete --partial "$OUT/" "$RSYNC_TARGET"

echo "$(date -u +%FT%TZ) export done"
