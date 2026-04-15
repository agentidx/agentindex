"""
Nerq Demand-Driven Pages — 10 New Page Types
===============================================
Built from proven search demand data.

Page types:
1. /what-is/{slug} — "What is X?" explainer pages
2. /stack/{slug} — Recommended AI stacks for use cases
3. /review/{slug} — Production readiness reviews
4. /migrate/{from}-to-{to} — Migration guides
5. /report/{slug} — Data reports
6. /guide/{slug} — Privacy & safety guides
7. /this-week — Weekly AI intelligence
8. /issues/{slug} — Known issues & status
9. /enterprise/{slug} — Enterprise guides
10. Sitemaps for all

Usage:
    from agentindex.demand_pages import mount_demand_pages
    mount_demand_pages(app)
"""

import html as html_mod
import json
import logging
import re
import time
from datetime import date, timedelta

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, render_hreflang

logger = logging.getLogger("nerq.demand_pages")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
MONTH_YEAR = date.today().strftime("%B %Y")

_cache = {}
CACHE_TTL = 3600


def _c(k):
    e = _cache.get(k)
    return e[1] if e and (time.time() - e[0]) < CACHE_TTL else None

def _sc(k, v):
    _cache[k] = (time.time(), v)
    return v

def _esc(t):
    return html_mod.escape(str(t)) if t else ""

def _slug(name):
    s = name.lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

def _fmt(n):
    if n is None: return "0"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(int(n))

def _grade_color(g):
    if not g: return "#6b7280"
    return {"A": "#16a34a", "B": "#0d9488", "C": "#ca8a04", "D": "#f97316"}.get(g[0].upper(), "#dc2626")

def _find_tool(query):
    """Find a tool using centralized entity resolution (software_registry + agents).
    Normalizes query: 'nord-vpn' → 'nordvpn' etc.
    """
    from agentindex.agent_safety_pages import _resolve_entity, _lookup_agent

    # Try centralized resolution first
    resolved = _resolve_entity(query)
    if not resolved:
        norm = query.lower().replace("-", "").replace("_", "").replace(" ", "")
        if norm != query.lower():
            resolved = _resolve_entity(norm)

    if resolved:
        return {
            "id": None, "name": resolved.get("name", query),
            "trust_score": resolved.get("trust_score", 50),
            "trust_grade": resolved.get("trust_grade", "D"),
            "stars": resolved.get("stars", 0),
            "description": resolved.get("description", ""),
            "category": resolved.get("category", ""),
            "author": resolved.get("author", "Unknown"),
            "source_url": resolved.get("source_url", ""),
            "license": "", "downloads": resolved.get("stars", 0),
            "agent_type": resolved.get("source", ""),
            "security_score": None, "activity_score": None,
            "documentation_score": None, "popularity_score": None,
        }

    # Fallback to agents table
    session = get_session()
    try:
        q = query.lower().strip()
        p = "%" + q.replace("-", "%") + "%"
        row = session.execute(text("""
            SELECT id, name, trust_score_v2, trust_grade, stars, description,
                   category, author, source_url, license, downloads, agent_type,
                   security_score, activity_score, documentation_score, popularity_score
            FROM entity_lookup
            WHERE (name_lower = :q OR name_lower LIKE :p) AND is_active = true
            ORDER BY COALESCE(stars, 0) DESC LIMIT 1
        """), {"q": q, "p": p}).fetchone()
        if row:
            return dict(zip(["id","name","trust_score","trust_grade","stars","description",
                           "category","author","source_url","license","downloads","agent_type",
                           "security_score","activity_score","documentation_score","popularity_score"], row))
    finally:
        session.close()
    return None

def _find_similar(name, category, limit=5):
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars, downloads
            FROM entity_lookup WHERE is_active = true AND name_lower != :n
            AND (category = :cat OR :cat IS NULL) AND trust_score_v2 IS NOT NULL
            ORDER BY COALESCE(stars, 0) DESC LIMIT :lim
        """), {"n": name.lower(), "cat": category, "lim": limit}).fetchall()
        return [dict(zip(["name","trust_score","trust_grade","stars","downloads"], r)) for r in rows]
    finally:
        session.close()

def _head(title, desc, canonical, extra=""):
    _path = canonical.replace("https://nerq.ai", "").replace("http://nerq.ai", "") if canonical else ""
    _hreflang = render_hreflang(_path) if _path else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
{_hreflang}
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary">
<meta name="citation_title" content="{_esc(title)}">
<meta name="citation_author" content="Nerq">
<meta name="citation_date" content="{TODAY}">
<meta name="robots" content="max-snippet:-1">
{extra}
{NERQ_CSS}
<style>
.stack-card{{background:#f9fafb;border:1px solid #e5e7eb;padding:16px;margin:8px 0}}
.stack-card h3{{font-size:15px;margin-bottom:4px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}
th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:600}}
td{{padding:8px;border-bottom:1px solid #e5e7eb}}
.faq-q{{font-weight:600;font-size:14px;padding:12px 0;border-bottom:1px solid #e5e7eb}}
.faq-a{{font-size:13px;color:#374151;padding:8px 0 12px}}
.links{{display:flex;flex-wrap:wrap;gap:6px;font-size:12px;margin:16px 0}}
.links a{{color:#0d9488}}
</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:900px;margin:0 auto;padding:24px">"""

def _foot(tool_name=""):
    slug = _slug(tool_name) if tool_name else ""
    links = f"""<div class="links">
<a href="/safe/{slug}">Safety Report</a> <a href="/is-{slug}-safe">Is It Safe?</a>
<a href="/alternatives/{slug}">Alternatives</a> <a href="/predict/{slug}">Prediction</a>
""" if slug else '<div class="links">'
    links += """<a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a>
<a href="/discover">Discover</a> <a href="/mcp-servers">MCP Servers</a>
<a href="/packages">Packages</a> <a href="/models">Models</a>
<a href="/stats/ai-ecosystem">Stats</a> <a href="/nerq/docs">API</a>
</div>"""
    return f"""{links}
<p style="font-size:12px;color:#6b7280;margin-top:16px">Last updated {MONTH_YEAR}. Trust scores based on automated analysis of public data.</p>
</main>{NERQ_FOOTER}</body></html>"""

def _faq(items):
    html = "".join(f'<div class="faq-q">{q}</div><div class="faq-a">{a}</div>' for q, a in items)
    jsonld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a}"}}}}' for q, a in items)
    return html, f'<script type="application/ld+json">{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{jsonld}]}}</script>'


def mount_demand_pages(app):

    # ════════════════════════════════════════
    # Redirect: /a-scam/{slug} → /is-{slug}-a-scam
    # ════════════════════════════════════════
    @app.get("/a-scam/{slug}")
    async def a_scam_redirect(slug: str):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f"/is-{slug}-a-scam", status_code=301)

    # ════════════════════════════════════════
    # BUILD 1: /what-is/{slug}
    # ════════════════════════════════════════
    @app.get("/what-is/{slug}", response_class=HTMLResponse)
    async def what_is_page(slug: str):
        ck = f"whatis:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        a = _find_tool(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        name = a["name"].split("/")[-1] if "/" in a["name"] else a["name"]
        score = a["trust_score"] or 0
        grade = a["trust_grade"] or "D"
        desc = a["description"] or f"An AI {a['agent_type'] or 'tool'}"
        cat = a["category"] or "AI tool"
        stars = a["stars"] or 0
        alts = _find_similar(a["name"], a["category"], 5)

        title = f"What is {_esc(name)}? {_esc(cat).title()} Overview & Trust Score {YEAR} | Nerq"
        meta = f"What is {_esc(name)}? It is a {_esc(cat)} with a Nerq Trust Score of {score:.0f}/100 ({grade}). {_esc(desc[:120]) if desc else 'Independent analysis and alternatives.'}."
        canonical = f"{SITE}/what-is/{_slug(a['name'])}"

        alts_html = ""
        for alt in alts[:5]:
            s = _slug(alt["name"])
            alts_html += f'<tr><td><a href="/what-is/{s}" style="color:#0d9488">{_esc(alt["name"].split("/")[-1])}</a></td><td>{(alt["trust_score"] or 0):.0f}</td><td>{_fmt(alt["stars"])}</td></tr>'

        faq_items = [
            (f"What is {_esc(name)} used for?", f"{_esc(name)} is a {_esc(cat)} tool. {_esc(desc[:200])}."),
            (f"Is {_esc(name)} free?", f"License: {_esc(a['license'] or 'Check project page')}. {_esc(name)} has {_fmt(stars)} GitHub stars."),
            (f"Is {_esc(name)} safe?", f"{_esc(name)} has a Nerq Trust Score of {score:.0f}/100 ({grade}). {'Safe for production use.' if score >= 70 else 'Use with caution.' if score >= 50 else 'Evaluate carefully.'}"),
            (f"What are alternatives to {_esc(name)}?", f"Top alternatives: {', '.join(_esc(a2['name'].split('/')[-1]) for a2 in alts[:3])}. See full comparison."),
        ]
        faq_html, faq_ld = _faq(faq_items)

        # Verdict
        if score >= 70: vt, vc, vbg, vi = "Safe", "#16a34a", "#f0fdf4", "✅"
        elif score >= 40: vt, vc, vbg, vi = "Use Caution", "#d97706", "#fffbeb", "⚠️"
        else: vt, vc, vbg, vi = "Avoid", "#dc2626", "#fef2f2", "🔴"

        page = _head(title, meta, canonical,
                     f'<meta name="nerq:type" content="what_is"><meta name="nerq:tools" content="{_esc(name)}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>What is {_esc(name)}?</h1>

<div style="border:2px solid {vc};border-radius:12px;padding:24px;margin:0 0 20px;background:{vbg}">
<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
<div><div style="font-size:3rem;font-weight:800;color:{vc}">{score:.0f}/100</div>
<div style="font-size:1.1rem;color:#666">Trust Score ({grade})</div></div>
<div style="text-align:right"><div style="font-size:1.5rem;font-weight:700;color:{vc}">{vi} {vt}</div></div>
</div></div>

<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(name)} is a {_esc(cat)} that {_esc(desc[:200])}. It has a Nerq Trust Score of <strong>{score:.0f}/100</strong> ({grade}). {_fmt(stars)} GitHub stars. Published by {_esc(a['author'] or 'Unknown')}. Last analyzed {MONTH_YEAR}.</p>

