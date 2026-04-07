"""
Add Trust Score badge endpoints to badge_api.py.
Adds:
  /compliance/badge/trust/{agent_id} - Shows "Nerq Trust | A (87/100)"
  /compliance/badge/trust-grade/{grade} - Shows generic grade badge

Run: cd ~/agentindex && venv/bin/python add_trust_badges.py
"""

FILE = "agentindex/compliance/badge_api.py"

with open(FILE, "r") as f:
    content = f.read()

if "trust-grade" in content:
    print("Trust badges already exist. Skipping.")
    exit(0)

TRUST_BADGES = '''

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
                text("SELECT trust_grade, trust_score_v2 FROM agents WHERE id = :id OR name = :name LIMIT 1"),
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
'''

content += TRUST_BADGES

with open(FILE, "w") as f:
    f.write(content)

print(f"Done! Added trust badge endpoints to {FILE}")
print(f"File now {len(content.splitlines())} lines")
print()
print("Usage in README.md:")
print('  ![Nerq Trust](https://nerq.ai/compliance/badge/trust/YOUR-AGENT-ID)')
print('  ![Nerq Trust](https://nerq.ai/compliance/badge/trust-grade/A)')

import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
