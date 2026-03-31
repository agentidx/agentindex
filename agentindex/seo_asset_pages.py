"""
Nerq Asset Pages — Phase 2+3
==============================
- /space/{org}/{name} — HuggingFace Space pages
- /container/{name} — Docker Hub container pages
- /dataset/{org}/{name} — HuggingFace Dataset pages
- /org/{name} — Organization hub pages

Usage in discovery.py:
    from agentindex.seo_asset_pages import mount_asset_pages
    mount_asset_pages(app)
"""

import html as html_mod
import logging
import math
import re
import time
from datetime import date

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_db_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.seo_asset_pages")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
MONTH_YEAR = date.today().strftime("%B %Y")
YEAR = date.today().year

_cache: dict[str, tuple[float, object]] = {}
CACHE_TTL = 3600


def _cached(key: str):
    e = _cache.get(key)
    if e and (time.time() - e[0]) < CACHE_TTL:
        return e[1]
    return None


def _set_cache(key: str, val):
    _cache[key] = (time.time(), val)
    return val


def _esc(t):
    return html_mod.escape(str(t)) if t else ""


def _to_slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _fmt_num(n):
    if n is None:
        return "0"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(int(n))


def _grade_color(grade):
    if not grade:
        return "#6b7280"
    g = grade[0].upper()
    return {"A": "#16a34a", "B": "#0d9488", "C": "#ca8a04", "D": "#f97316"}.get(g, "#dc2626")


def _verdict(score):
    if score and score >= 70:
        return "SAFE", "#16a34a", "This asset has strong trust signals and is considered safe for production use."
    elif score and score >= 50:
        return "CAUTION", "#ca8a04", "This asset has moderate trust signals. Review before using in production."
    else:
        return "RISK", "#dc2626", "This asset has weak trust signals. Use with caution and verify independently."


def _score_card(label, value, color=None):
    c = f' style="color:{color}"' if color else ""
    return f'<div style="padding:16px;border:1px solid #e5e7eb;text-align:center"><div style="font-size:24px;font-weight:700;font-family:ui-monospace,monospace"{c}>{_esc(str(value))}</div><div style="font-size:11px;color:#6b7280;text-transform:uppercase;margin-top:4px">{label}</div></div>'


def _internal_links(name, category, agent_type):
    """Generate minimum 10 internal links per page."""
    slug = _to_slug(name)
    cat_slug = _to_slug(category) if category else "coding"
    links = [
        f'<a href="/safe/{slug}" style="color:#0d9488">Safety Report</a>',
        f'<a href="/is-{slug}-safe" style="color:#0d9488">Is {_esc(name.split("/")[-1])} Safe?</a>',
        f'<a href="/best/{cat_slug}" style="color:#0d9488">Best {_esc(category or "Tools")}</a>',
        f'<a href="/leaderboard" style="color:#0d9488">Trust Leaderboard</a>',
        f'<a href="/trending" style="color:#0d9488">Trending</a>',
        f'<a href="/mcp-servers" style="color:#0d9488">MCP Servers</a>',
        f'<a href="/compare" style="color:#0d9488">Compare Tools</a>',
        f'<a href="/packages" style="color:#0d9488">Package Trust</a>',
        f'<a href="/models" style="color:#0d9488">AI Models</a>',
        f'<a href="/discover" style="color:#0d9488">Discover</a>',
        f'<a href="/gateway" style="color:#0d9488">Nerq Gateway</a>',
    ]
    return " &middot; ".join(links)


def _sitemap_xml(urls):
    entries = ""
    for url, prio in urls:
        entries += f"<url><loc>{html_mod.escape(url)}</loc><lastmod>{TODAY}</lastmod><changefreq>weekly</changefreq><priority>{prio}</priority></url>\n"
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{entries}</urlset>'


def _find_asset(query, agent_type):
    """Find an asset by name, filtered by type."""
    with get_db_session() as session:
        q = query.lower().strip()
        p = "%" + q.replace("-", "%").replace("/", "%") + "%"
        row = session.execute(text("""
            SELECT id, name, trust_score_v2, trust_grade, stars, description,
                   category, language, author, source, source_url, license,
                   security_score, activity_score, documentation_score,
                   popularity_score, eu_risk_class, downloads, agent_type, tags
            FROM agents
            WHERE (LOWER(name) = :q OR LOWER(name) LIKE :p) AND is_active = true
              AND agent_type = :atype
            ORDER BY COALESCE(downloads, 0) DESC, COALESCE(stars, 0) DESC
            LIMIT 1
        """), {"q": q, "p": p, "atype": agent_type}).fetchone()
        if not row:
            # Broader search
            row = session.execute(text("""
                SELECT id, name, trust_score_v2, trust_grade, stars, description,
                       category, language, author, source, source_url, license,
                       security_score, activity_score, documentation_score,
                       popularity_score, eu_risk_class, downloads, agent_type, tags
                FROM agents
                WHERE LOWER(name) LIKE :p AND is_active = true AND agent_type = :atype
                ORDER BY COALESCE(downloads, 0) DESC, COALESCE(stars, 0) DESC
                LIMIT 1
            """), {"p": p, "atype": agent_type}).fetchone()
        if row:
            return dict(zip(["id","name","trust_score","trust_grade","stars","description",
                           "category","language","author","source","source_url","license",
                           "security_score","activity_score","documentation_score",
                           "popularity_score","eu_risk_class","downloads","agent_type","tags"], row))
    return None


