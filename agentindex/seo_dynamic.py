"""
Nerq Dynamic SEO Pages — BUILD 8, 9, 11
=========================================
- BUILD 8: Auto-blog from data (trending weekly, new arrivals, movers)
- BUILD 9: Trending / New / Leaderboard live pages
- BUILD 11: HuggingFace model pages /model/{name}

Usage in discovery.py:
    from agentindex.seo_dynamic import mount_seo_dynamic
    mount_seo_dynamic(app)
"""

import html
import json
import logging
import re
import time
from datetime import date, timedelta

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_db_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.seo_dynamic")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year

# ── Cache ────────────────────────────────────────────────
_cache: dict[str, tuple[float, object]] = {}
CACHE_TTL = 1800  # 30 min for dynamic pages


def _cached(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def _set_cache(key: str, val):
    _cache[key] = (time.time(), val)
    return val


# ── Helpers ──────────────────────────────────────────────
def _to_slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _score_fmt(v) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _stars_fmt(v) -> str:
    if not v:
        return "-"
    try:
        n = int(v)
        if n >= 1000:
            return f"{n / 1000:.1f}k"
        return str(n)
    except (TypeError, ValueError):
        return "-"


def _grade_color(grade: str | None) -> str:
    if not grade:
        return "#6b7280"
    g = grade.upper().rstrip("+- ")
    if g in ("A", "AA"):
        return "#065f46"
    if g == "B":
        return "#1e40af"
    if g == "C":
        return "#92400e"
    return "#991b1b"


def _grade_pill(grade: str | None) -> str:
    g = html.escape(grade or "N/A")
    color = _grade_color(grade)
    return f'<span style="color:{color};font-weight:700">{g}</span>'


def _trunc(s: str | None, n: int = 120) -> str:
    if not s:
        return ""
    s = s.strip()
    return (s[:n] + "...") if len(s) > n else s


def _page(title: str, body: str, desc: str = "", canonical: str = "",
          jsonld: str = "", robots: str = "index, follow") -> str:
    canon = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    meta_desc = f'<meta name="description" content="{html.escape(desc)}">' if desc else ""
    ld = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{meta_desc}
<meta name="robots" content="{robots}">
{canon}
{ld}
<style>{NERQ_CSS}</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
{body}
</main>
{NERQ_FOOTER}
</body>
</html>"""


def _breadcrumb(*parts: tuple[str, str]) -> str:
    items = ['<a href="/">nerq</a>']
    for href, label in parts:
        if href:
            items.append(f'<a href="{href}">{html.escape(label)}</a>')
        else:
            items.append(html.escape(label))
    return f'<div class="breadcrumb">{" &rsaquo; ".join(items)}</div>'


def _agent_row(i: int, name: str, score, grade, stars, desc: str = "", extra: str = "") -> str:
    slug = _to_slug(name)
    return (
        f'<tr><td>{i}</td>'
        f'<td><a href="/is-{slug}-safe">{html.escape(name)}</a></td>'
        f'<td>{_score_fmt(score)}</td>'
        f'<td>{_grade_pill(grade)}</td>'
        f'<td>{_stars_fmt(stars)}</td>'
        f'<td>{html.escape(_trunc(desc))}</td>'
        f'{f"<td>{extra}</td>" if extra else ""}'
        f'</tr>'
    )


def _table_head(*cols: str) -> str:
    ths = "".join(f"<th>{c}</th>" for c in cols)
    return f"<table><thead><tr>{ths}</tr></thead><tbody>"


# ── Mount all routes ────────────────────────────────────────
def mount_seo_dynamic(app):
    """Mount dynamic SEO routes: blog, trending, leaderboard, model pages."""

    # ════════════════════════════════════════════════════════
    # BUILD 9: Trending / New / Leaderboard
    # ════════════════════════════════════════════════════════

    @app.get("/trending", response_class=HTMLResponse)
    async def trending_page():
        cached = _cached("trending")
        if cached:
            return HTMLResponse(cached)

        with get_db_session() as session:
            # Trending: highest stars among recently updated
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, description, category
                FROM agents
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND last_crawled > NOW() - INTERVAL '7 days'
                ORDER BY COALESCE(stars, 0) DESC
                LIMIT 50
            """)).fetchall()

        trows = ""
        ld_items = []
        for i, r in enumerate(rows, 1):
            name, score, grade, stars, desc, cat = r
            trows += _agent_row(i, name, score, grade, stars, desc or "")
            ld_items.append({"@type": "ListItem", "position": i, "name": name})

        table = _table_head("#", "Name", "Trust", "Grade", "Stars", "Description") + trows + "</tbody></table>"

        jsonld = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                             "name": f"Trending AI Tools {YEAR}", "numberOfItems": len(rows),
                             "itemListElement": ld_items})

        body = f"""{_breadcrumb(("", "Trending"))}
<h1>Trending AI Tools</h1>
<p class="desc">Most active AI agents and tools this week, ranked by community adoption. Updated {TODAY}.</p>
{table}
<p style="margin-top:16px;color:#6b7280">Based on GitHub stars and update activity in the last 7 days. Refreshed every 30 minutes.</p>"""

        result = _page(f"Trending AI Tools {YEAR} | Nerq", body,
                       desc=f"Trending AI agents and tools this week. Top {len(rows)} most active projects ranked by stars and trust.",
                       canonical=f"{SITE}/trending", jsonld=jsonld)
        _set_cache("trending", result)
        return HTMLResponse(result)

    @app.get("/new", response_class=HTMLResponse)
    async def new_agents_page():
        cached = _cached("new")
        if cached:
            return HTMLResponse(cached)

        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, description, category,
                       TO_CHAR(first_indexed, 'YYYY-MM-DD') as added
                FROM agents
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND first_indexed > NOW() - INTERVAL '14 days'
                ORDER BY first_indexed DESC
                LIMIT 50
            """)).fetchall()

        trows = ""
        for i, r in enumerate(rows, 1):
            name, score, grade, stars, desc, cat, added = r
            trows += _agent_row(i, name, score, grade, stars, desc or "", html.escape(added or ""))

        table = _table_head("#", "Name", "Trust", "Grade", "Stars", "Description", "Added") + trows + "</tbody></table>"

        body = f"""{_breadcrumb(("", "New"))}
