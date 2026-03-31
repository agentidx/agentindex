"""
Developer onboarding page — /start
Interactive guide to get started with Nerq/ZARQ APIs in 30 seconds.
Rebuilt with live preflight demo, formatted response, SDK install, testimonials, badge CTA.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router_start = APIRouter()


def _nerq_start() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Get Started — Nerq API in 30 Seconds</title>
<meta name="description" content="Check any AI agent's trust score in one API call. Free, no auth. Try it live, install the Python SDK, embed trust badges.">
<link rel="canonical" href="https://nerq.ai/start">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;color:#1a1a1a;background:#fff;line-height:1.6;font-size:15px}
a{color:#0d9488;text-decoration:none}a:hover{color:#0f766e}
code,pre{font-family:ui-monospace,'SF Mono','JetBrains Mono',monospace}
code{background:#f5f5f5;padding:1px 5px;font-size:0.9em}
pre{background:#1a1a1a;color:#e5e7eb;padding:16px;overflow-x:auto;font-size:13px;line-height:1.5;position:relative}
nav{border-bottom:1px solid #e5e7eb;padding:12px 0}
nav .inner{max-width:760px;margin:0 auto;padding:0 20px;display:flex;align-items:center;justify-content:space-between}
nav .logo{font-weight:700;font-size:1.1rem;color:#0d9488;text-decoration:none}
nav .links{display:flex;gap:20px;font-size:14px}
nav .links a{color:#6b7280}nav .links a:hover{color:#0d9488;text-decoration:none}
.container{max-width:760px;margin:0 auto;padding:40px 20px}
h1{font-size:2rem;font-weight:800;margin-bottom:6px;letter-spacing:-0.02em}
h2{font-size:1.15rem;font-weight:700;margin:36px 0 12px;display:flex;align-items:center;gap:8px}
.step-num{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;background:#0d9488;color:#fff;font-size:13px;font-weight:700;border-radius:50%;flex-shrink:0}
.subtitle{color:#6b7280;font-size:15px;margin-bottom:32px;line-height:1.7}

/* Try it section */
.try-section{border:2px solid #0d9488;padding:20px;margin:16px 0;background:#f0fdfa}
.try-row{display:flex;gap:8px}
.try-row input{flex:1;padding:10px 14px;border:1px solid #d1d5db;font-size:14px;font-family:ui-monospace,monospace;outline:none;background:#fff}
.try-row input:focus{border-color:#0d9488;box-shadow:0 0 0 2px rgba(13,148,136,0.15)}
.try-row button{padding:10px 24px;background:#0d9488;color:#fff;border:none;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap}
.try-row button:hover{background:#0f766e}
.try-row button:disabled{opacity:0.6;cursor:not-allowed}
#try-result{margin-top:16px;display:none}

/* Result card */
.result-card{background:#fff;border:1px solid #e5e7eb;padding:20px}
.result-header{display:flex;align-items:center;gap:16px;margin-bottom:16px}
.result-score{font-family:ui-monospace,monospace;font-size:3rem;font-weight:700;line-height:1}
.result-score.green{color:#059669}.result-score.yellow{color:#d97706}.result-score.red{color:#dc2626}
.result-meta{flex:1}
.result-name{font-weight:700;font-size:1.1rem}
.result-grade{display:inline-block;padding:2px 8px;font-size:12px;font-weight:700;color:#fff;margin-left:6px}
.result-grade.A{background:#059669}.result-grade.B{background:#0d9488}.result-grade.C{background:#d97706}.result-grade.D{background:#dc2626}.result-grade.F{background:#7f1d1d}
.result-sub{font-size:13px;color:#6b7280;margin-top:2px}
.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.result-cell{background:#f9fafb;padding:10px;border:1px solid #f3f4f6}
.result-cell .label{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em}
.result-cell .value{font-family:ui-monospace,monospace;font-size:1rem;font-weight:600;margin-top:2px}
.result-rec{margin-top:12px;padding:10px 14px;font-size:13px;font-weight:600;border-left:3px solid}
.result-rec.ALLOW{background:#ecfdf5;color:#065f46;border-color:#059669}
.result-rec.WARN{background:#fffbeb;color:#92400e;border-color:#d97706}
.result-rec.DENY{background:#fef2f2;color:#991b1b;border-color:#dc2626}
.result-curl{margin-top:12px;font-size:12px;color:#6b7280}

/* Install */
.install-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}
.install-block{border:1px solid #e5e7eb;padding:16px;position:relative}
.install-block .lang{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;font-weight:600}
.install-block pre{font-size:12px;margin:0;background:#f9fafb;color:#1a1a1a;padding:10px;border:1px solid #f3f4f6}
.install-block .copy-btn{position:absolute;top:8px;right:8px;background:#f3f4f6;border:1px solid #e5e7eb;color:#6b7280;font-size:10px;padding:2px 6px;cursor:pointer}

/* Testimonials */
.social-proof{background:#f9fafb;border:1px solid #e5e7eb;padding:20px;margin:16px 0}
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;text-align:center}
.stat-num{font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488}
.stat-label{font-size:12px;color:#6b7280;margin-top:2px}

/* Badge CTA */
.badge-cta{border:2px solid #e5e7eb;padding:24px;margin:20px 0;text-align:center}
.badge-cta h3{font-size:1rem;margin-bottom:8px}
.badge-cta .badge-demo{margin:12px auto;display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap}
.badge-cta pre{text-align:left;font-size:11px;margin:12px auto;max-width:520px;user-select:all;cursor:pointer}

/* CTA */
.cta-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:20px 0}
.cta-card{border:1px solid #e5e7eb;padding:16px;text-align:center;text-decoration:none;color:inherit;transition:border-color 0.2s}
.cta-card:hover{border-color:#0d9488;text-decoration:none}
.cta-card .cta-title{font-weight:700;font-size:14px;margin-bottom:4px;color:#0d9488}
.cta-card .cta-desc{font-size:12px;color:#6b7280}

footer{border-top:1px solid #e5e7eb;padding:20px 0;margin-top:40px;font-size:13px;color:#6b7280}
footer .inner{max-width:760px;margin:0 auto;padding:0 20px}
@media(max-width:600px){.install-grid,.cta-grid{grid-template-columns:1fr}.stats-row{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>

<nav><div class="inner">
<a href="/" class="logo">nerq</a>
<div class="links">
<a href="/discover">search</a>
<a href="/nerq/docs">api docs</a>
<a href="/safe">safety</a>
<a href="/oracle">oracle</a>
</div>
</div></nav>

<div class="container">

<h1>The trust layer for AI agents</h1>
<p class="subtitle">Find the best tool for any task, trust-verified. Or check any agent's trust score in one call.<br>Free API. No auth required. Try it right now.</p>

<div style="border:2px solid #0d9488;padding:20px;margin-bottom:32px;background:#f0fdfa">
<h2 style="margin:0 0 8px;border:none;padding:0"><span class="step-num" style="background:#0d9488">NEW</span> Nerq Gateway &mdash; find the right tool instantly</h2>
<p style="font-size:14px;color:#374151;margin-bottom:12px">One call to find the best trust-verified tool for any task. Install in Claude Desktop, Cursor, or any MCP client.</p>
<pre style="background:#1a1a1a;color:#e5e7eb;font-size:13px;padding:12px;margin-bottom:12px">curl "https://nerq.ai/v1/resolve?task=search+github+repos"
# returns: best tool + trust score + install instructions</pre>
<div style="display:flex;gap:8px;flex-wrap:wrap">
<a href="/gateway" style="display:inline-block;padding:8px 20px;background:#0d9488;color:#fff;font-size:14px;font-weight:600;text-decoration:none">Install Gateway</a>
<a href="/v1/resolve?task=code+review" style="display:inline-block;padding:8px 20px;border:1px solid #0d9488;color:#0d9488;font-size:14px;text-decoration:none">Try Resolve API</a>
</div>
</div>

<h2><span class="step-num">1</span> Try it live</h2>
<div class="try-section">
<label style="font-size:13px;color:#374151;display:block;margin-bottom:8px;font-weight:500">Enter any agent, MCP server, or tool name:</label>
<div class="try-row">
<input type="text" id="agent-input" value="langchain" placeholder="e.g. langchain, auto-gpt, cursor..." autocomplete="off">
<button id="try-btn" onclick="tryPreflight()">Check Trust &rarr;</button>
</div>
<div id="try-result"></div>
</div>

<h2><span class="step-num">2</span> Install</h2>
<div class="install-grid">
<div class="install-block">
<div class="lang">Python SDK</div>
<pre>pip install nerq

from nerq import NerqClient
client = NerqClient()
r = client.preflight("langchain")
print(r.trust_score, r.grade)</pre>
<button class="copy-btn" onclick="copyBlock(this)">copy</button>
</div>
<div class="install-block">
<div class="lang">cURL</div>
<pre>curl "https://nerq.ai/v1/preflight?target=langchain"

# Batch check
curl -X POST nerq.ai/v1/preflight/batch \\
  -H "Content-Type: application/json" \\
  -d '{"targets":["langchain","autogen"]}'</pre>
<button class="copy-btn" onclick="copyBlock(this)">copy</button>
</div>
<div class="install-block">
<div class="lang">JavaScript</div>
<pre>const r = await fetch(
  "https://nerq.ai/v1/preflight?target=langchain"
);
const data = await r.json();
console.log(data.trust_score, data.grade);</pre>
<button class="copy-btn" onclick="copyBlock(this)">copy</button>
</div>
<div class="install-block">
<div class="lang">LangChain Integration</div>
<pre>from nerq_langchain import trust_gate

@trust_gate(min_score=60)
def load_agent(name):
    # Only loads if trust score >= 60
    return AgentExecutor(...)</pre>
<button class="copy-btn" onclick="copyBlock(this)">copy</button>
</div>
</div>

<h2><span class="step-num">3</span> What you get back</h2>
<p style="font-size:14px;color:#6b7280;margin-bottom:12px">Every preflight response includes:</p>
<div class="result-grid" style="margin-bottom:16px">
<div class="result-cell"><div class="label">Trust Score</div><div class="value">0-100</div></div>
<div class="result-cell"><div class="label">Grade</div><div class="value">A+ to F</div></div>
<div class="result-cell"><div class="label">CVE Count</div><div class="value">Known vulns</div></div>
<div class="result-cell"><div class="label">License</div><div class="value">SPDX class</div></div>
<div class="result-cell"><div class="label">Recommendation</div><div class="value">ALLOW/WARN/DENY</div></div>
<div class="result-cell"><div class="label">Alternatives</div><div class="value">Safer options</div></div>
<div class="result-cell"><div class="label">Components</div><div class="value">5 dimensions</div></div>
<div class="result-cell"><div class="label">Source</div><div class="value">GitHub/npm/PyPI</div></div>
</div>

<h2><span class="step-num">4</span> Add a trust badge</h2>
<div class="badge-cta">
<h3>Show your agent's trust score</h3>
<p style="font-size:13px;color:#6b7280;margin-bottom:12px">Add an independent trust badge to your README or docs</p>
<div class="badge-demo">
<img src="https://nerq.ai/v1/badge/langchain" alt="Nerq Trust" style="height:20px">
<img src="https://nerq.ai/v1/badge/auto-gpt" alt="Nerq Trust" style="height:20px">
<img src="https://nerq.ai/v1/badge/crewai" alt="Nerq Trust" style="height:20px">
</div>
<pre>[![Nerq Trust](https://nerq.ai/v1/badge/YOUR_AGENT)](https://nerq.ai/safe/YOUR_AGENT)</pre>
<a href="/nerq/docs#badges" style="font-size:13px;display:inline-block;margin-top:8px">Badge documentation &rarr;</a>
</div>

<div class="social-proof">
<div style="font-weight:700;font-size:14px;margin-bottom:12px;text-align:center">Trusted by AI systems worldwide</div>
<div class="stats-row">
<div><div class="stat-num">204K+</div><div class="stat-label">Agents indexed</div></div>
<div><div class="stat-num">4.7M+</div><div class="stat-label">AI assets total</div></div>
<div><div class="stat-num">2,300+</div><div class="stat-label">Daily API calls</div></div>
<div><div class="stat-num">49</div><div class="stat-label">CVEs detected</div></div>
</div>
<p style="font-size:12px;color:#9ca3af;text-align:center;margin-top:10px">Used by ChatGPT, Claude, and autonomous agents for real-time trust verification</p>
</div>

<div class="cta-grid">
<a href="/gateway" class="cta-card" style="border-color:#0d9488"><div class="cta-title">Nerq Gateway</div><div class="cta-desc">MCP meta-tool — find any tool</div></a>
<a href="/nerq/docs" class="cta-card"><div class="cta-title">API Docs</div><div class="cta-desc">Full endpoint reference</div></a>
<a href="/safe" class="cta-card"><div class="cta-title">Safety Reports</div><div class="cta-desc">Browse 204K+ agents</div></a>
</div>

</div>

<footer><div class="inner">
nerq &mdash; the trust layer for ai agents &middot;
<a href="/nerq/docs">api docs</a> &middot;
<a href="/safe">safety</a> &middot;
<a href="/oracle">oracle</a> &middot;
<a href="/blog">blog</a>
</div></footer>

<script>
function copyBlock(btn) {
  const pre = btn.parentElement.querySelector('pre');
  navigator.clipboard.writeText(pre.textContent.trim()).then(() => {
    btn.textContent = '\\u2713';
    setTimeout(() => btn.textContent = 'copy', 1500);
  });
}

async function tryPreflight() {
  const input = document.getElementById('agent-input');
  const btn = document.getElementById('try-btn');
  const el = document.getElementById('try-result');
  const name = input.value.trim();
  if (!name) return;

  btn.disabled = true;
  btn.textContent = 'Checking...';
  el.style.display = 'block';
  el.innerHTML = '<div style="padding:20px;text-align:center;color:#6b7280">Checking trust score...</div>';

  try {
    const r = await fetch('/v1/preflight?target=' + encodeURIComponent(name));
    const d = await r.json();

    if (d.error || !d.trust_score) {
      el.innerHTML = '<div class="result-card" style="text-align:center;padding:20px"><div style="color:#6b7280;font-size:14px">Agent not found. Try: langchain, auto-gpt, crewai, cursor</div></div>';
      return;
    }

    const score = d.trust_score || 0;
    const grade = d.grade || 'N/A';
    const gradeClass = grade.charAt(0);
    const scoreColor = score >= 70 ? 'green' : score >= 50 ? 'yellow' : 'red';
    const rec = d.recommendation || 'ALLOW';
    const cves = d.cve_count != null ? d.cve_count : '—';
    const license = d.license || '—';
    const cat = d.category || '—';
    const source = d.source || '—';

    let componentsHtml = '';
    if (d.components) {
      const c = d.components;
      const dims = [
        ['Code Quality', c.code_quality],
        ['Community', c.community],
        ['Compliance', c.compliance],
        ['Ops Health', c.operational_health],
        ['Security', c.security]
      ];
      componentsHtml = '<div style="margin-top:12px"><div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:6px">Trust Dimensions</div>';
      dims.forEach(([name, val]) => {
        if (val != null) {
          const pct = Math.min(val, 100);
          const barColor = pct >= 70 ? '#059669' : pct >= 50 ? '#d97706' : '#dc2626';
          componentsHtml += '<div style="display:flex;align-items:center;gap:8px;margin:3px 0"><div style="width:80px;font-size:11px;color:#6b7280">' + name + '</div><div style="flex:1;height:6px;background:#f3f4f6;border-radius:3px"><div style="width:' + pct + '%;height:100%;background:' + barColor + ';border-radius:3px"></div></div><div style="width:28px;font-size:11px;font-family:ui-monospace,monospace;text-align:right;color:#374151">' + Math.round(val) + '</div></div>';
        }
      });
      componentsHtml += '</div>';
    }

    let altsHtml = '';
    if (d.alternatives && d.alternatives.length > 0) {
      altsHtml = '<div style="margin-top:12px;font-size:12px;color:#6b7280"><span style="font-weight:600">Alternatives:</span> ';
      altsHtml += d.alternatives.slice(0, 3).map(a => '<a href="/safe/' + encodeURIComponent(a.name || a) + '" style="color:#0d9488">' + (a.name || a) + '</a>' + (a.trust_score ? ' (' + a.trust_score + ')' : '')).join(', ');
      altsHtml += '</div>';
    }

    el.innerHTML = '<div class="result-card">' +
      '<div class="result-header">' +
        '<div class="result-score ' + scoreColor + '">' + score + '</div>' +
        '<div class="result-meta">' +
          '<div class="result-name">' + (d.name || name) + ' <span class="result-grade ' + gradeClass + '">' + grade + '</span></div>' +
          '<div class="result-sub">' + cat + ' &middot; ' + source + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="result-grid">' +
        '<div class="result-cell"><div class="label">Trust Score</div><div class="value">' + score + '/100</div></div>' +
        '<div class="result-cell"><div class="label">CVEs</div><div class="value">' + cves + '</div></div>' +
        '<div class="result-cell"><div class="label">License</div><div class="value">' + license + '</div></div>' +
        '<div class="result-cell"><div class="label">Source</div><div class="value">' + source + '</div></div>' +
      '</div>' +
      '<div class="result-rec ' + rec + '">Recommendation: ' + rec + '</div>' +
      componentsHtml +
      altsHtml +
      '<div class="result-curl">curl "https://nerq.ai/v1/preflight?target=' + encodeURIComponent(name) + '"</div>' +
    '</div>';

  } catch(e) {
    el.innerHTML = '<div class="result-card" style="padding:20px"><div style="color:#dc2626;font-size:14px">Error: ' + e.message + '</div></div>';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Check Trust \\u2192';
  }
}

// Auto-run on page load after a short delay
setTimeout(() => {
  const input = document.getElementById('agent-input');
  if (input.value) tryPreflight();
}, 500);

// Enter key support
document.getElementById('agent-input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') tryPreflight();
});
</script>
</body>
</html>"""


