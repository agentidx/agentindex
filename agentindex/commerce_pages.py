"""
Nerq Commerce Trust Pages
==========================
/commerce — Landing page for agentic commerce trust infrastructure
/commerce/docs — API documentation for Commerce Trust endpoint
/blog/agentic-commerce-trust — Blog post on AI shopping agent verification

Usage in discovery.py:
    from agentindex.commerce_pages import mount_commerce_pages
    mount_commerce_pages(app)
"""

import logging
from datetime import date, datetime
from pathlib import Path as _Path
from fastapi.responses import HTMLResponse

logger = logging.getLogger("nerq.commerce_pages")

SITE = "https://nerq.ai"
# Module-load-time "today" was a moving freshness lie under HCU. Pin
# dateModified to this file's mtime instead — it only moves when the
# page code itself actually changes.
try:
    TODAY = datetime.utcfromtimestamp(_Path(__file__).stat().st_mtime).strftime("%Y-%m-%d")
except Exception:
    TODAY = "2026-04-01"

# ── Dark-theme commerce styling (matches protocol/integration pages) ──
COMMERCE_CSS = """
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
.use-case-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin:20px 0}
.use-case-card{border:1px solid #222;border-radius:8px;padding:20px;background:#111;transition:border-color 0.15s}
.use-case-card:hover{border-color:#00d4aa}
.use-case-card h4{margin-bottom:6px;font-size:0.95rem}
.use-case-card p{color:#888;font-size:13px;line-height:1.6}
.flow-steps{display:flex;gap:12px;margin:20px 0;flex-wrap:wrap;align-items:center}
.flow-step{border:1px solid #222;border-radius:8px;padding:16px 20px;background:#111;text-align:center;flex:1;min-width:160px}
.flow-step .step-num{font-size:11px;color:#00d4aa;font-weight:700;font-family:'JetBrains Mono',monospace;margin-bottom:4px}
.flow-step .step-label{font-size:14px;color:#fff;font-weight:600}
.flow-step .step-desc{font-size:12px;color:#888;margin-top:4px}
.flow-arrow{font-size:18px;color:#333;flex-shrink:0}
.blog-meta{font-size:13px;color:#666;margin:8px 0 20px}
.blog-body p{margin:12px 0;color:#ccc;line-height:1.8}
.blog-body h2{margin-top:36px}
.blog-body h3{margin-top:24px}
.blog-body ul,.blog-body ol{margin:12px 0 12px 24px;color:#ccc}
.blog-body li{margin:6px 0;line-height:1.7}
.blog-body blockquote{border-left:3px solid #00d4aa;padding:8px 16px;margin:16px 0;color:#999;font-style:italic}
@media(max-width:640px){
nav .links{gap:12px;font-size:13px;flex-wrap:wrap}
.stat-row{gap:16px}
h1{font-size:1.4rem}
.flow-steps{flex-direction:column}
.flow-arrow{transform:rotate(90deg)}
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
<a href="/commerce">commerce</a>
<a href="/stats">stats</a>
<a href="/blog">blog</a>
</div>
</div></nav>"""

FOOTER = """<footer><div class="inner">
nerq &mdash; the ai asset search engine &middot; 5M+ assets indexed &middot;
<a href="/nerq/docs">api</a> &middot;
<a href="/integrate">integrate</a> &middot;
<a href="/protocol">protocol</a> &middot;
<a href="/commerce">commerce</a> &middot;
<a href="https://zarq.ai">zarq.ai</a> (crypto risk)
</div></footer>"""


# ── Route 1: /commerce — Landing page ──────────────────────────

