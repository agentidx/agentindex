"""
Nerq Agent Comparison Pages
=============================
Side-by-side comparison pages at /compare/{slug} and hub at /compare.
Captures "X vs Y" search traffic.

Usage in discovery.py:
    from agentindex.agent_compare_pages import mount_agent_compare_pages
    mount_agent_compare_pages(app)
"""

import json
import logging
import os
import time
from pathlib import Path
from datetime import date
from collections import defaultdict

from fastapi.responses import HTMLResponse, Response
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.compare_pages")

TEMPLATE_DIR = Path(__file__).parent / "templates"
PAIRS_PATH = Path(__file__).parent / "comparison_pairs.json"

# L1b compare-page canary: when L1B_COMPARE_UNLOCK_REGISTRIES is set (comma-
# separated list or "*" / "all"), /compare/<a>-vs-<b> pages whose slug parts
# resolve to software_registry rows in the allowlisted registries gain the
# "Detailed Score Analysis" FIVE_DIMS table and a .pplx-verdict element.
# Shadow-mode: additive only, leaves existing sections untouched.
_L1B_COMPARE_UNLOCK_ALLOWLIST: frozenset = frozenset(
    s.strip() for s in os.environ.get("L1B_COMPARE_UNLOCK_REGISTRIES", "").split(",") if s.strip()
)
_L1B_COMPARE_UNLOCK_ALL: bool = bool(_L1B_COMPARE_UNLOCK_ALLOWLIST & {"*", "all"})

_pairs = []
_pair_map = {}
_page_cache = {}
_CACHE_TTL = 3600
_CACHE_MAX = 500


def _load_pairs():
    global _pairs, _pair_map
    if _pair_map:
        return
    try:
        with open(PAIRS_PATH) as f:
            _pairs = json.load(f)
        _pair_map = {p["slug"]: p for p in _pairs}
        logger.info(f"Loaded {len(_pair_map)} comparison pairs")
    except Exception as e:
        logger.error(f"Failed to load comparison pairs: {e}")


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


_AGENT_COLS = """
    name,
    COALESCE(trust_score_v2, trust_score) as trust_score,
    trust_grade,
    category,
    source,
    source_url,
    stars,
    author,
    is_verified,
    compliance_score,
    eu_risk_class,
    documentation_score,
    activity_score,
    security_score,
    popularity_score,
    description
"""


def _lookup_agent(name):
    """Look up agent by name with fuzzy matching."""
    session = get_session()
    try:
        clean = name.replace("-", " ").replace("_", " ")
        row = session.execute(text(f"""
            SELECT {_AGENT_COLS} FROM (
                SELECT name, trust_score, trust_score_v2, trust_grade, category, source, source_url,
                       stars, author, is_verified, compliance_score, eu_risk_class, documentation_score,
                       activity_score, security_score, popularity_score, description, 1 AS _rank
                FROM entity_lookup WHERE name_lower = lower(:name) AND is_active = true
              UNION ALL
                SELECT name, trust_score, trust_score_v2, trust_grade, category, source, source_url,
                       stars, author, is_verified, compliance_score, eu_risk_class, documentation_score,
                       activity_score, security_score, popularity_score, description, 1 AS _rank
                FROM entity_lookup WHERE name_lower = lower(:clean) AND is_active = true
                AND :clean != :name
              UNION ALL
                SELECT name, trust_score, trust_score_v2, trust_grade, category, source, source_url,
                       stars, author, is_verified, compliance_score, eu_risk_class, documentation_score,
                       activity_score, security_score, popularity_score, description, 2 AS _rank
                FROM entity_lookup WHERE name_lower LIKE lower(:suffix) AND is_active = true
              UNION ALL
                SELECT name, trust_score, trust_score_v2, trust_grade, category, source, source_url,
                       stars, author, is_verified, compliance_score, eu_risk_class, documentation_score,
                       activity_score, security_score, popularity_score, description, 3 AS _rank
                FROM entity_lookup WHERE name_lower LIKE lower(:pattern) AND is_active = true
            ) sub
            ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST,
                     stars DESC NULLS LAST
            LIMIT 1
        """), {
            "name": name,
            "clean": clean,
            "suffix": f"%/{name}",
            "pattern": f"%{name}%",
        }).fetchone()
        return dict(row._mapping) if row else None
    finally:
        session.close()


_CANARY_SR_COLS = (
    "name, slug, registry, trust_score, trust_grade, "
    "security_score, maintenance_score, popularity_score, "
    "quality_score, community_score"
)


