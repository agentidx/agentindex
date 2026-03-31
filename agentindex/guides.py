"""
Developer guides -- /guides, /guides/langchain, /guides/crewai, /guides/mcp, /guides/autogen, /guides/getting-started
Comprehensive framework-specific guides with Nerq integration examples.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router_guides = APIRouter()

# ── Shared HTML fragments ────────────────────────────────────

_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="https://nerq.ai{path}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="https://nerq.ai{path}">
<meta property="og:type" content="article">
{extra_head}
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,sans-serif;color:#1a1a1a;background:#fff;line-height:1.7;font-size:15px}}
a{{color:#0d9488;text-decoration:none}}a:hover{{color:#0f766e}}
code,pre{{font-family:ui-monospace,'SF Mono','JetBrains Mono',monospace}}
code{{background:#f5f5f5;padding:1px 5px;font-size:0.88em}}
pre{{background:#1a1a1a;color:#e5e7eb;padding:16px;overflow-x:auto;font-size:13px;line-height:1.5;margin:12px 0;position:relative}}
nav{{border-bottom:1px solid #e5e7eb;padding:12px 0}}
nav .inner{{max-width:760px;margin:0 auto;padding:0 20px;display:flex;align-items:center;justify-content:space-between}}
nav .logo{{font-weight:700;font-size:1.1rem;color:#0d9488;text-decoration:none}}
nav .links{{display:flex;gap:20px;font-size:14px}}
nav .links a{{color:#6b7280}}nav .links a:hover{{color:#0d9488}}
.container{{max-width:760px;margin:0 auto;padding:40px 20px 60px}}
h1{{font-size:1.8rem;font-weight:800;margin-bottom:8px;letter-spacing:-0.02em}}
h2{{font-size:1.2rem;font-weight:700;margin:32px 0 12px;padding-top:20px;border-top:1px solid #f3f4f6}}
h3{{font-size:1rem;font-weight:600;margin:20px 0 8px}}
.subtitle{{color:#6b7280;font-size:14px;margin-bottom:24px}}
.tip{{background:#f0fdfa;border-left:3px solid #0d9488;padding:12px 16px;margin:16px 0;font-size:14px}}
.warn{{background:#fffbeb;border-left:3px solid #d97706;padding:12px 16px;margin:16px 0;font-size:14px}}
ul,ol{{margin:8px 0 8px 24px}}li{{margin:4px 0}}
.checklist{{list-style:none;margin-left:0}}
.checklist li::before{{content:'\\2713 ';color:#0d9488;font-weight:700;margin-right:4px}}
.breadcrumb{{font-size:13px;color:#9ca3af;margin-bottom:16px}}
.breadcrumb a{{color:#9ca3af}}
footer{{border-top:1px solid #e5e7eb;padding:20px 0;margin-top:40px;font-size:13px;color:#6b7280}}
footer .inner{{max-width:760px;margin:0 auto;padding:0 20px}}
.cta{{display:inline-block;padding:10px 24px;background:#0d9488;color:#fff;font-weight:600;font-size:14px;margin:8px 4px 8px 0}}
.cta:hover{{background:#0f766e;color:#fff}}
.cta-outline{{display:inline-block;padding:10px 24px;border:1px solid #0d9488;color:#0d9488;font-size:14px;margin:8px 4px 8px 0}}
</style>
</head>
<body>
<nav><div class="inner">
<a href="/" class="logo">nerq</a>
<div class="links">
<a href="/discover">search</a>
<a href="/gateway">gateway</a>
<a href="/guides">guides</a>
<a href="/start">api</a>
<a href="/nerq/docs">docs</a>
</div>
</div></nav>
<div class="container">
"""

_FOOT = """
</div>
<footer><div class="inner">
nerq &mdash; the trust layer for AI agents &middot;
<a href="/guides">guides</a> &middot;
<a href="/gateway">gateway</a> &middot;
<a href="/start">api</a> &middot;
<a href="/nerq/docs">docs</a>
</div></footer>
</body></html>
"""

def _faq_schema(pairs):
    import json
    items = []
    for q, a in pairs:
        items.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}})
    return '<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage", "mainEntity": items
    }) + '</script>'


# ── /guides hub ──────────────────────────────────────────────

