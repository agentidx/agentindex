"""
Nerq Answer-Box + Package Pages (BUILD 10, 12, 13)
====================================================
- BUILD 10: /answers/{slug} — Q&A answer-box pages
- BUILD 12: /package/{name} — npm/PyPI package trust pages
- BUILD 13: /package/{a}-vs-{b} — Package comparison pages

Usage in discovery.py:
    from agentindex.seo_answers_packages import mount_answers_packages
    mount_answers_packages(app)
"""

import html
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_db_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.seo_answers_packages")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
DATA_DIR = Path(__file__).parent.parent / "data"

_cache: dict[str, tuple[float, object]] = {}
CACHE_TTL = 3600


def _cached(key):
    e = _cache.get(key)
    if e and (time.time() - e[0]) < CACHE_TTL:
        return e[1]
    return None


def _set_cache(key, val):
    _cache[key] = (time.time(), val)
    return val


def _to_slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _score_fmt(v) -> str:
    if v is None: return "N/A"
    try: return f"{float(v):.0f}"
    except: return "N/A"


def _grade_color(g):
    if not g: return "#6b7280"
    g = g.upper().rstrip("+- ")
    if g in ("A","AA"): return "#065f46"
    if g == "B": return "#1e40af"
    if g == "C": return "#92400e"
    return "#991b1b"


def _grade_pill(grade):
    g = html.escape(grade or "N/A")
    return f'<span style="color:{_grade_color(grade)};font-weight:700">{g}</span>'


def _stars_fmt(v):
    if not v: return "-"
    try:
        n = int(v)
        return f"{n/1000:.1f}k" if n >= 1000 else str(n)
    except: return "-"


def _trunc(s, n=120):
    if not s: return ""
    s = s.strip()
    return (s[:n] + "...") if len(s) > n else s


def _page(title, body, desc="", canonical="", jsonld="", robots="index, follow"):
    canon = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    meta = f'<meta name="description" content="{html.escape(desc)}">' if desc else ""
    ld = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>{meta}
