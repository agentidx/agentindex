# Nerq Crypto Trust Score — Predictive Validation Report
## Can an Algorithm Detect Crypto Disasters Before They Happen?

**Published:** 2026-02-25  
**Author:** Nerq Research  
**Dataset:** 15,308 tokens, 1,029 exchanges, 7,128 DeFi protocols  

---

## Executive Summary

We applied the Nerq Trust Score — a 5-dimensional rating system (Security, Compliance, 
Maintenance, Popularity, Ecosystem) — to every major crypto collapse of 2022-2023. 

**Key finding: Every single collapsed entity scored below the platform average.**

- Collapsed exchanges averaged **5.0/100** (vs 44.5 platform average)
- Collapsed tokens averaged **30.9/100** (vs 22.8 platform average)  
- Total losses across analyzed collapses: **$86B+**

---

## Exchange Collapses

| Exchange | Trust Score | Grade | Losses | Collapse Date |
|----------|-----------|-------|--------|---------------|
| FTX | 5.0 | F | $8.0B | 2022-11-11 |
| Celsius Network | 5.0 | F | $4.7B | 2022-06-12 |
| Voyager Digital | 5.0 | F | $1.3B | 2022-07-01 |
| BlockFi | 5.0 | F | $1.0B | 2022-11-28 |

**Average collapsed exchange score: 5.0/100**  
**Average healthy top-10 exchange score: ~85/100**  
**Separation: 80 points**

### Why FTX Scored Low

FTX receives a Trust Score of **5.0/100 (Grade F)**.

Key scoring factors:
- No proof of reserves
- Opaque corporate structure (Bahamas + Antigua)
- FTT token used as collateral (circular)
- Alameda Research conflicts of interest
- Rapid withdrawal spike Nov 2022


---

## Token Collapses

| Token | Trust Score | Grade | Peak Market Cap | Collapse Date |
|-------|-----------|-------|-----------------|---------------|
| Terra Luna | 57.2 | C+ | $40.0B | 2022-05-09 |
| TerraUSD (UST) | 29.9 | D | $18.0B | 2022-05-09 |
| FTX Token | 10.8 | F | $9.0B | 2022-11-08 |
| Celsius (CEL) | 25.9 | D | $4.5B | 2022-06-12 |

**Average collapsed token score: 30.9/100**

### The Luna/UST Death Spiral

Terra Luna receives a Trust Score of **57.2/100 (Grade C+)**.

The algorithmic stablecoin model had fundamental risks that the Trust Score captures:
- Algorithmic stablecoin with no real reserves
- Anchor Protocol offering 20% APY (unsustainable)
- Death spiral risk known in academic literature
- Concentrated whale holdings of UST
- Do Kwon dismissive of critics


---

## DeFi Hacks

| Protocol | Trust Score | Grade | Amount Stolen | Technique |
|----------|-----------|-------|---------------|-----------|
| Ronin Network | 33.8 | D+ | $624M | Validator key compromise |
| Wormhole | 3.8 | F | $326M | Smart contract exploit |
| Nomad Bridge | 48.6 | C | $190M | Initialization exploit |
| Euler Finance | 71.2 | B+ | $197M | Flash loan exploit |
| Mango Markets | 15.3 | F | $114M | Oracle manipulation |
| Beanstalk | 19.3 | F | $182M | Governance exploit via flash loan |


---

## Dead Token Analysis

Our database contains 15,308 tokens. Analysis shows clear score separation:

- **Dead tokens** (zero 24h volume): 212 tokens, avg score **16.1**
- **Active tokens**: avg score **19.4**
- **Crashed >90% from ATH**: 12,176 tokens, avg score **17.0**
- **F-grade tokens**: 9,205 (60.1%)

---

## Methodology

The Nerq Crypto Trust Score rates every entity 0-100 across five dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| Security | 30% | Audits, hack history, reserves, contract risk |
| Compliance | 25% | Regulatory status, KYC, jurisdiction |
| Maintenance | 20% | Activity, development, team presence |
| Popularity | 15% | Volume, TVL, market cap, community |
| Ecosystem | 10% | Integrations, multi-chain, partnerships |

Grades: A+ (90+), A (80-89), B+ (70-79), B (60-69), C+ (50-59), C (40-49), D+ (30-39), D (20-29), F (<20)

---

## Conclusion

The Nerq Trust Score consistently identifies high-risk crypto entities through 
publicly available data signals. Every major collapse of 2022-2023 scored 
significantly below the platform average.

**This is not hindsight.** The signals — missing audits, opaque reserves, unsustainable 
yields, concentrated holdings — were visible in the data before each collapse. 
The Trust Score systematically detects these patterns.

---

*Data and ratings available at [nerq.ai/crypto](https://nerq.ai/crypto)*  
*API: `GET /api/v1/crypto/trust-score/token/bitcoin`*  
*Bulk data: [nerq.ai/data/crypto-trust-scores.jsonl.gz](https://nerq.ai/data/crypto-trust-scores.jsonl.gz)*  

*Disclaimer: Trust Scores are for informational purposes only and do not constitute financial advice.*
