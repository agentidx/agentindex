#!/usr/bin/env python3
"""Audit a Nerq localized page for language completeness.

USAGE:
    python3 scripts/audit_language_completeness.py /no/safe/nordvpn
    python3 scripts/audit_language_completeness.py /no/safe/nordvpn /de/safe/nordvpn
    python3 scripts/audit_language_completeness.py --base https://staging.nerq.ai /no/

WHY THIS EXISTS:
    On Dag 31, an old grep-based audit script gave a FALSE POSITIVE for
    Norwegian, claiming 4 English strings were still visible on /no/safe/
    nordvpn. We spent ~2 hours investigating before realizing the audit
    was matching:
        1. HTML comments like <!-- TRUST SCORE BREAKDOWN -->
        2. CSS class names like class="trust-score-breakdown"
        3. Script bodies containing English variable names
        4. Case-insensitive substring matches like "metodikk" vs "methodology"

    None of those are visible to users or AI crawlers. The page was
    actually 100% complete already.

THIS SCRIPT FIXES THAT:
    Uses Python's html.parser.HTMLParser to extract ONLY the visible
    text content. Strips comments, scripts, styles, and tag attributes
    before searching for English strings.

    Use this for every new language you add. Saves 2+ hours per language
    by eliminating false positives.

EXAMPLE OUTPUT:
    /no/safe/nordvpn:
      Visible text:        9348 chars
      English strings:     0 found ✅
      Internal links:      62/77 prefixed (80%)
      Status:              READY FOR PRODUCTION
"""
import argparse
import sys
import urllib.request
from html.parser import HTMLParser
from typing import List, Tuple


# Default English indicator strings to look for in visible text.
# These are phrases that should be translated on every localized page.
# Add more here as you discover untranslated strings during auditing.
ENGLISH_INDICATORS = [
    "Trust Score Breakdown",
    "Safety Guide",
    "Related Safety Rankings",
    "Key Findings",
    "Frequently Asked Questions",
    "Safer Alternatives",
    "Independent Trust",
    "See Also",
    "How We Rate",
    "Methodology",
    "Last Updated",
    "Data Sources",
    "Privacy Score",
    "Security Score",
    "Reliability Score",
    "Overall Trust",
    "Verdict",
    "Trust Components",
    "Browse Categories",
    "View All",
    "Read More",
    "Show More",
    "Hide",
    "Loading",
    "Click to expand",
    "Tap to expand",
]


