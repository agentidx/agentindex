#!/usr/bin/env python3
"""
Chrome Web Store Sitemap Crawler — extracts extension IDs and names from CWS sitemaps.
Inserts into software_registry with registry='chrome'.

Run: python3 -m agentindex.crawlers.chrome_sitemap_crawler [max_shards]
"""

import logging
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from sqlalchemy import text
from agentindex.db.models import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-6s %(message)s")
log = logging.getLogger("chrome_sitemap")

SITEMAP_INDEX = "https://chromewebstore.google.com/sitemap"
BATCH_SIZE = 100


def parse_sitemap_shard(shard_url):
    """Parse a single sitemap shard and extract extension slugs + names."""
    try:
        resp = requests.get(shard_url, timeout=30)
        if resp.status_code != 200:
            return []
        # Extract: /detail/{name}/{id}
        pattern = r'<loc>https://chromewebstore\.google\.com/detail/([^/]+)/([a-z]{32})</loc>'
        matches = re.findall(pattern, resp.text)
        results = []
        for name_encoded, ext_id in matches:
            name = unquote(name_encoded).replace('-', ' ').strip()
            slug = name_encoded.lower()[:100]
            # Clean slug
            slug = re.sub(r'[^a-z0-9-]', '-', slug).strip('-')[:80]
            if slug and len(slug) > 2:
                results.append({"name": name, "slug": slug, "ext_id": ext_id})
        return results
    except Exception as e:
        log.warning(f"Error parsing {shard_url}: {e}")
        return []


def main():
    max_shards = int(sys.argv[1]) if len(sys.argv) > 1 else 5  # Default: first 5 shards (~5K extensions)

    session = get_session()
    session.execute(text("SET statement_timeout = '10s'"))

    # Get sitemap index
    log.info(f"Fetching sitemap index (max {max_shards} shards)")
    resp = requests.get(SITEMAP_INDEX, timeout=30)
    shard_urls = re.findall(r'<loc>(https://chromewebstore\.google\.com/sitemap\?shard=\d+)</loc>', resp.text)
    shard_urls = shard_urls[:max_shards]
    log.info(f"Found {len(shard_urls)} shards to process")

    total = 0
    for i, url in enumerate(shard_urls):
        extensions = parse_sitemap_shard(url)
        log.info(f"Shard {i}: {len(extensions)} extensions")

        batch_count = 0
        for ext in extensions:
            try:
                session.execute(text("""
                    INSERT INTO software_registry (id, name, slug, registry, description, created_at)
                    VALUES (:id, :name, :slug, 'chrome', :desc, NOW())
                    ON CONFLICT (registry, slug) DO NOTHING
                """), {
                    "id": str(uuid.uuid4()),
                    "name": ext["name"][:255],
                    "slug": ext["slug"],
                    "desc": f"Chrome extension: {ext['name']}",
                })
                total += 1
                batch_count += 1
            except Exception:
                session.rollback()

            if batch_count >= BATCH_SIZE:
                session.commit()
                batch_count = 0

        session.commit()
        import time
        time.sleep(1)

    session.close()
    log.info(f"Chrome sitemap crawl complete: {total} extensions processed")


if __name__ == "__main__":
    main()
