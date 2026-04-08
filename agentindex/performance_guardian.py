"""
Performance Guardian — Autonomous performance monitor
======================================================
Detects, diagnoses, and fixes performance problems automatically.
Runs every 2 minutes via cron.

Actions:
- Monitors response times and connection count
- Diagnoses: bot floods, heavy processes, connection overload, high load
- Fixes: blocks aggressive IPs, logs heavy processes
- Cleans expired blocks automatically
"""

import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

LOG_FILE = Path.home() / "agentindex" / "logs" / "performance_guardian.log"
ANALYTICS_DB = str(Path.home() / "agentindex" / "logs" / "analytics.db")
BLOCK_FILE = str(Path.home() / "agentindex" / "data" / "blocked_ips.json")

# Thresholds
P95_ALERT_MS = 2000
P95_CRITICAL_MS = 5000
MAX_CONNECTIONS = 150
MAX_RPM_PER_BOT = 3000  # requests per 5 minutes (raised from 600)

# NEVER block these IPs — our own + essential bots
SAFE_IPS = {
    "194.132.208.188",  # Our office IP
    "127.0.0.1", "::1", "localhost",  # Localhost
}
# Google IP prefixes — NEVER block
SAFE_IP_PREFIXES = (
    "66.249.",      # Googlebot
    "64.233.",      # Google
    "72.14.",       # Google
    "74.125.",      # Google
    "209.85.",      # Google
    "216.239.",     # Google
    "40.77.167.",   # Bingbot
    "40.77.188.",   # Bingbot
    "52.167.144.",  # Bingbot
    "207.46.13.",   # Bingbot
    "157.55.39.",   # Bingbot
)
# NEVER block these user agents
SAFE_UA_PATTERNS = [
    "googlebot", "bingbot", "gptbot", "chatgpt-user", "claudebot",
    "perplexitybot", "applebot", "curl",  # curl = our own monitoring
    "yandexbot", "duckduckbot", "slurp",  # other search engines
]


