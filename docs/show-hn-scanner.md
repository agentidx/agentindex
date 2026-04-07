# Show HN Draft — AI Supply Chain Scanner

**Title:** Show HN: Nerq - Trust scanner for AI packages (npm, PyPI, HuggingFace)

**URL:** https://nerq.ai

**Text:**

I npm-installed an AI agent last month that had 12 stars, no license, and hadn't been updated in 8 months. It had full filesystem access. I didn't check any of that before running it.

That's the problem. We're adding AI packages to our projects faster than we can vet them. Traditional security scanners catch CVEs, but they don't tell you whether that random LangChain tool on PyPI is maintained, who built it, or if it's been abandoned.

Nerq scans 5M+ AI assets (204K agents and tools, 4.7M models and datasets) across npm, PyPI, HuggingFace, GitHub, and other registries. For each one it computes a Trust Score based on maintenance signals, license risk, security history, community activity, and documentation quality.

Five ways to use it:

1. Browser extension (Chrome) — adds trust badges directly on GitHub, npm, and PyPI pages. You see the score before you install.

2. VS Code extension — shows inline trust scores next to your imports and dependencies.

3. GitHub App — when a PR changes package.json, requirements.txt, or similar, it posts a trust report as a PR comment. Catches risky additions before merge.

4. MCP Server — Claude and Cursor can query trust scores natively. Ask "is this package safe?" and get a real answer.

5. API — `curl https://nerq.ai/v1/preflight?package=langchain` for CI/CD pipelines, custom integrations, whatever.

The /v1/preflight endpoint is the core of it. Give it a package name, get back a trust score, risk flags, and a verdict. Designed to slot into the same place you'd put a security scan.

Free API, no auth required. Built by one person with Claude Code.

Happy to answer questions about the scoring methodology or how we index across registries.

---

**Posting instructions:**
1. Go to https://news.ycombinator.com/submit
2. Title: "Show HN: Nerq - Trust scanner for AI packages (npm, PyPI, HuggingFace)"
3. URL: https://nerq.ai
4. Text: (copy from above — HN doesn't support markdown, plain text only)
5. Best time: Tuesday or Wednesday, 9-10am ET
6. After posting, reply to early comments quickly — HN rewards engagement in the first hour
