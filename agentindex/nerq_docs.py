"""
Nerq API Documentation Page — Sprint N0
Route: /nerq/docs
Swiss minimalism design.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from agentindex.nerq_design import nerq_page

router_nerq_docs = APIRouter(tags=["nerq-docs"])


@router_nerq_docs.get("/nerq/docs", response_class=HTMLResponse)
def nerq_docs_page():
    return HTMLResponse(_render_nerq_docs())


def _render_nerq_docs() -> str:
    body = """
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebAPI","name":"Nerq API","description":"REST API for searching, benchmarking, and assessing 5M+ AI assets.","documentation":"https://nerq.ai/nerq/docs","url":"https://nerq.ai/v1","provider":{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}}
</script>
<h1>nerq api</h1>
<p class="desc">5M+ AI assets indexed. Free, no auth. All responses JSON.</p>

<p style="font-size:13px;color:#6b7280;margin:12px 0">
<a href="#quickstart">quick start</a> &middot;
<a href="#kya">kya</a> &middot;
<a href="#weekly">weekly</a> &middot;
<a href="#verified">verified</a> &middot;
<a href="#benchmark">benchmark</a> &middot;
<a href="#search">search</a> &middot;
<a href="#stats">stats</a> &middot;
<a href="#discover">discover</a> &middot;
<a href="#badges">badges</a> &middot;
<a href="#mcp">mcp</a>
</p>

<h2 id="sdk">SDK</h2>
<pre>pip install nerq</pre>
<pre>from nerq import NerqClient
client = NerqClient()
r = client.preflight("langchain")
print(r.trust_score, r.recommendation)  # 82.4 PROCEED</pre>
<p class="desc"><a href="https://pypi.org/project/nerq/">PyPI</a> &middot; <a href="https://nerq.ai/docs">Swagger UI</a></p>

<h2 id="quickstart">Quick Start</h2>
<pre>
# ecosystem stats
curl https://nerq.ai/v1/agent/stats

# search for coding agents
curl "https://nerq.ai/v1/agent/search?q=code+review&amp;min_trust=50"

# benchmark a category
curl https://nerq.ai/v1/agent/benchmark/coding

# KYA &mdash; Know Your Agent
curl https://nerq.ai/v1/agent/kya/langchain
</pre>

<h2 id="kya">KYA &mdash; Know Your Agent</h2>
<p class="desc">Public due diligence. Trust score, compliance, risk level, verdict.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/kya/{name_or_uuid}</span></p>
<pre>curl https://nerq.ai/v1/agent/kya/langchain</pre>
<pre>{
  "agent_name": "langchain",
  "trust_score": 72.3,
  "compliance_score": 65.0,
  "risk_level": "TRUSTED",
  "eu_risk_class": "limited",
  "days_active": 180,
  "stars": 12500,
  "verdict": "Indexed 180 days, trust 72/100 [TRUSTED]."
}</pre>

<p><span class="method method-get">GET</span> <span class="ep">/kya</span></p>
<p class="desc">Interactive search page: <a href="/kya">nerq.ai/kya</a></p>

<h2 id="weekly">Weekly Signal</h2>
<p class="desc">Ecosystem snapshot: top agents, trust changes, framework adoption, categories.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/weekly</span></p>
<pre>curl https://nerq.ai/v1/agent/weekly</pre>
<pre>{
  "week_of": "2026-03-09",
  "new_indexed_count": 2399,
  "active_this_week": 4252,
  "ecosystem": {"total_agents": 66096, "total_tools": 60101, "total_mcp": 17468, "avg_trust_score": 67.3},
  "top_agents": [...],
  "agent_of_the_week": {"name": "...", "trust_score": 92.9, "grade": "A+"},
  "trust_changes": [...],
  "trending_frameworks": [...],
  "top_categories": [...]
}</pre>

<p><span class="method method-get">GET</span> <span class="ep">/weekly</span></p>
<p class="desc">HTML page: <a href="/weekly">nerq.ai/weekly</a></p>

<h2 id="verified">Nerq Verified</h2>
<p class="desc">Agents with trust score &ge; 70. Verified status shown on KYA and agent pages.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/verified</span></p>
<pre>curl https://nerq.ai/v1/agent/verified</pre>
<pre>{
  "verified_count": 18460,
  "threshold": 70,
  "agents": [
    {"name": "...", "trust_score": 92.9, "grade": "A+", "badge_url": "https://nerq.ai/badge/..."},
    ...
  ]
}</pre>

<p><span class="method method-get">GET</span> <span class="ep">/verified</span></p>
<p class="desc">Browse all verified agents: <a href="/verified">nerq.ai/verified</a></p>

