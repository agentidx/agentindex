"""
Nerq Compliance Pages
======================
SEO-optimized compliance hub, jurisdiction detail pages, and API docs.

Covers 52 jurisdictions from the jurisdiction_registry table.

Usage in discovery.py:
    from agentindex.compliance_pages import mount_compliance_pages
    mount_compliance_pages(app)
"""

import html
import json
import logging
from datetime import date

from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, nerq_page, nerq_head

logger = logging.getLogger("nerq.compliance_pages")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()

# ── In-memory cache ─────────────────────────────────────────
_jurisdictions = []  # list of dicts
_jurisdictions_by_id = {}  # id -> dict
_loaded = False


def _load_jurisdictions():
    """Load jurisdiction_registry once into memory."""
    global _jurisdictions, _jurisdictions_by_id, _loaded
    if _loaded:
        return
    try:
        session = get_session()
        rows = session.execute(text("""
            SELECT id, name, region, country, status, effective_date,
                   risk_model, risk_classes, high_risk_criteria, requirements,
                   penalty_max, penalty_per_violation, focus, source_url,
                   last_checked, last_updated, changelog
            FROM jurisdiction_registry
            ORDER BY name
        """)).fetchall()
        cols = ["id", "name", "region", "country", "status", "effective_date",
                "risk_model", "risk_classes", "high_risk_criteria", "requirements",
                "penalty_max", "penalty_per_violation", "focus", "source_url",
                "last_checked", "last_updated", "changelog"]
        _jurisdictions = [dict(zip(cols, r)) for r in rows]
        _jurisdictions_by_id = {j["id"]: j for j in _jurisdictions}
        _loaded = True
        session.close()
        logger.info(f"Loaded {len(_jurisdictions)} jurisdictions")
    except Exception as e:
        logger.error(f"Failed to load jurisdictions: {e}")


def _esc(s):
    """HTML-escape a value."""
    if s is None:
        return ""
    return html.escape(str(s))


def _esc_json(s):
    """Escape for use inside JSON strings."""
    if s is None:
        return ""
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")


def _make_slug(name):
    """Convert agent name to URL slug."""
    return name.lower().replace(" ", "-")


def _fmt_penalty(p):
    """Format penalty value for display."""
    if not p:
        return "N/A"
    s = str(p)
    # If it's a number, format with commas
    try:
        n = float(s.replace(",", "").replace("$", "").replace("€", "").replace("£", ""))
        if n >= 1_000_000:
            return f"€{n/1_000_000:.0f}M"
        if n >= 1_000:
            return f"€{n/1_000:.0f}K"
        return f"€{n:.0f}"
    except (ValueError, TypeError):
        return _esc(s)


def _status_pill(status):
    """Return CSS class for status pill."""
    if not status:
        return "pill-gray"
    s = str(status).lower()
    if s in ("enacted", "effective", "in force", "active"):
        return "pill-green"
    if s in ("proposed", "draft", "pending"):
        return "pill-yellow"
    return "pill-gray"


def _risk_pill(risk_class):
    """Return CSS class for risk class pill."""
    if not risk_class:
        return "pill-gray"
    r = str(risk_class).lower()
    if r in ("high", "unacceptable"):
        return "pill-red"
    if r in ("limited",):
        return "pill-yellow"
    if r in ("minimal",):
        return "pill-green"
    return "pill-gray"


# ── JSON for template rendering ─────────────────────────────
def _parse_json(val):
    """Parse a JSON column value (may be string, dict, list, or None)."""
    if val is None:
        return []
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


