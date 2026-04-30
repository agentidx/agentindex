"""
npm Bulk Enricher — Fast download + GitHub stars enrichment.
Uses bulk npm downloads API (128 packages/request) and batch GitHub.
Target: 10,000+ packages/hour.

Usage:
    python -m agentindex.crawlers.npm_bulk_enricher [--batch 10000] [--dry-run]
"""
import argparse
import json
import logging
import os
import re
import time
from datetime import datetime

import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [npm-bulk] %(message)s")
log = logging.getLogger("npm-bulk")

from agentindex.db_config import get_write_dsn
DB_DSN = os.environ.get("DATABASE_URL") or get_write_dsn(fmt="psycopg2")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
NPM_DL_BULK = "https://api.npmjs.org/downloads/point/last-month"
NPM_REGISTRY = "https://registry.npmjs.org"
STATE_FILE = os.path.expanduser("~/agentindex/logs/npm_bulk_state.json")
BULK_SIZE = 128  # Max packages per npm bulk download request


def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"processed": 0, "updated_dl": 0, "updated_stars": 0}


def _save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def _gh_headers():
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def fetch_bulk_downloads(names):
    """Fetch downloads for up to 128 packages in one request."""
    scoped = ",".join(names[:BULK_SIZE])
    try:
        resp = requests.get(f"{NPM_DL_BULK}/{scoped}", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            # Response is {pkg_name: {downloads: N, ...}} for bulk
            if isinstance(data, dict):
                result = {}
                for name in names:
                    pkg_data = data.get(name, {})
                    if isinstance(pkg_data, dict):
                        result[name] = pkg_data.get("downloads", 0)
                return result
    except Exception as e:
        log.warning(f"Bulk download fetch failed: {e}")
    return {}


def fetch_npm_metadata(name):
    """Fetch repo URL + license + version count from npm registry (lightweight)."""
    try:
        # Use abbreviated metadata (faster, smaller response)
        resp = requests.get(f"{NPM_REGISTRY}/{name}", timeout=8,
                           headers={"Accept": "application/vnd.npm.install-v1+json"})
        if resp.status_code == 200:
            data = resp.json()
            versions = data.get("versions", {})
            dist_tags = data.get("dist-tags", {})
            latest = dist_tags.get("latest", "")
            latest_data = versions.get(latest, {})

            repo = latest_data.get("repository", data.get("repository", {}))
            repo_url = None
            if isinstance(repo, dict):
                repo_url = repo.get("url", "")
            elif isinstance(repo, str):
                repo_url = repo
            if repo_url:
                repo_url = repo_url.replace("git+", "").replace("git://", "https://").replace(".git", "")
                if not repo_url.startswith("http"):
                    repo_url = None

            return {
                "repo_url": repo_url,
                "release_count": len(versions),
                "license": (data.get("license") or latest_data.get("license") or ""),
            }
    except Exception:
        pass
    return {}


def fetch_github_stars(repo_url):
    """Extract owner/repo from URL and fetch stars."""
    if not repo_url:
        return 0, 0
    m = re.search(r"github\.com[/:]([^/]+)/([^/\s?#]+)", repo_url)
    if not m:
        return 0, 0
    owner, repo = m.group(1), m.group(2).rstrip("/")
    try:
        resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}",
                           headers=_gh_headers(), timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("stargazers_count", 0), data.get("forks_count", 0)
    except Exception:
        pass
    return 0, 0


