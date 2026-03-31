#!/usr/bin/env python3
"""
System 11: Broken Link Auto-Monitor (C4)
Runs Wednesdays at 03:00.

Crawls target pages from broken_link_targets.json, finds dead outbound links,
checks if our pages (zarq.ai / nerq.ai) could be relevant replacements,
and appends findings to broken_links_found.json.

Uses only stdlib (urllib, html.parser) — no requests/bs4 dependency.
"""

import html.parser
import json
import logging
import os
import re
import ssl
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LOG_PATH = "/tmp/broken-link-monitor.log"
TARGETS_PATH = os.path.join(SCRIPT_DIR, "broken_link_targets.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "broken_links_found.json")
REPORT_DIR = os.path.join(PROJECT_ROOT, "docs", "auto-reports")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
REQUEST_DELAY = 0.5   # seconds between requests
TIMEOUT = 10           # seconds per request
MAX_LINKS_PER_TARGET = 10  # cap outbound links checked per page

# ---------------------------------------------------------------------------
# Logging — dual: file + stderr
# ---------------------------------------------------------------------------
logger = logging.getLogger("broken_link_monitor")
logger.setLevel(logging.INFO)

_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

_fh = logging.FileHandler(LOG_PATH)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)

_sh = logging.StreamHandler(sys.stderr)
_sh.setFormatter(_fmt)
logger.addHandler(_sh)

log = logger

# ---------------------------------------------------------------------------
# Keyword patterns (same as broken_link_finder.py)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# SSL context (some sites have iffy certs)
# ---------------------------------------------------------------------------
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------------------
# HTML link extractor (stdlib html.parser)
# ---------------------------------------------------------------------------
class LinkExtractor(html.parser.HTMLParser):
    """Extract href attributes from <a> tags."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value.strip())


def extract_links_from_html(html_text: str) -> list[str]:
    """Return list of href values found in HTML."""
    parser = LinkExtractor()
    try:
        parser.feed(html_text)
    except Exception:
        pass
    return parser.links


# ---------------------------------------------------------------------------
# HTTP helpers (urllib only)
# ---------------------------------------------------------------------------
def _make_request(url: str, method: str = "GET") -> Request:
    req = Request(url, method=method)
    req.add_header("User-Agent", USER_AGENT)
    return req


def fetch_page(url: str) -> str | None:
    """Fetch HTML content of a page. Returns None on failure."""
    try:
        req = _make_request(url, "GET")
        with urlopen(req, timeout=TIMEOUT, context=_ssl_ctx) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except Exception as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


def check_link(url: str) -> dict:
    """Check if a link is alive using HEAD, fallback to GET on 405."""
    result = {"url": url, "alive": False, "status_code": None, "error": None}

    # Try HEAD first
    try:
        req = _make_request(url, "HEAD")
        with urlopen(req, timeout=TIMEOUT, context=_ssl_ctx) as resp:
            result["status_code"] = resp.status
            if resp.status < 400:
                result["alive"] = True
                return result
    except HTTPError as e:
        result["status_code"] = e.code
        # 405 Method Not Allowed — fall through to GET
        if e.code == 405:
            pass
        elif e.code in (404, 410):
            return result
        else:
            # Other 4xx/5xx — fall through to GET
            pass
    except URLError:
        result["error"] = "connection_error"
        return result
    except Exception:
        # Fall through to GET
        pass

    if result["alive"]:
        return result

    # Fallback: GET
    try:
        req = _make_request(url, "GET")
        with urlopen(req, timeout=TIMEOUT, context=_ssl_ctx) as resp:
            result["status_code"] = resp.status
            result["alive"] = resp.status < 400
            result["error"] = None
    except HTTPError as e:
        result["status_code"] = e.code
        result["error"] = None
    except URLError:
        result["error"] = "connection_error"
    except Exception as e:
        result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Topic matching (mirrors broken_link_finder.py)
# ---------------------------------------------------------------------------
def suggest_replacement(dead_url: str) -> dict | None:
    """Given a dead URL, suggest a ZARQ/Nerq replacement URL and reason."""
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

    # Compare/vs keywords
    if COMPARE_KEYWORDS.search(combined):
        return {
            "our_url": "https://zarq.ai/compare/",
            "match_type": "comparison",
            "reason": "Dead link was a comparison/alternative page",
        }

    # Risk/security keywords
    if RISK_KEYWORDS.search(combined):
        return {
            "our_url": "https://zarq.ai/crash-watch",
            "match_type": "risk",
            "reason": "Dead link covered risk/security topics",
        }

    # Crypto keywords
    if CRYPTO_KEYWORDS.search(combined):
        return {
            "our_url": "https://zarq.ai/crash-watch",
            "match_type": "crypto",
            "reason": "Dead link covered crypto/DeFi topics",
        }

    # AI keywords
    if AI_KEYWORDS.search(combined):
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


# ---------------------------------------------------------------------------
# Link filtering
# ---------------------------------------------------------------------------
SKIP_PREFIXES = ("mailto:", "javascript:", "tel:", "#", "data:")


def is_external_link(href: str, source_domain: str) -> bool:
    """Return True if href is an external HTTP(S) link."""
    if not href:
        return False
    href_lower = href.lower()
    for prefix in SKIP_PREFIXES:
        if href_lower.startswith(prefix):
            return False
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    link_domain = parsed.netloc.lower().replace("www.", "")
    return link_domain != source_domain


def extract_external_links(html_text: str, source_url: str) -> list[str]:
    """Extract unique external links from HTML."""
    source_domain = urlparse(source_url).netloc.lower().replace("www.", "")
    raw_links = extract_links_from_html(html_text)
    seen = set()
    result = []
    for href in raw_links:
        full_url = urljoin(source_url, href)
        if not is_external_link(full_url, source_domain):
            continue
        # Normalize: strip fragment
        p = urlparse(full_url)
        clean = p._replace(fragment="").geturl()
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


# ---------------------------------------------------------------------------
# Core crawl logic
# ---------------------------------------------------------------------------
def crawl_target(target: dict) -> list[dict]:
    """Crawl one target page and return dead-link opportunities."""
    url = target["url"]
    niche = target.get("niche", "unknown")
    log.info("--- Target: %s [%s]", url, niche)

    html_text = fetch_page(url)
    if not html_text:
        return []

    external_links = extract_external_links(html_text, url)
    log.info("  Found %d external links (checking up to %d)", len(external_links), MAX_LINKS_PER_TARGET)

    opportunities = []
    for link in external_links[:MAX_LINKS_PER_TARGET]:
        time.sleep(REQUEST_DELAY)
        status = check_link(link)
        if status["alive"]:
            continue

        error_desc = str(status["status_code"] or status["error"])
        log.info("  DEAD: %s (%s)", link, error_desc)

        suggestion = suggest_replacement(link)
        if suggestion:
            opportunities.append({
                "source_url": url,
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


# ---------------------------------------------------------------------------
# Persistence — append + dedup
# ---------------------------------------------------------------------------
def load_existing_findings() -> list[dict]:
    """Load existing findings from broken_links_found.json."""
    if not os.path.exists(OUTPUT_PATH):
        return []
    try:
        with open(OUTPUT_PATH) as f:
            data = json.load(f)
        # Handle both formats: list or dict with "opportunities" key
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("opportunities", [])
    except (json.JSONDecodeError, OSError):
        return []
    return []


def dedup_findings(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merge new findings into existing, dedup by (source_url, dead_url)."""
    seen = set()
    for item in existing:
        key = (item.get("source_url") or item.get("source_page", ""), item.get("dead_url", ""))
        seen.add(key)

    merged = list(existing)
    added = 0
    for item in new:
        key = (item.get("source_url", ""), item.get("dead_url", ""))
        if key not in seen:
            seen.add(key)
            merged.append(item)
            added += 1

    log.info("Dedup: %d new unique findings added (from %d total new)", added, len(new))
    return merged


