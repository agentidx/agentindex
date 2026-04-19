"""L2 Block 2c — trust-score signal timeline block (T006, registry-allowlist gate).

Renders a "Signal Timeline" panel inside ``king_sections`` on the
``/safe/{slug}`` page, between the T005 Dependency Graph block and the
T004 External Trust Signals block, above the pre-existing "Detailed
Score Analysis" section. Gated on ``L2_BLOCK_2C_REGISTRIES`` using the
same fail-closed allowlist semantics as the L1 canary playbook /
Block 2a-kings / Block 2b-kings registry gates.

Why a second Block 2c module
----------------------------
``smedjan/renderers/block_2c.py`` (T114) surfaces the **AI-demand**
timeline (current score, 7d/30d deltas, 3σ surge flag) sourced from
``smedjan.ai_demand_scores`` + ``smedjan.ai_demand_history``, wrapped in
an HTML comment (shadow mode) and positioned below ``king_sections``.

This new module surfaces the **trust-score** timeline sourced from
``public.signal_events`` on the Nerq RO replica, and is positioned
*inside* ``king_sections`` via the separate ``L2_BLOCK_2C_REGISTRIES``
allowlist. The two paths are deliberately independent — the T114
module retains its MODE-toggled shadow stream unchanged.

Data source (Nerq read-only replica)
------------------------------------
- ``public.signal_events`` — 24,616 trust-drop / trust-gain events
  across 10,197 entities and 32 registries as of 2026-04-19. Columns
  used: ``date``, ``signal_type``, ``entity_id``, ``registry``,
  ``description``, ``created_at`` (tiebreaker for within-day
  ordering).
- ``public.software_registry`` — joined on ``(slug, registry)`` to
  pick up the current ``trust_score`` that anchors the 3-snapshot
  history.

The block is fail-closed: any unexpected error returns ``None`` so the
safety page renders unchanged. The caller short-circuits when the
slug's registry is not on the ``L2_BLOCK_2C_REGISTRIES`` allowlist.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Optional

log = logging.getLogger("agentindex.smedjan.l2_block_2c")


_DELTA_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*points", re.IGNORECASE)

_MONTH_NAMES = (
    "",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _format_month(d) -> str:
    """Render a date as ``"April 2026"`` — the {month_i} slot in the
    template. ``date`` objects and ``datetime`` both support ``.month``
    and ``.year``, so a single code path covers both.
    """
    if d is None:
        return ""
    return f"{_MONTH_NAMES[d.month]} {d.year}"


def _parse_delta(description: Optional[str]) -> Optional[float]:
    """Extract the signed delta from ``"Trust score changed by +18.4 points"``.

    Returns ``None`` when the description is missing or unparseable so
    the caller can skip a malformed row rather than inject a
    placeholder into the rendered prose.
    """
    if not description:
        return None
    m = _DELTA_RE.search(description)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:  # pragma: no cover — regex guarantees numeric-shape
        return None


def _fetch_signal_timeline(slug: str, registry: str) -> Optional[dict]:
    """Return a dict with signal-timeline surface fields for ``(slug, registry)``.

    Returns ``None`` when the entity has zero trust-score events, when
    the replica is unreachable, or when any unexpected error occurs.
    The caller must therefore treat ``None`` as "do not render".

    ``COLLATE "C"`` is applied on equality because the Nerq replica has
    an ICU collation drift that silently returns zero rows for
    byte-identical strings — the same workaround the T004/T005 helpers
    use.

    Shape of the returned dict::

        {
            "events": [                       # newest first, up to 3
                {"date": date, "delta": float, "description": str}, ...
            ],
            "trust_score": float | None,      # current score (anchor)
        }
    """
    try:
        from smedjan import sources
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("l2_block_2c: sources import failed: %s", exc)
        return None

    try:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT date, description "
                "FROM public.signal_events "
                "WHERE entity_id COLLATE \"C\" = %s "
                "AND registry COLLATE \"C\" = %s "
                "AND signal_type IN ('trust_drop_10plus','trust_gain_10plus') "
                "ORDER BY date DESC, created_at DESC "
                "LIMIT 3",
                (slug, registry),
            )
            rows = cur.fetchall()
            if not rows:
                return None

            events = []
            for d, desc in rows:
                delta = _parse_delta(desc)
                if delta is None:
                    continue
                events.append({"date": d, "delta": delta, "description": desc})
            if not events:
                return None

            cur.execute(
                "SELECT trust_score FROM public.software_registry "
                "WHERE slug COLLATE \"C\" = %s AND registry COLLATE \"C\" = %s "
                "LIMIT 1",
                (slug, registry),
            )
            row = cur.fetchone()
            trust_score = float(row[0]) if row and row[0] is not None else None

    except Exception as exc:
        log.warning("l2_block_2c: fetch failed for %s/%s: %s", registry, slug, exc)
        return None

    return {"events": events, "trust_score": trust_score}


def _reconstruct_history(
    events: list[dict],
    current_score: Optional[float],
) -> list[tuple[float, object]]:
    """Walk backwards from ``current_score`` using the event deltas to
    produce up to 3 ``(score, date)`` snapshots in chronological order
    (oldest first).

    The newest event's after-state is anchored to ``current_score`` —
    that is, ``score_3 = current_score`` and
    ``score_i = score_{i+1} - delta_{i+1}``. When ``current_score`` is
    unknown the function returns an empty list — the caller then falls
    back to the delta-only "Last significant change" line without
    attempting a misleading history with a fabricated anchor.
    """
    if current_score is None or not events:
        return []
    # events comes in newest-first order; walk chronologically newest->oldest
    # to compute before-states, then reverse for display.
    snapshots: list[tuple[float, object]] = [(current_score, events[0]["date"])]
    running = current_score
    for idx, ev in enumerate(events[:-1]):
        running = running - ev["delta"]
        # This snapshot sits "after the previous (older) event" which, in
        # chronological order, is the date of the NEXT event in the
        # newest-first list.
        snapshots.append((running, events[idx + 1]["date"]))
    return list(reversed(snapshots))  # oldest first


def _format_score(score: float) -> str:
    """Render a score like ``"78.8"`` (one decimal) but strip a trailing
    ``".0"`` so round numbers read as ``"46"`` rather than ``"46.0"``.
    """
    s = f"{score:.1f}"
    return s[:-2] if s.endswith(".0") else s


def render_signal_timeline_html(slug: str, registry: str) -> Optional[str]:
    """Return the Block 2c HTML snippet for ``(slug, registry)`` or
    ``None`` if empty.

    The output is a single ``<div class="section">…</div>`` modelled on
    the T004 Block 2a / T005 Block 2b blocks so it inherits the
    surrounding CSS without new styles. It contains none of the sacred
    tokens (``pplx-verdict``, ``ai-summary``, ``SpeakableSpecification``,
    ``FAQPage``) — the caller may therefore splice it directly into
    ``king_sections`` without touching any GEO-critical markup.
    """
    data = _fetch_signal_timeline(slug, registry)
    if data is None:
        return None

    events: list[dict] = data["events"]
    trust_score = data["trust_score"]
    if not events:
        return None

    lines: list[str] = []

    history = _reconstruct_history(events, trust_score)
    # Trust scores are bounded [0, 100]. If linear delta composition yields
    # a snapshot outside that range, the reconstructed history is
    # non-physical — typically because the events came from a backfill
    # batch that doesn't linearly compose with the current `trust_score`.
    # Drop the history line in that case and keep only the delta prose.
    history_in_bounds = all(0.0 <= sc <= 100.0 for sc, _ in history)
    if len(history) >= 2 and history_in_bounds:
        arrow = " &rarr; "
        history_str = arrow.join(
            f"{_format_score(sc)} ({html.escape(_format_month(d))})"
            for sc, d in history
        )
        lines.append(
            f"<li><strong>Trust score history:</strong> {history_str}.</li>"
        )

    newest = events[0]
    delta = newest["delta"]
    sign = "+" if delta >= 0 else "-"
    abs_str = _format_score(abs(delta))
    date_str = newest["date"].isoformat() if newest["date"] else ""
    lines.append(
        f"<li><strong>Last significant change:</strong> "
        f"{sign}{abs_str} points on {html.escape(date_str)}.</li>"
    )

    if not lines:
        return None

    s_slug = html.escape(slug)
    return (
        f'<div class="section block-2c-kings" data-block="2c-kings" data-slug="{s_slug}">'
        '<h2 class="section-title">Signal Timeline</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        "Significant trust-score moves from Nerq's ongoing daily scans "
        "(10+ point swings only)."
        "</p>"
        '<ul style="font-size:15px;line-height:1.7;color:#374151;margin:0;padding-left:20px">'
        + "".join(lines)
        + "</ul></div>"
    )
