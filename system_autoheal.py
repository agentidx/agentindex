#!/usr/bin/env python3
"""
NERQ System Auto-Healer — "Buzz"
==================================
Runs every 5 minutes via cron. Detects and fixes known failure modes.
Logs all actions. Writes status to healthcheck.db for dashboard.

Self-healing actions:
  1. Kill PostgreSQL queries stuck >5 min
  2. Kill idle-in-transaction >3 min
  3. Restart API if port 8000 not responding
  4. Restart parser if suspended (state T) or missing
  5. Kill duplicate orchestrator instances
  6. Kill hung cron jobs (trust_score, snapshot) >60 min

Philosophy: Fix what we know, warn about what we don't.
"""

import os
import sys
import json
import time
import signal
import sqlite3
import subprocess
from datetime import datetime

DB_PATH = os.path.expanduser("~/agentindex/logs/healthcheck.db")

# ── Circuit Breaker — stop restart storms ──────────────────
_FAILURE_STATE = os.path.expanduser("~/agentindex/logs/autoheal_failures.json")


def _load_failures():
    try:
        if os.path.exists(_FAILURE_STATE):
            with open(_FAILURE_STATE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_failures(failures):
    try:
        with open(_FAILURE_STATE, 'w') as f:
            json.dump(failures, f, indent=2)
    except Exception:
        pass


def should_restart(service_name, max_consecutive=5, backoff_minutes=30):
    """Circuit breaker: stop restarting after N consecutive failures."""
    failures = _load_failures()
    svc = failures.get(service_name, {"count": 0, "disabled_until": 0})
    now = time.time()

    if svc.get("disabled_until", 0) > now:
        remaining = int((svc["disabled_until"] - now) / 60)
        log(f"CIRCUIT BREAKER: {service_name} disabled for {remaining}min more", "WARN")
        return False

    if svc.get("count", 0) >= max_consecutive:
        svc["disabled_until"] = now + (backoff_minutes * 60)
        svc["count"] = 0
        failures[service_name] = svc
        _save_failures(failures)
        log(f"CIRCUIT BREAKER TRIPPED: {service_name} failed {max_consecutive}x — disabled {backoff_minutes}min", "WARN")
        return False

    return True


def record_result(service_name, success):
    """Record restart result for circuit breaker.
    
    A restart is only counted as 'success' if the previous restart happened
    more than 10 minutes ago. This prevents the counter from being reset
    during a restart oscillation (where each restart briefly succeeds at
    binding to port, then crashes again within minutes). Before this change,
    the 2026-04-09 incident saw 7+ restarts in 30 minutes without the
    circuit breaker ever tripping, because every other restart reported
    'Healthy after restart: True' and reset the counter to 0.
    """
    failures = _load_failures()
    svc = failures.get(service_name, {"count": 0, "disabled_until": 0})
    now = time.time()
    
    if success:
        last_restart = svc.get("last", 0)
        if last_restart > 0 and (now - last_restart) < 600:
            # Previous restart was <10 min ago — we're in an oscillation pattern.
            # Count this as failure for circuit-breaker purposes even though
            # the restart itself succeeded.
            svc["count"] = svc.get("count", 0) + 1
            log(f"Circuit breaker: {service_name} restarted <10min ago, counting as oscillation ({svc['count']}/5)", "WARN")
        else:
            svc["count"] = 0
    else:
        svc["count"] = svc.get("count", 0) + 1
    
    svc["last"] = now
    failures[service_name] = svc
    _save_failures(failures)


# ── Socket Health Monitor ──────────────────────────────────

def check_socket_health():
    """Early warning for port exhaustion. Returns False if system is under socket pressure."""
    try:
        result = subprocess.run(["netstat", "-an"], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split('\n')

        time_wait = sum(1 for l in lines if 'TIME_WAIT' in l)
        close_wait = sum(1 for l in lines if 'CLOSE_WAIT' in l)
        established = sum(1 for l in lines if 'ESTABLISHED' in l)

        if time_wait > 500 or close_wait > 100:
            log(f"SOCKET WARNING: TIME_WAIT={time_wait} CLOSE_WAIT={close_wait} ESTABLISHED={established}", "WARN")

        if time_wait > 1000 or close_wait > 300:
            log(f"SOCKET CRITICAL: TIME_WAIT={time_wait} CLOSE_WAIT={close_wait} — skipping restarts", "WARN")
            return False  # Signal: don't restart anything this cycle

        return True
    except Exception:
        return True
PSQL = "/opt/homebrew/Cellar/postgresql@16/16.11_1/bin/psql"

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [BUZZ/{level}] {msg}")

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return None, -1
    except Exception as e:
        return str(e), -1

def count_procs(grep_str):
    out, _ = run(f"ps aux | grep '{grep_str}' | grep -v grep | wc -l")
    return int(out.strip()) if out else 0

def get_pids(grep_str):
    out, _ = run(f"ps aux | grep '{grep_str}' | grep -v grep | awk '{{print $2}}'")
    return [int(p) for p in out.strip().split('\n') if p.strip()] if out else []

def get_proc_state(grep_str):
    out, _ = run(f"ps aux | grep '{grep_str}' | grep -v grep | awk '{{print $8}}'")
    return out.strip() if out else ""

def check_port(port):
    out, _ = run(f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' http://localhost:{port}/")
    return out if out else "000"

def check_api_health():
    """Deep health check — actually tests a real endpoint, not just port.
    
    Timeout is 20s (not 8s) because uvicorn cold-start latency on /v1/health
    after a restart can reach 15s — shorter timeouts created a feedback loop
    where every restart failed the next check, triggering another restart.
    See incident 2026-04-09 09:51-10:24 (7+ restarts in 30 minutes).
    A genuinely dead uvicorn returns connection refused immediately, not a
    timeout, so this longer timeout only protects against slow-but-working.
    """
    out, _ = run("curl -s -m 20 http://localhost:8000/v1/health", timeout=25)
    if not out:
        return False
    try:
        import json as _json
        data = _json.loads(out)
        return data.get("status") == "ok"
    except:
        return False

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS autoheal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            result TEXT
        )
    """)
    conn.execute("DELETE FROM autoheal_log WHERE timestamp < datetime('now', '-30 days')")
    conn.commit()
    return conn

def log_action(conn, action, detail="", result="OK"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO autoheal_log (timestamp, action, detail, result) VALUES (?, ?, ?, ?)",
        (ts, action, detail, result)
    )
    conn.commit()
    log(f"ACTION: {action} — {detail} → {result}", "HEAL")


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"  # qwen3:8b uses thinking mode which complicates parsing

# Level 1: safe auto-execute actions available to LLM diagnoser
#
# NOTE: restart_api was removed 2026-04-09 because the stop+start command
# sequence has a race condition with launchd KeepAlive=true — the service
# respawns between stop and start, causing "address already in use" errors
# that LLM then interprets as root cause and recommends another restart.
# This created a double-restart per heal cycle (main-path + LLM-path) that
# was the core mechanic of the 2026-04-09 restart loop incident.
#
# The main heal() path still restarts uvicorn when needed using the correct
# method: kill -9 + launchctl kickstart. That path has its own circuit
# breaker and uses should_restart("api", ...). If LLM recommends restart_api
# now, the action_name won't match SAFE_ACTIONS and it will be logged as a
# Level 2 "suggestion only" — recorded but not executed.
SAFE_ACTIONS = {
    "restart_postgresql": lambda: run("brew services restart postgresql@16", timeout=30),
    "clear_redis_cache": lambda: run("/opt/homebrew/bin/redis-cli FLUSHDB", timeout=5),
    "kill_idle_connections": lambda: run(f"""{PSQL} -d agentindex -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='agentindex' AND state='idle' AND query_start < now()-interval '5 minutes' AND pid != pg_backend_pid();" """, timeout=10),
}


