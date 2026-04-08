"""
Safety Ranking Tracker
======================
Tracks Google organic traffic, Googlebot crawl frequency, and AI bot engagement
for /is-X-safe and /safe/ pages. Outputs daily snapshot to data/safety_ranking_daily.json.

Usage:
    python -m agentindex.intelligence.safety_ranking_tracker
"""

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # agentindex repo root
ANALYTICS_DB = BASE_DIR / "logs" / "analytics.db"
TMP_DB = Path("/tmp/safety_ranking_check.db")
OUTPUT_PATH = BASE_DIR / "data" / "safety_ranking_daily.json"


def copy_db():
    """Copy analytics DB to /tmp to avoid holding locks on the live DB."""
    if not ANALYTICS_DB.exists():
        print(f"[ERROR] Analytics DB not found: {ANALYTICS_DB}")
        sys.exit(1)
    shutil.copy2(ANALYTICS_DB, TMP_DB)
    print(f"[OK] Copied {ANALYTICS_DB} -> {TMP_DB} ({TMP_DB.stat().st_size / 1024:.0f} KB)")


def run_queries():
    """Run all tracking queries against the copied DB."""
    conn = sqlite3.connect(str(TMP_DB))
    conn.row_factory = sqlite3.Row

    results = {}

    # ── 1. Google organic traffic to safety pages ──
    try:
        rows = conn.execute("""
            SELECT path, COUNT(DISTINCT ip) as visitors
            FROM requests
            WHERE referrer LIKE '%google%' AND is_bot = 0
            AND (path LIKE '/is-%safe' OR path LIKE '/safe/%')
            AND ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
            GROUP BY path ORDER BY visitors DESC LIMIT 20
        """).fetchall()
        results["google_organic"] = [dict(r) for r in rows]
    except Exception as e:
        print(f"[WARN] Google organic query failed: {e}")
        results["google_organic"] = []

    # ── 2. Googlebot crawl frequency ──
    try:
        rows = conn.execute("""
            SELECT path, COUNT(*) as crawls, MAX(ts) as last_crawl
            FROM requests
            WHERE user_agent LIKE '%Googlebot%'
            AND (path LIKE '/is-%safe' OR path LIKE '/safe/%')
            AND ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
            GROUP BY path ORDER BY crawls DESC LIMIT 30
        """).fetchall()
        results["googlebot_crawls"] = [dict(r) for r in rows]
    except Exception as e:
        print(f"[WARN] Googlebot crawl query failed: {e}")
        results["googlebot_crawls"] = []

    # ── 3. AI bot engagement ──
    try:
        rows = conn.execute("""
            SELECT
              CASE WHEN user_agent LIKE '%ChatGPT%' THEN 'ChatGPT'
                   WHEN user_agent LIKE '%GPTBot%' THEN 'GPTBot'
                   WHEN user_agent LIKE '%Perplexity%' THEN 'Perplexity'
                   WHEN user_agent LIKE '%Claude%' THEN 'Claude'
                   WHEN user_agent LIKE '%Google%' THEN 'Google'
                   ELSE 'Other'
              END as bot,
              SUM(CASE WHEN path LIKE '/is-%safe' THEN 1 ELSE 0 END) as is_safe_hits,
              SUM(CASE WHEN path LIKE '/safe/%' THEN 1 ELSE 0 END) as safe_hits,
              SUM(CASE WHEN path LIKE '/v1/preflight%' THEN 1 ELSE 0 END) as preflight_hits
            FROM requests WHERE is_bot = 1
            AND ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-7 days')
            GROUP BY bot ORDER BY is_safe_hits + safe_hits DESC
        """).fetchall()
        results["ai_bot_engagement"] = [dict(r) for r in rows]
    except Exception as e:
        print(f"[WARN] AI bot engagement query failed: {e}")
        results["ai_bot_engagement"] = []

    conn.close()
    return results


def save_results(results):
    """Save results to data/safety_ranking_daily.json."""
    output = {
        "generated_at": datetime.now(tz=__import__('datetime').timezone.utc).isoformat(),
        "source_db": str(ANALYTICS_DB),
        "window": "7 days",
        **results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"[OK] Saved results to {OUTPUT_PATH}")


def print_report(results):
    """Print a human-readable summary report."""
    print("\n" + "=" * 70)
    print("  SAFETY PAGE RANKING TRACKER — 7-day report")
    print("=" * 70)

    # Google organic
    organic = results.get("google_organic", [])
    print(f"\n── Google Organic Traffic ({len(organic)} pages with traffic) ──")
    if organic:
        # ALERT: any Google organic traffic is significant
        print()
        print("  ***********************************************************")
        print("  *  ALERT: Safety pages are getting Google organic traffic! *")
        print("  ***********************************************************")
        print()
        for row in organic:
            print(f"  {row['visitors']:>4} visitors  {row['path']}")
    else:
        print("  No Google organic traffic to safety pages yet.")

    # Googlebot crawls
    crawls = results.get("googlebot_crawls", [])
    print(f"\n── Googlebot Crawl Frequency ({len(crawls)} pages crawled) ──")
    if crawls:
        for row in crawls:
            print(f"  {row['crawls']:>4} crawls  last: {row['last_crawl']}  {row['path']}")
    else:
        print("  No Googlebot crawls on safety pages in last 7 days.")

    # AI bots
    bots = results.get("ai_bot_engagement", [])
    print(f"\n── AI Bot Engagement ({len(bots)} bot types) ──")
    if bots:
        print(f"  {'Bot':<14} {'is-X-safe':>10} {'safe/':>10} {'preflight':>10}")
        print(f"  {'─' * 14} {'─' * 10} {'─' * 10} {'─' * 10}")
        for row in bots:
            print(f"  {row['bot']:<14} {row['is_safe_hits']:>10} {row['safe_hits']:>10} {row['preflight_hits']:>10}")
    else:
        print("  No AI bot activity on safety pages.")

    print("\n" + "=" * 70)


def cleanup():
    """Remove temp DB."""
    try:
        TMP_DB.unlink(missing_ok=True)
    except Exception:
        pass


def main():
    print(f"[START] Safety Ranking Tracker — {datetime.now().isoformat()}")
    copy_db()
    try:
        results = run_queries()
        save_results(results)
        print_report(results)
    finally:
        cleanup()
    print("[DONE]")


if __name__ == "__main__":
    main()
