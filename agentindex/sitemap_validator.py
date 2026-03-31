"""
Sitemap Validator — Daily 08:00
================================
Validates all sitemaps for nerq.ai and zarq.ai:
- Correct host in URLs (no cross-domain contamination)
- Sample 50 random URLs per sitemap, check HTTP 200
- Count total URLs per sitemap
- Alert on >5% 404s or any host mismatch

Usage:
    python -m agentindex.sitemap_validator
"""

import logging
import random
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx

LOG_DIR = Path(__file__).parent.parent / "logs"
ALERT_LOG = LOG_DIR / "sitemap_alerts.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [sitemap-validator] %(message)s",
)
logger = logging.getLogger("sitemap-validator")

# Sitemaps to validate: (sitemap_url, expected_host)
SITEMAPS = [
    ("https://nerq.ai/sitemap.xml", "nerq.ai"),
    ("https://nerq.ai/sitemap-safe.xml", "nerq.ai"),
    ("https://nerq.ai/sitemap-mcp.xml", "nerq.ai"),
    ("https://zarq.ai/sitemap.xml", "zarq.ai"),
    ("https://zarq.ai/sitemap-crypto.xml", "zarq.ai"),
    ("https://zarq.ai/sitemap-tokens.xml", "zarq.ai"),
    ("https://zarq.ai/sitemap-zarq-content.xml", "zarq.ai"),
]

SAMPLE_SIZE = 50


def _extract_urls(xml_text):
    """Extract all <loc> URLs from sitemap XML."""
    urls = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for loc in root.findall(".//s:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())
        # Also check for sitemap index entries
        for loc in root.findall(".//s:sitemap/s:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())
    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
    return urls


def _write_alert(message):
    """Append alert to sitemap_alerts.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALERT_LOG, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] ALERT: {message}\n")
    logger.warning(f"ALERT: {message}")


def validate_sitemap(client, sitemap_url, expected_host):
    """Validate a single sitemap."""
    result = {
        "sitemap": sitemap_url,
        "expected_host": expected_host,
        "total_urls": 0,
        "host_mismatches": 0,
        "sampled": 0,
        "ok_200": 0,
        "not_found_404": 0,
        "other_errors": 0,
        "fetch_error": None,
    }

    # Fetch the sitemap
    try:
        resp = client.get(sitemap_url, timeout=30, follow_redirects=True)
        if resp.status_code != 200:
            result["fetch_error"] = f"HTTP {resp.status_code}"
            _write_alert(f"{sitemap_url} returned HTTP {resp.status_code}")
            return result
    except Exception as e:
        result["fetch_error"] = str(e)
        _write_alert(f"{sitemap_url} fetch failed: {e}")
        return result

    urls = _extract_urls(resp.text)
    result["total_urls"] = len(urls)

    if not urls:
        logger.info(f"  {sitemap_url}: 0 URLs (may be sitemap index)")
        return result

    # Check host correctness for ALL URLs
    for url in urls:
        if expected_host not in url:
            result["host_mismatches"] += 1

    if result["host_mismatches"] > 0:
        _write_alert(
            f"{sitemap_url}: {result['host_mismatches']} host mismatches "
            f"(expected {expected_host})"
        )

    # Sample up to SAMPLE_SIZE URLs and check HTTP status
    sample = random.sample(urls, min(SAMPLE_SIZE, len(urls)))
    result["sampled"] = len(sample)

    for url in sample:
        try:
            r = client.get(url, timeout=15, follow_redirects=True)
            if r.status_code == 200:
                result["ok_200"] += 1
            elif r.status_code == 404:
                result["not_found_404"] += 1
            else:
                result["other_errors"] += 1
        except Exception:
            result["other_errors"] += 1
        time.sleep(0.2)  # Be polite

    # Alert if >5% 404s
    if result["sampled"] > 0:
        pct_404 = result["not_found_404"] / result["sampled"]
        if pct_404 > 0.05:
            _write_alert(
                f"{sitemap_url}: {pct_404:.0%} 404s "
                f"({result['not_found_404']}/{result['sampled']} sampled)"
            )

    return result


def main():
    logger.info("=" * 60)
    logger.info("Sitemap Validator — starting")
    logger.info("=" * 60)

    total_urls = 0
    total_mismatches = 0
    total_404s = 0
    results = []

    with httpx.Client(
        headers={"User-Agent": "NerqSitemapValidator/1.0"},
        verify=True,
    ) as client:
        for sitemap_url, expected_host in SITEMAPS:
            logger.info(f"Validating {sitemap_url} ...")
            result = validate_sitemap(client, sitemap_url, expected_host)
            results.append(result)

            if result["fetch_error"]:
                logger.error(f"  FETCH ERROR: {result['fetch_error']}")
            else:
                logger.info(
                    f"  URLs: {result['total_urls']}, "
                    f"Host mismatches: {result['host_mismatches']}, "
                    f"Sampled: {result['sampled']} "
                    f"(200: {result['ok_200']}, 404: {result['not_found_404']}, "
                    f"err: {result['other_errors']})"
                )

            total_urls += result["total_urls"]
            total_mismatches += result["host_mismatches"]
            total_404s += result["not_found_404"]

    logger.info("")
    logger.info("=" * 60)
    logger.info("Sitemap Validator — COMPLETE")
    logger.info(f"  Sitemaps checked: {len(SITEMAPS)}")
    logger.info(f"  Total URLs across all sitemaps: {total_urls:,}")
    logger.info(f"  Host mismatches: {total_mismatches}")
    logger.info(f"  404s found (in samples): {total_404s}")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