def _collect_error_context():
    """Collect recent error logs for LLM analysis."""
    context_parts = []

    # Recent API error log
    err_log = os.path.expanduser("~/agentindex/logs/api_error.log")
    if os.path.exists(err_log):
        try:
            with open(err_log, 'r') as f:
                f.seek(max(0, os.path.getsize(err_log) - 8000))
                context_parts.append("=== API Error Log (last ~8KB) ===\n" + f.read()[-4000:])
        except Exception:
            pass

    # Recent autoheal log
    ah_log = os.path.expanduser("~/agentindex/logs/autoheal.log")
    if os.path.exists(ah_log):
        try:
            with open(ah_log, 'r') as f:
                f.seek(max(0, os.path.getsize(ah_log) - 4000))
                context_parts.append("=== Autoheal Log (recent) ===\n" + f.read()[-2000:])
        except Exception:
            pass

    # PG connection count
    out, _ = run(f"""{PSQL} -d agentindex -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='agentindex';" """)
    if out:
        context_parts.append(f"=== PG Connections: {out.strip()} ===")

    return "\n\n".join(context_parts)


def _call_ollama(prompt, timeout=30):
    """Call qwen3:8b via Ollama. Returns response text or None."""
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 300}
    }).encode()

    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except (urllib.error.URLError, TimeoutError, Exception) as e:
        log(f"Ollama call failed: {e}", "WARN")
        return None