# ═══════════════════════════════════════════════════════════════
# MOUNT
# ═══════════════════════════════════════════════════════════════
def mount_compliance_pages(app):
    """Mount compliance SEO pages onto the FastAPI app."""

    # ── TASK 1: Hub page ──────────────────────────────────────
    @app.get("/compliance", response_class=HTMLResponse)
    async def compliance_hub():
        _load_jurisdictions()
        total = len(_jurisdictions)

        # Agent stats
        try:
            session = get_session()
            stats = session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE eu_risk_class IS NOT NULL) as assessed,
                    COUNT(*) FILTER (WHERE eu_risk_class = 'minimal') as minimal,
                    COUNT(*) FILTER (WHERE eu_risk_class = 'high') as high,
                    COUNT(*) FILTER (WHERE eu_risk_class = 'limited') as limited
                FROM agents
            """)).fetchone()
            assessed = stats[0] or 0
            minimal = stats[1] or 0
            high_count = stats[2] or 0
            limited = stats[3] or 0
            session.close()
        except Exception:
            assessed, minimal, high_count, limited = 41734, 41126, 401, 207

        title = f"AI Agent Compliance — {total} Jurisdictions Covered"
        desc = (f"Nerq covers {total} AI regulation jurisdictions worldwide. "
                f"{assessed:,} agents assessed for compliance across EU AI Act, "
                f"US state laws, and global frameworks.")
        canonical = f"{SITE}/compliance"

        # Build jurisdiction table rows
        rows_html = ""
        for j in _jurisdictions:
            pill = _status_pill(j["status"])
            rows_html += f"""<tr>
<td><a href="/compliance/{_esc(j['id'])}">{_esc(j['name'])}</a></td>
<td>{_esc(j['region'])} / {_esc(j['country'])}</td>
<td><span class="pill {pill}">{_esc(j['status'])}</span></td>
<td>{_esc(j['effective_date'])}</td>
<td>{_esc(j['focus'])}</td>
<td>{_fmt_penalty(j['penalty_max'])}</td>
</tr>"""

        # JSON-LD: WebPage + ItemList + FAQPage
        item_list = [{
            "@type": "ListItem",
            "position": i + 1,
            "name": _esc_json(j["name"]),
            "url": f"{SITE}/compliance/{j['id']}"
        } for i, j in enumerate(_jurisdictions)]

        jsonld = json.dumps([
            {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": title,
                "description": desc,
                "url": canonical,
                "publisher": {
                    "@type": "Organization",
                    "name": "Nerq",
                    "url": SITE
                },
                "dateModified": TODAY
            },
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "name": "AI Regulation Jurisdictions",
                "numberOfItems": total,
                "itemListElement": item_list
            },
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": "How many jurisdictions does Nerq cover?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f"Nerq covers {total} AI regulation jurisdictions worldwide, including the EU AI Act, US state laws, and regulations across Asia, Latin America, and the Middle East."
                        }
                    },
                    {
                        "@type": "Question",
                        "name": "Does Nerq support EU AI Act compliance?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f"Yes. Nerq has assessed {assessed:,} AI agents against the EU AI Act risk classification framework, identifying {high_count} high-risk, {limited} limited-risk, and {minimal:,} minimal-risk agents."
                        }
                    },
                    {
                        "@type": "Question",
                        "name": "Can Nerq help with AI regulation?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": f"Nerq provides automated compliance checking across {total} jurisdictions. Use the Compliance API to check any AI agent against applicable regulations and receive risk classifications, gap analysis, and remediation guidance."
                        }
                    }
                ]
            },
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Nerq", "item": SITE},
                    {"@type": "ListItem", "position": 2, "name": "Compliance", "item": canonical}
                ]
            }
        ], separators=(",", ":"))

        body = f"""
<div class="breadcrumb"><a href="/">Nerq</a> / Compliance</div>

<div style="background:#f0fdfa;border:1px solid #99f6e4;padding:14px 18px;margin:12px 0 20px;font-size:14px;line-height:1.6" data-ai-summary="true">
<strong>AI Summary:</strong> Nerq tracks AI agent compliance across {total} jurisdictions worldwide.
{assessed:,} agents have been assessed for regulatory compliance, with risk classifications
spanning minimal ({minimal:,}), limited ({limited}), and high ({high_count}) risk categories.
Coverage includes the EU AI Act, US state-level AI laws, and regulations from {len(set(j['region'] for j in _jurisdictions if j.get('region')))} global regions.
</div>

<h1>{_esc(title)}</h1>
<p class="desc">Real-time compliance tracking for AI agents across global regulatory frameworks.</p>

