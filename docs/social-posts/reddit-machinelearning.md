Title: We analyzed 500 top AI repos for security CI — 81% have none

We built a tool that scans AI agent repositories for security practices. We checked the top 500 by GitHub stars.

Key findings:
- 404 of 500 (81%) have no automated security scanning in CI/CD
- 9 of the top 100 most popular AI tools have high risk scores
- Common issue: massive download counts but no CVE scanning, no dependency audits

The most exposed projects by vulnerability score include:

- **AUTOMATIC1111/stable-diffusion-webui** (160K stars, Trust Grade C) — no security signals detected, moderate trust for a project this widely used
- **n8n-io/n8n** (177K stars, Trust Grade C-) — lowest trust score (51.7) despite being one of the most starred projects; low security component flagged
- **f/prompts.chat** (145K stars, Trust Grade C) — no security signals detected, widely depended on with no automated scanning

These are repos that thousands of developers depend on daily.

We've open-sourced the scanning tool: pip install agent-security

Full report with all data: nerq.ai/vulnerable

Methodology: We checked for the presence of security-related GitHub Actions (snyk, dependabot, codeql, safety, bandit, trivy) in each repo's .github/workflows/ directory and analyzed trust signals including activity, documentation, community engagement, and code quality.
