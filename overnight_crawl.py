#!/usr/bin/env python3
"""
Overnight Crawler Watchdog
===========================
Checks every 10 minutes if crawlers are still running.
If any have died, restart them. No restart limit — keep going until data stops growing.
Only stop a crawler if it produced 0 new items in 30 minutes (3 consecutive checks).

Run with: nohup python3 overnight_crawl.py > logs/overnight.log 2>&1 &
"""

import subprocess
import time
import os
import sys
from datetime import datetime

# Use the venv Python that has all dependencies (sqlalchemy, psycopg2, requests)
PYTHON = os.path.expanduser("~/agentindex/venv/bin/python3")
WORKDIR = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(WORKDIR, "logs")

CRAWLERS = [
    {"name": "pypi",           "module": "agentindex.crawlers.pypi_crawler",           "args": "500000", "registry": "pypi"},
    {"name": "npm_bulk",       "module": "agentindex.crawlers.npm_bulk_crawler",       "args": "500000", "registry": "npm"},
    {"name": "nuget_catalog",  "module": "agentindex.crawlers.nuget_catalog_crawler",  "args": "400000", "registry": "nuget"},
    {"name": "packagist_bulk", "module": "agentindex.crawlers.packagist_bulk_crawler", "args": "400000", "registry": "packagist"},
    {"name": "gems_bulk",      "module": "agentindex.crawlers.gems_bulk_crawler",      "args": "200000", "registry": "gems"},
    {"name": "go",             "module": "agentindex.crawlers.go_crawler",             "args": "100000", "registry": "go"},
    {"name": "crates_bulk",    "module": "agentindex.crawlers.crates_bulk_loader",     "args": "200000", "registry": "crates"},
    {"name": "ios",            "module": "agentindex.crawlers.ios_crawler",            "args": "50000",  "registry": "ios"},
    {"name": "android",        "module": "agentindex.crawlers.android_crawler",        "args": "20000",  "registry": "android"},
    {"name": "firefox",        "module": "agentindex.crawlers.firefox_crawler",        "args": "50000",  "registry": "firefox"},
    {"name": "steam",          "module": "agentindex.crawlers.steam_crawler",          "args": "50000",  "registry": "steam"},
    {"name": "wordpress",      "module": "agentindex.crawlers.wordpress_crawler",      "args": "100000", "registry": "wordpress"},
    {"name": "website",        "module": "agentindex.crawlers.website_crawler",        "args": "10000",  "registry": "website"},
]

CHECK_INTERVAL = 600  # 10 minutes
STALL_LIMIT = 3       # 3 checks with no growth = done


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_count(registry):
    """Get current row count for a registry."""
    try:
        import psycopg2
        conn = psycopg2.connect("dbname=agentindex", connect_timeout=5)
        cur = conn.cursor()
        if registry == "website":
            cur.execute("SELECT COUNT(*) FROM website_cache")
        else:
            cur.execute("SELECT COUNT(*) FROM software_registry WHERE registry=%s", (registry,))
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        log(f"  DB error for {registry}: {e}")
        return -1


def is_running(module_name):
    """Check if a crawler process is running by matching its module name."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", module_name],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def start_crawler(crawler):
    """Start a crawler subprocess."""
    logfile = os.path.join(LOGDIR, f"overnight_{crawler['name']}.log")
    cmd = [PYTHON, "-m", crawler["module"], crawler["args"]]
    with open(logfile, "a") as f:
        f.write(f"\n--- Restarted at {datetime.now()} ---\n")
    proc = subprocess.Popen(
        cmd,
        stdout=open(logfile, "a"),
        stderr=subprocess.STDOUT,
        cwd=WORKDIR,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    return proc.pid


def main():
    os.makedirs(LOGDIR, exist_ok=True)

    log(f"Overnight watchdog started. Python: {PYTHON}")
    log(f"Crawlers: {len(CRAWLERS)}")

    # Initialize state
    state = {}
    for c in CRAWLERS:
        count = get_count(c["registry"])
        already_running = is_running(c["module"])
        state[c["name"]] = {
            "last_count": count,
            "stall": 0,
            "done": False,
            "restarts": 0,
        }
        status = "RUNNING" if already_running else "not running"
        log(f"  {c['name']:20s} {c['registry']:12s} count={count:>10,}  {status}")

    # Start any crawlers that aren't already running
    for c in CRAWLERS:
        if not is_running(c["module"]):
            pid = start_crawler(c)
            state[c["name"]]["restarts"] += 1
            log(f"  Started {c['name']} (pid={pid})")

    log("All crawlers launched. Entering watch loop.")
    log("")

    while True:
        time.sleep(CHECK_INTERVAL)

        all_done = True
        status_lines = []

        for c in CRAWLERS:
            name = c["name"]
            s = state[name]

            if s["done"]:
                continue

            all_done = False
            count = get_count(c["registry"])
            if count < 0:
                # DB error — skip this check
                continue

            delta = count - s["last_count"]
            running = is_running(c["module"])

            if delta > 0:
                # Making progress
                s["stall"] = 0
                s["last_count"] = count
                if not running:
                    pid = start_crawler(c)
                    s["restarts"] += 1
                    log(f"RESTART {name}: died but was growing (+{delta}). count={count:,} restarts={s['restarts']} pid={pid}")
                status_lines.append(f"  {name:20s} +{delta:<8,} total={count:>10,}  {'RUN' if running or not running else 'RUN'}")
            else:
                # No growth
                s["stall"] += 1
                if s["stall"] >= STALL_LIMIT:
                    s["done"] = True
                    log(f"DONE {name}: no growth in {STALL_LIMIT * CHECK_INTERVAL // 60} min. Final count={count:,}")
                elif not running:
                    pid = start_crawler(c)
                    s["restarts"] += 1
                    log(f"RESTART {name}: died, stall={s['stall']}/{STALL_LIMIT}. count={count:,} restarts={s['restarts']} pid={pid}")
                status_lines.append(f"  {name:20s} +0         total={count:>10,}  stall={s['stall']}/{STALL_LIMIT}")

        # Summary
        running_count = sum(1 for c in CRAWLERS if not state[c["name"]]["done"])
        done_count = sum(1 for c in CRAWLERS if state[c["name"]]["done"])
        total_items = sum(state[c["name"]]["last_count"] for c in CRAWLERS if state[c["name"]]["last_count"] > 0)
        total_restarts = sum(state[c["name"]]["restarts"] for c in CRAWLERS)

        log(f"STATUS: running={running_count} done={done_count} total_items={total_items:,} restarts={total_restarts}")
        for line in status_lines:
            print(line, flush=True)
        print("", flush=True)

        if all_done:
            log("ALL CRAWLERS DONE. Overnight crawl complete.")
            # Print final report
            log("")
            log("=== FINAL REPORT ===")
            for c in CRAWLERS:
                s = state[c["name"]]
                log(f"  {c['name']:20s} {c['registry']:12s} final={s['last_count']:>10,}  restarts={s['restarts']}")
            log(f"  {'TOTAL':20s} {'':12s} {total_items:>10,}")
            break


if __name__ == "__main__":
    main()