<meta name="robots" content="{robots}">{canon}{ld}
<style>{NERQ_CSS}</style></head><body>{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">{body}</main>
{NERQ_FOOTER}</body></html>"""


def _bc(*parts):
    items = ['<a href="/">nerq</a>']
    for href, label in parts:
        items.append(f'<a href="{href}">{html.escape(label)}</a>' if href else html.escape(label))
    return f'<div class="breadcrumb">{" &rsaquo; ".join(items)}</div>'


def _load_questions() -> list[dict]:
    cached = _cached("questions")
    if cached: return cached
    qf = DATA_DIR / "generated_questions.json"
    if qf.exists():
        with open(qf) as f:
            qs = json.load(f)
        return _set_cache("questions", qs)
    return []


def mount_answers_packages(app):
    """Mount /answers, /package, and related routes."""

    # ════════════════════════════════════════════════════════
    # BUILD 10: Answer-Box Q&A Pages
    # ════════════════════════════════════════════════════════

    @app.get("/answers", response_class=HTMLResponse)
    async def answers_hub():
        questions = _load_questions()
        items = ""
        for q in questions[:100]:
            items += f'<li style="margin:6px 0"><a href="/answers/{q["slug"]}">{html.escape(q["question"])}</a> <span style="color:#6b7280;font-size:13px">({html.escape(q["type"])})</span></li>'

        body = f"""{_bc(("", "Answers"))}
<h1>AI Tool Questions & Answers</h1>
<p class="desc">Direct answers to common questions about AI tools, safety, licensing, and alternatives.</p>
<ul>{items or '<li>No questions generated yet. Run the question generator first.</li>'}</ul>"""

        return HTMLResponse(_page(f"AI Tool FAQ — Questions & Answers {YEAR} | Nerq", body,
            desc=f"Answers to {len(questions)} common questions about AI tool safety, pricing, licensing, and alternatives.",
            canonical=f"{SITE}/answers"))

    @app.get("/answers/{slug}", response_class=HTMLResponse)
    async def answer_page(slug: str):
        questions = _load_questions()
        q = next((x for x in questions if x["slug"] == slug), None)

        if not q:
            # Try to generate on-the-fly from slug
            q = _generate_dynamic_answer(slug)

        if not q:
            return HTMLResponse(_page("Question not found | Nerq",
                f'{_bc(("/answers","Answers"),("","not found"))}<h1>Question not found</h1><p><a href="/answers">Browse all questions</a></p>'),
                status_code=404)

        question = html.escape(q["question"])
        tool_slug = _to_slug(q.get("tool_name") or "")
        tool_display = html.escape(q.get("tool_display") or q.get("tool_name") or "")

        # Related questions
        related = [x for x in questions if x.get("tool_name") == q.get("tool_name") and x["slug"] != slug][:5]
        related_html = ""
        if related:
            links = "".join(f'<li><a href="/answers/{r["slug"]}">{html.escape(r["question"])}</a></li>' for r in related)
            related_html = f"<h2>Related Questions</h2><ul>{links}</ul>"

        # Links to reports
        tool_links = ""
        if tool_slug:
            tool_links = f"""<h2>More About {tool_display}</h2>
<ul>
<li><a href="/is-{tool_slug}-safe">{tool_display} Safety Report</a></li>
<li><a href="/alternatives/{tool_slug}">{tool_display} Alternatives</a></li>
<li><a href="/guide/{tool_slug}">{tool_display} Guide</a></li>
<li><a href="/improve/{tool_slug}">Improve {tool_display} Trust Score</a></li>
</ul>"""

        # FAQ schema
        faq_ld = json.dumps({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{
                "@type": "Question", "name": q["question"],
                "acceptedAnswer": {"@type": "Answer", "text": q["answer_short"].replace("**", "")}
            }]
        })

        body = f"""{_bc(("/answers","Answers"),("", q["question"][:50]))}
<h1>{question}</h1>
<div style="font-size:1.1em;line-height:1.7;margin:16px 0;padding:16px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px">
{q["answer_short"]}
</div>
<h2>Details</h2>
<p>{q.get("answer_detail","")}</p>
{f'<p style="color:#6b7280">Trust Score: {_score_fmt(q.get("score"))}/100 ({_grade_pill(q.get("grade"))}). Stars: {_stars_fmt(q.get("stars"))}.</p>' if q.get("score") else ''}
{related_html}{tool_links}"""

        title = f"{q['question']} | Nerq"
        desc = q["answer_short"].replace("**", "")[:160]

        return HTMLResponse(_page(title, body, desc=desc,
            canonical=f"{SITE}/answers/{slug}", jsonld=faq_ld))

    # ════════════════════════════════════════════════════════
    # BUILD 12: Package Pages
    # ════════════════════════════════════════════════════════

    @app.get("/package/{org}/{pkg_name}", response_class=HTMLResponse)
    async def package_page_org(org: str, pkg_name: str):
        return await _render_package_page(f"{org}/{pkg_name}")

    @app.get("/package/{pkg_name}", response_class=HTMLResponse)
    async def package_page(pkg_name: str):
        if "-vs-" in pkg_name:
            return await _render_package_vs(pkg_name)
        return await _render_package_page(pkg_name)

    async def _render_package_page(query: str):
        cache_key = f"pkg:{query}"
        cached = _cached(cache_key)
        if cached:
            return HTMLResponse(cached)

        with get_db_session() as session:
            # Search in agents table for packages
            row = session.execute(text("""
                SELECT el.id, el.name, el.trust_score_v2, el.trust_grade, el.stars,
                       el.description, el.category, a.language, el.author, el.source,
                       el.source_url, el.license, el.security_score, el.activity_score,
                       el.documentation_score, el.popularity_score, el.eu_risk_class,
                       el.downloads, el.agent_type
                FROM entity_lookup el
                LEFT JOIN agents a ON a.id = el.id
                WHERE (el.name_lower = :q OR el.name_lower LIKE :p) AND el.is_active = true
                ORDER BY COALESCE(el.stars, 0) DESC
                LIMIT 1
            """), {"q": query.lower(), "p": f"%{query.replace('-','%')}%"}).fetchone()

            if not row:
                return HTMLResponse(_page("Package not found | Nerq",
                    f'{_bc(("/package","Packages"),("","not found"))}<h1>Package not found</h1>'
                    f'<p>Could not find &ldquo;{html.escape(query)}&rdquo;.</p>'
                    f'<p><a href="/discover">Search all indexed assets</a></p>'),
                    status_code=404)

            cols = ["id","name","trust_score_v2","trust_grade","stars","description",
                    "category","language","author","source","source_url","license",
                    "security_score","activity_score","documentation_score",
                    "popularity_score","eu_risk_class","downloads","agent_type"]
            pkg = dict(zip(cols, row))

            # Alternatives
            alts = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, description
                FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND id != CAST(:tid AS uuid) AND category = :cat
                ORDER BY COALESCE(trust_score_v2,0) DESC LIMIT 8
            """), {"tid": str(pkg["id"]), "cat": pkg.get("category") or ""}).fetchall()

        name = html.escape(pkg["name"])
        slug = _to_slug(pkg["name"])
        ts = pkg.get("trust_score_v2") or 0
        tg = pkg.get("trust_grade")
        lic = html.escape(pkg.get("license") or "Not specified")
        dl = pkg.get("downloads")
        dl_fmt = f"{int(dl):,}" if dl else "N/A"
        src = pkg.get("source") or "unknown"
        sec = pkg.get("security_score") or 0

        # Trust verdict
        if ts >= 80:
            verdict = f'<div style="background:#ecfdf5;border:1px solid #a7f3d0;padding:16px;margin:16px 0;border-radius:8px"><strong>Safe to use.</strong> {name} scores {_score_fmt(ts)}/100 with grade {_grade_pill(tg)}. Low risk for production use.</div>'
        elif ts >= 60:
            verdict = f'<div style="background:#fffbeb;border:1px solid #fde68a;padding:16px;margin:16px 0;border-radius:8px"><strong>Use with caution.</strong> {name} scores {_score_fmt(ts)}/100. Review security details before production use.</div>'
        else:
            verdict = f'<div style="background:#fef2f2;border:1px solid #fecaca;padding:16px;margin:16px 0;border-radius:8px"><strong>Higher risk.</strong> {name} scores {_score_fmt(ts)}/100. Carefully evaluate before using in production.</div>'

        # Score cards
        cards = f"""<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin:16px 0">
<div style="text-align:center;border:1px solid #e5e7eb;padding:16px;border-radius:8px"><div style="font-size:2em;font-weight:700">{_score_fmt(ts)}</div><div style="color:#6b7280">Trust Score</div></div>
<div style="text-align:center;border:1px solid #e5e7eb;padding:16px;border-radius:8px"><div style="font-size:2em">{_grade_pill(tg)}</div><div style="color:#6b7280">Grade</div></div>
<div style="text-align:center;border:1px solid #e5e7eb;padding:16px;border-radius:8px"><div style="font-size:2em;font-weight:700">{_score_fmt(sec)}</div><div style="color:#6b7280">Security</div></div>
<div style="text-align:center;border:1px solid #e5e7eb;padding:16px;border-radius:8px"><div style="font-size:2em;font-weight:700">{dl_fmt}</div><div style="color:#6b7280">Downloads</div></div>
</div>"""

        # Details
        details = f"""<h2>Package Details</h2>
<table>
<tr><td style="font-weight:600">Name</td><td>{name}</td></tr>
<tr><td style="font-weight:600">Author</td><td>{html.escape(pkg.get('author') or 'Unknown')}</td></tr>
<tr><td style="font-weight:600">License</td><td>{lic}</td></tr>
<tr><td style="font-weight:600">Language</td><td>{html.escape(pkg.get('language') or '-')}</td></tr>
<tr><td style="font-weight:600">Source</td><td>{html.escape(src)}{f' — <a href="{html.escape(pkg.get("source_url",""))}">view</a>' if pkg.get("source_url") else ''}</td></tr>
<tr><td style="font-weight:600">Category</td><td>{html.escape(pkg.get('category') or '-')}</td></tr>
<tr><td style="font-weight:600">Stars</td><td>{_stars_fmt(pkg.get('stars'))}</td></tr>
<tr><td style="font-weight:600">EU AI Act</td><td>{html.escape(pkg.get('eu_risk_class') or 'Not classified')}</td></tr>
</table>"""

        # Security
        security = f"""<h2>Security Analysis</h2>
<table>
<tr><td style="font-weight:600">Security Score</td><td>{_score_fmt(sec)}/100</td></tr>
<tr><td style="font-weight:600">Activity Score</td><td>{_score_fmt(pkg.get('activity_score'))}/100</td></tr>
<tr><td style="font-weight:600">Documentation</td><td>{_score_fmt(pkg.get('documentation_score'))}/100</td></tr>
<tr><td style="font-weight:600">Popularity</td><td>{_score_fmt(pkg.get('popularity_score'))}/100</td></tr>
</table>
<p><a href="/is-{slug}-safe">View full safety report &rarr;</a></p>"""

        # CI action
        ci_section = f"""<h2>Add to Your CI</h2>
<p>Automatically check {name} trust score in your CI pipeline:</p>
<pre style="background:#1e293b;color:#e2e8f0;padding:16px;border-radius:8px;font-size:13px;overflow-x:auto"># Check trust score before deploy
curl -s "https://nerq.ai/v1/preflight?target={html.escape(pkg['name'])}" | jq '.trust_score'</pre>"""

        # Alternatives
        alt_html = ""
        if alts:
            rows = ""
            for i, a in enumerate(alts, 1):
                aname, ascore, agrade, astars, adesc = a
                aslug = _to_slug(aname)
                rows += f'<tr><td>{i}</td><td><a href="/package/{aslug}">{html.escape(aname)}</a></td><td>{_score_fmt(ascore)}</td><td>{_grade_pill(agrade)}</td><td>{_stars_fmt(astars)}</td></tr>'
            alt_html = f"""<h2>Alternatives</h2>
<table><thead><tr><th>#</th><th>Name</th><th>Trust</th><th>Grade</th><th>Stars</th></tr></thead><tbody>{rows}</tbody></table>
<p><a href="/alternatives/{slug}">View all alternatives &rarr;</a></p>"""

        # FAQ
        faq_items = [
            (f"Is {pkg['name']} safe?", f"Trust Score: {_score_fmt(ts)}/100, Grade: {html.escape(tg or 'N/A')}. See the full safety report for details."),
            (f"Does {pkg['name']} have vulnerabilities?", f"Security Score: {_score_fmt(sec)}/100. Check /is-{slug}-safe for current vulnerability data."),
            (f"What license is {pkg['name']}?", f"License: {lic}."),
        ]
        faq = "<h2>FAQ</h2>"
        faq_ld_items = []
        for fq, fa in faq_items:
            faq += f'<details style="margin:8px 0;border:1px solid #e5e7eb;padding:12px;border-radius:6px"><summary style="cursor:pointer;font-weight:600">{html.escape(fq)}</summary><p style="margin-top:8px;color:#4b5563">{fa}</p></details>'
            faq_ld_items.append({"@type":"Question","name":fq,"acceptedAnswer":{"@type":"Answer","text":fa}})

        jsonld = json.dumps({"@context":"https://schema.org","@type":"FAQPage","mainEntity":faq_ld_items})

        title = f"Is {pkg['name']} Safe? Security & Trust Analysis | Nerq"
        desc = f"{pkg['name']}: Trust Score {_score_fmt(ts)}/100, Grade {html.escape(tg or 'N/A')}. Security analysis, license, alternatives."

        body = f"""{_bc(("/package","Packages"),("",pkg['name'][:60]))}
<h1>{name}</h1>
<p class="desc">{html.escape(_trunc(pkg.get('description') or '', 200))}</p>
{verdict}{cards}{details}{security}{ci_section}{alt_html}{faq}"""

        result = _page(title, body, desc=desc, canonical=f"{SITE}/package/{_to_slug(pkg['name'])}", jsonld=jsonld)
        _set_cache(cache_key, result)
        return HTMLResponse(result)

    # ── Package hub ────────────────────────────────────────
    @app.get("/package", response_class=HTMLResponse)
    @app.get("/packages", response_class=HTMLResponse)
    async def packages_hub():
        cached = _cached("packages_hub")
        if cached:
            return HTMLResponse(cached)

        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name, trust_score_v2, trust_grade, stars, downloads, language
                FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND agent_type IN ('package', 'tool', 'library')
                ORDER BY COALESCE(downloads, 0) DESC, COALESCE(stars, 0) DESC
                LIMIT 100
            """)).fetchall()
            if len(rows) < 20:
                rows = session.execute(text("""
                    SELECT name, trust_score_v2, trust_grade, stars, downloads, language
                    FROM entity_lookup WHERE is_active = true AND trust_score_v2 IS NOT NULL
                    ORDER BY COALESCE(stars, 0) DESC LIMIT 100
                """)).fetchall()

        trows = ""
        for i, r in enumerate(rows, 1):
            name, score, grade, stars, dl, lang = r
            slug = _to_slug(name)
            dl_fmt = f"{int(dl):,}" if dl else "-"
            trows += f'<tr><td>{i}</td><td><a href="/package/{slug}">{html.escape(name)}</a></td><td>{_score_fmt(score)}</td><td>{_grade_pill(grade)}</td><td>{_stars_fmt(stars)}</td><td>{dl_fmt}</td><td>{html.escape(lang or "-")}</td></tr>'

        table = f'<table><thead><tr><th>#</th><th>Package</th><th>Trust</th><th>Grade</th><th>Stars</th><th>Downloads</th><th>Language</th></tr></thead><tbody>{trows}</tbody></table>'

        body = f"""{_bc(("","Packages"))}
