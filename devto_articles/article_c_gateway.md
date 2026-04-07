---
title: "One MCP Server, 25,000 Tools: Stop Configuring MCP Servers One by One"
published: false
tags: [ai, mcp, claude, tools]
canonical_url: https://nerq.ai/?utm=devto_c
---

If you've been using Claude Desktop or any MCP-compatible client for a few weeks, you've probably noticed the configuration problem.

Every tool is a separate MCP server. Every server needs its own entry in `claude_desktop_config.json`. By the time you've added filesystem access, a web browser, a GitHub connector, a database query tool, and a Slack integration, your config file has six separate server definitions, six separate authentication setups, and six separate things to break when you update Claude.

There are currently 23,745 active MCP servers in the index. No one is configuring 23,745 separate entries.

## The Gateway Approach

Instead of connecting to individual MCP servers, you connect to one gateway that knows about all of them — and routes your requests to the right tool dynamically.

```json
{
  "mcpServers": {
    "nerq-gateway": {
      "command": "npx",
      "args": ["-y", "@nerq/mcp-gateway"],
      "env": {
        "NERQ_TRUST_MIN": "70"
      }
    }
  }
}
```

That's the entire config. One entry. The `NERQ_TRUST_MIN` parameter filters out tools below a trust score of 70 — so you're not accidentally routing requests through grade-D MCP servers.

The gateway is backed by the same index that powers the search API: 4,518,802 assets, 23,745 MCP servers specifically, continuously updated.

## How Routing Works

When you ask Claude to do something that requires a tool, the gateway receives the request and runs the same resolution logic as the `/v1/resolve` API endpoint. It detects the capabilities needed, scores candidates against the request, and routes to the highest-trust match.

For example, if you ask Claude to "pull the latest commit messages from my GitHub repo," the gateway detects `vcs` capability, looks up MCP servers with strong GitHub integration, filters by trust score, and proxies the request to the top result.

You never think about which MCP server is handling a given request. The routing is transparent.

## Trust-Filtered by Default

The ecosystem problem the gateway solves isn't just configuration fatigue — it's also the grade distribution problem.

Of the 23,745 MCP servers we index:

| Grade | Count | % of MCP servers |
|-------|-------|-----------------|
| A+ / A | 164   | 0.7% |
| B      | 1,430 | 6.0% |
| C      | 2,416 | 10.2% |
| D      | 14,414 | 60.7% |
| E      | 5,249 | 22.1% |

Without filtering, you have roughly a 60% chance of being routed to a grade-D server for any given request. Grade D means limited maintenance signals, sparse documentation, no clear security auditing history.

The `NERQ_TRUST_MIN` environment variable is your guardrail. Set it to 70 and you're working within the top ~7% of MCP servers by trust score. Set it to 50 and you open up more tools while still filtering out the long tail. The tradeoff is yours to make — the data is surfaced so you can actually make it.

## Switching to a Specific Tool

Sometimes you want a specific server, not the best available match. The gateway supports explicit routing:

```
@nerq use getsentry/XcodeBuildMCP for this build task
```

Or pin a tool for a whole session:

```
@nerq pin filesystem-tool=modelcontextprotocol/servers/filesystem
```

Pinning bypasses the automatic routing and locks the gateway to a specific server for a specific capability category. Useful when you're testing a new tool or when you need deterministic behavior across a long session.

## The Discovery Problem It Solves

Before the gateway existed, finding a good MCP server for a specific task looked like this:

1. Search GitHub for "mcp server [tool name]"
2. Find 12 results, 9 of which haven't been updated in six months
3. Pick one, add it to your config, realize the README is sparse
4. Repeat

With the gateway, that workflow becomes: ask Claude to do the thing, and if the gateway finds a well-trusted tool for it, it uses it. You can browse what's available at [nerq.ai](https://nerq.ai/?utm=devto_c), filter by capability and grade, and use the `@nerq` syntax to switch to anything in the index.

## A Note on Security

MCP servers run with access to whatever you grant them — filesystems, credentials, databases. The trust score is not a security audit. It's a maintenance quality signal. A high-trust server is not guaranteed safe; it's more likely to be actively maintained, documented, and responsive to reported issues.

For anything with elevated access, read the source code. The gateway links directly to the GitHub repository for every tool it routes through. One click from any routed request to the actual code.

## Getting Started

```bash
# Install the gateway
npx -y @nerq/mcp-gateway --version

# Or via npm global install
npm install -g @nerq/mcp-gateway
```

Then add the config block above to `claude_desktop_config.json`, restart Claude Desktop, and the full index is available.

The gateway is open source. Trust score thresholds, routing logic, and capability detection are all configurable. If you want to run it locally against your own index mirror, that's supported too.

**[Browse the full MCP server index at nerq.ai](https://nerq.ai/?utm=devto_c)** — 23,745 servers, graded, searchable, free.
