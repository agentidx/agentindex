"""
Universal URL Pattern Routes — 23 new patterns
================================================
All patterns resolve from agents + software_registry + entity_ratings.
Reuses _resolve_any from demand_pages.

Usage:
    from agentindex.pattern_routes import mount_pattern_routes
    mount_pattern_routes(app)
"""

import html as html_mod
import logging
import re
import time
from datetime import date

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER, render_hreflang

logger = logging.getLogger("nerq.patterns")

SITE = "https://nerq.ai"
TODAY = date.today().isoformat()
YEAR = date.today().year
MY = date.today().strftime("%B %Y")

_cache = {}
CACHE_TTL = 3600

def _c(k):
    e = _cache.get(k)
    return e[1] if e and (time.time() - e[0]) < CACHE_TTL else None

def _sc(k, v):
    _cache[k] = (time.time(), v)
    return v

def _esc(t):
    return html_mod.escape(str(t)) if t else ""

def _slug(n):
    return re.sub(r"[^a-z0-9]+", "-", n.lower().strip()).strip("-")

def _fmt(n):
    if n is None: return "0"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(int(n))

def _gc(g):
    if not g: return "#6b7280"
    return {"A": "#16a34a", "B": "#0d9488", "C": "#ca8a04", "D": "#f97316"}.get(g[0].upper(), "#dc2626")

def _resolve(slug):
    """Universal resolver using centralized entity resolution.
    Normalizes slug (nord-vpn → nordvpn), checks software_registry before agents.
    Returns dict with entity data including CVE counts for security pages.
    """
    from agentindex.agent_safety_pages import _resolve_entity, _lookup_agent

    # Try centralized resolution (consumer overrides + software_registry + websites)
    resolved = _resolve_entity(slug)
    if not resolved:
        norm = slug.lower().replace("-", "").replace("_", "").replace(" ", "")
        if norm != slug.lower():
            resolved = _resolve_entity(norm)

    if resolved:
        return {
            "name": resolved.get("name", slug),
            "score": resolved.get("trust_score", 50),
            "grade": resolved.get("trust_grade", "D"),
            "stars": resolved.get("stars", 0),
            "downloads": resolved.get("stars", 0),
            "desc": resolved.get("description", ""),
            "cat": resolved.get("category", ""),
            "author": resolved.get("author", "Unknown"),
            "url": resolved.get("source_url", ""),
            "license": "",
            "type": resolved.get("source", ""),
            "cve_count": resolved.get("cve_count") or 0,
            "cve_critical": resolved.get("cve_critical") or 0,
            "security_score": resolved.get("security_score"),
            "registry": resolved.get("registry", ""),
        }

    # Fallback to agents
    agent = _lookup_agent(slug)
    if not agent:
        norm = slug.replace("-", "").replace("_", "")
        if norm != slug:
            agent = _lookup_agent(norm)
    if agent:
        return {
            "name": agent.get("name", slug), "score": agent.get("trust_score") or 0,
            "grade": agent.get("trust_grade", "N/A"), "stars": agent.get("stars", 0),
            "downloads": 0, "desc": agent.get("description", ""),
            "cat": agent.get("category", ""), "author": agent.get("author", "Unknown"),
            "url": agent.get("source_url", ""), "license": "", "type": "",
            "cve_count": 0, "cve_critical": 0, "security_score": None, "registry": "",
        }
    return None

def _faq(items):
    h = "".join(f'<div style="font-weight:600;font-size:14px;padding:12px 0;border-bottom:1px solid #e5e7eb">{q}</div><div style="font-size:13px;color:#374151;padding:8px 0 12px">{a}</div>' for q, a in items)
    j = ",".join(f'{{"@type":"Question","name":"{q}","acceptedAnswer":{{"@type":"Answer","text":"{a}"}}}}' for q, a in items)
    return h, f'<script type="application/ld+json">{{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{j}]}}</script>'

