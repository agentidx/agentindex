"""
Nerq Project Health Report Pages
=================================
Public report pages for scanned GitHub projects.
Shows dependency health, CVEs, trust scores, and CI integration.
"""

import json
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.sql import text

from agentindex.nerq_design import nerq_page
from agentindex.db.models import get_engine


def _grade_pill(grade: str) -> str:
    """Return CSS class for grade pill."""
    if grade in ("A", "B"):
        return "pill-green"
    elif grade == "C":
        return "pill-yellow"
    return "pill-red"


def _grade_color(grade: str) -> str:
    """Return hex color for grade."""
    if grade in ("A", "B"):
        return "#065f46"
    elif grade == "C":
        return "#92400e"
    return "#991b1b"


def _grade_bg(grade: str) -> str:
    """Return background hex for grade hero."""
    if grade in ("A", "B"):
        return "#ecfdf5"
    elif grade == "C":
        return "#fffbeb"
    return "#fef2f2"


def _grade_border(grade: str) -> str:
    if grade in ("A", "B"):
        return "#a7f3d0"
    elif grade == "C":
        return "#fde68a"
    return "#fecaca"


def _dep_grade(score: float) -> str:
    """Convert a 0-100 trust score to a letter grade."""
    if score is None:
        return "?"
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    if score >= 20:
        return "D"
    return "F"