def _find_similar(name, category, agent_type, limit=8):
    """Find similar assets."""
    with get_db_session() as session:
        rows = session.execute(text("""
            SELECT name, trust_score_v2, trust_grade, stars, downloads
            FROM agents
            WHERE is_active = true AND agent_type = :atype
              AND LOWER(name) != :name
              AND (category = :cat OR :cat IS NULL)
              AND trust_score_v2 IS NOT NULL
            ORDER BY COALESCE(downloads, 0) DESC, COALESCE(stars, 0) DESC
            LIMIT :lim
        """), {"atype": agent_type, "name": name.lower(), "cat": category, "lim": limit}).fetchall()
        return [dict(zip(["name","trust_score","trust_grade","stars","downloads"], r)) for r in rows]


def _page_head(title, desc, canonical, asset_type, name, score, grade):
    """Generate full HTML head with all SEO + AI meta tags."""
    v, vc, _ = _verdict(score)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{_esc(title)}">
<meta name="twitter:description" content="{_esc(desc)}">
<meta name="nerq:type" content="{asset_type}">
<meta name="nerq:tools" content="{_esc(name)}">
<meta name="nerq:verdict" content="{v}">
<meta name="nerq:updated" content="{TODAY}">
{NERQ_CSS}
<style>
.score-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}}
.detail-table{{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0}}
.detail-table th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280;font-weight:600}}
.detail-table td{{padding:8px;border-bottom:1px solid #e5e7eb}}
.faq-q{{font-weight:600;font-size:14px;cursor:pointer;padding:12px 0;border-bottom:1px solid #e5e7eb}}
.faq-a{{font-size:13px;color:#374151;padding:8px 0 12px}}
.links{{display:flex;flex-wrap:wrap;gap:6px;font-size:12px;margin:16px 0}}
</style>
</head><body>
{NERQ_NAV}
<main class="container" style="max-width:900px;margin:0 auto;padding:24px">"""


def _page_foot(name, category, agent_type):
    """Generate page footer with internal links and disclaimer."""
    return f"""
<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb">
<div class="links">{_internal_links(name, category, agent_type)}</div>
</div>
<p style="font-size:12px;color:#6b7280;margin-top:16px">
<strong>Disclaimer:</strong> Nerq trust scores are automated assessments. Not endorsements. Last updated {MONTH_YEAR}.</p>
</main>
{NERQ_FOOTER}
</body></html>"""


# ════════════════════════════════════════════════════════════
# SPACE PAGES
# ════════════════════════════════════════════════════════════

def _render_space_page(query):
    ck = f"space:{query}"
    c = _cached(ck)
    if c:
        return c

    a = _find_asset(query, "space")
    if not a:
        return None

    name = a["name"]
    short = name.split("/")[-1] if "/" in name else name
    score = a["trust_score"] or 0
    grade = a["trust_grade"] or "D"
    v, vc, vd = _verdict(score)
    desc_text = a["description"] or f"HuggingFace Space by {a['author'] or 'unknown'}"
    author = a["author"] or "Unknown"
    downloads = a["downloads"] or 0
    stars = a["stars"] or 0
    source_url = a["source_url"] or f"https://huggingface.co/spaces/{name}"
    tags = a["tags"] or []
    tag_str = ", ".join(tags[:10]) if tags else "AI, HuggingFace"

    similar = _find_similar(name, a["category"], "space")
    sim_html = ""
    for s in similar[:6]:
        sim_html += f'<tr><td><a href="/space/{_to_slug(s["name"])}" style="color:#0d9488">{_esc(s["name"])}</a></td><td>{_fmt_num(s["downloads"])}</td><td style="color:{_grade_color(s["trust_grade"])}">{s["trust_score"]:.0f}</td></tr>'

    title = f"{_esc(short)} — Space Trust Analysis {YEAR} | Nerq"
    meta_desc = f"{_esc(short)} HuggingFace Space: Trust Score {score:.0f}/100 ({grade}). {v}. Independent safety analysis with {len(tags)} tags analyzed."

    faq_items = [
        (f"Is {_esc(short)} safe to use?", f"{_esc(short)} has a Nerq Trust Score of {score:.0f}/100 (Grade {grade}). Verdict: {v.lower()}. {vd}"),
        (f"What does {_esc(short)} do?", f"{_esc(desc_text[:200])}"),
        (f"Who created {_esc(short)}?", f"{_esc(short)} was created by {_esc(author)} and is hosted on HuggingFace Spaces."),
        (f"Are there alternatives to {_esc(short)}?", f"Yes. See the similar spaces listed above, ranked by trust score and popularity."),
    ]
    faq_html = "".join(f'<div class="faq-q">{q}</div><div class="faq-a">{a_text}</div>' for q, a_text in faq_items)
    faq_jsonld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a_text}"}}}}' for q, a_text in faq_items)

    canonical = f"{SITE}/space/{_to_slug(name)}"

    page = _page_head(title, meta_desc, canonical, "space", name, score, grade)
    page += f"""
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"SoftwareApplication","name":"{_esc(short)}","applicationCategory":"AI Space","operatingSystem":"Web","url":"{canonical}","author":{{"@type":"Organization","name":"{_esc(author)}"}},"aggregateRating":{{"@type":"AggregateRating","ratingValue":"{score/20:.1f}","bestRating":"5","worstRating":"1","ratingCount":"{max(1, stars)}"}}}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Nerq","item":"{SITE}"}},{{"@type":"ListItem","position":2,"name":"Spaces","item":"{SITE}/spaces"}},{{"@type":"ListItem","position":3,"name":"{_esc(short)}","item":"{canonical}"}}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_jsonld}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Dataset","name":"{_esc(short)} Trust Analysis","description":"Trust and safety analysis of {_esc(short)} HuggingFace Space","variableMeasured":[{{"@type":"PropertyValue","name":"Trust Score","value":"{score:.0f}","unitText":"points out of 100"}},{{"@type":"PropertyValue","name":"Grade","value":"{grade}"}},{{"@type":"PropertyValue","name":"Downloads","value":"{downloads}"}}]}}
</script>

<nav style="font-size:12px;color:#6b7280;margin-bottom:16px"><a href="/" style="color:#0d9488">Nerq</a> &rsaquo; <a href="/spaces" style="color:#0d9488">Spaces</a> &rsaquo; {_esc(short)}</nav>

<h1>{_esc(short)} — HuggingFace Space Trust & Safety Analysis {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{_esc(short)} is a HuggingFace Space by {_esc(author)} with a Nerq Trust Score of <strong>{score:.0f}/100</strong> (Grade {grade}). Verdict: <strong style="color:{vc}">{v}</strong>. {vd} Last analyzed {MONTH_YEAR}.</p>

<div class="score-grid">
{_score_card("Trust Score", f"{score:.0f}", vc)}
{_score_card("Grade", grade, _grade_color(grade))}
{_score_card("Stars", _fmt_num(stars))}
{_score_card("Downloads", _fmt_num(downloads))}
</div>

<h2>About {_esc(short)}</h2>
<p style="font-size:14px;color:#374151;line-height:1.7">{_esc(desc_text)}</p>

<h2>Details</h2>
<table class="detail-table">
<tr><th>Author</th><td>{_esc(author)}</td></tr>
<tr><th>Source</th><td><a href="{_esc(source_url)}" rel="nofollow" style="color:#0d9488">HuggingFace</a></td></tr>
<tr><th>Category</th><td>{_esc(a["category"] or "Uncategorized")}</td></tr>
<tr><th>Tags</th><td>{_esc(tag_str)}</td></tr>
<tr><th>License</th><td>{_esc(a["license"] or "Not specified")}</td></tr>
<tr><th>Language</th><td>{_esc(a["language"] or "Not specified")}</td></tr>
</table>

<h2>Security Analysis</h2>
<p style="font-size:14px;color:#374151">HuggingFace Spaces can execute code in your browser. This security analysis checks for known vulnerabilities, maintenance activity, and community trust signals.</p>
<table class="detail-table">
<tr><th>Security Score</th><td>{a["security_score"] or "Pending"}/100</td></tr>
<tr><th>Activity Score</th><td>{a["activity_score"] or "Pending"}/100</td></tr>
<tr><th>Documentation</th><td>{a["documentation_score"] or "Pending"}/100</td></tr>
<tr><th>Popularity</th><td>{a["popularity_score"] or "Pending"}/100</td></tr>
<tr><th>EU AI Act Class</th><td>{_esc(a["eu_risk_class"] or "Pending classification")}</td></tr>
</table>

{"<h2>Similar Spaces</h2><table class='detail-table'><tr><th>Space</th><th>Downloads</th><th>Trust</th></tr>" + sim_html + "</table>" if sim_html else ""}

<h2>Frequently Asked Questions</h2>
{faq_html}

<div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb">
<div style="font-weight:600;margin-bottom:8px">Check Any Space</div>
<pre style="background:#f5f5f5;padding:8px;font-size:12px;overflow-x:auto">curl nerq.ai/v1/preflight?target={_to_slug(name)}</pre>
<a href="/nerq/docs" style="font-size:12px;color:#0d9488">API docs &rarr;</a>
</div>
"""
    page += _page_foot(name, a["category"], "space")
    return _set_cache(ck, page)


# ════════════════════════════════════════════════════════════
# CONTAINER PAGES
# ════════════════════════════════════════════════════════════

def _render_container_page(query):
    ck = f"container:{query}"
    c = _cached(ck)
    if c:
        return c

    a = _find_asset(query, "container")
    if not a:
        return None

    name = a["name"]
    short = name.split("/")[-1] if "/" in name else name
    score = a["trust_score"] or 0
    grade = a["trust_grade"] or "D"
    v, vc, vd = _verdict(score)
    desc_text = a["description"] or f"Docker container image"
    author = a["author"] or "Unknown"
    downloads = a["downloads"] or 0
    stars = a["stars"] or 0
    source_url = a["source_url"] or f"https://hub.docker.com/r/{name}"

    similar = _find_similar(name, a["category"], "container")
    sim_html = ""
    for s in similar[:6]:
        sim_html += f'<tr><td><a href="/container/{_to_slug(s["name"])}" style="color:#0d9488">{_esc(s["name"])}</a></td><td>{_fmt_num(s["downloads"])}</td><td style="color:{_grade_color(s["trust_grade"])}">{s["trust_score"]:.0f}</td></tr>'

    title = f"Is {_esc(short)} Safe? Docker Security {YEAR} | Nerq"
    meta_desc = f"Is {_esc(short)} Docker image safe? Trust Score: {score:.0f}/100 ({grade}). {_fmt_num(downloads)} pulls. Independent container security analysis."

    faq_items = [
        (f"Is the {_esc(short)} Docker image safe?", f"{_esc(short)} has a Nerq Trust Score of {score:.0f}/100 (Grade {grade}). Verdict: {v.lower()}. Docker containers can execute arbitrary code, so always verify trust before pulling."),
        (f"Does {_esc(short)} have vulnerabilities?", f"Security score: {a['security_score'] or 'pending'}/100. Check the full analysis above for CVE data, maintenance status, and community trust signals."),
        (f"How many people use {_esc(short)}?", f"{_esc(short)} has {_fmt_num(downloads)} pulls on Docker Hub, indicating {'widespread' if downloads > 100000 else 'moderate' if downloads > 1000 else 'limited'} adoption."),
        (f"What are alternatives to {_esc(short)}?", f"See similar containers listed above, ranked by trust score and pull count."),
        (f"Is {_esc(short)} maintained?", f"Activity score: {a['activity_score'] or 'pending'}/100. A higher score indicates more recent updates and active maintenance."),
    ]
    faq_html = "".join(f'<div class="faq-q">{q}</div><div class="faq-a">{a_text}</div>' for q, a_text in faq_items)
    faq_jsonld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a_text}"}}}}' for q, a_text in faq_items)

    canonical = f"{SITE}/container/{_to_slug(name)}"

    page = _page_head(title, meta_desc, canonical, "container", name, score, grade)
    page += f"""
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"SoftwareApplication","name":"{_esc(short)}","applicationCategory":"Docker Container","operatingSystem":"Linux","url":"{canonical}","author":{{"@type":"Organization","name":"{_esc(author)}"}},"aggregateRating":{{"@type":"AggregateRating","ratingValue":"{score/20:.1f}","bestRating":"5","worstRating":"1","ratingCount":"{max(1, int(downloads/1000) if downloads else 1)}"}}}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Nerq","item":"{SITE}"}},{{"@type":"ListItem","position":2,"name":"Containers","item":"{SITE}/containers"}},{{"@type":"ListItem","position":3,"name":"{_esc(short)}","item":"{canonical}"}}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_jsonld}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Dataset","name":"{_esc(short)} Security Analysis","description":"Docker container security analysis for {_esc(short)}","variableMeasured":[{{"@type":"PropertyValue","name":"Trust Score","value":"{score:.0f}","unitText":"points out of 100"}},{{"@type":"PropertyValue","name":"Pulls","value":"{downloads}"}}]}}
</script>

<nav style="font-size:12px;color:#6b7280;margin-bottom:16px"><a href="/" style="color:#0d9488">Nerq</a> &rsaquo; <a href="/containers" style="color:#0d9488">Containers</a> &rsaquo; {_esc(short)}</nav>

<h1>Is {_esc(short)} Safe? Docker Container Security Analysis {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{_esc(short)} is a Docker container by {_esc(author)} with a Nerq Trust Score of <strong>{score:.0f}/100</strong> (Grade {grade}). Verdict: <strong style="color:{vc}">{v}</strong>. Docker containers execute arbitrary code — always verify trust before pulling. {_fmt_num(downloads)} total pulls. Last analyzed {MONTH_YEAR}.</p>

<div class="score-grid">
{_score_card("Trust Score", f"{score:.0f}", vc)}
{_score_card("Grade", grade, _grade_color(grade))}
{_score_card("Pulls", _fmt_num(downloads))}
{_score_card("Stars", _fmt_num(stars))}
</div>

<h2>About {_esc(short)}</h2>
<p style="font-size:14px;color:#374151;line-height:1.7">{_esc(desc_text)}</p>

<h2>Container Security Details</h2>
<p style="font-size:14px;color:#374151">Docker containers can access host resources, network, and data. This analysis evaluates the publisher's trustworthiness, image maintenance, and known security issues.</p>
<table class="detail-table">
<tr><th>Publisher</th><td>{_esc(author)}</td></tr>
<tr><th>Source</th><td><a href="{_esc(source_url)}" rel="nofollow" style="color:#0d9488">Docker Hub</a></td></tr>
<tr><th>Total Pulls</th><td>{downloads:,}</td></tr>
<tr><th>Stars</th><td>{stars:,}</td></tr>
<tr><th>Security Score</th><td>{a["security_score"] or "Pending"}/100</td></tr>
<tr><th>Activity Score</th><td>{a["activity_score"] or "Pending"}/100</td></tr>
<tr><th>Documentation</th><td>{a["documentation_score"] or "Pending"}/100</td></tr>
<tr><th>EU AI Act Class</th><td>{_esc(a["eu_risk_class"] or "Pending")}</td></tr>
</table>

{"<h2>Similar Containers</h2><table class='detail-table'><tr><th>Container</th><th>Pulls</th><th>Trust</th></tr>" + sim_html + "</table>" if sim_html else ""}

<h2>Frequently Asked Questions</h2>
{faq_html}

<div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb">
<div style="font-weight:600;margin-bottom:8px">Check Any Container</div>
<pre style="background:#f5f5f5;padding:8px;font-size:12px;overflow-x:auto">curl nerq.ai/v1/preflight?target={_to_slug(name)}</pre>
<a href="/nerq/docs" style="font-size:12px;color:#0d9488">API docs &rarr;</a>
</div>
"""
    page += _page_foot(name, a["category"], "container")
    return _set_cache(ck, page)


# ════════════════════════════════════════════════════════════
# DATASET PAGES
# ════════════════════════════════════════════════════════════

def _render_dataset_page(query):
    ck = f"dataset:{query}"
    c = _cached(ck)
    if c:
        return c

    a = _find_asset(query, "dataset")
    if not a:
        return None

    name = a["name"]
    short = name.split("/")[-1] if "/" in name else name
    score = a["trust_score"] or 0
    grade = a["trust_grade"] or "D"
    v, vc, vd = _verdict(score)
    desc_text = a["description"] or f"HuggingFace Dataset by {a['author'] or 'unknown'}"
    author = a["author"] or "Unknown"
    downloads = a["downloads"] or 0
    stars = a["stars"] or 0
    source_url = a["source_url"] or f"https://huggingface.co/datasets/{name}"
    license_str = a["license"] or "Not specified"
    tags = a["tags"] or []
    tag_str = ", ".join(tags[:10]) if tags else "Dataset, AI"

    similar = _find_similar(name, a["category"], "dataset")
    sim_html = ""
    for s in similar[:6]:
        sim_html += f'<tr><td><a href="/dataset/{_to_slug(s["name"])}" style="color:#0d9488">{_esc(s["name"])}</a></td><td>{_fmt_num(s["downloads"])}</td><td style="color:{_grade_color(s["trust_grade"])}">{s["trust_score"]:.0f}</td></tr>'

    title = f"{_esc(short)} — Dataset Trust Analysis {YEAR} | Nerq"
    meta_desc = f"{_esc(short)} dataset: Trust Score {score:.0f}/100 ({grade}). {_fmt_num(downloads)} downloads. License: {license_str}. Independent quality analysis."

    faq_items = [
        (f"Is {_esc(short)} safe to use?", f"{_esc(short)} has a Nerq Trust Score of {score:.0f}/100 (Grade {grade}). Verdict: {v.lower()}. Always check the license and data provenance before using in production."),
        (f"What license is {_esc(short)}?", f"License: {_esc(license_str)}. Verify the license terms on HuggingFace before commercial use."),
        (f"How popular is {_esc(short)}?", f"{_esc(short)} has {_fmt_num(downloads)} downloads and {_fmt_num(stars)} stars on HuggingFace, indicating {'strong' if downloads > 100000 else 'moderate' if downloads > 1000 else 'growing'} community adoption."),
        (f"Who maintains {_esc(short)}?", f"{_esc(short)} is maintained by {_esc(author)}. Activity score: {a['activity_score'] or 'pending'}/100."),
    ]
    faq_html = "".join(f'<div class="faq-q">{q}</div><div class="faq-a">{a_text}</div>' for q, a_text in faq_items)
    faq_jsonld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a_text}"}}}}' for q, a_text in faq_items)

    canonical = f"{SITE}/dataset/{_to_slug(name)}"

    page = _page_head(title, meta_desc, canonical, "dataset", name, score, grade)
    page += f"""
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Dataset","name":"{_esc(short)}","description":"{_esc(desc_text[:200])}","url":"{canonical}","license":"{_esc(license_str)}","creator":{{"@type":"Organization","name":"{_esc(author)}"}},"distribution":{{"@type":"DataDownload","encodingFormat":"application/json","contentUrl":"{_esc(source_url)}"}},"variableMeasured":[{{"@type":"PropertyValue","name":"Trust Score","value":"{score:.0f}","unitText":"points out of 100"}},{{"@type":"PropertyValue","name":"Downloads","value":"{downloads}"}}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Nerq","item":"{SITE}"}},{{"@type":"ListItem","position":2,"name":"Datasets","item":"{SITE}/datasets"}},{{"@type":"ListItem","position":3,"name":"{_esc(short)}","item":"{canonical}"}}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_jsonld}]}}
</script>

