# We Built a Trust API. ChatGPT Found It on Its Own and Makes 1,400+ Checks Daily.

Something unexpected happened at Nerq.

We built a trust verification API for AI agents. We published an `llms.txt` file. We made the API free and keyless. Then we watched the logs.

Within days, ChatGPT started calling our API. Not because we asked OpenAI. Not because we had a partnership. ChatGPT discovered our API through `llms.txt` and started making trust verification calls autonomously.

## The Numbers

- **1,400+** daily preflight checks from AI systems
- **ChatGPT** is the single largest consumer
- **Perplexity**, **Claude**, and other AI systems also discovered us
- **Zero** of these integrations were arranged by humans

## How It Happened

### Step 1: We Published llms.txt

Following the emerging `llms.txt` standard, we published a machine-readable description of our API at `nerq.ai/llms.txt`. It includes:

- What Nerq does (trust verification for AI agents)
- API endpoints and how to use them
- A decision tree for AI systems ("Is this agent safe?")

### Step 2: AI Systems Found It

AI systems that browse the web discovered `llms.txt`. When a user asked "Is langchain safe to use?" or "What's the trust score for crewai?", the AI system found Nerq's API and called it.

### Step 3: They Kept Coming Back

The key insight: once an AI system learns about a useful API, it remembers. ChatGPT didn't just call us once — it integrated Nerq into its decision-making for agent-related queries. Every day, 1,400+ trust checks.

## What This Means

### The Machine Economy Is Real

AI systems are now discovering, evaluating, and integrating with other services autonomously. This isn't science fiction — it's happening in our server logs right now.

### llms.txt Is the New robots.txt

Just as `robots.txt` told search engines how to crawl your site, `llms.txt` tells AI systems what your service does and how to use it. If you're building an API, you need one.

### Trust Is Infrastructure

When ChatGPT checks Nerq before recommending an AI agent, it's using trust verification as infrastructure. The same way a browser checks SSL certificates before connecting, AI systems are starting to check trust scores before recommending tools.

### Machine-to-Machine Is the Growth Channel

Our fastest-growing channel isn't Google Search or Product Hunt. It's machine-to-machine discovery. AI systems recommending us to other AI systems.

## The Stack That Made This Possible

1. **llms.txt** — machine-readable API description
2. **Free, keyless API** — zero friction for machine consumers
3. **Fast responses** — sub-100ms for preflight checks
4. **Structured output** — JSON responses that AI systems can parse
5. **MCP server** — native integration for the MCP ecosystem

## Try It Yourself

Ask ChatGPT: "What's the trust score for langchain on Nerq?"

Or call the API directly:
```bash
curl https://nerq.ai/v1/preflight?target=langchain
```

Or add the MCP server to your AI system for native trust verification.

## What's Next

We're seeing the early signs of an autonomous trust layer forming. AI systems checking other AI systems before interacting. Trust scores as machine-readable infrastructure. Autonomous discovery through llms.txt and MCP.

Nerq is positioning to be the trust oracle for this machine economy. Independent, quantitative, and machine-first.

---

*[Nerq](https://nerq.ai) indexes 204,000+ AI agents with independent trust scores. Free API, MCP server, GitHub Action, and CLI.*