def _render_report(row, owner: str, repo: str) -> str:
    grade = row.project_health_grade or "?"
    score = row.avg_trust_score or 0
    total = row.total_deps or 0
    critical = row.critical_cves or 0
    high = row.high_cves or 0
    deps_cves = row.deps_with_cves or 0
    no_license = row.deps_without_license or 0
    low_trust = row.deps_low_trust or 0
    scanned = row.scanned_at
    top_issues = row.top_issues if row.top_issues else []
    dep_list = row.dep_list if row.dep_list else []
    stars = row.github_stars or 0
    cost = row.estimated_monthly_cost

    if isinstance(top_issues, str):
        top_issues = json.loads(top_issues)
    if isinstance(dep_list, str):
        dep_list = json.loads(dep_list)

    scanned_str = ""
    if scanned:
        if isinstance(scanned, str):
            scanned_str = scanned[:10]
        else:
            scanned_str = scanned.strftime("%Y-%m-%d")

    pill_cls = _grade_pill(grade)
    g_color = _grade_color(grade)
    g_bg = _grade_bg(grade)
    g_border = _grade_border(grade)

    # --- Hero ---
    hero = f"""
    <div style="background:{g_bg};border:1px solid {g_border};padding:32px;margin-bottom:24px;display:flex;align-items:center;gap:32px;flex-wrap:wrap">
      <div style="font-size:5rem;font-weight:800;color:{g_color};font-family:ui-monospace,'SF Mono',monospace;line-height:1">{grade}</div>
      <div>
        <h1 style="font-size:1.5rem;margin-bottom:4px">{owner}/{repo}</h1>
        <div style="color:#6b7280;font-size:14px">Scanned {scanned_str}. {total} dependencies analyzed.</div>
        <div style="margin-top:8px">
          <span class="pill {pill_cls}" style="font-size:14px;padding:2px 10px">Score: {score:.0f}/100</span>
          {"<span style='margin-left:8px;color:#6b7280;font-size:13px'>" + str(stars) + " stars</span>" if stars else ""}
        </div>
      </div>
    </div>"""

    # --- Critical Issues ---
    critical_issues = [i for i in top_issues if i.get("severity") == "critical"] if top_issues else []
    critical_section = ""
    if critical > 0 or critical_issues:
        items = ""
        for iss in critical_issues:
            cve_id = iss.get("cve_id", "")
            pkg = iss.get("package", "")
            desc = iss.get("description", "")
            items += f'<div style="padding:8px 0;border-bottom:1px solid rgba(153,27,27,0.15)"><strong>{cve_id}</strong> in <code>{pkg}</code><br><span style="font-size:13px;color:#7f1d1d">{desc}</span></div>'
        if not items and critical > 0:
            items = f'<div style="padding:8px 0">{critical} critical CVE(s) found across {deps_cves} dependencies.</div>'
        critical_section = f"""
        <div style="background:#fef2f2;border:1px solid #fecaca;padding:16px;margin-bottom:16px">
          <h2 style="border:none;margin:0 0 8px;padding:0;color:#991b1b;font-size:1rem">Critical Issues ({critical})</h2>
          {items}
        </div>"""

    # --- Warnings ---
    high_issues = [i for i in top_issues if i.get("severity") == "high"] if top_issues else []
    warning_items = ""
    if high > 0:
        for iss in high_issues:
            cve_id = iss.get("cve_id", "")
            pkg = iss.get("package", "")
            desc = iss.get("description", "")
            warning_items += f'<div style="padding:6px 0;border-bottom:1px solid rgba(146,64,14,0.15)"><strong>{cve_id}</strong> in <code>{pkg}</code> &mdash; {desc}</div>'
        if not warning_items:
            warning_items = f'<div style="padding:6px 0">{high} high-severity CVE(s) detected.</div>'
    if low_trust > 0:
        warning_items += f'<div style="padding:6px 0"><strong>{low_trust}</strong> dependencies with low trust scores (&lt;40)</div>'
    if no_license > 0:
        warning_items += f'<div style="padding:6px 0"><strong>{no_license}</strong> dependencies without a declared license</div>'

    warnings_section = ""
    if warning_items:
        warnings_section = f"""
        <div style="background:#fffbeb;border:1px solid #fde68a;padding:16px;margin-bottom:16px">
          <h2 style="border:none;margin:0 0 8px;padding:0;color:#92400e;font-size:1rem">Warnings</h2>
          {warning_items}
        </div>"""

    # --- Dependency Table ---
    dep_rows = ""
    for dep in dep_list:
        dname = dep.get("name", "unknown")
        dscore = dep.get("trust_score")
        dscore_str = f"{dscore:.0f}" if dscore is not None else "&mdash;"
        dgrade = _dep_grade(dscore)
        dpill = _grade_pill(dgrade)
        dissues = dep.get("issues", [])
        dissue_str = ", ".join(dissues) if dissues else "&mdash;"
        dep_rows += f"""<tr>
          <td><code>{dname}</code></td>
          <td>{dscore_str}</td>
          <td><span class="pill {dpill}">{dgrade}</span></td>
          <td style="font-size:13px;color:#6b7280">{dissue_str}</td>
        </tr>"""

    dep_table = ""
    if dep_rows:
        dep_table = f"""
        <h2>Dependencies ({total})</h2>
        <div style="overflow-x:auto">
        <table>
          <thead><tr><th>Package</th><th>Trust Score</th><th>Grade</th><th>Issues</th></tr></thead>
          <tbody>{dep_rows}</tbody>
        </table>
        </div>"""

    # --- CI Integration ---
    ci_yaml = f"""name: Nerq Health Check
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 6 * * 1'

jobs:
  health-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Nerq Scan
        run: |
          curl -s "https://nerq.ai/report/{owner}/{repo}.json" | jq .project_health_grade
          GRADE=$(curl -s "https://nerq.ai/report/{owner}/{repo}.json" | jq -r .project_health_grade)
          if [ "$GRADE" = "D" ] || [ "$GRADE" = "F" ]; then
            echo "Health grade $GRADE is below threshold"
            exit 1
          fi"""

    ci_section = f"""
    <h2>Add to CI</h2>
    <p class="desc">Add this GitHub Action to check project health on every push.</p>
    <pre>{ci_yaml}</pre>"""

    # --- Badge ---
    badge_md = f"![Nerq Health](https://nerq.ai/report-badge/{owner}/{repo}.svg)"
    badge_section = f"""
    <h2>Badge</h2>
    <p class="desc">Add the health badge to your README:</p>
    <pre>{badge_md}</pre>
    <p style="margin-top:8px">{badge_md.replace("![Nerq Health]", '<img alt="Nerq Health" src').replace(")", '" style="height:20px">')}</p>"""

    # --- JSON-LD ---
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": f"{owner}/{repo}",
        "url": f"https://github.com/{owner}/{repo}",
        "applicationCategory": "DeveloperApplication",
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": str(round(score, 1)),
            "bestRating": "100",
            "worstRating": "0",
            "ratingCount": str(total),
        },
    }, indent=2)
    jsonld_tag = f'<script type="application/ld+json">{jsonld}</script>'

    # --- Breadcrumb ---
    breadcrumb = f'<div class="breadcrumb"><a href="/">nerq</a> / <a href="/reports">reports</a> / {owner}/{repo}</div>'

    # --- Cost estimate ---
    cost_line = ""
    if cost is not None:
        cost_line = f'<div style="margin:12px 0;font-size:14px;color:#6b7280">Estimated monthly dependency cost: <strong>${cost:,.0f}</strong></div>'

    body = f"""{breadcrumb}
    {hero}
    {critical_section}
    {warnings_section}
    {cost_line}
    {dep_table}
    {ci_section}
    {badge_section}
    {jsonld_tag}"""

    title = f"{owner}/{repo} Security Report \u2014 {total} Dependencies | Nerq"
    desc = f"Health grade {grade} for {owner}/{repo}. {critical} critical CVEs, {total} dependencies analyzed. Independent trust scoring by Nerq."
    canonical = f"https://nerq.ai/report/{owner}/{repo}"

    return nerq_page(title=title, body=body, description=desc, canonical=canonical)