<div class="stat-row">
<div class="stat-item"><div class="num">{total}</div><div class="label">Jurisdictions</div></div>
<div class="stat-item"><div class="num">{assessed:,}</div><div class="label">Agents Assessed</div></div>
<div class="stat-item"><div class="num">{minimal:,}</div><div class="label">Minimal Risk</div></div>
<div class="stat-item"><div class="num">{limited}</div><div class="label">Limited Risk</div></div>
<div class="stat-item"><div class="num">{high_count}</div><div class="label">High Risk</div></div>
</div>

<h2>All Jurisdictions</h2>
<div style="overflow-x:auto">
<table>
<thead><tr><th>Jurisdiction</th><th>Region / Country</th><th>Status</th><th>Effective Date</th><th>Focus</th><th>Max Penalty</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>

<h2>Compliance API</h2>
<p class="desc">Programmatic compliance checking is available via the <a href="/compliance/api">Compliance API</a>.
Check any agent against all {total} jurisdictions with a single API call.</p>

<h2>Frequently Asked Questions</h2>
<h3>How many jurisdictions does Nerq cover?</h3>
<p>Nerq covers {total} AI regulation jurisdictions worldwide, including the EU AI Act, US state laws, and regulations across Asia, Latin America, and the Middle East.</p>
<h3>Does Nerq support EU AI Act compliance?</h3>
<p>Yes. Nerq has assessed {assessed:,} AI agents against the EU AI Act risk classification framework, identifying {high_count} high-risk, {limited} limited-risk, and {minimal:,} minimal-risk agents.</p>
<h3>Can Nerq help with AI regulation?</h3>
<p>Nerq provides automated compliance checking across {total} jurisdictions. Use the <a href="/compliance/api">Compliance API</a> to check any AI agent against applicable regulations and receive risk classifications, gap analysis, and remediation guidance.</p>
"""

        page = f"""{nerq_head(title, desc, canonical)}
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nerq">
<script type="application/ld+json">{jsonld}</script>
<main class="container" style="padding-top:20px;padding-bottom:40px">
{body}
</main>
{NERQ_FOOTER}
</body></html>"""
        return HTMLResponse(page)

    # ── TASK 2: Individual jurisdiction page ──────────────────
    @app.get("/compliance/{slug}", response_class=HTMLResponse)
    async def compliance_jurisdiction(slug: str):
        # Skip routes handled by compliance API router
        if slug in ("api",):
            return await compliance_api_docs()
        if slug in ("check", "agent", "deadlines", "stats", "subscribe",
                     "track-upgrade", "multi-check", "jurisdictions", "changelog",
                     "mica", "badge"):
            return HTMLResponse(status_code=404, content="Not found")

        _load_jurisdictions()
        j = _jurisdictions_by_id.get(slug)
        if not j:
            return HTMLResponse("<h1>Jurisdiction not found</h1>", status_code=404)

        name = j["name"]
        title = f"AI Agent Compliance: {_esc(name)}"
        desc = (f"Compliance requirements for AI agents under {_esc(name)}. "
                f"Status: {_esc(j['status'])}. Focus: {_esc(j['focus'])}. "
                f"Assessed by Nerq across 41,000+ agents.")
        canonical = f"{SITE}/compliance/{slug}"

        # Parse JSON fields
        risk_classes = _parse_json(j.get("risk_classes"))
        high_risk_criteria = _parse_json(j.get("high_risk_criteria"))
        requirements = _parse_json(j.get("requirements"))

        # Agent risk distribution
        try:
            session = get_session()
            dist = session.execute(text("""
                SELECT eu_risk_class, COUNT(*) as cnt
                FROM agents
                WHERE eu_risk_class IS NOT NULL
                GROUP BY eu_risk_class
                ORDER BY cnt DESC
            """)).fetchall()
            dist_data = {r[0]: r[1] for r in dist}

            # Top 10 agents by compliance score
            top_agents = session.execute(text("""
                SELECT name, compliance_score, eu_risk_class,
                       COALESCE(trust_score_v2, trust_score) as trust_score
                FROM agents
                WHERE eu_risk_class IS NOT NULL
                ORDER BY compliance_score DESC, trust_score DESC
                LIMIT 10
            """)).fetchall()
            session.close()
        except Exception as e:
            logger.error(f"DB query failed for {slug}: {e}")
            dist_data = {"minimal": 41126, "high": 401, "limited": 207}
            top_agents = []

        # Status pill
        pill = _status_pill(j["status"])

        # Build overview section
        overview = f"""
