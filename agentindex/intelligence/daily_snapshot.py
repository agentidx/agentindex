#!/usr/bin/env python3
"""
Daily Signal Warehouse Collection
====================================
Captures trust snapshots, changes, AI behavior, ecosystem metrics, signal events.
Run daily at 04:00 via LaunchAgent.
"""

import json, logging, os, sqlite3, sys, time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agentindex.db.models import get_session
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("/tmp/daily_snapshot.log")])
logger = logging.getLogger("signal_warehouse")

TODAY = date.today()
ANALYTICS_DB = str(Path(__file__).parent.parent.parent / "logs" / "analytics.db")


def collect_software_snapshots(session):
    """Snapshot ALL software_registry entries in batches."""
    logger.info("Collecting software_registry snapshots...")
    # Batch by registry to avoid timeout
    regs = session.execute(text("SELECT DISTINCT registry FROM software_registry")).fetchall()
    total = 0
    for (reg,) in regs:
        try:
            session.execute(text("""
                INSERT INTO daily_snapshots (date, entity_type, entity_id, registry, trust_score, trust_grade, downloads, stars)
                SELECT :today, 'package', slug, registry, trust_score, trust_grade, downloads, stars
                FROM software_registry WHERE registry = :reg
                ON CONFLICT (date, entity_type, entity_id, registry) DO NOTHING
            """), {"today": TODAY.isoformat(), "reg": reg})
            session.commit()
            cnt = session.execute(text("SELECT COUNT(*) FROM daily_snapshots WHERE date = :d AND registry = :reg AND entity_type = 'package'"),
                                {"d": TODAY.isoformat(), "reg": reg}).fetchone()[0]
            total += cnt
            logger.info(f"    {reg}: {cnt:,} snapshots")
        except Exception as e:
            logger.warning(f"    {reg}: error - {e}")
            session.rollback()
    logger.info(f"  Software snapshots total: {total:,}")
    return total


def collect_agent_snapshots(session):
    """Snapshot top 100K agents in batches to avoid timeout."""
    logger.info("Collecting agent snapshots (top 100K, batched)...")
    batch_size = 10000
    total = 0
    for offset in range(0, 100000, batch_size):
        try:
            session.execute(text("""
                INSERT INTO daily_snapshots (date, entity_type, entity_id, registry, trust_score, trust_grade, downloads, stars)
                SELECT :today, 'agent', name, source, trust_score_v2, trust_grade, downloads, stars
                FROM agents
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                ORDER BY COALESCE(stars, 0) DESC
                LIMIT :lim OFFSET :off
                ON CONFLICT (date, entity_type, entity_id, registry) DO NOTHING
            """), {"today": TODAY.isoformat(), "lim": batch_size, "off": offset})
            session.commit()
            total += batch_size
        except Exception as e:
            logger.warning(f"  Agent batch offset {offset}: {e}")
            session.rollback()
            break
    count = session.execute(text("SELECT COUNT(*) FROM daily_snapshots WHERE date = :d AND entity_type = 'agent'"),
                           {"d": TODAY.isoformat()}).fetchone()[0]
    logger.info(f"  Agent snapshots: {count:,}")
    return count


def collect_website_snapshots(session):
    """Snapshot ALL website_cache entries."""
    logger.info("Collecting website snapshots...")
    result = session.execute(text("""
        INSERT INTO website_daily (date, domain, trust_score, ssl_valid, has_hsts, tranco_rank)
        SELECT :today, domain, trust_score, ssl_valid, has_hsts, tranco_rank
        FROM website_cache
        ON CONFLICT DO NOTHING
    """), {"today": TODAY.isoformat()})
    session.commit()
    count = session.execute(text("SELECT COUNT(*) FROM website_daily WHERE date = :d"),
                           {"d": TODAY.isoformat()}).fetchone()[0]
    logger.info(f"  Website snapshots: {count:,}")
    return count


