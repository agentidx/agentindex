"""
Nerq Agent Trust Protocol Page + Blog Post
============================================
/protocol — Readable web spec for the Nerq Agent Trust Protocol v1.0
/blog/trust-handshake — Blog post on agent-to-agent trust verification

Usage in discovery.py:
    from agentindex.protocol_page import mount_protocol_pages
    mount_protocol_pages(app)
"""

import logging
from datetime import date
from fastapi.responses import HTMLResponse

logger = logging.getLogger("nerq.protocol_page")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()

# ── Dark-theme protocol styling (matches integration_pages) ──
PROTOCOL_CSS = """
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
.stat-row{display:flex;gap:32px;margin:16px 0;flex-wrap:wrap}
.stat-item .num{font-family:'JetBrains Mono',monospace;font-size:1.4rem;font-weight:700;color:#00d4aa}
.stat-item .label{font-size:12px;color:#666}
.section-card{border:1px solid #222;border-radius:8px;padding:24px;margin:20px 0;background:#111}
.section-card h3{margin-top:0}
.faq-item{margin:16px 0;padding:16px 0;border-bottom:1px solid #1a1a1a}
.faq-q{font-weight:600;color:#fff;margin-bottom:6px}
.faq-a{color:#999;font-size:14px;line-height:1.7}
table{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}
th{text-align:left;padding:8px 12px;border-bottom:2px solid #222;color:#888;font-weight:600;font-size:13px}
td{padding:8px 12px;border-bottom:1px solid #1a1a1a}
tr:nth-child(even){background:#0f0f0f}
.hero-badge{display:inline-block;font-size:11px;font-weight:600;padding:2px 10px;border-radius:3px;background:#00d4aa22;color:#00d4aa;margin-bottom:12px;font-family:'JetBrains Mono',monospace;letter-spacing:0.05em}
.cta-link{display:inline-block;margin:8px 12px 8px 0;padding:8px 20px;border:1px solid #222;border-radius:6px;font-size:14px;color:#00d4aa;transition:border-color 0.15s}
.cta-link:hover{border-color:#00d4aa;text-decoration:none}
@media(max-width:640px){
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
<a href="/protocol">protocol</a>
<a href="/stats">stats</a>
<a href="/blog">blog</a>
</div>
</div></nav>"""

FOOTER = """<footer><div class="inner">
nerq &mdash; the ai asset search engine &middot; 5M+ assets indexed &middot;
<a href="/nerq/docs">api</a> &middot;
<a href="/integrate">integrate</a> &middot;
<a href="/protocol">protocol</a> &middot;
<a href="https://zarq.ai">zarq.ai</a> (crypto risk)
</div></footer>"""


