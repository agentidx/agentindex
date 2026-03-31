"""
SEO Trust Pages — nerq.ai
Route: GET /trust/{name}
Generates SEO-optimized trust assessment pages for individual agents.
"""
import time
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import nerq_page

router_trust_pages = APIRouter(tags=["seo"])

# ── In-memory cache (key -> (html, timestamp)) ──────────────────
_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 86400  # 24 hours
_CACHE_MAX = 1000

_TRUST_COLS = """
    name,
    COALESCE(trust_score_v2, trust_score) as trust_score,
    trust_grade,
    category,
    description,
    source_url,
    stars,
    author,
    first_indexed,
    is_verified,
    frameworks
"""


def _escape(s: str) -> str:
    """Escape HTML entities."""
    if not s:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _escape_json(s: str) -> str:
    """Escape string for JSON embedding."""
    if not s:
        return ""
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def _lookup_agent(name: str) -> dict | None:
    """Look up agent by name using UNION ALL pattern with trgm-friendly queries."""
    session = get_session()
    try:
        clean = name.replace("-", " ").replace("_", " ")
        row = session.execute(text(f"""
            SELECT {_TRUST_COLS} FROM (
                SELECT *, 1 AS _rank FROM agents
                WHERE LOWER(name) = LOWER(:name) AND is_active = true
              UNION ALL
                SELECT *, 1 AS _rank FROM agents
                WHERE LOWER(name) = LOWER(:clean) AND is_active = true
                AND :clean != :name
              UNION ALL
                SELECT *, 2 AS _rank FROM agents
                WHERE lower(name::text) LIKE lower(:suffix) AND is_active = true
              UNION ALL
                SELECT *, 3 AS _rank FROM agents
                WHERE lower(name::text) LIKE lower(:pattern) AND is_active = true
            ) sub
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST,
                     stars DESC NULLS LAST
            LIMIT 1
        """), {
            "name": name,
            "clean": clean,
            "suffix": f"%/{name}",
            "pattern": f"%{name}%",
        }).fetchone()
        return dict(row._mapping) if row else None
    finally:
        session.close()


def _grade_pill(grade: str) -> str:
    """Return pill CSS class based on grade."""
    if not grade:
        return "pill-gray"
    g = grade.upper()
    if g.startswith("A"):
        return "pill-green"
    if g.startswith("B"):
        return "pill-yellow"
    return "pill-red"


def _trust_assessment(name: str, score: float) -> str:
    """Generate trust assessment text based on score."""
    n = _escape(name)
    if score >= 85:
        return f"Highly Trusted &mdash; {n} ranks among the top AI agents with exceptional trust signals."
    if score >= 70:
        return f"Trusted &mdash; {n} demonstrates strong trust signals across security, maintenance, and ecosystem metrics."
    if score >= 50:
        return f"Moderate &mdash; {n} shows mixed trust signals. Review the full KYA report before use."
    return f"Low Trust &mdash; {n} has significant trust concerns. Proceed with caution."


