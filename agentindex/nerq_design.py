"""
Nerq Design System v13 — "Bloomberg Terminal of Trust"
======================================================
Render functions for all nerq.ai page components.
CSS lives in /static/nerq.css (external, cached 7 days).
Only critical above-fold CSS is inlined.

Import: from agentindex.nerq_design import (
    NERQ_CSS, NERQ_NAV, NERQ_FOOTER,
    render_head, render_nav, render_verdict_box, render_breadcrumb,
    render_trust_breakdown, render_cross_links, render_footer, render_faq,
    nerq_head, nerq_page
)
"""

import html as _html
from datetime import date

_CSS_VERSION = 13
_SITE = "https://nerq.ai"
_TODAY = date.today().isoformat()
_YEAR = date.today().year

# All supported languages for hreflang tags
HREFLANG_LANGS = ["en", "es", "pt", "fr", "de", "ja", "ru", "ko", "it", "tr",
                   "nl", "pl", "id", "th", "vi", "hi", "sv", "cs", "ro", "zh", "da", "ar"]


def render_hreflang(path):
    """Generate hreflang link tags for all supported languages.
    path: the English URL path (e.g., '/safe/express' or '/is-tiktok-safe').
    Returns HTML string with all hreflang <link> tags.
    """
    tags = []
    en_url = f"{_SITE}{path}"
    tags.append(f'<link rel="alternate" hreflang="en" href="{en_url}">')
    tags.append(f'<link rel="alternate" hreflang="x-default" href="{en_url}">')
    for lang in HREFLANG_LANGS:
        if lang == "en":
            continue
        tags.append(f'<link rel="alternate" hreflang="{lang}" href="{_SITE}/{lang}{path}">')
    return "\n".join(tags)

def _esc(s):
    return _html.escape(str(s)) if s else ""


# ── Score/grade color helpers ──────────────────────────────

def _score_class(score):
    """CSS class for a trust score value."""
    if score is None: return "sc-mid"
    s = float(score)
    if s >= 80: return "sc-high"
    if s >= 60: return "sc-good"
    if s >= 40: return "sc-mid"
    if s >= 20: return "sc-low"
    return "sc-crit"

def _grade_bg(grade):
    """CSS class for grade badge background."""
    if not grade: return "bg-mid"
    g = grade.upper()[0]
    if g == "A": return "bg-high"
    if g == "B": return "bg-good"
    if g == "C": return "bg-mid"
    if g == "D": return "bg-low"
    return "bg-crit"


# ── Critical inline CSS (above-fold only, <2KB) ───────────

_CRITICAL_CSS = """<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;line-height:1.6;background:#fff;font-size:15px}
a{color:#2563eb;text-decoration:none}
.nav{border-bottom:1px solid #e2e8f0;padding:10px 0;position:sticky;top:0;background:#fff;z-index:100}
.nav-inner{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}
.nav-logo{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}
.nav-logo:hover{text-decoration:none}
.nav-logo span{font-weight:400;color:#64748b;font-size:13px;margin-left:6px}
.nav-links{display:flex;gap:16px;font-size:13px;margin-left:auto}
.nav-links a{color:#64748b;text-decoration:none}
.container{max-width:780px;margin:0 auto;padding:0 20px}
.verdict{border:1px solid #e2e8f0;border-radius:12px;padding:24px 28px;margin:8px 0 20px;display:flex;align-items:center;gap:24px}
.verdict-num{font-size:38px;font-weight:700;line-height:1}
.sc-high{color:#16a34a}.sc-good{color:#22c55e}.sc-mid{color:#f59e0b}.sc-low{color:#ef4444}.sc-crit{color:#991b1b}
</style>"""


# ── Backward-compatible NERQ_CSS (inline, for legacy pages) ──