@router_guides.get("/guides", response_class=HTMLResponse, include_in_schema=False)
async def guides_hub():
    faq = _faq_schema([
        ("How do I get started with Nerq?", "Visit nerq.ai/guides/getting-started to choose your path: building agents, MCP servers, or using the API directly."),
        ("Which frameworks does Nerq support?", "Nerq integrates with LangChain, CrewAI, AutoGen, LlamaIndex, and any framework via the REST API. See nerq.ai/guides for framework-specific guides."),
    ])
    return _HEAD.format(
        title="Nerq Developer Guides -- Build Secure AI Agents",
        description="Framework-specific guides for building trust-verified AI agents with Nerq. LangChain, CrewAI, MCP, AutoGen.",
        path="/guides",
        extra_head=faq,
    ) + """
<p class="breadcrumb"><a href="/">nerq</a> / guides</p>
<h1>Developer Guides</h1>
<p class="subtitle">Build trust-verified AI agents with your framework of choice.</p>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:24px 0">

<a href="/guides/getting-started" style="border:2px solid #0d9488;padding:20px;text-decoration:none;color:inherit;display:block">
<h3 style="color:#0d9488;margin:0 0 6px">Getting Started</h3>
<p style="font-size:13px;color:#6b7280;margin:0">Choose your path. 3 lines of code to get started.</p>
</a>

<a href="/guides/langchain" style="border:1px solid #e5e7eb;padding:20px;text-decoration:none;color:inherit;display:block">
<h3 style="margin:0 0 6px">LangChain Guide</h3>
<p style="font-size:13px;color:#6b7280;margin:0">Dynamic tool discovery and trust gating for LangChain agents.</p>
</a>

<a href="/guides/crewai" style="border:1px solid #e5e7eb;padding:20px;text-decoration:none;color:inherit;display:block">
<h3 style="margin:0 0 6px">CrewAI Guide</h3>
<p style="font-size:13px;color:#6b7280;margin:0">Trust-verified crew members and tool selection.</p>
</a>

<a href="/guides/mcp" style="border:1px solid #e5e7eb;padding:20px;text-decoration:none;color:inherit;display:block">
<h3 style="margin:0 0 6px">MCP Server Guide</h3>
<p style="font-size:13px;color:#6b7280;margin:0">Build trusted MCP servers. Get discovered by 25K+ users.</p>
</a>

<a href="/guides/autogen" style="border:1px solid #e5e7eb;padding:20px;text-decoration:none;color:inherit;display:block">
<h3 style="margin:0 0 6px">AutoGen Guide</h3>
<p style="font-size:13px;color:#6b7280;margin:0">Trust-verified tool registration for AutoGen agents.</p>
</a>

<a href="/templates" style="border:1px solid #e5e7eb;padding:20px;text-decoration:none;color:inherit;display:block">
<h3 style="margin:0 0 6px">Templates</h3>
<p style="font-size:13px;color:#6b7280;margin:0">Ready-to-use project templates for every framework.</p>
</a>

</div>

<h2>What is Nerq?</h2>
<p>Nerq is the trust layer for AI agents. It indexes 204K+ agents and tools with trust scores based on security, maintenance, popularity, license compliance, and ecosystem health. One API call to check any agent or find the best tool for any task.</p>

<h2>Core APIs</h2>
<table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0">
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb"><code>GET /v1/resolve?task=...</code></td><td style="padding:8px;border-bottom:1px solid #e5e7eb">Find the best tool for a task</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb"><code>GET /v1/preflight?target=...</code></td><td style="padding:8px;border-bottom:1px solid #e5e7eb">Trust-check any agent</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #e5e7eb"><code>POST /v1/discover</code></td><td style="padding:8px;border-bottom:1px solid #e5e7eb">Search 204K+ agents</td></tr>
</table>

<div style="margin-top:24px">
<a href="/guides/getting-started" class="cta">Get Started</a>
<a href="/gateway" class="cta-outline">Install Gateway</a>
</div>
""" + _FOOT


# ── /guides/getting-started ──────────────────────────────────