def _fetch_canary_scores(slug_part: str):
    """Look up a slug in software_registry restricted to the L1b canary
    allowlist. Returns the enriched row dict (with all 5 King dims) or None.
    Callers must guard on _L1B_COMPARE_UNLOCK_ALLOWLIST being non-empty.

    Matches on either `slug` or `lower(name)` because the replica's
    idx_sr_slug btree is currently missing entries for some common packages
    (e.g. pandas), so a slug-only lookup is lossy. The OR-bitmap plan
    still resolves via indexes (idx_sr_slug + idx_sr_name_lower).
    """
    if not slug_part:
        return None
    session = get_session()
    try:
        if _L1B_COMPARE_UNLOCK_ALL:
            row = session.execute(text(
                f"SELECT {_CANARY_SR_COLS} FROM software_registry "
                "WHERE (slug = :slug OR lower(name) = :slug) "
                "ORDER BY enriched_at DESC NULLS LAST LIMIT 1"
            ), {"slug": slug_part}).fetchone()
        else:
            row = session.execute(text(
                f"SELECT {_CANARY_SR_COLS} FROM software_registry "
                "WHERE (slug = :slug OR lower(name) = :slug) "
                "AND registry = ANY(:regs) "
                "ORDER BY enriched_at DESC NULLS LAST LIMIT 1"
            ), {"slug": slug_part, "regs": list(_L1B_COMPARE_UNLOCK_ALLOWLIST)}).fetchone()
        return dict(row._mapping) if row else None
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


def _short_name(full_name):
    """Get the short display name from full agent name."""
    if "/" in full_name:
        return full_name.split("/")[-1]
    return full_name


def _fmt_score(val):
    if val is None:
        return "N/A"
    return f"{val:.0f}"


