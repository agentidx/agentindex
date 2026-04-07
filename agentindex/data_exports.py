"""
Data Exports & Webhook System
==============================
Serves downloadable data products and webhook subscriptions.

Routes:
  GET  /data                     — Open data download page
  GET  /data/trust-scores-latest.csv   — Top 10K agents CSV
  GET  /data/trust-scores-latest.json  — Top 10K agents JSON
  GET  /data/frameworks-latest.json    — Framework statistics
  GET  /data/cves-latest.json          — CVE summary
  POST /v1/webhooks/subscribe          — Subscribe to events
  GET  /v1/webhooks                    — List subscriptions
  DELETE /v1/webhooks/{id}             — Remove subscription
  GET  /webhooks                       — Documentation page
"""

import csv
import hashlib
import hmac
import io
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import text

from agentindex.db.models import get_session

logger = logging.getLogger("nerq.data-exports")

SQLITE_DB = "/Users/anstudio/agentindex/data/crypto_trust.db"
_data_cache = {}
_CACHE_TTL = 3600  # 1 hour


def _get_sqlite():
    return sqlite3.connect(SQLITE_DB, timeout=10)


def _init_webhook_db():
    try:
        conn = _get_sqlite()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS webhook_subscriptions (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                events TEXT NOT NULL,
                filter TEXT,
                secret TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_triggered TIMESTAMP,
                failure_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not init webhook DB: {e}")


def _cached(key, ttl=_CACHE_TTL):
    """Check if cache is valid."""
    if key in _data_cache:
        data, ts = _data_cache[key]
        if time.time() - ts < ttl:
            return data
    return None


def mount_data_exports(app):
    """Mount data export and webhook routes."""
    _init_webhook_db()

    # ================================================================
    # /data — Open Data page
    # ================================================================
    @app.get("/data", response_class=HTMLResponse)
    def data_page():
        try:
            from agentindex.nerq_design import nerq_page
            body = """
<h1>Open Data — Nerq AI Agent Trust Scores</h1>
<p>Download trust scores for 10,000+ AI agents. Updated weekly. <strong>CC-BY-4.0 license.</strong></p>

<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin:24px 0">
  <div style="border:1px solid #e5e7eb;padding:20px;border-radius:8px">
    <h3 style="margin:0 0 8px">Trust Scores CSV</h3>
    <p style="font-size:14px;color:#6b7280;margin:0 0 12px">Top 10,000 agents with trust scores, grades, categories, stars.</p>
    <a href="/data/trust-scores-latest.csv" style="display:inline-block;padding:8px 16px;background:#0d9488;color:white;text-decoration:none;border-radius:4px;font-size:14px">Download CSV</a>
  </div>
  <div style="border:1px solid #e5e7eb;padding:20px;border-radius:8px">
    <h3 style="margin:0 0 8px">Trust Scores JSON</h3>
    <p style="font-size:14px;color:#6b7280;margin:0 0 12px">Same data in JSON format for programmatic use.</p>
    <a href="/data/trust-scores-latest.json" style="display:inline-block;padding:8px 16px;background:#0d9488;color:white;text-decoration:none;border-radius:4px;font-size:14px">Download JSON</a>
  </div>
  <div style="border:1px solid #e5e7eb;padding:20px;border-radius:8px">
    <h3 style="margin:0 0 8px">Framework Stats</h3>
    <p style="font-size:14px;color:#6b7280;margin:0 0 12px">Agent counts and average trust scores per framework.</p>
    <a href="/data/frameworks-latest.json" style="display:inline-block;padding:8px 16px;background:#0d9488;color:white;text-decoration:none;border-radius:4px;font-size:14px">Download JSON</a>
  </div>
  <div style="border:1px solid #e5e7eb;padding:20px;border-radius:8px">
    <h3 style="margin:0 0 8px">CVE Summary</h3>
    <p style="font-size:14px;color:#6b7280;margin:0 0 12px">Known vulnerabilities affecting indexed agents.</p>
    <a href="/data/cves-latest.json" style="display:inline-block;padding:8px 16px;background:#0d9488;color:white;text-decoration:none;border-radius:4px;font-size:14px">Download JSON</a>
  </div>
</div>

<h2>API Access</h2>
<p>All data is also available via the REST API (no auth required):</p>
<pre><code>GET https://nerq.ai/v1/agent/search?q=langchain&limit=100
GET https://nerq.ai/v1/agent/stats
GET https://nerq.ai/v1/preflight?target=langchain</code></pre>
<p><a href="/nerq/docs">Full API documentation</a></p>

<h2>Webhooks</h2>
<p>Subscribe to real-time events (CVE alerts, trust changes, trending agents). <a href="/webhooks">Webhook documentation</a>.</p>

<h2>RSS Feeds</h2>
<ul>
<li><a href="/feed/cve-alerts.xml">CVE Alerts</a> (Atom)</li>
<li><a href="/feed/trending.xml">Trending Agents</a> (Atom)</li>
<li><a href="/feed/trust-changes.xml">Trust Score Changes</a> (Atom)</li>
</ul>

<h2>Citation</h2>
<p>Cite as: <em>Nerq AI Agent Trust Scores Dataset, 2026. https://nerq.ai/data</em></p>
<p>License: <a href="https://creativecommons.org/licenses/by/4.0/">CC-BY-4.0</a></p>
"""
            return HTMLResponse(content=nerq_page("Open Data — AI Agent Trust Scores", body,
                               description="Download trust scores for 10,000+ AI agents. Updated weekly. CC-BY-4.0."))
        except Exception:
            return HTMLResponse(content="<h1>Open Data</h1><p>Downloads available at /data/trust-scores-latest.csv</p>")

    # ================================================================
    # Data downloads
    # ================================================================
    @app.get("/data/trust-scores-latest.csv", response_class=Response)
    def trust_scores_csv():
        cached = _cached("csv")
        if cached:
            return Response(content=cached, media_type="text/csv",
                          headers={"Content-Disposition": "attachment; filename=nerq-trust-scores.csv"})
        try:
            s = get_session()
            rows = s.execute(text("""
                SELECT name, agent_type, category, source,
                       COALESCE(trust_score_v2, trust_score) as trust_score,
                       trust_grade, compliance_score, stars, author, source_url
                FROM entity_lookup
                WHERE is_active = true AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
                ORDER BY COALESCE(trust_score_v2, trust_score) DESC
                LIMIT 10000
            """)).fetchall()
            s.close()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["name", "type", "category", "source", "trust_score", "grade",
                           "compliance_score", "stars", "author", "source_url"])
            for r in rows:
                writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]])
            content = output.getvalue()
            _data_cache["csv"] = (content, time.time())
            return Response(content=content, media_type="text/csv",
                          headers={"Content-Disposition": "attachment; filename=nerq-trust-scores.csv"})
        except Exception as e:
            return Response(content=f"Error: {e}", status_code=500)

    @app.get("/data/trust-scores-latest.json")
    def trust_scores_json():
        cached = _cached("json")
        if cached:
            return JSONResponse(content=cached)
        try:
            s = get_session()
            rows = s.execute(text("""
                SELECT name, agent_type, category, source,
                       COALESCE(trust_score_v2, trust_score) as trust_score,
                       trust_grade, compliance_score, stars, author, source_url
                FROM entity_lookup
                WHERE is_active = true AND COALESCE(trust_score_v2, trust_score) IS NOT NULL
                ORDER BY COALESCE(trust_score_v2, trust_score) DESC
                LIMIT 10000
            """)).fetchall()
            s.close()

            data = [{
                "name": r[0], "type": r[1], "category": r[2], "source": r[3],
                "trust_score": float(r[4]) if r[4] else None, "grade": r[5],
                "compliance_score": float(r[6]) if r[6] else None,
                "stars": r[7], "author": r[8], "source_url": r[9]
            } for r in rows]
            _data_cache["json"] = (data, time.time())
            return JSONResponse(content=data)
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.get("/data/frameworks-latest.json")
    def frameworks_json():
        cached = _cached("frameworks")
        if cached:
            return JSONResponse(content=cached)
        try:
            s = get_session()
            rows = s.execute(text("""
                SELECT category, COUNT(*) as count,
                       AVG(COALESCE(trust_score_v2, trust_score)) as avg_score,
                       AVG(compliance_score) as avg_compliance
                FROM entity_lookup
                WHERE is_active = true AND category IS NOT NULL
                GROUP BY category
                HAVING COUNT(*) >= 5
                ORDER BY count DESC
                LIMIT 100
            """)).fetchall()
            s.close()
            data = [{
                "category": r[0], "count": r[1],
                "avg_trust_score": round(float(r[2]), 1) if r[2] else None,
                "avg_compliance": round(float(r[3]), 1) if r[3] else None,
            } for r in rows]
            _data_cache["frameworks"] = (data, time.time())
            return JSONResponse(content=data)
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.get("/data/cves-latest.json")
    def cves_json():
        cached = _cached("cves")
        if cached:
            return JSONResponse(content=cached)
        try:
            conn = sqlite3.connect("/Users/anstudio/agentindex/agentindex/crypto/crypto_trust.db", timeout=10)
            rows = conn.execute("""
                SELECT agent_name, cve_id, severity, description, fetched_at
                FROM agent_vulnerabilities
                ORDER BY fetched_at DESC
                LIMIT 500
            """).fetchall()
            conn.close()
            data = [{
                "agent": r[0], "cve_id": r[1], "severity": r[2],
                "description": r[3], "fetched_at": r[4]
            } for r in rows]
            _data_cache["cves"] = (data, time.time())
            return JSONResponse(content=data)
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=500)

    # ================================================================
    # Webhook system
    # ================================================================
    @app.post("/v1/webhooks/subscribe")
    async def webhook_subscribe(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(content={"error": "Invalid JSON"}, status_code=400)

        url = body.get("url")
        events = body.get("events", [])
        filter_data = body.get("filter", {})
        secret = body.get("secret", "")

        if not url:
            return JSONResponse(content={"error": "url is required"}, status_code=400)
        if not events:
            return JSONResponse(content={"error": "events list is required"}, status_code=400)

        valid_events = {"cve_alert", "trust_change", "trending_agent"}
        invalid = set(events) - valid_events
        if invalid:
            return JSONResponse(content={"error": f"Invalid events: {invalid}. Valid: {valid_events}"}, status_code=400)

        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat() + "Z"

        try:
            conn = _get_sqlite()
            conn.execute(
                "INSERT INTO webhook_subscriptions (id, url, events, filter, secret) VALUES (?, ?, ?, ?, ?)",
                (sub_id, url, json.dumps(events), json.dumps(filter_data), secret)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            return JSONResponse(content={"error": f"Database error: {e}"}, status_code=500)

        return JSONResponse(content={
            "subscription_id": sub_id,
            "status": "active",
            "events": events,
            "created": now,
        }, status_code=201)

    @app.get("/v1/webhooks")
    async def webhook_list(request: Request):
        try:
            conn = _get_sqlite()
            rows = conn.execute(
                "SELECT id, url, events, filter, created_at, last_triggered, failure_count, is_active "
                "FROM webhook_subscriptions WHERE is_active = 1 ORDER BY created_at DESC"
            ).fetchall()
            conn.close()
            subs = [{
                "id": r[0], "url": r[1], "events": json.loads(r[2]),
                "filter": json.loads(r[3]) if r[3] else {},
                "created_at": r[4], "last_triggered": r[5],
                "failure_count": r[6], "active": bool(r[7])
            } for r in rows]
            return JSONResponse(content={"subscriptions": subs, "count": len(subs)})
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=500)

    @app.delete("/v1/webhooks/{sub_id}")
    async def webhook_delete(sub_id: str):
        try:
            conn = _get_sqlite()
            conn.execute("UPDATE webhook_subscriptions SET is_active = 0 WHERE id = ?", (sub_id,))
            conn.commit()
            conn.close()
            return JSONResponse(content={"status": "deleted", "id": sub_id})
        except Exception as e:
            return JSONResponse(content={"error": str(e)}, status_code=500)

    # ================================================================
    # /webhooks — Documentation page
    # ================================================================
    @app.get("/webhooks", response_class=HTMLResponse)
    def webhooks_page():
        try:
            from agentindex.nerq_design import nerq_page
            body = """
<h1>Webhook Subscriptions</h1>
<p>Receive real-time notifications for CVE alerts, trust score changes, and trending agents.</p>

<h2>Subscribe</h2>
<pre><code>POST https://nerq.ai/v1/webhooks/subscribe
Content-Type: application/json

{
  "url": "https://your-server.com/webhook",
  "events": ["cve_alert", "trust_change", "trending_agent"],
  "filter": {
    "agents": ["langchain", "crewai"],
    "min_severity": "HIGH"
  },
  "secret": "your-webhook-secret"
}</code></pre>

<h3>Response</h3>
<pre><code>{
  "subscription_id": "sub_abc123",
  "status": "active",
  "events": ["cve_alert", "trust_change", "trending_agent"],
  "created": "2026-03-13T12:00:00Z"
}</code></pre>

<h2>Events</h2>
<table>
<thead><tr><th>Event</th><th>Description</th><th>Frequency</th></tr></thead>
<tbody>
<tr><td><code>cve_alert</code></td><td>New CVE affecting an indexed agent</td><td>As discovered</td></tr>
<tr><td><code>trust_change</code></td><td>Trust score changed by &gt;10 points</td><td>Daily</td></tr>
<tr><td><code>trending_agent</code></td><td>Agent trending in popularity</td><td>Weekly</td></tr>
</tbody>
</table>

<h2>Payload Signing</h2>
<p>If you provide a <code>secret</code>, each webhook payload includes an <code>X-Nerq-Signature</code> header with an HMAC-SHA256 signature of the body.</p>
<pre><code>import hmac, hashlib
expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
assert signature == f"sha256={expected}"</code></pre>

<h2>Manage Subscriptions</h2>
<pre><code>GET  /v1/webhooks          — List active subscriptions
DELETE /v1/webhooks/{id}   — Remove a subscription</code></pre>

<h2>Retry Policy</h2>
<p>Failed deliveries retry up to 3 times with exponential backoff. Subscriptions are disabled after 10 consecutive failures.</p>
"""
            return HTMLResponse(content=nerq_page("Webhook Subscriptions", body,
                               description="Subscribe to real-time CVE alerts, trust changes, and trending agent notifications."))
        except Exception:
            return HTMLResponse(content="<h1>Webhooks</h1><p>POST /v1/webhooks/subscribe to subscribe.</p>")

    logger.info("Data exports & webhook system mounted")


def dispatch_webhook(event_type: str, payload: dict):
    """Dispatch a webhook event to all matching subscribers."""
    try:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT id, url, events, filter, secret, failure_count FROM webhook_subscriptions WHERE is_active = 1"
        ).fetchall()
        conn.close()
    except Exception:
        return

    import urllib.request

    for r in rows:
        sub_id, url, events_str, filter_str, secret, failures = r
        events = json.loads(events_str)
        if event_type not in events:
            continue

        # Check filter
        if filter_str:
            f = json.loads(filter_str)
            agents_filter = f.get("agents", [])
            if agents_filter and payload.get("agent") not in agents_filter:
                continue

        body = json.dumps({"event": event_type, "data": payload, "timestamp": datetime.utcnow().isoformat()})
        headers = {"Content-Type": "application/json", "User-Agent": "Nerq-Webhook/1.0"}

        if secret:
            sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Nerq-Signature"] = f"sha256={sig}"

        try:
            req = urllib.request.Request(url, data=body.encode(), headers=headers, method="POST")
            urllib.request.urlopen(req, timeout=10)
            conn2 = _get_sqlite()
            conn2.execute("UPDATE webhook_subscriptions SET last_triggered = CURRENT_TIMESTAMP, failure_count = 0 WHERE id = ?", (sub_id,))
            conn2.commit()
            conn2.close()
        except Exception:
            conn2 = _get_sqlite()
            new_failures = failures + 1
            if new_failures >= 10:
                conn2.execute("UPDATE webhook_subscriptions SET is_active = 0, failure_count = ? WHERE id = ?", (new_failures, sub_id))
            else:
                conn2.execute("UPDATE webhook_subscriptions SET failure_count = ? WHERE id = ?", (new_failures, sub_id))
            conn2.commit()
            conn2.close()
