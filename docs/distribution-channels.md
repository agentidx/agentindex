# ZARQ Distribution Channels — Ready-to-Submit

Created: 2026-03-08

---

## 1. awesome-mcp-servers (PR to punkpeye/awesome-mcp-servers)

**Repo:** https://github.com/punkpeye/awesome-mcp-servers

**PR Title:** Add ZARQ Crypto Risk Intelligence MCP server

**Add to the Finance/Crypto section (or relevant category):**

```markdown
- [ZARQ Crypto Risk Intelligence](https://smithery.ai/server/agentidx/zarq-risk) - Independent crypto risk scoring for AI agents. Trust Score ratings (Aaa-D), Distance-to-Default with 7 signals, crash probability, and structural collapse warnings for 205 tokens. Free API, no auth required. ([Source](https://github.com/zarq-ai/zarq-mcp-server))
```

**PR Body:**
```
## What does this MCP server do?

ZARQ provides real-time crypto risk intelligence for AI agents:
- **11 tools**: safety check, trust score rating, distance-to-default, risk signals, token comparison, distress watchlist, alerts, bulk ratings, and more
- **205 tokens** rated with Moody's-style grades (Aaa through D)
- **Structural collapse detection**: 113/113 token deaths detected out-of-sample, 98% precision
- **Free API, no auth**: `GET https://zarq.ai/v1/check/bitcoin`

