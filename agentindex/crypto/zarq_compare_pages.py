"""
ZARQ Compare Pages — Tool Comparisons + Hub
=============================================
4 tool comparison pages (ZARQ vs competitor) + 1 hub page.

Pages:
  GET /compare                    — Comparison hub (zarq.ai only)
  GET /compare/zarq-vs-token-sniffer
  GET /compare/zarq-vs-rugcheck
  GET /compare/zarq-vs-goplus
  GET /compare/zarq-vs-suprafin

Usage in discovery.py (BEFORE mount_compare_pages):
    from agentindex.crypto.zarq_compare_pages import mount_zarq_compare_hub
    mount_zarq_compare_hub(app)
"""

import json
import logging
from datetime import date

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

logger = logging.getLogger("zarq.compare_pages")

SITE_URL = "https://zarq.ai"
TODAY = date.today().isoformat()


def _esc(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ─── Design tokens (shared ZARQ dark theme) ──────────────────────────

ZARQ_CSS = """:root {
  --white: #fafaf9; --black: #0a0a0a;
  --gray-100: #f5f5f4; --gray-200: #e7e5e4; --gray-400: #a8a29e;
  --gray-500: #78716c; --gray-600: #57534e; --gray-700: #44403c;
  --gray-800: #292524; --gray-900: #1c1917;
  --warm: #c2956b; --warm-light: rgba(194,149,107,0.08);
  --green: #16a34a; --red: #dc2626;
  --serif: 'DM Serif Display', serif;
  --sans: 'DM Sans', sans-serif;
  --mono: 'JetBrains Mono', monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--black); color: var(--white); font-family: var(--sans); min-height: 100vh; }
nav { padding: 16px 24px; border-bottom: 1px solid #1c1917; display: flex; align-items: center; gap: 16px; position: relative; }
nav a { color: var(--warm); text-decoration: none; font-family: var(--serif); font-size: 20px; }
nav .breadcrumb { font-family: var(--mono); font-size: 11px; color: var(--gray-500); }
.nav-mark { font-family: var(--mono); font-weight: 500; font-size: 15px; letter-spacing: 0.15em; text-transform: uppercase; color: var(--white); text-decoration: none; }
.nav-links { display: flex; gap: 24px; align-items: center; margin-left: auto; }
.nav-links a { font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-500); text-decoration: none; }
.nav-links a:hover { color: var(--white); }
.nav-api { font-size: 11px; color: var(--warm); border: 1px solid var(--warm); padding: 4px 12px; }
.nav-api:hover { background: var(--warm); color: var(--black); }
.nav-dropdown { position: relative; }
.nav-dropdown-trigger { cursor: pointer; }
.nav-dropdown-menu { display: none; position: absolute; top: 100%; right: 0; background: var(--gray-900); border: 1px solid #292524; padding: 8px 0; min-width: 180px; z-index: 200; }
.nav-dropdown:hover .nav-dropdown-menu { display: block; }
.nav-dropdown-menu a { display: block; padding: 8px 20px; font-family: var(--mono); font-size: 12px; color: var(--gray-500); white-space: nowrap; }
.nav-dropdown-menu a:hover { background: var(--warm-light); color: var(--white); }
.nav-toggle-input { display: none; }
.nav-hamburger { display: none; cursor: pointer; flex-direction: column; gap: 5px; }
.nav-hamburger span { display: block; width: 22px; height: 2px; background: var(--white); }
@media (max-width: 768px) {
  .nav-hamburger { display: flex; }
  .nav-links { display: none; position: absolute; top: 100%; left: 0; right: 0; background: var(--gray-900); border-bottom: 1px solid #292524; padding: 16px 20px; flex-direction: column; gap: 16px; }
  .nav-toggle-input:checked ~ .nav-links { display: flex; }
  .nav-dropdown-menu { display: block; position: static; border: none; padding: 0 0 0 12px; }
  .nav-dropdown-trigger { display: none; }
}
.container { max-width: 900px; margin: 0 auto; padding: 40px 24px; }
h1 { font-family: var(--serif); font-size: clamp(24px, 4vw, 36px); color: var(--white); margin-bottom: 8px; }
h2 { font-family: var(--serif); font-size: 22px; color: var(--white); margin-bottom: 16px; }
h3 { font-family: var(--serif); font-size: 17px; color: var(--white); }
.subtitle { color: var(--gray-500); font-size: 14px; margin-bottom: 40px; font-family: var(--mono); }
a { color: var(--warm); text-decoration: none; }
a:hover { text-decoration: underline; }
.card { background: var(--gray-900); border: 1px solid #292524; border-radius: 12px; padding: 24px; margin-bottom: 16px; }
.card.highlight { border-color: var(--warm); }
.badge { display: inline-block; font-family: var(--mono); font-size: 11px; font-weight: 700;
  padding: 2px 8px; border-radius: 4px; color: var(--white); background: var(--warm); }
.badge-yes { background: var(--green); }
.badge-no { background: #57534e; }
.feature-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 24px 0; }
.feature-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #1c1917; font-size: 13px; }
.feature-row:last-child { border-bottom: none; }
.feature-row .label { color: var(--gray-400); }
.bar-wrap { background: #292524; border-radius: 4px; height: 8px; width: 100%; margin-top: 4px; }
.bar-fill { border-radius: 4px; height: 8px; }
.faq { margin-bottom: 40px; }
.faq-item { border-bottom: 1px solid #1c1917; padding: 16px 0; }
.faq-item h3 { font-size: 15px; font-weight: 600; color: var(--white); margin-bottom: 6px; }
.faq-item p { font-size: 13px; color: var(--gray-500); line-height: 1.6; }
.hub-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin: 24px 0; }
.hub-card { background: var(--gray-900); border: 1px solid #292524; border-radius: 12px; padding: 20px;
  transition: border-color 0.2s; }
.hub-card:hover { border-color: var(--warm); }
.hub-card h3 { font-family: var(--serif); font-size: 16px; margin-bottom: 6px; }
.hub-card p { font-size: 12px; color: var(--gray-500); line-height: 1.5; }
.hub-card .tag { font-family: var(--mono); font-size: 10px; color: var(--warm); text-transform: uppercase;
  letter-spacing: 0.1em; margin-bottom: 6px; }
footer { border-top: 1px solid #1c1917; padding: 24px; text-align: center; font-size: 12px;
  color: var(--gray-600); font-family: var(--mono); }
.verdict { background: var(--warm-light); border: 1px solid var(--warm); border-radius: 8px;
  padding: 20px; margin: 24px 0; }
.verdict strong { color: var(--warm); font-family: var(--serif); }
@media (max-width: 640px) {
  .feature-grid { grid-template-columns: 1fr; }
  .hub-grid { grid-template-columns: 1fr; }
}"""

FONTS_LINK = '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'


# ─── Competitor data ──────────────────────────────────────────────────

COMPETITORS = {
    "token-sniffer": {
        "name": "Token Sniffer",
        "slug": "zarq-vs-token-sniffer",
        "tagline": "Smart contract scanner vs structural risk model",
        "description": (
            "Token Sniffer scans ERC-20 smart contracts for honeypots, rug pulls, and "
            "common scam patterns. It offers a free tier with premium features for deeper "
            "contract audits. Token Sniffer focuses on contract-level security."
        ),
        "features": {
            "Smart contract scanning":       ("No",  "Yes"),
            "Honeypot detection":            ("No",  "Yes"),
            "Structural risk model (NDD)":   ("Yes", "No"),
            "Crash probability prediction":  ("Yes", "No"),
            "Letter ratings (Aaa-D)":        ("Yes", "No"),
            "Multi-chain coverage":          ("Yes", "Partial"),
            "Distance-to-Default metric":    ("Yes", "No"),
            "Daily automated scoring":       ("Yes", "No"),
            "Hash-chained audit trail":      ("Yes", "No"),
            "Rug pull pattern detection":    ("No",  "Yes"),
        },
        "zarq_strengths": [
            "7-signal structural risk model predicts collapse, not just scams",
            "Distance-to-Default (NDD) quantifies how far a token is from structural failure",
            "Moody's-style letter ratings (Aaa through D) for institutional clarity",
            "198 tokens with daily automated scoring pipeline",
            "100% recall on structural collapse, 98% precision",
        ],
        "competitor_strengths": [
            "Contract-level scanning catches honeypots and rug pull code patterns",
            "Broad ERC-20 token coverage including new launches",
            "Free tier available for basic checks",
        ],
        "verdict": (
            "Token Sniffer tells you if a smart contract has malicious code. "
            "ZARQ tells you if the token's structural foundation is cracking. "
            "They solve different problems: Token Sniffer catches scams at the contract level, "
            "while ZARQ predicts structural collapse using quantitative risk modeling. "
            "For a complete risk picture, use both."
        ),
        "faq": [
            ("What is the difference between ZARQ and Token Sniffer?",
             "Token Sniffer focuses on scanning smart contract code for honeypots, rug pulls, and known scam patterns. "
             "ZARQ uses a 7-signal structural risk model with Distance-to-Default (NDD) to predict token collapse. "
             "Token Sniffer checks the code; ZARQ assesses fundamental structural health."),
            ("Does ZARQ detect rug pulls?",
             "ZARQ does not scan smart contract code for rug pull patterns. Instead, it detects structural weakness "
             "that precedes collapse -- including tokens that may rug pull -- through its NDD metric and crash probability model. "
             "ZARQ has 100% recall on structural collapse events."),
            ("Can I use ZARQ and Token Sniffer together?",
             "Yes. Token Sniffer provides contract-level security checks (is the code safe?), while ZARQ provides "
             "structural risk assessment (is the token fundamentally sound?). Together they cover both surface-level "
             "and deep structural risk."),
        ],
    },
    "rugcheck": {
        "name": "RugCheck",
        "slug": "zarq-vs-rugcheck",
        "tagline": "Solana rug pull checker vs multi-chain structural risk",
        "description": (
            "RugCheck is a Solana-focused tool that scans token contracts for rug pull indicators. "
            "It analyzes liquidity locks, holder distribution, mint authority, and freeze authority. "
            "RugCheck is popular in the Solana memecoin ecosystem."
        ),
        "features": {
            "Liquidity lock analysis":       ("No",  "Yes"),
            "Holder distribution check":     ("No",  "Yes"),
            "Structural risk model (NDD)":   ("Yes", "No"),
            "Crash probability prediction":  ("Yes", "No"),
            "Letter ratings (Aaa-D)":        ("Yes", "No"),
            "Multi-chain coverage":          ("Yes", "No"),
            "Distance-to-Default metric":    ("Yes", "No"),
            "Daily automated scoring":       ("Yes", "No"),
            "Hash-chained audit trail":      ("Yes", "No"),
            "Solana-specific checks":        ("No",  "Yes"),
        },
        "zarq_strengths": [
            "Multi-chain coverage (198 tokens) vs Solana-only",
            "Structural collapse prediction with quantitative NDD model",
            "Moody's-style letter ratings for institutional-grade risk communication",
            "Crash probability scoring -- not just pass/fail",
            "Hash-chained audit trail for verifiable, tamper-proof history",
        ],
        "competitor_strengths": [
            "Deep Solana-specific analysis (mint authority, freeze authority)",
            "Liquidity lock and holder concentration checks",
            "Fast rug pull indicator scanning for new Solana tokens",
        ],
        "verdict": (
            "RugCheck is excellent for quick Solana rug pull checks on new tokens. "
            "ZARQ provides multi-chain structural risk intelligence with quantitative modeling. "
            "If you are trading Solana memecoins, RugCheck catches obvious scams. "
            "If you need to understand whether a token's foundation is structurally sound, ZARQ's NDD model goes deeper."
        ),
        "faq": [
            ("Is ZARQ better than RugCheck?",
             "They serve different purposes. RugCheck is a Solana-focused rug pull scanner that checks liquidity locks and "
             "holder distribution. ZARQ is a multi-chain structural risk platform that predicts collapse using Distance-to-Default. "
             "RugCheck is faster for Solana-specific checks; ZARQ is deeper for structural risk assessment."),
            ("Does ZARQ cover Solana tokens?",
             "ZARQ covers 198 tokens across multiple chains, including major Solana ecosystem tokens. "
             "However, ZARQ focuses on established tokens with sufficient data for structural modeling, "
             "not newly launched memecoins. RugCheck is better suited for brand-new Solana token launches."),
            ("What does Distance-to-Default mean?",
             "Distance-to-Default (NDD) is ZARQ's proprietary metric that measures how far a token is from structural collapse. "
             "A higher NDD means the token has more structural buffer. When NDD drops below critical thresholds, "
             "ZARQ issues crash probability warnings. This is a fundamentally different approach from contract scanning."),
        ],
    },
    "goplus": {
        "name": "GoPlus",
        "slug": "zarq-vs-goplus",
        "tagline": "Security API vs structural risk intelligence",
        "description": (
            "GoPlus provides a security API for Web3 applications. It offers contract scanning, "
            "address risk assessment, phishing URL detection, and dApp security checks. "
            "GoPlus is API-first and multi-chain, used by wallets and DEXs for real-time security."
        ),
        "features": {
            "Contract security scanning":    ("No",  "Yes"),
            "Address risk assessment":       ("No",  "Yes"),
            "Phishing URL detection":        ("No",  "Yes"),
            "Structural risk model (NDD)":   ("Yes", "No"),
            "Crash probability prediction":  ("Yes", "No"),
            "Letter ratings (Aaa-D)":        ("Yes", "No"),
            "Multi-chain coverage":          ("Yes", "Yes"),
            "API access":                    ("Yes", "Yes"),
            "Hash-chained audit trail":      ("Yes", "No"),
            "dApp security checks":          ("No",  "Yes"),
        },
        "zarq_strengths": [
            "Structural collapse prediction -- not just contract security",
            "Distance-to-Default provides quantitative risk measurement",
            "Moody's-style letter ratings for institutional decision-making",
            "Daily automated pipeline with hash-chained audit trail",
            "100% recall on structural collapse, 98% precision",
        ],
        "competitor_strengths": [
            "Broad security API covering contracts, addresses, URLs, and dApps",
            "Real-time phishing and malicious address detection",
            "Widely integrated into wallets and DEXs for transaction screening",
        ],
        "verdict": (
            "GoPlus is a comprehensive security API that protects users from malicious contracts, "
            "phishing URLs, and risky addresses. ZARQ focuses on structural risk -- predicting "
            "whether a token will collapse, not whether a contract is malicious. "
            "GoPlus answers 'Is this interaction safe?' while ZARQ answers 'Is this asset structurally sound?'"
        ),
        "faq": [
            ("How does ZARQ compare to GoPlus Security?",
             "GoPlus is a security API that scans contracts, addresses, and URLs for malicious activity. "
             "ZARQ is a structural risk platform that predicts token collapse using a 7-signal model. "
             "GoPlus protects against scams and phishing; ZARQ predicts fundamental structural failure."),
            ("Does ZARQ offer an API like GoPlus?",
             "Yes. ZARQ provides API access to Trust Scores, letter ratings, NDD values, and crash probabilities. "
             "However, ZARQ's API focuses on risk intelligence rather than transaction-level security screening. "
             "GoPlus is better for real-time transaction security; ZARQ is better for risk assessment and portfolio monitoring."),
            ("Which should I use for my DeFi protocol?",
             "Consider using both. GoPlus can screen incoming transactions for malicious contracts and phishing. "
             "ZARQ can assess the structural health of tokens in your protocol's liquidity pools. "
             "Together they provide security (GoPlus) plus risk intelligence (ZARQ)."),
        ],
    },
    "suprafin": {
        "name": "SupraFin",
        "slug": "zarq-vs-suprafin",
        "tagline": "DeFi analytics dashboard vs crash risk intelligence",
        "description": (
            "SupraFin is a DeFi analytics dashboard that tracks yield opportunities, TVL changes, "
            "and protocol comparisons. It helps users find and compare DeFi yield farming opportunities "
            "across protocols."
        ),
        "features": {
            "Yield tracking":                ("No",  "Yes"),
            "TVL analysis":                  ("No",  "Yes"),
            "Protocol comparison":           ("No",  "Yes"),
            "Structural risk model (NDD)":   ("Yes", "No"),
            "Crash probability prediction":  ("Yes", "No"),
            "Letter ratings (Aaa-D)":        ("Yes", "No"),
            "Multi-chain coverage":          ("Yes", "Yes"),
            "Daily automated scoring":       ("Yes", "No"),
            "Hash-chained audit trail":      ("Yes", "No"),
            "DeFi yield optimization":       ("No",  "Yes"),
        },
        "zarq_strengths": [
            "Predicts structural collapse -- critical for yield farming risk management",
            "NDD model quantifies real risk behind high-APY opportunities",
            "Letter ratings communicate risk level without requiring DeFi expertise",
            "Crash probability helps avoid yield farms on structurally weak tokens",
            "Hash-chained audit trail provides verifiable risk history",
        ],
        "competitor_strengths": [
            "Comprehensive yield farming opportunity discovery",
            "TVL tracking and protocol-level analytics",
            "Side-by-side DeFi protocol comparison tools",
        ],
        "verdict": (
            "SupraFin helps you find yield opportunities. ZARQ helps you understand the risk behind them. "
            "A high-APY yield farm means nothing if the underlying token collapses. "
            "SupraFin answers 'Where is the yield?' while ZARQ answers 'Will this token survive?' "
            "Use SupraFin to find opportunities, then check ZARQ to understand the structural risk."
        ),
        "faq": [
            ("Should I use ZARQ or SupraFin for DeFi investing?",
             "They complement each other. SupraFin helps discover yield opportunities and compare DeFi protocols. "
             "ZARQ assesses the structural health of tokens underlying those opportunities. "
             "A high APY on a structurally weak token is a trap -- ZARQ's crash probability helps you avoid that."),
            ("Does ZARQ track DeFi yields?",
             "No. ZARQ focuses exclusively on risk intelligence: Trust Scores, Distance-to-Default, crash probability, "
             "and letter ratings. For yield tracking and TVL analytics, use a platform like SupraFin. "
             "Then use ZARQ to assess whether the tokens behind those yields are structurally sound."),
            ("What is crash probability and why does it matter for DeFi?",
             "Crash probability is ZARQ's prediction of structural collapse likelihood. For DeFi users, this is critical: "
             "if a token in your liquidity pool or yield farm has a high crash probability, your position is at risk of "
             "catastrophic loss regardless of the stated APY. ZARQ has 100% recall on structural collapse events."),
        ],
    },
}


TOKEN_PAIRS = [
    ("bitcoin-vs-ethereum",         "Bitcoin vs Ethereum"),
    ("solana-vs-avalanche-2",       "Solana vs Avalanche"),
    ("bnb-vs-matic-network",        "BNB vs Polygon"),
    ("cardano-vs-polkadot",         "Cardano vs Polkadot"),
    ("bitcoin-vs-solana",           "Bitcoin vs Solana"),
    ("ethereum-vs-solana",          "Ethereum vs Solana"),
    ("dogecoin-vs-shiba-inu",       "Dogecoin vs Shiba Inu"),
    ("chainlink-vs-uniswap",       "Chainlink vs Uniswap"),
    ("aave-vs-uniswap",            "Aave vs Uniswap"),
    ("bitcoin-vs-ripple",          "Bitcoin vs XRP"),
    ("ethereum-vs-cardano",        "Ethereum vs Cardano"),
    ("solana-vs-near",             "Solana vs NEAR"),
    ("bnb-vs-tron",                "BNB vs TRON"),
    ("litecoin-vs-dogecoin",       "Litecoin vs Dogecoin"),
    ("avalanche-2-vs-arbitrum",    "Avalanche vs Arbitrum"),
    ("polkadot-vs-chainlink",      "Polkadot vs Chainlink"),
]


# ─── Page renderers ──────────────────────────────────────────────────

def _render_tool_comparison(comp):
    """Render a ZARQ vs {competitor} tool comparison page."""
    name = comp["name"]
    slug = comp["slug"]
    url = f"{SITE_URL}/compare/{slug}"
    title = f"ZARQ vs {name} — Crypto Risk Tool Comparison | ZARQ"
    desc = (
        f"Compare ZARQ vs {name}. {comp['tagline']}. "
        f"ZARQ offers structural risk prediction with Distance-to-Default, crash probability, "
        f"and Moody's-style ratings. See the full feature comparison."
    )

    # JSON-LD: WebPage + FAQPage + BreadcrumbList
    web_page_schema = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": desc,
        "url": url,
        "provider": {"@type": "Organization", "name": "ZARQ", "url": SITE_URL},
    }

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in comp["faq"]
        ],
    }

    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": "Compare", "item": f"{SITE_URL}/compare"},
            {"@type": "ListItem", "position": 3, "name": f"ZARQ vs {name}", "item": url},
        ],
    }

    ai_comment = (
        f"<!-- AI-Citable Summary: ZARQ vs {name} comparison. "
        f"ZARQ is a structural risk intelligence platform offering a 7-signal risk model, "
        f"Distance-to-Default (NDD), crash probability, and Moody's-style letter ratings (Aaa-D) "
        f"for 198 crypto tokens. {name}: {comp['description']} "
        f"Key difference: {comp['verdict']} "
        f"Source: ZARQ (zarq.ai) -- independent crypto risk intelligence. -->"
    )

    # Feature rows
    feature_html = ""
    for feature, (zarq_val, comp_val) in comp["features"].items():
        zarq_cls = "badge-yes" if zarq_val == "Yes" else "badge-no"
        comp_cls = "badge-yes" if comp_val == "Yes" else ("badge-no" if comp_val == "No" else "")
        comp_style = "" if comp_cls else f' style="background:#d97706"'
        feature_html += f"""<div class="feature-row">
  <span class="label">{_esc(feature)}</span>
  <span><span class="badge {zarq_cls}">ZARQ: {zarq_val}</span> <span class="badge {comp_cls}"{comp_style}>{_esc(name)}: {comp_val}</span></span>
</div>\n"""

    # Strengths lists
    zarq_strengths_html = "".join(
        f'<li style="margin-bottom:6px;font-size:13px;color:var(--gray-400)">{_esc(s)}</li>'
        for s in comp["zarq_strengths"]
    )
    comp_strengths_html = "".join(
        f'<li style="margin-bottom:6px;font-size:13px;color:var(--gray-400)">{_esc(s)}</li>'
        for s in comp["competitor_strengths"]
    )

    # FAQ
    faq_html = ""
    for q, a in comp["faq"]:
        faq_html += f'<div class="faq-item"><h3>{_esc(q)}</h3><p>{_esc(a)}</p></div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{json.dumps(web_page_schema)}</script>
