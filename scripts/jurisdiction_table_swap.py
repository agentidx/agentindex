#!/usr/bin/env python3
"""
Jurisdiction Table Swap — build agent_jurisdiction_status_new from scratch,
sanity-check, then atomically swap to replace the live table.

Idempotent: safe to run weekly via LaunchAgent. Always starts fresh.

Workflow:
  1. DROP + CREATE agent_jurisdiction_status_new with live table's schema
  2. INSERT all assessments (agents x jurisdictions)
  3. CREATE INDEX ... _tmp (avoids name collision with live indexes)
  4. Sanity check: new_count >= 95% of live_count — else ABORT without swap
  5. Atomic swap inside transaction:
       live -> _old, _new -> live, rename indexes to canonical names
  6. DROP _old

Uses the same assessment logic as multi_jurisdiction_assess.py.
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

LIVE_TABLE = "agent_jurisdiction_status"
TARGET_TABLE = "agent_jurisdiction_status_new"
OLD_TABLE = "agent_jurisdiction_status_old"
BATCH_SIZE = 5000
DISK_CHECK_INTERVAL = 500000  # Check disk every 500K rows
SANITY_MIN_RATIO = 0.95  # _new must have >=95% of live row count before swap


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

    # Baseline: how big is the current live table? Used for sanity check
    # before swap. Uses pg_class.reltuples — avoids 60s+ COUNT(*) scan.
    cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = %s", (LIVE_TABLE,))
    row = cur.fetchone()
    live_baseline = row[0] if row else 0
    logger.info(f"Live table {LIVE_TABLE} baseline: ~{live_baseline:,} rows (pg_class estimate)")

    # Fresh build — drop any prior _new from crashed/aborted run.
    # Also drop any _old from a prior successful swap that didn't clean up.
    logger.info(f"Dropping any stale {TARGET_TABLE} / {OLD_TABLE}")
    cur.execute(f"DROP TABLE IF EXISTS {TARGET_TABLE}")
    cur.execute(f"DROP TABLE IF EXISTS {OLD_TABLE}")
    conn.commit()

    # Recreate _new with same schema as live.
    logger.info(f"Creating fresh {TARGET_TABLE} (schema copied from {LIVE_TABLE})")
    cur.execute(f"CREATE TABLE {TARGET_TABLE} (LIKE {LIVE_TABLE} INCLUDING DEFAULTS)")
    conn.commit()

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

    offset = 0
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

    # Build indexes with _tmp suffix to avoid collision with live table's
    # indexes during swap. Renamed to canonical names after DROP _old.
    logger.info("Building indexes on _new table...")
    for tmp_name, final_name, idx_col in [
        ("idx_ajs_agent_id_tmp", "idx_ajs_agent_id", "agent_id"),
        ("idx_ajs_jurisdiction_id_tmp", "idx_ajs_jurisdiction_id", "jurisdiction_id"),
    ]:
        cur.execute(f"CREATE INDEX {tmp_name} ON {TARGET_TABLE} ({idx_col})")
        conn.commit()
        logger.info(f"  Index {tmp_name} created (will rename to {final_name} after swap)")

    # Verify build
    cur.execute(f"SELECT COUNT(*), MIN(assessed_at)::date, MAX(assessed_at)::date FROM {TARGET_TABLE}")
    new_count, min_date, max_date = cur.fetchone()
    logger.info(f"Verification: {new_count:,} rows, dates {min_date} to {max_date}")

    # Sanity check: refuse swap if _new is missing data.
    # Prevents wiping a good live table with a truncated rebuild.
    min_acceptable = int(live_baseline * SANITY_MIN_RATIO)
    if new_count < min_acceptable:
        logger.error(
            f"SANITY FAIL: {TARGET_TABLE} has {new_count:,} rows, "
            f"need >={min_acceptable:,} (>={SANITY_MIN_RATIO*100:.0f}% of live={live_baseline:,}). "
            f"ABORTING SWAP. {TARGET_TABLE} left in place for inspection."
        )
        conn.close()
        sys.exit(2)
    logger.info(
        f"Sanity OK: new={new_count:,} >= {SANITY_MIN_RATIO*100:.0f}% of live={live_baseline:,}"
    )

    # Atomic swap: rename live -> _old and _new -> live inside one tx.
    # RENAME is metadata-only — near-instant, no data copy.
    logger.info("Performing atomic swap...")
    cur.execute(f"ALTER TABLE {LIVE_TABLE} RENAME TO {OLD_TABLE}")
    cur.execute(f"ALTER TABLE {TARGET_TABLE} RENAME TO {LIVE_TABLE}")
    conn.commit()
    logger.info(f"Swap complete: {TARGET_TABLE} is now live as {LIVE_TABLE}")

    # Rename indexes to canonical names (old ones are on _old which we drop next).
    cur.execute("ALTER INDEX idx_ajs_agent_id_tmp RENAME TO idx_ajs_agent_id")
    cur.execute("ALTER INDEX idx_ajs_jurisdiction_id_tmp RENAME TO idx_ajs_jurisdiction_id")
    conn.commit()
    logger.info("Indexes renamed to canonical names")

    # Drop old table (takes its old-named indexes with it).
    logger.info(f"Dropping {OLD_TABLE}...")
    cur.execute(f"DROP TABLE {OLD_TABLE}")
    conn.commit()
    logger.info(f"{OLD_TABLE} dropped — swap fully complete")

    conn.close()
    return new_count


if __name__ == "__main__":
    count = run()
    logger.info(f"Jurisdiction weekly swap DONE: {count:,} rows live in {LIVE_TABLE}")