def _render_compare_page(slug, pair_info):
    """Render a comparison page."""
    agent_a = _lookup_agent(pair_info["agent_a"])
    agent_b = _lookup_agent(pair_info["agent_b"])
    if not agent_a or not agent_b:
        return None

    # Extract data
    name_a = _short_name(agent_a["name"])
    name_b = _short_name(agent_b["name"])
    full_a = agent_a["name"]
    full_b = agent_b["name"]
    score_a = float(agent_a.get("trust_score") or 0)
    score_b = float(agent_b.get("trust_score") or 0)
    grade_a = agent_a.get("trust_grade") or "N/A"
    grade_b = agent_b.get("trust_grade") or "N/A"
    cat_a = agent_a.get("category") or "uncategorized"
    cat_b = agent_b.get("category") or "uncategorized"
    stars_a = agent_a.get("stars") or 0
    stars_b = agent_b.get("stars") or 0
    verified_a = agent_a.get("is_verified") or (score_a >= 70)
    verified_b = agent_b.get("is_verified") or (score_b >= 70)
    slug_a = _make_slug(full_a)
    slug_b = _make_slug(full_b)

    # Score signals
    sec_a = agent_a.get("security_score")
    sec_b = agent_b.get("security_score")
    comp_a = agent_a.get("compliance_score")
    comp_b = agent_b.get("compliance_score")
    act_a = agent_a.get("activity_score")
    act_b = agent_b.get("activity_score")
    doc_a = agent_a.get("documentation_score")
    doc_b = agent_b.get("documentation_score")
    pop_a = agent_a.get("popularity_score")
    pop_b = agent_b.get("popularity_score")
    eu_a = agent_a.get("eu_risk_class") or "N/A"
    eu_b = agent_b.get("eu_risk_class") or "N/A"

    # Score classes
    score_class_a = "vs-winner" if score_a >= score_b else "vs-loser" if score_a < score_b else ""
    score_class_b = "vs-winner" if score_b >= score_a else "vs-loser" if score_b < score_a else ""
    if abs(score_a - score_b) < 1.0:
        score_class_a = score_class_b = ""

    # Verified badges
    ver_a_html = '<span class="pill pill-green" style="font-size:11px">verified</span>' if verified_a else ""
    ver_b_html = '<span class="pill pill-green" style="font-size:11px">verified</span>' if verified_b else ""

    # Side stats
    def _stat_block(sec, comp, act, doc, stars, source, cat):
        lines = []
        lines.append(f'<div class="vs-stat"><span class="vs-stat-label">Category</span><span class="vs-stat-val">{_esc(cat)}</span></div>')
        lines.append(f'<div class="vs-stat"><span class="vs-stat-label">Stars</span><span class="vs-stat-val">{stars:,}</span></div>')
        lines.append(f'<div class="vs-stat"><span class="vs-stat-label">Source</span><span class="vs-stat-val">{_esc(source)}</span></div>')
        if sec is not None:
            lines.append(f'<div class="vs-stat"><span class="vs-stat-label">Security</span><span class="vs-stat-val">{sec:.0f}</span></div>')
        if comp is not None:
            lines.append(f'<div class="vs-stat"><span class="vs-stat-label">Compliance</span><span class="vs-stat-val">{comp:.0f}</span></div>')
        if act is not None:
            lines.append(f'<div class="vs-stat"><span class="vs-stat-label">Maintenance</span><span class="vs-stat-val">{act:.0f}</span></div>')
        if doc is not None:
            lines.append(f'<div class="vs-stat"><span class="vs-stat-label">Documentation</span><span class="vs-stat-val">{doc:.0f}</span></div>')
        return "\n".join(lines)

    stats_a = _stat_block(sec_a, comp_a, act_a, doc_a, stars_a, agent_a.get("source", ""), cat_a)
    stats_b = _stat_block(sec_b, comp_b, act_b, doc_b, stars_b, agent_b.get("source", ""), cat_b)

    # Comparison table rows
    metrics = [
        ("Trust Score", f"{score_a:.1f}/100", f"{score_b:.1f}/100", score_a, score_b),
        ("Grade", grade_a, grade_b, None, None),
        ("Stars", f"{stars_a:,}", f"{stars_b:,}", stars_a, stars_b),
        ("Category", cat_a, cat_b, None, None),
        ("Security", _fmt_score(sec_a), _fmt_score(sec_b), sec_a, sec_b),
        ("Compliance", _fmt_score(comp_a), _fmt_score(comp_b), comp_a, comp_b),
        ("Maintenance", _fmt_score(act_a), _fmt_score(act_b), act_a, act_b),
        ("Documentation", _fmt_score(doc_a), _fmt_score(doc_b), doc_a, doc_b),
        ("EU AI Act Risk", eu_a, eu_b, None, None),
        ("Verified", "Yes" if verified_a else "No", "Yes" if verified_b else "No", None, None),
    ]
    comp_rows = ""
    for label, val_a, val_b, num_a, num_b in metrics:
        highlight_a = highlight_b = ""
        if num_a is not None and num_b is not None:
            if num_a > num_b:
                highlight_a = ' style="color:#065f46;font-weight:700"'
            elif num_b > num_a:
                highlight_b = ' style="color:#065f46;font-weight:700"'
        comp_rows += (
            f'<tr><td style="color:#6b7280">{label}</td>'
            f'<td{highlight_a}>{_esc(val_a)}</td>'
            f'<td{highlight_b}>{_esc(val_b)}</td></tr>\n'
        )

    # Verdict
    diff = abs(score_a - score_b)
    if diff < 2.0:
        verdict = (
            f"{_esc(name_a)} ({score_a:.1f}) and {_esc(name_b)} ({score_b:.1f}) have nearly identical trust scores. "
            f"Both are solid choices. The decision should come down to your specific use case, team preferences, "
            f"and integration requirements rather than trust differences."
        )
    elif score_a > score_b:
        winner, loser = name_a, name_b
        w_score, l_score = score_a, score_b
        verdict = (
            f"{_esc(winner)} leads with a trust score of {w_score:.1f}/100 compared to {_esc(loser)}'s {l_score:.1f}/100 "
            f"(a {diff:.1f}-point difference). "
        )
        # Add specific signal comparison
        advantages = []
        if sec_a is not None and sec_b is not None and sec_a > sec_b:
            advantages.append(f"security ({sec_a:.0f} vs {sec_b:.0f})")
        if comp_a is not None and comp_b is not None and comp_a > comp_b:
            advantages.append(f"compliance ({comp_a:.0f} vs {comp_b:.0f})")
        if act_a is not None and act_b is not None and act_a > act_b:
            advantages.append(f"maintenance ({act_a:.0f} vs {act_b:.0f})")
        if advantages:
            verdict += f"{_esc(winner)} scores higher on {', '.join(advantages)}. "
        if stars_b > stars_a:
            verdict += f"However, {_esc(loser)} has stronger community adoption ({stars_b:,} vs {stars_a:,} stars). "
        verdict += "Both agents should be evaluated based on your specific requirements."
    else:
        winner, loser = name_b, name_a
        w_score, l_score = score_b, score_a
        verdict = (
            f"{_esc(winner)} leads with a trust score of {w_score:.1f}/100 compared to {_esc(loser)}'s {l_score:.1f}/100 "
            f"(a {diff:.1f}-point difference). "
        )
        advantages = []
        if sec_b is not None and sec_a is not None and sec_b > sec_a:
            advantages.append(f"security ({sec_b:.0f} vs {sec_a:.0f})")
        if comp_b is not None and comp_a is not None and comp_b > comp_a:
            advantages.append(f"compliance ({comp_b:.0f} vs {comp_a:.0f})")
        if act_b is not None and act_a is not None and act_b > act_a:
            advantages.append(f"maintenance ({act_b:.0f} vs {act_a:.0f})")
        if advantages:
            verdict += f"{_esc(winner)} scores higher on {', '.join(advantages)}. "
        if stars_a > stars_b:
            verdict += f"However, {_esc(loser)} has stronger community adoption ({stars_a:,} vs {stars_b:,} stars). "
        verdict += "Both agents should be evaluated based on your specific requirements."

    # AI summary
    ai_summary = (
        f"{_esc(name_a)} scores {score_a:.1f}/100 ({_esc(grade_a)}) while {_esc(name_b)} scores "
        f"{score_b:.1f}/100 ({_esc(grade_b)}) on the Nerq Trust Score. "
    )
    if diff < 2.0:
        ai_summary += "The two agents are essentially tied on overall trust. "
    elif score_a > score_b:
        ai_summary += f"{_esc(name_a)} leads by {diff:.1f} points. "
    else:
        ai_summary += f"{_esc(name_b)} leads by {diff:.1f} points. "
    ai_summary += (
        f"{_esc(name_a)} is a {_esc(cat_a)} {'tool' if cat_a != cat_b else 'agent'} with {stars_a:,} stars"
        f"{', Nerq Verified' if verified_a else ''}. "
        f"{_esc(name_b)} is a {_esc(cat_b)} {'tool' if cat_a != cat_b else 'agent'} with {stars_b:,} stars"
        f"{', Nerq Verified' if verified_b else ''}."
    )

    # FAQ
    faq_items = [
        {
            "q": f"Which is safer, {name_a} or {name_b}?",
            "a": (
                f"Based on Nerq's independent trust assessment, {_esc(name_a)} has a trust score of {score_a:.1f}/100 ({_esc(grade_a)}) "
                f"while {_esc(name_b)} scores {score_b:.1f}/100 ({_esc(grade_b)}). "
                f"{'Both agents are very close in overall trust.' if diff < 2 else f'The {diff:.1f}-point difference suggests ' + (_esc(name_a) if score_a > score_b else _esc(name_b)) + ' has a stronger trust profile.'} "
                f"Trust scores are based on security, compliance, maintenance, documentation, and community adoption."
            ),
        },
        {
            "q": f"How do {name_a} and {name_b} compare on security?",
            "a": (
                f"{_esc(name_a)} has a security score of {_fmt_score(sec_a)}/100 and {_esc(name_b)} scores {_fmt_score(sec_b)}/100. "
                f"{'Both have comparable security profiles.' if sec_a is not None and sec_b is not None and abs((sec_a or 0) - (sec_b or 0)) < 5 else 'There is a notable difference in their security assessments.'} "
                f"{_esc(name_a)}'s compliance score is {_fmt_score(comp_a)}/100 (EU risk: {_esc(eu_a)}), "
                f"while {_esc(name_b)}'s is {_fmt_score(comp_b)}/100 (EU risk: {_esc(eu_b)})."
            ),
        },
        {
            "q": f"Should I use {name_a} or {name_b}?",
            "a": (
                f"The choice depends on your requirements. {_esc(name_a)} ({_esc(cat_a)}, {stars_a:,} stars) "
                f"and {_esc(name_b)} ({_esc(cat_b)}, {stars_b:,} stars) serve "
                f"{'similar' if cat_a == cat_b else 'different'} use cases. "
                f"On trust, {_esc(name_a)} scores {score_a:.1f}/100 and {_esc(name_b)} scores {score_b:.1f}/100. "
                f"Review the full KYA reports for each agent before making a decision. "
                f"Consider factors like integration requirements, documentation quality "
                f"({_fmt_score(doc_a)} vs {_fmt_score(doc_b)}), and maintenance activity "
                f"({_fmt_score(act_a)} vs {_fmt_score(act_b)})."
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

    # JSON-LD
    title = f"{name_a} vs {name_b}: Compared Side-by-Side (2026)"
    if len(title) > 60:
        title = f"{name_a} vs {name_b} Comparison (2026)"
    if len(title) > 60:
        title = f"{name_a} vs {name_b}: Full Comparison"
    meta_desc = (
        f"{name_a} ({score_a:.0f}/100) vs {name_b} ({score_b:.0f}/100). "
        f"Trust scores, features, security, and community compared. "
        f"Find which fits your stack."
    )
    if len(meta_desc) > 160:
        meta_desc = meta_desc[:157] + "..."

    webpage_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": meta_desc,
        "url": f"https://nerq.ai/compare/{slug}",
        "publisher": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
    })

    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]}
            }
            for item in faq_items
        ]
    })

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai"},
            {"@type": "ListItem", "position": 2, "name": "Comparisons", "item": "https://nerq.ai/compare"},
            {"@type": "ListItem", "position": 3, "name": f"{name_a} vs {name_b}"},
        ]
    })

    # Related comparisons
    _load_pairs()
    related = []
    for p in _pairs:
        if p["slug"] == slug:
            continue
        # Prefer pairs that share an agent name
        if (pair_info["agent_a"] in [p["agent_a"], p["agent_b"]] or
            pair_info["agent_b"] in [p["agent_a"], p["agent_b"]] or
            p.get("category") == pair_info.get("category")):
            related.append(p)
        if len(related) >= 5:
            break
    # Fill if needed
    if len(related) < 3:
        for p in _pairs:
            if p["slug"] != slug and p not in related:
                related.append(p)
            if len(related) >= 5:
                break

    related_section = ""
    if related:
        cards = ""
        for r in related[:5]:
            rn_a = _short_name(r["agent_a"])
            rn_b = _short_name(r["agent_b"])
            cards += (
                f'<a href="/compare/{_esc(r["slug"])}" class="related-card">'
                f'<div class="rc-title">{_esc(rn_a)} vs {_esc(rn_b)}</div>'
                f'<div class="rc-cat">{_esc(r.get("category", ""))}</div>'
                f'</a>\n'
            )
        related_section = (
            f'<h2>Related Comparisons</h2>'
            f'<div class="related-grid">{cards}</div>'
        )

    # Dataset JSON-LD
    dataset_jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "Dataset",
        "name": f"{name_a} vs {name_b} Trust Comparison",
        "description": f"Independent trust and security comparison of {name_a} and {name_b}",
        "dateModified": date.today().isoformat(),
        "creator": {"@type": "Organization", "name": "Nerq", "url": "https://nerq.ai"},
        "variableMeasured": [
            {"@type": "PropertyValue", "name": f"{name_a} Trust Score", "value": score_a},
            {"@type": "PropertyValue", "name": f"{name_b} Trust Score", "value": score_b},
            {"@type": "PropertyValue", "name": f"{name_a} Security Score", "value": sec_a},
            {"@type": "PropertyValue", "name": f"{name_b} Security Score", "value": sec_b},
        ]
    })

    # Dimension-by-dimension analysis (1500+ words)
    dim_html = '<h2>Detailed Analysis</h2>'

    # Security
    if sec_a is not None and sec_b is not None:
        sec_w = name_a if sec_a >= sec_b else name_b
        sec_l = name_b if sec_a >= sec_b else name_a
        dim_html += f'<h3>Security</h3><p>{_esc(sec_w)} leads on security with a score of {_fmt_score(max(sec_a, sec_b))}/100 compared to {_esc(sec_l)}\'s {_fmt_score(min(sec_a, sec_b))}/100. This score reflects dependency vulnerability analysis, known CVE exposure, and security best practices. A higher security score means fewer known vulnerabilities and better security hygiene in the codebase.</p>'
    elif sec_a is not None or sec_b is not None:
        dim_html += f'<h3>Security</h3><p>Security scores measure dependency vulnerabilities, CVE exposure, and security practices. {_esc(name_a)} scores {_fmt_score(sec_a)} and {_esc(name_b)} scores {_fmt_score(sec_b)} on this dimension.</p>'

    # Activity/Maintenance
    if act_a is not None and act_b is not None:
        act_w = name_a if act_a >= act_b else name_b
        dim_html += f'<h3>Maintenance & Activity</h3><p>{_esc(act_w)} demonstrates stronger maintenance activity ({_fmt_score(max(act_a, act_b))}/100 vs {_fmt_score(min(act_a, act_b))}/100). This metric captures commit frequency, issue response times, and release cadence. Actively maintained tools receive faster security patches and are less likely to accumulate technical debt.</p>'
    elif act_a is not None or act_b is not None:
        dim_html += f'<h3>Maintenance & Activity</h3><p>Activity scores reflect how actively each project is maintained. {_esc(name_a)}: {_fmt_score(act_a)}, {_esc(name_b)}: {_fmt_score(act_b)}.</p>'

    # Documentation
    if doc_a is not None and doc_b is not None:
        doc_w = name_a if doc_a >= doc_b else name_b
        dim_html += f'<h3>Documentation</h3><p>{_esc(doc_w)} has better documentation ({_fmt_score(max(doc_a, doc_b))}/100 vs {_fmt_score(min(doc_a, doc_b))}/100). Good documentation reduces onboarding time and helps teams adopt the tool safely. This score evaluates README completeness, API documentation, code examples, and tutorial availability.</p>'
    elif doc_a is not None or doc_b is not None:
        dim_html += f'<h3>Documentation</h3><p>Documentation quality is evaluated based on README, API docs, and example coverage. {_esc(name_a)}: {_fmt_score(doc_a)}, {_esc(name_b)}: {_fmt_score(doc_b)}.</p>'

    # Community
    dim_html += f'<h3>Community & Adoption</h3><p>{_esc(name_a)} has {stars_a:,} GitHub stars while {_esc(name_b)} has {stars_b:,}. '
    if stars_a > stars_b * 2:
        dim_html += f'{_esc(name_a)} has significantly broader community adoption, which typically means more Stack Overflow answers, more third-party tutorials, and faster ecosystem development.'
    elif stars_b > stars_a * 2:
        dim_html += f'{_esc(name_b)} has significantly broader community adoption, which typically means more Stack Overflow answers, more third-party tutorials, and faster ecosystem development.'
    else:
        dim_html += 'Both tools have comparable community sizes, suggesting similar levels of ecosystem support and third-party resources.'
    dim_html += '</p>'

    # When to choose
    choose_a_pts, choose_b_pts = [], []
    if score_a > score_b: choose_a_pts.append("Higher overall trust score — more reliable for production use")
    elif score_b > score_a: choose_b_pts.append("Higher overall trust score — more reliable for production use")
    if (sec_a or 0) > (sec_b or 0): choose_a_pts.append("Stronger security profile with fewer known vulnerabilities")
    elif (sec_b or 0) > (sec_a or 0): choose_b_pts.append("Stronger security profile with fewer known vulnerabilities")
    if (act_a or 0) > (act_b or 0): choose_a_pts.append("More actively maintained with faster release cadence")
    elif (act_b or 0) > (act_a or 0): choose_b_pts.append("More actively maintained with faster release cadence")
    if stars_a > stars_b: choose_a_pts.append(f"Larger community ({stars_a:,} vs {stars_b:,} stars)")
    elif stars_b > stars_a: choose_b_pts.append(f"Larger community ({stars_b:,} vs {stars_a:,} stars)")
    if (doc_a or 0) > (doc_b or 0): choose_a_pts.append("Better documentation for faster onboarding")
    elif (doc_b or 0) > (doc_a or 0): choose_b_pts.append("Better documentation for faster onboarding")

    def _pts_li(pts):
        return "".join(f"<li>{_esc(p)}</li>" for p in pts) if pts else "<li>Consider if it better fits your specific use case</li>"

    choose_html = f'''<h2>When to Choose Each Tool</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0">
<div style="border:1px solid #d1fae5;background:#f0fdf4;border-radius:8px;padding:16px"><h3 style="margin-top:0">Choose {_esc(name_a)} if you need:</h3><ul style="color:#4b5563;margin-bottom:0">{_pts_li(choose_a_pts)}</ul></div>
<div style="border:1px solid #dbeafe;background:#eff6ff;border-radius:8px;padding:16px"><h3 style="margin-top:0">Choose {_esc(name_b)} if you need:</h3><ul style="color:#4b5563;margin-bottom:0">{_pts_li(choose_b_pts)}</ul></div>
</div>'''

    # Migration guide
    same_cat = cat_a.lower() == cat_b.lower()
    migration_html = f'''<h2>Switching from {_esc(name_a)} to {_esc(name_b)} (or vice versa)</h2>
<p>When migrating between {_esc(name_a)} and {_esc(name_b)}, consider these factors:</p>
<ol>
<li><strong>API Compatibility:</strong> {_esc(name_a)} ({_esc(cat_a)}) and {_esc(name_b)} ({_esc(cat_b)}) {"share similar interfaces since they are in the same category" if same_cat else "serve different categories, so migration may require significant refactoring"}.</li>
<li><strong>Security Review:</strong> Run a security audit after migration. Check the <a href="/is-{_esc(slug_a)}-safe">{_esc(name_a)} safety report</a> and <a href="/is-{_esc(slug_b)}-safe">{_esc(name_b)} safety report</a> for known issues.</li>
<li><strong>Testing:</strong> Ensure your test suite covers all integration points before switching in production.</li>
<li><strong>Community Support:</strong> {_esc(name_a)} has {stars_a:,} stars and {_esc(name_b)} has {stars_b:,}. Larger communities typically mean better Stack Overflow answers and migration guides.</li>
</ol>'''

    verdict_short = f"{_esc(name_a if score_a >= score_b else name_b)} scores higher ({_fmt_score(max(score_a,score_b))} vs {_fmt_score(min(score_a,score_b))})" if abs(score_a - score_b) >= 1 else "Essentially tied"
    today_str = date.today().isoformat()

    # L1b canary: "Detailed Score Analysis" FIVE_DIMS table + pplx-verdict.
    # Only populates when L1B_COMPARE_UNLOCK_REGISTRIES is set AND both slug
    # parts resolve to software_registry rows in the allowlisted registries.
    pplx_verdict_html = ""
    king_sections_html = ""
    if _L1B_COMPARE_UNLOCK_ALLOWLIST and "-vs-" in slug:
        sp_a, sp_b = slug.split("-vs-", 1)
        sr_a = _fetch_canary_scores(sp_a)
        sr_b = _fetch_canary_scores(sp_b)
        if sr_a and sr_b:
            # Dimension table — order mirrors agent_safety_pages.py:8380
            _dims = [
                ("Security", "security_score"),
                ("Maintenance", "maintenance_score"),
                ("Popularity", "popularity_score"),
                ("Quality", "quality_score"),
                ("Community", "community_score"),
            ]
            _name_ca = _esc(_short_name(sr_a["name"]))
            _name_cb = _esc(_short_name(sr_b["name"]))
            _rows = ""
            for dim_name, col in _dims:
                va = sr_a.get(col)
                vb = sr_b.get(col)
                def _cell(v):
                    if v is None:
                        return '<td style="text-align:right;color:#94a3b8">—</td>'
                    vf = float(v)
                    color = "#16a34a" if vf >= 70 else "#f59e0b" if vf >= 40 else "#dc2626"
                    return f'<td style="text-align:right;color:{color};font-weight:600">{vf:.0f}/100</td>'
                _rows += f"<tr><td>{dim_name}</td>{_cell(va)}{_cell(vb)}</tr>"
            king_sections_html = (
                '<div class="section" style="margin:20px 0">'
                '<h2>Detailed Score Analysis</h2>'
                '<table>'
                '<thead><tr>'
                '<th>Dimension</th>'
                f'<th style="text-align:right">{_name_ca}</th>'
                f'<th style="text-align:right">{_name_cb}</th>'
                '</tr></thead>'
                f'<tbody>{_rows}</tbody>'
                '</table>'
                '<p style="font-size:12px;color:#94a3b8;margin-top:6px">'
                f'Five-dimension Nerq trust breakdown '
                f'(registries: {_esc(sr_a["registry"])} / {_esc(sr_b["registry"])}). '
                'Scored equally weighted across security, maintenance, popularity, quality, community.'
                '</p>'
                '</div>'
            )
            _tsa = float(sr_a.get("trust_score") or 0)
            _tsb = float(sr_b.get("trust_score") or 0)
            _ga = _esc(sr_a.get("trust_grade") or "")
            _gb = _esc(sr_b.get("trust_grade") or "")
            if abs(_tsa - _tsb) < 1.0:
                _lead = "Nearly identical overall trust."
            elif _tsa > _tsb:
                _lead = f"{_name_ca} leads by {(_tsa - _tsb):.1f} points."
            else:
                _lead = f"{_name_cb} leads by {(_tsb - _tsa):.1f} points."
            pplx_verdict_html = (
                '<p class="pplx-verdict" style="font-size:1.05em;line-height:1.65;'
                'margin:12px 0 16px;padding:14px 18px;background:#f0fdf4;'
                'border-left:4px solid #16a34a;border-radius:4px">'
                f'<strong>{_name_ca}</strong> — Nerq Trust Score '
                f'<strong>{_tsa:.1f}/100{" (" + _ga + ")" if _ga else ""}</strong>. '
                f'<strong>{_name_cb}</strong> — Nerq Trust Score '
                f'<strong>{_tsb:.1f}/100{" (" + _gb + ")" if _gb else ""}</strong>. '
                f'{_lead}'
                '</p>'
            )

    # Render template
    html = (TEMPLATE_DIR / "agent_compare_page.html").read_text()
    replacements = {
        "{{ title }}": _esc(title),
        "{{ meta_description }}": _esc(meta_desc),
        "{{ slug }}": _esc(slug),
        "{{ name_a }}": _esc(name_a),
        "{{ name_b }}": _esc(name_b),
        "{{ name_a_raw }}": _esc(full_a),
        "{{ name_b_raw }}": _esc(full_b),
        "{{ slug_a }}": _esc(slug_a),
        "{{ slug_b }}": _esc(slug_b),
        "{{ score_a }}": f"{score_a:.1f}",
        "{{ score_b }}": f"{score_b:.1f}",
        "{{ grade_a }}": _esc(grade_a),
        "{{ grade_b }}": _esc(grade_b),
        "{{ pill_a }}": _grade_pill(grade_a),
        "{{ pill_b }}": _grade_pill(grade_b),
        "{{ score_class_a }}": score_class_a,
        "{{ score_class_b }}": score_class_b,
        "{{ verified_a }}": ver_a_html,
        "{{ verified_b }}": ver_b_html,
        "{{ stats_a }}": stats_a,
        "{{ stats_b }}": stats_b,
        "{{ comparison_rows }}": comp_rows,
        "{{ verdict }}": verdict,
        "{{ verdict_short }}": verdict_short,
        "{{ ai_summary }}": ai_summary,
        "{{ dimension_analysis }}": dim_html,
        "{{ choose_section }}": choose_html,
        "{{ migration_section }}": migration_html,
        "{{ faq_html }}": faq_html,
        "{{ related_section }}": related_section,
        "{{ webpage_jsonld }}": webpage_jsonld,
        "{{ dataset_jsonld }}": dataset_jsonld,
        "{{ faq_jsonld }}": faq_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
        "{{ today }}": today_str,
        "{{ nerq_css }}": NERQ_CSS,
        "{{ nerq_nav }}": NERQ_NAV,
        "{{ nerq_footer }}": NERQ_FOOTER,
        "{{ pplx_verdict }}": pplx_verdict_html,
        "{{ king_sections }}": king_sections_html,
    }
    for key, val in replacements.items():
        html = html.replace(key, str(val))
    return html