NERQ_CSS = f"""<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;line-height:1.6;font-size:15px;background:#fff}}
a{{color:#2563eb;text-decoration:none}}a:hover{{color:#1d4ed8;text-decoration:underline}}
code,pre{{font-family:ui-monospace,'SF Mono','Cascadia Mono',monospace}}
code{{background:#f1f5f9;padding:1px 5px;font-size:.9em;border-radius:3px}}
pre{{background:#f1f5f9;padding:16px;overflow-x:auto;font-size:13px;line-height:1.5;border:1px solid #e2e8f0;border-radius:6px}}
h1,h2,h3,h4{{font-weight:700;line-height:1.3}}
h1{{font-size:1.5rem;margin-bottom:8px}}
h2{{font-size:1.15rem;margin:24px 0 8px;padding-top:16px;border-top:1px solid #f1f5f9}}
h3{{font-size:1rem;margin:16px 0 6px}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}}
th{{text-align:left;padding:8px 10px;border-bottom:2px solid #e2e8f0;color:#64748b;font-weight:600;font-size:13px}}
td{{padding:8px 10px;border-bottom:1px solid #f1f5f9}}
tr:nth-child(even){{background:#fafbfc}}
.container{{max-width:780px;margin:0 auto;padding:0 20px}}
.nav{{border-bottom:1px solid #e2e8f0;padding:10px 0;position:sticky;top:0;background:#fff;z-index:100}}
.nav-inner{{max-width:1100px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:16px}}
.nav-logo{{font-size:20px;font-weight:700;color:#0f172a;text-decoration:none}}
.nav-logo:hover{{text-decoration:none}}
.nav-logo span{{font-weight:400;color:#64748b;font-size:13px;margin-left:6px}}
.nav-links{{display:flex;gap:16px;font-size:13px;margin-left:auto}}
.nav-links a{{color:#64748b;text-decoration:none}}
.nav-links a:hover{{color:#0f172a}}
.pill{{display:inline-block;padding:1px 8px;font-size:12px;font-weight:600;border-radius:4px}}
.pill-green{{background:#f0fdf4;color:#16a34a}}
.pill-yellow{{background:#fffbeb;color:#d97706}}
.pill-red{{background:#fef2f2;color:#ef4444}}
.pill-gray{{background:#f8fafc;color:#64748b}}
.breadcrumb{{font-size:13px;color:#64748b;padding:14px 0 6px}}
.breadcrumb a{{color:#64748b;text-decoration:none}}
.breadcrumb a:hover{{color:#0f172a}}
.section{{margin:20px 0}}
.desc{{color:#64748b;font-size:14px;margin:4px 0 12px}}
.cross-links{{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}}
.cross-link{{font-size:13px;padding:5px 14px;border:1px solid #e2e8f0;border-radius:20px;color:#475569;text-decoration:none}}
.cross-link:hover{{background:#f8fafc;color:#0f172a;text-decoration:none}}
footer{{border-top:1px solid #e2e8f0;padding:24px 0;margin-top:40px;font-size:13px;color:#94a3b8}}
footer .inner,.footer .wide-container{{max-width:1100px;margin:0 auto;padding:0 20px}}
.footer-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:24px}}
.footer-col h4{{font-size:13px;font-weight:600;color:#64748b;margin-bottom:8px}}
.footer a{{color:#64748b;text-decoration:none;display:block;padding:2px 0}}
.footer a:hover{{color:#0f172a}}
.footer-bottom{{margin-top:16px;padding-top:12px;border-top:1px solid #f1f5f9;font-size:12px;color:#94a3b8}}
@media(max-width:768px){{
.nav-inner{{flex-wrap:wrap}}
.nav-links{{gap:10px;font-size:12px}}
.footer-grid{{grid-template-columns:repeat(2,1fr)}}
table{{font-size:13px}}
th,td{{padding:6px 8px}}
}}
/* RTL support (Arabic) */
[dir="rtl"]{{direction:rtl;text-align:right}}
[dir="rtl"] .breadcrumb,[dir="rtl"] .nav-links{{flex-direction:row-reverse}}
[dir="rtl"] pre,[dir="rtl"] code{{direction:ltr;text-align:left}}
[dir="rtl"] .pplx-verdict{{border-left:none;border-right:4px solid #16a34a}}
[dir="rtl"] table th{{text-align:right}}
[dir="rtl"] td:first-child{{text-align:right}}
[dir="rtl"] .signal-card,.alt-card,.cross-link{{text-align:right}}
</style>"""


# ── Nav HTML ───────────────────────────────────────────────

NERQ_NAV = """<nav class="nav"><div class="nav-inner">
<a href="/" class="nav-logo">Nerq<span>Trust Intelligence</span></a>
<div class="nav-links">
<a href="/discover">Search</a>
<a href="/apps">Apps</a>
<a href="/npm">Packages</a>
<a href="/extensions">Extensions</a>
<a href="/websites">Websites</a>
<a href="/best/safest-countries">Travel</a>
<a href="/best/charities">Charities</a>
<a href="/compare">Compare</a>
<a href="/nerq/docs">API</a>
<select id="nerq-lang" onchange="(function(s){var v=s.value,p=location.pathname;if(v==='en'){p=p.replace(/^\\/[a-z]{2}\\//,'/');location.href=p||'/';}else{var m=p.match(/^\\/([a-z]{2})\\//);if(m){p=p.replace(/^\\/[a-z]{2}\\//,'/'+v+'/');}else if(p==='/'){p='/'+v+'/';}else{p='/'+v+p;}location.href=p;}})(this)" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:2px 4px;font-size:12px;color:#64748b;cursor:pointer">
<option value="en">EN</option><option value="es">ES</option><option value="de">DE</option><option value="fr">FR</option><option value="ja">JA</option><option value="pt">PT</option><option value="id">ID</option><option value="cs">CS</option><option value="th">TH</option><option value="ro">RO</option><option value="tr">TR</option><option value="hi">HI</option><option value="ru">RU</option><option value="pl">PL</option><option value="it">IT</option><option value="ko">KO</option><option value="vi">VI</option><option value="nl">NL</option><option value="sv">SV</option><option value="zh">ZH</option><option value="da">DA</option>
</select>
</div>
</div></nav>
<script>(function(){var m=location.pathname.match(/^\\/([a-z]{2})\\//);if(m){var s=document.getElementById('nerq-lang');if(s)s.value=m[1];}})();</script>"""