<nav style="font-size:12px;color:#6b7280;margin-bottom:16px"><a href="/" style="color:#0d9488">Nerq</a> &rsaquo; <a href="/datasets" style="color:#0d9488">Datasets</a> &rsaquo; {_esc(short)}</nav>

<h1>{_esc(short)} — Dataset Trust & Quality Analysis {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{_esc(short)} is a dataset by {_esc(author)} with a Nerq Trust Score of <strong>{score:.0f}/100</strong> (Grade {grade}). Verdict: <strong style="color:{vc}">{v}</strong>. {_fmt_num(downloads)} downloads. License: {_esc(license_str)}. Last analyzed {MONTH_YEAR}.</p>

<div class="score-grid">
{_score_card("Trust Score", f"{score:.0f}", vc)}
{_score_card("Grade", grade, _grade_color(grade))}
{_score_card("Downloads", _fmt_num(downloads))}
{_score_card("Stars", _fmt_num(stars))}
</div>

<h2>About This Dataset</h2>
<p style="font-size:14px;color:#374151;line-height:1.7">{_esc(desc_text)}</p>

<h2>Dataset Details</h2>
<table class="detail-table">
<tr><th>Author</th><td>{_esc(author)}</td></tr>
<tr><th>Source</th><td><a href="{_esc(source_url)}" rel="nofollow" style="color:#0d9488">HuggingFace</a></td></tr>
<tr><th>License</th><td>{_esc(license_str)}</td></tr>
<tr><th>Tags</th><td>{_esc(tag_str)}</td></tr>
<tr><th>Language</th><td>{_esc(a["language"] or "Not specified")}</td></tr>
<tr><th>Downloads</th><td>{downloads:,}</td></tr>
</table>

<h2>Quality & Trust Analysis</h2>
<table class="detail-table">
<tr><th>Security Score</th><td>{a["security_score"] or "Pending"}/100</td></tr>
<tr><th>Activity Score</th><td>{a["activity_score"] or "Pending"}/100</td></tr>
<tr><th>Documentation</th><td>{a["documentation_score"] or "Pending"}/100</td></tr>
<tr><th>Popularity</th><td>{a["popularity_score"] or "Pending"}/100</td></tr>
<tr><th>EU AI Act Class</th><td>{_esc(a["eu_risk_class"] or "Pending")}</td></tr>
</table>

{"<h2>Similar Datasets</h2><table class='detail-table'><tr><th>Dataset</th><th>Downloads</th><th>Trust</th></tr>" + sim_html + "</table>" if sim_html else ""}

<h2>Frequently Asked Questions</h2>
{faq_html}

<div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb">
<div style="font-weight:600;margin-bottom:8px">Check Any Dataset</div>
<pre style="background:#f5f5f5;padding:8px;font-size:12px;overflow-x:auto">curl nerq.ai/v1/preflight?target={_to_slug(name)}</pre>
<a href="/nerq/docs" style="font-size:12px;color:#0d9488">API docs &rarr;</a>
</div>
"""
    page += _page_foot(name, a["category"], "dataset")
    return _set_cache(ck, page)


# ════════════════════════════════════════════════════════════
# ORG PAGES
# ════════════════════════════════════════════════════════════

def _render_org_page(org_name):
    ck = f"org:{org_name}"
    c = _cached(ck)
    if c:
        return c

    with get_db_session() as session:
        rows = session.execute(text("""
            SELECT name, agent_type, trust_score_v2, trust_grade, stars, downloads, description
            FROM agents
            WHERE is_active = true AND LOWER(SPLIT_PART(name, '/', 1)) = :org
            ORDER BY COALESCE(downloads, 0) DESC, COALESCE(stars, 0) DESC
            LIMIT 200
        """), {"org": org_name.lower()}).fetchall()

    if not rows or len(rows) < 2:
        return None

    assets = [dict(zip(["name","type","trust_score","trust_grade","stars","downloads","description"], r)) for r in rows]

    # Aggregate stats
    total = len(assets)
    avg_score = sum(a["trust_score"] or 0 for a in assets) / total if total else 0
    total_stars = sum(a["stars"] or 0 for a in assets)
    total_downloads = sum(a["downloads"] or 0 for a in assets)
    type_counts = {}
    for a in assets:
        t = a["type"] or "other"
        type_counts[t] = type_counts.get(t, 0) + 1

    display_name = org_name
    # Try to get a nicer display name from the first asset
    if assets and "/" in assets[0]["name"]:
        display_name = assets[0]["name"].split("/")[0]

    title = f"{_esc(display_name)} AI Tools & Models {YEAR} | Nerq"
    meta_desc = f"{_esc(display_name)}: {total} AI assets. Avg Trust Score {avg_score:.0f}/100. {_fmt_num(total_stars)} stars. Independent trust analysis."

    canonical = f"{SITE}/org/{_to_slug(org_name)}"

    # Type breakdown
    type_html = " &middot; ".join(f"{v} {k}{'s' if v > 1 else ''}" for k, v in sorted(type_counts.items(), key=lambda x: -x[1]))

    # Asset table
    table_html = ""
    for a in assets[:50]:
        short = a["name"].split("/")[-1] if "/" in a["name"] else a["name"]
        atype = a["type"] or "other"
        route = {"model": "model", "dataset": "dataset", "space": "space", "container": "container"}.get(atype, "agent")
        slug = _to_slug(a["name"])
        sc = a["trust_score"] or 0
        gc = _grade_color(a["trust_grade"])
        table_html += f'<tr><td><a href="/{route}/{slug}" style="color:#0d9488">{_esc(short)}</a></td><td>{atype}</td><td style="color:{gc};font-weight:600">{sc:.0f}</td><td>{_fmt_num(a["stars"])}</td><td>{_fmt_num(a["downloads"])}</td></tr>'

    faq_items = [
        (f"What AI tools does {_esc(display_name)} publish?", f"{_esc(display_name)} has {total} AI assets on Nerq: {type_html}."),
        (f"Are {_esc(display_name)}'s tools safe?", f"Average Trust Score across all {_esc(display_name)} assets: {avg_score:.0f}/100."),
        (f"What is {_esc(display_name)}'s most popular tool?", f"The most popular asset is {_esc(assets[0]['name'])} with {_fmt_num(assets[0]['downloads'])} downloads."),
    ]
    faq_html = "".join(f'<div class="faq-q">{q}</div><div class="faq-a">{a_text}</div>' for q, a_text in faq_items)
    faq_jsonld = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a_text}"}}}}' for q, a_text in faq_items)

    v, vc, _ = _verdict(avg_score)
    page = _page_head(title, meta_desc, canonical, "organization", display_name, avg_score, "")
    page += f"""
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Organization","name":"{_esc(display_name)}","url":"{canonical}","description":"{total} AI assets with average Trust Score {avg_score:.0f}/100"}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{{"@type":"ListItem","position":1,"name":"Nerq","item":"{SITE}"}},{{"@type":"ListItem","position":2,"name":"Organizations","item":"{SITE}/orgs"}},{{"@type":"ListItem","position":3,"name":"{_esc(display_name)}","item":"{canonical}"}}]}}
</script>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{faq_jsonld}]}}
</script>

