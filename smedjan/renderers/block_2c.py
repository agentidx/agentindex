"""
L2 Block 2c — AI demand timeline renderer.

Source: `smedjan.ai_demand_scores` (current snapshot, ~44K rows as of
2026-04-19) + `smedjan.ai_demand_history` (historical snapshots,
primary key `(slug, computed_at)`). Both live on the Smedjan DB on
Hetzner — the read path is `sources.smedjan_db_cursor()`.

Note: at first render, `ai_demand_history` only contains the initial
snapshot (2026-04-19), so deltas/velocity/surge will render as "not
yet available" until enough history has accumulated. That is expected
and intentionally visible in the page, not hidden.

Surface fields
--------------
    current_score       real (0-100 range in the current seed)
    last_30d_queries    integer; raw query volume behind `current_score`
    delta_7d            score - score_~7d_ago; `None` until history
                        covers the window
    delta_30d           score - score_~30d_ago; `None` until history
                        covers the window
    velocity            mean pts/day over the last 7 days; `None` when
                        fewer than 2 points fall in that window
    is_surge_3sigma     True iff current_score > µ + 3σ of the
                        historical distribution; requires ≥ 14 points,
                        else `None`

Design notes
------------
* Fail-closed. Any `SourceUnavailable` or unexpected error returns
  `None` so the caller renders nothing — the agent safety page must
  never crash because of a Block 2c query.
* Reads only the Smedjan DB; no Nerq queries.
* No shadow/live wrapping here; the caller decides based on the
  `L2_BLOCK_2C_MODE` env var. This module always returns the raw block
  HTML (or `None` when there is nothing to render).
* No sacred tokens (`pplx-verdict`, `ai-summary`, `SpeakableSpecification`,
  `FAQPage`) appear in the output — safe to splice below king-sections
  and above FAQ.
"""
from __future__ import annotations

import html
import logging
import statistics
from datetime import timedelta
from typing import Optional

from smedjan import sources

log = logging.getLogger("smedjan.renderers.block_2c")

_WINDOW_7D = timedelta(days=7)
_WINDOW_30D = timedelta(days=30)
_MIN_SURGE_POINTS = 14


def _fetch_metrics(slug: str) -> Optional[dict]:
    try:
        with sources.smedjan_db_cursor() as (_, cur):
            cur.execute(
                "SELECT score, last_30d_queries, computed_at "
                "FROM smedjan.ai_demand_scores WHERE slug = %s",
                (slug,),
            )
            cur_row = cur.fetchone()
            if not cur_row:
                return None

            cur.execute(
                "SELECT computed_at, score "
                "FROM smedjan.ai_demand_history "
                "WHERE slug = %s ORDER BY computed_at ASC",
                (slug,),
            )
            history = cur.fetchall()
    except sources.SourceUnavailable as exc:
        log.warning("block_2c: smedjan db unavailable for %s: %s", slug, exc)
        return None
    except Exception as exc:  # last-ditch fail-closed
        log.warning("block_2c: query failed for %s: %s", slug, exc)
        return None

    current_score, last_30d_queries, computed_at = cur_row

    def _score_at_or_before(target_ts):
        # history is sorted ASC; pick the latest row ≤ target_ts
        found = None
        for ts, sc in history:
            if ts <= target_ts:
                found = sc
            else:
                break
        return found

    delta_7d = None
    delta_30d = None
    if history:
        s7 = _score_at_or_before(computed_at - _WINDOW_7D)
        s30 = _score_at_or_before(computed_at - _WINDOW_30D)
        if s7 is not None:
            delta_7d = current_score - s7
        if s30 is not None:
            delta_30d = current_score - s30

    velocity = None
    if history:
        window_pts = [
            (ts, sc) for ts, sc in history
            if ts >= computed_at - _WINDOW_7D
        ]
        if len(window_pts) >= 2:
            earliest_ts, earliest_score = window_pts[0]
            span_days = (computed_at - earliest_ts).total_seconds() / 86400.0
            if span_days > 0:
                velocity = (current_score - earliest_score) / span_days

    is_surge: Optional[bool] = None
    if len(history) >= _MIN_SURGE_POINTS:
        scores = [sc for _, sc in history]
        try:
            mu = statistics.fmean(scores)
            sigma = statistics.pstdev(scores)
        except statistics.StatisticsError:
            mu = sigma = None
        if sigma is not None:
            if sigma > 0:
                is_surge = current_score > (mu + 3 * sigma)
            else:
                is_surge = False  # flat history → by definition no surge

    return {
        "current_score": current_score,
        "last_30d_queries": last_30d_queries,
        "delta_7d": delta_7d,
        "delta_30d": delta_30d,
        "velocity": velocity,
        "is_surge_3sigma": is_surge,
        "history_points": len(history),
    }


def _fmt_score(val) -> str:
    if val is None:
        return "not available"
    try:
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return "not available"


def _fmt_delta(val) -> str:
    if val is None:
        return "not yet available"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "not yet available"
    sign = "+" if v >= 0 else "−"
    return f"{sign}{abs(v):.2f}"


def _fmt_velocity(val) -> str:
    if val is None:
        return "not yet available"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "not yet available"
    sign = "+" if v >= 0 else "−"
    return f"{sign}{abs(v):.2f} pts/day"


def _fmt_queries(val) -> str:
    if val is None:
        return "n/a"
    try:
        return f"{int(val):,}"
    except (TypeError, ValueError):
        return "n/a"


def render_block_2c_html(slug: str) -> Optional[str]:
    """Return the Block 2c HTML snippet for `slug`, or `None` if no data.

    The output is a single `<div class="section block-2c">…</div>` with
    no sacred tokens — callers may insert it between the king-sections
    area and the FAQ section without mutating any SEO/GEO-critical
    markup.
    """
    data = _fetch_metrics(slug)
    if data is None:
        return None
    if data["current_score"] is None:
        return None

    s_slug = html.escape(slug)
    current = data["current_score"]
    queries = data["last_30d_queries"]
    surge = data["is_surge_3sigma"]

    if surge is True:
        surge_line = (
            '<li><strong>Surge (3σ):</strong> yes — current score '
            "exceeds the 3-sigma band of its history.</li>"
        )
    elif surge is False:
        surge_line = (
            '<li><strong>Surge (3σ):</strong> no surge detected.</li>'
        )
    else:
        surge_line = (
            '<li><strong>Surge (3σ):</strong> history too short to '
            "decide.</li>"
        )

    return (
        f'<div class="section block-2c" data-block="2c" data-slug="{s_slug}">'
        '<h2 class="section-title">AI Demand Timeline</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        "Search demand from AI assistants over time. Shadow data — "
        "historical snapshots are accumulating."
        "</p>"
        '<ul style="font-size:15px;line-height:1.7;color:#374151;margin:0;padding-left:20px">'
        f'<li><strong>Current score:</strong> {_fmt_score(current)} '
        f'({_fmt_queries(queries)} queries in last 30 days).</li>'
        f'<li><strong>7-day change:</strong> {_fmt_delta(data["delta_7d"])}.</li>'
        f'<li><strong>30-day change:</strong> {_fmt_delta(data["delta_30d"])}.</li>'
        f'<li><strong>Velocity (7d):</strong> {_fmt_velocity(data["velocity"])}.</li>'
        f"{surge_line}"
        "</ul>"
        "</div>"
    )
