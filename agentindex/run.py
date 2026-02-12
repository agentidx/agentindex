"""
AgentIndex Main Orchestrator

Runs all system components:
- All spiders on schedule (GitHub, npm, PyPI, HuggingFace, MCP)
- Parser continuously
- Discovery API (always running)
- Missionary (publishes presence artifacts)
- System monitor (Vakten)

Single entry point: python -m agentindex.run
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agentindex.log"),
    ]
)
logger = logging.getLogger("agentindex")


def run_github_crawl():
    logger.info("Starting GitHub crawl...")
    try:
        from agentindex.spiders.github_spider import GitHubSpider
        spider = GitHubSpider()
        stats = spider.crawl(max_results_per_query=500)
        logger.info(f"GitHub crawl complete: {stats}")
    except Exception as e:
        logger.error(f"GitHub crawl failed: {e}")


def run_npm_crawl():
    logger.info("Starting npm crawl...")
    try:
        from agentindex.spiders.npm_spider import NpmSpider
        spider = NpmSpider()
        stats = spider.crawl(max_results_per_query=250)
        logger.info(f"npm crawl complete: {stats}")
    except Exception as e:
        logger.error(f"npm crawl failed: {e}")


def run_pypi_crawl():
    logger.info("Starting PyPI crawl...")
    try:
        from agentindex.spiders.pypi_spider import PypiSpider
        spider = PypiSpider()
        stats = spider.crawl(max_results_per_query=100)
        logger.info(f"PyPI crawl complete: {stats}")
    except Exception as e:
        logger.error(f"PyPI crawl failed: {e}")


def run_huggingface_crawl():
    logger.info("Starting HuggingFace crawl...")
    try:
        from agentindex.spiders.huggingface_spider import HuggingFaceSpider
        spider = HuggingFaceSpider()
        stats = spider.crawl(max_results_per_query=200)
        logger.info(f"HuggingFace crawl complete: {stats}")
    except Exception as e:
        logger.error(f"HuggingFace crawl failed: {e}")


def run_mcp_crawl():
    logger.info("Starting MCP crawl...")
    try:
        from agentindex.spiders.mcp_spider import McpSpider
        spider = McpSpider()
        stats = spider.crawl()
        logger.info(f"MCP crawl complete: {stats}")
    except Exception as e:
        logger.error(f"MCP crawl failed: {e}")


def run_parser():
    logger.info("Starting parser...")
    try:
        from agentindex.agents.parser import Parser
        parser = Parser()
        stats = parser.parse_pending(batch_size=100)
        logger.info(f"Parse complete: {stats}")
    except Exception as e:
        logger.error(f"Parser failed: {e}")


def run_classifier():
    logger.info("Starting classifier... pausing parser")
    import subprocess
    subprocess.run(["pkill", "-STOP", "-f", "parser_loop"], capture_output=True)
    try:
        from agentindex.agents.classifier import Classifier
        classifier = Classifier()
        stats = classifier.classify_pending(batch_size=200)
        logger.info(f"Classification complete: {stats}")
        dedup = classifier.deduplicate(batch_size=100)
        logger.info(f"Dedup complete: {dedup}")
    except Exception as e:
        logger.error(f"Classifier failed: {e}")
    finally:
        subprocess.run(["pkill", "-CONT", "-f", "parser_loop"], capture_output=True)
        logger.info("Parser resumed")


def run_ranker():
    logger.info("Starting nightly ranking...")
    try:
        from agentindex.agents.ranker import Ranker
        ranker = Ranker()
        stats = ranker.run_nightly()
        logger.info(f"Ranking complete: {stats}")
        leaders = ranker.get_category_leaders()
        logger.info(f"Category leaders: {leaders}")
    except Exception as e:
        logger.error(f"Ranker failed: {e}")


def run_executor():
    logger.info("Running action executor...")
    try:
        from agentindex.agents.executor import Executor
        executor = Executor()
        stats = executor.run_approved()
        logger.info(f"Executor complete: {stats}")
    except Exception as e:
        logger.error(f"Executor failed: {e}")


def run_missionary_daily():
    logger.info("Running Missionary 2.0 daily scan...")
    try:
        from agentindex.agents.missionary import Missionary
        missionary = Missionary()
        report = missionary.run_daily()
        actions = report.get("actions", [])
        logger.info(f"Missionary 2.0 complete. Actions: {len(actions)}")
        for action in actions[:5]:
            logger.info(f"  -> {action}")
    except Exception as e:
        logger.error(f"Missionary daily failed: {e}")


def run_system_check():
    try:
        from agentindex.agents.vakten import run_vakten
        run_vakten()
    except Exception as e:
        logger.error(f"System check failed: {e}")


def run_daily_report():
    try:
        from agentindex.db.models import Agent, DiscoveryLog, get_session
        from sqlalchemy import select, func

        session = get_session()
        total = session.execute(select(func.count(Agent.id))).scalar() or 0
        active = session.execute(select(func.count(Agent.id)).where(Agent.is_active == True)).scalar() or 0

        day_ago = datetime.utcnow() - timedelta(hours=24)
        new_today = session.execute(select(func.count(Agent.id)).where(Agent.first_indexed > day_ago)).scalar() or 0
        discovery_today = session.execute(select(func.count(DiscoveryLog.id)).where(DiscoveryLog.timestamp > day_ago)).scalar() or 0

        categories = session.execute(
            select(Agent.category, func.count(Agent.id))
            .where(Agent.is_active == True).group_by(Agent.category)
            .order_by(func.count(Agent.id).desc())
        ).all()

        sources = session.execute(
            select(Agent.source, func.count(Agent.id))
            .group_by(Agent.source).order_by(func.count(Agent.id).desc())
        ).all()

        session.close()

        cat_str = ", ".join(f"{c or 'unclassified'}:{n}" for c, n in categories[:10])
        src_str = ", ".join(f"{s}:{n}" for s, n in sources)

        logger.info(f"DAILY REPORT | Total: {total} | Active: {active} | New: {new_today} | "
                     f"Discovery: {discovery_today} | Sources: {src_str} | Categories: {cat_str}")
    except Exception as e:
        logger.error(f"Daily report failed: {e}")


def start_api_thread():
    from agentindex.api.discovery import start_api
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    logger.info("Discovery API started on port 8000")


def main():
    logger.info("=" * 60)
    logger.info("AgentIndex starting...")
    logger.info(f"Time: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    from agentindex.db.models import init_db
    init_db()

    run_missionary_daily()
    start_api_thread()
    time.sleep(2)

    scheduler = BackgroundScheduler()
    crawl_interval = int(os.getenv("CRAWL_INTERVAL_HOURS", "6"))

    # Stagger spider starts
    scheduler.add_job(run_github_crawl, "interval", hours=crawl_interval,
                      id="github", next_run_time=datetime.now())
    scheduler.add_job(run_mcp_crawl, "interval", hours=crawl_interval,
                      id="mcp", next_run_time=datetime.now() + timedelta(minutes=30))
    scheduler.add_job(run_npm_crawl, "interval", hours=crawl_interval,
                      id="npm", next_run_time=datetime.now() + timedelta(hours=1))
    scheduler.add_job(run_pypi_crawl, "interval", hours=crawl_interval,
                      id="pypi", next_run_time=datetime.now() + timedelta(hours=1, minutes=30))
    scheduler.add_job(run_huggingface_crawl, "interval", hours=crawl_interval,
                      id="huggingface", next_run_time=datetime.now() + timedelta(hours=2))

    # Parser runs as separate process
    # scheduler.add_job(run_parser, "interval", minutes=10, id="parser", next_run_time=datetime.now())
    scheduler.add_job(run_classifier, "interval", minutes=30, id="classifier", next_run_time=datetime.now() + timedelta(minutes=5))
    scheduler.add_job(run_ranker, "cron", hour=3, minute=0, id="ranker")  # 03:00 UTC nightly
    scheduler.add_job(run_missionary_daily, "cron", hour=7, minute=0, id="missionary")  # 07:00 UTC daily
    scheduler.add_job(run_executor, "interval", minutes=15, id="executor", next_run_time=datetime.now() + timedelta(minutes=2))
    scheduler.add_job(run_system_check, "interval", minutes=15,
                      id="status", next_run_time=datetime.now())
    scheduler.add_job(run_daily_report, "cron", hour=6, minute=0, id="daily")

    scheduler.start()

    logger.info("All systems running.")
    logger.info(f"Spiders: GitHub, MCP, npm, PyPI, HuggingFace (every {crawl_interval}h)")
    logger.info("Agents: Parser (30min), Classifier (2h), Ranker (03:00 UTC), Missionary (startup)")
    logger.info("API: http://localhost:8000/v1/")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduler.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
