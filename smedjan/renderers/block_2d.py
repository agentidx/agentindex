"""
L2 Block 2d — signal events feed renderer.

Source: `public.signal_events` on the Nerq read-only replica
(~24.6K rows / ~10.2K distinct entities, last 30 days as of 2026-04-19).
NOT mirrored into analytics_mirror, so Nerq RO is the only read path.

Initial render scope: top 500 entities by `ai_demand_score`. The set
is loaded once on first call from `smedjan.ai_demand_scores` and
cached for the life of the process.

Surface fields (the source table does not store old/new trust as
columns — only a textual `description` like "Trust score changed by
+21.8 points", from which the delta is parsed):

    event_ts        date           ← signal_events.date
    event_kind      text           ← signal_events.signal_type
    registry        text           ← signal_events.registry
    severity        text           ← signal_events.severity
    delta_pts       float | None   ← parsed from description (signed)
    description     text           ← raw description, displayed verbatim

Up to `_MAX_EVENTS_PER_SLUG` most recent events are surfaced per page.

Design notes
------------
* Fail-closed. Any `SourceUnavailable` or unexpected error returns
  `None` so the caller renders nothing — the agent safety page must
  never crash because of a Block 2d query.
* Reads only from Nerq RO and the Smedjan DB (for the top-500 set);
  no writes anywhere.
* No shadow/live wrapping here; the caller decides based on the
  `L2_BLOCK_2D_MODE` env var. This module always returns the raw block
  HTML (or `None` when there is nothing to render).
* No sacred tokens (`pplx-verdict`, `ai-summary`,
  `SpeakableSpecification`, `FAQPage`) appear in the output — safe to
  splice below king-sections and above FAQ.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Optional

from smedjan import sources

log = logging.getLogger("smedjan.renderers.block_2d")

_TOP_N = 500
_MAX_EVENTS_PER_SLUG = 10
_DELTA_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*points")

_top_slugs: Optional[frozenset[str]] = None
_top_slugs_loaded = False


def _load_top_slugs() -> Optional[frozenset[str]]:
    """Return the top-`_TOP_N` slug set, cached. `None` if the smedjan DB
    is unreachable — callers fail closed."""
    global _top_slugs, _top_slugs_loaded
    if _top_slugs_loaded:
        return _top_slugs
    try:
        with sources.smedjan_db_cursor() as (_, cur):
            cur.execute(
                "SELECT slug FROM smedjan.ai_demand_scores "
                "ORDER BY score DESC NULLS LAST LIMIT %s",
                (_TOP_N,),
            )
            _top_slugs = frozenset(r[0] for r in cur.fetchall())
    except sources.SourceUnavailable as exc:
        log.warning("block_2d: smedjan db unavailable for top-%d set: %s", _TOP_N, exc)
        _top_slugs = None
    except Exception as exc:  # last-ditch fail-closed
        log.warning("block_2d: top-%d query failed: %s", _TOP_N, exc)
        _top_slugs = None
    _top_slugs_loaded = True
    return _top_slugs


def _parse_delta(description: Optional[str]) -> Optional[float]:
    if not description:
        return None
    m = _DELTA_RE.search(description)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def _fetch_events(slug: str) -> Optional[list[dict]]:
    """Return up to `_MAX_EVENTS_PER_SLUG` most-recent events for `slug`,
    or `None` on data-source failure / empty result."""
    try:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT date, signal_type, severity, registry, description "
                "FROM public.signal_events "
                "WHERE entity_id = %s "
                "ORDER BY date DESC, id DESC LIMIT %s",
                (slug, _MAX_EVENTS_PER_SLUG),
            )
            rows = cur.fetchall()
    except sources.SourceUnavailable as exc:
        log.warning("block_2d: nerq_ro unavailable for %s: %s", slug, exc)
        return None
    except Exception as exc:  # last-ditch fail-closed
        log.warning("block_2d: query failed for %s: %s", slug, exc)
        return None
    if not rows:
        return None
    out = []
    for date, kind, severity, registry, description in rows:
        out.append({
            "event_ts": date,
            "event_kind": kind,
            "severity": severity,
            "registry": registry,
            "description": description,
            "delta_pts": _parse_delta(description),
        })
    return out


def _fmt_kind(kind: Optional[str]) -> str:
    if not kind:
        return "event"
    return kind.replace("_", " ")


def _fmt_delta(delta: Optional[float]) -> str:
    if delta is None:
        return ""
    sign = "+" if delta >= 0 else "−"
    return f" ({sign}{abs(delta):.1f} pts)"


def render_block_2d_html(slug: str) -> Optional[str]:
    """Return the Block 2d HTML snippet for `slug`, or `None` if the slug
    is out of the top-`_TOP_N` scope or has no signal events.

    The output is a single `<div class="section block-2d">…</div>` with
    no sacred tokens — callers may insert it between the king-sections
    area and the FAQ section without mutating any SEO/GEO-critical
    markup.
    """
    top = _load_top_slugs()
    if top is None or slug not in top:
        return None

    events = _fetch_events(slug)
    if not events:
        return None

    s_slug = html.escape(slug)
    items = []
    for ev in events:
        ts = ev["event_ts"].isoformat() if ev["event_ts"] is not None else ""
        kind = html.escape(_fmt_kind(ev["event_kind"]))
        registry = html.escape(ev["registry"] or "—")
        severity = html.escape(ev["severity"] or "")
        desc = html.escape(ev["description"] or "")
        delta = _fmt_delta(ev["delta_pts"])
        items.append(
            "<li>"
            f'<time datetime="{html.escape(ts)}">{html.escape(ts)}</time> · '
            f'<strong>{kind}</strong>{html.escape(delta)} · '
            f'registry <code>{registry}</code> · severity {severity}'
            f'<br><span style="color:#64748b">{desc}</span>'
            "</li>"
        )

    return (
        f'<div class="section block-2d" data-block="2d" data-slug="{s_slug}">'
        '<h2 class="section-title">Signal Events</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        "Recent trust-score changes and other signal events from the "
        "Nerq pipeline. Shadow data, read-only."
        "</p>"
        '<ul style="font-size:14px;line-height:1.6;color:#374151;margin:0;padding-left:20px">'
        + "".join(items) +
        "</ul>"
        "</div>"
    )
