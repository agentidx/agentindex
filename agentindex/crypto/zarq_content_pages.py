"""
ZARQ Content Pages
==================
Three SEO-optimized content pages:
  /crash-watch  — Live crash prediction dashboard
  /yield-risk   — DeFi yield risk monitor
  /learn        — Educational hub + 5 articles
  /learn/{slug} — Individual article pages

Usage in discovery.py:
    from agentindex.crypto.zarq_content_pages import mount_zarq_content_pages
    mount_zarq_content_pages(app)
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import date

from fastapi.responses import HTMLResponse, Response

logger = logging.getLogger("zarq.content_pages")

DB_PATH = str(Path(__file__).parent / "crypto_trust.db")
TEMPLATE_DIR = Path(__file__).parent / "templates"


def _esc(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fmt_pct(val):
    if val is None:
        return "N/A"
    return f"{val * 100:.1f}" if val < 1 else f"{val:.1f}"


def _fmt_usd(val):
    if val is None:
        return "N/A"
    if val >= 1e9:
        return f"{val / 1e9:.1f}B"
    if val >= 1e6:
        return f"{val / 1e6:.1f}M"
    if val >= 1e3:
        return f"{val / 1e3:.0f}K"
    return f"{val:.0f}"


# ─── Shared ZARQ design elements ─────────────────────────────────────

ZARQ_CSS = """:root {
  --white: #fafaf9;
  --black: #0a0a0a;
  --gray-100: #f5f5f4;
  --gray-200: #e7e5e4;
  --gray-300: #d6d3d1;
  --gray-400: #a8a29e;
  --gray-500: #78716c;
  --gray-600: #57534e;
  --gray-700: #44403c;
  --gray-800: #292524;
  --gray-900: #1c1917;
  --warm: #c2956b;
  --warm-light: rgba(194, 149, 107, 0.08);
  --green: #16a34a;
  --red: #dc2626;
  --yellow: #ca8a04;
  --serif: 'DM Serif Display', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'DM Sans', sans-serif;
  --measure: 680px;
  --wide: 1120px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
::selection { background: var(--warm); color: var(--black); }
html { font-size: 17px; -webkit-font-smoothing: antialiased; }
body { background: var(--white); color: var(--gray-800); font-family: var(--sans); line-height: 1.6; }

nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  padding: 20px 40px; display: flex; justify-content: space-between; align-items: center;
  backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  background: rgba(250, 250, 249, 0.85); border-bottom: 1px solid rgba(0,0,0,0.04);
}
.nav-mark { font-family: var(--mono); font-weight: 500; font-size: 15px; letter-spacing: 0.15em; text-transform: uppercase; color: var(--black); text-decoration: none; }
.nav-links { display: flex; gap: 32px; align-items: center; }
.nav-links a { font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-600); text-decoration: none; transition: color 0.2s; }
.nav-links a:hover { color: var(--black); }
.nav-api { font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; color: var(--warm); border: 1px solid var(--warm); padding: 6px 16px; text-decoration: none; transition: all 0.2s; }
.nav-api:hover { background: var(--warm); color: var(--white); }
.nav-dropdown { position: relative; }
.nav-dropdown-trigger { cursor: pointer; }
.nav-dropdown-menu { display: none; position: absolute; top: 100%; right: 0; background: var(--white); border: 1px solid var(--gray-200); box-shadow: 0 8px 24px rgba(0,0,0,0.08); padding: 8px 0; min-width: 180px; z-index: 200; }
.nav-dropdown:hover .nav-dropdown-menu { display: block; }
.nav-dropdown-menu a { display: block; padding: 8px 20px; font-family: var(--mono); font-size: 12px; letter-spacing: 0.05em; color: var(--gray-600); text-decoration: none; white-space: nowrap; }
.nav-dropdown-menu a:hover { background: var(--warm-light, rgba(194,149,107,0.08)); color: var(--black); }
.nav-toggle-input { display: none; }
.nav-hamburger { display: none; cursor: pointer; flex-direction: column; gap: 5px; }
.nav-hamburger span { display: block; width: 22px; height: 2px; background: var(--black); transition: all 0.3s; }

.container { max-width: var(--wide); margin: 0 auto; padding: 120px 40px 80px; }

.breadcrumb { font-family: var(--mono); font-size: 11px; color: var(--gray-500); margin-bottom: 24px; }
.breadcrumb a { color: var(--warm); text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }

h1 { font-family: var(--serif); font-size: 2.4rem; color: var(--black); line-height: 1.2; margin-bottom: 16px; }
.subtitle { font-family: var(--sans); font-size: 1rem; color: var(--gray-600); margin-bottom: 40px; }

.ai-summary { background: var(--gray-100); border-left: 3px solid var(--warm); padding: 20px 24px; margin-bottom: 40px; font-family: var(--sans); font-size: 15px; line-height: 1.7; color: var(--gray-700); }

.section-title { font-family: var(--serif); font-size: 1.6rem; color: var(--black); margin-bottom: 24px; margin-top: 48px; }

.faq-section { margin-top: 48px; margin-bottom: 48px; }
.faq-item { border-bottom: 1px solid var(--gray-200); padding: 24px 0; }
.faq-item:first-child { border-top: 1px solid var(--gray-200); }
.faq-q { font-family: var(--serif); font-size: 1.2rem; color: var(--black); margin-bottom: 12px; }
.faq-a { font-family: var(--sans); font-size: 15px; color: var(--gray-700); line-height: 1.7; }

footer { border-top: 1px solid var(--gray-200); padding: 40px; text-align: center; }
footer p { font-family: var(--mono); font-size: 11px; color: var(--gray-500); }
footer a { color: var(--warm); text-decoration: none; }

@media (max-width: 768px) {
  nav { padding: 16px 20px; }
  .nav-hamburger { display: flex; }
  .nav-links { display: none; position: absolute; top: 100%; left: 0; right: 0; background: var(--white); border-bottom: 1px solid var(--gray-200); padding: 16px 20px; flex-direction: column; gap: 16px; }
  .nav-toggle-input:checked ~ .nav-links { display: flex; }
  .nav-dropdown-menu { display: block; position: static; box-shadow: none; border: none; padding: 0 0 0 12px; }
  .nav-dropdown-trigger { display: none; }
  .container { padding: 100px 20px 60px; }
  h1 { font-size: 1.8rem; }
}"""

ZARQ_NAV = """<nav>
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
</nav>"""

ZARQ_FOOTER = """<footer>
  <p>&copy; 2026 <a href="https://zarq.ai">ZARQ</a> &mdash; Independent crypto risk intelligence &middot;
    <a href="/tokens">Tokens</a> &middot;
    <a href="/crash-watch">Crash Watch</a> &middot;
    <a href="/yield-risk">Yield Risk</a> &middot;
    <a href="/learn">Learn</a> &middot;
    <a href="/methodology">Methodology</a> &middot;
    <a href="/track-record">Track Record</a>
        <a href="/paper-trading">Paper Trading</a> &middot;
    <a href="https://nerq.ai">Nerq</a>
  </p>