def save_findings(findings: list[dict], targets_crawled: int, new_count: int):
    """Save merged findings to broken_links_found.json."""
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "targets_crawled": targets_crawled,
        "total_findings": len(findings),
        "new_this_run": new_count,
        "opportunities": findings,
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    log.info("Saved %d total findings to %s", len(findings), OUTPUT_PATH)


# ---------------------------------------------------------------------------
# Weekly report
# ---------------------------------------------------------------------------
def generate_report(findings_new: list[dict], targets_crawled: int, elapsed: float):
    """Write a markdown summary report."""
    os.makedirs(REPORT_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(REPORT_DIR, f"broken-links-weekly-{date_str}.md")

    lines = [
        f"# Broken Link Monitor — Weekly Report {date_str}",
        "",
        f"- **Targets crawled:** {targets_crawled}",
        f"- **New dead links found:** {len(findings_new)}",
        f"- **Runtime:** {elapsed:.1f}s",
        "",
    ]

    if not findings_new:
        lines.append("No new broken link opportunities found this run.")
    else:
        lines.append("## New Opportunities")
        lines.append("")
        lines.append("| Source Page | Dead URL | Error | Suggested Replacement | Match Type |")
        lines.append("|---|---|---|---|---|")
        for f in findings_new:
            src = f.get("source_url", "?")
            dead = f.get("dead_url", "?")
            err = f.get("error_code", "?")
            sug = f.get("suggestion", {})
            our = sug.get("our_url", "-")
            mtype = sug.get("match_type", "-")
            lines.append(f"| {src} | {dead} | {err} | {our} | {mtype} |")

    lines.append("")
    lines.append("---")
    lines.append(f"Generated by `broken_link_monitor.py` at {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    log.info("Report written to %s", report_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    log.info("=== Broken Link Auto-Monitor starting ===")

    # Load targets
    try:
        with open(TARGETS_PATH) as f:
            targets = json.load(f)
    except FileNotFoundError:
        log.error("Targets file not found: %s", TARGETS_PATH)
        sys.exit(1)
    except json.JSONDecodeError as e:
        log.error("Invalid JSON in targets file: %s", e)
        sys.exit(1)

    log.info("Loaded %d targets from %s", len(targets), TARGETS_PATH)

    # Crawl all targets
    all_new = []
    for i, target in enumerate(targets, 1):
        log.info("=== [%d/%d] ===", i, len(targets))
        results = crawl_target(target)
        all_new.extend(results)
        time.sleep(REQUEST_DELAY)

    # Load existing, merge, dedup, save
    existing = load_existing_findings()
    merged = dedup_findings(existing, all_new)
    new_unique = len(merged) - len(existing)
    save_findings(merged, len(targets), new_unique)

    elapsed = time.time() - t0

    # Generate weekly report
    generate_report(all_new, len(targets), elapsed)

    # Summary
    log.info("=== DONE ===")
    log.info("Targets crawled: %d", len(targets))
    log.info("Dead links found this run: %d", len(all_new))
    log.info("New unique findings added: %d", new_unique)
    log.info("Total findings in DB: %d", len(merged))
    log.info("Elapsed: %.1fs", elapsed)

    sys.exit(0)


if __name__ == "__main__":
    main()