@router_guides.get("/guides/getting-started", response_class=HTMLResponse, include_in_schema=False)
async def guide_getting_started():
    faq = _faq_schema([
        ("What is Nerq?", "Nerq is the trust layer for AI agents. It indexes 204K+ agents with trust scores and provides APIs for trust verification and tool discovery."),
        ("What is a Trust Score?", "A 0-100 score based on 5 pillars: Security (30%), Maintenance (20%), Popularity (15%), License Compliance (25%), and Ecosystem Health (10%). Scores map to grades A+ through F."),
        ("Is Nerq free?", "Yes. The API is free, no authentication required. Rate limits apply for high-volume usage."),
    ])
    return _HEAD.format(
        title="Getting Started with Nerq -- Trust Verification for AI Agents",
        description="Get started with Nerq in 30 seconds. Choose your path: building agents, MCP servers, or checking tool safety.",
        path="/guides/getting-started",
        extra_head=faq,
    ) + """
<p class="breadcrumb"><a href="/">nerq</a> / <a href="/guides">guides</a> / getting-started</p>
<h1>Getting Started with Nerq</h1>
<p class="subtitle">Choose your path. Get started in under 30 seconds.</p>

<h2>Choose Your Path</h2>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0">
<div style="border:1px solid #e5e7eb;padding:16px">
<h3>I'm building an agent</h3>
<p style="font-size:13px;color:#6b7280;margin:8px 0">Add dynamic tool discovery and trust checks.</p>
<pre style="font-size:12px">pip install nerq
import nerq
tool = nerq.resolve("code review")</pre>
<p style="font-size:13px;margin-top:8px"><a href="/guides/langchain">LangChain guide</a> &middot; <a href="/guides/crewai">CrewAI guide</a> &middot; <a href="/guides/autogen">AutoGen guide</a></p>
</div>

<div style="border:1px solid #e5e7eb;padding:16px">
<h3>I'm building an MCP server</h3>
<p style="font-size:13px;color:#6b7280;margin:8px 0">Get discovered. Get a high trust score.</p>
<pre style="font-size:12px">npx mcp-hub search "my-server"
curl nerq.ai/v1/preflight?target=my-server</pre>
<p style="font-size:13px;margin-top:8px"><a href="/guides/mcp">MCP server guide</a></p>
</div>

<div style="border:1px solid #e5e7eb;padding:16px">
<h3>I want to check if a tool is safe</h3>
<p style="font-size:13px;color:#6b7280;margin:8px 0">One call to check any agent or tool.</p>
<pre style="font-size:12px">curl nerq.ai/v1/preflight?target=langchain
# Trust: 87, Grade: A, ALLOW</pre>
<p style="font-size:13px;margin-top:8px"><a href="/start">API quick start</a></p>
</div>

<div style="border:1px solid #e5e7eb;padding:16px">
<h3>I want all tools in one place</h3>
<p style="font-size:13px;color:#6b7280;margin:8px 0">Zero-config access to 25,000+ MCP servers.</p>
<pre style="font-size:12px">npx mcp-hub install github-mcp-server
# or add nerq-gateway to Claude Desktop</pre>
<p style="font-size:13px;margin-top:8px"><a href="/gateway">Install gateway</a></p>
</div>
</div>

<h2>What is Nerq?</h2>
<p>Nerq indexes 204K+ AI agents, tools, and MCP servers with trust scores. Think of it as a credit rating for software: every agent gets a 0-100 score based on security, maintenance, popularity, license compliance, and ecosystem health.</p>
<p style="margin-top:8px">The API is free and requires no authentication. Use it to verify agents before trusting them, find the best tool for any task, or scan your dependencies for security issues.</p>

<h2>What is a Trust Score?</h2>
<p>A 0-100 composite score based on five pillars:</p>
<ul>
<li><strong>Security (30%)</strong> -- Known CVEs, vulnerability history, secure development practices</li>
<li><strong>License Compliance (25%)</strong> -- SPDX license, commercial friendliness</li>
<li><strong>Maintenance (20%)</strong> -- Update frequency, issue response time, active development</li>
<li><strong>Popularity (15%)</strong> -- Stars, downloads, community adoption</li>
<li><strong>Ecosystem Health (10%)</strong> -- Framework compatibility, integration quality</li>
</ul>
<p style="margin-top:8px">Scores map to letter grades: A+ (90+), A (80+), B (70+), C (60+), D (40+), F (&lt;40).</p>

<h2>Core APIs</h2>

<h3>Resolve -- Find the best tool for a task</h3>
<pre>curl "https://nerq.ai/v1/resolve?task=search+github+repos"
# Returns: github/github-mcp-server (Trust: 83, Grade: A)</pre>

<h3>Preflight -- Trust-check any agent</h3>
<pre>curl "https://nerq.ai/v1/preflight?target=langchain"
# Returns: trust_score, grade, recommendation, CVEs, alternatives</pre>

<h3>Search -- Find agents by keyword</h3>
<pre>curl "https://nerq.ai/v1/search?q=database&min_trust=70"
# Returns: ranked list of matching agents</pre>

<div style="margin-top:24px">
<a href="/guides/langchain" class="cta">LangChain Guide</a>
<a href="/guides/mcp" class="cta-outline">MCP Server Guide</a>
<a href="/gateway" class="cta-outline">Install Gateway</a>
</div>
""" + _FOOT


# ── /guides/langchain ────────────────────────────────────────