<script type="application/ld+json">{json.dumps(faq_schema)}</script>
<script type="application/ld+json">{json.dumps(breadcrumb_schema)}</script>
{FONTS_LINK}
<style>{ZARQ_CSS}</style>
</head>
<body>
{ai_comment}
<nav>
  <a href="/" class="nav-mark">zarq</a>
  <input type="checkbox" id="nav-toggle" class="nav-toggle-input">
  <label for="nav-toggle" class="nav-hamburger"><span></span><span></span><span></span></label>
  <div class="nav-links">
    <a href="/scan">Scan</a>
    <a href="/crypto">Ratings</a>
    <a href="/tokens">Token Ratings</a>
    <a href="/crash-watch">Crash Watch</a>
    <div class="nav-dropdown">
      <a href="#" class="nav-dropdown-trigger">More &#9662;</a>
      <div class="nav-dropdown-menu">
        <a href="/yield-risk">Yield Risk</a>
        <a href="/compare">Compare</a>
        <a href="/learn">Learn</a>
        <a href="/track-record">Track Record</a>
        <a href="/paper-trading">Paper Trading</a>
        <a href="/press">Press</a>
        <a href="/methodology">Methodology</a>
      </div>
    </div>
    <a href="/docs" class="nav-api">API</a>
  </div>
