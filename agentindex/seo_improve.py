"""
Nerq Improve & Widget Pages (System 1 + System 2)
===================================================
- /improve/{tool} — Personalized improvement plan
- /widget — Embeddable widget customization page

Usage in discovery.py:
    from agentindex.seo_improve import mount_seo_improve
    mount_seo_improve(app)
"""

import html
import json
import logging
import re
from datetime import date

from fastapi.responses import HTMLResponse
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.seo_improve")

SITE = "https://nerq.ai"
YEAR = date.today().year
TODAY = date.today().isoformat()


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


def _stars_fmt(v) -> str:
    if not v:
        return "-"
    try:
        n = int(v)
        return f"{n / 1000:.1f}k" if n >= 1000 else str(n)
    except (TypeError, ValueError):
        return "-"


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
<style>{NERQ_CSS}
.bar-bg {{background:#e5e7eb;height:20px;border-radius:4px;overflow:hidden;margin:4px 0}}
.bar-fill {{height:100%;border-radius:4px;transition:width 0.3s}}
.action-card {{border:1px solid #e5e7eb;padding:16px;margin:12px 0;border-radius:8px}}
.action-card:hover {{border-color:#2563eb}}
.points-badge {{background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:12px;font-size:13px;font-weight:600}}
.diff-easy {{color:#16a34a}} .diff-medium {{color:#ca8a04}} .diff-hard {{color:#dc2626}}
pre {{background:#f9fafb;padding:12px;border-radius:6px;overflow-x:auto;font-size:13px;border:1px solid #e5e7eb}}
</style>
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


def _score_bar(label: str, value, max_val: int = 100) -> str:
    v = 0
    try:
        v = float(value) if value else 0
    except (TypeError, ValueError):
        pass
    pct = min(100, max(0, v / max_val * 100))
    color = "#16a34a" if pct >= 70 else "#ca8a04" if pct >= 50 else "#dc2626"
    return f"""<div style="display:flex;align-items:center;gap:8px;margin:6px 0">
<div style="width:120px;font-weight:600;font-size:14px">{html.escape(label)}</div>
<div class="bar-bg" style="flex:1"><div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>
<div style="width:40px;text-align:right;font-weight:600;font-size:14px">{_score_fmt(value)}</div>
</div>"""


def mount_seo_improve(app):
    """Mount /improve/{tool} and /widget routes."""

    # ── /improve/{tool} ────────────────────────────────────
    @app.get("/improve/{tool_slug}", response_class=HTMLResponse)
    async def improve_page(tool_slug: str):
        from agentindex.intelligence.improvement_engine import get_improvements

        plan = get_improvements(tool_slug)
        if not plan:
            return HTMLResponse(_page("Tool not found | Nerq",
                f'{_breadcrumb(("/improve", "Improve"), ("", "not found"))}<h1>Tool not found</h1>'
                f'<meta name="robots" content="noindex">'
                f'<p><a href="/discover">Search all tools</a></p>'), status_code=410)

        agent = plan["agent"]
        actions = plan["actions"]
        competitors = plan["competitors"]
        name = html.escape(agent["name"])
        slug = _to_slug(agent["name"])
        ts = agent.get("trust_score_v2") or 0
        tg = agent.get("trust_grade")
        est = plan["estimated_new_score"]
        rank = plan["current_rank"]
        total = plan["total_in_category"]

        # Score breakdown
        bars = _score_bar("Security", agent.get("security_score"))
        bars += _score_bar("Activity", agent.get("activity_score"))
        bars += _score_bar("Documentation", agent.get("documentation_score"))
        bars += _score_bar("Popularity", agent.get("popularity_score"))

        score_section = f"""<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:16px 0">
<div>
<h2 style="margin-top:0">Current Score</h2>
<div style="text-align:center;margin:16px 0">
<div style="font-size:3em;font-weight:700;color:{_grade_color(tg)}">{_score_fmt(ts)}<span style="font-size:0.4em;color:#6b7280">/100</span></div>
<div style="font-size:1.4em">{_grade_pill(tg)}</div>
{f'<div style="color:#6b7280;margin-top:4px">Rank #{rank} of {total} in {html.escape(agent.get("category") or "all")}</div>' if rank else ''}
</div>
{bars}
</div>
<div>
<h2 style="margin-top:0">After Improvements</h2>
<div style="text-align:center;margin:16px 0">
<div style="font-size:3em;font-weight:700;color:#16a34a">{est}<span style="font-size:0.4em;color:#6b7280">/100</span></div>
<div style="color:#16a34a;font-weight:600">+{plan['total_potential_points']} potential points</div>
<div style="color:#6b7280;margin-top:4px">{len(actions)} actions available</div>
</div>
<div style="background:#ecfdf5;border:1px solid #a7f3d0;padding:16px;border-radius:8px;margin-top:16px">
<strong>Quick wins:</strong> {sum(1 for a in actions if a['difficulty'] == 'easy')} easy actions worth {sum(a['points'] for a in actions if a['difficulty'] == 'easy')} points
</div>
</div>
</div>"""

        # Action cards
        action_html = "<h2>Improvement Actions</h2><p>Ranked by point impact. Each action includes a copy-paste template.</p>"
        for i, a in enumerate(actions, 1):
            diff_class = f"diff-{a['difficulty']}"
            template_block = ""
            if a.get("template"):
                escaped_template = html.escape(a["template"])
                template_block = f'<details style="margin-top:8px"><summary style="cursor:pointer;color:#2563eb;font-size:13px">Copy template</summary><pre>{escaped_template}</pre></details>'

            action_html += f"""<div class="action-card">
<div style="display:flex;justify-content:space-between;align-items:center">
<h3 style="margin:0">{i}. {html.escape(a['title'])}</h3>
<div><span class="points-badge">+{a['points']} pts</span> <span class="{diff_class}" style="font-size:13px;margin-left:4px">{a['difficulty']}</span></div>
</div>
<p style="color:#4b5563;margin:8px 0">{html.escape(a['description'])}</p>
<div style="color:#6b7280;font-size:13px">Dimension: {html.escape(a['dimension'])}</div>
{template_block}
</div>"""

        # Competitor table
        comp_html = ""
        if competitors:
            comp_rows = ""
            for c in competitors[:5]:
                cslug = _to_slug(c["name"])
                comp_rows += f'<tr><td><a href="/is-{cslug}-safe">{html.escape(c["name"])}</a></td><td>{_score_fmt(c["score"])}</td><td>{_grade_pill(c["grade"])}</td><td>{_stars_fmt(c["stars"])}</td><td><a href="/improve/{cslug}" style="font-size:13px">improve</a></td></tr>'

            comp_html = f"""<h2>Competitors in {html.escape(agent.get('category') or 'your category')}</h2>
<table><thead><tr><th>Name</th><th>Trust</th><th>Grade</th><th>Stars</th><th></th></tr></thead>
<tbody>{comp_rows}</tbody></table>"""

        # CTA
        cta = f"""<div style="background:#eff6ff;border:1px solid #bfdbfe;padding:20px;border-radius:8px;margin:20px 0;text-align:center">
<h3>Need help improving?</h3>
<p>Implement these actions and your score will update automatically on the next crawl.</p>
<p><a href="/is-{slug}-safe" style="color:#2563eb">View full safety report</a> &middot; <a href="/alternatives/{slug}" style="color:#2563eb">See alternatives</a> &middot; <a href="/compare" style="color:#2563eb">Compare tools</a></p>
</div>"""

        jsonld = json.dumps({
            "@context": "https://schema.org", "@type": "HowTo",
            "name": f"Improve {agent['name']} Trust Score",
            "step": [{"@type": "HowToStep", "name": a["title"], "text": a["description"]} for a in actions[:5]]
        })

        title = f"Improve {agent['name']} Trust Score — {len(actions)} Actions | Nerq"
        desc = f"{agent['name']} scores {_score_fmt(ts)}/100. {len(actions)} specific actions to reach {est}. Templates included."

        body = f"""{_breadcrumb(("/improve", "Improve"), ("", name))}
<h1>Improve {name} Trust Score</h1>
<p class="desc">Personalized improvement plan. Updated {TODAY}.</p>
{score_section}{action_html}{comp_html}{cta}"""

        return HTMLResponse(_page(title, body, desc=desc,
                                   canonical=f"{SITE}/improve/{tool_slug}", jsonld=jsonld))

    # ── /improve hub ───────────────────────────────────────
    @app.get("/improve", response_class=HTMLResponse)
    async def improve_hub():
        from agentindex.db.models import get_db_session
        from sqlalchemy.sql import text as sqlt

        with get_db_session() as session:
            rows = session.execute(sqlt("""
                SELECT name, trust_score_v2, trust_grade, stars, category
                FROM agents WHERE is_active = true AND trust_score_v2 IS NOT NULL
                  AND trust_score_v2 < 80
                ORDER BY COALESCE(stars, 0) DESC
                LIMIT 30
            """)).fetchall()

        items = ""
        for r in rows:
            name, score, grade, stars, cat = r
            slug = _to_slug(name)
            items += f'<tr><td><a href="/improve/{slug}">{html.escape(name)}</a></td><td>{_score_fmt(score)}</td><td>{_grade_pill(grade)}</td><td>{_stars_fmt(stars)}</td><td>{html.escape(cat or "-")}</td></tr>'

        body = f"""{_breadcrumb(("", "Improve"))}
<h1>Improve Your Trust Score</h1>
<p class="desc">Popular tools with room to improve. Click any tool for a personalized action plan.</p>
<table><thead><tr><th>Tool</th><th>Score</th><th>Grade</th><th>Stars</th><th>Category</th></tr></thead>
<tbody>{items}</tbody></table>
<p style="margin-top:16px;color:#6b7280">Search for any tool at <a href="/discover">/discover</a> then visit /improve/tool-name for its improvement plan.</p>"""

        return HTMLResponse(_page(f"Improve AI Tool Trust Scores {YEAR} | Nerq", body,
                                   desc="Get personalized improvement plans for any AI tool. Specific actions with point values and templates.",
                                   canonical=f"{SITE}/improve"))

    # ── /widget customization page ─────────────────────────
    @app.get("/widget", response_class=HTMLResponse)
    async def widget_page():
        body = f"""{_breadcrumb(("", "Widget"))}
<h1>Nerq Trust Widget</h1>
<p class="desc">Embed trust scores on any website. Two styles: badge and card.</p>

<h2>1. Choose a tool</h2>
<div style="display:flex;gap:8px;margin:12px 0">
<input type="text" id="widget-tool" placeholder="e.g., langchain" style="flex:1;padding:8px;border:1px solid #d1d5db;border-radius:6px;font-size:14px" value="langchain">
<select id="widget-style" style="padding:8px;border:1px solid #d1d5db;border-radius:6px">
<option value="badge">Badge (inline)</option>
<option value="card">Card (full)</option>
</select>
<button onclick="updatePreview()" style="padding:8px 16px;background:#2563eb;color:white;border:none;border-radius:6px;cursor:pointer">Preview</button>
</div>

<h2>2. Preview</h2>
<div id="widget-preview" style="border:1px solid #e5e7eb;padding:20px;border-radius:8px;min-height:60px;background:#fafafa">
<div style="color:#6b7280">Enter a tool name and click Preview</div>
</div>

<h2>3. Copy embed code</h2>
<div style="position:relative">
<pre id="widget-code" style="background:#1e293b;color:#e2e8f0;padding:16px;border-radius:8px;font-size:13px">&lt;script src="https://nerq.ai/static/widget.js" data-nerq-tool="langchain" data-nerq-style="badge"&gt;&lt;/script&gt;</pre>
<button onclick="copyCode()" style="position:absolute;top:8px;right:8px;padding:4px 12px;background:#334155;color:white;border:none;border-radius:4px;cursor:pointer;font-size:12px">Copy</button>
</div>

<h2>Examples</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0">
<div style="border:1px solid #e5e7eb;padding:16px;border-radius:8px">
<h3 style="margin-top:0">Badge style</h3>
<code style="font-size:12px;color:#6b7280">&lt;script src="https://nerq.ai/static/widget.js" data-nerq-tool="langchain" data-nerq-style="badge"&gt;&lt;/script&gt;</code>
<div style="margin-top:12px" id="example-badge"></div>
</div>
<div style="border:1px solid #e5e7eb;padding:16px;border-radius:8px">
<h3 style="margin-top:0">Card style</h3>
<code style="font-size:12px;color:#6b7280">&lt;script ... data-nerq-style="card"&gt;&lt;/script&gt;</code>
<div style="margin-top:12px" id="example-card"></div>
</div>
</div>

<h2>Usage</h2>
<ul>
<li>Add the script tag anywhere in your HTML</li>
<li>Works on any website — no dependencies</li>
<li>Updates automatically (cached 1 hour)</li>
<li>Tiny footprint (~1KB, no external CSS/JS)</li>
<li>Links to full safety report on nerq.ai</li>
</ul>

<script>
function updatePreview() {{
  var tool = document.getElementById('widget-tool').value.trim();
  var style = document.getElementById('widget-style').value;
  if (!tool) return;

  // Update code
  var code = '<script src="https://nerq.ai/static/widget.js" data-nerq-tool="' + tool + '" data-nerq-style="' + style + '"><\\/script>';
  document.getElementById('widget-code').textContent = code;

  // Fetch and preview
  var preview = document.getElementById('widget-preview');
  preview.innerHTML = '<div style="color:#6b7280">Loading...</div>';

  fetch('/v1/preflight?target=' + encodeURIComponent(tool) + '&source=widget')
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      var score = d.trust_score || '?';
      var grade = d.target_grade || '?';
      var name = d.target_name || tool;
      var color = score >= 70 ? '#16a34a' : score >= 50 ? '#ca8a04' : '#dc2626';

      if (style === 'badge') {{
        preview.innerHTML = '<a href="https://nerq.ai/is-' + tool + '-safe" target="_blank" style="display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;background:' + color + '22;color:' + color + ';font:600 12px system-ui;text-decoration:none">Trust: ' + score + ' (' + grade + ')</a>';
      }} else {{
        preview.innerHTML = '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;font:14px system-ui;max-width:280px"><div style="font-weight:600">' + name + '</div><div style="color:' + color + ';font-size:20px;font-weight:700">' + score + '/100 (' + grade + ')</div><div style="color:#6b7280;font-size:12px">Updated daily</div><a href="https://nerq.ai/is-' + tool + '-safe" target="_blank" style="color:#2563eb;font-size:12px">Full report &rarr;</a><div style="color:#9ca3af;font-size:10px;margin-top:4px">Powered by Nerq</div></div>';
      }}
    }})
    .catch(function() {{ preview.innerHTML = '<div style="color:#dc2626">Tool not found</div>'; }});
}}

function copyCode() {{
  var text = document.getElementById('widget-code').textContent;
  navigator.clipboard.writeText(text).then(function() {{
    var btn = event.target;
    btn.textContent = 'Copied!';
    setTimeout(function() {{ btn.textContent = 'Copy'; }}, 2000);
  }});
}}

// Load examples on page load
window.addEventListener('load', function() {{
  fetch('/v1/preflight?target=langchain&source=widget')
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      var score = d.trust_score || '?';
      var grade = d.target_grade || '?';
      var color = score >= 70 ? '#16a34a' : score >= 50 ? '#ca8a04' : '#dc2626';

      document.getElementById('example-badge').innerHTML = '<a href="#" style="display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;background:' + color + '22;color:' + color + ';font:600 12px system-ui;text-decoration:none">Trust: ' + score + ' (' + grade + ')</a>';
      document.getElementById('example-card').innerHTML = '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px;font:14px system-ui;max-width:280px"><div style="font-weight:600">langchain</div><div style="color:' + color + ';font-size:20px;font-weight:700">' + score + '/100 (' + grade + ')</div><div style="color:#6b7280;font-size:12px">Updated daily</div><a href="#" style="color:#2563eb;font-size:12px">Full report &rarr;</a><div style="color:#9ca3af;font-size:10px;margin-top:4px">Powered by Nerq</div></div>';
    }});
}});
</script>"""

        return HTMLResponse(_page(f"Embeddable Trust Widget | Nerq", body,
                                   desc="Embed Nerq trust scores on any website. Badge and card styles. Copy-paste embed code.",
                                   canonical=f"{SITE}/widget"))

    logger.info("Mounted: /improve, /widget")
