"""L2 Block 2a — external trust signals block (T004, registry-allowlist gate).

Renders an "External Trust Signals" panel inside ``king_sections`` on the
``/safe/{slug}`` page, ABOVE the existing "Detailed Score Analysis"
section. Gated on ``L2_BLOCK_2A_REGISTRIES`` using the L1 canary
playbook's allowlist semantics (fail-closed empty = disabled).

Data source
-----------
``zarq.external_trust_signals`` on the Nerq read-only replica (22,502
rows / 7,724 distinct agents as of 2026-04-18). The table stores one
``(agent_name, source, signal_name) → signal_value`` tuple per signal,
with ``signal_max`` where it is a scored sub-check and ``fetched_at``
giving the last-scan timestamp. There is no parallel write in the
analytics mirror — Nerq RO is the only read path.

Surface fields assembled by ``_fetch_external_trust``:

    sources            {'osv_dev', 'openssf_scorecard', 'reddit', 'stackoverflow'}
    osv_count          osv_dev.vulnerability_count (int, can be 0)
    osv_scan_date      MAX(fetched_at) across osv_dev rows (date)
    openssf_score      openssf_scorecard.overall_score (float, 0–10)
    openssf_signals    {sub-check name: (value, max)} for the top-scoring
                       and worst-scoring sub-checks — feeds the prose
                       "(license 10/10, code_review 0/10)" tail.
    so_thread_count    stackoverflow.stackoverflow_questions (int)
    reddit_mentions    reddit.reddit_mentions_30d (int; note: 30d window,
                       not the 12 months the original draft template
                       mentioned — the design doc records the correction)

The block is fail-closed: any unexpected error returns ``None`` so the
safety page renders unchanged.
"""
from __future__ import annotations

import html
import logging
from typing import Optional

log = logging.getLogger("agentindex.smedjan.l2_block_2a")


_OPENSSF_SCORECARD_SUMMARY_KEYS = (
    "license",
    "maintained",
    "security_policy",
    "code_review",
    "branch_protection",
    "signed_releases",
    "vulnerabilities",
)


def _fetch_external_trust(slug: str) -> Optional[dict]:
    """Return a dict with external-trust surface fields for ``slug``.

    Returns ``None`` when the entity has no external-trust signals, when
    the replica is unreachable, or when any unexpected error occurs.
    The caller must therefore treat ``None`` as "do not render".

    ``COLLATE "C"`` is applied on equality because the Nerq replica has
    an ICU collation drift that silently returns zero rows for
    byte-identical strings (see ``smedjan/renderers/block_2a.py`` and
    ``smedjan/renderers/block_2b.py`` for the same workaround).
    """
    try:
        from smedjan import sources  # lazy: keep factory deps out of import path
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("l2_block_2a: sources import failed: %s", exc)
        return None

    try:
        with sources.nerq_readonly_cursor() as (_, cur):
            cur.execute(
                "SELECT source, signal_name, signal_value, signal_max, fetched_at "
                "FROM zarq.external_trust_signals "
                "WHERE agent_name COLLATE \"C\" = %s",
                (slug,),
            )
            rows = cur.fetchall()
    except Exception as exc:
        log.warning("l2_block_2a: fetch failed for %s: %s", slug, exc)
        return None

    if not rows:
        return None

    sources_seen: set[str] = set()
    osv_count: Optional[int] = None
    osv_scan_date = None
    openssf_score: Optional[float] = None
    openssf_signals: dict[str, tuple[float, float]] = {}
    so_thread_count: Optional[int] = None
    reddit_mentions: Optional[int] = None

    for src, name, value, smax, fetched_at in rows:
        sources_seen.add(src)
        if src == "osv_dev":
            if name == "vulnerability_count" and value is not None:
                osv_count = int(value)
            if fetched_at is not None:
                osv_scan_date = max(osv_scan_date, fetched_at) if osv_scan_date else fetched_at
        elif src == "openssf_scorecard":
            if name == "overall_score" and value is not None:
                openssf_score = float(value)
            elif (
                name in _OPENSSF_SCORECARD_SUMMARY_KEYS
                and value is not None
                and smax is not None
            ):
                openssf_signals[name] = (float(value), float(smax))
        elif src == "reddit" and name == "reddit_mentions_30d" and value is not None:
            reddit_mentions = int(value)
        elif src == "stackoverflow" and name == "stackoverflow_questions" and value is not None:
            so_thread_count = int(value)

    return {
        "sources": sources_seen,
        "osv_count": osv_count,
        "osv_scan_date": osv_scan_date,
        "openssf_score": openssf_score,
        "openssf_signals": openssf_signals,
        "so_thread_count": so_thread_count,
        "reddit_mentions": reddit_mentions,
    }