def _commerce_landing() -> str:
    title = "Trust Infrastructure for Agentic Commerce — Nerq"
    description = "Verify AI shopping agents before they transact. Trust layer for the $385B agentic commerce market."
    canonical = f"{SITE}/commerce"

    faq_jsonld = """{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What is agentic commerce?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Agentic commerce is the emerging category of autonomous AI agents that buy, sell, negotiate, and transact on behalf of humans or organizations. These agents operate independently, making purchasing decisions, comparing vendors, and executing transactions without human intervention for each step."
      }
    },
    {
      "@type": "Question",
      "name": "How do you verify AI shopping agents?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Nerq verifies AI agents by computing a Trust Score based on provenance analysis, behavioral history, code audit signals, and community reputation. The Commerce Trust endpoint evaluates both the agent initiating a transaction and the counterparty, returning an approval decision in under 50ms."
      }
    },
    {
      "@type": "Question",
      "name": "Is agentic commerce safe?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Agentic commerce carries risks including agent impersonation, unauthorized purchases, data exposure, and prompt injection attacks. Nerq mitigates these risks by providing real-time trust verification before any transaction executes, ensuring both parties in an agent-to-agent exchange meet minimum trust thresholds."
      }
    }
  ]
}"""

    webpage_jsonld = f"""{{"@context":"https://schema.org","@type":"WebPage","name":"{title}","description":"{description}","url":"{canonical}","dateModified":"{TODAY}","publisher":{{"@type":"Organization","name":"Nerq","url":"{SITE}"}}}}"""

    breadcrumb_jsonld = f"""{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Home","item":"{SITE}"}},{{"@type":"ListItem","position":2,"name":"Commerce","item":"{canonical}"}}]}}"""

    return f"""<!-- AI Summary: Nerq Commerce Trust Infrastructure — trust verification layer for the $385B agentic commerce market. Provides real-time agent verification before autonomous transactions. 204K agents indexed, sub-50ms verification, 1000 req/hr free tier. -->
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
<script type="application/ld+json">{webpage_jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
<script type="application/ld+json">{faq_jsonld}</script>
<style>{COMMERCE_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px">

<div class="breadcrumb"><a href="/">nerq</a> / commerce</div>

<div class="hero-badge">COMMERCE TRUST LAYER</div>
<h1>Trust Infrastructure for Agentic Commerce</h1>
<p class="desc">Verify AI shopping agents before they transact. The trust layer for the $385B agentic commerce market.</p>

<div class="stat-row">
<div class="stat-item"><div class="num">204K</div><div class="label">agents indexed</div></div>
<div class="stat-item"><div class="num">&lt;50ms</div><div class="label">verification latency</div></div>
<div class="stat-item"><div class="num">1,000</div><div class="label">req/hr free tier</div></div>
</div>

<h2>The Problem</h2>
<div class="section-card">
<p style="color:#ccc;line-height:1.8">AI agents are buying products, negotiating contracts, and settling payments autonomously. Morgan Stanley projects $190&ndash;385B in agent-driven e-commerce by 2030. But there is no verification layer. No way for a merchant to confirm an agent is authorized. No way for a platform to verify an agent&rsquo;s identity. No way to distinguish a legitimate purchasing agent from a malicious one. <strong style="color:#fff">Agentic commerce needs a trust layer.</strong></p>
</div>

<h2>How It Works</h2>
<div class="flow-steps">
<div class="flow-step">
<div class="step-num">01</div>
<div class="step-label">Agent Request</div>
<div class="step-desc">Agent initiates a transaction and sends identifiers to Nerq</div>
</div>
<div class="flow-arrow">&rarr;</div>
<div class="flow-step">
<div class="step-num">02</div>
<div class="step-label">Nerq Verify</div>
<div class="step-desc">Trust Score computed from provenance, behavior, code audit</div>
</div>
<div class="flow-arrow">&rarr;</div>
<div class="flow-step">
<div class="step-num">03</div>
<div class="step-label">Approve / Reject</div>
<div class="step-desc">Sub-50ms decision returned with confidence + risk level</div>
</div>
</div>

<h2>Code Example</h2>
<pre><span style="color:#00d4aa">from</span> nerq_commerce <span style="color:#00d4aa">import</span> verify_transaction

result = verify_transaction(
    agent_id=<span style="color:#e8c87a">"my-agent"</span>,
    counterparty=<span style="color:#e8c87a">"vendor"</span>,
    action=<span style="color:#e8c87a">"purchase"</span>,
    risk_tolerance=<span style="color:#e8c87a">"medium"</span>
)

<span style="color:#00d4aa">if</span> result.approved:
    execute_transaction()
</pre>

<h2>Use Cases</h2>
<div class="use-case-grid">
<div class="use-case-card">
<h4>AI Shopping Assistants</h4>
<p>Verify that a shopping agent is authorized to make purchases on behalf of its principal before processing payment.</p>
</div>
<div class="use-case-card">
<h4>Autonomous Procurement</h4>
<p>Enterprise procurement agents comparing vendors and placing orders need trust verification to prevent supply-chain attacks.</p>
</div>
<div class="use-case-card">
<h4>Agent-to-Agent Negotiation</h4>
<p>When two agents negotiate terms, both sides need to verify the other&rsquo;s identity and authorization before agreeing to binding terms.</p>
</div>
<div class="use-case-card">
<h4>DeFi Agent Operations</h4>
<p>Autonomous agents executing swaps, lending, and yield farming require trust checks to prevent unauthorized token transfers.</p>
</div>
</div>

<h2>Get Started</h2>
<div class="section-card">
<pre style="margin:0 0 12px">pip install nerq-commerce</pre>
<a href="/commerce/demo" class="cta-link" style="font-weight:700;color:#00f0c0">Try the live demo &rarr;</a>
<a href="/commerce/docs" class="cta-link">Read the docs &rarr;</a>
<a href="/protocol" class="cta-link">Trust Protocol spec &rarr;</a>
<a href="/integrate" class="cta-link">Integration guides &rarr;</a>
</div>

<h2>Frequently Asked Questions</h2>

<div class="faq-item">
<div class="faq-q">What is agentic commerce?</div>
<div class="faq-a">Agentic commerce is the emerging category of autonomous AI agents that buy, sell, negotiate, and transact on behalf of humans or organizations. These agents operate independently, making purchasing decisions, comparing vendors, and executing transactions without human intervention for each step.</div>
</div>

<div class="faq-item">
<div class="faq-q">How do you verify AI shopping agents?</div>
<div class="faq-a">Nerq verifies AI agents by computing a Trust Score based on provenance analysis, behavioral history, code audit signals, and community reputation. The Commerce Trust endpoint evaluates both the agent initiating a transaction and the counterparty, returning an approval decision in under 50ms.</div>
</div>

<div class="faq-item">
<div class="faq-q">Is agentic commerce safe?</div>
<div class="faq-a">Agentic commerce carries risks including agent impersonation, unauthorized purchases, data exposure, and prompt injection attacks. Nerq mitigates these risks by providing real-time trust verification before any transaction executes, ensuring both parties in an agent-to-agent exchange meet minimum trust thresholds.</div>
</div>

</main>
{FOOTER}
</body>
</html>"""


