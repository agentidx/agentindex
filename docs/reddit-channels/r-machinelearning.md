# Reddit Post Draft: r/MachineLearning

**Subreddit:** r/MachineLearning

**Tag:** [Project]

**Title:** [Project] I built a trust scoring engine for 5M+ AI assets — models, datasets, agents, and tools

**Body:**

I've been working on a problem that's been bugging me: how do you actually know if a model on HuggingFace is safe to use?

There are 700K+ models on HF alone. Some have great documentation, active maintainers, and clean training data provenance. Others are uploaded once, never updated, have no model card, and could contain anything. But there's no systematic way to tell them apart at a glance.

**What it does**

Nerq (nerq.ai) indexes over 5M AI assets — models, datasets, agents, and tools — and computes a Trust Score for each one based on signals like:

- Maintainer activity and track record
- Documentation completeness (model cards, dataset cards)
- Community adoption and usage patterns
- Update frequency and version history
- Known vulnerability associations

The score isn't a quality benchmark (that's what eval suites are for). It's closer to a supply chain health check — is this asset actively maintained, well-documented, and widely used, or is it abandoned and sketchy?

**How you can use it**

Two ways that might be relevant here:

1. **MCP Server** — If you use Claude, Cursor, or any MCP-compatible tool, you can connect the Nerq MCP server and query trust scores inline. Ask "is this model trustworthy?" and get a scored answer with reasoning while you work.

2. **API** — Straightforward REST API. Pass an asset identifier, get back a trust score with breakdown. Useful if you're building pipelines that pull models programmatically and want a gate.

I'm also working on a browser extension that will show trust badges directly on HuggingFace model pages, so you can see scores while browsing — that's still in progress.

**Why I built it**

I was building an agent system that needed to pull models dynamically, and I realized I had no automated way to vet them. I was manually checking stars, commits, and issues for every model. That felt like something a scoring system should handle.

Happy to answer questions about the scoring methodology or take feedback on what signals actually matter to you when evaluating models.

Site: https://nerq.ai
