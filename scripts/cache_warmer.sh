#!/bin/bash
# Cache Warmer — curls top pages through Cloudflare to keep edge cache warm
# Run hourly via LaunchAgent
# Each request warms both the Redis page cache (4h TTL) and Cloudflare edge (24h s-maxage)

LOG=~/agentindex/logs/cache_warmer.log
DOMAIN="https://nerq.ai"
MAX_PATHS=500
CONCURRENCY=10
DELAY=0.1  # 100ms between batches to avoid self-DoS

mkdir -p "$(dirname "$LOG")"
echo "$(date '+%Y-%m-%d %H:%M:%S') [WARM] Starting cache warmer" >> "$LOG"

# Get top paths from analytics (last 7 days, status 200 only)
PATHS=$(sqlite3 ~/agentindex/logs/analytics.db "
SELECT path FROM requests
WHERE ts > datetime('now', '-7 days')
AND status = 200
AND path NOT LIKE '/v1/%'
AND path NOT LIKE '/flywheel%'
AND path NOT LIKE '/dashboard%'
AND path NOT LIKE '/admin%'
AND path NOT LIKE '/static/%'
AND path NOT LIKE '/openapi%'
GROUP BY path
ORDER BY COUNT(*) DESC
LIMIT $MAX_PATHS;" 2>/dev/null)

if [ -z "$PATHS" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARM] No paths from analytics, using defaults" >> "$LOG"
    PATHS="/
/safe/express
/safe/react
/safe/openai
/safe/langchain
/best/safest-npm-packages
/best/best-ai-code-assistants
/best/safest-pypi-packages
/best/best-mcp-servers"
fi

COUNT=0
WARM=0
SKIP=0

while IFS= read -r path; do
    [ -z "$path" ] && continue
    COUNT=$((COUNT + 1))

    # Curl through CF — warms edge cache
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${DOMAIN}${path}" 2>/dev/null)

    if [ "$STATUS" = "200" ]; then
        WARM=$((WARM + 1))
    else
        SKIP=$((SKIP + 1))
    fi

    # Rate limit: sleep every CONCURRENCY requests
    if [ $((COUNT % CONCURRENCY)) -eq 0 ]; then
        sleep "$DELAY"
    fi
done <<< "$PATHS"

echo "$(date '+%Y-%m-%d %H:%M:%S') [WARM] Done: $WARM warmed, $SKIP skipped, $COUNT total" >> "$LOG"