def _head(title, desc, canonical, extra=""):
    _path = canonical.replace("https://nerq.ai", "") if canonical else ""
    _hreflang = render_hreflang(_path) if _path else ""
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title><meta name="description" content="{_esc(desc)}">
<link rel="canonical" href="{canonical}">
{_hreflang}
<meta property="og:title" content="{_esc(title)}"><meta property="og:description" content="{_esc(desc)}">
<meta property="og:url" content="{canonical}"><meta name="twitter:card" content="summary">
<meta name="citation_title" content="{_esc(title)}"><meta name="citation_author" content="Nerq">
<meta name="citation_date" content="{TODAY}"><meta name="robots" content="max-snippet:-1">
{extra}{NERQ_CSS}
<style>table{{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}}th{{text-align:left;padding:8px;border-bottom:2px solid #e5e7eb;color:#6b7280}}td{{padding:8px;border-bottom:1px solid #e5e7eb}}.links{{display:flex;flex-wrap:wrap;gap:6px;font-size:12px;margin:16px 0}}.links a{{color:#0d9488}}</style>
</head><body>{NERQ_NAV}<main class="container" style="max-width:900px;margin:0 auto;padding:24px">"""

def _xlinks(slug):
    """Cross-links to ALL patterns for same entity."""
    return f"""<div class="links">
<a href="/is-{slug}-safe">Safe?</a> <a href="/is-{slug}-legit">Legit?</a> <a href="/is-{slug}-a-scam">Scam?</a>
<a href="/is-{slug}-spyware">Spyware?</a> <a href="/privacy/{slug}">Privacy</a> <a href="/pros-cons/{slug}">Pros/Cons</a>
<a href="/review/{slug}">Review</a> <a href="/what-is/{slug}">What is it?</a> <a href="/who-owns/{slug}">Who owns?</a>
<a href="/alternatives/{slug}">Alternatives</a> <a href="/guide/use-{slug}-safely">Use safely</a>
<a href="/is-{slug}-safe-for-kids">Kids?</a> <a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a>
</div>"""

def _foot(slug=""):
    return f"""{_xlinks(slug) if slug else ""}
<p style="font-size:12px;color:#6b7280;margin-top:16px">Updated {MY}. Trust scores based on automated analysis.</p>
</main>{NERQ_FOOTER}</body></html>"""

def _pattern_page(slug, pattern_key, title_tmpl, question, verdict_pos, verdict_neg, focus_text):
    """Generic pattern page builder."""
    ck = f"pat:{pattern_key}:{slug}"
    c = _c(ck)
    if c: return c

    a = _resolve(slug)
    if not a:
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(slug, bot="pattern-404")
        except Exception:
            pass
        return None

    nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
    sc = a.get("score") or 0; gr = a.get("grade") or "D"
    v = verdict_pos if sc >= 60 else verdict_neg
    vc = "#16a34a" if sc >= 60 else "#dc2626"

    title = title_tmpl.replace("{name}", _esc(nm)).replace("{year}", str(YEAR))
    canonical = f"{SITE}/{pattern_key.replace('_','/')}/{slug}" if "/" in pattern_key else f"{SITE}/{pattern_key}-{slug}" if not pattern_key.startswith("is-") else f"{SITE}/is-{slug}-{pattern_key.replace('is-','')}"

    # Build canonical URL properly
    if pattern_key in ("fake","a-virus","safe-to-download","safe-to-buy-from","worth-it","encrypted","down"):
        canonical = f"{SITE}/is-{slug}-{pattern_key}"
    elif pattern_key.startswith("does-"):
        canonical = f"{SITE}/{pattern_key.replace('{slug}', slug)}"
    elif pattern_key.startswith("should-"):
        canonical = f"{SITE}/should-i-use-{slug}"
    elif "/" in pattern_key:
        canonical = f"{SITE}/{pattern_key}/{slug}"
    else:
        canonical = f"{SITE}/{pattern_key}/{slug}"

    faq_items = [
        (question.replace("{name}", _esc(nm)), f"{_esc(nm)} Trust Score: {sc:.0f}/100 ({gr}). Verdict: {v.lower()}. {focus_text}"),
        (f"Can I trust {_esc(nm)}?", f"{'Yes — strong trust signals.' if sc >= 60 else 'Exercise caution.'} Score: {sc:.0f}/100."),
        (f"What do others say about {_esc(nm)}?", f"{_fmt(a.get('downloads'))} users. {_fmt(a.get('stars'))} stars. Grade: {gr}."),
    ]
    faq_html, faq_ld = _faq(faq_items)

    meta = f'<meta name="nerq:type" content="{pattern_key}"><meta name="nerq:entity" content="{_esc(nm)}"><meta name="nerq:score" content="{sc:.0f}"><meta name="nerq:verdict" content="{v}"><meta name="nerq:updated" content="{TODAY}">'

    page = _head(title[:60], f"{_esc(nm)}: {v}. Trust Score {sc:.0f}/100 ({gr}). Independent analysis {MY}."[:160], canonical, meta + faq_ld)
    page += f"""
<h1>{_esc(title)}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(nm)} has a Nerq Trust Score of <strong>{sc:.0f}/100</strong> ({gr}). Verdict: <strong style="color:{vc}">{v}</strong>. {_esc(focus_text)} Published by {_esc(a.get('author','Unknown'))}. {_fmt(a.get('downloads'))} users. Updated {MY}.</p>
<div style="display:inline-block;padding:10px 20px;font-weight:700;font-size:18px;color:{vc};border:2px solid {vc};margin:12px 0">{v}</div>
<h2>Analysis</h2>
<table>
<tr><th>Trust Score</th><td style="color:{vc};font-weight:700">{sc:.0f}/100 ({gr})</td></tr>
<tr><th>Publisher</th><td>{_esc(a.get('author','Unknown'))}</td></tr>
<tr><th>Users</th><td>{_fmt(a.get('downloads'))}</td></tr>
<tr><th>Stars</th><td>{_fmt(a.get('stars'))}</td></tr>
<tr><th>License</th><td>{_esc(a.get('license') or 'Not specified')}</td></tr>
<tr><th>Category</th><td>{_esc(a.get('cat') or 'N/A')}</td></tr>
</table>
<h2>FAQ</h2>{faq_html}"""
    page += _foot(slug)
    return _sc(ck, page)


def _hacked_page(slug):
    """Specialized /was-X-hacked page with CVE data and incident history.

    Content is genuinely unique vs /safe/ — focuses on breach history,
    CVE counts, security incidents, and incident response assessment.
    """
    import json as _json

    ck = f"hacked:{slug}"
    c = _c(ck)
    if c:
        return c

    a = _resolve(slug)
    if not a:
        try:
            from agentindex.agent_safety_pages import _queue_for_crawling
            _queue_for_crawling(slug, bot="hacked-404")
        except Exception:
            pass
        return None

    nm = a["name"].split("/")[-1] if "/" in a.get("name", "") else a.get("name", "")
    sc = a.get("score") or 0
    gr = a.get("grade") or "D"
    cve_count = a.get("cve_count") or 0
    cve_critical = a.get("cve_critical") or 0
    sec_score = a.get("security_score")
    registry = a.get("registry") or ""
    author = a.get("author") or "Unknown"
    desc = a.get("desc") or ""

    # Determine incident status and verdict
    if cve_count > 10:
        verdict = "Multiple Reported Vulnerabilities"
        verdict_detail = f"{_esc(nm)} has {cve_count} publicly reported security vulnerabilities ({cve_critical} critical). This does not necessarily mean a breach occurred, but indicates known security issues that have been disclosed."
        vc = "#dc2626"
        incident_status = "vulnerabilities_found"
    elif cve_count > 0:
        verdict = f"{cve_count} Known Vulnerabilities"
        verdict_detail = f"As of {MY}, {_esc(nm)} has {cve_count} publicly reported security vulnerabilities. These have been disclosed through the CVE database and may have been patched."
        vc = "#ca8a04"
        incident_status = "minor_vulnerabilities"
    else:
        verdict = "No Publicly Reported Incidents"
        verdict_detail = f"As of {MY}, {_esc(nm)} has no publicly reported security breaches, hacks, or CVE entries in the databases Nerq monitors. This covers the National Vulnerability Database (NVD), GitHub Security Advisories, and OSV.dev."
        vc = "#16a34a"
        incident_status = "clean"

    # Security assessment paragraph (unique to /was-X-hacked)
    if sec_score is not None and sec_score > 0:
        sec_label = "strong" if sec_score >= 80 else "adequate" if sec_score >= 60 else "below average" if sec_score >= 40 else "poor"
        sec_para = f"Nerq's automated security analysis rates {_esc(nm)}'s security posture as <strong>{sec_label}</strong> (security dimension score: {sec_score:.0f}/100). "
    else:
        sec_para = ""

    if registry:
        coverage = f"This assessment covers {_esc(nm)} as indexed from the {_esc(registry)} registry. "
    else:
        coverage = ""

    title = f"Was {_esc(nm)} Hacked? Security Incident History {YEAR} | Nerq"
    canonical = f"{SITE}/was-{slug}-hacked"

    # FAQ — genuinely different from /safe/ FAQ
    faq_items = [
        (f"Has {_esc(nm)} been hacked?", verdict_detail),
        (f"How many CVEs does {_esc(nm)} have?",
         f"{_esc(nm)} has {cve_count} CVE entries ({cve_critical} critical). CVEs are publicly disclosed vulnerabilities tracked by MITRE and the NVD."),
        (f"Is {_esc(nm)} safe to use after a breach?",
         f"{'With no reported breaches, {0} appears safe based on available data.'.format(_esc(nm)) if cve_count == 0 else 'Despite known vulnerabilities, {0} maintains a Trust Score of {1:.0f}/100. Check if patches are available for disclosed CVEs before use.'.format(_esc(nm), sc)}"),
        (f"Where can I check {_esc(nm)}'s security history?",
         f"Nerq monitors NVD (nvd.nist.gov), GitHub Security Advisories, and OSV.dev for {_esc(nm)}. View the full trust analysis at nerq.ai/safe/{slug}."),
    ]
    faq_html, faq_ld = _faq(faq_items)

    # Article + FAQPage schema
    article_ld = f"""<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":"{_esc(title[:110])}","author":{{"@type":"Organization","name":"Nerq"}},"publisher":{{"@type":"Organization","name":"Nerq","url":"https://nerq.ai"}},"datePublished":"{TODAY}","dateModified":"{TODAY}","description":"{_esc(verdict_detail[:200])}"}}
</script>"""

    meta = (
        f'<meta name="nerq:type" content="hacked">'
        f'<meta name="nerq:entity" content="{_esc(nm)}">'
        f'<meta name="nerq:score" content="{sc:.0f}">'
        f'<meta name="nerq:verdict" content="{_esc(verdict)}">'
        f'<meta name="nerq:cve_count" content="{cve_count}">'
        f'<meta name="nerq:updated" content="{TODAY}">'
    )

    page = _head(
        title[:60],
        f"Was {_esc(nm)} hacked? {verdict}. {cve_count} CVEs. Security incident history and breach analysis. Updated {MY}."[:160],
        canonical,
        meta + faq_ld + article_ld
    )

    # Direct answer in first 100 words (critical for AI citation)
    page += f"""
<h1>Was {_esc(nm)} Hacked?</h1>
<p class="pplx-verdict ai-summary" style="font-size:16px;line-height:1.7;color:#1e293b;margin:12px 0 24px;padding:16px;background:#f8fafc;border-left:4px solid {vc};border-radius:0 8px 8px 0">
<strong>{verdict}.</strong> {verdict_detail} {sec_para}{coverage}Trust Score: {sc:.0f}/100 ({gr}).
Last checked: {TODAY}.</p>

<div style="display:inline-block;padding:10px 20px;font-weight:700;font-size:18px;color:{vc};border:2px solid {vc};border-radius:8px;margin:0 0 24px">{verdict}</div>

<h2>Security Incident Summary</h2>
<table>
<tr><th>CVE Count</th><td style="font-weight:700;color:{vc}">{cve_count}</td></tr>
<tr><th>Critical CVEs</th><td>{cve_critical}</td></tr>
<tr><th>Breach Status</th><td style="color:{vc}">{verdict}</td></tr>
<tr><th>Trust Score</th><td>{sc:.0f}/100 ({gr})</td></tr>"""
    if sec_score is not None and sec_score > 0:
        page += f'\n<tr><th>Security Dimension</th><td>{sec_score:.0f}/100</td></tr>'
    page += f"""
<tr><th>Publisher</th><td>{_esc(author)}</td></tr>
<tr><th>Registry</th><td>{_esc(registry) if registry else 'N/A'}</td></tr>
</table>

<h2>What We Check</h2>
<ul style="font-size:14px;line-height:1.8;color:#374151">
<li><strong>National Vulnerability Database (NVD)</strong> — CVE entries for publicly disclosed vulnerabilities</li>
<li><strong>GitHub Security Advisories</strong> — security alerts for open-source dependencies</li>
<li><strong>OSV.dev</strong> — Google's open-source vulnerability database</li>
<li><strong>Public breach reports</strong> — media reports and incident disclosures</li>
</ul>

<h2>Full Trust Analysis</h2>
<p style="font-size:14px;color:#374151">For a complete safety assessment including privacy, maintenance, and community trust signals, see <a href="/safe/{slug}" style="color:#0d9488;font-weight:600">{_esc(nm)} Trust Score on Nerq</a>.</p>

<h2>FAQ</h2>{faq_html}"""
    page += _foot(slug)
    return _sc(ck, page)


def mount_pattern_routes(app):
    """Mount all 23+ new URL patterns."""

    # ── SAFETY PATTERNS (4 new) ──
    SAFETY = {
        "a-scam": ("Is {name} a Scam? Legitimacy Check {year} | Nerq", "Is {name} a scam?", "Not a Scam", "Scam Risk", "Based on business verification, user reports, and trust signals."),
        "fake": ("Is {name} Fake? Authenticity Check {year} | Nerq", "Is {name} fake?", "Authentic", "Possibly Fake", "Based on publisher verification and community signals."),
        "a-virus": ("Is {name} a Virus? Malware Check {year} | Nerq", "Is {name} a virus?", "Clean", "Malware Risk", "Based on security analysis and known threat databases."),
        "safe-to-download": ("Is {name} Safe to Download? {year} | Nerq", "Is {name} safe to download?", "Safe to Download", "Download with Caution", "Based on source verification and security analysis."),
        "safe-to-buy-from": ("Is {name} Safe to Buy From? {year} | Nerq", "Is {name} safe to buy from?", "Safe to Buy", "Buy with Caution", "Based on business legitimacy and user trust signals."),
    }
    for key, (title, q, vp, vn, focus) in SAFETY.items():
        def _mk(k=key, t=title, qq=q, vvp=vp, vvn=vn, f=focus):
            async def h(slug: str):
                html = _pattern_page(slug, k, t, qq, vvp, vvn, f)
                return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
            return h
        app.get(f"/is-{{slug}}-{key}", response_class=HTMLResponse)(_mk())

    # ── PRIVACY PATTERNS (4 new) ──
    PRIVACY = {
        "sell-your-data": ("Does {name} Sell Your Data? {year} | Nerq", "Does {name} sell your data?", "No Evidence", "Data Selling Risk"),
        "track-you": ("Does {name} Track You? {year} | Nerq", "Does {name} track you?", "Minimal Tracking", "Extensive Tracking"),
        "listen-to-you": ("Does {name} Listen to You? {year} | Nerq", "Does {name} listen to conversations?", "No Evidence", "Audio Access Detected"),
        "encrypted": ("Is {name} Encrypted? {year} | Nerq", "Is {name} end-to-end encrypted?", "Encryption Available", "Encryption Unclear"),
    }
    for key, (title, q, vp, vn) in PRIVACY.items():
        def _mk(k=key, t=title, qq=q, vvp=vp, vvn=vn):
            async def h(slug: str):
                html = _pattern_page(slug, k, t, qq, vvp, vvn, "Based on privacy analysis of permissions, policies, and data practices.")
                return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
            return h
        if key == "encrypted":
            app.get(f"/is-{{slug}}-{key}", response_class=HTMLResponse)(_mk())
        else:
            app.get(f"/does-{{slug}}-{key}", response_class=HTMLResponse)(_mk())

    # ── REVIEW PATTERNS (2 new) ──
    @app.get("/is-{slug}-worth-it", response_class=HTMLResponse)
    async def worth_it(slug: str):
        html = _pattern_page(slug, "worth-it", "Is {name} Worth It? {year} | Nerq", "Is {name} worth it?", "Worth It", "Not Worth It", "Value assessment based on trust, features, and alternatives.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    @app.get("/should-i-use-{slug}", response_class=HTMLResponse)
    async def should_use(slug: str):
        html = _pattern_page(slug, "should-use", "Should I Use {name}? {year} | Nerq", "Should I use {name}?", "Recommended", "Consider Alternatives", "Recommendation based on trust score, alternatives, and use case fit.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    # ── PROFILE PATTERNS (3 new) ──
    @app.get("/who-owns/{slug}", response_class=HTMLResponse)
    async def who_owns(slug: str):
        html = _pattern_page(slug, "who-owns", "Who Owns {name}? Company Info {year} | Nerq", "Who owns {name}?", "Transparent", "Unclear", "Based on public business information.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    @app.get("/where-is-{slug}-based", response_class=HTMLResponse)
    async def where_based(slug: str):
        html = _pattern_page(slug, "where-based", "Where Is {name} Based? {year} | Nerq", "Where is {name} headquartered?", "Transparent", "Unclear", "Based on public business registration data.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    @app.get("/how-does-{slug}-make-money", response_class=HTMLResponse)
    async def how_money(slug: str):
        html = _pattern_page(slug, "how-money", "How Does {name} Make Money? {year} | Nerq", "How does {name} make money?", "Transparent Model", "Unclear Model", "Based on public business model analysis.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    # ── ACTION PATTERNS (3 new) ──
    @app.get("/how-to-delete-{slug}-account", response_class=HTMLResponse)
    async def delete_account(slug: str):
        html = _pattern_page(slug, "delete-account", "How to Delete {name} Account {year} | Nerq", "How to delete {name} account?", "Account Deletable", "Deletion Difficult", "Guide to account deletion and data removal.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    @app.get("/{slug}-security-settings", response_class=HTMLResponse)
    async def security_settings(slug: str):
        html = _pattern_page(slug, "security-settings", "{name} Security Settings Guide {year} | Nerq", "What are the best {name} security settings?", "Well-Secured", "Needs Configuration", "Security configuration guide based on trust analysis.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    @app.get("/was-{slug}-hacked", response_class=HTMLResponse)
    async def was_hacked(slug: str):
        html = _hacked_page(slug)
        if html:
            return HTMLResponse(html)
        return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    # ── STATUS PATTERNS (2 new) ──
    @app.get("/{slug}-data-breach", response_class=HTMLResponse)
    async def data_breach(slug: str):
        html = _pattern_page(slug, "data-breach", "{name} Data Breach History {year} | Nerq", "Has {name} had a data breach?", "No Known Breaches", "Breach Detected", "Based on public breach databases.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    @app.get("/is-{slug}-down", response_class=HTMLResponse)
    async def is_down(slug: str):
        html = _pattern_page(slug, "down", "Is {name} Down? Status {year} | Nerq", "Is {name} down right now?", "Operational", "Status Unknown", "Real-time status based on monitoring data.")
        return HTMLResponse(html) if html else HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)

    # ── COMPARISON PATTERNS (2 new) ──
    @app.get("/free-alternative-to-{slug}", response_class=HTMLResponse)
    async def free_alt(slug: str):
        ck = f"freealt:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)
        a = _resolve(slug)
        if not a: return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
        nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
        title = f"Free Alternative to {_esc(nm)} {YEAR} | Nerq"
        canonical = f"{SITE}/free-alternative-to-{slug}"
        faq_items = [(f"What is a free alternative to {_esc(nm)}?", f"Check /alternatives/{slug} for trust-ranked alternatives. Filter by license for free options.")]
        faq_html, faq_ld = _faq(faq_items)
        page = _head(title, f"Free alternatives to {_esc(nm)}. Trust-ranked. Updated {MY}.", canonical, faq_ld)
        page += f"""<h1>Free Alternative to {_esc(nm)} {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Looking for a free alternative to {_esc(nm)}? {_esc(nm)} has a Trust Score of {(a.get('score') or 0):.0f}/100. See trust-ranked alternatives below. Updated {MY}.</p>
<p style="font-size:14px;color:#374151">See <a href="/alternatives/{slug}" style="color:#0d9488">all alternatives to {_esc(nm)}</a> ranked by trust score.</p>
<h2>FAQ</h2>{faq_html}"""
        page += _foot(slug)
        return HTMLResponse(_sc(ck, page))

    @app.get("/private-alternative-to-{slug}", response_class=HTMLResponse)
    async def private_alt(slug: str):
        ck = f"privalt:{slug}"
        c = _c(ck)
        if c: return HTMLResponse(c)
        a = _resolve(slug)
        if not a: return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en"><head>
<title>{slug.replace("-", " ").title()} — Not Yet Analyzed | Nerq</title>
<meta name="robots" content="noindex">
<meta name="description" content="Nerq has not yet analyzed {slug.replace('-', ' ')}. Check back soon.">
<link rel="stylesheet" href="/static/nerq.css">
</head><body>
<h1>{slug.replace("-", " ").title()} — Not Yet Analyzed</h1>
<p>This entity has been queued for analysis. <a href="/">Search Nerq</a></p>
</body></html>""", status_code=200)
        nm = a["name"].split("/")[-1] if "/" in a.get("name","") else a.get("name","")
        title = f"Private Alternative to {_esc(nm)} {YEAR} | Nerq"
        canonical = f"{SITE}/private-alternative-to-{slug}"
        faq_items = [(f"What is a more private alternative to {_esc(nm)}?", f"Check /alternatives/{slug} for trust-ranked alternatives with better privacy.")]
        faq_html, faq_ld = _faq(faq_items)
        page = _head(title, f"More private alternatives to {_esc(nm)}. Privacy-ranked. Updated {MY}.", canonical, faq_ld)
        page += f"""<h1>Private Alternative to {_esc(nm)} {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">Looking for a more private alternative to {_esc(nm)}? See trust-ranked alternatives with better privacy practices. Updated {MY}.</p>
<p style="font-size:14px"><a href="/alternatives/{slug}" style="color:#0d9488">All alternatives</a> · <a href="/privacy/{slug}" style="color:#0d9488">Privacy analysis</a></p>
<h2>FAQ</h2>{faq_html}"""
        page += _foot(slug)
        return HTMLResponse(_sc(ck, page))

    # ── RANKING PATTERNS (new) ──
    RANKINGS = {
        "most-private/messaging-apps": "Most Private Messaging Apps",
        "most-private/email-providers": "Most Private Email Providers",
        "most-private/browsers": "Most Private Browsers",
        "most-private/search-engines": "Most Private Search Engines",
        "safest/social-media": "Safest Social Media Platforms",
        "safest/online-stores": "Safest Online Stores",
        "safest/payment-apps": "Safest Payment Apps",
        "safest/games-for-kids": "Safest Games for Kids",
    }

    for path, display in RANKINGS.items():
        def _mk(p=path, d=display):
            async def h():
                ck = f"rank:{p}"
                c = _c(ck)
                if c: return HTMLResponse(c)
                title = f"{d} {YEAR} — Trust Ranked | Nerq"
                canonical = f"{SITE}/{p}"
                page = _head(title, f"{d}. Ranked by Nerq Trust Score. Independent, no affiliate links. {MY}.", canonical,
                            f'<meta name="nerq:type" content="ranking"><meta name="nerq:updated" content="{TODAY}">')
                page += f"""<h1>{_esc(d)} — {YEAR}</h1>
<p style="font-size:15px;color:#374151;margin:8px 0 20px">{_esc(d)}, ranked by independent Nerq Trust Score. No affiliate links. Updated {MY}.</p>
<p style="font-size:14px;color:#6b7280">Rankings generated from trust analysis across 5M+ software entities. <a href="/stats/ai-ecosystem" style="color:#0d9488">See methodology</a>.</p>
<div class="links"><a href="/trending">Trending</a> <a href="/leaderboard">Leaderboard</a> <a href="/discover">Discover</a> <a href="/best/safest-apps-2026">Safest Apps</a> <a href="/best/safest-vpns-2026">Safest VPNs</a></div>"""
                page += f'<p style="font-size:12px;color:#6b7280;margin-top:16px">Updated {MY}.</p></main>{NERQ_FOOTER}</body></html>'
                return HTMLResponse(_sc(ck, page))
            return h
        app.get(f"/{path}", response_class=HTMLResponse)(_mk())

    logger.info(f"Mounted {4+4+2+3+3+2+2+2+len(RANKINGS)} new URL patterns")
