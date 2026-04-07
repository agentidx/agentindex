# Reddit Post Draft: r/selfhosted

**Subreddit:** r/selfhosted (also suitable for r/opensource)

**Title:** Nerq MCP Server — self-hostable trust scoring for AI assets, queryable from your own tools

**Body:**

I've been building a trust scoring engine for AI assets (models, agents, tools, packages) and wanted to share the self-hostable piece since it fits this community well.

**What it does**

Nerq indexes 5M+ AI assets and computes Trust Scores based on maintenance activity, documentation quality, adoption signals, and vulnerability history. Think of it as a reputation layer for the AI/package ecosystem.

The part that's relevant here: the **MCP server** and **REST API** are designed to be queried from your own infrastructure.

**MCP Server**

If you run Claude, Cursor, or any tool that supports the Model Context Protocol, you can point it at the Nerq MCP server. Then from inside your AI assistant, you can ask things like:

- "What's the trust score for this GitHub repo?"
- "Compare these two npm packages by maintainer reliability"
- "Is this HuggingFace model safe to use?"

It returns structured trust data your tools can act on.

**REST API**

Standard REST API if you want to integrate trust checks into your own workflows:

- CI/CD gates (block deploys that depend on low-trust packages)
- Homelab dashboards (monitor the trust posture of tools you run)
- Custom scripts and automation

**Why I built it**

I run a bunch of self-hosted AI tools and kept finding myself manually vetting dependencies and models. Checking last commit dates, scanning for known issues, reading through repos. It felt like something that should be a queryable service rather than manual research every time.

The index covers models (HuggingFace, Replicate), packages (npm, PyPI), GitHub repos, and AI agents/tools. Scores update as the underlying signals change.

**How to try it**

The API and MCP server are available at nerq.ai. The API is free for reasonable usage. If there's interest, I can look into packaging the scoring engine itself as a container for fully local operation.

Curious if anyone else has thought about trust/vetting as part of their self-hosted stack, or if this is solving a problem nobody has.

Site: https://nerq.ai
