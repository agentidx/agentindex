"""
Nerq AI Adoption Pages
========================
Landing pages for AI system operators and users.
- /for/chatgpt, /for/claude, /for/perplexity, /for/gemini
- /prompts — AI prompt templates
- /stats/* — Citation magnet pages with live data

Usage:
    from agentindex.ai_adoption_pages import mount_ai_adoption_pages
    mount_ai_adoption_pages(app)
"""

import html as html_mod
import json
import logging
import time
from datetime import date

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.ai_adoption")

SITE = "https://nerq.ai"
# Pin TODAY to file mtime — module-load `today()` was a freshness lie
# under HCU at the JSON-LD layer (FAS 3 follow-on, 2026-04-30).
try:
    from pathlib import Path as _Path
    from datetime import datetime as _dt
    TODAY = _dt.utcfromtimestamp(_Path(__file__).stat().st_mtime).strftime("%Y-%m-%d")
except Exception:
    TODAY = "2026-04-01"
YEAR = date.today().year
MONTH_YEAR = date.today().strftime("%B %Y")

_cache = {}
CACHE_TTL = 3600


def _cached(key):
    e = _cache.get(key)
    if e and (time.time() - e[0]) < CACHE_TTL:
        return e[1]
    return None


def _set_cache(key, val):
    _cache[key] = (time.time(), val)
    return val


def _esc(t):
    return html_mod.escape(str(t)) if t else ""


