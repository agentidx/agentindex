# Partnership Proposal: Nerq + AI Agents Directory

## Proposal

Add Nerq trust scores to AI Agents Directory listings, giving developers immediate visibility into agent reliability and security.

## What Nerq Provides

- Trust scores for 204,000+ AI agents
- 6-dimension analysis: Code Quality, Community, Compliance, Security, Operational Health, External Validation
- Free API — no authentication required
- Embeddable trust badges (SVG)

## Integration

**Simple badge embed** for each agent listing:
```html
<img src="https://nerq.ai/badge/{agent_name}.svg" alt="Nerq Trust Score">
```

**API enrichment** for detailed data:
```
GET https://nerq.ai/v1/preflight?target={agent_name}
→ { "trust_score": 82, "grade": "A", "recommendation": "SAFE", ... }
```

## Mutual Benefits

- **For AI Agents Directory**: Differentiate with trust data, increase user confidence
- **For Nerq**: Reach the directory's developer audience, increase API adoption
- **For developers**: Make informed decisions about which agents to use

## Contact

Anders Nilsson — anders@nerq.ai
https://nerq.ai