</footer>"""


# ─── PAGE 1: /crash-watch ────────────────────────────────────────────

def _render_crash_watch():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get all tokens with risk data, sorted by severity
    rows = conn.execute("""
        SELECT
            s.token_id,
            s.risk_level,
            s.structural_weakness,
            s.ndd_current,
            s.sig6_structure,
            s.trust_score,
            s.drawdown_90d,
            r.rating,
            r.score,
            n.crash_probability,
            n.alert_level,
            COALESCE(n.name, r.name, s.token_id) as name
        FROM nerq_risk_signals s
        LEFT JOIN crypto_rating_daily r ON s.token_id = r.token_id
            AND r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
        LEFT JOIN crypto_ndd_daily n ON s.token_id = n.token_id
            AND n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
        WHERE s.signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
        ORDER BY
            CASE s.risk_level
                WHEN 'CRITICAL' THEN 1
                WHEN 'WARNING' THEN 2
                WHEN 'WATCH' THEN 3
                ELSE 4
            END,
            n.crash_probability DESC NULLS LAST,
            s.ndd_current ASC NULLS LAST
    """).fetchall()
    conn.close()

    total = len(rows)
    critical = sum(1 for r in rows if r["risk_level"] == "CRITICAL")
    warning = sum(1 for r in rows if r["risk_level"] == "WARNING")
    watch = sum(1 for r in rows if r["risk_level"] == "WATCH")
    safe = sum(1 for r in rows if r["risk_level"] == "SAFE")
    total_warnings = critical + warning

    # Build table rows — show all non-SAFE tokens
    table_html = ""
    for r in rows:
        if r["risk_level"] == "SAFE":
            continue
        token_id = r["token_id"]
        name = r["name"] or token_id
        slug = token_id.lower().replace(" ", "-")
        rating = r["rating"] or "NR"
        crash_prob = r["crash_probability"]
        crash_str = f"{crash_prob * 100:.0f}%" if crash_prob is not None else "N/A"
        ndd = r["ndd_current"]
        ndd_str = f"{ndd:.2f}" if ndd is not None else "N/A"
        risk = r["risk_level"] or "WATCH"
        status_class = f"status-{risk.lower()}"
        sw = r["structural_weakness"] or 0

        # Key warning signal
        if sw and sw >= 1:
            key_warning = "Structural collapse detected"
        elif ndd is not None and ndd < 1.5:
            key_warning = "Near default threshold"
        elif crash_prob is not None and crash_prob > 0.5:
            key_warning = "High crash probability"
        elif r["drawdown_90d"] is not None and r["drawdown_90d"] < -0.5:
            dd = abs(r["drawdown_90d"]) * 100
            key_warning = f"{dd:.0f}% drawdown (90d)"
        elif ndd is not None and ndd < 2.0:
            key_warning = "Elevated distress signal"
        else:
            key_warning = "Under observation"

        table_html += (
            f'      <tr>\n'
            f'        <td><a href="/token/{_esc(slug)}" class="token-link">{_esc(name)}</a></td>\n'
            f'        <td class="mono-cell">{_esc(rating)}</td>\n'
            f'        <td class="mono-cell">{crash_str}</td>\n'
            f'        <td class="mono-cell">{ndd_str}</td>\n'
            f'        <td class="{status_class}">{_esc(risk)}</td>\n'
            f'        <td>{key_warning}</td>\n'
            f'      </tr>\n'
        )

    # FAQ
    faq_items = [
        {
            "q": "How accurate is ZARQ's crash prediction?",
            "a": (
                f"ZARQ's structural collapse model has achieved 100% recall (113 out of 113 historical collapses detected) "
                f"and 98% precision in out-of-sample testing from January 2024 to February 2026. The average detection lead time "
                f"is 22 months before terminal failure. The 1st target (-30%) hit rate is 92%, and the 2nd target (-50%) hit rate "
                f"is 65%. The full track record is independently verifiable at "
                f"github.com/kbanilsson-pixel/track-record. The model uses 7 quantitative signals adapted from Merton's "
                f"structural credit model to detect distress before price collapse."
            ),
        },
        {
            "q": "Which cryptos are most likely to crash?",
            "a": (
                f"As of {date.today().strftime('%B %Y')}, ZARQ monitors {total} tokens. Currently {critical} are rated CRITICAL "
                f"(imminent structural collapse risk), {warning} are WARNING (elevated stress), and {watch} are WATCH (under observation). "
                f"Tokens with Distance-to-Default below 1.0 have historically all experienced terminal failure. "
                f"Check the table above for the current watchlist sorted by severity. Individual token pages at /token/{{slug}} "
                f"provide detailed signal breakdowns."
            ),
        },
        {
            "q": "What is structural collapse in crypto?",
            "a": (
                f"Structural collapse is ZARQ's term for when a cryptocurrency's fundamental support structure deteriorates "
                f"beyond recovery — similar to how a bridge can fail from cumulative stress rather than a single event. "
                f"It's measured through Distance-to-Default (DtD), adapted from Merton's model originally used to predict "
                f"corporate defaults. When DtD falls below 1.0, the token has breached the distress threshold. "
                f"The 7 signals that compose DtD are: Liquidity Depth (10%), Holder Concentration (5%), Ecosystem Resilience (30%), "
                f"Fundamental Activity (10%), Contagion Exposure (25%), Structural Risk (5%), and Relative Weakness (15%). "
                f"A token can appear stable on price alone while its structural foundation is eroding — ZARQ detects this."
            ),
        },
    ]

    faq_html = ""
    faq_jsonld_items = []
    for item in faq_items:
        faq_html += (
            f'    <div class="faq-item">\n'
            f'      <div class="faq-q">{_esc(item["q"])}</div>\n'
            f'      <div class="faq-a">{item["a"]}</div>\n'
            f'    </div>\n'
        )
        faq_jsonld_items.append({
            "@type": "Question",
            "name": item["q"],
            "acceptedAnswer": {"@type": "Answer", "text": item["a"]}
        })

    today = date.today().isoformat()

    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Crypto Crash Watch — Tokens at Risk of Structural Collapse",
        "description": f"{total_warnings} tokens show structural stress or collapse warnings. 100% recall, 98% precision.",
        "url": "https://zarq.ai/crash-watch",
        "publisher": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
        "dateModified": today,
    })

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_jsonld_items
    })

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Crash Watch"},
        ]
    })

    html = (TEMPLATE_DIR / "crash_watch.html").read_text()
    replacements = {
        "{{ zarq_css }}": ZARQ_CSS,
        "{{ zarq_nav }}": ZARQ_NAV,
        "{{ zarq_footer }}": ZARQ_FOOTER,
        "{{ total_monitored }}": str(total),
        "{{ total_warnings }}": str(total_warnings),
        "{{ critical_count }}": str(critical),
        "{{ warning_count }}": str(warning),
        "{{ watch_count }}": str(watch),
        "{{ safe_count }}": str(safe),
        "{{ run_date }}": date.today().strftime("%B %d, %Y"),
        "{{ table_rows }}": table_html,
        "{{ faq_html }}": faq_html,
        "{{ webpage_jsonld }}": webpage_jsonld,
        "{{ faq_jsonld }}": faq_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
    }
    for k, v in replacements.items():
        html = html.replace(k, str(v))
    return html


# ─── PAGE 2: /yield-risk ─────────────────────────────────────────────

def _yield_risk_level(apy, il_risk, tvl, apy_reward=None):
    """Classify a DeFi pool into risk tiers."""
    if tvl is not None and tvl < 1_000_000 and apy and apy > 50:
        return "high"
    if apy and apy > 100:
        return "high"
    if il_risk == "yes" and apy and apy > 50:
        return "high"
    if apy_reward and apy_reward > 0 and apy and apy > 30:
        return "high"
    if il_risk == "yes":
        return "moderate"
    if apy_reward and apy_reward > 0:
        return "moderate"
    if tvl is not None and tvl < 10_000_000:
        return "moderate"
    return "low"


def _yield_warning(apy, il_risk, tvl, apy_reward=None, apy_base=None):
    """Generate warning text for a pool."""
    warnings = []
    if apy and apy > 100:
        warnings.append("Extremely high APY")
    elif apy and apy > 50:
        warnings.append("Elevated APY")
    if il_risk == "yes":
        warnings.append("IL exposure")
    if apy_reward and apy_base and apy_reward > apy_base:
        warnings.append("Reward-driven")
    if tvl is not None and tvl < 1_000_000:
        warnings.append("Low TVL")
    return ", ".join(warnings) if warnings else "—"


def _render_yield_risk():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get latest yields
    rows = conn.execute("""
        SELECT project, symbol, chain, apy, apy_base, apy_reward,
               tvl_usd, il_risk, stablecoin
        FROM defi_yields
        WHERE apy IS NOT NULL AND apy > 0 AND apy < 10000
          AND tvl_usd IS NOT NULL AND tvl_usd > 100000
        ORDER BY tvl_usd DESC
    """).fetchall()

    # Get project count
    project_count = conn.execute("SELECT COUNT(DISTINCT project) FROM defi_yields WHERE apy IS NOT NULL").fetchone()[0]

    conn.close()

    total_pools = len(rows)
    total_tvl = sum(r["tvl_usd"] or 0 for r in rows)

    # Classify pools
    low_count = 0
    moderate_count = 0
    high_count = 0
    for r in rows:
        level = _yield_risk_level(r["apy"], r["il_risk"], r["tvl_usd"], r["apy_reward"])
        if level == "low":
            low_count += 1
        elif level == "moderate":
            moderate_count += 1
        else:
            high_count += 1

    low_pct = round(low_count / total_pools * 100) if total_pools else 0
    high_pct = round(high_count / total_pools * 100) if total_pools else 0

    # Safe yields table — best risk-adjusted (low risk, sorted by APY desc)
    safe_rows = sorted(
        [r for r in rows if _yield_risk_level(r["apy"], r["il_risk"], r["tvl_usd"], r["apy_reward"]) == "low"
         and r["tvl_usd"] and r["tvl_usd"] > 10_000_000],
        key=lambda x: x["apy"] or 0,
        reverse=True
    )[:30]

    safe_table = ""
    for r in safe_rows:
        safe_table += (
            f'      <tr>\n'
            f'        <td>{_esc(r["project"])}</td>\n'
            f'        <td>{_esc(r["symbol"])}</td>\n'
            f'        <td>{_esc(r["chain"])}</td>\n'
            f'        <td class="mono-cell">{r["apy"]:.2f}%</td>\n'
            f'        <td class="mono-cell">${_fmt_usd(r["tvl_usd"])}</td>\n'
            f'        <td><span class="risk-dot risk-dot-low"></span><span class="risk-low">Low</span></td>\n'
            f'      </tr>\n'
        )

    # All pools table — sorted by APY desc with risk color
    all_sorted = sorted(rows, key=lambda x: x["apy"] or 0, reverse=True)[:50]
    all_table = ""
    for r in all_sorted:
        level = _yield_risk_level(r["apy"], r["il_risk"], r["tvl_usd"], r["apy_reward"])
        dot_class = f"risk-dot-{level}"
        text_class = f"risk-{level}"
        warning = _yield_warning(r["apy"], r["il_risk"], r["tvl_usd"], r["apy_reward"], r["apy_base"])
        all_table += (
            f'      <tr>\n'
            f'        <td>{_esc(r["project"])}</td>\n'
            f'        <td>{_esc(r["symbol"])}</td>\n'
            f'        <td>{_esc(r["chain"])}</td>\n'
            f'        <td class="mono-cell">{r["apy"]:.2f}%</td>\n'
            f'        <td class="mono-cell">${_fmt_usd(r["tvl_usd"])}</td>\n'
            f'        <td><span class="risk-dot {dot_class}"></span><span class="{text_class}">{level.title()}</span></td>\n'
            f'        <td style="font-size:13px;color:var(--gray-600)">{warning}</td>\n'
            f'      </tr>\n'
        )

    # Top safe projects for AI summary
    safe_projects = []
    seen = set()
    for r in safe_rows[:10]:
        if r["project"] not in seen:
            safe_projects.append(r["project"])
            seen.add(r["project"])
        if len(safe_projects) >= 3:
            break
    top_safe = ", ".join(safe_projects) if safe_projects else "Aave, Lido, Morpho"

    # FAQ
    faq_items = [
        {
            "q": "How to tell if a DeFi yield is safe?",
            "a": (
                f"Safe DeFi yields share three characteristics: they come from base APY (real economic activity like lending "
                f"interest or trading fees, not token reward emissions), they have no impermanent loss exposure (single-asset "
                f"deposits or same-peg pairs), and they operate on established protocols with high TVL and audit history. "
                f"Currently {low_count:,} out of {total_pools:,} monitored pools meet ZARQ's low-risk criteria. "
                f"As a rule of thumb: if a yield looks too good to be true (above 50% APY), it almost certainly is. "
                f"Check /crash-watch for tokens whose underlying value may be deteriorating."
            ),
        },
        {
            "q": "What makes a high APY risky?",
            "a": (
                f"High APY is risky because it's usually funded by token reward emissions rather than organic activity. "
                f"When a protocol offers 200% APY, it's typically printing governance tokens and distributing them as rewards. "
                f"These tokens often lose value over time as selling pressure increases, so your real return is much lower than "
                f"the advertised APY. Additionally, high-APY pools often involve impermanent loss (IL) — when you provide liquidity "
                f"to a trading pair, price divergence between the two tokens reduces your holdings. "
                f"Currently {high_count:,} pools ({high_pct}% of monitored pools) are flagged as high risk by ZARQ."
            ),
        },
        {
            "q": "How does ZARQ assess yield risk?",
            "a": (
                f"ZARQ's Yield Risk Engine classifies {total_pools:,} DeFi pools across {project_count} protocols into three "
                f"risk tiers. Low Risk (green): base APY only, no IL, TVL above $10M, established protocol. Moderate Risk "
                f"(yellow): includes reward emissions, moderate TVL, or some IL exposure. High Risk (red): APY above 50%, "
                f"low TVL, significant IL, or reward-dominated returns. Data is sourced from DeFiLlama's yield API and "
                f"cross-referenced with ZARQ's token risk ratings. Pools where the underlying token has a CRITICAL or "
                f"WARNING risk level on ZARQ's crash watch carry additional risk."
            ),
        },
    ]

    faq_html = ""
    faq_jsonld_items = []
    for item in faq_items:
        faq_html += (
            f'    <div class="faq-item">\n'
            f'      <div class="faq-q">{_esc(item["q"])}</div>\n'
            f'      <div class="faq-a">{item["a"]}</div>\n'
            f'    </div>\n'
        )
        faq_jsonld_items.append({
            "@type": "Question",
            "name": item["q"],
            "acceptedAnswer": {"@type": "Answer", "text": item["a"]}
        })

    today = date.today().isoformat()

    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "DeFi Yield Risk Monitor — Safe Yields vs Dangerous APY",
        "description": f"{total_pools} DeFi pools monitored. Color-coded risk assessment for yield farming.",
        "url": "https://zarq.ai/yield-risk",
        "publisher": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
        "dateModified": today,
    })

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_jsonld_items
    })

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Yield Risk"},
        ]
    })

    html = (TEMPLATE_DIR / "yield_risk.html").read_text()
    replacements = {
        "{{ zarq_css }}": ZARQ_CSS,
        "{{ zarq_nav }}": ZARQ_NAV,
        "{{ zarq_footer }}": ZARQ_FOOTER,
        "{{ total_pools }}": f"{total_pools:,}",
        "{{ total_projects }}": str(project_count),
        "{{ total_tvl }}": _fmt_usd(total_tvl),
        "{{ crawled_date }}": date.today().strftime("%B %d, %Y"),
        "{{ low_risk_count }}": f"{low_count:,}",
        "{{ moderate_risk_count }}": f"{moderate_count:,}",
        "{{ high_risk_count }}": f"{high_count:,}",
        "{{ low_risk_pct }}": str(low_pct),
        "{{ high_risk_pct }}": str(high_pct),
        "{{ top_safe_projects }}": _esc(top_safe),
        "{{ safe_table_rows }}": safe_table,
        "{{ all_table_rows }}": all_table,
        "{{ faq_html }}": faq_html,
        "{{ webpage_jsonld }}": webpage_jsonld,
        "{{ faq_jsonld }}": faq_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
    }
    for k, v in replacements.items():
        html = html.replace(k, str(v))
    return html


# ─── PAGE 3: /learn ──────────────────────────────────────────────────

ARTICLES = [
    {
        "slug": "how-to-check-if-crypto-is-safe",
        "title": "How to Check If a Cryptocurrency Is Safe (2026 Guide)",
        "short_title": "How to Check If Crypto Is Safe",
        "subtitle": "A practical guide to the 7 risk signals that matter most — with real examples from ZARQ's live analysis.",
        "meta_description": "Learn how to check if a cryptocurrency is safe using 7 quantitative risk signals. Real examples with trust scores, crash probabilities, and structural analysis.",
        "og_description": "How to check if a cryptocurrency is safe: 7 risk signals explained with real data.",
    },
    {
        "slug": "defi-risk-checklist",
        "title": "DeFi Risk Checklist: 7 Signals That Matter",
        "short_title": "DeFi Risk Checklist",
        "subtitle": "Before you deposit into any DeFi protocol, check these 7 signals to separate safe yields from ticking time bombs.",
        "meta_description": "DeFi risk checklist: 7 quantitative signals to assess protocol safety. Includes yield risk, TVL analysis, and crash probability checks.",
        "og_description": "DeFi risk checklist: 7 signals to check before depositing into any protocol.",
    },
    {
        "slug": "understanding-crash-probability",
        "title": "Understanding Crash Probability: A Beginner's Guide",
        "short_title": "Understanding Crash Probability",
        "subtitle": "What does '32% crash probability' actually mean? A plain-English explanation of ZARQ's crash model.",
        "meta_description": "Understanding crypto crash probability: what it means, how it's calculated, and how to use it. Beginner-friendly guide with real token examples.",
        "og_description": "What does crash probability mean? A beginner's guide with real crypto examples.",
    },
    {
        "slug": "distance-to-default-explained",
        "title": "What Is Distance-to-Default? Crypto Risk Explained",
        "short_title": "Distance-to-Default Explained",
        "subtitle": "Distance-to-Default is the most important number in crypto risk. Here's what it means and why it matters.",
        "meta_description": "Distance-to-Default (DtD) explained for crypto: how Merton's structural model predicts token failure. 100% recall on historical collapses.",
        "og_description": "Distance-to-Default explained: the number that predicts crypto collapse.",
    },
    {
        "slug": "crypto-trust-scores",
        "title": "Crypto Trust Scores: How ZARQ Rates Tokens",
        "short_title": "Crypto Trust Scores",
        "subtitle": "A Moody's-style rating system for crypto. Here's how it works and what the ratings mean.",
        "meta_description": "How ZARQ's crypto trust scores work: Moody's-style Aaa-D ratings based on 5 quantitative pillars. Independent, transparent, machine-readable.",
        "og_description": "How ZARQ rates crypto tokens on a Moody's-style scale from Aaa to D.",
    },
]


def _get_example_tokens():
    """Fetch a diverse set of real tokens for article examples."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT r.token_id, r.rating, r.score, r.name,
               n.crash_probability, n.ndd, n.alert_level, n.symbol,
               s.structural_weakness, s.risk_level
        FROM crypto_rating_daily r
        LEFT JOIN crypto_ndd_daily n ON r.token_id = n.token_id
            AND n.run_date = (SELECT MAX(run_date) FROM crypto_ndd_daily)
        LEFT JOIN nerq_risk_signals s ON r.token_id = s.token_id
            AND s.signal_date = (SELECT MAX(signal_date) FROM nerq_risk_signals)
        WHERE r.run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)
        ORDER BY r.score DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_total_tokens():
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(DISTINCT token_id) FROM crypto_rating_daily WHERE run_date = (SELECT MAX(run_date) FROM crypto_rating_daily)").fetchone()[0]
    conn.close()
    return count


