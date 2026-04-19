"""
L2 Block 2b — dependency-graph renderer.

Source: `public.dependency_edges` on the Nerq read-only replica
(npm-only today, ~880K edges / ~60K distinct entities).

Surface fields (computed on the fly — the source table only stores raw edges):

    direct_deps_count       count of non-dev edges where entity_from = slug
    dev_deps_count          count of dev edges (informational)
    transitive_risk         distinct downstream entities reached in a 2-hop
                            sample (capped at `_HOP_SAMPLE`). `None` when
                            the entity has no direct deps.
    cycle_detected          true when any direct dep of the entity itself
                            depends back on the entity (1-hop cycle check).
    dormant_maintainer_flag placeholder; no maintainer feed wired yet, so
                            always returned as `None` and rendered as a
                            "not-yet-available" line.

Design notes
------------
* Fail-closed. Any `SourceUnavailable` or unexpected error returns `None`
  so the caller renders nothing — the agent safety page must never crash
  because of a Block 2b query.
* No writes. Uses `sources.nerq_readonly_cursor()` exclusively.
* No shadow/live wrapping here; the caller decides based on the
  `L2_BLOCK_2B_MODE` env var. This module always returns the raw block
  HTML (or `None` when there is nothing to render).
"""
from __future__ import annotations

import html
import logging
from typing import Optional

from smedjan import sources

log = logging.getLogger("smedjan.renderers.block_2b")

_HOP_SAMPLE = 200  # cap direct-dep fan-out before 2-hop expansion


def _fetch_metrics(slug: str) -> Optional[dict]:
    """Return computed metrics for `slug`, or `None` when nothing to render.

    `COLLATE "C"` is applied on every equality/ANY predicate against
    `entity_from` / `entity_to`. Default collation equality silently
    returned zero rows on the Nerq RO replica (observed 2026-04-19 —
    ICU/locale drift produces visibly-equal strings that fail `=`). Byte
    collation is correct for these opaque package slugs anyway.
    """
    try:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT entity_to, dependency_type "
                "FROM public.dependency_edges "
                "WHERE entity_from COLLATE \"C\" = %s AND registry = 'npm'",
                (slug,),
            )
            rows = cur.fetchall()
            if not rows:
                return None

            direct = [r[0] for r in rows if r[1] != "dev"]
            dev = [r[0] for r in rows if r[1] == "dev"]

            cycle = False
            transitive = None
            if direct:
                sample = direct[:_HOP_SAMPLE]
                cur.execute(
                    "SELECT 1 FROM public.dependency_edges "
                    "WHERE entity_from COLLATE \"C\" = ANY(%s) "
                    "AND entity_to COLLATE \"C\" = %s "
                    "AND registry = 'npm' LIMIT 1",
                    (sample, slug),
                )
                cycle = cur.fetchone() is not None

                cur.execute(
                    "SELECT COUNT(DISTINCT entity_to) "
                    "FROM public.dependency_edges "
                    "WHERE entity_from COLLATE \"C\" = ANY(%s) "
                    "AND registry = 'npm'",
                    (sample,),
                )
                transitive = cur.fetchone()[0]

            return {
                "direct_deps_count": len(direct),
                "dev_deps_count": len(dev),
                "transitive_risk": transitive,
                "cycle_detected": cycle,
                "dormant_maintainer_flag": None,
            }
    except sources.SourceUnavailable as exc:
        log.warning("block_2b: nerq_ro unavailable for %s: %s", slug, exc)
        return None
    except Exception as exc:  # last-ditch fail-closed
        log.warning("block_2b: query failed for %s: %s", slug, exc)
        return None


def render_block_2b_html(slug: str) -> Optional[str]:
    """Return the Block 2b HTML snippet for `slug`, or `None` if no data.

    The output is a single `<div class="section block-2b">…</div>`. It
    contains none of the sacred tokens (`pplx-verdict`, `ai-summary`,
    `SpeakableSpecification`, `FAQPage`) — callers can therefore insert
    it between the king-sections area and the FAQ section without
    mutating any SEO/GEO-critical markup.
    """
    data = _fetch_metrics(slug)
    if data is None:
        return None
    if data["direct_deps_count"] == 0 and data["dev_deps_count"] == 0:
        return None

    s_slug = html.escape(slug)
    direct = data["direct_deps_count"]
    dev = data["dev_deps_count"]
    transitive = data["transitive_risk"]
    cycle = data["cycle_detected"]
    dormant = data["dormant_maintainer_flag"]

    if cycle:
        cycle_line = (
            '<li><strong>Cycle detected:</strong> yes — at least one direct '
            "dependency depends back on this entity.</li>"
        )
    else:
        cycle_line = (
            '<li><strong>Cycle detected:</strong> no 1-hop cycle observed.</li>'
        )

    if isinstance(transitive, int):
        transitive_line = (
            f'<li><strong>Transitive footprint (2-hop sample):</strong> '
            f"{transitive:,} distinct downstream entities.</li>"
        )
    else:
        transitive_line = (
            '<li><strong>Transitive footprint:</strong> not yet computed.</li>'
        )

    if dormant is None:
        dormant_line = (
            '<li><strong>Dormant maintainer:</strong> signal not yet '
            "available.</li>"
        )
    else:
        dormant_line = (
            f'<li><strong>Dormant maintainer:</strong> '
            f'{"flagged" if dormant else "no"}.</li>'
        )

    return (
        f'<div class="section block-2b" data-block="2b" data-slug="{s_slug}">'
        '<h2 class="section-title">Dependency Graph Signals</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        "Derived from open-source dependency edges. npm scope, shadow data."
        "</p>"
        '<ul style="font-size:15px;line-height:1.7;color:#374151;margin:0;padding-left:20px">'
        f'<li><strong>Direct dependencies:</strong> {direct:,} (+{dev:,} dev)</li>'
        f"{transitive_line}"
        f"{cycle_line}"
        f"{dormant_line}"
        "</ul>"
        "</div>"
    )
