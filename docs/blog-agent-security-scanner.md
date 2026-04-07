---
title: "Scanning Your AI Agent Dependencies for Trust: Introducing agent-security"
published: false
tags: ai, security, agents, devtools
---

# Scanning Your AI Agent Dependencies for Trust: Introducing agent-security

Your AI agent has 14 tool dependencies. You vetted maybe two of them. The rest? Copy-pasted from a tutorial, pinned to whatever version was current three months ago.

This is the state of agent security in 2026.

## The Problem

AI agents pull in tool dependencies the same way web apps pull in npm packages -- quickly and without much thought. But agent dependencies are worse:

- **They execute with broad permissions.** An MCP server can read files, make network calls, access databases. A bad one can exfiltrate data in a single invocation.
- **They change underneath you.** Tool registries don't have lock files. The server your agent called yesterday might serve different code today.
- **Nobody audits them.** There's no `npm audit` for agent tools. No Snyk. No Dependabot. You're on your own.

Until now.

## agent-security: Trust Scanning for Agent Dependencies

`agent-security` scans your project's agent and tool dependencies against Nerq's trust database of 204K+ indexed assets. It checks trust scores, maintenance status, known issues, and gives you a clear pass/fail.

### Install and Run

```bash
pip install agent-security
agent-security scan .
```

That's it. It detects your agent framework (LangChain, CrewAI, AutoGen, raw MCP configs), extracts tool references, and checks each one.

### What the Output Looks Like

```
$ agent-security scan .

Scanning project: ./my-agent
Framework detected: LangChain + MCP
Found 8 tool dependencies

TOOL                        TRUST   GRADE   STATUS
github-mcp-server           92.4    Aa2     PASS
slack-mcp                   84.1    A1      PASS
web-search-tool             71.3    Baa1    WARN - no recent commits
postgres-query-mcp          68.9    Baa2    WARN - broad permissions
random-util-server          23.7    B3      FAIL - abandoned, no license
file-access-mcp             41.2    Ba2     FAIL - trust below threshold
custom-internal-tool        --      --      SKIP - not in index
db-admin-mcp                55.1    Ba1     WARN - 2 known issues

Results: 2 PASS | 3 WARN | 2 FAIL | 1 SKIP
Minimum trust threshold: 50 (configurable with --min-trust)
```

Tools below the trust threshold get flagged. Abandoned tools, tools with no license, tools with known security issues -- all surfaced before your agent runs in production.

### Configuration

Create an `.agent-security.yml` in your project root to customize:

```yaml
min_trust: 60
fail_on_warn: false
ignore:
  - custom-internal-tool
  - legacy-adapter
allow_unlicensed: false
```

## CI Integration

Run trust scans on every PR. One command generates a GitHub Action:

```bash
agent-security ci
```

This creates `.github/workflows/agent-security.yml`:

```yaml
name: Agent Security Scan
on: [push, pull_request]

jobs:
  trust-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install agent-security
      - run: agent-security scan . --ci
```

The `--ci` flag exits with code 1 on any FAIL result, blocking the merge. Warnings are logged but don't break the build (unless you set `fail_on_warn: true`).

## Trust Badge

Show your users that your agent's dependencies are verified:

```bash
agent-security badge
```

Generates a badge URL for your README:

```markdown
[![Agent Trust: Verified](https://nerq.ai/badge/trust-verified-green.svg)](https://nerq.ai/scan/your-project)
```

The badge links to a public scan report showing which tools your agent uses and their trust grades. It re-scans weekly to stay current.

## What Gets Checked

Each tool dependency is scored against Nerq's five trust pillars:

- **Provenance** -- Is the source code public? Who maintains it?
- **Maintenance** -- When was the last commit? Are issues addressed?
- **Adoption** -- How many projects depend on it?
- **Security** -- Known vulnerabilities, permission scope, data handling
- **Compliance** -- License, API stability, breaking change history

Scores update daily as Nerq re-crawls the ecosystem.

## Try It

```bash
pip install agent-security
agent-security scan .
```

Works with any Python or Node agent project. Detects LangChain, CrewAI, AutoGen, Semantic Kernel, and raw MCP configurations automatically.

Docs: [nerq.ai/agent-security](https://nerq.ai/agent-security) | Source: [github.com/nerq-ai/agent-security](https://github.com/nerq-ai/agent-security)

---

*Built on Nerq's index of 204K+ agents and tools. Trust scores are independent and data-driven -- no vendor can pay for a higher rating.*
