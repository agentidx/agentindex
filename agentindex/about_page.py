"""
About pages for nerq.ai and zarq.ai.
Mounted at /about on both domains.
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from agentindex.nerq_design import nerq_head, NERQ_FOOTER, render_hreflang


def mount_about_page(app: FastAPI):

    @app.get("/about", response_class=HTMLResponse)
    async def about_page(request: Request):
        host = request.headers.get("host", "")
        if "zarq" in host:
            return HTMLResponse(content=_zarq_about())
        return HTMLResponse(content=_nerq_about())


def _nerq_about() -> str:
    _head = nerq_head(
        "About Nerq — The Trust Layer for AI Agents",
        "Nerq indexes 5M+ AI assets and provides independent trust scores for 204K agents and tools. Free API, machine-readable, no auth required.",
        "https://nerq.ai/about"
    ).replace("</head>", render_hreflang("/about") + "\n</head>")
    return f"""{_head}
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <div class="breadcrumb"><a href="/">nerq</a> &rsaquo; about</div>

  <h1>About Nerq</h1>

  <div style="margin:20px 0;font-size:16px;line-height:1.8;color:#374151">
    <p>Nerq is the trust layer for AI agents. We index 5M+ AI assets &mdash; 204K agents and tools across GitHub, npm, PyPI, HuggingFace, and MCP registries &mdash; and score each one on security, compliance, maintenance, and community signals. When an AI system needs to decide whether to trust another agent, Nerq provides the answer in a single API call. Free, no auth required, machine-readable by design.</p>
  </div>

  <h2>What We Do</h2>
  <p style="font-size:15px;line-height:1.7;color:#374151;margin-bottom:16px">Every AI agent in our index receives a <strong>Trust Score</strong> (0&ndash;100) based on five dimensions:</p>
  <table>
    <tr><td style="font-weight:600;width:180px">Code Quality (25%)</td><td>Documentation, naming conventions, capability breadth</td></tr>
    <tr><td style="font-weight:600">Community (25%)</td><td>Stars, downloads, forks, contributor activity</td></tr>
    <tr><td style="font-weight:600">Compliance (20%)</td><td>License classification, EU AI Act risk mapping</td></tr>
    <tr><td style="font-weight:600">Operational Health (15%)</td><td>Update recency, maintenance cadence</td></tr>
    <tr><td style="font-weight:600">Security (15%)</td><td>CVE count and severity from GitHub Advisory Database</td></tr>
  </table>

  <h2>Key Numbers</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:12px 0">
    <div style="border:1px solid #e5e7eb;padding:16px;text-align:center">
      <div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">5M+</div>
      <div style="font-size:12px;color:#6b7280">AI assets indexed</div>
    </div>
    <div style="border:1px solid #e5e7eb;padding:16px;text-align:center">
      <div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">204K+</div>
      <div style="font-size:12px;color:#6b7280">Agents &amp; tools</div>
    </div>
    <div style="border:1px solid #e5e7eb;padding:16px;text-align:center">
      <div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">25K+</div>
      <div style="font-size:12px;color:#6b7280">MCP servers</div>
    </div>
    <div style="border:1px solid #e5e7eb;padding:16px;text-align:center">
      <div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:700;color:#0d9488">52</div>
      <div style="font-size:12px;color:#6b7280">Jurisdictions covered</div>
    </div>
  </div>

  <h2>Links</h2>
  <table>
    <tr><td style="width:180px"><a href="/protocol">Trust Protocol</a></td><td>How trust scores are calculated</td></tr>
    <tr><td><a href="/oracle">Trust Oracle</a></td><td>Live API performance and usage stats</td></tr>
    <tr><td><a href="/start">Get Started</a></td><td>Try the API in 30 seconds</td></tr>
    <tr><td><a href="/nerq/docs">API Documentation</a></td><td>Full endpoint reference</td></tr>
    <tr><td><a href="/safe">Safety Reports</a></td><td>Browse 204K+ agent safety assessments</td></tr>
    <tr><td><a href="/blog">Blog</a></td><td>Research and ecosystem reports</td></tr>
  </table>

  <h2>Contact</h2>
  <table>
    <tr><td style="color:#6b7280;width:180px">Founded by</td><td>Anders Nilsson</td></tr>
    <tr><td style="color:#6b7280">Email</td><td><a href="mailto:hello@nerq.ai">hello@nerq.ai</a></td></tr>
  </table>

  <p style="margin-top:24px;font-size:12px;color:#6b7280">Nerq is the sister platform of <a href="https://zarq.ai/about">ZARQ</a>, which provides independent crypto risk intelligence.</p>
