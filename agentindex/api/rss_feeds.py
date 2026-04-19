"""
Per-registry RSS feeds — nerq.ai
Route: GET /feed/{registry}.xml

One RSS 2.0 feed per software registry (npm, pypi, wordpress, …).
Surfaces the 50 most-recently enriched entities so AI bots can use
lastmod / pubDate as a re-crawl signal.
"""
from datetime import datetime, timezone
from email.utils import format_datetime
from threading import Lock

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import text

from agentindex.db.models import get_session

router_rss_feeds = APIRouter(tags=["feed"])

_REGISTRY_CACHE: set[str] = set()
_REGISTRY_CACHE_TS: float = 0.0
_REGISTRY_CACHE_TTL = 3600.0
_REGISTRY_CACHE_LOCK = Lock()


def _escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _known_registries() -> set[str]:
    """Return the set of registries present in software_registry, cached 1h."""
    global _REGISTRY_CACHE, _REGISTRY_CACHE_TS
    import time
    now = time.time()
    with _REGISTRY_CACHE_LOCK:
        if _REGISTRY_CACHE and (now - _REGISTRY_CACHE_TS) < _REGISTRY_CACHE_TTL:
            return _REGISTRY_CACHE
        session = get_session()
        try:
            session.execute(text("SET LOCAL statement_timeout = '3s'"))
            rows = session.execute(text(
                "SELECT DISTINCT registry FROM software_registry WHERE registry IS NOT NULL"
            )).fetchall()
        finally:
            session.close()
        _REGISTRY_CACHE = {r[0] for r in rows if r[0]}
        _REGISTRY_CACHE_TS = now
        return _REGISTRY_CACHE


@router_rss_feeds.get("/feed/{registry}.xml")
def registry_feed(registry: str):
    """RSS 2.0 feed of the 50 most-recently enriched entities in a registry."""
    registry = registry.lower().strip()
    if registry not in _known_registries():
        raise HTTPException(status_code=404, detail=f"Unknown registry: {registry}")

    session = get_session()
    try:
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        rows = session.execute(text("""
            SELECT name, slug, description, trust_score, trust_grade,
                   enriched_at, updated_at, last_updated
            FROM software_registry
            WHERE registry = :reg
              AND enriched_at IS NOT NULL
            ORDER BY enriched_at DESC
            LIMIT 50
        """), {"reg": registry}).fetchall()
    finally:
        session.close()

    now_dt = datetime.now(timezone.utc)
    now_str = format_datetime(now_dt)

    items_xml = ""
    latest_pub = None
    for r in rows:
        name, slug, desc, score, grade, enriched_at, updated_at, last_updated = r
        pub_dt = enriched_at or updated_at or last_updated or now_dt
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        if latest_pub is None or pub_dt > latest_pub:
            latest_pub = pub_dt

        link = f"https://nerq.ai/safe/{slug}"
        title = name or slug
        if score is not None and grade:
            title = f"{title} — Trust {score:.0f} ({grade})"
        description = (desc or "")[:300]

        items_xml += (
            "    <item>\n"
            f"      <title>{_escape_xml(title)}</title>\n"
            f"      <link>{_escape_xml(link)}</link>\n"
            f"      <description>{_escape_xml(description)}</description>\n"
            f"      <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
            f"      <guid isPermaLink=\"true\">{_escape_xml(link)}</guid>\n"
            "    </item>\n"
        )

    last_build = format_datetime(latest_pub) if latest_pub else now_str
    channel_title = f"Nerq — {registry} (recently enriched)"
    channel_link = f"https://nerq.ai/feed/{registry}.xml"
    channel_desc = (
        f"The 50 most-recently enriched {registry} entities on Nerq, "
        "with trust scores and safety analysis."
    )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        '  <channel>\n'
        f'    <title>{_escape_xml(channel_title)}</title>\n'
        f'    <link>{_escape_xml(channel_link)}</link>\n'
        f'    <description>{_escape_xml(channel_desc)}</description>\n'
        '    <language>en</language>\n'
        f'    <lastBuildDate>{last_build}</lastBuildDate>\n'
        f'    <pubDate>{last_build}</pubDate>\n'
        f'{items_xml}'
        '  </channel>\n'
        '</rss>\n'
    )

    return Response(content=xml, media_type="application/rss+xml")
