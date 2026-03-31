#!/usr/bin/env python3
"""
Broken Link Reclamation Finder

Crawls target pages, finds dead outbound links, and suggests
relevant ZARQ/Nerq replacement URLs for link reclamation outreach.

Usage:
    python broken_link_finder.py              # Full crawl
    python broken_link_finder.py --dry-run    # Preview targets without crawling
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TARGETS_PATH = os.path.join(SCRIPT_DIR, "broken_link_targets.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "broken_links_found.json")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

REQUEST_DELAY = 0.5  # seconds between requests (max 2 req/s)
TIMEOUT = 5          # seconds per request

# --- Topic matching rules ---------------------------------------------------

CRYPTO_KEYWORDS = re.compile(
    r"(crypto|token|defi|bitcoin|ethereum|blockchain|stablecoin|swap|yield|"
    r"lending|liquidity|dex|cex|nft|web3|solana|avalanche|polygon|arbitrum|"
    r"optimism|chainlink|uniswap|aave|compound|makerdao|lido|staking)",
    re.IGNORECASE,
)

AI_KEYWORDS = re.compile(
    r"(agent|ai[\-\s]?tool|mcp|model[\-\s]?context|llm|langchain|autogpt|"
    r"crewai|openai|anthropic|hugging[\-\s]?face|replicate|machine[\-\s]?learning|"
    r"chatbot|copilot|assistant|automation)",
    re.IGNORECASE,
)

COMPARE_KEYWORDS = re.compile(
    r"(compare|vs|versus|alternative|competitor|comparison|review)",
    re.IGNORECASE,
)

RISK_KEYWORDS = re.compile(
    r"(risk|security|audit|vulnerability|exploit|hack|rug[\-\s]?pull|scam|fraud|safety)",
    re.IGNORECASE,
)

COMPETITOR_MAP = {
    "tokensniffer": "/compare/zarq-vs-token-sniffer",
    "token-sniffer": "/compare/zarq-vs-token-sniffer",
    "token sniffer": "/compare/zarq-vs-token-sniffer",
    "rugcheck": "/compare/zarq-vs-rugcheck",
    "rug-check": "/compare/zarq-vs-rugcheck",
    "goplus": "/compare/zarq-vs-goplus",
    "go-plus": "/compare/zarq-vs-goplus",
    "gopluslabs": "/compare/zarq-vs-goplus",
    "certik": "/compare/zarq-vs-certik",
    "de.fi": "/compare/zarq-vs-defi",
    "defisafety": "/compare/zarq-vs-defi-safety",
}


def suggest_replacement(dead_url: str) -> dict | None:
    """Given a dead URL, suggest a ZARQ/Nerq replacement URL and reason."""
    url_lower = dead_url.lower()
    parsed = urlparse(dead_url)
    domain = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()
    combined = f"{domain} {path}"

    # Check competitor names first (most specific)
    for keyword, replacement in COMPETITOR_MAP.items():
        if keyword in combined:
            return {
                "our_url": f"https://zarq.ai{replacement}",
                "match_type": "competitor",
                "reason": f"Dead link pointed to competitor ({keyword})",
            }

    # Check compare/vs keywords
    if COMPARE_KEYWORDS.search(combined):
        return {
            "our_url": "https://zarq.ai/compare/",
            "match_type": "comparison",
            "reason": "Dead link was a comparison/alternative page",
        }

    # Check risk/security keywords
    if RISK_KEYWORDS.search(combined):
        return {
            "our_url": "https://zarq.ai/crash-watch",
            "match_type": "risk",
            "reason": "Dead link covered risk/security topics",
        }

    # Check crypto keywords
    if CRYPTO_KEYWORDS.search(combined):
        return {
            "our_url": "https://zarq.ai/crash-watch",
            "match_type": "crypto",
            "reason": "Dead link covered crypto/DeFi topics",
        }

    # Check AI keywords
    if AI_KEYWORDS.search(combined):
        # Decide between /safe/ and /mcp/ based on specifics
        if "mcp" in combined or "model-context" in combined:
            our_url = "https://nerq.ai/mcp/"
        else:
            our_url = "https://nerq.ai/safe/"
        return {
            "our_url": our_url,
            "match_type": "ai",
            "reason": "Dead link covered AI/agent topics",
        }

    return None


def is_external_link(href: str, source_domain: str) -> bool:
    """Return True if href is an external HTTP(S) link."""
    if not href:
        return False
    # Skip non-http schemes
    for prefix in ("mailto:", "javascript:", "tel:", "#", "data:"):
        if href.lower().startswith(prefix):
            return False
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False  # relative link
    link_domain = parsed.netloc.lower().replace("www.", "")
    return link_domain != source_domain


def fetch_page(url: str, session: requests.Session) -> str | None:
    """Fetch HTML content of a page."""
    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


def check_link(url: str, session: requests.Session) -> dict:
    """Check if a link is alive. Returns status info."""
    result = {"url": url, "alive": False, "status_code": None, "error": None}

    # Try HEAD first
    try:
        resp = session.head(url, timeout=TIMEOUT, allow_redirects=True)
        result["status_code"] = resp.status_code
        if resp.status_code < 400:
            result["alive"] = True
            return result
        if resp.status_code in (404, 410):
            return result
    except requests.ConnectionError:
        result["error"] = "connection_error"
        return result
    except requests.Timeout:
        result["error"] = "timeout"
        return result
    except requests.RequestException:
        pass  # Fall through to GET

    # HEAD returned 4xx/5xx or failed — try GET
    try:
        resp = session.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
        resp.close()
        result["status_code"] = resp.status_code
        result["alive"] = resp.status_code < 400
        result["error"] = None
    except requests.ConnectionError:
        result["error"] = "connection_error"
    except requests.Timeout:
        result["error"] = "timeout"
    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def extract_external_links(html: str, source_url: str) -> list[str]:
    """Extract unique external links from HTML."""
    parsed_source = urlparse(source_url)
    source_domain = parsed_source.netloc.lower().replace("www.", "")

    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        # Resolve relative URLs (shouldn't match external filter, but be safe)
        full_url = urljoin(source_url, href)
        if is_external_link(full_url, source_domain):
            # Normalize: strip fragments
            p = urlparse(full_url)
            clean = p._replace(fragment="").geturl()
            links.add(clean)
    return sorted(links)


def crawl_target(target: dict, session: requests.Session, dry_run: bool) -> list[dict]:
    """Crawl one target page and return dead link opportunities."""
    url = target["url"]
    niche = target.get("niche", "unknown")
    log.info("--- Target: %s [%s]", url, niche)

    if dry_run:
        log.info("  [DRY RUN] Would crawl %s", url)
        return []

    html = fetch_page(url, session)
    if not html:
        return []

    external_links = extract_external_links(html, url)
    log.info("  Found %d external links", len(external_links))

    opportunities = []
    for link in external_links:
        time.sleep(REQUEST_DELAY)

        status = check_link(link, session)
        if status["alive"]:
            continue

        # Dead link found
        error_desc = str(status["status_code"] or status["error"])
        log.info("  DEAD: %s (%s)", link, error_desc)

        suggestion = suggest_replacement(link)
        if suggestion:
            opportunities.append({
                "source_page": url,
                "source_niche": niche,
                "dead_url": link,
                "error_code": error_desc,
                "suggestion": suggestion,
                "found_at": datetime.now(timezone.utc).isoformat(),
            })
            log.info("    -> Suggest: %s (%s)", suggestion["our_url"], suggestion["match_type"])
        else:
            log.info("    -> No matching replacement URL")

    return opportunities


def main():
    parser = argparse.ArgumentParser(description="Broken Link Reclamation Finder")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview target pages without crawling external links",
    )
    parser.add_argument(
        "--targets",
        default=TARGETS_PATH,
        help="Path to targets JSON file",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_PATH,
        help="Path to output JSON file",
    )
    args = parser.parse_args()

    # Load targets
    try:
        with open(args.targets) as f:
            targets = json.load(f)
    except FileNotFoundError:
        log.error("Targets file not found: %s", args.targets)
        sys.exit(1)

    log.info("Loaded %d targets from %s", len(targets), args.targets)

    if args.dry_run:
        log.info("=== DRY RUN MODE ===")
        for t in targets:
            log.info("  [%s] %s (%s)", t.get("niche", "?"), t["url"], t.get("type", "?"))
        log.info("Total: %d pages would be crawled", len(targets))
        return

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    all_opportunities = []
    for i, target in enumerate(targets, 1):
        log.info("=== [%d/%d] ===", i, len(targets))
        results = crawl_target(target, session, dry_run=False)
        all_opportunities.extend(results)
        time.sleep(REQUEST_DELAY)

    # Save results
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets_crawled": len(targets),
        "dead_links_found": len(all_opportunities),
        "opportunities": all_opportunities,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    log.info("=== DONE ===")
    log.info("Dead links with replacement suggestions: %d", len(all_opportunities))
    log.info("Results saved to %s", args.output)


if __name__ == "__main__":
    main()
