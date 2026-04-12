#!/usr/bin/env python3
"""
Incremental refresh of analytics aggregation tables.

Deletes and re-aggregates the last N days from the raw requests table
into requests_daily, requests_daily_social, requests_daily_new_ai, and
preflight_daily. Runs every 15 minutes via LaunchAgent
com.nerq.analytics-aggregation.

The aggregation tables are used by analytics_dashboard._query_data()
to serve /admin/analytics-dashboard in ~50ms instead of 300+s on the
16M-row raw requests table.
"""
import sqlite3
import sys
import time

DB = "/Users/anstudio/agentindex/logs/analytics.db"
DAYS_TO_REFRESH = 3  # yesterday + today + safety margin for timezone edge cases


def refresh():
    conn = sqlite3.connect(DB, timeout=300)
    start = time.time()

    # Determine date cutoff
    cutoff = conn.execute(
        "SELECT date('now', '-{} days')".format(DAYS_TO_REFRESH)
    ).fetchone()[0]
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Refreshing aggregation tables for days >= {cutoff}", flush=True)

    # 1. requests_daily
    conn.execute("DELETE FROM requests_daily WHERE day >= ?", (cutoff,))
    conn.execute("""
        INSERT INTO requests_daily (day, bot_name, is_ai_bot, is_bot, status, is_gptbot, is_preflight, visitor_type, country, lang, count)
        SELECT
            date(ts),
            bot_name,
            is_ai_bot,
            is_bot,
            status,
            CASE WHEN user_agent LIKE '%GPTBot%' THEN 1 ELSE 0 END,
            CASE WHEN path LIKE '/v1/preflight%' THEN 1 ELSE 0 END,
            visitor_type,
            country,
            CASE
                WHEN path LIKE '/es/%' THEN 'es' WHEN path LIKE '/de/%' THEN 'de'
                WHEN path LIKE '/fr/%' THEN 'fr' WHEN path LIKE '/ja/%' THEN 'ja'
                WHEN path LIKE '/pt/%' THEN 'pt' WHEN path LIKE '/id/%' THEN 'id'
                WHEN path LIKE '/cs/%' THEN 'cs' WHEN path LIKE '/th/%' THEN 'th'
                WHEN path LIKE '/ro/%' THEN 'ro' WHEN path LIKE '/tr/%' THEN 'tr'
                WHEN path LIKE '/hi/%' THEN 'hi' WHEN path LIKE '/ru/%' THEN 'ru'
                WHEN path LIKE '/pl/%' THEN 'pl' WHEN path LIKE '/it/%' THEN 'it'
                WHEN path LIKE '/ko/%' THEN 'ko' WHEN path LIKE '/vi/%' THEN 'vi'
                WHEN path LIKE '/nl/%' THEN 'nl' WHEN path LIKE '/sv/%' THEN 'sv'
                WHEN path LIKE '/zh/%' THEN 'zh' WHEN path LIKE '/da/%' THEN 'da'
                WHEN path LIKE '/ar/%' THEN 'ar' WHEN path LIKE '/no/%' THEN 'no'
                ELSE 'en'
            END,
            COUNT(*)
        FROM requests
        WHERE date(ts) >= ?
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
    """, (cutoff,))
    r1 = conn.execute("SELECT COUNT(*) FROM requests_daily WHERE day >= ?", (cutoff,)).fetchone()[0]
    print(f"  requests_daily: {r1} rows refreshed", flush=True)

    # 2. requests_daily_social
    conn.execute("DELETE FROM requests_daily_social WHERE day >= ?", (cutoff,))
    conn.execute("""
        INSERT INTO requests_daily_social (day, referrer_domain, count)
        SELECT date(ts), referrer_domain, COUNT(*)
        FROM requests
        WHERE date(ts) >= ?
          AND referrer_domain IN ('reddit.com','twitter.com','x.com','facebook.com','linkedin.com','t.co','news.ycombinator.com')
        GROUP BY 1, 2
    """, (cutoff,))
    r2 = conn.execute("SELECT COUNT(*) FROM requests_daily_social WHERE day >= ?", (cutoff,)).fetchone()[0]
    print(f"  requests_daily_social: {r2} rows refreshed", flush=True)

    # 3. requests_daily_new_ai
    conn.execute("DELETE FROM requests_daily_new_ai WHERE day >= ?", (cutoff,))
    conn.execute("""
        INSERT INTO requests_daily_new_ai (day, bot_category, count)
        SELECT date(ts),
          CASE
            WHEN user_agent LIKE '%Grok%' THEN 'Grok'
            WHEN user_agent LIKE '%DeepSeek%' THEN 'DeepSeek'
            WHEN user_agent LIKE '%MistralAI%' THEN 'Mistral'
            WHEN user_agent LIKE '%Sogou%' THEN 'Sogou'
            WHEN user_agent LIKE '%Baiduspider%' THEN 'Baidu'
            WHEN user_agent LIKE '%Yeti%' THEN 'Naver'
            WHEN user_agent LIKE '%DuckDuckBot%' THEN 'DuckDuckBot'
            WHEN user_agent LIKE '%coccocbot%' THEN 'CocCoc'
            WHEN user_agent LIKE '%LinkedInBot%' THEN 'LinkedIn'
            WHEN user_agent LIKE '%NotebookLM%' THEN 'NotebookLM'
            WHEN user_agent LIKE '%BraveSearch%' THEN 'Brave'
            WHEN user_agent LIKE '%kagi%' THEN 'Kagi'
          END,
          COUNT(*)
        FROM requests
        WHERE date(ts) >= ?
          AND (user_agent LIKE '%Grok%' OR user_agent LIKE '%DeepSeek%'
            OR user_agent LIKE '%MistralAI%' OR user_agent LIKE '%Sogou%'
            OR user_agent LIKE '%Baiduspider%' OR user_agent LIKE '%Yeti%'
            OR user_agent LIKE '%DuckDuckBot%' OR user_agent LIKE '%coccocbot%'
            OR user_agent LIKE '%LinkedInBot%' OR user_agent LIKE '%NotebookLM%'
            OR user_agent LIKE '%BraveSearch%' OR user_agent LIKE '%kagi%')
        GROUP BY 1, 2
    """, (cutoff,))
    r3 = conn.execute("SELECT COUNT(*) FROM requests_daily_new_ai WHERE day >= ?", (cutoff,)).fetchone()[0]
    print(f"  requests_daily_new_ai: {r3} rows refreshed", flush=True)

    # 4. preflight_daily
    conn.execute("DELETE FROM preflight_daily WHERE day >= ?", (cutoff,))
    conn.execute("""
        INSERT INTO preflight_daily (day, bot_name, count)
        SELECT date(ts), bot_name, COUNT(*)
        FROM preflight_analytics
        WHERE date(ts) >= ?
        GROUP BY 1, 2
    """, (cutoff,))
    r4 = conn.execute("SELECT COUNT(*) FROM preflight_daily WHERE day >= ?", (cutoff,)).fetchone()[0]
    print(f"  preflight_daily: {r4} rows refreshed", flush=True)

    conn.commit()
    conn.close()

    elapsed = time.time() - start
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DONE in {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    try:
        refresh()
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"ERROR: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)
