#!/usr/bin/env python3
"""
Jurisdiction Incremental Update — daily at 03:00 CET.
Updates assessments for agents whose trust or crawl data changed in last 25h.

Hybrid F strategy (2026-04-20):
  - WHERE: trust_calculated_at > 25h OR last_crawled > 25h (no risk_class filter)
  - ntfy alert if 0 agents found 3 consecutive days
"""
import logging, os, sys, json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [juris-incr] %(message)s",
    handlers=[logging.FileHandler(os.path.expanduser('~/agentindex/logs/jurisdiction_incremental.log')),
              logging.StreamHandler()])
log = logging.getLogger("juris-incr")

ZERO_STREAK_FILE = os.path.expanduser("~/agentindex/logs/.juris_incr_zero_streak")
NTFY_TOPIC = "nerq-alerts"


def _check_zero_streak(agents_found: int):
    """Track consecutive days with 0 agents. Alert via ntfy after 3."""
    import urllib.request
    if agents_found > 0:
        if os.path.exists(ZERO_STREAK_FILE):
            os.remove(ZERO_STREAK_FILE)
        return

    streak = 0
    if os.path.exists(ZERO_STREAK_FILE):
        try:
            streak = int(Path(ZERO_STREAK_FILE).read_text().strip())
        except (ValueError, OSError):
            streak = 0
    streak += 1
    Path(ZERO_STREAK_FILE).write_text(str(streak))
    log.warning(f"Zero-agent streak: {streak} consecutive runs")

    if streak >= 3:
        msg = (f"juris-incremental: 0 agents found for {streak} consecutive runs. "
               f"Crawl and trust pipelines may both be stalled.")
        log.error(msg)
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                data=msg.encode(),
                headers={"Title": "Jurisdiction Incremental: Pipeline Stall",
                          "Priority": "high", "Tags": "warning"})
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            log.error(f"ntfy send failed: {e}")


def run():
    import psycopg2, psycopg2.extras
    from multi_jurisdiction_assess import assess_agent_jurisdiction

    conn = psycopg2.connect("host=100.119.193.70 port=5432 dbname=agentindex user=anstudio")
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET statement_timeout = '0'")

    # Get jurisdictions
    cur.execute("SELECT id, name, country, risk_model, high_risk_criteria FROM jurisdiction_registry")
    jurisdictions = [dict(zip(['id','name','country','risk_model','high_risk_criteria'], r)) for r in cur.fetchall()]
    for j in jurisdictions:
        if isinstance(j['high_risk_criteria'], str):
            try: j['high_risk_criteria'] = json.loads(j['high_risk_criteria'])
            except: j['high_risk_criteria'] = {}

    # Hybrid F: 25h window, no risk_class filter (crawled agents lack risk_class)
    cur.execute("""
        SELECT id, risk_class, agent_type, domains, name, description
        FROM agents
        WHERE trust_calculated_at > now() - interval '25 hours'
           OR last_crawled > now() - interval '25 hours'
        ORDER BY id
    """)
    agents = cur.fetchall()
    log.info(f"Agents to update: {len(agents)} (changed in last 25h)")

    _check_zero_streak(len(agents))

    if not agents:
        log.info("No agents changed. Done.")
        conn.close()
        return

    updated = 0
    for agent_id, risk_class, agent_type, domains, name, desc in agents:
        vals = []
        for j in jurisdictions:
            status, risk_level, triggered, notes = assess_agent_jurisdiction(
                risk_class, agent_type, domains, name, desc, j
            )
            vals.append((agent_id, j['id'], status, risk_level, triggered, notes, datetime.now()))

        # Upsert: delete old + insert new for this agent
        cur.execute("DELETE FROM agent_jurisdiction_status WHERE agent_id = %s", (agent_id,))
        psycopg2.extras.execute_values(cur, """
            INSERT INTO agent_jurisdiction_status
            (agent_id, jurisdiction_id, status, risk_level, triggered_criteria, compliance_notes, assessed_at)
            VALUES %s
        """, vals, page_size=100)
        updated += 1

        if updated % 100 == 0:
            conn.commit()
            log.info(f"Progress: {updated}/{len(agents)} agents updated")

    conn.commit()
    conn.close()
    log.info(f"COMPLETE: {updated} agents x {len(jurisdictions)} jurisdictions updated")

if __name__ == "__main__":
    run()
