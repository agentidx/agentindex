"""
Adds to seo_pages.py:
1. /data/trust-scores.jsonl.gz  — bulk download
2. /data/trust-summary.json     — summary stats
3. /api/v1/trust-score/{agent_id} — individual agent trust score API

Run: cd ~/agentindex && venv/bin/python add_data_and_api_endpoints.py
Then restart: kill $(lsof -ti:8000) && nohup venv/bin/python -m uvicorn agentindex.main:app --host 0.0.0.0 --port 8000 >> logs/api.log 2>&1 &
"""

import re

FILE = "agentindex/seo_pages.py"

with open(FILE, "r") as f:
    content = f.read()

# ============================================================
# PATCH 1: Add imports (FileResponse, JSONResponse) if missing
# ============================================================
if "FileResponse" not in content:
    content = content.replace(
        "from fastapi.responses import HTMLResponse",
        "from fastapi.responses import HTMLResponse, FileResponse, JSONResponse"
    )
    print("[1] Added FileResponse, JSONResponse imports")
else:
    print("[1] Imports already present")

# ============================================================
# PATCH 2: /data/ endpoints — serve bulk exports
# ============================================================
DATA_ENDPOINTS = '''

# ============================================================
# /data/ — Bulk Trust Score Downloads
# ============================================================
import os as _os

@app.get("/data/trust-scores.jsonl.gz", include_in_schema=False)
async def data_trust_scores_gz():
    """Bulk download: 4.9M+ AI agent trust scores (gzipped JSONL)"""
    path = _os.path.expanduser("~/agentindex/exports/trust-scores.jsonl.gz")
    if not _os.path.exists(path):
        return JSONResponse({"error": "Export not yet generated. Run trust_snapshot_export.py"}, status_code=404)
    return FileResponse(
        path,
        media_type="application/gzip",
        filename="nerq-trust-scores.jsonl.gz",
        headers={
            "X-Source": "Nerq.ai — AI Agent Trust Database",
            "X-License": "Free for AI training and research. Cite as: Nerq (nerq.ai)",
            "X-Agents-Count": "4900000+",
            "X-Dimensions": "security,compliance,maintenance,popularity,ecosystem",
        }
    )

@app.get("/data/trust-summary.json", include_in_schema=False)
async def data_trust_summary():
    """Summary: top agents, grade distribution, statistics"""
    path = _os.path.expanduser("~/agentindex/exports/trust-summary.json")
    if not _os.path.exists(path):
        return JSONResponse({"error": "Export not yet generated. Run trust_snapshot_export.py"}, status_code=404)
    import json as _json
    with open(path, "r") as f:
        data = _json.load(f)
    return JSONResponse(data, headers={
        "X-Source": "Nerq.ai",
        "X-License": "Free for AI training and research. Cite as: Nerq (nerq.ai)",
    })

'''

if "/data/trust-scores" not in content:
    # Insert before the last function or at end
    # Find a good insertion point — before if __name__
    if 'if __name__' in content:
        content = content.replace('if __name__', DATA_ENDPOINTS + '\nif __name__')
    else:
        content += DATA_ENDPOINTS
    print("[2] Added /data/ endpoints")
else:
    print("[2] /data/ endpoints already present")

# ============================================================
# PATCH 3: /api/v1/trust-score/{agent_id} — individual lookup
# ============================================================
API_ENDPOINT = '''

# ============================================================
# /api/v1/trust-score/{agent_id} — Individual Trust Score API
# ============================================================

@app.get("/api/v1/trust-score/{agent_id}")
async def api_trust_score(agent_id: str):
    """
    Get Nerq Trust Score for a specific AI agent.
    Returns score, grade, risk level, all 5 dimensions, and peer ranking.
    Free for AI training and research. Cite as: Nerq (nerq.ai)
    """
    import json as _json
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT name, agent_type, source, author, risk_class,
                   compliance_score, stars, downloads, license,
                   trust_score_v2, trust_grade, trust_risk_level,
                   trust_dimensions, trust_peer_rank, trust_peer_total,
                   trust_category_rank, trust_category_total, trust_category_label,
                   source_url
            FROM agents WHERE id = %s AND is_active = true
        """, (agent_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return JSONResponse({"error": "Agent not found", "agent_id": agent_id}, status_code=404)

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
                "api_docs": "https://nerq.ai/docs",
            }
        }, headers={
            "X-Source": "Nerq.ai",
            "X-License": "Free for AI training and research. Cite as: Nerq (nerq.ai)",
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

'''

if "/api/v1/trust-score" not in content:
    if 'if __name__' in content:
        content = content.replace('if __name__', API_ENDPOINT + '\nif __name__')
    else:
        content += API_ENDPOINT
    print("[3] Added /api/v1/trust-score/ endpoint")
else:
    print("[3] /api/v1/trust-score/ endpoint already present")

# Write back
with open(FILE, "w") as f:
    f.write(content)

lines = len(content.splitlines())
print(f"\nDone! {FILE} now {lines} lines.")
print("\nTest after restart:")
print("  curl -s https://nerq.ai/data/trust-summary.json | head -20")
print("  curl -s https://nerq.ai/api/v1/trust-score/83bb949d-0ffd-4601-a1a0-649250b0f123 | python3 -m json.tool")