def llm_diagnose(conn):
    """Use qwen3:8b to diagnose issues and suggest/execute fixes."""
    context = _collect_error_context()
    if not context or len(context) < 50:
        return None

    prompt = f"""You are Buzz, a system auto-healer for a FastAPI server (ZARQ/Nerq).
Analyze these recent error logs and give:
1. ROOT CAUSE (1 sentence)
2. RECOMMENDED ACTION — pick ONE from: restart_postgresql, clear_redis_cache, kill_idle_connections, none
3. EXPLANATION (1 sentence)

Format your response EXACTLY as:
ROOT_CAUSE: <cause>
ACTION: <action_name>
EXPLANATION: <why>

Error context:
{context[:3000]}"""

    response = _call_ollama(prompt)
    if not response:
        return None

    log(f"LLM raw response: {response[:300]}", "INTEL")

    # Parse recommended action
    action_name = None
    for line in response.split('\n'):
        if line.strip().startswith('ACTION:'):
            action_name = line.split(':', 1)[1].strip().lower()
            break

    # Execute Level 1 (safe) actions only — with circuit breaker
    if action_name and action_name in SAFE_ACTIONS:
        svc_key = f"llm_{action_name}"
        if not should_restart(svc_key, max_consecutive=3, backoff_minutes=30):
            log(f"LLM action {action_name} blocked by circuit breaker", "WARN")
        else:
            log(f"LLM recommends Level 1 action: {action_name} — executing", "INTEL")
            result, rc = SAFE_ACTIONS[action_name]()
            log_action(conn, svc_key, f"LLM-recommended: {response[:100]}", f"rc={rc}")
            record_result(svc_key, rc == 0 if isinstance(rc, int) else True)
    elif action_name and action_name != "none":
        # Level 2: log only, don't execute
        log(f"LLM recommends Level 2 action (not auto-executing): {action_name}", "INTEL")
        log_action(conn, "llm_suggestion_only", f"{action_name}: {response[:150]}", "logged_only")

    return response


