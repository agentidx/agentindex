"""
/index page — Ecosystem Trust Index dashboard.

Renders the daily ecosystem trust index with sub-indices,
grade distribution, source rankings, and FAQ schema.
"""

import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger(__name__)
TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "ecosystem_index.html"

GRADE_COLORS = {
    "A+": "#059669", "A": "#059669",
    "B+": "#0d9488", "B": "#0d9488", "B-": "#0d9488",
    "C+": "#d97706", "C": "#d97706", "C-": "#d97706",
    "D+": "#dc2626", "D": "#dc2626", "D-": "#dc2626",
    "E": "#7f1d1d", "F": "#7f1d1d",
}

GRADE_ORDER = ["A+", "A", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "E", "F"]


def _grade_class(letter):
    if letter.startswith("A"):
        return "grade-a"
    if letter.startswith("B"):
        return "grade-b"
    if letter.startswith("C"):
        return "grade-c"
    if letter.startswith("D"):
        return "grade-d"
    return "grade-f"


def _render_index_page(snapshot: dict) -> str:
    html = TEMPLATE_PATH.read_text()

    overall = snapshot.get("overall", {})
    grades = snapshot.get("grades", {})
    sources = snapshot.get("sources", {})
    security = snapshot.get("security", {})
    maintenance = snapshot.get("maintenance", {})
    license_idx = snapshot.get("license", {})
    framework_idx = snapshot.get("framework", {})
    stars_corr = snapshot.get("stars_correlation", {})

    idx_val = overall.get("weighted_index", 0)
    total = overall.get("total_agents", 0)
    median = overall.get("median", 0)

    # Grade letter
    if idx_val >= 80:
        gl = "A"
    elif idx_val >= 70:
        gl = "B"
    elif idx_val >= 60:
        gl = "C"
    elif idx_val >= 50:
        gl = "D"
    else:
        gl = "F"

    pcts = grades.get("percentages", {})
    counts = grades.get("counts", {})
    d_pct = round(pcts.get("D", 0) + pcts.get("D+", 0) + pcts.get("D-", 0), 1)
    a_pct = round(pcts.get("A", 0) + pcts.get("A+", 0), 2)
    b_plus_pct = round(pcts.get("B+", 0) + pcts.get("B", 0) + pcts.get("B-", 0) + a_pct, 2)
    a_count = counts.get("A", 0) + counts.get("A+", 0)

    # Grade distribution bars
    grade_bars = []
    grade_legend = []
    grade_total = sum(counts.get(g, 0) for g in GRADE_ORDER)
    for g in GRADE_ORDER:
        c = counts.get(g, 0)
        if c == 0:
            continue
        pct = c / grade_total * 100
        color = GRADE_COLORS.get(g, "#6b7280")
        label = g if pct > 3 else ""
        grade_bars.append(
            f'<div style="width:{pct}%;background:{color}" title="{g}: {c:,} ({pct:.1f}%)">{label}</div>'
        )
        grade_legend.append(
            f'<span><span style="display:inline-block;width:10px;height:10px;background:{color};margin-right:4px"></span>{g}: {pct:.1f}%</span>'
        )

    # Source rows
    source_rows = []
    for src, data in sorted(sources.items(), key=lambda x: x[1].get("avg_score", 0), reverse=True)[:12]:
        source_rows.append(
            f'<tr><td>{src}</td><td class="mono">{data["count"]:,}</td>'
            f'<td class="mono">{data["avg_score"]}</td>'
            f'<td class="mono">{data.get("median", "—")}</td></tr>'
        )

    # Stars rows
    stars_rows = []
    bucket_order = ["0", "1-99", "100-999", "1K-10K", "10K-100K", "100K+"]
    for bucket in bucket_order:
        data = stars_corr.get(bucket, {})
        if data:
            stars_rows.append(
                f'<tr><td>{bucket}</td><td class="mono">{data["count"]:,}</td>'
                f'<td class="mono">{data["avg"]}</td>'
                f'<td class="mono">{data.get("median", "—")}</td></tr>'
            )

    # FAQ JSON-LD
    faq_items = [
        {"q": "What is the Nerq Ecosystem Trust Index?",
         "a": f"A daily-calculated metric measuring trust health across {total:,} AI agents from GitHub, npm, PyPI, Docker Hub, HuggingFace, and MCP registries."},
        {"q": "How is the trust index calculated?",
         "a": "Each agent receives a trust score (0-100) based on 13+ signals including security, maintenance, licenses, and community trust. The index weights by adoption (downloads > stars > equal)."},
        {"q": f"Why is the index only {idx_val}?",
         "a": f"{d_pct}% of agents are D-grade. Most lack security practices, documentation, or active maintenance. The ecosystem is in its early phase."},
        {"q": "What percentage of AI agents are safe to use?",
         "a": f"Only {b_plus_pct}% earn B or above. {a_pct}% earn an A. {d_pct}% are D-grade."},
        {"q": "How often is the index updated?",
         "a": "Daily at 09:45 UTC. Historical values tracked for trend analysis."},
    ]
    faq_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": item["q"],
             "acceptedAnswer": {"@type": "Answer", "text": item["a"]}}
            for item in faq_items
        ]
    })

    breadcrumb_jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Nerq", "item": "https://nerq.ai/"},
            {"@type": "ListItem", "position": 2, "name": "Ecosystem Trust Index", "item": "https://nerq.ai/index"},
        ]
    })

    replacements = {
        "{{ nerq_css }}": NERQ_CSS,
        "{{ nerq_nav }}": NERQ_NAV,
        "{{ nerq_footer }}": NERQ_FOOTER,
        "{{ index_value }}": str(idx_val),
        "{{ grade_letter }}": gl,
        "{{ grade_class }}": _grade_class(gl),
        "{{ total_agents }}": f"{total:,}",
        "{{ total_agents_raw }}": f"{total:,}",
        "{{ date }}": snapshot.get("date", "today"),
        "{{ median }}": str(median),
        "{{ d_pct }}": str(d_pct),
        "{{ a_pct }}": str(a_pct),
        "{{ b_plus_pct }}": str(b_plus_pct),
        "{{ a_count }}": f"{a_count:,}",
        "{{ security_index }}": str(security.get("index", "—")),
        "{{ security_cves }}": str(security.get("total_cves", 0)),
        "{{ security_agents }}": str(security.get("agents_with_cves", 0)),
        "{{ maintenance_index }}": str(maintenance.get("index", "—")),
        "{{ maintenance_fresh_pct }}": str(maintenance.get("freshness_30d_pct", maintenance.get("freshness_pct", 0))),
        "{{ license_pct }}": str(round(license_idx.get("index", 0))),
        "{{ license_total }}": f"{license_idx.get('total_licensed', 0):,}",
        "{{ framework_count }}": str(framework_idx.get("agents_with_frameworks", 0)),
        "{{ mcp_count }}": str(framework_idx.get("mcp_compatible", 0)),
        "{{ grade_bars }}": "\n    ".join(grade_bars),
        "{{ grade_legend }}": "\n    ".join(grade_legend),
        "{{ source_rows }}": "\n      ".join(source_rows),
        "{{ stars_rows }}": "\n      ".join(stars_rows),
        "{{ faq_jsonld }}": faq_jsonld,
        "{{ breadcrumb_jsonld }}": breadcrumb_jsonld,
    }

    for key, val in replacements.items():
        html = html.replace(key, val)

    return html


def mount_ecosystem_index(app: FastAPI):
    @app.get("/index", response_class=HTMLResponse, include_in_schema=False)
    async def ecosystem_index_page():
        from agentindex.intelligence.ecosystem_index import get_latest_snapshot
        snapshot = get_latest_snapshot()
        if not snapshot:
            return HTMLResponse("<h1>Index not yet calculated</h1><p>Check back after 09:45 UTC.</p>", status_code=503)
        return HTMLResponse(_render_index_page(snapshot))

    @app.get("/v1/index", include_in_schema=False)
    async def ecosystem_index_api():
        from agentindex.intelligence.ecosystem_index import get_latest_snapshot
        snapshot = get_latest_snapshot()
        if not snapshot:
            return {"error": "not_calculated", "message": "Index not yet calculated"}
        return {
            "index": snapshot.get("overall", {}),
            "grades": snapshot.get("grades", {}),
            "security": snapshot.get("security", {}),
            "maintenance": snapshot.get("maintenance", {}),
            "license": snapshot.get("license", {}),
            "date": snapshot.get("date"),
        }