</nav>
<div class="container">
  <h1>ZARQ vs {_esc(name)}</h1>
  <p class="subtitle">{_esc(comp['tagline'])}</p>

  <!-- Verdict -->
  <div class="verdict">
    <strong>Bottom line:</strong>
    <span style="color:var(--gray-400);font-size:14px;line-height:1.6">{_esc(comp['verdict'])}</span>
  </div>

  <!-- About each tool -->
  <div class="feature-grid">
    <div class="card highlight">
      <div style="font-family:var(--mono);font-size:11px;color:var(--warm);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px">ZARQ</div>
      <h3 style="margin-bottom:8px">Structural Risk Intelligence</h3>
      <p style="font-size:13px;color:var(--gray-400);line-height:1.6;margin-bottom:16px">
        ZARQ is an independent crypto risk intelligence platform. It uses a 7-signal structural risk model
        with Distance-to-Default (NDD), crash probability prediction, and Moody's-style letter ratings (Aaa through D).
        198 tokens scored daily with 100% recall on structural collapse and 98% precision. Hash-chained audit trail.
      </p>
      <ul style="list-style:disc;padding-left:20px">{zarq_strengths_html}</ul>
    </div>
    <div class="card">
      <div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px">{_esc(name)}</div>
      <h3 style="margin-bottom:8px">{_esc(comp['tagline'].split(' vs ')[-1].capitalize()) if ' vs ' in comp['tagline'] else _esc(name)}</h3>
      <p style="font-size:13px;color:var(--gray-400);line-height:1.6;margin-bottom:16px">{_esc(comp['description'])}</p>
      <ul style="list-style:disc;padding-left:20px">{comp_strengths_html}</ul>
    </div>
  </div>

  <!-- Feature comparison table -->
  <h2>Feature Comparison</h2>
  <div class="card" style="padding:16px 20px">
    {feature_html}
  </div>

  <!-- FAQ -->
  <h2 style="margin-top:40px">Frequently Asked Questions</h2>
  <div class="faq">
    {faq_html}
  </div>

  <!-- Internal links -->
  <div class="card" style="margin-top:24px">
    <h3 style="margin-bottom:12px;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500)">Explore ZARQ</h3>
    <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:13px">
      <a href="{SITE_URL}/methodology">Methodology</a>
      <a href="{SITE_URL}/crash-watch">Crash Watch</a>
      <a href="{SITE_URL}/tokens">All Tokens</a>
      <a href="{SITE_URL}/compare">All Comparisons</a>
      <a href="{SITE_URL}/token/bitcoin">Bitcoin Report</a>
      <a href="{SITE_URL}/token/ethereum">Ethereum Report</a>
    </div>
  </div>

  <p style="font-size:12px;color:var(--gray-600);font-family:var(--mono);margin:24px 0">
    Data updated daily. Not investment advice. <a href="{SITE_URL}/methodology" style="color:var(--warm)">Methodology &rarr;</a>
  </p>