<h1>New AI Tools</h1>
<p class="desc">Recently indexed AI agents and tools. Updated {TODAY}.</p>
{table}
<p style="margin-top:16px;color:#6b7280">New tools added to the Nerq index in the last 14 days.</p>"""

        result = _page(f"New AI Tools & Agents {YEAR} | Nerq", body,
                       desc=f"Newly indexed AI agents and tools. {len(rows)} new projects added in the last 14 days.",
                       canonical=f"{SITE}/new")
        _set_cache("new", result)
        return HTMLResponse(result)

    @app.get("/leaderboard", response_class=HTMLResponse)
    async def leaderboard_page():
        cached = _cached("leaderboard")
        if cached:
            return HTMLResponse(cached)

        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, description, category
                FROM agents
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                ORDER BY trust_score_v2 DESC
                LIMIT 100
            """)).fetchall()

        trows = ""
        ld_items = []
        for i, r in enumerate(rows, 1):
            name, score, grade, stars, desc, cat = r
            trows += _agent_row(i, name, score, grade, stars, desc or "")
            ld_items.append({"@type": "ListItem", "position": i, "name": name})

        table = _table_head("#", "Name", "Trust", "Grade", "Stars", "Description") + trows + "</tbody></table>"

        jsonld = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
                             "name": f"AI Trust Leaderboard {YEAR}", "numberOfItems": len(rows),
                             "itemListElement": ld_items})

        body = f"""{_breadcrumb(("", "Leaderboard"))}
<h1>AI Trust Leaderboard</h1>
<p class="desc">Top 100 most trusted AI tools, ranked by Nerq Trust Score. Updated {TODAY}.</p>
{table}
<p style="margin-top:16px;color:#6b7280">Trust Score combines security analysis, maintenance activity, documentation quality, and community adoption.</p>"""

        result = _page(f"AI Trust Leaderboard {YEAR} — Top 100 | Nerq", body,
                       desc=f"Top 100 most trusted AI agents and tools ranked by Nerq Trust Score. Independent security and reliability analysis.",
                       canonical=f"{SITE}/leaderboard", jsonld=jsonld)
        _set_cache("leaderboard", result)
        return HTMLResponse(result)

    @app.get("/leaderboard/{category_slug}", response_class=HTMLResponse)
    async def leaderboard_category(category_slug: str):
        cache_key = f"lb:{category_slug}"
        cached = _cached(cache_key)
        if cached:
            return HTMLResponse(cached)

        display = category_slug.replace("-", " ").title()

        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, description
                FROM agents
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND LOWER(COALESCE(category, '')) LIKE :pat
                ORDER BY trust_score_v2 DESC
                LIMIT 50
            """), {"pat": f"%{category_slug.replace('-', '%')}%"}).fetchall()

        if not rows:
            return HTMLResponse(_page("Category not found | Nerq",
                f'{_breadcrumb(("/leaderboard", "Leaderboard"), ("", "not found"))}<h1>No agents found</h1><p><a href="/leaderboard">View full leaderboard</a></p>'),
                status_code=404)

        trows = ""
        for i, r in enumerate(rows, 1):
            name, score, grade, stars, desc = r
            trows += _agent_row(i, name, score, grade, stars, desc or "")

        table = _table_head("#", "Name", "Trust", "Grade", "Stars", "Description") + trows + "</tbody></table>"

        body = f"""{_breadcrumb(("/leaderboard", "Leaderboard"), ("", display))}
