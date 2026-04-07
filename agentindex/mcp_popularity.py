"""
MCP Popularity Metrics
======================
Computes a composite popularity ranking for MCP servers based on:
  1. Page views from analytics.db (if available)
  2. Trust score from the agents table
  3. GitHub stars from the agents table

Usage:
    from agentindex.mcp_popularity import get_mcp_popularity
    rankings = get_mcp_popularity()
    # => {"harbor": 1, "n8n-ion8n": 2, ...}
"""

import logging
import os
import sqlite3
from collections import defaultdict

from sqlalchemy.sql import text
from agentindex.db.models import get_session

logger = logging.getLogger("nerq.mcp_popularity")

ANALYTICS_DB = os.path.join(os.path.dirname(__file__), '..', 'logs', 'analytics.db')

# Weights for the composite score
W_PAGE_VIEWS = 0.30
W_TRUST_SCORE = 0.40
W_STARS = 0.30


def _make_slug(name):
    """Mirror the slug logic from mcp_trust_pages."""
    slug = name.lower().strip()
    for ch in ['/', '\\', '(', ')', '[', ']', '{', '}', ':', ';', ',', '!', '?',
               '@', '#', '$', '%', '^', '&', '*', '=', '+', '|', '<', '>', '~', '`', "'", '"']:
        slug = slug.replace(ch, '')
    slug = slug.replace(' ', '-').replace('_', '-').replace('.', '-')
    while '--' in slug:
        slug = slug.replace('--', '-')
    return slug.strip('-')


def _get_page_views():
    """Get page view counts from analytics.db for /mcp/* pages."""
    views = {}
    if not os.path.exists(ANALYTICS_DB):
        return views
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        rows = conn.execute(
            "SELECT path, COUNT(*) as cnt FROM requests "
            "WHERE path LIKE '/mcp/%' "
            "AND path NOT IN ('/mcp/sse', '/mcp/messages', '/mcp/message', '/mcp') "
            "GROUP BY path ORDER BY cnt DESC"
        ).fetchall()
        conn.close()
        for path, cnt in rows:
            slug = path.replace('/mcp/', '', 1)
            if slug:
                views[slug] = cnt
    except Exception as e:
        logger.warning(f"Failed to read analytics for MCP popularity: {e}")
    return views


def _get_agent_data():
    """Get trust_score and stars for all active MCP servers."""
    agents = {}
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name,
                   COALESCE(trust_score_v2, trust_score) as trust_score,
                   stars
            FROM entity_lookup
            WHERE is_active = true AND agent_type = 'mcp_server'
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
        """)).fetchall()
        for r in rows:
            row = dict(r._mapping)
            name = row.get("name") or ""
            slug = _make_slug(name)
            if slug:
                agents[slug] = {
                    "name": name,
                    "trust_score": float(row.get("trust_score") or 0),
                    "stars": int(row.get("stars") or 0),
                }
    except Exception as e:
        logger.error(f"Failed to get agent data for MCP popularity: {e}")
    finally:
        session.close()
    return agents


def _normalize(values):
    """Min-max normalize a list of values to [0, 1]."""
    if not values:
        return []
    mn = min(values)
    mx = max(values)
    rng = mx - mn
    if rng == 0:
        return [0.5] * len(values)
    return [(v - mn) / rng for v in values]


def get_mcp_popularity():
    """
    Compute popularity rankings for MCP servers.

    Returns:
        dict: {slug: rank} where rank 1 = most popular.
              Also includes a second dict with metadata:
              {slug: {"rank": int, "total": int, "composite_score": float}}
    """
    page_views = _get_page_views()
    agent_data = _get_agent_data()

    # Merge all known slugs
    all_slugs = set(agent_data.keys()) | set(page_views.keys())
    if not all_slugs:
        return {}, {}

    # Build raw score lists per slug
    raw = {}
    for slug in all_slugs:
        pv = page_views.get(slug, 0)
        ad = agent_data.get(slug, {})
        raw[slug] = {
            "page_views": pv,
            "trust_score": ad.get("trust_score", 0),
            "stars": ad.get("stars", 0),
        }

    slugs = sorted(raw.keys())
    pv_vals = [raw[s]["page_views"] for s in slugs]
    ts_vals = [raw[s]["trust_score"] for s in slugs]
    st_vals = [raw[s]["stars"] for s in slugs]

    pv_norm = _normalize(pv_vals)
    ts_norm = _normalize(ts_vals)
    st_norm = _normalize(st_vals)

    # Compute composite score
    composite = {}
    for i, slug in enumerate(slugs):
        composite[slug] = (
            W_PAGE_VIEWS * pv_norm[i] +
            W_TRUST_SCORE * ts_norm[i] +
            W_STARS * st_norm[i]
        )

    # Sort by composite descending
    ranked = sorted(composite.items(), key=lambda x: x[1], reverse=True)

    total = len(ranked)
    rank_map = {}
    detail_map = {}
    for rank_idx, (slug, score) in enumerate(ranked, 1):
        rank_map[slug] = rank_idx
        detail_map[slug] = {
            "rank": rank_idx,
            "total": total,
            "composite_score": round(score, 4),
        }

    return rank_map, detail_map


# Cached result (TTL-based)
_cache = {"ranks": None, "details": None, "ts": 0}
_CACHE_TTL = 1800  # 30 minutes


def get_mcp_popularity_cached():
    """Cached version of get_mcp_popularity. Refreshes every 30 minutes."""
    import time
    now = time.time()
    if _cache["ranks"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["ranks"], _cache["details"]

    ranks, details = get_mcp_popularity()
    _cache["ranks"] = ranks
    _cache["details"] = details
    _cache["ts"] = now
    return ranks, details
