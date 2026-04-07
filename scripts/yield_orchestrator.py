#!/usr/bin/env python3
"""
Nerq Yield Orchestrator — Runs all yield pipelines on schedule.
Designed to be run by LaunchAgent every 15 minutes.
Each pipeline runs only at its scheduled interval.

Run: python3 scripts/yield_orchestrator.py
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WORKDIR = str(Path(__file__).parent.parent)
PYTHON = os.path.join(WORKDIR, "venv", "bin", "python3")
LOG_DIR = os.path.join(WORKDIR, "logs")
STATE_FILE = os.path.join(WORKDIR, "data", "yield_orchestrator_state.json")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "yield_orchestrator.log")),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("yield_orchestrator")

# Pipeline definitions: (name, script, interval_minutes, timeout_seconds)
PIPELINES = [
    ("yield_tracker", "scripts/yield_tracker.py", 60, 120),
    ("reach_dashboard", "scripts/reach_dashboard.py", 60, 120),
    ("yield_404_autonomous", "scripts/yield_404_autonomous.py", 360, 120),
    ("yield_deep_enrichment", "scripts/yield_deep_enrichment.py", 360, 120),
    ("yield_perplexity", "scripts/yield_perplexity.py", 1440, 60),
]


def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _should_run(name, interval_min, state):
    last_run = state.get(name, {}).get("last_run", 0)
    elapsed = time.time() - last_run
    return elapsed >= interval_min * 60


def _run_pipeline(name, script, timeout):
    cmd = [PYTHON, os.path.join(WORKDIR, script), "24"]
    log_path = os.path.join(LOG_DIR, f"{name}.log")

    log.info(f"Running {name}...")
    start = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKDIR
        )
        duration = time.time() - start
        success = result.returncode == 0

        # Append to pipeline-specific log
        with open(log_path, "a") as f:
            f.write(f"\n--- {datetime.now().isoformat()} ---\n")
            if result.stdout:
                f.write(result.stdout[-2000:])  # Last 2KB
            if result.stderr:
                f.write(f"\nSTDERR: {result.stderr[-500:]}")

        if success:
            log.info(f"  {name} completed in {duration:.1f}s")
        else:
            log.error(f"  {name} failed (exit {result.returncode}) in {duration:.1f}s")

        return success, duration
    except subprocess.TimeoutExpired:
        log.error(f"  {name} timed out after {timeout}s")
        return False, timeout
    except Exception as e:
        log.error(f"  {name} error: {e}")
        return False, 0


def main():
    log.info("Yield Orchestrator starting")
    state = _load_state()
    ran = 0

    for name, script, interval, timeout in PIPELINES:
        if not _should_run(name, interval, state):
            continue

        success, duration = _run_pipeline(name, script, timeout)
        state[name] = {
            "last_run": time.time(),
            "last_success": success,
            "last_duration": round(duration, 1),
            "last_ts": datetime.now().isoformat(),
        }
        ran += 1
        _save_state(state)

    if ran == 0:
        log.info("No pipelines due to run")
    else:
        log.info(f"Orchestrator completed: {ran} pipelines ran")


if __name__ == "__main__":
    main()