# ── Footer HTML ────────────────────────────────────────────

NERQ_EXPLORE = """<div class="cross-links" style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid #e2e8f0">
<a href="/apps" class="cross-link">Apps</a>
<a href="/npm" class="cross-link">Packages</a>
<a href="/websites" class="cross-link">Websites</a>
<a href="/vpns" class="cross-link">VPNs</a>
<a href="/games" class="cross-link">Games</a>
<a href="/extensions" class="cross-link">Extensions</a>
<a href="/wordpress-plugins" class="cross-link">WordPress</a>
<a href="/best/safest-countries" class="cross-link">Countries</a>
<a href="/best/charities" class="cross-link">Charities</a>
<a href="/compare" class="cross-link">Compare</a>
<a href="/check-website" class="cross-link">Check Website</a>
</div>"""

NERQ_FOOTER = NERQ_EXPLORE + """<footer class="footer"><div class="wide-container">
<div class="footer-grid">
<div class="footer-col"><h4>Check Safety</h4>
<a href="/apps">Mobile Apps</a><a href="/websites">Websites</a><a href="/extensions">Extensions</a>
<a href="/vpns">VPNs</a><a href="/games">Games</a><a href="/wordpress-plugins">WordPress</a><a href="/best/safest-countries">Countries</a><a href="/best/charities">Charities</a></div>
<div class="footer-col"><h4>Packages</h4>
<a href="/npm">npm</a><a href="/pypi">PyPI</a><a href="/crates">Rust Crates</a>
<a href="/nuget">NuGet</a><a href="/go-packages">Go</a><a href="/packagist">Packagist</a></div>
<div class="footer-col"><h4>Resources</h4>
<a href="/guides">Safety Guides</a><a href="/compare">Compare</a><a href="/check-website">Check Website</a>
<a href="/nerq/docs">API</a><a href="/badges">Trust Badges</a><a href="/llms.txt">llms.txt</a></div>
<div class="footer-col"><h4>Nerq</h4>
<p style="font-size:12px;color:#94a3b8;line-height:1.5">Trust scores for software, apps, websites, travel destinations, and charities. 7.5M+ entities from 26 registries. Independent. Data-driven.</p>
<a href="/about" style="margin-top:6px">About</a><a href="https://zarq.ai">zarq.ai (crypto)</a></div>
</div>
<div class="footer-bottom">nerq.ai &mdash; trust scores for all software &middot; 7.5M+ entities &middot; 26 registries &middot; 20 languages</div>
</div></footer>"""


# ── Render functions ───────────────────────────────────────

def render_head(title, description="", canonical="", extra_meta="", extra_ld="", lang="en"):
    """Full <head> with external CSS, critical inline CSS, meta tags."""
    canon = f'<link rel="canonical" href="{_esc(canonical)}">' if canonical else ""
    desc = f'<meta name="description" content="{_esc(description)}">' if description else ""
    return f"""<!DOCTYPE html>
<html lang="{_esc(lang)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
{desc}
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
{canon}
{extra_meta}
{extra_ld}
{_CRITICAL_CSS}
<link rel="stylesheet" href="/static/nerq.css?v={_CSS_VERSION}">
</head>
<body>"""


def render_nav(current_category=None):
    """Universal navigation bar."""
    return NERQ_NAV


def render_verdict_box(name, category, score, grade, verdict, updated=None):
    """Visual trust score verdict box. aria-hidden since info is in first paragraph."""
    sc = float(score) if score is not None else 0
    sc_cls = _score_class(sc)
    gr_cls = _grade_bg(grade)
    upd = updated or _TODAY
    return f"""<div class="verdict" aria-hidden="true">
<div class="verdict-score">
<div class="verdict-num {sc_cls}">{sc:.0f}</div>
<div class="verdict-of">/100</div>
<span class="verdict-grade {gr_cls}">{_esc(grade or 'N/A')}</span>
</div>
<div class="verdict-info">
<div class="verdict-name">{_esc(name)}</div>
<div class="verdict-cat">{_esc(category or '')}</div>
<div class="verdict-text {sc_cls}">{_esc(verdict or '')}</div>
<div class="verdict-date">Last analyzed: {_esc(upd)}</div>
</div>
</div>"""