</div>
<footer>ZARQ &mdash; Independent Crypto Risk Intelligence &nbsp;&middot;&nbsp; zarq.ai</footer>
</body>
</html>"""


def _render_hub_page():
    """Render the /compare hub page listing all comparisons."""
    title = "Crypto Comparisons — ZARQ Trust Score Comparisons | ZARQ"
    desc = (
        "Compare crypto tokens and risk tools with ZARQ Trust Scores. "
        "Token-vs-token comparisons, plus ZARQ vs Token Sniffer, RugCheck, GoPlus, and SupraFin."
    )
    url = f"{SITE_URL}/compare"

    web_page_schema = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": desc,
        "url": url,
        "provider": {"@type": "Organization", "name": "ZARQ", "url": SITE_URL},
    }

    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": "Compare", "item": url},
        ],
    }

    faq_items = [
        ("What is a ZARQ Trust Score comparison?",
         "ZARQ Trust Score comparisons show side-by-side risk profiles for crypto tokens. "
         "Each token is scored on a 100-point scale across Security, Compliance, Maintenance, "
         "Popularity, and Ecosystem dimensions, with a Moody's-style letter grade (Aaa through D)."),
        ("How does ZARQ compare to other risk tools?",
         "ZARQ is the only platform that predicts structural collapse using a quantitative model "
         "(Distance-to-Default, crash probability). Other tools focus on smart contract scanning "
         "or DeFi analytics. ZARQ goes deeper into whether a token's foundation is structurally sound."),
        ("How often are comparisons updated?",
         "ZARQ Trust Scores are updated daily through an automated scoring pipeline. "
         "Token comparison pages reflect the latest scores. Tool comparison pages are reviewed periodically."),
    ]

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq_items
        ],
    }

    ai_comment = (
        "<!-- AI-Citable Summary: ZARQ comparison hub. ZARQ provides Trust Score comparisons "
        "for crypto tokens (198 tokens, daily scoring) and tool comparisons vs Token Sniffer, "
        "RugCheck, GoPlus, and SupraFin. ZARQ uses a 7-signal structural risk model with "
        "Distance-to-Default (NDD), crash probability, and Moody's-style letter ratings (Aaa-D). "
        "Source: ZARQ (zarq.ai) -- independent crypto risk intelligence. -->"
    )

    # Tool comparison cards
    tool_cards = ""
    for key, comp in COMPETITORS.items():
        tool_cards += f"""<a href="{SITE_URL}/compare/{comp['slug']}" style="text-decoration:none;color:inherit">
  <div class="hub-card">
    <div class="tag">Tool Comparison</div>
    <h3>ZARQ vs {_esc(comp['name'])}</h3>
    <p>{_esc(comp['tagline'])}</p>
  </div>
