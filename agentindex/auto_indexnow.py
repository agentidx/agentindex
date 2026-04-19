#!/usr/bin/env python3
"""
Auto IndexNow Submission (B4)
==============================
Runs daily at 07:00 via LaunchAgent com.nerq.auto-indexnow.
Detects new/changed URLs since last run by comparing slug files
and sitemap contents, then submits to IndexNow for both zarq.ai
and nerq.ai.

Exit 0 on success.
"""

import json
import logging
import os
import sqlite3
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = "/tmp/auto-indexnow.log"
STATE_PATH = Path(__file__).parent / "auto_indexnow_state.json"

# Smedjan batch-trigger source (T152). The runtime queue lives outside the
# repo at ~/smedjan/measurement/indexnow-queue.txt; the in-repo path is the
# canonical template/fallback (one URL or slug per line, # for comments).
SMEDJAN_QUEUE_FILES = [
    Path.home() / "smedjan" / "measurement" / "indexnow-queue.txt",
    Path(__file__).resolve().parent.parent / "smedjan" / "measurement" / "indexnow-queue.txt",
]
SMEDJAN_BATCH_TOP_DEMAND = 100
SMEDJAN_BATCH_ENRICHED_HOURS = 24

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("auto-indexnow")

INDEXNOW_KEYS = {"zarq.ai": "zarq2026indexnow", "nerq.ai": "nerq2026indexnow"}
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH_SIZE = 100
XML_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Slug files that generate pages
SLUG_FILES = {
    "token_slugs": Path(__file__).parent / "crypto" / "token_slugs.json",
    "agent_safety_slugs": Path(__file__).parent / "agent_safety_slugs.json",
    "mcp_server_slugs": Path(__file__).parent / "mcp_server_slugs.json",
    "comparison_pairs": Path(__file__).parent / "comparison_pairs.json",
    "vitality_compare_pairs": Path(__file__).parent / "crypto" / "vitality_compare_pairs.json",
}

# Dynamic sitemap discovery — no more hardcoded lists.
# Fetches sitemap-index.xml + sitemap-localized.xml and extracts all child sitemaps.

