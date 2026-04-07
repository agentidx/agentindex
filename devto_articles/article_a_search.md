---
title: "Ask About Any AI Tool — Free API for Trust, Security & Cost Data"
published: false
tags: [ai, api, security, tools]
canonical_url: https://nerq.ai/?utm=devto_a
---

You're evaluating an AI tool for your project. You want to know: is it maintained? What's the license? Does anyone actually use it? What will it cost me? Normally that means 20 browser tabs and a lot of guesswork.

There's a free API that answers those questions in one call.

## The Problem: 4.5 Million AI Assets, No Easy Way to Compare Them

We index 4,518,802 active AI assets — agents, MCP servers, models, datasets, and tools — crawled from GitHub, HuggingFace, PyPI, npm, Docker Hub, and more. Each one gets a Trust Score based on maintenance activity, documentation quality, license clarity, community signals, and security hygiene.

The median Trust Score is 52.3 out of 100. Only 971 assets have earned an A grade. About 96% sit at grade D or below. That's not a bug in the scoring — that's the actual state of the ecosystem.

When you're picking a tool, you're usually comparing something unknown against something unknown. The `/v1/resolve` endpoint changes that.

## One Endpoint, Plain English Queries

```bash
curl "https://nerq.ai/v1/resolve?task=code+review+tool"
```

```json
{
  "task": "code review tool",
  "capabilities_detected": ["coding"],
  "recommendation": {
    "name": "getsentry/XcodeBuildMCP",
    "trust_score": 88.0,
    "grade": "A",
    "category": "infrastructure",
    "source": "github",
    "stars": 4530,
    "description": "A Model Context Protocol (MCP) server and CLI that provides tools for agent use when working on iOS and macOS projects.",
    "license": "MIT",
    "details_url": "https://nerq.ai/safe/getsentry/xcodebuildmcp",
    "install": {
      "github": "https://github.com/getsentry/XcodeBuildMCP",
      "git_clone": "git clone https://github.com/getsentry/XcodeBuildMCP",
      "nerq_api": "https://nerq.ai/v1/preflight?target=getsentry/XcodeBuildMCP"
    }
  },
  "alternatives": [...]
}
```

You get a recommendation, a Trust Score, a grade, and a list of alternatives — all from a plain-English task description. No API key required.

## Three More Queries Worth Trying

**Data pipeline automation:**
```bash
curl "https://nerq.ai/v1/resolve?task=data+pipeline+automation"
```
Returns: `apify/apify-mcp-server` (trust 76.2, grade B) — MCP server for web scraping and automation, 898 stars.

**SQL database agent:**
```bash
curl "https://nerq.ai/v1/resolve?task=sql+database+agent"
```
Returns: `Dicklesworthstone/mcp_agent_mail` (trust 84.7, grade A) — async coordination layer with SQLite-backed agent inboxes, 1,719 stars.

**Monitoring and observability:**
```bash
curl "https://nerq.ai/v1/resolve?task=monitoring+observability+agent"
```
The API detects capabilities like `devops`, `data_analytics`, or `coding` from your query, then scores the match between detected capabilities and candidate tools. The `capability_match` field tells you exactly how well a tool fits your stated need.

## What Goes Into the Trust Score

The score isn't a star count renamed. It's a composite of:

- **Quality score** — code structure, test presence, release cadence
- **Documentation score** — README completeness, examples, API docs
- **Activity score** — commit frequency, issue response time, contributor count
- **Security score** — dependency audits, CVE exposure, hardening signals
- **Popularity score** — stars, forks, downloads, dependents

Each dimension is independently queryable. If you want to filter specifically for well-documented tools, or tools with recent security audits, the data is there.

## The MCP Server Gap

We index 23,745 active MCP servers — the fastest-growing category right now. Of those, 164 (0.7%) hold an A+ or A grade. About 1,430 are grade B. The remaining ~21,000 are grade C or below.

That matters because MCP servers run with elevated access — they're connecting your AI assistant to filesystems, databases, APIs. A grade-D MCP server isn't necessarily dangerous, but it likely has minimal documentation, sparse commit history, and no clear security story.

The resolve endpoint surfaces the top-graded options for any use case, so you're not blindly trusting a tool because it appeared first in a search.

## Using It in CI

The API is free, unauthenticated, and fast enough to use in a pre-commit hook or CI pipeline step:

```bash
# Check a specific tool before installing
curl -s "https://nerq.ai/v1/preflight?target=anthropics/anthropic-tools" \
  | jq '.trust_score, .grade'
```

Or scan your whole `requirements.txt` / `package.json` against the index using `/v1/scan-project` — we'll cover that in the next article.

## Start Exploring

The index updates continuously as the ecosystem evolves. Tools that were grade D last month may have shipped major improvements. Tools that were grade A may have gone quiet.

**[Search the index at nerq.ai](https://nerq.ai/?utm=devto_a)** — no account needed, full API access free.

The ecosystem has 4.5 million assets. Most of them you've never heard of. Some of them are exactly what you need, and the data to find them is already collected.