<div class="card">
<h3>Overview</h3>
<table>
<tr><td style="width:160px;color:#6b7280;font-weight:600">Status</td><td><span class="pill {pill}">{_esc(j['status'])}</span></td></tr>
<tr><td style="color:#6b7280;font-weight:600">Effective Date</td><td>{_esc(j['effective_date'])}</td></tr>
<tr><td style="color:#6b7280;font-weight:600">Region</td><td>{_esc(j['region'])}</td></tr>
<tr><td style="color:#6b7280;font-weight:600">Country</td><td>{_esc(j['country'])}</td></tr>
<tr><td style="color:#6b7280;font-weight:600">Focus Area</td><td>{_esc(j['focus'])}</td></tr>
<tr><td style="color:#6b7280;font-weight:600">Max Penalty</td><td>{_fmt_penalty(j['penalty_max'])}</td></tr>"""
        if j.get("penalty_per_violation"):
            overview += f"""
<tr><td style="color:#6b7280;font-weight:600">Per Violation</td><td>{_fmt_penalty(j['penalty_per_violation'])}</td></tr>"""
        if j.get("source_url"):
            overview += f"""
<tr><td style="color:#6b7280;font-weight:600">Source</td><td><a href="{_esc(j['source_url'])}" target="_blank" rel="noopener">Official text</a></td></tr>"""
        overview += "\n</table>\n</div>"

        # Description based on focus and status
        focus_desc = ""
        focus = j.get("focus") or ""
        status = j.get("status") or ""
        if focus or status:
            focus_desc = f"""<p class="desc">{_esc(name)} is a {'currently ' + _esc(status).lower() if status else ''} regulation
focused on {_esc(focus).lower() if focus else 'AI governance'} in {_esc(j['country'] or j['region'] or 'this jurisdiction')}.
{'It establishes a risk-based framework for AI systems' if j.get('risk_model') else 'It sets regulatory requirements for AI systems'}
{' with penalties up to ' + _fmt_penalty(j['penalty_max']) + ' for non-compliance' if j.get('penalty_max') else ''}.</p>"""

        # Risk model section
        risk_section = ""
        if j.get("risk_model"):
            risk_section += f"""
<h2>Risk Model</h2>
<p class="desc">{_esc(j['risk_model'])}</p>"""
        if risk_classes:
            risk_section += "\n<h3>Risk Classes</h3>\n<ul>"
            if isinstance(risk_classes, list):
                for rc in risk_classes:
                    if isinstance(rc, dict):
                        rname = rc.get("name", rc.get("class", ""))
                        rdesc = rc.get("description", "")
                        risk_section += f"\n<li><strong>{_esc(rname)}</strong>{' — ' + _esc(rdesc) if rdesc else ''}</li>"
                    else:
                        risk_section += f"\n<li>{_esc(str(rc))}</li>"
            elif isinstance(risk_classes, dict):
                for k, v in risk_classes.items():
                    risk_section += f"\n<li><strong>{_esc(k)}</strong> — {_esc(str(v))}</li>"
            risk_section += "\n</ul>"

        # High-risk criteria
        if high_risk_criteria:
            risk_section += "\n<h3>High-Risk Criteria</h3>\n<ul>"
            for c in (high_risk_criteria if isinstance(high_risk_criteria, list) else [high_risk_criteria]):
                risk_section += f"\n<li>{_esc(str(c))}</li>"
            risk_section += "\n</ul>"

        # Requirements section
        req_section = ""
        if requirements:
            req_section = "\n<h2>Requirements</h2>\n<ul>"
            for r in (requirements if isinstance(requirements, list) else [requirements]):
                req_section += f"\n<li>{_esc(str(r))}</li>"
            req_section += "\n</ul>"

        # Agent distribution
        dist_html = """
