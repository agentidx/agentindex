"""
zarq_websocket_webhooks.py — Sprint 10: Real-time streaming + Webhook system

WebSocket streams (3 channels):
  /v1/stream/signals      — HC Alerts, STRUCTURAL_COLLAPSE, STRUCTURAL_STRESS
  /v1/stream/yield-traps  — New/escalated yield traps
  /v1/stream/agents       — New on-chain agent detections

Webhook system:
  POST /v1/webhooks/register  — register endpoint + event filter
  GET  /v1/webhooks           — list webhooks (by API key)
  DELETE /v1/webhooks/{id}    — remove webhook

Webhook delivery:
  - Exponential backoff retry: 3 attempts (5s, 25s, 125s)
  - HMAC-SHA256 payload signing
  - Dead Letter Queue for failed deliveries
  - Background delivery thread

Additive only — does NOT modify any nerq.ai routes.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Any

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("zarq.ws")

# ── Config ─────────────────────────────────────────────────────────────────────

DB_PATH = os.path.expanduser("~/agentindex/agentindex/crypto/crypto_trust.db")
WEBHOOK_DB = os.path.expanduser("~/agentindex/agentindex/crypto/zarq_webhooks.db")

VALID_EVENTS = {
    "signal.critical",
    "signal.structural_collapse",
    "signal.structural_stress",
    "yield.trap_new",
    "yield.trap_escalated",
    "agent.new_detected",
    "portfolio.risk_threshold",
}

RETRY_DELAYS = [5, 25, 125]   # seconds between retry attempts
DLQ_MAX = 1000                 # max dead letter queue entries

router_ws = APIRouter(tags=["WebSocket", "Webhooks"])


# ── Webhook DB setup ──────────────────────────────────────────────────────────

def init_webhook_db():
    conn = sqlite3.connect(WEBHOOK_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            webhook_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            events TEXT NOT NULL,
            secret TEXT,
            metadata TEXT,
            api_key TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            delivery_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            last_delivery_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
            delivery_id TEXT PRIMARY KEY,
            webhook_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            next_attempt_at REAL NOT NULL,
            last_attempt_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_dlq (
            dlq_id TEXT PRIMARY KEY,
            webhook_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            last_error TEXT,
            failed_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_webhook_db()


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections per channel."""

    def __init__(self):
        self._channels: Dict[str, Set[WebSocket]] = {
            "signals": set(),
            "yield-traps": set(),
            "agents": set(),
        }
        self._lock = threading.Lock()

    def connect(self, channel: str, ws: WebSocket):
        with self._lock:
            self._channels.setdefault(channel, set()).add(ws)

    def disconnect(self, channel: str, ws: WebSocket):
        with self._lock:
            self._channels.get(channel, set()).discard(ws)

    async def broadcast(self, channel: str, message: Dict):
        """Broadcast JSON message to all connections on a channel."""
        payload = json.dumps(message)
        dead = set()
        with self._lock:
            connections = set(self._channels.get(channel, set()))

        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        if dead:
            with self._lock:
                self._channels.get(channel, set()).difference_update(dead)

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._channels.get(channel, set()))


manager = ConnectionManager()


# ── WebSocket endpoints ───────────────────────────────────────────────────────