<h1>{html.escape(display)} Leaderboard</h1>
<p class="desc">Top {html.escape(display.lower())} ranked by Nerq Trust Score. Updated {TODAY}.</p>
{table}"""

        result = _page(f"{display} Leaderboard {YEAR} | Nerq", body,
                       desc=f"Top {display.lower()} ranked by trust and security. Independent analysis by Nerq.",
                       canonical=f"{SITE}/leaderboard/{category_slug}")
        _set_cache(cache_key, result)
        return HTMLResponse(result)

    # ════════════════════════════════════════════════════════
    # BUILD 8: Auto-blog from data changes
    # ════════════════════════════════════════════════════════

    @app.get("/insights", response_class=HTMLResponse)
    async def blog_index():
        cached = _cached("blog_index")
        if cached:
            return HTMLResponse(cached)

        posts = _generate_blog_posts()
        items = ""
        for p in posts:
            items += f"""<article style="border:1px solid #e5e7eb;padding:20px;margin:12px 0">
<h2 style="margin:0"><a href="/insights/{p['slug']}">{html.escape(p['title'])}</a></h2>
<p style="color:#6b7280;margin:4px 0">{html.escape(p['date'])} &middot; {html.escape(p.get('tag', 'Analysis'))}</p>
<p style="margin-top:8px">{html.escape(p['excerpt'])}</p>
</article>"""

        body = f"""{_breadcrumb(("", "Blog"))}
<h1>Nerq Blog</h1>
<p class="desc">Data-driven insights on AI tool safety, trends, and trust.</p>
{items}"""

        result = _page(f"AI Safety & Trust Blog {YEAR} | Nerq", body,
                       desc="Data-driven articles about AI tool safety, trending agents, and trust analysis.",
                       canonical=f"{SITE}/insights")
        _set_cache("blog_index", result)
        return HTMLResponse(result)

    @app.get("/insights/{slug}", response_class=HTMLResponse)
    async def blog_post(slug: str):
        cache_key = f"blog:{slug}"
        cached = _cached(cache_key)
        if cached:
            return HTMLResponse(cached)

        posts = _generate_blog_posts()
        post = next((p for p in posts if p["slug"] == slug), None)
        if not post:
            return HTMLResponse(_page("Post not found | Nerq",
                f'{_breadcrumb(("/insights", "Insights"), ("", "not found"))}<h1>Post not found</h1><p><a href="/insights">Browse all posts</a></p>'),
                status_code=404)

        jsonld = json.dumps({
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": post["title"], "datePublished": post["date"],
            "author": {"@type": "Organization", "name": "Nerq"},
            "description": post["excerpt"]
        })

        body = f"""{_breadcrumb(("/insights", "Insights"), ("", post['title'][:50]))}
