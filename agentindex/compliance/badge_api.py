"""Compliance Badge API - SVG shields for README embedding."""
from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import text
import os, sys

router = APIRouter(prefix="/compliance/badge", tags=["badge"])

COLORS = {"minimal":"#4af0c0","limited":"#ffaa33","high":"#ff4d6a","unacceptable":"#cc0000","unknown":"#888888"}
LABELS = {"minimal":"Minimal Risk","limited":"Limited Risk","high":"High Risk","unacceptable":"Prohibited","unknown":"Not Assessed"}

def _svg(label_text, value_text, color):
    lw = len(label_text) * 6.8 + 12
    vw = len(value_text) * 6.8 + 12
    tw = lw + vw
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="20" role="img">
  <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <clipPath id="r"><rect width="{tw}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#555"/><rect x="{lw}" width="{vw}" height="20" fill="{color}"/><rect width="{tw}" height="20" fill="url(#s)"/></g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,sans-serif" text-rendering="geometricPrecision" font-size="11">
    <text x="{lw/2}" y="14" fill="#010101" fill-opacity=".3">{label_text}</text><text x="{lw/2}" y="13">{label_text}</text>
    <text x="{lw+vw/2}" y="14" fill="#010101" fill-opacity=".3">{value_text}</text><text x="{lw+vw/2}" y="13">{value_text}</text>
  </g></svg>'''

@router.get("/{risk_class}")
async def badge_by_class(risk_class: str):
    rc = risk_class.lower().strip()
    if rc not in COLORS: rc = "unknown"
    return Response(content=_svg("Nerq Comply", LABELS[rc], COLORS[rc]), media_type="image/svg+xml", headers={"Cache-Control":"public, max-age=3600"})

@router.get("/agent/{agent_id}")
async def badge_by_agent(agent_id: str):
    rc = "unknown"
    try:
        sys.path.insert(0, os.path.expanduser("~/agentindex"))
        from agentindex.db.models import get_session
        session = get_session()
        try:
            row = session.execute(text("SELECT eu_risk_class FROM entity_lookup WHERE id = :id OR name = :name LIMIT 1"), {"id": agent_id, "name": agent_id}).fetchone()
            if row and row[0]: rc = row[0]
        finally: session.close()
    except: pass
    return Response(content=_svg("Nerq Comply", LABELS.get(rc,"Not Assessed"), COLORS.get(rc,COLORS["unknown"])), media_type="image/svg+xml", headers={"Cache-Control":"public, max-age=3600"})


@router.get("/multi/{risk_class}/{count}")
async def badge_multi(risk_class: str, count: int):
    rc = risk_class.lower().strip()
    if rc not in COLORS: rc = "unknown"
    label = LABELS.get(rc, "Not Assessed")
    color = COLORS.get(rc, COLORS["unknown"])
    jur = f"{count} jur"
    jw = len(jur) * 6.8 + 12
    lw = len("Nerq Comply") * 6.8 + 12
    vw = len(label) * 6.8 + 12
    tw = lw + vw + jw
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="20" role="img"><linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient><clipPath id="r"><rect width="{tw}" height="20" rx="3" fill="#fff"/></clipPath><g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#555"/><rect x="{lw}" width="{vw}" height="20" fill="{color}"/><rect x="{lw+vw}" width="{jw}" height="20" fill="#333"/><rect width="{tw}" height="20" fill="url(#s)"/></g><g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,sans-serif" text-rendering="geometricPrecision" font-size="11"><text x="{lw/2}" y="13">Nerq Comply</text><text x="{lw+vw/2}" y="13">{label}</text><text x="{lw+vw+jw/2}" y="13">{jur}</text></g></svg>'
    return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})


# Trust Score badge colors
TRUST_COLORS = {"A+":"#059669","A":"#10b981","B":"#3b82f6","C":"#f59e0b","D":"#f97316","E":"#ef4444","F":"#991b1b"}

@router.get("/trust/{agent_id}")
async def trust_badge_by_agent(agent_id: str):
    """SVG badge showing Nerq Trust Score for a specific agent. Embed in README."""
    grade = "?"
    score = "?"
    color = "#888888"
    try:
        sys.path.insert(0, os.path.expanduser("~/agentindex"))
        from agentindex.db.models import get_session
        session = get_session()
        try:
            row = session.execute(
                text("SELECT trust_grade, trust_score_v2 FROM entity_lookup WHERE id = :id OR name = :name LIMIT 1"),
                {"id": agent_id, "name": agent_id}
            ).fetchone()
            if row and row[0]:
                grade = row[0]
                score = str(int(round(row[1]))) if row[1] else "?"
                color = TRUST_COLORS.get(grade, "#888888")
        finally:
            session.close()
    except:
        pass
    value_text = grade + " (" + score + "/100)" if score != "?" else "Not Scored"
    return Response(
        content=_svg("Nerq Trust", value_text, color),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"}
    )

@router.get("/trust-grade/{grade}")
async def trust_badge_by_grade(grade: str):
    """Generic Trust Score grade badge. Use: /compliance/badge/trust-grade/A"""
    g = grade.upper().strip()
    color = TRUST_COLORS.get(g, "#888888")
    label = g if g in TRUST_COLORS else "?"
    return Response(
        content=_svg("Nerq Trust", label, color),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"}
    )
