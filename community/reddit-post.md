# Reddit Posts

## r/MachineLearning

**Title**: We built an independent trust database for 204K AI agents — here's what we learned about AI agent security

**Body**:
We've been indexing AI agents from GitHub, npm, PyPI, HuggingFace, and MCP registries for the past few months. 204,000+ agents and tools are now in the database, each with a Trust Score (0-100) based on code quality, community health, security, compliance, and more.

Key findings:
- 49 CVEs tracked across the AI agent ecosystem (9 critical, 31 high severity)
- MindsDB alone has 18 known CVEs
- MCP servers are an emerging attack surface — parameter injection and symlink bypass attacks
- Only ~5% of agents we index have comprehensive test suites

Free API: `curl nerq.ai/v1/preflight?target=langchain`
CLI: `pip install nerq`

Interested in what trust signals the ML community thinks matter most.

## r/LocalLLaMA

**Title**: Free trust verification API for AI agents — check any agent before using it

**Body**:
Built a trust verification system that indexes 204K+ AI agents. You can check any agent's trust score before integrating it:

```bash
curl nerq.ai/v1/preflight?target=ollama
```

Also works as an MCP server for agent-to-agent trust verification. Free, no API key needed.

Has anyone had issues with untrusted AI tools or MCP servers? Curious what security practices people follow.

## r/artificial

**Title**: ChatGPT is autonomously discovering and using our trust verification API — 1,400+ daily checks

**Body**:
We built a trust API for AI agents (nerq.ai). We published an llms.txt file describing it. ChatGPT discovered the API on its own and now makes 1,400+ trust verification calls per day — autonomously.

No partnership with OpenAI. No integration. Just a machine-readable description and a useful API.

This is what the machine economy looks like. AI systems discovering, evaluating, and using services without human intermediaries.

Free API: nerq.ai/v1/preflight?target=langchain
