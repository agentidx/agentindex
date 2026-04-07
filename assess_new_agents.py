#!/usr/bin/env python3
"""
Assess NEW agents only (those missing from agent_jurisdiction_status).
Does NOT truncate — only inserts missing agent×jurisdiction combinations.
"""

import psycopg2, psycopg2.extras, json, logging, os, sys, time
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [assess-new] %(message)s")
logger = logging.getLogger("assess-new")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')

# Import the assessment function from existing script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# We need to load jurisdiction rules - reuse existing logic
DOMAIN_SECTOR_MAP = {
    'healthcare': ['healthcare', 'health', 'medical', 'clinical', 'biomedical', 'life_safety'],
    'finance': ['financial', 'finance', 'financial_services', 'credit', 'insurance', 'fintech'],
    'legal': ['legal', 'law', 'justice', 'law_enforcement'],
    'education': ['education', 'academic'],
    'security': ['security', 'cybersecurity', 'surveillance', 'biometric', 'biometric_identification',
                 'critical_infrastructure', 'border_control', 'migration'],
    'transportation': ['transportation', 'autonomous_driving', 'self_driving', 'vehicle'],
    'media': ['content', 'media', 'creative', 'synthetic_media', 'deepfakes', 'ai_generated_content'],
    'code': ['code', 'software', 'development'],
    'general': []
}

BIOMETRIC_KW = ['biometric', 'face-recognition', 'facial', 'face-detect', 'iris', 'fingerprint',
                'emotion-recognition', 'emotion-detect', 'gait']
EMPLOYMENT_KW = ['hiring', 'recruitment', 'resume', 'hr', 'employment', 'candidate', 'interview',
                 'job-screening', 'workforce', 'talent']
CONTENT_GEN_KW = ['text-generation', 'image-generation', 'video-generation', 'deepfake',
                  'voice-clone', 'tts', 'text-to-speech', 'stable-diffusion', 'diffusion',
                  'content-generation', 'generative', 'chatbot', 'chat', 'conversational']
CRITICAL_INFRA_KW = ['critical-infrastructure', 'energy', 'power-grid', 'water', 'telecom',
                     'transport-system', 'nuclear']
GOVERNMENT_KW = ['government', 'public-sector', 'state-agency', 'municipal', 'federal']
FRONTIER_KW = ['frontier', 'large-language-model', 'foundation-model', 'llm']


def load_jurisdictions(conn):
    cur = conn.cursor()
    cur.execute("""SELECT id, name, country, risk_model, risk_classes, 
                   high_risk_criteria, requirements, focus, status as law_status
                   FROM jurisdiction_registry""")
    cols = [d[0] for d in cur.description]
    jurisdictions = []
    for row in cur.fetchall():
        j = dict(zip(cols, row))
        for f in ['risk_classes', 'high_risk_criteria', 'requirements']:
            j[f] = json.loads(j[f]) if isinstance(j[f], str) else j[f]
        jurisdictions.append(j)
    return jurisdictions


def run():
    conn = psycopg2.connect(DB_URL)
    jurisdictions = load_jurisdictions(conn)
    j_count = len(jurisdictions)
    
    cur = conn.cursor()
    
    # Find agents NOT in agent_jurisdiction_status
    cur.execute("""
        SELECT COUNT(*) FROM agents a 
        WHERE a.risk_class IS NOT NULL 
        AND NOT EXISTS (
            SELECT 1 FROM agent_jurisdiction_status ajs WHERE ajs.agent_id = a.id::text
        )
    """)
    new_count = cur.fetchone()[0]
    logger.info(f"New agents to assess: {new_count:,} x {j_count} jurisdictions = {new_count * j_count:,} assessments")
    
    if new_count == 0:
        logger.info("Nothing to do — all agents already assessed!")
        conn.close()
        return
    
    # Import the assess function from existing script
    # We exec the file to get the function
    import importlib.util
    spec = importlib.util.spec_from_file_location("mja", os.path.expanduser("~/agentindex/multi_jurisdiction_assess.py"))
    mja = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mja)
    
    batch_size = 5000
    offset = 0
    total_inserted = 0
    start_time = time.time()
    
    while True:
        cur.execute("""
            SELECT a.id, a.risk_class, a.agent_type, a.domains, a.name, a.description 
            FROM agents a
            WHERE a.risk_class IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM agent_jurisdiction_status ajs WHERE ajs.agent_id = a.id::text
            )
            ORDER BY a.id
            LIMIT %s
        """, (batch_size,))
        
        agents = cur.fetchall()
        if not agents:
            break
        
        insert_vals = []
        for agent_id, risk_class, agent_type, domains, name, desc in agents:
            for j in jurisdictions:
                status, risk_level, triggered, notes = mja.assess_agent_jurisdiction(
                    risk_class, agent_type, domains, name, desc, j
                )
                insert_vals.append((
                    agent_id, j['id'], status, risk_level,
                    triggered, notes, datetime.now()
                ))
        
        psycopg2.extras.execute_values(cur, """
            INSERT INTO agent_jurisdiction_status 
            (agent_id, jurisdiction_id, status, risk_level, triggered_criteria, compliance_notes, assessed_at)
            VALUES %s
            ON CONFLICT (agent_id, jurisdiction_id) DO NOTHING
        """, insert_vals, page_size=10000)
        conn.commit()
        
        total_inserted += len(insert_vals)
        offset += len(agents)
        elapsed = time.time() - start_time
        rate = offset / elapsed if elapsed > 0 else 0
        eta = (new_count - offset) / rate if rate > 0 else 0
        
        logger.info(f"Progress: {offset:,}/{new_count:,} agents ({total_inserted:,} assessments, {rate:.0f} agents/sec, ETA: {eta/60:.1f}min)")
    
    elapsed = time.time() - start_time
    logger.info(f"DONE: {offset:,} agents, {total_inserted:,} assessments in {elapsed/60:.1f}min")
    conn.close()


if __name__ == "__main__":
    run()