@router_guides.get("/guides/langchain", response_class=HTMLResponse, include_in_schema=False)
async def guide_langchain():
    faq = _faq_schema([
        ("How do I make my LangChain agent secure?", "Use nerq.preflight() to trust-check every tool before use, nerq.resolve() for dynamic tool discovery, and agent-security in CI to scan dependencies on every PR."),
        ("How do I add trust verification to LangChain?", "pip install nerq, then use nerq.resolve(task, framework='langchain') to find trusted tools and nerq.preflight(name) to verify individual tools."),
        ("What is the best way to discover LangChain tools?", "Use nerq.resolve() to find the best tool for any task from 25,000+ indexed tools, filtered by trust score and framework compatibility."),
    ])
    return _HEAD.format(
        title="Building Secure LangChain Agents -- Complete Guide 2026 | Nerq",
        description="Complete guide to building secure LangChain agents with trust verification, dynamic tool discovery, and CI/CD integration.",
        path="/guides/langchain",
        extra_head=faq,
    ) + """
<p class="breadcrumb"><a href="/">nerq</a> / <a href="/guides">guides</a> / langchain</p>
<h1>Building Secure LangChain Agents</h1>
<p class="subtitle">Complete guide to trust verification, dynamic tool discovery, and CI/CD for LangChain. Updated March 2026.</p>

<h2>Why Trust Verification Matters</h2>
<p>LangChain agents can use arbitrary tools -- and most developers hardcode tool selections without checking if those tools are maintained, secure, or even still active. Of the 204K+ agents indexed by Nerq, only 18K meet the "verified" threshold (trust score 70+).</p>
<p style="margin-top:8px">Trust verification ensures your agent only uses tools that pass security, maintenance, and license checks. It takes one line of code and prevents supply chain attacks, abandoned dependencies, and license violations.</p>

<h2>Quick Start</h2>
<pre>pip install langchain langchain-openai nerq</pre>
<pre>import nerq

# Find the best tool for any task -- one call
tool = nerq.resolve("code review", framework="langchain", min_trust=70)
print(f"{tool['name']}: Trust {tool['trust_score']} ({tool['grade']})")

# Check trust for a specific tool
result = nerq.preflight("langchain")
print(f"Trust: {result['target_trust']} -- {result['recommendation']}")</pre>

<h2>Dynamic Tool Discovery</h2>
<p>Instead of hardcoding tools, use <code>nerq.resolve()</code> to find the best tool for each task at runtime:</p>
<pre>import nerq

def get_tools(tasks: list[str], min_trust: int = 70):
    # Dynamically discover trusted tools for a list of tasks.
    tools = []
    for task in tasks:
        result = nerq.resolve(task, framework="langchain", min_trust=min_trust)
        if result:
            print(f"  {task} -> {result['name']} (Trust: {result['trust_score']})")
            tools.append(result)
    return tools

# Usage
tools = get_tools(["code review", "web search", "database query"])
# code review -> github/github-mcp-server (Trust: 83)
# web search -> brave-search-mcp (Trust: 78)
# database query -> DB Connector (Trust: 74)</pre>

<div class="tip">
<strong>Why dynamic discovery?</strong> Tools get updated, deprecated, and replaced. A tool that was safe last month might have a new CVE today. Dynamic discovery always returns the current best option.
</div>

<h2>Trust Gating</h2>
<p>Block untrusted tools from being loaded:</p>
<pre>import nerq

def trust_gate(name: str, min_trust: int = 60):
    # Gate decorator -- blocks tools below trust threshold.
    result = nerq.preflight(name)
    trust = result.get("target_trust", 0)
    rec = result.get("recommendation", "UNKNOWN")

    if rec == "DENY" or trust < min_trust:
        raise RuntimeError(
            f"Blocked {name}: trust {trust} ({rec}). "
            f"Minimum required: {min_trust}"
        )
    print(f"  Allowed: {name} (trust {trust}, {rec})")
    return result

# Usage -- check before importing/using any tool
trust_gate("langchain")        # Passes (trust 87)
trust_gate("some-risky-tool")  # Raises RuntimeError</pre>

<h2>Full Agent Example</h2>
<pre>from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import nerq

load_dotenv()

def main():
    llm = ChatOpenAI(model="gpt-4o-mini")

    # 1. Discover tools dynamically
    print("Discovering tools...")
    code_tool = nerq.resolve("code review", min_trust=70)
    search_tool = nerq.resolve("web search", min_trust=70)

    tools_found = [t for t in [code_tool, search_tool] if t]
    print(f"Ready with {len(tools_found)} trust-verified tools.")

    for t in tools_found:
        print(f"  {t['name']}: Trust {t['trust_score']} ({t['grade']})")

    # 2. Use the LLM
    response = llm.invoke("Summarize the latest AI security news")
    print(response.content)

if __name__ == "__main__":
    main()</pre>

<h2>CI/CD Integration</h2>
<p>Add automated trust checking to every PR with <a href="https://github.com/agentic-index/agent-security">agent-security</a>:</p>
<pre># .github/workflows/trust-check.yml
name: Trust Check
on: [push, pull_request]
jobs:
  trust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install agent-security
      - run: agent-security scan requirements.txt --ci</pre>
<p>This will fail the build if any dependency has a critical trust issue (score &lt; 40 or DENY recommendation).</p>

<h2>Best Practices Checklist</h2>
<ul class="checklist">
<li>Use <code>nerq.resolve()</code> instead of hardcoding tool selections</li>
<li>Set <code>min_trust=70</code> or higher for production agents</li>
<li>Add <code>nerq.preflight()</code> checks before importing third-party tools</li>
<li>Use agent-security in CI to catch trust regressions</li>
<li>Add a Nerq trust badge to your README</li>
<li>Include <code>.well-known/agent.json</code> for machine discovery</li>
<li>Include <code>llms.txt</code> for AI-readable documentation</li>
<li>Keep dependencies updated -- trust scores decay with inactivity</li>
</ul>

<h2>Template</h2>
<p>Start from our ready-made template with all of this built in:</p>
<a href="/templates" class="cta">Use LangChain Template</a>
<a href="/gateway" class="cta-outline">Install Gateway</a>
""" + _FOOT