def _discover_sitemaps(domain: str) -> list[str]:
    """Discover all sitemap URLs for a domain by parsing the sitemap index(es).
    For nerq.ai: parses sitemap-index.xml + sitemap-localized.xml.
    For zarq.ai: parses robots.txt Sitemap: directives (no sitemap-index)."""
    sitemaps = []

    if domain == "zarq.ai":
        # zarq has no sitemap-index — parse robots.txt for Sitemap: lines
        try:
            req = urllib.request.Request("http://localhost:8000/robots.txt",
                                         headers={"Host": "zarq.ai"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                for line in resp.read().decode().splitlines():
                    if line.strip().lower().startswith("sitemap:"):
                        url = line.split(":", 1)[1].strip()
                        if "zarq.ai" in url:
                            sitemaps.append(url)
        except Exception as e:
            logger.warning("Could not parse zarq robots.txt: %s", e)
    else:
        # nerq: parse sitemap indexes
        indices = ["http://localhost:8000/sitemap-index.xml",
                    "http://localhost:8000/sitemap-localized.xml"]
        for index_url in indices:
            try:
                req = urllib.request.Request(index_url, headers={"Host": domain})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    root = ET.fromstring(resp.read())
                for loc in root.findall(".//sm:loc", XML_NS):
                    if loc.text:
                        sitemaps.append(loc.text.strip())
                if not sitemaps:
                    for loc in root.iter("loc"):
                        if loc.text:
                            sitemaps.append(loc.text.strip())
            except Exception as e:
                logger.warning("Could not fetch index %s: %s", index_url, e)

    # Filter: only keep sitemaps for the target domain
    sitemaps = [s for s in sitemaps if domain in s]
    logger.info("Discovered %d sitemaps for %s", len(sitemaps), domain)
    return sitemaps

# Legacy hardcoded lists kept as fallbacks (used if dynamic discovery fails)
ZARQ_SITEMAPS = [
    "http://localhost:8000/sitemap-pages.xml",
    "http://localhost:8000/sitemap-tokens.xml",
    "http://localhost:8000/sitemap-crypto.xml",
    "http://localhost:8000/sitemap-compare.xml",
    "http://localhost:8000/sitemap-zarq-content.xml",
    "http://localhost:8000/sitemap-zarq-compare.xml",
    "http://localhost:8000/sitemap-safe-tokens.xml",
]

NERQ_SITEMAPS = [
    "http://localhost:8000/sitemap-static.xml",
    "http://localhost:8000/sitemap-safe.xml",
    "http://localhost:8000/sitemap-safe-1.xml",
    "http://localhost:8000/sitemap-safe-2.xml",
    "http://localhost:8000/sitemap-safe-3.xml",
    "http://localhost:8000/sitemap-safe-4.xml",
    "http://localhost:8000/sitemap-safe-5.xml",
    "http://localhost:8000/sitemap-safe-6.xml",
    "http://localhost:8000/sitemap-safe-7.xml",
    "http://localhost:8000/sitemap-safe-8.xml",
    "http://localhost:8000/sitemap-safe-9.xml",
    "http://localhost:8000/sitemap-safe-10.xml",
    "http://localhost:8000/sitemap-safe-11.xml",
    "http://localhost:8000/sitemap-safety.xml",
    "http://localhost:8000/sitemap-mcp.xml",
    "http://localhost:8000/sitemap-compare.xml",
    "http://localhost:8000/sitemap-compare-pages.xml",
    "http://localhost:8000/sitemap-best.xml",
    "http://localhost:8000/sitemap-alternatives.xml",
    "http://localhost:8000/sitemap-guides.xml",
    "http://localhost:8000/sitemap-trending.xml",
    "http://localhost:8000/sitemap-models.xml",
    "http://localhost:8000/sitemap-models-1.xml",
    "http://localhost:8000/sitemap-models-2.xml",
    "http://localhost:8000/sitemap-models-3.xml",
    "http://localhost:8000/sitemap-models-4.xml",
    "http://localhost:8000/sitemap-models-5.xml",
    "http://localhost:8000/sitemap-models-6.xml",
    "http://localhost:8000/sitemap-models-7.xml",
    "http://localhost:8000/sitemap-blog.xml",
    "http://localhost:8000/sitemap-answers.xml",
    "http://localhost:8000/sitemap-packages.xml",
    "http://localhost:8000/sitemap-packages-1.xml",
    "http://localhost:8000/sitemap-packages-2.xml",
    "http://localhost:8000/sitemap-packages-3.xml",
    "http://localhost:8000/sitemap-spaces.xml",
    "http://localhost:8000/sitemap-containers.xml",
    "http://localhost:8000/sitemap-datasets.xml",
    "http://localhost:8000/sitemap-orgs.xml",
]


def load_state() -> dict:
    """Load previous run state."""
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict):
    """Save current state for next run comparison."""
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def load_slugs(path: Path) -> set[str]:
    """Load a slug file and return set of entries."""
    if not path.exists():
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            # Could be list of strings or list of dicts
            slugs = set()
            for item in data:
                if isinstance(item, str):
                    slugs.add(item)
                elif isinstance(item, dict):
                    # comparison_pairs: [{"slug": "...", ...}]
                    s = item.get("slug") or item.get("id") or item.get("name", "")
                    if s:
                        slugs.add(str(s))
            return slugs
        elif isinstance(data, dict):
            return set(data.keys())
        return set()
    except Exception as e:
        logger.warning("Failed to load %s: %s", path, e)
        return set()


def fetch_sitemap_urls(sitemap_url: str) -> list[str]:
    """Fetch and parse a sitemap XML, returning all <loc> URLs."""
    try:
        req = urllib.request.Request(sitemap_url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        urls = []
        for loc in root.findall(".//sm:loc", XML_NS):
            if loc.text:
                urls.append(loc.text.strip())
        if not urls:
            for loc in root.iter("loc"):
                if loc.text:
                    urls.append(loc.text.strip())
        return urls
    except Exception as e:
        logger.warning("Could not fetch %s: %s", sitemap_url, e)
        return []


def submit_to_indexnow(host: str, urls: list[str], key_location: str) -> tuple[int, int]:
    """Submit URLs in batches. Returns (success_count, fail_count)."""
    if not urls:
        return 0, 0

    success = 0
    fail = 0

    for i in range(0, len(urls), BATCH_SIZE):
        batch = urls[i:i + BATCH_SIZE]
        payload = {
            "host": host,
            "key": INDEXNOW_KEYS.get(host, "zarq2026indexnow"),
            "keyLocation": key_location,
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
            logger.error("IndexNow batch failed: %s", e)
            fail += len(batch)
            continue

        if status in (200, 202):
            success += len(batch)
            if (i // BATCH_SIZE + 1) % 100 == 0:
                logger.info("  [OK] Batch %d: %d/%d URLs submitted", i // BATCH_SIZE + 1, success, len(urls))
        elif status == 429:
            fail += len(batch)
            logger.warning("  [RATE LIMITED] Batch %d: HTTP 429 — stopping", i // BATCH_SIZE + 1)
            break  # Stop on rate limit instead of burning through all batches
        else:
            fail += len(batch)
            logger.warning("  [WARN] Batch %d: %d URLs -> HTTP %d", i // BATCH_SIZE + 1, len(batch), status)

        time.sleep(0.3)  # 0.3s between batches

    return success, fail


# ── Smedjan batch trigger (T152) ────────────────────────────────
# Adds a separate URL source to the daily IndexNow run, sourced from:
#   1. software_registry rows whose enriched_at moved in the last 24h
#   2. top-N entries from smedjan.ai_demand_scores (N=100)
#   3. operator-curated list at ~/smedjan/measurement/indexnow-queue.txt
# All three feed nerq.ai/safe/{slug}; the queue file may also contain full
# URLs (any host) — those are routed by host. Failures here are logged and
# swallowed so the existing IndexNow flow keeps running.

def _slug_to_safe_url(slug: str) -> str:
    return f"https://nerq.ai/safe/{slug}"


def _normalize_queue_entry(line: str):
    """Map a queue file line to (host, url) or None for blanks/comments."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("http://") or s.startswith("https://"):
        from urllib.parse import urlparse
        host = urlparse(s).netloc
        if not host:
            return None
        return host, s
    # bare slug → default to nerq.ai/safe/{slug}
    return "nerq.ai", _slug_to_safe_url(s)


def _load_smedjan_queue_file():
    entries = []
    for path in SMEDJAN_QUEUE_FILES:
        if not path.exists():
            continue
        try:
            with open(path) as f:
                for line in f:
                    pair = _normalize_queue_entry(line)
                    if pair is not None:
                        entries.append(pair)
            logger.info("  Smedjan queue file %s: %d entries", path, len(entries))
            return entries  # first existing file wins
        except Exception as e:
            logger.warning("  Could not read smedjan queue %s: %s", path, e)
    return entries


def _smedjan_top_demand_slugs(limit: int = SMEDJAN_BATCH_TOP_DEMAND) -> list[str]:
    """Top-N slugs by ai_demand_score from smedjan DB. Empty list on failure."""
    try:
        from smedjan import sources as _sm_sources
        with _sm_sources.smedjan_db_cursor() as (_conn, cur):
            cur.execute(
                "SELECT slug FROM smedjan.ai_demand_scores "
                "ORDER BY score DESC NULLS LAST LIMIT %s",
                (limit,),
            )
            return [r[0] for r in cur.fetchall() if r[0]]
    except Exception as e:
        logger.warning("  Smedjan top-demand query failed: %s", e)
        return []


def _smedjan_recently_enriched_slugs(hours: int = SMEDJAN_BATCH_ENRICHED_HOURS) -> list[str]:
    """Slugs whose enriched_at moved in the last N hours (Nerq RO)."""
    try:
        import psycopg2
        conn = psycopg2.connect(dbname="agentindex", user="anstudio")
        conn.set_session(readonly=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT slug FROM software_registry "
            "WHERE enriched_at >= NOW() - (%s || ' hours')::interval "
            "  AND slug IS NOT NULL AND slug <> ''",
            (str(hours),),
        )
        slugs = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return slugs
    except Exception as e:
        logger.warning("  Smedjan enriched-at query failed: %s", e)
        return []


def collect_smedjan_batch_urls():
    """Return {host: [urls]} for the Smedjan T152 batch trigger.

    Sources:
      - top-100 demand slugs
      - recently enriched (24h) slugs
      - queue file entries (may include foreign hosts)

    Deduplicated per host. Provenance is logged but not embedded in output.
    """
    by_host = {"nerq.ai": set(), "zarq.ai": set()}

    top = _smedjan_top_demand_slugs()
    for s in top:
        by_host["nerq.ai"].add(_slug_to_safe_url(s))
    if top:
        logger.info("  Smedjan top-demand: %d slugs", len(top))

    enriched = _smedjan_recently_enriched_slugs()
    for s in enriched:
        by_host["nerq.ai"].add(_slug_to_safe_url(s))
    if enriched:
        logger.info("  Smedjan enriched(<24h): %d slugs", len(enriched))

    queued = _load_smedjan_queue_file()
    for host, url in queued:
        by_host.setdefault(host, set()).add(url)
    if queued:
        logger.info("  Smedjan queue file: %d entries", len(queued))

    return {host: sorted(urls) for host, urls in by_host.items() if urls}


def detect_new_urls(prev_state: dict) -> tuple[list[str], list[str], dict]:
    """Detect new/changed URLs since last run.
    Returns (zarq_new_urls, nerq_new_urls, new_state).
    """
    new_state = {}
    zarq_new = []
    nerq_new = []

    # Strategy 1: Compare slug file contents
    for name, path in SLUG_FILES.items():
        current = load_slugs(path)
        prev_slugs = set(prev_state.get(f"slugs_{name}", []))
        new_slugs = current - prev_slugs
        new_state[f"slugs_{name}"] = list(current)

        if new_slugs:
            logger.info("  %s: %d new slugs", name, len(new_slugs))

            if name == "token_slugs":
                for s in new_slugs:
                    zarq_new.append(f"https://zarq.ai/token/{s}")
            elif name == "agent_safety_slugs":
                for s in new_slugs:
                    nerq_new.append(f"https://nerq.ai/safe/{s}")
            elif name == "mcp_server_slugs":
                for s in new_slugs:
                    nerq_new.append(f"https://nerq.ai/mcp/{s}")
            elif name == "comparison_pairs":
                for s in new_slugs:
                    nerq_new.append(f"https://nerq.ai/compare/{s}")
            elif name == "vitality_compare_pairs":
                for s in new_slugs:
                    zarq_new.append(f"https://zarq.ai/compare/{s}")

    # Strategy 2: Dynamic sitemap discovery + compare full URL sets
    prev_zarq_urls = set(prev_state.get("zarq_urls", []))
    prev_nerq_urls = set(prev_state.get("nerq_urls", []))

    # Discover sitemaps dynamically from sitemap-index.xml
    zarq_sitemap_urls = _discover_sitemaps("zarq.ai")
    nerq_sitemap_urls = _discover_sitemaps("nerq.ai")

    # Fallback to hardcoded lists if discovery returns nothing
    zarq_sm_sources = zarq_sitemap_urls if zarq_sitemap_urls else ZARQ_SITEMAPS
    nerq_sm_sources = nerq_sitemap_urls if nerq_sitemap_urls else NERQ_SITEMAPS

    def _fetch_all_from_sitemaps(sm_sources, domain):
        """Fetch URLs from non-lang sitemaps. Lang sitemaps are too heavy (50K URLs
        each × 1470 = would take 45 min). Instead we fetch only the core sitemaps
        and handle lang URLs separately via direct DB query."""
        result = set()
        # Split: core sitemaps (small, fast) vs lang sitemaps (huge, skip fetching)
        core_sms = [s for s in sm_sources if "sitemap-lang-" not in s]
        lang_count = len(sm_sources) - len(core_sms)
        if lang_count > 0:
            logger.info("    Skipping %d lang sitemaps (handled via DB query)", lang_count)

        for i, sm in enumerate(core_sms):
            local_sm = sm
            if sm.startswith(f"https://{domain}/"):
                local_sm = sm.replace(f"https://{domain}/", "http://localhost:8000/")
            elif not sm.startswith("http://localhost"):
                continue
            urls = fetch_sitemap_urls(local_sm)
            result.update(u for u in urls if domain in u)
            if (i + 1) % 5 == 0:
                time.sleep(0.5)
            if (i + 1) % 20 == 0:
                logger.info("    Fetched %d/%d core sitemaps (%d URLs)", i + 1, len(core_sms), len(result))
        return result

    current_zarq_urls = _fetch_all_from_sitemaps(zarq_sm_sources, "zarq.ai")
    current_nerq_urls = _fetch_all_from_sitemaps(nerq_sm_sources, "nerq.ai")

    # Add high-value lang URLs from DB (kings × active languages)
    # Full 36M+ URL set is impractical — submit top entities per language
    try:
        import psycopg2
        _pg = psycopg2.connect(dbname="agentindex", user="anstudio")
        _pg.set_session(readonly=True)
        _cur = _pg.cursor()
        # M5.1 EXPERIMENT (started 2026-04-11): Kings prioritization removed
        # to test crawl bias hypothesis. Random sampling from broader pool
        # (trust_score >= 50) ensures Kings get ~1.6% of slots, matching
        # their natural prevalence rather than 100%. After 7 days, compare
        # citation yield for Kings vs non-Kings sampled this way.
        # See: docs/status/leverage-sprint-day-3-m5-experiment.md
        # Reverse: restore the WHERE/ORDER BY clauses commented below.
        # ORIGINAL: WHERE (is_king = true OR trust_score >= 70)
        #           ORDER BY is_king DESC NULLS LAST, trust_score DESC NULLS LAST
        _cur.execute("""
            SELECT slug FROM software_registry
            WHERE trust_score IS NOT NULL AND trust_score >= 50
              AND description IS NOT NULL AND description != ''
            ORDER BY RANDOM()
            LIMIT 50000
        """)
        _slugs = [r[0] for r in _cur.fetchall()]
        _cur.close()
        _pg.close()

        # Active translated languages (those with full quality translations)
        _active_langs = ["es", "de", "fr", "ja", "pt", "id"]
        _lang_url_count = 0
        for _lang in _active_langs:
            for _slug in _slugs:
                current_nerq_urls.add(f"https://nerq.ai/{_lang}/safe/{_slug}")
                _lang_url_count += 1
        logger.info("  [M5.1 EXPERIMENT] Added %d random-sampled lang URLs (%d entities × %d langs)",
                     _lang_url_count, len(_slugs), len(_active_langs))
    except Exception as _db_err:
        logger.warning("Could not generate lang URLs from DB: %s", _db_err)

    sitemap_zarq_new = current_zarq_urls - prev_zarq_urls
    sitemap_nerq_new = current_nerq_urls - prev_nerq_urls

    if sitemap_zarq_new:
        logger.info("  Sitemap: %d new zarq.ai URLs", len(sitemap_zarq_new))
    if sitemap_nerq_new:
        logger.info("  Sitemap: %d new nerq.ai URLs", len(sitemap_nerq_new))

    zarq_new.extend(sitemap_zarq_new)
    nerq_new.extend(sitemap_nerq_new)

    new_state["zarq_urls"] = list(current_zarq_urls)
    new_state["nerq_urls"] = list(current_nerq_urls)

    # T152: Smedjan batch trigger — fold in URLs from demand/enriched/queue.
    try:
        smedjan_batch = collect_smedjan_batch_urls()
        for host, urls in smedjan_batch.items():
            if host == "zarq.ai":
                zarq_new.extend(urls)
            else:
                nerq_new.extend(urls)
        if smedjan_batch:
            logger.info("  Smedjan batch trigger contributed: %s",
                        {h: len(u) for h, u in smedjan_batch.items()})
    except Exception as e:
        logger.warning("  Smedjan batch trigger failed (existing flow continues): %s", e)

    # Deduplicate
    zarq_new = list(set(zarq_new))
    nerq_new = list(set(nerq_new))

    # Always include key pages that may have updated content (vitality recalc etc.)
    # These are resubmitted daily to ensure freshness
    daily_zarq = [
        "https://zarq.ai/vitality",
        "https://zarq.ai/tokens",
        "https://zarq.ai/crash-watch",
        "https://zarq.ai/scan",
    ]
    daily_nerq = [
        "https://nerq.ai/",
        "https://nerq.ai/discover",
        "https://nerq.ai/safety-digest",
        "https://nerq.ai/llms.txt",
        "https://nerq.ai/.well-known/agent.json",
    ]
    zarq_new.extend(daily_zarq)
    nerq_new.extend(daily_nerq)

    zarq_new = list(set(zarq_new))
    nerq_new = list(set(nerq_new))

    return zarq_new, nerq_new, new_state


DAILY_INDEXNOW_BUDGET = 200_000  # IndexNow rate limit ~200-300K/day, be conservative

# ── Priority-based submit tracking ──────────────────────────────
# Track which URLs have been submitted and when, using a SQLite DB.
_SUBMIT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "indexnow_submit_tracking.db")

def _init_tracking_db():
    os.makedirs(os.path.dirname(_SUBMIT_DB), exist_ok=True)
    conn = sqlite3.connect(_SUBMIT_DB, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS submitted_urls (
        url TEXT PRIMARY KEY,
        first_submitted TEXT NOT NULL,
        last_submitted TEXT NOT NULL,
        submit_count INTEGER DEFAULT 1
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS submitted_sitemaps (
        sitemap_url TEXT PRIMARY KEY,
        last_pinged TEXT NOT NULL
    )""")
    conn.commit()
    return conn

def _prioritize_urls(urls: list[str], budget: int) -> list[str]:
    """Sort URLs by priority: never-submitted first, then oldest-submitted.
    Returns at most `budget` URLs."""
    if len(urls) <= budget:
        return urls
    try:
        conn = _init_tracking_db()
        # Split into never-submitted and previously-submitted
        known = set()
        for batch_start in range(0, len(urls), 500):
            batch = urls[batch_start:batch_start+500]
            placeholders = ",".join("?" * len(batch))
            rows = conn.execute(f"SELECT url FROM submitted_urls WHERE url IN ({placeholders})", batch).fetchall()
            known.update(r[0] for r in rows)
        conn.close()

        never = [u for u in urls if u not in known]
        old = [u for u in urls if u in known]
        logger.info("  Priority: %d never-submitted, %d previously-submitted", len(never), len(old))

        # Take never-submitted first, fill remaining with old
        result = never[:budget]
        remaining = budget - len(result)
        if remaining > 0:
            result.extend(old[:remaining])
        return result
    except Exception as e:
        logger.warning("Priority sorting failed: %s — using first %d", e, budget)
        return urls[:budget]

def _record_submitted(urls: list[str]):
    """Record URLs as submitted in tracking DB."""
    try:
        conn = _init_tracking_db()
        now = datetime.now(timezone.utc).isoformat()
        for i in range(0, len(urls), 1000):
            batch = urls[i:i+1000]
            conn.executemany(
                "INSERT INTO submitted_urls (url, first_submitted, last_submitted, submit_count) "
                "VALUES (?, ?, ?, 1) ON CONFLICT(url) DO UPDATE SET "
                "last_submitted=excluded.last_submitted, submit_count=submit_count+1",
                [(u, now, now) for u in batch]
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Recording submissions failed: %s", e)


# ── Google Ping ─────────────────────────────────────────────────

def ping_google_sitemaps(sitemap_urls: list[str], dry_run=False) -> int:
    """Ping Google for each sitemap URL. No rate limit issues — 1 req/sec is safe."""
    import urllib.parse
    pinged = 0
    for sm in sitemap_urls:
        encoded = urllib.parse.quote(sm, safe='')
        ping_url = f"https://www.google.com/ping?sitemap={encoded}"
        if dry_run:
            pinged += 1
            continue
        try:
            req = urllib.request.Request(ping_url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
            if status == 200:
                pinged += 1
            else:
                logger.warning("  Google ping %d for %s", status, sm[:80])
        except Exception as e:
            logger.warning("  Google ping failed for %s: %s", sm[:60], e)
        time.sleep(1)
        if pinged % 100 == 0 and pinged > 0:
            logger.info("  Google pinged %d/%d sitemaps", pinged, len(sitemap_urls))
    return pinged


def main(dry_run=False, max_urls=0):
    t0 = time.time()
    now = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("Auto IndexNow submission started at %s%s", now.isoformat(),
                " [DRY RUN]" if dry_run else "")

    prev_state = load_state()
    last_run = prev_state.get("last_run", "never")
    logger.info("Last run: %s", last_run)

    logger.info("Detecting new/changed URLs...")
    zarq_urls, nerq_urls, new_state = detect_new_urls(prev_state)

    budget = max_urls if max_urls > 0 else DAILY_INDEXNOW_BUDGET
    logger.info("Candidate URLs: zarq.ai=%d, nerq.ai=%d (budget: %d)", len(zarq_urls), len(nerq_urls), budget)

    # Priority-based selection: never-submitted first, then oldest
    zarq_budget = min(len(zarq_urls), budget // 10)  # ~10% for zarq
    nerq_budget = budget - zarq_budget
    zarq_urls = _prioritize_urls(zarq_urls, zarq_budget)
    nerq_urls = _prioritize_urls(nerq_urls, nerq_budget)

    logger.info("After priority: zarq.ai=%d, nerq.ai=%d", len(zarq_urls), len(nerq_urls))

    if dry_run:
        logger.info("[DRY RUN] Would submit %d zarq + %d nerq URLs", len(zarq_urls), len(nerq_urls))
        logger.info("[DRY RUN] Sample zarq: %s", zarq_urls[:3])
        logger.info("[DRY RUN] Sample nerq: %s", nerq_urls[:3])
        # Still do Google Ping in dry-run (count only)
        all_sitemaps = _discover_sitemaps("nerq.ai") + _discover_sitemaps("zarq.ai")
        logger.info("[DRY RUN] Would ping Google for %d sitemaps", len(all_sitemaps))
        return 0

    total_success = 0
    total_fail = 0

    # Submit zarq.ai
    if zarq_urls:
        logger.info("Submitting %d zarq.ai URLs...", len(zarq_urls))
        s, f = submit_to_indexnow("zarq.ai", zarq_urls, "https://zarq.ai/zarq2026indexnow.txt")
        total_success += s
        total_fail += f
        _record_submitted([u for u in zarq_urls[:s]])  # only record successful

    # Submit nerq.ai
    if nerq_urls:
        logger.info("Submitting %d nerq.ai URLs...", len(nerq_urls))
        s, f = submit_to_indexnow("nerq.ai", nerq_urls, "https://nerq.ai/nerq2026indexnow.txt")
        total_success += s
        total_fail += f
        _record_submitted([u for u in nerq_urls[:s]])

    # Save state
    new_state["last_run"] = now.isoformat()
    new_state["last_zarq_count"] = len(zarq_urls)
    new_state["last_nerq_count"] = len(nerq_urls)
    save_state(new_state)

    elapsed_indexnow = time.time() - t0
    logger.info("-" * 60)
    logger.info("INDEXNOW COMPLETE")
    logger.info("  URLs submitted:    %d (zarq=%d, nerq=%d)", len(zarq_urls) + len(nerq_urls), len(zarq_urls), len(nerq_urls))
    logger.info("  Success:           %d", total_success)
    logger.info("  Failed:            %d", total_fail)
    logger.info("  Elapsed:           %.1fs", elapsed_indexnow)

    # NOTE: Google deprecated /ping endpoint (returns 404 since 2023).
    # Google discovers sitemaps via robots.txt Sitemap: directives instead.
    # Bing/Yandex discovery happens via IndexNow (above).

    elapsed_total = time.time() - t0
    logger.info("TOTAL ELAPSED: %.1fs (IndexNow: %.1fs, Google: %.1fs)",
                elapsed_total, elapsed_indexnow, elapsed_total - elapsed_indexnow)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    if "--smedjan-batch-only" in sys.argv:
        # T152: report what the Smedjan batch source would queue, no submit.
        batch = collect_smedjan_batch_urls()
        total = sum(len(v) for v in batch.values())
        logger.info("Smedjan batch trigger preview: %d total URLs", total)
        for host, urls in batch.items():
            logger.info("  %s: %d URLs (sample: %s)", host, len(urls), urls[:3])
        sys.exit(0)
    _dry = "--dry-run" in sys.argv
    _max = 0
    for _a in sys.argv:
        if _a.startswith("--max-urls="):
            _max = int(_a.split("=")[1])
    sys.exit(main(dry_run=_dry, max_urls=_max))
