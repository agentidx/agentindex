"""
Compatibility API & Pages — Sprint 2
======================================
Endpoints:
  GET /v1/compatible/{agent}     — Agent compatibility data
  GET /v1/frameworks             — Framework landscape
  GET /v1/mcp/compatible/{client} — MCP servers for a client
Pages:
  /compatibility                 — Hub page
  /framework/{name}              — Framework detail pages
  /mcp/compatible/{client}       — Client compatibility pages
  /dependencies                  — Dependency health dashboard

Usage in discovery.py:
    from agentindex.compatibility_api import mount_compatibility
    mount_compatibility(app)
"""

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.sql import text

from agentindex.db.models import get_session
from agentindex.nerq_design import NERQ_CSS, NERQ_NAV, NERQ_FOOTER

logger = logging.getLogger("nerq.compatibility")

SQLITE_DB = Path(__file__).parent / "crypto" / "crypto_trust.db"


def _sqlite_query(sql, params=()):
    if not SQLITE_DB.exists():
        return []
    conn = sqlite3.connect(str(SQLITE_DB))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def _esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def mount_compatibility(app):

    # ═══════════════════════════════════════════════════════════
    # GET /v1/compatible/{agent} — Full compatibility data
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/compatible/{agent_name}")
    def compatible(agent_name: str):
        start = time.time()

        # Frameworks
        frameworks = _sqlite_query(
            "SELECT framework, version, confidence FROM agent_frameworks WHERE agent_name = ? OR agent_name LIKE ?",
            (agent_name, f"%{agent_name}%")
        )

        # Compatible MCP servers (same framework)
        agent_fws = [f["framework"] for f in frameworks]
        compatible_mcp = []
        if agent_fws:
            session = get_session()
            try:
                for fw in agent_fws[:5]:
                    rows = session.execute(text("""
                        SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score, trust_grade
                        FROM entity_lookup
                        WHERE is_active = true AND agent_type = 'mcp_server'
                          AND frameworks::text ILIKE :fw
                        ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
                        LIMIT 10
                    """), {"fw": f"%{fw}%"}).fetchall()
                    for r in rows:
                        d = dict(r._mapping)
                        compatible_mcp.append({
                            "name": d["name"],
                            "trust_score": round(float(d["trust_score"] or 0), 1),
                            "confidence": "explicit",
                        })
            finally:
                session.close()

        # Compatible agents (shared deps + same framework)
        compatible_agents = []
        shared = _sqlite_query(
            "SELECT agent_b as name, shared_count, shared_packages FROM agent_shared_deps WHERE agent_a = ? "
            "UNION SELECT agent_a as name, shared_count, shared_packages FROM agent_shared_deps WHERE agent_b = ? "
            "ORDER BY shared_count DESC LIMIT 10",
            (agent_name, agent_name)
        )
        for s in shared:
            # Get trust score
            session = get_session()
            try:
                row = session.execute(text(
                    "SELECT COALESCE(trust_score_v2, trust_score) as ts FROM entity_lookup WHERE name = :n AND is_active = true LIMIT 1"
                ), {"n": s["name"]}).fetchone()
                ts = round(float(row[0]), 1) if row and row[0] else 0
            finally:
                session.close()

            packages = json.loads(s["shared_packages"]) if s["shared_packages"] else []
            reason_parts = [f"{s['shared_count']} shared dependencies"]
            # Check same framework
            other_fws = _sqlite_query(
                "SELECT framework FROM agent_frameworks WHERE agent_name = ?", (s["name"],)
            )
            other_fw_names = [f["framework"] for f in other_fws]
            common_fws = set(agent_fws) & set(other_fw_names)
            if common_fws:
                reason_parts.append(f"both use {', '.join(common_fws)}")

            compat_score = min(30 + s["shared_count"] * 2, 100)
            if common_fws:
                compat_score = min(compat_score + 20, 100)

            compatible_agents.append({
                "name": s["name"],
                "trust_score": ts,
                "compatibility_score": compat_score,
                "shared_deps": s["shared_count"],
                "reason": ". ".join(reason_parts),
            })

        # Dependencies
        deps = _sqlite_query(
            "SELECT dependency_name, dependency_version, registry FROM agent_dependencies WHERE agent_name = ? OR agent_name LIKE ?",
            (agent_name, f"%{agent_name}%")
        )

        # Vulnerable deps
        vuln_deps = _sqlite_query(
            "SELECT ad.dependency_name FROM agent_dependencies ad "
            "INNER JOIN agent_vulnerabilities av ON ad.dependency_name = av.agent_name "
            "WHERE ad.agent_name = ? OR ad.agent_name LIKE ?",
            (agent_name, f"%{agent_name}%")
        )

        # Detect language
        registries = set(d.get("registry", "") for d in deps)
        language = "python" if "pypi" in registries else "javascript" if "npm" in registries else "unknown"
        if "pypi" in registries and "npm" in registries:
            language = "python+javascript"

        dep_health = "GOOD" if len(vuln_deps) == 0 else "CAUTION" if len(vuln_deps) <= 2 else "POOR"

        return JSONResponse(content={
            "agent": agent_name,
            "frameworks": [{"name": f["framework"], "version": f.get("version"), "confidence": f["confidence"]} for f in frameworks],
            "compatible_mcp_servers": compatible_mcp[:10],
            "compatible_agents": compatible_agents[:10],
            "language": language,
            "dependencies_count": len(deps),
            "vulnerable_dependencies": len(vuln_deps),
            "dependency_health": dep_health,
            "response_time_ms": round((time.time() - start) * 1000, 1),
        })

    # ═══════════════════════════════════════════════════════════
    # GET /v1/frameworks — Framework landscape
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/frameworks")
    def frameworks_api():
        start = time.time()
        stats = _sqlite_query(
            "SELECT * FROM framework_stats ORDER BY agent_count DESC"
        )

        frameworks = []
        for s in stats:
            # Get top agents for this framework
            top = _sqlite_query(
                "SELECT agent_name FROM agent_frameworks WHERE framework = ? LIMIT 5",
                (s["framework"],)
            )
            top_names = [t["agent_name"] for t in top]

            # Compatible frameworks (share agents)
            compat_fws = _sqlite_query(
                "SELECT DISTINCT af2.framework FROM agent_frameworks af1 "
                "INNER JOIN agent_frameworks af2 ON af1.agent_name = af2.agent_name "
                "WHERE af1.framework = ? AND af2.framework != ? "
                "GROUP BY af2.framework ORDER BY COUNT(*) DESC LIMIT 5",
                (s["framework"], s["framework"])
            )

            frameworks.append({
                "name": s["framework"],
                "agent_count": s["agent_count"],
                "avg_trust_score": s["avg_trust_score"],
                "total_ecosystem_downloads": s["total_npm_downloads"],
                "top_agents": top_names,
                "compatible_frameworks": [f["framework"] for f in compat_fws],
            })

        return JSONResponse(content={
            "frameworks": frameworks,
            "total_frameworks_tracked": len(frameworks),
            "last_updated": stats[0]["updated_at"] if stats else None,
            "response_time_ms": round((time.time() - start) * 1000, 1),
        })

    # ═══════════════════════════════════════════════════════════
    # GET /v1/mcp/compatible/{client} — MCP servers for a client
    # ═══════════════════════════════════════════════════════════

    @app.get("/v1/mcp/compatible/{client}")
    def mcp_compatible(
        client: str,
        min_trust: int = Query(0, ge=0, le=100),
        limit: int = Query(20, ge=1, le=100),
    ):
        start = time.time()

        # Get compatible servers from SQLite
        compat = _sqlite_query(
            "SELECT server_name, confidence, sdk_version FROM mcp_compatibility WHERE client = ? ORDER BY confidence ASC",
            (client.lower(),)
        )

        if not compat:
            return JSONResponse(content={
                "client": client,
                "compatible_servers": [],
                "total_compatible": 0,
                "response_time_ms": round((time.time() - start) * 1000, 1),
            })

        server_names = [c["server_name"] for c in compat]
        confidence_map = {c["server_name"]: c["confidence"] for c in compat}

        # Get trust scores from PG
        session = get_session()
        try:
            results = []
            batch_size = 50
            for i in range(0, len(server_names), batch_size):
                batch = server_names[i:i + batch_size]
                placeholders = ",".join(f":n{j}" for j in range(len(batch)))
                params = {f"n{j}": n for j, n in enumerate(batch)}
                params["min_ts"] = min_trust

                rows = session.execute(text(f"""
                    SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                           trust_grade, source_url
                    FROM entity_lookup
                    WHERE name IN ({placeholders})
                      AND is_active = true
                      AND COALESCE(trust_score_v2, trust_score) >= :min_ts
                    ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
                """), params).fetchall()

                for r in rows:
                    d = dict(r._mapping)
                    results.append({
                        "name": d["name"],
                        "trust_score": round(float(d["trust_score"] or 0), 1),
                        "grade": d.get("trust_grade") or "N/A",
                        "confidence": confidence_map.get(d["name"], "inferred"),
                        "source_url": d.get("source_url"),
                    })
        finally:
            session.close()

        results.sort(key=lambda x: -x["trust_score"])

        return JSONResponse(content={
            "client": client,
            "compatible_servers": results[:limit],
            "total_compatible": len(results),
            "response_time_ms": round((time.time() - start) * 1000, 1),
        })

    # ═══════════════════════════════════════════════════════════
    # /compatibility — Hub page
    # ═══════════════════════════════════════════════════════════

    @app.get("/compatibility", response_class=HTMLResponse)
    def compatibility_page(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        stats = _sqlite_query("SELECT * FROM framework_stats ORDER BY agent_count DESC LIMIT 20")

        fw_cards = ""
        for s in stats:
            fw_cards += (
                f'<a href="/framework/{_esc(s["framework"])}" class="alt-card">'
                f'<div class="alt-name">{_esc(s["framework"])}</div>'
                f'<div class="alt-score">{s["agent_count"]:,} agents &middot; avg {s["avg_trust_score"] or 0:.0f}/100</div>'
                f'</a>'
            )

        clients = ["cursor", "claude", "chatgpt", "windsurf", "cody", "continue", "cline", "zed", "vscode"]
        client_cards = ""
        for cl in clients:
            count = len(_sqlite_query("SELECT 1 FROM mcp_compatibility WHERE client = ?", (cl,)))
            client_cards += (
                f'<a href="/mcp/compatible/{cl}" class="alt-card">'
                f'<div class="alt-name">{_esc(cl.title())}</div>'
                f'<div class="alt-score">{count} MCP servers</div>'
                f'</a>'
            )

        faq_jsonld = json.dumps({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": "Which MCP servers work with Cursor?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Nerq indexes MCP servers compatible with Cursor. Visit nerq.ai/mcp/compatible/cursor for a trust-ranked list."}},
                {"@type": "Question", "name": "Is LangChain compatible with CrewAI?",
                 "acceptedAnswer": {"@type": "Answer", "text": "LangChain and CrewAI share common dependencies and can be used together. Check nerq.ai/v1/compatible/langchain for details."}},
                {"@type": "Question", "name": "What frameworks support MCP?",
                 "acceptedAnswer": {"@type": "Answer", "text": "MCP is supported by multiple frameworks including LangChain, Vercel AI SDK, and others. Visit nerq.ai/v1/frameworks for the full landscape."}},
            ]
        })

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Agent Compatibility Matrix — Which Agents Work Together | Nerq</title>
<meta name="description" content="Explore which AI agents, frameworks, and MCP servers are compatible. Trust-ranked compatibility data for 204K+ AI assets.">
<link rel="canonical" href="https://nerq.ai/compatibility">
<script type="application/ld+json">{faq_jsonld}</script>
<style>{NERQ_CSS}
.alt-card{{border:1px solid #e5e7eb;padding:16px;text-decoration:none;color:inherit;transition:border-color .2s}}
.alt-card:hover{{border-color:#0d9488}}
.alt-name{{font-weight:700;font-size:15px;color:#1a1a1a;margin-bottom:4px}}
.alt-score{{font-size:13px;color:#0d9488;font-family:ui-monospace,monospace}}
.grid-3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}}
.search-box{{display:flex;gap:8px;max-width:500px;margin:20px auto}}
.search-box input{{flex:1;padding:10px 14px;border:1px solid #e5e7eb;font-size:14px;font-family:system-ui,sans-serif}}
.search-box button{{padding:10px 20px;background:#0d9488;color:#fff;border:none;font-weight:600;cursor:pointer}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <h1>AI Agent Compatibility Matrix</h1>
  <p class="desc">Explore which agents, frameworks, and MCP servers work together. All compatibility data is backed by dependency analysis and trust scores.</p>

  <div class="search-box">
    <input id="q" placeholder="Find agents compatible with..." autofocus>
    <button onclick="location.href='/v1/compatible/'+encodeURIComponent(document.getElementById('q').value)">Check</button>
  </div>

  <h2>Frameworks</h2>
  <p style="font-size:14px;color:#6b7280">Which frameworks power the AI agent ecosystem</p>
  <div class="grid-3">{fw_cards}</div>

  <h2>MCP Client Compatibility</h2>
  <p style="font-size:14px;color:#6b7280">Find MCP servers for your IDE or client</p>
  <div class="grid-3">{client_cards}</div>

  <div style="margin-top:32px;padding:20px;border:1px solid #e5e7eb;background:#f9fafb">
    <h3 style="margin:0 0 8px">API Access</h3>
    <pre style="font-size:12px;background:#f5f5f5;padding:12px;margin:8px 0;overflow-x:auto">GET /v1/compatible/langchain    — Agent compatibility
GET /v1/frameworks              — Framework landscape
GET /v1/mcp/compatible/cursor   — MCP servers for a client</pre>
    <a href="/nerq/docs" style="font-size:13px;color:#0d9488">Full API docs &rarr;</a>
  </div>
</main>
{NERQ_FOOTER}
</body>
</html>"""
        return HTMLResponse(content=html)

    # ═══════════════════════════════════════════════════════════
    # /framework/{name} — Framework detail page
    # ═══════════════════════════════════════════════════════════

    @app.get("/framework/{fw_name}", response_class=HTMLResponse)
    def framework_page(fw_name: str, request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        stats = _sqlite_query("SELECT * FROM framework_stats WHERE framework = ?", (fw_name,))
        if not stats:
            return HTMLResponse(status_code=404, content=f"<h1>Framework '{_esc(fw_name)}' not found</h1>")
        s = stats[0]

        # Get agents using this framework
        agents = _sqlite_query(
            "SELECT agent_name, confidence FROM agent_frameworks WHERE framework = ? LIMIT 100",
            (fw_name,)
        )
        agent_names = [a["agent_name"] for a in agents]

        # Get trust scores from PG
        session = get_session()
        agent_rows = []
        try:
            if agent_names:
                batch = agent_names[:50]
                placeholders = ",".join(f":n{j}" for j in range(len(batch)))
                params = {f"n{j}": n for j, n in enumerate(batch)}
                rows = session.execute(text(f"""
                    SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                           trust_grade, category, stars
                    FROM entity_lookup WHERE name IN ({placeholders}) AND is_active = true
                    ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
                """), params).fetchall()
                agent_rows = [dict(r._mapping) for r in rows]
        finally:
            session.close()

        table = ""
        for r in agent_rows:
            from agentindex.agent_safety_pages import _make_slug
            slug = _make_slug(r["name"])
            table += (
                f'<tr>'
                f'<td><a href="/safe/{_esc(slug)}">{_esc(r["name"])}</a></td>'
                f'<td style="font-family:ui-monospace,monospace">{r["trust_score"] or 0:.1f}</td>'
                f'<td>{_esc(r.get("trust_grade") or "N/A")}</td>'
                f'<td>{_esc(r.get("category") or "")}</td>'
                f'<td style="font-family:ui-monospace,monospace">{(r.get("stars") or 0):,}</td>'
                f'</tr>'
            )

        # Compatible frameworks
        compat = _sqlite_query(
            "SELECT DISTINCT af2.framework, COUNT(*) as cnt FROM agent_frameworks af1 "
            "INNER JOIN agent_frameworks af2 ON af1.agent_name = af2.agent_name "
            "WHERE af1.framework = ? AND af2.framework != ? "
            "GROUP BY af2.framework ORDER BY cnt DESC LIMIT 10",
            (fw_name, fw_name)
        )
        compat_html = " &middot; ".join(
            f'<a href="/framework/{_esc(c["framework"])}">{_esc(c["framework"])} ({c["cnt"]})</a>'
            for c in compat
        ) if compat else "None detected yet"

        title = fw_name.replace("-", " ").title()

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Best {_esc(title)} Agents 2026 — Trust Ranked | Nerq</title>
<meta name="description" content="{s['agent_count']} AI agents use {_esc(title)}. Average trust score: {s['avg_trust_score'] or 0:.0f}/100. Trust-ranked list of {_esc(title)} agents and tools.">
<link rel="canonical" href="https://nerq.ai/framework/{_esc(fw_name)}">
<style>{NERQ_CSS}</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/compatibility">compatibility</a> &rsaquo; {_esc(title)}</div>
  <h1>Best {_esc(title)} Agents 2026</h1>
  <p class="desc">{s['agent_count']} agents and tools use {_esc(title)}. Average trust score: {s['avg_trust_score'] or 0:.0f}/100.</p>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0">
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#0d9488;font-family:ui-monospace,monospace">{s['agent_count']:,}</div>
      <div style="font-size:12px;color:#6b7280">Agents</div>
    </div>
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#0d9488;font-family:ui-monospace,monospace">{s['avg_trust_score'] or 0:.0f}</div>
      <div style="font-size:12px;color:#6b7280">Avg Trust Score</div>
    </div>
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#0d9488;font-family:ui-monospace,monospace">{(s['total_npm_downloads'] or 0):,}</div>
      <div style="font-size:12px;color:#6b7280">Weekly Downloads</div>
    </div>
  </div>

  <h2>Compatible Frameworks</h2>
  <p style="font-size:14px">{compat_html}</p>

  <h2>Top {_esc(title)} Agents by Trust Score</h2>
  <table>
    <thead><tr><th>Agent</th><th>Score</th><th>Grade</th><th>Category</th><th>Stars</th></tr></thead>
    <tbody>{table}</tbody>
  </table>

  <div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb">
    <strong>API:</strong> <code style="font-size:12px">GET /v1/discover?q=&framework={_esc(fw_name)}&sort=trust_score</code>
    <a href="/v1/discover?q=agents&framework={_esc(fw_name)}&sort=trust_score&limit=20" style="font-size:12px;margin-left:8px;color:#0d9488">Try it &rarr;</a>
  </div>
</main>
{NERQ_FOOTER}
</body>
</html>"""
        return HTMLResponse(content=html)

    # ═══════════════════════════════════════════════════════════
    # /mcp/compatible/{client} — MCP client page (HTML)
    # ═══════════════════════════════════════════════════════════

    @app.get("/mcp/compatible/{client}", response_class=HTMLResponse)
    def mcp_client_page(client: str, request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        compat = _sqlite_query(
            "SELECT server_name, confidence, sdk_version FROM mcp_compatibility WHERE client = ? ORDER BY confidence ASC",
            (client.lower(),)
        )

        server_names = [c["server_name"] for c in compat]
        confidence_map = {c["server_name"]: c["confidence"] for c in compat}

        # Get trust scores
        session = get_session()
        servers = []
        try:
            if server_names:
                for i in range(0, min(len(server_names), 100), 50):
                    batch = server_names[i:i + 50]
                    placeholders = ",".join(f":n{j}" for j in range(len(batch)))
                    params = {f"n{j}": n for j, n in enumerate(batch)}
                    rows = session.execute(text(f"""
                        SELECT name, COALESCE(trust_score_v2, trust_score) as trust_score,
                               trust_grade, source_url
                        FROM entity_lookup WHERE name IN ({placeholders}) AND is_active = true
                        ORDER BY COALESCE(trust_score_v2, trust_score) DESC NULLS LAST
                    """), params).fetchall()
                    servers.extend([dict(r._mapping) for r in rows])
        finally:
            session.close()

        client_title = client.title()
        if client == "vscode":
            client_title = "VS Code"
        elif client == "chatgpt":
            client_title = "ChatGPT"

        table = ""
        for s in servers:
            from agentindex.agent_safety_pages import _make_slug
            slug = _make_slug(s["name"])
            conf = confidence_map.get(s["name"], "inferred")
            conf_pill = "pill-green" if conf == "explicit" else "pill-yellow" if conf == "config_example" else "pill-gray"
            table += (
                f'<tr>'
                f'<td><a href="/safe/{_esc(slug)}">{_esc(s["name"])}</a></td>'
                f'<td style="font-family:ui-monospace,monospace">{float(s["trust_score"] or 0):.1f}</td>'
                f'<td>{_esc(s.get("trust_grade") or "N/A")}</td>'
                f'<td><span class="pill {conf_pill}" style="font-size:11px">{_esc(conf)}</span></td>'
                f'</tr>'
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MCP Servers Compatible with {_esc(client_title)} — Trust Ranked | Nerq</title>
<meta name="description" content="{len(servers)} MCP servers compatible with {_esc(client_title)}, ranked by trust score. Find verified MCP servers for your {_esc(client_title)} setup.">
<link rel="canonical" href="https://nerq.ai/mcp/compatible/{_esc(client)}">
<style>{NERQ_CSS}
.pill-green{{background:#d1fae5;color:#065f46}}.pill-yellow{{background:#fef3c7;color:#92400e}}.pill-gray{{background:#f3f4f6;color:#4b5563}}
</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <div class="breadcrumb"><a href="/">nerq</a> &rsaquo; <a href="/compatibility">compatibility</a> &rsaquo; {_esc(client_title)} MCP</div>
  <h1>MCP Servers Compatible with {_esc(client_title)}</h1>
  <p class="desc">{len(servers)} MCP servers verified compatible with {_esc(client_title)}, ranked by Nerq Trust Score.</p>

  <table>
    <thead><tr><th>Server</th><th>Trust Score</th><th>Grade</th><th>Confidence</th></tr></thead>
    <tbody>{table if table else '<tr><td colspan="4">No compatibility data yet. Run the MCP compatibility scanner to populate.</td></tr>'}</tbody>
  </table>

  <div style="margin-top:24px;padding:16px;background:#f9fafb;border:1px solid #e5e7eb">
    <strong>API:</strong> <code style="font-size:12px">GET /v1/mcp/compatible/{_esc(client)}?min_trust=70&limit=20</code>
  </div>
</main>
{NERQ_FOOTER}
</body>
</html>"""
        return HTMLResponse(content=html)

    # ═══════════════════════════════════════════════════════════
    # /dependencies — Dependency health dashboard
    # ═══════════════════════════════════════════════════════════

    @app.get("/dependencies", response_class=HTMLResponse)
    def dependencies_page(request: Request):
        host = (request.headers.get("host") or "").lower()
        if "nerq" not in host:
            return HTMLResponse(status_code=404, content="Not found")

        # Top deps
        top_deps = _sqlite_query(
            "SELECT dependency_name, registry, COUNT(*) as usage_count "
            "FROM agent_dependencies GROUP BY dependency_name ORDER BY usage_count DESC LIMIT 30"
        )

        # Vulnerable deps
        vuln_deps = _sqlite_query(
            "SELECT DISTINCT ad.dependency_name, COUNT(DISTINCT ad.agent_name) as affected_agents "
            "FROM agent_dependencies ad "
            "INNER JOIN agent_vulnerabilities av ON ad.dependency_name = av.agent_name "
            "GROUP BY ad.dependency_name ORDER BY affected_agents DESC LIMIT 20"
        )

        total_deps = _sqlite_query("SELECT COUNT(DISTINCT dependency_name) as c FROM agent_dependencies")
        total_agents = _sqlite_query("SELECT COUNT(DISTINCT agent_name) as c FROM agent_dependencies")

        total_dep_count = total_deps[0]["c"] if total_deps else 0
        total_agent_count = total_agents[0]["c"] if total_agents else 0

        dep_table = ""
        for d in top_deps:
            is_vuln = any(v["dependency_name"] == d["dependency_name"] for v in vuln_deps)
            vuln_tag = ' <span class="pill pill-red" style="font-size:10px">CVE</span>' if is_vuln else ""
            dep_table += (
                f'<tr>'
                f'<td>{_esc(d["dependency_name"])}{vuln_tag}</td>'
                f'<td>{_esc(d["registry"])}</td>'
                f'<td style="font-family:ui-monospace,monospace">{d["usage_count"]:,}</td>'
                f'</tr>'
            )

        vuln_table = ""
        for v in vuln_deps:
            vuln_table += (
                f'<tr>'
                f'<td>{_esc(v["dependency_name"])}</td>'
                f'<td style="font-family:ui-monospace,monospace;color:#dc2626">{v["affected_agents"]:,}</td>'
                f'</tr>'
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Agent Dependency Health — Ecosystem Security Report | Nerq</title>
<meta name="description" content="Ecosystem-wide dependency health for AI agents. {total_dep_count:,} unique dependencies across {total_agent_count:,} agents. Vulnerability tracking and freshness analysis.">
<link rel="canonical" href="https://nerq.ai/dependencies">
<style>{NERQ_CSS}.pill-red{{background:#fee2e2;color:#991b1b}}</style>
</head>
<body>
{NERQ_NAV}
<main class="container" style="padding-top:20px;padding-bottom:40px">
  <h1>AI Agent Dependency Health</h1>
  <p class="desc">Ecosystem-wide dependency analysis across {total_agent_count:,} AI agents. {total_dep_count:,} unique dependencies tracked.</p>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0">
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#0d9488;font-family:ui-monospace,monospace">{total_dep_count:,}</div>
      <div style="font-size:12px;color:#6b7280">Unique Dependencies</div>
    </div>
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#0d9488;font-family:ui-monospace,monospace">{total_agent_count:,}</div>
      <div style="font-size:12px;color:#6b7280">Agents Analyzed</div>
    </div>
    <div class="card" style="padding:16px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#dc2626;font-family:ui-monospace,monospace">{len(vuln_deps)}</div>
      <div style="font-size:12px;color:#6b7280">Vulnerable Dependencies</div>
    </div>
  </div>

  <h2>Most-Used Dependencies</h2>
  <table>
    <thead><tr><th>Package</th><th>Registry</th><th>Used By</th></tr></thead>
    <tbody>{dep_table if dep_table else '<tr><td colspan="3">No dependency data yet. Run the dependency graph builder.</td></tr>'}</tbody>
  </table>

  {'<h2>Vulnerable Dependencies</h2><p style="color:#6b7280;font-size:14px">Dependencies with known CVEs used by multiple agents</p><table><thead><tr><th>Package</th><th>Affected Agents</th></tr></thead><tbody>' + vuln_table + '</tbody></table>' if vuln_table else ''}
</main>
{NERQ_FOOTER}
</body>
</html>"""
        return HTMLResponse(content=html)

    logger.info("Mounted compatibility API: /v1/compatible, /v1/frameworks, /v1/mcp/compatible, /compatibility, /framework, /dependencies")