<h1>Package Security & Trust</h1>
<p class="desc">Trust scores for npm, PyPI, and other packages. Updated {TODAY}.</p>
{table}"""

        result = _page(f"Package Security & Trust Analysis {YEAR} | Nerq", body,
            desc="Security and trust analysis for npm, PyPI, and software packages. Independent scoring.",
            canonical=f"{SITE}/packages")
        _set_cache("packages_hub", result)
        return HTMLResponse(result)

    # ════════════════════════════════════════════════════════
    # BUILD 13: Package Comparison Pages
    # ════════════════════════════════════════════════════════

    async def _render_package_vs(comparison_slug: str):
        parts = comparison_slug.split("-vs-", 1)
        slug_a, slug_b = parts[0], parts[1]
        if slug_a > slug_b:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(f"/package/{slug_b}-vs-{slug_a}", status_code=301)

        cache_key = f"pkg_vs:{slug_a}:{slug_b}"
        cached = _cached(cache_key)
        if cached:
            return HTMLResponse(cached)

        with get_db_session() as session:
            def find_pkg(s):
                r = session.execute(text("""
                    SELECT name, trust_score_v2, trust_grade, stars, description,
                           license, language, security_score, activity_score,
                           documentation_score, downloads, source
                    FROM entity_lookup WHERE (name_lower = :q OR name_lower LIKE :p)
                      AND is_active = true ORDER BY COALESCE(stars,0) DESC LIMIT 1
                """), {"q": s.lower(), "p": f"%{s.replace('-','%')}%"}).fetchone()
                if r:
                    cols = ["name","score","grade","stars","desc","license","language",
                            "security","activity","docs","downloads","source"]
                    return dict(zip(cols, r))
                return None

            a = find_pkg(slug_a)
            b = find_pkg(slug_b)

        if not a or not b:
            missing = slug_a if not a else slug_b
            return HTMLResponse(_page("Package not found | Nerq",
                f'{_bc(("/package","Packages"),("","not found"))}<h1>Package not found</h1><p>Could not find &ldquo;{html.escape(missing)}&rdquo;.</p>'),
                status_code=404)

        na, nb = html.escape(a["name"]), html.escape(b["name"])
        sa, sb = a.get("score") or 0, b.get("score") or 0
        winner = na if sa >= sb else nb

        verdict = f'<div style="background:#ecfdf5;border:1px solid #a7f3d0;padding:16px;margin:16px 0;border-radius:8px"><strong>Which is safer?</strong> {winner} scores higher with {_score_fmt(max(sa,sb))}/100 vs {_score_fmt(min(sa,sb))}/100.</div>'

        rows = ""
        for label, va, vb in [
            ("Trust Score", _score_fmt(sa), _score_fmt(sb)),
            ("Grade", _grade_pill(a.get("grade")), _grade_pill(b.get("grade"))),
            ("Security", _score_fmt(a.get("security")), _score_fmt(b.get("security"))),
            ("Activity", _score_fmt(a.get("activity")), _score_fmt(b.get("activity"))),
            ("Stars", _stars_fmt(a.get("stars")), _stars_fmt(b.get("stars"))),
            ("Downloads", f'{int(a["downloads"]):,}' if a.get("downloads") else "-", f'{int(b["downloads"]):,}' if b.get("downloads") else "-"),
            ("License", html.escape(a.get("license") or "-"), html.escape(b.get("license") or "-")),
            ("Language", html.escape(a.get("language") or "-"), html.escape(b.get("language") or "-")),
        ]:
            rows += f"<tr><td style='font-weight:600'>{label}</td><td>{va}</td><td>{vb}</td></tr>"

        table = f"<table><thead><tr><th>Metric</th><th>{na}</th><th>{nb}</th></tr></thead><tbody>{rows}</tbody></table>"

        faq_ld = json.dumps({"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
            {"@type":"Question","name":f"Is {a['name']} better than {b['name']}?",
             "acceptedAnswer":{"@type":"Answer","text":f"{a['name']} scores {_score_fmt(sa)} and {b['name']} scores {_score_fmt(sb)} on Nerq Trust Score."}}
        ]})

        slug_a_safe, slug_b_safe = _to_slug(a["name"]), _to_slug(b["name"])
        links = f"""<p style="margin-top:16px">
