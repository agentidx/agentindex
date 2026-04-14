#!/usr/bin/env python3
"""
GitHub Contributor Metrics Collector — Monthly batch job.

For each entity with a GitHub source_url, fetches:
- Active contributors (unique commit authors) in last 6 months
- Total historical contributors
- Top contributor concentration (% of commits by #1 author)

Classifies into tiers:
- dormant: 0 active contributors in 6 months
- single-maintainer: 1 active contributor
- small-team: 2-5 active contributors
- active-community: 6+ active contributors

Rate limit: GitHub API 5000 req/hr with token. Uses 2 requests per repo
(commits + contributors), so ~2500 repos/hr.

Usage:
    python3 scripts/collect_contributor_metrics.py              # run batch
    python3 scripts/collect_contributor_metrics.py --limit 100   # test with 100
    python3 scripts/collect_contributor_metrics.py --status       # show progress
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
PG_DSN = os.environ.get("DATABASE_URL", "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "contributor-metrics.log")),
    ]
)
log = logging.getLogger("contrib")

GITHUB_API = "https://api.github.com"
GITHUB_RE = re.compile(r"github\.com/([^/]+)/([^/?\#]+)")


def parse_github_url(url):
    """Extract owner/repo from a GitHub URL."""
    if not url:
        return None, None
    m = GITHUB_RE.search(url)
    if not m:
        return None, None
    owner = m.group(1)
    repo = m.group(2).rstrip(".git")
    return owner, repo


def github_get(path):
    """Make a GitHub API request with rate limit handling."""
    url = f"{GITHUB_API}{path}"
    req = urllib.request.Request(url)
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "NerqContributorCollector/1.0")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            remaining = int(resp.headers.get("X-RateLimit-Remaining", 5000))
            if remaining < 100:
                reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait = max(0, reset - time.time()) + 5
                log.warning(f"Rate limit low ({remaining}), sleeping {wait:.0f}s")
                time.sleep(wait)
            return json.loads(resp.read().decode()), resp.headers
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        if e.code == 403:
            reset = int(e.headers.get("X-RateLimit-Reset", 0))
            wait = max(0, reset - time.time()) + 10
            log.warning(f"Rate limited, sleeping {wait:.0f}s")
            time.sleep(wait)
            return None, None
        if e.code == 409:  # Empty repository
            return None, None
        log.warning(f"HTTP {e.code} for {path}")
        return None, None
    except Exception as e:
        log.warning(f"Error fetching {path}: {e}")
        return None, None


def get_active_authors(owner, repo, months=6):
    """Get unique commit authors in the last N months."""
    since = (datetime.now(timezone.utc) - timedelta(days=months * 30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    authors = set()
    page = 1

    while page <= 3:  # max 300 commits
        data, _ = github_get(f"/repos/{owner}/{repo}/commits?per_page=100&page={page}&since={since}")
        if not data or not isinstance(data, list) or len(data) == 0:
            break
        for commit in data:
            if commit.get("author") and commit["author"].get("login"):
                authors.add(commit["author"]["login"])
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.3)

    return authors


def get_contributors(owner, repo):
    """Get all-time contributors with commit counts."""
    data, _ = github_get(f"/repos/{owner}/{repo}/contributors?per_page=100")
    if not data or not isinstance(data, list):
        return [], 0
    total = sum(c.get("contributions", 0) for c in data)
    return data, total


def classify_tier(active_count):
    """Classify contributor tier."""
    if active_count == 0:
        return "dormant"
    elif active_count == 1:
        return "single-maintainer"
    elif active_count <= 5:
        return "small-team"
    else:
        return "active-community"


def get_entities_to_process(conn, limit=None):
    """Get entities with GitHub URLs, prioritized by downloads/stars."""
    cur = conn.cursor()
    cur.execute("""
        SELECT el.id, el.source_url, el.downloads, el.stars
        FROM entity_lookup el
        WHERE el.source_url LIKE '%%github.com%%'
          AND el.is_active = true
          AND NOT EXISTS (
              SELECT 1 FROM contributor_metrics cm WHERE cm.agent_id = el.id
          )
        ORDER BY COALESCE(el.downloads, 0) + COALESCE(el.stars, 0) * 10 DESC
        LIMIT %s
    """, (limit or 100000,))
    rows = cur.fetchall()
    cur.close()
    return rows


def save_metrics(conn, agent_id, owner, repo, active_authors, contributors, total_commits):
    """Save contributor metrics to Postgres."""
    active_count = len(active_authors)
    total_contribs = len(contributors)

    if total_commits > 0 and contributors:
        top_pct = contributors[0].get("contributions", 0) / total_commits
    else:
        top_pct = 1.0 if total_contribs <= 1 else 0.0

    tier = classify_tier(active_count)

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contributor_metrics
            (agent_id, repo_owner, repo_name, active_contributors_6mo,
             total_contributors, top_contributor_pct, contributor_tier)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (agent_id) DO UPDATE SET
            active_contributors_6mo = EXCLUDED.active_contributors_6mo,
            total_contributors = EXCLUDED.total_contributors,
            top_contributor_pct = EXCLUDED.top_contributor_pct,
            contributor_tier = EXCLUDED.contributor_tier,
            collected_at = NOW()
    """, (str(agent_id), owner, repo, active_count, total_contribs, round(top_pct, 4), tier))
    conn.commit()
    cur.close()
    return tier