class VisibleTextExtractor(HTMLParser):
    """Extract only the user-visible text from HTML.
    
    Skips: scripts, styles, comments, tag attributes, and the contents
    of <select>, <noscript>, and conditional comment blocks.
    """

    SKIP_TAGS = frozenset({"script", "style", "noscript", "select", "template"})

    def __init__(self):
        super().__init__()
        self.text_parts: List[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)

    def handle_comment(self, data):
        # Explicitly ignore HTML comments — never visible to users.
        pass

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def fetch_html(url: str, timeout: int = 30) -> str:
    """Fetch URL and return HTML body. Adds a User-Agent so we look like
    a real browser to avoid bot blocks."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) "
                          "Nerq-Audit/1.0",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_visible_text(html: str) -> str:
    """Strip HTML to visible-text-only via HTMLParser."""
    parser = VisibleTextExtractor()
    parser.feed(html)
    return parser.get_text()


def find_english_strings(visible_text: str, indicators: List[str]) -> List[Tuple[str, str]]:
    """Find English indicator strings in visible text.
    
    Returns list of (indicator, context) tuples where context is
    ~30 chars before and after the match.
    """
    found = []
    for indicator in indicators:
        idx = visible_text.find(indicator)
        if idx >= 0:
            start = max(0, idx - 30)
            end = min(len(visible_text), idx + len(indicator) + 30)
            context = visible_text[start:end].replace("\n", " ").strip()
            found.append((indicator, context))
    return found


def count_internal_links(html: str, lang: str) -> Tuple[int, int]:
    """Count (prefixed_count, total_internal_count) of internal links.
    
    Internal = href starting with /, not http://, https://, mailto:, etc.
    Prefixed = href starting with /{lang}/.
    """
    import re
    # Find all href="..." or href='...'
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    
    internal = []
    for h in hrefs:
        if h.startswith("/") and not h.startswith("//"):
            internal.append(h)
    
    # Dedupe (we want unique URLs, not raw count)
    internal = list(set(internal))
    
    if lang == "en":
        return len(internal), len(internal)  # English passes everything
    
    prefix = f"/{lang}/"
    prefixed = [h for h in internal if h.startswith(prefix) or h == f"/{lang}"]
    return len(prefixed), len(internal)


def detect_lang_from_url(url: str) -> str:
    """Detect language code from URL path. Returns 'en' if no /XX/ prefix."""
    import re
    m = re.match(r"https?://[^/]+/([a-z]{2})(/|$)", url)
    if m:
        return m.group(1)
    return "en"


def audit_url(url: str, base: str = "https://nerq.ai") -> dict:
    """Audit a single URL and return a result dict.
    
    Result keys: url, lang, visible_chars, english_found, link_prefixed,
    link_total, status.
    """
    if url.startswith("/"):
        full_url = base + url
    else:
        full_url = url
    
    lang = detect_lang_from_url(full_url)
    
    try:
        html = fetch_html(full_url)
    except Exception as e:
        return {
            "url": full_url,
            "lang": lang,
            "error": str(e),
            "status": "FETCH_FAILED",
        }
    
    visible = extract_visible_text(html)
    english = find_english_strings(visible, ENGLISH_INDICATORS)
    prefixed, total = count_internal_links(html, lang)
    
    pct = (prefixed * 100 // total) if total > 0 else 100
    
    # Threshold logic:
    # - 80%+ is READY (the mathematical max — global paths like /v1/, /static/,
    #   /methodology, /contact, etc are intentionally not prefixed)
    # - 60-79% means link-fix exists but Cloudflare may serve stale cache
    # - <60% means link-fix is missing entirely
    if english:
        status = f"NEEDS_TRANSLATION ({len(english)} strings)"
    elif lang != "en" and pct < 60:
        status = f"NEEDS_LINK_FIX ({pct}% prefixed)"
    elif lang != "en" and pct < 80:
        status = f"PARTIAL — likely stale cache ({pct}% prefixed)"
    else:
        status = f"READY ({pct}%)"
    
    return {
        "url": full_url,
        "lang": lang,
        "visible_chars": len(visible),
        "english_found": english,
        "link_prefixed": prefixed,
        "link_total": total,
        "link_pct": pct,
        "status": status,
    }


def print_result(result: dict):
    """Pretty-print a single audit result."""
    print(f"\n{result['url']}")
    print(f"  Language:        {result['lang']}")
    
    if "error" in result:
        print(f"  ERROR:           {result['error']}")
        return
    
    print(f"  Visible text:    {result['visible_chars']} chars")
    print(f"  Internal links:  {result['link_prefixed']}/{result['link_total']} prefixed ({result['link_pct']}%)")
    
    eng = result['english_found']
    if eng:
        print(f"  English strings: {len(eng)} found ❌")
        for indicator, context in eng[:5]:
            print(f"      \"{indicator}\" in: ...{context}...")
        if len(eng) > 5:
            print(f"      ... and {len(eng) - 5} more")
    else:
        print(f"  English strings: 0 found ✅")
    
    print(f"  Status:          {result['status']}")


def main():
    parser = argparse.ArgumentParser(
        description="Audit Nerq localized pages for language completeness."
    )
    parser.add_argument(
        "urls",
        nargs="+",
        help="URLs or paths to audit (e.g. /no/safe/nordvpn or full https URL)",
    )
    parser.add_argument(
        "--base",
        default="https://nerq.ai",
        help="Base URL for relative paths (default: https://nerq.ai)",
    )
    args = parser.parse_args()
    
    results = []
    for url in args.urls:
        result = audit_url(url, base=args.base)
        results.append(result)
        print_result(result)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    ready = sum(1 for r in results if r.get("status", "").startswith("READY"))
    failed = sum(1 for r in results if "FAILED" in r.get("status", ""))
    needs_work = len(results) - ready - failed
    
    print(f"  Total audited:  {len(results)}")
    print(f"  Ready:          {ready}")
    print(f"  Needs work:     {needs_work}")
    print(f"  Fetch failed:   {failed}")
    
    # Exit non-zero if any page is not ready (useful for CI)
    sys.exit(0 if needs_work == 0 and failed == 0 else 1)


if __name__ == "__main__":
    main()
