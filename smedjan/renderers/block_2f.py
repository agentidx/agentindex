"""
L5 Block 2f — cross-registry internal-linking renderer (T305).

Source: ``public.software_registry`` on the Nerq read-only replica.
For a given (slug, current_registry) pair, returns same-slug entries in
OTHER registries (e.g. the ``react`` npm page links the ``react`` nuget
and rubygems pages). An April 2026 analysis identified 3,748 name-matches
across registries.

Surface fields (per sibling)

    slug            text          ← software_registry.slug (opaque)
    registry        text          ← software_registry.registry
    trust_score     float | None  ← used only for ordering (desc)

Up to ``_MAX_SIBLINGS_PER_SLUG`` links surface per page.

Design notes
------------
* Fail-closed. Any ``SourceUnavailable`` or unexpected error returns
  ``None``; the caller renders nothing so the /safe/ page never crashes
  because of a Block 2f query.
* Read-only. Uses the same ``get_session()`` read path that the existing
  ``_get_cross_registry_links`` helper in ``agent_safety_pages.py`` uses,
  so the access pattern is already proven under the production pool.
* No shadow/live wrapping here; the caller decides based on the
  ``L5_CROSS_REGISTRY_MODE`` env var. This module always returns the raw
  block HTML (or ``None`` when there are no siblings).
* No sacred tokens (``pplx-verdict``, ``ai-summary``,
  ``SpeakableSpecification``, ``FAQPage``) appear in the output — safe to
  splice between the FAQ section and the similar-entities section.
* Anchors are internal only: ``/safe/{sibling_slug}?registry={sibling_registry}``
  per the T305 acceptance criteria.
"""
from __future__ import annotations

import html
import logging
from typing import Optional

log = logging.getLogger("smedjan.renderers.block_2f")

_MAX_SIBLINGS_PER_SLUG = 10

_REGISTRY_DISPLAY = {
    "npm": "npm",
    "pypi": "PyPI",
    "crates": "crates.io",
    "nuget": "NuGet",
    "gems": "RubyGems",
    "rubygems": "RubyGems",
    "go": "Go modules",
    "packagist": "Packagist",
    "homebrew": "Homebrew",
    "chrome": "Chrome Web Store",
    "firefox": "Firefox Add-ons",
    "vscode": "VS Code Marketplace",
    "wordpress": "WordPress",
    "ios": "App Store",
    "android": "Google Play",
    "steam": "Steam",
}


def _registry_label(registry: Optional[str]) -> str:
    if not registry:
        return "other registry"
    return _REGISTRY_DISPLAY.get(
        registry,
        registry.replace("_", " ").title(),
    )


def _fetch_siblings(slug: str, current_registry: str) -> Optional[list[dict]]:
    """Return up to ``_MAX_SIBLINGS_PER_SLUG`` same-slug entries from other
    registries, ordered by trust_score desc. ``None`` on data-source
    failure or empty result."""
    try:
        from agentindex.db.models import get_session
        from sqlalchemy.sql import text
    except Exception as exc:
        log.warning("block_2f: db/sqlalchemy import failed: %s", exc)
        return None

    session = get_session()
    try:
        rows = session.execute(
            text(
                "SELECT slug, registry, trust_score "
                "FROM software_registry "
                "WHERE slug = :slug AND registry != :reg "
                "  AND trust_score IS NOT NULL AND trust_score > 0 "
                "ORDER BY trust_score DESC "
                "LIMIT :lim"
            ),
            {"slug": slug, "reg": current_registry or "", "lim": _MAX_SIBLINGS_PER_SLUG},
        ).fetchall()
    except Exception as exc:
        log.warning("block_2f: query failed for %s: %s", slug, exc)
        return None
    finally:
        session.close()

    if not rows:
        return None
    return [dict(r._mapping) for r in rows]


def render_block_2f_html(slug: str, current_registry: str) -> Optional[str]:
    """Return the Block 2f HTML snippet for ``slug``, or ``None`` when there
    is no cross-registry sibling to surface.

    The output is a single ``<section class="section block-2f">…</section>``
    with no sacred tokens. Callers may insert it between the FAQ section
    and the similar-entities section without mutating any SEO/GEO-critical
    markup.
    """
    if not slug:
        return None

    siblings = _fetch_siblings(slug, current_registry or "")
    if not siblings:
        return None

    s_slug = html.escape(slug)
    items = []
    for sib in siblings:
        sib_slug = sib.get("slug") or ""
        sib_reg = sib.get("registry") or ""
        if not sib_slug or not sib_reg:
            continue
        label = _registry_label(sib_reg)
        score = sib.get("trust_score")
        score_str = f"{score:.0f}" if isinstance(score, (int, float)) else "—"
        href = f"/safe/{html.escape(sib_slug)}?registry={html.escape(sib_reg)}"
        items.append(
            "<li>"
            f'<a href="{href}">{html.escape(label)}</a>'
            f' &middot; <span style="color:#64748b">Trust {html.escape(score_str)}/100</span>'
            "</li>"
        )

    if not items:
        return None

    return (
        f'<section class="section block-2f" data-block="2f" data-slug="{s_slug}">'
        '<h2 class="section-title">Related in other registries</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        "The same name appears in other registries. Each entry is a distinct "
        "package with its own Trust Score — open the one you depend on."
        "</p>"
        '<ul style="font-size:15px;line-height:1.7;color:#374151;margin:0;padding-left:20px">'
        + "".join(items) +
        "</ul>"
        "</section>"
    )
