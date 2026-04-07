"""
NERQ TRUST SCORE v2.2 — CONTENT TYPE ENHANCEMENT
=================================================
Extracts rich signals from HuggingFace tags and metadata to 
differentiate 4.6M models/spaces/datasets.

New signals parsed from tags:
  - license:* → Security dimension
  - arxiv:* → Quality/research signal → Security (documentation proxy)
  - dataset:* → Ecosystem (data lineage)
  - base_model:* → Ecosystem (dependency/lineage)
  - Framework tags (safetensors, pytorch, transformers, etc) → Ecosystem
  - Language tags (en, ja, zh, etc) → Ecosystem (internationalization)
  
Enhanced popularity scoring:
  - Downloads with better logarithmic curve for HF scale
  - Tag count as documentation quality proxy

Run AFTER v2.1. Only re-scores content types (model, space, dataset).
~15-20 min for 4.6M agents.
"""

import psycopg2
import json
import time
import sys
import math
from datetime import datetime

DB = "dbname=agentindex"
BATCH_SIZE = 5000

# Grade thresholds (unchanged — absolute, universal)
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

WEIGHTS = {
    'security': 0.30,
    'compliance': 0.25,
    'maintenance': 0.20,
    'popularity': 0.15,
    'ecosystem': 0.10,
}

# ================================================================
# TAG PARSING RULES
# ================================================================

FRAMEWORK_TAGS = {
    'transformers', 'pytorch', 'tensorflow', 'jax', 'flax', 'safetensors',
    'onnx', 'openvino', 'coreml', 'gguf', 'gptq', 'awq', 'ct2',
    'keras', 'paddlepaddle', 'spacy', 'flair', 'stanza', 'fastai',
    'scikit-learn', 'timm', 'diffusers', 'peft', 'trl', 'accelerate',
    'sentence-transformers', 'setfit', 'span-marker', 'adapters',
    'gradio', 'streamlit', 'docker', 'static',
}

LANGUAGE_CODES = {
    'en', 'zh', 'ja', 'ko', 'fr', 'de', 'es', 'pt', 'ru', 'ar',
    'hi', 'it', 'nl', 'pl', 'tr', 'vi', 'th', 'id', 'sv', 'da',
    'no', 'fi', 'cs', 'ro', 'hu', 'el', 'he', 'uk', 'bg', 'hr',
    'sk', 'sl', 'lt', 'lv', 'et', 'mt', 'ga', 'ca', 'eu', 'gl',
    'multilingual', 'multi', 'code',
}

SDK_QUALITY = {
    'gradio': 8,
    'streamlit': 7,
    'docker': 6,
    'static': 3,
}


def parse_tags(tags):
    """Extract structured signals from HuggingFace tags."""
    if not tags:
        return {}
    
    signals = {
        'has_license': False,
        'license_type': None,
        'has_arxiv': False,
        'arxiv_count': 0,
        'has_dataset_ref': False,
        'dataset_count': 0,
        'has_base_model': False,
        'frameworks': [],
        'languages': [],
        'tag_count': len(tags),
        'has_region': False,
    }
    
    for tag in tags:
        tag_lower = tag.lower().strip()
        
        if tag_lower.startswith('license:'):
            signals['has_license'] = True
            signals['license_type'] = tag_lower.split(':', 1)[1]
        elif tag_lower.startswith('arxiv:'):
            signals['has_arxiv'] = True
            signals['arxiv_count'] += 1
        elif tag_lower.startswith('dataset:'):
            signals['has_dataset_ref'] = True
            signals['dataset_count'] += 1
        elif tag_lower.startswith('base_model:'):
            signals['has_base_model'] = True
        elif tag_lower in FRAMEWORK_TAGS:
            signals['frameworks'].append(tag_lower)
        elif tag_lower in LANGUAGE_CODES:
            signals['languages'].append(tag_lower)
        elif tag_lower.startswith('region:'):
            signals['has_region'] = True
    
    return signals