<h2>Agent Risk Distribution</h2>
<div class="stat-row">"""
        for rc, cnt in sorted(dist_data.items(), key=lambda x: -x[1]):
            rp = _risk_pill(rc)
            dist_html += f"""
<div class="stat-item"><div class="num">{cnt:,}</div><div class="label"><span class="pill {rp}">{_esc(rc)}</span></div></div>"""
        dist_html += "\n</div>"

        # Top agents table
        agents_html = ""
        if top_agents:
            agents_html = """
<h2>Top Agents by Compliance Score</h2>
<table>
<thead><tr><th>Agent</th><th>Compliance</th><th>Risk Class</th><th>Trust Score</th></tr></thead>
<tbody>"""
            for a in top_agents:
                a_name = a[0] or "Unknown"
                a_score = a[1]
                a_risk = a[2]
                a_trust = a[3]
                a_slug = _make_slug(a_name)
                rp = _risk_pill(a_risk)
                agents_html += f"""<tr>
<td><a href="/safe/{_esc(a_slug)}">{_esc(a_name)}</a></td>
<td>{f'{a_score:.1f}' if a_score else 'N/A'}</td>
<td><span class="pill {rp}">{_esc(a_risk)}</span></td>
<td>{f'{a_trust:.1f}' if a_trust else 'N/A'}</td>
</tr>"""
            agents_html += "\n</tbody></table>"

        # FAQs
        faq1_q = f"What are the compliance requirements under {_esc_json(name)}?"
        faq1_a = (f"{_esc_json(name)} requires AI systems to meet specific regulatory standards"
                  f"{' focused on ' + _esc_json(focus) if focus else ''}. "
                  f"Nerq automatically checks AI agents against these requirements.")
        faq2_q = f"How does {_esc_json(name)} classify AI risk?"
        faq2_a = (f"{_esc_json(name)} "
                  f"{'uses a risk-based classification: ' + _esc_json(j.get('risk_model', '')) if j.get('risk_model') else 'establishes requirements for AI systems'}. "
                  f"Nerq maps each agent to the applicable risk class.")
        faq3_q = f"What are the penalties under {_esc_json(name)}?"
        faq3_a = (f"Non-compliance with {_esc_json(name)} can result in penalties"
                  f"{' up to ' + str(j['penalty_max']) if j.get('penalty_max') else ''}. "
                  f"Use Nerq to identify compliance gaps before enforcement.")

        jsonld = json.dumps([
            {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": title,
                "description": desc,
                "url": canonical,
                "publisher": {"@type": "Organization", "name": "Nerq", "url": SITE},
                "dateModified": TODAY
            },
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": faq1_q,
                     "acceptedAnswer": {"@type": "Answer", "text": faq1_a}},
                    {"@type": "Question", "name": faq2_q,
                     "acceptedAnswer": {"@type": "Answer", "text": faq2_a}},
                    {"@type": "Question", "name": faq3_q,
                     "acceptedAnswer": {"@type": "Answer", "text": faq3_a}}
                ]
            },
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Nerq", "item": SITE},
                    {"@type": "ListItem", "position": 2, "name": "Compliance", "item": f"{SITE}/compliance"},
                    {"@type": "ListItem", "position": 3, "name": _esc_json(name), "item": canonical}
                ]
            }
        ], separators=(",", ":"))

        body = f"""
<div class="breadcrumb"><a href="/">Nerq</a> / <a href="/compliance">Compliance</a> / {_esc(name)}</div>

<div style="background:#f0fdfa;border:1px solid #99f6e4;padding:14px 18px;margin:12px 0 20px;font-size:14px;line-height:1.6" data-ai-summary="true">
<strong>AI Summary:</strong> {_esc(name)} is {('an ' + _esc(status).lower()) if status else 'a'} AI regulation
in {_esc(j['country'] or j['region'] or 'this jurisdiction')}
{('focused on ' + _esc(focus).lower()) if focus else ''}.
{('Maximum penalty: ' + _fmt_penalty(j['penalty_max']) + '.') if j.get('penalty_max') else ''}
Nerq has assessed {sum(dist_data.values()):,} agents against applicable risk classifications.
</div>