# ── /guides/crewai ───────────────────────────────────────────

@router_guides.get("/guides/crewai", response_class=HTMLResponse, include_in_schema=False)
async def guide_crewai():
    faq = _faq_schema([
        ("How do I make my CrewAI agent secure?", "Use nerq.resolve() to discover trusted tools for each crew member and nerq.preflight() to verify tools before assignment."),
        ("How do I add trust verification to CrewAI?", "pip install nerq, then call nerq.resolve(task, framework='crewai') when building your crew to ensure every tool is trust-verified."),
    ])
    return _HEAD.format(
        title="Building Secure CrewAI Agents -- Complete Guide 2026 | Nerq",
        description="Complete guide to building secure CrewAI agents with trust-verified crew members and dynamic tool discovery.",
        path="/guides/crewai",
        extra_head=faq,
    ) + """
<p class="breadcrumb"><a href="/">nerq</a> / <a href="/guides">guides</a> / crewai</p>
<h1>Building Secure CrewAI Agents</h1>
<p class="subtitle">Trust-verified crew members, dynamic tool discovery, and CI/CD for CrewAI. Updated March 2026.</p>

<h2>Quick Start</h2>
<pre>pip install crewai nerq</pre>
<pre>import nerq
from crewai import Agent, Task, Crew

# Find trusted tools for each crew role
code_tool = nerq.resolve("code review", framework="crewai", min_trust=70)
search_tool = nerq.resolve("web search", framework="crewai", min_trust=70)

# Build agents with verified tools
reviewer = Agent(
    role="Code Reviewer",
    goal="Review code for quality and security",
    backstory=f"Uses {code_tool['name']} (Trust: {code_tool['trust_score']})",
    tools=[]
)

researcher = Agent(
    role="Researcher",
    goal="Find relevant information",
    backstory=f"Uses {search_tool['name']} (Trust: {search_tool['trust_score']})",
    tools=[]
)</pre>

<h2>Trust-Verified Crew Builder</h2>
<p>Automate crew construction with trust verification:</p>
<pre>import nerq

def build_trusted_crew(roles: dict[str, str], min_trust: int = 70):
    # Build a crew where every tool is trust-verified.
    # Args: roles = {role_name: task_description}, min_trust = minimum trust score
    agents = []
    for role, task_desc in roles.items():
        tool = nerq.resolve(task_desc, framework="crewai", min_trust=min_trust)
        if not tool:
            print(f"  Warning: no trusted tool found for {role}")
            continue

        # Verify the tool passes preflight
        check = nerq.preflight(tool["name"])
        if check.get("recommendation") == "DENY":
            print(f"  Blocked: {tool['name']} (DENY)")
            continue

        agent = Agent(
            role=role,
            goal=task_desc,
            backstory=f"Specialist using {tool['name']} (Trust: {tool['trust_score']})",
        )
        agents.append(agent)
        print(f"  {role}: {tool['name']} (Trust: {tool['trust_score']})")

    return agents

# Usage
agents = build_trusted_crew({
    "Code Reviewer": "code review and security analysis",
    "Researcher": "web search and data gathering",
    "Analyst": "data analysis and visualization",
})</pre>

<h2>CI/CD Integration</h2>
<pre># .github/workflows/trust-check.yml
name: Trust Check
on: [push, pull_request]
jobs:
  trust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install agent-security
      - run: agent-security scan requirements.txt --ci</pre>

<h2>Best Practices</h2>
<ul class="checklist">
<li>Use <code>nerq.resolve()</code> for each crew member's tool selection</li>
<li>Set <code>min_trust=70</code> for production crews</li>
<li>Verify tools with <code>nerq.preflight()</code> before assignment</li>
<li>Add agent-security to your CI pipeline</li>
<li>Include <code>.well-known/agent.json</code> and <code>llms.txt</code></li>
</ul>

<a href="/templates" class="cta">Use CrewAI Template</a>
<a href="/guides/langchain" class="cta-outline">LangChain Guide</a>
""" + _FOOT


