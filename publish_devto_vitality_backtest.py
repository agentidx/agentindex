#!/usr/bin/env python3
"""Publish Vitality Score backtest article to Dev.to."""
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests not installed, saving as draft instead")
    sys.exit(1)

DEVTO_KEY_PATH = Path.home() / ".config" / "nerq" / "devto_api_key"
DRAFT_PATH = Path.home() / "agentindex" / "docs" / "devto-vitality-backtest.md"

title = "We Backtested Our Crypto Ecosystem Score — Here's What Predicted Crash Protection (p < 0.001)"

body_markdown = r"""During the 2025–2026 crypto crash, our top-quintile tokens lost 26% while bottom-quintile lost 70%.

We didn't cherry-pick this result. We tested across 3 time windows, 355–412 tokens each, with proper out-of-sample methodology. Here's what we found.

## What Is the Vitality Score?

[ZARQ](https://zarq.ai) rates 15,000+ crypto tokens on a 0–100 "Vitality Score" measuring ecosystem health across 5 weighted dimensions:

1. **Ecosystem Gravity** (20%) — protocol count, TVL, stablecoin presence on the token's chain(s)
2. **Capital Commitment** (20%) — TVL retention, yield pool density
3. **Coordination Efficiency** (15%) — DeFi category diversity, audit coverage
4. **Stress Resilience** (25%) — NDD stability, crash probability, drawdown behavior
5. **Organic Momentum** (20%) — TVL trend, price trend, rating trend

Grades range from S (≥85, exceptional) through F (<25, minimal).

## The Backtest: 3 Windows, No Look-Ahead Bias

We reconstructed a historical Vitality proxy at 3 past dates using only data available at that time, then measured forward returns:

| Window | Score Date | Forward Period | Tokens |
|--------|-----------|----------------|--------|
| A | Jan 2024 | Jan 2024 → Jan 2025 (12 months) | 355 |
| B | Jan 2025 | Jan 2025 → Jan 2026 (12 months) | 363 |
| C | Jul 2025 | Jul 2025 → Feb 2026 (crash, 8 months) | 412 |

For each window, we split tokens into quintiles by Vitality Score and measured median returns.

## The Results

### Window C (the crash window) — statistically significant

| Quintile | N | Vitality Score | Median Return |
|----------|---|----------------|---------------|
| **Q1 (TOP)** | 82 | 52.5–67.7 | **-26.1%** |
| Q2 | 82 | 43.6–52.3 | -48.8% |
| Q3 | 82 | 38.3–43.5 | -55.4% |
| Q4 | 82 | 33.3–38.2 | -56.1% |
| **Q5 (BOTTOM)** | 84 | 26.7–33.3 | **-70.4%** |

**Q1–Q5 spread: +44.3%. Perfectly monotonic (4/4 steps). t-statistic: 3.35, p-value: 0.0008.**

### Windows A and B

Window A (bull market): Q1–Q5 spread +9.3%, NOT statistically significant (p=0.556). The model doesn't predict upside well.

Window B (bear market): Q1–Q5 spread +27.1%, perfectly monotonic (4/4), but NOT significant (p=0.392) due to high variance.

## Which Dimension Matters Most?

We tested each dimension independently. The answer is clear:

| Dimension | Window B Spread | Window C Spread |
|-----------|----------------|----------------|
| **Stress Resilience** | **+66.1%** | **+52.5%** |
| Organic Momentum | +1.1% | +6.2% |
| Capital Commitment | -1.9% | +3.2% |
| Ecosystem Gravity | -11.4% | -8.3% |
| Coordination Efficiency | -18.5% | -8.6% |

**Stress Resilience dominates.** Ecosystem Gravity and Coordination Efficiency actually show *negative* spreads — they measure ecosystem quality but don't predict returns.

## Being Honest About Limitations

- Only Window C is statistically significant. Windows A and B show the right direction but aren't conclusive alone.
- The model predicts **downside protection** better than **upside performance**.
- Sample sizes are 355–412 tokens per window — large for crypto research but small in absolute terms.
- **Survivorship bias**: tokens that died during windows are excluded from the analysis.
- Crypto returns are fat-tailed and non-normal — p-values should be interpreted cautiously.
- **Past performance does not guarantee future results.**

## How to Use It

Check any token's Vitality Score:

```
GET https://zarq.ai/v1/vitality/ethereum
```

Response:
```json
{
  "token": "ethereum",
  "vitality_score": 65.0,
  "grade": "B",
  "dimensions": {
    "ecosystem_gravity": 97.6,
    "capital_commitment": 53.3,
    "coordination_efficiency": 80.8,
    "stress_resilience": 58.9,
    "organic_momentum": 40.0
  },
  "confidence": 100,
  "interpretation": "Developing ecosystem with solid fundamentals"
}
```

Or check it alongside Trust Score and crash probability:

```
GET https://zarq.ai/v1/check/ethereum
```

## The Bottom Line

Vitality Score is most valuable as a **crash protection indicator**. Tokens with high ecosystem quality — especially high Stress Resilience — lost significantly less during the 2025–2026 crash. The signal is consistent across all 3 windows but only statistically significant in the crash window.

This doesn't mean high-Vitality tokens will go up. It means they're less likely to collapse when the market turns.

**Links:**
- [Vitality Score Rankings](https://zarq.ai/vitality) — all 15,000+ tokens ranked
- [Full Backtest Results](https://zarq.ai/vitality/backtest) — detailed methodology + data
- [Methodology](https://zarq.ai/vitality/methodology) — how the 5 dimensions are calculated
- [API Documentation](https://zarq.ai/docs) — free, no auth required

---

*Data and analysis by [ZARQ](https://zarq.ai) — the trust layer for the machine economy.*
"""

tags = ["crypto", "investing", "datascience", "defi"]
canonical_url = "https://zarq.ai/vitality/backtest"


def publish():
    """Publish to Dev.to or save as draft."""
    # Save draft locally
    DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRAFT_PATH.write_text(f"# {title}\n\n{body_markdown}")
    print(f"Draft saved to {DRAFT_PATH}")

    # Try to publish
    if not DEVTO_KEY_PATH.exists():
        print(f"No Dev.to API key found at {DEVTO_KEY_PATH}")
        print("To publish, create the file with your Dev.to API key")
        return

    api_key = DEVTO_KEY_PATH.read_text().strip()
    resp = requests.post(
        "https://dev.to/api/articles",
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "article": {
                "title": title,
                "body_markdown": body_markdown,
                "published": True,
                "tags": tags,
                "canonical_url": canonical_url,
            }
        },
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        print(f"Published: {data.get('url', 'unknown URL')}")
    else:
        print(f"Error {resp.status_code}: {resp.text[:500]}")


if __name__ == "__main__":
    publish()
