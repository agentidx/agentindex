---
title: "Building a Trust Score MCP Server for Claude and Cursor"
published: false
tags: ["ai", "mcp", "security", "tooling"]
cover_image_description: "A split screen showing a Claude conversation on the left asking about a package's trust score, and the MCP server JSON response on the right with score, grade, and recommendation."
---

The Model Context Protocol (MCP) lets AI assistants call external tools. Claude, Cursor, Windsurf, and other MCP-compatible clients can discover and invoke tools at runtime — which means your AI assistant can check whether a package is safe before it recommends it to you.

I built an MCP server that exposes Nerq's trust scoring engine as a set of tools any MCP client can call. Here is how to set it up and what it can do.

## What MCP Is (30-Second Version)

MCP is a standard for connecting AI assistants to external data and tools. Instead of the assistant guessing or hallucinating, it calls a tool that returns real data. An MCP server exposes tools with JSON Schema inputs and returns structured results. Claude Desktop, Cursor, Windsurf, and others support it natively.

## The Nerq MCP Server

The server exposes four tools:

1. **`discover_agents`** — Find AI agents and tools by describing what you need. Returns ranked results with trust scores.
2. **`trust_gate`** — Check if a specific agent or package meets a trust threshold. Returns approve/reject with the score and grade.
3. **`trust_compare`** — Compare two agents side-by-side on trust score, grade, and recommendation.
4. **`agent_index_stats`** — Get current index statistics: total assets, categories, sources.

## Setup

Add Nerq to your MCP client configuration. For Claude Desktop, edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nerq": {
      "command": "python",
      "args": ["-m", "agentindex.mcp_server"]
    }
  }
}
```

For Cursor, add the same block to your MCP settings. For any MCP client that supports stdio transport, the config is identical.

Install the server:

```bash
pip install agentindex
```

Or run from source:

```bash
git clone https://github.com/nerq-ai/agentindex.git
cd agentindex
pip install -e .
```

## Using It

Once configured, your AI assistant can call the tools directly. Here are some example interactions:

**"Is langchain safe to use?"**

The assistant calls `trust_gate` with `name: "langchain"` and returns:

```
langchain — Trust Score: 82/100 (Grade: A)
Recommendation: PROCEED
Maintenance: Active (last commit 2 days ago)
License: MIT
Known CVEs: 0
```

**"Find me an agent for code review"**

The assistant calls `discover_agents` with `need: "code review"` and returns a ranked list:

```
1. codex (Score: 85, Grade: A) — OpenAI code review agent
2. crewai (Score: 78, Grade: B+) — Multi-agent framework
3. aider (Score: 76, Grade: B+) — AI pair programming
```

**"Compare autogen and crewai"**

The assistant calls `trust_compare` with both names:

```
autogen: 75/100 (B+) vs crewai: 78/100 (B+)
Winner: crewai by 3 points
Both: PROCEED
```

## Why This Matters

AI assistants recommend packages constantly. "Use this library," "install this tool," "try this agent." Without trust scoring, those recommendations are based on popularity and training data — not on current maintenance status, security posture, or license compliance.

With the Nerq MCP server, the assistant checks before it recommends. If a package has a trust score of 31 and two unpatched CVEs, the assistant knows that and can suggest alternatives.

This is especially important for agentic workflows. When an agent autonomously selects and invokes other agents, trust scoring is not optional — it is the difference between a working pipeline and a supply chain incident.

## The Trust Gate Pattern

The most useful tool is `trust_gate`. It takes a name and an optional threshold (default 60) and returns a binary approve/reject decision. You can use this in any agentic workflow:

1. Agent A wants to call Agent B
2. Agent A calls `trust_gate(name="agent-b", threshold=70)`
3. If approved, proceed. If rejected, find an alternative.

This is the simplest form of agent-to-agent trust verification. No API keys, no complex setup — just a tool call.

## Try It

Install the MCP server, add it to your Claude or Cursor config, and ask your assistant about a package. The trust data is live and covers 5M+ AI assets.

---

*Nerq indexes 5M+ AI assets with trust scores. Available as a browser extension, VS Code extension, GitHub App, MCP Server, and API. [nerq.ai](https://nerq.ai)*
