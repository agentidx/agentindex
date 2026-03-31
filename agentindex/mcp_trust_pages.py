"""
Nerq MCP Server Trust Pages
=============================
Trust-rated MCP server pages at /mcp/{slug} and hub at /mcp.
Captures "best MCP servers", "[server] MCP server", "MCP server for [X]" traffic.

Usage in discovery.py:
    from agentindex.mcp_trust_pages import mount_mcp_trust_pages
    mount_mcp_trust_pages(app)
"""

import json
import logging
import time
from pathlib import Path
from datetime import date

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER
from agentindex.mcp_popularity import get_mcp_popularity_cached

logger = logging.getLogger("nerq.mcp_trust")

TEMPLATE_DIR = Path(__file__).parent / "templates"
SLUGS_PATH = Path(__file__).parent / "mcp_server_slugs.json"

_slug_map = {}
_slug_list = []
_page_cache = {}
_CACHE_TTL = 3600
_CACHE_MAX = 600


def _load_slugs():
    global _slug_map, _slug_list
    if _slug_map:
        return
    try:
        with open(SLUGS_PATH) as f:
            _slug_list = json.load(f)
        _slug_map = {s["slug"]: s for s in _slug_list}
        logger.info(f"Loaded {len(_slug_map)} MCP server slugs")
    except Exception as e:
        logger.error(f"Failed to load MCP server slugs: {e}")


def _esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _grade_pill(grade):
    if not grade:
        return "pill-gray"
    g = grade.upper()
    if g.startswith("A"):
        return "pill-green"
    if g.startswith("B"):
        return "pill-yellow"
    return "pill-red"


_COLS = """
    name,
    COALESCE(trust_score_v2, trust_score) as trust_score,
    trust_grade,
    category,
    description,
    source_url,
    source,
    stars,
    author,
    is_verified,
    frameworks,
    protocols,
    capabilities,
    compliance_score,
    eu_risk_class,
    documentation_score,
    activity_score,
    security_score,
    popularity_score
"""


def _lookup_server(name):
    session = get_session()
    try:
        clean = name.replace("-", " ").replace("_", " ")
        row = session.execute(text(f"""
            SELECT {_COLS} FROM (
                SELECT *, 1 AS _rank FROM agents
                WHERE LOWER(name) = LOWER(:name) AND is_active = true AND agent_type = 'mcp_server'
              UNION ALL
                SELECT *, 2 AS _rank FROM agents
                WHERE lower(name::text) LIKE lower(:suffix) AND is_active = true AND agent_type = 'mcp_server'
              UNION ALL
                SELECT *, 3 AS _rank FROM agents
                WHERE lower(name::text) LIKE lower(:pattern) AND is_active = true AND agent_type = 'mcp_server'
            ) sub
            ORDER BY _rank, COALESCE(trust_score_v2, trust_score) DESC NULLS LAST,
                     stars DESC NULLS LAST
            LIMIT 1
        """), {"name": name, "clean": clean, "suffix": f"%/{name}", "pattern": f"%{name}%"}).fetchone()
        return dict(row._mapping) if row else None
    finally:
        session.close()


