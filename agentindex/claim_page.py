"""
Claim Page — Claim your Nerq Trust Badge
Route: GET /claim, POST /claim/submit
"""

import json
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from agentindex.db.models import get_session, get_write_session
from agentindex.nerq_design import nerq_page, NERQ_CSS, NERQ_NAV, NERQ_FOOTER

router_claim = APIRouter(tags=["claim"])


# ── Helpers ──────────────────────────────────────────────────

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _lookup_agent(name: str, session) -> dict | None:
    """Find agent by name using UNION ALL with trgm-compatible LIKE."""
    if not name:
        return None
    row = session.execute(text("""
        SELECT id, name,
               COALESCE(trust_score_v2, trust_score) AS trust_score,
               trust_grade, category, first_indexed, is_verified, source_url
        FROM (
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, first_indexed, is_verified, source_url, 1 AS _r
            FROM entity_lookup WHERE name_lower = lower(:name) AND is_active = true
          UNION ALL
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, first_indexed, is_verified, source_url, 2 AS _r
            FROM entity_lookup WHERE name_lower LIKE lower(:suffix) AND is_active = true
          UNION ALL
            SELECT id, name, trust_score, trust_score_v2, trust_grade, category, first_indexed, is_verified, source_url, 3 AS _r
            FROM entity_lookup WHERE name_lower LIKE lower(:pattern) AND is_active = true
        ) sub
        ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
        LIMIT 1
    """), {"name": name, "suffix": f"%/{name}", "pattern": f"%{name}%"}).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "name": row[1],
        "trust_score": round(float(row[2]), 1) if row[2] else None,
        "grade": row[3],
        "category": row[4],
        "first_indexed": row[5],
        "verified": bool(row[6]) or (float(row[2]) >= 70 if row[2] else False),
        "source_url": row[7],
    }


def _rank_in_category(session, category: str, trust_score: float) -> int | None:
    if not category or trust_score is None:
        return None
    row = session.execute(text("""
        SELECT COUNT(*) FROM entity_lookup
        WHERE category = :cat
          AND COALESCE(trust_score_v2, trust_score) > :score
          AND is_active = true
    """), {"cat": category, "score": trust_score}).fetchone()
    return (row[0] + 1) if row else None


def _featured_agents(session) -> list[dict]:
    """Get recent scout_evaluate entries from last 24h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = session.execute(text("""
        SELECT agent_name, details, created_at
        FROM nerq_scout_log
        WHERE event_type = 'scout_evaluate'
          AND created_at >= :cutoff
          AND agent_name IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 5
    """), {"cutoff": cutoff}).fetchall()

    featured = []
    for r in rows:
        details = r[1] if isinstance(r[1], dict) else json.loads(r[1]) if r[1] else {}
        featured.append({
            "name": r[0],
            "trust_score": details.get("trust_score"),
            "grade": details.get("grade"),
            "category": details.get("category"),
        })
    return featured


def _score_pill(score) -> str:
    if score is None:
        return '<span class="pill pill-gray">N/A</span>'
    s = float(score)
    if s >= 70:
        return f'<span class="pill pill-green">{s:.0f}</span>'
    elif s >= 40:
        return f'<span class="pill pill-yellow">{s:.0f}</span>'
    else:
        return f'<span class="pill pill-red">{s:.0f}</span>'


# ── GET /claim ───────────────────────────────────────────────

@router_claim.get("/claim", response_class=HTMLResponse)
def claim_page(q: str = Query(None)):
    """Claim your Nerq Trust Badge page."""

    # Search box
    q_val = _esc(q) if q else ""
    search_html = f"""
<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; claim</div>
<h1>Claim your Nerq Trust Badge</h1>
<p class="desc">See your trust score and embed it in your README.</p>
<form class="search-box" method="get" action="/claim">
<input type="text" name="q" placeholder="Search by agent or repo name..." value="{q_val}">
<button type="submit">Look up</button>
</form>
"""

    result_html = ""

    if q:
        session = get_session()
        try:
            agent = _lookup_agent(q.strip(), session)

            if agent:
                name = agent["name"]
                score = agent["trust_score"]
                grade = agent["grade"] or "—"
                category = agent["category"] or "—"
                verified = agent["verified"]
                rank = _rank_in_category(session, agent["category"], score)

                verified_badge = (
                    '<span class="pill pill-green" style="margin-left:8px">Verified</span>'
                    if verified else
                    '<span class="pill pill-gray" style="margin-left:8px">Unverified</span>'
                )
                rank_text = f"#{rank}" if rank else "—"

                badge_md = f"[![Nerq Trust](https://nerq.ai/badge/{name})](https://nerq.ai/kya/{name})"
                badge_md_escaped = _esc(badge_md)

                tweet_text = (
                    f"My agent {name} scored {score:.0f}/100 ({grade}) "
                    f"on the @nerq_ai Trust Index https://nerq.ai/kya/{name}"
                ) if score else f"Check out {name} on the @nerq_ai Trust Index https://nerq.ai/kya/{name}"
                tweet_url = f"https://twitter.com/intent/tweet?text={quote(tweet_text)}"

                result_html = f"""
<div class="section">
<h2>{_esc(name)} {verified_badge}</h2>
<div class="stat-row">
<div class="stat-item"><div class="num">{f'{score:.1f}' if score else '—'}</div><div class="label">Trust Score</div></div>
<div class="stat-item"><div class="num">{_esc(grade)}</div><div class="label">Grade</div></div>
<div class="stat-item"><div class="num">{_esc(str(category))}</div><div class="label">Category</div></div>
<div class="stat-item"><div class="num">{rank_text}</div><div class="label">Rank in Category</div></div>
</div>
</div>

