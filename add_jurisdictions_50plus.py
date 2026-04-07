#!/usr/bin/env python3
"""Add 38 new jurisdictions to reach 52+ total in jurisdiction_registry."""

import sys, os
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

from agentindex.db.models import get_session
from sqlalchemy import text
import json

def add_new_jurisdictions():
    session = get_session()
    
    new_jurisdictions = [
        # ============================================================
        # US STATES (10 new)
        # ============================================================
        {
            "id": "us_ca_ab2013",
            "name": "California AI Training Data Transparency Act",
            "region": "US-CA",
            "country": "US",
            "status": "effective",
            "effective_date": "2026-01-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["covered_developer", "not_covered"]),
            "high_risk_criteria": json.dumps({
                "generative_ai": ["public_use_genai_developers"],
                "triggers": ["training_data_disclosure"]
            }),
            "requirements": json.dumps([
                "Publish high-level training data information",
                "Dataset summaries and IP flags",
                "Privacy and processing history disclosure"
            ]),
            "penalty_max": "$5,000 per violation per day",
            "penalty_per_violation": "$5,000 per violation per day",
            "focus": "training_data_transparency",
            "source_url": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240AB2013"
        },
        {
            "id": "us_ca_sb243",
            "name": "California Companion Chatbot Safety Act",
            "region": "US-CA",
            "country": "US",
            "status": "effective",
            "effective_date": "2026-01-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["companion_chatbot", "not_applicable"]),
            "high_risk_criteria": json.dumps({
                "chatbot_safety": ["minor_interactions", "self_harm_prevention"],
                "triggers": ["social_ai_chatbot", "minor_user"]
            }),
            "requirements": json.dumps([
                "Protocols to prevent self-harm content",
                "Disclosure of AI interaction to minors",
                "Safety protocols for companion chatbots"
            ]),
            "penalty_max": "AG enforcement",
            "penalty_per_violation": "Varies",
            "focus": "chatbot_minor_safety",
            "source_url": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260SB243"
        },
        {
            "id": "us_ut_aipa",
            "name": "Utah AI Policy Act",
            "region": "US-UT",
            "country": "US",
            "status": "effective",
            "effective_date": "2024-05-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["generative_ai_interaction", "not_covered"]),
            "high_risk_criteria": json.dumps({
                "consumer_interactions": ["generative_ai_disclosure"],
                "triggers": ["consumer_facing_genai"]
            }),
            "requirements": json.dumps([
                "Clear disclosure of generative AI interactions",
                "Consumer notification requirements",
                "AI regulatory sandbox participation option"
            ]),
            "penalty_max": "UDCP enforcement",
            "penalty_per_violation": "Varies",
            "focus": "transparency_disclosure",
            "source_url": "https://le.utah.gov/~2024/bills/static/SB0149.html"
        },
        {
            "id": "us_ut_sb226",
            "name": "Utah AI Amendments",
            "region": "US-UT",
            "country": "US",
            "status": "effective",
            "effective_date": "2025-05-07",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["regulated_ai_use", "general"]),
            "high_risk_criteria": json.dumps({
                "regulated_occupations": ["licensed_professionals_using_ai"],
                "triggers": ["professional_ai_use"]
            }),
            "requirements": json.dumps([
                "AI disclosure in regulated occupations",
                "Expanded AI regulatory sandbox",
                "Professional responsibility for AI outputs"
            ]),
            "penalty_max": "Professional licensing penalties",
            "penalty_per_violation": "Varies by profession",
            "focus": "professional_ai_use",
            "source_url": "https://le.utah.gov/~2025/bills/static/SB0226.html"
        },
        {
            "id": "us_ct_sb1295",
            "name": "Connecticut AI / Automated Decision Act",
            "region": "US-CT",
            "country": "US",
            "status": "enacted",
            "effective_date": "2026-07-01",
            "risk_model": "binary",
            "risk_classes": json.dumps(["automated_decision_system", "not_covered"]),
            "high_risk_criteria": json.dumps({
                "consequential_decisions": ["employment", "education", "financial", "housing", "healthcare"],
                "triggers": ["automated_decision_making", "profiling"]
            }),
            "requirements": json.dumps([
                "Impact assessments for automated decisions",
                "Consumer opt-out rights",
                "Right to human review",
                "Transparency about AI use in decisions"
            ]),
            "penalty_max": "AG enforcement under CTDPA",
            "penalty_per_violation": "$5,000 per violation",
            "focus": "automated_decision_making",
            "source_url": "https://www.cga.ct.gov/2025/ACT/PA/PDF/2025PA-00002-R00SB-01295-PA.PDF"
        },
        {
            "id": "us_ny_ll144",
            "name": "NYC Local Law 144 (AEDT)",
            "region": "US-NY",
            "country": "US",
            "status": "effective",
            "effective_date": "2023-07-05",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["aedt_employment", "not_applicable"]),
            "high_risk_criteria": json.dumps({
                "employment_ai": ["automated_employment_decision_tool"],
                "triggers": ["hiring_screening", "promotion_decisions"]
            }),
            "requirements": json.dumps([
                "Annual independent bias audit",
                "Public disclosure of audit results",
                "Notice to candidates 10 days before use",
                "Alternative selection process option"
            ]),
            "penalty_max": "$1,500 per violation",
            "penalty_per_violation": "$500-$1,500 per violation",
            "focus": "employment_bias_audit",
            "source_url": "https://legistar.council.nyc.gov/LegislationDetail.aspx?ID=4344524"
        },
        {
            "id": "us_ny_raise",
            "name": "New York RAISE Act",
            "region": "US-NY",
            "country": "US",
            "status": "enacted",
            "effective_date": "2027-01-01",
            "risk_model": "tiered_3",
            "risk_classes": json.dumps(["frontier_model", "high_risk", "general"]),
            "high_risk_criteria": json.dumps({
                "frontier_ai": ["large_compute_models", "critical_capabilities"],
                "triggers": ["compute_threshold", "capability_assessment"]
            }),
            "requirements": json.dumps([
                "Safety evaluations for frontier models",
                "Red-teaming requirements",
                "Incident reporting",
                "Whistleblower protections"
            ]),
            "penalty_max": "$25M per violation",
            "penalty_per_violation": "Up to $25M",
            "focus": "frontier_model_safety",
            "source_url": "https://www.nysenate.gov/legislation/bills/2025/A9449"
        },
        {
            "id": "us_il_hb3773",
            "name": "Illinois AI in Employment Act",
            "region": "US-IL",
            "country": "US",
            "status": "effective",
            "effective_date": "2026-01-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["ai_employment_decision", "not_applicable"]),
            "high_risk_criteria": json.dumps({
                "employment_ai": ["hiring", "firing", "discipline", "tenure", "training"],
                "triggers": ["ai_driven_employment_decision"]
            }),
            "requirements": json.dumps([
                "Compliance with Human Rights Act",
                "Non-discrimination in AI employment tools",
                "Documentation of AI decision processes"
            ]),
            "penalty_max": "Human Rights Act penalties",
            "penalty_per_violation": "Compensatory and punitive damages",
            "focus": "employment_discrimination",
            "source_url": "https://www.ilga.gov/legislation/billstatus.asp?DocNum=3773&GAID=17&GA=103"
        },
        {
            "id": "us_md_aieha",
            "name": "Maryland AI in Employment & Housing Act",
            "region": "US-MD",
            "country": "US",
            "status": "effective",
            "effective_date": "2025-10-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["ai_employment_housing", "not_applicable"]),
            "high_risk_criteria": json.dumps({
                "protected_decisions": ["employment", "housing"],
                "triggers": ["ai_assisted_decision", "discriminatory_outcome"]
            }),
            "requirements": json.dumps([
                "Prohibition of AI discrimination in employment",
                "Prohibition of AI discrimination in housing",
                "Compliance with existing anti-discrimination law"
            ]),
            "penalty_max": "Civil rights enforcement",
            "penalty_per_violation": "Compensatory damages",
            "focus": "anti_discrimination",
            "source_url": "https://mgaleg.maryland.gov/mgawebsite/Legislation/Details/SB0255"
        },
        {
            "id": "us_fed_takedown",
            "name": "TAKE IT DOWN Act (Federal)",
            "region": "US-FED",
            "country": "US",
            "status": "enacted",
            "effective_date": "2026-05-19",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["nonconsensual_intimate_imagery", "not_applicable"]),
            "high_risk_criteria": json.dumps({
                "ai_deepfakes": ["nonconsensual_intimate_images", "ai_generated_deepfakes"],
                "triggers": ["distribution", "creation"]
            }),
            "requirements": json.dumps([
                "Remove flagged content within 48 hours",
                "Establish notice-and-removal process",
                "FTC enforcement compliance"
            ]),
            "penalty_max": "3 years imprisonment",
            "penalty_per_violation": "Criminal penalties",
            "focus": "deepfake_intimate_imagery",
            "source_url": "https://www.congress.gov/bill/119th-congress/senate-bill/146"
        },

        # ============================================================
        # EU NATIONAL IMPLEMENTATIONS (8 new)
        # ============================================================
        {
            "id": "eu_de_aiact",
            "name": "Germany AI Act Implementation",
            "region": "EU-DE",
            "country": "DE",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "eu_ai_act_annex_iii": True,
                "national_additions": ["BaFin_financial_oversight", "automotive_ai"],
                "triggers": ["eu_ai_act_plus_national"]
            }),
            "requirements": json.dumps([
                "EU AI Act full compliance",
                "BaFin oversight for financial AI",
                "BSI cybersecurity requirements for AI",
                "National AI supervisory authority coordination"
            ]),
            "penalty_max": "€35M or 7% global turnover (EU AI Act)",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },
        {
            "id": "eu_fr_aiact",
            "name": "France AI Act Implementation",
            "region": "EU-FR",
            "country": "FR",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "eu_ai_act_annex_iii": True,
                "national_additions": ["CNIL_data_protection_overlap", "culture_sector_ai"],
                "triggers": ["eu_ai_act_plus_national"]
            }),
            "requirements": json.dumps([
                "EU AI Act full compliance",
                "CNIL coordination for AI + GDPR overlap",
                "AI Action Summit commitments",
                "National market surveillance via DGCCRF"
            ]),
            "penalty_max": "€35M or 7% global turnover (EU AI Act)",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },
        {
            "id": "eu_it_aiact",
            "name": "Italy AI Act Implementation",
            "region": "EU-IT",
            "country": "IT",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "eu_ai_act_annex_iii": True,
                "national_additions": ["AgID_public_sector_ai", "Garante_privacy_ai"],
                "triggers": ["eu_ai_act_plus_national"]
            }),
            "requirements": json.dumps([
                "EU AI Act full compliance",
                "AgID oversight for public sector AI",
                "Garante Privacy coordination",
                "National AI strategy alignment"
            ]),
            "penalty_max": "€35M or 7% global turnover (EU AI Act)",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },
        {
            "id": "eu_es_aiact",
            "name": "Spain AI Act Implementation",
            "region": "EU-ES",
            "country": "ES",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "eu_ai_act_annex_iii": True,
                "national_additions": ["AESIA_sandbox", "employment_ai_focus"],
                "triggers": ["eu_ai_act_plus_national"]
            }),
            "requirements": json.dumps([
                "EU AI Act full compliance",
                "AESIA (Spanish AI Supervisory Agency) oversight",
                "AI regulatory sandbox participation",
                "Employment AI specific requirements"
            ]),
            "penalty_max": "€35M or 7% global turnover (EU AI Act)",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },
        {
            "id": "eu_nl_aiact",
            "name": "Netherlands AI Act Implementation",
            "region": "EU-NL",
            "country": "NL",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "eu_ai_act_annex_iii": True,
                "national_additions": ["AP_data_protection_ai", "algorithm_register"],
                "triggers": ["eu_ai_act_plus_national"]
            }),
            "requirements": json.dumps([
                "EU AI Act full compliance",
                "Autoriteit Persoonsgegevens AI oversight",
                "Government algorithm register compliance",
                "Dutch AI Coalition standards"
            ]),
            "penalty_max": "€35M or 7% global turnover (EU AI Act)",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },
        {
            "id": "eu_se_aiact",
            "name": "Sweden AI Act Implementation",
            "region": "EU-SE",
            "country": "SE",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "eu_ai_act_annex_iii": True,
                "national_additions": ["IMY_data_protection_ai", "public_sector_ai"],
                "triggers": ["eu_ai_act_plus_national"]
            }),
            "requirements": json.dumps([
                "EU AI Act full compliance",
                "IMY (Integritetsskyddsmyndigheten) AI oversight",
                "Swedish public sector AI guidelines",
                "National AI centre coordination"
            ]),
            "penalty_max": "€35M or 7% global turnover (EU AI Act)",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },
        {
            "id": "eu_ie_aiact",
            "name": "Ireland AI Act Implementation",
            "region": "EU-IE",
            "country": "IE",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "eu_ai_act_annex_iii": True,
                "national_additions": ["DPC_ai_gdpr_overlap", "tech_hub_focus"],
                "triggers": ["eu_ai_act_plus_national"]
            }),
            "requirements": json.dumps([
                "EU AI Act full compliance",
                "S.I. No. 366/2025 competent authority designation",
                "DPC coordination for AI + GDPR",
                "National coordination mechanisms"
            ]),
            "penalty_max": "€35M or 7% global turnover (EU AI Act)",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },
        {
            "id": "eu_pl_aiact",
            "name": "Poland AI Act Implementation",
            "region": "EU-PL",
            "country": "PL",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "eu_ai_act_annex_iii": True,
                "national_additions": ["UODO_data_protection_ai"],
                "triggers": ["eu_ai_act_plus_national"]
            }),
            "requirements": json.dumps([
                "EU AI Act full compliance",
                "UODO AI oversight coordination",
                "National AI supervisory authority setup",
                "Polish market surveillance"
            ]),
            "penalty_max": "€35M or 7% global turnover (EU AI Act)",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },

        # ============================================================
        # ASIA-PACIFIC (7 new)
        # ============================================================
        {
            "id": "in_it_rules",
            "name": "India IT Rules (AI Amendments 2026)",
            "region": "IN",
            "country": "IN",
            "status": "effective",
            "effective_date": "2026-02-20",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["intermediary_ai", "general"]),
            "high_risk_criteria": json.dumps({
                "ai_content": ["synthetic_generated_content", "deepfakes"],
                "triggers": ["intermediary_hosting_ai_content", "digital_media"]
            }),
            "requirements": json.dumps([
                "AI-generated content labeling (explicit + implicit)",
                "Expedited removal of unlawful AI content",
                "Due diligence for AI content intermediaries",
                "Compliance with DPDP Act 2023"
            ]),
            "penalty_max": "Loss of safe harbor protection",
            "penalty_per_violation": "Civil and criminal liability",
            "focus": "content_labeling_intermediary",
            "source_url": "https://www.meity.gov.in/content/information-technology-intermediary-guidelines-and-digital-media-ethics-code-rules-2021"
        },
        {
            "id": "in_ai_governance",
            "name": "India AI Governance Guidelines",
            "region": "IN",
            "country": "IN",
            "status": "voluntary",
            "effective_date": "2025-12-01",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["high_risk", "moderate_risk", "low_risk"]),
            "high_risk_criteria": json.dumps({
                "sensitive_sectors": ["healthcare", "fintech", "education"],
                "triggers": ["ai_safety_board_designation"]
            }),
            "requirements": json.dumps([
                "Responsible AI development practices",
                "Sandbox-to-regulation compliance pathway",
                "AI Safety Board pilot sector compliance",
                "OECD/G20 AI principles alignment"
            ]),
            "penalty_max": "Voluntary (binding rules expected mid-2026)",
            "penalty_per_violation": "N/A (guidelines)",
            "focus": "governance_principles",
            "source_url": "https://indiaai.gov.in/ai-governance"
        },
        {
            "id": "tw_ai_basic_act",
            "name": "Taiwan AI Basic Act",
            "region": "TW",
            "country": "TW",
            "status": "effective",
            "effective_date": "2025-07-23",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["high_risk", "general"]),
            "high_risk_criteria": json.dumps({
                "ai_principles": ["human_rights", "safety", "privacy"],
                "triggers": ["government_designation"]
            }),
            "requirements": json.dumps([
                "AI governance principles adoption",
                "Innovation promotion measures",
                "Talent development requirements",
                "Cross-sector AI coordination"
            ]),
            "penalty_max": "Administrative guidance",
            "penalty_per_violation": "Reputational + administrative",
            "focus": "broad_principles",
            "source_url": "https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=J0030189"
        },
        {
            "id": "th_ai_governance",
            "name": "Thailand AI Governance Guidelines",
            "region": "TH",
            "country": "TH",
            "status": "voluntary",
            "effective_date": "2024-01-01",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["high_impact", "general"]),
            "high_risk_criteria": json.dumps({
                "ai_ethics": ["fairness", "transparency", "safety"],
                "triggers": ["voluntary_adoption"]
            }),
            "requirements": json.dumps([
                "AI ethics principles compliance",
                "Transparency in AI decision-making",
                "Data governance requirements",
                "Risk assessment practices"
            ]),
            "penalty_max": "N/A (voluntary)",
            "penalty_per_violation": "N/A (voluntary)",
            "focus": "governance_principles",
            "source_url": "https://www.onde.go.th/view/1/AI_Governance/EN-US"
        },
        {
            "id": "ph_ai_development",
            "name": "Philippines AI Development Act",
            "region": "PH",
            "country": "PH",
            "status": "proposed",
            "effective_date": None,
            "risk_model": "risk_based",
            "risk_classes": json.dumps(["high_risk", "moderate_risk", "low_risk"]),
            "high_risk_criteria": json.dumps({
                "critical_sectors": ["healthcare", "education", "government"],
                "triggers": ["significant_impact", "automated_decisions"]
            }),
            "requirements": json.dumps([
                "AI development standards",
                "Ethical AI guidelines",
                "National AI strategy compliance",
                "Data protection alignment"
            ]),
            "penalty_max": "TBD",
            "penalty_per_violation": "TBD",
            "focus": "development_governance",
            "source_url": "https://www.senate.gov.ph/lisdata/4130936975!.pdf"
        },
        {
            "id": "au_ai_guardrails",
            "name": "Australia Mandatory AI Guardrails",
            "region": "AU",
            "country": "AU",
            "status": "proposed",
            "effective_date": "2026-TBD",
            "risk_model": "risk_based",
            "risk_classes": json.dumps(["high_risk", "general_purpose", "low_risk"]),
            "high_risk_criteria": json.dumps({
                "consequential_decisions": ["employment", "financial", "healthcare", "government", "legal"],
                "triggers": ["significant_harm_potential", "vulnerable_populations"]
            }),
            "requirements": json.dumps([
                "Mandatory guardrails for high-risk AI",
                "Transparency and explainability",
                "Testing and monitoring requirements",
                "Human oversight mechanisms"
            ]),
            "penalty_max": "TBD (legislation pending)",
            "penalty_per_violation": "TBD",
            "focus": "high_risk_guardrails",
            "source_url": "https://www.industry.gov.au/publications/proposals-paper-introducing-mandatory-guardrails-ai-high-risk-settings"
        },
        {
            "id": "nz_ai_charter",
            "name": "New Zealand Algorithm Charter",
            "region": "NZ",
            "country": "NZ",
            "status": "voluntary",
            "effective_date": "2020-07-01",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["algorithmic_decision", "general"]),
            "high_risk_criteria": json.dumps({
                "government_algorithms": ["public_sector_decisions"],
                "triggers": ["operational_algorithm_use"]
            }),
            "requirements": json.dumps([
                "Transparency about algorithm use",
                "Human oversight of algorithmic decisions",
                "Regular algorithm reviews",
                "Privacy-protective practices"
            ]),
            "penalty_max": "N/A (voluntary charter)",
            "penalty_per_violation": "N/A",
            "focus": "government_algorithms",
            "source_url": "https://data.govt.nz/toolkit/data-ethics/government-algorithm-transparency-and-accountability/algorithm-charter/"
        },

        # ============================================================
        # MIDDLE EAST & AFRICA (5 new)
        # ============================================================
        {
            "id": "ae_ai_strategy",
            "name": "UAE AI Strategy 2031",
            "region": "AE",
            "country": "AE",
            "status": "effective",
            "effective_date": "2024-01-01",
            "risk_model": "licensing_based",
            "risk_classes": json.dumps(["licensed_ai", "general_ai", "sandbox_ai"]),
            "high_risk_criteria": json.dumps({
                "ai_licensing": ["DIFC_AI_licence", "ADGM_framework"],
                "triggers": ["commercial_ai_deployment", "government_ai"]
            }),
            "requirements": json.dumps([
                "AI licensing through DIFC or ADGM",
                "AIATC oversight compliance",
                "Stargate UAE infrastructure alignment",
                "Ethical AI principles adoption"
            ]),
            "penalty_max": "Licensing revocation + fines",
            "penalty_per_violation": "Varies by free zone",
            "focus": "licensing_innovation",
            "source_url": "https://ai.gov.ae/strategy/"
        },
        {
            "id": "sa_ai_ethics",
            "name": "Saudi Arabia AI Ethics Principles",
            "region": "SA",
            "country": "SA",
            "status": "effective",
            "effective_date": "2023-09-01",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["high_impact", "moderate_impact", "low_impact"]),
            "high_risk_criteria": json.dumps({
                "sdaia_oversight": ["healthcare_ai", "government_ai", "financial_ai"],
                "triggers": ["vision_2030_alignment", "critical_sector"]
            }),
            "requirements": json.dumps([
                "SDAIA ethical AI principles compliance",
                "National Data Bank alignment",
                "AI transparency and fairness",
                "Vision 2030 strategic alignment"
            ]),
            "penalty_max": "SDAIA enforcement",
            "penalty_per_violation": "Administrative measures",
            "focus": "ethics_principles",
            "source_url": "https://sdaia.gov.sa/en/SDAIA/about/Documents/SDAIA-AI-Ethics.pdf"
        },
        {
            "id": "ke_data_protection",
            "name": "Kenya Data Protection (AI Provisions)",
            "region": "KE",
            "country": "KE",
            "status": "effective",
            "effective_date": "2021-11-25",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["automated_decision", "general_processing"]),
            "high_risk_criteria": json.dumps({
                "automated_decisions": ["profiling", "automated_individual_decisions"],
                "triggers": ["significant_effects_on_individuals"]
            }),
            "requirements": json.dumps([
                "Right not to be subject to automated decisions",
                "Data protection impact assessments",
                "Transparency about automated processing",
                "ODPC compliance requirements"
            ]),
            "penalty_max": "KES 5M or 1% annual turnover",
            "penalty_per_violation": "Up to KES 5M",
            "focus": "data_protection_automated",
            "source_url": "https://www.odpc.go.ke/dpa-act/"
        },
        {
            "id": "ng_ndpr",
            "name": "Nigeria Data Protection (AI Provisions)",
            "region": "NG",
            "country": "NG",
            "status": "effective",
            "effective_date": "2023-06-14",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["automated_decision", "general_processing"]),
            "high_risk_criteria": json.dumps({
                "automated_decisions": ["profiling", "ai_decision_making"],
                "triggers": ["personal_data_processing", "automated_decisions"]
            }),
            "requirements": json.dumps([
                "Data protection compliance for AI systems",
                "Right to object to automated profiling",
                "Impact assessments for high-risk processing",
                "NDPC registration and compliance"
            ]),
            "penalty_max": "NGN 10M or 2% annual turnover",
            "penalty_per_violation": "Up to NGN 10M",
            "focus": "data_protection_automated",
            "source_url": "https://ndpc.gov.ng/Files/Nigeria_Data_Protection_Act_2023.pdf"
        },
        {
            "id": "za_popia_ai",
            "name": "South Africa POPIA (AI Provisions)",
            "region": "ZA",
            "country": "ZA",
            "status": "effective",
            "effective_date": "2021-07-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["automated_decision", "general_processing"]),
            "high_risk_criteria": json.dumps({
                "automated_decisions": ["profiling", "automated_individual_decisions"],
                "triggers": ["personal_information_processing"]
            }),
            "requirements": json.dumps([
                "Right not to be subject to automated decisions",
                "Purpose limitation for AI processing",
                "Information regulator oversight",
                "Prior authorization for certain processing"
            ]),
            "penalty_max": "ZAR 10M or imprisonment",
            "penalty_per_violation": "Up to ZAR 10M",
            "focus": "data_protection_automated",
            "source_url": "https://popia.co.za/"
        },

        # ============================================================
        # LATIN AMERICA (4 new)
        # ============================================================
        {
            "id": "cl_ai_bill",
            "name": "Chile AI Regulation Bill",
            "region": "CL",
            "country": "CL",
            "status": "proposed",
            "effective_date": None,
            "risk_model": "risk_based",
            "risk_classes": json.dumps(["high_risk", "moderate_risk", "low_risk"]),
            "high_risk_criteria": json.dumps({
                "fundamental_rights": ["safety", "privacy", "non_discrimination"],
                "triggers": ["automated_decisions", "critical_sectors"]
            }),
            "requirements": json.dumps([
                "Risk assessment requirements",
                "Transparency obligations",
                "Human oversight mechanisms",
                "Alignment with OECD AI principles"
            ]),
            "penalty_max": "TBD",
            "penalty_per_violation": "TBD",
            "focus": "broad_safety",
            "source_url": "https://www.bcn.cl/leychile"
        },
        {
            "id": "co_ai_guidelines",
            "name": "Colombia AI Ethics Framework",
            "region": "CO",
            "country": "CO",
            "status": "voluntary",
            "effective_date": "2024-01-01",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["high_impact", "general"]),
            "high_risk_criteria": json.dumps({
                "government_ai": ["public_sector_ai_use"],
                "triggers": ["voluntary_adoption"]
            }),
            "requirements": json.dumps([
                "AI ethics guidelines compliance",
                "Transparency in government AI",
                "MinTIC coordination",
                "OECD AI principles alignment"
            ]),
            "penalty_max": "N/A (voluntary)",
            "penalty_per_violation": "N/A",
            "focus": "ethics_principles",
            "source_url": "https://www.mintic.gov.co/portal/inicio/Sala-de-prensa/Noticias/"
        },
        {
            "id": "pe_ai_law",
            "name": "Peru AI Promotion Law",
            "region": "PE",
            "country": "PE",
            "status": "effective",
            "effective_date": "2023-07-01",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["government_ai", "general"]),
            "high_risk_criteria": json.dumps({
                "government_ai": ["public_administration_ai"],
                "triggers": ["government_deployment"]
            }),
            "requirements": json.dumps([
                "AI development promotion",
                "Ethical use principles",
                "Government AI deployment standards",
                "National AI strategy alignment"
            ]),
            "penalty_max": "Administrative guidance",
            "penalty_per_violation": "N/A",
            "focus": "promotion_ethics",
            "source_url": "https://www.gob.pe/institucion/congreso-de-la-republica/normas-legales/"
        },
        {
            "id": "mx_ai_regulation",
            "name": "Mexico AI Regulation Initiative",
            "region": "MX",
            "country": "MX",
            "status": "proposed",
            "effective_date": None,
            "risk_model": "risk_based",
            "risk_classes": json.dumps(["high_risk", "moderate_risk", "low_risk"]),
            "high_risk_criteria": json.dumps({
                "critical_sectors": ["healthcare", "education", "government", "finance"],
                "triggers": ["significant_impact", "automated_decisions"]
            }),
            "requirements": json.dumps([
                "Risk-based AI classification",
                "Transparency and accountability",
                "Human rights protection",
                "National AI strategy alignment"
            ]),
            "penalty_max": "TBD",
            "penalty_per_violation": "TBD",
            "focus": "broad_safety",
            "source_url": "https://www.senado.gob.mx/"
        },

        # ============================================================
        # INTERNATIONAL FRAMEWORKS (4 new)
        # ============================================================
        {
            "id": "intl_oecd_ai",
            "name": "OECD AI Principles",
            "region": "INTL",
            "country": "INTL",
            "status": "voluntary",
            "effective_date": "2024-05-02",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["trustworthy_ai", "non_compliant"]),
            "high_risk_criteria": json.dumps({
                "trustworthy_ai": ["human_centred", "transparent", "robust", "accountable"],
                "triggers": ["oecd_member_adoption"]
            }),
            "requirements": json.dumps([
                "Inclusive growth and sustainable development",
                "Human-centred values and fairness",
                "Transparency and explainability",
                "Robustness, security and safety",
                "Accountability"
            ]),
            "penalty_max": "N/A (voluntary principles)",
            "penalty_per_violation": "N/A",
            "focus": "governance_principles",
            "source_url": "https://oecd.ai/en/ai-principles"
        },
        {
            "id": "intl_coe_convention",
            "name": "Council of Europe AI Convention",
            "region": "INTL",
            "country": "INTL",
            "status": "enacted",
            "effective_date": "2025-09-01",
            "risk_model": "rights_based",
            "risk_classes": json.dumps(["rights_impacting", "general"]),
            "high_risk_criteria": json.dumps({
                "human_rights": ["fundamental_rights_impact", "democratic_values"],
                "triggers": ["public_sector_ai", "rights_affecting_decisions"]
            }),
            "requirements": json.dumps([
                "Human rights protection in AI deployment",
                "Transparency requirements",
                "Accountability and oversight mechanisms",
                "Risk and impact management",
                "Remedies for AI-caused harm"
            ]),
            "penalty_max": "Treaty obligations (national enforcement)",
            "penalty_per_violation": "National law dependent",
            "focus": "human_rights",
            "source_url": "https://www.coe.int/en/web/artificial-intelligence/the-framework-convention-on-artificial-intelligence"
        },
        {
            "id": "intl_iso42001",
            "name": "ISO/IEC 42001 AI Management System",
            "region": "INTL",
            "country": "INTL",
            "status": "effective",
            "effective_date": "2023-12-18",
            "risk_model": "management_system",
            "risk_classes": json.dumps(["certified", "non_certified"]),
            "high_risk_criteria": json.dumps({
                "management_system": ["ai_lifecycle", "risk_management"],
                "triggers": ["voluntary_certification", "regulatory_reference"]
            }),
            "requirements": json.dumps([
                "AI management system establishment",
                "Risk assessment and treatment",
                "AI policy and objectives",
                "Competence and awareness",
                "Monitoring, measurement and evaluation"
            ]),
            "penalty_max": "N/A (certification standard)",
            "penalty_per_violation": "N/A",
            "focus": "management_system",
            "source_url": "https://www.iso.org/standard/81230.html"
        },
        {
            "id": "cn_ai_labeling",
            "name": "China AI Content Labeling Rules",
            "region": "CN",
            "country": "CN",
            "status": "effective",
            "effective_date": "2025-09-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["ai_content_provider", "ai_content_distributor"]),
            "high_risk_criteria": json.dumps({
                "ai_generated_content": ["text", "image", "audio", "video", "vr"],
                "triggers": ["content_generation", "content_distribution"]
            }),
            "requirements": json.dumps([
                "Explicit AI content labels (text, audio, image indicators)",
                "Implicit labels (metadata, provider ID, content ID)",
                "Platform detection mechanisms",
                "Label reinforcement by distributors"
            ]),
            "penalty_max": "CAC enforcement measures",
            "penalty_per_violation": "Content removal + penalties",
            "focus": "content_labeling",
            "source_url": "https://www.cac.gov.cn/"
        },
    ]

    insert_count = 0
    skip_count = 0
    
    for j in new_jurisdictions:
        try:
            existing = session.execute(
                text("SELECT id FROM jurisdiction_registry WHERE id = :id"),
                {"id": j["id"]}
            ).fetchone()
            
            if existing:
                skip_count += 1
                continue
            
            session.execute(text("""
                INSERT INTO jurisdiction_registry 
                (id, name, region, country, status, effective_date, risk_model,
                 risk_classes, high_risk_criteria, requirements, penalty_max,
                 penalty_per_violation, focus, source_url, last_checked, last_updated, changelog)
                VALUES 
                (:id, :name, :region, :country, :status, :effective_date, :risk_model,
                 :risk_classes, :high_risk_criteria, :requirements, :penalty_max,
                 :penalty_per_violation, :focus, :source_url, :last_checked, :last_updated, :changelog)
            """), {
                **j,
                "last_checked": "2026-02-22T13:00:00Z",
                "last_updated": "2026-02-22T13:00:00Z",
                "changelog": "[]"
            })
            insert_count += 1
        except Exception as e:
            print(f"ERROR inserting {j['id']}: {e}")
    
    session.commit()
    
    # Final count
    total = session.execute(text("SELECT COUNT(*) FROM jurisdiction_registry")).scalar()
    
    print(f"\n{'='*60}")
    print(f"JURISDICTION EXPANSION COMPLETE")
    print(f"{'='*60}")
    print(f"New jurisdictions added: {insert_count}")
    print(f"Already existed (skipped): {skip_count}")
    print(f"TOTAL jurisdictions: {total}")
    print(f"{'='*60}")
    
    # Summary by region
    regions = session.execute(text("""
        SELECT country, COUNT(*) as cnt 
        FROM jurisdiction_registry 
        GROUP BY country 
        ORDER BY cnt DESC
    """)).fetchall()
    
    print(f"\nBy country/region:")
    for r in regions:
        print(f"  {r[0]:5s}: {r[1]} jurisdictions")
    
    # Summary by status
    statuses = session.execute(text("""
        SELECT status, COUNT(*) as cnt 
        FROM jurisdiction_registry 
        GROUP BY status 
        ORDER BY cnt DESC
    """)).fetchall()
    
    print(f"\nBy status:")
    for s in statuses:
        print(f"  {s[0]:20s}: {s[1]}")

if __name__ == "__main__":
    add_new_jurisdictions()
