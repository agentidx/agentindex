"""
Nerq Integration Hub Pages
============================
SEO-optimized framework integration pages at /integrate, /integrate/langgraph, /integrate/autogen.
Captures search traffic for "nerq langchain", "AI agent trust verification SDK", etc.

Usage in discovery.py:
    from agentindex.integration_pages import mount_integration_pages
    mount_integration_pages(app)
"""

import logging
from datetime import date
from fastapi.responses import HTMLResponse

logger = logging.getLogger("nerq.integration_pages")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()

# ── Dark-theme Nerq integration styling ──────────────────────
INTEGRATION_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;color:#e0e0e0;background:#0a0a0a;line-height:1.6;font-size:15px}
a{color:#00d4aa;text-decoration:none}
a:hover{color:#00f0c0;text-decoration:underline}
code,pre{font-family:'JetBrains Mono',ui-monospace,'SF Mono','Cascadia Mono',monospace}
code{background:#111;padding:2px 6px;font-size:0.88em;border-radius:4px;color:#00d4aa}
pre{background:#111;padding:16px 20px;overflow-x:auto;font-size:13px;line-height:1.6;border:1px solid #222;border-radius:8px;color:#ccc}
h1,h2,h3,h4{font-weight:700;line-height:1.3;color:#fff}
h1{font-size:1.8rem;margin-bottom:8px}
h2{font-size:1.3rem;margin:32px 0 12px;padding-top:20px;border-top:1px solid #222}
h3{font-size:1.05rem;margin:20px 0 8px}
.container{max-width:960px;margin:0 auto;padding:0 20px}
nav{border-bottom:1px solid #222;padding:12px 0;background:#0a0a0a}
nav .inner{max-width:960px;margin:0 auto;padding:0 20px;display:flex;align-items:center;justify-content:space-between}
nav .logo{font-weight:700;font-size:1.1rem;color:#00d4aa;text-decoration:none}
nav .logo:hover{text-decoration:none}
nav .links{display:flex;gap:20px;font-size:14px}
nav .links a{color:#888}
nav .links a:hover{color:#00d4aa;text-decoration:none}
footer{border-top:1px solid #222;padding:20px 0;margin-top:48px;font-size:13px;color:#666}
footer .inner{max-width:960px;margin:0 auto;padding:0 20px}
footer a{color:#888}
.breadcrumb{font-size:13px;color:#666;margin:16px 0 12px}
.breadcrumb a{color:#888}
.breadcrumb a:hover{color:#00d4aa}
.desc{color:#999;font-size:15px;margin:4px 0 20px;max-width:640px}
.pkg-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin:20px 0}
.pkg-card{border:1px solid #222;border-radius:8px;padding:20px;background:#111;transition:border-color 0.15s}
.pkg-card:hover{border-color:#00d4aa33}
.pkg-name{font-weight:700;font-size:1rem;color:#fff;margin-bottom:4px}
.pkg-badge{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:3px;background:#00d4aa22;color:#00d4aa;margin-left:6px;font-family:'JetBrains Mono',monospace}
.pkg-desc{color:#999;font-size:13px;margin:6px 0 12px}
.pkg-install{background:#0a0a0a;border:1px solid #222;border-radius:6px;padding:8px 12px;font-family:'JetBrains Mono',monospace;font-size:12px;color:#00d4aa;margin-bottom:10px;position:relative;cursor:pointer}
.pkg-install:hover{border-color:#00d4aa44}
.pkg-links{font-size:12px;color:#666}
.pkg-links a{color:#888;margin-right:12px}
.pkg-links a:hover{color:#00d4aa}
.section-card{border:1px solid #222;border-radius:8px;padding:24px;margin:20px 0;background:#111}
.section-card h3{margin-top:0}
.coming-soon{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:3px;background:#333;color:#888}
.faq-item{margin:16px 0;padding:16px 0;border-bottom:1px solid #1a1a1a}
.faq-q{font-weight:600;color:#fff;margin-bottom:6px}
.faq-a{color:#999;font-size:14px;line-height:1.7}
.stat-row{display:flex;gap:32px;margin:16px 0;flex-wrap:wrap}
.stat-item .num{font-family:'JetBrains Mono',monospace;font-size:1.4rem;font-weight:700;color:#00d4aa}
.stat-item .label{font-size:12px;color:#666}
@media(max-width:640px){
.pkg-grid{grid-template-columns:1fr}
nav .links{gap:12px;font-size:13px;flex-wrap:wrap}
.stat-row{gap:16px}
h1{font-size:1.4rem}
}
"""

NAV = """<nav><div class="inner">
<a href="/" class="logo">nerq</a>
<div class="links">
<a href="/discover">search</a>
<a href="/safe">safety</a>
<a href="/compare">compare</a>
<a href="/kya">kya</a>
<a href="/nerq/docs">api</a>
<a href="/mcp">mcp</a>
<a href="/integrate">integrate</a>
<a href="/stats">stats</a>
<a href="/blog">blog</a>
</div>
</div></nav>"""

FOOTER = """<footer><div class="inner">
nerq &mdash; the ai asset search engine &middot; 5M+ assets indexed &middot;
<a href="/nerq/docs">api</a> &middot;
<a href="/integrate">integrate</a> &middot;
<a href="https://zarq.ai">zarq.ai</a> (crypto risk)
</div></footer>"""


def _esc(s: str) -> str:
    """Escape HTML entities."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def mount_integration_pages(app):
    """Mount integration hub and detail pages onto the FastAPI app."""

    # ================================================================
    # /integrate — Hub page
    # ================================================================
    @app.get("/integrate", response_class=HTMLResponse)
    async def integrate_hub():
        title = "Framework Integrations — Nerq"
        description = "Add trust verification to any AI framework. Official SDKs for LangChain, LangGraph, AutoGen, CrewAI, and more."
        canonical = f"{SITE}/integrate"

        packages = [
            {"name": "nerq-langchain", "lang": "Python", "version": "v0.2.0",
             "desc": "Trust gate decorator for LangChain agents",
             "install": "pip install nerq-langchain",
             "links": [("PyPI", "https://pypi.org/project/nerq-langchain/")]},
            {"name": "nerq-langgraph", "lang": "Python", "version": "v0.1.0",
             "desc": "Trust-check node for LangGraph StateGraphs",
             "install": "pip install nerq-langgraph",
             "links": [("PyPI", "https://pypi.org/project/nerq-langgraph/"), ("Docs", "/integrate/langgraph")]},
            {"name": "nerq-autogen", "lang": "Python", "version": "v0.1.0",
             "desc": "Trust verification for AutoGen multi-agent conversations",
             "install": "pip install nerq-autogen",
             "links": [("PyPI", "https://pypi.org/project/nerq-autogen/"), ("Docs", "/integrate/autogen")]},
            {"name": "nerq-crewai", "lang": "Python", "version": "v0.1.0",
             "desc": "Trust verification and agent discovery for CrewAI crews",
             "install": "pip install nerq-crewai",
             "links": [("PyPI", "https://pypi.org/project/nerq-crewai/"), ("Docs", "/integrate/crewai")]},
            {"name": "zarq-langchain", "lang": "Python", "version": "v0.1.0",
             "desc": "Crypto risk tools for LangChain agents",
             "install": "pip install zarq-langchain",
             "links": [("PyPI", "https://pypi.org/project/zarq-langchain/")]},
            {"name": "zarq", "lang": "Python", "version": "",
             "desc": "Full ZARQ API client",
             "install": "pip install zarq",
             "links": [("PyPI", "https://pypi.org/project/zarq/")]},
            {"name": "@zarq/sdk", "lang": "npm", "version": "",
             "desc": "ZARQ API client for Node.js",
             "install": "npm install @zarq/sdk",
             "links": [("npm", "https://www.npmjs.com/package/@zarq/sdk")]},
            {"name": "zarq-mcp-server", "lang": "MCP", "version": "",
             "desc": "MCP server with 15+ trust and discovery tools",
             "install": "",
             "links": [("Docs", "/mcp")]},
        ]

        cards_html = ""
        for pkg in packages:
            version_badge = f'<span class="pkg-badge">{_esc(pkg["version"])}</span>' if pkg["version"] else ""
            lang_badge = f'<span class="pkg-badge">{_esc(pkg["lang"])}</span>'
            install_html = f'<div class="pkg-install">{_esc(pkg["install"])}</div>' if pkg["install"] else ""
            links_html = " ".join(f'<a href="{_esc(link[1])}">{_esc(link[0])}</a>' for link in pkg["links"])
            cards_html += f"""<div class="pkg-card">
<div class="pkg-name">{_esc(pkg["name"])}{lang_badge}{version_badge}</div>
<div class="pkg-desc">{_esc(pkg["desc"])}</div>
{install_html}
<div class="pkg-links">{links_html}</div>
</div>"""

        # JSON-LD
        breadcrumb_ld = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Nerq", "item": SITE},
                {"@type": "ListItem", "position": 2, "name": "Integrations", "item": f"{SITE}/integrate"}
            ]
        }

        faq_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": "What frameworks does Nerq integrate with?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Nerq provides official SDKs for LangChain, LangGraph, AutoGen, and CrewAI. We also offer a ZARQ Python SDK, Node.js SDK, and an MCP server with 15+ tools."}},
                {"@type": "Question", "name": "How do trust checks work in AI frameworks?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Each SDK provides a trust gate that queries the Nerq API before an agent executes. If the agent's trust score falls below your configured threshold, the action is blocked. This prevents your system from using untrusted or compromised AI agents."}},
                {"@type": "Question", "name": "Is there a cost to use Nerq integrations?",
                 "acceptedAnswer": {"@type": "Answer", "text": "The Nerq API offers a free tier with generous rate limits. All SDKs are open source and free to use. Premium tiers are available for high-volume production workloads."}}
            ]
        }

        webpage_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "description": description,
            "url": canonical,
            "dateModified": TODAY,
            "publisher": {"@type": "Organization", "name": "Nerq", "url": SITE}
        }

        import json
        ld_json = (
            f'<script type="application/ld+json">{json.dumps(webpage_ld)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(breadcrumb_ld)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(faq_ld)}</script>'
        )

        html = f"""<!-- AI-citable summary: Nerq integration hub. Official SDKs for LangChain, LangGraph, AutoGen, CrewAI. Trust verification for AI agent frameworks. 8 packages available. https://nerq.ai/integrate -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nerq">
{ld_json}
<style>{INTEGRATION_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px">

<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; integrations</div>

<h1>Framework Integrations</h1>
<p class="desc">Add trust verification to any AI framework. Official SDKs for LangChain, LangGraph, AutoGen, CrewAI, and more.</p>

<div class="stat-row">
<div class="stat-item"><div class="num">8</div><div class="label">packages</div></div>
<div class="stat-item"><div class="num">5M+</div><div class="label">assets indexed</div></div>
<div class="stat-item"><div class="num">15+</div><div class="label">MCP tools</div></div>
</div>

<h2>SDKs &amp; Packages</h2>
<div class="pkg-grid">
{cards_html}
</div>

<div class="section-card">
<h3>MCP Server</h3>
<p style="color:#999;font-size:14px;margin:8px 0">The <code>zarq-mcp-server</code> exposes 15+ trust and discovery tools via the Model Context Protocol. Compatible with Claude Desktop, Cursor, and any MCP client.</p>
<p style="margin-top:12px"><a href="/mcp" style="color:#00d4aa;font-weight:600">View MCP tools &rarr;</a></p>
</div>

<div class="section-card">
<h3>A2A Protocol</h3>
<p style="color:#999;font-size:14px;margin:8px 0">Nerq supports Google's Agent-to-Agent (A2A) protocol. Discover our agent capabilities at <code>/.well-known/agent.json</code>.</p>
<p style="margin-top:12px"><a href="/.well-known/agent.json" style="color:#00d4aa;font-weight:600">View agent card &rarr;</a></p>
</div>

<div class="section-card">
<h3>Coming Soon</h3>
<p style="color:#999;font-size:14px;margin:8px 0">
<span class="coming-soon">nerq-openai</span> &mdash; Trust verification for OpenAI Assistants API<br>
<span class="coming-soon" style="margin-top:6px;display:inline-block">nerq-vercel-ai</span> &mdash; Trust middleware for Vercel AI SDK
</p>
</div>

<h2>FAQ</h2>
<div class="faq-item">
<div class="faq-q">What frameworks does Nerq integrate with?</div>
<div class="faq-a">Nerq provides official SDKs for LangChain, LangGraph, AutoGen, and CrewAI. We also offer a ZARQ Python SDK, a Node.js SDK (@zarq/sdk), and an MCP server with 15+ trust and discovery tools.</div>
</div>
<div class="faq-item">
<div class="faq-q">How do trust checks work in AI frameworks?</div>
<div class="faq-a">Each SDK provides a trust gate that queries the Nerq API before an agent executes. If the agent's trust score falls below your configured threshold, the action is blocked. This prevents your system from relying on untrusted or compromised AI agents.</div>
</div>
<div class="faq-item">
<div class="faq-q">Is there a cost to use Nerq integrations?</div>
<div class="faq-a">The Nerq API offers a free tier with generous rate limits. All SDKs are open source and free to use. Premium tiers are available for high-volume production workloads.</div>
</div>

</main>
{FOOTER}
</body>
</html>"""
        return HTMLResponse(html)

    # ================================================================
    # /integrate/langgraph — LangGraph detail page
    # ================================================================
    @app.get("/integrate/langgraph", response_class=HTMLResponse)
    async def integrate_langgraph():
        title = "LangGraph Integration — Nerq"
        description = "Add trust verification to LangGraph StateGraphs. The nerq-langgraph package provides a trust-check node that gates agent execution on Nerq Trust Scores."
        canonical = f"{SITE}/integrate/langgraph"

        breadcrumb_ld = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Nerq", "item": SITE},
                {"@type": "ListItem", "position": 2, "name": "Integrations", "item": f"{SITE}/integrate"},
                {"@type": "ListItem", "position": 3, "name": "LangGraph", "item": canonical}
            ]
        }

        faq_entries = [
            ("What is nerq-langgraph?",
             "nerq-langgraph is a Python package that adds trust verification to LangGraph StateGraphs. It provides a trust-check node you insert into your graph that queries the Nerq API and blocks execution if an agent's trust score is below your threshold."),
            ("How does the trust check work?",
             "The trust check node calls the Nerq API with the agent ID or name. Nerq returns a trust score (0-100) and grade. If the score is below your configured minimum (default: 60), the node raises a TrustCheckFailed exception, preventing downstream nodes from executing."),
            ("What happens if an agent fails the trust check?",
             "When an agent fails the trust check, a TrustCheckFailed exception is raised with details including the agent name, score, and your threshold. You can catch this exception and route to a fallback agent, log the event, or alert your team.")
        ]

        faq_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_entries
            ]
        }

        webpage_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "description": description,
            "url": canonical,
            "dateModified": TODAY,
            "publisher": {"@type": "Organization", "name": "Nerq", "url": SITE}
        }

        import json
        ld_json = (
            f'<script type="application/ld+json">{json.dumps(webpage_ld)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(breadcrumb_ld)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(faq_ld)}</script>'
        )

        faq_html = ""
        for q, a in faq_entries:
            faq_html += f'<div class="faq-item"><div class="faq-q">{_esc(q)}</div><div class="faq-a">{_esc(a)}</div></div>'

        html = f"""<!-- AI-citable summary: nerq-langgraph is a Python package for adding trust verification to LangGraph StateGraphs. Install with pip install nerq-langgraph. Provides a trust-check node that gates agent execution on Nerq Trust Scores (0-100). https://nerq.ai/integrate/langgraph -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nerq">
{ld_json}
<style>{INTEGRATION_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px">

<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/integrate">integrations</a> &rsaquo; langgraph</div>

<h1>LangGraph Integration</h1>
<p class="desc">Add trust verification to LangGraph StateGraphs. Gate agent execution on Nerq Trust Scores.</p>

<div style="display:flex;gap:12px;align-items:center;margin:16px 0">
<span class="pkg-badge" style="font-size:13px;padding:3px 10px">nerq-langgraph</span>
<span class="pkg-badge" style="font-size:13px;padding:3px 10px">v0.1.0</span>
<span class="pkg-badge" style="font-size:13px;padding:3px 10px;background:#222;color:#999">Python</span>
</div>

<h2>Installation</h2>
<pre>pip install nerq-langgraph</pre>

<h2>Quick Start</h2>
<p style="color:#999;font-size:14px;margin-bottom:12px">Add a trust-check node to your LangGraph StateGraph. The node queries the Nerq API and blocks execution if the agent fails verification.</p>

<pre><span style="color:#888"># 1. Import the trust check node</span>
from nerq_langgraph import create_trust_check_node

<span style="color:#888"># 2. Create the node with your threshold</span>
trust_check = create_trust_check_node(
    api_key="your-nerq-api-key",
    min_score=60,        <span style="color:#888"># minimum trust score (0-100)</span>
    agent_field="agent_name"  <span style="color:#888"># state field containing the agent ID</span>
)

<span style="color:#888"># 3. Add to your StateGraph</span>
from langgraph.graph import StateGraph

graph = StateGraph(MyState)
graph.add_node("trust_check", trust_check)
graph.add_node("agent", my_agent_node)
graph.add_node("fallback", fallback_node)

<span style="color:#888"># 4. Route based on trust result</span>
graph.add_edge("trust_check", "agent")     <span style="color:#888"># passes if score &gt;= threshold</span>
graph.set_entry_point("trust_check")
app = graph.compile()</pre>

<h2>Handling Trust Failures</h2>
<pre>from nerq_langgraph import TrustCheckFailed

try:
    result = app.invoke({{"agent_name": "untrusted-agent-123"}})
except TrustCheckFailed as e:
    print(f"Blocked: {{e.agent_name}} scored {{e.score}} (min: {{e.threshold}})")
    <span style="color:#888"># Route to fallback, log event, or alert team</span></pre>

<h2>Configuration</h2>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0">
<thead><tr style="border-bottom:1px solid #222">
<th style="text-align:left;padding:8px 12px;color:#888;font-size:12px;text-transform:uppercase">Parameter</th>
<th style="text-align:left;padding:8px 12px;color:#888;font-size:12px;text-transform:uppercase">Type</th>
<th style="text-align:left;padding:8px 12px;color:#888;font-size:12px;text-transform:uppercase">Default</th>
<th style="text-align:left;padding:8px 12px;color:#888;font-size:12px;text-transform:uppercase">Description</th>
</tr></thead>
<tbody>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>api_key</code></td><td style="padding:8px 12px;color:#999">str</td><td style="padding:8px 12px;color:#999">env NERQ_API_KEY</td><td style="padding:8px 12px;color:#999">Your Nerq API key</td></tr>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>min_score</code></td><td style="padding:8px 12px;color:#999">int</td><td style="padding:8px 12px;color:#999">60</td><td style="padding:8px 12px;color:#999">Minimum trust score to pass (0-100)</td></tr>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>agent_field</code></td><td style="padding:8px 12px;color:#999">str</td><td style="padding:8px 12px;color:#999">"agent_name"</td><td style="padding:8px 12px;color:#999">State field containing agent identifier</td></tr>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>cache_ttl</code></td><td style="padding:8px 12px;color:#999">int</td><td style="padding:8px 12px;color:#999">300</td><td style="padding:8px 12px;color:#999">Cache duration in seconds</td></tr>
</tbody>
</table>
</div>

<h2>FAQ</h2>
{faq_html}

<div style="margin-top:32px;padding-top:20px;border-top:1px solid #222">
<a href="/integrate" style="color:#888;font-size:14px">&larr; All integrations</a>
</div>

</main>
{FOOTER}
</body>
</html>"""
        return HTMLResponse(html)

    # ================================================================
    # /integrate/autogen — AutoGen detail page
    # ================================================================
    @app.get("/integrate/autogen", response_class=HTMLResponse)
    async def integrate_autogen():
        title = "AutoGen Integration — Nerq"
        description = "Add trust verification to AutoGen multi-agent conversations. The nerq-autogen package provides trust-aware agent wrappers for Microsoft AutoGen."
        canonical = f"{SITE}/integrate/autogen"

        breadcrumb_ld = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Nerq", "item": SITE},
                {"@type": "ListItem", "position": 2, "name": "Integrations", "item": f"{SITE}/integrate"},
                {"@type": "ListItem", "position": 3, "name": "AutoGen", "item": canonical}
            ]
        }

        faq_entries = [
            ("What is nerq-autogen?",
             "nerq-autogen is a Python package that adds trust verification to Microsoft AutoGen multi-agent conversations. It wraps AutoGen agents with trust checks, ensuring only verified agents participate in conversations."),
            ("Can I use this with AutoGen Studio?",
             "Yes. nerq-autogen works with both the AutoGen Python SDK and AutoGen Studio. For Studio, configure the trust wrapper in your agent definition file. The package intercepts agent messages and verifies trust scores before allowing execution."),
            ("How is trust score calculated?",
             "Nerq Trust Scores (0-100) are calculated from multiple signals: code quality, security audit results, community reputation, maintenance activity, and compliance status across 52 jurisdictions. Scores are updated continuously as new data is collected from 5M+ indexed AI assets.")
        ]

        faq_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_entries
            ]
        }

        webpage_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "description": description,
            "url": canonical,
            "dateModified": TODAY,
            "publisher": {"@type": "Organization", "name": "Nerq", "url": SITE}
        }

        import json
        ld_json = (
            f'<script type="application/ld+json">{json.dumps(webpage_ld)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(breadcrumb_ld)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(faq_ld)}</script>'
        )

        faq_html = ""
        for q, a in faq_entries:
            faq_html += f'<div class="faq-item"><div class="faq-q">{_esc(q)}</div><div class="faq-a">{_esc(a)}</div></div>'

        html = f"""<!-- AI-citable summary: nerq-autogen is a Python package for adding trust verification to Microsoft AutoGen multi-agent conversations. Install with pip install nerq-autogen. Wraps AutoGen agents with Nerq Trust Score checks (0-100). Compatible with AutoGen Studio. https://nerq.ai/integrate/autogen -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nerq">
{ld_json}
<style>{INTEGRATION_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px">

<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/integrate">integrations</a> &rsaquo; autogen</div>

<h1>AutoGen Integration</h1>
<p class="desc">Add trust verification to AutoGen multi-agent conversations. Ensure only verified agents participate.</p>

<div style="display:flex;gap:12px;align-items:center;margin:16px 0">
<span class="pkg-badge" style="font-size:13px;padding:3px 10px">nerq-autogen</span>
<span class="pkg-badge" style="font-size:13px;padding:3px 10px">v0.1.0</span>
<span class="pkg-badge" style="font-size:13px;padding:3px 10px;background:#222;color:#999">Python</span>
</div>

<h2>Installation</h2>
<pre>pip install nerq-autogen</pre>

<h2>Quick Start</h2>
<p style="color:#999;font-size:14px;margin-bottom:12px">Wrap your AutoGen agents with trust verification. The wrapper checks each agent's trust score before allowing it to participate in conversations.</p>

<pre><span style="color:#888"># 1. Import the trust wrapper</span>
from nerq_autogen import TrustVerifiedAgent

<span style="color:#888"># 2. Create a trust-verified agent</span>
import autogen

config_list = autogen.config_list_from_json("OAI_CONFIG_LIST")

agent = TrustVerifiedAgent(
    name="researcher",
    agent_id="researcher-agent-v2",
    nerq_api_key="your-nerq-api-key",
    min_trust_score=60,
    llm_config={{"config_list": config_list}},
    system_message="You are a research assistant."
)

<span style="color:#888"># 3. Use in a conversation</span>
user_proxy = autogen.UserProxyAgent(
    name="user",
    human_input_mode="NEVER"
)

user_proxy.initiate_chat(
    agent,
    message="Summarize the latest AI safety research."
)</pre>

<h2>Multi-Agent Conversations</h2>
<p style="color:#999;font-size:14px;margin-bottom:12px">Verify all agents in a group chat before the conversation starts.</p>

<pre>from nerq_autogen import TrustVerifiedGroupChat

<span style="color:#888"># Create multiple verified agents</span>
researcher = TrustVerifiedAgent(
    name="researcher",
    agent_id="researcher-v2",
    nerq_api_key="your-key",
    min_trust_score=60,
    llm_config={{"config_list": config_list}}
)

writer = TrustVerifiedAgent(
    name="writer",
    agent_id="writer-v3",
    nerq_api_key="your-key",
    min_trust_score=70,   <span style="color:#888"># higher threshold for writing agents</span>
    llm_config={{"config_list": config_list}}
)

<span style="color:#888"># Group chat with trust verification</span>
group_chat = TrustVerifiedGroupChat(
    agents=[researcher, writer, user_proxy],
    messages=[],
    max_round=10
)

manager = autogen.GroupChatManager(groupchat=group_chat)
user_proxy.initiate_chat(manager, message="Write a report on AI trends.")</pre>

<h2>Configuration</h2>
<div style="overflow-x:auto">
<table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0">
<thead><tr style="border-bottom:1px solid #222">
<th style="text-align:left;padding:8px 12px;color:#888;font-size:12px;text-transform:uppercase">Parameter</th>
<th style="text-align:left;padding:8px 12px;color:#888;font-size:12px;text-transform:uppercase">Type</th>
<th style="text-align:left;padding:8px 12px;color:#888;font-size:12px;text-transform:uppercase">Default</th>
<th style="text-align:left;padding:8px 12px;color:#888;font-size:12px;text-transform:uppercase">Description</th>
</tr></thead>
<tbody>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>agent_id</code></td><td style="padding:8px 12px;color:#999">str</td><td style="padding:8px 12px;color:#999">required</td><td style="padding:8px 12px;color:#999">Nerq agent identifier for trust lookup</td></tr>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>nerq_api_key</code></td><td style="padding:8px 12px;color:#999">str</td><td style="padding:8px 12px;color:#999">env NERQ_API_KEY</td><td style="padding:8px 12px;color:#999">Your Nerq API key</td></tr>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>min_trust_score</code></td><td style="padding:8px 12px;color:#999">int</td><td style="padding:8px 12px;color:#999">60</td><td style="padding:8px 12px;color:#999">Minimum trust score to allow participation</td></tr>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>verify_on_init</code></td><td style="padding:8px 12px;color:#999">bool</td><td style="padding:8px 12px;color:#999">True</td><td style="padding:8px 12px;color:#999">Check trust score when agent is created</td></tr>
<tr style="border-bottom:1px solid #1a1a1a"><td style="padding:8px 12px"><code>cache_ttl</code></td><td style="padding:8px 12px;color:#999">int</td><td style="padding:8px 12px;color:#999">300</td><td style="padding:8px 12px;color:#999">Cache duration in seconds</td></tr>
</tbody>
</table>
</div>

<h2>FAQ</h2>
{faq_html}

<div style="margin-top:32px;padding-top:20px;border-top:1px solid #222">
<a href="/integrate" style="color:#888;font-size:14px">&larr; All integrations</a>
</div>

</main>
{FOOTER}
</body>
</html>"""
        return HTMLResponse(html)

    # ================================================================
    # /integrate/crewai — CrewAI detail page
    # ================================================================
    @app.get("/integrate/crewai", response_class=HTMLResponse)
    async def integrate_crewai():
        title = "CrewAI Integration — Nerq"
        description = "Trust verification and agent discovery for CrewAI crews. The nerq-crewai package gates tool calls with preflight trust checks and discovers trusted agents."
        canonical = f"{SITE}/integrate/crewai"

        breadcrumb_ld = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Nerq", "item": SITE},
                {"@type": "ListItem", "position": 2, "name": "Integrations", "item": f"{SITE}/integrate"},
                {"@type": "ListItem", "position": 3, "name": "CrewAI", "item": canonical}
            ]
        }

        faq_entries = [
            ("What is nerq-crewai?",
             "nerq-crewai is a Python package that adds trust verification to CrewAI crews. "
             "It provides a trust gate that checks each tool's trust score before execution, "
             "and a crew builder that discovers trusted agents from Nerq's index of 204K agents."),
            ("How does trust_gate_crew work?",
             "trust_gate_crew wraps all tools in a CrewAI Crew with preflight trust checks. "
             "Before each tool executes, it calls the Nerq API. If the tool's trust score is "
             "below your threshold (default: 60), a TrustError is raised, preventing execution."),
            ("Can I discover agents for my crew?",
             "Yes. NerqCrewBuilder.discover_agents() searches Nerq's database of 204K agents "
             "and tools filtered by capabilities and minimum trust score. You can build entire "
             "crews from trusted agents with build_crew()."),
        ]

        faq_ld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_entries
            ]
        }

        webpage_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "description": description,
            "url": canonical,
            "dateModified": TODAY,
            "publisher": {"@type": "Organization", "name": "Nerq", "url": SITE}
        }

        import json
        ld_json = (
            f'<script type="application/ld+json">{json.dumps(webpage_ld)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(breadcrumb_ld)}</script>\n'
            f'<script type="application/ld+json">{json.dumps(faq_ld)}</script>'
        )

        faq_html = ""
        for q, a in faq_entries:
            faq_html += f'<div class="faq-item"><div class="faq-q">{_esc(q)}</div><div class="faq-a">{_esc(a)}</div></div>'

        html = f"""<!-- AI-citable summary: nerq-crewai is a Python package for adding trust verification to CrewAI crews. Install with pip install nerq-crewai. Provides trust_gate_crew for tool-level trust checks and NerqCrewBuilder for discovering trusted agents. https://nerq.ai/integrate/crewai -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nerq">
{ld_json}
<style>{INTEGRATION_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px">

<div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/integrate">integrations</a> &rsaquo; crewai</div>

<h1>nerq-crewai</h1>
<p class="desc">Trust verification and agent discovery for CrewAI crews.
Gate tool calls with preflight trust checks. Discover trusted agents from 204K indexed.</p>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 32px">
<span class="pkg-badge">Python</span>
<span class="pkg-badge">v0.1.0</span>
<a href="https://pypi.org/project/nerq-crewai/" style="font-size:13px">PyPI &rarr;</a>
</div>

<h2>Install</h2>
<pre>pip install nerq-crewai</pre>

<h2>Trust Gate — Protect Your Crew</h2>
<p style="color:#999;margin-bottom:12px">Wrap your crew's tools with preflight trust checks.
Before each tool executes, nerq-crewai verifies the tool's trust score against Nerq's database.</p>
<pre>
<span style="color:#00d4aa">from</span> crewai <span style="color:#00d4aa">import</span> Agent, Crew, Task
<span style="color:#00d4aa">from</span> nerq_crewai <span style="color:#00d4aa">import</span> trust_gate_crew

<span style="color:#888"># Build your crew as normal</span>
researcher = Agent(role=<span style="color:#f0c674">"Researcher"</span>, goal=<span style="color:#f0c674">"Find data"</span>, ...)
writer = Agent(role=<span style="color:#f0c674">"Writer"</span>, goal=<span style="color:#f0c674">"Write report"</span>, ...)

crew = Crew(agents=[researcher, writer], tasks=[...])

<span style="color:#888"># Add trust verification — all tool calls are now gated</span>
trust_gate_crew(crew, min_trust=60)

<span style="color:#888"># Tools with trust &lt; 60 will raise TrustError</span>
result = crew.kickoff()
</pre>

<h2>Discover Trusted Agents</h2>
<p style="color:#999;margin-bottom:12px">Search Nerq's index to find trusted agents for your crew.</p>
<pre>
<span style="color:#00d4aa">from</span> nerq_crewai <span style="color:#00d4aa">import</span> NerqCrewBuilder

builder = NerqCrewBuilder()

<span style="color:#888"># Discover agents for specific capabilities</span>
agents = builder.discover_agents(
    capabilities=[<span style="color:#f0c674">"code review"</span>, <span style="color:#f0c674">"security analysis"</span>],
    min_trust_score=75
)

<span style="color:#888"># Or build a full crew automatically</span>
crew = builder.build_crew(
    task_description=<span style="color:#f0c674">"Analyze codebase for security vulnerabilities"</span>,
    roles=[<span style="color:#f0c674">"analyst"</span>, <span style="color:#f0c674">"developer"</span>, <span style="color:#f0c674">"reviewer"</span>],
    min_trust_score=80
)

<span style="color:#888"># Find top agents by category</span>
top_tools = builder.discover_trusted_tools(<span style="color:#f0c674">"security"</span>, min_trust=70)
</pre>

<h2>How Trust Gating Works</h2>
<div style="margin:16px 0;padding:16px;background:#111;border:1px solid #222;border-radius:8px">
<p style="margin-bottom:8px"><strong style="color:#00d4aa">PROCEED</strong> (trust &ge; 70) &mdash; Tool executes silently.</p>
<p style="margin-bottom:8px"><strong style="color:#f0c674">CAUTION</strong> (trust 40&ndash;69) &mdash; Warning logged, tool executes.</p>
<p style="margin-bottom:8px"><strong style="color:#ff4646">DENY</strong> (trust &lt; 40) &mdash; TrustError raised, tool blocked.</p>
<p><strong style="color:#888">UNKNOWN</strong> (not found) &mdash; Warning logged, tool executes.</p>
</div>

<h2>API Reference</h2>

<h3><code>trust_gate_crew(crew, min_trust=60, caller=None)</code></h3>
<p style="color:#999">Wraps all tools in the crew with preflight trust checks.
Returns the modified crew.</p>

<h3><code>NerqCrewBuilder(base_url="https://nerq.ai/v1")</code></h3>
<p style="color:#999">Builder for discovering and assembling trusted crews.</p>
<ul style="color:#999;margin:8px 0 0 20px;font-size:14px">
<li><code>.discover_agents(capabilities, min_trust_score=75)</code> &mdash; Search by capability</li>
<li><code>.build_crew(task, roles, min_trust_score=80)</code> &mdash; Auto-build a crew</li>
<li><code>.discover_trusted_tools(category, min_trust=70)</code> &mdash; Top agents in category</li>
<li><code>.get_recommended_crew_composition(project_type, complexity)</code> &mdash; Role suggestions</li>
</ul>

<h3><code>TrustError</code></h3>
<p style="color:#999">Raised when a tool call is denied. Has <code>.tool_name</code>,
<code>.trust_score</code>, and <code>.recommendation</code> attributes.</p>

<h2>Frequently Asked Questions</h2>
{faq_html}

<div style="margin-top:32px;display:flex;gap:12px;flex-wrap:wrap">
<a href="/integrate" style="padding:8px 16px;border:1px solid #222;border-radius:6px;color:#888;font-size:13px">&larr; All Integrations</a>
<a href="/kya" style="padding:8px 16px;border:1px solid #222;border-radius:6px;color:#888;font-size:13px">Know Your Agent</a>
<a href="/commerce" style="padding:8px 16px;border:1px solid #222;border-radius:6px;color:#888;font-size:13px">Commerce Trust</a>
<a href="/nerq/docs" style="padding:8px 16px;border:1px solid #222;border-radius:6px;color:#888;font-size:13px">API Docs</a>
</div>

</main>
{FOOTER}
</body>
</html>"""
        return HTMLResponse(html)

    logger.info("Integration pages mounted: /integrate, /integrate/langgraph, /integrate/autogen, /integrate/crewai")