def _get_alternatives(category, current_name, current_score, limit=5):
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                   trust_grade, category, source
            FROM agents
            WHERE is_active = true AND agent_type = 'mcp_server'
              AND category = :cat
              AND LOWER(name) != LOWER(:name)
              AND COALESCE(trust_score_v2, trust_score) >= :score
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC
            LIMIT :lim
        """), {"cat": category, "name": current_name, "score": current_score, "lim": limit}).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        session.close()


def _make_slug(name):
    slug = name.lower().strip()
    for ch in ['/', '\\', '(', ')', '[', ']', '{', '}', ':', ';', ',', '!', '?',
               '@', '#', '$', '%', '^', '&', '*', '=', '+', '|', '<', '>', '~', '`', "'", '"']:
        slug = slug.replace(ch, '')
    slug = slug.replace(' ', '-').replace('_', '-').replace('.', '-')
    while '--' in slug:
        slug = slug.replace('--', '-')
    return slug.strip('-')


def _trust_assessment(name, score):
    n = _esc(name)
    if score >= 85:
        return f"Highly Trusted &mdash; {n} is among the top-rated MCP servers with excellent trust signals across security, compliance, and maintenance. It has been independently assessed by Nerq and shows consistently strong quality indicators."
    if score >= 70:
        return f"Trusted &mdash; {n} demonstrates solid trust signals and meets the Nerq Verified threshold. It shows good security practices, active maintenance, and healthy community adoption."
    if score >= 55:
        return f"Moderate &mdash; {n} shows mixed trust signals. Some areas are strong while others could be improved. Review the full KYA report before integrating into production."
    if score >= 40:
        return f"Caution &mdash; {n} has below-average trust signals. There may be concerns around maintenance, security, or adoption. Conduct additional due diligence."
    return f"Low Trust &mdash; {n} has significant trust concerns. Thorough investigation recommended before use."


def _assessment_short(score):
    if score >= 85:
        return "Highly trusted."
    if score >= 70:
        return "Trusted — strong signals."
    if score >= 55:
        return "Moderate — mixed signals."
    if score >= 40:
        return "Caution — below average."
    return "Low trust — significant concerns."


def _fmt(val):
    if val is None:
        return "N/A"
    return f"{val:.0f}"


def _check_safe_page_exists(name):
    """Check if this MCP server also has a /safe/ page."""
    from agentindex.agent_safety_pages import _load_slugs as _load_safe, _slug_map as _safe_map
    _load_safe()
    slug = _make_slug(name)
    return slug if slug in _safe_map else None


def _render_server_page(slug, server_info):
    name = server_info.get("name", slug)
    srv = _lookup_server(name)
    if not srv:
        return None

    name = srv.get("name") or name
    score = float(srv.get("trust_score") or 0)
    score_str = f"{score:.1f}"
    grade = srv.get("trust_grade") or "N/A"
    category = srv.get("category") or "uncategorized"
    source = srv.get("source") or "unknown"
    source_url = srv.get("source_url") or ""
    stars = srv.get("stars") or 0
    author = srv.get("author") or "Unknown"
    description = srv.get("description") or ""
    is_verified = srv.get("is_verified") or (score >= 70)
    frameworks = srv.get("frameworks") or []
    capabilities = srv.get("capabilities") or []
    if isinstance(capabilities, str):
        try:
            capabilities = json.loads(capabilities)
        except:
            capabilities = []

    compliance_score = srv.get("compliance_score")
    eu_risk_class = srv.get("eu_risk_class") or ""
    doc_score = srv.get("documentation_score")
    activity_score = srv.get("activity_score")
    security_score = srv.get("security_score")
    popularity_score = srv.get("popularity_score")

    assessment = _trust_assessment(name, score)
    short = _assessment_short(score)
    pill_class = _grade_pill(grade)

    # Find strongest signal for AI summary
    sig_pairs = []
    if security_score is not None:
        sig_pairs.append(("security", security_score))
    if compliance_score is not None:
        sig_pairs.append(("compliance", compliance_score))
    if activity_score is not None:
        sig_pairs.append(("maintenance", activity_score))
    if doc_score is not None:
        sig_pairs.append(("documentation", doc_score))
    if popularity_score is not None:
        sig_pairs.append(("popularity", popularity_score))
    best_sig_text = ""
    if sig_pairs:
        best = max(sig_pairs, key=lambda x: x[1])
        best_sig_text = f"Its strongest signal is {best[0]} ({best[1]:.0f}/100). "

    caps_count = len(capabilities) if isinstance(capabilities, list) else 0
    caps_text = f"It lists {caps_count} capabilities. " if caps_count > 0 else ""

    # AI summary — citation-optimized for ChatGPT/Claude/Perplexity
    _pop_rank_text = ""
    try:
        ranks, details = get_mcp_popularity_cached()
        _pd = details.get(slug)
        if _pd:
            _pop_rank_text = f" Ranked #{_pd['rank']} of {_pd['total']} MCP servers on Nerq."
    except Exception:
        pass
    ai_summary = (
        f"{_esc(name)} is an MCP server with a Nerq Trust Score of {score_str}/100 ({_esc(grade)}).{_pop_rank_text} "
        f"{'Nerq Verified — recommended for production use.' if is_verified else 'Not yet Nerq Verified (requires 70+).'} "
        f"{best_sig_text}{caps_text}"
        f"Last verified: {date.today().isoformat()}."
    )

    # Signals grid
    signals = []
    if security_score is not None:
        signals.append(("Security", f"{security_score:.0f}", "Code quality, vulnerability exposure, and security practices."))
    if compliance_score is not None:
        signals.append(("Compliance", f"{compliance_score:.0f}", f"Regulatory alignment. EU AI Act risk class: {_esc(eu_risk_class) or 'N/A'}."))
    if activity_score is not None:
        signals.append(("Maintenance", f"{activity_score:.0f}", "Update frequency, issue responsiveness, active development."))
    if doc_score is not None:
        signals.append(("Documentation", f"{doc_score:.0f}", "README quality, API docs, usage examples."))
    if popularity_score is not None:
        signals.append(("Popularity", f"{popularity_score:.0f}", f"Community adoption. {stars:,} stars on {_esc(source)}."))
    if not signals:
        signals.append(("Overall Trust", score_str, "Composite score across all trust dimensions."))

    signals_html = ""
    for sig_name, sig_val, sig_desc in signals:
        signals_html += (
            f'<div class="signal-card">'
            f'<div class="sig-name">{sig_name}</div>'
            f'<div class="sig-val">{sig_val}</div>'
            f'<div class="sig-desc">{sig_desc}</div>'
            f'</div>'
        )

    # Capabilities section
    capabilities_section = ""
    if capabilities and isinstance(capabilities, list):
        items = "".join(f"<li>{_esc(str(c))}</li>" for c in capabilities[:10])
        capabilities_section = (
            f'<section><h2>Capabilities</h2>'
            f'<ul class="caps-list">{items}</ul></section>'
        )

    # Verified badge
    verified_badge = '<span class="pill pill-green" style="font-size:11px">verified</span>' if is_verified else ""

    # Source link
    source_link = f'<a href="{_esc(source_url)}">{_esc(source_url)}</a>' if source_url else "N/A"

    # Frameworks row
    frameworks_row = ""
    if frameworks:
        fw_html = " &middot; ".join(_esc(f) for f in frameworks[:5])
        frameworks_row = f'<tr><td style="color:#6b7280">Frameworks</td><td>{fw_html}</td></tr>'

    # Alternatives
    alternatives = _get_alternatives(category, name, score)
    alternatives_section = ""
    if alternatives:
        cards = ""
        for alt in alternatives:
            alt_slug = _make_slug(alt["name"])
            alt_score = alt.get("trust_score") or 0
            cards += (
                f'<a href="/mcp/{_esc(alt_slug)}" class="alt-card">'
                f'<div class="alt-name">{_esc(alt["name"])}</div>'
                f'<div class="alt-score">{alt_score:.1f}/100 &middot; {_esc(alt.get("trust_grade", ""))}</div>'
                f'<div class="alt-cat">{_esc(alt.get("source", ""))}</div>'
                f'</a>'
            )
        alternatives_section = (
            f'<section><h2>Higher-Rated MCP Servers in {_esc(category)}</h2>'
            f'<div class="alt-grid">{cards}</div></section>'
        )

    # Popularity ranking
    popularity_rank_html = ""
    try:
        ranks, details = get_mcp_popularity_cached()
        pop_detail = details.get(slug)
        if pop_detail:
            pop_rank = pop_detail["rank"]
            pop_total = pop_detail["total"]
            popularity_rank_html = f'<tr><td style="color:#6b7280">Popularity</td><td>#{pop_rank} of {pop_total} MCP servers</td></tr>'
    except Exception as e:
        logger.warning(f"Failed to get popularity for {slug}: {e}")

    # Cross-link to /safe/ page if it exists
    safe_slug = _check_safe_page_exists(name)
    safe_link = ""
    if safe_slug:
        safe_link = f'<a href="/safe/{_esc(safe_slug)}" style="display:inline-block;padding:8px 20px;border:1px solid #e5e7eb;color:#6b7280;font-size:14px;font-weight:600;text-decoration:none">Safety Report</a>'

    # FAQ
    best_signal = max(signals, key=lambda x: float(x[1]) if x[1].replace('.', '').isdigit() else 0) if signals else ("Overall", score_str, "")
    alt_names = ", ".join(_esc(a["name"]) for a in alternatives[:3]) if alternatives else "none found"
    alt_scores_str = ", ".join(f'{a.get("trust_score", 0):.0f}' for a in alternatives[:3]) if alternatives else ""

    faq_items = [
        {
            "q": f"Is {name} MCP server safe to use?",
            "a": (
                f"{_esc(name)} has a Nerq Trust Score of {score_str}/100, earning a {_esc(grade)} grade. "
                f"{assessment.replace('&mdash;', '—')} "
                f"Its strongest signal is {best_signal[0].lower()} ({best_signal[1]}/100). "
                f"{'It is Nerq Verified, meeting the 70+ trust threshold.' if is_verified else 'It has not yet reached the Nerq Verified threshold of 70.'} "
                f"Always review the full KYA report before integrating any MCP server into production."
            ),
        },
        {
            "q": f"What is {name}'s trust score?",
            "a": (
                f"Nerq assigns {_esc(name)} a trust score of {score_str} out of 100, with a grade of {_esc(grade)}. "
                f"This score is computed from security, compliance, maintenance activity, documentation quality, "
                f"and community adoption ({stars:,} stars). "
                f"{'Compliance score: ' + str(round(compliance_score)) + '/100. ' if compliance_score else ''}"
                f"{'EU AI Act risk class: ' + _esc(eu_risk_class) + '. ' if eu_risk_class else ''}"
                f"Scores are updated daily based on the latest publicly available signals."
            ),
        },
        {
            "q": f"Are there higher-rated alternatives to {name}?",
            "a": (
                f"In the {_esc(category)} category, "
                f"{'higher-rated MCP servers include ' + alt_names + ' (scores: ' + alt_scores_str + ').' if alternatives else 'no higher-rated MCP servers were found — this is among the top-rated.'} "
                f"{_esc(name)} scores {score_str}/100. "
                f"When choosing between MCP servers, consider security ({_fmt(security_score)}), "
                f"maintenance ({_fmt(activity_score)}), and documentation ({_fmt(doc_score)}). "
                f"Use Nerq's KYA endpoint for detailed analysis."
            ),
        },
    ]

    faq_html = ""
    for item in faq_items:
        faq_html += (
            f'<div class="faq-item">'
            f'<div class="faq-q">{_esc(item["q"])}</div>'
            f'<div class="faq-a">{item["a"]}</div>'
            f'</div>\n'
        )

    # SEO
    title = f"{name} MCP Server — Trust Score {score_str}/100 — Nerq"
    meta_desc = (
        f"{name} MCP server has a Nerq Trust Score of {score_str}/100 ({grade}). "
        f"{short} Independent trust assessment with security, compliance, and ecosystem analysis."
    )
    og_desc = f"{name} — {grade} trust grade, {score_str}/100. Independent MCP server trust assessment by Nerq."

    # JSON-LD
    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": f"Is {name} MCP Server Safe? Trust Score {score_str}/100",
        "description": meta_desc,
        "url": f"https://nerq.ai/mcp/{slug}",
        "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
    })

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": item["q"],
             "acceptedAnswer": {"@type": "Answer", "text": item["a"].replace("&mdash;", "—")}}
            for item in faq_items
        ]
    })

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai"},
            {"@type": "ListItem", "position": 2, "name": "MCP Servers", "item": "https://nerq.ai/mcp"},
            {"@type": "ListItem", "position": 3, "name": name},
        ]
    })

    badge_md = f"[![Nerq Trust Score](https://nerq.ai/badge/{_esc(name)})](https://nerq.ai/mcp/{_esc(slug)})"

    # Render template
    html = (TEMPLATE_DIR / "mcp_server_page.html").read_text()
    replacements = {
        "{{ title }}": _esc(title),
        "{{ meta_description }}": _esc(meta_desc),
        "{{ og_description }}": _esc(og_desc),
        "{{ slug }}": _esc(slug),
        "{{ name }}": _esc(name),
        "{{ name_raw }}": _esc(name),
        "{{ score }}": score_str,
        "{{ grade }}": _esc(grade),
        "{{ grade_pill }}": pill_class,
        "{{ category }}": _esc(category),
        "{{ source }}": _esc(source),
        "{{ author }}": _esc(author),
        "{{ stars_fmt }}": f"{stars:,}",
        "{{ assessment }}": assessment,
        "{{ ai_summary }}": ai_summary,
        "{{ verified_badge }}": verified_badge,
        "{{ signals_html }}": signals_html,
        "{{ capabilities_section }}": capabilities_section,
        "{{ source_link }}": source_link,
        "{{ frameworks_row }}": frameworks_row,
        "{{ popularity_rank_row }}": popularity_rank_html,
        "{{ alternatives_section }}": alternatives_section,
        "{{ faq_html }}": faq_html,
        "{{ safe_link }}": safe_link,
        "{{ badge_markdown }}": _esc(badge_md),
        "{{ webpage_jsonld }}": webpage_jsonld,
        "{{ faq_jsonld }}": faq_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
        "{{ software_jsonld }}": json.dumps({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": name,
            "applicationCategory": "MCP Server",
            "applicationSubCategory": category,
            "description": description[:200] if description else f"{name} MCP server",
            "url": f"https://nerq.ai/mcp/{slug}",
            "author": {"@type": "Organization", "name": author},
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": score_str,
                "bestRating": "100",
                "worstRating": "0",
                "ratingCount": "1",
                "reviewCount": "1",
            },
            "review": {
                "@type": "Review",
                "author": {"@type": "Organization", "name": "Nerq"},
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": score_str,
                    "bestRating": "100",
                    "worstRating": "0",
                },
                "reviewBody": f"{name} MCP server receives a {grade} trust grade ({score_str}/100) from Nerq.",
            },
        }),
        "{{ nerq_css }}": NERQ_CSS,
        "{{ nerq_nav }}": NERQ_NAV,
        "{{ nerq_footer }}": NERQ_FOOTER,
    }
    for key, val in replacements.items():
        html = html.replace(key, str(val))
    return html


def _render_hub_page():
    _load_slugs()
    session = get_session()
    try:
        rows = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                   trust_grade, category, source, stars, is_verified
            FROM agents
            WHERE is_active = true AND agent_type = 'mcp_server'
              AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC, stars DESC NULLS LAST
            LIMIT 500
        """)).fetchall()
    finally:
        session.close()

    # Get popularity rankings for the hub
    try:
        pop_ranks, pop_details = get_mcp_popularity_cached()
    except Exception:
        pop_ranks, pop_details = {}, {}

    total = len(rows)
    verified_count = 0
    top_score = 0
    table_rows = ""
    itemlist_items = []

    for i, r in enumerate(rows):
        row = dict(r._mapping)
        name = row["name"] or ""
        slug = _make_slug(name)
        if not slug:
            continue
        score = float(row["trust_score"] or 0)
        grade = row["trust_grade"] or "N/A"
        category = row["category"] or "uncategorized"
        source = row["source"] or "unknown"
        stars = row["stars"] or 0
        is_verified = row["is_verified"] or (score >= 70)
        if is_verified:
            verified_count += 1
        if score > top_score:
            top_score = score

        verified_html = '<span class="verified-dot" title="Nerq Verified"></span>Yes' if is_verified else "No"
        verified_sort = "1" if is_verified else "0"
        pill = _grade_pill(grade)

        pop_rank = pop_ranks.get(slug, 9999)
        pop_total = pop_details.get(slug, {}).get("total", len(pop_ranks)) or len(pop_ranks)

        table_rows += (
            f'<tr>'
            f'<td><a href="/mcp/{_esc(slug)}">{_esc(name)}</a></td>'
            f'<td>{_esc(category)}</td>'
            f'<td data-sort="{score:.1f}" style="font-family:ui-monospace,monospace;font-size:13px">{score:.1f}</td>'
            f'<td><span class="pill {pill}">{_esc(grade)}</span></td>'
            f'<td data-sort="{verified_sort}">{verified_html}</td>'
            f'<td>{_esc(source)}</td>'
            f'<td data-sort="{stars}" style="font-family:ui-monospace,monospace;font-size:13px">{stars:,}</td>'
            f'<td data-sort="{pop_rank}" style="font-family:ui-monospace,monospace;font-size:13px">#{pop_rank}</td>'
            f'</tr>\n'
        )

        itemlist_items.append({
            "@type": "ListItem",
            "position": i + 1,
            "url": f"https://nerq.ai/mcp/{slug}",
            "name": f"{name} — {grade} ({score:.0f}/100)"
        })

    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"MCP Server Trust Ratings — {total} Servers Rated",
        "description": f"Independent trust ratings for {total} MCP servers by Nerq.",
        "numberOfItems": total,
        "itemListElement": itemlist_items
    })

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai"},
            {"@type": "ListItem", "position": 2, "name": "MCP Servers"},
        ]
    })

    html = (TEMPLATE_DIR / "mcp_server_hub.html").read_text()
    html = html.replace("{{ total }}", str(total))
    html = html.replace("{{ verified_count }}", str(verified_count))
    html = html.replace("{{ top_score }}", f"{top_score:.1f}")
    html = html.replace("{{ table_rows }}", table_rows)
    html = html.replace("{{ itemlist_jsonld }}", itemlist_jsonld)
    html = html.replace("{{ breadcrumb_jsonld }}", breadcrumb_jsonld)
    html = html.replace("{{ nerq_css }}", NERQ_CSS)
    html = html.replace("{{ nerq_nav }}", NERQ_NAV)
    html = html.replace("{{ nerq_footer }}", NERQ_FOOTER)
    return html