# ── Route 2: /commerce/docs — API Documentation ───────────────

def _commerce_docs() -> str:
    title = "Commerce Trust API — Nerq"
    description = "API documentation for the Nerq Commerce Trust endpoint. Verify AI agent transactions in real time."
    canonical = f"{SITE}/commerce/docs"

    webpage_jsonld = f"""{{"@context":"https://schema.org","@type":"WebPage","name":"{title}","description":"{description}","url":"{canonical}","dateModified":"{TODAY}","publisher":{{"@type":"Organization","name":"Nerq","url":"{SITE}"}}}}"""

    breadcrumb_jsonld = f"""{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Home","item":"{SITE}"}},{{"@type":"ListItem","position":2,"name":"Commerce","item":"{SITE}/commerce"}},{{"@type":"ListItem","position":3,"name":"Docs","item":"{canonical}"}}]}}"""

    return f"""<!-- AI Summary: Nerq Commerce Trust API documentation. POST /v1/commerce/verify for single transaction verification, POST /v1/commerce/verify/batch for bulk verification. SDK: pip install nerq-commerce. Rate limit: 1000 req/hr free, 50K req/hr pro. Sub-50ms p95 latency. -->
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
<script type="application/ld+json">{webpage_jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
<style>{COMMERCE_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px">

<div class="breadcrumb"><a href="/">nerq</a> / <a href="/commerce">commerce</a> / docs</div>

<div class="hero-badge">API REFERENCE</div>
<h1>Commerce Trust API</h1>
<p class="desc">Verify AI agent transactions before execution. Single and batch endpoints with sub-50ms latency.</p>

<h2>Base URL</h2>
<pre>https://nerq.ai/v1/commerce</pre>

<h2>Authentication</h2>
<p style="color:#ccc;margin:8px 0">Include your API key in the <code>Authorization</code> header:</p>
<pre>Authorization: Bearer YOUR_API_KEY</pre>
<p style="color:#888;font-size:13px;margin-top:8px">Get your API key at <a href="/nerq/docs">/nerq/docs</a>. Free tier: 1,000 req/hr. Pro: 50,000 req/hr.</p>

<h2>POST /v1/commerce/verify</h2>
<p style="color:#ccc;margin:8px 0 16px">Verify a single agent transaction. Returns approval decision with trust metadata.</p>

<h3>Request Body</h3>
<pre>{{
  "agent_id": "shopping-agent-42",
  "counterparty": "vendor-abc",
  "action": "purchase",
  "risk_tolerance": "medium",
  "amount_usd": 250.00,
  "metadata": {{
    "category": "electronics",
    "platform": "marketplace-x"
  }}
}}</pre>

<h3>Request Fields</h3>
<table>
<tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr>
<tr><td><code>agent_id</code></td><td>string</td><td>Yes</td><td>Identifier of the agent initiating the transaction</td></tr>
<tr><td><code>counterparty</code></td><td>string</td><td>Yes</td><td>Identifier of the vendor or receiving agent</td></tr>
<tr><td><code>action</code></td><td>string</td><td>Yes</td><td>Transaction type: <code>purchase</code>, <code>sell</code>, <code>negotiate</code>, <code>transfer</code></td></tr>
<tr><td><code>risk_tolerance</code></td><td>string</td><td>No</td><td>Threshold: <code>low</code>, <code>medium</code>, <code>high</code>. Default: <code>medium</code></td></tr>
<tr><td><code>amount_usd</code></td><td>number</td><td>No</td><td>Transaction amount in USD for risk-adjusted scoring</td></tr>
<tr><td><code>metadata</code></td><td>object</td><td>No</td><td>Additional context (category, platform, etc.)</td></tr>
</table>

<h3>Response</h3>
<pre>{{
  "approved": true,
  "trust_score": 0.87,
  "agent_trust": {{
    "score": 0.87,
    "risk_level": "low",
    "provenance": "verified",
    "last_audit": "2026-03-10"
  }},
  "counterparty_trust": {{
    "score": 0.92,
    "risk_level": "low",
    "provenance": "verified",
    "last_audit": "2026-03-11"
  }},
  "decision": {{
    "action": "approve",
    "confidence": 0.94,
    "risk_factors": [],
    "recommendation": "Transaction meets trust threshold for medium risk tolerance."
  }},
  "latency_ms": 23
}}</pre>

<h3>Response Fields</h3>
<table>
<tr><th>Field</th><th>Type</th><th>Description</th></tr>
<tr><td><code>approved</code></td><td>boolean</td><td>Whether the transaction is approved</td></tr>
<tr><td><code>trust_score</code></td><td>number</td><td>Combined trust score (0.0&ndash;1.0)</td></tr>
<tr><td><code>agent_trust</code></td><td>object</td><td>Trust details for the initiating agent</td></tr>
<tr><td><code>counterparty_trust</code></td><td>object</td><td>Trust details for the counterparty</td></tr>
<tr><td><code>decision</code></td><td>object</td><td>Decision metadata with confidence and risk factors</td></tr>
<tr><td><code>latency_ms</code></td><td>number</td><td>Server-side processing time in milliseconds</td></tr>
</table>

<h3>cURL Example</h3>
<pre>curl -X POST https://nerq.ai/v1/commerce/verify \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "agent_id": "shopping-agent-42",
    "counterparty": "vendor-abc",
    "action": "purchase",
    "risk_tolerance": "medium"
  }}'</pre>

<h2>POST /v1/commerce/verify/batch</h2>
<p style="color:#ccc;margin:8px 0 16px">Verify multiple transactions in a single request. Max 50 transactions per batch.</p>

<h3>Request Body</h3>
<pre>{{
  "transactions": [
    {{
      "agent_id": "procurement-bot-7",
      "counterparty": "supplier-alpha",
      "action": "purchase",
      "risk_tolerance": "low"
    }},
    {{
      "agent_id": "procurement-bot-7",
      "counterparty": "supplier-beta",
      "action": "negotiate",
      "risk_tolerance": "medium"
    }}
  ]
}}</pre>

<h3>Response</h3>
<pre>{{
  "results": [
    {{
      "index": 0,
      "approved": true,
      "trust_score": 0.91,
      "decision": {{"action": "approve", "confidence": 0.95}}
    }},
    {{
      "index": 1,
      "approved": true,
      "trust_score": 0.84,
      "decision": {{"action": "approve", "confidence": 0.88}}
    }}
  ],
  "batch_latency_ms": 67
}}</pre>

<h2>SDK Usage</h2>
<pre>pip install nerq-commerce</pre>

<h3>Python SDK</h3>
<pre><span style="color:#00d4aa">from</span> nerq_commerce <span style="color:#00d4aa">import</span> NerqCommerce

client = NerqCommerce(api_key=<span style="color:#e8c87a">"YOUR_API_KEY"</span>)

<span style="color:#888"># Single verification</span>
result = client.verify(
    agent_id=<span style="color:#e8c87a">"my-agent"</span>,
    counterparty=<span style="color:#e8c87a">"vendor"</span>,
    action=<span style="color:#e8c87a">"purchase"</span>,
    risk_tolerance=<span style="color:#e8c87a">"medium"</span>
)

<span style="color:#00d4aa">if</span> result.approved:
    print(f<span style="color:#e8c87a">"Approved with score {{result.trust_score}}"</span>)

<span style="color:#888"># Batch verification</span>
results = client.verify_batch([
    {{"agent_id": <span style="color:#e8c87a">"bot-1"</span>, "counterparty": <span style="color:#e8c87a">"vendor-a"</span>, "action": <span style="color:#e8c87a">"purchase"</span>}},
    {{"agent_id": <span style="color:#e8c87a">"bot-1"</span>, "counterparty": <span style="color:#e8c87a">"vendor-b"</span>, "action": <span style="color:#e8c87a">"negotiate"</span>}},
])
</pre>

<h2>Error Codes</h2>
<table>
<tr><th>Code</th><th>Meaning</th><th>Description</th></tr>
<tr><td><code>400</code></td><td>Bad Request</td><td>Missing required fields or invalid values. Check <code>agent_id</code>, <code>counterparty</code>, and <code>action</code>.</td></tr>
<tr><td><code>401</code></td><td>Unauthorized</td><td>Missing or invalid API key.</td></tr>
<tr><td><code>429</code></td><td>Rate Limited</td><td>Exceeded rate limit. Free: 1,000 req/hr. Pro: 50,000 req/hr. Retry after <code>Retry-After</code> header.</td></tr>
<tr><td><code>500</code></td><td>Server Error</td><td>Internal error. Retry with exponential backoff. If persistent, contact support.</td></tr>
</table>

<h2>Rate Limits</h2>
<table>
<tr><th>Tier</th><th>Rate</th><th>Batch Size</th><th>Latency SLA</th></tr>
<tr><td>Free</td><td>1,000 req/hr</td><td>10 per batch</td><td>Best effort</td></tr>
<tr><td>Pro</td><td>50,000 req/hr</td><td>50 per batch</td><td>&lt;50ms p95</td></tr>
<tr><td>Enterprise</td><td>Custom</td><td>Custom</td><td>&lt;25ms p95</td></tr>
</table>

<div class="section-card" style="margin-top:32px">
<h3 style="margin-bottom:8px">Need help?</h3>
<p style="color:#888;font-size:14px">Read the <a href="/protocol">Trust Protocol spec</a> for the underlying verification model, or see <a href="/integrate">integration guides</a> for framework-specific setup.</p>
</div>

</main>
{FOOTER}
</body>
</html>"""