def _protocol_page() -> str:
    """Build the /protocol spec page."""

    title = "Nerq Agent Trust Protocol v1.0 — Agent-to-Agent Trust Verification"
    description = "A lightweight HTTP protocol for AI agents to verify the trustworthiness of other agents before interaction."
    canonical = f"{SITE}/protocol"

    json_ld_webpage = f"""{{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "name": "Nerq Agent Trust Protocol v1.0",
  "description": "{description}",
  "url": "{canonical}",
  "datePublished": "2026-03-12",
  "dateModified": "{TODAY}",
  "publisher": {{"@type": "Organization", "name": "Nerq", "url": "{SITE}"}}
}}"""

    json_ld_breadcrumb = f"""{{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {{"@type": "ListItem", "position": 1, "name": "Nerq", "item": "{SITE}"}},
    {{"@type": "ListItem", "position": 2, "name": "Protocol", "item": "{canonical}"}}
  ]
}}"""

    json_ld_faq = """{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {"@type": "Question", "name": "What is the Nerq Trust Protocol?", "acceptedAnswer": {"@type": "Answer", "text": "The Nerq Trust Protocol is a lightweight HTTP-based protocol that enables AI agents to verify the trustworthiness of other agents before interacting with them. It provides trust scores, grades, and risk signals through a simple REST API."}},
    {"@type": "Question", "name": "How do AI agents verify each other?", "acceptedAnswer": {"@type": "Answer", "text": "An agent calls GET /v1/preflight with the target agent's name. Nerq returns a trust score (0-100), letter grade, and recommendation (PROCEED, CAUTION, or ABORT). The calling agent applies a threshold gate to decide whether to proceed."}},
    {"@type": "Question", "name": "What trust score threshold should I use?", "acceptedAnswer": {"@type": "Answer", "text": "For production workloads, use a threshold of 70 or higher. For financial or safety-critical tasks, use 80+. For exploratory or sandboxed tasks, 50+ is acceptable. The default recommendation is 70."}}
  ]
}"""

    return f"""<!-- AI-SUMMARY: The Nerq Agent Trust Protocol v1.0 defines a lightweight HTTP protocol for AI agents to verify each other's trustworthiness before interaction. It specifies trust queries via GET /v1/preflight, trust gates with configurable thresholds, and integration patterns for LangChain, LangGraph, CrewAI, AutoGen, and A2A. -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nerq">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<script type="application/ld+json">{json_ld_webpage}</script>
<script type="application/ld+json">{json_ld_breadcrumb}</script>
<script type="application/ld+json">{json_ld_faq}</script>
<style>{PROTOCOL_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">

<div class="breadcrumb"><a href="/">nerq</a> / protocol</div>

<span class="hero-badge">PROTOCOL v1.0</span>
<h1>Agent Trust Protocol</h1>
<p class="desc">A lightweight HTTP protocol for AI agents to verify the trustworthiness of other agents before interaction. One API call, one trust decision.</p>

<!-- Overview -->
<h2>Overview</h2>
<p style="color:#999;margin-bottom:16px">AI agents increasingly delegate tasks to other agents. Without trust verification, failures cascade. The Nerq Trust Protocol provides a standardized way for agents to check trust before interaction.</p>

<div class="stat-row">
  <div class="stat-item"><div class="num">35.6%</div><div class="label">agent interaction failure rate without trust checks</div></div>
  <div class="stat-item"><div class="num">60%</div><div class="label">of enterprises don't trust AI agent outputs</div></div>
  <div class="stat-item"><div class="num">40%</div><div class="label">of agent deployments canceled due to trust concerns</div></div>
</div>

<!-- Trust Query -->
<h2>Trust Query</h2>
<p style="color:#999;margin-bottom:12px">A single HTTP GET returns everything an agent needs to make a trust decision.</p>

<h3>Request</h3>
<pre>GET /v1/preflight?target=langchain&amp;caller=my-agent HTTP/1.1
Host: nerq.ai
Accept: application/json</pre>

<h3>Response</h3>
<pre>{{
  "target": "langchain",
  "trust_score": 87.3,
  "trust_grade": "A",
  "recommendation": "PROCEED",
  "risk_flags": [],
  "checked_at": "2026-03-12T14:30:00Z",
  "ttl": 3600
}}</pre>

<div class="section-card">
<h3>Response Fields</h3>
<table>
<tr><th>Field</th><th>Type</th><th>Description</th></tr>
<tr><td><code>target</code></td><td>string</td><td>Name of the agent being checked</td></tr>
<tr><td><code>trust_score</code></td><td>float</td><td>Trust score from 0 to 100</td></tr>
<tr><td><code>trust_grade</code></td><td>string</td><td>Letter grade: A, B, C, D, F</td></tr>
<tr><td><code>recommendation</code></td><td>string</td><td>PROCEED, CAUTION, or ABORT</td></tr>
<tr><td><code>risk_flags</code></td><td>array</td><td>Active risk signals (e.g., "no-license", "low-maintenance")</td></tr>
<tr><td><code>checked_at</code></td><td>ISO 8601</td><td>Timestamp of the trust check</td></tr>
<tr><td><code>ttl</code></td><td>int</td><td>Seconds until the score should be re-checked</td></tr>
</table>
</div>

<!-- Trust Gate -->
<h2>Trust Gate</h2>
<p style="color:#999;margin-bottom:12px">Agents apply a threshold to the trust score. If the score is below the threshold, the agent should not delegate.</p>

<div class="section-card">
<h3>Recommended Thresholds</h3>
<table>
<tr><th>Use Case</th><th>Threshold</th><th>Action if Below</th></tr>
<tr><td>Financial / safety-critical</td><td><code>80</code></td><td>ABORT &mdash; do not delegate</td></tr>
<tr><td>Production workloads</td><td><code>70</code></td><td>ABORT or require human approval</td></tr>
<tr><td>Exploratory / sandboxed</td><td><code>50</code></td><td>CAUTION &mdash; proceed with logging</td></tr>
<tr><td>Research / development</td><td><code>30</code></td><td>CAUTION &mdash; proceed with monitoring</td></tr>
</table>
</div>

<h3>Gate Logic (3 lines)</h3>
<pre>result = requests.get("https://nerq.ai/v1/preflight", params={{"target": agent_name}}).json()
if result["trust_score"] &lt; THRESHOLD:
    raise RuntimeError(f"Trust gate failed: {{agent_name}} scored {{result['trust_score']}}")</pre>

<!-- Integration Patterns -->
<h2>Integration Patterns</h2>
<p style="color:#999;margin-bottom:12px">Drop-in trust checks for popular agent frameworks.</p>

<div class="section-card">
<h3>LangChain</h3>
<pre>from langchain.tools import tool
import requests

@tool
def check_trust(agent: str) -&gt; str:
    r = requests.get("https://nerq.ai/v1/preflight", params={{"target": agent}}).json()
    return f"{{agent}}: {{r['trust_score']}} ({{r['recommendation']}})"</pre>
</div>

<div class="section-card">
<h3>LangGraph</h3>
<pre>def trust_gate_node(state):
    r = requests.get("https://nerq.ai/v1/preflight", params={{"target": state["agent"]}}).json()
    state["trusted"] = r["trust_score"] &gt;= 70
    return state</pre>
</div>

<div class="section-card">
<h3>CrewAI</h3>
<pre>from crewai.tools import BaseTool

class TrustCheck(BaseTool):
    name = "nerq_trust_check"
    description = "Check an agent's trust score before delegation"
    def _run(self, agent: str) -&gt; str:
        r = requests.get("https://nerq.ai/v1/preflight", params={{"target": agent}}).json()
        return f"Score: {{r['trust_score']}}, Recommendation: {{r['recommendation']}}"</pre>
</div>

<div class="section-card">
<h3>AutoGen</h3>
<pre>def trust_check(agent_name: str) -&gt; dict:
    \"\"\"Check trust score for an agent via Nerq.\"\"\"
    return requests.get("https://nerq.ai/v1/preflight", params={{"target": agent_name}}).json()</pre>
</div>

<!-- A2A Trust Handshake -->
<h2>A2A Trust Handshake</h2>
<p style="color:#999;margin-bottom:12px">When two agents interact via Google's Agent-to-Agent (A2A) protocol, the calling agent should verify trust before sending tasks.</p>

<div class="section-card">
<h3>Handshake Flow</h3>
<pre>1. Agent A discovers Agent B via A2A /.well-known/agent.json
2. Agent A calls GET /v1/preflight?target=agent-b&amp;caller=agent-a
3. Nerq returns trust score, grade, and recommendation
4. If trust_score &gt;= threshold: Agent A sends task to Agent B
5. If trust_score &lt; threshold: Agent A aborts or escalates to human</pre>
</div>

<pre># A2A + Nerq trust handshake
import requests

def a2a_with_trust(target_url: str, task: dict, threshold: int = 70):
    # Step 1: Discover agent
    agent_card = requests.get(f"{{target_url}}/.well-known/agent.json").json()
    agent_name = agent_card.get("name", "unknown")

    # Step 2: Trust check
    trust = requests.get("https://nerq.ai/v1/preflight", params={{"target": agent_name}}).json()

    # Step 3: Gate
    if trust["trust_score"] &lt; threshold:
        return {{"error": f"Trust gate failed: {{agent_name}} scored {{trust['trust_score']}}"}}

    # Step 4: Send task via A2A
    return requests.post(f"{{target_url}}/a2a", json=task).json()</pre>

<!-- Links -->
<h2>Resources</h2>
<a href="/integrate" class="cta-link">Integration Hub</a>
<a href="/safe" class="cta-link">Agent Safety Reports</a>
<a href="/blog/trust-handshake" class="cta-link">Blog: Trust Handshake</a>
<a href="https://github.com/nerq-ai/trust-protocol" class="cta-link">GitHub</a>
<a href="/federation" class="cta-link">Federation Protocol</a>

<!-- Federated Trust -->
<h2>Federated Trust</h2>
<p>Nerq Trust Scores are federated across 13+ independent data sources for maximum reliability:</p>
<ul>
<li><strong>Proprietary:</strong> GitHub activity, npm/PyPI downloads, CVE/NVD scanning, license analysis, framework detection, pricing data</li>
<li><strong>External:</strong> OpenSSF Scorecard (security practices), OSV.dev (vulnerability cross-reference), Stack Overflow (community), Reddit (sentiment)</li>
<li><strong>Federated:</strong> External platforms can contribute their own trust assessments via <code>POST /v1/federation/contribute</code></li>
</ul>
<p>The more sources that independently confirm an agent's quality, the higher the confidence score. See <a href="/federation">/federation</a> for full details.</p>

<!-- FAQ -->
<h2>FAQ</h2>
<div class="faq-item">
  <div class="faq-q">What is the Nerq Trust Protocol?</div>
  <div class="faq-a">The Nerq Trust Protocol is a lightweight HTTP-based protocol that enables AI agents to verify the trustworthiness of other agents before interacting with them. It provides trust scores, grades, and risk signals through a simple REST API.</div>
</div>
<div class="faq-item">
  <div class="faq-q">How do AI agents verify each other?</div>
  <div class="faq-a">An agent calls <code>GET /v1/preflight</code> with the target agent's name. Nerq returns a trust score (0&ndash;100), letter grade, and recommendation (PROCEED, CAUTION, or ABORT). The calling agent applies a threshold gate to decide whether to proceed.</div>
</div>
<div class="faq-item">
  <div class="faq-q">What trust score threshold should I use?</div>
  <div class="faq-a">For production workloads, use a threshold of 70 or higher. For financial or safety-critical tasks, use 80+. For exploratory or sandboxed tasks, 50+ is acceptable. The default recommendation is 70.</div>
</div>

</main>
{FOOTER}
</body>
</html>"""


