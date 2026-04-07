#!/usr/bin/env python3
"""
Autonomous Crawler Manager
============================
Runs ALL crawlers until targets reached. Auto-restarts on crash.
Usage: nohup python3 crawler_manager.py > logs/crawler_manager.log 2>&1 &
"""

import subprocess, time, json, os, sys
from datetime import datetime

VENV_PYTHON = os.path.expanduser("~/agentindex/venv/bin/python")
WORKDIR = os.path.expanduser("~/agentindex")

CRAWLERS = [
    {"name": "npm", "module": "agentindex.crawlers.npm_crawler", "target": 500000, "registry": "npm", "batch": 100000},
    {"name": "pypi", "module": "agentindex.crawlers.pypi_crawler", "target": 500000, "registry": "pypi", "batch": 50000},
    {"name": "crates", "module": "agentindex.crawlers.crates_crawler", "target": 150000, "registry": "crates", "batch": 50000},
    {"name": "gems", "module": "agentindex.crawlers.rubygems_crawler", "target": 200000, "registry": "gems", "batch": 50000},
    {"name": "nuget", "module": "agentindex.crawlers.nuget_crawler", "target": 100000, "registry": "nuget", "batch": 20000},
    {"name": "packagist", "module": "agentindex.crawlers.packagist_crawler", "target": 100000, "registry": "packagist", "batch": 20000},
    {"name": "go", "module": "agentindex.crawlers.go_crawler", "target": 100000, "registry": "go", "batch": 50000},
    {"name": "wordpress", "module": "agentindex.crawlers.wordpress_crawler", "target": 59000, "registry": "wordpress", "batch": 59000},
    {"name": "vscode", "module": "agentindex.crawlers.vscode_crawler", "target": 50000, "registry": "vscode", "batch": 50000},
    {"name": "ios", "module": "agentindex.crawlers.ios_crawler", "target": 30000, "registry": "ios", "batch": 20000},
    {"name": "android", "module": "agentindex.crawlers.android_crawler", "target": 20000, "registry": "android", "batch": 10000},
    {"name": "steam", "module": "agentindex.crawlers.steam_crawler", "target": 20000, "registry": "steam", "batch": 20000},
    {"name": "firefox", "module": "agentindex.crawlers.firefox_crawler", "target": 30000, "registry": "firefox", "batch": 30000},
    {"name": "chrome", "module": "agentindex.crawlers.chrome_crawler_v2", "target": 100, "registry": "extension", "batch": 100},
    {"name": "homebrew", "module": "agentindex.crawlers.homebrew_crawler", "target": 8500, "registry": "homebrew", "batch": 8500},
    {"name": "websites", "module": "agentindex.crawlers.website_crawler", "target": 10000, "registry": "website", "batch": 5000},
]

MAX_CONCURRENT = 6
CHECK_INTERVAL = 300  # 5 minutes
STALL_THRESHOLD = 3   # 15 min no growth = stalled


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_count(registry):
    try:
        import psycopg2
        conn = psycopg2.connect("dbname=agentindex")
        cur = conn.cursor()
        if registry == "website":
            cur.execute("SELECT COUNT(*) FROM website_cache")
        else:
            cur.execute("SELECT COUNT(*) FROM software_registry WHERE registry = %s", (registry,))
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        log(f"DB error ({registry}): {e}")
        return 0