def collect_entity_snapshots(session):
    """Snapshot ALL entity_ratings."""
    logger.info("Collecting entity rating snapshots...")
    result = session.execute(text("""
        INSERT INTO daily_snapshots (date, entity_type, entity_id, registry, trust_score, trust_grade, extra)
        SELECT :today, entity_type, entity_slug, 'entity_rating', score, rating,
               jsonb_build_object('tools_found', tools_found, 'critical_issues', critical_issues)
        FROM entity_ratings WHERE score > 0
        ON CONFLICT (date, entity_type, entity_id, registry) DO NOTHING
    """), {"today": TODAY.isoformat()})
    session.commit()
    count = session.execute(text("SELECT COUNT(*) FROM daily_snapshots WHERE date = :d AND registry = 'entity_rating'"),
                           {"d": TODAY.isoformat()}).fetchone()[0]
    logger.info(f"  Entity rating snapshots: {count:,}")
    return count


def detect_trust_changes(session):
    """Compare today's scores to yesterday's, log changes > 2 points."""
    logger.info("Detecting trust changes...")
    yesterday = (TODAY.toordinal() - 1)
    from datetime import date as dt
    yesterday_date = dt.fromordinal(yesterday).isoformat()

    result = session.execute(text("""
        INSERT INTO trust_changes (date, entity_id, entity_type, registry, old_score, new_score, change, reason)
        SELECT :today, t.entity_id, t.entity_type, t.registry,
               y.trust_score, t.trust_score, t.trust_score - y.trust_score,
               CASE WHEN t.trust_score - y.trust_score > 10 THEN 'major_improvement'
                    WHEN t.trust_score - y.trust_score > 2 THEN 'improvement'
                    WHEN t.trust_score - y.trust_score < -10 THEN 'major_decline'
                    WHEN t.trust_score - y.trust_score < -2 THEN 'decline'
                    ELSE 'minor_change' END
        FROM daily_snapshots t
        JOIN daily_snapshots y ON y.entity_id = t.entity_id
                               AND y.entity_type = t.entity_type
                               AND y.registry = t.registry
                               AND y.date = :yesterday
        WHERE t.date = :today
        AND t.trust_score IS NOT NULL AND y.trust_score IS NOT NULL
        AND ABS(t.trust_score - y.trust_score) > 2
        ON CONFLICT DO NOTHING
    """), {"today": TODAY.isoformat(), "yesterday": yesterday_date})
    session.commit()
    count = session.execute(text("SELECT COUNT(*) FROM trust_changes WHERE date = :d"),
                           {"d": TODAY.isoformat()}).fetchone()[0]
    logger.info(f"  Trust changes detected: {count:,}")

    # Log major changes as signal events
    major = session.execute(text("""
        SELECT entity_id, change, registry FROM trust_changes
        WHERE date = :d AND ABS(change) > 10
    """), {"d": TODAY.isoformat()}).fetchall()
    for m in major:
        session.execute(text("""
            INSERT INTO signal_events (date, signal_type, severity, entity_id, registry, description)
            VALUES (:d, :type, 'high', :eid, :reg, :desc)
        """), {"d": TODAY.isoformat(),
               "type": "trust_drop_10plus" if m[1] < 0 else "trust_gain_10plus",
               "eid": m[0], "reg": m[2],
               "desc": f"Trust score changed by {m[1]:+.1f} points"})
    session.commit()
    logger.info(f"  Major changes (signal events): {len(major)}")
    return count