def log(msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [guardian] {msg}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except Exception:
        pass
    print(line.strip())


def check_health():
    """Measure response time and connection count."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{time_total}",
             "--max-time", "8", "http://localhost:8000/v1/preflight?target=test"],
            capture_output=True, text=True, timeout=10
        )
        rt_ms = float(result.stdout.strip()) * 1000

        conns_result = subprocess.run(
            ["lsof", "-i", ":8000"], capture_output=True, text=True, timeout=5
        )
        conn_count = max(0, len(conns_result.stdout.strip().split("\n")) - 1)

        load = os.getloadavg()

        return {"rt_ms": rt_ms, "connections": conn_count, "load_1m": load[0]}
    except Exception as e:
        log(f"Health check error: {e}")
        return None


def diagnose():
    """Find root causes of slow performance."""
    causes = []

    # 1. Bot flood from analytics DB
    try:
        db = sqlite3.connect(ANALYTICS_DB, timeout=3)
        rows = db.execute("""
            SELECT ip, substr(user_agent, 1, 80) as ua, COUNT(*) as hits
            FROM requests
            WHERE ts > strftime('%Y-%m-%dT%H:%M:%f', 'now', '-5 minutes')
            GROUP BY ip
            ORDER BY hits DESC
            LIMIT 10
        """).fetchall()
        db.close()

        for ip, ua, hits in rows:
            if hits > MAX_RPM_PER_BOT:
                causes.append({
                    "type": "bot_flood", "ip": ip,
                    "user_agent": ua or "unknown", "hits_5m": hits,
                    "severity": "critical" if hits > 2000 else "high"
                })
    except Exception as e:
        log(f"DB diagnosis error: {e}")

    # 2. Connection overload
    try:
        result = subprocess.run(["lsof", "-i", ":8000"], capture_output=True, text=True, timeout=5)
        conn_count = max(0, len(result.stdout.strip().split("\n")) - 1)
        if conn_count > MAX_CONNECTIONS:
            causes.append({"type": "connection_overload", "connections": conn_count, "severity": "critical"})
    except Exception:
        pass

    # 3. High system load
    try:
        load = os.getloadavg()
        if load[0] > 6.0:
            causes.append({"type": "high_load", "load_1m": load[0], "load_5m": load[1], "severity": "high"})
    except Exception:
        pass

    # 4. Heavy Python/Postgres processes
    try:
        result = subprocess.run(["ps", "aux", "-r"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split("\n")[:15]:
            parts = line.split(None, 10)
            if len(parts) > 10:
                try:
                    cpu = float(parts[2])
                except ValueError:
                    continue
                cmd = parts[10]
                if cpu > 40 and ("python" in cmd.lower() or "postgres" in cmd.lower()):
                    # Skip known essential processes
                    if any(x in cmd.lower() for x in ["uvicorn", "cloudflared", "claude"]):
                        continue
                    causes.append({
                        "type": "heavy_process", "process": cmd[:100],
                        "cpu_pct": cpu, "pid": parts[1], "severity": "medium"
                    })
    except Exception:
        pass

    return causes


def fix(causes):
    """Apply automatic fixes."""
    actions = []

    for cause in causes:
        if cause["type"] == "bot_flood":
            ip = cause["ip"]
            ua = cause["user_agent"]
            hits = cause["hits_5m"]

            # NEVER block safe IPs (exact match or prefix match)
            if ip in SAFE_IPS or ip.startswith(SAFE_IP_PREFIXES):
                log(f"SKIPPING safe IP: {ip} ({hits} hits/5m) — protected")
                continue

            # NEVER block safe user agents (search bots, AI bots, our monitoring)
            ua_lower = ua.lower()
            if any(pattern in ua_lower for pattern in SAFE_UA_PATTERNS):
                log(f"SKIPPING safe UA: {ua[:50]} from {ip} ({hits} hits/5m)")
                actions.append(f"Safe bot {ua[:30]} — not blocking")
                continue

            # Check if it's a known bot handled by rate limiter
            known_bots = ["meta-externalagent", "meta-webindexer", "semrushbot", "mj12bot",
                         "dataforseobot", "amazonbot", "yandexbot"]
            is_known = any(b in ua_lower for b in known_bots)

            if is_known:
                log(f"Known bot flood: {ua[:50]} from {ip} ({hits} hits/5m) — rate limiter active")
                actions.append(f"Known bot {ua[:30]} — rate limiter handling")
            else:
                # Block unknown aggressive IP
                log(f"BLOCKING unknown aggressive IP: {ip} ({ua[:50]}) — {hits} hits/5m")
                try:
                    blocked = json.loads(open(BLOCK_FILE).read()) if os.path.exists(BLOCK_FILE) else {}
                    blocked[ip] = {
                        "reason": f"Auto-blocked: {hits} hits in 5 min",
                        "blocked_at": datetime.utcnow().isoformat(),
                        "user_agent": ua[:200],
                        "expires": time.time() + 3600  # 1 hour
                    }
                    with open(BLOCK_FILE, "w") as f:
                        json.dump(blocked, f, indent=2)
                    actions.append(f"Blocked IP {ip} for 1h ({hits} hits/5m)")
                except Exception as e:
                    log(f"Failed to block IP {ip}: {e}")

        elif cause["type"] == "connection_overload":
            log(f"Connection overload: {cause['connections']} connections")
            actions.append(f"Connection overload: {cause['connections']}")

        elif cause["type"] == "high_load":
            log(f"High load: {cause['load_1m']:.1f}")
            actions.append(f"High load: {cause['load_1m']:.1f}")

        elif cause["type"] == "heavy_process":
            log(f"Heavy process: PID {cause['pid']} {cause['process'][:60]} ({cause['cpu_pct']}% CPU)")
            actions.append(f"Flagged PID {cause['pid']} ({cause['cpu_pct']}% CPU)")

    return actions


def clean_expired_blocks():
    """Remove expired IP blocks."""
    if not os.path.exists(BLOCK_FILE):
        return
    try:
        blocked = json.loads(open(BLOCK_FILE).read())
        now = time.time()
        expired = [ip for ip, info in blocked.items() if info.get("expires", 0) < now]
        if expired:
            for ip in expired:
                del blocked[ip]
                log(f"Unblocked expired IP: {ip}")
            with open(BLOCK_FILE, "w") as f:
                json.dump(blocked, f, indent=2)
    except Exception:
        pass


def main():
    clean_expired_blocks()

    health = check_health()
    if not health:
        return

    rt = health["rt_ms"]
    conns = health["connections"]
    load = health["load_1m"]

    if rt < P95_ALERT_MS and conns < MAX_CONNECTIONS and load < 6.0:
        return  # All good — stay silent

    log(f"ALERT: rt={rt:.0f}ms conns={conns} load={load:.1f}")

    causes = diagnose()
    if causes:
        log(f"Diagnosed {len(causes)} cause(s): {[c['type'] for c in causes]}")
        actions = fix(causes)
        if actions:
            log(f"Actions: {actions}")
    else:
        log("No specific cause identified — transient spike")


if __name__ == "__main__":
    main()
