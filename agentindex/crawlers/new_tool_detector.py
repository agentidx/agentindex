#!/usr/bin/env python3
"""
New Tool Detector
=================
Scans GitHub and npm for newly published AI-related repos/packages and
checks whether they are already in our agents database (PostgreSQL).
Results are written to ~/agentindex/data/new_tools_detected.json.

Usage:
    python3 agentindex/crawlers/new_tool_detector.py --scan    # run full scan
    python3 agentindex/crawlers/new_tool_detector.py --report  # show last results

Does NOT auto-add to DB or create pages — detection only.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx
import psycopg2

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [new-tool-detector] %(message)s",
)
logger = logging.getLogger("new-tool-detector")

RESULTS_PATH = Path(os.path.expanduser("~/agentindex/data/new_tools_detected.json"))

# Load env (best-effort — file may not exist in all environments)
_env_file = Path(os.path.expanduser("~/agentindex/.env"))
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

GITHUB_TOKEN: Optional[str] = os.environ.get("GITHUB_TOKEN")
from agentindex.db_config import get_read_dsn
DATABASE_URL: str = os.environ.get("DATABASE_URL") or get_read_dsn()

# GitHub search: repos created within the last N days
GITHUB_LOOKBACK_DAYS = 7
GITHUB_MIN_STARS = 50

# GitHub search queries
GITHUB_QUERIES = [
    "agent in:name,description,topics",
    "mcp in:name,description,topics",
    "ai-tool in:name,description,topics",
    "llm in:name,description,topics",
]

# npm registries to search
NPM_QUERIES = [
    {"text": "mcp-server", "label": "mcp-server"},
    {"text": "ai-agent", "label": "ai-agent"},
]
NPM_LOOKBACK_DAYS = 7

# HTTP timeouts
HTTP_TIMEOUT = 20.0
RATE_DELAY = 1.0  # seconds between GitHub API calls


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _pg_connect():
    """Return a psycopg2 connection, or None if unavailable."""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as exc:
        logger.warning("Could not connect to PostgreSQL (%s) — DB check skipped.", exc)
        return None


def check_existing_in_db(source_urls: list[str]) -> set[str]:
    """
    Return the subset of *source_urls* that are already in our agents table.
    Falls back to an empty set if the DB is unavailable.
    """
    if not source_urls:
        return set()

    conn = _pg_connect()
    if conn is None:
        return set()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_url FROM entity_lookup WHERE source_url = ANY(%s)",
                (source_urls,),
            )
            rows = cur.fetchall()
        return {row[0] for row in rows}
    except Exception as exc:
        logger.warning("DB query failed: %s", exc)
        return set()
    finally:
        conn.close()


def check_existing_by_name(names: list[str]) -> set[str]:
    """
    Return the subset of tool *names* (lowercased) that already exist in our DB.
    Used as a secondary fuzzy check when the exact URL might differ.
    """
    if not names:
        return set()

    conn = _pg_connect()
    if conn is None:
        return set()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name_lower FROM entity_lookup WHERE name_lower = ANY(%s)",
                ([n.lower() for n in names],),
            )
            rows = cur.fetchall()
        return {row[0] for row in rows}
    except Exception as exc:
        logger.warning("DB name query failed: %s", exc)
        return set()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GitHub scanner
# ---------------------------------------------------------------------------

def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    else:
        logger.warning("No GITHUB_TOKEN found — GitHub rate limits will be very low.")
    return headers


def _github_date_cutoff() -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=GITHUB_LOOKBACK_DAYS)
    return cutoff.strftime("%Y-%m-%d")


def fetch_github_trending(query: str, cutoff_date: str, client: httpx.Client) -> list[dict]:
    """Fetch GitHub repos matching *query* created after *cutoff_date* with ≥ GITHUB_MIN_STARS stars."""
    results: list[dict] = []
    page = 1
    per_page = 30

    full_query = f"{query} stars:>={GITHUB_MIN_STARS} created:>{cutoff_date}"
    logger.info("GitHub search: %r", full_query)

    while True:
        params = {
            "q": full_query,
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
            "page": page,
        }
        try:
            resp = client.get(
                "https://api.github.com/search/repositories",
                headers=_github_headers(),
                params=params,
                timeout=HTTP_TIMEOUT,
            )
        except Exception as exc:
            logger.warning("GitHub API request failed: %s", exc)
            break

        if resp.status_code == 403:
            logger.warning("GitHub rate-limited (403). Stopping GitHub scan.")
            break
        if resp.status_code == 422:
            logger.warning("GitHub rejected query (422): %s", resp.text[:200])
            break
        if resp.status_code != 200:
            logger.warning("GitHub returned %s: %s", resp.status_code, resp.text[:200])
            break

        data = resp.json()
        items = data.get("items", [])
        if not items:
            break

        for item in items:
            created_at = item.get("created_at", "")
            if created_at < cutoff_date:
                continue  # skip older repos (shouldn't happen but be safe)

            results.append({
                "name": item.get("full_name", ""),
                "display_name": item.get("name", ""),
                "description": item.get("description") or "",
                "url": item.get("html_url", ""),
                "source": "github",
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "language": item.get("language"),
                "topics": item.get("topics", []),
                "created_at": created_at,
                "updated_at": item.get("updated_at", ""),
                "owner": item.get("owner", {}).get("login", ""),
                "search_query": query,
            })

        total = data.get("total_count", 0)
        logger.info("  page %d: %d items (total matching: %d)", page, len(items), total)

        # Only fetch first 3 pages per query to avoid hammering the API
        if page >= 3 or len(results) >= total:
            break

        page += 1
        time.sleep(RATE_DELAY)

    return results


def scan_github() -> list[dict]:
    """Run all GitHub queries and return deduplicated results."""
    cutoff_date = _github_date_cutoff()
    logger.info("Scanning GitHub — cutoff date: %s, min stars: %d", cutoff_date, GITHUB_MIN_STARS)

    seen_urls: set[str] = set()
    all_results: list[dict] = []

    with httpx.Client() as client:
        for query in GITHUB_QUERIES:
            try:
                results = fetch_github_trending(query, cutoff_date, client)
                for r in results:
                    if r["url"] not in seen_urls:
                        seen_urls.add(r["url"])
                        all_results.append(r)
                time.sleep(RATE_DELAY)
            except Exception as exc:
                logger.warning("Error in GitHub query %r: %s", query, exc)

    logger.info("GitHub: %d unique repos found", len(all_results))
    return all_results


# ---------------------------------------------------------------------------
# npm scanner
# ---------------------------------------------------------------------------

def _parse_npm_date(date_str: str) -> Optional[datetime]:
    """Parse npm date strings in ISO 8601 format."""
    if not date_str:
        return None
    try:
        # npm returns strings like "2024-03-15T12:00:00.000Z"
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_npm_packages(query_cfg: dict, client: httpx.Client) -> list[dict]:
    """Fetch npm packages matching *query_cfg* published in the last NPM_LOOKBACK_DAYS days."""
    text = query_cfg["text"]
    label = query_cfg["label"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=NPM_LOOKBACK_DAYS)

    results: list[dict] = []

    urls = [
        f"https://registry.npmjs.org/-/v1/search?text={text}&not=deprecated&popularity=1.0&size=20",
        f"https://registry.npmjs.org/-/v1/search?text={text}&not=deprecated&size=20",
    ]
    seen_names: set[str] = set()

    for url in urls:
        logger.info("npm search: %s", url)
        try:
            resp = client.get(url, timeout=HTTP_TIMEOUT)
        except Exception as exc:
            logger.warning("npm API request failed: %s", exc)
            continue

        if resp.status_code != 200:
            logger.warning("npm returned %s for %s", resp.status_code, url)
            continue

        data = resp.json()
        objects = data.get("objects", [])
        logger.info("  returned %d packages", len(objects))

        for obj in objects:
            pkg = obj.get("package", {})
            pkg_name = pkg.get("name", "")
            if not pkg_name or pkg_name in seen_names:
                continue
            seen_names.add(pkg_name)

            # Filter by publish date
            date_str = pkg.get("date", "")
            published = _parse_npm_date(date_str)
            if published and published < cutoff:
                continue  # older than our lookback window

            links = pkg.get("links", {})
            npm_url = links.get("npm") or f"https://www.npmjs.com/package/{pkg_name}"

            results.append({
                "name": pkg_name,
                "display_name": pkg_name,
                "description": pkg.get("description") or "",
                "url": npm_url,
                "source": "npm",
                "stars": 0,
                "downloads": obj.get("downloads", {}).get("monthly", 0) if isinstance(obj.get("downloads"), dict) else 0,
                "version": pkg.get("version", ""),
                "publisher": pkg.get("publisher", {}).get("username", "") if isinstance(pkg.get("publisher"), dict) else "",
                "keywords": pkg.get("keywords", []),
                "published_at": date_str,
                "npm_score": obj.get("score", {}).get("final", 0.0) if isinstance(obj.get("score"), dict) else 0.0,
                "search_label": label,
            })

    return results


def scan_npm() -> list[dict]:
    """Run all npm queries and return deduplicated results."""
    logger.info(
        "Scanning npm — lookback: %d days", NPM_LOOKBACK_DAYS
    )
    seen_names: set[str] = set()
    all_results: list[dict] = []

    with httpx.Client() as client:
        for query_cfg in NPM_QUERIES:
            try:
                results = fetch_npm_packages(query_cfg, client)
                for r in results:
                    if r["name"] not in seen_names:
                        seen_names.add(r["name"])
                        all_results.append(r)
                time.sleep(0.5)
            except Exception as exc:
                logger.warning("Error in npm query %r: %s", query_cfg, exc)

    logger.info("npm: %d unique packages found", len(all_results))
    return all_results


# ---------------------------------------------------------------------------
# DB presence check
# ---------------------------------------------------------------------------

def annotate_with_db_status(tools: list[dict]) -> list[dict]:
    """
    Add *is_new* field to each tool record.
    is_new=True  → not found in our DB (genuinely new to us)
    is_new=False → already indexed
    """
    if not tools:
        return tools

    # Primary check: by canonical URL
    source_urls = [t["url"] for t in tools if t.get("url")]
    existing_urls = check_existing_in_db(source_urls)

    # Secondary check: by name (catches duplicates with slightly different URLs)
    names = [t["name"] for t in tools if t.get("name")]
    existing_names = check_existing_by_name(names)

    for tool in tools:
        url_match = tool.get("url", "") in existing_urls
        name_match = tool.get("name", "").lower() in existing_names
        tool["is_new"] = not (url_match or name_match)
        tool["db_url_match"] = url_match
        tool["db_name_match"] = name_match

    return tools


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def run_scan() -> dict:
    """Run the full scan and return the results dict."""
    scan_started_at = datetime.now(timezone.utc).isoformat()
    logger.info("=== New Tool Detector — scan started at %s ===", scan_started_at)

    github_tools = scan_github()
    npm_tools = scan_npm()
    all_tools = github_tools + npm_tools

    logger.info("Checking %d tools against database...", len(all_tools))
    all_tools = annotate_with_db_status(all_tools)

    new_tools = [t for t in all_tools if t.get("is_new")]
    known_tools = [t for t in all_tools if not t.get("is_new")]

    results = {
        "scan_completed_at": datetime.now(timezone.utc).isoformat(),
        "scan_started_at": scan_started_at,
        "config": {
            "github_lookback_days": GITHUB_LOOKBACK_DAYS,
            "github_min_stars": GITHUB_MIN_STARS,
            "npm_lookback_days": NPM_LOOKBACK_DAYS,
            "github_queries": GITHUB_QUERIES,
            "npm_queries": [q["label"] for q in NPM_QUERIES],
        },
        "summary": {
            "total_found": len(all_tools),
            "new_to_us": len(new_tools),
            "already_indexed": len(known_tools),
            "github_found": len(github_tools),
            "npm_found": len(npm_tools),
            "github_new": sum(1 for t in github_tools if t.get("is_new")),
            "npm_new": sum(1 for t in npm_tools if t.get("is_new")),
        },
        "new_tools": new_tools,
        "known_tools": known_tools,
    }

    # Ensure output directory exists
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str))
    logger.info("Results saved to %s", RESULTS_PATH)

    return results


# ---------------------------------------------------------------------------
# Report display
# ---------------------------------------------------------------------------

def print_report(results: dict) -> None:
    summary = results.get("summary", {})
    config = results.get("config", {})
    new_tools = results.get("new_tools", [])
    scan_ts = results.get("scan_completed_at", "unknown")

    print(f"\n{'='*70}")
    print(f"  NEW TOOL DETECTOR — Report")
    print(f"  Scan completed: {scan_ts}")
    print(f"  GitHub lookback: {config.get('github_lookback_days', '?')} days  |  min stars: {config.get('github_min_stars', '?')}")
    print(f"  npm lookback:   {config.get('npm_lookback_days', '?')} days")
    print(f"{'='*70}")
    print(f"  Total found:       {summary.get('total_found', 0):>5}")
    print(f"  NEW to us:         {summary.get('new_to_us', 0):>5}  ← not in our DB")
    print(f"  Already indexed:   {summary.get('already_indexed', 0):>5}")
    print(f"  GitHub new/found:  {summary.get('github_new', 0)}/{summary.get('github_found', 0)}")
    print(f"  npm new/found:     {summary.get('npm_new', 0)}/{summary.get('npm_found', 0)}")
    print(f"{'='*70}")

    if not new_tools:
        print("  No new tools detected.\n")
        return

    # Group by source for display
    github_new = [t for t in new_tools if t["source"] == "github"]
    npm_new = [t for t in new_tools if t["source"] == "npm"]

    if github_new:
        print(f"\n  GITHUB — {len(github_new)} new repos (sorted by stars):\n")
        github_new_sorted = sorted(github_new, key=lambda x: x.get("stars", 0), reverse=True)
        for i, t in enumerate(github_new_sorted, 1):
            stars = t.get("stars", 0)
            name = t.get("name", "")
            desc = t.get("description", "")[:80]
            url = t.get("url", "")
            created = t.get("created_at", "")[:10]
            lang = t.get("language") or ""
            topics = ", ".join(t.get("topics", [])[:4])
            print(f"  {i:>3}. ⭐ {stars:<6} {name}")
            if desc:
                print(f"       {desc}")
            print(f"       {url}")
            print(f"       created: {created}  lang: {lang}  topics: {topics}")
            print()

    if npm_new:
        print(f"\n  NPM — {len(npm_new)} new packages:\n")
        for i, t in enumerate(npm_new, 1):
            name = t.get("name", "")
            desc = t.get("description", "")[:80]
            url = t.get("url", "")
            published = t.get("published_at", "")[:10]
            version = t.get("version", "")
            publisher = t.get("publisher", "")
            keywords = ", ".join(t.get("keywords", [])[:4])
            score = t.get("npm_score", 0.0)
            print(f"  {i:>3}. {name} v{version}")
            if desc:
                print(f"       {desc}")
            print(f"       {url}")
            print(f"       published: {published}  publisher: {publisher}  score: {score:.2f}")
            if keywords:
                print(f"       keywords: {keywords}")
            print()

    print(f"  Full results: {RESULTS_PATH}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Detect new AI tools/repos from GitHub and npm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--scan", action="store_true", help="Run a fresh scan and save results")
    parser.add_argument("--report", action="store_true", help="Show summary of last saved scan")
    args = parser.parse_args()

    if not args.scan and not args.report:
        parser.print_help()
        sys.exit(1)

    if args.scan:
        results = run_scan()
        print_report(results)

    elif args.report:
        if not RESULTS_PATH.exists():
            print(f"No results file found at {RESULTS_PATH}. Run --scan first.")
            sys.exit(1)
        results = json.loads(RESULTS_PATH.read_text())
        print_report(results)


if __name__ == "__main__":
    main()