def score_content_agent(agent_type, dims, downloads, stars, tags, pipeline_tag, sdk, tag_signals):
    """Re-score a content-type agent using enhanced signals."""
    
    new_dims = dict(dims)
    
    # ──────────────────────────────────────
    # SECURITY (enhanced with tag-parsed license + arxiv)
    # ──────────────────────────────────────
    sec = dims.get('security', 50.0)
    
    # License from tags (many HF models have license in tags but not in license field)
    if tag_signals.get('has_license'):
        lic = tag_signals.get('license_type', '')
        permissive = ['mit', 'apache-2.0', 'bsd-2-clause', 'bsd-3-clause', 'cc-by-4.0',
                       'cc-by-sa-4.0', 'openrail', 'openrail++', 'bigscience-openrail-m',
                       'llama2', 'llama3', 'llama3.1', 'llama3.2', 'gemma']
        restrictive = ['cc-by-nc-4.0', 'cc-by-nc-sa-4.0', 'cc-by-nc-nd-4.0',
                        'gpl-3.0', 'agpl-3.0']
        
        if any(p in lic for p in permissive):
            sec = max(sec, 65)  # Permissive license = good
        elif any(r in lic for r in restrictive):
            sec = max(sec, 55)  # Restrictive but declared = ok
        else:
            sec = max(sec, 52)  # Unknown license but declared = slightly better
    
    # Arxiv paper = peer-reviewed / documented research
    if tag_signals.get('has_arxiv'):
        sec = min(100, sec + 8)
        if tag_signals.get('arxiv_count', 0) > 1:
            sec = min(100, sec + 4)  # Multiple papers = well-researched
    
    # Tag count as documentation quality proxy
    tc = tag_signals.get('tag_count', 0)
    if tc >= 8:
        sec = min(100, sec + 5)  # Well-tagged = well-documented
    elif tc >= 5:
        sec = min(100, sec + 3)
    elif tc <= 1:
        sec = max(sec - 3, 0)  # Barely tagged = poor documentation
    
    new_dims['security'] = round(sec, 1)
    
    # ──────────────────────────────────────
    # MAINTENANCE (keep as-is from v2.1 — no new data available)
    # ──────────────────────────────────────
    # No changes — we don't have last_modified for bulk HF crawls
    
    # ──────────────────────────────────────
    # POPULARITY (enhanced download curve for HF scale)
    # ──────────────────────────────────────
    pop = dims.get('popularity', 30.0)
    
    if downloads and downloads > 0:
        # Logarithmic scale tuned for HuggingFace download volumes
        # HF models can have billions of downloads
        if downloads >= 10000000:    # 10M+
            dl_score = 98
        elif downloads >= 1000000:   # 1M+
            dl_score = 92
        elif downloads >= 100000:    # 100K+
            dl_score = 83
        elif downloads >= 10000:     # 10K+
            dl_score = 72
        elif downloads >= 1000:      # 1K+
            dl_score = 60
        elif downloads >= 100:       # 100+
            dl_score = 48
        elif downloads >= 10:        # 10+
            dl_score = 38
        else:                        # 1-9
            dl_score = 28
        
        # Stars bonus (if available)
        star_bonus = 0
        if stars and stars > 0:
            if stars >= 100: star_bonus = 15
            elif stars >= 50: star_bonus = 12
            elif stars >= 10: star_bonus = 8
            elif stars >= 3: star_bonus = 5
            else: star_bonus = 2
        
        pop = min(100, max(dl_score, pop) + star_bonus)
    elif stars and stars > 0:
        # No downloads but has stars (mainly spaces)
        if stars >= 100: pop = 80
        elif stars >= 50: pop = 70
        elif stars >= 10: pop = 55
        elif stars >= 3: pop = 42
        else: pop = 35
    
    new_dims['popularity'] = round(pop, 1)
    
    # ──────────────────────────────────────
    # ECOSYSTEM (enhanced with framework/language/lineage from tags)
    # ──────────────────────────────────────
    eco = dims.get('ecosystem', 30.0)
    
    # Frameworks detected
    fw_count = len(tag_signals.get('frameworks', []))
    if fw_count >= 3:
        eco = min(100, eco + 20)  # Multiple frameworks = high interoperability
    elif fw_count >= 2:
        eco = min(100, eco + 15)
    elif fw_count >= 1:
        eco = min(100, eco + 10)
    
    # Language support
    lang_count = len(tag_signals.get('languages', []))
    if lang_count >= 3:
        eco = min(100, eco + 10)  # Multilingual = broad ecosystem
    elif lang_count >= 1:
        eco = min(100, eco + 5)
    
    # Data lineage (dataset references)
    if tag_signals.get('has_dataset_ref'):
        eco = min(100, eco + 8)
        if tag_signals.get('dataset_count', 0) > 2:
            eco = min(100, eco + 4)  # Multiple dataset refs = well-documented lineage
    
    # Base model reference (fine-tuned from known model)
    if tag_signals.get('has_base_model'):
        eco = min(100, eco + 6)  # Transparent lineage
    
    # Pipeline tag (model has declared purpose)
    if pipeline_tag and pipeline_tag != 'None':
        eco = min(100, eco + 5)
    
    # SDK for spaces
    if sdk and sdk in SDK_QUALITY:
        eco = min(100, eco + SDK_QUALITY[sdk])
    
    new_dims['ecosystem'] = round(eco, 1)
    
    # ──────────────────────────────────────
    # RECOMPUTE TOTAL
    # ──────────────────────────────────────
    total = (
        new_dims.get('security', 50) * WEIGHTS['security'] +
        new_dims.get('compliance', 40) * WEIGHTS['compliance'] +
        new_dims.get('maintenance', 40) * WEIGHTS['maintenance'] +
        new_dims.get('popularity', 30) * WEIGHTS['popularity'] +
        new_dims.get('ecosystem', 30) * WEIGHTS['ecosystem']
    )
    total = round(max(0, min(100, total)), 1)
    
    return total, new_dims


