"""
Lazy compare fallback middleware.

Intercepts 404 responses for ``/compare/<a>-vs-<b>`` and either:

1. Lazy-renders the pair if both entities exist in ``entity_lookup`` (exact or
   cleaned match — no broad LIKE fallback, which previously produced noise).
2. 301-redirects to the single-entity safety page if only one side exists.
3. Returns a 200 "Not Yet Analyzed" placeholder otherwise, preserving crawl
   budget.

Source: AUDIT-QUERY-20260418 finding #2 (22.3% 404 rate on /compare/<pair>).
See follow-up task ``FU-QUERY-20260418-02``.
"""

from __future__ import annotations

import html as _html
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger("nerq.compare_fallback")


def _split_pair(path: str) -> tuple[str, str] | None:
    if not path.startswith("/compare/"):
        return None
    slug = path[len("/compare/"):]
    if "/" in slug or "-vs-" not in slug:
        return None
    a, b = slug.split("-vs-", 1)
    if not a or not b:
        return None
    return a, b


def _lookup_exact(name: str) -> dict | None:
    """entity_lookup match by exact name_lower, dash-cleaned, or GitHub-style
    owner/repo suffix. Skips the broad ``%name%`` LIKE fallback used elsewhere
    so we don't silently 200-render unrelated entities."""
    try:
        from agentindex.db.models import get_session
        from sqlalchemy.sql import text
    except Exception:
        return None

    session = get_session()
    try:
        clean = name.replace("-", " ").replace("_", " ")
        row = session.execute(text("""
            SELECT name,
                   COALESCE(trust_score_v2, trust_score) AS trust_score,
                   trust_grade, category, source, source_url,
                   stars, author, is_verified, compliance_score,
                   eu_risk_class, documentation_score, activity_score,
                   security_score, popularity_score, description
            FROM (
                SELECT name, trust_score, trust_score_v2, trust_grade,
                       category, source, source_url, stars, author, is_verified,
                       compliance_score, eu_risk_class, documentation_score,
                       activity_score, security_score, popularity_score,
                       description, 1 AS _rank
                FROM entity_lookup
                WHERE is_active = true AND name_lower = lower(:name)
              UNION ALL
                SELECT name, trust_score, trust_score_v2, trust_grade,
                       category, source, source_url, stars, author, is_verified,
                       compliance_score, eu_risk_class, documentation_score,
                       activity_score, security_score, popularity_score,
                       description, 2 AS _rank
                FROM entity_lookup
                WHERE is_active = true AND name_lower = lower(:clean)
                  AND :clean <> :name
              UNION ALL
                SELECT name, trust_score, trust_score_v2, trust_grade,
                       category, source, source_url, stars, author, is_verified,
                       compliance_score, eu_risk_class, documentation_score,
                       activity_score, security_score, popularity_score,
                       description, 3 AS _rank
                FROM entity_lookup
                WHERE is_active = true AND name_lower LIKE lower(:suffix)
            ) sub
            ORDER BY _rank,
                     COALESCE(trust_score_v2, trust_score) DESC NULLS LAST,
                     stars DESC NULLS LAST
            LIMIT 1
        """), {
            "name": name,
            "clean": clean,
            "suffix": f"%/{name}",
        }).fetchone()
        return dict(row._mapping) if row else None
    except Exception as e:
        logger.warning("entity_lookup query failed for %r: %s", name, e)
        return None
    finally:
        session.close()


def _safety_path(slug: str) -> str:
    slug = slug.strip("/ ")
    return f"/is-{slug}-safe"


def _not_yet_analyzed(a: str, b: str) -> HTMLResponse:
    # Hard 404 — soft-200-with-noindex was being treated as soft-404 spam
    # under HCU. The previous "preserve crawl budget" rationale lost out
    # to the algorithmic-action risk (FAS 4 / DEL A8, 2026-04-30).
    return HTMLResponse(
        "<h1>Not Found</h1><p>One or both entities are not in our index.</p>",
        status_code=404,
    )


def _queue_miss(slug_a: str, slug_b: str, reason: str) -> None:
    try:
        from agentindex.agent_safety_pages import _queue_for_crawling
        _queue_for_crawling(slug_a, bot=f"compare-lazy-{reason}")
        _queue_for_crawling(slug_b, bot=f"compare-lazy-{reason}")
    except Exception:
        pass


def _render_pair(slug: str, slug_a: str, slug_b: str) -> HTMLResponse | None:
    try:
        from agentindex.agent_compare_pages import _render_compare_page
    except Exception:
        return None
    pair_info = {
        "slug": slug,
        "agent_a": slug_a,
        "agent_b": slug_b,
        "category": "",
    }
    try:
        rendered = _render_compare_page(slug, pair_info)
    except Exception as e:
        logger.warning("lazy _render_compare_page(%s) failed: %s", slug, e)
        return None
    if not rendered:
        return None
    return HTMLResponse(content=rendered, status_code=200)


def _resolve(path: str) -> Response | None:
    parsed = _split_pair(path)
    if not parsed:
        return None
    slug_a, slug_b = parsed
    slug = f"{slug_a}-vs-{slug_b}"

    a = _lookup_exact(slug_a)
    b = _lookup_exact(slug_b)

    if a and b:
        rendered = _render_pair(slug, slug_a, slug_b)
        if rendered is not None:
            return rendered
        # Rare: lookup found both but the full renderer couldn't build a page.
        # Fall through to placeholder rather than leaking a 404.
        _queue_miss(slug_a, slug_b, "render-fail")
        return _not_yet_analyzed(slug_a, slug_b)

    if a and not b:
        return RedirectResponse(url=_safety_path(slug_a), status_code=301)
    if b and not a:
        return RedirectResponse(url=_safety_path(slug_b), status_code=301)

    _queue_miss(slug_a, slug_b, "both-missing")
    return _not_yet_analyzed(slug_a, slug_b)


class CompareFallbackMiddleware(BaseHTTPMiddleware):
    """Rescue 404s on /compare/<a>-vs-<b> via lazy entity_lookup rendering."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if response.status_code != 404:
            return response
        path = request.url.path
        if not path.startswith("/compare/") or "-vs-" not in path:
            return response

        # Drain the inner 404 body so the underlying stream is fully consumed
        # before we replace it.
        if hasattr(response, "body_iterator"):
            try:
                async for _ in response.body_iterator:
                    pass
            except Exception:
                pass

        fallback = _resolve(path)
        if fallback is None:
            return response
        return fallback


def install_compare_fallback(app) -> None:
    """Register the middleware on the FastAPI/Starlette app."""
    app.add_middleware(CompareFallbackMiddleware)
    logger.info("CompareFallbackMiddleware installed")
