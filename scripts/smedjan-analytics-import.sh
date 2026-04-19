#!/usr/bin/env bash
# Smedjan analytics-mirror importer — runs on smedjan.nbg1.hetzner.
# Consumes CSVs dropped by the Mac Studio exporter in
# /home/smedjan/analytics-import/ and reloads analytics_mirror.*.
#
# Scheduler: daily 01:30 UTC via systemd timer smedjan-analytics-import.timer
# (on smedjan.nbg1). TRUNCATE + \copy reload model. Checksums verified if
# present.
#
# Source-of-truth path (this file, in the Mac Studio repo):
#   agentindex/scripts/smedjan-analytics-import.sh
# Deployed to:
#   smedjan:/home/smedjan/smedjan/scripts/analytics-mirror-import.sh
set -euo pipefail

IN=${SMEDJAN_IMPORT_DIR:-/home/smedjan/analytics-import}
LOG=${SMEDJAN_LOG:-/home/smedjan/smedjan/worker-logs/analytics-import-$(date +%Y-%m-%d).log}
HOST_NAME="anderss-mac-studio"

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "$(date -u +%FT%TZ) import start"

if [[ ! -f "$IN/READY" ]]; then
    echo "ERROR: $IN/READY missing — export did not complete"
    exit 2
fi

# Verify checksums for mandatory tables.
for name in preflight_analytics requests requests_daily; do
    if [[ ! -s "$IN/$name.csv" ]]; then
        echo "ERROR: $IN/$name.csv missing or empty"
        exit 3
    fi
    if [[ -s "$IN/$name.sha256" ]]; then
        expected=$(cat "$IN/$name.sha256")
        actual=$(sha256sum "$IN/$name.csv" | awk '{print $1}')
        if [[ "$expected" != "$actual" ]]; then
            echo "ERROR: $name checksum mismatch (expected $expected, got $actual)"
            exit 4
        fi
    fi
done

# search_events is optional during rollout: the Nerq side (FU-QUERY-20260418-08)
# writes to logs/analytics.db:search_events but requires a Nerq restart before
# rows accumulate. Treat missing CSV as skip-with-warning, not a hard error.
IMPORT_SEARCH_EVENTS=false
if [[ -e "$IN/search_events.csv" ]]; then
    if [[ -s "$IN/search_events.sha256" ]]; then
        expected=$(cat "$IN/search_events.sha256")
        actual=$(sha256sum "$IN/search_events.csv" | awk '{print $1}')
        if [[ "$expected" != "$actual" ]]; then
            echo "ERROR: search_events checksum mismatch (expected $expected, got $actual)"
            exit 4
        fi
    fi
    IMPORT_SEARCH_EVENTS=true
    echo "$(date -u +%FT%TZ) search_events.csv present ($(wc -l <"$IN/search_events.csv" | tr -d ' ') rows) — will import"
else
    echo "$(date -u +%FT%TZ) WARN: search_events.csv missing — skipping (Nerq restart pending)"
fi
echo "$(date -u +%FT%TZ) checksums OK"

# Load secret
# shellcheck disable=SC1091
source /home/smedjan/smedjan/config/.env
export PGPASSWORD="$SMEDJAN_APP_PW"

psql -h localhost -U smedjan_app -d smedjan -v ON_ERROR_STOP=1 <<SQL
BEGIN;

TRUNCATE analytics_mirror.preflight_analytics;
\copy analytics_mirror.preflight_analytics (id, ts, target, bot_name, ip, status, duration_ms, country) FROM '$IN/preflight_analytics.csv' WITH (FORMAT csv, NULL '\N')

TRUNCATE analytics_mirror.requests;
\copy analytics_mirror.requests (id, ts, method, path, status, duration_ms, ip, user_agent, bot_name, is_bot, is_ai_bot, referrer, referrer_domain, query_string, search_query, country, ai_source, visitor_type, bot_purpose) FROM '$IN/requests.csv' WITH (FORMAT csv, NULL '\N')

TRUNCATE analytics_mirror.requests_daily;
\copy analytics_mirror.requests_daily (day, bot_name, is_ai_bot, is_bot, status, is_gptbot, is_preflight, visitor_type, country, lang, count) FROM '$IN/requests_daily.csv' WITH (FORMAT csv, NULL '\N')

INSERT INTO analytics_mirror._sync_state (table_name, row_count, synced_at, source_host, source_hash) VALUES
  ('preflight_analytics', (SELECT count(*) FROM analytics_mirror.preflight_analytics), now(), '${HOST_NAME}', (SELECT md5(string_agg(id::text, ',' ORDER BY id)) FROM (SELECT id FROM analytics_mirror.preflight_analytics ORDER BY id LIMIT 1000) s)),
  ('requests',            (SELECT count(*) FROM analytics_mirror.requests),            now(), '${HOST_NAME}', (SELECT md5(string_agg(id::text, ',' ORDER BY id)) FROM (SELECT id FROM analytics_mirror.requests ORDER BY id LIMIT 1000) s)),
  ('requests_daily',      (SELECT count(*) FROM analytics_mirror.requests_daily),      now(), '${HOST_NAME}', NULL)
ON CONFLICT (table_name) DO UPDATE
    SET row_count   = EXCLUDED.row_count,
        synced_at   = EXCLUDED.synced_at,
        source_host = EXCLUDED.source_host,
        source_hash = EXCLUDED.source_hash;

COMMIT;
SQL

if [[ "$IMPORT_SEARCH_EVENTS" == "true" ]]; then
    psql -h localhost -U smedjan_app -d smedjan -v ON_ERROR_STOP=1 <<SQL
BEGIN;

TRUNCATE analytics_mirror.search_events;
\copy analytics_mirror.search_events (id, ts, q, q_normalized, result_count, duration_ms, ip, user_agent, referrer, bot_name, is_bot, is_ai_bot, visitor_type, country, source) FROM '$IN/search_events.csv' WITH (FORMAT csv, NULL '\N')

INSERT INTO analytics_mirror._sync_state (table_name, row_count, synced_at, source_host, source_hash) VALUES
  ('search_events', (SELECT count(*) FROM analytics_mirror.search_events), now(), '${HOST_NAME}', (SELECT md5(string_agg(id::text, ',' ORDER BY id)) FROM (SELECT id FROM analytics_mirror.search_events ORDER BY id LIMIT 1000) s))
ON CONFLICT (table_name) DO UPDATE
    SET row_count   = EXCLUDED.row_count,
        synced_at   = EXCLUDED.synced_at,
        source_host = EXCLUDED.source_host,
        source_hash = EXCLUDED.source_hash;

COMMIT;
SQL
fi

echo "$(date -u +%FT%TZ) import done"
psql -h localhost -U smedjan_app -d smedjan -c "SELECT table_name, row_count, synced_at FROM analytics_mirror._sync_state ORDER BY table_name;"
