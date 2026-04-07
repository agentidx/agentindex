"""
Federation API & Pages — Sprint 5
====================================
Endpoints:
  POST /v1/federation/contribute       — Submit external trust signals
  GET  /v1/federation/sources          — List all trust data sources
  GET  /v1/federation/agent/{name}/signals — Full signal breakdown for agent
  GET  /verified                       — Verified agents page
  GET  /federation                     — Federation protocol page
  GET  /badge/{name}/verified.svg      — Verified badge
  GET  /badge/{name}/verified-plus.svg — Verified Plus badge

Usage in discovery.py:
    from agentindex.federation_api import mount_federation
    mount_federation(app)
"""

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.sql import text

from agentindex.nerq_design import nerq_page

logger = logging.getLogger("federation-api")

SQLITE_DB = Path(__file__).parent / "crypto" / "crypto_trust.db"


_db_initialized = False

def _init_db():
    global _db_initialized
    if _db_initialized:
        return
    try:
        conn = sqlite3.connect(str(SQLITE_DB), timeout=10)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS federation_contributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contributor TEXT NOT NULL,
                contributor_trust TEXT DEFAULT 'UNVERIFIED',
                agent_name TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                score REAL,
                max_score REAL DEFAULT 100,
                evidence TEXT,
                contributed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                incorporated BOOLEAN DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fc_agent ON federation_contributions(agent_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fc_contrib ON federation_contributions(contributor)")
        conn.commit()
        conn.close()
        _db_initialized = True
    except Exception:
        pass  # Will retry on next request


def _get_conn():
    _init_db()
    return sqlite3.connect(str(SQLITE_DB), timeout=10)


def _is_nerq(request):
    host = request.headers.get("host", "")
    return "nerq" in host or "localhost" in host


# ── API Endpoints ────────────────────────────────────

def _contribute(request: Request):
    """POST /v1/federation/contribute — Accept external trust signals."""
    import asyncio

    async def _inner():
        body = await request.json()
        contributor = body.get("contributor", "")
        signals = body.get("signals", [])

        if not contributor or not signals:
            return JSONResponse({"error": "Missing contributor or signals"}, status_code=400)

        conn = _get_conn()
        accepted = 0
        rejected = 0

        for sig in signals:
            agent_name = sig.get("agent_name", "")
            signal_type = sig.get("signal_type", "")
            score = sig.get("score")
            max_score = sig.get("max_score", 100)
            evidence = sig.get("evidence", "")

            if not agent_name or not signal_type or score is None:
                rejected += 1
                continue

            try:
                conn.execute("""
                    INSERT INTO federation_contributions
                    (contributor, contributor_trust, agent_name, signal_type, score, max_score, evidence)
                    VALUES (?, 'UNVERIFIED', ?, ?, ?, ?, ?)
                """, (contributor, agent_name, signal_type, score, max_score, evidence[:500] if evidence else ""))
                accepted += 1
            except Exception:
                rejected += 1

        conn.commit()
        conn.close()

        return JSONResponse({
            "accepted": accepted,
            "rejected": rejected,
            "message": "Thank you. Signals will be incorporated into next trust score calculation.",
            "contributor_trust": "UNVERIFIED",
        })

    return asyncio.get_event_loop().run_until_complete(_inner()) if hasattr(request, '_receive') else JSONResponse({"error": "async required"})


def _sources(request: Request):
    """GET /v1/federation/sources — List all data sources."""
    if not _is_nerq(request):
        return JSONResponse({"error": "Not found"}, status_code=404)

    conn = _get_conn()

    # Count external signal coverage
    openssf_count = 0
    osv_count = 0
    so_count = 0
    reddit_count = 0
    try:
        openssf_count = conn.execute(
            "SELECT COUNT(DISTINCT agent_name) FROM external_trust_signals WHERE source = 'openssf_scorecard'"
        ).fetchone()[0]
        osv_count = conn.execute(
            "SELECT COUNT(DISTINCT agent_name) FROM external_trust_signals WHERE source = 'osv_dev'"
        ).fetchone()[0]
        so_count = conn.execute(
            "SELECT COUNT(DISTINCT agent_name) FROM external_trust_signals WHERE source = 'stackoverflow'"
        ).fetchone()[0]
        reddit_count = conn.execute(
            "SELECT COUNT(DISTINCT agent_name) FROM external_trust_signals WHERE source = 'reddit'"
        ).fetchone()[0]
    except Exception:
        pass

    # Federation contributors
    fed_contribs = []
    try:
        rows = conn.execute("""
            SELECT contributor, contributor_trust, COUNT(DISTINCT agent_name) as agents, COUNT(*) as signals
            FROM federation_contributions
            GROUP BY contributor
        """).fetchall()
        fed_contribs = [{"name": r[0], "trust_level": r[1], "agents": r[2], "signals": r[3]} for r in rows]
    except Exception:
        pass

    total_enriched = 0
    try:
        total_enriched = conn.execute(
            "SELECT COUNT(DISTINCT agent_name) FROM external_trust_signals"
        ).fetchone()[0]
    except Exception:
        pass

    conn.close()

    from agentindex.db.models import get_session
    session = get_session()
    try:
        total_agents = session.execute(text("SELECT COUNT(*) FROM entity_lookup WHERE is_active = true")).scalar() or 0
    finally:
        session.close()

    return JSONResponse({
        "proprietary_sources": [
            {"name": "GitHub Activity", "type": "code_quality", "coverage": f"{total_agents:,} agents"},
            {"name": "NPM Downloads", "type": "popularity", "coverage": "8,786 packages"},
            {"name": "PyPI Downloads", "type": "popularity", "coverage": "3,214 packages"},
            {"name": "CVE/NVD Scanner", "type": "security", "coverage": "2,000 agents"},
            {"name": "License Checker", "type": "compliance", "coverage": "4,785 agents"},
            {"name": "Framework Detector", "type": "compatibility", "coverage": "111 mappings"},
            {"name": "Pricing Crawler", "type": "economics", "coverage": "562 agents"},
        ],
        "external_sources": [
            {"name": "OpenSSF Scorecard", "type": "security", "coverage": f"{openssf_count:,} agents"},
            {"name": "OSV.dev", "type": "security", "coverage": f"{osv_count:,} agents"},
            {"name": "Stack Overflow", "type": "community", "coverage": f"{so_count:,} agents"},
            {"name": "Reddit", "type": "community", "coverage": f"{reddit_count:,} agents"},
        ],
        "federated_contributors": fed_contribs,
        "total_data_sources": 11 + len(fed_contribs),
        "total_agents_with_enrichment": total_enriched,
        "methodology": "https://nerq.ai/protocol",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })


def _agent_signals(request: Request, agent_name: str):
    """GET /v1/federation/agent/{name}/signals — Full signal breakdown."""
    if not _is_nerq(request):
        return JSONResponse({"error": "Not found"}, status_code=404)

    from agentindex.db.models import get_session
    session = get_session()

    try:
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        row = session.execute(text("""
            SELECT name, COALESCE(trust_score_v2, trust_score) as ts, trust_grade,
                   stars, downloads, license, source, category,
                   last_source_update, forks
            FROM agents
            WHERE name_lower LIKE :q AND is_active = true
            ORDER BY CASE WHEN name_lower = :exact THEN 0 ELSE 1 END
            LIMIT 1
        """), {"q": f"%{agent_name.lower()}%", "exact": agent_name.lower()}).fetchone()

        if not row:
            return JSONResponse({"error": "Agent not found"}, status_code=404)

        d = dict(row._mapping)
        name = d["name"]
        score = float(d["ts"]) if d["ts"] else 0

        # Get last commit days ago
        last_commit_days = None
        if d.get("last_source_update"):
            try:
                lu = d["last_source_update"]
                if isinstance(lu, str):
                    from datetime import datetime as dt
                    lu = dt.fromisoformat(lu.replace("Z", "+00:00"))
                last_commit_days = (datetime.now(timezone.utc) - lu.replace(tzinfo=timezone.utc if lu.tzinfo is None else lu.tzinfo)).days
            except Exception:
                pass

    finally:
        session.close()

    conn = _get_conn()

    # External signals
    external = {}
    try:
        rows = conn.execute(
            "SELECT source, signal_name, signal_value, signal_max, fetched_at FROM external_trust_signals WHERE agent_name = ?",
            (name,)
        ).fetchall()
        for r in rows:
            source = r[0]
            if source == "openssf_scorecard" and r[1] == "overall_score":
                external["openssf_scorecard"] = {"score": r[2], "max": r[3], "fetched": r[4][:10] if r[4] else None}
            elif source == "osv_dev" and r[1] == "vulnerability_count":
                max_sev_row = conn.execute(
                    "SELECT raw_data FROM external_trust_signals WHERE agent_name = ? AND source = 'osv_dev' AND signal_name = 'max_severity'",
                    (name,)
                ).fetchone()
                max_sev = json.loads(max_sev_row[0]).get("severity", "NONE") if max_sev_row and max_sev_row[0] else "NONE"
                external["osv_vulnerabilities"] = {"count": int(r[2] or 0), "max_severity": max_sev, "fetched": r[4][:10] if r[4] else None}
            elif source == "stackoverflow":
                external["stackoverflow_questions"] = int(r[2] or 0)
            elif source == "reddit":
                external["reddit_mentions_30d"] = int(r[2] or 0)
    except Exception:
        pass

    # CVEs from our DB
    known_cves = 0
    try:
        cve_row = conn.execute(
            "SELECT COUNT(*) FROM agent_vulnerabilities WHERE agent_name = ?",
            (name,)
        ).fetchone()
        known_cves = cve_row[0] if cve_row else 0
    except Exception:
        pass

    # Federation contributions
    federated = []
    try:
        fed_rows = conn.execute(
            "SELECT contributor, signal_type, score, max_score, evidence, contributed_at FROM federation_contributions WHERE agent_name = ?",
            (name,)
        ).fetchall()
        federated = [{"contributor": r[0], "signal_type": r[1], "score": r[2], "max_score": r[3],
                       "evidence": r[4], "contributed_at": r[5]} for r in fed_rows]
    except Exception:
        pass

    conn.close()

    data_sources = 3  # GitHub, name, description always present
    if d.get("downloads"): data_sources += 1
    if known_cves > 0: data_sources += 1
    if d.get("license"): data_sources += 1
    data_sources += len(external)
    if federated: data_sources += 1

    confidence = "HIGH" if data_sources >= 8 else "MEDIUM" if data_sources >= 5 else "LOW"

    return JSONResponse({
        "agent": name,
        "federated_score": score,
        "confidence": confidence,
        "signals": {
            "proprietary": {
                "github_stars": d.get("stars"),
                "github_forks": d.get("forks"),
                "downloads": d.get("downloads"),
                "known_cves": known_cves,
                "license": d.get("license"),
                "last_commit_days_ago": last_commit_days,
                "trust_score_nerq": score,
                "trust_grade": d.get("trust_grade"),
            },
            "external": external,
            "federated": federated,
        },
        "data_sources_used": data_sources,
        "methodology": "https://nerq.ai/trust-score",
    })


# ── Pages ────────────────────────────────────────────

def _verified_page(request: Request):
    """GET /verified — List of verified agents."""
    if not _is_nerq(request):
        return JSONResponse({"error": "Not found"}, status_code=404)

    conn = _get_conn()
    verified = []
    total = 0
    total_plus = 0
    try:
        rows = conn.execute("""
            SELECT agent_name, verification_level, verified_since, current_score, consecutive_days_above_threshold
            FROM verified_agents
            ORDER BY CASE WHEN verification_level = 'VERIFIED_PLUS' THEN 0 ELSE 1 END,
                     current_score DESC
        """).fetchall()
        for r in rows:
            verified.append({
                "name": r[0], "level": r[1], "since": r[2], "score": r[3], "days": r[4]
            })
            if r[1] == "VERIFIED_PLUS":
                total_plus += 1
            total += 1
    except Exception:
        pass
    conn.close()

    # Build page
    rows_html = ""
    for v in verified:
        slug = v["name"].lower().replace("/", "").replace(" ", "-")
        badge = "Verified+" if v["level"] == "VERIFIED_PLUS" else "Verified"
        badge_color = "#8b5cf6" if v["level"] == "VERIFIED_PLUS" else "#c2956b"
        since_str = v["since"][:10] if v["since"] else "—"
        rows_html += f"""
        <tr>
            <td><a href="/safe/{slug}" style="color:#c2956b;text-decoration:none;font-weight:600">{v["name"]}</a></td>
            <td><span style="background:{badge_color};color:#fff;padding:2px 10px;border-radius:4px;font-size:12px">{badge}</span></td>
            <td style="font-family:var(--mono)">{v["score"]:.1f}</td>
            <td>{v["days"]}d</td>
            <td>{since_str}</td>
        </tr>"""

    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "What does Nerq Verified mean?",
             "acceptedAnswer": {"@type": "Answer", "text": f"Nerq Verified means an AI agent has maintained a trust score of 80 or above for at least 30 consecutive days. Currently {total} agents hold this status."}},
            {"@type": "Question", "name": "How do I get my agent verified?",
             "acceptedAnswer": {"@type": "Answer", "text": "Maintain a Nerq trust score of 80+ for 30 consecutive days. Scores are automatically calculated from code quality, community adoption, compliance, security, and external validation signals."}},
            {"@type": "Question", "name": f"How many agents are Nerq Verified?",
             "acceptedAnswer": {"@type": "Answer", "text": f"Currently {total} agents are Nerq Verified, of which {total_plus} hold the premium Verified+ status (trust score 90+ for 30 days)."}},
        ]
    })

    body = f"""
    <script type="application/ld+json">{faq_schema}</script>
    <h1 style="font-family:var(--serif)">Verified AI Agents</h1>
    <p style="color:#888;max-width:700px">
        Nerq Verified agents have maintained consistently high trust scores, demonstrating sustained
        code quality, community support, compliance, and security.
    </p>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin:24px 0">
        <div style="background:#1a1a1a;border-radius:8px;padding:20px;text-align:center">
            <div style="font-family:var(--mono);font-size:28px;color:#c2956b">{total}</div>
            <div style="color:#888;font-size:13px">Total Verified</div>
        </div>
        <div style="background:#1a1a1a;border-radius:8px;padding:20px;text-align:center">
            <div style="font-family:var(--mono);font-size:28px;color:#8b5cf6">{total_plus}</div>
            <div style="color:#888;font-size:13px">Verified+</div>
        </div>
        <div style="background:#1a1a1a;border-radius:8px;padding:20px;text-align:center">
            <div style="font-family:var(--mono);font-size:28px;color:#16a34a">{total - total_plus}</div>
            <div style="color:#888;font-size:13px">Verified</div>
        </div>
    </div>

    <h2 style="font-family:var(--serif);margin-top:32px">How to Get Verified</h2>
    <div style="background:#1a1a1a;border-radius:8px;padding:20px;margin-bottom:24px;max-width:700px">
        <p style="margin:0 0 12px 0"><strong>VERIFIED</strong> — Maintain a Nerq trust score of <span style="color:#c2956b">80+</span> for 30 consecutive days.</p>
        <p style="margin:0"><strong>VERIFIED+</strong> — Maintain a Nerq trust score of <span style="color:#8b5cf6">90+</span> for 30 consecutive days.</p>
    </div>

    <h2 style="font-family:var(--serif)">Verified Agents</h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
        <thead>
            <tr style="border-bottom:1px solid #333;color:#888">
                <th style="text-align:left;padding:8px">Agent</th>
                <th style="text-align:left;padding:8px">Status</th>
                <th style="text-align:left;padding:8px">Score</th>
                <th style="text-align:left;padding:8px">Streak</th>
                <th style="text-align:left;padding:8px">Since</th>
            </tr>
        </thead>
        <tbody>{rows_html if rows_html else '<tr><td colspan="5" style="padding:20px;color:#666;text-align:center">Verification program just launched — first verified agents will appear within 30 days.</td></tr>'}</tbody>
    </table>

    <h2 style="font-family:var(--serif);margin-top:40px">FAQ</h2>
    <details style="margin-bottom:12px;background:#1a1a1a;border-radius:8px;padding:16px">
        <summary style="cursor:pointer;font-weight:600">What does Nerq Verified mean?</summary>
        <p style="color:#ccc;margin-top:8px">Nerq Verified means an AI agent has maintained a trust score of 80 or above for at least 30 consecutive days, demonstrating consistent quality across code, community, compliance, and security dimensions.</p>
    </details>
    <details style="margin-bottom:12px;background:#1a1a1a;border-radius:8px;padding:16px">
        <summary style="cursor:pointer;font-weight:600">How do I get my agent verified?</summary>
        <p style="color:#ccc;margin-top:8px">Simply maintain a high-quality project. Nerq automatically scores all indexed agents daily. Once your score stays at 80+ for 30 days, you'll be verified automatically.</p>
    </details>
    <details style="margin-bottom:12px;background:#1a1a1a;border-radius:8px;padding:16px">
        <summary style="cursor:pointer;font-weight:600">Can verification be revoked?</summary>
        <p style="color:#ccc;margin-top:8px">Yes. If your trust score drops below 80, there is a 7-day grace period. If it does not recover, verification is removed.</p>
    </details>
    """

    html = nerq_page("Verified AI Agents — Nerq Trusted | Nerq", body,
                      description=f"{total} verified AI agents with sustained trust scores of 80+. Nerq Verified means consistent quality.",
                      canonical="https://nerq.ai/verified")
    return HTMLResponse(content=html)