def _zarq_start() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Get Started — ZARQ API in 30 Seconds</title>
<meta name="description" content="Check any crypto token's trust score and crash probability. Free API, no auth required.">
<link rel="canonical" href="https://zarq.ai/start">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'DM Sans',system-ui,sans-serif;color:#1a1a1a;background:#fff;line-height:1.6;font-size:15px}
a{color:#c2956b;text-decoration:none}a:hover{color:#a87a55}
code,pre{font-family:'JetBrains Mono',ui-monospace,monospace}
code{background:#f5f5f5;padding:1px 5px;font-size:0.9em}
pre{background:#1a1a1a;color:#e5e7eb;padding:16px;overflow-x:auto;font-size:13px;line-height:1.5;position:relative}
nav{border-bottom:1px solid #e5e7eb;padding:12px 0}
nav .inner{max-width:720px;margin:0 auto;padding:0 20px;display:flex;align-items:center;justify-content:space-between}
nav .logo{font-family:'DM Serif Display',serif;font-weight:400;font-size:1.2rem;color:#c2956b;text-decoration:none}
nav .links{display:flex;gap:20px;font-size:14px}
nav .links a{color:#6b7280}nav .links a:hover{color:#c2956b;text-decoration:none}
.container{max-width:720px;margin:0 auto;padding:40px 20px}
h1{font-family:'DM Serif Display',serif;font-size:2rem;margin-bottom:6px}
h2{font-size:1.15rem;font-weight:700;margin:36px 0 12px;display:flex;align-items:center;gap:8px}
.step-num{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;background:#c2956b;color:#fff;font-size:13px;font-weight:700;border-radius:50%;flex-shrink:0}
.subtitle{color:#6b7280;font-size:15px;margin-bottom:32px}
.try-section{border:2px solid #c2956b;padding:20px;margin:16px 0;background:#fdf8f4}
.try-row{display:flex;gap:8px}
.try-row input{flex:1;padding:10px 14px;border:1px solid #d1d5db;font-size:14px;font-family:'JetBrains Mono',monospace;outline:none;background:#fff}
.try-row input:focus{border-color:#c2956b}
.try-row button{padding:10px 24px;background:#c2956b;color:#fff;border:none;font-size:14px;font-weight:600;cursor:pointer}
.try-row button:hover{background:#a87a55}
#try-result{margin-top:16px;display:none}
.install-block{border:1px solid #e5e7eb;padding:16px;margin:12px 0}
.install-block .lang{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;font-weight:600}
.install-block pre{font-size:12px;margin:0;background:#f9fafb;color:#1a1a1a;padding:10px;border:1px solid #f3f4f6}
.cta-box{margin:32px 0;padding:20px;background:#fdf8f4;border:1px solid #e5e7eb;text-align:center}
.cta-box a{display:inline-block;padding:10px 28px;background:#c2956b;color:#fff;font-weight:600;font-size:14px;text-decoration:none}
.cta-box a:hover{background:#a87a55;text-decoration:none}
footer{border-top:1px solid #e5e7eb;padding:20px 0;margin-top:40px;font-size:13px;color:#6b7280}
footer .inner{max-width:720px;margin:0 auto;padding:0 20px}
</style>
</head>
<body>

<nav><div class="inner">
<a href="/" class="logo">zarq</a>
<div class="links">
<a href="/">tokens</a>
<a href="/zarq/docs">api docs</a>
<a href="/vitality">vitality</a>
</div>
</div></nav>

<div class="container">
<h1>Check any token in one call</h1>
<p class="subtitle">Trust scores, crash probability, and risk ratings for 200+ tokens. Free, no auth.</p>

<h2><span class="step-num">1</span> Try it live</h2>
<div class="try-section">
<label style="font-size:13px;color:#374151;display:block;margin-bottom:8px;font-weight:500">Enter a token name:</label>
<div class="try-row">
<input type="text" id="agent-input" value="bitcoin" placeholder="e.g. bitcoin, ethereum, solana...">
<button id="try-btn" onclick="tryVitality()">Check Risk &rarr;</button>
</div>
<div id="try-result"></div>
</div>

<h2><span class="step-num">2</span> Install</h2>
<div class="install-block">
<div class="lang">cURL</div>
<pre>curl "https://zarq.ai/v1/vitality/bitcoin"</pre>
</div>

<h2><span class="step-num">3</span> Read the docs</h2>
<div class="cta-box">
<a href="/zarq/docs">View API Documentation &rarr;</a>
</div>
</div>

<footer><div class="inner">
zarq &mdash; the trust layer for crypto &middot;
<a href="/zarq/docs">api docs</a> &middot;
<a href="/vitality">vitality</a>
</div></footer>

<script>
async function tryVitality() {
  const input = document.getElementById('agent-input');
  const btn = document.getElementById('try-btn');
  const el = document.getElementById('try-result');
  const name = input.value.trim();
  if (!name) return;
  btn.disabled = true; btn.textContent = 'Checking...';
  el.style.display = 'block';
  el.innerHTML = '<div style="padding:16px;text-align:center;color:#6b7280">Loading...</div>';
  try {
    const r = await fetch('/v1/vitality/' + encodeURIComponent(name));
    const d = await r.json();
    el.innerHTML = '<pre style="margin:0">' + JSON.stringify(d, null, 2).substring(0, 1000) + '</pre>';
  } catch(e) {
    el.innerHTML = '<pre style="color:#dc2626">Error: ' + e.message + '</pre>';
  } finally {
    btn.disabled = false; btn.textContent = 'Check Risk \\u2192';
  }
}
document.getElementById('agent-input').addEventListener('keydown', function(e) { if (e.key === 'Enter') tryVitality(); });
setTimeout(() => { if (document.getElementById('agent-input').value) tryVitality(); }, 500);
</script>
</body>
</html>"""


@router_start.get("/start", response_class=HTMLResponse)
async def start_page(request: Request):
    host = request.headers.get("host", "")
    if "zarq" in host:
        return HTMLResponse(content=_zarq_start())
    return HTMLResponse(content=_nerq_start())