def _build_article_body(slug, tokens):
    """Generate educational article content with real data woven in."""
    # Find specific tokens by name/rating for examples
    def find(name):
        for t in tokens:
            if t["token_id"] == name or (t.get("name") and t["name"].lower() == name.lower()):
                return t
        return None

    btc = find("bitcoin") or {}
    eth = find("ethereum") or {}
    sol = find("solana") or {}
    # Find a warning-level token
    warned = next((t for t in tokens if t.get("risk_level") == "WARNING" and t.get("crash_probability")), {})
    # Find a critical token
    critical = next((t for t in tokens if t.get("risk_level") == "CRITICAL" and t.get("crash_probability")), {})
    # Find a high-rated token
    top = tokens[0] if tokens else {}
    # Find a low-rated token
    low = tokens[-1] if tokens else {}

    def _tk_link(t):
        tid = t.get("token_id", "")
        name = t.get("name", tid)
        return f'<a href="/token/{_esc(tid)}">{_esc(name)}</a>'

    def _tk_score(t):
        s = t.get("score")
        return f"{s:.1f}" if s else "N/A"

    def _tk_crash(t):
        cp = t.get("crash_probability")
        return f"{cp * 100:.0f}%" if cp else "N/A"

    def _tk_ndd(t):
        n = t.get("ndd")
        return f"{n:.2f}" if n else "N/A"

    if slug == "how-to-check-if-crypto-is-safe":
        return f"""
    <h2>Why Most "DYOR" Advice Falls Short</h2>
    <p>Everyone tells you to "do your own research" before investing in crypto. But what does that actually mean in practice? Reading a whitepaper? Checking the team's LinkedIn? Scrolling through Twitter sentiment? None of these tell you the most important thing: <strong>is this token structurally sound, or is it slowly collapsing?</strong></p>
    <p>ZARQ uses 7 quantitative risk signals — no opinions, no hype, just math — to answer this question for every rated token. Here's how each signal works and what to look for.</p>

    <h2>Signal 1: Trust Score (0-100)</h2>
    <p>The trust score is the starting point. It's a composite of five pillars: ecosystem strength, contagion risk, historical resilience, fundamental quality, and rug pull risk. Scores above 70 indicate investment-grade quality. Below 50 means significant concerns.</p>
    <div class="example-box">
      <div class="ex-label">Real Example</div>
      <p>{_tk_link(btc)} has a trust score of {_tk_score(btc)}/100 — one of the highest-rated tokens. Compare that to {_tk_link(low)}, which scores {_tk_score(low)}/100. The gap reflects differences in liquidity, track record, and structural integrity.</p>
    </div>

    <h2>Signal 2: Rating (Aaa to D)</h2>
    <p>ZARQ maps trust scores to a Moody's-style rating scale. Aaa is the highest quality. Baa3 and above is "investment grade" — everything below is speculative. The rating tells you at a glance where a token sits on the quality spectrum.</p>
    <p>Current distribution: most tokens fall in the A3 to Baa2 range. Very few earn Aaa or Aa ratings. Tokens rated Ba or below carry materially higher risk of significant drawdowns.</p>

    <h2>Signal 3: Crash Probability</h2>
    <p>This is the model-estimated likelihood of a &gt;50% drawdown. It's not a prediction of "when" — it's a risk measure. A token with 5% crash probability is structurally sound. A token with 40% crash probability has real structural weaknesses that could lead to collapse.</p>
    <div class="example-box">
      <div class="ex-label">Real Example</div>
      <p>{_tk_link(btc)}: {_tk_crash(btc)} crash probability. {_tk_link(eth)}: {_tk_crash(eth)}. {'Compare to ' + _tk_link(warned) + ': ' + _tk_crash(warned) + ' — significantly elevated.' if warned else ''}</p>
    </div>

    <h2>Signal 4: Distance-to-Default (DtD)</h2>
    <p>Adapted from Merton's structural credit model, DtD measures how far a token is from its "default threshold" — the point where structural collapse becomes likely. Above 3.0 is healthy. Between 1.0 and 2.0 is elevated risk. Below 1.0 means the token has breached the distress threshold, and historically, 100% of tokens that reach this level have experienced terminal failure.</p>
    <p>Learn more: <a href="/learn/distance-to-default-explained">Distance-to-Default Explained</a></p>

    <h2>Signal 5: Structural Weakness Flag</h2>
    <p>A binary signal that fires when the DtD model detects deteriorating structural integrity. Currently {sum(1 for t in tokens if t.get('structural_weakness') and t['structural_weakness'] >= 1)} tokens have active structural weakness flags. When this flag is active, the token is in ZARQ's <a href="/crash-watch">Crash Watch</a> list.</p>

    <h2>Signal 6: Risk Level (SAFE / WATCH / WARNING / CRITICAL)</h2>
    <p>ZARQ assigns every token a risk level based on the combination of all signals. SAFE means no structural concerns. WATCH means the token is being monitored for emerging stress. WARNING means elevated risk with active stress signals. CRITICAL means structural collapse is imminent or underway.</p>

    <h2>Signal 7: Contagion Exposure</h2>
    <p>No token exists in isolation. When a major token collapses, it can drag others down with it — especially tokens in the same ecosystem or with high correlation. ZARQ's contagion model maps these interconnections. Tokens with high contagion exposure carry "hidden" risk that isn't visible from their own fundamentals.</p>

    <h2>How to Use These Signals</h2>
    <p>Start with the quick check: <code>GET zarq.ai/v1/check/{{token}}</code>. This returns a single verdict (SAFE, WARNING, or CRITICAL) along with the trust score, crash probability, and DtD. For deeper analysis, visit the individual <a href="/tokens">token rating page</a>.</p>
    <p>The key principle: <strong>look for convergence</strong>. A token with a good trust score but rising crash probability is a yellow flag. A token with a WARNING risk level but stable DtD might be experiencing temporary stress. When multiple signals point in the same direction, that's the signal that matters.</p>
"""

    elif slug == "defi-risk-checklist":
        return f"""
    <h2>The 7-Point DeFi Risk Checklist</h2>
    <p>Before depositing into any DeFi protocol, check these seven signals. Each one catches a different type of risk. Together, they give you a comprehensive picture of whether a yield opportunity is genuinely safe or a ticking time bomb.</p>

    <h3>1. Where Does the Yield Come From?</h3>
    <p>This is the single most important question. There are only three legitimate sources of yield in DeFi:</p>
    <ul>
      <li><strong>Lending interest</strong> — borrowers pay you to use your capital (Aave, Compound, Morpho)</li>
      <li><strong>Trading fees</strong> — you earn a share of swap fees by providing liquidity (Uniswap, Curve)</li>
      <li><strong>Staking rewards</strong> — you earn protocol inflation for securing the network (Lido, Rocket Pool)</li>
    </ul>
    <p>If the APY comes from "reward tokens" instead of one of these three sources, the yield is likely unsustainable. When rewards dry up, the APY collapses — and so does the token price of the rewards.</p>

    <h3>2. Check the Base APY vs Reward APY Split</h3>
    <p>ZARQ's <a href="/yield-risk">Yield Risk Monitor</a> breaks down every pool's APY into base (organic) and reward (token emissions). If the reward APY is higher than the base APY, most of the yield is coming from token printing — a red flag. Safe pools have base APY that makes economic sense on its own.</p>

    <h3>3. Impermanent Loss Exposure</h3>
    <p>If you're providing liquidity to a trading pair, you're exposed to impermanent loss (IL). When the prices of the two tokens diverge, you end up with less value than if you'd simply held them. IL can easily wipe out months of yield. Stablecoin pairs (USDC/USDT) have near-zero IL. Volatile pairs (ETH/MEME) can have devastating IL.</p>

    <h3>4. TVL Stability</h3>
    <p>Total Value Locked tells you how much capital other people trust the protocol with. High TVL (&gt;$100M) from a diversified depositor base is a positive signal. Low TVL (&lt;$1M) or rapidly declining TVL is a warning. On ZARQ's yield monitor, pools below $10M TVL are automatically flagged as elevated risk.</p>

    <h3>5. Check the Underlying Token's Risk Rating</h3>
    <p>Even a "safe" yield is worthless if the underlying token collapses. Before depositing into any pool, check the risk rating of the tokens involved on ZARQ's <a href="/tokens">token ratings page</a>. If the underlying token is rated WARNING or CRITICAL on the <a href="/crash-watch">Crash Watch</a>, your yield is at serious risk.</p>
    <div class="example-box">
      <div class="ex-label">Cross-Check Example</div>
      <p>{_tk_link(eth)} is rated {eth.get('rating', 'N/A')} with {_tk_crash(eth)} crash probability — low underlying risk. A yield from an ETH staking pool on a reputable protocol is much safer than an exotic yield on a token with structural warnings.</p>
    </div>

    <h3>6. Audit History</h3>
    <p>Has the protocol been audited by a reputable firm? How many audits? Are the audit reports public? Protocols with zero audits or only self-audits carry significantly higher smart contract risk. Major protocols like Aave and Compound have multiple audits from firms like Trail of Bits and OpenZeppelin.</p>

    <h3>7. Protocol Age and Track Record</h3>
    <p>Protocols that have survived multiple market cycles are less likely to have critical vulnerabilities. New protocols (less than 6 months old) have not been battle-tested. The DeFi graveyard is full of protocols that offered amazing yields for a few months before collapsing.</p>

    <h2>Quick Risk Assessment Framework</h2>
    <ul>
      <li><strong>Green light:</strong> Base APY only, no IL, TVL &gt; $100M, multiple audits, 1+ year old</li>
      <li><strong>Yellow light:</strong> Some reward APY, moderate IL, TVL $10M-$100M, 1 audit, 6-12 months old</li>
      <li><strong>Red light:</strong> Reward-dominated APY &gt; 50%, high IL, TVL &lt; $10M, no audits, &lt; 6 months old</li>
    </ul>
    <p>Use ZARQ's <a href="/yield-risk">Yield Risk Monitor</a> to see this analysis applied to thousands of live pools.</p>
"""

    elif slug == "understanding-crash-probability":
        return f"""
    <h2>What Does "32% Crash Probability" Mean?</h2>
    <p>When ZARQ says a token has a 32% crash probability, it means: based on the token's current structural signals, there is approximately a 1-in-3 chance of a &gt;50% price decline. It does <strong>not</strong> mean the token will lose 32% of its value. It's a probability of a severe event, not a price prediction.</p>
    <p>Think of it like weather forecasting. "30% chance of rain" doesn't mean it will drizzle — it means there's a meaningful chance of a storm. In crypto, a 30%+ crash probability means the structural foundations are stressed enough that a collapse is a realistic scenario.</p>

    <h2>How Is It Calculated?</h2>
    <p>ZARQ's crash probability model uses 7 quantitative signals, each weighted based on its historical predictive power:</p>
    <ol>
      <li><strong>Liquidity Depth (10%)</strong> — How deep is the order book? Low liquidity means small sells cause big price drops.</li>
      <li><strong>Holder Concentration (5%)</strong> — Are a few wallets holding most of the supply? Concentrated holdings increase dump risk.</li>
      <li><strong>Ecosystem Resilience (30%)</strong> — How well does the token recover from market-wide shocks? This is the single most important signal.</li>
      <li><strong>Fundamental Activity (10%)</strong> — Is the network actually being used? Active addresses, transaction volume, developer activity.</li>
      <li><strong>Contagion Exposure (25%)</strong> — How interconnected is this token with other at-risk tokens? Contagion cascades are a leading cause of crypto crashes.</li>
      <li><strong>Structural Risk (5%)</strong> — Detected anomalies in price patterns that historically precede collapses.</li>
      <li><strong>Relative Weakness (15%)</strong> — Is the token underperforming its peers? Persistent relative weakness often precedes absolute decline.</li>
    </ol>

    <h2>Real Examples</h2>
    <div class="example-box">
      <div class="ex-label">Low Crash Probability</div>
      <p>{_tk_link(btc)} has a crash probability of {_tk_crash(btc)}. With the deepest liquidity in crypto, massive holder base, strong ecosystem resilience, and decades of track record, its structural foundation is the most robust in the market.</p>
    </div>
    <div class="example-box">
      <div class="ex-label">{'Elevated Crash Probability' if warned else 'Moderate Example'}</div>
      <p>{_tk_link(warned) + ' has a crash probability of ' + _tk_crash(warned) + '. ' if warned else ''}{('Its risk level is ' + warned.get('risk_level', 'WARNING') + ' with a Distance-to-Default of ' + _tk_ndd(warned) + '.') if warned else 'Tokens with elevated crash probability show weakening structural signals.'} These are not guaranteed to crash, but the structural stress is measurable and significant.</p>
    </div>

    <h2>What the Numbers Mean in Practice</h2>
    <ul>
      <li><strong>&lt;5% crash probability:</strong> Structurally very sound. Major tokens with deep liquidity.</li>
      <li><strong>5-15%:</strong> Moderate risk. Some structural pressure but no active warnings.</li>
      <li><strong>15-30%:</strong> Elevated risk. Active stress signals. Worth monitoring on <a href="/crash-watch">Crash Watch</a>.</li>
      <li><strong>30-50%:</strong> High risk. Multiple structural weaknesses detected. Caution strongly advised.</li>
      <li><strong>&gt;50%:</strong> Severe risk. Structural collapse may be underway. Check the token's DtD — if below 1.0, historical precedent is 100% failure.</li>
    </ul>

    <h2>The Track Record</h2>
    <p>ZARQ's crash model has been tested against 113 historical token collapses. Results: 100% recall (every collapse was detected in advance), 98% precision (very few false alarms), and a 22-month average lead time. The 1st target (-30% decline) was hit in 92% of cases. The 2nd target (-50%) was hit in 65%.</p>
    <p>Full results at <a href="/track-record">ZARQ Track Record</a> and independently verified at <a href="https://github.com/kbanilsson-pixel/track-record" style="color:var(--warm)">github.com/kbanilsson-pixel/track-record</a>.</p>

    <h2>How to Use Crash Probability</h2>
    <p>Don't use crash probability as a trading signal. Use it as a <strong>risk filter</strong>. Before buying any token, check its crash probability at <code>zarq.ai/v1/check/{{token}}</code>. If it's above 30%, understand that you're taking on significant structural risk. If it's above 50%, you should have a very specific reason for holding it. Combine with the <a href="/learn/distance-to-default-explained">Distance-to-Default</a> score for a complete risk picture.</p>
"""

    elif slug == "distance-to-default-explained":
        return f"""
    <h2>The Most Important Number You've Never Heard Of</h2>
    <p>Distance-to-Default (DtD) is the single most predictive metric for identifying tokens at risk of structural collapse. Adapted from Robert Merton's Nobel Prize-winning structural credit model — originally used to predict corporate bankruptcies — DtD measures how far a token is from its "point of no return."</p>
    <p>In traditional finance, Merton's model asks: how far is a company's asset value from the point where it can no longer cover its debts? In crypto, ZARQ adapts this to ask: <strong>how far is a token's structural health from the point where collapse becomes inevitable?</strong></p>

    <h2>The Scale</h2>
    <ul>
      <li><strong>DtD &gt; 4.0 — Very Strong:</strong> Far from any distress threshold. The token has robust structural foundations. Example: {_tk_link(btc)} at DtD {_tk_ndd(btc)}.</li>
      <li><strong>DtD 3.0-4.0 — Healthy:</strong> Comfortable distance from default. No immediate concerns.</li>
      <li><strong>DtD 2.0-3.0 — Moderate:</strong> Some structural pressure is present. Worth monitoring. Example: {_tk_link(eth)} at DtD {_tk_ndd(eth)}.</li>
      <li><strong>DtD 1.0-2.0 — Elevated Risk:</strong> Approaching the distress zone. Active structural stress. These tokens appear on ZARQ's <a href="/crash-watch">Crash Watch</a>.</li>
      <li><strong>DtD &lt; 1.0 — Critical:</strong> Below the default threshold. Historically, <strong>100% of tokens that reach this level have experienced terminal failure</strong>. This is the single most powerful predictive signal in ZARQ's arsenal.</li>
    </ul>

    <h2>The 7 Components</h2>
    <p>DtD is not a single number plucked from the air — it's a weighted composite of 7 quantitative signals, each measuring a different dimension of structural health:</p>
    <ol>
      <li><strong>Ecosystem Resilience (30%)</strong> — the largest weight. How well does the token maintain value during market-wide stress? Tokens that consistently drop more than peers during selloffs have deteriorating ecosystem support.</li>
      <li><strong>Contagion Exposure (25%)</strong> — interconnection with other at-risk tokens. When one domino falls, which tokens get hit? This signal detected the cascading failures during the 2022 LUNA/3AC/FTX contagion wave.</li>
      <li><strong>Relative Weakness (15%)</strong> — persistent underperformance vs peers in the same category. A token that consistently lags its competitors is often losing the competitive battle for ecosystem relevance.</li>
      <li><strong>Liquidity Depth (10%)</strong> — how much sell pressure the market can absorb without significant price impact.</li>
      <li><strong>Fundamental Activity (10%)</strong> — on-chain activity, developer commits, transaction volume.</li>
      <li><strong>Holder Concentration (5%)</strong> — whale dominance. When 80% of supply is held by 10 wallets, one exit can trigger a cascade.</li>
      <li><strong>Structural Risk (5%)</strong> — detected anomalies in price microstructure that historically precede collapses.</li>
    </ol>

    <h2>Why DtD Works Better Than Price Analysis</h2>
    <p>Price-based analysis (technical analysis, moving averages, RSI) can only tell you what already happened. DtD measures the <strong>structural health underneath the price</strong>. A token can have a stable price while its DtD is deteriorating — like a building with invisible foundation cracks. By the time the price moves, it's often too late.</p>
    <p>ZARQ's testing shows that DtD typically begins deteriorating 12-22 months <strong>before</strong> the final price collapse. This lead time is what makes it useful: it gives you months, not hours, to adjust your position.</p>

    <div class="example-box">
      <div class="ex-label">Historical Pattern</div>
      <p>LUNA's DtD began declining in early 2021, over a year before its collapse in May 2022. The price was at all-time highs while the structural model was signaling growing fragility. By the time DtD breached 1.0, collapse was essentially inevitable. ZARQ's model detected all 113 historical collapses using this pattern.</p>
    </div>

    <h2>How to Monitor DtD</h2>
    <p>Every <a href="/tokens">token rating page</a> shows the current DtD alongside the trust score and crash probability. For a portfolio view, check the <a href="/crash-watch">Crash Watch</a> dashboard, which sorts all monitored tokens by structural severity. The API endpoint <code>GET zarq.ai/v1/check/{{token}}</code> includes DtD in the response.</p>
    <p>Key threshold to remember: <strong>DtD below 1.0 = 100% historical failure rate.</strong> There are no known exceptions.</p>
"""

    elif slug == "crypto-trust-scores":
        total_count = len(tokens)
        aa_count = sum(1 for t in tokens if t.get("rating", "").startswith("Aa"))
        a_count = sum(1 for t in tokens if t.get("rating", "").startswith("A") and not t.get("rating", "").startswith("Aa"))
        baa_count = sum(1 for t in tokens if t.get("rating", "").startswith("Baa"))
        spec_count = sum(1 for t in tokens if t.get("rating", "").startswith("Ba") or t.get("rating", "").startswith("B") and not t.get("rating", "").startswith("Baa"))

        return f"""
    <h2>Why Crypto Needs a Rating System</h2>
    <p>Traditional finance has Moody's, S&P, and Fitch. These agencies rate bonds and companies on standardized scales, so investors can quickly assess risk without doing deep analysis on every security. Crypto has had nothing equivalent — until now.</p>
    <p>ZARQ rates {total_count} tokens on a Moody's-style scale from Aaa (highest quality) to D (default). Every rating is backed by quantitative analysis across 5 pillars, updated daily, and available through a free API. No opinions, no conflicts of interest — just math.</p>

    <h2>The Rating Scale</h2>
    <p>ZARQ's scale mirrors Moody's corporate bond ratings. The key dividing line is between <strong>investment grade</strong> (Baa3 and above) and <strong>speculative grade</strong> (Ba1 and below).</p>
    <ul>
      <li><strong>Aaa</strong> — Highest quality, minimal risk. Currently {aa_count} tokens. Examples: stablecoins with deep reserves, commodity-backed tokens.</li>
      <li><strong>A1 to A3</strong> — High quality, low risk. Currently {a_count} tokens. Most major Layer 1 blockchains fall here, including {_tk_link(btc)} and {_tk_link(eth)}.</li>
      <li><strong>Baa1 to Baa3</strong> — Medium grade, moderate risk. Currently {baa_count} tokens. Investment grade but with some vulnerability to adverse conditions.</li>
      <li><strong>Ba1 and below</strong> — Speculative grade. Elevated risk of significant drawdown. These tokens require close monitoring.</li>
    </ul>

    <h2>The 5 Pillars</h2>
    <p>Every trust score is computed from five quantitative pillars, each measuring a different dimension of quality:</p>

    <h3>Pillar 1: Ecosystem Strength (Market Fundamentals)</h3>
    <p>Market cap rank, trading volume stability, exchange presence, and overall market position. Tokens with deep, stable ecosystems score higher. This pillar measures whether the token has genuine economic activity or is just speculative volume.</p>

    <h3>Pillar 2: Contagion Risk (Correlation Analysis)</h3>
    <p>How correlated is this token with other at-risk assets? Tokens that move independently during market stress have lower contagion risk. This pillar helps identify tokens that would survive a market-wide crash vs. those that would amplify it.</p>

    <h3>Pillar 3: Historical Resilience (Drawdown Recovery)</h3>
    <p>How well has the token recovered from past crashes? Maximum drawdown, recovery time, and annualized volatility. Tokens that bounce back quickly from market shocks demonstrate structural resilience. Tokens that never recover from drawdowns signal deteriorating fundamentals.</p>

    <h3>Pillar 4: Fundamental Quality (Long-term Signals)</h3>
    <p>Token age, price consistency over time, long-term trend strength, and fundamental value indicators. Young tokens with volatile histories score lower. Tokens with multi-year track records and consistent development score higher.</p>

    <h3>Pillar 5: Rug Pull Risk (Anomaly Detection)</h3>
    <p>Anomaly detection screening for patterns associated with rug pulls: extreme price movements, suspicious volume spikes, dump patterns, and other statistical anomalies. This pillar catches the specific risks unique to crypto — intentional exit scams and coordinated dumps.</p>

    <div class="example-box">
      <div class="ex-label">Pillar Breakdown Example</div>
      <p>{_tk_link(btc)} ({btc.get('rating', 'N/A')}, score {_tk_score(btc)}): Strong across all five pillars, with ecosystem strength and historical resilience as standout signals. Compare to {_tk_link(low)} ({low.get('rating', 'N/A')}, score {_tk_score(low)}), which scores significantly lower on ecosystem strength and resilience.</p>
    </div>

    <h2>How Scores Map to Ratings</h2>
    <p>Trust scores (0-100) are mapped to ratings using calibrated thresholds derived from the historical distribution of token outcomes. Tokens above ~80 earn A-tier ratings. Tokens in the 60-80 range fall into Baa territory (investment grade, but with moderate risk). Below 60 enters speculative territory.</p>
    <p>The distribution is intentionally top-heavy: only tokens that demonstrate quality across all five pillars earn the highest ratings. There is no grade inflation.</p>

    <h2>Using Trust Scores</h2>
    <p>Browse all ratings on the <a href="/tokens">Token Ratings</a> page. For any individual token, the API provides instant access: <code>GET zarq.ai/v1/check/{{token}}</code>. Combine the trust score with <a href="/learn/understanding-crash-probability">crash probability</a> and <a href="/learn/distance-to-default-explained">Distance-to-Default</a> for a complete risk picture.</p>
    <p>For portfolio risk, use the <a href="/crash-watch">Crash Watch</a> to monitor all your holdings in one view, or the <a href="/yield-risk">Yield Risk Monitor</a> to assess DeFi positions.</p>
"""

    return "<p>Article content is being generated.</p>"