<h2 id="benchmark">Benchmark</h2>
<p class="desc">Ranked leaderboards by category. Top 20 by trust score.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/benchmark/categories</span></p>
<pre>curl https://nerq.ai/v1/agent/benchmark/categories</pre>
<pre>[
  {"category": "coding", "count": 10939, "avg_trust_score": 67.7},
  {"category": "security", "count": 1160, "avg_trust_score": 68.5},
  ...
]</pre>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/benchmark/{category}</span></p>
<p class="desc">Response header <code>X-Total-In-Category</code> has the full count.</p>
<pre>curl https://nerq.ai/v1/agent/benchmark/coding</pre>
<pre>[
  {
    "agent_name": "ccmanager",
    "trust_score": 90.9,
    "compliance_score": 87.0,
    "risk_level": "TRUSTED",
    "days_indexed": 28,
    "platform": "github",
    "github_stars": 831
  },
  ...
]</pre>

<h2 id="search">Search</h2>
<p class="desc">Fulltext search across 204K agents, tools, MCP servers.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/search</span></p>

<table class="param-table">
<tr><th>param</th><th>type</th><th>description</th></tr>
<tr><td><code>q</code></td><td>string</td><td>Search query (fulltext on name + description)</td></tr>
<tr><td><code>domain</code></td><td>string</td><td>Filter by domain: coding, security, finance, ...</td></tr>
<tr><td><code>type</code></td><td>string</td><td>Filter: <code>agent</code>, <code>mcp_server</code>, <code>tool</code></td></tr>
<tr><td><code>min_trust</code></td><td>float</td><td>Minimum trust score (0-100)</td></tr>
<tr><td><code>limit</code></td><td>int</td><td>Results per page (1-100, default 20)</td></tr>
<tr><td><code>offset</code></td><td>int</td><td>Pagination offset</td></tr>
</table>

<pre>curl "https://nerq.ai/v1/agent/search?q=code+review&amp;type=agent&amp;min_trust=50&amp;limit=5"</pre>
<pre>{
  "results": [
    {"name": "code-review-agent", "agent_type": "agent",
     "trust_score": 71.5, "category": "coding"},
    ...
  ],
  "total": 142,
  "limit": 5,
  "offset": 0
}</pre>

<h2 id="stats">Stats</h2>
<p class="desc">Ecosystem breakdown. Cached 1 hour.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/stats</span></p>
<pre>curl https://nerq.ai/v1/agent/stats</pre>
<pre>{
  "total_assets": 4919340,
  "total_agents": 66096,
  "total_tools": 60101,
  "total_mcp_servers": 17468,
  "total_models": 2559184,
  "total_datasets": 795193,
  "categories": {"coding": 10939, "security": 1160, ...},
  "frameworks": {"langchain": 8500, ...},
  "trust_distribution": {"TRUSTED": 135048, "CAUTION": 8617, "UNTRUSTED": 0},
  "average_trust_score": 65.2
}</pre>

<h2 id="discover">Semantic Discovery</h2>
<p class="desc">Natural language search via FAISS + sentence-transformers.</p>

<p><span class="method method-post">POST</span> <span class="ep">/v1/discover</span></p>
<pre>curl -X POST https://nerq.ai/v1/discover \\
  -H "Content-Type: application/json" \\
  -d '{"need": "agent that reviews smart contracts"}'</pre>
<pre>{
  "results": [...],
  "total_matching": 15,
  "index_size": 4919340,
  "protocol": "agentindex/v1"
}</pre>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/{uuid}</span></p>
<p class="desc">Agent detail by UUID.</p>

<h2 id="preflight">Preflight Trust Check</h2>
<p class="desc">Pre-interaction trust verification for agent-to-agent communication. Check if an agent is trusted before delegating tasks or accepting requests.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/preflight?target={name}&amp;caller={name}</span></p>

<table class="param-table">
<tr><th>param</th><th>type</th><th>description</th></tr>
<tr><td><code>target</code></td><td>string</td><td>Required. Agent name to check.</td></tr>
<tr><td><code>caller</code></td><td>string</td><td>Optional. Calling agent name for interaction risk.</td></tr>
</table>

<pre>curl "https://nerq.ai/v1/preflight?target=SWE-agent&amp;caller=my-agent"</pre>

<pre>{
  "target": "SWE-agent",
  "target_trust": 92.5,
  "target_grade": "A+",
  "target_verified": true,
  "target_category": "security",
  "interaction_risk": "LOW",
  "recommendation": "PROCEED",
  "compliance_flags": []
}</pre>

<p class="desc"><strong>Recommendation values:</strong> <code>PROCEED</code> (target &ge; 70, caller &ge; 40) &middot;
<code>CAUTION</code> (target 40&ndash;69 or caller &lt; 40) &middot;
<code>DENY</code> (target &lt; 40) &middot;
<code>UNKNOWN</code> (target not found).
Cached 5 min per caller+target pair.</p>

