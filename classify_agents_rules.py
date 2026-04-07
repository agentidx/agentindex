#!/usr/bin/env python3
import psycopg2, psycopg2.extras, json, re, logging, os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [classify] %(message)s",
    handlers=[logging.FileHandler(f'classify_{datetime.now().strftime("%Y%m%d_%H%M")}.log'), logging.StreamHandler()])
logger = logging.getLogger("classify")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')

HIGH_RISK = ['biometric','face-recognition','facial-recognition','emotion-recognition','surveillance','medical','clinical','diagnosis','pathology','radiology','drug-discovery','healthcare','autonomous-driving','self-driving','credit-scoring','loan-approval','recruitment','hiring','resume-screening','legal-judgment','law-enforcement','predictive-policing','border-control','critical-infrastructure','weapon','military']
LIMITED_RISK = ['chatbot','chat','conversational','assistant','text-generation','content-generation','deepfake','face-swap','voice-clone','tts','text-to-speech','image-generation','text-to-image','stable-diffusion','diffusion','video-generation','recommendation']
DOMAIN_MAP = {'healthcare':['medical','clinical','health','biomedical','pathology','radiology','drug','pharma','disease','diagnosis','cancer','protein','bio'],'finance':['financial','finance','banking','trading','stock','crypto','loan','credit','insurance','fraud'],'legal':['legal','law','court','contract','compliance','regulatory','gdpr'],'education':['education','school','student','learning','exam','academic'],'security':['security','cybersecurity','malware','vulnerability','threat','surveillance','biometric'],'transportation':['autonomous','driving','vehicle','traffic','drone','robotics'],'media':['image','video','audio','music','speech','voice','creative','art','generation'],'nlp':['text','language','translation','summarization','ner','sentiment','classification','embedding','bert','gpt','llm','llama','mistral'],'code':['code','programming','developer','github','coding','software'],'science':['scientific','research','chemistry','physics','climate','weather','satellite']}
TYPE_SOURCES = {'dataset':['huggingface_dataset','huggingface_dataset_full','huggingface_dataset_v2'],'space':['huggingface_space','huggingface_space_full','huggingface_space_v2'],'mcp_server':['mcp','mcp_registry'],'container':['docker_hub'],'package':['npm','pypi','pypi_ai']}

def classify(source, name, tags, desc):
    name = name or ''; tags = tags or []; desc = desc or ''
    text = f"{name} {' '.join(tags)} {desc}".lower()
    # Type
    atype = 'model'
    for t, srcs in TYPE_SOURCES.items():
        if source in srcs: atype = t; break
    else:
        if any(k in text for k in ['agent','autonomous','agentic','swarm','multi-agent']): atype = 'agent'
        elif any(k in text for k in ['mcp','model-context-protocol']): atype = 'mcp_server'
        elif any(k in text for k in ['tool','plugin','extension','cli']): atype = 'tool'
        elif source == 'github': atype = 'tool'
        elif source in ('replicate','replicate_cursor'): atype = 'model'
    # Risk
    risk = 'minimal'
    if any(k in text for k in ['social-scoring','social-credit','subliminal']): risk = 'unacceptable'
    elif any(k in text or k.replace('-',' ') in text for k in HIGH_RISK): risk = 'high'
    elif any(k in text or k.replace('-',' ') in text for k in LIMITED_RISK): risk = 'limited'
    # Domains
    domains = [d for d, kws in DOMAIN_MAP.items() if any(k in text for k in kws)] or ['general']
    return atype, risk, domains

def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    for col, ct in [('agent_type','VARCHAR(50)'),('risk_class','VARCHAR(50)'),('domains','TEXT[]'),('classified_at','TIMESTAMP')]:
        try:
            cur.execute(f"ALTER TABLE agents ADD COLUMN IF NOT EXISTS {col} {ct}")
            conn.commit()
        except: conn.rollback()
    cur.execute("SELECT COUNT(*) FROM agents WHERE classified_at IS NULL")
    unclassified = cur.fetchone()[0]
    logger.info(f"Unclassified: {unclassified:,}")
    total = 0
    while True:
        cur.execute("SELECT id, source, name, tags, description FROM agents WHERE classified_at IS NULL ORDER BY downloads DESC NULLS LAST LIMIT 1000")
        rows = cur.fetchall()
        if not rows: break
        updates = []
        for r in rows:
            aid, src, nm, tg, dsc = r
            at, rc, dm = classify(src, nm, tg, dsc)
            updates.append((at, rc, dm, datetime.now(), aid))
        psycopg2.extras.execute_batch(cur, "UPDATE agents SET agent_type=%s, risk_class=%s, domains=%s, classified_at=%s WHERE id=%s", updates, page_size=500)
        conn.commit()
        total += len(updates)
        if total % 10000 == 0:
            logger.info(f"Classified: {total:,} / {unclassified:,}")
    logger.info(f"DONE: {total:,} classified")
    cur.execute("SELECT risk_class, COUNT(*) FROM agents WHERE classified_at IS NOT NULL GROUP BY risk_class ORDER BY count DESC")
    for r in cur.fetchall(): logger.info(f"  {r[0]}: {r[1]:,}")
    cur.execute("SELECT agent_type, COUNT(*) FROM agents WHERE classified_at IS NOT NULL GROUP BY agent_type ORDER BY count DESC")
    for r in cur.fetchall(): logger.info(f"  {r[0]}: {r[1]:,}")
    conn.close()

if __name__ == '__main__':
    main()