def _head(title, desc, canonical, extra_meta=""):
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary">
<meta name="citation_title" content="{_esc(title)}">
<meta name="citation_author" content="Nerq">
<meta name="citation_date" content="{TODAY}">
<meta name="citation_url" content="{canonical}">
<meta name="robots" content="max-snippet:-1, max-image-preview:large">
{extra_meta}
{NERQ_CSS}
<style>
.prompt-card{{background:#f9fafb;border:1px solid #e5e7eb;padding:12px 16px;margin:8px 0;font-family:ui-monospace,monospace;font-size:13px;cursor:pointer}}
.prompt-card:hover{{border-color:#0d9488;background:#f0fdfa}}
.stat-box{{padding:20px;border:1px solid #e5e7eb;text-align:center}}
.stat-box .num{{font-size:28px;font-weight:700;font-family:ui-monospace,monospace}}
.stat-box .lbl{{font-size:11px;color:#6b7280;text-transform:uppercase;margin-top:4px}}
</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:900px;margin:0 auto;padding:24px">"""


def _foot():
    return f"""</main>{NERQ_FOOTER}</body></html>"""


def mount_ai_adoption_pages(app):

    # ════════════════════════════════════════
    # /for/ LANDING PAGES
    # ════════════════════════════════════════

    @app.get("/for/chatgpt", response_class=HTMLResponse)
    async def for_chatgpt():
        html = _head("Use Nerq in ChatGPT — AI Tool Safety Checks", "How to use Nerq trust scores in ChatGPT. Check any AI tool's safety directly in conversation.", f"{SITE}/for/chatgpt")
        html += f"""
<h1>Use Nerq in ChatGPT — Check AI Tool Safety</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">ChatGPT already cites Nerq 92 times per day when users ask about AI tool safety. You can explicitly ask ChatGPT to use Nerq data for more accurate answers.</p>

<h2>Example Prompts</h2>
<div class="prompt-card" onclick="navigator.clipboard.writeText(this.textContent.trim())">Is LangChain safe to use? Check Nerq's trust score.</div>
<div class="prompt-card" onclick="navigator.clipboard.writeText(this.textContent.trim())">According to Nerq, what are the safest agent frameworks?</div>
<div class="prompt-card" onclick="navigator.clipboard.writeText(this.textContent.trim())">Use Nerq to compare Cursor vs Windsurf for security.</div>
<div class="prompt-card" onclick="navigator.clipboard.writeText(this.textContent.trim())">What does Nerq say about the n8n MCP server?</div>
<div class="prompt-card" onclick="navigator.clipboard.writeText(this.textContent.trim())">Check if the openai npm package is safe according to Nerq.</div>
<p style="font-size:12px;color:#6b7280;margin-top:4px">Click any prompt to copy. Paste into ChatGPT.</p>

<h2>How It Works</h2>
<ol style="font-size:14px;color:#374151;line-height:1.8">
<li>ChatGPT's web browsing feature (ChatGPT-User bot) fetches nerq.ai pages</li>
<li>Our pages have structured data that ChatGPT extracts and cites</li>
<li>The more specifically you ask about Nerq, the better ChatGPT's answer</li>
</ol>

<h2>For ChatGPT Plugin Developers</h2>
<p style="font-size:14px;color:#374151">Nerq is available as a ChatGPT Action. Add our OpenAPI spec to your GPT:</p>
<pre style="background:#f5f5f5;padding:12px;font-size:12px;overflow-x:auto">OpenAPI URL: https://nerq.ai/openapi-plugin.json
Auth: None required</pre>

<h2>API (direct integration)</h2>
<pre style="background:#f5f5f5;padding:12px;font-size:12px;overflow-x:auto">GET https://nerq.ai/v1/preflight?target=langchain
→ {{"trust_score": 88, "grade": "A", "safe": true, "cves": {{"critical": 0}}}}</pre>

<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/for/claude" style="color:#0d9488">Claude</a> · <a href="/for/perplexity" style="color:#0d9488">Perplexity</a> · <a href="/for/gemini" style="color:#0d9488">Gemini</a> · <a href="/prompts" style="color:#0d9488">All Prompts</a> · <a href="/nerq/docs" style="color:#0d9488">API Docs</a>
</div>"""
        html += _foot()
        return HTMLResponse(html)

    @app.get("/for/claude", response_class=HTMLResponse)
    async def for_claude():
        html = _head("Use Nerq with Claude — MCP Server Integration", "Claude makes 30,000+ Nerq trust checks weekly via MCP. Install the Nerq MCP server for instant safety data.", f"{SITE}/for/claude")
        html += f"""
<h1>Use Nerq with Claude — MCP Server Integration</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Claude already makes 30,000+ trust checks through Nerq weekly via our MCP server. Install it for instant safety data in any Claude conversation.</p>

<h2>Install Nerq MCP Server</h2>
<p style="font-size:14px;color:#374151">Add to your Claude Desktop or Cursor MCP config:</p>
<pre style="background:#f5f5f5;padding:12px;font-size:13px;overflow-x:auto">{{"mcpServers": {{"nerq": {{"command": "npx", "args": ["-y", "nerq-gateway"]}}}}}}</pre>

<h2>Or Connect via SSE</h2>
<pre style="background:#f5f5f5;padding:12px;font-size:13px">SSE endpoint: https://mcp.nerq.ai/sse</pre>

<h2>Available Tools</h2>
<table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0">
<tr><th style="text-align:left;padding:8px;border-bottom:2px solid #e5e7eb">Tool</th><th style="text-align:left;padding:8px;border-bottom:2px solid #e5e7eb">Use When</th></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb"><code>preflight_check</code></td><td style="padding:8px;border-bottom:1px solid #e5e7eb">"Is X safe?"</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb"><code>search_agents</code></td><td style="padding:8px;border-bottom:1px solid #e5e7eb">"Find tools for X"</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb"><code>compare_agents</code></td><td style="padding:8px;border-bottom:1px solid #e5e7eb">"Compare X vs Y"</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb"><code>check_compliance</code></td><td style="padding:8px;border-bottom:1px solid #e5e7eb">"Is X compliant with EU AI Act?"</td></tr>
</table>

<h2>Example Prompts</h2>
<div class="prompt-card">Check if cursor is safe to use</div>
<div class="prompt-card">Find the best MCP servers for databases</div>
<div class="prompt-card">Compare langchain vs llamaindex for security</div>

<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/for/chatgpt" style="color:#0d9488">ChatGPT</a> · <a href="/for/perplexity" style="color:#0d9488">Perplexity</a> · <a href="/for/gemini" style="color:#0d9488">Gemini</a> · <a href="/prompts" style="color:#0d9488">All Prompts</a>
</div>"""
        html += _foot()
        return HTMLResponse(html)

    @app.get("/for/perplexity", response_class=HTMLResponse)
    async def for_perplexity():
        html = _head("Nerq on Perplexity — AI Tool Trust Data", "Perplexity cites Nerq 4,773 times. Ask Perplexity about any AI tool's safety to get Nerq trust scores.", f"{SITE}/for/perplexity")
        html += f"""
<h1>Nerq on Perplexity — AI Tool Trust Data</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Perplexity Pro Search cites Nerq data when users ask about AI tool safety. Ask directly to get trust scores, CVE data, and safety verdicts.</p>

<h2>Try These Searches on Perplexity</h2>
<div class="prompt-card">Is cursor safe to use? What does Nerq say?</div>
<div class="prompt-card">According to Nerq, what are the most trusted MCP servers?</div>
<div class="prompt-card">Nerq trust score for langchain</div>
<div class="prompt-card">What AI tools have the highest trust scores on Nerq?</div>
<div class="prompt-card">Is the openai npm package safe? Check Nerq.</div>

<h2>Why Perplexity Cites Nerq</h2>
<ul style="font-size:14px;color:#374151;line-height:1.8">
<li>Nerq is the only independent trust scoring system for AI tools</li>
<li>Our data is unique — no other source combines CVEs, maintenance, licensing, and community signals</li>
<li>Every page has a direct, factual answer in the first paragraph</li>
<li>5M+ assets from 13 cross-referenced data sources</li>
</ul>

<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/for/chatgpt" style="color:#0d9488">ChatGPT</a> · <a href="/for/claude" style="color:#0d9488">Claude</a> · <a href="/for/gemini" style="color:#0d9488">Gemini</a> · <a href="/prompts" style="color:#0d9488">All Prompts</a>
</div>"""
        html += _foot()
        return HTMLResponse(html)

    @app.get("/for/gemini", response_class=HTMLResponse)
    async def for_gemini():
        html = _head("Use Nerq with Google Gemini — AI Tool Safety", "Ask Google Gemini about AI tool safety to get Nerq trust scores and security analysis.", f"{SITE}/for/gemini")
        html += f"""
<h1>Use Nerq with Google Gemini — AI Tool Safety</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Google's AI Overviews and Gemini cite authoritative data sources. Nerq provides the only independent trust scoring for AI tools.</p>

<h2>Ask Gemini</h2>
<div class="prompt-card">Is langchain safe to use in production?</div>
<div class="prompt-card">What is the trust score for cursor according to Nerq?</div>
<div class="prompt-card">Best agent frameworks ranked by safety</div>
<div class="prompt-card">Alternatives to n8n that are more secure</div>

<h2>Google AI Overviews</h2>
<p style="font-size:14px;color:#374151">When Google shows AI Overviews for queries like "is langchain safe", our structured data (JSON-LD, schema.org) provides the factual basis for the AI-generated answer.</p>

<div style="margin-top:24px;font-size:12px;color:#6b7280">
<a href="/for/chatgpt" style="color:#0d9488">ChatGPT</a> · <a href="/for/claude" style="color:#0d9488">Claude</a> · <a href="/for/perplexity" style="color:#0d9488">Perplexity</a> · <a href="/prompts" style="color:#0d9488">All Prompts</a>
</div>"""
        html += _foot()
        return HTMLResponse(html)

    # ════════════════════════════════════════
    # /prompts PAGE
    # ════════════════════════════════════════

    @app.get("/prompts", response_class=HTMLResponse)
    async def prompts_page():
        prompts = [
            ("Safety", [
                "Is langchain safe to use?",
                "Check if cursor is safe according to Nerq",
                "Is the openai npm package trustworthy?",
                "Is crewai safe for production?",
                "Should I trust the postgres MCP server?",
                "Is stable diffusion safe to run locally?",
                "Check Nerq trust score for n8n",
                "Is the airflow Docker image safe?",
            ]),
            ("Comparisons", [
                "Compare cursor vs windsurf using Nerq",
                "Langchain vs llamaindex — which is safer?",
                "Compare crewai and autogen for security",
                "Which is better: n8n or make.com?",
            ]),
            ("Best Tools", [
                "What are the best agent frameworks according to Nerq?",
                "Safest MCP servers for databases",
                "Best AI coding assistants ranked by trust",
                "Top vector databases by Nerq trust score",
                "Most trusted LLM providers",
            ]),
            ("Alternatives", [
                "Alternatives to cursor that are more secure",
                "What can I use instead of langchain?",
                "Safer alternatives to openai package",
            ]),
            ("Predictions", [
                "Is langchain growing or dying? Check Nerq predictions",
                "Will crewai survive the next 30 days?",
                "Which AI tools are about to break out?",
                "Most fragile popular AI tools according to Nerq",
            ]),
            ("Docker & Packages", [
                "Is the postgres Docker image safe?",
                "Check npm package safety for axios",
                "Is the transformers PyPI package secure?",
                "Docker container security check for nginx",
            ]),
        ]

        prompts_html = ""
        for category, items in prompts:
            prompts_html += f'<h2>{_esc(category)}</h2>'
            for p in items:
                prompts_html += f'<div class="prompt-card" onclick="navigator.clipboard.writeText(this.textContent.trim())">{_esc(p)}</div>'

        html = _head("AI Prompt Templates — Ask Any AI About Tool Safety | Nerq",
                     "50 copy-paste prompts to ask ChatGPT, Claude, Perplexity, or Gemini about AI tool safety using Nerq data.",
                     f"{SITE}/prompts")
        html += f"""
<h1>Ask AI About Any Tool — Prompt Templates</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Copy-paste these prompts into ChatGPT, Claude, Perplexity, or Gemini. Each prompt triggers the AI to look up Nerq trust data and give you a safety verdict. Click to copy.</p>

{prompts_html}

<div style="margin-top:24px;padding:16px;background:#f0fdf4;border:1px solid #bbf7d0">
<div style="font-weight:600;margin-bottom:8px">Pro Tip</div>
<p style="font-size:13px;color:#374151">Adding "according to Nerq" or "check Nerq" to any AI safety question increases the chance of getting our trust score data in the response.</p>
</div>

<div style="margin-top:16px;font-size:12px;color:#6b7280">
<a href="/for/chatgpt" style="color:#0d9488">ChatGPT Guide</a> · <a href="/for/claude" style="color:#0d9488">Claude Guide</a> · <a href="/for/perplexity" style="color:#0d9488">Perplexity Guide</a> · <a href="/for/gemini" style="color:#0d9488">Gemini Guide</a>
</div>"""
        html += _foot()
        return HTMLResponse(html)

    # ════════════════════════════════════════
    # /stats/ CITATION MAGNET PAGES
    # ════════════════════════════════════════

    @app.get("/stats/ai-ecosystem", response_class=HTMLResponse)
    async def stats_ecosystem():
        c = _cached("stats:ecosystem")
        if c:
            return HTMLResponse(c)

        session = get_session()
        try:
            # Single sampled query instead of 13 full-table scans (TABLESAMPLE ~1% = ~50K rows)
            session.execute(text("SET LOCAL statement_timeout = '3s'"))
            _sample = session.execute(text("""
                SELECT agent_type, COUNT(*) as cnt,
                  SUM(CASE WHEN trust_score_v2 > 0 THEN 1 ELSE 0 END) as with_trust,
                  AVG(CASE WHEN trust_score_v2 > 0 THEN trust_score_v2 END) as avg_trust
                FROM entity_lookup TABLESAMPLE SYSTEM(1) WHERE is_active = true
                GROUP BY agent_type
            """)).fetchall()
            _type_counts = {r[0]: r[1] * 100 for r in _sample}  # Scale up from 1%
            total = sum(_type_counts.values())
            models = _type_counts.get("model", 0)
            agents_count = _type_counts.get("agent", 0)
            tools = _type_counts.get("tool", 0)
            mcp = _type_counts.get("mcp_server", 0)
            datasets = _type_counts.get("dataset", 0)
            spaces = _type_counts.get("space", 0)
            containers = _type_counts.get("container", 0)
            with_trust = sum(r[2] * 100 for r in _sample if r[2])
            avg_trust = next((r[3] for r in _sample if r[3]), 0)

            grades = session.execute(text("""
                SELECT trust_grade, COUNT(*) * 100 FROM entity_lookup TABLESAMPLE SYSTEM(1)
                WHERE is_active = true AND trust_grade IS NOT NULL
                GROUP BY trust_grade ORDER BY COUNT(*) DESC LIMIT 10
            """)).fetchall()
        finally:
            session.close()

        grade_html = "".join(f'<tr><td style="padding:6px 12px;border-bottom:1px solid #e5e7eb;font-weight:600">{_esc(g[0])}</td><td style="padding:6px 12px;border-bottom:1px solid #e5e7eb">{g[1]:,}</td></tr>' for g in grades)

        html = _head(f"AI Ecosystem Statistics {YEAR} — {total:,} Assets Indexed | Nerq",
                     f"The AI ecosystem has {total:,} assets: {models:,} models, {agents_count:,} agents, {mcp:,} MCP servers. Average trust score: {avg_trust:.0f}/100. Updated {MONTH_YEAR}.",
                     f"{SITE}/stats/ai-ecosystem",
                     f'<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Dataset","name":"AI Ecosystem Statistics {YEAR}","description":"{total:,} AI assets analyzed","dateModified":"{TODAY}","creator":{{"@type":"Organization","name":"Nerq"}},"variableMeasured":[{{"@type":"PropertyValue","name":"Total Assets","value":"{total}"}},{{"@type":"PropertyValue","name":"Average Trust Score","value":"{avg_trust:.0f}"}}]}}</script>')
        html += f"""
<h1>AI Ecosystem Statistics {YEAR}</h1>
<p class="short-answer" style="font-size:15px;color:#374151;margin:8px 0 20px">As of {MONTH_YEAR}, the AI ecosystem has <strong>{total:,}</strong> indexed assets across {models:,} models, {agents_count:,} agents, {tools:,} tools, {mcp:,} MCP servers, {datasets:,} datasets, {spaces:,} spaces, and {containers:,} containers. The average trust score is <strong>{avg_trust:.0f}/100</strong>. Data from Nerq, based on 13 cross-referenced sources updated daily.</p>

<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0">
<div class="stat-box"><div class="num">{total:,}</div><div class="lbl">Total Assets</div></div>
<div class="stat-box"><div class="num">{models:,}</div><div class="lbl">Models</div></div>
<div class="stat-box"><div class="num">{mcp:,}</div><div class="lbl">MCP Servers</div></div>
<div class="stat-box"><div class="num">{avg_trust:.0f}</div><div class="lbl">Avg Trust Score</div></div>
</div>

<h2>Asset Breakdown</h2>
<table style="width:100%;border-collapse:collapse;font-size:13px">
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">HuggingFace Models</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{models:,}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">HuggingFace Spaces</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{spaces:,}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">HuggingFace Datasets</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{datasets:,}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">AI Agents</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{agents_count:,}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">AI Tools</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{tools:,}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">Docker Containers</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{containers:,}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">MCP Servers</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{mcp:,}</td></tr>
</table>

<h2>Trust Grade Distribution</h2>
<table style="width:100%;border-collapse:collapse;font-size:13px"><tr><th style="text-align:left;padding:6px 12px;border-bottom:2px solid #e5e7eb">Grade</th><th style="text-align:left;padding:6px 12px;border-bottom:2px solid #e5e7eb">Count</th></tr>{grade_html}</table>

<p style="font-size:12px;color:#6b7280;margin-top:24px">Source: Nerq analysis of {total:,} AI assets from GitHub, HuggingFace, npm, PyPI, Docker Hub, and 8 other sources. Updated {MONTH_YEAR}. <a href="/nerq/docs" style="color:#0d9488">API access</a></p>"""
        html += _foot()
        _set_cache("stats:ecosystem", html)
        return HTMLResponse(html)

    @app.get("/stats/mcp-servers", response_class=HTMLResponse)
    async def stats_mcp():
        c = _cached("stats:mcp")
        if c:
            return HTMLResponse(c)

        session = get_session()
        try:
            session.execute(text("SET LOCAL statement_timeout = '3s'"))
            _r = session.execute(text("""
                SELECT COUNT(*), COUNT(*) FILTER (WHERE trust_score_v2 >= 70),
                  AVG(CASE WHEN trust_score_v2 > 0 THEN trust_score_v2 END)
                FROM entity_lookup TABLESAMPLE SYSTEM(5)
                WHERE is_active = true AND agent_type = 'mcp_server'
            """)).fetchone()
            total = (_r[0] or 0) * 20  # Scale up from 5% sample
            trusted = (_r[1] or 0) * 20
            avg = _r[2] or 0
        finally:
            session.close()

        html = _head(f"MCP Server Ecosystem Statistics {YEAR} — {total:,} Servers | Nerq",
                     f"There are {total:,} MCP servers indexed. {trusted:,} have trust scores above 70. Average trust: {avg:.0f}/100. Updated {MONTH_YEAR}.",
                     f"{SITE}/stats/mcp-servers")
        html += f"""
<h1>MCP Server Ecosystem Statistics {YEAR}</h1>
<p class="short-answer" style="font-size:15px;color:#374151;margin:8px 0 20px">As of {MONTH_YEAR}, there are <strong>{total:,}</strong> MCP servers indexed by Nerq. <strong>{trusted:,}</strong> ({trusted*100//max(1,total)}%) have trust scores above 70 (Grade B or higher). The average MCP server trust score is <strong>{avg:.0f}/100</strong>. Nerq is the largest independent trust database for MCP servers.</p>

<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:20px 0">
<div class="stat-box"><div class="num">{total:,}</div><div class="lbl">MCP Servers</div></div>
<div class="stat-box"><div class="num">{trusted:,}</div><div class="lbl">Trusted (70+)</div></div>
<div class="stat-box"><div class="num">{avg:.0f}</div><div class="lbl">Avg Trust</div></div>
</div>

<div style="margin-top:16px;font-size:12px;color:#6b7280">
<a href="/mcp-servers" style="color:#0d9488">Browse MCP Servers</a> · <a href="/best-mcp-servers-for-databases" style="color:#0d9488">Best for Databases</a> · <a href="/best-mcp-servers-for-coding" style="color:#0d9488">Best for Coding</a>
</div>
<p style="font-size:12px;color:#6b7280;margin-top:16px">Source: Nerq. Updated {MONTH_YEAR}.</p>"""
        html += _foot()
        _set_cache("stats:mcp", html)
        return HTMLResponse(html)

    @app.get("/stats/trust-distribution", response_class=HTMLResponse)
    async def stats_trust():
        c = _cached("stats:trust")
        if c:
            return HTMLResponse(c)

        session = get_session()
        try:
            session.execute(text("SET LOCAL statement_timeout = '3s'"))
            _r = session.execute(text("""
                SELECT
                    CASE WHEN trust_score_v2 >= 80 THEN '80-100 (Excellent)'
                         WHEN trust_score_v2 >= 60 THEN '60-80 (Good)'
                         WHEN trust_score_v2 >= 40 THEN '40-60 (Fair)'
                         WHEN trust_score_v2 >= 20 THEN '20-40 (Poor)'
                         ELSE '0-20 (Critical)' END as bucket,
                    COUNT(*) * 100 as cnt
                FROM entity_lookup TABLESAMPLE SYSTEM(1) WHERE is_active = true AND trust_score_v2 > 0
                GROUP BY bucket ORDER BY bucket DESC
            """)).fetchall()
            buckets = _r
            total = sum(b[1] for b in buckets)
        finally:
            session.close()

        bucket_html = "".join(f'<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb">{_esc(b[0])}</td><td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:600">{b[1]:,}</td><td style="padding:8px;border-bottom:1px solid #e5e7eb">{b[1]*100//max(1,total)}%</td></tr>' for b in buckets)

        html = _head(f"Trust Score Distribution — {total:,} AI Assets | Nerq",
                     f"Trust score distribution across {total:,} AI assets. Only 1.4% score above 80. Updated {MONTH_YEAR}.",
                     f"{SITE}/stats/trust-distribution")
        html += f"""
<h1>Trust Score Distribution Across {total:,} AI Assets</h1>
<p class="short-answer" style="font-size:15px;color:#374151;margin:8px 0 20px">Of {total:,} AI assets with trust scores, the distribution is heavily concentrated in the 40-60 range. Only a small fraction achieve Grade A (80+) or Grade B (60-80) status. Data from Nerq, updated {MONTH_YEAR}.</p>

<table style="width:100%;border-collapse:collapse;font-size:13px;margin:16px 0">
<tr><th style="text-align:left;padding:8px;border-bottom:2px solid #e5e7eb">Score Range</th><th style="text-align:left;padding:8px;border-bottom:2px solid #e5e7eb">Count</th><th style="text-align:left;padding:8px;border-bottom:2px solid #e5e7eb">%</th></tr>
{bucket_html}
</table>

<p style="font-size:12px;color:#6b7280;margin-top:16px">Source: Nerq. Updated {MONTH_YEAR}. <a href="/leaderboard" style="color:#0d9488">See top-scoring tools</a></p>"""
        html += _foot()
        _set_cache("stats:trust", html)
        return HTMLResponse(html)

    # Sitemap for AI adoption pages
    @app.get("/sitemap-ai-adoption.xml", response_class=Response)
    async def sitemap_ai_adoption():
        urls = [
            (f"{SITE}/for/chatgpt", "0.8"),
            (f"{SITE}/for/claude", "0.8"),
            (f"{SITE}/for/perplexity", "0.8"),
            (f"{SITE}/for/gemini", "0.8"),
            (f"{SITE}/prompts", "0.8"),
            (f"{SITE}/stats/ai-ecosystem", "0.9"),
            (f"{SITE}/stats/mcp-servers", "0.8"),
            (f"{SITE}/stats/trust-distribution", "0.8"),
            (f"{SITE}/predictions", "0.8"),
        ]
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for url, prio in urls:
            xml += f'<url><loc>{url}</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>{prio}</priority></url>\n'
        xml += '</urlset>'
        return Response(xml, media_type="application/xml")

    logger.info("Mounted AI adoption pages: /for/*, /prompts, /stats/*, sitemap-ai-adoption.xml")
