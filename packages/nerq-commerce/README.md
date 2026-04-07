# nerq-commerce

Trust verification for agentic commerce. Verify AI shopping agents before they transact on your behalf.

Built on the [Nerq Trust Protocol](https://nerq.ai/protocol).

## Install

```bash
pip install nerq-commerce
```

## Quick Start — 3 Lines

```python
from nerq_commerce import verify_transaction

result = verify_transaction("my-agent", "vendor-agent", "purchase", "medium")
if result.approved:
    execute_transaction()
```

## CommerceGate — Production Use

```python
from nerq_commerce import CommerceGate

gate = CommerceGate(default_threshold=70, cache_ttl=300)

# Verify before purchase
result = gate.verify("shopping-assistant", "amazon-agent", "purchase", "high")
print(result.verdict)              # "approve", "review", or "reject"
print(result.agent_trust_score)    # 88.5
print(result.risk_factors)         # []
print(result.approved)             # True

# Batch verify
results = gate.verify_batch([
    {"agent_id": "a1", "counterparty_id": "b1", "transaction_type": "purchase", "amount_range": "low"},
    {"agent_id": "a2", "counterparty_id": "b2", "transaction_type": "payment", "amount_range": "critical"},
])
```

## Transaction Types

| Type | Description | Threshold Range |
|------|-------------|-----------------|
| `purchase` | Agent buying goods/services | 60-90 |
| `delegation` | Delegating tasks to another agent | 50-85 |
| `data_exchange` | Sharing data between agents | 40-80 |
| `payment` | Financial transactions | 65-95 |

## Amount Ranges

| Range | Description | Effect |
|-------|-------------|--------|
| `low` | < $100 equivalent | Lowest thresholds |
| `medium` | $100-$1,000 | Standard thresholds |
| `high` | $1,000-$10,000 | Stricter verification |
| `critical` | > $10,000 | Maximum scrutiny |

## Links

- [Commerce Trust](https://nerq.ai/commerce)
- [API Docs](https://nerq.ai/commerce/docs)
- [Protocol Spec](https://nerq.ai/protocol)
- [Integration Hub](https://nerq.ai/integrate)
