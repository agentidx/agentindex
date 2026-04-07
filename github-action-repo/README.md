# Nerq Trust Check Action

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-Nerq%20Trust%20Check-green?logo=github)](https://github.com/marketplace/actions/nerq-trust-check)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Verify AI agent and dependency trust scores in your CI/CD pipeline. Powered by [Nerq](https://nerq.ai) — the world's largest AI agent trust database (204,000+ agents indexed).

## Why?

AI agents and tools can introduce security risks, compliance gaps, and reliability issues. This action checks every AI dependency against Nerq's trust database before it reaches production.

- **Trust Score** (0-100) across 6 dimensions: Code Quality, Community, Compliance, Operational Health, Security, External Validation
- **CVE Detection** — flag agents with known vulnerabilities
- **Grade System** — A+ to F ratings with clear pass/fail

## Quick Start

```yaml
- uses: nerq-ai/trust-check-action@v1
  with:
    agents: "langchain, crewai, autogen"
    min-score: 60
```

## Usage

### Check specific agents

```yaml
name: AI Trust Check
on: [push, pull_request]

jobs:
  trust-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: nerq-ai/trust-check-action@v1
        with:
          agents: "langchain, crewai, autogen"
          min-score: 60
          fail-on-critical-cve: true
```

### Scan requirements.txt

```yaml
- uses: nerq-ai/trust-check-action@v1
  with:
    requirements-file: "requirements.txt"
    min-score: 50
```

### Scan package.json

```yaml
- uses: nerq-ai/trust-check-action@v1
  with:
    requirements-file: "package.json"
    min-score: 60
    fail-on-cve: true
```

### Use outputs in subsequent steps

```yaml
- uses: nerq-ai/trust-check-action@v1
  id: trust
  with:
    agents: "langchain"
- run: echo "Passed: ${{ steps.trust.outputs.passed }}"
- run: echo "Results: ${{ steps.trust.outputs.results }}"
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `agents` | Comma-separated agent names to check | No | |
| `requirements-file` | Path to `requirements.txt` or `package.json` to scan | No | |
| `min-score` | Minimum acceptable trust score (0-100) | No | `60` |
| `fail-on-cve` | Fail if any agent has known CVEs | No | `false` |
| `fail-on-critical-cve` | Fail if any agent has CRITICAL CVEs | No | `true` |

> At least one of `agents` or `requirements-file` must be provided.

## Outputs

| Output | Description |
|--------|-------------|
| `results` | JSON array of check results |
| `passed` | `true` if all checks passed, `false` otherwise |
| `agents-checked` | Number of agents checked |

### Result object shape

```json
{
  "agent": "langchain",
  "score": 82,
  "grade": "A",
  "cves": 0,
  "recommendation": "SAFE",
  "passed": true,
  "reason": ""
}
```

## Step Summary

The action automatically generates a GitHub Step Summary table:

| Agent | Score | Grade | CVEs | Status |
|-------|-------|-------|------|--------|
| langchain | 82/100 | A | 0 | OK |
| crewai | 75/100 | B+ | 0 | OK |
| sketchy-agent | 23/100 | D | 3 | Score 23 < min 60 |

## How It Works

1. Queries `nerq.ai/v1/preflight?target={agent}` for each agent
2. Checks trust score against `min-score` threshold
3. Checks for CVEs based on `fail-on-cve` / `fail-on-critical-cve` settings
4. Generates step summary and sets outputs
5. Fails the workflow if any check doesn't pass

No API key required. No dependencies. Fail-open on network errors (agent gets `passed: true` with `grade: ERR`).

## API

This action uses the free [Nerq Preflight API](https://nerq.ai/docs). No authentication needed.

```bash
curl https://nerq.ai/v1/preflight?target=langchain
```

## License

MIT