<pre># Python (requests)
import requests
r = requests.get("https://nerq.ai/v1/preflight",
    params={"target": "SWE-agent", "caller": "my-bot"})
check = r.json()
if check["recommendation"] == "PROCEED":
    # safe to interact
    pass</pre>

<pre># Python (nerq SDK) — pip install nerq
from nerq import NerqClient
client = NerqClient()
r = client.preflight("SWE-agent")
if r.is_safe():
    print(f"Trusted: {r.trust_score} ({r.trust_grade})")</pre>

<pre># JavaScript (fetch)
const res = await fetch("https://nerq.ai/v1/preflight?target=SWE-agent&amp;caller=my-bot");
const check = await res.json();
if (check.recommendation === "PROCEED") {
  // safe to interact
}</pre>

<h3>Batch Preflight (up to 50 agents)</h3>
<p><span class="method method-post">POST</span> <span class="ep">/v1/preflight/batch</span></p>

<pre>curl -X POST https://nerq.ai/v1/preflight/batch \\
  -H "Content-Type: application/json" \\
  -d '{"targets": ["langchain", "crewai", "autogen"]}'</pre>

<pre># Python (nerq SDK)
batch = client.preflight_batch(["langchain", "crewai", "autogen"])
for name, r in batch.items():
    print(f"{name}: {r.trust_grade} ({r.recommendation})")
print("Not found:", batch.not_found)</pre>

<pre>// JavaScript
const res = await fetch("https://nerq.ai/v1/preflight/batch", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({targets: ["langchain", "crewai", "autogen"]})
});
const {results, not_found} = await res.json();</pre>

<h3>Commerce Trust Verification</h3>
<p><span class="method method-post">POST</span> <span class="ep">/v1/commerce/verify</span></p>
<p class="desc">Verify trust before agent-to-agent transactions. Returns approve/review/reject.</p>

<pre>curl -X POST https://nerq.ai/v1/commerce/verify \\
  -H "Content-Type: application/json" \\
  -d '{"agent_id": "buyer-agent", "counterparty_id": "seller-agent", "transaction_type": "payment", "amount_range": "high"}'</pre>

<pre># Python (nerq SDK)
v = client.commerce_verify("buyer-agent", "seller-agent", "payment", "high")
if v.is_approved():
    proceed_with_transaction()</pre>

<pre>// JavaScript
const res = await fetch("https://nerq.ai/v1/commerce/verify", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    agent_id: "buyer-agent",
    counterparty_id: "seller-agent",
    transaction_type: "payment",
    amount_range: "high"
  })
});
const verdict = await res.json();
if (verdict.verdict === "approve") { /* proceed */ }</pre>

<h2 id="reviews">Reviews</h2>
<p class="desc">Report tool usage outcomes. Reviews influence trust scores over time.</p>

<p><span class="method method-post">POST</span> <span class="ep">/v1/agent/review</span></p>
<pre>curl -X POST https://nerq.ai/v1/agent/review \
  -H "Content-Type: application/json" \
  -d '{"reviewer": "my-agent", "target": "SWE-agent", "outcome": "success", "latency_ms": 230}'</pre>
<pre>{
  "recorded": true,
  "target": "SWE-agent",
  "target_trust_before": 92.5,
  "review_bonus": 0.3,
  "total_reviews": 47,
  "success_rate": 0.94
}</pre>

<table class="param-table">
<tr><th>field</th><th>type</th><th>description</th></tr>
<tr><td><code>reviewer</code></td><td>string</td><td>Required. Who is reviewing.</td></tr>
<tr><td><code>target</code></td><td>string</td><td>Required. Agent being reviewed.</td></tr>
<tr><td><code>outcome</code></td><td>string</td><td>Required. <code>success</code>, <code>failure</code>, or <code>partial</code>.</td></tr>
<tr><td><code>latency_ms</code></td><td>integer</td><td>Optional. Response time observed.</td></tr>
<tr><td><code>notes</code></td><td>string</td><td>Optional. Free text (max 500 chars).</td></tr>
</table>
<p class="desc">Rate limit: 100 reviews/day per IP. Zero auth.</p>

<h2 id="reputation">Reputation</h2>
<p class="desc">Combined static trust + community review signal.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/reputation/{name}</span></p>
<pre>curl https://nerq.ai/v1/agent/reputation/SWE-agent</pre>
<pre>{
  "name": "SWE-agent/SWE-agent",
  "trust_score": 92.8,
  "static_trust": 92.5,
  "review_bonus": 0.3,
  "total_reviews": 47,
  "success_rate": 0.94,
  "days_active": 180,
  "verified": true,
  "rank_in_category": 3,
  "category": "security",
  "badge_url": "https://nerq.ai/badge/SWE-agent"
}</pre>