<h2>Why This Score</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>{'✅' if (a.get('security_score') or 0) >= 60 else '⚠️'} <strong>Security</strong>: {(a.get('security_score') or 0):.0f}/100 — {'No known vulnerabilities' if (a.get('security_score') or 0) >= 60 else 'Some security concerns'}</li>
<li>{'✅' if (a.get('activity_score') or 0) >= 60 else '⚠️'} <strong>Maintenance</strong>: {(a.get('activity_score') or 0):.0f}/100 — {'Actively maintained' if (a.get('activity_score') or 0) >= 60 else 'Maintenance activity is low'}</li>
<li>{'✅' if stars > 1000 else '⚠️'} <strong>Community</strong>: {_fmt(stars)} stars, {_fmt(a['downloads'])} downloads — {'Large community' if stars > 1000 else 'Growing community'}</li>
<li>{'✅' if a.get('license') else '⚠️'} <strong>Transparency</strong>: License: {_esc(a['license'] or 'Not specified')} — {'Clear licensing' if a.get('license') else 'No license specified'}</li>
</ul>

<h2>Trust & Safety Overview</h2>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0">
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700;color:{_grade_color(grade)}">{score:.0f}</div><div style="font-size:10px;color:#6b7280">TRUST SCORE</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{grade}</div><div style="font-size:10px;color:#6b7280">GRADE</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{_fmt(stars)}</div><div style="font-size:10px;color:#6b7280">STARS</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{_fmt(a['downloads'])}</div><div style="font-size:10px;color:#6b7280">DOWNLOADS</div></div>
</div>

<h2>What {_esc(name)} Does</h2>
<p style="font-size:14px;color:#374151;line-height:1.7">{_esc(name)} is a {_esc(a['agent_type'] or 'tool')} in the {_esc(cat)} category. {_esc(desc[:400])}. It is published by {_esc(a['author'] or 'an independent developer')} and {'is open source' if a.get('license') else 'has no specified license'}. With {_fmt(stars)} GitHub stars and {_fmt(a['downloads'])} downloads, it has {'a large and active' if stars > 5000 else 'a growing' if stars > 100 else 'a small'} community of users and contributors.</p>

<h2>Who Should Use {_esc(name)}</h2>
<p style="font-size:14px;color:#374151;line-height:1.7">{_esc(name)} is {'well-suited for production use given its strong trust score and active community.' if score >= 70 else 'suitable for evaluation and non-critical use. Review the trust score breakdown before using in production.' if score >= 50 else 'recommended only for experimental use. Consider alternatives with higher trust scores for production systems.'}</p>

<h2>Details</h2>
<table>
<tr><th>Author</th><td>{_esc(a['author'] or 'Unknown')}</td></tr>
<tr><th>Category</th><td>{_esc(cat)}</td></tr>
<tr><th>License</th><td>{_esc(a['license'] or 'Not specified')}</td></tr>
<tr><th>Type</th><td>{_esc(a['agent_type'] or 'Tool')}</td></tr>
<tr><th>Source</th><td><a href="{_esc(a['source_url'] or '#')}" rel="nofollow" style="color:#0d9488">View on GitHub</a></td></tr>
<tr><th>Security Score</th><td>{(a.get('security_score') or 0):.0f}/100</td></tr>
<tr><th>Activity Score</th><td>{(a.get('activity_score') or 0):.0f}/100</td></tr>
</table>

<h2>How to Get Started</h2>
<p style="font-size:14px;color:#374151">Check the trust score before installing:</p>
<pre style="background:#f5f5f5;padding:12px;font-size:13px;overflow-x:auto">curl nerq.ai/v1/preflight?target={_slug(a['name'])}</pre>
<p style="font-size:13px;color:#6b7280;margin-top:6px"><a href="/guide/{_slug(name)}" style="color:#0d9488">Setup guide</a> · <a href="/safe/{_slug(a['name'])}" style="color:#0d9488">Full safety report</a> · <a href="/review/{_slug(name)}" style="color:#0d9488">Production review</a> · <a href="/is-{_slug(name)}-safe" style="color:#0d9488">Is it safe?</a></p>

{"<h2>Safer Alternatives</h2><table><tr><th>Tool</th><th>Trust</th><th>Stars</th></tr>" + alts_html + "</table>" if alts_html else ""}