<h1>{_esc(title)}</h1>
{focus_desc}

{overview}
{risk_section}
{req_section}
{dist_html}
{agents_html}

<h2>Frequently Asked Questions</h2>
<h3>{_esc(faq1_q)}</h3>
<p>{_esc(faq1_a.replace(_esc_json(name), name))}</p>
<h3>{_esc(faq2_q)}</h3>
<p>{_esc(faq2_a.replace(_esc_json(name), name))}</p>
<h3>{_esc(faq3_q)}</h3>
<p>{_esc(faq3_a.replace(_esc_json(name), name))}</p>

<p style="margin-top:24px"><a href="/compliance">&larr; All jurisdictions</a></p>
"""

        page = f"""{nerq_head(title, desc, canonical)}
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<script type="application/ld+json">{jsonld}</script>
<main class="container" style="padding-top:20px;padding-bottom:40px">
{body}
</main>
{NERQ_FOOTER}
</body></html>"""
        return HTMLResponse(page)

    # ── TASK 5: API documentation page ────────────────────────
    async def compliance_api_docs():
        title = "Compliance API Documentation"
        desc = ("Nerq Compliance API — check AI agents against 52 jurisdictions. "
                "Endpoints for single-agent checks, multi-jurisdiction scans, deadlines, and stats.")
        canonical = f"{SITE}/compliance/api"

        jsonld = json.dumps([
            {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": title,
                "description": desc,
                "url": canonical,
                "publisher": {"@type": "Organization", "name": "Nerq", "url": SITE},
                "dateModified": TODAY
            },
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Nerq", "item": SITE},
                    {"@type": "ListItem", "position": 2, "name": "Compliance", "item": f"{SITE}/compliance"},
                    {"@type": "ListItem", "position": 3, "name": "API Docs", "item": canonical}
                ]
            }
        ], separators=(",", ":"))

        body = f"""
<div class="breadcrumb"><a href="/">Nerq</a> / <a href="/compliance">Compliance</a> / API Docs</div>

<h1>{_esc(title)}</h1>
<p class="desc">Programmatic compliance checking for AI agents across 52 global jurisdictions.
All endpoints accept and return JSON. Authentication via API key in the <code>X-API-Key</code> header.</p>

<h2><span class="method method-post">POST</span> <span class="ep">/compliance/check</span></h2>
<p>Check a single agent against all applicable jurisdictions.</p>
<h3>Request Body</h3>
<pre>{{
  "agent_id": "uuid-of-agent",
  "jurisdictions": ["eu_ai_act", "us_co_sb205"],  // optional filter
  "include_remediation": true                       // optional
}}</pre>
<h3>Response</h3>
<pre>{{
  "agent_id": "uuid-of-agent",
  "agent_name": "example-agent",
  "overall_status": "partially_compliant",
  "jurisdictions": [
    {{
      "id": "eu_ai_act",
      "name": "EU AI Act",
      "risk_class": "high",
      "status": "non_compliant",
      "gaps": ["missing risk assessment", "no human oversight mechanism"],
      "remediation": ["Implement risk assessment procedure", "Add human-in-the-loop"]
    }}
  ],
  "checked_at": "2026-03-12T00:00:00Z"
}}</pre>
<h3>curl Example</h3>
<pre>curl -X POST https://nerq.ai/compliance/check \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: your-api-key" \\
  -d '{{"agent_id": "your-agent-uuid"}}'</pre>

<h2><span class="method method-get">GET</span> <span class="ep">/compliance/agent/{{agent_id}}</span></h2>
<p>Get the stored compliance status for a specific agent across all jurisdictions.</p>
<h3>curl Example</h3>
<pre>curl https://nerq.ai/compliance/agent/your-agent-uuid \\
  -H "X-API-Key: your-api-key"</pre>