def main():
    conn = psycopg2.connect(DB)
    conn.autocommit = False
    cur = conn.cursor()
    cur2 = conn.cursor()
    
    print("=" * 65)
    print("  NERQ TRUST SCORE v2.2 — CONTENT TYPE ENHANCEMENT")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    
    # Count targets
    cur.execute("""
        SELECT agent_type, COUNT(*) 
        FROM agents 
        WHERE agent_type IN ('model', 'space', 'dataset')
          AND trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY agent_type ORDER BY COUNT(*) DESC
    """)
    type_counts = {r[0]: r[1] for r in cur.fetchall()}
    total = sum(type_counts.values())
    print(f"\n  Targeting {total:,} content-type agents:")
    for t, c in type_counts.items():
        print(f"    {t:<15} {c:>10,}")
    
    # ============================================================
    # STEP 1: Re-score with tag-parsed signals
    # ============================================================
    print(f"\n[1/3] Re-scoring with tag-parsed signals...")
    
    offset = 0
    updated = 0
    t0 = time.time()
    
    while True:
        cur.execute("""
            SELECT id, agent_type, trust_dimensions, downloads, stars, tags,
                   raw_metadata
            FROM agents
            WHERE agent_type IN ('model', 'space', 'dataset')
              AND trust_score_v2 IS NOT NULL AND is_active = true
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (BATCH_SIZE, offset))
        
        rows = cur.fetchall()
        if not rows:
            break
        
        batch_updates = []
        
        for row in rows:
            agent_id, agent_type, dims_raw, downloads, stars, tags, meta_raw = row
            
            if not dims_raw:
                continue
            
            dims = dims_raw if isinstance(dims_raw, dict) else json.loads(dims_raw)
            
            # Get metadata fields
            meta = {}
            if meta_raw:
                meta = meta_raw if isinstance(meta_raw, dict) else json.loads(meta_raw)
            
            # Merge tags from both sources
            all_tags = list(tags or [])
            meta_tags = meta.get('tags', [])
            if meta_tags and isinstance(meta_tags, list):
                # Add meta tags that aren't already in tags
                existing = set(t.lower() for t in all_tags)
                for mt in meta_tags:
                    if isinstance(mt, str) and mt.lower() not in existing:
                        all_tags.append(mt)
            
            # Parse tag signals
            tag_signals = parse_tags(all_tags)
            
            # Get pipeline_tag and sdk from metadata
            pipeline_tag = meta.get('pipeline_tag')
            sdk = meta.get('sdk')
            
            # Re-score
            new_score, new_dims = score_content_agent(
                agent_type, dims, downloads, stars, all_tags,
                pipeline_tag, sdk, tag_signals
            )
            
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
        
        sys.stdout.write(f"\r   {offset:,} / {total:,} ({offset/total*100:.1f}%) | {rate:.0f}/sec | ETA {eta/60:.1f}min")
        sys.stdout.flush()
        
        if offset % 50000 == 0:
            conn.commit()
    
    conn.commit()
    print(f"\n  Updated {updated:,} agents")
    
    # ============================================================
    # STEP 2: Recompute peer ranks for affected types
    # ============================================================
    print(f"\n[2/3] Recomputing peer ranks for content types...")
    
    for agent_type in ['model', 'space', 'dataset']:
        cnt = type_counts.get(agent_type, 0)
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
        """, (cnt, agent_type))
        conn.commit()
        print(f"  {agent_type:<15} {cnt:>10,} re-ranked")
    
    # ============================================================
    # STEP 3: Recompute category ranks for affected categories
    # ============================================================
    print(f"\n[3/3] Recomputing category ranks...")
    
    cur.execute("""
        SELECT domains[1] as primary_domain, agent_type, COUNT(*) as cnt
        FROM agents
        WHERE domains IS NOT NULL AND array_length(domains, 1) > 0
          AND agent_type IN ('model', 'space', 'dataset')
          AND trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY domains[1], agent_type
        HAVING COUNT(*) >= 5
        ORDER BY cnt DESC
    """)
    categories = cur.fetchall()
    
    cat_count = 0
    for domain, agent_type, cnt in categories:
        label = f"{domain} {agent_type}s"
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
        if cat_count % 10 == 0:
            conn.commit()
    conn.commit()
    print(f"  {cat_count} categories re-ranked")
    
    # ============================================================
    # RESULTS
    # ============================================================
    print("\n" + "=" * 65)
    print("  RESULTS")
    print("=" * 65)
    
    # Grade distribution
    cur.execute("""
        SELECT trust_grade, COUNT(*) 
        FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY trust_grade ORDER BY trust_grade
    """)
    grades = cur.fetchall()
    total_all = sum(g[1] for g in grades)
    
    print("\n  -- Overall Grade Distribution --")
    for grade, cnt in grades:
        pct = cnt / total_all * 100
        bar = '#' * int(pct / 2)
        print(f"    {grade:>2}: {cnt:>10,} ({pct:>5.1f}%) {bar}")
    
    # Per-type distribution
    cur.execute("""
        SELECT agent_type, COUNT(*),
               ROUND(AVG(trust_score_v2)::numeric, 1),
               ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY trust_score_v2)::numeric, 1),
               ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY trust_score_v2)::numeric, 1),
               ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY trust_score_v2)::numeric, 1),
               ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY trust_score_v2)::numeric, 1)
        FROM agents WHERE trust_score_v2 IS NOT NULL AND is_active = true
        GROUP BY agent_type ORDER BY COUNT(*) DESC
    """)
    print(f"\n  -- Per-Type Distribution --")
    print(f"    {'Type':<15} {'Count':>10} {'Avg':>6} {'P25':>6} {'P50':>6} {'P75':>6} {'P90':>6}")
    for r in cur.fetchall():
        print(f"    {r[0] or 'unknown':<15} {r[1]:>10,} {r[2]:>6} {r[3]:>6} {r[4]:>6} {r[5]:>6} {r[6]:>6}")
    
    # Grade distribution per content type
    for atype in ['model', 'space', 'dataset']:
        cur.execute("""
            SELECT trust_grade, COUNT(*)
            FROM agents WHERE agent_type = %s AND trust_score_v2 IS NOT NULL AND is_active = true
            GROUP BY trust_grade ORDER BY trust_grade
        """, (atype,))
        results = cur.fetchall()
        type_total = sum(r[1] for r in results)
        print(f"\n  -- {atype.upper()} Grade Distribution --")
        for grade, cnt in results:
            pct = cnt / type_total * 100
            bar = '#' * int(pct)
            print(f"    {grade:>2}: {cnt:>10,} ({pct:>5.1f}%) {bar}")
    
    # Top models
    cur.execute("""
        SELECT trust_grade, trust_score_v2, name, downloads, stars,
               trust_peer_rank, trust_peer_total
        FROM agents
        WHERE agent_type = 'model' AND trust_score_v2 IS NOT NULL AND is_active = true
        ORDER BY trust_score_v2 DESC LIMIT 10
    """)
    print(f"\n  -- Top 10 Models --")
    for i, r in enumerate(cur.fetchall(), 1):
        dl = f"{r[3]:,}" if r[3] else "0"
        print(f"    {i:>2}. {r[0]:>2} {r[1]:>5.1f}  {r[2]:<45} DL:{dl:<15} #{r[5]:,}/{r[6]:,}")
    
    elapsed_total = time.time() - t0
    print(f"\n  DONE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({elapsed_total/60:.1f} min)")
    print("=" * 65)
    
    conn.close()


if __name__ == "__main__":
    main()
