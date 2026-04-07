# Building Crypto Risk Intelligence Into Your Trading Bot

*How to add pre-trade safety checks, crash alerts, and risk-adjusted position sizing using the ZARQ API — in under 50 lines of code.*

---

Every crypto trading bot has the same blind spot: it knows price, volume, and maybe some technical indicators, but it has no idea if the token it's about to buy is showing structural signs of collapse.

ZARQ fixes that. Here's how to integrate crypto risk intelligence into any trading bot using our free API.

## The Problem

Consider what happened with FTX's FTT token, or Terra's LUNA. Bots that were optimizing for momentum or mean-reversion signals kept buying all the way down. A simple risk check — "is this token showing structural distress?" — would have flagged both well before the crash.

ZARQ's structural collapse detection system identified 113 out of 113 tokens that subsequently died during our out-of-sample validation period (January 2024 – February 2026), with 98% precision.

## Quick Start: The Safety Check Endpoint

The fastest integration is the pre-trade safety check. One API call, under 100ms response time, no authentication required:

```bash
curl https://zarq.ai/v1/crypto/safety/bitcoin
```

Response:
```json
{
  "data": {
    "token_id": "bitcoin",
    "safe": true,
    "risk_level": "WARNING",
    "trust_grade": "A2",
    "ndd": 4.2,
    "alert_level": "SAFE",
    "hc_alert": false,
    "crash_probability": 0.03,
    "flags": []
  }
}
```

The key field is `safe`. If it's `false`, your bot should think twice before entering a position.

## Integration Pattern: Pre-Trade Guard

Here's a minimal Python implementation:

```python
import requests

ZARQ_BASE = "https://zarq.ai/v1/crypto"

def is_safe_to_trade(token_id: str) -> bool:
    """Check if a token is safe before executing a trade."""
    try:
        r = requests.get(f"{ZARQ_BASE}/safety/{token_id}", timeout=5)
        data = r.json().get("data", {})
        
        # Block trade if any of these conditions
        if not data.get("safe", False):
            return False
        if data.get("crash_probability", 1.0) > 0.25:
            return False
        if data.get("alert_level") in ("CRITICAL", "STRUCTURAL_COLLAPSE"):
            return False
            
        return True
    except:
        return True  # Fail open — don't block trades on API errors

# Usage in your trading loop:
def execute_trade(token_id, side, amount):
    if side == "BUY" and not is_safe_to_trade(token_id):
        print(f"BLOCKED: {token_id} failed safety check")
        return
    # ... proceed with trade
```

That's it. Seven lines of logic that could have prevented losses on every major crypto collapse of 2022-2023.

## Advanced: Risk-Adjusted Position Sizing

For more sophisticated bots, use the full rating endpoint to adjust position sizes:

```python
def get_risk_multiplier(token_id: str) -> float:
    """Scale position size based on risk level."""
    r = requests.get(f"{ZARQ_BASE}/rating/{token_id}", timeout=5)
    data = r.json().get("data", {})
    
    score = data.get("score", 50)
    risk_level = data.get("risk_level", "WATCH")
    
    multipliers = {
        "SAFE": 1.0,
        "WATCH": 0.7,
        "WARNING": 0.3,
        "CRITICAL": 0.0,
    }
    
    return multipliers.get(risk_level, 0.5)
```

## Monitoring: Early Warning Webhook

Poll the early warning endpoint every hour to catch emerging risks:

```python
def check_portfolio_alerts(holdings: list[str]):
    """Check if any holdings have active alerts."""
    r = requests.get(f"{ZARQ_BASE}/early-warning", timeout=10)
    alerts = r.json().get("data", [])
    
    for alert in alerts:
        if alert["token_id"] in holdings:
            print(f"⚠️ ALERT: {alert['token_id']} — {alert['alert_level']}")
            print(f"   Crash probability: {alert.get('crash_probability', 'N/A')}")
```

## For AI Agent Developers

If you're building autonomous AI agents that trade crypto, ZARQ provides an MCP (Model Context Protocol) server for direct integration:

```json
{
  "mcpServers": {
    "zarq": {
      "url": "https://zarq.ai/mcp/sse",
      "transport": "sse"
    }
  }
}
```

Your agent can then call tools like `crypto_safety_check`, `crypto_rating`, and `crypto_alerts` natively.

## Rate Limits & Pricing

During beta, all endpoints are free with a 1,000 calls/day rate limit. That's enough for most trading bots (checking 100 tokens every 10 minutes = 600 calls/day).

No API key required. Just start calling.

## What's Next

- **Portfolio stresstest**: `POST /v1/crypto/stresstest` — test your entire portfolio against historical crash scenarios
- **Contagion mapping**: understand second-order risk through dependency chains
- **Paper trading signals**: follow our conviction-ranked long/short pairs at `/paper-trading`

Full API docs: [zarq.ai/docs](https://zarq.ai/docs)
White Paper: [zarq.ai/whitepaper](https://zarq.ai/whitepaper)
Bulk data (CC BY 4.0): [zarq.ai/data/crypto-ratings.jsonl.gz](https://zarq.ai/data/crypto-ratings.jsonl.gz)

---

*ZARQ is a crypto risk intelligence platform. Free during beta. Machine-first. [zarq.ai](https://zarq.ai)*