</a>\n"""

    # Token pair cards
    token_cards = ""
    for pair_slug, pair_label in TOKEN_PAIRS:
        token_cards += f"""<a href="{SITE_URL}/compare/{pair_slug}" style="text-decoration:none;color:inherit">
  <div class="hub-card">
    <div class="tag">Token Comparison</div>
    <h3>{_esc(pair_label)}</h3>
    <p>Trust Score comparison with pillar breakdown</p>
  </div>
</a>\n"""

    # Vitality comparison cards (50 pairs based on Vitality Score divergence)
    vitality_cards = ""
    try:
        import sqlite3
        from pathlib import Path as _P
        vp_path = _P(__file__).parent / "vitality_compare_pairs.json"
        if vp_path.exists():
            vitality_pairs = json.loads(vp_path.read_text())
            for vp in vitality_pairs:
                slug = f"{vp['a']}-vs-{vp['b']}"
                a_vs = vp.get("a_vs", 0)
                b_vs = vp.get("b_vs", 0)
                diff = abs(a_vs - b_vs)
                vitality_cards += f"""<a href="{SITE_URL}/compare/{slug}" style="text-decoration:none;color:inherit">
  <div class="hub-card">
    <div class="tag" style="background:rgba(194,149,107,0.15);color:#c2956b">Crash Protection</div>
    <h3>{_esc(vp['a_name'])} vs {_esc(vp['b_name'])}</h3>
    <p style="font-family:var(--mono);font-size:12px">Vitality: {a_vs:.0f} ({vp.get('a_grade','?')}) vs {b_vs:.0f} ({vp.get('b_grade','?')}) &mdash; {diff:.0f}pt gap</p>
  </div>
