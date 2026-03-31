"""
/trust-score pillar page — targeting "AI agent trust score" queries.
Explains the methodology, shows interactive search, links to /safe/, /protocol, /oracle.
"""
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from agentindex.nerq_design import nerq_head, NERQ_FOOTER


def mount_trust_score_page(app: FastAPI):

    @app.get("/trust-score", response_class=HTMLResponse)
    async def trust_score_page():
        faq_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "What is an AI agent trust score?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "An AI agent trust score is a numerical rating from 0 to 100 that measures the trustworthiness of an AI agent based on security, compliance, maintenance, community adoption, and code quality signals. Nerq calculates trust scores for 204,000+ agents across GitHub, npm, PyPI, HuggingFace, and MCP registries."
                    }
                },
                {
                    "@type": "Question",
                    "name": "How is the AI agent trust score calculated?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Nerq's Trust Score v2 combines five weighted dimensions: Code Quality (25%) measures documentation and capability breadth. Community (25%) measures stars, downloads, and contributors. Compliance (20%) checks license classification and regulatory status. Operational Health (15%) tracks update frequency and maintenance. Security (15%) checks for known CVEs from the GitHub Advisory Database. Scores update daily."
                    }
                },
                {
                    "@type": "Question",
                    "name": "What is a good trust score for an AI agent?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Agents scoring 70+ receive a Nerq Verified badge and are considered trustworthy for production use. Scores of 85+ indicate highly trusted agents with excellent security and maintenance practices. Scores below 50 indicate significant risk — these agents may have known vulnerabilities, poor maintenance, or compliance issues. Agents scoring below 30 receive a DENY recommendation in preflight checks."
                    }
                },
                {
                    "@type": "Question",
                    "name": "How do I check an AI agent's trust score?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Use the Nerq API: curl https://nerq.ai/v1/preflight?target=AGENT_NAME. The response includes the trust score, grade (A+ through F), recommendation (ALLOW/WARN/DENY), CVE count, license classification, and safer alternatives. No API key or authentication required. You can also use the Python SDK: pip install nerq."
                    }
                },
                {
                    "@type": "Question",
                    "name": "Is the AI agent trust score free?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "Yes. The Nerq Trust API is completely free with no authentication required. Rate limit is 100 requests per hour. The API covers 204,000+ agents and tools. Batch checks of up to 50 agents per request are also available."
                    }
                },
            ]
        })

        return HTMLResponse(content=f"""{nerq_head(
            "AI Agent Trust Score — How We Rate 204K Agents | Nerq",
            "What is an AI agent trust score? Nerq rates 204K+ agents on security, compliance, maintenance, and community signals. Free API, no auth. Check any agent instantly.",
            "https://nerq.ai/trust-score"
        )}
<script type="application/ld+json">{faq_jsonld}</script>
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <div class="breadcrumb"><a href="/">nerq</a> &rsaquo; trust score</div>

  <h1>AI Agent Trust Score</h1>
  <p class="desc">How Nerq rates 204K+ AI agents on trustworthiness — and how to check any agent in one API call.</p>

  <!-- Interactive search -->
  <div style="border:2px solid #0d9488;padding:20px;margin:20px 0;background:#f0fdfa">
    <div style="font-weight:600;font-size:15px;margin-bottom:10px">Check any agent's trust score</div>
    <div style="display:flex;gap:8px">
      <input type="text" id="ts-input" value="langchain" placeholder="e.g. langchain, auto-gpt, cursor..." style="flex:1;padding:10px 14px;border:1px solid #d1d5db;font-size:14px;font-family:ui-monospace,monospace;outline:none">
      <button id="ts-btn" onclick="checkTrust()" style="padding:10px 24px;background:#0d9488;color:#fff;border:none;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap">Check Score</button>
    </div>
    <div id="ts-result" style="margin-top:12px;display:none"></div>
  </div>

  <h2 style="border-top:none;padding-top:0">What is an AI Agent Trust Score?</h2>
  <p style="font-size:15px;line-height:1.8;color:#374151">
    An AI agent trust score is a numerical rating from 0 to 100 that measures the trustworthiness of an AI agent, tool, or MCP server. Unlike a simple "safe/unsafe" label, trust scores decompose trust into multiple dimensions — allowing developers and AI systems to make nuanced decisions about which agents to integrate, delegate to, or recommend.
  </p>
  <p style="font-size:15px;line-height:1.8;color:#374151;margin-top:12px">
    Nerq calculates trust scores for <strong>204,000+ agents</strong> across GitHub, npm, PyPI, HuggingFace, and MCP registries. Scores update daily. The methodology is documented at <a href="/protocol">/protocol</a>.
  </p>

  <h2>The Five Dimensions</h2>
  <p style="font-size:14px;color:#6b7280;margin-bottom:16px">Trust Score v2 combines five weighted dimensions:</p>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin:16px 0">
    <div class="card" style="padding:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div style="width:36px;height:36px;background:#ecfdf5;display:flex;align-items:center;justify-content:center;font-size:18px">Q</div>
        <div>
          <div style="font-weight:700;font-size:15px">Code Quality</div>
          <div style="font-size:12px;color:#6b7280">25% weight</div>
        </div>
      </div>
      <p style="font-size:14px;color:#374151;line-height:1.6;margin:0">Documentation completeness, naming conventions, capability breadth, README quality. Measures how well-built the agent is.</p>
    </div>

    <div class="card" style="padding:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div style="width:36px;height:36px;background:#eff6ff;display:flex;align-items:center;justify-content:center;font-size:18px">C</div>
        <div>
          <div style="font-weight:700;font-size:15px">Community</div>
          <div style="font-size:12px;color:#6b7280">25% weight</div>
        </div>
      </div>
      <p style="font-size:14px;color:#374151;line-height:1.6;margin:0">Stars, downloads, forks, contributor count, npm/PyPI weekly download volume. Measures real-world adoption and community trust.</p>
    </div>

    <div class="card" style="padding:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div style="width:36px;height:36px;background:#fef3c7;display:flex;align-items:center;justify-content:center;font-size:18px">L</div>
        <div>
          <div style="font-weight:700;font-size:15px">Compliance</div>
          <div style="font-size:12px;color:#6b7280">20% weight</div>
        </div>
      </div>
      <p style="font-size:14px;color:#374151;line-height:1.6;margin:0">License classification (SPDX), EU AI Act risk mapping, regulatory status across 52 jurisdictions. Critical for enterprise deployments.</p>
    </div>

    <div class="card" style="padding:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div style="width:36px;height:36px;background:#fef2f2;display:flex;align-items:center;justify-content:center;font-size:18px">O</div>
        <div>
          <div style="font-weight:700;font-size:15px">Operational Health</div>
          <div style="font-size:12px;color:#6b7280">15% weight</div>
        </div>
      </div>
      <p style="font-size:14px;color:#374151;line-height:1.6;margin:0">Update recency, commit frequency, release cadence. An agent that hasn't been updated in 6 months is a risk — dependencies go stale, vulnerabilities go unpatched.</p>
    </div>

    <div class="card" style="padding:20px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <div style="width:36px;height:36px;background:#fce7f3;display:flex;align-items:center;justify-content:center;font-size:18px">S</div>
        <div>
          <div style="font-weight:700;font-size:15px">Security</div>
          <div style="font-size:12px;color:#6b7280">15% weight</div>
        </div>
      </div>
      <p style="font-size:14px;color:#374151;line-height:1.6;margin:0">Known CVE count and severity from the GitHub Advisory Database. Agents with unpatched CRITICAL CVEs get flagged with a DENY recommendation.</p>
    </div>
  </div>

  <h2>Score Ranges &amp; Grades</h2>
  <table>
    <tr><th>Score</th><th>Grade</th><th>Meaning</th><th>Recommendation</th></tr>
    <tr><td style="font-family:ui-monospace,monospace;font-weight:600">90&ndash;100</td><td><span class="pill pill-green">A+</span></td><td>Exceptional trust across all dimensions</td><td>ALLOW</td></tr>
    <tr><td style="font-family:ui-monospace,monospace;font-weight:600">80&ndash;89</td><td><span class="pill pill-green">A</span></td><td>Strong trust signals, minor areas for improvement</td><td>ALLOW</td></tr>
    <tr><td style="font-family:ui-monospace,monospace;font-weight:600">70&ndash;79</td><td><span class="pill pill-green">B+</span></td><td>Nerq Verified threshold — trusted for production</td><td>ALLOW</td></tr>
    <tr><td style="font-family:ui-monospace,monospace;font-weight:600">60&ndash;69</td><td><span class="pill pill-yellow">B</span></td><td>Moderate trust — review before production use</td><td>WARN</td></tr>
    <tr><td style="font-family:ui-monospace,monospace;font-weight:600">50&ndash;59</td><td><span class="pill pill-yellow">C</span></td><td>Mixed signals — proceed with caution</td><td>WARN</td></tr>
    <tr><td style="font-family:ui-monospace,monospace;font-weight:600">30&ndash;49</td><td><span class="pill pill-red">D</span></td><td>Below average — significant concerns</td><td>DENY</td></tr>
    <tr><td style="font-family:ui-monospace,monospace;font-weight:600">0&ndash;29</td><td><span class="pill pill-red">F</span></td><td>Low trust — not recommended</td><td>DENY</td></tr>
  </table>

  <h2>How to Check a Trust Score</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0">
    <div class="card" style="padding:16px">
      <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;font-weight:600">cURL</div>
      <pre style="font-size:12px;margin:0">curl "https://nerq.ai/v1/preflight?target=langchain"</pre>
    </div>
    <div class="card" style="padding:16px">
      <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;font-weight:600">Python SDK</div>
      <pre style="font-size:12px;margin:0">pip install nerq

from nerq import NerqClient
client = NerqClient()
r = client.preflight("langchain")
print(r.trust_score, r.grade)</pre>
    </div>
  </div>

  <h2>What You Get Back</h2>
  <p style="font-size:14px;color:#6b7280;margin-bottom:12px">Every preflight response includes:</p>
  <table>
    <tr><td style="font-weight:600;width:160px">trust_score</td><td>0&ndash;100 composite score</td></tr>
    <tr><td style="font-weight:600">grade</td><td>A+ through F letter grade</td></tr>
    <tr><td style="font-weight:600">recommendation</td><td>ALLOW, WARN, or DENY</td></tr>
    <tr><td style="font-weight:600">cve_count</td><td>Known vulnerabilities from GitHub Advisory DB</td></tr>
    <tr><td style="font-weight:600">license</td><td>SPDX license classification</td></tr>
    <tr><td style="font-weight:600">components</td><td>Per-dimension scores (code_quality, community, compliance, operational_health, security)</td></tr>
    <tr><td style="font-weight:600">alternatives</td><td>Higher-rated agents in the same category</td></tr>
    <tr><td style="font-weight:600">source</td><td>Registry where the agent was indexed (github, npm, pypi, etc.)</td></tr>
  </table>

  <h2>Coverage</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:12px 0">
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">204K+</div>
      <div style="font-size:12px;color:#6b7280">Agents &amp; tools</div>
    </div>
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">25K+</div>
      <div style="font-size:12px;color:#6b7280">MCP servers</div>
    </div>
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">4.7M+</div>
      <div style="font-size:12px;color:#6b7280">Total AI assets</div>
    </div>
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">12</div>
      <div style="font-size:12px;color:#6b7280">Registries</div>
    </div>
  </div>

  <h2>Use Cases</h2>
  <table>
    <tr><td style="font-weight:600;width:200px">Pre-integration check</td><td>Verify an agent's trust score before adding it to your project</td></tr>
    <tr><td style="font-weight:600">Agent-to-agent trust</td><td>Automated preflight checks before delegating tasks between agents</td></tr>
    <tr><td style="font-weight:600">CI/CD gating</td><td>Block deployments that depend on agents below a trust threshold</td></tr>
    <tr><td style="font-weight:600">MCP server vetting</td><td>Verify MCP servers before granting them tool access</td></tr>
    <tr><td style="font-weight:600">Compliance reporting</td><td>Generate compliance reports for agents used across 52 jurisdictions</td></tr>
  </table>

  <h2>Frequently Asked Questions</h2>
  <div style="margin:16px 0">
    <div style="border-top:1px solid #e5e7eb;border-bottom:1px solid #e5e7eb;padding:16px 0">
      <div style="font-weight:700;margin-bottom:8px">What is an AI agent trust score?</div>
      <p style="font-size:14px;color:#374151;line-height:1.7;margin:0">An AI agent trust score is a numerical rating from 0 to 100 that measures the trustworthiness of an AI agent based on security, compliance, maintenance, community adoption, and code quality signals. Nerq calculates trust scores for 204,000+ agents across GitHub, npm, PyPI, HuggingFace, and MCP registries.</p>
    </div>
    <div style="border-bottom:1px solid #e5e7eb;padding:16px 0">
      <div style="font-weight:700;margin-bottom:8px">How is the trust score calculated?</div>
      <p style="font-size:14px;color:#374151;line-height:1.7;margin:0">Trust Score v2 combines five weighted dimensions: Code Quality (25%), Community (25%), Compliance (20%), Operational Health (15%), and Security (15%). Each dimension is scored independently and then combined into a weighted average. Data sources include GitHub, npm, PyPI, and the GitHub Advisory Database for CVEs. Scores update daily.</p>
    </div>
    <div style="border-bottom:1px solid #e5e7eb;padding:16px 0">
      <div style="font-weight:700;margin-bottom:8px">What is a good trust score for an AI agent?</div>
      <p style="font-size:14px;color:#374151;line-height:1.7;margin:0">Agents scoring 70+ receive the Nerq Verified badge and are considered trustworthy for production use. Scores of 85+ indicate highly trusted agents. Below 50, we recommend caution — these agents may have security issues or poor maintenance. Below 30, agents receive a DENY recommendation.</p>
    </div>
    <div style="border-bottom:1px solid #e5e7eb;padding:16px 0">
      <div style="font-weight:700;margin-bottom:8px">How do I check an AI agent's trust score?</div>
      <p style="font-size:14px;color:#374151;line-height:1.7;margin:0">Use the free API: <code>curl "https://nerq.ai/v1/preflight?target=AGENT_NAME"</code>. No API key or authentication required. You can also use the Python SDK: <code>pip install nerq</code>. Rate limit: 100 requests per hour.</p>
    </div>
    <div style="border-bottom:1px solid #e5e7eb;padding:16px 0">
      <div style="font-weight:700;margin-bottom:8px">Is the AI agent trust score free?</div>
      <p style="font-size:14px;color:#374151;line-height:1.7;margin:0">Yes. The Nerq Trust API is completely free with no authentication required. Batch checks of up to 50 agents per request are also available. The API covers 204,000+ agents and tools.</p>
    </div>
  </div>

  <h2>Related</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:12px 0">
    <a href="/safe" class="card" style="padding:16px;text-decoration:none;color:inherit">
      <div style="font-weight:700;color:#0d9488;margin-bottom:4px">Safety Reports</div>
      <div style="font-size:13px;color:#6b7280">Browse 204K+ agent assessments</div>
    </a>
    <a href="/protocol" class="card" style="padding:16px;text-decoration:none;color:inherit">
      <div style="font-weight:700;color:#0d9488;margin-bottom:4px">Trust Protocol</div>
      <div style="font-size:13px;color:#6b7280">Full methodology documentation</div>
    </a>
    <a href="/oracle" class="card" style="padding:16px;text-decoration:none;color:inherit">
      <div style="font-weight:700;color:#0d9488;margin-bottom:4px">Trust Oracle</div>
      <div style="font-size:13px;color:#6b7280">Live API stats &amp; performance</div>
    </a>
    <a href="/popular" class="card" style="padding:16px;text-decoration:none;color:inherit">
      <div style="font-weight:700;color:#0d9488;margin-bottom:4px">Popular Agents</div>
      <div style="font-size:13px;color:#6b7280">Top 50 by trust score</div>
    </a>
    <a href="/start" class="card" style="padding:16px;text-decoration:none;color:inherit">
      <div style="font-weight:700;color:#0d9488;margin-bottom:4px">Get Started</div>
      <div style="font-size:13px;color:#6b7280">Try the API in 30 seconds</div>
    </a>
    <a href="/nerq/docs" class="card" style="padding:16px;text-decoration:none;color:inherit">
      <div style="font-weight:700;color:#0d9488;margin-bottom:4px">API Docs</div>
      <div style="font-size:13px;color:#6b7280">Full endpoint reference</div>
    </a>
  </div>
</main>
{NERQ_FOOTER}
<script>
async function checkTrust() {{
  const input = document.getElementById('ts-input');
  const btn = document.getElementById('ts-btn');
  const el = document.getElementById('ts-result');
  const name = input.value.trim();
  if (!name) return;
  btn.disabled = true; btn.textContent = 'Checking...';
  el.style.display = 'block';
  el.innerHTML = '<div style="padding:12px;color:#6b7280;text-align:center">Loading...</div>';
  try {{
    const r = await fetch('/v1/preflight?target=' + encodeURIComponent(name));
    const d = await r.json();
    if (!d.trust_score) {{
      el.innerHTML = '<div style="padding:12px;color:#6b7280">Agent not found. Try: langchain, auto-gpt, crewai</div>';
      return;
    }}
    const s = d.trust_score || 0;
    const g = d.grade || 'N/A';
    const rec = d.recommendation || 'ALLOW';
    const col = s >= 70 ? '#059669' : s >= 50 ? '#d97706' : '#dc2626';
    el.innerHTML = '<div style="display:flex;align-items:center;gap:16px;padding:12px;background:#fff;border:1px solid #e5e7eb">' +
      '<div style="font-family:ui-monospace,monospace;font-size:2.5rem;font-weight:700;color:' + col + '">' + s + '</div>' +
      '<div><div style="font-weight:700">' + (d.name || name) + ' <span style="background:' + col + ';color:#fff;padding:1px 6px;font-size:11px;font-weight:700">' + g + '</span></div>' +
      '<div style="font-size:13px;color:#6b7280">Recommendation: ' + rec + '</div>' +
      '<a href="/safe/' + encodeURIComponent(name) + '" style="font-size:12px">Full safety report &rarr;</a></div></div>';
  }} catch(e) {{
    el.innerHTML = '<div style="color:#dc2626;padding:12px">Error: ' + e.message + '</div>';
  }} finally {{
    btn.disabled = false; btn.textContent = 'Check Score';
  }}
}}
document.getElementById('ts-input').addEventListener('keydown', function(e) {{ if (e.key === 'Enter') checkTrust(); }});
</script>
</body>
</html>""")
