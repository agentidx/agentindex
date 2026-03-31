"""
ZARQ Chain SEO Pages
====================
Chain-specific pages showing tokens deployed on each blockchain.
  GET /chains            — Hub page listing all chains
  GET /chain/{slug}      — Individual chain page with token table
  GET /sitemap-chains.xml — XML sitemap for all chain pages

Usage in discovery.py:
    from agentindex.crypto.chain_pages import mount_chain_pages
    mount_chain_pages(app)
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import date
from html import escape as _html_esc
from fastapi.responses import HTMLResponse, Response

logger = logging.getLogger("zarq.chain_pages")

DB_PATH = str(Path(__file__).parent / "crypto_trust.db")

# ---------------------------------------------------------------------------
# Chain slug mapping
# ---------------------------------------------------------------------------
CHAIN_SLUG_MAP = {
    "Ethereum": "ethereum",
    "Bitcoin": "bitcoin",
    "Solana": "solana",
    "Binance": "bsc",
    "Tron": "tron",
    "Polygon": "polygon",
    "Avalanche": "avalanche",
    "Arbitrum": "arbitrum",
    "Optimism": "optimism",
    "Base": "base",
    "Cardano": "cardano",
    "Near": "near",
    "Fantom": "fantom",
    "Sui": "sui",
    "Aptos": "aptos",
    "TON": "ton",
    "Cosmos": "cosmos",
    "Polkadot": "polkadot",
    "Ripple": "ripple",
    "Doge": "doge",
    "Litecoin": "litecoin",
    "Hedera": "hedera",
    "Sonic": "sonic",
    "Celo": "celo",
    "Stellar": "stellar",
    "Chiliz": "chiliz",
    "zkSync Era": "zksync-era",
    "Algorand": "algorand",
    "Starknet": "starknet",
    "Scroll": "scroll",
    "Ronin": "ronin",
    "Manta": "manta",
    "Linea": "linea",
    "Mantle": "mantle",
    "Plasma": "plasma",
    "Cronos": "cronos",
    "Klaytn": "klaytn",
    "Kava": "kava",
    "EOS": "eos",
    "Op_Bnb": "opbnb",
    "xDai": "gnosis",
    "Hyperliquid L1": "hyperliquid",
    "Moonbeam": "moonbeam",
    "Harmony": "harmony",
    "Blast": "blast",
    "Mode": "mode",
    "Sei": "sei",
    "Metis": "metis",
    "Berachain": "berachain",
    "Injective": "injective",
    "Tezos": "tezos",
}

# Reverse mapping: slug -> chain name
SLUG_TO_CHAIN = {v: k for k, v in CHAIN_SLUG_MAP.items()}

# Chain display names for nicer titles
CHAIN_DISPLAY_NAMES = {
    "bsc": "BNB Chain (BSC)",
    "gnosis": "Gnosis Chain",
    "opbnb": "opBNB",
    "zksync-era": "zkSync Era",
    "ton": "TON",
    "eos": "EOS",
    "hyperliquid": "Hyperliquid",
    "doge": "Dogecoin",
    "ripple": "XRP Ledger",
}


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
    m = {"SAFE": "#16a34a", "WATCH": "#ca8a04", "WARNING": "#ea580c", "CRITICAL": "#dc2626"}
    return m.get(level, "#78716c")


def _status_class(level):
    m = {"SAFE": "status-safe", "WATCH": "status-watch", "WARNING": "status-warning", "CRITICAL": "status-critical"}
    return m.get(level, "")


def _fmt_tvl(val):
    if val is None or val == 0:
        return "N/A"
    if val >= 1e9:
        return f"${val / 1e9:.1f}B"
    if val >= 1e6:
        return f"${val / 1e6:.1f}M"
    if val >= 1e3:
        return f"${val / 1e3:.0f}K"
    return f"${val:.0f}"


def _display_name(slug):
    return CHAIN_DISPLAY_NAMES.get(slug, SLUG_TO_CHAIN.get(slug, slug.replace("-", " ").title()))


def _get_chain_data():
    """Parse all tokens and group by chain."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT d.token_id, d.symbol, d.name, d.chains, d.category, d.tvl_latest,
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

    chain_data = {}  # slug -> { name, tokens: [...], total_tvl }
    seen_per_chain = {}  # slug -> set of token_ids (deduplicate)

    for row in rows:
        chains_raw = row["chains"]
        if not chains_raw:
            continue
        try:
            chain_list = json.loads(chains_raw)
        except (json.JSONDecodeError, TypeError):
            continue

        token_info = {
            "token_id": row["token_id"],
            "symbol": row["symbol"] or "",
            "name": row["name"] or row["token_id"].replace("-", " ").title(),
            "category": row["category"] or "",
            "tvl": row["tvl_latest"] or 0,
            "rating": row["rating"] or "",
            "score": row["score"] or 0,
            "risk_level": row["risk_level"] or "",
            "trust_score": row["trust_score"] or 0,
        }

        for chain_name in chain_list:
            slug = CHAIN_SLUG_MAP.get(chain_name)
            if not slug:
                # Auto-generate slug for unknown chains
                slug = chain_name.lower().replace(" ", "-").replace("_", "-")
                CHAIN_SLUG_MAP[chain_name] = slug
                SLUG_TO_CHAIN[slug] = chain_name

            if slug not in chain_data:
                chain_data[slug] = {"name": _display_name(slug), "tokens": [], "total_tvl": 0}
                seen_per_chain[slug] = set()

            if token_info["token_id"] not in seen_per_chain[slug]:
                seen_per_chain[slug].add(token_info["token_id"])
                chain_data[slug]["tokens"].append(token_info)
                chain_data[slug]["total_tvl"] += token_info["tvl"]

    return chain_data