def run(batch_size=10000, dry_run=False):
    state = _load_state()
    # TCP keepalives: this run can take 30+ minutes; without keepalives,
    # network middleboxes silently drop the SSL connection and the final
    # report query fails with "SSL connection has been closed unexpectedly".
    conn = psycopg2.connect(
        DB_DSN,
        options="-c statement_timeout=30000 -c application_name=nerq_enricher",
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=10,
        keepalives_count=6,
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Get packages to enrich. Mix two cohorts so the rate is sustained
    # post-2026-04-30 fix (the original WHERE clause only picked
    # never-enriched rows, which converged on a stuck set of dead packages
    # and produced 0 updates per run):
    #
    #   1. ~30% never-enriched (downloads NULL or 0)
    #   2. ~70% stale-but-enriched (updated_at < NOW() - 14 days)
    #
    # ORDER BY ensures deterministic-ish progress through the long tail
    # without re-hitting the same rows every 30-min cycle.
    _never_n = max(1, batch_size // 3)
    _stale_n = batch_size - _never_n
    cur.execute("""
        (
            SELECT id, name, downloads, stars, repository_url, 'never'::text AS cohort
            FROM software_registry
            WHERE registry = 'npm'
              AND (downloads IS NULL OR downloads <= 0)
            ORDER BY name
            LIMIT %s
        )
        UNION ALL
        (
            SELECT id, name, downloads, stars, repository_url, 'stale'::text AS cohort
            FROM software_registry
            WHERE registry = 'npm'
              AND downloads IS NOT NULL AND downloads > 0
              AND (updated_at IS NULL OR updated_at < NOW() - INTERVAL '14 days')
            ORDER BY updated_at NULLS FIRST, name
            LIMIT %s
        )
    """, (_never_n, _stale_n))
    rows = cur.fetchall()
    log.info(
        f"Processing {len(rows)} npm packages (batch={batch_size}, "
        f"never-enriched cohort={_never_n}, stale-cohort={_stale_n})"
    )

    if dry_run:
        log.info("DRY RUN")
        cur.close(); conn.close(); return

    # Phase 1: Bulk download counts (128 at a time — very fast)
    names = [r[1] for r in rows]
    id_map = {r[1]: r[0] for r in rows}
    dl_map = {r[1]: r[2] or 0 for r in rows}
    star_map = {r[1]: r[3] or 0 for r in rows}
    repo_map = {r[1]: r[4] for r in rows}
    cohort_map = {r[1]: (r[5] if len(r) > 5 else "never") for r in rows}

    updated_dl = 0
    refreshed_only = 0
    for i in range(0, len(names), BULK_SIZE):
        chunk = names[i:i+BULK_SIZE]
        downloads = fetch_bulk_downloads(chunk)
        for name, dl in downloads.items():
            if dl > 0 and dl > dl_map.get(name, 0):
                # Real download bump
                cur.execute(
                    "UPDATE software_registry SET downloads=%s, weekly_downloads=%s, "
                    "updated_at=NOW() WHERE id=%s",
                    (dl, dl, id_map[name]),
                )
                dl_map[name] = dl
                updated_dl += 1
            elif cohort_map.get(name) == "stale":
                # Stale-cohort row: refresh updated_at even if downloads
                # didn't actually change. This is what restores the
                # entity_lookup sync rate post-2026-04-30 — the trigger
                # on agents/software_registry was firing only on real
                # data deltas, which were vanishingly rare.
                cur.execute(
                    "UPDATE software_registry SET updated_at=NOW() WHERE id=%s",
                    (id_map[name],),
                )
                refreshed_only += 1
        time.sleep(0.3)  # Light rate limit for bulk API
        if (i + BULK_SIZE) % 1000 < BULK_SIZE:
            log.info(
                f"  Downloads: {i+len(chunk)}/{len(names)}, "
                f"updated: {updated_dl}, refreshed: {refreshed_only}"
            )

    log.info(f"Downloads phase complete: {updated_dl} updated, {refreshed_only} stale-refreshed")

    # Phase 2: GitHub stars for packages with repo URL but no stars
    need_stars = [(n, repo_map[n]) for n in names if star_map.get(n, 0) == 0 and repo_map.get(n)]
    log.info(f"Fetching GitHub stars for {len(need_stars)} packages")

    updated_stars = 0
    gh_rate = 0.8 if GITHUB_TOKEN else 60.0
    for i, (name, repo_url) in enumerate(need_stars):
        stars, forks = fetch_github_stars(repo_url)
        if stars > 0:
            cur.execute("UPDATE software_registry SET stars=%s, forks=%s WHERE id=%s",
                       (stars, forks, id_map[name]))
            updated_stars += 1
        if (i + 1) % 500 == 0:
            log.info(f"  Stars: {i+1}/{len(need_stars)}, updated: {updated_stars}")
        time.sleep(gh_rate)

    # Phase 3: Metadata for packages without repo URL (to get it)
    no_repo = [n for n in names if not repo_map.get(n) and star_map.get(n, 0) == 0][:2000]
    log.info(f"Fetching npm metadata for {len(no_repo)} packages without repo URL")
    for i, name in enumerate(no_repo):
        meta = fetch_npm_metadata(name)
        if meta.get("repo_url"):
            cur.execute("UPDATE software_registry SET repository_url=%s, release_count=%s, license=COALESCE(NULLIF(%s,''),license) WHERE id=%s",
                       (meta["repo_url"], meta.get("release_count", 0), str(meta.get("license", ""))[:100], id_map[name]))
        if (i + 1) % 500 == 0:
            log.info(f"  Metadata: {i+1}/{len(no_repo)}")
        time.sleep(0.05)

    state["processed"] = state.get("processed", 0) + len(rows)
    state["updated_dl"] = state.get("updated_dl", 0) + updated_dl
    state["updated_stars"] = state.get("updated_stars", 0) + updated_stars
    _save_state(state)

    # Report
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE downloads > 0) as has_dl,
               COUNT(*) FILTER (WHERE stars > 0) as has_stars,
               COUNT(*) as total
        FROM software_registry WHERE registry='npm'
    """)
    r = cur.fetchone()
    log.info(f"npm totals: {r[0]}/{r[2]} have downloads, {r[1]}/{r[2]} have stars")
    log.info(f"Session: +{updated_dl} downloads, +{updated_stars} stars")

    cur.close(); conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=10000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(batch_size=args.batch, dry_run=args.dry_run)