def heal():
    conn = init_db()
    actions_taken = 0

    # ── 0. Socket health — abort if system under pressure ──
    if not check_socket_health():
        log("Socket pressure detected — skipping restart cycle to let connections drain", "WARN")
        conn.close()
        return

    # ── 1. PostgreSQL: kill stuck queries >5 min ──
    out, _ = run(f"""{PSQL} -d agentindex -t -A -c "
        SELECT pid, left(query, 60), extract(epoch from now()-query_start)::int as secs
        FROM pg_stat_activity
        WHERE datname='agentindex' AND state = 'active'
          AND query_start < now() - interval '5 minutes'
          AND pid != pg_backend_pid()
        ORDER BY query_start;
    " """)
    if out:
        for line in out.strip().split('\n'):
            if '|' not in line:
                continue
            parts = line.split('|')
            pid = parts[0].strip()
            query = parts[1].strip() if len(parts) > 1 else "?"
            secs = parts[2].strip() if len(parts) > 2 else "?"
            log(f"Killing stuck query PID {pid} ({secs}s): {query[:50]}", "HEAL")
            run(f"""{PSQL} -d agentindex -c "SELECT pg_terminate_backend({pid});" """)
            log_action(conn, "kill_stuck_query", f"PID {pid}, {secs}s: {query[:50]}")
            actions_taken += 1

    # ── 2. PostgreSQL: kill idle-in-transaction >3 min ──
    out, _ = run(f"""{PSQL} -d agentindex -t -A -c "
        SELECT pid, extract(epoch from now()-query_start)::int as secs
        FROM pg_stat_activity
        WHERE datname='agentindex' AND state = 'idle in transaction'
          AND query_start < now() - interval '3 minutes'
          AND pid != pg_backend_pid();
    " """)
    if out:
        for line in out.strip().split('\n'):
            if '|' not in line:
                continue
            pid = line.split('|')[0].strip()
            secs = line.split('|')[1].strip() if '|' in line else "?"
            log(f"Killing idle-in-transaction PID {pid} ({secs}s)", "HEAL")
            run(f"""{PSQL} -d agentindex -c "SELECT pg_terminate_backend({pid});" """)
            log_action(conn, "kill_idle_tx", f"PID {pid}, {secs}s")
            actions_taken += 1

    # ── 2b. PostgreSQL: kill ZOMBIE backends (idle but >50% CPU) ──
    # ROOT CAUSE of recurring slowdowns: PG processes that finished queries
    # but hold massive memory allocations, consuming 50-99% CPU.
    # Also check if pg_dump is running — if so, skip ALL zombie killing this cycle
    _dump_running, _ = run("pgrep -f pg_dump", timeout=3)
    _skip_zombies = bool(_dump_running and _dump_running.strip())
    if _skip_zombies:
        log("pg_dump running — skipping zombie PG backend check this cycle", "INFO")

    out, _ = run("ps aux | grep 'postgres.*agentindex' | grep -v grep", timeout=5)
    if out and not _skip_zombies:
        for line in out.strip().split('\n'):
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                zpid = parts[1]
                zcpu = float(parts[2])
            except (ValueError, IndexError):
                continue
            if zcpu > 50:
                # Check state + query — NEVER kill backup/dump processes
                zstate_out, _ = run(f"""{PSQL} -d agentindex -t -A -c "SELECT state || '|' || LEFT(query,30) || '|' || COALESCE(application_name,'') FROM pg_stat_activity WHERE pid = {zpid};" """, timeout=3)
                zinfo = zstate_out.strip() if zstate_out else ""
                zstate = zinfo.split('|')[0] if '|' in zinfo else zinfo
                zquery = zinfo.split('|')[1] if '|' in zinfo and len(zinfo.split('|')) > 1 else ""
                zapp = zinfo.split('|')[2] if '|' in zinfo and len(zinfo.split('|')) > 2 else ""
                # Skip backup/dump processes
                if 'COPY' in zquery or 'pg_dump' in zapp or 'backup' in zapp.lower() or 'rescore' in zapp.lower() or 'enricher' in zapp.lower():
                    log(f"Skipping PG PID {zpid} — backup/dump in progress (app={zapp})", "INFO")
                    continue
                if zstate in ('idle', ''):
                    log(f"Zombie PG backend: PID {zpid}, CPU {zcpu}%, state='{zstate}' — terminating", "HEAL")
                    run(f"""{PSQL} -d agentindex -c "SELECT pg_terminate_backend({zpid});" """)
                    log_action(conn, "kill_zombie_pg_backend", f"PID {zpid}, CPU {zcpu}%")
                    actions_taken += 1

    # ── 3. PostgreSQL: kill lock waiters >3 min ──
    out, _ = run(f"""{PSQL} -d agentindex -t -A -c "
        SELECT count(*) FROM pg_stat_activity
        WHERE datname='agentindex' AND wait_event_type = 'Lock'
          AND query_start < now() - interval '3 minutes';
    " """)
    if out and int(out.strip() or 0) > 3:
        log(f"Lock storm detected ({out.strip()} waiters), killing all lock waiters", "HEAL")
        run(f"""{PSQL} -d agentindex -c "
            SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE datname='agentindex' AND wait_event_type = 'Lock'
              AND query_start < now() - interval '3 minutes'
              AND pid != pg_backend_pid();
        " """)
        log_action(conn, "kill_lock_storm", f"{out.strip()} waiters killed")
        actions_taken += 1

    # ── 4. API: restart if not responding or hung ──
    api_healthy = check_api_health()
    check_yield_api()
    check_yield_crawler()
    if not api_healthy:
        if not should_restart("api", max_consecutive=5, backoff_minutes=30):
            log("API restart skipped by circuit breaker", "WARN")
        else:
            api_status = check_port(8000)
            log(f"API failed deep health check (port status: {api_status}), restarting", "HEAL")
            pids = get_pids("discovery:app")
            for pid in pids:
                run(f"kill -9 {pid}")
            time.sleep(2)
            run(f"launchctl kickstart gui/$(id -u)/com.nerq.api 2>/dev/null")
            time.sleep(5)
            new_healthy = check_api_health()
            log_action(conn, "restart_api", f"Old PIDs: {pids}, port was {api_status}", f"Healthy after restart: {new_healthy}")
            record_result("api", new_healthy)
            actions_taken += 1

    # ── 5. Parser: restart if suspended or missing ──
    parser_count = count_procs("run_parser_loop")
    if parser_count == 0:
        if not should_restart("parser", max_consecutive=5, backoff_minutes=30):
            log("Parser restart skipped by circuit breaker", "WARN")
        else:
            log("Parser not running, triggering LaunchAgent restart", "HEAL")
            run("launchctl kickstart gui/$(id -u)/com.agentindex.parser")
            time.sleep(3)
            new_count = count_procs("run_parser_loop")
            log_action(conn, "restart_parser", "Was missing")
            record_result("parser", new_count > 0)
            actions_taken += 1
    elif parser_count > 0:
        state = get_proc_state("run_parser_loop")
        if "T" in state:
            log("Parser is SUSPENDED, killing to trigger restart", "HEAL")
            pids = get_pids("run_parser_loop")
            for pid in pids:
                run(f"kill -9 {pid}")
            time.sleep(3)
            log_action(conn, "restart_parser", f"Was suspended (state T), killed PIDs: {pids}")
            actions_taken += 1

    # ── 6. Master watchdog: fix missing or duplicates ──
    # Note: The old "com.agentindex.orchestrator" label was wrong — correct label
    # is com.nerq.master-watchdog. Process grep matches "master_watchdog".
    orch_count = count_procs("master_watchdog")
    if orch_count == 0:
        if not should_restart("master_watchdog", max_consecutive=5, backoff_minutes=60):
            log("Master watchdog restart skipped by circuit breaker", "WARN")
        else:
            log("Master watchdog not running, attempting restart", "HEAL")
            out, rc = run("launchctl kickstart gui/$(id -u)/com.nerq.master-watchdog 2>&1")
            if rc != 0 or "Could not find" in (out or ""):
                log("kickstart failed, trying launchctl load", "HEAL")
                run("launchctl load ~/Library/LaunchAgents/com.nerq.master-watchdog.plist 2>&1")
            time.sleep(3)
            new_count = count_procs("master_watchdog")
            log_action(conn, "restart_master_watchdog", f"Was missing, now {new_count} running")
            record_result("master_watchdog", new_count > 0)
            actions_taken += 1
    elif orch_count > 1:
        pids = get_pids("master_watchdog")
        log(f"Multiple master watchdogs ({orch_count}), killing extras", "HEAL")
        for pid in sorted(pids)[1:]:
            run(f"kill -9 {pid}")
            log_action(conn, "kill_dup_master_watchdog", f"PID {pid}")
        actions_taken += 1

    # ── 7. Hung cron jobs (trust_score, snapshot) >60 min ──
    for proc_name in ["compute_trust_score", "trust_snapshot_export"]:
        pids = get_pids(proc_name)
        if pids:
            # Check if running >60 min
            for pid in pids:
                elapsed, _ = run(f"ps -o etime= -p {pid}")
                if elapsed:
                    elapsed = elapsed.strip()
                    # Parse elapsed time (format: [[dd-]hh:]mm:ss)
                    parts = elapsed.replace('-', ':').split(':')
                    try:
                        if len(parts) >= 3:
                            mins = int(parts[-3]) * 60 + int(parts[-2]) if len(parts) == 4 else int(parts[-3])
                        else:
                            mins = int(parts[0])
                        if mins > 60:
                            log(f"Killing hung {proc_name} (PID {pid}, {elapsed})", "HEAL")
                            run(f"kill -9 {pid}")
                            log_action(conn, f"kill_hung_{proc_name}", f"PID {pid}, elapsed {elapsed}")
                            actions_taken += 1
                    except:
                        pass

    # ── 8. Connection count check ──
    out, _ = run(f"""{PSQL} -d agentindex -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='agentindex';" """)
    if out and int(out.strip() or 0) > 40:
        log(f"High connection count: {out.strip()}, killing idle connections", "HEAL")
        run(f"""{PSQL} -d agentindex -c "
            SELECT pg_terminate_backend(pid) FROM pg_stat_activity
            WHERE datname='agentindex' AND state = 'idle'
              AND query_start < now() - interval '10 minutes'
              AND pid != pg_backend_pid();
        " """)
        log_action(conn, "cleanup_idle_connections", f"Count was {out.strip()}")
        actions_taken += 1

    # ── 9. Redis: restart if down ──
    redis_ok, _ = run("/opt/homebrew/bin/redis-cli ping")
    if not redis_ok or redis_ok.strip() != "PONG":
        if not should_restart("redis", max_consecutive=5, backoff_minutes=15):
            log("Redis restart skipped by circuit breaker", "WARN")
        else:
            log("Redis not responding, restarting", "HEAL")
            run("/opt/homebrew/bin/brew services restart redis 2>/dev/null")
            time.sleep(3)
            redis_ok2, _ = run("/opt/homebrew/bin/redis-cli ping")
            success = redis_ok2 and redis_ok2.strip() == "PONG"
            log_action(conn, "restart_redis", f"Was down, now {redis_ok2}")
            record_result("redis", success)
            actions_taken += 1

    # ── 10. LaunchAgents: reload if unloaded ──
    agents_map = {
        "dashboard": ("agentindex.dashboard", "com.agentindex.dashboard"),
        "mcp_sse": ("mcp_sse_server", "com.agentindex.mcp-sse"),
    }
    for name, (grep_str, label) in agents_map.items():
        if count_procs(grep_str) == 0:
            if not should_restart(name, max_consecutive=5, backoff_minutes=30):
                log(f"{name} restart skipped by circuit breaker", "WARN")
                continue
            log(f"{name} not running, trying kickstart then load", "HEAL")
            out, rc = run(f"launchctl kickstart gui/$(id -u)/{label} 2>&1")
            if rc != 0 or "Could not find" in (out or ""):
                run(f"launchctl load ~/Library/LaunchAgents/{label}.plist 2>&1")
            time.sleep(3)
            new_count = count_procs(grep_str)
            log_action(conn, f"restart_{name}", f"Was missing, now {new_count}")
            record_result(name, new_count > 0)
            actions_taken += 1

    # ── 11. Analytics retention (daily at 03:00-03:05 only) ──
    _h = datetime.now().hour
    _m = datetime.now().minute
    if _h == 3 and _m < 6:
        try:
            import sqlite3 as _sqlite3_ret
            _adb = os.path.expanduser("~/agentindex/logs/analytics.db")
            if os.path.exists(_adb):
                _db_size_gb = os.path.getsize(_adb) / (1024**3)
                _ret_days = 30 if _db_size_gb > 5 else 45 if _db_size_gb > 3 else 60
                _rc = _sqlite3_ret.connect(_adb)
                _rc.execute("PRAGMA auto_vacuum = INCREMENTAL;")
                _rc.execute("PRAGMA journal_mode = WAL;")
                _del = _rc.execute(f"DELETE FROM requests WHERE ts < datetime('now', '-{_ret_days} days')").rowcount
                if _del > 0:
                    _rc.execute("PRAGMA incremental_vacuum(1000);")
                    log(f"Analytics retention: deleted {_del} rows >{_ret_days} days (DB {_db_size_gb:.1f}GB)", "INFO")
                    log_action(conn, "analytics_retention", f"Deleted {_del} rows, retention={_ret_days}d")
                    actions_taken += 1
                _rc.commit()
                _rc.close()
        except Exception as _ret_e:
            log(f"Analytics retention error: {_ret_e}", "WARN")

    # ── 11b. check_events.db retention (90 days, at 03:00-03:05) ──
    if _h == 3 and _m < 6:
        _check_db = os.path.expanduser("~/agentindex/logs/check_events.db")
        if os.path.exists(_check_db):
            try:
                _ce = sqlite3.connect(_check_db, timeout=3)
                _ce_del = _ce.execute("DELETE FROM check_events WHERE ts < datetime('now', '-90 days')").rowcount
                if _ce_del > 0:
                    _ce.execute("PRAGMA incremental_vacuum;")
                    log(f"check_events retention: deleted {_ce_del} rows >90 days", "INFO")
                    actions_taken += 1
                _ce.commit()
                _ce.close()
            except Exception as _ce_e:
                log(f"check_events retention error: {_ce_e}", "WARN")

    # ── 12. Log rotation (daily at 03:00-03:05 only) ──
    if _h == 3 and _m < 6:
        import glob as _glob_rot
        for _lf in _glob_rot.glob(os.path.expanduser("~/agentindex/logs/*.log")):
            if os.path.getsize(_lf) > 100 * 1024 * 1024:  # >100MB
                log(f"Rotating large log: {os.path.basename(_lf)} ({os.path.getsize(_lf)//1024//1024}MB)", "INFO")
                os.rename(_lf, _lf + f".{datetime.now().strftime('%Y%m%d')}")
                log_action(conn, "rotate_log", os.path.basename(_lf))
                actions_taken += 1

    # ── 13. LLM Diagnostics (qwen3:8b via Ollama) ──
    if actions_taken > 0:
        try:
            diagnosis = llm_diagnose(conn)
            if diagnosis:
                log(f"LLM diagnosis: {diagnosis[:200]}", "INTEL")
        except Exception as e:
            log(f"LLM diagnostics skipped: {e}", "WARN")

    # ── Summary ──
    if actions_taken == 0:
        log("All clear — no actions needed")
    else:
        log(f"Took {actions_taken} healing action(s)")

    conn.close()
    return actions_taken



