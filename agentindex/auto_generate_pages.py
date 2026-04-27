#!/usr/bin/env python3
"""
Auto-Generate Pages (B1)
=========================
Runs daily at 07:15 via LaunchAgent com.nerq.auto-pages.
Ensures slug files are in sync with what's routable:
- Checks for new tokens in DB not yet in token_slugs.json
- Checks Postgres for agents with trust >= 50 not yet in agent_safety_slugs.json
- Checks Postgres for MCP servers not yet in mcp_server_slugs.json
- Regenerates sitemaps if anything changed (via IndexNow trigger)

Exit 0 on success.
"""

import json
import logging
import os
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LOG_PATH = "/tmp/auto-pages.log"
SCRIPT_DIR = Path(__file__).parent

# Slug files
TOKEN_SLUGS_PATH = SCRIPT_DIR / "crypto" / "token_slugs.json"
AGENT_SLUGS_PATH = SCRIPT_DIR / "agent_safety_slugs.json"
MCP_SLUGS_PATH = SCRIPT_DIR / "mcp_server_slugs.json"

# Databases
RISK_DB = str(SCRIPT_DIR / "crypto" / "crypto_trust.db")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("auto-pages")


# Slug-validation gate. Audit AUDIT-QUERY-20260427 finding 10 traced 833
# distinct /is-badge/<slug>-safe 404s to slugs containing whitespace, capitals,
# dots, leading/trailing hyphens, non-ASCII, and bare numeric IDs leaking from
# entity_lookup.slug and from the name-derived slugifier below. Anything
# written to a *_slugs.json from this script must clear _is_valid_slug.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
_NUMERIC_ONLY_RE = re.compile(r"^[0-9-]+$")


def _is_valid_slug(slug) -> bool:
    if not isinstance(slug, str) or len(slug) < 2:
        return False
    if not _SLUG_RE.match(slug):
        return False
    if _NUMERIC_ONLY_RE.match(slug):
        return False
    return True


def _slugify(name) -> str:
    """Best-effort canonicalisation: NFKD-strip accents, lowercase, collapse
    any non-[a-z0-9] run into a single hyphen, trim hyphens. Returns "" if
    nothing usable remains — callers must re-check with _is_valid_slug.
    """
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _gated_slug(raw_slug, name) -> str:
    """Return a slug that passes _is_valid_slug, or "" if neither the raw slug
    nor a name-derived fallback is salvageable. Callers must drop entries that
    receive ""."""
    if _is_valid_slug(raw_slug):
        return raw_slug
    fallback = _slugify(raw_slug if isinstance(raw_slug, str) and raw_slug else name)
    if _is_valid_slug(fallback):
        return fallback
    fallback = _slugify(name)
    return fallback if _is_valid_slug(fallback) else ""


def grade_from_score(score):
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 40: return "D"
    return "F"


def sync_token_slugs() -> int:
    """Check NDD daily for tokens not in token_slugs.json."""
    if not TOKEN_SLUGS_PATH.exists():
        logger.warning("token_slugs.json not found")
        return 0

    with open(TOKEN_SLUGS_PATH) as f:
        slugs = json.load(f)

    existing = set(slugs.keys())

    conn = sqlite3.connect(RISK_DB)
    rows = conn.execute("""
        SELECT DISTINCT token_id, symbol, name, trust_grade, market_cap_rank
        FROM crypto_ndd_daily
        WHERE (token_id, run_date) IN (
            SELECT token_id, MAX(run_date) FROM crypto_ndd_daily GROUP BY token_id
        )
    """).fetchall()
    conn.close()

    added = 0
    for r in rows:
        token_id, symbol, name, grade, rank = r
        if token_id and token_id not in existing:
            tier = "T1" if rank and rank <= 200 else "T2" if rank and rank <= 1000 else "T3"
            slugs[token_id] = {
                "symbol": symbol,
                "name": name,
                "tier": tier,
                "risk_grade": grade or "NR",
            }
            added += 1

    if added > 0:
        with open(TOKEN_SLUGS_PATH, "w") as f:
            json.dump(slugs, f, indent=2)

    return added