def _federation_page(request: Request):
    """GET /federation — Federation protocol page."""
    if not _is_nerq(request):
        return JSONResponse({"error": "Not found"}, status_code=404)

    conn = _get_conn()
    contribs = 0
    try:
        contribs = conn.execute("SELECT COUNT(DISTINCT contributor) FROM federation_contributions").fetchone()[0]
    except Exception:
        pass
    conn.close()

    body = f"""
    <h1 style="font-family:var(--serif)">Nerq Trust Federation</h1>
    <p style="color:#888;max-width:700px;font-size:16px">
        Contribute &amp; consume trust data. Nerq aggregates trust signals from multiple independent sources.
        The more sources, the more reliable the score.
    </p>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px;margin:32px 0">
        <div style="background:#1a1a1a;border-radius:8px;padding:24px">
            <h3 style="font-family:var(--serif);color:#c2956b;margin-top:0">What is Federation?</h3>
            <p style="color:#ccc;font-size:14px">Trust federation allows multiple platforms to contribute their independent quality assessments to a shared trust score. Instead of relying on a single source, federated scores combine signals from OpenSSF, OSV.dev, community data, and partner platforms.</p>
        </div>
        <div style="background:#1a1a1a;border-radius:8px;padding:24px">
            <h3 style="font-family:var(--serif);color:#c2956b;margin-top:0">Why It Matters</h3>
            <p style="color:#ccc;font-size:14px">No single platform can observe everything. OpenSSF sees security practices. npm sees downloads. GitHub sees code quality. By federating these signals, we create a more complete and harder-to-game trust score.</p>
        </div>
    </div>

    <h2 style="font-family:var(--serif)">For Data Contributors</h2>
    <div style="background:#1a1a1a;border-radius:8px;padding:24px;margin-bottom:24px">
        <p style="color:#ccc;margin-top:0">Submit your trust signals via our API:</p>
        <pre style="background:#111;border-radius:6px;padding:16px;overflow-x:auto;font-size:13px;color:#e0e0e0">POST /v1/federation/contribute
Content-Type: application/json

{{
  "contributor": "your-platform.io",
  "signals": [
    {{
      "agent_name": "langchain",
      "signal_type": "behavioral_reputation",
      "score": 82,
      "max_score": 100,
      "evidence": "Based on 5,000 successful task completions"
    }}
  ]
}}</pre>
        <h4 style="color:#c2956b;margin-bottom:8px">Trust Levels</h4>
        <table style="width:100%;font-size:13px;border-collapse:collapse">
            <tr style="border-bottom:1px solid #333">
                <td style="padding:8px;color:#888">UNVERIFIED</td>
                <td style="padding:8px;color:#ccc">New contributor — signals stored but given minimal weight</td>
            </tr>
            <tr style="border-bottom:1px solid #333">
                <td style="padding:8px;color:#c2956b">VERIFIED</td>
                <td style="padding:8px;color:#ccc">Methodology validated by Nerq — standard weight in scoring</td>
            </tr>
            <tr>
                <td style="padding:8px;color:#8b5cf6">TRUSTED</td>
                <td style="padding:8px;color:#ccc">Established partner — full weight in trust calculations</td>
            </tr>
        </table>
    </div>

    <h2 style="font-family:var(--serif)">For Data Consumers</h2>
    <div style="background:#1a1a1a;border-radius:8px;padding:24px;margin-bottom:24px">
        <p style="color:#ccc;margin-top:0">Access federated trust scores via:</p>
        <pre style="background:#111;border-radius:6px;padding:16px;overflow-x:auto;font-size:13px;color:#e0e0e0">GET /v1/federation/sources
GET /v1/federation/agent/{{name}}/signals
GET /v1/preflight?target={{name}}</pre>
        <p style="color:#888;font-size:13px;margin-bottom:0">All responses include confidence levels based on number of data sources available.</p>
    </div>

    <h2 style="font-family:var(--serif)">Open Invitation</h2>
    <p style="color:#ccc;max-width:700px">
        We invite all platforms that assess AI agent quality to contribute their signals.
        Whether you track task completion rates, user satisfaction, uptime metrics, or behavioral reputation —
        your data makes the ecosystem's trust scores more reliable for everyone.
    </p>
    <p style="color:#888;font-size:14px">
        Current federated contributors: <strong style="color:#c2956b">{contribs}</strong>
    </p>
    """

    html = nerq_page("Nerq Trust Federation — Contribute & Consume Trust Data", body,
                      description="Nerq Trust Federation: contribute and consume multi-source trust data for AI agents. Open protocol for building trustworthy AI.",
                      canonical="https://nerq.ai/federation")
    return HTMLResponse(content=html)


