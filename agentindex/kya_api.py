"""
KYA — Know Your Agent
Public due diligence endpoint for AI agents.
Route: /v1/agent/kya/{agent_id_or_name}
HTML: /kya, /kya/{agent_name}
Zero auth, zero rate limit.
"""

import os
import re
import sqlite3
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, JSONResponse

from agentindex.db.models import get_session
from sqlalchemy import text

CRYPTO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto", "crypto_trust.db")

router_kya = APIRouter(tags=["kya"])


def _is_uuid(s: str) -> bool:
    try:
        UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


def _risk_label(trust_score, compliance_score):
    """Compute risk level from scores."""
    if trust_score is None:
        return "UNKNOWN"
    if trust_score >= 60 and (compliance_score or 0) >= 40:
        return "TRUSTED"
    if trust_score >= 35:
        return "CAUTION"
    return "UNTRUSTED"


def _zarq_check(token_id: str) -> dict | None:
    """If agent is associated with a crypto token, get ZARQ risk data."""
    if not os.path.exists(CRYPTO_DB):
        return None
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT s.trust_score, s.risk_level, s.ndd_current, s.structural_weakness,
                   r.rating, c.crash_prob_v3
            FROM nerq_risk_signals s
            LEFT JOIN crypto_rating_daily r ON s.token_id = r.token_id
                AND r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
            LEFT JOIN (
                SELECT token_id, crash_prob_v3 FROM crash_model_v3_predictions
                WHERE date = (SELECT MAX(date) FROM crash_model_v3_predictions WHERE token_id = ?)
                AND token_id = ?
            ) c ON s.token_id = c.token_id
            WHERE s.token_id = ? AND s.signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
        """, (token_id, token_id, token_id)).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "token_id": token_id,
            "trust_score": round(float(row["trust_score"]), 2) if row["trust_score"] else None,
            "risk_level": row["risk_level"],
            "rating": row["rating"],
            "distance_to_default": round(float(row["ndd_current"]), 2) if row["ndd_current"] else None,
            "crash_probability": round(float(row["crash_prob_v3"]), 4) if row["crash_prob_v3"] else None,
            "structural_weakness": (row["structural_weakness"] or 0) >= 2,
        }
    except Exception:
        return None


_KYA_COLS = """id, name, description, source, author, category,
    COALESCE(trust_score_v2, trust_score) as trust_score,
    compliance_score, eu_risk_class, trust_grade,
    first_indexed, is_verified, is_active,
    stars, downloads, protocols, frameworks, source_url, license"""


def _lookup_agent(identifier: str) -> dict | None:
    """Look up agent by UUID or name search.
    Runs all match strategies and returns the highest trust-scored result.
    """
    session = get_session()
    try:
        if _is_uuid(identifier):
            row = session.execute(text(f"""
                SELECT {_KYA_COLS}
                FROM entity_lookup WHERE id = :id AND is_active = true
            """), {"id": identifier}).fetchone()
            return dict(row._mapping) if row else None

        clean = identifier.replace("-", " ").replace("_", " ")
        row = session.execute(text(f"""
            SELECT {_KYA_COLS} FROM (
                SELECT id, name, description, source, author, category, trust_score, trust_score_v2,
                       compliance_score, eu_risk_class, trust_grade, first_indexed, is_verified,
                       is_active, stars, downloads, protocols, frameworks, source_url, license, 1 AS _rank
                FROM entity_lookup WHERE name_lower = lower(:name) AND is_active = true
              UNION ALL
                SELECT id, name, description, source, author, category, trust_score, trust_score_v2,
                       compliance_score, eu_risk_class, trust_grade, first_indexed, is_verified,
                       is_active, stars, downloads, protocols, frameworks, source_url, license, 1 AS _rank
                FROM entity_lookup WHERE name_lower = lower(:clean) AND is_active = true
                AND :clean != :name
              UNION ALL
                SELECT id, name, description, source, author, category, trust_score, trust_score_v2,
                       compliance_score, eu_risk_class, trust_grade, first_indexed, is_verified,
                       is_active, stars, downloads, protocols, frameworks, source_url, license, 2 AS _rank
                FROM entity_lookup WHERE name_lower LIKE lower(:suffix) AND is_active = true
              UNION ALL
                SELECT id, name, description, source, author, category, trust_score, trust_score_v2,
                       compliance_score, eu_risk_class, trust_grade, first_indexed, is_verified,
                       is_active, stars, downloads, protocols, frameworks, source_url, license, 3 AS _rank
                FROM entity_lookup WHERE name_lower LIKE lower(:pattern) AND is_active = true
            ) sub
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST,
                     stars DESC NULLS LAST
            LIMIT 1
        """), {
            "name": identifier,
            "clean": clean,
            "suffix": f"%/{identifier}",
            "pattern": f"%{identifier}%",
        }).fetchone()
        return dict(row._mapping) if row else None
    finally:
        session.close()


@router_kya.get("/v1/agent/kya/{identifier:path}")
def kya_check(identifier: str, response: Response):
    """
    Know Your Agent — Public due diligence report.
    Pass agent UUID or name. Returns trust data, compliance, risk level.
    """
    agent = _lookup_agent(identifier)
    if not agent:
        return JSONResponse(status_code=404, content={
            "error": "Agent not found",
            "detail": f"No active agent matching '{identifier}'.",
            "hint": "Try the agent name or UUID. Search at zarq.ai/kya",
        })

    trust = agent.get("trust_score")
    compliance = agent.get("compliance_score")
    risk_level = _risk_label(trust, compliance)

    first_indexed = agent.get("first_indexed")
    if first_indexed:
        try:
            fi = datetime.fromisoformat(str(first_indexed))
            days_active = max(1, (datetime.now(timezone.utc) - fi.replace(tzinfo=timezone.utc)).days)
        except Exception:
            days_active = None
    else:
        days_active = None

    # Check for crypto association (by name matching)
    agent_name_lower = (agent.get("name") or "").lower()
    zarq = None
    crypto_keywords = ["bitcoin", "ethereum", "solana", "token", "defi", "swap", "bridge", "wallet"]
    if any(kw in agent_name_lower for kw in crypto_keywords):
        for token in ["bitcoin", "ethereum", "solana"]:
            if token in agent_name_lower:
                zarq = _zarq_check(token)
                break

    verdict_parts = [f"This agent has been indexed for {days_active or '?'} days"]
    if trust is not None:
        verdict_parts.append(f"with a trust score of {trust:.0f}/100")
    verdict_parts.append(f"[{risk_level}]")
    verdict = " ".join(verdict_parts) + "."

    # Enrichment: CVEs, downloads, license
    security = {"known_cves": 0, "max_severity": None, "has_active_advisory": False}
    popularity_extra = {"npm_weekly_downloads": None, "pypi_weekly_downloads": None}
    license_info = {"license": agent.get("license"), "license_category": None}
    try:
        enr_conn = sqlite3.connect(CRYPTO_DB, timeout=2)
        enr_conn.row_factory = sqlite3.Row
        aid = str(agent["id"])
        cve_row = enr_conn.execute(
            "SELECT COUNT(*) as cnt, MAX(severity) as max_sev, "
            "MAX(CASE WHEN status='open' THEN 1 ELSE 0 END) as active "
            "FROM agent_vulnerabilities WHERE agent_id = ?", (aid,)
        ).fetchone()
        if cve_row and cve_row["cnt"] > 0:
            security = {"known_cves": cve_row["cnt"], "max_severity": cve_row["max_sev"],
                        "has_active_advisory": bool(cve_row["active"])}
        npm_row = enr_conn.execute("SELECT weekly_downloads FROM package_downloads WHERE agent_id = ? AND registry = 'npm'", (aid,)).fetchone()
        pypi_row = enr_conn.execute("SELECT weekly_downloads FROM package_downloads WHERE agent_id = ? AND registry = 'pypi'", (aid,)).fetchone()
        if npm_row: popularity_extra["npm_weekly_downloads"] = npm_row["weekly_downloads"]
        if pypi_row: popularity_extra["pypi_weekly_downloads"] = pypi_row["weekly_downloads"]
        lic_row = enr_conn.execute("SELECT license_spdx, license_category FROM agent_licenses WHERE agent_id = ?", (aid,)).fetchone()
        if lic_row:
            license_info = {"license": lic_row["license_spdx"], "license_category": lic_row["license_category"]}
        enr_conn.close()
    except Exception:
        pass

    result = {
        "agent_id": str(agent["id"]),
        "agent_name": agent.get("name"),
        "description": (agent.get("description") or "")[:500],
        "platform": agent.get("source"),
        "category": agent.get("category"),
        "author": agent.get("author"),
        "trust_score": round(float(trust), 1) if trust else None,
        "compliance_score": round(float(compliance), 1) if compliance else None,
        "eu_risk_class": agent.get("eu_risk_class"),
        "trust_grade": agent.get("trust_grade"),
        "risk_level": risk_level,
        "is_verified": agent.get("is_verified", False),
        "days_active": days_active,
        "stars": agent.get("stars"),
        "downloads": agent.get("downloads"),
        "protocols": agent.get("protocols"),
        "frameworks": agent.get("frameworks"),
        "source_url": agent.get("source_url"),
        "security": security,
        "popularity": popularity_extra,
        "license_info": license_info,
        "zarq_risk_check": zarq,
        "verdict": verdict,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    response.headers["Cache-Control"] = "public, max-age=300"
    return result


# ── HTML Page ──

@router_kya.get("/kya/{identifier:path}", response_class=HTMLResponse)
@router_kya.get("/kya", response_class=HTMLResponse)
@router_kya.get("/know-your-agent", response_class=HTMLResponse)
def kya_page(identifier: str = ""):
    return HTMLResponse(_render_kya_page(identifier))


def _render_kya_page(identifier: str = "") -> str:
    from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER
    og_title = "kya &mdash; know your agent | nerq"
    og_desc = "Free AI agent due diligence. Trust score, compliance, risk level for 204K agents."
    if identifier:
        og_title = f"kya: {identifier} | nerq"
        og_desc = f"Due diligence report for {identifier}."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{og_title}</title>
<meta name="description" content="{og_desc}">
<link rel="canonical" href="https://nerq.ai/kya/{identifier}">
<meta name="robots" content="index, follow">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"WebPage","name":"{og_title}","description":"{og_desc}","url":"https://nerq.ai/kya/{identifier}","provider":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}}}}
</script>
<style>{NERQ_CSS}
.loading{{text-align:center;padding:40px;color:#6b7280}}
.error{{text-align:center;padding:40px;color:#dc2626}}
.row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #e5e7eb;font-size:14px}}
.row:last-child{{border:none}}
.lbl{{color:#6b7280}}
.val{{font-weight:600}}
.verdict{{padding:12px;border:1px solid #e5e7eb;margin-top:12px;font-size:14px}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
<h1>kya &mdash; know your agent</h1>
<p class="desc">Search 204K agents &amp; tools. Free due diligence.</p>
<div class="search-box" style="max-width:500px">
<input type="text" id="agent-input" placeholder="agent name or UUID..." value="{identifier}">
<button onclick="doSearch()">check</button>
</div>
<div id="report" style="margin-top:20px"></div>
<div id="also-checked" style="margin-top:24px;display:none">
<h3 style="font-size:14px;color:#6b7280;margin-bottom:8px">Also checked by visitors</h3>
<div id="also-list" style="display:flex;gap:8px;flex-wrap:wrap"></div>
</div>
</main>
{NERQ_FOOTER}
<script>
const input = document.getElementById('agent-input');
input.addEventListener('keydown', e => {{ if (e.key === 'Enter') doSearch(); }});

function doSearch() {{
    const q = input.value.trim();
    if (!q) return;
    history.pushState(null, '', '/kya/' + encodeURIComponent(q));
    loadReport(q);
}}

async function loadReport(id) {{
    const el = document.getElementById('report');
    el.innerHTML = '<div class="loading">loading...</div>';
    try {{
        const r = await fetch('/v1/agent/kya/' + encodeURIComponent(id));
        if (!r.ok) {{ el.innerHTML = '<div class="error">Agent not found</div>'; return; }}
        render(await r.json());
    }} catch(e) {{ el.innerHTML = '<div class="error">Failed to load</div>'; }}
}}

function render(d) {{
    const rl = d.risk_level;
    const pc = rl === 'TRUSTED' ? 'pill-green' : rl === 'CAUTION' ? 'pill-yellow' : 'pill-red';
    const verified = d.trust_score != null && d.trust_score >= 70;
    const vbadge = verified ? ' <span style="display:inline-flex;align-items:center;gap:4px;background:#ecfdf5;color:#065f46;padding:2px 8px;font-size:12px;font-weight:600;border:1px solid #a7f3d0;vertical-align:middle">&#x2713; Nerq Verified</span>' : '';
    let h = `<div class="card"><h2>${{d.agent_name || 'Unknown'}} <span class="pill ${{pc}}">${{rl}}</span>${{vbadge}}</h2>
<table style="width:100%">
<tr><td class="lbl">Agent ID</td><td class="val"><code>${{d.agent_id}}</code></td></tr>
<tr><td class="lbl">Platform</td><td class="val">${{d.platform || '\u2014'}}</td></tr>
<tr><td class="lbl">Category</td><td class="val">${{d.category || '\u2014'}}</td></tr>
<tr><td class="lbl">Author</td><td class="val">${{d.author || '\u2014'}}</td></tr>
<tr><td class="lbl">Trust Score</td><td class="val">${{d.trust_score != null ? d.trust_score + '/100' : '\u2014'}}</td></tr>
<tr><td class="lbl">Compliance</td><td class="val">${{d.compliance_score != null ? d.compliance_score + '/100' : '\u2014'}}</td></tr>
<tr><td class="lbl">EU Risk Class</td><td class="val">${{d.eu_risk_class || '\u2014'}}</td></tr>
<tr><td class="lbl">Days Active</td><td class="val">${{d.days_active || '\u2014'}}</td></tr>
<tr><td class="lbl">Stars</td><td class="val">${{d.stars || '\u2014'}}</td></tr>`;
    if (d.source_url) h += `<tr><td class="lbl">Source</td><td class="val"><a href="${{d.source_url}}" target="_blank">${{d.source_url.substring(0,60)}}</a></td></tr>`;
    h += `</table>`;

    // Security section
    if (d.security) {{
        const s = d.security;
        const sevColor = {{'CRITICAL':'#dc2626','HIGH':'#ea580c','MEDIUM':'#ca8a04','LOW':'#16a34a'}}[s.max_severity] || '#6b7280';
        h += `<h3 style="margin-top:16px">Security</h3><table style="width:100%">
<tr><td class="lbl">Known CVEs</td><td class="val">${{s.known_cves || 0}}${{s.max_severity ? ' <span style="display:inline-block;padding:1px 6px;font-size:11px;font-weight:600;color:#fff;background:'+sevColor+'">' + s.max_severity + '</span>' : ''}}</td></tr>
<tr><td class="lbl">Active Advisory</td><td class="val">${{s.has_active_advisory ? '\u26a0\ufe0f Yes' : '\u2714\ufe0f No'}}</td></tr></table>`;
    }}
    // License
    if (d.license_info) {{
        const li = d.license_info;
        const licBadge = {{'PERMISSIVE':'\u2705','COPYLEFT':'\u26a0\ufe0f','VIRAL':'\u26d4','UNKNOWN':'\u2753','PROPRIETARY':'\u26a0\ufe0f'}}[li.license_category] || '';
        h += `<tr><td class="lbl">License</td><td class="val">${{li.license || '\u2014'}} ${{licBadge}} ${{li.license_category || ''}}</td></tr>`;
    }}
    // Popularity
    if (d.popularity) {{
        const p = d.popularity;
        if (p.npm_weekly_downloads || p.pypi_weekly_downloads) {{
            h += `<h3 style="margin-top:16px">Popularity</h3><table style="width:100%">`;
            if (p.npm_weekly_downloads) h += `<tr><td class="lbl">npm Downloads/week</td><td class="val">${{p.npm_weekly_downloads.toLocaleString()}}</td></tr>`;
            if (p.pypi_weekly_downloads) h += `<tr><td class="lbl">PyPI Downloads/week</td><td class="val">${{p.pypi_weekly_downloads.toLocaleString()}}</td></tr>`;
            h += `</table>`;
        }}
    }}
    if (d.zarq_risk_check) {{
        const z = d.zarq_risk_check;
        h += `<h3 style="margin-top:16px">ZARQ Crypto Risk</h3><table style="width:100%">
<tr><td class="lbl">Token</td><td class="val">${{z.token_id}}</td></tr>
<tr><td class="lbl">Rating</td><td class="val">${{z.rating}}</td></tr>
<tr><td class="lbl">Risk Level</td><td class="val">${{z.risk_level}}</td></tr>
<tr><td class="lbl">DtD</td><td class="val">${{z.distance_to_default}}</td></tr>
<tr><td class="lbl">Crash Prob</td><td class="val">${{z.crash_probability ? (z.crash_probability * 100).toFixed(1) + '%' : '\u2014'}}</td></tr>
</table>`;
    }}
    h += `<div class="verdict">${{d.verdict}}</div></div>`;
    h += `<p style="font-size:12px;color:#6b7280;margin-top:8px">${{d.checked_at}} &middot; <a href="/v1/agent/kya/${{encodeURIComponent(d.agent_name || d.agent_id)}}">json</a></p>`;
    document.getElementById('report').innerHTML = h;
    // Inject JSON-LD Review schema
    if (d.trust_score != null) {{
        const existing = document.getElementById('kya-jsonld');
        if (existing) existing.remove();
        const s = document.createElement('script');
        s.type = 'application/ld+json';
        s.id = 'kya-jsonld';
        s.textContent = JSON.stringify({{
            "@context": "https://schema.org",
            "@type": "Review",
            "itemReviewed": {{
                "@type": "SoftwareApplication",
                "name": d.agent_name,
                "applicationCategory": "AI Agent"
            }},
            "author": {{"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"}},
            "reviewRating": {{
                "@type": "Rating",
                "ratingValue": d.trust_score,
                "bestRating": 100,
                "worstRating": 0
            }},
            "reviewBody": d.verdict
        }});
        document.head.appendChild(s);
    }}
}}

if ('{identifier}') loadReport('{identifier}');

// Load "also checked" suggestions
const POPULAR = ['langchain','SWE-agent','cursor','harbor','nanoclaw','qlib','chatgpt-on-wechat','strudel-mcp-server','kagent','pentestagent','presenton','ccmanager'];
function showAlsoChecked(current) {{
  const el = document.getElementById('also-list');
  const sec = document.getElementById('also-checked');
  const filtered = POPULAR.filter(n => n.toLowerCase() !== (current||'').toLowerCase()).slice(0,6);
  if (!filtered.length) return;
  el.innerHTML = filtered.map(n => `<a href="/kya/${{encodeURIComponent(n)}}" style="font-size:13px;padding:4px 10px;border:1px solid #e5e7eb;color:#6b7280;text-decoration:none" onmouseover="this.style.borderColor='#0d9488';this.style.color='#0d9488'" onmouseout="this.style.borderColor='#e5e7eb';this.style.color='#6b7280'">${{n}}</a>`).join('');
  sec.style.display = 'block';
}}
if ('{identifier}') showAlsoChecked('{identifier}');
</script>
</body>
</html>"""