<article>
<h1>{html.escape(post['title'])}</h1>
<p style="color:#6b7280">{html.escape(post['date'])} &middot; {html.escape(post.get('tag', 'Analysis'))}</p>
{post['body']}
</article>"""

        result = _page(post["title"] + " | Nerq", body,
                       desc=post["excerpt"], canonical=f"{SITE}/insights/{slug}", jsonld=jsonld)
        _set_cache(cache_key, result)
        return HTMLResponse(result)

    # ════════════════════════════════════════════════════════
    # BUILD 11: HuggingFace Model Pages /model/{name}
    # ════════════════════════════════════════════════════════

    @app.get("/model/{org}/{model_name}", response_class=HTMLResponse)
    async def model_page(org: str, model_name: str):
        full_name = f"{org}/{model_name}"
        return await _render_model_page(full_name)

    @app.get("/model/{model_name}", response_class=HTMLResponse)
    async def model_page_short(model_name: str):
        return await _render_model_page(model_name)

    async def _render_model_page(query: str):
        cache_key = f"model:{query}"
        cached = _cached(cache_key)
        if cached:
            return HTMLResponse(cached)

        with get_db_session() as session:
            # Try exact name match first
            row = session.execute(text("""
                SELECT id, name, trust_score_v2, trust_grade, stars, description,
                       category, language, author, source, source_url, license,
                       security_score, activity_score, documentation_score,
                       popularity_score, eu_risk_class, downloads, agent_type
                FROM agents
                WHERE LOWER(name) = :q AND is_active = true
                LIMIT 1
            """), {"q": query.lower()}).fetchone()

            if not row:
                # Fuzzy match
                pattern = query.replace("-", "%").replace("/", "%")
                row = session.execute(text("""
                    SELECT id, name, trust_score_v2, trust_grade, stars, description,
                           category, language, author, source, source_url, license,
                           security_score, activity_score, documentation_score,
                           popularity_score, eu_risk_class, downloads, agent_type
                    FROM agents
                    WHERE LOWER(name) LIKE :p AND is_active = true
                      AND (source = 'huggingface' OR category IN ('model', 'dataset')
                           OR agent_type IN ('model', 'dataset'))
                    ORDER BY COALESCE(stars, 0) DESC
                    LIMIT 1
                """), {"p": f"%{pattern}%"}).fetchone()

            if not row:
                # Broadest match
                pattern = query.replace("-", "%").replace("/", "%")
                row = session.execute(text("""
                    SELECT id, name, trust_score_v2, trust_grade, stars, description,
                           category, language, author, source, source_url, license,
                           security_score, activity_score, documentation_score,
                           popularity_score, eu_risk_class, downloads, agent_type
                    FROM agents
                    WHERE LOWER(name) LIKE :p AND is_active = true
                    ORDER BY COALESCE(stars, 0) DESC
                    LIMIT 1
                """), {"p": f"%{pattern}%"}).fetchone()

            if not row:
                return HTMLResponse(_page("Model not found | Nerq",
                    f'{_breadcrumb(("/model", "Models"), ("", "not found"))}<h1>Model not found</h1>'
                    f'<p>Could not find &ldquo;{html.escape(query)}&rdquo;.</p>'
                    f'<p><a href="/discover">Search all indexed assets</a></p>'),
                    status_code=404)

            cols = ["id", "name", "trust_score_v2", "trust_grade", "stars", "description",
                    "category", "language", "author", "source", "source_url", "license",
                    "security_score", "activity_score", "documentation_score",
                    "popularity_score", "eu_risk_class", "downloads", "agent_type"]
            m = dict(zip(cols, row))

            # Get similar models
            similar_rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, description
                FROM agents
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND id != CAST(:tid AS uuid)
                  AND (source = :src OR category = :cat)
                ORDER BY COALESCE(trust_score_v2, 0) DESC
                LIMIT 8
            """), {"tid": str(m["id"]), "src": m.get("source") or "", "cat": m.get("category") or ""}).fetchall()

        name = html.escape(m["name"])
        slug = _to_slug(m["name"])
        ts = m.get("trust_score_v2")
        tg = m.get("trust_grade")
        desc_text = html.escape(_trunc(m.get("description") or "", 300))
        src = m.get("source") or "unknown"
        src_url = m.get("source_url") or ""
        dl = m.get("downloads")
        dl_fmt = f"{int(dl):,}" if dl else "N/A"

        # Trust card
        trust_card = f"""<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin:16px 0">
<div style="text-align:center;border:1px solid #e5e7eb;padding:16px"><div style="font-size:2em;font-weight:700">{_score_fmt(ts)}</div><div style="color:#6b7280">Trust Score</div></div>
<div style="text-align:center;border:1px solid #e5e7eb;padding:16px"><div style="font-size:2em;font-weight:700">{_grade_pill(tg)}</div><div style="color:#6b7280">Grade</div></div>
<div style="text-align:center;border:1px solid #e5e7eb;padding:16px"><div style="font-size:2em;font-weight:700">{_stars_fmt(m.get('stars'))}</div><div style="color:#6b7280">Stars</div></div>
<div style="text-align:center;border:1px solid #e5e7eb;padding:16px"><div style="font-size:2em;font-weight:700">{dl_fmt}</div><div style="color:#6b7280">Downloads</div></div>
</div>"""

        # Details table
        details = f"""<h2>Details</h2>
<table>
<tr><td style="font-weight:600">Author</td><td>{html.escape(m.get('author') or 'Unknown')}</td></tr>
<tr><td style="font-weight:600">Source</td><td>{html.escape(src)}{f' — <a href="{html.escape(src_url)}">view</a>' if src_url else ''}</td></tr>
<tr><td style="font-weight:600">Category</td><td>{html.escape(m.get('category') or '-')}</td></tr>
<tr><td style="font-weight:600">Type</td><td>{html.escape(m.get('agent_type') or '-')}</td></tr>
<tr><td style="font-weight:600">Language</td><td>{html.escape(m.get('language') or '-')}</td></tr>
<tr><td style="font-weight:600">License</td><td>{html.escape(m.get('license') or '-')}</td></tr>
</table>"""

        # Security section
        security = f"""<h2>Security & Trust Analysis</h2>
<table>
<tr><td style="font-weight:600">Security Score</td><td>{_score_fmt(m.get('security_score'))}</td></tr>
<tr><td style="font-weight:600">Activity Score</td><td>{_score_fmt(m.get('activity_score'))}</td></tr>
<tr><td style="font-weight:600">Documentation Score</td><td>{_score_fmt(m.get('documentation_score'))}</td></tr>
<tr><td style="font-weight:600">Popularity Score</td><td>{_score_fmt(m.get('popularity_score'))}</td></tr>
<tr><td style="font-weight:600">EU AI Act Risk Class</td><td>{html.escape(m.get('eu_risk_class') or 'Not classified')}</td></tr>
</table>
<p><a href="/is-{slug}-safe">View full safety report &rarr;</a></p>"""

        # Similar models
        sim_rows = ""
        for i, sr in enumerate(similar_rows, 1):
            sname, sscore, sgrade, sstars, sdesc = sr
            sim_rows += _agent_row(i, sname, sscore, sgrade, sstars, sdesc or "")
        similar_html = ""
        if sim_rows:
            similar_html = f"""<h2>Similar Models & Tools</h2>
{_table_head('#', 'Name', 'Trust', 'Grade', 'Stars', 'Description')}{sim_rows}</tbody></table>
<p><a href="/alternatives/{slug}">View all alternatives &rarr;</a></p>"""

        # FAQ
        faq_items = [
            (f"Is {m['name']} safe to use?", f"Trust Score: {_score_fmt(ts)}, Grade: {html.escape(tg or 'N/A')}. <a href='/is-{slug}-safe'>Full safety report</a>."),
            (f"What is {m['name']}?", desc_text or "An AI model indexed by Nerq."),
            (f"Who created {m['name']}?", f"Author: {html.escape(m.get('author') or 'Unknown')}. Source: {html.escape(src)}."),
        ]
        faq = ""
        for q, a in faq_items:
            faq += f'<details style="margin:8px 0;border:1px solid #e5e7eb;padding:12px"><summary style="cursor:pointer;font-weight:600">{html.escape(q)}</summary><p style="margin-top:8px;color:#4b5563">{a}</p></details>'
        faq = f"<h2>FAQ</h2>{faq}"

        jsonld = json.dumps({
            "@context": "https://schema.org", "@type": "SoftwareApplication",
            "name": m["name"],
            "description": m.get("description") or "",
            "author": {"@type": "Organization", "name": m.get("author") or "Unknown"},
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": str(_score_fmt(ts)), "bestRating": "100", "worstRating": "0", "ratingCount": str(max(1, m.get("stars") or 1))}
        })

        body = f"""{_breadcrumb(("/model", "Models"), ("", m['name'][:60]))}
<h1>{name}</h1>
<p class="desc">{desc_text}</p>
{trust_card}{details}{security}{similar_html}{faq}"""

        title = f"{m['name']} — Trust & Safety Analysis {YEAR} | Nerq"
        desc = f"{m['name']}: Trust Score {_score_fmt(ts)}, Grade {html.escape(tg or 'N/A')}. Security analysis, alternatives, and safety report."

        result = _page(title, body, desc=desc, canonical=f"{SITE}/model/{_to_slug(m['name'])}", jsonld=jsonld)
        _set_cache(cache_key, result)
        return HTMLResponse(result)

    # ── Model hub ──────────────────────────────────────────
    @app.get("/model", response_class=HTMLResponse)
    @app.get("/models", response_class=HTMLResponse)
    async def models_hub():
        cached = _cached("models_hub")
        if cached:
            return HTMLResponse(cached)

        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, description
                FROM agents
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND (source = 'huggingface' OR agent_type IN ('model', 'dataset')
                       OR category IN ('model', 'dataset'))
                ORDER BY COALESCE(stars, 0) DESC
                LIMIT 100
            """)).fetchall()

            total = session.execute(text("""
                SELECT COUNT(*) FROM agents
                WHERE is_active = true
                  AND (source = 'huggingface' OR agent_type IN ('model', 'dataset')
                       OR category IN ('model', 'dataset'))
            """)).scalar() or 0

        trows = ""
        for i, r in enumerate(rows, 1):
            name, score, grade, stars, desc = r
            slug = _to_slug(name)
            trows += f'<tr><td>{i}</td><td><a href="/model/{slug}">{html.escape(name)}</a></td><td>{_score_fmt(score)}</td><td>{_grade_pill(grade)}</td><td>{_stars_fmt(stars)}</td><td>{html.escape(_trunc(desc))}</td></tr>'

        table = _table_head("#", "Name", "Trust", "Grade", "Stars", "Description") + trows + "</tbody></table>"

        body = f"""{_breadcrumb(("", "Models"))}
