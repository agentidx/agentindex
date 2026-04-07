Title: PSA: 81% of popular AI/MCP repos have no security scanning — here's a free tool to check yours

We scanned 500 popular AI agent and MCP server repos. 81% have zero security CI.

Some of the most exposed projects we found:

- **AUTOMATIC1111/stable-diffusion-webui** (160K stars) — Trust Grade C, zero security signals in CI
- **n8n-io/n8n** (177K stars) — Trust Grade C-, lowest trust score (51.7) of any major project we scanned
- **f/prompts.chat** (145K stars) — Trust Grade C, no dependency auditing despite massive adoption

Quick way to check your own project:

pip install agent-security
agent-security scan requirements.txt

It checks each dependency against a trust database of 204K+ agents, flags CVEs, license issues, and maintenance problems.

Also works on package.json for JS projects.

Free, open source, no account needed.

Full findings: nerq.ai/vulnerable
