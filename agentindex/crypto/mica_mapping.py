"""
MiCA Token Classification
=========================
Maps crypto tokens to EU Markets in Crypto-Assets (MiCA) regulation categories:
  - E-Money Token (EMT): Stablecoins pegged to a single fiat currency
  - Asset-Referenced Token (ART): Tokens backed by baskets of assets, commodities, or multiple currencies
  - Utility Token / Crypto-Asset: Everything else

Also provides the /compliance/mica page and MiCA display helper for token pages.

Usage:
    from agentindex.crypto.mica_mapping import get_mica_category, mount_mica_pages
    category = get_mica_category("tether")
    mount_mica_pages(app)
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import date
from html import escape as _html_esc
from fastapi.responses import HTMLResponse

logger = logging.getLogger("zarq.mica")

DB_PATH = str(Path(__file__).parent / "crypto_trust.db")

# ---------------------------------------------------------------------------
# MiCA classification constants
# ---------------------------------------------------------------------------

# E-Money Tokens: stablecoins pegged to a single fiat currency
EMT_TOKEN_IDS = {
    # USD-pegged
    'tether', 'usd-coin', 'binance-usd', 'dai', 'true-usd', 'paxos-standard',
    'gusd', 'frax', 'usdd', 'tusd', 'busd', 'lusd', 'susd', 'usdp',
    'first-digital-usd', 'ethena-usde', 'usde', 'paypal-usd', 'fdusd',
    'gemini-dollar', 'husd', 'nusd', 'musd', 'cusd',
    'terrausd', 'ust', 'magic-internet-money',
    'ondo-us-dollar-yield',
    # EUR-pegged
    'stasis-eur', 'euro-coin', 'eurs',
}

# Categories in defi_protocol_tokens that indicate stablecoin nature
EMT_CATEGORIES = {
    'Algo-Stables', 'Dual-Token Stablecoin', 'Stablecoin Issuer',
    'Stablecoin Wrapper', 'Partially Algorithmic Stablecoin',
}

# Asset-Referenced Tokens: commodity-backed or basket-backed
ART_TOKEN_IDS = {
    'pax-gold', 'tether-gold', 'wrapped-bitcoin', 'wrapped-steth',
    'rocket-pool-eth', 'coinbase-wrapped-staked-eth',
    'wrapped-ether', 'wrapped-eeth',
}

# Categories that indicate asset-referenced nature
ART_CATEGORIES = {
    'RWA', 'Liquid Staking', 'Liquid Restaking', 'Restaking',
    'Restaked BTC', 'Decentralized BTC', 'Anchor BTC',
    'Synthetics',
}

# MiCA category labels
MICA_EMT = "E-Money Token (EMT)"
MICA_ART = "Asset-Referenced Token (ART)"
MICA_UTILITY = "Utility Token / Crypto-Asset"


def get_mica_category(token_id: str, category: str = None) -> str:
    """
    Classify a token under MiCA regulation categories.

    Args:
        token_id: The CoinGecko-style token identifier
        category: Optional DeFiLlama category for the protocol

    Returns:
        One of: "E-Money Token (EMT)", "Asset-Referenced Token (ART)", "Utility Token / Crypto-Asset"
    """
    tid = token_id.lower().strip() if token_id else ""

    # Direct token ID match for EMTs
    if tid in EMT_TOKEN_IDS:
        return MICA_EMT

    # Category-based EMT classification
    if category and category in EMT_CATEGORIES:
        return MICA_EMT

    # Direct token ID match for ARTs
    if tid in ART_TOKEN_IDS:
        return MICA_ART

    # Category-based ART classification
    if category and category in ART_CATEGORIES:
        return MICA_ART

    return MICA_UTILITY


def get_mica_badge_html(token_id: str, category: str = None) -> str:
    """Return a small HTML snippet for the MiCA classification badge on token pages."""
    mica_cat = get_mica_category(token_id, category)

    if mica_cat == MICA_EMT:
        color = "#2563eb"
        bg = "rgba(37,99,235,0.06)"
        icon = "EMT"
    elif mica_cat == MICA_ART:
        color = "#c2956b"
        bg = "rgba(194,149,107,0.08)"
        icon = "ART"
    else:
        color = "#78716c"
        bg = "#f5f5f4"
        icon = "CA"

    return (
        f'<div style="margin:24px 0;padding:16px 20px;border:1px solid {color}20;background:{bg}">'
        f'<div style="font-family:var(--mono);font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:{color};margin-bottom:4px">MiCA Classification</div>'
        f'<div style="font-family:var(--sans);font-size:0.95rem;color:var(--gray-800)">'
        f'<strong style="font-family:var(--mono);color:{color}">[{icon}]</strong> {_html_esc(mica_cat)}'
        f'</div>'
        f'<div style="font-family:var(--mono);font-size:11px;color:var(--gray-500);margin-top:4px">'
        f'Under EU MiCA regulation (2023/1114). <a href="/compliance/mica" style="color:{color}">Learn more</a>'
        f'</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# /compliance/mica page
# ---------------------------------------------------------------------------

def _esc(text):
    if not text:
        return ""
    return _html_esc(str(text))


def _rating_color(rating):
    if not rating:
        return "#78716c"
    r = rating.lower()
    if r.startswith("aa") or r.startswith("a"):
        return "#16a34a"
    if r.startswith("baa"):
        return "#ca8a04"
    if r.startswith("ba") or r.startswith("b"):
        return "#ea580c"
    if r.startswith("c"):
        return "#dc2626"
    return "#78716c"


def _risk_color(level):
    return {"SAFE": "#16a34a", "WATCH": "#ca8a04", "WARNING": "#ea580c", "CRITICAL": "#dc2626"}.get(level, "#78716c")


def _render_mica_page():
    """Render /compliance/mica page showing all tokens grouped by MiCA category."""
    today = date.today().isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT d.token_id, d.symbol, d.name, d.category, d.tvl_latest,
               r.rating, r.score,
               n.risk_level, n.trust_score
        FROM defi_protocol_tokens d
        LEFT JOIN crypto_rating_daily r ON d.token_id = r.token_id
          AND r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
        LEFT JOIN nerq_risk_signals n ON d.token_id = n.token_id
          AND n.signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
        WHERE d.token_id IS NOT NULL AND d.token_id <> ''
        ORDER BY d.tvl_latest DESC
    """).fetchall()
    conn.close()

    # Classify and group
    groups = {MICA_EMT: [], MICA_ART: [], MICA_UTILITY: []}
    seen = set()
    for row in rows:
        tid = row["token_id"]
        if tid in seen:
            continue
        seen.add(tid)

        mica_cat = get_mica_category(tid, row["category"])
        groups[mica_cat].append({
            "token_id": tid,
            "symbol": (row["symbol"] or "").upper(),
            "name": row["name"] or tid.replace("-", " ").title(),
            "category": row["category"] or "",
            "tvl": row["tvl_latest"] or 0,
            "rating": row["rating"] or "NR",
            "score": row["score"] or 0,
            "risk_level": row["risk_level"] or "N/A",
        })

    total = sum(len(v) for v in groups.values())

    # Risk distribution per MiCA category
    def _risk_dist(tokens):
        d = {"SAFE": 0, "WATCH": 0, "WARNING": 0, "CRITICAL": 0}
        for t in tokens:
            rl = t["risk_level"]
            if rl in d:
                d[rl] += 1
        return d

    # Build category sections
    sections = ""
    cat_order = [MICA_EMT, MICA_ART, MICA_UTILITY]
    cat_colors = {MICA_EMT: "#2563eb", MICA_ART: "#c2956b", MICA_UTILITY: "#78716c"}
    cat_codes = {MICA_EMT: "EMT", MICA_ART: "ART", MICA_UTILITY: "CA"}
    cat_descriptions = {
        MICA_EMT: "E-Money Tokens reference a single official currency and aim to maintain a stable value. Under MiCA, EMT issuers must be authorized as credit institutions or e-money institutions, maintain 1:1 reserves, and provide redemption rights.",
        MICA_ART: "Asset-Referenced Tokens reference multiple currencies, commodities, or other assets. MiCA requires ART issuers to maintain adequate reserves, publish regular reports, and comply with governance requirements.",
        MICA_UTILITY: "Crypto-assets that do not qualify as EMT or ART fall under the general crypto-asset regime. This includes utility tokens, governance tokens, and other digital assets. MiCA requires whitepapers and basic consumer protections.",
    }

    for cat in cat_order:
        tokens = groups[cat]
        count = len(tokens)
        color = cat_colors[cat]
        code = cat_codes[cat]
        desc = cat_descriptions[cat]
        risk_dist = _risk_dist(tokens)

        # Risk distribution bar
        risk_bar = ""
        for rl in ["SAFE", "WATCH", "WARNING", "CRITICAL"]:
            rc = risk_dist[rl]
            if rc > 0:
                risk_bar += f'<span style="font-family:var(--mono);font-size:12px;padding:2px 8px;background:{_risk_color(rl)}10;color:{_risk_color(rl)}">{rl} {rc}</span> '

        # Token table (top 30 by TVL)
        table_rows = ""
        for t in tokens[:50]:
            sc = {"SAFE": "status-safe", "WATCH": "status-watch", "WARNING": "status-warning", "CRITICAL": "status-critical"}.get(t["risk_level"], "")
            table_rows += (
                f'<tr>'
                f'<td><a href="/token/{_esc(t["token_id"])}" style="color:var(--warm)">{_esc(t["name"])}</a></td>'
                f'<td class="mono">{_esc(t["symbol"])}</td>'
                f'<td class="mono">{_esc(t["category"])}</td>'
                f'<td><span class="rating-badge" style="color:{_rating_color(t["rating"])}">{_esc(t["rating"])}</span></td>'
                f'<td class="mono {sc}">{_esc(t["risk_level"])}</td>'
                f'</tr>\n'
            )

        remaining = count - 50 if count > 50 else 0
        more_text = f'<p style="font-family:var(--mono);font-size:12px;color:var(--gray-500);margin-top:8px">...and {remaining} more tokens</p>' if remaining else ""

        sections += (
            f'<div style="margin-top:48px">'
            f'<h2 style="font-family:var(--serif);font-size:1.5rem;font-weight:400;color:{color}">'
            f'<span style="font-family:var(--mono);font-size:13px;letter-spacing:0.05em">[{code}]</span> {_esc(cat)}</h2>'
            f'<p style="color:var(--gray-600);font-size:0.92rem;line-height:1.6;margin:8px 0 16px">{_esc(desc)}</p>'
            f'<div style="display:flex;gap:12px;align-items:center;margin-bottom:16px">'
            f'<span style="font-family:var(--mono);font-size:14px;font-weight:500">{count} tokens</span>'
            f'{risk_bar}'
            f'</div>'
            f'<table>'
            f'<thead><tr><th>Token</th><th>Symbol</th><th>Category</th><th>Rating</th><th>Risk</th></tr></thead>'
            f'<tbody>{table_rows}</tbody>'
            f'</table>'
            f'{more_text}'
            f'</div>\n'
        )

    # AI summary
    ai_summary = (
        f"ZARQ classifies {total} tracked tokens under the EU Markets in Crypto-Assets (MiCA) regulation framework. "
        f"{len(groups[MICA_EMT])} tokens qualify as E-Money Tokens (EMT), "
        f"{len(groups[MICA_ART])} as Asset-Referenced Tokens (ART), and "
        f"{len(groups[MICA_UTILITY])} as general Utility Tokens / Crypto-Assets. "
        f"Each token's ZARQ risk rating provides an independent assessment complementary to MiCA compliance."
    )

    # FAQs
    faq_data = [
        ("What is MiCA and how does it affect crypto tokens?",
         "The Markets in Crypto-Assets Regulation (MiCA, Regulation 2023/1114) is the EU's comprehensive framework for crypto-asset regulation. "
         "It classifies tokens into three categories: E-Money Tokens (EMTs) pegged to fiat currencies, "
         "Asset-Referenced Tokens (ARTs) backed by baskets of assets, and general crypto-assets. "
         "MiCA imposes different requirements for each category, including reserve requirements, transparency obligations, and governance standards."),
        ("How does ZARQ classify tokens under MiCA?",
         f"ZARQ maps each token to a MiCA category based on its economic function and backing mechanism. "
         f"Stablecoins pegged to a single fiat currency (USDT, USDC, DAI, etc.) are classified as E-Money Tokens. "
         f"Tokens backed by commodities or asset baskets (PAXG, XAUt, liquid staking derivatives) are Asset-Referenced Tokens. "
         f"All other tokens default to the general Utility Token / Crypto-Asset category. "
         f"Currently {len(groups[MICA_EMT])} EMTs, {len(groups[MICA_ART])} ARTs, and {len(groups[MICA_UTILITY])} utility tokens are classified."),
        ("Does a ZARQ rating replace MiCA compliance?",
         "No. ZARQ ratings are independent quantitative risk assessments based on market signals, structural integrity, and crash probability models. "
         "They complement but do not replace MiCA compliance requirements. "
         "A high ZARQ trust score indicates lower quantitative risk, but it does not certify regulatory compliance. "
         "Token issuers must independently comply with MiCA requirements through authorized entities in EU member states."),
    ]

    faq_html = ""
    faq_jsonld_items = []
    for q, a in faq_data:
        faq_html += f'<div class="faq-item"><div class="faq-q">{_esc(q)}</div><div class="faq-a">{_esc(a)}</div></div>\n'
        faq_jsonld_items.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}})

    # JSON-LD
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Compliance"},
            {"@type": "ListItem", "position": 3, "name": "MiCA Classification"},
        ]
    })

    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"MiCA Token Classification — {total} Tokens Mapped",
        "description": f"EU MiCA regulation classification for {total} crypto tokens. EMT, ART, and utility token mapping with risk ratings.",
        "url": "https://zarq.ai/compliance/mica",
        "publisher": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
        "dateModified": today,
    })

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_jsonld_items
    })

    ZARQ_FONTS = '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">\n'

    ZARQ_CSS_INLINE = """<style>
:root {
  --white: #fafaf9; --black: #0a0a0a;
  --gray-100: #f5f5f4; --gray-200: #e7e5e4; --gray-400: #a8a29e;
  --gray-500: #78716c; --gray-600: #57534e; --gray-700: #44403c;
  --gray-800: #292524; --gray-900: #1c1917;
  --warm: #c2956b; --warm-light: rgba(194,149,107,0.08);
  --red: #dc2626; --green: #16a34a; --yellow: #ca8a04;
  --serif: 'DM Serif Display', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'DM Sans', sans-serif;
  --wide: 1120px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
::selection { background: var(--warm); color: var(--black); }
html { font-size: 17px; -webkit-font-smoothing: antialiased; }
body { background: var(--white); color: var(--gray-800); font-family: var(--sans); line-height: 1.6; }
a { color: var(--warm); text-decoration: none; }
a:hover { text-decoration: underline; }
nav { position: fixed; top: 0; left: 0; right: 0; z-index: 100; padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; backdrop-filter: blur(20px); background: rgba(250,250,249,0.85); border-bottom: 1px solid rgba(0,0,0,0.04); }
.nav-mark { font-family: var(--mono); font-weight: 500; font-size: 15px; letter-spacing: 0.15em; text-transform: uppercase; color: var(--black); text-decoration: none; }
.nav-links { display: flex; gap: 32px; align-items: center; }
.nav-links a { font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-600); text-decoration: none; }
.nav-links a:hover { color: var(--black); }
.nav-api { font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; color: var(--warm); border: 1px solid var(--warm); padding: 6px 16px; text-decoration: none; }
.nav-api:hover { background: var(--warm); color: var(--white); }
.container { max-width: var(--wide); margin: 0 auto; padding: 120px 40px 60px; }
h1 { font-family: var(--serif); font-size: 2.2rem; font-weight: 400; line-height: 1.2; margin-bottom: 8px; }
h2 { font-family: var(--serif); font-size: 1.5rem; font-weight: 400; }
.subtitle { font-size: 1.05rem; color: var(--gray-600); margin-bottom: 32px; }
.breadcrumb { font-family: var(--mono); font-size: 12px; color: var(--gray-500); margin-bottom: 24px; }
.breadcrumb a { color: var(--warm); }
.ai-summary { background: var(--warm-light); border-left: 3px solid var(--warm); padding: 16px 20px; margin-bottom: 32px; font-size: 0.95rem; line-height: 1.6; color: var(--gray-700); }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0 32px; }
.summary-card { border: 1px solid var(--gray-200); padding: 20px; text-align: center; }
.summary-card .val { font-family: var(--mono); font-size: 1.8rem; font-weight: 500; }
.summary-card .lbl { font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; color: var(--gray-500); margin-top: 4px; text-transform: uppercase; }
table { width: 100%; border-collapse: collapse; margin-top: 8px; }
th { font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-500); text-align: left; padding: 12px 16px; border-bottom: 2px solid var(--gray-200); }
td { padding: 10px 16px; border-bottom: 1px solid var(--gray-100); font-size: 0.9rem; }
tr:hover { background: var(--warm-light); }
.mono { font-family: var(--mono); font-size: 13px; }
.rating-badge { font-family: var(--mono); font-weight: 500; }
.status-safe { color: var(--green); }
.status-watch { color: var(--yellow); }
.status-warning { color: #ea580c; }
.status-critical { color: var(--red); }
.faq-section { margin-top: 48px; }
.faq-item { border-bottom: 1px solid var(--gray-200); padding: 20px 0; }
.faq-q { font-weight: 600; font-size: 1rem; margin-bottom: 8px; }
.faq-a { color: var(--gray-600); font-size: 0.92rem; line-height: 1.65; }
footer { padding: 60px 40px 40px; border-top: 1px solid var(--gray-200); margin-top: 80px; display: flex; justify-content: space-between; max-width: var(--wide); margin-left: auto; margin-right: auto; }
footer div { font-family: var(--mono); font-size: 12px; color: var(--gray-500); }
@media (max-width: 768px) {
  nav { padding: 16px 20px; }
  .container { padding: 100px 20px 40px; }
  h1 { font-size: 1.5rem; }
  .summary-grid { grid-template-columns: 1fr; }
  td, th { padding: 8px 10px; }
}
</style>"""

    html = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>MiCA Token Classification — {total} Tokens Mapped | ZARQ</title>\n'
        f'<meta name="description" content="EU MiCA regulation classification for {total} crypto tokens. E-Money Tokens, Asset-Referenced Tokens, and utility tokens mapped with independent risk ratings.">\n'
        '<link rel="canonical" href="https://zarq.ai/compliance/mica">\n'
        '<meta property="og:title" content="MiCA Token Classification — ZARQ">\n'
        f'<meta property="og:description" content="EU MiCA mapping for {total} tokens with risk ratings.">\n'
        '<meta property="og:url" content="https://zarq.ai/compliance/mica">\n'
        '<meta property="og:type" content="article">\n'
        '<meta property="og:site_name" content="ZARQ">\n'
        '<meta name="robots" content="index, follow">\n'
        f'<script type="application/ld+json">{webpage_jsonld}</script>\n'
        f'<script type="application/ld+json">{faq_jsonld}</script>\n'
        f'<script type="application/ld+json">{breadcrumb_jsonld}</script>\n'
        + ZARQ_FONTS + ZARQ_CSS_INLINE
        + '</head><body>\n'
        '<nav>\n'
        '  <a href="/" class="nav-mark">zarq</a>\n'
        '  <div class="nav-links">\n'
        '    <a href="/scan">Scan</a>\n'
        '    <a href="/crypto">Ratings</a>\n'
        '    <a href="/tokens">Token Ratings</a>\n'
        '    <a href="/chains">Chains</a>\n'
        '    <a href="/crash-watch">Crash Watch</a>\n'
        '    <a href="/docs" class="nav-api">API</a>\n'
        '  </div>\n'
        '</nav>\n'
        '<div class="container">\n'
        '  <div class="breadcrumb"><a href="/">ZARQ</a> / Compliance / MiCA Classification</div>\n'
        '  <h1>MiCA Token Classification</h1>\n'
        f'  <p class="subtitle">{total} tokens mapped to EU MiCA regulation categories with independent risk ratings.</p>\n'
        f'  <div class="ai-summary">{_esc(ai_summary)}</div>\n'
        '  <div class="summary-grid">\n'
        f'    <div class="summary-card"><div class="val" style="color:#2563eb">{len(groups[MICA_EMT])}</div><div class="lbl">E-Money Tokens</div></div>\n'
        f'    <div class="summary-card"><div class="val" style="color:#c2956b">{len(groups[MICA_ART])}</div><div class="lbl">Asset-Referenced Tokens</div></div>\n'
        f'    <div class="summary-card"><div class="val" style="color:#78716c">{len(groups[MICA_UTILITY])}</div><div class="lbl">Utility Tokens</div></div>\n'
        '  </div>\n'
        + sections
        + '  <div class="faq-section">\n'
        + '    <h2>Frequently Asked Questions</h2>\n'
        + faq_html
        + '  </div>\n'
        + '  <div style="margin-top:48px;padding:24px;background:var(--gray-100);border:1px solid var(--gray-200);font-family:var(--mono);font-size:12px;color:var(--gray-600)">'
        + '    <strong>Disclaimer:</strong> ZARQ MiCA classifications are informational mapping based on token economic characteristics. '
        + 'They do not constitute legal advice or regulatory determination. Consult qualified legal counsel for compliance obligations.'
        + '  </div>\n'
        + '</div>\n'
        '<footer>\n'
        '  <div>ZARQ &mdash; Independent Crypto Intelligence</div>\n'
        '  <div>zarq.ai</div>\n'
        '</footer>\n'
        '</body></html>'
    )
    return html


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------

def mount_mica_pages(app):
    """Mount /compliance/mica on zarq.ai host."""
    from starlette.requests import Request

    def _is_zarq(request: Request) -> bool:
        host = request.headers.get("host", "")
        return "zarq" in host or "localhost" in host or "127.0.0.1" in host

    @app.get("/compliance/mica", response_class=HTMLResponse)
    async def compliance_mica_page(request: Request):
        if not _is_zarq(request):
            return HTMLResponse(status_code=404, content="Not found")
        try:
            html = _render_mica_page()
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering MiCA page: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    logger.info("Mounted MiCA compliance page: /compliance/mica")
