---
title: "Nerq Gateway: Stop Hardcoding Your AI Agent's Tools"
published: false
tags: ai, agents, mcp, devtools
---

# Nerq Gateway: Stop Hardcoding Your AI Agent's Tools

If you're building AI agents, you've probably written something like this:

```python
TOOLS = [
    {"name": "github-mcp", "url": "https://github-mcp.example.com"},
    {"name": "slack-bot", "url": "https://slack-tool.example.com"},
    {"name": "db-query", "url": "https://some-db-proxy.internal"},
]

agent = Agent(tools=TOOLS)
```

Congratulations, you now have three problems.

## The Problem with Hardcoded Tool Lists

**They break.** Tool URLs change. Servers go down. Maintainers abandon projects. Your agent stops working at 2 AM and you get paged because a dependency you never audited decided to move endpoints.

**They're a security risk.** That MCP server your agent calls -- who runs it? When was it last updated? Does it have known vulnerabilities? You don't know, because you copy-pasted a URL from a blog post six months ago and never checked again.

**They limit your agent's capability.** Your agent can only use what you've manually wired up. It can't discover that there's a better, faster, more trustworthy tool for the same task. You've turned a general-purpose reasoning engine into a static function caller.

This is the equivalent of hardcoding IP addresses instead of using DNS. We solved this for networking decades ago. It's time to solve it for agents.

## Nerq Gateway: Runtime Tool Resolution with Trust

Nerq Gateway resolves tasks to trust-verified tools at runtime. Instead of maintaining a static list of tools, your agent describes what it needs and Nerq returns the best match -- verified, scored, and ready to connect.

### How It Works

**Step 1: Describe the task.**

```python
from nerq import NerqGateway

nerq = NerqGateway(api_key="your-key")

# Find tools that can interact with GitHub repos
results = nerq.resolve("manage github repositories and pull requests")
```

**Step 2: Get back trust-scored matches.**

```python
for tool in results:
    print(f"{tool.name} — Trust: {tool.trust_score} ({tool.trust_grade})")
    print(f"  Source: {tool.source_url}")
    print(f"  Stars: {tool.stars}  Last updated: {tool.last_updated}")
```

```
github-mcp-server — Trust: 92.4 (Aa2)
  Source: https://github.com/modelcontextprotocol/servers
  Stars: 14200  Last updated: 2026-03-12

gh-actions-tool — Trust: 78.1 (A3)
  Source: https://github.com/example/gh-actions-tool
  Stars: 340  Last updated: 2026-02-28
```

**Step 3: Verify trust before connecting.**

```python
# Preflight check — verify the tool meets your trust threshold
check = nerq.preflight("github-mcp-server", min_trust=80)

if check.passed:
    agent.connect(check.tool)
else:
    print(f"Blocked: {check.reason}")
    # "Trust score 45.2 below threshold 80. Last commit 9 months ago."
```

That's it. Three lines to go from "I need a GitHub tool" to "here's a verified one."

### What Happens Under the Hood

When you call `nerq.resolve()`, the gateway searches across Nerq's index of **204,000+ agents and tools**, including **25,000+ MCP servers**. It ranks results by relevance and trust score.

The trust score itself is based on five pillars:

| Pillar | What it measures |
|--------|-----------------|
| **Provenance** | Who built it? Is the source verifiable? |
| **Maintenance** | Recent commits, release cadence, issue response time |
| **Adoption** | Stars, downloads, dependent projects |
| **Security** | Known CVEs, dependency audit, permissions scope |
| **Compliance** | License clarity, data handling, API stability |

Each tool gets a score from 0-100 and a letter grade (Aaa to C), modeled after credit ratings. A tool with a trust score below 50 isn't necessarily malicious -- but your agent should probably think twice before calling it autonomously.

## Installation

**Python:**

```bash
pip install nerq
```

**Node / CLI:**

```bash
npm i -g nerq-gateway
```

**Quick search from the terminal:**

```bash
npx nerq-gateway search "github"
npx nerq-gateway search "database query tool"
npx nerq-gateway search "image generation"
```

## Integrating with Your Agent Framework

Nerq Gateway works with any agent framework. Here's a LangChain example:

```python
from nerq import NerqGateway
from langchain.agents import initialize_agent

nerq = NerqGateway()

# Resolve tools dynamically based on the user's request
def get_tools_for_task(task_description: str, min_trust: int = 75):
    results = nerq.resolve(task_description, limit=5)
    return [
        tool.to_langchain()
        for tool in results
        if tool.trust_score >= min_trust
    ]

tools = get_tools_for_task("search the web and summarize results")
agent = initialize_agent(tools=tools, llm=llm)
```

For CrewAI, AutoGen, or raw OpenAI function calling, the pattern is the same: resolve, filter by trust, connect.

## Why This Matters

The agentic ecosystem is growing fast. There are thousands of MCP servers, tool providers, and agent-to-agent protocols appearing every week. No developer can manually audit all of them.

Without a trust layer, you're flying blind. Your agent picks up a tool from a registry, calls it with user data, and you have no idea if the server on the other end is maintained, secure, or even doing what it claims.

Nerq Gateway is DNS + TLS for the agent ecosystem. Resolution plus verification.

## Try It Now

```bash
# Search the index from your terminal
npx nerq-gateway search "github"

# Or visit the web interface
# https://nerq.ai/gateway
```

Full docs and API reference at [nerq.ai/gateway](https://nerq.ai/gateway).

---

*Nerq indexes 204K+ agents and tools with independent trust scores. No pay-to-play rankings. No self-reported scores. Just data.*
