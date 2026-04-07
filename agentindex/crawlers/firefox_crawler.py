#!/usr/bin/env python3
"""
Firefox Extension Crawler — AMO API v5.

Crawls ALL Firefox extensions from addons.mozilla.org API v5,
sorted by users DESC. Upserts into software_registry with registry='firefox'.

Usage:
    python3 -m agentindex.crawlers.firefox_crawler
    python3 -m agentindex.crawlers.firefox_crawler 5000   # limit to 5000
"""
import sys
import time
import uuid
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from sqlalchemy import text
from agentindex.db.models import get_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-6s %(message)s",
)
logger = logging.getLogger("firefox_crawler")

API_URL = "https://addons.mozilla.org/api/v5/addons/search/"
PAGE_SIZE = 50
RATE_LIMIT_SECONDS = 1.0
BATCH_SIZE = 50
LOG_EVERY = 500
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds, multiplied by attempt number

UPSERT_SQL = text("""
    INSERT INTO software_registry
        (id, name, slug, registry, description, author, downloads,
         weekly_downloads, latest_version, homepage_url, enriched_at, created_at)
    VALUES
        (:id, :name, :slug, 'firefox', :desc, :auth, :dl,
         :wdl, :ver, :url, NOW(), NOW())
    ON CONFLICT (registry, slug) DO UPDATE SET
        name = EXCLUDED.name,
        description = COALESCE(NULLIF(EXCLUDED.description, ''), software_registry.description),
        author = COALESCE(NULLIF(EXCLUDED.author, ''), software_registry.author),
        downloads = GREATEST(COALESCE(software_registry.downloads, 0), EXCLUDED.downloads),
        weekly_downloads = EXCLUDED.weekly_downloads,
        latest_version = EXCLUDED.latest_version,
        enriched_at = NOW()
""")


def _extract_localized(field):
    """Extract a string from an AMO localized field (dict or str)."""
    if field is None:
        return ""
    if isinstance(field, str):
        return field
    if isinstance(field, dict):
        return field.get("en-US") or next(iter(field.values()), "")
    return str(field)


def _fetch_page(page: int) -> dict | None:
    """Fetch a single page from AMO API with retries."""
    params = {
        "type": "extension",
        "page_size": PAGE_SIZE,
        "sort": "users",
        "app": "firefox",
        "page": page,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * attempt
                logger.warning(f"Rate limited on page {page}, waiting {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                logger.warning(f"Page {page}: HTTP {resp.status_code}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)
                    continue
                return None
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Page {page} attempt {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
            else:
                return None
    return None


def _parse_extension(ext: dict) -> dict:
    """Parse a single AMO extension result into an upsert-ready dict."""
    name = _extract_localized(ext.get("name"))
    slug = ext.get("slug", "")
    summary = _extract_localized(ext.get("summary"))
    description = summary or _extract_localized(ext.get("description"))

    # Author
    authors = ext.get("authors") or []
    if authors and isinstance(authors[0], dict):
        author = authors[0].get("name", "")
    elif authors and isinstance(authors[0], str):
        author = authors[0]
    else:
        author = ""

    # Metrics
    daily_users = ext.get("average_daily_users") or 0
    weekly_downloads = ext.get("weekly_downloads") or 0

    # Version
    current_version = ext.get("current_version") or {}
    version = current_version.get("version", "")

    # Ratings
    ratings = ext.get("ratings") or {}

    # Permissions (from current version file)
    permissions = []
    _f = current_version.get("file")
    files = [_f] if isinstance(_f, dict) else (current_version.get("files") or [])
    for f in files:
        if f and isinstance(f, dict):
            permissions.extend(f.get("permissions") or [])

    # Category — AMO returns categories as list or dict
    categories = ext.get("categories") or []
    if isinstance(categories, dict):
        cat_list = categories.get("firefox") or []
    elif isinstance(categories, list):
        cat_list = categories
    else:
        cat_list = []
    category = cat_list[0] if cat_list else "extension"

    return {
        "id": str(uuid.uuid4()),
        "name": str(name)[:255],
        "slug": slug,
        "desc": str(description)[:500],
        "auth": str(author)[:200],
        "dl": daily_users,
        "wdl": weekly_downloads,
        "ver": str(version)[:50],
        "url": f"https://addons.mozilla.org/en-US/firefox/addon/{slug}/",
    }


def crawl(limit: int = 100_000):
    """Crawl Firefox extensions from AMO API v5."""
    logger.info(f"Starting Firefox AMO crawl (limit={limit})")
    session = get_session()
    session.execute(text("SET statement_timeout = '10s'"))

    total = 0
    upserted = 0
    page = 1
    batch_count = 0

    while total < limit:
        data = _fetch_page(page)
        if data is None:
            logger.error(f"Failed to fetch page {page}, stopping.")
            break

        results = data.get("results") or []
        if not results:
            logger.info(f"No results on page {page}, crawl complete.")
            break

        page_count = data.get("count", 0)
        if page == 1:
            logger.info(f"AMO reports {page_count} total extensions")

        for ext in results:
            if total >= limit:
                break

            try:
                entry = _parse_extension(ext)
                session.execute(UPSERT_SQL, entry)
                upserted += 1
                batch_count += 1
            except Exception as e:
                logger.warning(f"Error on {ext.get('slug', '?')}: {e}")
                session.rollback()

            total += 1

            # Batch commit
            if batch_count >= BATCH_SIZE:
                session.commit()
                batch_count = 0

            # Progress log
            if total % LOG_EVERY == 0:
                logger.info(f"Progress: {total} processed, {upserted} upserted")

        # Check if there's a next page
        next_url = data.get("next")
        if not next_url:
            logger.info("No next page, crawl complete.")
            break

        page += 1
        time.sleep(RATE_LIMIT_SECONDS)

    # Final commit
    if batch_count > 0:
        session.commit()

    session.close()
    logger.info(f"Firefox crawl complete: {total} processed, {upserted} upserted")
    return upserted


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    crawl(limit)