<div class="section">
<h2>Badge Preview</h2>
<p style="margin:12px 0"><img src="/badge/{_esc(name)}" alt="Nerq Trust Badge for {_esc(name)}" style="max-height:28px"></p>
</div>

<div class="section">
<h2>Embed in your README</h2>
<div style="position:relative">
<pre id="badge-md" style="user-select:all">{badge_md_escaped}</pre>
<button onclick="navigator.clipboard.writeText(document.getElementById('badge-md').textContent).then(()=>this.textContent='Copied!')" style="position:absolute;top:8px;right:8px;padding:4px 12px;background:#0d9488;color:#fff;border:none;font-size:12px;cursor:pointer;font-family:system-ui,sans-serif">Copy</button>
</div>
</div>

<div class="section">
<h2>Share</h2>
<a href="{tweet_url}" target="_blank" rel="noopener" style="display:inline-block;padding:8px 20px;background:#1da1f2;color:#fff;font-size:14px;font-weight:600;text-decoration:none">Share on Twitter</a>
<a href="/kya/{_esc(name)}" style="display:inline-block;padding:8px 20px;border:1px solid #e5e7eb;font-size:14px;font-weight:600;margin-left:8px">View full KYA report</a>
</div>
"""
            else:
                # Not found — show submission form
                result_html = f"""
<div class="card" style="margin-top:16px">
<h3>Agent not found</h3>
<p class="desc">We don't have <strong>{_esc(q.strip())}</strong> in our index yet. Submit it for review:</p>
<form method="post" action="/claim/submit" style="margin-top:12px">
<div style="margin-bottom:8px">
<label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">Agent name</label>
<input type="text" name="name" value="{_esc(q.strip())}" style="width:100%;padding:8px 12px;border:1px solid #e5e7eb;font-size:14px;font-family:system-ui,sans-serif">
</div>
<div style="margin-bottom:12px">
<label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">GitHub URL</label>
<input type="text" name="github_url" placeholder="https://github.com/..." style="width:100%;padding:8px 12px;border:1px solid #e5e7eb;font-size:14px;font-family:system-ui,sans-serif">
</div>
<button type="submit" style="padding:8px 20px;background:#0d9488;color:#fff;border:none;font-size:14px;font-weight:600;cursor:pointer;font-family:system-ui,sans-serif">Submit for review</button>
</form>
</div>
"""
        finally:
            session.close()

    # Featured agents section
    featured_html = ""
    try:
        session = get_session()
        try:
            featured = _featured_agents(session)
            if featured:
                cards = ""
                for f in featured:
                    fname = f["name"] or "—"
                    fscore = f.get("trust_score")
                    fgrade = f.get("grade") or "—"
                    fcat = f.get("category") or "—"
                    cards += f"""<div class="card" style="display:flex;align-items:center;justify-content:space-between">
<div>
<strong><a href="/kya/{_esc(fname)}">{_esc(fname)}</a></strong>
<span class="desc" style="margin-left:8px">{_esc(fcat)}</span>
</div>
<div style="display:flex;align-items:center;gap:12px">
{_score_pill(fscore)}
<span style="font-size:13px;color:#6b7280">{_esc(fgrade)}</span>
<img src="/badge/{_esc(fname)}" alt="" style="max-height:20px">
</div>
</div>"""

                featured_html = f"""
<div class="section" style="margin-top:32px">
<h2>Recently scouted</h2>
<p class="desc">Agents evaluated by the Nerq Scout in the last 24 hours.</p>
{cards}
</div>
"""
        finally:
            session.close()
    except Exception:
        pass

    body = f"{search_html}{result_html}{featured_html}"

    return HTMLResponse(nerq_page(
        title="Claim your Nerq Trust Badge",
        body=body,
        description="Look up your AI agent's trust score and embed a Nerq Trust Badge in your README.",
        canonical="https://nerq.ai/claim",
    ))


# ── POST /claim/submit ───────────────────────────────────────

@router_claim.post("/claim/submit", response_class=HTMLResponse)
async def claim_submit(request: Request):
    """Accept agent submission for review."""
    try:
        form = await request.form()
        name = (form.get("name") or "").strip()
        github_url = (form.get("github_url") or "").strip()
    except Exception:
        return HTMLResponse(nerq_page(
            title="Error",
            body="<h1>Error</h1><p>Could not process your submission.</p>",
        ), status_code=400)

    if not name:
        return HTMLResponse(nerq_page(
            title="Error",
            body="<h1>Error</h1><p>Agent name is required.</p>",
        ), status_code=400)

    session = get_write_session()
    try:
        session.execute(text("""
            INSERT INTO nerq_scout_log (event_type, agent_name, details)
            VALUES ('claim_submit', :name, :details)
        """), {
            "name": name,
            "details": json.dumps({
                "github_url": github_url,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }),
        })
        session.commit()
    except Exception as e:
        session.rollback()
        return HTMLResponse(nerq_page(
            title="Error",
            body=f"<h1>Error</h1><p>Could not save submission: {_esc(str(e))}</p>",
        ), status_code=500)
    finally:
        session.close()

    body = f"""
<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/claim">claim</a> &rsaquo; submitted</div>
<h1>Thank you</h1>
<p style="margin:12px 0">We received your submission for <strong>{_esc(name)}</strong>.</p>
<p class="desc">The Nerq Scout will evaluate it in the next cycle. Check back soon at:</p>
<p><a href="/kya/{_esc(name)}">/kya/{_esc(name)}</a></p>
<p style="margin-top:20px"><a href="/claim">&larr; Back to claim page</a></p>
"""

    return HTMLResponse(nerq_page(
        title=f"Submitted: {name}",
        body=body,
        description=f"Agent {name} submitted for Nerq Trust evaluation.",
    ))