## Links
- Smithery: https://smithery.ai/server/agentidx/zarq-risk
- API docs: https://zarq.ai/zarq/docs
- MCP endpoint: https://mcp.zarq.ai/mcp (Streamable HTTP)
- SSE endpoint: https://mcp.zarq.ai/sse
- Source: https://github.com/zarq-ai/zarq-mcp-server
```

---

## 2. awesome-langchain (PR to kyrolabs/awesome-langchain)

**Repo:** https://github.com/kyrolabs/awesome-langchain

**PR Title:** Add zarq-langchain: crypto risk tool for LangChain agents

**Add to Tools section:**

```markdown
- [zarq-langchain](https://pypi.org/project/zarq-langchain/) - Add pre-trade crypto risk scoring to LangChain agents. Returns trust score, crash probability, and SAFE/WARNING/CRITICAL verdict for 205 tokens. Free API, no auth. `pip install zarq-langchain` ![PyPI](https://img.shields.io/pypi/v/zarq-langchain)
```

**PR Body:**
```
## What is zarq-langchain?

A LangChain tool that adds crypto risk intelligence to any agent. 3 lines to integrate:

```python
from zarq_langchain import ZARQRiskCheck
tools = [ZARQRiskCheck()]
agent = initialize_agent(tools, llm, agent=AgentType.OPENAI_FUNCTIONS)
```

Returns formatted risk assessments that LLMs can reason about:
- Trust Score (0-100) with Moody's-style rating
- Crash probability
- SAFE/WARNING/CRITICAL verdict

Free API, no auth needed. 205 tokens covered.

- PyPI: https://pypi.org/project/zarq-langchain/
- API: https://zarq.ai/v1/check/bitcoin
```

---

## 3. MCP.so

**URL:** https://mcp.so

**Action:** Check if they have a "Submit" or "Add Server" page. If yes, submit:
- Name: ZARQ Crypto Risk Intelligence
- URL: https://mcp.zarq.ai/mcp
- Transport: Streamable HTTP
- Tools: 11
- Description: Independent crypto risk scoring for AI agents. Trust Score, crash probability, distance-to-default for 205 tokens. Free, no auth.
- Tags: crypto, risk, defi, finance, trust-score
- Source: https://github.com/zarq-ai/zarq-mcp-server

---

## 4. Product Hunt Launch

**Product Name:** ZARQ — Crypto Risk Intelligence for AI Agents

**Tagline:** Moody's for crypto. Trust scores, crash prediction, and risk ratings for 205 tokens.

**Description:**
ZARQ is an independent crypto risk intelligence platform that helps AI agents and traders make safer decisions.

**Key features:**
- Trust Score ratings (Aaa through D) for 205 tokens — like Moody's for crypto
- Distance-to-Default with 7 structural signals — detects collapses before they happen
- 113/113 token deaths detected out-of-sample with 98% precision
- Free API, no auth: `GET https://zarq.ai/v1/check/bitcoin`
- MCP server with 11 tools for Claude, ChatGPT, and any AI agent
- LangChain integration: `pip install zarq-langchain`
- ElizaOS plugin: `npm install @zarq/elizaos-plugin`

**Why now?**
The agentic economy is here. Stripe launched agent-to-agent payments. Stablecoin settlement hit $110T annualized. AI agents need a trust layer before they can autonomously trade crypto. ZARQ is that trust layer.

**Maker comment:**
"I built ZARQ because I saw AI agents making crypto decisions without any risk framework. Every financial institution has credit ratings — why shouldn't AI agents? ZARQ gives them Moody's-quality risk scoring in <100ms, for free."

**Links:**
- Website: https://zarq.ai
- API Docs: https://zarq.ai/zarq/docs
- MCP Server: https://smithery.ai/server/agentidx/zarq-risk
- PyPI: https://pypi.org/project/zarq-langchain/
- npm: https://www.npmjs.com/package/@zarq/elizaos-plugin
- Track Record: https://github.com/kbanilsson-pixel/track-record

---

## 5. Hacker News — Show HN

**Title:** Show HN: ZARQ – Free crypto risk API for AI agents (Moody's-style ratings for 205 tokens)

**Body:**
```
I built ZARQ because AI agents are starting to make autonomous crypto decisions, but they have no risk framework.

ZARQ provides:
- Trust Score ratings (Aaa-D) like Moody's, for 205 crypto tokens
- Distance-to-Default (DtD) with 7 structural signals
- Crash probability estimation
- Structural collapse detection (113/113 token deaths caught OOS, 98% precision)

The API is free, no auth needed:
  curl https://zarq.ai/v1/check/bitcoin

There's also an MCP server (11 tools) for Claude/ChatGPT, a LangChain wrapper (pip install zarq-langchain), and an ElizaOS plugin.

The track record is SHA-256 hash-chained and publicly verifiable from day 1: https://github.com/kbanilsson-pixel/track-record

Technical details:
- Signals: liquidity stress, holder concentration, resilience decay, fundamental weakness, contagion risk, structural fragility, relative weakness
- Rating methodology: 5-pillar weighted scoring (Security 30%, Compliance 25%, Maintenance 20%, Popularity 15%, Ecosystem 10%)
- API: FastAPI, <100ms P50 latency, zero-auth tier system

Happy to answer questions about the methodology or risk models.

API docs: https://zarq.ai/zarq/docs
MCP: https://smithery.ai/server/agentidx/zarq-risk
```

---

## 6. Dev.to / Hashnode Blog Post

**Title:** How to add pre-trade risk scoring to your LangChain crypto agent in 2 lines

**Body:**

```markdown
# How to add pre-trade risk scoring to your LangChain crypto agent in 2 lines

If you're building a crypto trading agent with LangChain, your agent probably makes buy/sell decisions based on price data, sentiment, or technical indicators. But does it check if the token is about to structurally collapse?

## The problem

In 2024-2025, 113 tokens experienced structural collapse (>50% drawdown). Many of these showed clear warning signs in their on-chain and market microstructure data — but most trading agents don't check for this.

## The solution: 2 lines

```python
from zarq_langchain import ZARQRiskCheck

tools = [ZARQRiskCheck()]  # Add to your agent's tool list
```

That's it. Your agent now has access to ZARQ's risk intelligence:

```
ZARQ Risk Check: Bitcoin (BTC)
Verdict: WARNING
Trust Score: 74.52/100 (Rating: A2)
Crash Probability: 31.8%
Distance to Default: 3.03
Structural Weakness: Yes
CAUTION: Elevated risk. Proceed with reduced position size.
```

## What's under the hood?

ZARQ rates 205 crypto tokens using 7 structural signals:
1. **Liquidity stress** — is trading volume drying up?
2. **Holder concentration** — are whales dumping?
3. **Resilience decay** — does the token recover from drawdowns?
4. **Fundamental weakness** — development activity, TVL trends
5. **Contagion risk** — correlated token failures
6. **Structural fragility** — market microstructure breakdown
7. **Relative weakness** — underperforming sector peers

When ≥3 signals fire simultaneously, ZARQ issues a **Structural Collapse** warning. Out-of-sample, this signal has caught 113/113 token deaths with 98% precision.

## Full example

```python
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, AgentType
from zarq_langchain import ZARQRiskCheck

llm = ChatOpenAI(model="gpt-4")
tools = [ZARQRiskCheck()]
agent = initialize_agent(tools, llm, agent=AgentType.OPENAI_FUNCTIONS)

result = agent.run("Should I buy solana? Check the risk first.")
print(result)
```

## Also available as

- **MCP Server** (11 tools): [Smithery](https://smithery.ai/server/agentidx/zarq-risk)
- **ElizaOS plugin**: `npm install @zarq/elizaos-plugin`
- **Raw API**: `curl https://zarq.ai/v1/check/bitcoin` (free, no auth)

## Links

- Install: `pip install zarq-langchain`
- API docs: https://zarq.ai/zarq/docs
- Track record: https://github.com/kbanilsson-pixel/track-record
```

---

## 7. X/Twitter Accounts to DM (Agent Builders)

These accounts build with LangChain, ElizaOS, CrewAI, or AI agent frameworks:

| Handle | Why |
|--------|-----|
| @hwchase17 | Harrison Chase — LangChain creator |
| @joaomdmoura | João Moura — CrewAI creator |
| @shaboroshin | Shaw — ElizaOS/ai16z core contributor |
| @jxnlco | Jason Liu — instructor/structured output, AI agent tooling |
| @llaboratorydev | LLaboratory — builds AI agent tools |
| @_ryanmac | Ryan McAdams — AI agent infrastructure |
| @mcaborot | MCA Borot — builds crypto AI agents |
| @0xSleuth_ | DeFi agent builder, crypto AI |
| @AutoGPTdev | Toran Richards — AutoGPT, agent frameworks |
| @vilosk | Vilos K — builds crypto trading bots with AI |

**DM Template:**
```
Hey [name] — I built a free crypto risk API for AI agents (zarq.ai).
It gives LangChain/MCP tools a Moody's-style trust score + crash probability for 205 tokens.

2 lines to add: pip install zarq-langchain

Would love your feedback — happy to customize the tool for your use case.
```

---

## 8. CoinGecko Ecosystem

**Path to listing:**

1. **CoinGecko API Partners page** — ZARQ uses CoinGecko price data. Check if they have an ecosystem/partners section where data consumers are listed.

2. **CoinGecko Learn** — Submit a guest post about "How AI Agents Use Credit Ratings for Crypto" to their learn section (https://www.coingecko.com/learn).

3. **CoinGecko Discord/Forum** — Share ZARQ as a project built on their API. They often feature ecosystem projects.

4. **API Attribution** — Ensure all ZARQ pages credit CoinGecko as data source. This increases chance of being featured.

5. **CoinGecko Categories** — Request a new category "AI Risk Intelligence" or submit ZARQ under their existing DeFi tools category.

**Contact:** Check CoinGecko's partnerships page or email partnerships@coingecko.com.

---

## Priority Order

| # | Channel | Effort | Expected Impact | Status |
|---|---------|--------|----------------|--------|
| 1 | awesome-mcp-servers PR | 15 min | High (developers browse this) | Ready |
| 2 | awesome-langchain PR | 15 min | Medium | Ready |
| 3 | Hacker News Show HN | 10 min | High (if it lands) | Ready |
| 4 | MCP.so | 10 min | Medium | Check site |
| 5 | Dev.to blog post | 5 min (paste) | Medium (SEO + discovery) | Ready |
| 6 | Product Hunt | 30 min | High (launch day) | Ready |
| 7 | X DMs | 30 min | High (direct) | 10 targets |
| 8 | CoinGecko | 1 hour | Medium-long term | Research |
