# MCP Registry Submissions — nerq-gateway

Checklist for submitting `nerq-gateway` to the major MCP registries.

**Package:** nerq-gateway (npm)
**Repository:** https://github.com/nerq-ai/nerq-gateway
**Homepage:** https://nerq.ai/gateway
**Version:** 1.0.0

---

## Standard metadata (use across all registries)

- **Name:** nerq-gateway
- **Description:** Trust verification gateway for MCP servers. Preflight checks, trust scores, and task-to-tool resolution. 25,000+ servers indexed.
- **Tags:** trust, security, discovery, mcp, agents
- **Author:** Nerq <api@nerq.ai>
- **License:** MIT
- **Install command:** `npx -y nerq-gateway`
- **Category:** Security / Discovery / Developer Tools

---

## 1. Smithery (smithery.ai)

### Prerequisites
- npm package `nerq-gateway` must be published and public on npmjs.com
- GitHub repo `nerq-ai/nerq-gateway` must be public

### Option A: CLI publish (preferred)

```bash
npx @smithery/cli publish nerq-gateway
```

Follow the interactive prompts. If the CLI is not yet available or errors out, use Option B.

### Option B: Manual submission

1. Go to **https://smithery.ai/submit** (or https://smithery.ai/new)
2. Sign in with GitHub
3. Fill in the following fields:

| Field | Value |
|-------|-------|
| Package name | `nerq-gateway` |
| npm package | `nerq-gateway` |
| Description | Trust verification gateway for MCP servers. Preflight checks, trust scores, and task-to-tool resolution. 25,000+ servers indexed. |
| Repository URL | https://github.com/nerq-ai/nerq-gateway |
| Homepage | https://nerq.ai/gateway |
| Tags | trust, security, discovery, mcp, agents |
| Install command | `npx -y nerq-gateway` |
| Category | Security |

4. Submit and wait for review (typically 1-3 days)

### Smithery config file (if required)

Some Smithery submissions require a `smithery.yaml` in the repo root. If prompted, create it:

```yaml
name: nerq-gateway
description: Trust verification gateway for MCP servers. Preflight checks, trust scores, and task-to-tool resolution. 25,000+ servers indexed.
install: npx -y nerq-gateway
tags:
  - trust
  - security
  - discovery
  - mcp
  - agents
env:
  - name: NERQ_MIN_TRUST
    description: Minimum trust score for tools (0-100)
    default: "60"
    required: false
  - name: NERQ_AUTO_DISCOVER
    description: Auto-suggest tools for unknown tasks
    default: "true"
    required: false
  - name: NERQ_API_URL
    description: Nerq API URL
    default: "https://nerq.ai"
    required: false
```

---

## 2. Glama (glama.ai)

### Prerequisites
- GitHub repo must be public

### Submission steps

1. Go to **https://glama.ai/mcp/servers** and click "Submit Server" (or go directly to https://glama.ai/mcp/servers/submit)
2. Alternatively, open a PR on their GitHub index repo:
   - Fork **https://github.com/nicholaspark-es/glama-mcp-servers** (check for current repo name on glama.ai)
   - Add an entry for nerq-gateway

3. Fill in:

| Field | Value |
|-------|-------|
| Name | nerq-gateway |
| Description | Trust verification gateway for MCP servers. Preflight checks, trust scores, and task-to-tool resolution. 25,000+ servers indexed. |
| Repository | https://github.com/nerq-ai/nerq-gateway |
| Install | `npx -y nerq-gateway` |
| Tags | trust, security, discovery, mcp, agents |
| Homepage | https://nerq.ai/gateway |

4. Submit the form or PR and wait for approval

---

## 3. mcp.run

### Prerequisites
- npm package must be published

### Submission steps

1. Go to **https://mcp.run** and look for "Add Server" or "Submit" link
2. If web submission is available, fill in:

| Field | Value |
|-------|-------|
| Name | nerq-gateway |
| Description | Trust verification gateway for MCP servers. Preflight checks, trust scores, and task-to-tool resolution. 25,000+ servers indexed. |
| npm package | nerq-gateway |
| Repository | https://github.com/nerq-ai/nerq-gateway |
| Tags | trust, security, discovery, mcp, agents |

3. If no web form exists, check for:
   - A GitHub repo where servers are listed (open a PR to add nerq-gateway)
   - A Discord or community channel for submissions
   - An email contact on the site

4. mcp.run may also auto-index from npm if the package has the `mcp` keyword in package.json (already present in nerq-gateway)

---

## 4. mcpservers.org

### Prerequisites
- GitHub repo must be public

### Submission steps

1. Go to **https://mcpservers.org**
2. Look for "Submit" or "Add Server" button
3. If the site uses a GitHub-based index:
   - Fork the repository (check https://github.com/nicholasgasior/awesome-mcp-servers or similar — verify the actual repo linked from mcpservers.org)
   - Add an entry in the appropriate category (Security / Discovery / Developer Tools)
   - Open a PR with the following entry:

```markdown
- [nerq-gateway](https://github.com/nerq-ai/nerq-gateway) - Trust verification gateway for MCP servers. Preflight checks, trust scores, and task-to-tool resolution. 25,000+ servers indexed.
```

4. If web form submission, fill in:

| Field | Value |
|-------|-------|
| Name | nerq-gateway |
| Description | Trust verification gateway for MCP servers. Preflight checks, trust scores, and task-to-tool resolution. 25,000+ servers indexed. |
| Repository | https://github.com/nerq-ai/nerq-gateway |
| Install | `npx -y nerq-gateway` |
| Tags | trust, security, discovery, mcp, agents |
| Category | Security / Discovery |

---

## Post-submission checklist

- [ ] Smithery: submitted via CLI or web form
- [ ] Glama: submitted via web form or GitHub PR
- [ ] mcp.run: submitted or confirmed auto-indexed
- [ ] mcpservers.org: submitted via web form or GitHub PR
- [ ] Verify each listing appears within 1 week
- [ ] Check that install command `npx -y nerq-gateway` works from each listing
- [ ] Confirm description and tags are rendered correctly

## Additional registries to consider later

| Registry | URL | Notes |
|----------|-----|-------|
| awesome-mcp-servers (GitHub) | https://github.com/punkpeye/awesome-mcp-servers | Popular curated list, submit via PR |
| mcp.so | https://mcp.so | Community directory |
| mcpmarket.com | https://mcpmarket.com | Marketplace-style listing |
| cursor.directory | https://cursor.directory | Cursor-focused MCP directory |