</a>\n"""
    except Exception:
        pass

    # FAQ HTML
    faq_html = ""
    for q, a in faq_items:
        faq_html += f'<div class="faq-item"><h3>{_esc(q)}</h3><p>{_esc(a)}</p></div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
<meta name="robots" content="index, follow">
<script type="application/ld+json">{json.dumps(web_page_schema)}</script>
<script type="application/ld+json">{json.dumps(faq_schema)}</script>
<script type="application/ld+json">{json.dumps(breadcrumb_schema)}</script>
{FONTS_LINK}
<style>{ZARQ_CSS}</style>
</head>
<body>
{ai_comment}
<nav>
  <a href="/" class="nav-mark">zarq</a>
  <input type="checkbox" id="nav-toggle" class="nav-toggle-input">
  <label for="nav-toggle" class="nav-hamburger"><span></span><span></span><span></span></label>
  <div class="nav-links">
    <a href="/scan">Scan</a>
    <a href="/crypto">Ratings</a>
    <a href="/tokens">Token Ratings</a>
    <a href="/crash-watch">Crash Watch</a>
    <div class="nav-dropdown">
      <a href="#" class="nav-dropdown-trigger">More &#9662;</a>
      <div class="nav-dropdown-menu">
        <a href="/yield-risk">Yield Risk</a>
        <a href="/compare">Compare</a>
        <a href="/learn">Learn</a>
        <a href="/track-record">Track Record</a>
        <a href="/paper-trading">Paper Trading</a>
        <a href="/press">Press</a>
        <a href="/methodology">Methodology</a>
      </div>
    </div>
    <a href="/docs" class="nav-api">API</a>
  </div>
</nav>
<div class="container">
  <h1>Crypto Comparisons</h1>
  <p class="subtitle">ZARQ Trust Score comparisons &mdash; tokens, tools, and risk intelligence</p>

  <!-- Tool comparisons -->
  <h2>ZARQ vs Risk Tools</h2>
  <p style="font-size:13px;color:var(--gray-500);margin-bottom:16px;line-height:1.6">
    How does ZARQ's structural risk model compare to other crypto risk and security tools?
    ZARQ predicts structural collapse. Others scan contracts or track yields. Different problems, different tools.
  </p>
  <div class="hub-grid">
    {tool_cards}
  </div>

  <!-- Token comparisons -->
  <h2 style="margin-top:40px">Token Comparisons</h2>
  <p style="font-size:13px;color:var(--gray-500);margin-bottom:16px;line-height:1.6">
    Side-by-side Trust Score comparisons for popular crypto token pairs. Scored across Security,
    Compliance, Maintenance, Popularity, and Ecosystem dimensions with Moody's-style letter grades.
  </p>
  <div class="hub-grid">
    {token_cards}
  </div>

  <!-- Vitality / Crash Protection comparisons -->
  <h2 style="margin-top:40px">Crash Protection Comparisons</h2>
  <p style="font-size:13px;color:var(--gray-500);margin-bottom:8px;line-height:1.6">
    50 token pairs ranked by Vitality Score divergence. Higher Vitality = more crash-resistant.
    <strong style="color:var(--warm)">Backtested:</strong> top-quintile tokens lost 44% less in the 2025&ndash;2026 crash (p&lt;0.001).
    <a href="/vitality/backtest" style="color:var(--warm)">Full results &rarr;</a>
  </p>
  <div class="hub-grid">
    {vitality_cards}
  </div>

  <!-- FAQ -->
  <h2 style="margin-top:40px">Frequently Asked Questions</h2>
  <div class="faq">
    {faq_html}
  </div>

  <!-- Internal links -->
  <div class="card" style="margin-top:24px">
    <h3 style="margin-bottom:12px;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:var(--gray-500)">Explore ZARQ</h3>
    <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:13px">
      <a href="{SITE_URL}/methodology">Methodology</a>
      <a href="{SITE_URL}/crash-watch">Crash Watch</a>
      <a href="{SITE_URL}/tokens">All Tokens</a>
      <a href="{SITE_URL}/token/bitcoin">Bitcoin Report</a>
      <a href="{SITE_URL}/token/ethereum">Ethereum Report</a>
    </div>
  </div>

  <p style="font-size:12px;color:var(--gray-600);font-family:var(--mono);margin:24px 0">
    Data updated daily. Not investment advice. <a href="{SITE_URL}/methodology" style="color:var(--warm)">Methodology &rarr;</a>
  </p>
</div>
<footer>ZARQ &mdash; Independent Crypto Risk Intelligence &nbsp;&middot;&nbsp; zarq.ai</footer>
</body>
</html>"""


