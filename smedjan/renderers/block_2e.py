"""
L2 Block 2e — dimensions-dashboard renderer.

Source: `public.software_registry.dimensions` (JSONB) on the Nerq
read-only replica. Only ~1.8K of the 2.4M rows have non-empty
dimensions today, so most calls return `None`. The data lives only in
Nerq (no analytics_mirror copy confirmed 2026-04-19).

Surface fields
--------------
    dimension_count         number of keys in the dimensions object
    top_dimension_names     up to `_TOP_N` keys, ranked by value desc
    sample_dimension_values list of (name, value) pairs for the same
                            top-N subset, preserving rank order

Design notes
------------
* Fail-closed. Any `SourceUnavailable` or unexpected error returns
  `None`; the caller renders nothing so the agent-safety page never
  crashes because of a Block 2e query.
* No writes. Uses `sources.nerq_readonly_cursor()` exclusively.
* No shadow/live wrapping here; the caller decides based on the
  `L2_BLOCK_2E_MODE` env var. This module always returns the raw block
  HTML (or `None`).
* No sacred tokens (`pplx-verdict`, `ai-summary`, `SpeakableSpecification`,
  `FAQPage`) appear in the output — safe to splice below king-sections
  and above FAQ.
"""
from __future__ import annotations

import html
import logging
from typing import Optional

from smedjan import sources

log = logging.getLogger("smedjan.renderers.block_2e")

_TOP_N = 5


def _fetch_metrics(slug: str) -> Optional[dict]:
    try:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT dimensions FROM public.software_registry "
                "WHERE slug = %s AND dimensions IS NOT NULL LIMIT 1",
                (slug,),
            )
            row = cur.fetchone()
    except sources.SourceUnavailable as exc:
        log.warning("block_2e: nerq_ro unavailable for %s: %s", slug, exc)
        return None
    except Exception as exc:
        log.warning("block_2e: query failed for %s: %s", slug, exc)
        return None

    if not row or not row[0]:
        return None

    dims = row[0]
    if not isinstance(dims, dict) or not dims:
        return None

    numeric_items = [(k, v) for k, v in dims.items() if isinstance(v, (int, float))]
    if not numeric_items:
        return None

    numeric_items.sort(key=lambda kv: kv[1], reverse=True)
    top = numeric_items[:_TOP_N]

    return {
        "dimension_count": len(dims),
        "top_dimension_names": [k for k, _ in top],
        "sample_dimension_values": [(k, v) for k, v in top],
    }


def render_block_2e_html(slug: str) -> Optional[str]:
    """Return the Block 2e HTML snippet for `slug`, or `None` if no data.

    The output is a single `<div class="section block-2e">…</div>` with
    no sacred tokens — callers may insert it between the king-sections
    area and the FAQ section without mutating any SEO/GEO-critical
    markup.
    """
    data = _fetch_metrics(slug)
    if data is None:
        return None

    s_slug = html.escape(slug)
    count = data["dimension_count"]
    rows = data["sample_dimension_values"]

    items_html = "".join(
        f'<li><strong>{html.escape(str(name))}:</strong> '
        f'{value:g}</li>'
        for name, value in rows
    )

    return (
        f'<div class="section block-2e" data-block="2e" data-slug="{s_slug}">'
        '<h2 class="section-title">Trust Dimensions</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        f"{count} dimension{'s' if count != 1 else ''} scored for this entity "
        "(top values shown). Shadow data — values and coverage are evolving."
        "</p>"
        '<ul style="font-size:15px;line-height:1.7;color:#374151;margin:0;padding-left:20px">'
        f"{items_html}"
        "</ul>"
        "</div>"
    )
