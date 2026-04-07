"""
NERQ TRUST SCORE v2.1 — REGRADE + PEER RANK
=============================================
Updates from v2.0:
1. "No data ≠ bad" — neutral values replaced with type medians
2. Peer rank — global rank within agent_type
3. Category rank — rank within primary domain + agent_type
4. Grade thresholds unchanged (absolute, universal)

Run AFTER compute_trust_score.py v2.0 has completed.
This script re-scores dimensions where neutral defaults were used,
then computes ranks. ~15-20 min for 4.9M agents.
"""

import psycopg2
import psycopg2.extras
import json
import time
import sys
from datetime import datetime

DB = "dbname=agentindex"
BATCH_SIZE = 5000

# ================================================================
# GRADE THRESHOLDS (unchanged — absolute, universal)
# ================================================================
def compute_grade(score):
    if score >= 90: return 'A+'
    if score >= 80: return 'A'
    if score >= 70: return 'B'
    if score >= 60: return 'C'
    if score >= 45: return 'D'
    if score >= 30: return 'E'
    return 'F'

def compute_risk(score):
    if score >= 70: return 'low'
    if score >= 50: return 'medium'
    if score >= 30: return 'high'
    return 'critical'

# Dimension weights (unchanged)
WEIGHTS = {
    'security': 0.30,
    'compliance': 0.25,
    'maintenance': 0.20,
    'popularity': 0.15,
    'ecosystem': 0.10,
}