<h1>AI Models & Datasets</h1>
<p class="desc">{total:,} models and datasets indexed with trust scores. Updated {TODAY}.</p>
{table}
<p style="margin-top:16px;color:#6b7280">Showing top 100 by stars. <a href="/discover">Search all {total:,} assets</a>.</p>"""

        result = _page(f"AI Models & Datasets {YEAR} — Trust Scores | Nerq", body,
                       desc=f"{total:,} AI models and datasets with independent trust scores. Security analysis for HuggingFace, GitHub, and more.",
                       canonical=f"{SITE}/models")
        _set_cache("models_hub", result)
        return HTMLResponse(result)

    # ── Sitemaps for new pages ─────────────────────────────
    @app.get("/sitemap-trending.xml", response_class=Response)
    async def sitemap_trending():
        urls = [
            (f"{SITE}/trending", "0.8"),
            (f"{SITE}/new", "0.8"),
            (f"{SITE}/leaderboard", "0.8"),
            (f"{SITE}/models", "0.7"),
            (f"{SITE}/insights", "0.7"),
        ]
        return Response(_sitemap_xml(urls), media_type="application/xml")

    @app.get("/sitemap-models.xml", response_class=Response)
    async def sitemap_models():
        """Redirect: first chunk of model sitemap."""
        return await _sitemap_models_chunk(0)

    @app.get("/sitemap-models-{chunk}.xml", response_class=Response)
    async def sitemap_models_chunked(chunk: int):
        return await _sitemap_models_chunk(chunk)

    async def _sitemap_models_chunk(chunk: int):
        cache_key = f"sitemap:models:{chunk}"
        cached = _cached(cache_key)
        if cached:
            return Response(cached, media_type="application/xml")

        offset = chunk * 50000
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name FROM agents
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND (agent_type = 'model' OR (source LIKE '%%huggingface%%' AND agent_type IN ('model', 'space')))
                  AND description IS NOT NULL AND LENGTH(description) > 10
                ORDER BY COALESCE(downloads, 0) DESC, COALESCE(stars, 0) DESC
                OFFSET :off LIMIT 50000
            """), {"off": offset}).fetchall()

        if not rows:
            return Response('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
                          media_type="application/xml")

        urls = [(f"{SITE}/model/{_to_slug(r[0])}", "0.6") for r in rows]
        xml = _sitemap_xml(urls)
        _set_cache(cache_key, xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-blog.xml", response_class=Response)
    async def sitemap_blog():
        posts = _generate_blog_posts()
        urls = [(f"{SITE}/insights/{p['slug']}", "0.6") for p in posts]
        urls.insert(0, (f"{SITE}/blog", "0.7"))
        return Response(_sitemap_xml(urls), media_type="application/xml")

    logger.info("Mounted dynamic SEO routes: /trending, /new, /leaderboard, /insights, /model")


# ── Blog post generator (outside mount) ────────────────────
def _generate_blog_posts() -> list[dict]:
    """Generate blog posts from live DB data."""
    cached = _cached("blog_posts")
    if cached:
        return cached

    posts = []
    today = date.today()

    with get_db_session() as session:
        # Post 1: Weekly Top 10
        top10 = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars
            FROM agents WHERE is_active = true AND trust_score_v2 IS NOT NULL
            ORDER BY trust_score_v2 DESC LIMIT 10
        """)).fetchall()

        if top10:
            top_list = ""
            for i, r in enumerate(top10, 1):
                slug = _to_slug(r[0])
                top_list += f'<li><a href="/is-{slug}-safe">{html.escape(r[0])}</a> — Trust Score {_score_fmt(r[1])} ({_grade_pill(r[2])}), {_stars_fmt(r[3])} stars</li>'

            week_num = today.isocalendar()[1]
            posts.append({
                "slug": f"top-10-trusted-ai-tools-week-{week_num}-{YEAR}",
                "title": f"Top 10 Most Trusted AI Tools — Week {week_num}, {YEAR}",
                "date": today.isoformat(),
                "tag": "Weekly Ranking",
                "excerpt": f"This week's most trusted AI tools based on Nerq Trust Score analysis of {len(top10)} projects.",
                "body": f"<h2>This Week's Top 10</h2><ol>{top_list}</ol>"
                        f"<p>Trust Scores combine security analysis, maintenance activity, documentation quality, and community adoption signals.</p>"
                        f'<p><a href="/leaderboard">View full leaderboard &rarr;</a></p>'
            })

        # Post 2: New arrivals
        new_agents = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, category
            FROM agents WHERE is_active = true AND trust_score_v2 IS NOT NULL
              AND first_indexed > NOW() - INTERVAL '7 days'
            ORDER BY COALESCE(stars, 0) DESC LIMIT 10
        """)).fetchall()

        if new_agents:
            new_list = ""
            for r in new_agents:
                slug = _to_slug(r[0])
                new_list += f'<li><a href="/is-{slug}-safe">{html.escape(r[0])}</a> — {html.escape(r[3] or "General")} — Score {_score_fmt(r[1])}</li>'

            posts.append({
                "slug": f"new-ai-tools-week-{today.isocalendar()[1]}-{YEAR}",
                "title": f"New AI Tools This Week — {today.strftime('%B %d, %Y')}",
                "date": today.isoformat(),
                "tag": "New Arrivals",
                "excerpt": f"{len(new_agents)} new AI tools indexed this week with trust scores.",
                "body": f"<h2>Newly Indexed</h2><ul>{new_list}</ul>"
                        f'<p><a href="/new">See all new tools &rarr;</a></p>'
            })

        # Post 3: Category spotlight
        cat_data = session.execute(text("""
            SELECT category, COUNT(*) as cnt, AVG(trust_score_v2) as avg_score
            FROM agents WHERE is_active = true AND trust_score_v2 IS NOT NULL AND category IS NOT NULL
            GROUP BY category ORDER BY cnt DESC LIMIT 10
        """)).fetchall()

        if cat_data:
            cat_rows = ""
            for r in cat_data:
                cat_name, cnt, avg = r
                cat_rows += f"<tr><td>{html.escape(str(cat_name))}</td><td>{cnt:,}</td><td>{_score_fmt(avg)}</td></tr>"

            posts.append({
                "slug": f"ai-tool-categories-{today.strftime('%Y-%m')}",
                "title": f"AI Tool Categories — {today.strftime('%B %Y')} Overview",
                "date": today.isoformat(),
                "tag": "Analysis",
                "excerpt": f"Overview of {len(cat_data)} AI tool categories with average trust scores.",
                "body": f"<h2>Category Breakdown</h2>"
                        f"<table><thead><tr><th>Category</th><th>Tools</th><th>Avg Trust</th></tr></thead>"
                        f"<tbody>{cat_rows}</tbody></table>"
                        f'<p><a href="/best">Browse best-of lists &rarr;</a></p>'
            })

        # Post 4: Trust grade distribution
        grade_data = session.execute(text("""
            SELECT trust_grade, COUNT(*) as cnt
            FROM agents WHERE is_active = true AND trust_grade IS NOT NULL
            GROUP BY trust_grade ORDER BY cnt DESC
        """)).fetchall()

        if grade_data:
            grade_rows = ""
            total = sum(r[1] for r in grade_data)
            for r in grade_data:
                pct = (r[1] / total * 100) if total else 0
                grade_rows += f"<tr><td>{_grade_pill(r[0])}</td><td>{r[1]:,}</td><td>{pct:.1f}%</td></tr>"

            posts.append({
                "slug": f"ai-trust-grade-distribution-{today.strftime('%Y-%m')}",
                "title": f"AI Trust Grade Distribution — {today.strftime('%B %Y')}",
                "date": today.isoformat(),
                "tag": "Research",
                "excerpt": f"How {total:,} AI tools score on the Nerq trust grading scale.",
                "body": f"<h2>Grade Distribution</h2>"
                        f"<table><thead><tr><th>Grade</th><th>Count</th><th>%</th></tr></thead>"
                        f"<tbody>{grade_rows}</tbody></table>"
                        f"<p>Trust grades range from A (highest trust) to D (lowest). "
                        f"Each grade reflects a combination of security, maintenance, documentation, and community signals.</p>"
            })

    _set_cache("blog_posts", posts)
    return posts


def _sitemap_xml(urls: list[tuple[str, str]]) -> str:
    entries = ""
    for url, prio in urls:
        entries += f"<url><loc>{html.escape(url)}</loc><lastmod>{TODAY}</lastmod><priority>{prio}</priority></url>\n"
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{entries}</urlset>'