# ---------------------------------------------------------------------------
# Shared HTML components (ZARQ design system)
# ---------------------------------------------------------------------------
ZARQ_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
"""

ZARQ_FONTS = '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">\n'

ZARQ_CSS = """<style>
:root {
  --white: #fafaf9; --black: #0a0a0a;
  --gray-100: #f5f5f4; --gray-200: #e7e5e4; --gray-400: #a8a29e;
  --gray-500: #78716c; --gray-600: #57534e; --gray-700: #44403c;
  --gray-800: #292524; --gray-900: #1c1917;
  --warm: #c2956b; --warm-light: rgba(194,149,107,0.08);
  --red: #dc2626; --red-light: rgba(220,38,38,0.06);
  --green: #16a34a; --green-light: rgba(22,163,74,0.06);
  --yellow: #ca8a04;
  --serif: 'DM Serif Display', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'DM Sans', sans-serif;
  --measure: 680px; --wide: 1120px;
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
.nav-links a { font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-600); text-decoration: none; transition: color 0.2s; }
.nav-links a:hover { color: var(--black); }
.nav-links a.active { color: var(--warm); }
.nav-api { font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; color: var(--warm); border: 1px solid var(--warm); padding: 6px 16px; text-decoration: none; transition: all 0.2s; }
.nav-api:hover { background: var(--warm); color: var(--white); }
.container { max-width: var(--wide); margin: 0 auto; padding: 120px 40px 60px; }
h1 { font-family: var(--serif); font-size: 2.2rem; font-weight: 400; line-height: 1.2; margin-bottom: 8px; }
h2 { font-family: var(--serif); font-size: 1.5rem; font-weight: 400; margin: 48px 0 16px; }
.subtitle { font-size: 1.05rem; color: var(--gray-600); margin-bottom: 32px; }
.breadcrumb { font-family: var(--mono); font-size: 12px; color: var(--gray-500); margin-bottom: 24px; }
.breadcrumb a { color: var(--warm); text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }
.ai-summary { background: var(--warm-light); border-left: 3px solid var(--warm); padding: 16px 20px; margin-bottom: 32px; font-size: 0.95rem; line-height: 1.6; color: var(--gray-700); }
.chain-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; margin-top: 24px; }
.chain-card { border: 1px solid var(--gray-200); padding: 24px; transition: border-color 0.2s, box-shadow 0.2s; text-decoration: none; color: inherit; display: block; }
.chain-card:hover { border-color: var(--warm); box-shadow: 0 4px 16px rgba(0,0,0,0.06); text-decoration: none; }
.chain-card h3 { font-family: var(--serif); font-size: 1.2rem; font-weight: 400; margin-bottom: 8px; }
.chain-card .stats { font-family: var(--mono); font-size: 12px; color: var(--gray-600); display: flex; gap: 16px; margin-bottom: 12px; }
.chain-card .risk-bar { display: flex; gap: 6px; }
.risk-dot { font-family: var(--mono); font-size: 11px; padding: 2px 8px; border-radius: 2px; }
.risk-safe { background: var(--green-light); color: var(--green); }
.risk-watch { background: rgba(202,138,4,0.08); color: var(--yellow); }
.risk-warning { background: rgba(234,88,12,0.08); color: #ea580c; }
.risk-critical { background: var(--red-light); color: var(--red); }
table { width: 100%; border-collapse: collapse; margin-top: 16px; }
th { font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-500); text-align: left; padding: 12px 16px; border-bottom: 2px solid var(--gray-200); cursor: pointer; user-select: none; white-space: nowrap; }
th:hover { color: var(--black); }
td { padding: 10px 16px; border-bottom: 1px solid var(--gray-100); font-size: 0.9rem; }
tr:hover { background: var(--warm-light); }
.mono { font-family: var(--mono); font-size: 13px; }
.rating-badge { font-family: var(--mono); font-weight: 500; }
.status-safe { color: var(--green); }
.status-watch { color: var(--yellow); }
.status-warning { color: #ea580c; }
.status-critical { color: var(--red); }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin: 24px 0 32px; }
.summary-card { border: 1px solid var(--gray-200); padding: 20px; text-align: center; }
.summary-card .val { font-family: var(--mono); font-size: 1.8rem; font-weight: 500; }
.summary-card .lbl { font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; color: var(--gray-500); margin-top: 4px; text-transform: uppercase; }
.faq-section { margin-top: 48px; }
.faq-item { border-bottom: 1px solid var(--gray-200); padding: 20px 0; }
.faq-q { font-family: var(--sans); font-weight: 600; font-size: 1rem; margin-bottom: 8px; }
.faq-a { color: var(--gray-600); font-size: 0.92rem; line-height: 1.65; }
footer { padding: 60px 40px 40px; border-top: 1px solid var(--gray-200); margin-top: 80px; display: flex; justify-content: space-between; max-width: var(--wide); margin-left: auto; margin-right: auto; }
footer div { font-family: var(--mono); font-size: 12px; color: var(--gray-500); }
@media (max-width: 768px) {
  nav { padding: 16px 20px; }
  .container { padding: 100px 20px 40px; }
  h1 { font-size: 1.5rem; }
  .chain-grid { grid-template-columns: 1fr; }
  table { font-size: 0.8rem; }
  td, th { padding: 8px 10px; }
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>"""

ZARQ_NAV = """<nav>
  <a href="/" class="nav-mark">zarq</a>
  <div class="nav-links">
    <a href="/scan">Scan</a>
    <a href="/crypto">Ratings</a>
    <a href="/tokens">Token Ratings</a>
    <a href="/chains" class="active">Chains</a>
    <a href="/crash-watch">Crash Watch</a>
    <a href="/docs" class="nav-api">API</a>
  </div>
</nav>"""

ZARQ_FOOTER = """<footer>
  <div>ZARQ &mdash; Independent Crypto Intelligence</div>
  <div>zarq.ai</div>
</footer>"""


def _sort_script():
    return """<script>
document.querySelectorAll('th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const table = th.closest('table');
    const tbody = table.querySelector('tbody');
    const idx = Array.from(th.parentNode.children).indexOf(th);
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const asc = th.dataset.dir !== 'asc';
    th.parentNode.querySelectorAll('th').forEach(h => h.dataset.dir = '');
    th.dataset.dir = asc ? 'asc' : 'desc';
    rows.sort((a, b) => {
      let va = a.children[idx].dataset.sort || a.children[idx].textContent.trim();
      let vb = b.children[idx].dataset.sort || b.children[idx].textContent.trim();
      const na = parseFloat(va), nb = parseFloat(vb);
      if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
      return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    rows.forEach(r => tbody.appendChild(r));
  });
});
</script>"""


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------

def _render_chains_hub(chain_data):
    """Render /chains hub page."""
    today = date.today().isoformat()

    # Sort chains by token count descending
    sorted_chains = sorted(chain_data.items(), key=lambda x: len(x[1]["tokens"]), reverse=True)
    total_chains = len(sorted_chains)

    # Build cards
    cards = ""
    itemlist_items = []
    for i, (slug, data) in enumerate(sorted_chains):
        name = data["name"]
        tokens = data["tokens"]
        count = len(tokens)
        tvl_str = _fmt_tvl(data["total_tvl"])

        # Risk summary
        risk_counts = {"SAFE": 0, "WATCH": 0, "WARNING": 0, "CRITICAL": 0}
        for t in tokens:
            rl = t["risk_level"]
            if rl in risk_counts:
                risk_counts[rl] += 1

        risk_dots = ""
        for rl, cnt in risk_counts.items():
            if cnt > 0:
                cls = f"risk-{rl.lower()}"
                risk_dots += f'<span class="risk-dot {cls}">{rl} {cnt}</span>'

        cards += (
            f'<a href="/chain/{_esc(slug)}" class="chain-card">'
            f'<h3>{_esc(name)}</h3>'
            f'<div class="stats"><span>{count} tokens</span><span>TVL {tvl_str}</span></div>'
            f'<div class="risk-bar">{risk_dots}</div>'
            f'</a>\n'
        )

        itemlist_items.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": f"https://zarq.ai/chain/{slug}",
            "name": f"{name} — {count} tokens rated"
        })

    ai_summary = (
        f"ZARQ tracks tokens across {total_chains} blockchains with independent risk ratings, "
        f"crash probability models, and structural integrity signals. "
        f"Each chain page shows all rated tokens deployed on that network with their current risk status."
    )

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Chains"},
        ]
    })

    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"Crypto Risk Ratings by Blockchain — {total_chains} Chains",
        "description": f"Independent crypto risk ratings organized by blockchain. {total_chains} chains with token-level ratings.",
        "url": "https://zarq.ai/chains",
        "publisher": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
        "dateModified": today,
    })

    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Blockchain Risk Overview — {total_chains} Chains",
        "numberOfItems": total_chains,
        "itemListElement": itemlist_items[:50]
    })

    html = (
        ZARQ_HEAD
        + f'<title>Crypto Risk Ratings by Blockchain — {total_chains} Chains | ZARQ</title>\n'
        + f'<meta name="description" content="Independent crypto risk ratings organized by blockchain. Browse {total_chains} chains with per-token trust scores, crash probability, and structural integrity signals.">\n'
        + '<link rel="canonical" href="https://zarq.ai/chains">\n'
        + '<meta property="og:title" content="Crypto Risk Ratings by Blockchain — ZARQ">\n'
        + f'<meta property="og:description" content="Browse {total_chains} blockchains with token-level risk ratings.">\n'
        + '<meta property="og:url" content="https://zarq.ai/chains">\n'
        + '<meta property="og:type" content="website">\n'
        + '<meta property="og:site_name" content="ZARQ">\n'
        + '<meta name="robots" content="index, follow">\n'
        + f'<script type="application/ld+json">{webpage_jsonld}</script>\n'
        + f'<script type="application/ld+json">{breadcrumb_jsonld}</script>\n'
        + f'<script type="application/ld+json">{itemlist_jsonld}</script>\n'
        + ZARQ_FONTS + ZARQ_CSS
        + '</head><body>\n'
        + ZARQ_NAV
        + '<div class="container">\n'
        + '  <div class="breadcrumb"><a href="/">ZARQ</a> / Chains</div>\n'
        + f'  <h1>Crypto Risk Ratings by Blockchain</h1>\n'
        + f'  <p class="subtitle">{total_chains} blockchains tracked with independent token-level risk ratings.</p>\n'
        + f'  <div class="ai-summary">{_esc(ai_summary)}</div>\n'
        + f'  <div class="chain-grid">\n{cards}  </div>\n'
        + '</div>\n'
        + ZARQ_FOOTER
        + '</body></html>'
    )
    return html


def _render_chain_page(slug, chain_data):
    """Render /chain/{slug} page."""
    if slug not in chain_data:
        return None

    data = chain_data[slug]
    name = data["name"]
    tokens = data["tokens"]
    total = len(tokens)
    tvl_str = _fmt_tvl(data["total_tvl"])
    today = date.today().isoformat()

    # Risk summary
    risk_counts = {"SAFE": 0, "WATCH": 0, "WARNING": 0, "CRITICAL": 0, "": 0}
    for t in tokens:
        rl = t["risk_level"]
        if rl in risk_counts:
            risk_counts[rl] += 1
        else:
            risk_counts[""] += 1
    rated_count = risk_counts["SAFE"] + risk_counts["WATCH"] + risk_counts["WARNING"] + risk_counts["CRITICAL"]

    # Summary cards
    summary_cards = (
        f'<div class="summary-grid">'
        f'<div class="summary-card"><div class="val">{total}</div><div class="lbl">Tokens</div></div>'
        f'<div class="summary-card"><div class="val">{tvl_str}</div><div class="lbl">Total TVL</div></div>'
        f'<div class="summary-card"><div class="val" style="color:var(--green)">{risk_counts["SAFE"]}</div><div class="lbl">Safe</div></div>'
        f'<div class="summary-card"><div class="val" style="color:var(--yellow)">{risk_counts["WATCH"]}</div><div class="lbl">Watch</div></div>'
        f'<div class="summary-card"><div class="val" style="color:#ea580c">{risk_counts["WARNING"]}</div><div class="lbl">Warning</div></div>'
        f'<div class="summary-card"><div class="val" style="color:var(--red)">{risk_counts["CRITICAL"]}</div><div class="lbl">Critical</div></div>'
        f'</div>'
    )

    # Token table
    table_rows = ""
    for t in sorted(tokens, key=lambda x: x["tvl"], reverse=True):
        tid = t["token_id"]
        tname = t["name"]
        sym = (t["symbol"] or "").upper()
        rating = t["rating"] or "NR"
        score = t["score"]
        risk_level = t["risk_level"] or "N/A"
        tvl = _fmt_tvl(t["tvl"])
        cat = t["category"]
        sc = _status_class(risk_level)

        table_rows += (
            f'<tr>'
            f'<td><a href="/token/{_esc(tid)}">{_esc(tname)}</a></td>'
            f'<td class="mono">{_esc(sym)}</td>'
            f'<td class="mono">{_esc(cat)}</td>'
            f'<td><span class="rating-badge" style="color:{_rating_color(rating)}">{_esc(rating)}</span></td>'
            f'<td class="mono" data-sort="{score:.1f}">{score:.1f}</td>'
            f'<td class="mono {sc}" data-sort="{risk_level}">{_esc(risk_level)}</td>'
            f'<td class="mono" data-sort="{t["tvl"]:.0f}">{tvl}</td>'
            f'</tr>\n'
        )

    # AI summary
    dominant_risk = max(["SAFE", "WATCH", "WARNING", "CRITICAL"], key=lambda x: risk_counts[x])
    ai_summary = (
        f"ZARQ rates {total} tokens on {_esc(name)} with independent risk assessments. "
        f"Of {rated_count} rated tokens, {risk_counts['SAFE']} are SAFE, {risk_counts['WATCH']} on WATCH, "
        f"{risk_counts['WARNING']} at WARNING, and {risk_counts['CRITICAL']} CRITICAL. "
        f"The dominant risk status is {dominant_risk}. Total value locked across protocols: {tvl_str}."
    )

    # FAQs
    faq1_q = f"How safe are tokens on {_esc(name)}?"
    faq1_a = (
        f"ZARQ has rated {rated_count} tokens deployed on {_esc(name)}. "
        f"Currently {risk_counts['SAFE']} tokens are rated SAFE with no structural weaknesses, "
        f"while {risk_counts['CRITICAL']} tokens have CRITICAL risk levels indicating elevated collapse probability. "
        f"Individual token safety varies significantly — always check the specific token rating."
    )
    faq2_q = f"What is the total TVL on {_esc(name)}?"
    faq2_a = (
        f"The total value locked across {total} tracked protocols on {_esc(name)} is {tvl_str}. "
        f"This covers DeFi protocols, bridges, staking pools, and other on-chain deployments. "
        f"TVL is sourced from DeFiLlama and updated regularly."
    )
    faq3_q = f"Which {_esc(name)} tokens have the highest risk?"
    critical_tokens = [t for t in tokens if t["risk_level"] in ("CRITICAL", "WARNING")][:5]
    if critical_tokens:
        names_list = ", ".join(_esc(t["name"]) for t in critical_tokens)
        faq3_a = (
            f"The highest-risk tokens on {_esc(name)} currently include: {names_list}. "
            f"These tokens have elevated crash probability or structural weakness signals. "
            f"ZARQ updates risk assessments daily based on quantitative on-chain and market signals."
        )
    else:
        faq3_a = (
            f"Currently no {_esc(name)} tokens are at CRITICAL or WARNING levels. "
            f"Risk levels can change daily based on market conditions and structural signals."
        )

    # JSON-LD
    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Chains", "item": "https://zarq.ai/chains"},
            {"@type": "ListItem", "position": 3, "name": name},
        ]
    })

    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"{name} Token Risk Ratings — {total} Tokens",
        "description": f"Independent risk ratings for {total} tokens on {name}. Trust scores, crash probability, structural integrity.",
        "url": f"https://zarq.ai/chain/{slug}",
        "publisher": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
        "dateModified": today,
    })

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": faq1_q, "acceptedAnswer": {"@type": "Answer", "text": faq1_a}},
            {"@type": "Question", "name": faq2_q, "acceptedAnswer": {"@type": "Answer", "text": faq2_a}},
            {"@type": "Question", "name": faq3_q, "acceptedAnswer": {"@type": "Answer", "text": faq3_a}},
        ]
    })

    html = (
        ZARQ_HEAD
        + f'<title>Best {_esc(name)} Tokens 2026 — Safety Rankings | ZARQ</title>\n'
        + f'<meta name="description" content="{total} tokens on {_esc(name)} ranked by safety. Top rated: {", ".join(_esc(t["name"]) for t in tokens[:3])}.">\n'
        + f'<link rel="canonical" href="https://zarq.ai/chain/{_esc(slug)}">\n'
        + f'<meta property="og:title" content="Best {_esc(name)} Tokens 2026 — Safety Rankings | ZARQ">\n'
        + f'<meta property="og:description" content="{total} tokens on {_esc(name)} ranked by safety. Top rated: {", ".join(_esc(t["name"]) for t in tokens[:3])}.">\n'
        + f'<meta property="og:url" content="https://zarq.ai/chain/{_esc(slug)}">\n'
        + '<meta property="og:type" content="article">\n'
        + '<meta property="og:site_name" content="ZARQ">\n'
        + '<meta name="robots" content="index, follow">\n'
        + f'<script type="application/ld+json">{webpage_jsonld}</script>\n'
        + f'<script type="application/ld+json">{faq_jsonld}</script>\n'
        + f'<script type="application/ld+json">{breadcrumb_jsonld}</script>\n'
        + ZARQ_FONTS + ZARQ_CSS
        + '</head><body>\n'
        + ZARQ_NAV
        + '<div class="container">\n'
        + f'  <div class="breadcrumb"><a href="/">ZARQ</a> / <a href="/chains">Chains</a> / {_esc(name)}</div>\n'
        + f'  <h1>{_esc(name)} — Token Risk Ratings</h1>\n'
        + f'  <p class="subtitle">{total} tokens tracked on {_esc(name)} with independent risk assessments.</p>\n'
        + f'  <div class="ai-summary">{_esc(ai_summary)}</div>\n'
        + summary_cards
        + f'  <h2>All Tokens on {_esc(name)}</h2>\n'
        + '  <table>\n'
        + '    <thead><tr>'
        + '<th data-sort="text">Token</th>'
        + '<th data-sort="text">Symbol</th>'
        + '<th data-sort="text">Category</th>'
        + '<th data-sort="text">Rating</th>'
        + '<th data-sort="num">Score</th>'
        + '<th data-sort="text">Risk</th>'
        + '<th data-sort="num">TVL</th>'
        + '</tr></thead>\n'
        + f'    <tbody>\n{table_rows}    </tbody>\n'
        + '  </table>\n'
        + '  <div class="faq-section">\n'
        + '    <h2>Frequently Asked Questions</h2>\n'
        + f'    <div class="faq-item"><div class="faq-q">{faq1_q}</div><div class="faq-a">{faq1_a}</div></div>\n'
        + f'    <div class="faq-item"><div class="faq-q">{faq2_q}</div><div class="faq-a">{faq2_a}</div></div>\n'
        + f'    <div class="faq-item"><div class="faq-q">{faq3_q}</div><div class="faq-a">{faq3_a}</div></div>\n'
        + '  </div>\n'
        + '  <div style="margin-top:48px;padding:24px;background:var(--gray-100);border:1px solid var(--gray-200);font-family:var(--mono);font-size:12px;color:var(--gray-600)">'
        + '    <strong>Disclaimer:</strong> ZARQ ratings are quantitative risk assessments, not investment advice. Always do your own research.'
        + '  </div>\n'
        + '</div>\n'
        + ZARQ_FOOTER
        + _sort_script()
        + '</body></html>'
    )
    return html


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------

def chain_sitemap(chain_data):
    """Generate XML sitemap for chain pages."""
    today = date.today().isoformat()
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    # Hub page
    xml += f'  <url>\n    <loc>https://zarq.ai/chains</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.9</priority>\n  </url>\n'

    # Individual chain pages
    for slug in sorted(chain_data.keys()):
        xml += f'  <url>\n    <loc>https://zarq.ai/chain/{_esc(slug)}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>\n'

    xml += '</urlset>'
    return xml


def mount_chain_pages(app):
    """Mount /chains, /chain/{slug}, /sitemap-chains.xml on zarq.ai host."""
    from starlette.requests import Request

    def _is_zarq(request: Request) -> bool:
        host = request.headers.get("host", "")
        return "zarq" in host or "localhost" in host or "127.0.0.1" in host

    @app.get("/chains", response_class=HTMLResponse)
    async def chains_hub(request: Request):
        if not _is_zarq(request):
            return HTMLResponse(status_code=404, content="Not found")
        try:
            data = _get_chain_data()
            html = _render_chains_hub(data)
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering chains hub: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/chain/{slug}", response_class=HTMLResponse)
    async def chain_page(slug: str, request: Request):
        if not _is_zarq(request):
            return HTMLResponse(status_code=404, content="Not found")
        try:
            data = _get_chain_data()
            html = _render_chain_page(slug, data)
            if html is None:
                return HTMLResponse(status_code=404, content="<h1>Chain not found</h1><p>No data for this chain.</p>")
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering chain page {slug}: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/sitemap-chains.xml", response_class=Response)
    async def sitemap_chains_xml():
        try:
            data = _get_chain_data()
            xml = chain_sitemap(data)
            return Response(content=xml, media_type="application/xml")
        except Exception as e:
            logger.error(f"Error generating chains sitemap: {e}")
            return Response(status_code=500, content="Error generating sitemap")

    logger.info("Mounted chain pages: /chains, /chain/{slug}, /sitemap-chains.xml")