def _verified_badge_svg(request: Request, agent_name: str):
    """GET /badge/{name}/verified.svg — Gold verified badge."""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="160" height="20">
  <linearGradient id="a" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <rect rx="3" width="160" height="20" fill="#555"/>
  <rect rx="3" x="80" width="80" height="20" fill="#c2956b"/>
  <rect rx="3" width="160" height="20" fill="url(#a)"/>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,sans-serif" font-size="11">
    <text x="40" y="14">nerq</text>
    <text x="120" y="14">✓ verified</text>
  </g>
</svg>"""
    return HTMLResponse(content=svg, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})


def _verified_plus_badge_svg(request: Request, agent_name: str):
    """GET /badge/{name}/verified-plus.svg — Platinum verified+ badge."""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="170" height="20">
  <linearGradient id="a" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <rect rx="3" width="170" height="20" fill="#555"/>
  <rect rx="3" x="80" width="90" height="20" fill="#8b5cf6"/>
  <rect rx="3" width="170" height="20" fill="url(#a)"/>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,sans-serif" font-size="11">
    <text x="40" y="14">nerq</text>
    <text x="125" y="14">✦ verified+</text>
  </g>
</svg>"""
    return HTMLResponse(content=svg, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})


# ── Mount ────────────────────────────────────────────