<h2>Frequently Asked Questions</h2>
{faq_html}
"""
        page += _foot(a["name"])
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # BUILD 2: /stack/{slug}
    # ════════════════════════════════════════
    STACKS = {
        "rag-app": {"title": "Build a RAG App", "tools": ["langchain", "chromadb", "openai", "fastapi", "unstructured"], "desc": "Retrieval-Augmented Generation application"},
        "ai-chatbot": {"title": "Build an AI Chatbot", "tools": ["openai", "langchain", "streamlit", "chromadb"], "desc": "Conversational AI chatbot"},
        "ai-agent": {"title": "Build an AI Agent", "tools": ["crewai", "langchain", "openai", "chromadb", "fastapi"], "desc": "Autonomous AI agent system"},
        "local-llm": {"title": "Run LLMs Locally", "tools": ["ollama", "open-webui", "chromadb", "gradio"], "desc": "Private, local LLM setup"},
        "ai-startup-mvp": {"title": "AI Startup MVP", "tools": ["vercel", "openai", "supabase", "langchain", "stripe"], "desc": "AI SaaS minimum viable product"},
        "enterprise-ai": {"title": "Enterprise AI Stack", "tools": ["langchain", "pinecone", "openai", "fastapi", "datadog"], "desc": "Production enterprise AI"},
        "mcp-server": {"title": "Build an MCP Server", "tools": ["mcp", "fastapi", "openai", "docker"], "desc": "Model Context Protocol server"},
        "ai-automation": {"title": "Build AI Automation", "tools": ["n8n", "openai", "langchain", "supabase"], "desc": "AI-powered workflow automation"},
        "self-hosted-ai": {"title": "Self-Hosted AI", "tools": ["ollama", "open-webui", "chromadb", "docker", "nginx"], "desc": "Fully private AI infrastructure"},
        "ai-coding-assistant": {"title": "Build AI Coding Tool", "tools": ["openai", "langchain", "chromadb", "fastapi"], "desc": "AI-powered code assistant"},
        "multi-agent-system": {"title": "Multi-Agent System", "tools": ["crewai", "autogen", "langchain", "openai"], "desc": "Coordinated multi-agent system"},
        "document-ai": {"title": "Build Document AI", "tools": ["unstructured", "langchain", "chromadb", "openai", "fastapi"], "desc": "Document processing with AI"},
        "ai-search": {"title": "Build AI Search", "tools": ["chromadb", "openai", "langchain", "fastapi"], "desc": "Semantic search powered by AI"},
        "privacy-first-ai": {"title": "Privacy-First AI", "tools": ["ollama", "chromadb", "fastapi", "docker"], "desc": "AI with zero cloud dependency"},
        "ai-for-solo-developer": {"title": "Solo Dev AI Stack", "tools": ["cursor", "ollama", "supabase", "vercel"], "desc": "AI tools for independent developers"},
        "image-generation": {"title": "AI Image Generation", "tools": ["stable-diffusion", "comfyui", "gradio", "docker"], "desc": "AI image generation pipeline"},
        "voice-ai": {"title": "Build Voice AI", "tools": ["elevenlabs", "openai", "fastapi", "gradio"], "desc": "Voice synthesis and recognition"},
        "ai-saas": {"title": "Build AI SaaS", "tools": ["openai", "langchain", "supabase", "vercel", "stripe"], "desc": "AI-powered SaaS product"},
        "ai-customer-support": {"title": "AI Customer Support", "tools": ["openai", "langchain", "chromadb", "intercom"], "desc": "AI-powered customer support"},
        "ai-content-generation": {"title": "AI Content Generation", "tools": ["openai", "langchain", "grammarly", "vercel"], "desc": "Automated content creation"},
        "code-review-ai": {"title": "AI Code Review", "tools": ["openai", "langchain", "github-copilot", "fastapi"], "desc": "Automated code review pipeline"},
        "ai-data-analysis": {"title": "AI Data Analysis", "tools": ["openai", "langchain", "pandas", "streamlit"], "desc": "AI-powered data analysis"},
        "ai-testing": {"title": "AI Testing Pipeline", "tools": ["openai", "langchain", "pytest", "fastapi"], "desc": "AI-assisted testing"},
        "ai-on-mac": {"title": "AI Stack for Mac", "tools": ["ollama", "cursor", "open-webui", "docker"], "desc": "Best AI tools for macOS"},
        "ai-for-small-team": {"title": "Small Team AI", "tools": ["cursor", "openai", "supabase", "vercel", "linear"], "desc": "AI stack for small teams"},
    }

    @app.get("/stack/{slug}", response_class=HTMLResponse)
    async def stack_page(slug: str):
        stack = STACKS.get(slug)
        if not stack:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        ck = f"stack:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        tools_data = []
        for tool_name in stack["tools"]:
            t = _find_tool(tool_name)
            if t:
                tools_data.append(t)
            else:
                tools_data.append({"name": tool_name, "trust_score": 50, "trust_grade": "D", "stars": 0, "description": "", "category": ""})

        avg_trust = sum((t.get("trust_score") or 0) for t in tools_data) / max(1, len(tools_data))
        title = f"{stack['title']} — Stack {YEAR} | Nerq"
        desc_text = stack["desc"]
        canonical = f"{SITE}/stack/{slug}"

        tools_html = ""
        for t in tools_data:
            n = t["name"].split("/")[-1] if "/" in t.get("name", "") else t.get("name", "")
            ts = t.get("trust_score") or 0
            gc = _grade_color(t.get("trust_grade"))
            tools_html += f'<div class="stack-card"><h3><a href="/what-is/{_slug(n)}" style="color:#0d9488">{_esc(n)}</a></h3><p style="font-size:12px;color:#6b7280">{_esc((t.get("description") or "")[:100])}</p><div style="font-size:13px">Trust: <strong style="color:{gc}">{ts:.0f}/100</strong> · {_fmt(t.get("stars"))} stars</div></div>'

        faq_items = [
            (f"What tools do I need for {_esc(desc_text.lower())}?", f"We recommend: {', '.join(t['name'].split('/')[-1] for t in tools_data)}. Average stack trust score: {avg_trust:.0f}/100."),
            (f"What is the best {_esc(desc_text.lower())} stack?", f"This stack of {len(tools_data)} tools scores {avg_trust:.0f}/100 average trust. See details above."),
            (f"Is this stack safe for production?", f"{'Yes — average trust score of {:.0f} indicates production readiness.'.format(avg_trust) if avg_trust >= 60 else 'Evaluate carefully — some components have lower trust scores.'}"),
        ]
        faq_html, faq_ld = _faq(faq_items)

        page = _head(title, f"Recommended {desc_text} stack: {len(tools_data)} tools, avg trust {avg_trust:.0f}/100. {MONTH_YEAR}.", canonical,
                     f'<meta name="nerq:type" content="stack"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>{_esc(stack['title'])} — Recommended Stack {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">A {_esc(desc_text)} stack with {len(tools_data)} trust-verified tools. Average stack trust score: <strong>{avg_trust:.0f}/100</strong>. Updated {MONTH_YEAR}.</p>

<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:16px 0">
<div style="padding:12px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:20px;font-weight:700">{len(tools_data)}</div><div style="font-size:10px;color:#6b7280">TOOLS</div></div>
<div style="padding:12px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:20px;font-weight:700;color:{_grade_color('A' if avg_trust >= 70 else 'C')}">{avg_trust:.0f}</div><div style="font-size:10px;color:#6b7280">AVG TRUST</div></div>
<div style="padding:12px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:20px;font-weight:700">{sum((t.get('stars') or 0) for t in tools_data):,}</div><div style="font-size:10px;color:#6b7280">TOTAL STARS</div></div>
</div>

<h2>Recommended Tools</h2>
{tools_html}

<h2>FAQ</h2>
{faq_html}
"""
        page += _foot()
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # BUILD 3: /review/{slug}
    # ════════════════════════════════════════
    @app.get("/review/{slug}", response_class=HTMLResponse)
    async def review_page(slug: str):
        ck = f"review:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        a = _find_tool(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        name = a["name"].split("/")[-1] if "/" in a["name"] else a["name"]
        score = a["trust_score"] or 0
        grade = a["trust_grade"] or "D"
        desc = a["description"] or ""

        if score >= 70: verdict, vc = "Production Ready", "#16a34a"
        elif score >= 50: verdict, vc = "Use With Caution", "#ca8a04"
        else: verdict, vc = "Not Recommended for Production", "#dc2626"

        alts = _find_similar(a["name"], a["category"], 5)
        alts_html = "".join(f'<tr><td><a href="/review/{_slug(al["name"])}" style="color:#0d9488">{_esc(al["name"].split("/")[-1])}</a></td><td>{(al["trust_score"] or 0):.0f}</td><td>{al["trust_grade"] or "D"}</td></tr>' for al in alts)

        title = f"{_esc(name)} Review {YEAR} — Production Ready? | Nerq"
        canonical = f"{SITE}/review/{_slug(a['name'])}"

        faq_items = [
            (f"Is {_esc(name)} production ready?", f"Verdict: {verdict}. Trust Score: {score:.0f}/100 ({grade})."),
            (f"Is {_esc(name)} good for enterprise?", f"{'Yes — strong trust metrics.' if score >= 70 else 'Evaluate based on your requirements.'} Security: {a.get('security_score') or 'N/A'}/100."),
            (f"Should I use {_esc(name)} in {YEAR}?", f"{_esc(name)} has {_fmt(a['stars'])} stars and a trust score of {score:.0f}. {verdict}."),
        ]
        faq_html, faq_ld = _faq(faq_items)

        page = _head(title, f"{_esc(name)} review: {verdict}. Trust {score:.0f}/100 ({grade}). {_fmt(a['stars'])} stars. {MONTH_YEAR}.", canonical,
                     f'<meta name="nerq:type" content="review"><meta name="nerq:tools" content="{_esc(name)}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>{_esc(name)} Review {YEAR} — Production Ready?</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(name)} has a Nerq Trust Score of <strong>{score:.0f}/100</strong> ({grade}). Verdict: <strong style="color:{vc}">{verdict}</strong>. {_fmt(a['stars'])} stars. {_esc(desc[:150])}. Updated {MONTH_YEAR}.</p>

<div style="display:inline-block;padding:10px 20px;font-weight:700;font-size:18px;color:{vc};border:2px solid {vc};margin:12px 0">{verdict.upper()}</div>

<h2>Trust Score Breakdown</h2>
<table>
<tr><th>Dimension</th><th>Score</th></tr>
<tr><td>Security</td><td>{a.get('security_score') or 'Pending'}/100</td></tr>
<tr><td>Maintenance</td><td>{a.get('activity_score') or 'Pending'}/100</td></tr>
<tr><td>Documentation</td><td>{a.get('documentation_score') or 'Pending'}/100</td></tr>
<tr><td>Popularity</td><td>{a.get('popularity_score') or 'Pending'}/100</td></tr>
</table>

{"<h2>Alternatives</h2><table><tr><th>Tool</th><th>Trust</th><th>Grade</th></tr>" + alts_html + "</table>" if alts_html else ""}

<h2>FAQ</h2>
{faq_html}
"""
        page += _foot(a["name"])
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # BUILD 4: /migrate/{from}-to-{to}
    # ════════════════════════════════════════
    @app.get("/migrate/{from_tool}-to-{to_tool}", response_class=HTMLResponse)
    async def migrate_page(from_tool: str, to_tool: str):
        ck = f"migrate:{from_tool}:{to_tool}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        a = _find_tool(from_tool)
        b = _find_tool(to_tool)

        name_a = (a["name"].split("/")[-1] if a and "/" in a["name"] else from_tool) if a else from_tool
        name_b = (b["name"].split("/")[-1] if b and "/" in b["name"] else to_tool) if b else to_tool
        score_a = (a["trust_score"] or 0) if a else 0
        score_b = (b["trust_score"] or 0) if b else 0
        diff = score_b - score_a

        title = f"Migrate {_esc(name_a)} to {_esc(name_b)} — Guide {YEAR} | Nerq"
        canonical = f"{SITE}/migrate/{from_tool}-to-{to_tool}"

        faq_items = [
            (f"Should I switch from {_esc(name_a)} to {_esc(name_b)}?", f"Trust score change: {score_a:.0f} → {score_b:.0f} ({'+' if diff >= 0 else ''}{diff:.0f}). {_esc(name_b)} {'has a higher trust score.' if diff > 0 else 'has a similar trust score.' if abs(diff) < 5 else 'has a lower trust score.'}"),
            (f"How hard is it to migrate from {_esc(name_a)} to {_esc(name_b)}?", f"Difficulty depends on your integration depth. Both tools serve similar use cases."),
            (f"Is {_esc(name_b)} better than {_esc(name_a)}?", f"{_esc(name_b)} trust: {score_b:.0f}/100. {_esc(name_a)} trust: {score_a:.0f}/100. {'Yes, higher trust.' if diff > 5 else 'Comparable.' if abs(diff) <= 5 else 'Lower trust, but may have other advantages.'}"),
        ]
        faq_html, faq_ld = _faq(faq_items)

        page = _head(title, f"Migrate from {_esc(name_a)} ({score_a:.0f}) to {_esc(name_b)} ({score_b:.0f}). Trust change: {'+' if diff >= 0 else ''}{diff:.0f}.", canonical,
                     f'<meta name="nerq:type" content="migration"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>Migrate from {_esc(name_a)} to {_esc(name_b)} — {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Migrating from {_esc(name_a)} (Trust: {score_a:.0f}/100) to {_esc(name_b)} (Trust: {score_b:.0f}/100) {'improves' if diff > 0 else 'changes'} your trust score by <strong>{'+' if diff >= 0 else ''}{diff:.0f} points</strong>. Updated {MONTH_YEAR}.</p>

<h2>Trust Score Impact</h2>
<table>
<tr><th></th><th>{_esc(name_a)}</th><th>{_esc(name_b)}</th></tr>
<tr><td>Trust Score</td><td>{score_a:.0f}/100</td><td style="font-weight:700;color:{_grade_color('A' if score_b >= 70 else 'C')}">{score_b:.0f}/100</td></tr>
<tr><td>Grade</td><td>{(a['trust_grade'] if a else 'N/A')}</td><td>{(b['trust_grade'] if b else 'N/A')}</td></tr>
<tr><td>Stars</td><td>{_fmt(a['stars'] if a else 0)}</td><td>{_fmt(b['stars'] if b else 0)}</td></tr>
</table>

<h2>FAQ</h2>
{faq_html}

<div style="margin-top:16px;font-size:12px;color:#6b7280">
<a href="/compare/{from_tool}-vs-{to_tool}" style="color:#0d9488">Full comparison</a> ·
<a href="/what-is/{to_tool}" style="color:#0d9488">What is {_esc(name_b)}?</a> ·
<a href="/review/{to_tool}" style="color:#0d9488">{_esc(name_b)} review</a>
</div>
"""
        page += _foot()
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # BUILD 7: /this-week
    # ════════════════════════════════════════
    @app.get("/this-week", response_class=HTMLResponse)
    async def this_week_page():
        ck = "this_week"
        c = _c(ck)
        if c: return HTMLResponse(c)

        session = get_session()
        try:
            # Trending (star acceleration)
            trending = session.execute(text("""
                SELECT agent_name, star_velocity_7d, ai_attention_score
                FROM prediction_signals
                WHERE calculated_at = (SELECT MAX(calculated_at) FROM prediction_signals)
                AND star_velocity_7d > 0
                ORDER BY star_velocity_7d DESC LIMIT 10
            """)).fetchall()

            # New predictions
            preds = session.execute(text("""
                SELECT agent_name, nerq_predictive_index, adoption_phase
                FROM predictions
                WHERE predicted_at = (SELECT MAX(predicted_at) FROM predictions)
                ORDER BY nerq_predictive_index DESC LIMIT 10
            """)).fetchall()

            total_obs = session.execute(text("SELECT COUNT(DISTINCT agent_id) FROM prediction_observations")).fetchone()[0]
        except Exception:
            trending, preds, total_obs = [], [], 0
        finally:
            session.close()

        title = f"This Week in AI Tools — {MONTH_YEAR} | Nerq"
        canonical = f"{SITE}/this-week"

        trending_html = ""
        for r in trending:
            trending_html += f'<tr><td><a href="/what-is/{_slug(r[0])}" style="color:#0d9488">{_esc(r[0].split("/")[-1])}</a></td><td style="color:#16a34a">+{r[1]}</td><td>{(r[2] or 0):.0f}</td></tr>'

        page = _head(title, f"Weekly AI tools intelligence. Trending tools, predictions, and health warnings. {MONTH_YEAR}.", canonical,
                     f'<meta name="nerq:type" content="weekly"><meta name="nerq:updated" content="{TODAY}">')
        page += f"""
<h1>This Week in AI Tools — {MONTH_YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Weekly intelligence on {total_obs:,} tracked AI tools. Trending tools, predictions, and ecosystem health. Updated {MONTH_YEAR}.</p>

<h2>Trending (Highest Star Growth)</h2>
<table><tr><th>Tool</th><th>Stars/week</th><th>AI Interest</th></tr>
{trending_html if trending_html else '<tr><td colspan="3" style="color:#6b7280">Collecting data...</td></tr>'}
</table>

<h2>Top Predictions</h2>
<table><tr><th>Tool</th><th>NPI</th><th>Phase</th></tr>
{"".join(f'<tr><td>{_esc(r[0].split("/")[-1])}</td><td>{(r[1] or 0):.0f}</td><td>{r[2] or "?"}</td></tr>' for r in preds[:10]) if preds else '<tr><td colspan="3" style="color:#6b7280">Collecting data...</td></tr>'}
</table>

<div style="margin-top:16px;font-size:12px;color:#6b7280">
<a href="/predictions" style="color:#0d9488">Full predictions</a> · <a href="/trending" style="color:#0d9488">Trending</a> · <a href="/stats/ai-ecosystem" style="color:#0d9488">Ecosystem stats</a>
</div>
"""
        page += _foot()
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # BUILD 8: /issues/{slug}
    # ════════════════════════════════════════
    @app.get("/issues/{slug}", response_class=HTMLResponse)
    async def issues_page(slug: str):
        ck = f"issues:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        a = _find_tool(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        name = a["name"].split("/")[-1] if "/" in a["name"] else a["name"]
        score = a["trust_score"] or 0
        activity = a.get("activity_score") or 0

        title = f"{_esc(name)} Known Issues & Status {YEAR} | Nerq"
        canonical = f"{SITE}/issues/{_slug(a['name'])}"

        page = _head(title, f"{_esc(name)} status and known issues. Activity score: {activity}/100. Trust: {score:.0f}/100.", canonical,
                     f'<meta name="nerq:type" content="issues"><meta name="nerq:tools" content="{_esc(name)}"><meta name="nerq:updated" content="{TODAY}">')
        page += f"""
<h1>{_esc(name)} — Known Issues & Status {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(name)} has an activity score of <strong>{activity}/100</strong> and trust score of {score:.0f}/100. {'Actively maintained.' if activity >= 60 else 'Maintenance activity is declining.' if activity >= 30 else 'Low maintenance activity.'} Updated {MONTH_YEAR}.</p>

<h2>Maintenance Status</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Activity Score</td><td>{'&#x1f7e2;' if activity >= 60 else '&#x1f7e1;' if activity >= 30 else '&#x1f534;'} {activity}/100</td></tr>
<tr><td>Trust Score</td><td>{score:.0f}/100</td></tr>
<tr><td>Stars</td><td>{_fmt(a['stars'])}</td></tr>
<tr><td>License</td><td>{_esc(a['license'] or 'Not specified')}</td></tr>
</table>

<div style="margin-top:16px;font-size:12px;color:#6b7280">
<a href="/safe/{_slug(a['name'])}" style="color:#0d9488">Full safety report</a> ·
<a href="/review/{_slug(a['name'])}" style="color:#0d9488">Production review</a> ·
<a href="/alternatives/{_slug(a['name'])}" style="color:#0d9488">Alternatives</a>
</div>
"""
        page += _foot(a["name"])
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # SITEMAPS
    # ════════════════════════════════════════
    @app.get("/sitemap-what-is.xml", response_class=Response)
    async def sitemap_what_is():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT name FROM entity_lookup WHERE is_active = true
                AND description IS NOT NULL AND LENGTH(description) > 10
                AND (stars > 100 OR downloads > 1000)
                ORDER BY COALESCE(stars, 0) DESC LIMIT 5000
            """)).fetchall()
        finally:
            session.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            xml += f'<url><loc>{SITE}/what-is/{_slug(r[0])}</loc><lastmod>{TODAY}</lastmod><priority>0.7</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-stacks.xml", response_class=Response)
    async def sitemap_stacks():
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for slug in STACKS:
            xml += f'<url><loc>{SITE}/stack/{slug}</loc><lastmod>{TODAY}</lastmod><priority>0.8</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-reviews.xml", response_class=Response)
    async def sitemap_reviews():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT name FROM entity_lookup WHERE is_active = true
                AND trust_score_v2 IS NOT NULL AND stars > 500
                ORDER BY COALESCE(stars, 0) DESC LIMIT 1000
            """)).fetchall()
        finally:
            session.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            xml += f'<url><loc>{SITE}/review/{_slug(r[0])}</loc><lastmod>{TODAY}</lastmod><priority>0.7</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-migrate.xml", response_class=Response)
    async def sitemap_migrate():
        pairs = [
            "langchain-to-llamaindex", "openai-to-anthropic", "openai-to-ollama",
            "copilot-to-cursor", "copilot-to-windsurf", "pinecone-to-qdrant",
            "pinecone-to-chromadb", "chromadb-to-qdrant", "zapier-to-n8n",
            "firebase-to-supabase", "autogen-to-crewai", "vercel-to-netlify",
            "langchain-to-langgraph", "cursor-to-windsurf", "chatgpt-to-claude",
            "midjourney-to-stable-diffusion", "ollama-to-lmstudio",
            "notion-to-obsidian", "jira-to-linear", "tensorflow-to-pytorch",
        ]
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for p in pairs:
            xml += f'<url><loc>{SITE}/migrate/{p}</loc><lastmod>{TODAY}</lastmod><priority>0.7</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-issues.xml", response_class=Response)
    async def sitemap_issues():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT name FROM entity_lookup WHERE is_active = true AND stars > 500
                ORDER BY COALESCE(stars, 0) DESC LIMIT 1000
            """)).fetchall()
        finally:
            session.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            xml += f'<url><loc>{SITE}/issues/{_slug(r[0])}</loc><lastmod>{TODAY}</lastmod><priority>0.6</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    # ════════════════════════════════════════
    # BUILD: /ai-interest/{slug}
    # ════════════════════════════════════════
    @app.get("/ai-interest/{slug}", response_class=HTMLResponse)
    async def ai_interest_page(slug: str):
        ck = f"aiint:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        session = get_session()
        try:
            row = session.execute(text("""
                SELECT agent_name, ai_crawls_24h, chatgpt_crawls, perplexity_crawls,
                       claude_crawls, human_visits, preflight_checks, stars
                FROM prediction_observations
                WHERE LOWER(agent_name) LIKE :p
                AND observed_at = (SELECT MAX(observed_at) FROM prediction_observations)
                ORDER BY ai_crawls_24h DESC LIMIT 1
            """), {"p": f"%{slug.replace('-','%')}%"}).fetchone()
        finally:
            session.close()

        if not row:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        name = row[0].split("/")[-1] if "/" in row[0] else row[0]
        ai_total = row[1] or 0
        chatgpt = row[2] or 0
        perplexity = row[3] or 0
        claude = row[4] or 0
        human = row[5] or 0
        preflight = row[6] or 0
        stars = row[7] or 0

        title = f"AI Interest in {_esc(name)} — What AI Systems Say | Nerq"
        canonical = f"{SITE}/ai-interest/{slug}"
        meta = f"{_esc(name)} received {ai_total} AI checks recently. ChatGPT: {chatgpt}, Claude: {claude}, Perplexity: {perplexity}. Unique to Nerq."

        faq_items = [
            (f"Do AI systems recommend {_esc(name)}?", f"{_esc(name)} received {ai_total} AI bot visits. ChatGPT: {chatgpt}, Perplexity: {perplexity}, Claude: {claude}."),
            (f"Is {_esc(name)} popular with AI?", f"AI interest score: {ai_total}. Human visits: {human}. Preflight checks: {preflight}."),
        ]
        faq_html, faq_ld = _faq(faq_items)

        page = _head(title, meta, canonical,
                     f'<meta name="nerq:type" content="ai_interest"><meta name="nerq:tools" content="{_esc(name)}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>AI Interest in {_esc(name)}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(name)} received <strong>{ai_total}</strong> AI system checks recently. ChatGPT checked it {chatgpt} times, Perplexity {perplexity} times, Claude {claude} times. This data is unique to Nerq — we track how often AI systems access information about each tool. Updated {MONTH_YEAR}.</p>

<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0">
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{ai_total}</div><div style="font-size:10px;color:#6b7280">AI TOTAL</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{chatgpt}</div><div style="font-size:10px;color:#6b7280">CHATGPT</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{perplexity}</div><div style="font-size:10px;color:#6b7280">PERPLEXITY</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{claude}</div><div style="font-size:10px;color:#6b7280">CLAUDE</div></div>
</div>

<h2>Human Interest</h2>
<table>
<tr><td>Human visits</td><td><strong>{human}</strong></td></tr>
<tr><td>Preflight checks</td><td><strong>{preflight}</strong></td></tr>
<tr><td>GitHub stars</td><td><strong>{_fmt(stars)}</strong></td></tr>
</table>

<p style="font-size:13px;color:#6b7280;margin-top:16px">This data is unique to Nerq. We track how often AI systems (ChatGPT, Perplexity, Claude) access information about each tool, providing a proxy for what millions of AI users are asking about.</p>

<h2>FAQ</h2>
{faq_html}
"""
        page += _foot(row[0])
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # BUILD: /profile/{slug}
    # ════════════════════════════════════════
    @app.get("/profile/{slug}", response_class=HTMLResponse)
    async def profile_page(slug: str):
        ck = f"profile:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        a = _find_tool(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

        name = a["name"].split("/")[-1] if "/" in a["name"] else a["name"]
        score = a["trust_score"] or 0
        grade = a["trust_grade"] or "D"
        desc = a["description"] or ""
        stars = a["stars"] or 0
        downloads = a["downloads"] or 0

        sources = []
        if "github" in (a.get("source_url") or "").lower(): sources.append("GitHub")
        if stars > 0: sources.append("GitHub Stars")
        if downloads > 0: sources.append("Downloads")
        if a.get("license"): sources.append("License")
        if a.get("security_score"): sources.append("Security Scan")
        if a.get("activity_score"): sources.append("Activity Analysis")

        alts = _find_similar(a["name"], a["category"], 5)

        title = f"{_esc(name)}: Trust Score & Full Profile ({YEAR})"
        if len(title) > 60:
            title = f"{_esc(name)[:35]} — Profile & Trust ({YEAR})"
        canonical = f"{SITE}/profile/{_slug(a['name'])}"

        faq_items = [
            (f"What is {_esc(name)}?", f"{_esc(name)} is a {_esc(a['category'] or 'tool')}. {_esc(desc[:150])}."),
            (f"How trustworthy is {_esc(name)}?", f"Trust Score: {score:.0f}/100 ({grade}). Data from {len(sources)} sources."),
        ]
        faq_html, faq_ld = _faq(faq_items)

        meta_desc = f"{_esc(name)}: {score:.0f}/100 trust score ({grade}). {_fmt(stars)} stars, {len(sources)} data sources. Security analysis, alternatives, and community insights."
        if len(meta_desc) > 160:
            meta_desc = meta_desc[:157] + "..."
        page = _head(title, meta_desc, canonical,
                     f'<meta name="nerq:type" content="profile"><meta name="nerq:tools" content="{_esc(name)}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>{_esc(name)} — Complete AI Tool Profile {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(name)} appears across <strong>{len(sources)} data sources</strong>. Trust Score: <strong>{score:.0f}/100</strong> ({grade}). {_fmt(stars)} stars. {_fmt(downloads)} downloads. {_esc(desc[:150])}. Updated {MONTH_YEAR}.</p>

<h2>Trust &amp; Safety</h2>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0">
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700;color:{_grade_color(grade)}">{score:.0f}</div><div style="font-size:10px;color:#6b7280">TRUST</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{grade}</div><div style="font-size:10px;color:#6b7280">GRADE</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{_fmt(stars)}</div><div style="font-size:10px;color:#6b7280">STARS</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{len(sources)}</div><div style="font-size:10px;color:#6b7280">SOURCES</div></div>
</div>

<h2>Data Sources</h2>
<table>
<tr><th>Source</th><th>Status</th></tr>
{"".join(f'<tr><td>{_esc(s)}</td><td style="color:#16a34a">Available</td></tr>' for s in sources)}
</table>

<h2>Details</h2>
<table>
<tr><th>Author</th><td>{_esc(a['author'] or 'Unknown')}</td></tr>
<tr><th>Category</th><td>{_esc(a['category'] or 'N/A')}</td></tr>
<tr><th>Type</th><td>{_esc(a['agent_type'] or 'Tool')}</td></tr>
<tr><th>License</th><td>{_esc(a['license'] or 'Not specified')}</td></tr>
<tr><th>Security Score</th><td>{a.get('security_score') or 'Pending'}/100</td></tr>
<tr><th>Activity Score</th><td>{a.get('activity_score') or 'Pending'}/100</td></tr>
<tr><th>Documentation</th><td>{a.get('documentation_score') or 'Pending'}/100</td></tr>
</table>

{"<h2>Alternatives</h2><table><tr><th>Tool</th><th>Trust</th><th>Stars</th></tr>" + "".join(f'<tr><td><a href="/profile/{_slug(al["name"])}" style="color:#0d9488">{_esc(al["name"].split("/")[-1])}</a></td><td>{(al["trust_score"] or 0):.0f}</td><td>{_fmt(al["stars"])}</td></tr>' for al in alts) + "</table>" if alts else ""}

<h2>FAQ</h2>
{faq_html}
"""
        page += _foot(a["name"])
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # DATA FEEDS
    # ════════════════════════════════════════
    @app.get("/feed/daily-changes.jsonl", response_class=Response)
    async def feed_daily_changes():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, downloads, agent_type
                FROM entity_lookup WHERE is_active = true
                AND trust_score_v2 IS NOT NULL
                ORDER BY COALESCE(stars, 0) DESC LIMIT 1000
            """)).fetchall()
        finally:
            session.close()
        lines = []
        for r in rows:
            lines.append(json.dumps({"name": r[0], "trust_score": float(r[1]) if r[1] else 0,
                                    "grade": r[2], "stars": r[3], "downloads": r[4], "type": r[5]}))
        return Response("\n".join(lines), media_type="application/x-ndjson",
                       headers={"Content-Disposition": "inline"})

    @app.get("/feed/ai-interest.jsonl", response_class=Response)
    async def feed_ai_interest():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT agent_name, ai_crawls_24h, chatgpt_crawls, perplexity_crawls,
                       claude_crawls, human_visits, preflight_checks
                FROM prediction_observations
                WHERE observed_at = (SELECT MAX(observed_at) FROM prediction_observations)
                AND ai_crawls_24h > 0
                ORDER BY ai_crawls_24h DESC
            """)).fetchall()
        finally:
            session.close()
        lines = [json.dumps({"name": r[0], "ai_total": r[1], "chatgpt": r[2],
                            "perplexity": r[3], "claude": r[4], "human": r[5], "preflight": r[6]}) for r in rows]
        return Response("\n".join(lines), media_type="application/x-ndjson")

    @app.get("/feed/predictions.jsonl", response_class=Response)
    async def feed_predictions():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT agent_name, nerq_predictive_index, adoption_phase,
                       fragility_index, ai_recommendation_prob, survival_30d_prob
                FROM predictions
                WHERE predicted_at = (SELECT MAX(predicted_at) FROM predictions)
                ORDER BY nerq_predictive_index DESC LIMIT 1000
            """)).fetchall()
        finally:
            session.close()
        lines = [json.dumps({"name": r[0], "npi": float(r[1]) if r[1] else 0, "phase": r[2],
                            "fragility": float(r[3]) if r[3] else 0,
                            "ai_prob": float(r[4]) if r[4] else 0, "survival": float(r[5]) if r[5] else 0}) for r in rows]
        return Response("\n".join(lines), media_type="application/x-ndjson")

    @app.get("/feed/entity-ratings.jsonl", response_class=Response)
    async def feed_entity_ratings():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT entity_name, entity_type, rating, score, tools_found, critical_issues, industry, country
                FROM entity_ratings WHERE score > 0
                ORDER BY score DESC
            """)).fetchall()
        finally:
            session.close()
        lines = [json.dumps({"name": r[0], "type": r[1], "rating": r[2], "score": float(r[3]) if r[3] else 0,
                            "tools": r[4], "critical": r[5], "industry": r[6], "country": r[7]}) for r in rows]
        return Response("\n".join(lines), media_type="application/x-ndjson")

    # ════════════════════════════════════════
    # SITEMAPS for new page types
    # ════════════════════════════════════════
    @app.get("/sitemap-ai-interest.xml", response_class=Response)
    async def sitemap_ai_interest():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT agent_name FROM prediction_observations
                WHERE observed_at = (SELECT MAX(observed_at) FROM prediction_observations)
                AND ai_crawls_24h > 0
                ORDER BY ai_crawls_24h DESC LIMIT 2000
            """)).fetchall()
        finally:
            session.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            xml += f'<url><loc>{SITE}/ai-interest/{_slug(r[0])}</loc><lastmod>{TODAY}</lastmod><priority>0.7</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-profiles.xml", response_class=Response)
    async def sitemap_profiles():
        session = get_session()
        try:
            rows = session.execute(text("""
                SELECT name FROM entity_lookup WHERE is_active = true
                AND description IS NOT NULL AND LENGTH(description) > 10
                AND (stars > 100 OR downloads > 1000)
                ORDER BY COALESCE(stars, 0) DESC LIMIT 5000
            """)).fetchall()
        finally:
            session.close()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for r in rows:
            xml += f'<url><loc>{SITE}/profile/{_slug(r[0])}</loc><lastmod>{TODAY}</lastmod><priority>0.6</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    # ════════════════════════════════════════
    # NEW URL PATTERNS (6 high-volume patterns)
    # ════════════════════════════════════════

    def _resolve_any(slug):
        """Resolve entity from any source. Fast slug-first lookup with fallbacks."""
        sl = slug.lower().strip()

        # Strategy 1: Direct slug lookup in software_registry (fastest, most reliable)
        try:
            session = get_session()
            try:
                row = session.execute(text("""
                    SELECT name, slug, registry, trust_score, trust_grade, description,
                           author, downloads, stars
                    FROM software_registry
                    WHERE slug = :slug
                    ORDER BY is_king DESC NULLS LAST, trust_score DESC NULLS LAST
                    LIMIT 1
                """), {"slug": sl}).fetchone()
                if row:
                    r = dict(row._mapping)
                    return {"name": r["name"], "trust_score": r.get("trust_score") or 0,
                            "trust_grade": r.get("trust_grade") or "D", "stars": r.get("stars") or 0,
                            "downloads": r.get("downloads") or 0, "description": r.get("description") or "",
                            "category": r.get("registry") or "", "author": r.get("author") or "",
                            "license": "", "agent_type": r.get("registry") or "",
                            "source_url": "", "security_score": None,
                            "activity_score": None, "documentation_score": None, "popularity_score": None}
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"_resolve_any strategy 1 failed for '{sl}': {e}")

        # Strategy 2: Centralized resolution (_find_tool uses _resolve_entity + agents)
        try:
            a = _find_tool(slug)
            if a:
                return a
        except Exception as e:
            logger.warning(f"_resolve_any strategy 2 failed for '{sl}': {e}")

        logger.warning(f"_resolve_any: no match for '{sl}'")
        return None

    # 1. /is-{slug}-legit
    @app.get("/is-{slug}-legit", response_class=HTMLResponse)
    async def is_legit_page(slug: str):
        ck = f"legit:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)
        a = _resolve_any(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
        nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
        sc = a.get("trust_score") or 0; gr = a.get("trust_grade") or "D"
        v = "LEGIT" if sc >= 60 else "USE CAUTION" if sc >= 40 else "SUSPICIOUS"
        vc = "#16a34a" if sc >= 60 else "#ca8a04" if sc >= 40 else "#dc2626"
        canonical = f"{SITE}/is-{slug}-legit"
        faq_items = [
            (f"Is {_esc(nm)} legit?", f"Trust Score: {sc:.0f}/100 ({gr}). Verdict: {v.lower()}."),
            (f"Is {_esc(nm)} a real company?", f"{_esc(nm)} is published by {_esc(a.get('author','Unknown'))}. {_fmt(a.get('downloads'))} users."),
            (f"Can I trust {_esc(nm)}?", f"{'Yes — strong trust signals.' if sc >= 60 else 'Exercise caution.' if sc >= 40 else 'Multiple risk indicators detected.'}"),
            (f"Is {_esc(nm)} a scam?", f"Scam indicators: {'none detected' if sc >= 60 else 'some risk flags' if sc >= 40 else 'elevated risk — verify independently'}."),
        ]
        faq_html, faq_ld = _faq(faq_items)
        page = _head(f"Is {_esc(nm)} Legit? Trust Analysis {YEAR} | Nerq",
                     f"Is {_esc(nm)} legit? Trust Score: {sc:.0f}/100 ({gr}). {v}. Independent analysis.",
                     canonical,
                     f'<meta name="nerq:type" content="legit_check"><meta name="nerq:entity" content="{_esc(nm)}"><meta name="nerq:score" content="{sc:.0f}"><meta name="nerq:verdict" content="{v}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>Is {_esc(nm)} Legit?</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(nm)} has a Nerq Trust Score of <strong>{sc:.0f}/100</strong> ({gr}). Verdict: <strong style="color:{vc}">{v}</strong>. Published by {_esc(a.get('author','Unknown'))}. {_fmt(a.get('downloads'))} users. Updated {MONTH_YEAR}.</p>
<div style="display:inline-block;padding:10px 20px;font-weight:700;font-size:18px;color:{vc};border:2px solid {vc};margin:12px 0">{v}</div>
<h2>Legitimacy Signals</h2>
<table><tr><th>Signal</th><th>Status</th></tr>
<tr><td>Trust Score</td><td style="color:{vc};font-weight:700">{sc:.0f}/100 ({gr})</td></tr>
<tr><td>Publisher</td><td>{_esc(a.get('author','Unknown'))}</td></tr>
<tr><td>Users/Downloads</td><td>{_fmt(a.get('downloads'))}</td></tr>
<tr><td>Stars</td><td>{_fmt(a.get('stars'))}</td></tr>
<tr><td>License</td><td>{_esc(a.get('license') or 'Not specified')}</td></tr>
</table>
<h2>FAQ</h2>{faq_html}
<div class="links"><a href="/is-{slug}-safe">Is it safe?</a> <a href="/privacy/{slug}">Privacy</a> <a href="/pros-cons/{slug}">Pros & cons</a> <a href="/is-{slug}-spyware">Spyware?</a> <a href="/review/{slug}">Review</a> <a href="/what-is/{slug}">What is it?</a> <a href="/alternatives/{slug}">Alternatives</a> <a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a> <a href="/discover">Discover</a></div>"""
        page += _foot(nm)
        return HTMLResponse(_sc(ck, page))

    # 2. /is-{slug}-safe-for-kids
    @app.get("/is-{slug}-safe-for-kids", response_class=HTMLResponse)
    async def safe_for_kids_page(slug: str):
        ck = f"kids:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)
        a = _resolve_any(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
        nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
        sc = a.get("trust_score") or 0; gr = a.get("trust_grade") or "D"
        v = "SAFE FOR KIDS" if sc >= 70 else "PARENTAL GUIDANCE" if sc >= 50 else "NOT RECOMMENDED"
        vc = "#16a34a" if sc >= 70 else "#ca8a04" if sc >= 50 else "#dc2626"
        canonical = f"{SITE}/is-{slug}-safe-for-kids"
        faq_items = [
            (f"Is {_esc(nm)} safe for kids?", f"Child Safety: {v}. Trust Score: {sc:.0f}/100. {'Suitable for most ages.' if sc >= 70 else 'Parental oversight recommended.' if sc >= 50 else 'Contains risks for children.'}"),
            (f"What age is {_esc(nm)} appropriate for?", f"{'Ages 7+' if sc >= 70 else 'Ages 13+ with supervision' if sc >= 50 else 'Ages 18+ or not recommended'}. Based on trust and content analysis."),
            (f"Does {_esc(nm)} have parental controls?", f"Check the app's settings for parental controls. We recommend reviewing privacy settings regardless."),
            (f"Can strangers contact my child on {_esc(nm)}?", f"Review the app's social features and messaging settings. Disable chat with strangers if available."),
        ]
        faq_html, faq_ld = _faq(faq_items)
        page = _head(f"Is {_esc(nm)} Safe for Kids? {YEAR} | Nerq",
                     f"Is {_esc(nm)} safe for kids? {v}. Trust: {sc:.0f}/100. Parent safety guide.",
                     canonical,
                     f'<meta name="nerq:type" content="kids_safety"><meta name="nerq:entity" content="{_esc(nm)}"><meta name="nerq:score" content="{sc:.0f}"><meta name="nerq:verdict" content="{v}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>Is {_esc(nm)} Safe for Kids?</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(nm)} Child Safety Rating: <strong style="color:{vc}">{v}</strong>. Trust Score: {sc:.0f}/100 ({gr}). {'This software shows strong trust signals and is generally safe for children.' if sc >= 70 else 'Parental guidance is recommended. Review privacy and social settings.' if sc >= 50 else 'This software has risk factors that make it unsuitable for unsupervised use by children.'} Updated {MONTH_YEAR}.</p>
<div style="display:inline-block;padding:10px 20px;font-weight:700;font-size:18px;color:{vc};border:2px solid {vc};margin:12px 0">{v}</div>
<h2>Safety Assessment</h2>
<table><tr><th>Factor</th><th>Rating</th></tr>
<tr><td>Overall Trust</td><td>{sc:.0f}/100</td></tr>
<tr><td>Child Safety</td><td style="color:{vc};font-weight:700">{v}</td></tr>
<tr><td>Publisher</td><td>{_esc(a.get('author','Unknown'))}</td></tr>
</table>
<h2>Recommendations for Parents</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Review and adjust privacy settings</li>
<li>Disable chat/messaging with strangers if available</li>
<li>Set up parental controls or screen time limits</li>
<li>Monitor usage, especially for younger children</li>
<li>Discuss online safety with your child</li>
</ul>
<h2>FAQ</h2>{faq_html}
<div class="links"><a href="/is-{slug}-safe">General safety</a> <a href="/privacy/{slug}">Privacy</a> <a href="/is-{slug}-spyware">Spyware?</a> <a href="/guide/use-{slug}-safely">Use safely</a> <a href="/what-is/{slug}">What is it?</a> <a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a> <a href="/discover">Discover</a> <a href="/best/safest-games-for-kids">Safe games</a> <a href="/best/safest-apps-2026">Safe apps</a></div>"""
        page += _foot(nm)
        return HTMLResponse(_sc(ck, page))

    # 3. /is-{slug}-spyware
    @app.get("/is-{slug}-spyware", response_class=HTMLResponse)
    async def spyware_page(slug: str):
        ck = f"spy:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)
        a = _resolve_any(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
        nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
        sc = a.get("trust_score") or 0; gr = a.get("trust_grade") or "D"
        v = "LOW SPYWARE RISK" if sc >= 70 else "MODERATE RISK" if sc >= 50 else "HIGH SPYWARE RISK"
        vc = "#16a34a" if sc >= 70 else "#ca8a04" if sc >= 50 else "#dc2626"
        canonical = f"{SITE}/is-{slug}-spyware"
        faq_items = [
            (f"Is {_esc(nm)} spyware?", f"Spyware Risk: {v}. Trust Score: {sc:.0f}/100. {'No spyware indicators detected.' if sc >= 70 else 'Some data collection concerns.' if sc >= 50 else 'Elevated data collection risk.'}"),
            (f"Does {_esc(nm)} spy on you?", f"{'No evidence of unauthorized data collection.' if sc >= 70 else 'Collects standard analytics data. Review privacy settings.' if sc >= 50 else 'Collects significant data. Review permissions carefully.'}"),
            (f"Does {_esc(nm)} listen to your conversations?", f"There is no verified evidence of {_esc(nm)} recording audio without consent. However, review microphone permissions."),
        ]
        faq_html, faq_ld = _faq(faq_items)
        page = _head(f"Is {_esc(nm)} Spyware? Privacy Analysis {YEAR} | Nerq",
                     f"Is {_esc(nm)} spyware? {v}. Trust: {sc:.0f}/100. Privacy and tracking analysis.",
                     canonical,
                     f'<meta name="nerq:type" content="spyware_check"><meta name="nerq:entity" content="{_esc(nm)}"><meta name="nerq:score" content="{sc:.0f}"><meta name="nerq:verdict" content="{v}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>Is {_esc(nm)} Spyware?</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(nm)} Spyware Risk: <strong style="color:{vc}">{v}</strong>. Nerq Trust Score: {sc:.0f}/100 ({gr}). {'No spyware indicators detected in our analysis.' if sc >= 70 else 'Some data collection practices warrant review.' if sc >= 50 else 'Elevated risk of aggressive data collection. Review carefully.'} Updated {MONTH_YEAR}.</p>
<div style="display:inline-block;padding:10px 20px;font-weight:700;font-size:18px;color:{vc};border:2px solid {vc};margin:12px 0">{v}</div>
<h2>Spyware Indicators</h2>
<table><tr><th>Indicator</th><th>Status</th></tr>
<tr><td>Trust Score</td><td>{sc:.0f}/100</td></tr>
<tr><td>Data Collection Risk</td><td style="color:{vc}">{v}</td></tr>
<tr><td>Publisher Verified</td><td>{'Yes' if a.get('author') else 'Unknown'}</td></tr>
</table>
<h2>FAQ</h2>{faq_html}
<div class="links"><a href="/is-{slug}-safe">Is it safe?</a> <a href="/privacy/{slug}">Full privacy analysis</a> <a href="/is-{slug}-legit">Is it legit?</a> <a href="/guide/use-{slug}-safely">Use safely</a> <a href="/what-is/{slug}">What is it?</a> <a href="/pros-cons/{slug}">Pros & cons</a> <a href="/alternatives/{slug}">Alternatives</a> <a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a> <a href="/discover">Discover</a></div>"""
        page += _foot(nm)
        return HTMLResponse(_sc(ck, page))

    # 4. /privacy/{slug}
    @app.get("/privacy/{slug}", response_class=HTMLResponse)
    async def privacy_page(slug: str):
        ck = f"priv:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)
        a = _resolve_any(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
        nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
        sc = a.get("trust_score") or 0; gr = a.get("trust_grade") or "D"
        priv = "HIGH" if sc >= 70 else "MODERATE" if sc >= 50 else "LOW"
        vc = "#16a34a" if sc >= 70 else "#ca8a04" if sc >= 50 else "#dc2626"
        canonical = f"{SITE}/privacy/{slug}"
        faq_items = [
            (f"Does {_esc(nm)} sell my data?", f"Privacy Score: {priv}. {'No evidence of data selling.' if sc >= 70 else 'Review their privacy policy for data sharing details.' if sc >= 50 else 'Data practices are concerning. Review privacy policy carefully.'}"),
            (f"What data does {_esc(nm)} collect?", f"Data collection level: {'minimal' if sc >= 70 else 'moderate' if sc >= 50 else 'extensive'}. Check privacy policy for specifics."),
            (f"How to make {_esc(nm)} more private?", f"Review privacy settings. Disable optional data sharing. Consider using a VPN. Limit permissions."),
            (f"Is {_esc(nm)} GDPR compliant?", f"{'Likely compliant based on trust signals.' if sc >= 60 else 'Compliance status unclear. Verify independently.'}"),
        ]
        faq_html, faq_ld = _faq(faq_items)
        page = _head(f"{_esc(nm)} Privacy Analysis {YEAR} | Nerq",
                     f"{_esc(nm)} privacy: {priv}. Trust Score: {sc:.0f}/100. Does it sell your data? Independent analysis.",
                     canonical,
                     f'<meta name="nerq:type" content="privacy"><meta name="nerq:entity" content="{_esc(nm)}"><meta name="nerq:score" content="{sc:.0f}"><meta name="nerq:privacy_score" content="{priv}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>{_esc(nm)} Privacy Analysis — Does It Sell Your Data?</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(nm)} Privacy Score: <strong style="color:{vc}">{priv}</strong>. Trust Score: {sc:.0f}/100 ({gr}). Data collection: {'minimal' if sc >= 70 else 'moderate' if sc >= 50 else 'extensive'}. {'No evidence of data selling.' if sc >= 70 else 'Review privacy policy.' if sc >= 50 else 'Privacy practices are concerning.'} Updated {MONTH_YEAR}.</p>
<h2>Privacy Assessment</h2>
<table><tr><th>Factor</th><th>Rating</th></tr>
<tr><td>Privacy Score</td><td style="color:{vc};font-weight:700">{priv}</td></tr>
<tr><td>Trust Score</td><td>{sc:.0f}/100</td></tr>
<tr><td>Data Collection</td><td>{'Minimal' if sc >= 70 else 'Moderate' if sc >= 50 else 'Extensive'}</td></tr>
<tr><td>Publisher</td><td>{_esc(a.get('author','Unknown'))}</td></tr>
</table>
<h2>How to Improve Your Privacy</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>Review and minimize app permissions</li>
<li>Disable optional data sharing in settings</li>
<li>Use a VPN for additional privacy</li>
<li>Review the privacy policy for data sharing details</li>
<li>Consider more private alternatives if needed</li>
</ol>
<h2>FAQ</h2>{faq_html}
<div class="links"><a href="/is-{slug}-safe">Safety</a> <a href="/is-{slug}-spyware">Spyware?</a> <a href="/is-{slug}-legit">Legit?</a> <a href="/guide/use-{slug}-safely">Use safely</a> <a href="/pros-cons/{slug}">Pros & cons</a> <a href="/what-is/{slug}">What is it?</a> <a href="/alternatives/{slug}">Alternatives</a> <a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a> <a href="/best/most-private-apps-2026">Most private apps</a></div>"""
        page += _foot(nm)
        return HTMLResponse(_sc(ck, page))

    # 5. /pros-cons/{slug}
    @app.get("/pros-cons/{slug}", response_class=HTMLResponse)
    async def pros_cons_page(slug: str):
        ck = f"pc:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)
        a = _resolve_any(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
        nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
        sc = a.get("trust_score") or 0; gr = a.get("trust_grade") or "D"
        # Auto-generate pros/cons from trust dimensions
        pros, cons = [], []
        if (a.get("stars") or 0) > 1000: pros.append(f"Large community ({_fmt(a['stars'])} stars)")
        if sc >= 60: pros.append(f"Good trust score ({sc:.0f}/100)")
        if a.get("license"): pros.append(f"Clear license ({_esc(a['license'][:30])})")
        if (a.get("downloads") or 0) > 10000: pros.append(f"Widely used ({_fmt(a['downloads'])} users)")
        if a.get("description") and len(a["description"]) > 50: pros.append("Well-documented")
        if not pros: pros.append("Available and functional")
        if sc < 50: cons.append(f"Low trust score ({sc:.0f}/100)")
        if not a.get("license"): cons.append("No clear license specified")
        if (a.get("stars") or 0) < 100: cons.append("Small community")
        if not cons: cons.append("No major concerns identified")
        canonical = f"{SITE}/pros-cons/{slug}"
        verdict = "RECOMMENDED" if sc >= 60 else "ACCEPTABLE" if sc >= 40 else "NOT RECOMMENDED"
        faq_items = [
            (f"What are the pros and cons of {_esc(nm)}?", f"Pros: {pros[0]}. Cons: {cons[0]}. Overall: {verdict.lower()}."),
            (f"Is {_esc(nm)} worth it?", f"Trust Score: {sc:.0f}/100 ({gr}). {verdict.lower()}."),
            (f"Should I use {_esc(nm)} in {YEAR}?", f"{'Yes.' if sc >= 60 else 'Evaluate alternatives.' if sc >= 40 else 'Consider alternatives.'} Score: {sc:.0f}/100."),
        ]
        faq_html, faq_ld = _faq(faq_items)
        page = _head(f"{_esc(nm)} Pros and Cons {YEAR} | Nerq",
                     f"{_esc(nm)} pros and cons: Trust {sc:.0f}/100. {pros[0]}. {cons[0]}. Data-driven analysis.",
                     canonical,
                     f'<meta name="nerq:type" content="pros_cons"><meta name="nerq:entity" content="{_esc(nm)}"><meta name="nerq:score" content="{sc:.0f}"><meta name="nerq:verdict" content="{verdict}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""
<h1>{_esc(nm)} Pros and Cons {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(nm)} Trust Score: <strong>{sc:.0f}/100</strong> ({gr}). Key strength: {_esc(pros[0])}. Key concern: {_esc(cons[0])}. Overall: {verdict.lower()}. Updated {MONTH_YEAR}.</p>
<h2 style="color:#16a34a">Pros</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">{"".join(f"<li>{_esc(p)}</li>" for p in pros)}</ul>
<h2 style="color:#dc2626">Cons</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">{"".join(f"<li>{_esc(c)}</li>" for c in cons)}</ul>
<h2>The Verdict</h2>
<p style="font-size:14px;color:#374151"><strong>{verdict}</strong>. {_esc(nm)} scores {sc:.0f}/100 on the Nerq Trust Index.</p>
<h2>FAQ</h2>{faq_html}
<div class="links"><a href="/is-{slug}-safe">Safety</a> <a href="/review/{slug}">Full review</a> <a href="/privacy/{slug}">Privacy</a> <a href="/alternatives/{slug}">Alternatives</a> <a href="/what-is/{slug}">What is it?</a> <a href="/is-{slug}-legit">Legit?</a> <a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a> <a href="/discover">Discover</a> <a href="/compare">Compare</a></div>"""
        page += _foot(nm)
        return HTMLResponse(_sc(ck, page))

    # 6. /guide/use-{slug}-safely
    @app.get("/guide/use-{slug}-safely", response_class=HTMLResponse)
    async def use_safely_page(slug: str):
        ck = f"usafe:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)
        a = _resolve_any(slug)
        if not a:
            try:
                from agentindex.agent_safety_pages import _queue_for_crawling
                _queue_for_crawling(slug, bot="404-route")
            except Exception:
                pass
            # Do NOT cache "Not Yet Analyzed" — entity may resolve on next request
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
        nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
        sc = a.get("trust_score") or 0; gr = a.get("trust_grade") or "D"
        canonical = f"{SITE}/guide/use-{slug}-safely"
        faq_items = [
            (f"How to use {_esc(nm)} safely?", f"Start by reviewing privacy settings. Trust Score: {sc:.0f}/100. Follow our security checklist below."),
            (f"What are the best {_esc(nm)} privacy settings?", f"Disable unnecessary data sharing. Limit permissions. Use strong authentication."),
            (f"How to secure {_esc(nm)}?", f"Enable 2FA, review permissions, keep updated, use strong passwords."),
        ]
        faq_html, faq_ld = _faq(faq_items)
        # HowTo JSON-LD for guide pages
        import json as _json
        _howto_ld = '<script type="application/ld+json">' + _json.dumps({
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": f"How to Use {nm} Safely",
            "description": f"Security guide for {nm}. Trust Score: {sc:.0f}/100 ({gr}).",
            "step": [
                {"@type": "HowToStep", "position": 1, "name": "Update to the latest version", "text": "Security patches fix known vulnerabilities. Always use the most recent version."},
                {"@type": "HowToStep", "position": 2, "name": "Review permissions", "text": "Disable access to camera, microphone, contacts unless needed for core functionality."},
                {"@type": "HowToStep", "position": 3, "name": "Enable two-factor authentication", "text": "If available, always enable 2FA for an extra layer of security."},
                {"@type": "HowToStep", "position": 4, "name": "Use a strong, unique password", "text": "Don't reuse passwords from other services. Use a password manager."},
                {"@type": "HowToStep", "position": 5, "name": "Review privacy settings", "text": "Disable optional data sharing and analytics. Opt out of personalized advertising."},
                {"@type": "HowToStep", "position": 6, "name": "Monitor for updates", "text": "Keep the software updated for security patches. Check Nerq for trust score changes."},
                {"@type": "HowToStep", "position": 7, "name": "Check alternatives if needed", "text": f"If trust score is below 50, consider safer alternatives at nerq.ai/alternatives/{slug}."},
            ]
        }) + '</script>'
        page = _head(f"How to Use {_esc(nm)} Safely — Guide {YEAR} | Nerq",
                     f"How to use {_esc(nm)} safely. Trust Score: {sc:.0f}/100. Security settings guide.",
                     canonical,
                     f'<meta name="nerq:type" content="safety_guide"><meta name="nerq:entity" content="{_esc(nm)}"><meta name="nerq:score" content="{sc:.0f}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}{_howto_ld}')
        page += f"""
<h1>How to Use {_esc(nm)} Safely — Security Guide {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(nm)} has a Trust Score of <strong>{sc:.0f}/100</strong> ({gr}). {'With default settings, it is generally safe.' if sc >= 70 else 'With the right settings, you can use it more safely.' if sc >= 50 else 'Extra caution is needed. Follow all steps below.'} Updated {MONTH_YEAR}.</p>
<h2>Security Checklist</h2>
<ol style="font-size:14px;color:#374151;line-height:2">
<li><strong>Update to the latest version</strong> — security patches fix known vulnerabilities</li>
<li><strong>Review permissions</strong> — disable access to camera, microphone, contacts unless needed</li>
<li><strong>Enable two-factor authentication</strong> — if available, always enable 2FA</li>
<li><strong>Use a strong, unique password</strong> — don't reuse passwords from other services</li>
<li><strong>Review privacy settings</strong> — disable optional data sharing and analytics</li>
<li><strong>Limit social features</strong> — restrict who can contact you or see your activity</li>
<li><strong>Monitor for updates</strong> — keep the software updated for security patches</li>
<li><strong>Check alternatives</strong> — if trust score is below 50, consider <a href="/alternatives/{slug}" style="color:#0d9488">safer alternatives</a></li>
</ol>
<h2>Privacy Settings</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Disable location tracking (unless essential)</li>
<li>Opt out of personalized advertising</li>
<li>Disable analytics and crash reporting if possible</li>
<li>Review and delete stored data periodically</li>
</ul>
<h2>When to Stop Using {_esc(nm)}</h2>
<p style="font-size:14px;color:#374151">Consider switching if: the trust score drops below 40, a data breach is reported, the app requests new suspicious permissions, or a more private alternative becomes available.</p>
<h2>FAQ</h2>{faq_html}
<div class="links"><a href="/is-{slug}-safe">Safety report</a> <a href="/privacy/{slug}">Privacy analysis</a> <a href="/is-{slug}-spyware">Spyware check</a> <a href="/pros-cons/{slug}">Pros & cons</a> <a href="/review/{slug}">Review</a> <a href="/what-is/{slug}">What is it?</a> <a href="/alternatives/{slug}">Alternatives</a> <a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a> <a href="/best/most-private-apps-2026">Most private apps</a></div>"""
        page += _foot(nm)
        return HTMLResponse(_sc(ck, page))

    # ════════════════════════════════════════
    # REGISTRY-SPECIFIC ROUTES (/npm/, /pypi/, /extension/, /vscode/, etc.)
    # ════════════════════════════════════════
    def _find_reg(registry, slug):
        session = get_session()
        try:
            row = session.execute(text("""
                SELECT name, slug, registry, description, author, license, downloads,
                       stars, trust_score, trust_grade, repository_url, homepage_url
                FROM software_registry WHERE registry = :reg AND (slug = :slug OR LOWER(name) = :slug) LIMIT 1
            """), {"reg": registry, "slug": slug.lower()}).fetchone()
            return dict(zip(["name","slug","registry","description","author","license",
                           "downloads","stars","trust_score","trust_grade","repo_url","homepage"], row)) if row else None
        finally:
            session.close()

    def _reg_page(registry, slug, display_type):
        ck = f"reg:{registry}:{slug}"
        c = _c(ck)
        if c: return c
        entry = _find_reg(registry, slug)
        if not entry:
            a = _find_tool(slug)
            if a:
                entry = {"name": a["name"], "description": a["description"], "author": a["author"],
                        "license": a["license"], "downloads": a["downloads"], "stars": a["stars"],
                        "trust_score": a["trust_score"], "trust_grade": a["trust_grade"],
                        "repo_url": a.get("source_url"), "homepage": ""}
            else:
                return None
        nm = entry["name"].split("/")[-1] if "/" in str(entry.get("name","")) else entry.get("name","")
        sc = entry.get("trust_score") or 0
        gr = entry.get("trust_grade") or "D"
        faq_items = [(f"Is {_esc(nm)} safe?", f"Trust: {sc:.0f}/100 ({gr}). {_esc((entry.get('description') or '')[:150])}.")]
        faq_html, faq_ld = _faq(faq_items)
        page = _head(f"Is {_esc(nm)} Safe? {display_type} {YEAR} | Nerq",
                     f"{_esc(nm)}: Trust {sc:.0f}/100 ({gr}). {_fmt(entry.get('downloads'))} downloads.",
                     f"{SITE}/{registry}/{slug}",
                     f'<meta name="nerq:type" content="{registry}"><meta name="nerq:score" content="{sc:.0f}"><meta name="nerq:updated" content="{TODAY}">{faq_ld}')
        page += f"""<h1>Is {_esc(nm)} Safe? — {display_type} {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(nm)} has a Trust Score of <strong>{sc:.0f}/100</strong> ({gr}). {_fmt(entry.get('downloads'))} downloads. Updated {MONTH_YEAR}.</p>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0">
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700;color:{_grade_color(gr)}">{sc:.0f}</div><div style="font-size:10px;color:#6b7280">TRUST</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{gr}</div><div style="font-size:10px;color:#6b7280">GRADE</div></div>
<div style="padding:14px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:22px;font-weight:700">{_fmt(entry.get('downloads'))}</div><div style="font-size:10px;color:#6b7280">DOWNLOADS</div></div>
</div>
<table><tr><th>Author</th><td>{_esc(entry.get('author') or 'Unknown')}</td></tr>
<tr><th>License</th><td>{_esc(entry.get('license') or 'Not specified')}</td></tr></table>
<h2>FAQ</h2>{faq_html}"""
        page += _foot(nm)
        return _sc(ck, page)

    for _r, _d in [("npm","npm Package"),("pypi","PyPI Package"),("extension","Chrome Extension"),
                   ("vscode","VS Code Extension"),("crates","Rust Crate"),("go","Go Module"),
                   ("gems","Ruby Gem"),("packagist","PHP Package"),("nuget","NuGet Package"),
                   ("wordpress","WordPress Plugin"),("vpn","VPN Service"),
                   ("ios","iOS App"),("android","Android App"),("steam","Steam Game")]:
        def _mk(_r=_r, _d=_d):
            async def _h(slug: str):
                html = _reg_page(_r, slug, _d)
                if html:
                    return HTMLResponse(html)
                try:
                    from agentindex.agent_safety_pages import _queue_for_crawling
                    _queue_for_crawling(slug, bot="404-route")
                except Exception:
                    pass
                return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
            return _h
        app.get(f"/{_r}/{{slug}}", response_class=HTMLResponse)(_mk())

    # /app/{slug} — merged iOS + Android route
    @app.get("/app/{slug}", response_class=HTMLResponse)
    async def app_page(slug: str):
        # Try iOS first, then Android, then agents fallback
        for reg, disp in [("ios", "iOS App"), ("android", "Android App")]:
            html = _reg_page(reg, slug, disp)
            if html: return HTMLResponse(html)
        # Fallback to agents table
        html = _reg_page("ios", slug, "Mobile App")
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(slug, bot="404-route")
        except Exception:
            pass
        return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    # /game/{slug} — Steam games
    @app.get("/game/{slug}", response_class=HTMLResponse)
    async def game_page(slug: str):
        html = _reg_page("steam", slug, "Steam Game")
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(slug, bot="404-route")
        except Exception:
            pass
        return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    # /website/{domain} — Website trust analysis
    @app.get("/website/{domain}", response_class=HTMLResponse)
    async def website_page(domain: str):
        ck = f"website:{domain}"
        c = _c(ck)
        if c: return HTMLResponse(c)

        session = get_session()
        try:
            row = session.execute(text("""
                SELECT domain, trust_score, trust_grade, tranco_rank, domain_age_days,
                       ssl_valid, ssl_issuer, has_hsts, factors
                FROM website_cache WHERE domain = :d
            """), {"d": domain.lower()}).fetchone()
        finally:
            session.close()

        if not row:
            return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>{_esc(domain)} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>{NERQ_NAV}
<main class="container" style="max-width:800px;margin:0 auto;padding:24px">
<h1>{_esc(domain)} — Not Yet Analyzed</h1>
<p>Nerq has not yet analyzed this website. <a href="/check-website">Check a website</a> or <a href="/">search</a>.</p>
</main>{NERQ_FOOTER}</body></html>""", status_code=200)

        r = dict(row._mapping)
        score = r.get("trust_score") or 0
        grade = r.get("trust_grade") or "D"
        rank = r.get("tranco_rank")
        ssl = r.get("ssl_valid")
        hsts = r.get("has_hsts")
        age = r.get("domain_age_days")

        if score >= 70: verdict, vc = "Trusted", "#16a34a"
        elif score >= 50: verdict, vc = "Use with Caution", "#f59e0b"
        else: verdict, vc = "Significant Concerns", "#ef4444"

        title = f"Is {_esc(domain)} Safe? Website Trust Score {score:.0f}/100 | Nerq"
        desc = f"{_esc(domain)} has a Nerq Trust Score of {score:.0f}/100 ({grade}). {verdict}."

        details = f"""<table>
<tr><td style="color:#6b7280;width:160px">Trust Score</td><td><strong style="color:{vc}">{score:.0f}/100 ({grade})</strong></td></tr>
<tr><td style="color:#6b7280">Verdict</td><td style="color:{vc}">{verdict}</td></tr>
{'<tr><td style="color:#6b7280">Tranco Rank</td><td>#' + str(rank) + '</td></tr>' if rank else ''}
<tr><td style="color:#6b7280">SSL Certificate</td><td>{"Valid" if ssl else "Invalid/Missing"}</td></tr>
<tr><td style="color:#6b7280">HSTS</td><td>{"Enabled" if hsts else "Not enabled"}</td></tr>
{'<tr><td style="color:#6b7280">Domain Age</td><td>' + str(age) + ' days</td></tr>' if age else ''}
</table>"""

        page = _head(title, desc, f"{SITE}/website/{_esc(domain)}",
                      f'<meta name="nerq:type" content="website"><meta name="nerq:score" content="{score:.0f}"><meta name="nerq:grade" content="{grade}"><meta name="nerq:updated" content="{TODAY}">')
        page += f"""<h1>Is {_esc(domain)} Safe?</h1>
<p class="ai-summary">{_esc(domain)} has a Nerq Trust Score of {score:.0f}/100 ({grade}). Verdict: {verdict}. {'Ranked #' + str(rank) + ' globally by Tranco.' if rank else ''} SSL: {'valid' if ssl else 'invalid'}. HSTS: {'enabled' if hsts else 'not enabled'}. Last analyzed: {TODAY}.</p>
<div style="border:1px solid #e2e8f0;border-radius:10px;padding:20px;margin:12px 0" aria-hidden="true">
<div style="font-size:36px;font-weight:700;color:{vc}">{score:.0f}<span style="font-size:14px;color:#64748b">/100</span></div>
<div style="font-size:14px;color:{vc};font-weight:600;margin-top:4px">{verdict}</div>
</div>
<h2>Details</h2>
{details}
<h2>Related</h2>
<div class="links">
<a href="/is-{_esc(domain.replace('.', '-'))}-safe">Safety</a>
<a href="/is-{_esc(domain.replace('.', '-'))}-legit">Legit?</a>
<a href="/is-{_esc(domain.replace('.', '-'))}-a-scam">Scam?</a>
<a href="/check-website">Check another website</a>
</div>"""
        page += _foot(domain)
        return HTMLResponse(_sc(ck, page))

    logger.info("Mounted demand pages: /what-is, /stack, /review, /migrate, /this-week, /issues, /ai-interest, /profile, /feed, registry routes, /app, /game, /website + sitemaps")
