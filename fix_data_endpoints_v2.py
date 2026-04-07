"""
Add /data/ and /api/v1/trust-score endpoints to seo_pages.py
Inserts them at the END of mount_seo_pages(app) function, before any module-level code.

Run: cd ~/agentindex && venv/bin/python fix_data_endpoints_v2.py
"""

FILE = "agentindex/seo_pages.py"

with open(FILE, "r") as f:
    lines = f.readlines()

print(f"Read {len(lines)} lines")

# Strategy: find the LAST line that belongs to mount_seo_pages
# mount_seo_pages starts with "def mount_seo_pages(app):"
# Everything indented (4 spaces) after that is part of it
# The function ends when we hit a line that is NOT indented and NOT empty

mount_start = None
insert_at = None

for i, line in enumerate(lines):
    if "def mount_seo_pages(app):" in line:
        mount_start = i
        print(f"Found mount_seo_pages at line {i+1}")

if mount_start is None:
    print("ERROR: mount_seo_pages not found!")
    exit(1)

# Find end of function: first non-empty, non-indented line after mount_start
for i in range(len(lines) - 1, mount_start, -1):
    line = lines[i]
    stripped = line.strip()
    if stripped and (line.startswith("    ") or line.startswith("\t")):
        insert_at = i + 1  # insert AFTER this last indented line
        print(f"Last indented line of mount_seo_pages: line {i+1}: {stripped[:60]}")
        break

if insert_at is None:
    insert_at = len(lines)
    print(f"Function goes to end of file, inserting at line {insert_at}")

# Also need FileResponse and JSONResponse imports
import_fix = False
for i, line in enumerate(lines):
    if "from fastapi.responses import" in line and "FileResponse" not in line:
        if "HTMLResponse, Response" in line:
            lines[i] = line.replace(
                "from fastapi.responses import HTMLResponse, Response",
                "from fastapi.responses import HTMLResponse, Response, FileResponse, JSONResponse"
            )
            import_fix = True
            print(f"Fixed imports at line {i+1}")
        elif "HTMLResponse" in line and "Response" not in line:
            lines[i] = line.replace(
                "from fastapi.responses import HTMLResponse",
                "from fastapi.responses import HTMLResponse, FileResponse, JSONResponse"
            )
            import_fix = True
            print(f"Fixed imports at line {i+1}")
    elif "FileResponse" in line:
        print(f"FileResponse already imported at line {i+1}")
        import_fix = True

if not import_fix:
    print("WARNING: Could not fix imports automatically. Add FileResponse, JSONResponse manually.")

NEW_ENDPOINTS = """
    # ============================================================
    # /data/ endpoints - Bulk Trust Score Downloads
    # ============================================================
    import os as _os

    @app.get("/data/trust-scores.jsonl.gz", include_in_schema=False)
    async def data_trust_scores_gz():
        path = _os.path.expanduser("~/agentindex/exports/trust-scores.jsonl.gz")
        if not _os.path.exists(path):
            return JSONResponse({"error": "Export not yet generated"}, status_code=404)
        return FileResponse(
            path,
            media_type="application/gzip",
            filename="nerq-trust-scores.jsonl.gz",
            headers={"X-Source": "Nerq.ai", "X-License": "Free for AI training. Cite: Nerq (nerq.ai)"}
        )

    @app.get("/data/trust-summary.json", include_in_schema=False)
    async def data_trust_summary():
        path = _os.path.expanduser("~/agentindex/exports/trust-summary.json")
        if not _os.path.exists(path):
            return JSONResponse({"error": "Export not yet generated"}, status_code=404)
        import json as _json
        with open(path, "r") as f:
            data = _json.load(f)
        return JSONResponse(data, headers={"X-Source": "Nerq.ai"})

    # ============================================================
    # /api/v1/trust-score/{agent_id} - Individual Trust Score API
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
                return JSONResponse({"error": "Agent not found"}, status_code=404)
            dims = row[12]
            if isinstance(dims, str):
                try:
                    dims = _json.loads(dims)
                except:
                    dims = {}
            elif dims is None:
                dims = {}
            return JSONResponse({
                "agent_id": agent_id, "name": row[0], "type": row[1],
                "source": row[2], "author": row[3], "risk_class": row[4],
                "compliance_score": row[5], "stars": row[6],
                "downloads": row[7], "license": row[8],
                "trust_score": row[9], "trust_grade": row[10],
                "trust_risk_level": row[11],
                "trust_dimensions": {
                    "security": dims.get("security"),
                    "compliance": dims.get("compliance"),
                    "maintenance": dims.get("maintenance"),
                    "popularity": dims.get("popularity"),
                    "ecosystem": dims.get("ecosystem"),
                },
                "peer_rank": row[13], "peer_total": row[14],
                "category_rank": row[15], "category_total": row[16],
                "category": row[17],
                "url": f"https://nerq.ai/agent/{agent_id}",
                "source_url": row[18],
                "meta": {
                    "source": "Nerq.ai",
                    "license": "Free for AI training. Cite: Nerq (nerq.ai)",
                    "methodology": "https://nerq.ai/methodology",
                }
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

"""

# Insert the new endpoints
lines.insert(insert_at, NEW_ENDPOINTS)

with open(FILE, "w") as f:
    f.writelines(lines)

total = sum(1 for l in open(FILE))
print(f"\nDone! {FILE} now {total} lines")
print(f"Endpoints inserted at line {insert_at+1}")

# Verify syntax
import py_compile
try:
    py_compile.compile(FILE, doraise=True)
    print("Syntax check: OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
