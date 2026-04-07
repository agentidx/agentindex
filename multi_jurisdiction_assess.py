#!/usr/bin/env python3
"""
Multi-Jurisdiction Compliance Assessment Engine
Assesses all agents against all 52 jurisdictions using rule-based matching.
Creates agent_jurisdiction_status table and populates it.

For each agent, maps risk_class + agent_type + domains against each jurisdiction's
high_risk_criteria to determine per-jurisdiction compliance status.
"""

import psycopg2, psycopg2.extras, json, logging, os, time
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [multi-juris] %(message)s",
    handlers=[logging.FileHandler(f'multi_jurisdiction_{datetime.now().strftime("%Y%m%d_%H%M")}.log'),
              logging.StreamHandler()])
logger = logging.getLogger("multi-juris")
DB_URL = os.getenv('DATABASE_URL', 'postgresql://localhost/agentindex')


def create_table(conn):
    """Create agent_jurisdiction_status table."""
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_jurisdiction_status (
        agent_id TEXT NOT NULL,
        jurisdiction_id TEXT NOT NULL,
        status TEXT NOT NULL,
        risk_level TEXT,
        triggered_criteria TEXT,
        compliance_notes TEXT,
        assessed_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (agent_id, jurisdiction_id)
    )
    """)
    # Indexes for fast lookups
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ajs_agent ON agent_jurisdiction_status(agent_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ajs_jurisdiction ON agent_jurisdiction_status(jurisdiction_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ajs_status ON agent_jurisdiction_status(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ajs_risk ON agent_jurisdiction_status(risk_level)")
    conn.commit()
    logger.info("agent_jurisdiction_status table ready")


def load_jurisdictions(conn):
    """Load all jurisdictions with their rules."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, country, risk_model, risk_classes, 
               high_risk_criteria, requirements, focus, status as law_status
        FROM jurisdiction_registry
    """)
    cols = [d[0] for d in cur.description]
    jurisdictions = []
    for row in cur.fetchall():
        j = dict(zip(cols, row))
        j['risk_classes'] = json.loads(j['risk_classes']) if isinstance(j['risk_classes'], str) else j['risk_classes']
        j['high_risk_criteria'] = json.loads(j['high_risk_criteria']) if isinstance(j['high_risk_criteria'], str) else j['high_risk_criteria']
        j['requirements'] = json.loads(j['requirements']) if isinstance(j['requirements'], str) else j['requirements']
        jurisdictions.append(j)
    logger.info(f"Loaded {len(jurisdictions)} jurisdictions")
    return jurisdictions


# ============================================================
# JURISDICTION-SPECIFIC ASSESSMENT RULES
# ============================================================

# Domain-to-sector mapping for jurisdiction matching
DOMAIN_SECTOR_MAP = {
    'healthcare': ['healthcare', 'health', 'medical', 'clinical', 'biomedical', 'life_safety'],
    'finance': ['financial', 'finance', 'financial_services', 'credit', 'insurance', 'fintech'],
    'legal': ['legal', 'law', 'justice', 'law_enforcement'],
    'education': ['education', 'academic'],
    'security': ['security', 'cybersecurity', 'surveillance', 'biometric', 'biometric_identification',
                 'critical_infrastructure', 'border_control', 'migration'],
    'transportation': ['transportation', 'autonomous_driving', 'self_driving', 'vehicle'],
    'media': ['content', 'media', 'creative', 'synthetic_media', 'deepfakes', 'ai_generated_content'],
    'nlp': ['language', 'text', 'nlp'],
    'code': ['code', 'software', 'development'],
    'science': ['science', 'research'],
    'general': []
}

# Keywords that trigger specific jurisdiction concerns
BIOMETRIC_KW = ['biometric', 'face-recognition', 'facial', 'face-detect', 'iris', 'fingerprint',
                'emotion-recognition', 'emotion-detect', 'gait']
EMPLOYMENT_KW = ['hiring', 'recruitment', 'resume', 'hr', 'employment', 'candidate', 'interview',
                 'job-screening', 'workforce', 'talent']
CONTENT_GEN_KW = ['text-generation', 'image-generation', 'video-generation', 'deepfake',
                  'voice-clone', 'tts', 'text-to-speech', 'stable-diffusion', 'diffusion',
                  'content-generation', 'generative', 'chatbot', 'chat', 'conversational']
CRITICAL_INFRA_KW = ['critical-infrastructure', 'energy', 'power-grid', 'water', 'telecom',
                     'transport-system', 'nuclear']
SOCIAL_SCORING_KW = ['social-scoring', 'social-credit', 'citizen-score', 'subliminal']
GOVERNMENT_KW = ['government', 'public-sector', 'state-agency', 'municipal', 'federal']
FRONTIER_KW = ['frontier', 'large-language-model', 'foundation-model', 'llm']


def assess_agent_jurisdiction(agent_risk, agent_type, agent_domains, agent_name, agent_desc,
                               jurisdiction):
    """
    Assess one agent against one jurisdiction.
    Returns (status, risk_level, triggered_criteria, notes)
    """
    j_id = jurisdiction['id']
    j_focus = jurisdiction.get('focus', '')
    risk_model = jurisdiction.get('risk_model', '')
    high_risk_criteria = jurisdiction.get('high_risk_criteria', {})
    
    # Build agent text for keyword matching
    text = f"{agent_name or ''} {agent_desc or ''} {' '.join(agent_domains or [])}".lower()
    
    # Check keyword categories
    is_biometric = any(k in text for k in BIOMETRIC_KW)
    is_employment = any(k in text for k in EMPLOYMENT_KW)
    is_content_gen = any(k in text for k in CONTENT_GEN_KW)
    is_critical_infra = any(k in text for k in CRITICAL_INFRA_KW)
    is_social_scoring = any(k in text for k in SOCIAL_SCORING_KW)
    is_government = any(k in text for k in GOVERNMENT_KW)
    is_frontier = any(k in text for k in FRONTIER_KW)
    is_healthcare = 'healthcare' in (agent_domains or [])
    is_finance = 'finance' in (agent_domains or [])
    is_legal = 'legal' in (agent_domains or [])
    is_education = 'education' in (agent_domains or [])
    is_security = 'security' in (agent_domains or [])
    is_media = 'media' in (agent_domains or [])
    
    # Default
    status = 'compliant'
    risk_level = 'minimal'
    triggered = []
    notes = ''
    
    # ============================================================
    # EU AI ACT & NATIONAL IMPLEMENTATIONS
    # ============================================================
    if j_id == 'eu_ai_act' or j_id.startswith('eu_'):
        if is_social_scoring:
            status = 'non_compliant'
            risk_level = 'unacceptable'
            triggered.append('prohibited_practice:social_scoring')
            notes = 'Prohibited under Art. 5 EU AI Act'
        elif agent_risk == 'unacceptable':
            status = 'non_compliant'
            risk_level = 'unacceptable'
            triggered.append('risk_class:unacceptable')
            notes = 'Prohibited under Art. 5 EU AI Act'
        elif agent_risk == 'high' or is_biometric or is_critical_infra:
            status = 'requires_conformity'
            risk_level = 'high'
            triggered_items = []
            if is_biometric: triggered_items.append('annex_iii:biometric')
            if is_critical_infra: triggered_items.append('annex_iii:critical_infrastructure')
            if is_healthcare: triggered_items.append('annex_iii:healthcare')
            if is_education: triggered_items.append('annex_iii:education')
            if is_employment: triggered_items.append('annex_iii:employment')
            if is_legal: triggered_items.append('annex_iii:justice')
            if is_finance: triggered_items.append('annex_iii:essential_services')
            triggered = triggered_items or ['risk_class:high']
            notes = 'High-risk: requires conformity assessment (Art. 43), CE marking, risk management (Art. 9)'
        elif is_content_gen or agent_risk == 'limited':
            status = 'transparency_required'
            risk_level = 'limited'
            triggered.append('art_50:transparency')
            notes = 'Transparency obligations: must disclose AI-generated content (Art. 50)'
        else:
            status = 'compliant'
            risk_level = 'minimal'
            notes = 'Minimal risk: voluntary codes of practice encouraged'

    # ============================================================
    # US — COLORADO AI ACT
    # ============================================================
    elif j_id == 'us_co_sb205':
        if is_employment or is_finance or is_healthcare or is_education or is_legal:
            status = 'high_risk'
            risk_level = 'high'
            triggered.append('consequential_decision')
            if is_employment: triggered.append('sector:employment')
            if is_finance: triggered.append('sector:financial_services')
            if is_healthcare: triggered.append('sector:healthcare')
            if is_education: triggered.append('sector:education')
            if is_legal: triggered.append('sector:legal_services')
            notes = 'High-risk: consequential decision tool. Requires impact assessment, consumer notification, annual bias audit.'
        else:
            status = 'not_high_risk'
            risk_level = 'minimal'
            notes = 'Not classified as high-risk consequential decision tool'

    # ============================================================
    # US — CALIFORNIA FRONTIER AI (SB 53)
    # ============================================================
    elif j_id == 'us_ca_sb53':
        if is_frontier and agent_type == 'model':
            status = 'covered_model'
            risk_level = 'high'
            triggered.append('frontier_model')
            notes = 'Covered frontier model: requires safety protocols, third-party audit, incident reporting'
        else:
            status = 'not_covered'
            risk_level = 'minimal'
            notes = 'Not a covered frontier model under SB 53'

    # ============================================================
    # US — CALIFORNIA AI TRANSPARENCY (SB 942)
    # ============================================================
    elif j_id == 'us_ca_sb942':
        if is_content_gen:
            status = 'requires_watermark'
            risk_level = 'limited'
            triggered.append('ai_generated_content')
            notes = 'Requires watermarking of AI-generated content and AI detection tools'
        else:
            status = 'exempt'
            risk_level = 'minimal'
            notes = 'Not subject to watermarking requirements'

    # ============================================================
    # US — CALIFORNIA AB 2013 (Training Data Transparency)
    # ============================================================
    elif j_id == 'us_ca_ab2013':
        if agent_type == 'model' and is_content_gen:
            status = 'requires_disclosure'
            risk_level = 'limited'
            triggered.append('genai_training_data')
            notes = 'Must publish high-level training data information'
        else:
            status = 'not_covered'
            risk_level = 'minimal'
            notes = 'Not a public-use generative AI system'

    # ============================================================
    # US — CALIFORNIA SB 243 (Companion Chatbot)
    # ============================================================
    elif j_id == 'us_ca_sb243':
        if any(k in text for k in ['companion', 'chatbot', 'social-ai', 'emotional', 'relationship']):
            status = 'requires_safety_protocols'
            risk_level = 'limited'
            triggered.append('companion_chatbot')
            notes = 'Must implement self-harm prevention protocols and AI disclosure to minors'
        else:
            status = 'not_applicable'
            risk_level = 'minimal'
            notes = 'Not a companion chatbot'

    # ============================================================
    # US — TEXAS RAIGA
    # ============================================================
    elif j_id == 'us_tx_raiga' or j_id == 'us_tx_traiga':
        if is_social_scoring or any(k in text for k in ['self-harm', 'violence', 'weapon', 'deepfake']):
            status = 'restricted'
            risk_level = 'high'
            triggered.append('restricted_purpose')
            notes = 'Restricted purpose under TRAIGA. AG enforcement with significant penalties.'
        else:
            status = 'compliant'
            risk_level = 'minimal'
            notes = 'Not a restricted-purpose AI system under TRAIGA'

    # ============================================================
    # US — ILLINOIS (AIVI + HB3773)
    # ============================================================
    elif j_id in ('us_il_aivi', 'us_il_hb3773'):
        if is_employment:
            status = 'requires_compliance'
            risk_level = 'high'
            triggered.append('employment_ai')
            notes = 'Employment AI: requires notice, explanation, right to human review'
        else:
            status = 'not_applicable'
            risk_level = 'minimal'
            notes = 'Not an employment AI tool'

    # ============================================================
    # US — NYC LOCAL LAW 144
    # ============================================================
    elif j_id == 'us_ny_ll144':
        if is_employment:
            status = 'requires_bias_audit'
            risk_level = 'high'
            triggered.append('aedt_employment')
            notes = 'AEDT: requires annual independent bias audit, public results, 10-day candidate notice'
        else:
            status = 'not_applicable'
            risk_level = 'minimal'
            notes = 'Not an automated employment decision tool'

    # ============================================================
    # US — NY RAISE ACT
    # ============================================================
    elif j_id == 'us_ny_raise':
        if is_frontier and agent_type == 'model':
            status = 'covered_frontier'
            risk_level = 'high'
            triggered.append('frontier_model')
            notes = 'Frontier model: safety evaluations, red-teaming, incident reporting required'
        else:
            status = 'not_covered'
            risk_level = 'minimal'
            notes = 'Not a covered frontier model'

    # ============================================================
    # US — UTAH, CONNECTICUT, MARYLAND, TAKE IT DOWN
    # ============================================================
    elif j_id in ('us_ut_aipa', 'us_ut_sb226'):
        if is_content_gen:
            status = 'requires_disclosure'
            risk_level = 'limited'
            triggered.append('genai_disclosure')
            notes = 'Must clearly disclose generative AI interactions to consumers'
        else:
            status = 'not_covered'
            risk_level = 'minimal'

    elif j_id == 'us_ct_sb1295':
        if is_employment or is_finance or is_healthcare or is_education:
            status = 'requires_assessment'
            risk_level = 'high'
            triggered.append('automated_decision')
            notes = 'Automated decision system: impact assessment, opt-out rights, human review required'
        else:
            status = 'not_covered'
            risk_level = 'minimal'

    elif j_id == 'us_md_aieha':
        if is_employment:
            status = 'requires_compliance'
            risk_level = 'high'
            triggered.append('employment_discrimination')
            notes = 'Must comply with anti-discrimination requirements for AI in employment'
        else:
            status = 'not_applicable'
            risk_level = 'minimal'

    elif j_id == 'us_fed_takedown':
        if any(k in text for k in ['deepfake', 'face-swap', 'intimate', 'nude', 'nsfw']):
            status = 'regulated'
            risk_level = 'high'
            triggered.append('nonconsensual_imagery')
            notes = 'TAKE IT DOWN Act: platforms must remove flagged content within 48h'
        else:
            status = 'not_applicable'
            risk_level = 'minimal'

    # ============================================================
    # SOUTH KOREA
    # ============================================================
    elif j_id == 'kr_ai_basic_act':
        if agent_risk == 'high' or is_biometric or is_healthcare or is_finance:
            status = 'high_impact'
            risk_level = 'high'
            triggered.append('high_impact_ai')
            notes = 'High-impact AI: risk assessment, human oversight, transparency required'
        elif is_content_gen:
            status = 'moderate_impact'
            risk_level = 'limited'
            triggered.append('moderate_impact')
            notes = 'Moderate-impact: transparency and data quality requirements'
        else:
            status = 'low_impact'
            risk_level = 'minimal'

    # ============================================================
    # CHINA
    # ============================================================
    elif j_id == 'cn_cybersecurity':
        if is_critical_infra or is_security:
            status = 'critical_sector'
            risk_level = 'high'
            triggered.append('critical_infrastructure')
            notes = 'Critical sector: data localization, security assessments, government approval required'
        else:
            status = 'general'
            risk_level = 'minimal'

    elif j_id == 'cn_ai_labeling':
        if is_content_gen:
            status = 'requires_labeling'
            risk_level = 'limited'
            triggered.append('ai_content_labeling')
            notes = 'Must add explicit + implicit labels to AI-generated content (text, image, audio, video)'
        else:
            status = 'not_applicable'
            risk_level = 'minimal'

    # ============================================================
    # JAPAN
    # ============================================================
    elif j_id == 'jp_ai_bill':
        if agent_risk == 'high':
            status = 'review_recommended'
            risk_level = 'limited'
            triggered.append('ai_principles')
            notes = 'Principles-based: government may publicly name non-cooperative companies'
        else:
            status = 'compliant'
            risk_level = 'minimal'

    # ============================================================
    # UK
    # ============================================================
    elif j_id == 'uk_ai_regulation':
        if is_healthcare or is_finance or is_education or is_employment:
            status = 'sector_regulated'
            risk_level = 'high'
            triggered.append('sector_specific')
            if is_healthcare: triggered.append('sector:healthcare')
            if is_finance: triggered.append('sector:finance')
            notes = 'Sector-specific regulation: oversight by relevant sector regulator'
        else:
            status = 'minimal_regulation'
            risk_level = 'minimal'

    # ============================================================
    # CANADA
    # ============================================================
    elif j_id == 'ca_aida':
        if agent_risk == 'high' or is_biometric or is_employment:
            status = 'high_impact'
            risk_level = 'high'
            triggered.append('high_impact_system')
            notes = 'High-impact system: risk assessment, mitigation, monitoring required (proposed)'
        else:
            status = 'not_high_impact'
            risk_level = 'minimal'

    # ============================================================
    # BRAZIL
    # ============================================================
    elif j_id == 'br_ai_bill':
        if is_social_scoring:
            status = 'unacceptable_risk'
            risk_level = 'unacceptable'
            triggered.append('excessive_risk')
            notes = 'Excessive risk: prohibited (proposed bill mirrors EU approach)'
        elif agent_risk == 'high' or is_biometric or is_healthcare:
            status = 'high_risk'
            risk_level = 'high'
            triggered.append('high_risk')
            notes = 'High-risk: impact assessment, strict liability (proposed)'
        elif is_content_gen:
            status = 'limited_risk'
            risk_level = 'limited'
            triggered.append('transparency')
        else:
            status = 'minimal_risk'
            risk_level = 'minimal'

    # ============================================================
    # SINGAPORE
    # ============================================================
    elif j_id == 'sg_ai_governance':
        if agent_risk == 'high' or is_healthcare or is_finance:
            status = 'high_impact'
            risk_level = 'high'
            triggered.append('voluntary_high_impact')
            notes = 'High-impact: voluntary governance framework recommends full compliance'
        else:
            status = 'low_impact'
            risk_level = 'minimal'

    # ============================================================
    # VIETNAM
    # ============================================================
    elif j_id == 'vn_ai_law':
        if is_healthcare or is_finance or is_education or is_security:
            status = 'high_risk'
            risk_level = 'high'
            triggered.append('sensitive_sector')
            notes = 'Sensitive sector: risk assessment, human oversight, data protection required'
        else:
            status = 'low_risk'
            risk_level = 'minimal'

    # ============================================================
    # INDIA
    # ============================================================
    elif j_id == 'in_it_rules':
        if is_content_gen:
            status = 'requires_labeling'
            risk_level = 'limited'
            triggered.append('ai_content_labeling')
            notes = 'Must label AI-generated content (explicit + implicit). Expedited removal of unlawful content.'
        else:
            status = 'general_compliance'
            risk_level = 'minimal'

    elif j_id == 'in_ai_governance':
        if is_healthcare or is_finance or is_education:
            status = 'high_risk'
            risk_level = 'high'
            triggered.append('sensitive_sector')
            notes = 'Sensitive sector: AI Safety Board pilot compliance recommended'
        else:
            status = 'general'
            risk_level = 'minimal'

    # ============================================================
    # TAIWAN
    # ============================================================
    elif j_id == 'tw_ai_basic_act':
        if agent_risk == 'high':
            status = 'review_recommended'
            risk_level = 'limited'
            triggered.append('ai_governance')
            notes = 'Principles-based: governance adoption recommended for high-risk AI'
        else:
            status = 'compliant'
            risk_level = 'minimal'

    # ============================================================
    # UAE & SAUDI
    # ============================================================
    elif j_id == 'ae_ai_strategy':
        if is_government or is_finance or is_healthcare:
            status = 'requires_licensing'
            risk_level = 'high'
            triggered.append('ai_licensing')
            notes = 'Requires AI licensing through DIFC/ADGM for commercial deployment'
        else:
            status = 'general'
            risk_level = 'minimal'

    elif j_id == 'sa_ai_ethics':
        if is_government or is_healthcare or is_finance:
            status = 'high_impact'
            risk_level = 'high'
            triggered.append('sdaia_oversight')
            notes = 'SDAIA ethical principles: transparency and Vision 2030 alignment required'
        else:
            status = 'general'
            risk_level = 'minimal'

    # ============================================================
    # AFRICA (Kenya, Nigeria, South Africa)
    # ============================================================
    elif j_id in ('ke_data_protection', 'ng_ndpr', 'za_popia_ai'):
        if is_employment or is_finance or is_healthcare:
            status = 'requires_assessment'
            risk_level = 'high'
            triggered.append('automated_decision')
            notes = 'Automated decision-making: data protection impact assessment required, right to object'
        else:
            status = 'general_processing'
            risk_level = 'minimal'

    # ============================================================
    # LATIN AMERICA (Chile, Colombia, Peru, Mexico)
    # ============================================================
    elif j_id in ('cl_ai_bill', 'mx_ai_regulation'):
        if agent_risk == 'high' or is_biometric:
            status = 'high_risk'
            risk_level = 'high'
            triggered.append('high_risk_proposed')
            notes = 'High-risk classification under proposed legislation'
        else:
            status = 'minimal_risk'
            risk_level = 'minimal'

    elif j_id in ('co_ai_guidelines', 'pe_ai_law'):
        if is_government:
            status = 'government_compliance'
            risk_level = 'limited'
            triggered.append('government_ai')
            notes = 'Government AI: ethics guidelines apply'
        else:
            status = 'general'
            risk_level = 'minimal'

    # ============================================================
    # AUSTRALIA & NEW ZEALAND
    # ============================================================
    elif j_id == 'au_ai_guardrails':
        if is_employment or is_finance or is_healthcare or is_legal or is_government:
            status = 'high_risk'
            risk_level = 'high'
            triggered.append('high_risk_setting')
            notes = 'Mandatory guardrails: transparency, testing, human oversight required (proposed)'
        else:
            status = 'general'
            risk_level = 'minimal'

    elif j_id == 'nz_ai_charter':
        if is_government:
            status = 'charter_applies'
            risk_level = 'limited'
            triggered.append('government_algorithm')
            notes = 'Algorithm Charter: transparency and human oversight for government algorithms'
        else:
            status = 'not_applicable'
            risk_level = 'minimal'

    # ============================================================
    # INTERNATIONAL (OECD, CoE, ISO)
    # ============================================================
    elif j_id == 'intl_oecd_ai':
        if agent_risk == 'high':
            status = 'review_recommended'
            risk_level = 'limited'
            triggered.append('oecd_principles')
            notes = 'OECD principles: trustworthy AI assessment recommended'
        else:
            status = 'aligned'
            risk_level = 'minimal'

    elif j_id == 'intl_coe_convention':
        if is_biometric or is_employment or agent_risk == 'high':
            status = 'rights_impacting'
            risk_level = 'high'
            triggered.append('human_rights_impact')
            notes = 'Rights-impacting AI: transparency, accountability, remedies required'
        else:
            status = 'general'
            risk_level = 'minimal'

    elif j_id == 'intl_iso42001':
        status = 'certification_available'
        risk_level = 'minimal'
        notes = 'ISO/IEC 42001 certification available for AI management systems'

    # ============================================================
    # THAILAND, PHILIPPINES (catch remaining)
    # ============================================================
    elif j_id == 'th_ai_governance':
        if agent_risk == 'high':
            status = 'high_impact'
            risk_level = 'limited'
            triggered.append('ai_ethics')
            notes = 'Voluntary: ethics principles compliance recommended'
        else:
            status = 'general'
            risk_level = 'minimal'

    elif j_id == 'ph_ai_development':
        if is_healthcare or is_education or is_government:
            status = 'high_risk'
            risk_level = 'high'
            triggered.append('critical_sector')
            notes = 'Critical sector AI: development standards apply (proposed)'
        else:
            status = 'general'
            risk_level = 'minimal'

    # ============================================================
    # FALLBACK for any unmatched jurisdiction
    # ============================================================
    else:
        if agent_risk == 'high':
            status = 'review_recommended'
            risk_level = 'limited'
            notes = f'High-risk agent: review recommended under {j_id}'
        else:
            status = 'no_specific_rules'
            risk_level = 'minimal'
            notes = f'No specific rules matched for {j_id}'

    return status, risk_level, '|'.join(triggered) if triggered else None, notes


def run_assessment(batch_size=5000):
    """Run multi-jurisdiction assessment on all agents."""
    conn = psycopg2.connect(DB_URL)
    create_table(conn)
    
    jurisdictions = load_jurisdictions(conn)
    j_count = len(jurisdictions)
    
    # Get total agent count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM agents WHERE risk_class IS NOT NULL")
    total_agents = cur.fetchone()[0]
    logger.info(f"Agents to assess: {total_agents:,} x {j_count} jurisdictions = {total_agents * j_count:,} assessments")
    
    # Truncate existing (faster than upsert for full rebuild)
    cur.execute("TRUNCATE agent_jurisdiction_status")
    conn.commit()
    logger.info("Truncated existing assessments")
    
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
        """, (batch_size, offset))
        
        agents = cur.fetchall()
        if not agents:
            break
        
        # Build batch of all agent x jurisdiction combinations
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
        
        # Bulk insert
        psycopg2.extras.execute_values(cur, """
            INSERT INTO agent_jurisdiction_status 
            (agent_id, jurisdiction_id, status, risk_level, triggered_criteria, compliance_notes, assessed_at)
            VALUES %s
        """, insert_vals, page_size=10000)
        conn.commit()
        
        total_inserted += len(insert_vals)
        offset += batch_size
        elapsed = time.time() - start_time
        agents_done = offset if offset < total_agents else total_agents
        rate = agents_done / elapsed if elapsed > 0 else 0
        eta = (total_agents - agents_done) / rate if rate > 0 else 0
        
        logger.info(f"Progress: {agents_done:,}/{total_agents:,} agents "
                     f"({total_inserted:,} assessments, "
                     f"{rate:.0f} agents/sec, ETA: {eta/60:.1f}min)")
    
    elapsed = time.time() - start_time
    logger.info(f"\n{'='*60}")
    logger.info(f"MULTI-JURISDICTION ASSESSMENT COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Agents assessed: {total_agents:,}")
    logger.info(f"Jurisdictions: {j_count}")
    logger.info(f"Total assessments: {total_inserted:,}")
    logger.info(f"Time: {elapsed/60:.1f} minutes")
    
    # Summary stats
    cur.execute("""
        SELECT risk_level, COUNT(*) 
        FROM agent_jurisdiction_status 
        GROUP BY risk_level 
        ORDER BY COUNT(*) DESC
    """)
    logger.info(f"\nBy risk level:")
    for r in cur.fetchall():
        logger.info(f"  {r[0]:20s}: {r[1]:>12,}")
    
    cur.execute("""
        SELECT jurisdiction_id, 
               COUNT(*) FILTER (WHERE risk_level = 'high') as high,
               COUNT(*) FILTER (WHERE risk_level = 'limited') as limited,
               COUNT(*) FILTER (WHERE risk_level = 'minimal') as minimal
        FROM agent_jurisdiction_status 
        GROUP BY jurisdiction_id
        ORDER BY high DESC
        LIMIT 20
    """)
    logger.info(f"\nTop 20 jurisdictions by high-risk count:")
    logger.info(f"{'Jurisdiction':35s} {'High':>10s} {'Limited':>10s} {'Minimal':>10s}")
    for r in cur.fetchall():
        logger.info(f"  {r[0]:33s} {r[1]:>10,} {r[2]:>10,} {r[3]:>10,}")
    
    conn.close()


if __name__ == "__main__":
    run_assessment()
