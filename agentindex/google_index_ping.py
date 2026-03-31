#!/usr/bin/env python3
"""Ping Google with all ZARQ and Nerq sitemaps to trigger re-crawling."""

import urllib.request
import urllib.parse
import sys

SITEMAPS = [
    "https://zarq.ai/sitemap.xml",
    "https://zarq.ai/sitemap-pages.xml",
    "https://zarq.ai/sitemap-tokens.xml",
    "https://zarq.ai/sitemap-crypto.xml",
    "https://zarq.ai/sitemap-compare.xml",
    "https://zarq.ai/sitemap-zarq-content.xml",
    "https://zarq.ai/sitemap-zarq-compare.xml",
    "https://nerq.ai/sitemap-index.xml",
    "https://nerq.ai/sitemap-static.xml",
    "https://nerq.ai/sitemap-safe.xml",
    "https://nerq.ai/sitemap-mcp.xml",
    "https://nerq.ai/sitemap-compare.xml",
]


def ping_google(sitemap_url: str) -> int:
    """Ping Google with a sitemap URL. Returns HTTP status code."""
    encoded = urllib.parse.quote(sitemap_url, safe="")
    ping_url = f"http://www.google.com/ping?sitemap={encoded}"
    try:
        req = urllib.request.Request(ping_url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        print(f"  ERROR: {e}")
        return -1


def main():
    print("=== Google Sitemap Ping ===\n")
    success = 0
    for sitemap in SITEMAPS:
        status = ping_google(sitemap)
        marker = "OK" if status == 200 else "FAIL"
        print(f"  [{marker}] {status}  {sitemap}")
        if status == 200:
            success += 1

    print(f"\nResults: {success}/{len(SITEMAPS)} sitemaps pinged successfully.")
    return 0 if success == len(SITEMAPS) else 1


if __name__ == "__main__":
    sys.exit(main())
