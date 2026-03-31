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
    """Deep health check — actually tests a real endpoint, not just port."""
    out, _ = run("curl -s -m 8 http://localhost:8000/v1/health", timeout=12)
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

# Level 1: safe auto-execute actions
SAFE_ACTIONS = {
    "restart_api": lambda: run("launchctl stop com.nerq.api && sleep 2 && launchctl start com.nerq.api", timeout=15),
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
2. RECOMMENDED ACTION — pick ONE from: restart_api, restart_postgresql, clear_redis_cache, kill_idle_connections, none
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

    # Execute Level 1 (safe) actions only
    if action_name and action_name in SAFE_ACTIONS:
        log(f"LLM recommends Level 1 action: {action_name} — executing", "INTEL")
        result, rc = SAFE_ACTIONS[action_name]()
        log_action(conn, f"llm_{action_name}", f"LLM-recommended: {response[:100]}", f"rc={rc}")
    elif action_name and action_name != "none":
        # Level 2: log only, don't execute
        log(f"LLM recommends Level 2 action (not auto-executing): {action_name}", "INTEL")
        log_action(conn, "llm_suggestion_only", f"{action_name}: {response[:150]}", "logged_only")

    return response


def heal():
    conn = init_db()
    actions_taken = 0

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
    out, _ = run("ps aux | grep 'postgres.*agentindex' | grep -v grep", timeout=5)
    if out:
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
                # Check if this PG backend is idle (finished its query)
                zstate_out, _ = run(f"""{PSQL} -d agentindex -t -A -c "SELECT state FROM pg_stat_activity WHERE pid = {zpid};" """, timeout=3)
                zstate = zstate_out.strip() if zstate_out else ""
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
        api_status = check_port(8000)
        log(f"API failed deep health check (port status: {api_status}), restarting", "HEAL")
        pids = get_pids("discovery:app")
        for pid in pids:
            run(f"kill -9 {pid}")
        time.sleep(2)
        # LaunchAgent KeepAlive will restart it, but kick it just in case
        run(f"launchctl kickstart gui/$(id -u)/com.nerq.api 2>/dev/null")
        time.sleep(5)
        new_healthy = check_api_health()
        log_action(conn, "restart_api", f"Old PIDs: {pids}, port was {api_status}", f"Healthy after restart: {new_healthy}")
        actions_taken += 1

    # ── 5. Parser: restart if suspended or missing ──
    parser_count = count_procs("run_parser_loop")
    if parser_count == 0:
        log("Parser not running, triggering LaunchAgent restart", "HEAL")
        run("launchctl kickstart gui/$(id -u)/com.agentindex.parser")
        time.sleep(3)
        log_action(conn, "restart_parser", "Was missing")
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

    # ── 6. Orchestrator: fix missing or duplicates ──
    orch_count = count_procs("agentindex.run")
    if orch_count == 0:
        log("Orchestrator not running, attempting restart", "HEAL")
        out, rc = run("launchctl kickstart gui/$(id -u)/com.agentindex.orchestrator 2>&1")
        if rc != 0 or "Could not find" in (out or ""):
            log("kickstart failed, trying launchctl load", "HEAL")
            run("launchctl load ~/Library/LaunchAgents/com.agentindex.orchestrator.plist 2>&1")
        time.sleep(3)
        new_count = count_procs("agentindex.run")
        log_action(conn, "restart_orchestrator", f"Was missing, now {new_count} running")
        actions_taken += 1
    elif orch_count > 1:
        pids = get_pids("agentindex.run")
        log(f"Multiple orchestrators ({orch_count}), killing extras", "HEAL")
        for pid in sorted(pids)[1:]:
            run(f"kill -9 {pid}")
            log_action(conn, "kill_dup_orchestrator", f"PID {pid}")
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
        log("Redis not responding, restarting", "HEAL")
        run("/opt/homebrew/bin/brew services restart redis 2>/dev/null")
        time.sleep(3)
        redis_ok2, _ = run("/opt/homebrew/bin/redis-cli ping")
        log_action(conn, "restart_redis", f"Was down, now {redis_ok2}")
        actions_taken += 1

    # ── 10. LaunchAgents: reload if unloaded ──
    agents_map = {
        "parser": ("run_parser_loop", "com.agentindex.parser"),
        "dashboard": ("agentindex.dashboard", "com.agentindex.dashboard"),
        "mcp_sse": ("mcp_sse_server", "com.agentindex.mcp-sse"),
    }
    for name, (grep_str, label) in agents_map.items():
        if count_procs(grep_str) == 0:
            log(f"{name} not running, trying kickstart then load", "HEAL")
            out, rc = run(f"launchctl kickstart gui/$(id -u)/{label} 2>&1")
            if rc != 0 or "Could not find" in (out or ""):
                run(f"launchctl load ~/Library/LaunchAgents/{label}.plist 2>&1")
            time.sleep(3)
            new_count = count_procs(grep_str)
            log_action(conn, f"restart_{name}", f"Was missing, now {new_count}")
            actions_taken += 1

    # ── 11. Analytics retention (daily at 03:00-03:05 only) ──
    _h = datetime.now().hour
    _m = datetime.now().minute
    if _h == 3 and _m < 6:
        try:
            import sqlite3 as _sqlite3_ret
            _adb = os.path.expanduser("~/agentindex/logs/analytics.db")
            if os.path.exists(_adb):
                _rc = _sqlite3_ret.connect(_adb)
                _del = _rc.execute("DELETE FROM requests WHERE ts < datetime('now', '-90 days')").rowcount
                if _del > 0:
                    _rc.execute("PRAGMA incremental_vacuum;")
                    log(f"Analytics retention: deleted {_del} rows >90 days", "INFO")
                    log_action(conn, "analytics_retention", f"Deleted {_del} rows")
                    actions_taken += 1
                _rc.commit()
                _rc.close()
        except Exception as _ret_e:
            log(f"Analytics retention error: {_ret_e}", "WARN")

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
    for ep in ["/v1/yield/overview", "/v1/yield/insights?limit=1"]:
        code = check_port_path(8000, ep)
        if code != "200":
            log(f"Yield endpoint degraded: {ep} -> {code}", "WARN")
            return False
    log("Yield API: OK")
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
