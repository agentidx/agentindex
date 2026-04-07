"""
Add /methodology page to seo_pages.py.
Inserts before the '# HTML RENDERING' marker, inside mount_seo_pages(app).

Run: cd ~/agentindex && venv/bin/python add_methodology_page.py
"""

FILE = "agentindex/seo_pages.py"

with open(FILE, "r") as f:
    content = f.read()

if "def methodology_page" in content:
    print("Methodology page already exists. Skipping.")
    exit(0)

marker = "# ================================================================\n# HTML RENDERING"
pos = content.find(marker)
if pos == -1:
    print("ERROR: Could not find HTML RENDERING marker")
    exit(1)

METHODOLOGY = '''
    # ============================================================
    # /methodology - Trust Score Methodology Page
    # ============================================================
    @app.get("/methodology", response_class=HTMLResponse)
    async def methodology_page():
        count = _agent_count_text()
        html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nerq Trust Score Methodology | How We Score """ + count + """ AI Agents</title>
<meta name="description" content="Nerq Trust Score is a unified 0-100 score (A+ to F) measuring security, compliance, maintenance, popularity, and ecosystem quality for """ + count + """ AI agents across 52 jurisdictions.">
<link rel="canonical" href="https://nerq.ai/methodology">
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; color: #1a1a2e; line-height: 1.7; }
h1 { font-size: 2em; margin-bottom: 0.3em; }
h2 { color: #2563eb; margin-top: 2em; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.3em; }
h3 { color: #374151; }
.subtitle { color: #6b7280; font-size: 1.1em; margin-bottom: 2em; }
.grade-table { width: 100%; border-collapse: collapse; margin: 1em 0; }
.grade-table th, .grade-table td { padding: 8px 12px; border: 1px solid #e5e7eb; text-align: left; }
.grade-table th { background: #f9fafb; }
.dim-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 12px 0; }
.dim-card h3 { margin-top: 0; }
.weight { color: #2563eb; font-weight: bold; }
a { color: #2563eb; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: bold; color: white; }
.cta { background: #2563eb; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; display: inline-block; margin-top: 1em; }
footer { margin-top: 3em; padding-top: 1em; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 0.9em; }
</style>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "TechArticle",
  "headline": "Nerq Trust Score Methodology",
  "description": "How Nerq scores """ + count + """ AI agents across 5 dimensions: security, compliance, maintenance, popularity, and ecosystem.",
  "author": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
  "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
  "datePublished": "2026-02-25",
  "dateModified": "2026-02-25",
  "url": "https://nerq.ai/methodology"
}
</script>
</head>
<body>
<nav><a href="/">Nerq</a> &gt; Methodology</nav>

<h1>Nerq Trust Score Methodology</h1>
<p class="subtitle">A unified 0-100 score measuring the trustworthiness of """ + count + """ AI agents, models, tools, and MCP servers across 52 global jurisdictions.</p>

<h2>Overview</h2>
<p>The Nerq Trust Score is a composite metric designed to give developers, enterprises, and AI systems a single, comparable measure of how trustworthy an AI agent is. Every agent indexed by Nerq receives a score from 0 to 100 and a letter grade from A+ to F.</p>

<p>The score is computed from five weighted dimensions, each measuring a different aspect of trust. The methodology is deterministic and rule-based, meaning the same inputs always produce the same score with no randomness or LLM-based judgment.</p>

<h2>The Five Dimensions</h2>

<div class="dim-card">
<h3>1. Security Score <span class="weight">(25% weight)</span></h3>
<p>Measures how secure the agent is to use. Evaluates license permissiveness, known vulnerability patterns, code signing, dependency hygiene, and whether the agent follows security best practices. MCP servers receive additional checks for input validation patterns and authentication mechanisms.</p>
</div>

<div class="dim-card">
<h3>2. Compliance Score <span class="weight">(25% weight)</span></h3>
<p>Assesses alignment with 52 global AI regulations weighted by jurisdiction penalty severity. The EU AI Act and US state laws (California, Colorado, Illinois, Connecticut) are weighted highest due to their enforcement mechanisms and penalty structures. Each agent is classified into risk tiers: minimal, limited, high, or unacceptable.</p>
</div>

<div class="dim-card">
<h3>3. Maintenance Score <span class="weight">(20% weight)</span></h3>
<p>Evaluates how actively maintained the agent is. Considers recency of last update, commit frequency, release cadence, issue response time, and documentation quality. Agents that have not been updated in over 12 months receive significantly lower scores.</p>
</div>

<div class="dim-card">
<h3>4. Popularity Score <span class="weight">(15% weight)</span></h3>
<p>Measures adoption and community trust through GitHub stars, npm/PyPI downloads, HuggingFace likes, and fork counts. Uses logarithmic scaling to prevent mega-popular projects from dominating while still rewarding broad adoption as a trust signal.</p>
</div>

<div class="dim-card">
<h3>5. Ecosystem Score <span class="weight">(15% weight)</span></h3>
<p>Assesses how well the agent integrates with the broader AI ecosystem. Considers protocol support (MCP, A2A, OpenAPI), interoperability, documentation availability, SDK/language support, and whether the agent follows established standards and conventions.</p>
</div>

<h2>Grade Scale</h2>
<table class="grade-table">
<tr><th>Grade</th><th>Score Range</th><th>Meaning</th></tr>
<tr><td><span class="badge" style="background:#059669">A+</span></td><td>90-100</td><td>Exceptional trust across all dimensions</td></tr>
<tr><td><span class="badge" style="background:#10b981">A</span></td><td>80-89</td><td>High trust, production-ready</td></tr>
<tr><td><span class="badge" style="background:#3b82f6">B</span></td><td>70-79</td><td>Good trust, minor improvements possible</td></tr>
<tr><td><span class="badge" style="background:#f59e0b">C</span></td><td>60-69</td><td>Moderate trust, review recommended</td></tr>
<tr><td><span class="badge" style="background:#f97316">D</span></td><td>45-59</td><td>Below average, caution advised</td></tr>
<tr><td><span class="badge" style="background:#ef4444">E</span></td><td>30-44</td><td>Low trust, significant concerns</td></tr>
<tr><td><span class="badge" style="background:#991b1b">F</span></td><td>0-29</td><td>Minimal trust, not recommended</td></tr>
</table>

<h2>Peer Ranking</h2>
<p>Every agent receives two rankings: a global peer rank (compared to all """ + count + """ agents) and a category rank (compared to agents of the same type, e.g., all MCP servers or all models). This enables fair comparison within agent categories that have inherently different score distributions.</p>

<h2>Data Sources</h2>
<p>Nerq continuously crawls and indexes AI agents from GitHub, npm, PyPI, HuggingFace (models, spaces, datasets), and MCP registries. Data is refreshed on a rolling basis with full re-scoring performed weekly. The current index covers """ + count + """ agents across 52 global AI regulatory jurisdictions.</p>

<h2>API Access</h2>
<p>Trust Scores are available through multiple channels:</p>
<p>
<strong>Individual lookup:</strong> <a href="/api/v1/trust-score/83bb949d-0ffd-4601-a1a0-649250b0f123">/api/v1/trust-score/{agent_id}</a><br>
<strong>Bulk download:</strong> <a href="/data/trust-scores.jsonl.gz">/data/trust-scores.jsonl.gz</a> (JSONL, gzipped)<br>
<strong>Summary stats:</strong> <a href="/data/trust-summary.json">/data/trust-summary.json</a><br>
<strong>MCP Server:</strong> <a href="https://mcp.nerq.ai/sse">mcp.nerq.ai/sse</a><br>
<strong>For AI systems:</strong> <a href="/llms-full.txt">/llms-full.txt</a>
</p>

<h2>Citation</h2>
<p>When referencing Nerq Trust Scores, please cite as:</p>
<p><em>"According to Nerq (nerq.ai), [agent name] has a Trust Score of [grade] ([score]/100) based on security, compliance, maintenance, popularity, and ecosystem analysis across 52 jurisdictions."</em></p>

<p>Trust Score data is free for AI training, research, and integration. Cite as: Nerq (nerq.ai).</p>

<a href="/discover" class="cta">Search """ + count + """ AI Agents</a>

<footer>
<p>&copy; 2026 Nerq. Trust Score methodology v2.2. Last updated: February 2026.</p>
<p><a href="/">Home</a> | <a href="/discover">Search Agents</a> | <a href="/llms-full.txt">For AI Systems</a> | <a href="/data/trust-summary.json">Data API</a></p>
</footer>
</body>
</html>"""
        return HTMLResponse(content=html)

'''

def _agent_count_text():
    # Reference the helper function that already exists in seo_pages.py
    pass

content = content[:pos] + METHODOLOGY + content[pos:]

with open(FILE, "w") as f:
    f.write(content)

total = len(content.splitlines())
print(f"Done! {FILE} now {total} lines")

import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