# ── /guides/mcp ──────────────────────────────────────────────

@router_guides.get("/guides/mcp", response_class=HTMLResponse, include_in_schema=False)
async def guide_mcp():
    faq = _faq_schema([
        ("How do I make my MCP server trusted?", "Add an MIT or Apache license, comprehensive README, keep dependencies updated, run security audits, add .well-known/agent.json, and add a Nerq trust badge to your README."),
        ("How do I get a high Nerq trust score?", "Focus on: MIT/Apache license (+25%), no CVEs (+30%), regular updates (+20%), 100+ GitHub stars (+15%), and framework compatibility (+10%)."),
        ("How do I distribute my MCP server?", "Publish to npm, register on Smithery and Glama, add to awesome-mcp-servers, ensure nerq-gateway compatibility, and add .well-known/agent.json for machine discovery."),
    ])
    return _HEAD.format(
        title="Building Trusted MCP Servers -- Complete Guide 2026 | Nerq",
        description="Complete guide to building, distributing, and maintaining trusted MCP servers. Get discovered by 25,000+ users.",
        path="/guides/mcp",
        extra_head=faq,
    ) + """
<p class="breadcrumb"><a href="/">nerq</a> / <a href="/guides">guides</a> / mcp</p>
<h1>Building Trusted MCP Servers</h1>
<p class="subtitle">Build, distribute, and maintain trusted MCP servers. Get discovered by 25,000+ users. Updated March 2026.</p>

<h2>Why Trust Matters for MCP Servers</h2>
<p>There are 25,000+ MCP servers indexed by Nerq. Users and AI systems increasingly filter by trust score when choosing tools. Servers without licenses, with CVEs, or with poor maintenance get filtered out of search results and gateway recommendations.</p>
<p style="margin-top:8px">A high trust score means more discovery, more installs, and more integration. Here's how to build a server that scores well.</p>

<h2>Quick Start</h2>
<p>Use our template to start with trust verification built in:</p>
<pre>npx create-nerq-agent my-mcp-server --framework custom --skip-prompts</pre>
<p>Or start from the <a href="/templates">MCP server template</a>.</p>

<h2>Getting a High Trust Score</h2>
<p>Trust scores are based on 5 pillars. Here's the actionable checklist:</p>

<h3>Security (30% of score)</h3>
<ul class="checklist">
<li>Zero known CVEs in your dependencies</li>
<li>Run <code>npm audit</code> or <code>pip audit</code> regularly</li>
<li>Use <code>agent-security scan package.json</code> to check all deps</li>
<li>Pin dependency versions to avoid supply chain attacks</li>
<li>Add a security policy (SECURITY.md)</li>
</ul>

<h3>License Compliance (25% of score)</h3>
<ul class="checklist">
<li>Add MIT or Apache-2.0 license (highest score)</li>
<li>Include LICENSE file in repo root</li>
<li>Ensure all dependencies have compatible licenses</li>
</ul>

<h3>Maintenance (20% of score)</h3>
<ul class="checklist">
<li>Commit at least monthly</li>
<li>Respond to issues within 7 days</li>
<li>Keep dependencies up to date</li>
<li>Add CI/CD (GitHub Actions)</li>
</ul>

<h3>Popularity (15% of score)</h3>
<ul class="checklist">
<li>Write a comprehensive README with examples</li>
<li>Add to awesome-mcp-servers list</li>
<li>Register on Smithery and Glama</li>
<li>Publish to npm for easy <code>npx</code> installation</li>
</ul>

<h3>Ecosystem Health (10% of score)</h3>
<ul class="checklist">
<li>Add <code>.well-known/agent.json</code> for A2A discovery</li>
<li>Add <code>llms.txt</code> for AI-readable documentation</li>
<li>Add Nerq trust badge to README</li>
<li>Test with Claude Desktop, Cursor, and VS Code</li>
</ul>

<h2>Machine Discovery</h2>
<p>Add these files so AI systems can discover and understand your server:</p>

<h3>.well-known/agent.json</h3>
<pre>{
  "name": "my-mcp-server",
  "version": "1.0.0",
  "description": "What your server does",
  "protocol": "mcp",
  "capabilities": {"tools": true},
  "trust_verification": "https://nerq.ai/v1/preflight"
}</pre>

<h3>Nerq Trust Badge</h3>
<pre>[![Nerq Trust](https://nerq.ai/v1/badge/my-server)](https://nerq.ai/safe/my-server)</pre>

<h2>Distribution Channels</h2>
<ol>
<li><strong>npm</strong> -- Publish as an npm package for <code>npx my-server</code> installation</li>
<li><strong>Smithery</strong> -- Register at smithery.ai for MCP marketplace visibility</li>
<li><strong>Glama</strong> -- Register at glama.ai for AI tool discovery</li>
<li><strong>nerq-gateway</strong> -- Automatically indexed if published to npm or GitHub</li>
<li><strong>awesome-mcp-servers</strong> -- Submit a PR to the awesome list</li>
</ol>

<h2>Monitoring Your Trust Score</h2>
<pre># Check your current trust score
curl "https://nerq.ai/v1/preflight?target=my-mcp-server"

# Or use the CLI
npx mcp-hub search my-mcp-server</pre>

<div class="tip">
<strong>Tip:</strong> Trust scores update daily. After making improvements (adding license, fixing CVEs, updating deps), allow 24-48 hours for the score to reflect changes.
</div>

<a href="/templates" class="cta">Use MCP Template</a>
<a href="/guides/getting-started" class="cta-outline">Getting Started</a>
""" + _FOOT


