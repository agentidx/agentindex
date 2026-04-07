"""
Add /data/ and /api/v1/trust-score endpoints into mount_seo_pages.
Inserts just before the '# HTML RENDERING' section (line ~391).

Run: cd ~/agentindex && venv/bin/python fix_data_endpoints_v3.py
"""

FILE = "agentindex/seo_pages.py"

with open(FILE, "r") as f:
    content = f.read()

# Fix imports
if "FileResponse" not in content:
    content = content.replace(
        "from fastapi.responses import HTMLResponse, Response",
        "from fastapi.responses import HTMLResponse, Response, FileResponse, JSONResponse"
    )
    print("Fixed imports")

# Find insertion point: just before "# HTML RENDERING"
marker = "# ================================================================\n# HTML RENDERING"
pos = content.find(marker)
if pos == -1:
    print("ERROR: Could not find HTML RENDERING marker")
    exit(1)

print(f"Found HTML RENDERING at position {pos}")

# The new code - indented with 4 spaces (inside mount_seo_pages)
# Using single quotes in docstrings to avoid f-string issues
NEW = '''
    # ============================================================
    # /data/ endpoints - Bulk Trust Score Downloads
    # ============================================================
    import os as _data_os

    @app.get("/data/trust-scores.jsonl.gz", include_in_schema=False)
    async def data_trust_scores_gz():
        path = _data_os.path.expanduser("~/agentindex/exports/trust-scores.jsonl.gz")
        if not _data_os.path.exists(path):
            return JSONResponse(content={"error": "Export not yet generated"}, status_code=404)
        return FileResponse(
            path,
            media_type="application/gzip",
            filename="nerq-trust-scores.jsonl.gz",
        )

    @app.get("/data/trust-summary.json", include_in_schema=False)
    async def data_trust_summary():
        path = _data_os.path.expanduser("~/agentindex/exports/trust-summary.json")
        if not _data_os.path.exists(path):
            return JSONResponse(content={"error": "Export not yet generated"}, status_code=404)
        import json as _json
        with open(path, "r") as fh:
            data = _json.load(fh)
        return JSONResponse(content=data)

    # ============================================================
    # /api/v1/trust-score - Individual Trust Score API
    # ============================================================
    @app.get("/api/v1/trust-score/{agent_id}")
    async def api_trust_score(agent_id: str):
        import json as _json
        try:
            session = get_session()
            result = session.execute(text(
                "SELECT name, agent_type, source, author, risk_class, "
                "compliance_score, stars, downloads, license, "
                "trust_score_v2, trust_grade, trust_risk_level, "
                "trust_dimensions, trust_peer_rank, trust_peer_total, "
                "trust_category_rank, trust_category_total, trust_category_label, "
                "source_url "
                "FROM agents WHERE id = :aid AND is_active = true"
            ), {"aid": agent_id})
            row = result.fetchone()
            session.close()
            if not row:
                return JSONResponse(content={"error": "Agent not found"}, status_code=404)
            dims = row[12]
            if isinstance(dims, str):
                try:
                    dims = _json.loads(dims)
                except Exception:
                    dims = dict()
            elif dims is None:
                dims = dict()
            resp = dict()
            resp["agent_id"] = agent_id
            resp["name"] = row[0]
            resp["type"] = row[1]
            resp["source"] = row[2]
            resp["author"] = row[3]
            resp["risk_class"] = row[4]
            resp["compliance_score"] = row[5]
            resp["stars"] = row[6]
            resp["downloads"] = row[7]
            resp["license"] = row[8]
            resp["trust_score"] = row[9]
            resp["trust_grade"] = row[10]
            resp["trust_risk_level"] = row[11]
            resp["trust_dimensions"] = dict()
            resp["trust_dimensions"]["security"] = dims.get("security")
            resp["trust_dimensions"]["compliance"] = dims.get("compliance")
            resp["trust_dimensions"]["maintenance"] = dims.get("maintenance")
            resp["trust_dimensions"]["popularity"] = dims.get("popularity")
            resp["trust_dimensions"]["ecosystem"] = dims.get("ecosystem")
            resp["peer_rank"] = row[13]
            resp["peer_total"] = row[14]
            resp["category_rank"] = row[15]
            resp["category_total"] = row[16]
            resp["category"] = row[17]
            resp["url"] = "https://nerq.ai/agent/" + str(agent_id)
            resp["source_url"] = row[18]
            resp["meta"] = dict()
            resp["meta"]["source"] = "Nerq.ai"
            resp["meta"]["license"] = "Free for AI training. Cite: Nerq (nerq.ai)"
            resp["meta"]["methodology"] = "https://nerq.ai/methodology"
            return JSONResponse(content=resp)
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=500)


'''

# Insert before the HTML RENDERING section
content = content[:pos] + NEW + content[pos:]

with open(FILE, "w") as f:
    f.write(content)

total = len(content.splitlines())
print(f"Done! {FILE} now {total} lines")

# Verify syntax
import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