def main():
    conn = psycopg2.connect(DB)
    conn.autocommit = False
    
    print("=" * 65)
    print("  NERQ TRUST SCORE v2.1 — REGRADE + PEER RANK")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    
    # ============================================================
    # STEP 1: Add new columns if not exist
    # ============================================================
    print("\n[1/5] Preparing columns...")
    cur = conn.cursor()
    for col, typ in [
        ("trust_peer_rank", "INTEGER"),
        ("trust_peer_total", "INTEGER"),
        ("trust_category_rank", "INTEGER"),
        ("trust_category_total", "INTEGER"),
        ("trust_category_label", "VARCHAR(100)"),
    ]:
        try:
            cur.execute(f"ALTER TABLE agents ADD COLUMN {col} {typ}")
            print(f"  Added {col}")
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()
            print(f"  {col} exists")
    conn.commit()
    print("  Done")
    
    # ============================================================
    # STEP 2: Compute median scores per agent_type for each dimension
    # ============================================================
    print("\n[2/5] Computing type medians for neutral value replacement...")
    cur.execute("""
        SELECT agent_type,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY trust_score_v2) as median_total,
               COUNT(*) as cnt
        FROM agents
        WHERE trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY agent_type
    """)
    type_medians_total = {}
    for row in cur.fetchall():
        type_medians_total[row[0]] = {'median': float(row[1]), 'count': int(row[2])}
    
    # Get per-dimension medians by sampling agents WITH real data per type
    # For maintenance: agents that have last_source_update
    # For popularity: agents that have stars > 0 or downloads > 0
    # For security: agents that have license not null
    
    cur.execute("""
        SELECT agent_type,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY 
                   (trust_dimensions->>'maintenance')::float
               ) as median_maintenance
        FROM agents
        WHERE trust_dimensions->>'maintenance' IS NOT NULL
          AND last_source_update IS NOT NULL
          AND is_active = true
        GROUP BY agent_type
    """)
    type_maint_medians = {r[0]: float(r[1]) for r in cur.fetchall()}
    
    cur.execute("""
        SELECT agent_type,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY 
                   (trust_dimensions->>'popularity')::float
               ) as median_popularity
        FROM agents
        WHERE trust_dimensions->>'popularity' IS NOT NULL
          AND (stars > 0 OR downloads > 0)
          AND is_active = true
        GROUP BY agent_type
    """)
    type_pop_medians = {r[0]: float(r[1]) for r in cur.fetchall()}
    
    cur.execute("""
        SELECT agent_type,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY 
                   (trust_dimensions->>'security')::float
               ) as median_security
        FROM agents
        WHERE trust_dimensions->>'security' IS NOT NULL
          AND license IS NOT NULL AND license != 'NOASSERTION'
          AND is_active = true
        GROUP BY agent_type
    """)
    type_sec_medians = {r[0]: float(r[1]) for r in cur.fetchall()}
    
    print("  Type medians (maintenance / popularity / security):")
    all_types = set(list(type_maint_medians.keys()) + list(type_pop_medians.keys()) + list(type_sec_medians.keys()))
    for t in sorted(all_types):
        m = type_maint_medians.get(t, '-')
        p = type_pop_medians.get(t, '-')
        s = type_sec_medians.get(t, '-')
        cnt = type_medians_total.get(t, {}).get('count', 0)
        if m != '-': m = f"{m:.1f}"
        if p != '-': p = f"{p:.1f}"
        if s != '-': s = f"{s:.1f}"
        print(f"    {t or 'unknown':<20} maint:{m:>6}  pop:{p:>6}  sec:{s:>6}  (n={cnt:,})")
    
    # ============================================================
    # STEP 3: Re-score agents with adjusted neutral values
    # ============================================================
    print(f"\n[3/5] Re-scoring with type-aware neutral values...")
    
    cur2 = conn.cursor()
    
    total = cur.execute("SELECT COUNT(*) FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true")
    total = cur.fetchone()[0]
    
    updated = 0
    offset = 0
    t0 = time.time()
    
    while True:
        cur.execute("""
            SELECT id, agent_type, trust_dimensions,
                   last_source_update, stars, downloads, license
            FROM agents
            WHERE trust_score_v2 IS NOT NULL AND is_active = true
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (BATCH_SIZE, offset))
        
        rows = cur.fetchall()
        if not rows:
            break
        
        batch_updates = []
        
        for row in rows:
            agent_id, agent_type, dims_raw, last_update, stars, downloads, lic = row
            
            if not dims_raw:
                continue
            
            dims = dims_raw if isinstance(dims_raw, dict) else json.loads(dims_raw)
            
            changed = False
            new_dims = dict(dims)
            
            # Check if maintenance used default neutral (40)
            # If agent has no last_source_update AND maintenance is exactly 40.0
            if last_update is None and abs(dims.get('maintenance', 0) - 40.0) < 0.1:
                median_m = type_maint_medians.get(agent_type, 40.0)
                new_dims['maintenance'] = round(median_m, 1)
                changed = True
            
            # Check if popularity used default neutral (30)
            # If agent has no stars AND no downloads AND popularity is exactly 30.0
            if (not stars or stars == 0) and (not downloads or downloads == 0) and abs(dims.get('popularity', 0) - 30.0) < 0.1:
                median_p = type_pop_medians.get(agent_type, 30.0)
                new_dims['popularity'] = round(median_p, 1)
                changed = True
            
            # Check if security used baseline default
            # If agent has no license AND security baseline was ~50
            if (not lic or lic == 'NOASSERTION') and abs(dims.get('security', 0) - 50.0) < 5.0:
                median_s = type_sec_medians.get(agent_type)
                if median_s and abs(dims.get('security', 0) - 50.0) < 0.1:
                    # Only replace exact baseline (50.0), not ones adjusted by other rules
                    new_dims['security'] = round(median_s, 1)
                    changed = True
            
            if changed:
                # Recompute total score
                new_score = (
                    new_dims.get('security', dims.get('security', 50)) * WEIGHTS['security'] +
                    new_dims.get('compliance', dims.get('compliance', 40)) * WEIGHTS['compliance'] +
                    new_dims.get('maintenance', dims.get('maintenance', 40)) * WEIGHTS['maintenance'] +
                    new_dims.get('popularity', dims.get('popularity', 30)) * WEIGHTS['popularity'] +
                    new_dims.get('ecosystem', dims.get('ecosystem', 30)) * WEIGHTS['ecosystem']
                )
                new_score = round(max(0, min(100, new_score)), 1)
                new_grade = compute_grade(new_score)
                new_risk = compute_risk(new_score)
                
                batch_updates.append((
                    new_score, new_grade, new_risk, json.dumps(new_dims),
                    agent_id
                ))
        
        if batch_updates:
            cur2.executemany("""
                UPDATE agents SET
                    trust_score_v2 = %s,
                    trust_grade = %s,
                    trust_risk_level = %s,
                    trust_dimensions = %s,
                    trust_scored_at = NOW()
                WHERE id = %s
            """, batch_updates)
        
        updated += len(batch_updates)
        offset += BATCH_SIZE
        
        elapsed = time.time() - t0
        rate = offset / elapsed if elapsed > 0 else 0
        eta = (total - offset) / rate if rate > 0 else 0
        
        sys.stdout.write(f"\r   {offset:,} / {total:,} ({offset/total*100:.1f}%) | {rate:.0f}/sec | changed: {updated:,} | ETA {eta/60:.1f}min")
        sys.stdout.flush()
        
        if offset % 50000 == 0:
            conn.commit()
    
    conn.commit()
    print(f"\n  Re-scored {updated:,} agents")
    
    # ============================================================
    # STEP 4: Compute peer rank (within agent_type)
    # ============================================================
    print(f"\n[4/5] Computing peer ranks...")
    
    for agent_type, info in sorted(type_medians_total.items(), key=lambda x: -x[1]['count']):
        type_count = info['count']
        cur.execute("""
            UPDATE agents a SET
                trust_peer_rank = sub.rank,
                trust_peer_total = %s
            FROM (
                SELECT id, 
                       ROW_NUMBER() OVER (ORDER BY trust_score_v2 DESC, stars DESC NULLS LAST) as rank
                FROM agents
                WHERE agent_type = %s AND trust_score_v2 IS NOT NULL AND is_active = true
            ) sub
            WHERE a.id = sub.id
        """, (type_count, agent_type))
        conn.commit()
        print(f"  {agent_type or 'unknown':<20} {type_count:>10,} agents ranked")
    
    # ============================================================
    # STEP 5: Compute category rank (within primary domain + agent_type)
    # ============================================================
    print(f"\n[5/5] Computing category ranks...")
    
    # Get all domain + type combos with at least 5 agents
    cur.execute("""
        SELECT domains[1] as primary_domain, agent_type, COUNT(*) as cnt
        FROM agents
        WHERE domains IS NOT NULL AND array_length(domains, 1) > 0
          AND trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY domains[1], agent_type
        HAVING COUNT(*) >= 5
        ORDER BY cnt DESC
    """)
    
    categories = cur.fetchall()
    print(f"  {len(categories)} categories to rank")
    
    cat_count = 0
    for domain, agent_type, cnt in categories:
        label = f"{domain} {agent_type}s" if agent_type else f"{domain}"
        
        cur.execute("""
            UPDATE agents a SET
                trust_category_rank = sub.rank,
                trust_category_total = %s,
                trust_category_label = %s
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (ORDER BY trust_score_v2 DESC, stars DESC NULLS LAST) as rank
                FROM agents
                WHERE domains[1] = %s AND agent_type = %s
                  AND trust_score_v2 IS NOT NULL AND is_active = true
            ) sub
            WHERE a.id = sub.id
        """, (cnt, label, domain, agent_type))
        
        cat_count += 1
        if cat_count % 20 == 0:
            conn.commit()
            sys.stdout.write(f"\r  {cat_count} / {len(categories)} categories done")
            sys.stdout.flush()
    
    conn.commit()
    print(f"\r  {cat_count} / {len(categories)} categories done")
    
    # ============================================================
    # RESULTS
    # ============================================================
    print("\n" + "=" * 65)
    
    # New grade distribution
    cur.execute("""
        SELECT trust_grade, COUNT(*) as cnt
        FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY trust_grade ORDER BY trust_grade
    """)
    grades = cur.fetchall()
    total_scored = sum(g[1] for g in grades)
    
    print(f"  RESULTS — {total_scored:,} agents")
    print("=" * 65)
    
    print("\n  -- New Grade Distribution --")
    for grade, cnt in grades:
        pct = cnt / total_scored * 100
        bar = '#' * int(pct / 2)
        print(f"    {grade:>2}: {cnt:>10,} ({pct:>5.1f}%) {bar}")
    
    # Per-type averages
    cur.execute("""
        SELECT agent_type, COUNT(*) as cnt,
               ROUND(AVG(trust_score_v2)::numeric, 1) as avg,
               ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY trust_score_v2)::numeric, 1) as p25,
               ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY trust_score_v2)::numeric, 1) as p50,
               ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY trust_score_v2)::numeric, 1) as p75
        FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY agent_type ORDER BY cnt DESC
    """)
    print("\n  -- Per-Type Distribution (after fix) --")
    print(f"    {'Type':<20} {'Count':>10} {'Avg':>6} {'P25':>6} {'P50':>6} {'P75':>6}")
    for r in cur.fetchall():
        print(f"    {r[0] or 'unknown':<20} {r[1]:>10,} {r[2]:>6} {r[3]:>6} {r[4]:>6} {r[5]:>6}")
    
    # Top 15
    cur.execute("""
        SELECT trust_grade, trust_score_v2, name, agent_type,
               trust_peer_rank, trust_peer_total,
               trust_category_rank, trust_category_total, trust_category_label
        FROM agents
        WHERE trust_score_v2 IS NOT NULL AND is_active = true
        ORDER BY trust_score_v2 DESC LIMIT 15
    """)
    print("\n  -- Top 15 (with ranks) --")
    for i, r in enumerate(cur.fetchall(), 1):
        grade, score, name, atype, pr, pt, cr, ct, cl = r
        peer = f"#{pr:,} of {pt:,} {atype}s" if pr else ""
        cat = f"#{cr} of {ct} {cl}" if cr else ""
        print(f"    {i:>2}. {grade:>2} {score:>5.1f}  {name:<40} {peer:<30} {cat}")
    
    # Sample: show some MCP servers with ranks
    cur.execute("""
        SELECT trust_grade, trust_score_v2, name,
               trust_peer_rank, trust_peer_total,
               trust_category_rank, trust_category_total, trust_category_label
        FROM agents
        WHERE agent_type = 'mcp_server' AND trust_score_v2 IS NOT NULL AND is_active = true
        ORDER BY trust_score_v2 DESC LIMIT 10
    """)
    print("\n  -- Top 10 MCP Servers (with ranks) --")
    for i, r in enumerate(cur.fetchall(), 1):
        grade, score, name, pr, pt, cr, ct, cl = r
        peer = f"#{pr:,} of {pt:,} mcp_servers" if pr else ""
        cat = f"#{cr} of {ct} {cl}" if cr else ""
        print(f"    {i:>2}. {grade:>2} {score:>5.1f}  {name:<40} {peer:<30} {cat}")
    
    # Create indexes
    print("\n  Creating indexes...")
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_trust_peer_rank ON agents(agent_type, trust_peer_rank) WHERE trust_peer_rank IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_trust_cat_rank ON agents(trust_category_label, trust_category_rank) WHERE trust_category_rank IS NOT NULL",
    ]:
        cur.execute(idx)
    conn.commit()
    
    elapsed_total = time.time() - t0
    print(f"\n  DONE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({elapsed_total/60:.1f} min)")
    print("=" * 65)
    
    conn.close()

if __name__ == "__main__":
    main()