def _render_learn_hub():
    total = _get_total_tokens()

    article_cards = ""
    itemlist_items = []
    for i, art in enumerate(ARTICLES):
        article_cards += (
            f'    <a href="/learn/{art["slug"]}" class="article-card">\n'
            f'      <div class="card-num">Guide {i + 1}</div>\n'
            f'      <div class="card-title">{_esc(art["title"])}</div>\n'
            f'      <div class="card-desc">{_esc(art["subtitle"])}</div>\n'
            f'      <div class="card-meta">Free &middot; {_esc(art["short_title"])}</div>\n'
            f'    </a>\n'
        )
        itemlist_items.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": f"https://zarq.ai/learn/{art['slug']}",
            "name": art["title"],
        })

    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Crypto Risk Education — ZARQ Learn",
        "description": f"Educational guides on crypto risk assessment with real data from {total} rated tokens.",
        "numberOfItems": len(ARTICLES),
        "itemListElement": itemlist_items,
    })

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Learn"},
        ]
    })

    html = (TEMPLATE_DIR / "learn_hub.html").read_text()
    replacements = {
        "{{ zarq_css }}": ZARQ_CSS,
        "{{ zarq_nav }}": ZARQ_NAV,
        "{{ zarq_footer }}": ZARQ_FOOTER,
        "{{ total_tokens }}": str(total),
        "{{ article_cards }}": article_cards,
        "{{ itemlist_jsonld }}": itemlist_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
    }
    for k, v in replacements.items():
        html = html.replace(k, str(v))
    return html