# ─── Sitemap ──────────────────────────────────────────────────────────

def _render_sitemap():
    """Sitemap for tool comparison pages, token pairs, and hub."""
    today = date.today().isoformat()
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += (
        f'  <url><loc>{SITE_URL}/compare</loc><lastmod>{today}</lastmod>'
        f'<changefreq>weekly</changefreq><priority>0.9</priority></url>\n'
    )
    for comp in COMPETITORS.values():
        xml += (
            f'  <url><loc>{SITE_URL}/compare/{comp["slug"]}</loc><lastmod>{today}</lastmod>'
            f'<changefreq>monthly</changefreq><priority>0.7</priority></url>\n'
        )
    # Vitality comparison pairs
    try:
        from pathlib import Path as _P
        vp_path = _P(__file__).parent / "vitality_compare_pairs.json"
        if vp_path.exists():
            vitality_pairs = json.loads(vp_path.read_text())
            for vp in vitality_pairs:
                slug = f"{vp['a']}-vs-{vp['b']}"
                xml += (
                    f'  <url><loc>{SITE_URL}/compare/{slug}</loc><lastmod>{today}</lastmod>'
                    f'<changefreq>weekly</changefreq><priority>0.6</priority></url>\n'
                )
    except Exception:
        pass
    xml += '</urlset>'
    return xml


