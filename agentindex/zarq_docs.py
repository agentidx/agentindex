"""
ZARQ API Documentation Page — Public, no auth needed.
Route: /zarq/docs
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router_docs = APIRouter(tags=["docs"])


@router_docs.get("/zarq/docs", response_class=HTMLResponse)
def docs_page():
    return HTMLResponse(_render_docs())


def _render_docs() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZARQ API Documentation — Risk Intelligence for the Machine Economy</title>
<meta name="description" content="ZARQ API docs: trust scores, crash probability, and structural risk for 205 crypto tokens. Free, no API key needed.">
<link rel="canonical" href="https://zarq.ai/zarq/docs">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
    --warm: #c2956b;
    --warm-light: #f5ebe0;
    --bg: #fafaf8;
    --card-bg: #fff;
    --text: #1a1a1a;
    --text-secondary: #6b7280;
    --border: #e5e7eb;
    --green: #059669;
    --red: #dc2626;
    --yellow: #d97706;
    --code-bg: #1e1e2e;
    --code-text: #cdd6f4;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'DM Sans', -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }
.container { max-width: 800px; margin: 0 auto; padding: 0 24px; }
header {
    background: #fff; border-bottom: 1px solid var(--border);
    padding: 24px 0; text-align: center;
}
header h1 {
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 2rem; font-weight: 400;
}
header h1 span { color: var(--warm); }
header p { color: var(--text-secondary); margin-top: 8px; font-size: 1.05rem; }
.badge {
    display: inline-block; background: var(--warm); color: #fff;
    font-size: 0.75rem; font-weight: 600; padding: 3px 12px;
    border-radius: 20px; margin-top: 12px;
}

section { padding: 40px 0; border-bottom: 1px solid var(--border); }
section:last-of-type { border: none; }
h2 {
    font-family: 'DM Serif Display', Georgia, serif;
    font-size: 1.5rem; font-weight: 400; margin-bottom: 16px;
}
h3 { font-size: 1rem; font-weight: 600; margin: 20px 0 8px; color: var(--warm); }

pre {
    background: var(--code-bg); color: var(--code-text);
    padding: 16px 20px; border-radius: 10px; overflow-x: auto;
    font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
    line-height: 1.5; margin: 12px 0;
}
code {
    font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
    background: #f3f4f6; padding: 2px 6px; border-radius: 4px;
}
pre code { background: none; padding: 0; }
.comment { color: #6c7086; }
.string { color: #a6e3a1; }
.keyword { color: #cba6f7; }
.url { color: #89b4fa; }

table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.9rem; }
table th { text-align: left; color: var(--text-secondary); font-weight: 500; padding: 10px 12px; border-bottom: 2px solid var(--border); }
table td { padding: 10px 12px; border-bottom: 1px solid #f3f4f6; }
table td:first-child { font-family: 'JetBrains Mono', monospace; font-weight: 500; }

.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin: 12px 0; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
.pill-green { background: #d1fae5; color: var(--green); }
.pill-yellow { background: #fef3c7; color: var(--yellow); }
.pill-red { background: #fee2e2; color: var(--red); }

.method { display: inline-block; background: var(--green); color: #fff; padding: 2px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; font-weight: 600; margin-right: 8px; }
.endpoint { font-family: 'JetBrains Mono', monospace; font-size: 0.95rem; }

footer { background: var(--warm-light); padding: 32px 0; text-align: center; font-size: 0.9rem; color: var(--text-secondary); }
footer a { color: var(--warm); text-decoration: none; font-weight: 600; }

a { color: var(--warm); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 600px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
</head>
<body>

<header>
    <div class="container">
        <h1><span>ZARQ</span> API Documentation</h1>
        <p>Risk intelligence for the machine economy</p>
        <span class="badge">Free &bull; No API Key &bull; 205 Tokens</span>
    </div>
</header>

<div class="container">

<section>
<h2>What is ZARQ?</h2>
<p>ZARQ is the trust layer for autonomous financial decisions. AI agents making crypto trades, swaps, or lending decisions need independent risk assessment. ZARQ provides that: Moody's-style trust ratings (Aaa&ndash;D), distance-to-default scoring, structural collapse detection, and crash probability for 205 digital assets. Every rating is hash-chained for tamper evidence.</p>

<div class="grid-2" style="margin-top:16px">
<div class="card">
    <strong>Track Record</strong><br>
    <span style="font-family:JetBrains Mono,monospace;font-size:1.2rem;color:var(--green)">100%</span> recall on 113 structural collapses<br>
    <span style="font-family:JetBrains Mono,monospace;font-size:1.2rem">98%</span> precision (22 months OOS)
</div>
<div class="card">
    <strong>Coverage</strong><br>
    <span style="font-family:JetBrains Mono,monospace;font-size:1.2rem;color:var(--warm)">205</span> tokens rated<br>
    <span style="font-family:JetBrains Mono,monospace;font-size:1.2rem">50</span> verified crash saves
</div>
</div>
</section>

<section>
<h2>Quick Start</h2>
<p>One HTTP call. No auth. No signup.</p>
<pre><code><span class="comment"># Check any token's risk</span>
curl <span class="url">https://zarq.ai/v1/check/bitcoin</span></code></pre>

<h3>Response</h3>
<pre><code>{
  <span class="string">"token"</span>: <span class="string">"bitcoin"</span>,
  <span class="string">"verdict"</span>: <span class="string">"SAFE"</span>,
  <span class="string">"trust_score"</span>: 74.52,
  <span class="string">"rating"</span>: <span class="string">"A2"</span>,
  <span class="string">"distance_to_default"</span>: 3.06,
  <span class="string">"structural_weakness"</span>: false,
  <span class="string">"crash_probability"</span>: 0.3177,
  <span class="string">"price_usd"</span>: 70825.0,
  <span class="string">"checked_at"</span>: <span class="string">"2026-03-08T..."</span>
}</code></pre>

<h3>Verdict Values</h3>
<table>
<tr><th>Verdict</th><th>Meaning</th><th>Action</th></tr>
<tr><td><span class="pill pill-green">SAFE</span></td><td>No structural issues</td><td>Proceed normally</td></tr>
<tr><td><span class="pill pill-yellow">WARNING</span></td><td>Elevated risk</td><td>Reduce position size</td></tr>
<tr><td><span class="pill pill-red">CRITICAL</span></td><td>Structural collapse detected</td><td>Do not trade</td></tr>
</table>
</section>

<section>
<h2>API Endpoints</h2>

<h3>Zero-Friction Check (Recommended)</h3>
<p><span class="method">GET</span> <span class="endpoint">/v1/check/{token}</span></p>
<p>Single-call risk verdict. Use CoinGecko-style token IDs (e.g. <code>bitcoin</code>, <code>ethereum</code>, <code>solana</code>).</p>

<h3>Ratings &amp; Risk</h3>
<table>
<tr><th>Endpoint</th><th>Description</th></tr>
<tr><td><code>GET /v1/crypto/ratings</code></td><td>All token ratings</td></tr>
<tr><td><code>GET /v1/crypto/rating/{token}</code></td><td>Single token rating + pillars</td></tr>
<tr><td><code>GET /v1/crypto/ndd/{token}</code></td><td>Distance-to-default time series</td></tr>
<tr><td><code>GET /v1/crypto/signals</code></td><td>Active WARNING/CRITICAL signals</td></tr>
<tr><td><code>GET /v1/crypto/early-warning</code></td><td>Active risk alerts</td></tr>
<tr><td><code>GET /v1/crypto/safety/{token}</code></td><td>Lightweight pre-trade check (&lt;100ms)</td></tr>
<tr><td><code>GET /v1/crypto/distress-watch</code></td><td>Tokens with DtD &lt; 2.0</td></tr>
<tr><td><code>GET /v1/crypto/compare/{t1}/{t2}</code></td><td>Side-by-side comparison</td></tr>
</table>

<h3>Stress Test &amp; Contagion</h3>
<table>
<tr><th>Endpoint</th><th>Description</th></tr>
<tr><td><code>POST /v1/crypto/stresstest</code></td><td>Portfolio stress test</td></tr>
<tr><td><code>GET /v1/crypto/contagion/{token}</code></td><td>Contagion exposure</td></tr>
<tr><td><code>GET /v1/crypto/transition-matrix/{level}</code></td><td>Rating transition probabilities</td></tr>
</table>

<h3>Crash Shield</h3>
<table>
<tr><th>Endpoint</th><th>Description</th></tr>
<tr><td><code>GET /v1/crash-shield/saves</code></td><td>All verified crash saves</td></tr>
<tr><td><code>POST /v1/crash-shield/subscribe</code></td><td>Webhook for crash alerts</td></tr>
</table>

<h3>Paper Trading</h3>
<table>
<tr><th>Endpoint</th><th>Description</th></tr>
<tr><td><code>GET /v1/crypto/paper-trading/nav/{portfolio}</code></td><td>NAV history (ALPHA, DYNAMIC, CONSERVATIVE)</td></tr>
<tr><td><code>GET /v1/crypto/paper-trading/positions/{portfolio}</code></td><td>Current positions</td></tr>
<tr><td><code>GET /v1/crypto/paper-trading/audit</code></td><td>SHA-256 audit trail</td></tr>
</table>

<h3>KYA — Know Your Agent</h3>
<table>
<tr><th>Endpoint</th><th>Description</th></tr>
<tr><td><code>GET /v1/agent/kya/{name_or_id}</code></td><td>Agent due diligence (trust, compliance, risk level)</td></tr>
<tr><td><code>GET /kya/{name}</code></td><td>KYA report page (HTML, shareable)</td></tr>
</table>
<p>204K agents & tools indexed. Returns trust score, compliance score, risk level (TRUSTED/CAUTION/UNTRUSTED), and verdict.</p>

<h3>The ZARQ Signal — Risk Feed</h3>
<table>
<tr><th>Endpoint</th><th>Description</th></tr>
<tr><td><code>GET /v1/signal/feed</code></td><td>Live risk feed — all 205 tokens sorted by severity</td></tr>
<tr><td><code>GET /v1/signal/feed/history?days=30</code></td><td>Daily snapshots of signal counts</td></tr>
<tr><td><code>POST /v1/signal/subscribe</code></td><td>Register for notifications (coming soon)</td></tr>
<tr><td><code>GET /signal</code></td><td>Signal dashboard page (HTML, auto-refreshing)</td></tr>
</table>

<h3>Bulk Data</h3>
<p><span class="method">GET</span> <span class="endpoint">/data/crypto-trust-scores.jsonl.gz</span></p>
<p>All ratings in JSONL format. CC BY 4.0 license.</p>
</section>

<section>
<h2>Rate Limits</h2>
<table>
<tr><th>Tier</th><th>Calls/Day</th><th>Response</th></tr>
<tr><td>Open</td><td>0&ndash;500</td><td>Full response</td></tr>
<tr><td>Signal</td><td>500&ndash;2,000</td><td>Full response + usage headers</td></tr>
<tr><td>Degraded</td><td>2,000&ndash;5,000</td><td>Crash probability and DtD redacted</td></tr>
<tr><td>Blocked</td><td>5,000+</td><td>HTTP 402 — upgrade required</td></tr>
</table>
<p>Need unlimited access? Contact <a href="mailto:hello@zarq.ai">hello@zarq.ai</a> for Pro ($49/mo) or Enterprise plans.</p>
</section>

<section>
<h2>Integrations</h2>
<p>Add risk intelligence to your agent in 1&ndash;2 lines.</p>

<h3>LangChain / LangGraph</h3>
<pre><code><span class="keyword">from</span> zarq_langchain <span class="keyword">import</span> ZARQRiskCheck
tools = [ZARQRiskCheck()]
<span class="comment"># Your agent now checks token risk before trading</span></code></pre>
<p><code>pip install zarq-langchain</code></p>

<h3>ElizaOS</h3>
<pre><code><span class="keyword">import</span> zarqPlugin <span class="keyword">from</span> <span class="string">"@zarq/elizaos-plugin"</span>;
plugins: [zarqPlugin]
<span class="comment">// Agent auto-checks risk on crypto questions</span></code></pre>
<p><code>npm install @zarq/elizaos-plugin</code></p>

<h3>Solana Agent Kit</h3>
<pre><code><span class="keyword">from</span> zarq_tool <span class="keyword">import</span> check_token_risk
risk = check_token_risk(<span class="string">"SOL"</span>)  <span class="comment"># or mint address</span></code></pre>

<h3>MCP (Claude Desktop, Cursor, Windsurf)</h3>
<pre><code>{
  <span class="string">"mcpServers"</span>: {
    <span class="string">"zarq"</span>: { <span class="string">"url"</span>: <span class="string">"https://mcp.zarq.ai/sse"</span> }
  }
}</code></pre>

<h3>Any Language (Raw HTTP)</h3>
<pre><code><span class="comment"># Python</span>
<span class="keyword">import</span> httpx
r = httpx.get(<span class="string">"https://zarq.ai/v1/check/bitcoin"</span>)
data = r.json()

<span class="comment"># JavaScript</span>
<span class="keyword">const</span> r = <span class="keyword">await</span> fetch(<span class="string">"https://zarq.ai/v1/check/bitcoin"</span>);
<span class="keyword">const</span> data = <span class="keyword">await</span> r.json();

<span class="comment"># curl</span>
curl https://zarq.ai/v1/check/bitcoin</code></pre>
</section>

<section>
<h2>Rating Scale</h2>
<table>
<tr><th>Grade</th><th>Score Range</th><th>Category</th></tr>
<tr><td>Aaa</td><td>95&ndash;100</td><td rowspan="4">Investment Grade</td></tr>
<tr><td>Aa1&ndash;Aa3</td><td>85&ndash;94</td></tr>
<tr><td>A1&ndash;A3</td><td>70&ndash;84</td></tr>
<tr><td>Baa1&ndash;Baa3</td><td>60&ndash;69</td></tr>
<tr><td>Ba1&ndash;Ba3</td><td>50&ndash;59</td><td rowspan="4">Speculative Grade</td></tr>
<tr><td>B1&ndash;B3</td><td>40&ndash;49</td></tr>
<tr><td>Caa&ndash;C</td><td>20&ndash;39</td></tr>
<tr><td>D</td><td>0&ndash;19</td></tr>
</table>
</section>

<section>
<h2>More Resources</h2>
<div class="grid-2">
<a href="/demo/save-simulator" class="card" style="text-decoration:none;color:inherit">
    <strong>Save Simulator</strong><br>
    <span style="color:var(--text-secondary)">See the 50 biggest crashes ZARQ caught early</span>
</a>
<a href="/crypto/alerts" class="card" style="text-decoration:none;color:inherit">
    <strong>Live Alerts</strong><br>
    <span style="color:var(--text-secondary)">Current structural warnings</span>
</a>
<a href="/risk-scanner" class="card" style="text-decoration:none;color:inherit">
    <strong>Risk Scanner</strong><br>
    <span style="color:var(--text-secondary)">Interactive portfolio risk check</span>
</a>
<a href="/paper-trading" class="card" style="text-decoration:none;color:inherit">
    <strong>Paper Trading</strong><br>
    <span style="color:var(--text-secondary)">Live trading with hash-chained audit</span>
</a>
</div>
</section>

</div>

<footer>
    <div class="container">
        <strong><a href="https://zarq.ai">ZARQ</a></strong> &mdash; Trust Layer for the Machine Economy<br>
        <a href="https://zarq.ai/whitepaper">White Paper</a> &bull;
        <a href="https://zarq.ai/methodology">Methodology</a> &bull;
        <a href="https://zarq.ai/track-record">Track Record</a> &bull;
        <a href="mailto:hello@zarq.ai">hello@zarq.ai</a>
    </div>
</footer>

</body>
</html>"""
