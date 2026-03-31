#!/usr/bin/env python3
"""Submit URLs to IndexNow API by collecting them from local sitemaps."""

import json
import sys
import urllib.request
import xml.etree.ElementTree as ET

INDEXNOW_KEY = "zarq2026indexnow"
INDEXNOW_KEY_LOCATION = "https://zarq.ai/zarq2026indexnow.txt"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH_SIZE = 100

# Sitemaps to fetch from localhost for zarq.ai
ZARQ_SITEMAPS = [
    "http://localhost:8000/sitemap.xml",
    "http://localhost:8000/sitemap-pages.xml",
    "http://localhost:8000/sitemap-tokens.xml",
    "http://localhost:8000/sitemap-crypto.xml",
    "http://localhost:8000/sitemap-compare.xml",
    "http://localhost:8000/sitemap-zarq-content.xml",
    "http://localhost:8000/sitemap-zarq-compare.xml",
]

NERQ_SITEMAPS = [
    "http://localhost:8000/sitemap-index.xml",
    "http://localhost:8000/sitemap-static.xml",
    "http://localhost:8000/sitemap-safe.xml",
    "http://localhost:8000/sitemap-mcp.xml",
    "http://localhost:8000/sitemap-compare.xml",
]

XML_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_urls_from_sitemap(sitemap_url: str) -> list[str]:
    """Fetch and parse a sitemap XML, returning all <loc> URLs."""
    try:
        req = urllib.request.Request(sitemap_url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        # Handle both <url><loc> and <sitemap><loc> (sitemap index)
        urls = []
        for loc in root.findall(".//sm:loc", XML_NS):
            if loc.text:
                urls.append(loc.text.strip())
        # Try without namespace (some sitemaps omit it)
        if not urls:
            for loc in root.iter("loc"):
                if loc.text:
                    urls.append(loc.text.strip())
        return urls
    except Exception as e:
        print(f"  WARN: Could not fetch {sitemap_url}: {e}")
        return []


def submit_to_indexnow(host: str, urls: list[str], key_location: str | None = None) -> None:
    """Submit URLs in batches to the IndexNow API."""
    if not urls:
        print(f"  No URLs to submit for {host}.")
        return

    total = len(urls)
    submitted = 0
    effective_key_location = key_location or INDEXNOW_KEY_LOCATION

    for i in range(0, total, BATCH_SIZE):
        batch = urls[i : i + BATCH_SIZE]
        payload = {
            "host": host,
            "key": INDEXNOW_KEY,
            "keyLocation": effective_key_location,
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
            print(f"  ERROR submitting batch {i // BATCH_SIZE + 1}: {e}")
            continue

        batch_num = i // BATCH_SIZE + 1
        marker = "OK" if status in (200, 202) else "WARN"
        print(f"  [{marker}] Batch {batch_num}: {len(batch)} URLs -> HTTP {status}")
        submitted += len(batch)

    print(f"  Total submitted for {host}: {submitted}/{total}")


def main():
    print("=== IndexNow URL Submission ===\n")

    # Collect zarq.ai URLs
    print("Fetching zarq.ai sitemaps from localhost...")
    zarq_urls = []
    for sm in ZARQ_SITEMAPS:
        urls = fetch_urls_from_sitemap(sm)
        print(f"  {sm} -> {len(urls)} URLs")
        zarq_urls.extend(urls)

    # Filter to only zarq.ai URLs
    zarq_urls = [u for u in zarq_urls if "zarq.ai" in u]
    # Deduplicate preserving order
    seen = set()
    unique_zarq = []
    for u in zarq_urls:
        if u not in seen:
            seen.add(u)
            unique_zarq.append(u)
    zarq_urls = unique_zarq

    print(f"\nTotal unique zarq.ai URLs: {len(zarq_urls)}")

    # Collect nerq.ai URLs
    print("\nFetching nerq.ai sitemaps from localhost...")
    nerq_urls = []
    for sm in NERQ_SITEMAPS:
        urls = fetch_urls_from_sitemap(sm)
        print(f"  {sm} -> {len(urls)} URLs")
        nerq_urls.extend(urls)

    # Filter to only nerq.ai URLs
    nerq_urls = [u for u in nerq_urls if "nerq.ai" in u]
    seen2 = set()
    unique_nerq = []
    for u in nerq_urls:
        if u not in seen2:
            seen2.add(u)
            unique_nerq.append(u)
    nerq_urls = unique_nerq

    print(f"Total unique nerq.ai URLs: {len(nerq_urls)}")

    # Submit zarq.ai
    print(f"\n--- Submitting zarq.ai URLs to IndexNow ---")
    submit_to_indexnow("zarq.ai", zarq_urls)

    # Submit nerq.ai (key file now hosted on nerq.ai)
    if nerq_urls:
        print(f"\n--- Submitting nerq.ai URLs to IndexNow ---")
        submit_to_indexnow("nerq.ai", nerq_urls, key_location="https://nerq.ai/zarq2026indexnow.txt")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
