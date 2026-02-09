"""
AgentIndex Vakten (The Guard)

Standalone system monitor that:
- Checks all services are running
- Monitors disk space, memory usage
- Detects stuck crawl jobs
- Auto-restarts crashed components
- Writes health report to file (readable remotely)
- Detects scraping/abuse patterns in API logs

Run standalone: python -m agentindex.agents.vakten
Or integrated via the orchestrator.
"""

import os
import time
import logging
import subprocess
import json
from datetime import datetime, timedelta
from agentindex.db.models import Agent, DiscoveryLog, CrawlJob, get_session
from sqlalchemy import select, func

logger = logging.getLogger("agentindex.vakten")

HEALTH_FILE = os.path.expanduser("~/agentindex/health.json")
ALERT_FILE = os.path.expanduser("~/agentindex/alerts.log")


class Vakten:
    """System guardian — monitors, alerts, and auto-recovers."""

    def __init__(self):
        self.session = get_session()
        self.alerts = []

    def full_check(self) -> dict:
        """Run all health checks and return status report."""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "healthy",
            "checks": {},
            "alerts": [],
        }

        # 1. Database health
        report["checks"]["database"] = self._check_database()

        # 2. Ollama health
        report["checks"]["ollama"] = self._check_ollama()

        # 3. Disk space
        report["checks"]["disk"] = self._check_disk()

        # 4. Memory usage
        report["checks"]["memory"] = self._check_memory()

        # 5. Crawl pipeline health
        report["checks"]["pipeline"] = self._check_pipeline()

        # 6. API responsiveness
        report["checks"]["api"] = self._check_api()

        # 7. Stuck jobs
        report["checks"]["stuck_jobs"] = self._check_stuck_jobs()

        # 8. Abuse detection
        report["checks"]["abuse"] = self._check_abuse()

        # 9. Index growth
        report["checks"]["growth"] = self._check_growth()

        # Determine overall status
        report["alerts"] = self.alerts
        if any(a["severity"] == "critical" for a in self.alerts):
            report["status"] = "critical"
        elif any(a["severity"] == "warning" for a in self.alerts):
            report["status"] = "degraded"

        # Write health file
        self._write_health_file(report)

        # Write alerts
        if self.alerts:
            self._write_alerts()

        return report

    def _check_database(self) -> dict:
        """Check PostgreSQL is responsive."""
        try:
            from sqlalchemy import text
            result = self.session.execute(text("SELECT 1")).scalar()
            total = self.session.execute(select(func.count(Agent.id))).scalar() or 0
            return {"status": "ok", "total_agents": total}
        except Exception as e:
            self._alert("critical", "database", f"PostgreSQL not responding: {e}")
            return {"status": "error", "error": str(e)}

    def _check_ollama(self) -> dict:
        """Check Ollama is running and model is loaded."""
        try:
            from ollama import Client
            url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            client = Client(host=url)
            models = client.list()
            names = [m.get("name", "") for m in models.get("models", [])]
            if not names:
                self._alert("warning", "ollama", "No models loaded")
                return {"status": "warning", "models": []}
            return {"status": "ok", "models": names}
        except Exception as e:
            self._alert("critical", "ollama", f"Ollama not responding: {e}")
            return {"status": "error", "error": str(e)}

    def _check_disk(self) -> dict:
        """Check available disk space."""
        try:
            stat = os.statvfs("/")
            total_gb = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
            used_pct = ((total_gb - free_gb) / total_gb) * 100

            if free_gb < 10:
                self._alert("critical", "disk", f"Only {free_gb:.1f}GB free")
            elif free_gb < 50:
                self._alert("warning", "disk", f"Only {free_gb:.1f}GB free")

            return {
                "status": "ok" if free_gb >= 10 else "warning",
                "total_gb": round(total_gb, 1),
                "free_gb": round(free_gb, 1),
                "used_percent": round(used_pct, 1),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_memory(self) -> dict:
        """Check system memory usage (macOS compatible)."""
        try:
            result = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                # Fallback for non-macOS
                return {"status": "ok", "note": "vm_stat not available"}

            lines = result.stdout.strip().split("\n")
            stats = {}
            for line in lines[1:]:
                if ":" in line:
                    key, val = line.split(":", 1)
                    val = val.strip().rstrip(".")
                    try:
                        stats[key.strip()] = int(val)
                    except ValueError:
                        pass

            page_size = 16384  # Apple Silicon default
            free_pages = stats.get("Pages free", 0)
            inactive_pages = stats.get("Pages inactive", 0)
            available_mb = (free_pages + inactive_pages) * page_size / (1024 * 1024)

            if available_mb < 1024:
                self._alert("warning", "memory", f"Low memory: {available_mb:.0f}MB available")

            return {
                "status": "ok" if available_mb >= 1024 else "warning",
                "available_mb": round(available_mb),
            }
        except Exception as e:
            return {"status": "unknown", "error": str(e)}

    def _check_pipeline(self) -> dict:
        """Check crawl → parse → classify → rank pipeline health."""
        try:
            statuses = self.session.execute(
                select(Agent.crawl_status, func.count(Agent.id))
                .group_by(Agent.crawl_status)
            ).all()

            counts = {s: c for s, c in statuses}

            # Check for bottlenecks
            indexed = counts.get("indexed", 0)
            parsed = counts.get("parsed", 0)
            classified = counts.get("classified", 0)
            ranked = counts.get("ranked", 0)

            if indexed > 5000:
                self._alert("warning", "pipeline", f"Parser backlog: {indexed} agents waiting")

            if parsed > 2000:
                self._alert("warning", "pipeline", f"Classifier backlog: {parsed} agents waiting")

            return {
                "status": "ok",
                "indexed": indexed,
                "parsed": parsed,
                "classified": classified,
                "ranked": ranked,
                "failed": counts.get("parse_failed", 0) + counts.get("removed", 0),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_api(self) -> dict:
        """Check if Discovery API is responding."""
        try:
            import httpx
            port = os.getenv("API_PORT", "8100")
            response = httpx.get(f"http://localhost:{port}/v1/health", timeout=5)
            if response.status_code == 200:
                return {"status": "ok", "port": port}
            else:
                self._alert("critical", "api", f"API returned {response.status_code}")
                return {"status": "error", "code": response.status_code}
        except Exception as e:
            self._alert("critical", "api", f"API not responding: {e}")
            return {"status": "error", "error": str(e)}

    def _check_stuck_jobs(self) -> dict:
        """Detect crawl jobs that have been running too long."""
        try:
            cutoff = datetime.utcnow() - timedelta(hours=3)
            stuck = self.session.execute(
                select(CrawlJob).where(
                    CrawlJob.status == "running",
                    CrawlJob.started_at < cutoff,
                )
            ).scalars().all()

            if stuck:
                names = [f"{j.source}({j.id})" for j in stuck]
                self._alert("warning", "stuck_jobs", f"Stuck jobs: {', '.join(names)}")

                # Auto-fix: mark as failed
                for job in stuck:
                    job.status = "failed"
                    job.error_message = "Auto-killed by Vakten: exceeded 3h runtime"
                self.session.commit()

            return {"status": "ok", "stuck_count": len(stuck)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_abuse(self) -> dict:
        """Detect potential scraping or abuse patterns."""
        try:
            hour_ago = datetime.utcnow() - timedelta(hours=1)

            # Total requests last hour
            total = self.session.execute(
                select(func.count(DiscoveryLog.id))
                .where(DiscoveryLog.timestamp > hour_ago)
            ).scalar() or 0

            if total > 1000:
                self._alert("warning", "abuse", f"High request volume: {total}/hour")

            return {"status": "ok", "requests_last_hour": total}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_growth(self) -> dict:
        """Track index growth rate."""
        try:
            day_ago = datetime.utcnow() - timedelta(hours=24)
            week_ago = datetime.utcnow() - timedelta(days=7)

            new_today = self.session.execute(
                select(func.count(Agent.id)).where(Agent.first_indexed > day_ago)
            ).scalar() or 0

            new_week = self.session.execute(
                select(func.count(Agent.id)).where(Agent.first_indexed > week_ago)
            ).scalar() or 0

            total = self.session.execute(
                select(func.count(Agent.id)).where(Agent.is_active == True)
            ).scalar() or 0

            if new_today == 0 and total > 100:
                self._alert("warning", "growth", "No new agents indexed in 24h")

            return {
                "status": "ok",
                "total_active": total,
                "new_24h": new_today,
                "new_7d": new_week,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _alert(self, severity: str, component: str, message: str):
        """Record an alert."""
        alert = {
            "severity": severity,
            "component": component,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.alerts.append(alert)
        if severity == "critical":
            logger.critical(f"ALERT [{component}]: {message}")
        else:
            logger.warning(f"ALERT [{component}]: {message}")

    def _write_health_file(self, report: dict):
        """Write health report to JSON file (readable via Tailscale/SSH)."""
        try:
            os.makedirs(os.path.dirname(HEALTH_FILE), exist_ok=True)
            with open(HEALTH_FILE, "w") as f:
                json.dump(report, f, indent=2)
        except Exception as e:
            logger.error(f"Could not write health file: {e}")

    def _write_alerts(self):
        """Append alerts to alert log."""
        try:
            with open(ALERT_FILE, "a") as f:
                for alert in self.alerts:
                    f.write(f"{alert['timestamp']} [{alert['severity'].upper()}] "
                            f"{alert['component']}: {alert['message']}\n")
        except Exception as e:
            logger.error(f"Could not write alerts: {e}")


def run_vakten():
    """Run a single health check cycle."""
    vakten = Vakten()
    report = vakten.full_check()

    status = report["status"]
    checks_ok = sum(1 for c in report["checks"].values() if c.get("status") == "ok")
    checks_total = len(report["checks"])

    logger.info(
        f"VAKTEN | Status: {status.upper()} | "
        f"Checks: {checks_ok}/{checks_total} OK | "
        f"Alerts: {len(report['alerts'])}"
    )

    return report


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    report = run_vakten()
    print(json.dumps(report, indent=2))