def sync_agent_slugs() -> int:
    """Check Postgres for agents with COALESCE(trust_score_v2, trust_score) >= 50
    not yet in agent_safety_slugs.json.

    Uses entity_lookup.slug directly (rather than deriving from name) so the
    JSON keys match the canonical slug format that /safe/<slug> and the
    sitemap emitter both expect. Filters on the v2-preferring coalesce because
    trust_score (v1) is NULL on most top-trust_score_v2 rows. Allowlist keeps
    agent/tool/mcp_server plus NULL agent_type so the top-v2 inventory of
    github-source pages is no longer excluded.
    """
    if not AGENT_SLUGS_PATH.exists():
        logger.warning("agent_safety_slugs.json not found")
        return 0

    with open(AGENT_SLUGS_PATH) as f:
        slug_list = json.load(f)

    existing = {a["slug"] for a in slug_list}

    try:
        import psycopg2
        from agentindex.db_config import get_read_dsn
        db_url = os.getenv("DATABASE_URL") or get_read_dsn()
        conn = psycopg2.connect(db_url)
        conn.set_session(readonly=True)
        cur = conn.cursor()

        cur.execute("""
            SELECT slug, name, source_url, category, source,
                   COALESCE(trust_score_v2, trust_score) AS trust_display, stars,
                   activity_score, security_score, popularity_score, documentation_score,
                   is_verified
            FROM entity_lookup
            WHERE is_active = true
              AND slug IS NOT NULL
              AND COALESCE(trust_score_v2, trust_score) >= 50
              AND (agent_type IN ('agent', 'tool', 'mcp_server') OR agent_type IS NULL)
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
        """)

        added = 0
        rejected = 0
        for row in cur.fetchall():
            slug, name, source_url, category, source, trust_display, stars, \
                activity, security, popularity, documentation, is_verified = row

            gated = _gated_slug(slug, name)
            if not gated:
                rejected += 1
                continue
            if gated in existing:
                continue
            entry = {
                "slug": gated,
                "name": name,
                "category": category or "general",
                "source": source or "github",
                "trust_score": round(trust_display, 1) if trust_display else 0,
                "trust_grade": grade_from_score(trust_display) if trust_display else "NR",
                "is_verified": bool(is_verified and trust_display and trust_display >= 70),
                "stars": stars or 0,
            }
            slug_list.append(entry)
            existing.add(gated)
            added += 1

        cur.close()
        conn.close()

        if rejected:
            logger.info("Agent slug gate rejected %d invalid slugs", rejected)

        if added > 0:
            with open(AGENT_SLUGS_PATH, "w") as f:
                json.dump(slug_list, f, indent=2)

        return added

    except Exception as e:
        logger.warning("Postgres query failed for agents: %s", e)
        return 0


def sync_mcp_slugs() -> int:
    """Check Postgres for MCP servers not yet in mcp_server_slugs.json."""
    if not MCP_SLUGS_PATH.exists():
        logger.warning("mcp_server_slugs.json not found")
        return 0

    with open(MCP_SLUGS_PATH) as f:
        slug_list = json.load(f)

    existing = {m["slug"] for m in slug_list}

    try:
        import psycopg2
        from agentindex.db_config import get_read_dsn
        db_url = os.getenv("DATABASE_URL") or get_read_dsn()
        conn = psycopg2.connect(db_url)
        conn.set_session(readonly=True)
        cur = conn.cursor()

        cur.execute("""
            SELECT name, source_url, category, source, trust_score, stars,
                   is_verified
            FROM entity_lookup
            WHERE is_active = true
              AND trust_score >= 50
              AND agent_type = 'mcp_server'
            ORDER BY trust_score DESC
        """)

        added = 0
        rejected = 0
        for row in cur.fetchall():
            name, source_url, category, source, trust_score, stars, is_verified = row

            gated = _gated_slug(None, name)
            if not gated:
                rejected += 1
                continue
            if gated in existing:
                continue
            entry = {
                "slug": gated,
                "name": name,
                "trust_score": round(trust_score, 1) if trust_score else 0,
                "trust_grade": grade_from_score(trust_score) if trust_score else "NR",
                "category": category or "infrastructure",
                "source": source or "github",
                "stars": stars or 0,
                "is_verified": bool(is_verified and trust_score and trust_score >= 70),
            }
            slug_list.append(entry)
            existing.add(gated)
            added += 1

        cur.close()
        conn.close()

        if rejected:
            logger.info("MCP slug gate rejected %d invalid slugs", rejected)

        if added > 0:
            with open(MCP_SLUGS_PATH, "w") as f:
                json.dump(slug_list, f, indent=2)

        return added

    except Exception as e:
        logger.warning("Postgres query failed for MCP servers: %s", e)
        return 0