def render_breadcrumb(items):
    """Breadcrumb nav. items = [(url, label), ...]. Last item has no url.
    Also returns BreadcrumbList JSON-LD."""
    bc_html = '<nav class="breadcrumb" aria-label="Breadcrumb">'
    bc_items = []
    for i, (url, label) in enumerate(items):
        if i > 0:
            bc_html += '<span class="sep">&rsaquo;</span>'
        if url:
            bc_html += f'<a href="{_esc(url)}">{_esc(label)}</a>'
        else:
            bc_html += f'<span>{_esc(label)}</span>'
        bc_items.append(f'{{"@type":"ListItem","position":{i+1},"name":"{_esc(label)}","item":"{_esc(url or "")}"}}')
    bc_html += '</nav>'

    ld = f"""<script type="application/ld+json">{{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{",".join(bc_items)}]}}</script>"""
    return bc_html + "\n" + ld


def render_trust_breakdown(scores):
    """Trust score breakdown bars. scores = dict of {label: score}."""
    if not scores:
        return ""
    html = '<div class="section"><h2 class="section-title">Trust Score Breakdown</h2>'
    for label, val in scores.items():
        v = float(val) if val is not None else 0
        cls = _score_class(v)
        color = {"sc-high": "#16a34a", "sc-good": "#22c55e", "sc-mid": "#f59e0b", "sc-low": "#ef4444", "sc-crit": "#991b1b"}.get(cls, "#94a3b8")
        html += f"""<div class="breakdown-item">
<span class="breakdown-label">{_esc(label)}</span>
<div class="breakdown-bar"><div class="breakdown-fill" style="width:{v:.0f}%;background:{color}"></div></div>
<span class="breakdown-val {cls}">{v:.0f}</span>
</div>"""
    html += '</div>'
    return html


def render_cross_links(entity_slug, patterns=None):
    """Pill-button links to other URL patterns for the same entity."""
    if not entity_slug:
        return ""
    s = _esc(entity_slug)
    default_patterns = [
        (f"/is-{s}-safe", "Safety"),
        (f"/is-{s}-legit", "Legit?"),
        (f"/is-{s}-a-scam", "Scam?"),
        (f"/privacy/{s}", "Privacy"),
        (f"/review/{s}", "Review"),
        (f"/pros-cons/{s}", "Pros & Cons"),
        (f"/is-{s}-safe-for-kids", "Safe for Kids?"),
        (f"/alternatives/{s}", "Alternatives"),
        (f"/who-owns/{s}", "Who Owns?"),
        (f"/what-is/{s}", "What Is?"),
    ]
    links = patterns or default_patterns
    html = '<nav class="cross-links" aria-label="Related analyses">'
    for url, label in links:
        html += f'<a href="{url}" class="cross-link">{_esc(label)}</a>'
    html += '</nav>'
    return html


def render_faq(qas):
    """FAQ section using native <details>/<summary>. qas = [(question, answer), ...]."""
    if not qas:
        return ""
    html = '<div class="section faq"><h2 class="section-title">FAQ</h2>'
    for q, a in qas:
        html += f"""<details>
<summary>{_esc(q)}</summary>
<div class="faq-a">{a}</div>
</details>"""
    html += '</div>'
    return html


def render_footer(lang="en"):
    """Full page footer."""
    return NERQ_FOOTER


# ── Backward-compatible helpers ────────────────────────────

def nerq_head(title: str, description: str = "", canonical: str = "") -> str:
    """Legacy: generate <head> with inline CSS. Use render_head() for new pages."""
    canon = f'<link rel="canonical" href="{_esc(canonical)}">' if canonical else ""
    desc = f'<meta name="description" content="{_esc(description)}">' if description else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
{desc}
{canon}
{NERQ_CSS}
<link rel="stylesheet" href="/static/nerq.css?v={_CSS_VERSION}">
</head>
<body>
{NERQ_NAV}"""


def nerq_page(title: str, body: str, description: str = "", canonical: str = "") -> str:
    """Legacy: wrap body in a full page. Use render_head() + render_footer() for new pages."""
    return f"""{nerq_head(title, description, canonical)}
<main class="container" style="padding-top:20px;padding-bottom:40px">
{body}
</main>
{NERQ_FOOTER}
</body>
</html>"""
