# We Scanned 204,000 AI Agents for Vulnerabilities. Here's What We Found.

At Nerq, we index and analyze over 204,000 AI agents and tools from GitHub, npm, PyPI, HuggingFace, and MCP registries. We assign each one a Trust Score based on 6 dimensions and 13+ independent signals.

As part of that analysis, we track known vulnerabilities (CVEs) across the AI agent ecosystem. Here's what we found.

## The Numbers

- **49 CVEs** tracked across the AI agent ecosystem
- **9 CRITICAL** severity vulnerabilities
- **31 HIGH** severity vulnerabilities
- **11 agents** with at least one known CVE
- **204,000+** agents scanned in total

That means roughly **0.005%** of indexed agents have a known CVE. Sounds small — until you realize these are some of the most widely-used agents in production.

## The Most Vulnerable Agents

| Agent | CVEs | Critical | High |
|-------|------|----------|------|
| MindsDB | 18 | 4 | 8 |
| Roo Code | 10 | 2 | 5 |
| Apache Hertzbeat | 6 | 1 | 4 |
| n8n | 4 | 1 | 3 |
| MCP Servers | 3 | 0 | 2 |

## What Types of Vulnerabilities?

The most common vulnerability categories in AI agents:

1. **Unauthorized access / permission bypass** — agents that expose internal APIs or skip authentication checks
2. **Cross-site scripting (XSS)** — agents with web interfaces that don't sanitize input
3. **Server-side request forgery (SSRF)** — agents that can be tricked into making requests to internal services
4. **Credential exfiltration** — agents with domain allowlist bypasses that leak credentials
5. **Parameter injection** — MCP servers that don't sanitize parameters in protocol conversion

## The MCP Risk

MCP (Model Context Protocol) is exploding in adoption. But with that comes new attack surfaces:

- **CVE-2026-29791**: Missing parameter sanitization in MCP-to-OpenAPI conversion (agentgateway)
- Multiple MCP servers lack input validation on tool arguments
- Symlink bypass attacks allow reading files outside allowed directories

When an AI system connects to an untrusted MCP server, it's giving that server access to execute code in a privileged context. Trust verification before connection is critical.

## What Should You Do?

### 1. Check Before You Connect
Before integrating any AI agent or MCP server:
```bash
curl https://nerq.ai/v1/preflight?target=agent-name
```

### 2. Add Trust Gates to CI/CD
Use the Nerq GitHub Action to block untrusted agents:
```yaml
- uses: nerq-ai/trust-check-action@v1
  with:
    requirements-file: requirements.txt
    min-score: 60
    fail-on-critical-cve: true
```

### 3. Use the CLI
```bash
pip install nerq
nerq check langchain
nerq scan requirements.txt
```

### 4. Monitor Continuously
Subscribe to Nerq's CVE alert feed:
- RSS: `https://nerq.ai/feed/cve-alerts.xml`
- Webhook: `POST https://nerq.ai/v1/webhooks/subscribe`

## Methodology

Nerq's Trust Score (0-100) is computed across 6 dimensions:
- **Code Quality** (20%): test coverage, documentation, code structure
- **Community** (20%): stars, contributors, activity, adoption
- **Compliance** (15%): license clarity, data handling, regulatory alignment
- **Operational Health** (15%): release frequency, issue response time, uptime
- **Security** (15%): CVE history, dependency vulnerabilities, security practices
- **External Validation** (15%): third-party audits, certifications, reviews

All scores are independently computed. No agent can pay for a higher score.

---

*Data from [nerq.ai](https://nerq.ai) — the AI agent trust database. Free API, no authentication required.*
