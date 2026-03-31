"""
SEO Monitor — proxy for Google Search Console.
Tracks Googlebot crawls, organic referral traffic, rising/dropping pages.
Runs daily at 09:00 via LaunchAgent.

Usage: python3 -m agentindex.seo_monitor
"""
import sqlite3
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'logs', 'analytics.db')
REPORT_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'auto-reports')
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'seo_weekly.json')


def run():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    today = datetime.utcnow().strftime('%Y-%m-%d')
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
    two_weeks_ago = (datetime.utcnow() - timedelta(days=14)).strftime('%Y-%m-%d')

    report = {"generated": today, "sections": {}}

    # 1. Googlebot crawl volume per page type per day
    crawl_by_type = conn.execute("""
        SELECT date(ts) as day,
            CASE
                WHEN path LIKE '/token/%' OR path LIKE '/crypto/token/%' THEN 'token'
                WHEN path LIKE '/safe/%' THEN 'agent-safe'
                WHEN path LIKE '/mcp/%' THEN 'mcp'
                WHEN path LIKE '/compare/%' THEN 'compare'
                WHEN path LIKE '/chain/%' THEN 'chain'
                WHEN path LIKE '/kya%' THEN 'kya'
                WHEN path LIKE '/agent/%' THEN 'agent'
                WHEN path = '/' THEN 'homepage'
                ELSE 'other'
            END as page_type,
            COUNT(*) as crawls,
            COUNT(DISTINCT path) as unique_pages
        FROM requests
        WHERE bot_name = 'Google' AND ts >= ?
        GROUP BY day, page_type
        ORDER BY day, crawls DESC
    """, (two_weeks_ago,)).fetchall()

    crawl_data = {}
    for r in crawl_by_type:
        day = r['day']
        if day not in crawl_data:
            crawl_data[day] = {}
        crawl_data[day][r['page_type']] = {"crawls": r['crawls'], "unique_pages": r['unique_pages']}
    report["sections"]["googlebot_crawls_by_day"] = crawl_data

    # 2. Google organic traffic per page (7 days)
    organic = conn.execute("""
        SELECT path, COUNT(DISTINCT ip) as visitors, COUNT(*) as hits
        FROM requests
        WHERE referrer_domain LIKE '%google%' AND is_bot = 0
        AND ts >= ?
        GROUP BY path
        ORDER BY visitors DESC
        LIMIT 50
    """, (week_ago,)).fetchall()
    report["sections"]["google_organic_top_pages"] = [
        {"path": r['path'], "visitors": r['visitors'], "hits": r['hits']}
        for r in organic
    ]

    # 3. Rising pages: more Googlebot crawls this week vs last week
    rising = conn.execute("""
        SELECT path,
            SUM(CASE WHEN ts >= ? THEN 1 ELSE 0 END) as this_week,
            SUM(CASE WHEN ts < ? AND ts >= ? THEN 1 ELSE 0 END) as last_week
        FROM requests
        WHERE bot_name = 'Google' AND ts >= ?
        GROUP BY path
        HAVING this_week > 3 AND this_week > last_week * 1.5
        ORDER BY (this_week - last_week) DESC
        LIMIT 20
    """, (week_ago, week_ago, two_weeks_ago, two_weeks_ago)).fetchall()
    report["sections"]["rising_pages"] = [
        {"path": r['path'], "this_week": r['this_week'], "last_week": r['last_week'],
         "change": f"+{r['this_week'] - r['last_week']}"}
        for r in rising
    ]

    # 4. Dropping pages: fewer crawls this week
    dropping = conn.execute("""
        SELECT path,
            SUM(CASE WHEN ts >= ? THEN 1 ELSE 0 END) as this_week,
            SUM(CASE WHEN ts < ? AND ts >= ? THEN 1 ELSE 0 END) as last_week
        FROM requests
        WHERE bot_name = 'Google' AND ts >= ?
        GROUP BY path
        HAVING last_week > 3 AND this_week < last_week * 0.5
        ORDER BY (last_week - this_week) DESC
        LIMIT 20
    """, (week_ago, week_ago, two_weeks_ago, two_weeks_ago)).fetchall()
    report["sections"]["dropping_pages"] = [
        {"path": r['path'], "this_week": r['this_week'], "last_week": r['last_week'],
         "change": f"-{r['last_week'] - r['this_week']}"}
        for r in dropping
    ]

    # 5. High crawl, zero organic (indexed but not ranking)
    high_crawl_no_organic = conn.execute("""
        SELECT g.path, g.crawls, COALESCE(o.visitors, 0) as organic_visitors
        FROM (
            SELECT path, COUNT(*) as crawls
            FROM requests WHERE bot_name = 'Google' AND ts >= ?
            GROUP BY path HAVING crawls >= 5
        ) g
        LEFT JOIN (
            SELECT path, COUNT(DISTINCT ip) as visitors
            FROM requests WHERE referrer_domain LIKE '%google%' AND is_bot = 0 AND ts >= ?
            GROUP BY path
        ) o ON g.path = o.path
        WHERE COALESCE(o.visitors, 0) = 0
        ORDER BY g.crawls DESC
        LIMIT 30
    """, (week_ago, week_ago)).fetchall()
    report["sections"]["crawled_but_not_ranking"] = [
        {"path": r['path'], "googlebot_crawls": r['crawls']}
        for r in high_crawl_no_organic
    ]

    # 6. Summary stats
    total_crawls = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE bot_name = 'Google' AND ts >= ?",
        (week_ago,)
    ).fetchone()[0]
    total_organic = conn.execute(
        "SELECT COUNT(DISTINCT ip) FROM requests WHERE referrer_domain LIKE '%google%' AND is_bot = 0 AND ts >= ?",
        (week_ago,)
    ).fetchone()[0]
    unique_crawled = conn.execute(
        "SELECT COUNT(DISTINCT path) FROM requests WHERE bot_name = 'Google' AND ts >= ?",
        (week_ago,)
    ).fetchone()[0]

    report["sections"]["summary"] = {
        "total_googlebot_crawls_7d": total_crawls,
        "unique_pages_crawled_7d": unique_crawled,
        "google_organic_visitors_7d": total_organic,
        "crawl_to_organic_ratio": f"{total_crawls}:{total_organic}",
    }

    conn.close()

    # Save JSON
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, 'w') as f:
        json.dump(report, f, indent=2)

    # Generate markdown report
    os.makedirs(REPORT_DIR, exist_ok=True)
    md_path = os.path.join(REPORT_DIR, f"seo-weekly-{today}.md")

    s = report["sections"]["summary"]
    md = f"""# SEO Weekly Report — {today}

## Summary
- Googlebot crawls (7d): **{s['total_googlebot_crawls_7d']:,}**
- Unique pages crawled: **{s['unique_pages_crawled_7d']:,}**
- Google organic visitors: **{s['google_organic_visitors_7d']}**
- Crawl:Organic ratio: {s['crawl_to_organic_ratio']}

## Top Google Organic Pages
| Page | Visitors | Hits |
|------|----------|------|
"""
    for p in report["sections"]["google_organic_top_pages"][:20]:
        md += f"| {p['path']} | {p['visitors']} | {p['hits']} |\n"

    md += "\n## Rising Pages (Googlebot attention increasing)\n| Page | This Week | Last Week | Change |\n|------|-----------|-----------|--------|\n"
    for p in report["sections"]["rising_pages"][:15]:
        md += f"| {p['path']} | {p['this_week']} | {p['last_week']} | {p['change']} |\n"

    md += "\n## Crawled but Not Ranking (opportunity)\n| Page | Crawls |\n|------|--------|\n"
    for p in report["sections"]["crawled_but_not_ranking"][:15]:
        md += f"| {p['path']} | {p['googlebot_crawls']} |\n"

    md += "\n---\n*Generated by seo_monitor.py*\n"

    with open(md_path, 'w') as f:
        f.write(md)

    # Print summary
    print(f"\nSEO Weekly Report — {today}")
    print(f"  Googlebot crawls (7d): {s['total_googlebot_crawls_7d']:,}")
    print(f"  Unique pages crawled:  {s['unique_pages_crawled_7d']:,}")
    print(f"  Google organic:        {s['google_organic_visitors_7d']} visitors")
    print(f"  Rising pages:          {len(report['sections']['rising_pages'])}")
    print(f"  Dropping pages:        {len(report['sections']['dropping_pages'])}")
    print(f"  Crawled not ranking:   {len(report['sections']['crawled_but_not_ranking'])}")
    print(f"  Report: {md_path}")


if __name__ == "__main__":
    run()