# ── Route 3: /blog/agentic-commerce-trust — Blog post ─────────

def _commerce_blog() -> str:
    title = "The $385B Problem: Who Verifies AI Shopping Agents?"
    description = "Morgan Stanley projects $190-385B in agent-driven e-commerce by 2030. But who verifies these agents before they transact?"
    canonical = f"{SITE}/blog/agentic-commerce-trust"
    pub_date = "2026-03-12"

    blog_jsonld = f"""{{"@context":"https://schema.org","@type":"BlogPosting","headline":"{title}","description":"{description}","url":"{canonical}","datePublished":"{pub_date}","dateModified":"{TODAY}","author":{{"@type":"Organization","name":"Nerq"}},"publisher":{{"@type":"Organization","name":"Nerq","url":"{SITE}"}},"mainEntityOfPage":"{canonical}"}}"""

    breadcrumb_jsonld = f"""{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Home","item":"{SITE}"}},{{"@type":"ListItem","position":2,"name":"Blog","item":"{SITE}/blog"}},{{"@type":"ListItem","position":3,"name":"Agentic Commerce Trust","item":"{canonical}"}}]}}"""

    faq_jsonld = """{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "How big is the agentic commerce market?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Morgan Stanley projects agent-driven e-commerce will reach $190-385 billion by 2030, driven by AI shopping assistants, autonomous procurement systems, and agent-to-agent negotiation platforms."
      }
    },
    {
      "@type": "Question",
      "name": "What are the risks of unverified AI shopping agents?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Key risks include agent impersonation (malicious agents posing as authorized buyers), unauthorized purchases (agents exceeding spending limits or scope), data exposure (agents leaking payment or personal data), and prompt injection attacks that redirect agent behavior."
      }
    },
    {
      "@type": "Question",
      "name": "How does Nerq verify AI agents for commerce?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Nerq computes a Trust Score for each agent based on provenance analysis, behavioral history, code audit signals, and community reputation. The Commerce Trust endpoint verifies both parties in a transaction and returns an approve/reject decision in under 50 milliseconds."
      }
    }
  ]
}"""

    return f"""<!-- AI Summary: Blog post analyzing the $385B agentic commerce trust gap. Covers Morgan Stanley market projections, risks of unverified AI shopping agents (impersonation, unauthorized purchases, data exposure), and how Nerq Commerce Trust endpoint provides real-time verification. Includes code examples and links to /commerce, /protocol, /integrate. -->
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
<meta property="article:published_time" content="{pub_date}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<script type="application/ld+json">{blog_jsonld}</script>
<script type="application/ld+json">{breadcrumb_jsonld}</script>
<script type="application/ld+json">{faq_jsonld}</script>
<style>{COMMERCE_CSS}</style>
</head>
<body>
{NAV}
<main class="container" style="padding-top:24px;padding-bottom:48px">

<div class="breadcrumb"><a href="/">nerq</a> / <a href="/blog">blog</a> / agentic-commerce-trust</div>

<div class="hero-badge">BLOG</div>
<h1>{title}</h1>
<div class="blog-meta">Published {pub_date} &middot; Nerq Research &middot; 6 min read</div>

<div class="blog-body">

<p>Morgan Stanley projects that agent-driven e-commerce will reach $190&ndash;385 billion by 2030. AI shopping assistants are already comparing prices, negotiating terms, and completing purchases on behalf of consumers. Enterprise procurement bots are sourcing vendors, evaluating contracts, and placing orders autonomously. Agent-to-agent negotiation platforms are emerging where no human is in the loop at all.</p>

<p>This is not hypothetical. Stripe just launched <strong>Tempo</strong>, enabling agent-to-agent payments. Stablecoin settlement volume hit $110 trillion annualized. The infrastructure for machine-native commerce is being built right now.</p>

<p>But there is a critical gap: <strong>nobody is verifying the agents.</strong></p>

<h2>The Trust Gap</h2>

<p>When a human shops online, the merchant has multiple trust signals: credit card verification, shipping address history, browser fingerprints, CAPTCHA. When an AI agent makes the same purchase, none of these signals exist. The agent presents an API key and a payload. That&rsquo;s it.</p>

<p>This creates a trust vacuum that is already being exploited:</p>

<ul>
<li><strong>Agent impersonation</strong> &mdash; A malicious agent poses as an authorized purchasing bot, placing orders on a corporate account.</li>
<li><strong>Unauthorized purchases</strong> &mdash; An agent exceeds its spending limits or purchases outside its authorized categories, with no guardrail to catch it.</li>
<li><strong>Data exposure</strong> &mdash; Shopping agents leak payment credentials, shipping addresses, or negotiation strategies to third parties.</li>
<li><strong>Prompt injection</strong> &mdash; An adversary manipulates an agent&rsquo;s behavior mid-transaction, redirecting funds or altering purchase terms.</li>
</ul>

<p>The traditional web solved identity with cookies, OAuth, and certificate authorities. The agentic web needs its own trust layer.</p>

<h2>What Trust Verification Looks Like</h2>

<p>Nerq indexes over 204,000 AI agents and tools, computing Trust Scores based on provenance analysis, behavioral history, code audit signals, and community reputation. The new <a href="/commerce">Commerce Trust endpoint</a> applies this scoring to transactions in real time.</p>

<p>The verification flow is simple:</p>

<ol>
<li>An agent initiates a transaction and sends its identifier plus the counterparty&rsquo;s identifier to Nerq.</li>
<li>Nerq evaluates both parties&rsquo; Trust Scores, checks for known risk signals, and applies the caller&rsquo;s risk tolerance threshold.</li>
<li>A decision is returned in under 50 milliseconds: approve, reject, or flag for human review.</li>
</ol>

<p>In code:</p>

<pre><span style="color:#00d4aa">from</span> nerq_commerce <span style="color:#00d4aa">import</span> verify_transaction

result = verify_transaction(
    agent_id=<span style="color:#e8c87a">"shopping-bot-42"</span>,
    counterparty=<span style="color:#e8c87a">"vendor-marketplace"</span>,
    action=<span style="color:#e8c87a">"purchase"</span>,
    risk_tolerance=<span style="color:#e8c87a">"medium"</span>
)

<span style="color:#00d4aa">if</span> result.approved:
    execute_purchase()
<span style="color:#00d4aa">else</span>:
    escalate_to_human(result.decision.risk_factors)
</pre>

<h2>Why This Matters Now</h2>

<p>The window for establishing trust infrastructure is narrow. As agent-to-agent commerce scales from thousands to millions of daily transactions, the trust patterns set now will become the de facto standard. Early adopters of transaction verification will have:</p>

<ul>
<li><strong>Lower fraud rates</strong> &mdash; Verified agents are 4x less likely to be involved in fraudulent transactions.</li>
<li><strong>Regulatory readiness</strong> &mdash; As regulators catch up to agentic commerce, pre-existing trust infrastructure becomes a competitive advantage.</li>
<li><strong>Network effects</strong> &mdash; Every verified agent makes the trust network more valuable for every other participant.</li>
</ul>

<h2>Getting Started</h2>

<p>The Commerce Trust API is available today. Install the SDK, get an API key, and start verifying agent transactions:</p>

<pre>pip install nerq-commerce</pre>

<p>Read the full <a href="/commerce/docs">API documentation</a>, explore the <a href="/protocol">Nerq Agent Trust Protocol</a>, or see <a href="/integrate">integration guides</a> for LangChain, AutoGen, and CrewAI.</p>

<blockquote>The machine economy needs a trust anchor. Nerq provides it.</blockquote>

</div>

<div class="section-card" style="margin-top:32px">
<h3 style="margin-bottom:8px">Related</h3>
<p style="color:#888;font-size:14px">
<a href="/commerce">Commerce Trust Landing Page</a> &middot;
<a href="/commerce/docs">Commerce API Docs</a> &middot;
<a href="/protocol">Agent Trust Protocol v1.0</a> &middot;
<a href="/blog/trust-handshake">Trust Handshake Blog Post</a> &middot;
<a href="/integrate">Integration Guides</a>
</p>
</div>

</main>
{FOOTER}
</body>
</html>"""