def _render_not_scanned(owner: str, repo: str) -> str:
    body = f"""
    <div class="breadcrumb"><a href="/">nerq</a> / <a href="/reports">reports</a> / {owner}/{repo}</div>
    <div style="text-align:center;padding:60px 0">
      <div style="font-size:4rem;font-weight:800;color:#d1d5db;font-family:ui-monospace,'SF Mono',monospace">?</div>
      <h1 style="margin:12px 0 8px">{owner}/{repo}</h1>
      <p class="desc" style="margin-bottom:24px">This project has not been scanned yet.</p>
      <a href="/scan?repo={owner}/{repo}" class="pill pill-green" style="font-size:15px;padding:8px 24px;text-decoration:none;border-radius:2px">Scan Now</a>
      <p style="margin-top:16px;font-size:13px;color:#9ca3af">Free scan &mdash; takes about 30 seconds</p>
    </div>"""
    title = f"{owner}/{repo} \u2014 Not Yet Scanned | Nerq"
    desc = f"Request a health scan for {owner}/{repo} on Nerq."
    canonical = f"https://nerq.ai/report/{owner}/{repo}"
    return nerq_page(title=title, body=body, description=desc, canonical=canonical)


def mount_report_pages(app):
    """Mount project health report routes on the FastAPI app."""

    @app.get("/report/{owner}/{repo}", response_class=HTMLResponse)
    async def report_page(owner: str, repo: str):
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM project_scans WHERE repo_full_name = :name"),
                {"name": f"{owner}/{repo}"},
            ).fetchone()

        if not row:
            return HTMLResponse(_render_not_scanned(owner, repo), status_code=404)
        return HTMLResponse(_render_report(row, owner, repo))

    @app.get("/report/{owner}/{repo}.json")
    async def report_json(owner: str, repo: str):
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM project_scans WHERE repo_full_name = :name"),
                {"name": f"{owner}/{repo}"},
            ).fetchone()

        if not row:
            return JSONResponse({"error": "not_scanned", "repo": f"{owner}/{repo}"}, status_code=404)

        data = dict(row._mapping)
        # Serialize datetime and non-JSON-safe types
        for k, v in data.items():
            if isinstance(v, datetime):
                data[k] = v.isoformat()
        return JSONResponse(data)
