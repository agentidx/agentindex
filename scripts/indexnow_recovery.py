#!/usr/bin/env python3
"""
IndexNow Recovery Submission — "We're Back"
=============================================
Submits high-priority URLs after an outage to signal search engines
and AI systems to re-crawl. Three tiers:

  1. Top 1000 most-visited pages (from analytics.db)
  2. All /best/ pages — EN + 21 localized languages
  3. llms.txt, sitemaps, and infrastructure URLs

Usage:
  cd ~/agentindex && venv/bin/python scripts/indexnow_recovery.py
"""

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH_SIZE = 100
BATCH_DELAY = 0.3  # seconds between batches
XML_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

HOSTS = {
    "nerq.ai": {
        "key": "nerq2026indexnow",
        "keyLocation": "https://nerq.ai/nerq2026indexnow.txt",
    },
    "zarq.ai": {
        "key": "zarq2026indexnow",
        "keyLocation": "https://zarq.ai/zarq2026indexnow.txt",
    },
}


def fetch_sitemap_urls(sitemap_url):
    """Fetch URLs from a sitemap XML served on localhost."""
    try:
        req = urllib.request.Request(sitemap_url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        urls = [l.text.strip() for l in root.findall(".//sm:loc", XML_NS) if l.text]
        if not urls:
            urls = [l.text.strip() for l in root.iter("loc") if l.text]
        return urls
    except Exception as e:
        print(f"  WARN: {sitemap_url}: {e}")
        return []


def submit_batch(host, urls):
    """Submit a list of URLs to IndexNow for the given host. Returns (submitted, failed)."""
    cfg = HOSTS[host]
    submitted = 0
    failed = 0

    for i in range(0, len(urls), BATCH_SIZE):
        batch = urls[i:i + BATCH_SIZE]
        payload = {
            "host": host,
            "key": cfg["key"],
            "keyLocation": cfg["keyLocation"],
            "urlList": batch,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            INDEXNOW_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception as e:
            print(f"  ERROR batch {i // BATCH_SIZE + 1}: {e}")
            failed += len(batch)
            continue

        ok = status in (200, 202)
        tag = "OK" if ok else f"HTTP {status}"
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(urls) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  [{tag}] batch {batch_num}/{total_batches} ({len(batch)} URLs)")

        if ok:
            submitted += len(batch)
        else:
            failed += len(batch)

        if i + BATCH_SIZE < len(urls):
            time.sleep(BATCH_DELAY)

    return submitted, failed


def get_top_visited_pages(limit=1000):
    """Query analytics.db for top human-visited pages."""
    db_path = os.path.expanduser("~/agentindex/logs/analytics.db")
    if not os.path.exists(db_path):
        print("  WARN: analytics.db not found")
        return []

    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT path, COUNT(*) as hits
        FROM requests
        WHERE is_bot = 0
          AND status = 200
          AND path NOT LIKE '/v1/%'
          AND path NOT LIKE '/static/%'
          AND path NOT LIKE '/ab-%'
          AND path NOT LIKE '/admin/%'
          AND path NOT LIKE '/dashboard%'
          AND path NOT LIKE '/flywheel%'
          AND path NOT LIKE '/internal/%'
          AND path NOT LIKE '/my/%'
          AND path != '/favicon.ico'
          AND path != '/robots.txt'
        GROUP BY path
        ORDER BY hits DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [path for path, _ in rows]


def get_best_pages_en():
    """Fetch all /best/ page URLs from the sitemap."""
    return fetch_sitemap_urls("http://localhost:8000/sitemap-best.xml")


def get_best_pages_localized():
    """Fetch all localized /best/ pages from sitemap index."""
    index_urls = fetch_sitemap_urls("http://localhost:8000/sitemap-best-localized.xml")
    all_urls = []
    for idx_url in index_urls:
        # Convert https://nerq.ai/sitemap-... to localhost
        local = idx_url.replace("https://nerq.ai/", "http://localhost:8000/")
        urls = fetch_sitemap_urls(local)
        all_urls.extend(urls)
        print(f"    {os.path.basename(local)}: {len(urls)} URLs")
    return all_urls


def get_infrastructure_urls():
    """Key infrastructure URLs that AI systems and crawlers need."""
    return [
        # llms.txt — AI system discovery
        "https://nerq.ai/llms.txt",
        "https://zarq.ai/llms.txt",
        # Sitemap indexes
        "https://nerq.ai/sitemap-index.xml",
        "https://nerq.ai/sitemap-localized.xml",
        "https://zarq.ai/sitemap.xml",
        # Agent discovery
        "https://nerq.ai/.well-known/agent.json",
        "https://zarq.ai/.well-known/agent.json",
        # Key landing pages
        "https://nerq.ai/",
        "https://nerq.ai/discover",
        "https://nerq.ai/nerq/docs",
        "https://nerq.ai/guides",
        "https://nerq.ai/compare",
        "https://zarq.ai/",
        "https://zarq.ai/vitality",
        "https://zarq.ai/tokens",
        "https://zarq.ai/crash-watch",
    ]


def path_to_url(path, host="nerq.ai"):
    """Convert a path like /safe/express to https://nerq.ai/safe/express."""
    if path.startswith("http"):
        return path
    return f"https://{host}{path}"


def main():
    print("=" * 60)
    print("  IndexNow Recovery — Post-Outage Re-Index Signal")
    print("=" * 60)
    print()

    # ── 1. Top visited pages ──
    print("[1/3] Top 1000 most-visited pages (from analytics)...")
    top_paths = get_top_visited_pages(1000)
    print(f"  Found {len(top_paths)} unique paths")

    # Split by host
    nerq_top = []
    zarq_top = []
    for p in top_paths:
        if p.startswith("/zarq/") or p.startswith("/crypto"):
            zarq_top.append(path_to_url(p, "zarq.ai"))
        else:
            nerq_top.append(path_to_url(p, "nerq.ai"))
    print(f"  nerq.ai: {len(nerq_top)}, zarq.ai: {len(zarq_top)}")

    # ── 2. /best/ pages ──
    print()
    print("[2/3] All /best/ pages (EN + localized)...")
    best_en = get_best_pages_en()
    print(f"  EN /best/: {len(best_en)} URLs")

    best_localized = get_best_pages_localized()
    print(f"  Localized /best/: {len(best_localized)} URLs")

    all_best = best_en + best_localized

    # ── 3. Infrastructure URLs ──
    print()
    print("[3/3] Infrastructure URLs (llms.txt, sitemaps, landing)...")
    infra = get_infrastructure_urls()
    print(f"  {len(infra)} URLs")

    # ── Deduplicate and split by host ──
    nerq_urls = []
    zarq_urls = []
    seen = set()

    for url in infra + nerq_top + all_best + zarq_top:
        if url in seen:
            continue
        seen.add(url)
        if "zarq.ai" in url:
            zarq_urls.append(url)
        elif "nerq.ai" in url:
            nerq_urls.append(url)

    print()
    print(f"Total unique URLs: {len(nerq_urls) + len(zarq_urls)}")
    print(f"  nerq.ai: {len(nerq_urls)}")
    print(f"  zarq.ai: {len(zarq_urls)}")

    # ── Submit ──
    print()
    print("=" * 60)
    print("  Submitting to IndexNow API")
    print("=" * 60)

    total_submitted = 0
    total_failed = 0

    if nerq_urls:
        print(f"\n--- nerq.ai ({len(nerq_urls)} URLs) ---")
        s, f = submit_batch("nerq.ai", nerq_urls)
        total_submitted += s
        total_failed += f

    if zarq_urls:
        print(f"\n--- zarq.ai ({len(zarq_urls)} URLs) ---")
        s, f = submit_batch("zarq.ai", zarq_urls)
        total_submitted += s
        total_failed += f

    # ── Summary ──
    print()
    print("=" * 60)
    print(f"  DONE: {total_submitted} submitted, {total_failed} failed")
    print("=" * 60)
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