_SOURCE_LABEL = {
    "osv_dev": "OSV.dev",
    "openssf_scorecard": "OpenSSF Scorecard",
    "reddit": "Reddit",
    "stackoverflow": "Stack Overflow",
}


def _format_sources_list(sources_seen: set[str]) -> str:
    labels = [_SOURCE_LABEL.get(s, s) for s in sources_seen]
    labels.sort()
    if len(labels) <= 1:
        return labels[0] if labels else ""
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _format_signals_summary(signals: dict[str, tuple[float, float]]) -> str:
    """Pick up to three sub-checks to flesh out the prose tail.

    One highest, one lowest, optionally one mid-range — gives the reader
    a quick signal that the Scorecard is real data, not a flat "10/10"
    marketing number.
    """
    if not signals:
        return ""
    items = sorted(signals.items(), key=lambda kv: kv[1][0])
    picks: list[tuple[str, tuple[float, float]]] = []
    picks.append(items[-1])  # best
    if len(items) > 1 and items[0] is not items[-1]:
        picks.append(items[0])  # worst
    seen_names = {p[0] for p in picks}
    for k, v in items:
        if len(picks) >= 3:
            break
        if k not in seen_names:
            picks.append((k, v))
            seen_names.add(k)
    formatted = ", ".join(
        f"{html.escape(name.replace('_', ' '))} {val:g}/{smax:g}"
        for name, (val, smax) in picks
    )
    return formatted


def render_external_trust_block(slug: str) -> Optional[str]:
    """Return the Block 2a HTML snippet for ``slug`` or ``None`` if empty.

    The block is a single ``<div class="section">…</div>`` modelled on
    the other king-section blocks so it takes on the surrounding CSS
    without new styles. It contains none of the sacred tokens
    (``pplx-verdict``, ``ai-summary``, ``SpeakableSpecification``,
    ``FAQPage``) — the caller may therefore splice it directly into
    ``king_sections`` above "Detailed Score Analysis" without touching
    any GEO-critical markup.
    """
    data = _fetch_external_trust(slug)
    if data is None:
        return None
    if not data["sources"]:
        return None

    s_slug = html.escape(slug)
    lines: list[str] = []

    sources_list = _format_sources_list(data["sources"])
    if sources_list:
        lines.append(
            f"<li><strong>Verified by:</strong> {html.escape(sources_list)}.</li>"
        )

    if data["osv_count"] is not None:
        scan = (
            f" last scan {data['osv_scan_date'].date().isoformat()}"
            if data["osv_scan_date"] is not None
            else ""
        )
        lines.append(
            f"<li><strong>Vulnerabilities found:</strong> "
            f"{data['osv_count']:,} (OSV.dev{scan}).</li>"
        )

    if data["openssf_score"] is not None:
        summary = _format_signals_summary(data["openssf_signals"])
        tail = f" ({summary})" if summary else ""
        lines.append(
            f"<li><strong>OpenSSF Scorecard:</strong> "
            f"{data['openssf_score']:g}/10{tail}.</li>"
        )

    if data["so_thread_count"] is not None or data["reddit_mentions"] is not None:
        so = data["so_thread_count"] if data["so_thread_count"] is not None else 0
        rd = data["reddit_mentions"] if data["reddit_mentions"] is not None else 0
        lines.append(
            f"<li><strong>Community signal:</strong> {so:,} Stack Overflow "
            f"threads and {rd:,} Reddit posts (last 30 days).</li>"
        )

    if not lines:
        return None

    return (
        f'<div class="section block-2a-kings" data-block="2a-kings" data-slug="{s_slug}">'
        '<h2 class="section-title">External Trust Signals</h2>'
        '<p style="font-size:14px;color:#64748b;margin:0 0 8px">'
        "Independent verification from public vulnerability, scorecard "
        "and community sources."
        "</p>"
        '<ul style="font-size:15px;line-height:1.7;color:#374151;margin:0;padding-left:20px">'
        + "".join(lines)
        + "</ul></div>"
    )
