"""
Website Trust Score Re-scorer
==============================
Widens Tranco rank buckets for websites. Data already exists in downloads column.
No external API calls needed — just re-calculates scores with wider differentiation.

Usage:
    python -m agentindex.crawlers.website_rescore [--batch 50000] [--dry-run]
"""
import argparse
import logging
import os

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [website-rescore] %(message)s")
logger = logging.getLogger("website-rescore")

DB_DSN = os.environ.get("DATABASE_URL", "dbname=agentindex")


def rescore_website(cur, pkg_id, tranco_rank, sec, maint, comm, qual):
    """Recalculate trust_score using Tranco rank with wider buckets."""
    # Tranco rank: lower = more popular. 0 = unknown.
    if tranco_rank <= 0:
        pop = 20  # Unknown
    elif tranco_rank <= 100:
        pop = 98  # Top 100 websites
    elif tranco_rank <= 1_000:
        pop = 92
    elif tranco_rank <= 5_000:
        pop = 85
    elif tranco_rank <= 10_000:
        pop = 78
    elif tranco_rank <= 50_000:
        pop = 70
    elif tranco_rank <= 100_000:
        pop = 60
    elif tranco_rank <= 250_000:
        pop = 50
    elif tranco_rank <= 500_000:
        pop = 40
    elif tranco_rank <= 1_000_000:
        pop = 30
    else:
        pop = 20

    total = round((sec or 90) * 0.25 + (maint or 50) * 0.25 + pop * 0.15 + (comm or 35) * 0.15 + (qual or 30) * 0.20, 1)
    grade = ("A+" if total >= 90 else "A" if total >= 85 else "A-" if total >= 80 else
             "B+" if total >= 75 else "B" if total >= 70 else "B-" if total >= 65 else
             "C+" if total >= 60 else "C" if total >= 55 else "C-" if total >= 50 else
             "D" if total >= 40 else "F")

    cur.execute(
        "UPDATE software_registry SET trust_score=%s, trust_grade=%s, popularity_score=%s WHERE id=%s",
        (total, grade, round(pop, 1), pkg_id)
    )


def run(batch_size=50000, dry_run=False):
    conn = psycopg2.connect(DB_DSN, options="-c statement_timeout=60000")
    conn.autocommit = True
    cur = conn.cursor()

    # Check current distribution
    cur.execute("""
        SELECT ROUND(AVG(trust_score)::numeric,1), ROUND(STDDEV(trust_score)::numeric,1),
               MIN(trust_score), MAX(trust_score)
        FROM software_registry WHERE registry='website' AND trust_score IS NOT NULL
    """)
    r = cur.fetchone()
    logger.info(f"BEFORE: avg={r[0]}, stddev={r[1]}, min={r[2]}, max={r[3]}")

    if dry_run:
        # Show Tranco rank distribution
        cur.execute("""
            SELECT CASE
                WHEN downloads <= 1000 THEN '1-1K'
                WHEN downloads <= 10000 THEN '1K-10K'
                WHEN downloads <= 100000 THEN '10K-100K'
                WHEN downloads <= 500000 THEN '100K-500K'
                ELSE '500K+'
            END as bucket, COUNT(*)
            FROM software_registry WHERE registry='website' AND downloads > 0
            GROUP BY bucket ORDER BY MIN(downloads)
        """)
        for row in cur.fetchall():
            logger.info(f"  Tranco rank {row[0]}: {row[1]:,} websites")
        cur.close(); conn.close(); return

    # Re-score all websites
    cur.execute(
        "SELECT id, downloads, security_score, maintenance_score, community_score, quality_score "
        "FROM software_registry WHERE registry='website' AND trust_score IS NOT NULL "
        "LIMIT %s", (batch_size,)
    )
    rows = cur.fetchall()
    logger.info(f"Re-scoring {len(rows)} websites...")

    for i, (pkg_id, rank, sec, maint, comm, qual) in enumerate(rows):
        rescore_website(cur, pkg_id, rank or 0, sec, maint, comm, qual)
        if (i + 1) % 10000 == 0:
            logger.info(f"  Progress: {i+1}/{len(rows)}")

    # Check new distribution
    cur.execute("""
        SELECT ROUND(AVG(trust_score)::numeric,1), ROUND(STDDEV(trust_score)::numeric,1),
               MIN(trust_score), MAX(trust_score)
        FROM software_registry WHERE registry='website' AND trust_score IS NOT NULL
    """)
    r = cur.fetchone()
    logger.info(f"AFTER: avg={r[0]}, stddev={r[1]}, min={r[2]}, max={r[3]}")
    cur.close(); conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=50000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(batch_size=args.batch, dry_run=args.dry_run)