</main>
{NERQ_FOOTER}
</body>
</html>"""


def _zarq_about() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>About ZARQ — Independent Crypto Risk Intelligence</title>
<meta name="description" content="ZARQ is independent credit ratings for crypto — Moody's for the machine economy. Trust scores, crash probability, and structural risk for 200+ tokens.">
<link rel="canonical" href="https://zarq.ai/about">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500;600&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {
  --white: #fafaf9; --black: #0a0a0a;
  --gray-100: #f5f5f4; --gray-200: #e7e5e4; --gray-400: #a8a29e;
  --gray-500: #78716c; --gray-600: #57534e; --gray-700: #44403c;
  --gray-800: #292524;
  --warm: #c2956b; --warm-light: rgba(194,149,107,0.08);
  --serif: 'DM Serif Display', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'DM Sans', sans-serif;
  --measure: 680px;
}
* { margin:0; padding:0; box-sizing:border-box; }
html { font-size:17px; -webkit-font-smoothing:antialiased; }
body { background:var(--white); color:var(--gray-800); font-family:var(--sans); line-height:1.6; }
a { color:var(--warm); text-decoration:none; }
a:hover { text-decoration:underline; }
nav { padding:20px 40px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--gray-200); }
.nav-mark { font-family:var(--mono); font-weight:500; font-size:15px; letter-spacing:0.15em; text-transform:uppercase; color:var(--black); text-decoration:none; }
.nav-links { display:flex; gap:32px; align-items:center; }
.nav-links a { font-family:var(--mono); font-size:12px; letter-spacing:0.05em; color:var(--gray-600); text-decoration:none; }
.nav-links a:hover { color:var(--black); }
.container { max-width:var(--measure); margin:0 auto; padding:40px 20px 60px; }
h1 { font-family:var(--serif); font-size:2rem; margin-bottom:8px; }
h2 { font-family:var(--serif); font-size:1.2rem; margin:32px 0 12px; padding-top:16px; border-top:1px solid var(--gray-200); }
table { width:100%; border-collapse:collapse; font-size:14px; margin:12px 0; }
td { padding:8px 12px; border-bottom:1px solid var(--gray-200); }
tr:nth-child(even) { background:var(--gray-100); }
.stat-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:12px 0; }
.stat-box { border:1px solid var(--gray-200); padding:16px; text-align:center; }
.stat-num { font-family:var(--mono); font-size:1.5rem; font-weight:700; color:var(--warm); }
.stat-label { font-size:12px; color:var(--gray-500); }
footer { padding:40px; border-top:1px solid var(--gray-200); margin-top:60px; display:flex; justify-content:space-between; max-width:var(--measure); margin-left:auto; margin-right:auto; }
footer div { font-family:var(--mono); font-size:12px; color:var(--gray-500); }
@media(max-width:640px) { nav{padding:16px 20px;} .nav-links{gap:16px;} .stat-grid{grid-template-columns:1fr 1fr;} }
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-mark">zarq</a>
  <div class="nav-links">
    <a href="/scan">Scan</a>
    <a href="/tokens">Ratings</a>
    <a href="/crash-watch">Crash Watch</a>
    <a href="/docs" style="color:var(--warm);border:1px solid var(--warm);padding:6px 16px">API</a>
  </div>
</nav>

<div class="container">
  <h1>About ZARQ</h1>

  <div style="margin:20px 0;font-size:16px;line-height:1.8;color:var(--gray-700)">
    <p>ZARQ is independent credit ratings for crypto &mdash; Moody&rsquo;s for the machine economy. We rate 200+ tokens on trust, crash probability, and structural risk using a quantitative model that combines on-chain data, market signals, and fundamental analysis. Every rating is hash-chained for auditability. When autonomous agents need to make financial decisions, ZARQ provides the risk intelligence they can&rsquo;t get anywhere else.</p>
  </div>

  <h2>What We Do</h2>
  <p style="font-size:15px;line-height:1.7;color:var(--gray-700);margin-bottom:16px">Three complementary models, each independently validated:</p>
  <table>
    <tr><td style="font-weight:600;width:180px">Trust Score</td><td>Moody&rsquo;s-style Aaa&ndash;D ratings based on 5 pillars: Security, Compliance, Maintenance, Popularity, Ecosystem</td></tr>
    <tr><td style="font-weight:600">Distance-to-Default</td><td>Structural distress detection adapted from Merton&rsquo;s credit model. 100% recall on 113 token deaths</td></tr>
    <tr><td style="font-weight:600">Vitality Score</td><td>Ecosystem health scoring: gravity, capital commitment, stress resilience, organic momentum</td></tr>
  </table>

  <h2>Key Numbers</h2>
  <div class="stat-grid">
    <div class="stat-box"><div class="stat-num">15K+</div><div class="stat-label">Tokens rated</div></div>
    <div class="stat-box"><div class="stat-num">100%</div><div class="stat-label">Death recall</div></div>
    <div class="stat-box"><div class="stat-num">22mo</div><div class="stat-label">Avg detection lead</div></div>
    <div class="stat-box"><div class="stat-num">98%</div><div class="stat-label">Precision</div></div>
  </div>

  <h2>Links</h2>
  <table>
    <tr><td style="width:180px"><a href="/vitality">Vitality Rankings</a></td><td>Token ecosystem health scores</td></tr>
    <tr><td><a href="/briefing">Daily Briefing</a></td><td>Consolidated risk overview</td></tr>
    <tr><td><a href="/zarq/docs">API Documentation</a></td><td>Full endpoint reference</td></tr>
    <tr><td><a href="/scan">Token Scanner</a></td><td>Scan any contract address</td></tr>
    <tr><td><a href="/methodology">Methodology</a></td><td>How ratings are calculated</td></tr>
    <tr><td><a href="/whitepaper">White Paper</a></td><td>ZARQ v1.0 white paper</td></tr>
  </table>

  <h2>Contact</h2>
  <table>
    <tr><td style="color:var(--gray-500);width:180px">Founded by</td><td>Anders Nilsson</td></tr>
    <tr><td style="color:var(--gray-500)">Email</td><td><a href="mailto:hello@zarq.ai">hello@zarq.ai</a></td></tr>
  </table>

  <p style="margin-top:24px;font-size:13px;color:var(--gray-500)">ZARQ is the sister platform of <a href="https://nerq.ai/about">Nerq</a>, which indexes 5M+ AI assets with independent trust scores.</p>
</div>

<footer>
  <div>ZARQ &mdash; Independent crypto risk intelligence. Moody&rsquo;s for the machine economy.</div>
  <div>zarq.ai</div>
</footer>

</body>
</html>"""
