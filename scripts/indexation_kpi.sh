#!/bin/bash
PSQL="/opt/homebrew/opt/postgresql@16/bin/psql"
DB="$HOME/agentindex/logs/analytics.db"
LOGFILE="$HOME/agentindex/logs/indexation_kpi.csv"
DATE=$(date -u +"%Y-%m-%d")

if [ ! -f "$LOGFILE" ]; then
  echo "date,enriched,indexable_pages,ai_citations_24h,citations_per_1k_pages,new_enriched_24h,chatgpt_24h,claude_24h,bytedance_24h,perplexity_24h" > "$LOGFILE"
fi

# Enriched = alla med enriched_at (inga trust_score/description-filter)
ENRICHED=$($PSQL -d agentindex -tAc "SELECT COUNT(*) FROM software_registry WHERE enriched_at IS NOT NULL;" 2>/dev/null || echo "0")

# Pages = SUM per registry (enriched * patterns * 22 languages)
PAGES=$($PSQL -d agentindex -tAc "
SELECT SUM(cnt * pats * 22)::bigint FROM (
    SELECT registry, COUNT(*) as cnt,
        CASE registry
            WHEN 'npm' THEN 13 WHEN 'pypi' THEN 13 WHEN 'nuget' THEN 13 WHEN 'crates' THEN 13
            WHEN 'gems' THEN 13 WHEN 'go' THEN 13 WHEN 'packagist' THEN 13
            WHEN 'wordpress' THEN 12 WHEN 'vscode' THEN 8 WHEN 'ios' THEN 18 WHEN 'android' THEN 18
            WHEN 'steam' THEN 8 WHEN 'firefox' THEN 8 WHEN 'chrome' THEN 8
            WHEN 'website' THEN 15 WHEN 'vpn' THEN 17 WHEN 'homebrew' THEN 10
            WHEN 'saas' THEN 15 WHEN 'ai_tool' THEN 15 WHEN 'crypto' THEN 10
            WHEN 'country' THEN 36 WHEN 'city' THEN 36 WHEN 'charity' THEN 15
            WHEN 'ingredient' THEN 15 WHEN 'supplement' THEN 15 WHEN 'cosmetic_ingredient' THEN 15
            ELSE 10
        END as pats
    FROM software_registry WHERE enriched_at IS NOT NULL
    GROUP BY registry
) sub;
" 2>/dev/null || echo "0")

NEW_ENRICHED=$($PSQL -d agentindex -tAc "SELECT COUNT(*) FROM software_registry WHERE enriched_at >= NOW() - INTERVAL '24 hours';" 2>/dev/null || echo "0")
CITATIONS=$(sqlite3 "$DB" "SELECT COALESCE(SUM(CASE WHEN is_ai_bot=1 AND status=200 THEN 1 ELSE 0 END), 0) FROM requests WHERE ts >= datetime('now', '-24 hours');" 2>/dev/null || echo "0")
CHATGPT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM requests WHERE ts >= datetime('now', '-24 hours') AND status=200 AND user_agent LIKE '%ChatGPT%';" 2>/dev/null || echo "0")
CLAUDE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM requests WHERE ts >= datetime('now', '-24 hours') AND status=200 AND user_agent LIKE '%Claude%';" 2>/dev/null || echo "0")
BYTEDANCE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM requests WHERE ts >= datetime('now', '-24 hours') AND status=200 AND (user_agent LIKE '%Bytespider%' OR user_agent LIKE '%ByteDance%');" 2>/dev/null || echo "0")
PERPLEXITY=$(sqlite3 "$DB" "SELECT COUNT(*) FROM requests WHERE ts >= datetime('now', '-24 hours') AND status=200 AND user_agent LIKE '%Perplexity%';" 2>/dev/null || echo "0")

if [ "$PAGES" -gt 0 ] 2>/dev/null; then
  CPK=$(echo "scale=2; $CITATIONS * 1000 / $PAGES" | bc 2>/dev/null || echo "0")
else
  CPK="0"
fi

echo "$DATE,$ENRICHED,$PAGES,$CITATIONS,$CPK,$NEW_ENRICHED,$CHATGPT,$CLAUDE,$BYTEDANCE,$PERPLEXITY" >> "$LOGFILE"