<h2 id="ledger">Interaction Ledger</h2>
<p class="desc">Interaction history for an agent.</p>

<p><span class="method method-get">GET</span> <span class="ep">/v1/agent/ledger/{name}?days=30</span></p>
<pre>curl "https://nerq.ai/v1/agent/ledger/SWE-agent?days=30"</pre>
<pre>{
  "name": "SWE-agent",
  "period_days": 30,
  "reviews_received": 12,
  "reviews_given": 3,
  "success_rate": 0.92,
  "trust_score": 92.8,
  "trust_trend": "stable",
  "recent_interactions": [...]
}</pre>

<h2 id="badges">Badges</h2>
<p class="desc">Embeddable SVG trust badges for README files. <a href="/badges">Showcase &amp; examples</a></p>

<p><span class="method method-get">GET</span> <span class="ep">/badge/{name}</span></p>
<p class="desc">Returns an SVG trust badge for the agent. Embed in any README.</p>
<pre>![Nerq Trust](https://nerq.ai/badge/YOUR_AGENT)</pre>

<table class="param-table">
<tr><th>endpoint</th><th>description</th></tr>
<tr><td><code>/badge/{name}</code></td><td>Lookup by agent name</td></tr>
<tr><td><code>/badge/npm/{package}</code></td><td>Lookup by npm package</td></tr>
<tr><td><code>/badge/pypi/{package}</code></td><td>Lookup by PyPI package</td></tr>
</table>

<pre># Markdown
[![Nerq Trust](https://nerq.ai/badge/AGENT_NAME)](https://nerq.ai/kya/AGENT_NAME)

# HTML
&lt;a href="https://nerq.ai/kya/AGENT_NAME"&gt;&lt;img src="https://nerq.ai/badge/AGENT_NAME" alt="Nerq Trust"&gt;&lt;/a&gt;</pre>

<p class="desc">Returns <code>image/svg+xml</code>, cached 1 hour, CORS enabled. Shows &ldquo;unknown&rdquo; if agent not found.</p>

<h2 id="mcp">MCP</h2>
<p class="desc">Nerq as an MCP server for Claude, ChatGPT, other LLM clients.</p>

<table>
<tr><th>tool</th><th>description</th></tr>
<tr><td><code>discover_agents</code></td><td>Find agents by natural language need</td></tr>
<tr><td><code>find_best_agent</code></td><td>Top 5 in category above min trust</td></tr>
<tr><td><code>agent_benchmark</code></td><td>Benchmark leaderboard for a category</td></tr>
<tr><td><code>get_agent_stats</code></td><td>Ecosystem statistics</td></tr>
<tr><td><code>kya_check_agent</code></td><td>Know Your Agent due diligence</td></tr>
<tr><td><code>preflight_trust_check</code></td><td>Pre-interaction trust verification</td></tr>
</table>

<pre># SSE endpoint
https://nerq.ai/mcp/sse

# server card
https://nerq.ai/.well-known/mcp/server-card.json</pre>

<h2 id="reports">Reports</h2>
<p class="desc">Research and analysis from the Nerq index.</p>
<table>
<tr><th>report</th><th>date</th></tr>
<tr><td><a href="/report/q1-2026">State of AI Assets &mdash; Q1 2026</a></td><td>2026-03-09</td></tr>
<tr><td><a href="/report/best-coding-agents-2026">Best AI Coding Agents 2026</a></td><td>2026-03-09</td></tr>
<tr><td><a href="/report/best-devops-agents-2026">Best AI DevOps Agents 2026</a></td><td>2026-03-09</td></tr>
<tr><td><a href="/report/best-security-agents-2026">Best AI Security Agents 2026</a></td><td>2026-03-09</td></tr>
<tr><td><a href="/report/best-communication-agents-2026">Best AI Communication Agents 2026</a></td><td>2026-03-09</td></tr>
<tr><td><a href="/report/best-content-agents-2026">Best AI Content Creation Agents 2026</a></td><td>2026-03-09</td></tr>
<tr><td><a href="/report/benchmark">With Nerq vs Without Nerq &mdash; Benchmark</a></td><td>2026-03-10</td></tr>
</table>

<p style="margin-top:24px;padding:12px;border:1px solid #e5e7eb;font-size:14px">
Crypto risk intelligence (Trust Scores, crash prediction, NDD): <a href="https://zarq.ai/zarq/docs">zarq.ai/zarq/docs</a>
</p>
"""
    return nerq_page(
        "nerq api docs",
        body,
        description="Nerq API: search, benchmark, assess 5M+ AI assets. Free, no auth.",
        canonical="https://nerq.ai/nerq/docs",
    )