@router_ws.websocket("/v1/stream/signals")
async def ws_signals(websocket: WebSocket):
    """Real-time risk signal stream — HC Alerts, STRUCTURAL_COLLAPSE, STRUCTURAL_STRESS."""
    await websocket.accept()
    manager.connect("signals", websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "signals",
            "message": "Connected to ZARQ signal stream. Events fire on new HC Alerts and structural weakness detections.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        while True:
            # Keep-alive ping every 30s
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        manager.disconnect("signals", websocket)
    except Exception as e:
        logger.warning(f"Signal WS disconnect: {e}")
        manager.disconnect("signals", websocket)


@router_ws.websocket("/v1/stream/yield-traps")
async def ws_yield_traps(websocket: WebSocket):
    """Real-time yield trap alerts — fires when new traps detected or traps escalate."""
    await websocket.accept()
    manager.connect("yield-traps", websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "yield-traps",
            "message": "Connected to ZARQ yield trap stream.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        manager.disconnect("yield-traps", websocket)
    except Exception as e:
        logger.warning(f"Yield WS disconnect: {e}")
        manager.disconnect("yield-traps", websocket)


@router_ws.websocket("/v1/stream/agents")
async def ws_agents(websocket: WebSocket):
    """Real-time agent activity stream — new on-chain agent detections and activity spikes."""
    await websocket.accept()
    manager.connect("agents", websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "agents",
            "message": "Connected to ZARQ agent stream.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        manager.disconnect("agents", websocket)
    except Exception as e:
        logger.warning(f"Agent WS disconnect: {e}")
        manager.disconnect("agents", websocket)


# ── Event dispatcher — call this from signal/yield/agent pipelines ─────────────

async def dispatch_event(event_type: str, payload: Dict):
    """
    Dispatch an event to WebSocket subscribers and webhook queue.

    Call this from your existing pipelines when signals fire:

        from agentindex.crypto.zarq_websocket_webhooks import dispatch_event
        await dispatch_event("signal.critical", {"token_id": "xyz", ...})
    """
    event = {
        "type": "event",
        "event": event_type,
        "data": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # WebSocket broadcast
    channel_map = {
        "signal.critical": "signals",
        "signal.structural_collapse": "signals",
        "signal.structural_stress": "signals",
        "yield.trap_new": "yield-traps",
        "yield.trap_escalated": "yield-traps",
        "agent.new_detected": "agents",
    }
    channel = channel_map.get(event_type)
    if channel:
        await manager.broadcast(channel, event)

    # Queue webhook deliveries (non-blocking)
    threading.Thread(
        target=_queue_webhooks,
        args=(event_type, payload),
        daemon=True,
    ).start()


def _queue_webhooks(event_type: str, payload: Dict):
    """Find matching webhooks and queue delivery."""
    conn = sqlite3.connect(WEBHOOK_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        webhooks = conn.execute(
            "SELECT * FROM webhooks WHERE status = 'active'"
        ).fetchall()
        for wh in webhooks:
            events = json.loads(wh["events"])
            if event_type in events or "*" in events:
                delivery_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO webhook_deliveries
                    (delivery_id, webhook_id, event_type, payload, status,
                     attempts, next_attempt_at, created_at)
                    VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)
                """, (
                    delivery_id,
                    wh["webhook_id"],
                    event_type,
                    json.dumps({"event": event_type, "data": payload,
                                "timestamp": datetime.now(timezone.utc).isoformat()}),
                    time.time(),
                    datetime.now(timezone.utc).isoformat(),
                ))
        conn.commit()
    finally:
        conn.close()


# ── Webhook delivery worker ───────────────────────────────────────────────────

def _webhook_delivery_worker():
    """Background thread: deliver pending webhooks with exponential backoff retry."""
    client = httpx.Client(timeout=10)
    while True:
        try:
            _process_pending_deliveries(client)
        except Exception as e:
            logger.error(f"Webhook worker error: {e}")
        time.sleep(5)


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """HMAC-SHA256 signature for payload verification."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def _process_pending_deliveries(client: httpx.Client):
    conn = sqlite3.connect(WEBHOOK_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        now = time.time()
        pending = conn.execute("""
            SELECT d.*, w.url, w.secret, w.webhook_id as wh_id
            FROM webhook_deliveries d
            JOIN webhooks w ON w.webhook_id = d.webhook_id
            WHERE d.status = 'pending' AND d.next_attempt_at <= ?
            LIMIT 50
        """, (now,)).fetchall()

        for delivery in pending:
            delivery_id = delivery["delivery_id"]
            attempts = delivery["attempts"]
            payload_str = delivery["payload"]
            url = delivery["url"]
            secret = delivery["secret"]

            headers = {
                "Content-Type": "application/json",
                "X-ZARQ-Event": delivery["event_type"],
                "X-ZARQ-Delivery": delivery_id,
                "X-ZARQ-Attempt": str(attempts + 1),
            }

            if secret:
                sig = _sign_payload(payload_str.encode(), secret)
                headers["X-ZARQ-Signature"] = f"sha256={sig}"

            try:
                resp = client.post(url, content=payload_str, headers=headers)
                success = resp.is_success

            except Exception as e:
                success = False
                last_error = str(e)
            else:
                last_error = None if success else f"HTTP {resp.status_code}"

            new_attempts = attempts + 1
            now_iso = datetime.now(timezone.utc).isoformat()

            if success:
                conn.execute("""
                    UPDATE webhook_deliveries
                    SET status='delivered', attempts=?, last_attempt_at=?, last_error=NULL
                    WHERE delivery_id=?
                """, (new_attempts, now_iso, delivery_id))
                conn.execute("""
                    UPDATE webhooks
                    SET delivery_count = delivery_count + 1, last_delivery_at=?
                    WHERE webhook_id=?
                """, (now_iso, delivery["wh_id"]))

            elif new_attempts >= len(RETRY_DELAYS) + 1:
                # Move to Dead Letter Queue
                dlq_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO webhook_dlq
                    (dlq_id, webhook_id, event_type, payload, attempts, last_error, failed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (dlq_id, delivery["webhook_id"], delivery["event_type"],
                      payload_str, new_attempts, last_error, now_iso))
                conn.execute("""
                    UPDATE webhook_deliveries SET status='dead' WHERE delivery_id=?
                """, (delivery_id,))
                conn.execute("""
                    UPDATE webhooks SET failure_count = failure_count + 1
                    WHERE webhook_id=?
                """, (delivery["wh_id"],))
                logger.warning(f"Webhook {delivery_id} moved to DLQ after {new_attempts} attempts")

            else:
                # Schedule next retry
                delay = RETRY_DELAYS[new_attempts - 1] if new_attempts - 1 < len(RETRY_DELAYS) else 300
                conn.execute("""
                    UPDATE webhook_deliveries
                    SET attempts=?, last_attempt_at=?, next_attempt_at=?, last_error=?
                    WHERE delivery_id=?
                """, (new_attempts, now_iso, time.time() + delay, last_error, delivery_id))

        conn.commit()
    finally:
        conn.close()


# Start delivery worker thread
_worker_thread = threading.Thread(target=_webhook_delivery_worker, daemon=True)
_worker_thread.start()


# ── Webhook REST endpoints ─────────────────────────────────────────────────────

class WebhookRegisterRequest(BaseModel):
    url: str = Field(..., description="Your endpoint URL (HTTPS recommended)")
    events: List[str] = Field(..., description="Event types to subscribe to")
    secret: Optional[str] = Field(None, description="HMAC-SHA256 signing secret")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Arbitrary metadata")


@router_ws.post("/v1/webhooks/register", summary="Register a webhook")
def register_webhook(req: WebhookRegisterRequest, request: Request):
    """
    Register a webhook URL for risk event notifications.

    Payload is delivered via HTTP POST with:
    - X-ZARQ-Event: event type
    - X-ZARQ-Signature: sha256=<hmac> (if secret provided)
    - X-ZARQ-Delivery: unique delivery ID
    - X-ZARQ-Attempt: attempt number (1, 2, 3)

    Retry: 3 attempts with exponential backoff (5s, 25s, 125s).
    Failed deliveries stored in dead letter queue.
    """
    # Validate events
    invalid = [e for e in req.events if e not in VALID_EVENTS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event types: {invalid}. Valid: {sorted(VALID_EVENTS)}"
        )

    api_key = request.headers.get("X-API-Key")
    webhook_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(WEBHOOK_DB, timeout=10)
    try:
        conn.execute("""
            INSERT INTO webhooks
            (webhook_id, url, events, secret, metadata, api_key, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
        """, (
            webhook_id,
            req.url,
            json.dumps(req.events),
            req.secret,
            json.dumps(req.metadata) if req.metadata else None,
            api_key,
            now,
        ))
        conn.commit()
    finally:
        conn.close()

    base_url = str(request.base_url).rstrip("/")

    return {
        "data": {
            "webhook_id": webhook_id,
            "url": req.url,
            "events": req.events,
            "status": "active",
            "created_at": now,
            "test_url": f"{base_url}/v1/webhooks/{webhook_id}/test",
        },
        "meta": {"version": "1.0"}
    }


@router_ws.get("/v1/webhooks", summary="List registered webhooks")
def list_webhooks(request: Request):
    """List webhooks registered with the current API key."""
    api_key = request.headers.get("X-API-Key")
    conn = sqlite3.connect(WEBHOOK_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if api_key:
            rows = conn.execute(
                "SELECT * FROM webhooks WHERE api_key = ? ORDER BY created_at DESC",
                (api_key,)
            ).fetchall()
        else:
            rows = []
    finally:
        conn.close()

    webhooks = []
    for row in rows:
        d = dict(row)
        d["events"] = json.loads(d.get("events") or "[]")
        d.pop("secret", None)
        webhooks.append(d)

    return {"data": {"webhooks": webhooks, "count": len(webhooks)}, "meta": {"version": "1.0"}}


@router_ws.delete("/v1/webhooks/{webhook_id}", summary="Delete a webhook")
def delete_webhook(webhook_id: str, request: Request):
    """Delete a webhook by ID."""
    conn = sqlite3.connect(WEBHOOK_DB, timeout=10)
    try:
        conn.execute("DELETE FROM webhooks WHERE webhook_id = ?", (webhook_id,))
        conn.commit()
    finally:
        conn.close()
    return JSONResponse(status_code=204, content=None)


@router_ws.post("/v1/webhooks/{webhook_id}/test", summary="Send test event to webhook")
def test_webhook(webhook_id: str):
    """Send a test event to verify your webhook endpoint is reachable."""
    conn = sqlite3.connect(WEBHOOK_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        wh = conn.execute(
            "SELECT * FROM webhooks WHERE webhook_id = ?", (webhook_id,)
        ).fetchone()
    finally:
        conn.close()

    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_payload = json.dumps({
        "event": "test",
        "data": {
            "message": "This is a test event from ZARQ",
            "webhook_id": webhook_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    })

    headers = {
        "Content-Type": "application/json",
        "X-ZARQ-Event": "test",
        "X-ZARQ-Delivery": str(uuid.uuid4()),
        "X-ZARQ-Attempt": "1",
    }
    if wh["secret"]:
        sig = _sign_payload(test_payload.encode(), wh["secret"])
        headers["X-ZARQ-Signature"] = f"sha256={sig}"

    try:
        resp = httpx.post(wh["url"], content=test_payload, headers=headers, timeout=10)
        return {
            "data": {
                "success": resp.is_success,
                "status_code": resp.status_code,
                "url": wh["url"],
            },
            "meta": {"version": "1.0"}
        }
    except Exception as e:
        return {
            "data": {"success": False, "error": str(e), "url": wh["url"]},
            "meta": {"version": "1.0"}
        }


@router_ws.get("/v1/webhooks/dlq", summary="Dead letter queue — failed deliveries")
def get_dlq(request: Request, limit: int = 50):
    """View failed webhook deliveries (dead letter queue)."""
    api_key = request.headers.get("X-API-Key")
    conn = sqlite3.connect(WEBHOOK_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM webhook_dlq ORDER BY failed_at DESC LIMIT ?",
            (min(limit, 200),)
        ).fetchall()
    finally:
        conn.close()

    items = []
    for row in rows:
        d = dict(row)
        try:
            d["payload"] = json.loads(d.get("payload", "{}"))
        except Exception:
            pass
        items.append(d)

    return {"data": {"items": items, "count": len(items)}, "meta": {"version": "1.0"}}


# ── Stats endpoint ─────────────────────────────────────────────────────────────

@router_ws.get("/v1/stream/status", summary="WebSocket stream status")
def stream_status():
    """Current subscriber counts per stream channel."""
    return {
        "data": {
            "channels": {
                "signals": manager.subscriber_count("signals"),
                "yield-traps": manager.subscriber_count("yield-traps"),
                "agents": manager.subscriber_count("agents"),
            },
            "total_subscribers": sum(
                manager.subscriber_count(c)
                for c in ["signals", "yield-traps", "agents"]
            )
        },
        "meta": {"version": "1.0"}
    }


# ── Mount helper ───────────────────────────────────────────────────────────────

def mount_websocket_webhooks(app):
    """Mount WebSocket + webhook routes. Call from discovery.py."""
    app.include_router(router_ws)
