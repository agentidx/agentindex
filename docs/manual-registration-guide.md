# ZARQ Manual Registration Guide

Step-by-step instructions for Anders. Do these in order.

---

## 1. Smithery MCP Registration

1. Go to https://smithery.ai
2. Click "Add Server" or "Register MCP Server"
3. Fill in:
   - **Server URL:** `https://mcp.zarq.ai/sse`
   - **Name:** ZARQ Risk Intelligence
   - **Description:** Real-time crypto risk scoring for AI agents. Trust Score, crash probability, distance-to-default for 205 tokens. Moody's-style ratings (Aaa-D). 100% recall on structural collapses (113/113). Free, no API key needed.
   - **Tags:** crypto, risk, defi, trust-score, agent-tools, mcp
   - **Icon/Logo:** Use ZARQ logo or leave default
4. Submit and verify the server responds to health check
5. Test: search for "zarq" on Smithery to confirm listing

---

## 2. Glama MCP Registration

1. Go to https://glama.ai/mcp/servers
2. Click "Submit MCP Server" or equivalent
3. Fill in:
   - **Server URL:** `https://mcp.zarq.ai/sse`
   - **Name:** ZARQ Risk Intelligence
   - **Description:** (same as Smithery above)
   - **Category:** Finance / Crypto / Risk
4. Submit and verify

---

## 3. ERC-8004 Registration

ERC-8004 is the "Agent Commerce Protocol" for on-chain agent identity.

### What You Need
- MetaMask or similar wallet with ETH (for gas)
- Your agent-card JSON (already live at `https://zarq.ai/.well-known/agent-card.json`)

### Steps
1. The ERC-8004 spec uses an `IdentityRegistry` contract
2. Registration requires calling `registerAgent(url, metadata)` on-chain
3. **Recommended: Register on Base first** (cheaper gas, ~$0.01 vs ~$5 on Ethereum mainnet)
4. Base IdentityRegistry: Check https://erc8004.org or the ERC-8004 GitHub for deployed contract addresses
5. Call `registerAgent("https://zarq.ai/.well-known/agent-card.json", "ZARQ Risk Intelligence")`

### Agent Card Contents (already deployed)
```
GET https://zarq.ai/.well-known/agent-card.json
```
Update the agent-card to include ZARQ-specific skills:
- `check_token_risk`: Risk check for crypto tokens
- `get_trust_scores`: All token ratings
- `stress_test_portfolio`: Portfolio stress testing

### Gas Estimates
- Base: ~$0.01-0.05
- Ethereum mainnet: ~$3-10
- Solana: ~$0.001

---

## 4. Discord Posts (Ready to Copy-Paste)

### ElizaOS Discord

```
Built a free risk-check plugin for ElizaOS agents. Checks trust score, crash probability, and structural risk for 205 crypto tokens before your agent trades.

What it does:
- Returns SAFE / WARNING / CRITICAL verdict
- Trust score (0-100, Moody's-style Aaa-D scale)
- Crash probability and distance-to-default
- 100% recall on 113 structural collapses in backtesting

Zero API key, zero signup, free under 5,000 calls/day.

Install:
npm install @zarq/elizaos-plugin

Usage:
import zarqPlugin from "@zarq/elizaos-plugin";
// Add to your agent's plugins array
plugins: [zarqPlugin]

Your agent will automatically check token risk when users ask about crypto safety.

API: https://zarq.ai/v1/check/bitcoin
Docs: https://zarq.ai/zarq/docs
```

### LangChain Discord / Community

```
zarq-langchain — adds pre-trade risk intelligence to any LangChain agent in 2 lines.

pip install zarq-langchain

from zarq_langchain import ZARQRiskCheck
tools = [ZARQRiskCheck()]
# That's it. Your agent now checks 205 tokens for structural collapse signals.

What you get per check:
- Verdict: SAFE / WARNING / CRITICAL
- Trust Score: 0-100 (mapped to Moody's Aaa-D scale)
- Crash Probability (calibrated on 22 months OOS data)
- Distance to Default (Merton structural credit model)

100% recall on structural collapses, 98% precision. Free, no API key.

Try it: curl https://zarq.ai/v1/check/bitcoin
Docs: https://zarq.ai/zarq/docs
```

### r/algotrading Post

```
Title: Open-sourced a risk-scoring API for crypto trading bots — catches structural collapses before they happen

Built an API that scores 205 crypto tokens on structural risk — trust score, crash probability, distance-to-default. Think Merton's structural credit model adapted for crypto.

Backtest results (22 months out-of-sample, Jan 2024 — Feb 2026):
- 113/113 structural collapses detected (100% recall)
- 98% precision
- Average 22-month lead time before terminal failure
- Top save: Story (IP) dropped 86.2%, detected 80 days early
- Portable Alpha backtest: Sharpe 2.02 (conservative) to 5.56 (aggressive)

The API is free, no auth needed:
curl https://zarq.ai/v1/check/bitcoin

Returns: verdict (SAFE/WARNING/CRITICAL), trust score, crash probability, distance-to-default, rating (Moody's-style Aaa through D).

Integrations for LangChain, ElizaOS, Solana Agent Kit, and MCP (Claude Desktop). Also have a save-simulator showing the 50 biggest crash saves: https://zarq.ai/demo/save-simulator

Full docs: https://zarq.ai/zarq/docs
Paper trading live since March 2026 with SHA-256 hash-chained audit trail.

Feedback welcome — especially from anyone running crypto bots that could use pre-trade risk checks.
```

---

## 5. Verification Checklist

After completing registrations:

- [ ] `https://zarq.ai/v1/check/bitcoin` returns 200 from external network
- [ ] `https://zarq.ai/demo/save-simulator` renders correctly
- [ ] `https://zarq.ai/zarq/docs` renders correctly
- [ ] `https://mcp.zarq.ai/sse` responds (MCP SSE endpoint)
- [ ] Smithery listing visible at smithery.ai (search "zarq")
- [ ] Glama listing visible at glama.ai (search "zarq")
- [ ] `pip install zarq-langchain` works from PyPI (after publishing)
- [ ] `npm install @zarq/elizaos-plugin` works from npm (after publishing)