def _blog_trust_handshake() -> str:
    """Build the /blog/trust-handshake blog post."""

    title = "How AI Agents Verify Each Other: The Trust Handshake"
    description = "35.6% of agent interactions fail without trust checks. Here's how the Nerq Trust Protocol solves agent-to-agent verification."
    canonical = f"{SITE}/blog/trust-handshake"

    json_ld_blog = f"""{{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": "{title}",
  "description": "{description}",
  "url": "{canonical}",
  "datePublished": "2026-03-12",
  "dateModified": "{TODAY}",
  "author": {{"@type": "Organization", "name": "Nerq"}},
  "publisher": {{"@type": "Organization", "name": "Nerq", "url": "{SITE}"}},
  "mainEntityOfPage": "{canonical}"
}}"""

    json_ld_breadcrumb = f"""{{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {{"@type": "ListItem", "position": 1, "name": "Nerq", "item": "{SITE}"}},
    {{"@type": "ListItem", "position": 2, "name": "Blog", "item": "{SITE}/blog"}},
    {{"@type": "ListItem", "position": 3, "name": "Trust Handshake", "item": "{canonical}"}}
  ]
}}"""

    json_ld_faq = """{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {"@type": "Question", "name": "What is a trust handshake between AI agents?", "acceptedAnswer": {"@type": "Answer", "text": "A trust handshake is the process where one AI agent verifies the trustworthiness of another agent before delegating a task. It involves querying Nerq's preflight API to get a trust score and applying a threshold gate."}},
    {"@type": "Question", "name": "Why do agent interactions fail without trust checks?", "acceptedAnswer": {"@type": "Answer", "text": "Without trust checks, agents may delegate tasks to unreliable, unmaintained, or malicious agents. Research shows a 35.6% failure rate in agent interactions that lack trust verification, leading to cascading failures and unreliable outputs."}},
    {"@type": "Question", "name": "How do I add trust checks to LangGraph?", "acceptedAnswer": {"@type": "Answer", "text": "Add a trust_gate node to your LangGraph workflow that calls GET /v1/preflight before the delegation node. If the trust score is below your threshold, route to a fallback or abort node instead of proceeding."}}
  ]
}"""

    return f"""<!-- AI-SUMMARY: This blog post explains how AI agents verify each other using the Nerq Trust Protocol. It covers the 35.6% failure rate problem in agent-to-agent interactions, the trust handshake solution via GET /v1/preflight, and a step-by-step code walkthrough showing how a LangGraph agent checks trust before delegation. -->
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Nerq">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<script type="application/ld+json">{json_ld_blog}</script>
<script type="application/ld+json">{json_ld_breadcrumb}</script>
<script type="application/ld+json">{json_ld_faq}</script>
<style>{PROTOCOL_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">

<div class="breadcrumb"><a href="/">nerq</a> / <a href="/blog">blog</a> / trust-handshake</div>

<span class="hero-badge">BLOG</span>
<h1>How AI Agents Verify Each Other: The Trust Handshake</h1>
<p style="color:#666;font-size:13px;margin-bottom:20px">March 12, 2026 &middot; Nerq Team</p>
<p class="desc">35.6% of agent interactions fail without trust checks. Here&rsquo;s how the Nerq Trust Protocol solves agent-to-agent verification in three lines of code.</p>

<!-- The Problem -->
<h2>The Problem: Blind Delegation</h2>
<p style="color:#999;margin-bottom:12px">Multi-agent systems are growing fast. LangGraph workflows chain multiple agents. CrewAI assembles agent teams. AutoGen orchestrates agent conversations. But none of them answer a critical question: <strong style="color:#fff">should this agent be trusted?</strong></p>

<div class="stat-row">
  <div class="stat-item"><div class="num">35.6%</div><div class="label">failure rate without trust checks</div></div>
  <div class="stat-item"><div class="num">60%</div><div class="label">of enterprises don't trust AI outputs</div></div>
  <div class="stat-item"><div class="num">40%</div><div class="label">of deployments canceled over trust</div></div>
</div>

<p style="color:#999;margin-top:16px">When Agent A delegates a research task to Agent B, it has no way to know if Agent B is well-maintained, has a track record, or is safe to use. The result: cascading failures, hallucinated data passed between agents, and production outages.</p>

<!-- The Solution -->
<h2>The Solution: Nerq Trust Protocol</h2>
<p style="color:#999;margin-bottom:12px">The <a href="/protocol">Nerq Trust Protocol</a> adds a single verification step before any agent-to-agent interaction. One HTTP call. One trust decision.</p>

<div class="section-card">
<h3>The Trust Handshake in 3 Steps</h3>
<p style="color:#999;font-size:14px;margin-bottom:12px"><strong style="color:#fff">Step 1:</strong> Agent A identifies a candidate agent to delegate to.</p>
<p style="color:#999;font-size:14px;margin-bottom:12px"><strong style="color:#fff">Step 2:</strong> Agent A calls Nerq&rsquo;s preflight API to check the candidate&rsquo;s trust score.</p>
<p style="color:#999;font-size:14px;margin-bottom:12px"><strong style="color:#fff">Step 3:</strong> Agent A applies a threshold gate. If the score is high enough, it proceeds. If not, it aborts or finds an alternative.</p>
</div>

<pre>import requests

# One API call to check trust
result = requests.get("https://nerq.ai/v1/preflight", params={{"target": "gpt-researcher"}}).json()

# One trust decision
if result["trust_score"] &lt; 70:
    raise RuntimeError(f"Trust gate failed: scored {{result['trust_score']}}")
</pre>

<!-- Code Walkthrough -->
<h2>Code Walkthrough: LangGraph + Trust Gate</h2>
<p style="color:#999;margin-bottom:12px">Here&rsquo;s a complete LangGraph workflow where Agent A (a researcher) checks trust before delegating to a sub-agent.</p>

<pre>from langgraph.graph import StateGraph
import requests

NERQ_API = "https://nerq.ai"
THRESHOLD = 70

def discover_agents(state):
    \"\"\"Find candidate agents for the task.\"\"\"
    state["candidates"] = ["gpt-researcher", "crewai", "autogpt"]
    return state

def trust_gate(state):
    \"\"\"Check trust for each candidate. Pick the best trusted one.\"\"\"
    best = None
    for agent_name in state["candidates"]:
        r = requests.get(f"{{NERQ_API}}/v1/preflight", params={{"target": agent_name}}).json()
        score = r.get("trust_score", 0)
        if score &gt;= THRESHOLD and (best is None or score &gt; best["score"]):
            best = {{"name": agent_name, "score": score, "grade": r.get("trust_grade")}}
    state["delegate"] = best
    return state

def delegate_or_abort(state):
    \"\"\"Delegate to the trusted agent, or abort.\"\"\"
    if state["delegate"]:
        return {{"result": f"Delegated to {{state['delegate']['name']}} (score: {{state['delegate']['score']}})"}}
    return {{"result": "No trusted agent found. Task aborted."}}

# Build the graph
graph = StateGraph(dict)
graph.add_node("discover", discover_agents)
graph.add_node("trust_gate", trust_gate)
graph.add_node("delegate", delegate_or_abort)
graph.add_edge("discover", "trust_gate")
graph.add_edge("trust_gate", "delegate")
graph.set_entry_point("discover")
graph.set_finish_point("delegate")

app = graph.compile()
result = app.invoke({{}})
print(result)</pre>

<p style="color:#999;margin-top:16px">The trust gate node sits between discovery and delegation. It&rsquo;s a single node, a single API call per candidate, and it prevents your workflow from delegating to untrusted agents.</p>

<!-- What Trust Scores Mean -->
<h2>What Trust Scores Mean</h2>
<div class="section-card">
<table>
<tr><th>Score</th><th>Grade</th><th>Meaning</th></tr>
<tr><td><code>90&ndash;100</code></td><td>A</td><td>Highly trusted. Well-maintained, widely used, strong track record.</td></tr>
<tr><td><code>70&ndash;89</code></td><td>B</td><td>Trusted. Active development, reasonable adoption.</td></tr>
<tr><td><code>50&ndash;69</code></td><td>C</td><td>Caution. May have gaps in maintenance or documentation.</td></tr>
<tr><td><code>30&ndash;49</code></td><td>D</td><td>Low trust. Limited adoption, potential issues.</td></tr>
<tr><td><code>0&ndash;29</code></td><td>F</td><td>Untrusted. Do not delegate production tasks.</td></tr>
</table>
</div>

<!-- Next Steps -->
<h2>Next Steps</h2>
<a href="/protocol" class="cta-link">Read the Full Protocol Spec</a>
<a href="/integrate/langgraph" class="cta-link">LangGraph Integration Guide</a>
<a href="/safe" class="cta-link">Agent Safety Reports</a>

<!-- FAQ -->
<h2>FAQ</h2>
<div class="faq-item">
  <div class="faq-q">What is a trust handshake between AI agents?</div>
  <div class="faq-a">A trust handshake is the process where one AI agent verifies the trustworthiness of another agent before delegating a task. It involves querying Nerq&rsquo;s preflight API to get a trust score and applying a threshold gate.</div>
</div>
<div class="faq-item">
  <div class="faq-q">Why do agent interactions fail without trust checks?</div>
  <div class="faq-a">Without trust checks, agents may delegate tasks to unreliable, unmaintained, or malicious agents. Research shows a 35.6% failure rate in agent interactions that lack trust verification, leading to cascading failures and unreliable outputs.</div>
</div>
<div class="faq-item">
  <div class="faq-q">How do I add trust checks to LangGraph?</div>
  <div class="faq-a">Add a <code>trust_gate</code> node to your LangGraph workflow that calls <code>GET /v1/preflight</code> before the delegation node. If the trust score is below your threshold, route to a fallback or abort node instead of proceeding.</div>
</div>

</main>
{FOOTER}
</body>
</html>"""


def mount_protocol_pages(app):
    """Mount /protocol and /blog/trust-handshake routes."""

    @app.get("/protocol", response_class=HTMLResponse, include_in_schema=False)
    async def protocol_page():
        return HTMLResponse(_protocol_page())

    @app.get("/blog/trust-handshake", response_class=HTMLResponse, include_in_schema=False)
    async def blog_trust_handshake():
        return HTMLResponse(_blog_trust_handshake())

    logger.info("Mounted /protocol and /blog/trust-handshake")