<h3>Response</h3>
<pre>{{
  "agent_id": "uuid",
  "agent_name": "example-agent",
  "eu_risk_class": "minimal",
  "compliance_score": 87.5,
  "jurisdictions": [
    {{
      "id": "eu_ai_act",
      "name": "EU AI Act",
      "status": "compliant",
      "risk_level": "minimal"
    }}
  ],
  "last_checked": "2026-03-12T00:00:00Z"
}}</pre>

<h2><span class="method method-get">GET</span> <span class="ep">/compliance/deadlines</span></h2>
<p>List upcoming compliance deadlines across all jurisdictions.</p>
<h3>curl Example</h3>
<pre>curl https://nerq.ai/compliance/deadlines \\
  -H "X-API-Key: your-api-key"</pre>
<h3>Response</h3>
<pre>{{
  "deadlines": [
    {{
      "jurisdiction_id": "eu_ai_act",
      "jurisdiction_name": "EU AI Act",
      "effective_date": "2025-08-02",
      "status": "effective",
      "days_until": -222
    }}
  ]
}}</pre>

<h2><span class="method method-get">GET</span> <span class="ep">/compliance/stats</span></h2>
<p>Aggregate compliance statistics across all assessed agents.</p>
<h3>curl Example</h3>
<pre>curl https://nerq.ai/compliance/stats \\
  -H "X-API-Key: your-api-key"</pre>
<h3>Response</h3>
<pre>{{
  "total_agents_assessed": 41734,
  "jurisdictions_covered": 52,
  "risk_distribution": {{
    "minimal": 41126,
    "limited": 207,
    "high": 401
  }},
  "average_compliance_score": 72.3
}}</pre>

<h2><span class="method method-post">POST</span> <span class="ep">/compliance/multi-check</span></h2>
<p>Check multiple agents in a single request. Maximum 50 agents per call.</p>
<h3>Request Body</h3>
<pre>{{
  "agent_ids": ["uuid-1", "uuid-2", "uuid-3"],
  "jurisdictions": ["eu_ai_act"]  // optional filter
}}</pre>
<h3>curl Example</h3>
<pre>curl -X POST https://nerq.ai/compliance/multi-check \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: your-api-key" \\
  -d '{{"agent_ids": ["uuid-1", "uuid-2"]}}'</pre>
<h3>Response</h3>
<pre>{{
  "results": [
    {{
      "agent_id": "uuid-1",
      "agent_name": "agent-one",
      "overall_status": "compliant",
      "jurisdictions": [...]
    }},
    {{
      "agent_id": "uuid-2",
      "agent_name": "agent-two",
      "overall_status": "non_compliant",
      "jurisdictions": [...]
    }}
  ],
  "checked_at": "2026-03-12T00:00:00Z"
}}</pre>

<p style="margin-top:24px"><a href="/compliance">&larr; Back to Compliance Hub</a></p>
"""

        page = f"""{nerq_head(title, desc, canonical)}
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nerq">
<script type="application/ld+json">{jsonld}</script>
<main class="container" style="padding-top:20px;padding-bottom:40px">
{body}
</main>
{NERQ_FOOTER}
</body></html>"""
        return HTMLResponse(page)

    # ── Sitemap ───────────────────────────────────────────────
    @app.get("/sitemap-compliance.xml", response_class=Response)
    async def sitemap_compliance():
        _load_jurisdictions()

        urls = []
        # Hub page
        urls.append(f"""<url><loc>{SITE}/compliance</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>""")

        # Individual jurisdiction pages
        for j in _jurisdictions:
            urls.append(f"""<url><loc>{SITE}/compliance/{_esc(j['id'])}</loc><lastmod>{TODAY}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>""")

        # API docs
        urls.append(f"""<url><loc>{SITE}/compliance/api</loc><lastmod>{TODAY}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>""")

        # MICA page (exists on zarq.ai, include in sitemap)
        urls.append(f"""<url><loc>{SITE}/compliance/mica</loc><lastmod>{TODAY}</lastmod><changefreq>monthly</changefreq><priority>0.7</priority></url>""")

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{''.join(urls)}
</urlset>"""
        return Response(content=xml, media_type="application/xml")

    logger.info("Compliance pages mounted: /compliance, /compliance/{slug}, /compliance/api, /sitemap-compliance.xml")