class Crawler:
    def __init__(self, config):
        self.cfg = config
        self.name = config["name"]
        self.proc = None
        self.restarts = 0
        self.max_restarts = 5
        self.last_count = 0
        self.stall_checks = 0
        self.status = "pending"
        self.started_at = None
        self.finished_at = None

    def start(self):
        batch = self.cfg["batch"]
        module = self.cfg["module"]
        logfile = os.path.join(WORKDIR, "logs", f"cm_{self.name}.log")

        with open(logfile, "a") as f:
            f.write(f"\n=== Start {datetime.now()} attempt {self.restarts + 1} ===\n")
            self.proc = subprocess.Popen(
                [VENV_PYTHON, "-m", module, str(batch)],
                stdout=f, stderr=f, cwd=WORKDIR
            )

        self.status = "running"
        self.started_at = datetime.now()
        self.restarts += 1
        self.stall_checks = 0
        log(f"START {self.name} PID={self.proc.pid} attempt={self.restarts} batch={batch}")

    def check(self):
        if self.status != "running":
            return

        current = get_count(self.cfg["registry"])
        target = self.cfg["target"]

        # Process exited?
        if self.proc and self.proc.poll() is not None:
            if current >= target * 0.85:
                self.status = "done"
                self.finished_at = datetime.now()
                log(f"DONE {self.name}: {current}/{target}")
            elif self.restarts < self.max_restarts:
                log(f"CRASHED {self.name} at {current}. Restarting in 10s...")
                time.sleep(10)
                self.start()
            else:
                self.status = "failed"
                self.finished_at = datetime.now()
                log(f"FAILED {self.name} after {self.max_restarts} attempts. Count: {current}")
            return

        # Check stalling
        if current == self.last_count:
            self.stall_checks += 1
            if self.stall_checks >= STALL_THRESHOLD:
                if current >= target * 0.5:
                    self.status = "done"
                    self.proc.terminate()
                    self.finished_at = datetime.now()
                    log(f"STALLED-DONE {self.name}: {current}/{target} (>50%)")
                elif self.restarts < self.max_restarts:
                    self.proc.terminate()
                    time.sleep(5)
                    log(f"STALLED {self.name} at {current}. Restarting...")
                    self.start()
                else:
                    self.status = "failed"
                    self.proc.terminate()
                    self.finished_at = datetime.now()
                    log(f"STALLED-FAILED {self.name} at {current}")
        else:
            self.stall_checks = 0

        self.last_count = current

    @property
    def info(self):
        return {
            "status": self.status,
            "count": get_count(self.cfg["registry"]),
            "target": self.cfg["target"],
            "restarts": self.restarts,
            "started": self.started_at.isoformat() if self.started_at else None,
            "finished": self.finished_at.isoformat() if self.finished_at else None,
            "pid": self.proc.pid if self.proc and self.proc.poll() is None else None,
        }


def save_status(crawlers):
    status = {c.name: c.info for c in crawlers}
    total = sum(v["count"] for v in status.values())
    status["_summary"] = {
        "total_items": total,
        "running": sum(1 for c in crawlers if c.status == "running"),
        "done": sum(1 for c in crawlers if c.status == "done"),
        "failed": sum(1 for c in crawlers if c.status == "failed"),
        "pending": sum(1 for c in crawlers if c.status == "pending"),
        "updated": datetime.now().isoformat(),
    }
    with open(os.path.join(WORKDIR, "logs", "crawler_status.json"), "w") as f:
        json.dump(status, f, indent=2)


def main():
    os.makedirs(os.path.join(WORKDIR, "logs"), exist_ok=True)
    log("=== CRAWLER MANAGER STARTING ===")

    crawlers = [Crawler(c) for c in CRAWLERS]

    # Initialize counts and skip already-done
    for c in crawlers:
        current = get_count(c.cfg["registry"])
        c.last_count = current
        if current >= c.cfg["target"] * 0.85:
            c.status = "done"
            c.finished_at = datetime.now()
            log(f"SKIP {c.name}: already at {current}/{c.cfg['target']}")

    # Start initial batch
    active = 0
    for c in crawlers:
        if active >= MAX_CONCURRENT:
            break
        if c.status == "pending":
            c.start()
            active += 1
            time.sleep(2)  # Stagger starts

    save_status(crawlers)

    # Main loop
    while True:
        time.sleep(CHECK_INTERVAL)

        # Check all running
        active = 0
        for c in crawlers:
            if c.status == "running":
                c.check()
                if c.status == "running":
                    active += 1

        # Start pending if slots available
        for c in crawlers:
            if c.status == "pending" and active < MAX_CONCURRENT:
                c.start()
                active += 1
                time.sleep(2)

        # Save + report
        save_status(crawlers)
        done = sum(1 for c in crawlers if c.status == "done")
        failed = sum(1 for c in crawlers if c.status == "failed")
        pending = sum(1 for c in crawlers if c.status == "pending")
        total = sum(get_count(c.cfg["registry"]) for c in crawlers)
        log(f"Active={active} Done={done} Failed={failed} Pending={pending} Total={total:,}")

        if active == 0 and pending == 0:
            log("=== ALL CRAWLERS COMPLETE ===")
            save_status(crawlers)
            break


if __name__ == "__main__":
    main()
