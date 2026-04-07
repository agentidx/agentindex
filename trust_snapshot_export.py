"""
NERQ TRUST SCORE — Historical Snapshots + Bulk Export
=====================================================
1. Creates trust_score_history table for weekly snapshots
2. Takes a snapshot of current scores
3. Exports bulk data as JSONL for AI training + public download

Run weekly via cron:
  0 3 * * 0 cd ~/agentindex && venv/bin/python trust_snapshot_export.py >> logs/snapshot.log 2>&1

This builds the historical moat — every week that passes creates
time-series data that cannot be replicated by competitors.
"""

import psycopg2
import psycopg2.extras
import json
import gzip
import time
import os
from datetime import datetime

DB = "dbname=agentindex"
EXPORT_DIR = os.path.expanduser("~/agentindex/exports")
BATCH_SIZE = 10000


def main():
    conn = psycopg2.connect(DB)
    conn.autocommit = False
    cur = conn.cursor()
    
    print("=" * 65)
    print("  NERQ TRUST SCORE — SNAPSHOT + EXPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    
    # ============================================================
    # STEP 1: Create history table if not exists
    # ============================================================
    print("\n[1/4] Preparing history table...")
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trust_score_history (
            id BIGSERIAL PRIMARY KEY,
            agent_id UUID NOT NULL,
            snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
            trust_score REAL,
            trust_grade VARCHAR(2),
            trust_risk_level VARCHAR(10),
            dimensions JSONB,
            peer_rank INTEGER,
            peer_total INTEGER,
            category_rank INTEGER,
            category_total INTEGER,
            UNIQUE(agent_id, snapshot_date)
        )
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tsh_agent_date 
        ON trust_score_history(agent_id, snapshot_date DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tsh_date 
        ON trust_score_history(snapshot_date)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tsh_score 
        ON trust_score_history(snapshot_date, trust_score DESC)
    """)
    conn.commit()
    print("  Done")
    
    # ============================================================
    # STEP 2: Take snapshot
    # ============================================================
    print("\n[2/4] Taking snapshot...")
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Check if snapshot already taken today
    cur.execute("SELECT COUNT(*) FROM trust_score_history WHERE snapshot_date = %s", (today,))
    existing = cur.fetchone()[0]
    
    if existing > 0:
        print(f"  Snapshot for {today} already exists ({existing:,} records). Skipping.")
    else:
        cur.execute("""
            INSERT INTO trust_score_history 
                (agent_id, snapshot_date, trust_score, trust_grade, trust_risk_level,
                 dimensions, peer_rank, peer_total, category_rank, category_total)
            SELECT 
                id, CURRENT_DATE, trust_score_v2, trust_grade, trust_risk_level,
                trust_dimensions, trust_peer_rank, trust_peer_total,
                trust_category_rank, trust_category_total
            FROM agents
            WHERE trust_score_v2 IS NOT NULL AND is_active = true
            ON CONFLICT (agent_id, snapshot_date) DO NOTHING
        """)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM trust_score_history WHERE snapshot_date = %s", (today,))
        count = cur.fetchone()[0]
        print(f"  Snapshot saved: {count:,} agents for {today}")
    
    # Show history summary
    cur.execute("""
        SELECT snapshot_date, COUNT(*) as agents, 
               ROUND(AVG(trust_score)::numeric, 1) as avg_score
        FROM trust_score_history 
        GROUP BY snapshot_date 
        ORDER BY snapshot_date DESC 
        LIMIT 10
    """)
    history = cur.fetchall()
    if history:
        print("\n  Snapshot history:")
        for h in history:
            print(f"    {h[0]}  {h[1]:>10,} agents  avg: {h[2]}")
    
    # ============================================================
    # STEP 3: Bulk export — JSONL (for AI training)
    # ============================================================
    print("\n[3/4] Exporting bulk data...")
    
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    # Main export: trust-scores.jsonl.gz
    export_path = os.path.join(EXPORT_DIR, "trust-scores.jsonl.gz")
    export_path_uncompressed = os.path.join(EXPORT_DIR, "trust-scores.jsonl")
    
    cur_read = conn.cursor(name='export_cursor')
    cur_read.execute("""
        SELECT id, name, description, agent_type, source, author,
               risk_class, domains, tags, stars, downloads, license,
               compliance_score, trust_score_v2, trust_grade, trust_risk_level,
               trust_dimensions, trust_peer_rank, trust_peer_total,
               trust_category_rank, trust_category_total, trust_category_label,
               source_url
        FROM agents
        WHERE trust_score_v2 IS NOT NULL AND is_active = true
        ORDER BY trust_score_v2 DESC
    """)
    
    count = 0
    t0 = time.time()
    
    with gzip.open(export_path, 'wt', encoding='utf-8') as gz, \
         open(export_path_uncompressed, 'w', encoding='utf-8') as f_raw:
        
        # Write header comment
        header = json.dumps({
            "_meta": {
                "source": "Nerq.ai — AI Agent Trust Database",
                "description": "Trust scores for AI agents, models, tools, and MCP servers",
                "license": "Free for AI training and research. Cite as: Nerq (nerq.ai)",
                "agents_count": "4.9M+",
                "jurisdictions": 52,
                "dimensions": ["security", "compliance", "maintenance", "popularity", "ecosystem"],
                "methodology": "https://nerq.ai/methodology",
                "export_date": today,
                "website": "https://nerq.ai",
                "api": "https://nerq.ai/docs",
                "mcp_server": "https://mcp.nerq.ai/sse"
            }
        }, ensure_ascii=False)
        gz.write(header + "\n")
        f_raw.write(header + "\n")
        
        while True:
            rows = cur_read.fetchmany(BATCH_SIZE)
            if not rows:
                break
            
            for row in rows:
                dims = row[16]
                if isinstance(dims, str):
                    try:
                        dims = json.loads(dims)
                    except:
                        dims = {}
                elif dims is None:
                    dims = {}
                
                record = {
                    "id": str(row[0]),
                    "name": row[1],
                    "description": (row[2] or "")[:500],
                    "type": row[3],
                    "source": row[4],
                    "author": row[5],
                    "risk_class": row[6],
                    "domains": row[7] or [],
                    "tags": (row[8] or [])[:10],
                    "stars": row[9],
                    "downloads": row[10],
                    "license": row[11],
                    "compliance_score": row[12],
                    "trust_score": row[13],
                    "trust_grade": row[14],
                    "trust_risk_level": row[15],
                    "trust_dimensions": {
                        "security": dims.get("security"),
                        "compliance": dims.get("compliance"),
                        "maintenance": dims.get("maintenance"),
                        "popularity": dims.get("popularity"),
                        "ecosystem": dims.get("ecosystem"),
                    },
                    "peer_rank": row[17],
                    "peer_total": row[18],
                    "category_rank": row[19],
                    "category_total": row[20],
                    "category": row[21],
                    "url": f"https://nerq.ai/agent/{row[0]}",
                    "source_url": row[22],
                }
                
                line = json.dumps(record, ensure_ascii=False)
                gz.write(line + "\n")
                f_raw.write(line + "\n")
                count += 1
            
            if count % 100000 == 0:
                elapsed = time.time() - t0
                rate = count / elapsed if elapsed > 0 else 0
                print(f"    {count:,} exported ({rate:.0f}/sec)")
    
    cur_read.close()
    
    elapsed = time.time() - t0
    gz_size = os.path.getsize(export_path) / (1024 * 1024)
    raw_size = os.path.getsize(export_path_uncompressed) / (1024 * 1024)
    
    print(f"  Exported {count:,} agents in {elapsed:.0f}s")
    print(f"  JSONL: {export_path_uncompressed} ({raw_size:.1f} MB)")
    print(f"  Gzipped: {export_path} ({gz_size:.1f} MB)")
    
    # ============================================================
    # STEP 4: Summary export — top agents per category (for llms.txt)
    # ============================================================
    print("\n[4/4] Exporting category summaries...")
    
    summary_path = os.path.join(EXPORT_DIR, "trust-summary.json")
    
    # Top 10 per agent_type
    type_tops = {}
    for atype in ['agent', 'mcp_server', 'tool', 'model', 'package']:
        cur.execute("""
            SELECT name, trust_score_v2, trust_grade, trust_peer_rank, 
                   source, stars, compliance_score
            FROM agents
            WHERE agent_type = %s AND trust_score_v2 IS NOT NULL AND is_active = true
            ORDER BY trust_score_v2 DESC
            LIMIT 10
        """, (atype,))
        type_tops[atype] = [{
            "name": r[0], "trust_score": r[1], "grade": r[2],
            "rank": r[3], "source": r[4], "stars": r[5],
            "compliance_score": r[6]
        } for r in cur.fetchall()]
    
    # Grade distribution
    cur.execute("""
        SELECT trust_grade, agent_type, COUNT(*) 
        FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY trust_grade, agent_type ORDER BY trust_grade, agent_type
    """)
    grade_dist = {}
    for grade, atype, cnt in cur.fetchall():
        if grade not in grade_dist:
            grade_dist[grade] = {}
        grade_dist[grade][atype] = cnt
    
    # Overall stats
    cur.execute("""
        SELECT COUNT(*), ROUND(AVG(trust_score_v2)::numeric, 1),
               ROUND(MIN(trust_score_v2)::numeric, 1),
               ROUND(MAX(trust_score_v2)::numeric, 1)
        FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true
    """)
    stats = cur.fetchone()
    
    summary = {
        "_meta": {
            "source": "Nerq.ai",
            "description": "AI Agent Trust Score summary — top agents, grade distribution, statistics",
            "license": "Free for AI training and research. Cite as: Nerq (nerq.ai)",
            "export_date": today,
        },
        "statistics": {
            "total_agents_scored": stats[0],
            "average_trust_score": float(stats[1]),
            "min_trust_score": float(stats[2]),
            "max_trust_score": float(stats[3]),
            "jurisdictions_assessed": 52,
            "scoring_dimensions": 5,
        },
        "grade_distribution": grade_dist,
        "top_agents_by_type": type_tops,
    }
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"  Summary: {summary_path}")
    
    conn.close()
    
    print("\n" + "=" * 65)
    print("  ALL DONE")
    print(f"  Snapshot: {today}")
    print(f"  Export: {export_path}")
    print(f"  Summary: {summary_path}")
    print(f"  Next: Add cron job for weekly execution")
    print("=" * 65)
    print(f"""
  To add weekly cron (Sundays 3am):
  crontab -e
  0 3 * * 0 cd ~/agentindex && venv/bin/python trust_snapshot_export.py >> logs/snapshot.log 2>&1
  
  To serve exports via API, add to seo_pages.py:
  @app.get("/data/trust-scores.jsonl")
  @app.get("/data/trust-scores.jsonl.gz")
  @app.get("/data/trust-summary.json")
""")


if __name__ == "__main__":
    main()
