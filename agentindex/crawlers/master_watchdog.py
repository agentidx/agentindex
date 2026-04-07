#!/usr/bin/env python3
"""
Master Watchdog — keeps ALL enrichment pipelines and crawlers alive.
Checks every 2 minutes. Restarts dead processes. Logs everything.

Run: python3 -m agentindex.crawlers.master_watchdog
Or as LaunchAgent with KeepAlive=true.
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WORKDIR = str(Path(__file__).parent.parent.parent)
PYTHON = os.path.join(WORKDIR, "venv", "bin", "python3")
LOG_DIR = os.path.join(WORKDIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "master_watchdog.log")),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("master_watchdog")

# All processes to monitor. Each has a grep pattern and restart command.
# Max 3 concurrent enrichment processes to avoid overloading DB/CPU
MAX_CONCURRENT = 2  # Increased back — 4 workers now handle API load

# Round-robin enrichment: small batches (2000) per registry so the watchdog
# cycles through ALL registries. Within each batch: most popular first
# (ORDER BY downloads DESC in the enrichment query).
# npm/pypi have dedicated LaunchAgents and are NOT managed here.
BATCH_SIZE = 2000  # Small batches → fast rotation → all registries get attention

PROCESSES = [
    {"name": "vscode_enrichment", "grep": "registry_enrichment.*vscode",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "vscode", str(BATCH_SIZE)],
     "log": "vscode_enrichment.log"},
    {"name": "steam_enrichment", "grep": "registry_enrichment.*steam",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "steam", str(BATCH_SIZE)],
     "log": "steam_enrichment.log"},
    {"name": "crates_enrichment", "grep": "registry_enrichment.*crates",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "crates", str(BATCH_SIZE)],
     "log": "crates_enrichment.log"},
    {"name": "nuget_enrichment", "grep": "registry_enrichment.*nuget",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "nuget", str(BATCH_SIZE)],
     "log": "nuget_enrichment.log"},
    {"name": "packagist_enrichment", "grep": "registry_enrichment.*packagist",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "packagist", str(BATCH_SIZE)],
     "log": "packagist_enrichment.log"},
    {"name": "go_enrichment", "grep": "registry_enrichment.*go\\b",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "go", str(BATCH_SIZE)],
     "log": "go_enrichment.log"},
    {"name": "gems_enrichment", "grep": "registry_enrichment.*gems",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "gems", str(BATCH_SIZE)],
     "log": "gems_enrichment.log"},
    {"name": "homebrew_enrichment", "grep": "registry_enrichment.*homebrew",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "homebrew", str(BATCH_SIZE)],
     "log": "homebrew_enrichment.log"},
    {"name": "ios_enrichment", "grep": "registry_enrichment.*ios",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "ios", str(BATCH_SIZE)],
     "log": "ios_enrichment.log"},
    {"name": "firefox_enrichment", "grep": "registry_enrichment.*firefox",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "firefox", str(BATCH_SIZE)],
     "log": "firefox_enrichment.log"},
    {"name": "chrome_enrichment", "grep": "registry_enrichment.*chrome",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "chrome", str(BATCH_SIZE)],
     "log": "chrome_enrichment.log"},
    {"name": "saas_enrichment", "grep": "registry_enrichment.*saas",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "saas", str(BATCH_SIZE)],
     "log": "saas_enrichment.log"},
    {"name": "ai_tool_enrichment", "grep": "registry_enrichment.*ai_tool",
     "cmd": [PYTHON, "-m", "agentindex.crawlers.registry_enrichment", "ai_tool", str(BATCH_SIZE)],
     "log": "ai_tool_enrichment.log"},
]


def is_running(grep_pattern):
    """Check if a process matching the grep pattern is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", grep_pattern],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def start_process(proc):
    """Start a process in the background."""
    log_path = os.path.join(LOG_DIR, proc["log"])
    with open(log_path, "a") as f:
        f.write(f"\n--- Restarted by watchdog at {datetime.now()} ---\n")
    p = subprocess.Popen(
        proc["cmd"],
        stdout=open(log_path, "a"),
        stderr=subprocess.STDOUT,
        cwd=WORKDIR,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    log.info(f"Started {proc['name']} (PID {p.pid})")
    return p.pid


def _check_completed():
    """Check which registries have been fully enriched.
    A registry is completed if ≥99% have enriched_at set AND
    the count of unenriched entities is < 100 (no point running enricher for <100).
    """
    completed = set()
    try:
        import subprocess as _sp
        result = _sp.run(
            [PYTHON, "-c", """
from agentindex.db.models import get_session
from sqlalchemy import text
s = get_session()
s.execute(text("SET statement_timeout = '10s'"))
rows = s.execute(text(
    "SELECT registry, COUNT(*), COUNT(enriched_at), COUNT(*) - COUNT(enriched_at) as unenriched "
    "FROM software_registry GROUP BY registry"
)).fetchall()
s.close()
for r in rows:
    unenriched = r[3]
    if r[2] >= r[1] * 0.99 and r[1] > 0 and unenriched < 100:
        print(r[0])
"""],
            capture_output=True, text=True, cwd=WORKDIR, timeout=60
        )
        completed = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
    except Exception as e:
        log.warning(f"Completed check failed: {e}")
    return completed


def main():
    log.info(f"Master Watchdog started. Max {MAX_CONCURRENT} concurrent. {len(PROCESSES)} in queue.")
    log.info(f"Python: {PYTHON}")

    _completed_registries = set()
    check_count = 0
    _next_idx = 0  # Round-robin pointer
    while True:
        # Every 10 checks (20 min), refresh completed registries list
        if check_count % 10 == 0:
            _completed_registries = _check_completed()
            if _completed_registries:
                log.info(f"Completed registries (skipping): {_completed_registries}")
        # Count currently running enrichment processes
        running = [p for p in PROCESSES if is_running(p["grep"])]
        running_count = len(running)

        # Round-robin: start from _next_idx, wrap around, pick next available
        started = 0
        checked = 0
        while running_count + started < MAX_CONCURRENT and checked < len(PROCESSES):
            proc = PROCESSES[_next_idx % len(PROCESSES)]
            _next_idx = (_next_idx + 1) % len(PROCESSES)
            checked += 1
            if is_running(proc["grep"]):
                continue
            reg_name = proc["name"].replace("_enrichment", "")
            if reg_name in _completed_registries:
                continue
            log.info(f"Starting {proc['name']} (batch {BATCH_SIZE}, {running_count + started + 1}/{MAX_CONCURRENT})")
            try:
                start_process(proc)
                started += 1
                time.sleep(5)
            except Exception as e:
                log.error(f"Failed to start {proc['name']}: {e}")

        check_count += 1
        # Log status every 10 checks (20 min)
        if check_count % 10 == 0:
            names = [p["name"] for p in PROCESSES if is_running(p["grep"])]
            log.info(f"Status: {len(names)}/{MAX_CONCURRENT} running: {', '.join(names)}")

        time.sleep(120)  # Check every 2 minutes


if __name__ == "__main__":
    main()