def _render_hub_page():
    """Render the comparison hub page."""
    _load_pairs()

    # Group pairs by category
    by_cat = defaultdict(list)
    for p in _pairs:
        by_cat[p.get("category", "other")].append(p)

    # Sort categories: coding first, then alphabetical
    cat_order = sorted(by_cat.keys(), key=lambda c: ("0" + c if c == "coding" else "1" + c))

    total = len(_pairs)
    category_sections = ""
    itemlist_items = []

    pos = 0
    for cat in cat_order:
        pairs_in_cat = by_cat[cat]
        category_sections += f'<div class="cat-group"><h2>{_esc(cat.title())} ({len(pairs_in_cat)})</h2>\n<div class="compare-grid">\n'

        for p in pairs_in_cat:
            pos += 1
            name_a = _short_name(p["agent_a"])
            name_b = _short_name(p["agent_b"])
            category_sections += (
                f'<a href="/compare/{_esc(p["slug"])}" class="compare-card">'
                f'<div class="cc-title">{_esc(name_a)} vs {_esc(name_b)}</div>'
                f'<div class="cc-cat">{_esc(cat)}</div>'
                f'</a>\n'
            )
            itemlist_items.append({
                "@type": "ListItem",
                "position": pos,
                "url": f"https://nerq.ai/compare/{p['slug']}",
                "name": f"{name_a} vs {name_b}",
            })

        category_sections += '</div></div>\n'

    itemlist_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Software Comparisons — {total} Side-by-Side Trust Reviews",
        "description": f"Compare {total} software pairs on trust, security, and maintenance.",
        "numberOfItems": total,
        "itemListElement": itemlist_items,
    })

    html = (TEMPLATE_DIR / "agent_compare_hub.html").read_text()
    html = html.replace("{{ total }}", str(total))
    html = html.replace("{{ category_sections }}", category_sections)
    html = html.replace("{{ itemlist_jsonld }}", itemlist_jsonld)
    html = html.replace("{{ nerq_css }}", NERQ_CSS)
    html = html.replace("{{ nerq_nav }}", NERQ_NAV)
    html = html.replace("{{ nerq_footer }}", NERQ_FOOTER)
    return html


def mount_agent_compare_pages(app):
    """Mount /compare hub route. Individual /compare/{slug} and /sitemap-compare.xml
    are handled via host-based dispatch in crypto_seo_pages.py to avoid route conflicts."""
    _load_pairs()

    @app.get("/compare", response_class=HTMLResponse)
    async def agent_compare_hub():
        try:
            html = _render_hub_page()
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Error rendering compare hub: {e}")
            return HTMLResponse(status_code=500, content=f"<h1>Error</h1><p>{_esc(str(e))}</p>")

    logger.info(f"Mounted agent compare hub: {len(_pair_map)} pairs")