def mount_federation(app):
    """Mount federation API and pages on the app."""
    from fastapi import Body

    @app.post("/v1/federation/contribute")
    async def contribute(request: Request):
        body = await request.json()
        contributor = body.get("contributor", "")
        signals = body.get("signals", [])

        if not contributor or not signals:
            return JSONResponse({"error": "Missing contributor or signals"}, status_code=400)

        conn = _get_conn()
        accepted = 0
        rejected = 0

        for sig in signals:
            agent_name = sig.get("agent_name", "")
            signal_type = sig.get("signal_type", "")
            score = sig.get("score")
            max_score = sig.get("max_score", 100)
            evidence = sig.get("evidence", "")

            if not agent_name or not signal_type or score is None:
                rejected += 1
                continue

            try:
                conn.execute("""
                    INSERT INTO federation_contributions
                    (contributor, contributor_trust, agent_name, signal_type, score, max_score, evidence)
                    VALUES (?, 'UNVERIFIED', ?, ?, ?, ?, ?)
                """, (contributor, agent_name, signal_type, score, max_score, (evidence or "")[:500]))
                accepted += 1
            except Exception as e:
                logger.error(f"Federation insert error: {e}")
                rejected += 1

        conn.commit()
        conn.close()

        return JSONResponse({
            "accepted": accepted,
            "rejected": rejected,
            "message": "Thank you. Signals will be incorporated into next trust score calculation.",
            "contributor_trust": "UNVERIFIED",
        })

    app.add_api_route("/v1/federation/sources", _sources, methods=["GET"])
    app.add_api_route("/v1/federation/agent/{agent_name:path}/signals", _agent_signals, methods=["GET"])
    app.add_api_route("/verified", _verified_page, methods=["GET"])
    app.add_api_route("/federation", _federation_page, methods=["GET"])
    app.add_api_route("/badge/{agent_name}/verified.svg", _verified_badge_svg, methods=["GET"])
    app.add_api_route("/badge/{agent_name}/verified-plus.svg", _verified_plus_badge_svg, methods=["GET"])
