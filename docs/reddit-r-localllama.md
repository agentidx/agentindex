# Reddit Post Draft — r/LocalLLaMA

**Subreddit:** r/LocalLLaMA

**Title:** nerq-gateway: One MCP config line gives you access to 25,000 trust-verified tools

**Body:**

I've been frustrated with MCP server configuration. Every new tool needs a new config entry, you have to find it, figure out the install, hope it's not abandoned.

So I built **nerq-gateway** — one MCP server that acts as a gateway to 25,000+ others:

```json
{
  "mcpServers": {
    "nerq": {"command": "npx", "args": ["-y", "nerq-gateway"]}
  }
}
```

Now I just ask Claude "search my GitHub repos" or "query my postgres database" and the gateway:
1. Finds the best MCP server for the task
2. Trust-checks it (security, license, maintenance)
3. Returns the recommendation with install instructions

**Also shipped:**
- `npx nerq-mcp-hub search "database"` — CLI to find and auto-install MCP servers
- `pip install agent-security && agent-security scan requirements.txt` — scan your deps for trust issues
- `npx create-nerq-agent my-project` — scaffold a project with trust verification built in

The trust data comes from nerq.ai which indexes 204K agents from GitHub, npm, PyPI, HuggingFace, Smithery, etc. Every agent gets a 0-100 trust score.

Free, no auth. Try it:
```
curl https://nerq.ai/v1/resolve?task=search+github
```

---

**Posting instructions:**
1. Post to r/LocalLLaMA (no flair needed)
2. Best time: Any weekday, early afternoon ET
3. This sub loves practical tools — lead with the one-liner install