<nav style="font-size:12px;color:#6b7280;margin-bottom:16px"><a href="/" style="color:#0d9488">Nerq</a> &rsaquo; <a href="/orgs" style="color:#0d9488">Organizations</a> &rsaquo; {_esc(display_name)}</nav>

<h1>{_esc(display_name)} AI Tools & Models — Trust Analysis {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{_esc(display_name)} publishes {total} AI assets on Nerq with an average Trust Score of <strong>{avg_score:.0f}/100</strong>. Total: {_fmt_num(total_stars)} stars, {_fmt_num(total_downloads)} downloads. Asset types: {type_html}. Last analyzed {MONTH_YEAR}.</p>

<div class="score-grid">
{_score_card("Assets", str(total))}
{_score_card("Avg Trust", f"{avg_score:.0f}", vc)}
{_score_card("Total Stars", _fmt_num(total_stars))}
{_score_card("Downloads", _fmt_num(total_downloads))}
</div>

<h2>All Assets by {_esc(display_name)}</h2>
<table class="detail-table">
<tr><th>Name</th><th>Type</th><th>Trust</th><th>Stars</th><th>Downloads</th></tr>
{table_html}
</table>
{f"<p style='font-size:12px;color:#6b7280'>Showing top 50 of {total} assets.</p>" if total > 50 else ""}

<h2>Frequently Asked Questions</h2>
{faq_html}
"""
    page += _page_foot(display_name, None, "organization")
    return _set_cache(ck, page)


# ════════════════════════════════════════════════════════════
# MOUNT FUNCTION
# ════════════════════════════════════════════════════════════

def mount_asset_pages(app):
    """Mount all Phase 2+3 asset page routes."""

    # ── SPACE ROUTES ────────────────────────────
    @app.get("/space/{org}/{space_name}", response_class=HTMLResponse)
    async def space_page_org(org: str, space_name: str):
        html = _render_space_page(f"{org}/{space_name}")
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(f"{org}/{space_name}", bot="404-route")
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

    @app.get("/space/{space_name}", response_class=HTMLResponse)
    async def space_page(space_name: str):
        html = _render_space_page(space_name)
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(space_name, bot="404-route")
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

    @app.get("/spaces", response_class=HTMLResponse)
    async def spaces_hub():
        cached = _cached("spaces_hub")
        if cached:
            return HTMLResponse(cached)
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, downloads, description
                FROM agents WHERE is_active = true AND agent_type = 'space'
                AND description IS NOT NULL AND LENGTH(description) > 10
                ORDER BY COALESCE(downloads, 0) DESC LIMIT 100
            """)).fetchall()
            total = session.execute(text("SELECT COUNT(*) FROM agents WHERE is_active=true AND agent_type='space'")).scalar() or 0

        rows_html = ""
        for r in rows:
            slug = _to_slug(r[0])
            rows_html += f'<tr><td><a href="/space/{slug}" style="color:#0d9488">{_esc(r[0])}</a></td><td style="color:{_grade_color(r[2])}">{(r[1] or 0):.0f}</td><td>{_fmt_num(r[4])}</td></tr>'

        html = _page_head(f"HuggingFace Spaces Trust Directory {YEAR} | Nerq",
                         f"Browse {total:,} HuggingFace Spaces with independent trust scores. Find safe AI demos and apps.",
                         f"{SITE}/spaces", "directory", "spaces", None, None)
        html += f"""
<h1>HuggingFace Spaces — Trust Directory {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{total:,} HuggingFace Spaces indexed with trust scores. Each Space is analyzed for security, maintenance, and community signals.</p>
<table class="detail-table"><tr><th>Space</th><th>Trust</th><th>Downloads</th></tr>{rows_html}</table>
</main>{NERQ_FOOTER}</body></html>"""
        _set_cache("spaces_hub", html)
        return HTMLResponse(html)

    # ── CONTAINER ROUTES ────────────────────────
    @app.get("/container/{org}/{container_name}", response_class=HTMLResponse)
    async def container_page_org(org: str, container_name: str):
        html = _render_container_page(f"{org}/{container_name}")
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(f"{org}/{container_name}", bot="404-route")
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

    @app.get("/container/{container_name}", response_class=HTMLResponse)
    async def container_page(container_name: str):
        html = _render_container_page(container_name)
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(container_name, bot="404-route")
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

    @app.get("/containers", response_class=HTMLResponse)
    async def containers_hub():
        cached = _cached("containers_hub")
        if cached:
            return HTMLResponse(cached)
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, downloads, description
                FROM agents WHERE is_active = true AND agent_type = 'container'
                AND description IS NOT NULL AND LENGTH(description) > 10
                ORDER BY COALESCE(downloads, 0) DESC LIMIT 100
            """)).fetchall()
            total = session.execute(text("SELECT COUNT(*) FROM agents WHERE is_active=true AND agent_type='container'")).scalar() or 0

        rows_html = ""
        for r in rows:
            slug = _to_slug(r[0])
            rows_html += f'<tr><td><a href="/container/{slug}" style="color:#0d9488">{_esc(r[0])}</a></td><td style="color:{_grade_color(r[2])}">{(r[1] or 0):.0f}</td><td>{_fmt_num(r[4])}</td></tr>'

        html = _page_head(f"Docker Container Security Directory {YEAR} | Nerq",
                         f"Security analysis for {total:,} Docker Hub containers. Trust scores, vulnerability data, publisher verification.",
                         f"{SITE}/containers", "directory", "containers", None, None)
        html += f"""
