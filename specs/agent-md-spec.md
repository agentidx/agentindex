# agent.md Specification v0.1

## Purpose

`agent.md` is a standard file that AI agents publish to declare their capabilities,
making them automatically discoverable by other agents and indexing services.

Think of it as `robots.txt` for agent capabilities — a simple, universal convention
that any agent framework can adopt.

## Placement

Place `agent.md` in one of these locations:
- Root of your repository: `/agent.md`
- Well-known URL: `https://yourdomain.com/.well-known/agent.md`
- Package root: alongside `package.json` or `pyproject.toml`

## Format

The file uses YAML frontmatter followed by optional Markdown documentation.

```yaml
---
# Required fields
name: your-agent-name
version: 1.0.0
description: One sentence describing what your agent does

# Capabilities: specific actions this agent can perform
capabilities:
  - analyze legal contracts
  - identify risk clauses
  - generate compliance reports

# Category (pick one)
category: legal
# Options: coding, research, content, legal, data, finance, marketing,
#          design, devops, security, education, health, communication,
#          productivity, infrastructure, other

# How to invoke this agent
invocation:
  type: mcp          # mcp, api, npm, pip, docker, github
  install: "npm install @legal/contract-review"
  endpoint: "https://api.example.com/v1"

# Protocols supported
protocols:
  - mcp
  - rest

# Pricing
pricing:
  model: free         # free, freemium, paid, usage_based
  price: 0.00
  currency: USD
  unit: per_call      # per_call, per_month, per_token

# Optional
author: your-name-or-org
license: MIT
homepage: https://example.com
repository: https://github.com/you/your-agent
---

# Your Agent Name

Detailed description of what your agent does and how to use it.

## Examples

Show example invocations and responses here.

## Limitations

Be honest about what your agent cannot do.
```

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| name | string | Unique identifier for the agent |
| version | semver | Current version |
| description | string | One-sentence summary |
| capabilities | list | Specific actions the agent can perform |
| category | string | Primary category |
| invocation | object | How to call this agent |

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| protocols | list | Supported protocols (mcp, a2a, rest, grpc) |
| pricing | object | Cost information |
| author | string | Creator name or organization |
| license | string | SPDX license identifier |
| homepage | string | Project homepage URL |
| repository | string | Source code URL |

## Discovery

Services that index `agent.md` files will automatically:
1. Crawl repositories and domains for `agent.md`
2. Parse the frontmatter into structured data
3. Make the agent discoverable via search APIs
4. Rank agents based on quality signals

## Examples

### MCP Server

```yaml
---
name: filesystem-mcp
version: 2.1.0
description: Read and write files on the local filesystem
capabilities:
  - read files
  - write files
  - list directories
  - search files by pattern
category: devops
invocation:
  type: mcp
  install: "npx @modelcontextprotocol/server-filesystem"
protocols:
  - mcp
pricing:
  model: free
author: modelcontextprotocol
license: MIT
---
```

### API Agent

```yaml
---
name: legal-reviewer
version: 1.0.0
description: AI-powered contract review and risk analysis
capabilities:
  - analyze contracts for risk clauses
  - identify non-standard terms
  - generate compliance checklists
  - compare against template agreements
category: legal
invocation:
  type: api
  endpoint: https://api.legalreview.ai/v1
  docs: https://docs.legalreview.ai
protocols:
  - rest
  - a2a
pricing:
  model: usage_based
  price: 0.50
  currency: USD
  unit: per_call
author: LegalReview AI
---
```

### Python Package

```yaml
---
name: data-cleaner
version: 3.2.1
description: Automated data cleaning and normalization
capabilities:
  - detect and fix data type mismatches
  - remove duplicates
  - handle missing values
  - normalize text fields
  - validate data schemas
category: data
invocation:
  type: pip
  install: "pip install data-cleaner-agent"
protocols:
  - rest
pricing:
  model: free
author: datacleaner
license: Apache-2.0
---
```

## Why agent.md?

The AI agent ecosystem is growing rapidly but lacks a standard way for agents
to declare their capabilities. Current discovery methods rely on:
- Manual registration in directories
- Hardcoded knowledge of available tools
- Platform-specific formats

`agent.md` solves this by providing a universal, human-readable, machine-parseable
format that works across all platforms and frameworks.

## Adopting agent.md

1. Create an `agent.md` file in your repository root
2. Fill in the required fields
3. Commit and push
4. Your agent will be automatically discovered by indexing services

No registration required. No API calls needed. Just a file.