def check_port_path(port, path):
    out, _ = run(f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' http://localhost:{port}{path}")
    return out if out else "000"

def check_yield_api():
    # NOTE: yield endpoints can be slow (10-15s cold start after uvicorn restart)
    # but slowness is NOT a reason to restart the API. check_port_path has a 5s
    # curl timeout, which previously returned 000 for a slow-but-working endpoint
    # and triggered a restart_api action — creating a feedback loop where each
    # restart caused the next cold-start to fail the check, causing another
    # restart. Background: restart loop incident 2026-04-09 09:51-10:24 (at
    # least 7 restarts in 30 minutes). Fixed by making yield check observe-only.
    # The real liveness check is check_api_health() against /v1/health with 8s
    # timeout — that one can still trigger restart.
    for ep in ["/v1/yield/overview", "/v1/yield/insights?limit=1"]:
        code = check_port_path(8000, ep)
        if code != "200":
            log(f"Yield endpoint degraded: {ep} -> {code} (not triggering restart)", "WARN")
    log("Yield API check complete")
    return True

def check_yield_crawler():
    import sqlite3 as _sq
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    try:
        hc_db = os.path.expanduser("~/agentindex/logs/healthcheck.db")
        if not os.path.exists(hc_db): return
        c = _sq.connect(hc_db)
        row = c.execute("SELECT run_at, pools_updated FROM yield_crawler_status ORDER BY run_at DESC LIMIT 1").fetchone()
        c.close()
        if not row: log("Yield crawler: aldrig kört", "WARN"); return
        age = _dt.now(_tz.utc) - _dt.fromisoformat(row[0]).replace(tzinfo=_tz.utc)
        if age > _td(hours=26): log(f"Yield crawler: {age.seconds//3600}h sedan — kan vara stoppat", "WARN")
        else: log(f"Yield crawler: OK — senast {age.seconds//3600}h sedan, {row[1]} pooler")
    except Exception as e: log(f"Yield crawler check: {e}", "WARN")

if __name__ == "__main__":
    heal()