def show_status(conn):
    """Show collection progress."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM contributor_metrics")
    collected = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM entity_lookup WHERE source_url LIKE '%%github.com%%' AND is_active = true")
    total_github = cur.fetchone()[0]

    cur.execute("""
        SELECT contributor_tier, COUNT(*) as cnt,
               ROUND(AVG(active_contributors_6mo), 1) as avg_active,
               ROUND(AVG(top_contributor_pct)::numeric, 3) as avg_concentration
        FROM contributor_metrics
        GROUP BY contributor_tier
        ORDER BY cnt DESC
    """)
    tiers = cur.fetchall()

    cur.execute("""
        SELECT ROUND(AVG(active_contributors_6mo), 1),
               ROUND(AVG(total_contributors), 1),
               ROUND(AVG(top_contributor_pct)::numeric, 3)
        FROM contributor_metrics
    """)
    avgs = cur.fetchone()

    cur.close()

    print(f"\n{'='*60}")
    print(f"Contributor Metrics Collection Status")
    print(f"{'='*60}")
    print(f"  Collected: {collected:,} / {total_github:,} GitHub entities ({collected/max(total_github,1)*100:.1f}%)")
    if avgs and avgs[0] is not None:
        print(f"  Avg active contributors (6mo): {avgs[0]}")
        print(f"  Avg total contributors: {avgs[1]}")
        print(f"  Avg top contributor concentration: {float(avgs[2]):.1%}")
    print(f"\n  Tier distribution:")
    for tier, cnt, avg_active, avg_conc in tiers:
        print(f"    {tier:<25} {cnt:>6} entities  (avg active: {avg_active}, concentration: {float(avg_conc):.1%})")
    print(f"{'='*60}")


def run(limit=None):
    import psycopg2

    if not GITHUB_TOKEN:
        log.error("GITHUB_TOKEN required. Set it as environment variable.")
        sys.exit(1)

    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False

    entities = get_entities_to_process(conn, limit)
    log.info(f"Entities to process: {len(entities)}")

    if not entities:
        log.info("All GitHub entities already processed!")
        show_status(conn)
        conn.close()
        return

    processed = 0
    errors = 0
    skipped = 0
    tier_counts = {"dormant": 0, "single-maintainer": 0, "small-team": 0, "active-community": 0}
    t0 = time.time()

    for agent_id, source_url, downloads, stars in entities:
        owner, repo = parse_github_url(source_url)
        if not owner or not repo:
            skipped += 1
            continue

        try:
            active_authors = get_active_authors(owner, repo)
            contributors, total_commits = get_contributors(owner, repo)
            tier = save_metrics(conn, agent_id, owner, repo, active_authors, contributors, total_commits)
            tier_counts[tier] += 1
            processed += 1

            if processed % 100 == 0:
                elapsed = time.time() - t0
                rate = processed / max(elapsed, 1)
                remaining = (len(entities) - processed - skipped) / max(rate, 0.01)
                log.info(
                    f"  Progress: {processed}/{len(entities)} ({rate:.1f}/s, ~{remaining/3600:.1f}h remaining). "
                    f"Tiers: d={tier_counts['dormant']} s={tier_counts['single-maintainer']} "
                    f"t={tier_counts['small-team']} a={tier_counts['active-community']}"
                )

        except Exception as e:
            log.warning(f"Error processing {owner}/{repo}: {e}")
            errors += 1
            try:
                conn.rollback()
            except Exception:
                conn = psycopg2.connect(PG_DSN)
                conn.autocommit = False

        time.sleep(0.5)  # ~2 API calls per entity, stay under 5000/hr

    elapsed = time.time() - t0
    log.info(f"\nBatch complete: {processed} processed, {skipped} skipped, {errors} errors, {elapsed/60:.0f} min")
    log.info(f"Tiers: {tier_counts}")
    show_status(conn)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitHub Contributor Metrics Collector")
    parser.add_argument("--limit", type=int, help="Max entities to process")
    parser.add_argument("--status", action="store_true", help="Show progress only")
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)

    if args.status:
        import psycopg2
        conn = psycopg2.connect(PG_DSN)
        show_status(conn)
        conn.close()
    else:
        run(limit=args.limit)