def _render_trust_page(agent: dict) -> str:
    """Build the full trust page HTML."""
    name = agent.get("name") or "Unknown"
    score = agent.get("trust_score") or 0
    grade = agent.get("trust_grade") or "N/A"
    category = agent.get("category") or "Uncategorized"
    description = agent.get("description") or ""
    source_url = agent.get("source_url") or ""
    stars = agent.get("stars") or 0
    author = agent.get("author") or "Unknown"
    first_indexed = agent.get("first_indexed")
    is_verified = agent.get("is_verified", False)
    frameworks = agent.get("frameworks") or []

    score_display = f"{score:.1f}" if isinstance(score, float) else str(score)
    pill_class = _grade_pill(grade)
    assessment = _trust_assessment(name, float(score) if score else 0)

    # Format first indexed date
    indexed_display = ""
    if first_indexed:
        if isinstance(first_indexed, datetime):
            indexed_display = first_indexed.strftime("%B %d, %Y")
        else:
            indexed_display = str(first_indexed)[:10]

    # Frameworks display
    fw_html = ""
    if frameworks:
        fw_html = " &middot; ".join(_escape(f) for f in frameworks[:5])

    # Verified badge
    verified_badge = ""
    if is_verified:
        verified_badge = ' <span class="pill pill-green" style="font-size:11px">verified</span>'

    # Badge markdown
    badge_url = f"https://nerq.ai/badge/{_escape(name)}.svg"
    badge_md = f"[![Nerq Trust Score]({badge_url})](https://nerq.ai/trust/{_escape(name)})"

    # Canonical and meta
    canonical = f"https://nerq.ai/trust/{_escape(name)}"
    meta_desc = (
        f"{_escape(name)} has a Nerq Trust Score of {score_display}/100 ({_escape(grade)}). "
        f"Independent trust assessment based on security, compliance, maintenance, and ecosystem signals."
    )
    title = f"Is {_escape(name)} trustworthy? Nerq Trust Score: {score_display}/100 ({_escape(grade)})"

    # JSON-LD
    json_ld = (
        '{"@context":"https://schema.org","@type":"SoftwareApplication",'
        f'"name":"{_escape_json(name)}",'
        f'"description":"{_escape_json(description[:300])}",'
        f'"applicationCategory":"{_escape_json(category)}",'
        f'"author":{{"@type":"Person","name":"{_escape_json(author)}"}},'
        f'"aggregateRating":{{"@type":"AggregateRating","ratingValue":"{score_display}","bestRating":"100","worstRating":"0","ratingCount":"1"}}'
        "}"
    )

    body = f"""
<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/discover">search</a> &rsaquo; trust</div>

<h1>{_escape(name)} Trust Score{verified_badge}</h1>

<div class="card" style="text-align:center;padding:32px 16px;margin:16px 0">
  <div style="font-family:ui-monospace,'SF Mono',monospace;font-size:3.5rem;font-weight:700;color:#0d9488;line-height:1">{score_display}</div>
  <div style="font-size:14px;color:#6b7280;margin:4px 0 12px">out of 100</div>
  <span class="pill {pill_class}" style="font-size:14px;padding:4px 16px">{_escape(grade)}</span>
  <span class="pill pill-gray" style="font-size:14px;padding:4px 16px;margin-left:8px">{_escape(category)}</span>
</div>

<div class="card" style="margin:16px 0;padding:20px">
  <h3 style="margin:0 0 8px">Trust Assessment</h3>
  <p style="font-size:15px;line-height:1.7;margin:0">{assessment}</p>
</div>

<h2>Details</h2>
<table>
  <tr><td style="color:#6b7280;width:140px">Author</td><td>{_escape(author)}</td></tr>
  <tr><td style="color:#6b7280">Category</td><td>{_escape(category)}</td></tr>
  <tr><td style="color:#6b7280">Stars</td><td>{stars:,}</td></tr>
  <tr><td style="color:#6b7280">Source</td><td>{"<a href=\"" + _escape(source_url) + "\">" + _escape(source_url) + "</a>" if source_url else "N/A"}</td></tr>
  <tr><td style="color:#6b7280">First Indexed</td><td>{indexed_display or "N/A"}</td></tr>
  {"<tr><td style=\"color:#6b7280\">Frameworks</td><td>" + fw_html + "</td></tr>" if fw_html else ""}
</table>

<h2>Badge Embed</h2>
<div class="card" style="padding:20px">
  <p style="margin:0 0 8px"><img src="{badge_url}" alt="Nerq Trust Score for {_escape(name)}" style="height:20px"></p>
  <p style="font-size:13px;color:#6b7280;margin:0 0 8px">Copy this markdown to embed the trust badge:</p>
  <pre style="font-size:12px;user-select:all;cursor:pointer">{_escape(badge_md)}</pre>
</div>

<h2>Actions</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin:12px 0">
  <a href="/kya/{_escape(name)}" style="display:inline-block;padding:8px 20px;background:#0d9488;color:#fff;font-size:14px;font-weight:600;text-decoration:none">Full KYA Report</a>
  <a href="/v1/preflight?target={_escape(name)}" style="display:inline-block;padding:8px 20px;border:1px solid #0d9488;color:#0d9488;font-size:14px;font-weight:600;text-decoration:none">Preflight Check</a>
</div>

<script type="application/ld+json">{json_ld}</script>
"""

    return nerq_page(title=title, body=body, description=meta_desc, canonical=canonical)


def _cache_get(key: str) -> str | None:
    """Get from cache if not expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    html, ts = entry
    if time.time() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return html


def _cache_set(key: str, html: str) -> None:
    """Set cache entry, evict oldest if at capacity."""
    if len(_cache) >= _CACHE_MAX:
        # Evict oldest entry
        oldest_key = min(_cache, key=lambda k: _cache[k][1])
        del _cache[oldest_key]
    _cache[key] = (html, time.time())


@router_trust_pages.get("/trust/{name}", response_class=HTMLResponse)
def trust_page(name: str):
    """SEO-optimized trust assessment page for an agent."""
    cache_key = name.lower().strip()

    cached = _cache_get(cache_key)
    if cached:
        return HTMLResponse(cached)

    agent = _lookup_agent(name)
    if not agent:
        html_404 = nerq_page(
            title=f"Agent Not Found - {_escape(name)}",
            body=f"""
<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; trust</div>
<h1>Agent not found</h1>
<p class="desc">No agent matching &ldquo;{_escape(name)}&rdquo; was found in the Nerq index.</p>
<p style="margin-top:16px"><a href="/discover?q={_escape(name)}">Search for &ldquo;{_escape(name)}&rdquo;</a></p>
""",
            description=f"No trust data found for {_escape(name)}.",
        )
        return HTMLResponse(html_404, status_code=404)

    html = _render_trust_page(agent)
    _cache_set(cache_key, html)
    return HTMLResponse(html)