def mount_mcp_trust_pages(app):
    """Mount /mcp hub and /mcp/{slug} pages.
    IMPORTANT: /mcp/{slug} must not conflict with existing /mcp/sse and /mcp/message endpoints."""
    _load_slugs()

    # The hub replaces the old /mcp-servers redirect-style page
    @app.get("/mcp", response_class=HTMLResponse)
    async def mcp_trust_hub(request: Request):
        try:
            html = _render_hub_page()
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering MCP hub: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/mcp/{slug}", response_class=HTMLResponse)
    async def mcp_trust_page(slug: str, request: Request):
        # MCP protocol endpoints are handled by earlier routes (/mcp/sse, /mcp/messages)
        # This should not be reached for those slugs, but just in case:
        if slug in ("sse", "message", "messages"):
            return HTMLResponse(status_code=404, content="Not found")

        _load_slugs()
        server_info = _slug_map.get(slug, {})
        if not server_info:
            server_info = {"name": slug.replace("-", " ")}

        now = time.time()
        cache_key = slug
        if cache_key in _page_cache:
            html, ts = _page_cache[cache_key]
            if now - ts < _CACHE_TTL:
                return HTMLResponse(content=html)

        try:
            html = _render_server_page(slug, server_info)
            if html is None:
                try:
                    from agentindex.agent_safety_pages import _queue_for_crawling
                    _queue_for_crawling(slug, bot="404-route")
                except Exception:
                    pass
                return HTMLResponse(content=f"""<!DOCTYPE html><html><head>
<title>Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/static/nerq.css?v=13">
</head><body>
<h1>Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
            if len(_page_cache) < _CACHE_MAX:
                _page_cache[cache_key] = (html, now)
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering MCP page {slug}: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    @app.get("/sitemap-mcp.xml", response_class=Response)
    async def sitemap_mcp():
        _load_slugs()
        today = date.today().isoformat()
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        xml += f'  <url>\n    <loc>https://nerq.ai/mcp</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>1.0</priority>\n  </url>\n'
        for s in _slug_list:
            xml += f'  <url>\n    <loc>https://nerq.ai/mcp/{s["slug"]}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n'
        xml += '</urlset>'
        return Response(content=xml, media_type="application/xml")

    logger.info(f"Mounted MCP trust pages: {len(_slug_map)} servers, /mcp hub, /sitemap-mcp.xml")