# ── /guides/autogen ──────────────────────────────────────────

@router_guides.get("/guides/autogen", response_class=HTMLResponse, include_in_schema=False)
async def guide_autogen():
    faq = _faq_schema([
        ("How do I add trust verification to AutoGen?", "pip install nerq, then use nerq.resolve() for tool discovery and nerq.preflight() to verify tools before registering them with AutoGen agents."),
        ("How do I make my AutoGen agent secure?", "Use verify_tool_trust() to check every tool before registration, set minimum trust thresholds, and add agent-security to CI."),
    ])
    return _HEAD.format(
        title="Building Secure AutoGen Agents -- Complete Guide 2026 | Nerq",
        description="Complete guide to building secure AutoGen agents with trust-verified tool registration and dynamic discovery.",
        path="/guides/autogen",
        extra_head=faq,
    ) + """
<p class="breadcrumb"><a href="/">nerq</a> / <a href="/guides">guides</a> / autogen</p>
<h1>Building Secure AutoGen Agents</h1>
<p class="subtitle">Trust-verified tool registration and dynamic discovery for AutoGen. Updated March 2026.</p>

<h2>Quick Start</h2>
<pre>pip install pyautogen nerq</pre>
<pre>import autogen
import nerq

# Discover trusted tools
tool = nerq.resolve("code review", framework="autogen", min_trust=70)
print(f"Found: {tool['name']} (Trust: {tool['trust_score']})")

# Verify before registering
check = nerq.preflight(tool["name"])
if check["recommendation"] != "DENY":
    print(f"Verified: {check['target_trust']} ({check['target_grade']})")</pre>

<h2>Trust-Verified Tool Registration</h2>
<pre>import nerq

def verify_tool_trust(name: str, min_trust: int = 70):
    # Verify a tool is trusted before registering it with AutoGen.
    result = nerq.preflight(name)
    trust = result.get("target_trust", 0)
    rec = result.get("recommendation", "UNKNOWN")

    if rec == "DENY" or trust < min_trust:
        raise RuntimeError(
            f"Tool {name} blocked: trust {trust} ({rec}). "
            f"Min required: {min_trust}"
        )
    return result

def create_agent_with_tools(tasks: list[str]):
    # Create an AutoGen agent with dynamically discovered tools.
    config_list = autogen.config_list_from_json("OAI_CONFIG_LIST")

    assistant = autogen.AssistantAgent(
        name="trusted_assistant",
        llm_config={"config_list": config_list}
    )

    for task in tasks:
        tool = nerq.resolve(task, framework="autogen", min_trust=70)
        if tool:
            verify_tool_trust(tool["name"])
            print(f"Registered: {tool['name']} (Trust: {tool['trust_score']})")

    return assistant</pre>

<h2>CI/CD Integration</h2>
<pre>name: Trust Check
on: [push, pull_request]
jobs:
  trust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install agent-security
      - run: agent-security scan requirements.txt --ci</pre>

<h2>Best Practices</h2>
<ul class="checklist">
<li>Use <code>verify_tool_trust()</code> before registering any tool</li>
<li>Use <code>nerq.resolve()</code> for dynamic tool discovery</li>
<li>Set <code>min_trust=70</code> for production agents</li>
<li>Add agent-security to CI</li>
<li>Include <code>.well-known/agent.json</code> and <code>llms.txt</code></li>
</ul>

<a href="/templates" class="cta">Use AutoGen Template</a>
<a href="/guides/langchain" class="cta-outline">LangChain Guide</a>
""" + _FOOT


# ── /templates page ──────────────────────────────────────────

