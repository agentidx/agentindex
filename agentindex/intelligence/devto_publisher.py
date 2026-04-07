"""
Dev.to Publisher
================
Publishes auto-generated comparison posts to Dev.to.

Requires DEVTO_API_KEY environment variable.

Usage:
    python -m agentindex.intelligence.devto_publisher
"""

import json
import logging
import os
import sqlite3
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [devto] %(message)s")
logger = logging.getLogger("devto")

SQLITE_DB = "/Users/anstudio/agentindex/data/crypto_trust.db"
DEVTO_API_KEY = os.environ.get("DEVTO_API_KEY", "")
PUBLISHED_FILE = "/Users/anstudio/agentindex/data/devto_published.json"


def _load_published():
    try:
        with open(PUBLISHED_FILE) as f:
            return json.load(f)
    except:
        return []


def _save_published(slugs):
    with open(PUBLISHED_FILE, "w") as f:
        json.dump(slugs, f)


def publish_to_devto(title: str, content: str, tags: list) -> str:
    """Publish an article to Dev.to. Returns URL or empty string."""
    if not DEVTO_API_KEY:
        logger.warning("DEVTO_API_KEY not set, skipping")
        return ""

    body = json.dumps({
        "article": {
            "title": title,
            "body_markdown": content,
            "published": True,
            "tags": tags[:4],  # Dev.to max 4 tags
            "canonical_url": f"https://nerq.ai/blog/{title.lower().replace(' ', '-')[:50]}",
        }
    }).encode()

    req = urllib.request.Request(
        "https://dev.to/api/articles",
        data=body,
        headers={
            "Content-Type": "application/json",
            "api-key": DEVTO_API_KEY,
            "User-Agent": "nerq-publisher/1.0",
        },
        method="POST"
    )

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        url = data.get("url", "")
        logger.info(f"Published to Dev.to: {url}")
        return url
    except Exception as e:
        logger.error(f"Failed to publish to Dev.to: {e}")
        return ""


def run():
    """Publish unpublished comparisons to Dev.to."""
    published = _load_published()

    try:
        conn = sqlite3.connect(SQLITE_DB, timeout=10)
        rows = conn.execute(
            "SELECT slug, title, content, category FROM auto_comparisons ORDER BY generated_at DESC LIMIT 20"
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"Could not read comparisons: {e}")
        return 0

    count = 0
    for slug, title, content, category in rows:
        if slug in published:
            continue

        tags = ["ai", "agents", "comparison", "security"]
        # Add cross-link to nerq.ai at the end
        content += f"\n\n---\n\n*Originally published at [Nerq](https://nerq.ai/blog/{slug}). Trust scores from [nerq.ai](https://nerq.ai) — the AI agent trust database.*"

        url = publish_to_devto(title, content, tags)
        if url:
            published.append(slug)
            count += 1
        if count >= 5:  # Max 5 per run
            break

    _save_published(published)
    return count


def main():
    logger.info("Dev.to Publisher — starting")
    count = run()
    logger.info(f"Published {count} articles to Dev.to")


if __name__ == "__main__":
    main()
