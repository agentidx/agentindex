"""
L2 Block 2a — external trust signals renderer.

Source: `zarq.external_trust_signals` on the Nerq read-only replica
(~22.5K rows / ~7.7K distinct agents as of 2026-04-19; NOT present in
analytics_mirror, so Nerq RO is the only read path).

Surface fields (all derived — the source table stores (source, signal)
tuples, not per-agent booleans):

    has_osv_signal           any row with source = 'osv_dev'
    has_openssf_score        any row with source = 'openssf_scorecard'
    reddit_mentions          signal_value where source = 'reddit' and
                             signal_name = 'reddit_mentions_30d'
    stackoverflow_mentions   signal_value where source = 'stackoverflow'
                             and signal_name = 'stackoverflow_questions'
    total_signal_sources     COUNT(DISTINCT source) for the agent

Design notes
------------
* Fail-closed. Any `SourceUnavailable` or unexpected error returns
  `None` so the caller renders nothing — the agent safety page must
  never crash because of a Block 2a query.
* No writes. Uses `sources.nerq_readonly_cursor()` exclusively.
* No shadow/live wrapping here; the caller decides based on the
  `L2_BLOCK_2A_MODE` env var. This module always returns the raw block
  HTML (or `None` when there is nothing to render).
"""
from __future__ import annotations

import html
import logging
from typing import Optional

from smedjan import sources

log = logging.getLogger("smedjan.renderers.block_2a")


def _fetch_metrics(slug: str) -> Optional[dict]:
    """Return computed metrics for `slug`, or `None` when nothing to render.

    `COLLATE "C"` is applied on the equality against `agent_name` for the
    same reason as block_2b: default collation equality has silently
    returned zero rows on the Nerq RO replica for byte-identical strings
    (ICU/locale drift). Byte collation is correct for these opaque slugs.
    """
    try:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT source, signal_name, signal_value "
                "FROM zarq.external_trust_signals "
                "WHERE agent_name COLLATE \"C\" = %s",
                (slug,),
            )
            rows = cur.fetchall()
            if not rows:
                return None

            sources_seen = {r[0] for r in rows}
            reddit = None
            stackoverflow = None
            for src, name, val in rows:
                if src == "reddit" and name == "reddit_mentions_30d":
                    reddit = val
                elif src == "stackoverflow" and name == "stackoverflow_questions":
                    stackoverflow = val

            return {
                "has_osv_signal": "osv_dev" in sources_seen,
                "has_openssf_score": "openssf_scorecard" in sources_seen,
                "reddit_mentions": reddit,
                "stackoverflow_mentions": stackoverflow,
                "total_signal_sources": len(sources_seen),
            }
    except sources.SourceUnavailable as exc:
        log.warning("block_2a: nerq_ro unavailable for %s: %s", slug, exc)
        return None
    except Exception as exc:  # last-ditch fail-closed
        log.warning("block_2a: query failed for %s: %s", slug, exc)
        return None


def _fmt_count(val) -> str:
    if val is None:
        return "not available"
    try:
        return f"{int(val):,}"
    except (TypeError, ValueError):
        return "not available"


def render_block_2a_html(slug: str) -> Optional[str]:
    """Return the Block 2a HTML snippet for `slug`, or `None` if no data.

    The output is a single `<div class="section block-2a">…</div>`. It
    contains none of the sacred tokens (`pplx-verdict`, `ai-summary`,
    `SpeakableSpecification`, `FAQPage`) — callers can therefore insert
    it between the king-sections area and the FAQ section without
    mutating any SEO/GEO-critical markup.
    """
    data = _fetch_metrics(slug)
    if data is None:
        return None
    if data["total_signal_sources"] == 0:
        return None

    s_slug = html.escape(slug)
    osv_line = (
        '<li><strong>OSV vulnerability scan:</strong> signal present.</li>'
        if data["has_osv_signal"]
        else '<li><strong>OSV vulnerability scan:</strong> no signal yet.</li>'
    )
    openssf_line = (
        '<li><strong>OpenSSF scorecard:</strong> signal present.</li>'
        if data["has_openssf_score"]
        else '<li><strong>OpenSSF scorecard:</strong> no signal yet.</li>'
    )
    reddit_line = (
        f'<li><strong>Reddit mentions (30d):</strong> '
        f'{_fmt_count(data["reddit_mentions"])}.</li>'
    )
    so_line = (
        f'<li><strong>Stack Overflow questions:</strong> '
        f'{_fmt_count(data["stackoverflow_mentions"])}.</li>'
    )
    sources_line = (
        f'<li><strong>Distinct signal sources:</strong> '
        f'{data["total_signal_sources"]}.</li>'
    )

    return (
        f'<div class="section block-2a" data-block="2a" data-slug="{s_slug}">'
        '<h2 class="section-title">External Trust Signals</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        "Aggregated from public vulnerability, scorecard and community "
        "sources. Shadow data, read-only."
        "</p>"
        '<ul style="font-size:15px;line-height:1.7;color:#374151;margin:0;padding-left:20px">'
        f"{osv_line}"
        f"{openssf_line}"
        f"{reddit_line}"
        f"{so_line}"
        f"{sources_line}"
        "</ul>"
        "</div>"
    )