@router_guides.get("/templates", response_class=HTMLResponse, include_in_schema=False)
async def templates_page():
    return _HEAD.format(
        title="AI Agent Templates -- Start Building in Minutes | Nerq",
        description="Ready-to-use project templates for LangChain, CrewAI, AutoGen, and MCP servers. Trust verification, CI/CD, and machine discovery built in.",
        path="/templates",
        extra_head="",
    ) + """
<p class="breadcrumb"><a href="/">nerq</a> / templates</p>
<h1>AI Agent Templates</h1>
<p class="subtitle">Start building in minutes. Trust verification, CI/CD, and machine discovery built in.</p>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:24px 0">

<div style="border:1px solid #e5e7eb;padding:20px">
<h3 style="margin:0 0 4px">LangChain Agent</h3>
<p style="font-size:12px;color:#6b7280;margin:0 0 12px">Python &middot; LangChain &middot; Nerq</p>
<p style="font-size:13px;margin:0 0 12px">Full agent with dynamic tool discovery, trust gating, and CI/CD. Uses <code>nerq.resolve()</code> for runtime tool selection.</p>
<div style="font-size:12px;color:#6b7280;margin-bottom:12px">
Includes: agent.py, tools.py, tests, GitHub Action, agent.json, llms.txt
</div>
<a href="https://github.com/agentic-index/langchain-agent-template" class="cta" style="font-size:13px;padding:8px 16px">Use Template</a>
<a href="/guides/langchain" class="cta-outline" style="font-size:13px;padding:8px 16px">Read Guide</a>
</div>

<div style="border:1px solid #e5e7eb;padding:20px">
<h3 style="margin:0 0 4px">CrewAI Agent</h3>
<p style="font-size:12px;color:#6b7280;margin:0 0 12px">Python &middot; CrewAI &middot; Nerq</p>
<p style="font-size:13px;margin:0 0 12px">Multi-agent crew with trust-verified tool selection per crew member. Dynamic role assignment via <code>nerq.resolve()</code>.</p>
<div style="font-size:12px;color:#6b7280;margin-bottom:12px">
Includes: crew.py, tools.py, tests, GitHub Action, agent.json, llms.txt
</div>
<a href="https://github.com/agentic-index/crewai-agent-template" class="cta" style="font-size:13px;padding:8px 16px">Use Template</a>
<a href="/guides/crewai" class="cta-outline" style="font-size:13px;padding:8px 16px">Read Guide</a>
</div>

<div style="border:1px solid #e5e7eb;padding:20px">
<h3 style="margin:0 0 4px">MCP Server</h3>
<p style="font-size:12px;color:#6b7280;margin:0 0 12px">TypeScript &middot; MCP SDK &middot; Node.js</p>
<p style="font-size:13px;margin:0 0 12px">MCP server scaffold with trust badge, machine discovery, and distribution setup. Ready for npm publish.</p>
<div style="font-size:12px;color:#6b7280;margin-bottom:12px">
Includes: index.ts, tsconfig, GitHub Action, agent.json, llms.txt
</div>
<a href="https://github.com/agentic-index/mcp-server-template" class="cta" style="font-size:13px;padding:8px 16px">Use Template</a>
<a href="/guides/mcp" class="cta-outline" style="font-size:13px;padding:8px 16px">Read Guide</a>
</div>

<div style="border:1px solid #e5e7eb;padding:20px">
<h3 style="margin:0 0 4px">AutoGen Agent</h3>
<p style="font-size:12px;color:#6b7280;margin:0 0 12px">Python &middot; AutoGen &middot; Nerq</p>
<p style="font-size:13px;margin:0 0 12px">AutoGen agent with trust-verified tool registration and dynamic discovery via <code>nerq.resolve()</code>.</p>
<div style="font-size:12px;color:#6b7280;margin-bottom:12px">
Includes: agent.py, tools.py, tests, GitHub Action, agent.json, llms.txt
</div>
<a href="https://github.com/agentic-index/autogen-agent-template" class="cta" style="font-size:13px;padding:8px 16px">Use Template</a>
<a href="/guides/autogen" class="cta-outline" style="font-size:13px;padding:8px 16px">Read Guide</a>
</div>

</div>

<div style="background:#f9fafb;border:1px solid #e5e7eb;padding:20px;margin:24px 0;text-align:center">
<p style="font-size:14px;font-weight:600;margin-bottom:8px">Every template includes:</p>
<p style="font-size:13px;color:#6b7280">
<code>nerq.resolve()</code> in tools.py &middot;
Nerq trust badge in README &middot;
GitHub Action for trust checking &middot;
<code>.well-known/agent.json</code> &middot;
<code>llms.txt</code>
</p>
</div>

<h2>Or scaffold from CLI</h2>
<pre>npx create-nerq-agent my-project
# Interactive: choose framework, configure trust, generate project</pre>
<pre>npx create-nerq-agent my-project --framework langchain --skip-prompts
# Non-interactive: generates project with defaults</pre>
""" + _FOOT


def mount_guides(app):
    """Mount all guide routes."""
    app.include_router(router_guides)