def clean_existing_slug_file(path: Path) -> int:
    """One-shot pass that strips entries failing _is_valid_slug from an existing
    *_slugs.json. Returns the number of entries removed. Tries to repair via
    _slugify(name) before dropping; deduplicates the result. Safe to run on
    every invocation — does nothing when the file is already clean."""
    if not path.exists():
        return 0
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("clean_existing_slug_file: cannot read %s: %s", path, e)
        return 0
    if not isinstance(data, list):
        return 0

    seen: set = set()
    cleaned: list = []
    removed = 0
    repaired = 0
    for entry in data:
        if not isinstance(entry, dict):
            removed += 1
            continue
        raw = entry.get("slug")
        if _is_valid_slug(raw):
            if raw in seen:
                removed += 1
                continue
            seen.add(raw)
            cleaned.append(entry)
            continue
        fixed = _gated_slug(raw, entry.get("name", ""))
        if fixed and fixed not in seen:
            entry["slug"] = fixed
            seen.add(fixed)
            cleaned.append(entry)
            repaired += 1
            continue
        removed += 1

    if removed or repaired:
        with open(path, "w") as f:
            json.dump(cleaned, f, indent=2)
        logger.info(
            "Slug cleanup %s: removed=%d repaired=%d kept=%d",
            path.name, removed, repaired, len(cleaned),
        )
    return removed + repaired


def main():
    t0 = time.time()
    now = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("Auto-Generate Pages started at %s", now.isoformat())

    # Strip any pre-existing invalid entries before sync runs add new ones.
    cleaned_agents = clean_existing_slug_file(AGENT_SLUGS_PATH)
    cleaned_mcp = clean_existing_slug_file(MCP_SLUGS_PATH)

    # Sync each slug file
    new_tokens = sync_token_slugs()
    logger.info("Token slugs: +%d new", new_tokens)

    new_agents = sync_agent_slugs()
    logger.info("Agent safety slugs: +%d new", new_agents)

    new_mcp = sync_mcp_slugs()
    logger.info("MCP server slugs: +%d new", new_mcp)

    total_new = new_tokens + new_agents + new_mcp + cleaned_agents + cleaned_mcp

    # If anything changed, the sitemaps auto-regenerate from slug files on next request.
    # The IndexNow system at 07:00 (or next day) will pick up changes.
    if total_new > 0:
        logger.info("Changes detected — sitemaps will regenerate on next request")
        # Force reload of slug caches by touching the files
        for p in [TOKEN_SLUGS_PATH, AGENT_SLUGS_PATH, MCP_SLUGS_PATH]:
            if p.exists():
                p.touch()

    elapsed = time.time() - t0
    logger.info("-" * 60)
    logger.info("AUTO-GENERATE PAGES COMPLETE")
    logger.info("  New token pages:   %d", new_tokens)
    logger.info("  New agent pages:   %d", new_agents)
    logger.info("  New MCP pages:     %d", new_mcp)
    logger.info("  Total new:         %d", total_new)
    logger.info("  Elapsed:           %.1fs", elapsed)
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
