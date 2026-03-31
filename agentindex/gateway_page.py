"""
/gateway page — nerq-gateway landing page.

"One MCP server. 25,000 tools. Zero config."
"""

import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER


def _page():
    mcp_config = json.dumps({
        "mcpServers": {
            "nerq": {
                "command": "npx",
                "args": ["-y", "nerq-gateway"],
                "env": {
                    "NERQ_AUTO_DISCOVER": "true"
                }
            }
        }
    }, indent=2)

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "What is nerq-gateway?",
             "acceptedAnswer": {"@type": "Answer", "text": "nerq-gateway is a single MCP server that gives your AI agent access to 25,000+ tools. It uses the Nerq API to find, verify, and recommend the best tool for any task — with zero configuration."}},
            {"@type": "Question", "name": "How do I install nerq-gateway?",
             "acceptedAnswer": {"@type": "Answer", "text": "Add it to your Claude Desktop config (claude_desktop_config.json) with one JSON block, then restart Claude. No API key needed. Free tier: 100 requests/day."}},
            {"@type": "Question", "name": "Is nerq-gateway safe?",
             "acceptedAnswer": {"@type": "Answer", "text": "Every tool recommended by nerq-gateway is trust-verified. Nerq checks CVEs, licenses, maintenance status, and 10+ other signals before recommending any tool. You can set a minimum trust threshold."}},
            {"@type": "Question", "name": "What tools are available?",
             "acceptedAnswer": {"@type": "Answer", "text": "nerq-gateway can discover and recommend tools from 25,000+ MCP servers and 204,000+ AI agents across GitHub, npm, PyPI, Docker Hub, and HuggingFace. Categories include source control, databases, communication, code review, security, cloud, and more."}},
            {"@type": "Question", "name": "How does tool discovery work?",
             "acceptedAnswer": {"@type": "Answer", "text": "When you describe a task, nerq-gateway calls the /v1/resolve API which parses your task into capability categories, searches the Nerq database, ranks candidates by trust score, capability match, and popularity, then returns the best recommendation with install instructions."}},
        ]
    })

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nerq Gateway — One MCP Server. 25,000 Tools. Zero Config.</title>
<meta name="description" content="nerq-gateway gives your AI agent access to 25,000+ MCP servers with one config line. Trust-verified tool discovery for Claude, Cursor, and any MCP client.">
<link rel="canonical" href="https://nerq.ai/gateway">
<meta property="og:title" content="Nerq Gateway — One MCP Server. 25,000 Tools.">
<meta property="og:description" content="Your AI agent just got 1000x more capable. One MCP server, 25,000 tools, zero config.">
<meta property="og:url" content="https://nerq.ai/gateway">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{faq_jsonld}</script>
<style>
{NERQ_CSS}
.gw-hero{{text-align:center;padding:48px 16px 40px}}
.gw-hero h1{{font-size:2.5rem;font-weight:700;line-height:1.2;margin:0 0 12px}}
.gw-hero .sub{{font-size:1.25rem;color:#6b7280;margin:0 0 32px}}
.gw-install{{background:#0a0a0a;color:#e5e7eb;padding:24px;margin:0 auto 32px;max-width:600px;font-family:ui-monospace,'SF Mono',monospace;font-size:13px;line-height:1.6;overflow-x:auto;cursor:pointer;position:relative}}
.gw-install:hover{{background:#111}}
.gw-install .copy-hint{{position:absolute;top:8px;right:12px;font-size:11px;color:#6b7280;font-family:system-ui}}
.flow{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:32px 0;text-align:center}}
.flow-step{{padding:16px 8px;border:1px solid #e5e7eb}}
.flow-step .step-num{{font-size:12px;color:#6b7280;font-weight:600}}
.flow-step .step-txt{{font-size:14px;font-weight:600;color:#1a1a1a;margin-top:4px}}
.flow-step .step-desc{{font-size:12px;color:#6b7280;margin-top:4px}}
.flow-arrow{{display:flex;align-items:center;justify-content:center;color:#0d9488;font-size:24px;font-weight:700}}
.tools-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:24px 0}}
.tool-card{{border:1px solid #e5e7eb;padding:16px}}
.tool-card .tool-name{{font-weight:700;font-size:15px;color:#1a1a1a;margin-bottom:4px;font-family:ui-monospace,'SF Mono',monospace}}
.tool-card .tool-desc{{font-size:13px;color:#6b7280;line-height:1.5}}
.compare-table{{width:100%;border-collapse:collapse;margin:24px 0}}
.compare-table th,.compare-table td{{padding:12px 16px;text-align:left;border-bottom:1px solid #e5e7eb}}
.compare-table th{{font-size:12px;color:#6b7280;text-transform:uppercase;font-weight:600}}
.compare-table .yes{{color:#059669;font-weight:600}}
.compare-table .no{{color:#dc2626}}
.try-section{{background:#f9fafb;border:1px solid #e5e7eb;padding:24px;margin:32px 0}}
.try-section input{{padding:10px 14px;border:1px solid #e5e7eb;font-size:14px;font-family:system-ui;width:60%}}
.try-section button{{padding:10px 20px;background:#0d9488;color:#fff;border:none;font-size:14px;font-weight:600;cursor:pointer}}
#resolve-result{{margin-top:16px;font-family:ui-monospace,'SF Mono',monospace;font-size:13px;white-space:pre-wrap;max-height:300px;overflow-y:auto}}
.faq-section{{margin:32px 0}}
.faq-item{{border-bottom:1px solid #e5e7eb;padding:16px 0}}
.faq-item:first-child{{border-top:1px solid #e5e7eb}}
.faq-q{{font-weight:700;font-size:1rem;color:#1a1a1a;margin-bottom:8px}}
.faq-a{{font-size:15px;color:#374151;line-height:1.7}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <div class="breadcrumb"><a href="/">nerq</a> &rsaquo; gateway</div>

  <div class="gw-hero">
    <h1>One MCP Server.<br>25,000 Tools.<br>Zero Config.</h1>
    <p class="sub">Your AI agent just got 1000x more capable.</p>
  </div>

  <h2 style="text-align:center;font-size:14px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px">Install in 30 seconds</h2>
  <div class="gw-install" onclick="navigator.clipboard.writeText(this.innerText.replace('Click to copy','').trim())">
    <div class="copy-hint">Click to copy</div>
<pre style="margin:0;color:#e5e7eb">{mcp_config}</pre>
  </div>
  <p style="text-align:center;font-size:13px;color:#6b7280">Add to <code>~/Library/Application Support/Claude/claude_desktop_config.json</code> &middot; Restart Claude &middot; Done.</p>

  <h2>How it works</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:24px 0">
    <div class="flow-step">
      <div class="step-num">1</div>
      <div class="step-txt">You ask</div>
      <div class="step-desc">&ldquo;Search my GitHub repos for security issues&rdquo;</div>
    </div>
    <div class="flow-step">
      <div class="step-num">2</div>
      <div class="step-txt">Claude asks gateway</div>
      <div class="step-desc">find_tool(&ldquo;github search&rdquo;)</div>
    </div>
    <div class="flow-step">
      <div class="step-num">3</div>
      <div class="step-txt">Gateway resolves</div>
      <div class="step-desc">Searches 25K servers, trust-verifies</div>
    </div>
    <div class="flow-step">
      <div class="step-num">4</div>
      <div class="step-txt">Returns best match</div>
      <div class="step-desc">github-mcp-server (Trust: 83, A)</div>
    </div>
    <div class="flow-step">
      <div class="step-num">5</div>
      <div class="step-txt">Claude uses it</div>
      <div class="step-desc">With install instructions ready</div>
    </div>
  </div>

  <h2>Gateway Tools</h2>
  <div class="tools-grid">
    <div class="tool-card">
      <div class="tool-name">find_tool</div>
      <div class="tool-desc">Find the best MCP server or tool for any task. Describe what you need, get a trust-verified recommendation with install instructions.</div>
    </div>
    <div class="tool-card">
      <div class="tool-name">check_trust</div>
      <div class="tool-desc">Check the trust score and security status of any agent or tool before using it. CVEs, license, maintenance status.</div>
    </div>
    <div class="tool-card">
      <div class="tool-name">search_agents</div>
      <div class="tool-desc">Search 204,000+ AI agents and tools. Filter by trust score, category, framework, or keywords.</div>
    </div>
    <div class="tool-card">
      <div class="tool-name">compare_agents</div>
      <div class="tool-desc">Compare two agents side-by-side on trust, security, pricing, and compatibility. Get a clear winner.</div>
    </div>
  </div>

  <h2>Try it live</h2>
  <div class="try-section">
    <p style="margin:0 0 12px;font-size:15px;font-weight:600">What tool do you need?</p>
    <form id="try-form" onsubmit="return tryResolve(event)" style="display:flex;gap:8px">
      <input id="try-input" placeholder="e.g., search github repos, query postgres, send slack message..." style="flex:1">
      <button type="submit">Resolve</button>
    </form>
    <div id="resolve-result"></div>
  </div>

  <h2>Without vs With Gateway</h2>
  <table class="compare-table">
    <thead><tr><th></th><th>Without Gateway</th><th>With Gateway</th></tr></thead>
    <tbody>
      <tr><td>Setup</td><td class="no">Configure each server manually</td><td class="yes">One config line</td></tr>
      <tr><td>Tools available</td><td class="no">Only what you configured</td><td class="yes">25,000+ servers</td></tr>
      <tr><td>Trust verification</td><td class="no">Hope they're safe</td><td class="yes">Every tool trust-verified</td></tr>
      <tr><td>New capabilities</td><td class="no">Manually find &amp; add servers</td><td class="yes">Auto-discovery</td></tr>
      <tr><td>CVE checking</td><td class="no">Not checked</td><td class="yes">Checked before recommendation</td></tr>
      <tr><td>Install instructions</td><td class="no">Search docs yourself</td><td class="yes">Ready to paste</td></tr>
    </tbody>
  </table>

  <h2>Trust verification built in</h2>
  <p style="font-size:15px;line-height:1.7;color:#374151">Every tool recommended by the gateway is trust-verified against 13+ independent signals. Nerq checks known CVEs, license compliance, maintenance activity, community signals, and security practices. You set the minimum trust threshold (default: 60/100). Tools below your threshold are never recommended.</p>

  <div class="faq-section">
    <h2>FAQ</h2>
    <div class="faq-item">
      <div class="faq-q">What is nerq-gateway?</div>
      <div class="faq-a">nerq-gateway is a single MCP server that gives your AI agent access to 25,000+ tools. It uses the Nerq /v1/resolve API to find, verify, and recommend the best tool for any task &mdash; with zero configuration.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">How do I install it?</div>
      <div class="faq-a">Add the JSON config block above to your Claude Desktop config file (<code>~/Library/Application Support/Claude/claude_desktop_config.json</code>), then restart Claude. No API key needed. Free tier: 100 requests/day.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Is it safe?</div>
      <div class="faq-a">Yes. Every tool is trust-verified before recommendation. Nerq checks CVEs, licenses, maintenance status, and 10+ other signals. Set <code>NERQ_MIN_TRUST=70</code> for stricter filtering.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">What tools can it find?</div>
      <div class="faq-a">Anything in the Nerq index: GitHub tools, MCP servers, npm/PyPI packages, Docker images. Categories include source control, databases, communication, code review, security, cloud, AI/ML, media, and more.</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Does it work with Cursor?</div>
      <div class="faq-a">Yes. nerq-gateway works with any MCP client including Claude Desktop, Cursor, VS Code, and custom MCP implementations.</div>
    </div>
  </div>

  <div style="margin-top:32px;padding:20px 24px;border:1px solid #e5e7eb;background:#f9fafb;text-align:center">
    <div style="font-weight:700;font-size:18px;margin-bottom:8px">Get started in 30 seconds</div>
    <p style="font-size:14px;color:#6b7280;margin:0 0 16px">npm &middot; No API key &middot; Free tier</p>
    <code style="background:#0a0a0a;color:#e5e7eb;padding:10px 20px;font-size:14px;display:inline-block">npx nerq-gateway</code>
    <div style="margin-top:12px;font-size:13px">
      <a href="https://npmjs.com/package/nerq-gateway" style="color:#0d9488">npm</a> &middot;
      <a href="https://github.com/nerq-ai/nerq-gateway" style="color:#0d9488">GitHub</a> &middot;
      <a href="/nerq/docs" style="color:#0d9488">API docs</a>
    </div>
  </div>
</main>
{NERQ_FOOTER}
<script>
async function tryResolve(e) {{
  e.preventDefault();
  const task = document.getElementById('try-input').value;
  if (!task) return false;
  const el = document.getElementById('resolve-result');
  el.textContent = 'Resolving...';
  try {{
    const res = await fetch('/v1/resolve?task=' + encodeURIComponent(task) + '&min_trust=50');
    const data = await res.json();
    if (data.recommendation) {{
      const r = data.recommendation;
      let txt = 'Recommended: ' + r.name + '\\n';
      txt += 'Trust Score: ' + r.trust_score + '/100 (' + r.grade + ')\\n';
      txt += 'Category: ' + (r.category || 'unknown') + '\\n';
      if (r.description) txt += 'Description: ' + r.description.substring(0, 150) + '\\n';
      if (r.install && r.install.mcp_config) {{
        txt += '\\nMCP Config:\\n' + JSON.stringify(r.install.mcp_config, null, 2) + '\\n';
      }}
      if (data.alternatives && data.alternatives.length > 0) {{
        txt += '\\nAlternatives:\\n';
        data.alternatives.forEach(a => {{
          txt += '  - ' + a.name + ' (' + a.trust_score + '/100, ' + a.grade + ') — ' + a.tradeoff + '\\n';
        }});
      }}
      txt += '\\nResolved in ' + data.response_time_ms + 'ms from ' + data.total_candidates + ' candidates';
      el.textContent = txt;
    }} else {{
      el.textContent = 'No tools found for: ' + task;
    }}
  }} catch (err) {{
    el.textContent = 'Error: ' + err.message;
  }}
  return false;
}}
</script>
</body>
</html>"""


def mount_gateway_page(app: FastAPI):
    @app.get("/gateway", response_class=HTMLResponse, include_in_schema=False)
    async def gateway():
        return HTMLResponse(_page())