<h1>Docker Container Security Directory {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{total:,} Docker Hub containers analyzed for security, maintenance, and trust. Every pull needs a trust check first.</p>
<table class="detail-table"><tr><th>Container</th><th>Trust</th><th>Pulls</th></tr>{rows_html}</table>
</main>{NERQ_FOOTER}</body></html>"""
        _set_cache("containers_hub", html)
        return HTMLResponse(html)

    # ── DATASET ROUTES ──────────────────────────
    @app.get("/dataset/{org}/{dataset_name}", response_class=HTMLResponse)
    async def dataset_page_org(org: str, dataset_name: str):
        html = _render_dataset_page(f"{org}/{dataset_name}")
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(f"{org}/{dataset_name}", bot="404-route")
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

    @app.get("/dataset/{dataset_name}", response_class=HTMLResponse)
    async def dataset_page(dataset_name: str):
        html = _render_dataset_page(dataset_name)
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(dataset_name, bot="404-route")
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

    @app.get("/datasets", response_class=HTMLResponse)
    async def datasets_hub():
        cached = _cached("datasets_hub")
        if cached:
            return HTMLResponse(cached)
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, downloads, license
                FROM agents WHERE is_active = true AND agent_type = 'dataset'
                AND description IS NOT NULL AND LENGTH(description) > 10
                ORDER BY COALESCE(downloads, 0) DESC LIMIT 100
            """)).fetchall()
            total = session.execute(text("SELECT COUNT(*) FROM agents WHERE is_active=true AND agent_type='dataset'")).scalar() or 0

        rows_html = ""
        for r in rows:
            slug = _to_slug(r[0])
            rows_html += f'<tr><td><a href="/dataset/{slug}" style="color:#0d9488">{_esc(r[0])}</a></td><td style="color:{_grade_color(r[2])}">{(r[1] or 0):.0f}</td><td>{_fmt_num(r[4])}</td><td>{_esc(r[5] or "—")}</td></tr>'

        html = _page_head(f"AI Dataset Trust Directory {YEAR} | Nerq",
                         f"Trust analysis for {total:,} AI datasets. Quality scores, license info, provenance checks.",
                         f"{SITE}/datasets", "directory", "datasets", None, None)
        html += f"""
<h1>AI Dataset Trust & Quality Directory {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{total:,} AI datasets indexed with trust scores. Check quality, licensing, and provenance before training.</p>
<table class="detail-table"><tr><th>Dataset</th><th>Trust</th><th>Downloads</th><th>License</th></tr>{rows_html}</table>
</main>{NERQ_FOOTER}</body></html>"""
        _set_cache("datasets_hub", html)
        return HTMLResponse(html)

    # ── ORG ROUTES ──────────────────────────────
    @app.get("/org/{org_name}", response_class=HTMLResponse)
    async def org_page(org_name: str):
        html = _render_org_page(org_name)
        if html:
            return HTMLResponse(html)
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(org_name, bot="404-route")
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

    @app.get("/orgs", response_class=HTMLResponse)
    async def orgs_hub():
        cached = _cached("orgs_hub")
        if cached:
            return HTMLResponse(cached)
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT SPLIT_PART(name, '/', 1) as org, COUNT(*) as cnt,
                       MAX(stars) as max_stars, AVG(trust_score_v2) as avg_trust
                FROM agents WHERE is_active = true AND name LIKE '%%/%%'
                GROUP BY org HAVING COUNT(*) >= 3
                ORDER BY cnt DESC LIMIT 200
            """)).fetchall()
            total = session.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT SPLIT_PART(name, '/', 1) FROM agents
                    WHERE is_active = true AND name LIKE '%%/%%'
                    GROUP BY 1 HAVING COUNT(*) >= 3
                ) sub
            """)).scalar() or 0

        rows_html = ""
        for r in rows:
            slug = _to_slug(r[0])
            avg = r[3] or 0
            rows_html += f'<tr><td><a href="/org/{slug}" style="color:#0d9488">{_esc(r[0])}</a></td><td>{r[1]}</td><td>{avg:.0f}</td><td>{_fmt_num(r[2])}</td></tr>'

        html = _page_head(f"AI Organizations Directory {YEAR} | Nerq",
                         f"Browse {total:,} AI organizations with trust-scored tools, models, and datasets.",
                         f"{SITE}/orgs", "directory", "orgs", None, None)
        html += f"""
<h1>AI Organizations — Trust Directory {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 16px">{total:,} organizations publishing AI assets, ranked by catalog size. Trust scores aggregated across all published tools.</p>
<table class="detail-table"><tr><th>Organization</th><th>Assets</th><th>Avg Trust</th><th>Top Stars</th></tr>{rows_html}</table>
</main>{NERQ_FOOTER}</body></html>"""
        _set_cache("orgs_hub", html)
        return HTMLResponse(html)

    # ── SITEMAPS ────────────────────────────────

    @app.get("/sitemap-spaces.xml", response_class=Response)
    @app.get("/sitemap-spaces-{chunk}.xml", response_class=Response)
    async def sitemap_spaces(chunk: int = 0):
        cache_key = f"sitemap:spaces:{chunk}"
        cached = _cached(cache_key)
        if cached:
            return Response(cached, media_type="application/xml")
        offset = chunk * 50000
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name FROM agents WHERE is_active = true AND agent_type = 'space'
                AND description IS NOT NULL AND LENGTH(description) > 10
                ORDER BY COALESCE(downloads, 0) DESC
                OFFSET :off LIMIT 50000
            """), {"off": offset}).fetchall()
        urls = [(f"{SITE}/space/{_to_slug(r[0])}", "0.5") for r in rows]
        if chunk == 0:
            urls.insert(0, (f"{SITE}/spaces", "0.7"))
        xml = _sitemap_xml(urls)
        _set_cache(cache_key, xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-containers.xml", response_class=Response)
    async def sitemap_containers():
        cached = _cached("sitemap:containers")
        if cached:
            return Response(cached, media_type="application/xml")
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name FROM agents WHERE is_active = true AND agent_type = 'container'
                AND description IS NOT NULL AND LENGTH(description) > 10
                ORDER BY COALESCE(downloads, 0) DESC LIMIT 50000
            """)).fetchall()
        urls = [(f"{SITE}/container/{_to_slug(r[0])}", "0.7") for r in rows]
        urls.insert(0, (f"{SITE}/containers", "0.8"))
        xml = _sitemap_xml(urls)
        _set_cache("sitemap:containers", xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-datasets.xml", response_class=Response)
    async def sitemap_datasets():
        cached = _cached("sitemap:datasets")
        if cached:
            return Response(cached, media_type="application/xml")
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name FROM agents WHERE is_active = true AND agent_type = 'dataset'
                AND description IS NOT NULL AND LENGTH(description) > 10
                ORDER BY COALESCE(downloads, 0) DESC LIMIT 50000
            """)).fetchall()
        urls = [(f"{SITE}/dataset/{_to_slug(r[0])}", "0.6") for r in rows]
        urls.insert(0, (f"{SITE}/datasets", "0.7"))
        xml = _sitemap_xml(urls)
        _set_cache("sitemap:datasets", xml)
        return Response(xml, media_type="application/xml")

    @app.get("/sitemap-orgs.xml", response_class=Response)
    async def sitemap_orgs():
        cached = _cached("sitemap:orgs")
        if cached:
            return Response(cached, media_type="application/xml")
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT SPLIT_PART(name, '/', 1) as org
                FROM agents WHERE is_active = true AND name LIKE '%%/%%'
                GROUP BY org HAVING COUNT(*) >= 3
                ORDER BY COUNT(*) DESC LIMIT 50000
            """)).fetchall()
        urls = [(f"{SITE}/org/{_to_slug(r[0])}", "0.6") for r in rows]
        urls.insert(0, (f"{SITE}/orgs", "0.7"))
        xml = _sitemap_xml(urls)
        _set_cache("sitemap:orgs", xml)
        return Response(xml, media_type="application/xml")

    logger.info("Mounted asset pages: /space, /container, /dataset, /org + sitemaps")
