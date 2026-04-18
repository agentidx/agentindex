#!/usr/bin/env python3
"""
Jurisdiction Table Swap — populate agent_jurisdiction_status_new,
then atomically rename to replace the live table.

Uses the same assessment logic as multi_jurisdiction_assess.py
but writes to a _new table for zero-downtime swap.
"""

import psycopg2, psycopg2.extras, json, logging, os, sys, time, subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [juris-swap] %(message)s",
    handlers=[logging.FileHandler(os.path.expanduser('~/agentindex/logs/jurisdiction_swap.log')),
              logging.StreamHandler()])
logger = logging.getLogger("juris-swap")

from agentindex.db_config import get_write_dsn

# Import the assessment function from the original script
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from multi_jurisdiction_assess import assess_agent_jurisdiction, create_table

TARGET_TABLE = "agent_jurisdiction_status_new"
BATCH_SIZE = 5000
DISK_CHECK_INTERVAL = 500000  # Check disk every 500K rows


def check_disk():
    """Check Nbg disk — abort if < 10% free."""
    try:
        result = subprocess.run(
            ["ssh", "root@100.119.193.70", "df / | tail -1 | awk '{print $5}'"],
            capture_output=True, text=True, timeout=10
        )
        pct = int(result.stdout.strip().rstrip('%'))
        return pct
    except Exception:
        return 50  # Assume OK if check fails


def run():
    # Connect directly to Nbg primary (bypass PgBouncer — transaction mode
    # resets SET after each commit, causing statement_timeout to revert)
    dsn = "host=100.119.193.70 port=5432 dbname=agentindex user=anstudio"
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()

    # Set generous timeout for this long-running operation
    cur.execute("SET statement_timeout = '0'")

    # Get jurisdictions
    cur.execute("SELECT id, name, country, risk_model, high_risk_criteria FROM jurisdiction_registry")
    jurisdictions = [dict(zip(['id','name','country','risk_model','high_risk_criteria'], r)) for r in cur.fetchall()]
    j_count = len(jurisdictions)
    logger.info(f"Loaded {j_count} jurisdictions")

    # Parse high_risk_criteria JSON
    for j in jurisdictions:
        if isinstance(j['high_risk_criteria'], str):
            try:
                j['high_risk_criteria'] = json.loads(j['high_risk_criteria'])
            except Exception:
                j['high_risk_criteria'] = {}

    # Get total agent count
    cur.execute("SELECT COUNT(*) FROM agents WHERE risk_class IS NOT NULL")
    total_agents = cur.fetchone()[0]
    logger.info(f"Agents to assess: {total_agents:,} x {j_count} = {total_agents * j_count:,} assessments")

    # Check existing rows to resume from crash
    cur.execute(f"SELECT COUNT(*) FROM {TARGET_TABLE}")
    existing = cur.fetchone()[0]
    if existing > 0:
        # Resume: skip agents already processed
        offset = existing // j_count
        logger.info(f"RESUMING from {existing:,} existing rows (offset {offset:,})")
    else:
        offset = 0
        logger.info("Starting fresh")
    total_inserted = 0
    start_time = time.time()

    while True:
        cur.execute("""
            SELECT id, risk_class, agent_type, domains, name, description
            FROM agents
            WHERE risk_class IS NOT NULL
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (BATCH_SIZE, offset))

        agents = cur.fetchall()
        if not agents:
            break

        insert_vals = []
        for agent_id, risk_class, agent_type, domains, name, desc in agents:
            for j in jurisdictions:
                status, risk_level, triggered, notes = assess_agent_jurisdiction(
                    risk_class, agent_type, domains, name, desc, j
                )
                insert_vals.append((
                    agent_id, j['id'], status, risk_level,
                    triggered, notes, datetime.now()
                ))

        psycopg2.extras.execute_values(cur, f"""
            INSERT INTO {TARGET_TABLE}
            (agent_id, jurisdiction_id, status, risk_level, triggered_criteria, compliance_notes, assessed_at)
            VALUES %s
        """, insert_vals, page_size=10000)
        conn.commit()

        total_inserted += len(insert_vals)
        offset += BATCH_SIZE
        elapsed = time.time() - start_time
        agents_done = min(offset, total_agents)
        rate = agents_done / elapsed if elapsed > 0 else 0
        eta = (total_agents - agents_done) / rate if rate > 0 else 0

        logger.info(f"Progress: {agents_done:,}/{total_agents:,} agents "
                     f"({total_inserted:,} rows, "
                     f"{rate:.0f} agents/sec, ETA: {eta/60:.1f}min)")

        # Disk check
        if total_inserted % DISK_CHECK_INTERVAL < len(insert_vals):
            disk_pct = check_disk()
            if disk_pct > 90:
                logger.error(f"DISK CRITICAL: {disk_pct}% used — ABORTING")
                cur.execute(f"TRUNCATE {TARGET_TABLE}")
                conn.commit()
                conn.close()
                sys.exit(1)
            logger.info(f"Disk check: {disk_pct}% used — OK")

    elapsed = time.time() - start_time
    logger.info(f"COMPLETE: {total_inserted:,} rows in {elapsed/60:.1f} min")

    # Verify
    cur.execute(f"SELECT COUNT(*), MIN(assessed_at)::date, MAX(assessed_at)::date FROM {TARGET_TABLE}")
    count, min_date, max_date = cur.fetchone()
    logger.info(f"Verification: {count:,} rows, dates {min_date} to {max_date}")

    conn.close()
    return count


if __name__ == "__main__":
    count = run()
    logger.info(f"Table swap ready: {count:,} rows in {TARGET_TABLE}")
    logger.info("Run RENAME manually after verification.")
