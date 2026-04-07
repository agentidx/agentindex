# S3 — Agent Distribution: Framework Plugins

**Date:** 2026-03-07
**Status:** Complete — 61/61 tests passing

---

## Task A: LangChain Tool Wrapper

**File:** `integrations/langchain/zarq_langchain.py`

- `ZARQRiskCheck` class extending `BaseTool` from `langchain_core`
- Pydantic `ZARQRiskCheckInput` schema with `token` field
- Sync `_run()` and async `_arun()` methods
- Calls `GET {api_base}/v1/check/{token}`, returns formatted multi-line string
- Handles 404 (unknown token) with helpful error
- Verdict-specific advice: CRITICAL = "avoid trading", WARNING = "reduce position", SAFE = "no issues"
- Configurable `api_base` for local testing

**3-line integration:**
```python
from zarq_langchain import ZARQRiskCheck
tools = [ZARQRiskCheck()]
agent = initialize_agent(tools, llm, agent=AgentType.OPENAI_FUNCTIONS)
```

---

## Task B: ElizaOS Plugin

**File:** `integrations/elizaos/plugin-zarq.ts`

- Full ElizaOS plugin with `CHECK_TOKEN_RISK` action
- `validate()` triggers on crypto risk/safety/trade messages
- `handler()` extracts token from message via LLM (using `generateObject` + Zod schema)
- Common symbol-to-CoinGecko mapping (BTC→bitcoin, ETH→ethereum, etc.)
- Formatted markdown response with verdict, scores, and recommendation
- Two `ActionExample` pairs for ElizaOS example system
- 5 similes: CHECK_CRYPTO_RISK, TOKEN_SAFETY_CHECK, etc.
- Exports: `zarqPlugin` (default), `checkTokenRisk`, `formatRiskReport`

**1-line integration:**
```typescript
import zarqPlugin from "./plugin-zarq";
plugins: [zarqPlugin]
```

---

## Task C: Solana Agent Kit Tool

**File:** `integrations/solana-agent-kit/zarq_tool.py`

- `check_token_risk(mint_or_symbol)` — accepts mint addresses, symbols, or CoinGecko IDs
- `resolve_token_id()` with 3-level resolution: mint → symbol → coingecko ID
- 12 Solana mint address mappings (SOL, USDC, USDT, JUP, BONK, POPCAT, etc.)
- 25+ symbol mappings (SOL, BTC, ETH, DOGE, ADA, XRP, DOT, etc.)
- Adds `recommendation` field to response: "DO NOT TRADE", "REDUCE POSITION", or "OK TO TRADE"
- `ZARQ_TOOL_DEFINITION` dict compatible with Solana Agent Kit tool format

**1-line integration:**
```python
from zarq_tool import check_token_risk
risk = check_token_risk("SOL")
```

---

## Task D: Universal README

**File:** `integrations/README.md`

Shows the 1-line integration for each framework:
- LangChain / LangGraph
- ElizaOS
- Solana Agent Kit
- MCP (Claude, Cursor)
- Raw HTTP (any language)

Plus response field reference table.

---

## Files Created

| File | Description |
|------|-------------|
| `integrations/langchain/zarq_langchain.py` | LangChain BaseTool with sync + async |
| `integrations/langchain/README.md` | Usage, examples, API details |
| `integrations/elizaos/plugin-zarq.ts` | ElizaOS plugin with CHECK_TOKEN_RISK action |
| `integrations/elizaos/README.md` | Installation, trigger examples |
| `integrations/solana-agent-kit/zarq_tool.py` | Solana Agent Kit tool with mint resolution |
| `integrations/solana-agent-kit/README.md` | Usage, mint table, pre-trade pattern |
| `integrations/README.md` | Universal 1-line integration guide |

## Test Results

```
61 passed, 103 warnings in 39.04s
```

New tests (+9):
- `TestSolanaAgentKitTool::test_resolve_symbol` — SOL/BTC/ETH symbol resolution
- `TestSolanaAgentKitTool::test_resolve_mint` — Solana mint address resolution
- `TestSolanaAgentKitTool::test_resolve_coingecko_id` — passthrough IDs
- `TestSolanaAgentKitTool::test_check_token_risk_live` — live API call with SOL
- `TestSolanaAgentKitTool::test_check_token_risk_unknown` — unknown token error
- `TestSolanaAgentKitTool::test_tool_definition_has_required_keys` — tool format validation
- `TestLangChainTool::test_langchain_tool_imports` — import + name/description
- `TestLangChainTool::test_langchain_tool_run` — live API call with bitcoin
- `TestLangChainTool::test_langchain_tool_unknown_token` — 404 handling