def _render_learn_article(slug):
    art = next((a for a in ARTICLES if a["slug"] == slug), None)
    if not art:
        return None

    tokens = _get_example_tokens()
    total = len(tokens)

    body = _build_article_body(slug, tokens)

    # Build FAQ based on article
    faq_map = {
        "how-to-check-if-crypto-is-safe": [
            ("What are the 7 risk signals for crypto?", f"ZARQ uses 7 quantitative signals: Trust Score (0-100 composite), Rating (Aaa-D Moody's scale), Crash Probability (likelihood of >50% drawdown), Distance-to-Default (structural health measure), Structural Weakness Flag (binary collapse warning), Risk Level (SAFE/WATCH/WARNING/CRITICAL), and Contagion Exposure (interconnection risk). Together they provide a complete risk picture for each of {total} rated tokens."),
            ("How do I DYOR in crypto properly?", f"True DYOR means checking quantitative risk signals, not just reading whitepapers or Twitter. Start with ZARQ's quick check (zarq.ai/v1/check/{{token}}) to get the trust score, crash probability, and Distance-to-Default. Then review the full token page at zarq.ai/token/{{slug}} for the 5-pillar breakdown. Focus on convergence: when multiple signals point in the same direction, that's the real signal."),
            ("Is there a free crypto risk checker?", f"Yes. ZARQ's API is free during beta with no authentication required. The quick check endpoint (GET zarq.ai/v1/check/{{token}}) returns a verdict (SAFE/WARNING/CRITICAL), trust score, crash probability, and Distance-to-Default for any of {total} rated tokens. Rate limit is 5,000 requests per day."),
        ],
        "defi-risk-checklist": [
            ("What makes a DeFi yield safe?", "Safe DeFi yields have three characteristics: base APY from real economic activity (lending interest or trading fees), no impermanent loss exposure, and high TVL on an audited protocol. If the yield primarily comes from reward token emissions rather than organic activity, it's likely unsustainable."),
            ("How do I check if a DeFi protocol is safe?", f"Check the protocol on ZARQ's Yield Risk Monitor (zarq.ai/yield-risk) for color-coded risk assessment. Then verify: (1) the underlying token's risk rating on zarq.ai/tokens, (2) whether the yield is base APY or reward-driven, (3) audit history, (4) TVL stability over time, and (5) the protocol's age and track record."),
            ("What APY is too good to be true?", "Generally, base APY above 20% on stablecoins or above 50% on volatile tokens is suspicious. If the total APY is above 100%, it's almost certainly driven by unsustainable reward emissions. Check the base vs reward APY split on ZARQ's yield monitor — if reward APY exceeds base APY, the yield will likely decrease significantly."),
        ],
        "understanding-crash-probability": [
            ("What does crash probability mean in crypto?", f"Crash probability is the model-estimated likelihood of a >50% price decline, based on 7 quantitative structural signals. A 30% crash probability means roughly a 1-in-3 chance of severe decline. It's a risk measure, not a price prediction. ZARQ calculates this for {total} tokens, updated daily."),
            ("How accurate is crypto crash prediction?", "ZARQ's crash model has achieved 100% recall (detected all 113 historical collapses) and 98% precision (very few false alarms) in out-of-sample testing. The average detection lead time is 22 months. The 1st target (-30%) hit rate is 92%, 2nd target (-50%) is 65%. Track record independently verified on GitHub."),
            ("What crash probability is dangerous?", "Below 5% is structurally sound. 5-15% is moderate. 15-30% is elevated — the token is on ZARQ's Crash Watch. 30-50% is high risk with active structural weaknesses. Above 50% is severe — check the Distance-to-Default, and if it's below 1.0, historical precedent shows 100% failure rate."),
        ],
        "distance-to-default-explained": [
            ("What is Distance-to-Default in crypto?", "Distance-to-Default (DtD) measures how far a token is from structural collapse, adapted from Robert Merton's Nobel Prize-winning model for predicting corporate defaults. The scale runs from 0 (at default threshold) to 5+ (very healthy). DtD below 1.0 means the token has breached the distress threshold — historically, 100% of tokens reaching this level have failed."),
            ("What DtD score is dangerous?", "DtD above 4.0 is very strong. 3.0-4.0 is healthy. 2.0-3.0 is moderate with some pressure. 1.0-2.0 is elevated risk — these tokens appear on ZARQ's Crash Watch. Below 1.0 is critical: every token that has reached this level has experienced terminal failure. The key threshold is 1.0."),
            ("How is DtD different from price analysis?", "Price analysis (technical analysis, RSI, moving averages) tells you what already happened. DtD measures structural health underneath the price. A token can have a stable price while its DtD deteriorates — like a building with invisible foundation cracks. DtD typically begins declining 12-22 months before final price collapse, providing actionable lead time."),
        ],
        "crypto-trust-scores": [
            ("How does ZARQ rate crypto tokens?", f"ZARQ rates {total} tokens on a Moody's-style scale (Aaa to D) using 5 quantitative pillars: Ecosystem Strength (market fundamentals), Contagion Risk (correlation analysis), Historical Resilience (drawdown recovery), Fundamental Quality (long-term signals), and Rug Pull Risk (anomaly detection). Scores 0-100 map to ratings, with Baa3+ being investment grade."),
            ("What is a good crypto trust score?", f"Scores above 80 earn A-tier ratings (high quality, low risk). 60-80 is Baa territory (investment grade but moderate risk). Below 60 is speculative grade with elevated risk. The average trust score across {total} rated tokens reflects the overall market quality."),
            ("Are ZARQ crypto ratings independent?", "Yes. ZARQ's ratings are purely quantitative — computed from 5 pillars using publicly observable data. There are no paid placements, no conflicts of interest, and no manual overrides. Every rating is hash-chained for tamper evidence and updated daily. The methodology is fully documented at zarq.ai/methodology."),
        ],
    }

    faq_items = faq_map.get(slug, [])
    faq_html = ""
    faq_jsonld_items = []
    for q, a in faq_items:
        faq_html += (
            f'    <div class="faq-item">\n'
            f'      <div class="faq-q">{_esc(q)}</div>\n'
            f'      <div class="faq-a">{a}</div>\n'
            f'    </div>\n'
        )
        faq_jsonld_items.append({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a}
        })

    # AI summary per article
    ai_summaries = {
        "how-to-check-if-crypto-is-safe": f"This guide explains 7 quantitative risk signals ZARQ uses to assess cryptocurrency safety: Trust Score, Rating, Crash Probability, Distance-to-Default, Structural Weakness, Risk Level, and Contagion Exposure. Includes real examples from {total} rated tokens.",
        "defi-risk-checklist": f"A practical 7-point DeFi risk checklist covering yield source analysis, base vs reward APY, impermanent loss, TVL stability, underlying token risk, audit history, and protocol age. Links to ZARQ's live Yield Risk Monitor and Crash Watch.",
        "understanding-crash-probability": f"Crash probability explained for beginners: what a 32% crash probability means, how it's calculated from 7 signals, real token examples, and the track record (100% recall, 98% precision on 113 historical collapses).",
        "distance-to-default-explained": f"Distance-to-Default (DtD) is ZARQ's most predictive metric, adapted from Merton's structural credit model. DtD below 1.0 has a 100% historical failure rate. Explains the 7 components and how to monitor DtD for any token.",
        "crypto-trust-scores": f"How ZARQ rates {total} tokens on a Moody's-style scale (Aaa-D) using 5 quantitative pillars. Explains the rating scale, pillar methodology, and how to use trust scores for portfolio decisions.",
    }

    # Related articles
    related_html = ""
    other_articles = [a for a in ARTICLES if a["slug"] != slug][:4]
    if other_articles:
        cards = ""
        for a in other_articles:
            cards += (
                f'    <a href="/learn/{a["slug"]}" class="related-card">\n'
                f'      <div class="rc-title">{_esc(a["short_title"])}</div>\n'
                f'      <div class="rc-desc">{_esc(a["subtitle"][:100])}</div>\n'
                f'    </a>\n'
            )
        related_html = (
            f'  <div class="related-articles">\n'
            f'    <h2 class="section-title">Related Guides</h2>\n'
            f'    <div class="related-grid">\n{cards}    </div>\n'
            f'  </div>\n'
        )

    today = date.today().isoformat()

    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": art["title"],
        "description": art["meta_description"],
        "url": f"https://zarq.ai/learn/{slug}",
        "publisher": {"@type": "Organization", "name": "ZARQ", "url": "https://zarq.ai"},
        "dateModified": today,
    })

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_jsonld_items
    })

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ZARQ", "item": "https://zarq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Learn", "item": "https://zarq.ai/learn"},
            {"@type": "ListItem", "position": 3, "name": art["short_title"]},
        ]
    })

    html = (TEMPLATE_DIR / "learn_article.html").read_text()
    replacements = {
        "{{ zarq_css }}": ZARQ_CSS,
        "{{ zarq_nav }}": ZARQ_NAV,
        "{{ zarq_footer }}": ZARQ_FOOTER,
        "{{ title }}": _esc(art["title"]),
        "{{ short_title }}": _esc(art["short_title"]),
        "{{ subtitle }}": _esc(art["subtitle"]),
        "{{ slug }}": _esc(slug),
        "{{ meta_description }}": _esc(art["meta_description"]),
        "{{ og_description }}": _esc(art["og_description"]),
        "{{ ai_summary }}": ai_summaries.get(slug, ""),
        "{{ article_body }}": body,
        "{{ faq_html }}": faq_html,
        "{{ related_section }}": related_html,
        "{{ webpage_jsonld }}": webpage_jsonld,
        "{{ faq_jsonld }}": faq_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
    }
    for k, v in replacements.items():
        html = html.replace(k, str(v))
    return html