<a href="/package/{slug_a_safe}">{na} details</a> &middot;
<a href="/package/{slug_b_safe}">{nb} details</a> &middot;
<a href="/is-{slug_a_safe}-safe">{na} safety</a> &middot;
<a href="/is-{slug_b_safe}-safe">{nb} safety</a>
</p>"""

        title = f"{a['name']} vs {b['name']} — Package Security Comparison | Nerq"
        desc = f"Compare {a['name']} and {b['name']}: trust scores, security, downloads, and license."

        body = f"""{_bc(("/package","Packages"),("",f"{na} vs {nb}"))}
<h1>{na} vs {nb}</h1>
<p class="desc">Side-by-side security and trust comparison. Updated {TODAY}.</p>
{verdict}{table}{links}"""

        result = _page(title, body, desc=desc,
            canonical=f"{SITE}/package/{slug_a}-vs-{slug_b}", jsonld=faq_ld)
        _set_cache(cache_key, result)
        return HTMLResponse(result)

    # ── Sitemaps ───────────────────────────────────────────

    @app.get("/sitemap-answers.xml", response_class=Response)
    async def sitemap_answers():
        questions = _load_questions()
        urls = [(f"{SITE}/answers/{q['slug']}", "0.6") for q in questions]  # All questions
        urls.insert(0, (f"{SITE}/answers", "0.7"))
        return Response(_sitemap_xml(urls), media_type="application/xml")

    @app.get("/sitemap-packages.xml", response_class=Response)
    async def sitemap_packages():
        """First chunk of package sitemap."""
        return await _sitemap_packages_chunk(0)

    @app.get("/sitemap-packages-{chunk}.xml", response_class=Response)
    async def sitemap_packages_chunked(chunk: int):
        return await _sitemap_packages_chunk(chunk)

    async def _sitemap_packages_chunk(chunk: int):
        cache_key = f"sitemap:packages:{chunk}"
        cached = _cached(cache_key)
        if cached:
            return Response(cached, media_type="application/xml")

        offset = chunk * 50000
        with get_db_session() as session:
            rows = session.execute(text("""
                SELECT name FROM entity_lookup
                WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND (source LIKE '%%npm%%' OR source LIKE '%%pypi%%'
                       OR agent_type IN ('package', 'tool', 'library'))
                  AND description IS NOT NULL AND LENGTH(description) > 10
                ORDER BY COALESCE(downloads, 0) DESC, COALESCE(stars, 0) DESC
                OFFSET :off LIMIT 50000
            """), {"off": offset}).fetchall()

        if not rows:
            return Response('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
                          media_type="application/xml")

        urls = [(f"{SITE}/package/{_to_slug(r[0])}", "0.8") for r in rows]
        if chunk == 0:
            urls.insert(0, (f"{SITE}/packages", "0.8"))
            # Add comparison pairs for top 500
            pkg_names = [r[0] for r in rows[:500]]
            seen_vs = set()
            for i in range(min(500, len(pkg_names))):
                for j in range(i + 1, min(500, len(pkg_names))):
                    if len(seen_vs) >= 1000:
                        break
                    sa, sb = sorted([_to_slug(pkg_names[i]), _to_slug(pkg_names[j])])
                    key = f"{sa}-vs-{sb}"
                    if key not in seen_vs and sa != sb and len(sa) > 1 and len(sb) > 1:
                        seen_vs.add(key)
                        urls.append((f"{SITE}/package/{key}", "0.7"))
                if len(seen_vs) >= 1000:
                    break

        xml = _sitemap_xml(urls)
        _set_cache(cache_key, xml)
        return Response(xml, media_type="application/xml")

    logger.info("Mounted: /answers, /package, /package/{a}-vs-{b}, sitemaps")


def _generate_dynamic_answer(slug: str) -> dict | None:
    """Try to generate an answer from a slug like 'is-langchain-safe'."""
    parts = slug.split("-")
    if len(parts) < 3:
        return None

    # Try to extract tool name and question pattern
    question = slug.replace("-", " ").title()
    # Find which tool this is about
    with get_db_session() as session:
        for length in range(len(parts), 1, -1):
            for start in range(len(parts) - length + 1):
                candidate = "-".join(parts[start:start+length])
                row = session.execute(text("""
                    SELECT name, trust_score_v2, trust_grade, stars, license, description
                    FROM entity_lookup WHERE name_lower LIKE :p AND is_active = true
                    ORDER BY COALESCE(stars,0) DESC LIMIT 1
                """), {"p": f"%{candidate.replace('-','%')}%"}).fetchone()
                if row:
                    from agentindex.intelligence.question_generator import _generate_answer, _clean_name
                    tool = {"name":row[0],"score":row[1],"grade":row[2],"stars":row[3],
                            "license":row[4],"description":row[5],"category":"","source":"","security_score":0}
                    display = _clean_name(row[0])
                    # Guess question type
                    qtype = "safety"
                    if "free" in slug or "pric" in slug: qtype = "pricing"
                    elif "licen" in slug: qtype = "licensing"
                    elif "review" in slug: qtype = "review"
                    elif "alternative" in slug: qtype = "alternatives"
                    elif "what" in slug: qtype = "overview"

                    ans = _generate_answer(question, qtype, tool, display)
                    if ans:
                        return {
                            "slug": slug, "question": question, "type": qtype,
                            "tool_name": row[0], "tool_display": display,
                            "answer_short": ans["short"], "answer_detail": ans["detail"],
                            "score": row[1], "grade": row[2], "stars": row[3],
                        }
    return None


def _sitemap_xml(urls):
    entries = ""
    for url, prio in urls:
        entries += f"<url><loc>{html.escape(url)}</loc><lastmod>{TODAY}</lastmod><priority>{prio}</priority></url>\n"
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{entries}</urlset>'
