"""
Trending content generator — discovers what AI agents/tokens are trending
by cross-referencing AI bot fetch patterns with human traffic.

Outputs trending.json consumed by homepage sections.
Run periodically: python -m agentindex.trending_generator
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'logs', 'analytics.db')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trending.json')


def generate_trending():
    """Analyze traffic patterns to find trending agents and tokens."""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row

    trending = {
        "generated_at": datetime.utcnow().isoformat(),
        "trending_agents": [],
        "trending_tokens": [],
        "ai_bot_interests": [],
    }

    # 1. Agents trending with AI bots (ChatGPT-User, Claude, etc.)
    ai_agent_hits = conn.execute("""
        SELECT path, count(*) as hits, count(distinct ip) as unique_ips,
               group_concat(distinct bot_name) as bots
        FROM requests
        WHERE is_ai_bot = 1
          AND path LIKE '/agent/%'
          AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
        GROUP BY path
        ORDER BY hits DESC
        LIMIT 20
    """).fetchall()

    for row in ai_agent_hits:
        slug = row['path'].replace('/agent/', '').strip('/')
        if not slug or '/' in slug:
            continue
        trending["ai_bot_interests"].append({
            "slug": slug,
            "ai_hits_7d": row['hits'],
            "unique_ai_bots": row['unique_ips'],
            "bot_names": row['bots'],
        })

    # 2. Agents with most human traffic growth (compare last 3 days vs prior 4)
    human_growth = conn.execute("""
        SELECT path,
            SUM(CASE WHEN ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-3 days') THEN 1 ELSE 0 END) as recent,
            SUM(CASE WHEN ts < strftime('%Y-%m-%dT%H:%M:%f', 'now', '-3 days') AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days') THEN 1 ELSE 0 END) as prior
        FROM requests
        WHERE is_bot = 0
          AND (path LIKE '/agent/%' OR path LIKE '/kya%' OR path LIKE '/safe/%')
          AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
        GROUP BY path
        HAVING recent > 2
        ORDER BY (recent * 1.0 / MAX(prior, 1)) DESC
        LIMIT 15
    """).fetchall()

    for row in human_growth:
        path = row['path']
        slug = path.split('/')[-1] if '/' in path else path
        if not slug:
            continue
        trending["trending_agents"].append({
            "slug": slug,
            "path": path,
            "hits_recent_3d": row['recent'],
            "hits_prior_4d": row['prior'],
            "growth_ratio": round(row['recent'] / max(row['prior'], 1), 2),
        })

    # 3. Tokens trending (zarq.ai)
    token_growth = conn.execute("""
        SELECT path,
            SUM(CASE WHEN ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-3 days') THEN 1 ELSE 0 END) as recent,
            SUM(CASE WHEN ts < strftime('%Y-%m-%dT%H:%M:%f', 'now', '-3 days') AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days') THEN 1 ELSE 0 END) as prior
        FROM requests
        WHERE is_bot = 0
          AND (path LIKE '/token/%' OR path LIKE '/vitality%')
          AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
        GROUP BY path
        HAVING recent > 1
        ORDER BY (recent * 1.0 / MAX(prior, 1)) DESC
        LIMIT 10
    """).fetchall()

    for row in token_growth:
        slug = row['path'].split('/')[-1] if '/' in row['path'] else row['path']
        if not slug or slug in ('token', 'vitality'):
            continue
        trending["trending_tokens"].append({
            "slug": slug,
            "path": row['path'],
            "hits_recent_3d": row['recent'],
            "hits_prior_4d": row['prior'],
            "growth_ratio": round(row['recent'] / max(row['prior'], 1), 2),
        })

    # 4. Most searched queries
    top_searches = conn.execute("""
        SELECT search_query, count(*) as cnt
        FROM requests
        WHERE search_query IS NOT NULL
          AND length(search_query) > 0
          AND is_bot = 0
          AND ts >= strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
        GROUP BY search_query
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()

    trending["top_searches"] = [
        {"query": row['search_query'], "count": row['cnt']}
        for row in top_searches
    ]

    conn.close()

    # Write output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(trending, f, indent=2)

    print(f"Trending data generated: {len(trending['trending_agents'])} agents, "
          f"{len(trending['trending_tokens'])} tokens, "
          f"{len(trending['ai_bot_interests'])} AI bot interests, "
          f"{len(trending['top_searches'])} top searches")
    return trending


if __name__ == "__main__":
    generate_trending()