# ─── Mount all routes ────────────────────────────────────────────────

_page_cache = {}
_CACHE_TTL = 1800
_CACHE_MAX = 20

def mount_zarq_content_pages(app):
    """Mount /crash-watch, /yield-risk, /learn, and /learn/{slug} routes."""
    import time

    @app.get("/crash-watch", response_class=HTMLResponse)
    async def crash_watch_page():
        now = time.time()
        if "crash-watch" in _page_cache:
            html, ts = _page_cache["crash-watch"]
            if now - ts < _CACHE_TTL:
                return HTMLResponse(content=html)
        try:
            html = _render_crash_watch()
            _page_cache["crash-watch"] = (html, now)
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering crash-watch: {e}", exc_info=True)
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    # /yield-risk is handled by zarq_yield_page.py (which calls _render_yield_risk from here)

    @app.get("/learn", response_class=HTMLResponse)
    async def learn_hub_page():
        now = time.time()
        if "learn-hub" in _page_cache:
            html, ts = _page_cache["learn-hub"]
            if now - ts < _CACHE_TTL:
                return HTMLResponse(content=html)
        try:
            html = _render_learn_hub()
            _page_cache["learn-hub"] = (html, now)
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering learn hub: {e}", exc_info=True)
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/learn/{slug}", response_class=HTMLResponse)
    async def learn_article_page(slug: str):
        valid_slugs = {a["slug"] for a in ARTICLES}
        if slug not in valid_slugs:
            return HTMLResponse(status_code=404, content="<h1>Article not found</h1>")

        now = time.time()
        cache_key = f"learn-{slug}"
        if cache_key in _page_cache:
            html, ts = _page_cache[cache_key]
            if now - ts < _CACHE_TTL:
                return HTMLResponse(content=html)
        try:
            html = _render_learn_article(slug)
            if html is None:
                return HTMLResponse(status_code=404, content="<h1>Article not found</h1>")
            if len(_page_cache) < _CACHE_MAX:
                _page_cache[cache_key] = (html, now)
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering learn/{slug}: {e}", exc_info=True)
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    # Sitemap for all new pages
    @app.get("/sitemap-zarq-content.xml", response_class=Response)
    async def sitemap_zarq_content():
        today = date.today().isoformat()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for page in ["/crash-watch", "/yield-risk", "/learn"]:
            xml += f'  <url>\n    <loc>https://zarq.ai{page}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.9</priority>\n  </url>\n'
        for art in ARTICLES:
            xml += f'  <url>\n    <loc>https://zarq.ai/learn/{art["slug"]}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n'
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")

    logger.info("Mounted ZARQ content pages: /crash-watch, /yield-risk, /learn, 5 articles, sitemap")
