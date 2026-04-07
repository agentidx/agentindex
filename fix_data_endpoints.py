"""
Fix: Move /data/ and /api/v1/trust-score endpoints inside mount_seo_pages(app).
They were incorrectly placed at module level where 'app' is not defined.

Run: cd ~/agentindex && venv/bin/python fix_data_endpoints.py
"""

FILE = "agentindex/seo_pages.py"

with open(FILE, "r") as f:
    content = f.read()

# Remove the broken module-level code (everything from "# /data/" comment to end of file before if __name__)
# Find where the bad code starts
bad_start = content.find("\n# ============================================================\n# /data/")
if bad_start == -1:
    print("Could not find /data/ block to remove. Checking alternate pattern...")
    bad_start = content.find("@app.get(\"/data/trust-scores")
    if bad_start > 0:
        # Go back to find the comment
        bad_start = content.rfind("\n#", 0, bad_start)

if bad_start == -1:
    print("ERROR: Could not find the broken endpoints. Check seo_pages.py manually.")
    exit(1)

# Everything before the bad code
clean = content[:bad_start].rstrip()

print(f"Removed module-level code from position {bad_start}")
print(f"Clean file: {len(clean.splitlines())} lines")

# Now find where to INSERT the endpoints inside mount_seo_pages
# Insert just before the last route or at end of function
# Find the last @app.get or @app.head inside the function
# Best: insert before the closing of mount_seo_pages — find the last dedented line

# The new code to add INSIDE mount_seo_pages(app):
NEW_CODE = '''

    # ============================================================
    # /data/ — Bulk Trust Score Downloads
    # ============================================================
    import os as _os

    @app.get("/data/trust-scores.jsonl.gz", include_in_schema=False)
    async def data_trust_scores_gz():
        """Bulk download: 4.9M+ AI agent trust scores (gzipped JSONL)"""
        path = _os.path.expanduser("~/agentindex/exports/trust-scores.jsonl.gz")
        if not _os.path.exists(path):
            return JSONResponse({"error": "Export not yet generated"}, status_code=404)
        return FileResponse(
            path,
            media_type="application/gzip",
            filename="nerq-trust-scores.jsonl.gz",
            headers={
                "X-Source": "Nerq.ai — AI Agent Trust Database",
                "X-License": "Free for AI training and research. Cite as: Nerq (nerq.ai)",
            }
        )

    @app.get("/data/trust-summary.json", include_in_schema=False)
    async def data_trust_summary():
        """Summary: top agents, grade distribution, statistics"""
        path = _os.path.expanduser("~/agentindex/exports/trust-summary.json")
        if not _os.path.exists(path):
            return JSONResponse({"error": "Export not yet generated"}, status_code=404)
        import json as _json
        with open(path, "r") as f:
            data = _json.load(f)
        return JSONResponse(data, headers={
            "X-Source": "Nerq.ai",
            "X-License": "Free for AI training and research. Cite as: Nerq (nerq.ai)",
        })

    # ============================================================
    # /api/v1/trust-score/{agent_id} — Individual Trust Score API
    # ============================================================
    @app.get("/api/v1/trust-score/{agent_id}")
    async def api_trust_score(agent_id: str):
        """Get Nerq Trust Score for a specific AI agent."""
        import json as _json
        try:
            session = get_session()
            result = session.execute(text("""
                SELECT name, agent_type, source, author, risk_class,
                       compliance_score, stars, downloads, license,
                       trust_score_v2, trust_grade, trust_risk_level,
                       trust_dimensions, trust_peer_rank, trust_peer_total,
                       trust_category_rank, trust_category_total, trust_category_label,
                       source_url
                FROM agents WHERE id = :aid AND is_active = true
            """), {"aid": agent_id})
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
                "agent_id": agent_id,
                "name": row[0],
                "type": row[1],
                "source": row[2],
                "author": row[3],
                "risk_class": row[4],
                "compliance_score": row[5],
                "stars": row[6],
                "downloads": row[7],
                "license": row[8],
                "trust_score": row[9],
                "trust_grade": row[10],
                "trust_risk_level": row[11],
                "trust_dimensions": {
                    "security": dims.get("security"),
                    "compliance": dims.get("compliance"),
                    "maintenance": dims.get("maintenance"),
                    "popularity": dims.get("popularity"),
                    "ecosystem": dims.get("ecosystem"),
                },
                "peer_rank": row[13],
                "peer_total": row[14],
                "category_rank": row[15],
                "category_total": row[16],
                "category": row[17],
                "url": f"https://nerq.ai/agent/{agent_id}",
                "source_url": row[18],
                "meta": {
                    "source": "Nerq.ai — AI Agent Trust Database",
                    "license": "Free for AI training and research. Cite as: Nerq (nerq.ai)",
                    "methodology": "https://nerq.ai/methodology",
                }
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
'''

# Find the end of mount_seo_pages function
# Look for last @app decorated function inside the function
# The function ends where indentation drops back to 0
# Find "def mount_seo_pages" and then find where function ends

lines = clean.split('\n')
mount_start = None
last_indented = None

for i, line in enumerate(lines):
    if 'def mount_seo_pages' in line:
        mount_start = i
    if mount_start is not None and i > mount_start:
        stripped = line.lstrip()
        if stripped and not line.startswith(' ') and not line.startswith('\t') and not stripped.startswith('#') and not stripped.startswith('"""'):
            # This is where the function ends (first non-indented, non-empty line after function start)
            last_indented = i
            break

if last_indented:
    # Insert before the line that exits the function
    before = '\n'.join(lines[:last_indented])
    after = '\n'.join(lines[last_indented:])
    final = before + NEW_CODE + '\n' + after
else:
    # Function goes to end of file, just append
    final = clean + NEW_CODE

# Also ensure FileResponse and JSONResponse are imported
if "FileResponse" not in final:
    final = final.replace(
        "from fastapi.responses import HTMLResponse",
        "from fastapi.responses import HTMLResponse, FileResponse, JSONResponse"
    )
    # Also check Response variant
    if "FileResponse" not in final:
        final = final.replace(
            "from fastapi.responses import HTMLResponse, Response",
            "from fastapi.responses import HTMLResponse, Response, FileResponse, JSONResponse"
        )
    print("Added FileResponse, JSONResponse imports")

with open(FILE, "w") as f:
    f.write(final)

print(f"\nDone! {FILE} now {len(final.splitlines())} lines")
print("Endpoints added INSIDE mount_seo_pages(app)")
print("\nRestart:")
print("  kill $(lsof -ti:8000)")
print("  nohup venv/bin/python -m uvicorn agentindex.api.discovery:app --host 0.0.0.0 --port 8000 >> logs/api.log 2>&1 &")