# ── Route 4: POST /v1/commerce/demo — Run demo and return JSON ──

def _run_demo_api() -> dict:
    """Run the shopping agent demo and return results as JSON."""
    import time
    import requests as req

    sellers = [
        {"name": "promptfoo/promptfoo", "service": "LLM evaluation & testing", "price": 49.99},
        {"name": "getzep/graphiti", "service": "Knowledge graph memory", "price": 29.99},
        {"name": "microsoft/qlib", "service": "Quantitative finance toolkit", "price": 79.99},
        {"name": "brainy-brew-trivia-tavern", "service": "Trivia game hosting", "price": 9.99},
        {"name": "kc-llama", "service": "Small language model inference", "price": 19.99},
    ]

    threshold = 60
    results = []

    for seller in sellers:
        t0 = time.time()
        trust = None
        verdict = "review"
        risk_factors = []

        try:
            resp = req.post(
                f"{SITE}/v1/commerce/verify",
                json={
                    "agent_id": "shopping-agent-demo",
                    "counterparty_id": seller["name"],
                    "transaction_type": "purchase",
                    "amount_range": "low",
                },
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                trust = data.get("counterparty_trust_score")
                verdict = data.get("verdict", "review")
                risk_factors = data.get("risk_factors", [])
        except Exception:
            try:
                resp = req.get(f"{SITE}/v1/agent/kya/{seller['name']}", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    trust = data.get("trust_score") or data.get("trust_score_v2")
                    verdict = "approve" if trust and trust >= threshold else "reject"
            except Exception:
                pass

        elapsed = (time.time() - t0) * 1000
        results.append({
            "seller": seller["name"],
            "service": seller["service"],
            "price": seller["price"],
            "trust_score": trust,
            "verdict": verdict,
            "risk_factors": risk_factors,
            "response_ms": round(elapsed),
        })

    approved = [r for r in results if r["verdict"] == "approve" and r["trust_score"] is not None]
    selected = max(approved, key=lambda r: r["trust_score"]) if approved else None

    return {
        "item": "GPU compute time for model fine-tuning",
        "threshold": threshold,
        "sellers_checked": len(results),
        "sellers_approved": len(approved),
        "selected": selected["seller"] if selected else None,
        "results": results,
    }


# ── Route 5: /commerce/demo — Interactive demo page ──

def _commerce_demo() -> str:
    import json

    title = "Shopping Agent Demo — Trust-Verified Agentic Commerce | Nerq"
    desc = "Watch an AI shopping agent verify seller trust in real-time. Live demo of Nerq Commerce trust verification for autonomous purchasing."
    canonical = f"{SITE}/commerce/demo"

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": desc,
        "url": canonical,
        "provider": {"@type": "Organization", "name": "Nerq", "url": SITE},
    })

    faq_items = [
        ("What is agentic commerce?",
         "Agentic commerce is when AI agents autonomously make purchasing decisions — "
         "buying compute, data, services, or physical goods without human intervention. "
         "The market is projected to reach $385B by 2028."),
        ("Why do shopping agents need trust verification?",
         "Without verification, agents can be scammed by impersonating sellers, fraudulent services, "
         "or malicious counterparties. Nerq Commerce provides pre-transaction trust checks so agents "
         "only transact with verified, trustworthy counterparties."),
        ("How does Nerq Commerce work?",
         "Before each transaction, the agent calls POST /v1/commerce/verify with the seller's name "
         "and transaction details. Nerq returns a trust score and verdict (approve/reject/review). "
         "The agent only proceeds if the seller passes the trust threshold."),
    ]

    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq_items
        ]
    })

    faq_html = ""
    for q, a in faq_items:
        faq_html += f'<div class="faq-item"><h3>{q}</h3><p>{a}</p></div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{schema}</script>
