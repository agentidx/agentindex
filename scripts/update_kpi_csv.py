#!/usr/bin/env python3
"""
Auto-update indexation_kpi.csv with data from analytics.db + PostgreSQL.
Runs daily via LaunchAgent. Appends one row per calendar day.

Data sources:
  - analytics.db: AI citations, preflight, per-bot breakdown (calendar day UTC)
  - PostgreSQL: enriched count, indexable pages

Counting method:
  - ai_citations_24h = all is_ai_bot=1 requests (any status) excluding /v1/preflight
  - Per-bot: matched by bot_name LIKE pattern
  - enriched = cumulative COUNT(enriched_at IS NOT NULL) from software_registry
  - indexable_pages = enriched × avg patterns per entity × LANGS
"""

import csv
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/agentindex"))

ANALYTICS_DB = os.path.expanduser("~/agentindex/logs/analytics.db")
KPI_CSV = os.path.expanduser("~/agentindex/logs/indexation_kpi.csv")
PSQL = "/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"
LANGS = 22

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("kpi-csv")


def get_existing_dates():
    """Read existing CSV and return set of dates already recorded."""
    dates = set()
    if not os.path.exists(KPI_CSV):
        return dates
    with open(KPI_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            dates.add(row.get("date", ""))
    return dates


def get_analytics_for_date(dt_str):
    """Get AI citation data from analytics.db for a specific calendar day."""
    conn = sqlite3.connect(ANALYTICS_DB, timeout=30)
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as total_ai,
                SUM(CASE WHEN bot_name LIKE '%ChatGPT%' OR bot_name LIKE '%OpenAI%' THEN 1 ELSE 0 END) as chatgpt,
                SUM(CASE WHEN bot_name LIKE '%Claude%' THEN 1 ELSE 0 END) as claude,
                SUM(CASE WHEN bot_name LIKE '%Byte%' OR bot_name LIKE '%bytespider%' THEN 1 ELSE 0 END) as bytedance,
                SUM(CASE WHEN bot_name LIKE '%Perplexity%' THEN 1 ELSE 0 END) as perplexity
            FROM requests
            WHERE DATE(ts) = ?
              AND is_ai_bot = 1
              AND path NOT LIKE '/v1/preflight%'
        """, (dt_str,)).fetchone()
        return {
            "ai_citations_24h": row[0] or 0,
            "chatgpt_24h": row[1] or 0,
            "claude_24h": row[2] or 0,
            "bytedance_24h": row[3] or 0,
            "perplexity_24h": row[4] or 0,
        }
    finally:
        conn.close()


def get_enrichment_data(dt_str):
    """Get enrichment data from PostgreSQL for a specific date."""
    try:
        # Cumulative enriched up to and including this date
        result = subprocess.run(
            [PSQL, "-d", "agentindex", "-t", "-A", "-F", "|", "-c",
             f"SELECT COUNT(*) as enriched, "
             f"COUNT(*) FILTER (WHERE enriched_at <= '{dt_str} 23:59:59') as enriched_by_date "
             f"FROM software_registry WHERE enriched_at IS NOT NULL"],
            capture_output=True, text=True, timeout=30
        )
        parts = result.stdout.strip().split("|")
        total_enriched = int(parts[0]) if parts[0] else 0

        # For historical dates, use enriched_at <= date; for today use total
        if dt_str == str(date.today()):
            enriched = total_enriched
        else:
            enriched = int(parts[1]) if len(parts) > 1 and parts[1] else total_enriched

        # New enriched in 24h
        result2 = subprocess.run(
            [PSQL, "-d", "agentindex", "-t", "-A", "-c",
             f"SELECT COUNT(*) FROM software_registry "
             f"WHERE enriched_at >= '{dt_str} 00:00:00' AND enriched_at < '{dt_str} 23:59:59'"],
            capture_output=True, text=True, timeout=30
        )
        new_enriched = int(result2.stdout.strip()) if result2.stdout.strip() else 0

        # Indexable pages: enriched × average patterns (~13) × LANGS
        indexable = enriched * 13 * LANGS

        # Citations per 1K pages
        return {
            "enriched": enriched,
            "indexable_pages": indexable,
            "new_enriched_24h": new_enriched,
        }
    except Exception as e:
        log.warning("PostgreSQL error: %s", e)
        return {"enriched": 0, "indexable_pages": 0, "new_enriched_24h": 0}


def main():
    log.info("Updating KPI CSV...")

    existing = get_existing_dates()
    log.info("Existing dates: %d", len(existing))

    # Find dates that need data: from first analytics day to yesterday
    conn = sqlite3.connect(ANALYTICS_DB, timeout=30)
    first_day = conn.execute("SELECT MIN(DATE(ts)) FROM requests WHERE is_ai_bot=1").fetchone()[0]
    conn.close()

    if not first_day:
        log.info("No analytics data found")
        return

    start = date.fromisoformat(first_day)
    end = date.today() - timedelta(days=1)  # Only complete days

    missing = []
    d = start
    while d <= end:
        ds = d.isoformat()
        if ds not in existing:
            missing.append(ds)
        d += timedelta(days=1)

    if not missing:
        log.info("All dates up to %s already in CSV", end)
        return

    log.info("Missing dates: %d (%s to %s)", len(missing), missing[0], missing[-1])

    # Collect data for missing dates
    new_rows = []
    for dt_str in missing:
        analytics = get_analytics_for_date(dt_str)
        enrichment = get_enrichment_data(dt_str)

        citations = analytics["ai_citations_24h"]
        pages = enrichment["indexable_pages"]
        cpk = round(citations / max(pages / 1000, 1), 2) if pages > 0 else 0

        row = {
            "date": dt_str,
            "enriched": enrichment["enriched"],
            "indexable_pages": pages,
            "ai_citations_24h": citations,
            "citations_per_1k_pages": cpk,
            "new_enriched_24h": enrichment["new_enriched_24h"],
            "chatgpt_24h": analytics["chatgpt_24h"],
            "claude_24h": analytics["claude_24h"],
            "bytedance_24h": analytics["bytedance_24h"],
            "perplexity_24h": analytics["perplexity_24h"],
        }
        new_rows.append(row)
        log.info("  %s: citations=%d, enriched=%d, pages=%s",
                 dt_str, citations, enrichment["enriched"], enrichment["indexable_pages"])

    # Read existing CSV, merge, sort, write
    all_rows = []
    if os.path.exists(KPI_CSV):
        with open(KPI_CSV) as f:
            all_rows = list(csv.DictReader(f))

    # Remove duplicates (keep new data for dates that exist)
    new_dates = {r["date"] for r in new_rows}
    all_rows = [r for r in all_rows if r["date"] not in new_dates]
    all_rows.extend(new_rows)

    # Sort by date, remove duplicate dates (keep latest)
    seen = {}
    for r in all_rows:
        seen[r["date"]] = r  # last wins
    all_rows = sorted(seen.values(), key=lambda r: r["date"])

    # Write
    fields = ["date", "enriched", "indexable_pages", "ai_citations_24h",
              "citations_per_1k_pages", "new_enriched_24h",
              "chatgpt_24h", "claude_24h", "bytedance_24h", "perplexity_24h"]
    with open(KPI_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    log.info("Written %d rows to %s (%d new)", len(all_rows), KPI_CSV, len(new_rows))


if __name__ == "__main__":
    main()