def collect_ai_behavior(session):
    """Aggregate AI bot access from analytics DB."""
    logger.info("Collecting AI behavior...")
    if not os.path.exists(ANALYTICS_DB):
        logger.warning("Analytics DB not found"); return 0

    try:
        conn = sqlite3.connect(ANALYTICS_DB, timeout=5)
        rows = conn.execute("""
            SELECT
                CASE WHEN path LIKE '/safe/%' THEN REPLACE(path, '/safe/', '')
                     WHEN path LIKE '/is-%' THEN SUBSTR(path, 5)
                     ELSE path END as entity,
                CASE WHEN user_agent LIKE '%ChatGPT%' THEN 'chatgpt'
                     WHEN user_agent LIKE '%GPTBot%' THEN 'gptbot'
                     WHEN user_agent LIKE '%Perplexity%' THEN 'perplexity'
                     WHEN user_agent LIKE '%Claude%' THEN 'claude'
                     WHEN user_agent LIKE '%Google%' THEN 'google'
                     ELSE 'other' END as bot,
                CASE WHEN path LIKE '/is-%-safe%' THEN 'safety'
                     WHEN path LIKE '/privacy/%' THEN 'privacy'
                     WHEN path LIKE '/compare/%' THEN 'compare'
                     WHEN path LIKE '/is-%-legit%' THEN 'legit'
                     WHEN path LIKE '/review/%' THEN 'review'
                     ELSE 'other' END as pattern,
                COUNT(*) as cnt,
                MIN(ts) as first, MAX(ts) as last
            FROM requests
            WHERE is_bot = 1
            AND ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-24 hours')
            AND path NOT LIKE '/static%' AND path NOT LIKE '/sitemap%' AND path NOT LIKE '/robots%'
            GROUP BY entity, bot, pattern
            HAVING cnt >= 2
            ORDER BY cnt DESC
            LIMIT 5000
        """).fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f"Analytics query failed: {e}"); return 0

    count = 0
    for entity, bot, pattern, cnt, first, last in rows:
        try:
            session.execute(text("""
                INSERT INTO ai_behavior_daily (date, entity_id, bot, page_pattern, request_count, first_seen, last_seen)
                VALUES (:d, :eid, :bot, :pat, :cnt, :first, :last)
            """), {"d": TODAY.isoformat(), "eid": entity[:200], "bot": bot,
                  "pat": pattern, "cnt": cnt, "first": first, "last": last})
            count += 1
        except Exception:
            session.rollback()

    session.commit()
    logger.info(f"  AI behavior entries: {count:,}")
    return count


def collect_ecosystem_metrics(session):
    """Per-registry aggregate metrics."""
    logger.info("Collecting ecosystem metrics...")

    rows = session.execute(text("""
        SELECT registry, COUNT(*) as total,
               AVG(trust_score) as avg_ts,
               COUNT(CASE WHEN trust_score >= 70 THEN 1 END) as above_70,
               COUNT(CASE WHEN trust_score < 30 THEN 1 END) as below_30,
               SUM(downloads) as total_dl
        FROM software_registry
        GROUP BY registry
    """)).fetchall()

    count = 0
    for r in rows:
        try:
            session.execute(text("""
                INSERT INTO ecosystem_daily (date, registry, total_entities, avg_trust_score,
                    entities_above_70, entities_below_30, total_downloads)
                VALUES (:d, :reg, :total, :avg, :above, :below, :dl)
            """), {"d": TODAY.isoformat(), "reg": r[0], "total": r[1],
                  "avg": float(r[2]) if r[2] else 0, "above": r[3] or 0,
                  "below": r[4] or 0, "dl": r[5] or 0})
            count += 1
        except Exception:
            session.rollback()

    session.commit()
    logger.info(f"  Ecosystem metrics: {count} registries")
    return count


def _set_timeout(session, seconds=300):
    """Set statement_timeout for the current session (survives commits and rollbacks)."""
    session.execute(text(f"SET statement_timeout = '{seconds}s'"))


def main():
    start = time.time()
    logger.info(f"=== DAILY SNAPSHOT {TODAY} ===")

    session = get_session()
    try:
        # Set generous timeout for batch operations (not the API's 5s)
        _set_timeout(session, 300)

        collectors = [
            ("Software", collect_software_snapshots),
            ("Agents", collect_agent_snapshots),
            ("Websites", collect_website_snapshots),
            ("Entity ratings", collect_entity_snapshots),
            ("Trust changes", detect_trust_changes),
            ("AI behavior", collect_ai_behavior),
            ("Ecosystem", collect_ecosystem_metrics),
        ]

        results = {}
        for name, fn in collectors:
            try:
                _set_timeout(session, 300)
                results[name] = fn(session)
            except Exception as e:
                logger.error(f"  {name} FAILED: {e}")
                session.rollback()
                results[name] = 0

        elapsed = time.time() - start
        logger.info(f"=== SNAPSHOT COMPLETE ({elapsed:.0f}s) ===")
        for name, count in results.items():
            logger.info(f"  {name}: {count:,}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
