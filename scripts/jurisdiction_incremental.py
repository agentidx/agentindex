#!/usr/bin/env python3
"""
Jurisdiction Incremental Update — daily at 03:00 CET.
Updates assessments for agents whose trust data changed in last 24h.
"""
import logging, os, sys, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [juris-incr] %(message)s",
    handlers=[logging.FileHandler(os.path.expanduser('~/agentindex/logs/jurisdiction_incremental.log')),
              logging.StreamHandler()])
log = logging.getLogger("juris-incr")

def run():
    import psycopg2, psycopg2.extras, json
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

    # Get agents updated in last 24h
    cur.execute("""
        SELECT id, risk_class, agent_type, domains, name, description
        FROM agents
        WHERE risk_class IS NOT NULL
          AND (trust_calculated_at > now() - interval '24 hours'
               OR last_crawled > now() - interval '24 hours')
        ORDER BY id
    """)
    agents = cur.fetchall()
    log.info(f"Agents to update: {len(agents)} (changed in last 24h)")

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
    log.info(f"COMPLETE: {updated} agents × {len(jurisdictions)} jurisdictions updated")

if __name__ == "__main__":
    run()
