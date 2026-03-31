"""
Google & Bing Sitemap Ping — Daily 08:15
==========================================
Pings search engines with all sitemaps so they know to re-crawl.
Runs after sitemap_validator (08:00) to ensure sitemaps are valid first.

Usage:
    python -m agentindex.google_ping
"""

import logging
import time
from datetime import datetime
from urllib.parse import quote

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [google-ping] %(message)s",
)
logger = logging.getLogger("google-ping")

SITEMAPS = [
    "https://nerq.ai/sitemap.xml",
    "https://nerq.ai/sitemap-safe.xml",
    "https://nerq.ai/sitemap-mcp.xml",
    "https://nerq.ai/sitemap-static.xml",
    "https://zarq.ai/sitemap.xml",
    "https://zarq.ai/sitemap-crypto.xml",
    "https://zarq.ai/sitemap-tokens.xml",
    "https://zarq.ai/sitemap-zarq-content.xml",
]

PING_ENDPOINTS = [
    ("Google", "https://www.google.com/ping?sitemap={sitemap}"),
    ("Bing", "https://www.bing.com/ping?sitemap={sitemap}"),
]


def main():
    logger.info("=" * 60)
    logger.info("Sitemap Ping — starting")
    logger.info("=" * 60)

    success = 0
    failed = 0

    with httpx.Client(
        headers={"User-Agent": "NerqSitemapPing/1.0"},
        timeout=30,
        follow_redirects=True,
    ) as client:
        for sitemap in SITEMAPS:
            for engine_name, url_template in PING_ENDPOINTS:
                url = url_template.format(sitemap=quote(sitemap, safe=""))
                try:
                    resp = client.get(url)
                    status = resp.status_code
                    if status in (200, 202):
                        logger.info(f"  {engine_name} <- {sitemap}: OK ({status})")
                        success += 1
                    else:
                        logger.warning(f"  {engine_name} <- {sitemap}: HTTP {status}")
                        failed += 1
                except Exception as e:
                    logger.error(f"  {engine_name} <- {sitemap}: ERROR {e}")
                    failed += 1
                time.sleep(1)  # Don't hammer

    # Also submit to IndexNow (Bing + Yandex + others)
    logger.info("Submitting to IndexNow...")
    try:
        # Collect all sitemap URLs as pages to index
        indexnow_urls = list(SITEMAPS)
        # Add key pages
        indexnow_urls.extend([
            "https://nerq.ai/",
            "https://nerq.ai/safe",
            "https://nerq.ai/trust-score",
            "https://nerq.ai/start",
            "https://nerq.ai/about",
            "https://zarq.ai/",
            "https://zarq.ai/tokens",
            "https://zarq.ai/crash-watch",
        ])

        resp = client.post(
            "https://api.indexnow.org/indexnow",
            json={
                "host": "nerq.ai",
                "key": "nerq2026indexnow",
                "keyLocation": "https://nerq.ai/nerq2026indexnow.txt",
                "urlList": [u for u in indexnow_urls if "nerq.ai" in u],
            },
            headers={"Content-Type": "application/json"},
        )
        logger.info(f"  IndexNow (nerq): {resp.status_code}")

        resp = client.post(
            "https://api.indexnow.org/indexnow",
            json={
                "host": "zarq.ai",
                "key": "zarq2026indexnow",
                "keyLocation": "https://zarq.ai/zarq2026indexnow.txt",
                "urlList": [u for u in indexnow_urls if "zarq.ai" in u],
            },
            headers={"Content-Type": "application/json"},
        )
        logger.info(f"  IndexNow (zarq): {resp.status_code}")
    except Exception as e:
        logger.error(f"  IndexNow error: {e}")

    logger.info("")
    logger.info("=" * 60)
    logger.info("Sitemap Ping — COMPLETE")
    logger.info(f"  Pings sent: {success + failed} (success: {success}, failed: {failed})")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