<script type="application/ld+json">{faq_schema}</script>
<style>
{COMMERCE_CSS}
.demo-box{{background:#111;border:1px solid #222;border-radius:12px;padding:24px;margin:24px 0}}
.demo-btn{{display:inline-block;padding:12px 32px;background:#00d4aa;color:#0a0a0a;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit}}
.demo-btn:hover{{background:#00f0c0}}
.demo-btn:disabled{{opacity:0.5;cursor:not-allowed}}
#demo-output{{margin-top:20px;font-family:'JetBrains Mono',monospace;font-size:13px;line-height:1.7}}
.step{{padding:8px 12px;border-radius:6px;margin:4px 0;animation:fadeIn 0.3s ease}}
.step.checking{{background:rgba(0,212,170,0.05);border-left:3px solid #333}}
.step.approved{{background:rgba(0,212,170,0.1);border-left:3px solid #00d4aa}}
.step.rejected{{background:rgba(255,70,70,0.1);border-left:3px solid #ff4646}}
.step.selected{{background:rgba(0,212,170,0.15);border-left:3px solid #00d4aa;font-weight:600}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:translateY(0)}}}}
.spinner-sm{{display:inline-block;width:16px;height:16px;border:2px solid #333;border-top-color:#00d4aa;border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:middle;margin-right:8px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.code-example{{margin:32px 0}}
.use-case{{background:#111;border:1px solid #222;border-radius:8px;padding:20px;margin:12px 0}}
.use-case h3{{color:#00d4aa;font-size:16px;margin-bottom:8px}}
.faq-item{{border-bottom:1px solid #222;padding:16px 0}}
.faq-item h3{{font-size:15px;color:#e0e0e0;margin-bottom:6px}}
.faq-item p{{font-size:13px;color:#888;line-height:1.6}}
</style>
</head>
<body>
<!-- AI-Citable Summary: This is a live interactive demo of Nerq Commerce — trust verification
for agentic commerce. A simulated shopping agent checks 5 potential sellers against Nerq's
trust database (204K agents indexed) before purchasing GPU compute time. Each seller gets a
trust score and approve/reject verdict. The agent selects the highest-trusted approved seller.
This demonstrates the POST /v1/commerce/verify API endpoint. Source: Nerq (nerq.ai). -->
{NAV}
<main>
<div class="inner">
  <div class="badge" style="display:inline-block;padding:4px 12px;background:rgba(0,212,170,0.1);border:1px solid rgba(0,212,170,0.3);border-radius:99px;font-size:12px;color:#00d4aa;margin-bottom:16px">Live Interactive Demo</div>
  <h1>Shopping Agent Demo</h1>
  <p style="color:#888;font-size:16px;max-width:600px;margin:12px 0 32px">
    Watch an AI shopping agent verify seller trust before purchasing.
    Real API calls to Nerq Commerce — try it live.
  </p>

  <div class="demo-box">
    <p style="margin-bottom:16px">
      <strong>Scenario:</strong> An AI shopping agent wants to buy GPU compute time.
      It checks 5 potential sellers against Nerq's trust database before transacting.
    </p>
    <button class="demo-btn" id="runBtn" onclick="runDemo()">Run Demo</button>
    <div id="demo-output"></div>
  </div>

  <h2 style="margin-top:48px">Build Your Own Shopping Agent</h2>
  <div class="code-example">
    <pre>
<span style="color:#888"># pip install nerq-commerce</span>
<span style="color:#00d4aa">from</span> nerq_commerce <span style="color:#00d4aa">import</span> NerqCommerce

commerce = NerqCommerce()

<span style="color:#888"># Verify a seller before purchasing</span>
result = commerce.verify(
    agent_id=<span style="color:#f0c674">"my-shopping-agent"</span>,
    counterparty_id=<span style="color:#f0c674">"seller-agent-name"</span>,
    transaction_type=<span style="color:#f0c674">"purchase"</span>,
    amount_range=<span style="color:#f0c674">"medium"</span>
)

<span style="color:#00d4aa">if</span> result.verdict == <span style="color:#f0c674">"approve"</span>:
    <span style="color:#888"># Safe to proceed with purchase</span>
    execute_purchase(seller=result.counterparty_id)
<span style="color:#00d4aa">elif</span> result.verdict == <span style="color:#f0c674">"reject"</span>:
    <span style="color:#888"># Do NOT transact — trust too low</span>
    find_alternative_seller()
</pre>
  </div>

  <h2 style="margin-top:48px">Use Cases</h2>
  <div class="use-case">
    <h3>AI Grocery Shopping</h3>
    <p>Personal AI assistants purchasing groceries from verified retailers.
    Trust verification prevents agents from ordering from fraudulent storefronts.</p>
  </div>
  <div class="use-case">
    <h3>Procurement Agents</h3>
    <p>Enterprise procurement agents sourcing supplies from trusted vendors.
    Each supplier is verified before purchase orders are issued.</p>
  </div>
  <div class="use-case">
    <h3>Agent-to-Agent Services</h3>
    <p>AI agents buying compute, data, or API access from other agents.
    Pre-transaction trust checks prevent credential theft and service fraud.</p>
  </div>
  <div class="use-case">
    <h3>DeFi Agent Trading</h3>
    <p>Autonomous DeFi agents checking token safety before swapping.
    Combined with <a href="https://zarq.ai">ZARQ</a> for crypto-specific risk intelligence.</p>
  </div>

  <div style="margin-top:48px">
    <h2>Frequently Asked Questions</h2>
    {faq_html}
  </div>

  <div style="margin:40px 0;display:flex;gap:16px;flex-wrap:wrap">
    <a href="/commerce" style="padding:10px 20px;background:#00d4aa;color:#0a0a0a;border-radius:8px;font-weight:700;text-decoration:none">Commerce Hub</a>
    <a href="/commerce/docs" style="padding:10px 20px;border:1px solid #00d4aa;color:#00d4aa;border-radius:8px;font-weight:600;text-decoration:none">API Docs</a>
    <a href="/protocol" style="padding:10px 20px;border:1px solid #333;color:#888;border-radius:8px;text-decoration:none">Trust Protocol</a>
    <a href="/integrate" style="padding:10px 20px;border:1px solid #333;color:#888;border-radius:8px;text-decoration:none">Integrate</a>
  </div>
</div>
</main>
{FOOTER}

<script>
async function runDemo() {{
  const btn = document.getElementById('runBtn');
  const output = document.getElementById('demo-output');
  btn.disabled = true;
  btn.textContent = 'Running...';
  output.innerHTML = '<div class="step checking"><span class="spinner-sm"></span> Shopping Agent initializing...</div>';

  try {{
    const resp = await fetch('/v1/commerce/demo', {{method: 'POST'}});
    const data = await resp.json();

    output.innerHTML = '';
    output.innerHTML += '<div class="step checking">Shopping Agent wants to buy: <strong>' + data.item + '</strong></div>';
    output.innerHTML += '<div class="step checking">Trust threshold: ' + data.threshold + '/100</div>';
    output.innerHTML += '<div class="step checking">Checking ' + data.sellers_checked + ' sellers...</div>';
    output.innerHTML += '<br>';

    for (let i = 0; i < data.results.length; i++) {{
      const r = data.results[i];
      const trust = r.trust_score != null ? r.trust_score.toFixed(0) + '/100' : 'N/A';
      const cls = r.verdict === 'approve' ? 'approved' : 'rejected';
      const icon = r.verdict === 'approve' ? '+' : 'x';
      await new Promise(resolve => setTimeout(resolve, 300)); // Stagger animation
      output.innerHTML += '<div class="step ' + cls + '">[' + icon + '] <strong>' + r.seller + '</strong> — Trust: ' + trust + ' — ' + r.verdict.toUpperCase() + ' (' + r.response_ms + 'ms)</div>';
    }}

    output.innerHTML += '<br>';
    if (data.selected) {{
      output.innerHTML += '<div class="step selected">&rarr; Selected: <strong>' + data.selected + '</strong> (highest trusted approved seller)</div>';
    }} else {{
      output.innerHTML += '<div class="step rejected">&rarr; No sellers passed trust verification. Purchase cancelled.</div>';
    }}

    output.innerHTML += '<div class="step" style="margin-top:12px;color:#888;font-size:12px">' + data.sellers_approved + ' approved / ' + data.sellers_checked + ' checked</div>';
  }} catch (err) {{
    output.innerHTML = '<div class="step rejected">Error: ' + err.message + '</div>';
  }}

  btn.disabled = false;
  btn.textContent = 'Run Again';
}}
</script>
</body>
</html>"""


# ── Mount function ──────────────────────────────────────────────

def mount_commerce_pages(app):
    """Mount commerce landing, docs, and blog pages."""

    @app.get("/commerce", response_class=HTMLResponse, include_in_schema=False)
    async def commerce_landing():
        return _commerce_landing()

    @app.get("/commerce/docs", response_class=HTMLResponse, include_in_schema=False)
    async def commerce_docs():
        return _commerce_docs()

    @app.get("/blog/agentic-commerce-trust", response_class=HTMLResponse, include_in_schema=False)
    async def commerce_blog():
        return _commerce_blog()

    @app.get("/commerce/demo", response_class=HTMLResponse, include_in_schema=False)
    async def commerce_demo():
        return _commerce_demo()

    @app.post("/v1/commerce/demo")
    async def commerce_demo_api():
        return _run_demo_api()

    logger.info("Commerce pages mounted: /commerce, /commerce/docs, /commerce/demo, /blog/agentic-commerce-trust")