# ─── Mount function ──────────────────────────────────────────────────

def mount_zarq_compare_hub(app):
    """
    Mount ZARQ comparison hub and tool comparison pages.

    Adds:
      GET /compare                        — Hub page (zarq.ai only)
      GET /compare/zarq-vs-{slug}         — 4 tool comparison pages (zarq.ai only)
      GET /sitemap-zarq-compare.xml       — Sitemap for tool comparisons

    Mount this in discovery.py BEFORE mount_compare_pages so that
    /compare and /compare/zarq-vs-* are matched before the catch-all /compare/{slug}.
    """

    # Pre-render pages (static content, no DB needed)
    _tool_pages = {}
    for key, comp in COMPETITORS.items():
        _tool_pages[comp["slug"]] = _render_tool_comparison(comp)

    _hub_html = _render_hub_page()
    _sitemap_xml = _render_sitemap()

    @app.get("/compare", response_class=HTMLResponse)
    def zarq_compare_hub(request: Request):
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            # Let the Nerq agent compare hub handle this
            from agentindex.agent_compare_pages import _render_hub_page
            return HTMLResponse(content=_render_hub_page())
        return HTMLResponse(content=_hub_html)

    @app.get("/compare/zarq-vs-token-sniffer", response_class=HTMLResponse)
    def zarq_vs_token_sniffer(request: Request):
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            return HTMLResponse(status_code=404, content="<h1>Not found</h1>")
        return HTMLResponse(content=_tool_pages["zarq-vs-token-sniffer"])

    @app.get("/compare/zarq-vs-rugcheck", response_class=HTMLResponse)
    def zarq_vs_rugcheck(request: Request):
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            return HTMLResponse(status_code=404, content="<h1>Not found</h1>")
        return HTMLResponse(content=_tool_pages["zarq-vs-rugcheck"])

    @app.get("/compare/zarq-vs-goplus", response_class=HTMLResponse)
    def zarq_vs_goplus(request: Request):
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            return HTMLResponse(status_code=404, content="<h1>Not found</h1>")
        return HTMLResponse(content=_tool_pages["zarq-vs-goplus"])

    @app.get("/compare/zarq-vs-suprafin", response_class=HTMLResponse)
    def zarq_vs_suprafin(request: Request):
        host = request.headers.get("host", "")
        if "zarq.ai" not in host:
            return HTMLResponse(status_code=404, content="<h1>Not found</h1>")
        return HTMLResponse(content=_tool_pages["zarq-vs-suprafin"])

    @app.get("/sitemap-zarq-compare.xml", response_class=Response)
    def sitemap_zarq_compare():
        return Response(content=_sitemap_xml, media_type="application/xml")

    logger.info("Mounted ZARQ compare hub + 4 tool comparison pages + sitemap")
