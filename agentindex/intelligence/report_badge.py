"""
Nerq Project Health Badge (SVG)
================================
Shields.io-style SVG badge showing the project health grade.
GET /report-badge/{owner}/{repo}.svg
"""

from fastapi.responses import Response
from sqlalchemy.sql import text

from agentindex.db.models import get_engine


def _badge_svg(label: str, value: str, value_color: str, value_bg: str) -> str:
    """Generate a shields.io-style SVG badge."""
    label_width = len(label) * 6.5 + 12
    value_width = len(value) * 7.5 + 12
    total_width = label_width + value_width
    label_x = label_width / 2
    value_x = label_width + value_width / 2

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width:.0f}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width:.0f}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width:.0f}" height="20" fill="#555"/>
    <rect x="{label_width:.0f}" width="{value_width:.0f}" height="20" fill="{value_bg}"/>
    <rect width="{total_width:.0f}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="11">
    <text aria-hidden="true" x="{label_x:.0f}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_x:.0f}" y="14" fill="#fff">{label}</text>
    <text aria-hidden="true" x="{value_x:.0f}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{value_x:.0f}" y="14" fill="{value_color}">{value}</text>
  </g>
</svg>"""


def _grade_colors(grade: str):
    """Return (text_color, bg_color) for a grade."""
    if grade in ("A", "B"):
        return "#fff", "#4c1"       # green
    elif grade == "C":
        return "#fff", "#dfb317"    # yellow
    elif grade in ("D", "F"):
        return "#fff", "#e05d44"    # red
    return "#fff", "#9f9f9f"        # gray for unknown


def mount_report_badge(app):
    """Mount the SVG badge endpoint on the FastAPI app."""

    @app.get("/report-badge/{owner}/{repo}.svg")
    async def report_badge(owner: str, repo: str):
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT project_health_grade, avg_trust_score FROM project_scans WHERE repo_full_name = :name"),
                {"name": f"{owner}/{repo}"},
            ).fetchone()

        if not row or not row.project_health_grade:
            svg = _badge_svg("nerq health", "not scanned", "#fff", "#9f9f9f")
            return Response(
                content=svg,
                media_type="image/svg+xml",
                headers={"Cache-Control": "public, max-age=3600"},
            )

        grade = row.project_health_grade
        score = row.avg_trust_score
        value = f"{grade} | {score:.0f}" if score is not None else grade
        text_color, bg_color = _grade_colors(grade)

        svg = _badge_svg("nerq health", value, text_color, bg_color)
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )
