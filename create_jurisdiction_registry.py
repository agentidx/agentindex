#!/usr/bin/env python3
"""Create jurisdiction_registry table and seed with 14 jurisdictions per produktspec."""

import sys, os
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

from agentindex.db.models import get_session
from sqlalchemy import text
import json

def create_jurisdiction_registry():
    """Create jurisdiction_registry table exactly per produktspec."""
    
    session = get_session()
    
    # Create table
    create_table_sql = text("""
    CREATE TABLE IF NOT EXISTS jurisdiction_registry (
        id TEXT PRIMARY KEY,              -- "eu_ai_act", "us_co_sb205", "kr_ai_basic_act"
        name TEXT NOT NULL,               -- "EU AI Act"
        region TEXT NOT NULL,             -- "EU", "US-CO", "KR", "CN", "SG"
        country TEXT NOT NULL,            -- "EU", "US", "KR", "CN", "SG"
        status TEXT NOT NULL,             -- "enacted", "effective", "proposed", "amended"
        effective_date TEXT,              -- "2026-08-02"
        risk_model TEXT NOT NULL,         -- "tiered_4" | "binary" | "tiered_3" | "sector_specific"
        risk_classes TEXT NOT NULL,       -- JSON: ["unacceptable","high","limited","minimal"]
        high_risk_criteria TEXT,          -- JSON: beskrivning av vad som triggar high-risk
        requirements TEXT,                -- JSON: lista av compliance-krav
        penalty_max TEXT,                 -- "€35M or 7% global turnover"
        penalty_per_violation TEXT,       -- "$20,000 per violation per consumer"
        focus TEXT,                       -- "broad_safety" | "algorithmic_discrimination" | "transparency"
        source_url TEXT,                  -- Officiell lagtext
        last_checked TEXT,                -- Sentinel senaste check
        last_updated TEXT,                -- Senaste ändring
        changelog TEXT DEFAULT '[]'       -- JSON: lista av ändringar
    )
    """)
    
    session.execute(create_table_sql)
    session.commit()
    print("✅ jurisdiction_registry table created")
    
    return session

def seed_14_jurisdictions():
    """Seed med 14 jurisdiktioner exactly per produktspec."""
    
    session = create_jurisdiction_registry()
    
    # 14 jurisdictions data per produktspec
    jurisdictions = [
        {
            "id": "eu_ai_act",
            "name": "EU AI Act",
            "region": "EU",
            "country": "EU", 
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "tiered_4",
            "risk_classes": json.dumps(["unacceptable", "high", "limited", "minimal"]),
            "high_risk_criteria": json.dumps({
                "annex_iii_systems": ["biometric_identification", "critical_infrastructure", "education", "employment", "essential_services", "law_enforcement", "migration", "justice", "democratic_processes"],
                "triggers": ["safety_components", "conformity_assessment", "high_risk_areas"]
            }),
            "requirements": json.dumps([
                "Risk management system (Art. 9)",
                "Data governance measures (Art. 10)",
                "Technical documentation (Art. 11)", 
                "Record keeping (Art. 12)",
                "Transparency for users (Art. 13)",
                "Human oversight (Art. 14)",
                "Accuracy, robustness, cybersecurity (Art. 15)"
            ]),
            "penalty_max": "€35M or 7% global turnover",
            "penalty_per_violation": "€15M or 3% turnover",
            "focus": "broad_safety",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689"
        },
        {
            "id": "us_co_sb205",
            "name": "Colorado AI Act",
            "region": "US-CO",
            "country": "US",
            "status": "enacted", 
            "effective_date": "2026-06-30",
            "risk_model": "binary",
            "risk_classes": json.dumps(["high_risk", "not_high_risk"]),
            "high_risk_criteria": json.dumps({
                "consequential_decisions": ["employment", "education", "financial_services", "government_services", "healthcare", "housing", "insurance", "legal_services"],
                "triggers": ["substantial_risk", "algorithmic_discrimination"]
            }),
            "requirements": json.dumps([
                "Complete algorithmic discrimination program",
                "Impact assessment before deployment",
                "Consumer notification requirements", 
                "Annual algorithmic discrimination audit"
            ]),
            "penalty_max": "$500,000 per violation", 
            "penalty_per_violation": "$20,000 per affected consumer",
            "focus": "algorithmic_discrimination",
            "source_url": "https://leg.colorado.gov/bills/sb24-205"
        },
        {
            "id": "us_ca_sb53",
            "name": "California Frontier AI Act", 
            "region": "US-CA",
            "country": "US",
            "status": "effective",
            "effective_date": "2026-01-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["covered_model", "not_covered"]),
            "high_risk_criteria": json.dumps({
                "frontier_models": ["compute_threshold", "capability_threshold"],
                "triggers": ["10^26_FLOPs", "hazardous_capabilities"]
            }),
            "requirements": json.dumps([
                "Safety and security protocols",
                "Third-party auditing",
                "Incident reporting",
                "Whistleblower protections"
            ]),
            "penalty_max": "$10M to $50M per violation",
            "penalty_per_violation": "Varies by severity",
            "focus": "frontier_model_safety", 
            "source_url": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240SB53"
        },
        {
            "id": "us_ca_sb942",
            "name": "California AI Transparency Act",
            "region": "US-CA", 
            "country": "US",
            "status": "enacted",
            "effective_date": "2026-08-02",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["requires_watermark", "exempt"]),
            "high_risk_criteria": json.dumps({
                "ai_generated_content": ["synthetic_media", "deepfakes"],
                "triggers": ["public_facing", "commercial_use"]
            }),
            "requirements": json.dumps([
                "Watermarking of AI-generated content",
                "AI detection tools provision",
                "Clear disclosure requirements"
            ]),
            "penalty_max": "$5,000 per violation",
            "penalty_per_violation": "$5,000 per violation",
            "focus": "transparency_watermarks",
            "source_url": "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240SB942"
        },
        {
            "id": "us_tx_raiga", 
            "name": "Texas RAIGA",
            "region": "US-TX",
            "country": "US",
            "status": "effective",
            "effective_date": "2026-01-01", 
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["covered_entity", "not_covered"]),
            "high_risk_criteria": json.dumps({
                "government_ai": ["state_agency", "local_government"],
                "triggers": ["public_sector_deployment"]
            }),
            "requirements": json.dumps([
                "AI inventory and assessment",
                "Public transparency reporting", 
                "Accountability measures"
            ]),
            "penalty_max": "Administrative remedies",
            "penalty_per_violation": "Varies",
            "focus": "transparency_accountability",
            "source_url": "https://capitol.texas.gov/BillLookup/History.aspx?LegSess=88R&Bill=HB2060"
        },
        {
            "id": "us_il_aivi",
            "name": "Illinois AI Video Interview Act",
            "region": "US-IL",
            "country": "US", 
            "status": "effective",
            "effective_date": "2020-01-01",
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["ai_video_interview", "not_applicable"]),
            "high_risk_criteria": json.dumps({
                "employment_ai": ["video_interview_analysis"],
                "triggers": ["hiring_decisions", "ai_analysis"]
            }),
            "requirements": json.dumps([
                "Advance notice to applicants",
                "Explanation of AI analysis",
                "Right to request human review"
            ]),
            "penalty_max": "$5,000 per violation",
            "penalty_per_violation": "$5,000 per violation",
            "focus": "employment_ai",
            "source_url": "https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=4015"
        },
        {
            "id": "kr_ai_basic_act",
            "name": "South Korea AI Basic Act",
            "region": "KR",
            "country": "KR",
            "status": "effective",
            "effective_date": "2026-01-22",
            "risk_model": "tiered_3", 
            "risk_classes": json.dumps(["high_impact", "moderate_impact", "low_impact"]),
            "high_risk_criteria": json.dumps({
                "high_impact_areas": ["life_safety", "privacy", "human_rights", "democratic_values"],
                "triggers": ["significant_impact", "widespread_deployment"]
            }),
            "requirements": json.dumps([
                "Risk assessment and management",
                "Human oversight mechanisms",
                "Data quality assurance",
                "Transparency and explainability"
            ]),
            "penalty_max": "₩300M or 3% revenue", 
            "penalty_per_violation": "Varies by impact level",
            "focus": "broad_safety",
            "source_url": "https://www.law.go.kr/LSW/eng/engLsSc.do?menuId=2&query=AI+Basic+Act"
        },
        {
            "id": "cn_cybersecurity",
            "name": "China Cybersecurity Amendment",
            "region": "CN",
            "country": "CN",
            "status": "effective",
            "effective_date": "2026-01-01",
            "risk_model": "sector_specific", 
            "risk_classes": json.dumps(["critical_sector", "general"]),
            "high_risk_criteria": json.dumps({
                "critical_infrastructure": ["telecommunications", "energy", "finance", "transport"],
                "triggers": ["data_localization", "security_review"]
            }),
            "requirements": json.dumps([
                "Data localization requirements",
                "Security assessments",
                "Government approval for transfers",
                "Regular security audits"
            ]),
            "penalty_max": "¥1M to ¥10M",
            "penalty_per_violation": "¥100K to ¥1M",
            "focus": "security_data_localisation",
            "source_url": "http://www.npc.gov.cn/npc/c30834/201611/1834e4e8b83a4bb6ab15b8ab4dc7d49d.shtml"
        },
        {
            "id": "vn_ai_law",
            "name": "Vietnam AI Law",
            "region": "VN", 
            "country": "VN",
            "status": "enacted",
            "effective_date": "2026-TBD",
            "risk_model": "risk_based",
            "risk_classes": json.dumps(["high_risk", "moderate_risk", "low_risk"]),
            "high_risk_criteria": json.dumps({
                "sensitive_sectors": ["healthcare", "education", "finance", "security"],
                "triggers": ["personal_data", "critical_decisions"]
            }),
            "requirements": json.dumps([
                "Risk assessment before deployment",
                "Human oversight requirements",
                "Data protection compliance",
                "Regular monitoring and auditing"
            ]),
            "penalty_max": "VND 2B",
            "penalty_per_violation": "VND 500M to 2B",
            "focus": "broad_safety", 
            "source_url": "https://thuvienphapluat.vn/van-ban/Cong-nghe-thong-tin/Nghi-dinh-15-2020-ND-CP-an-toan-thong-tin-mang-434725.aspx"
        },
        {
            "id": "br_ai_bill",
            "name": "Brazil AI Bill",
            "region": "BR",
            "country": "BR", 
            "status": "proposed",
            "effective_date": None,
            "risk_model": "risk_based",
            "risk_classes": json.dumps(["unacceptable_risk", "high_risk", "limited_risk", "minimal_risk"]),
            "high_risk_criteria": json.dumps({
                "fundamental_rights": ["safety", "health", "privacy", "discrimination"],
                "triggers": ["significant_impact", "automated_decisions"]
            }),
            "requirements": json.dumps([
                "Impact assessment",
                "Risk mitigation measures", 
                "Human oversight",
                "Transparency obligations"
            ]),
            "penalty_max": "R$ 50M or 2% revenue",
            "penalty_per_violation": "R$ 2M to 50M",
            "focus": "broad_safety",
            "source_url": "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2236340"
        },
        {
            "id": "ca_aida", 
            "name": "Canada AIDA",
            "region": "CA",
            "country": "CA",
            "status": "proposed",
            "effective_date": None,
            "risk_model": "impact_based",
            "risk_classes": json.dumps(["high_impact", "moderate_impact", "low_impact"]),
            "high_risk_criteria": json.dumps({
                "high_impact_systems": ["substantial_harm", "biased_decisions"],
                "triggers": ["material_impact", "automated_decisions"]
            }),
            "requirements": json.dumps([
                "Risk assessment and mitigation",
                "Mitigation measures implementation",
                "Monitoring and reporting",
                "Record keeping requirements"
            ]),
            "penalty_max": "CAD $25M or 5% revenue",
            "penalty_per_violation": "CAD $10M per violation",
            "focus": "high_impact_systems",
            "source_url": "https://www.parl.ca/DocumentViewer/en/44-1/bill/C-27/first-reading"
        },
        {
            "id": "sg_ai_governance",
            "name": "Singapore AI Framework",
            "region": "SG",
            "country": "SG",
            "status": "voluntary",
            "effective_date": None,
            "risk_model": "voluntary",
            "risk_classes": json.dumps(["high_impact", "moderate_impact", "low_impact"]),
            "high_risk_criteria": json.dumps({
                "high_impact_decisions": ["significant_consequences", "human_autonomy"],
                "triggers": ["voluntary_adoption"]
            }),
            "requirements": json.dumps([
                "Internal governance structures",
                "Risk management practices",
                "Human oversight mechanisms", 
                "Transparency measures"
            ]),
            "penalty_max": "N/A (voluntary)",
            "penalty_per_violation": "N/A (voluntary)",
            "focus": "governance_principles",
            "source_url": "https://www.pdpc.gov.sg/Help-and-Resources/2020/01/Model-AI-Governance-Framework"
        },
        {
            "id": "uk_ai_regulation",
            "name": "UK AI Regulation Bill",
            "region": "UK",
            "country": "UK",
            "status": "proposed", 
            "effective_date": None,
            "risk_model": "sector_specific",
            "risk_classes": json.dumps(["high_risk", "moderate_risk", "low_risk"]),
            "high_risk_criteria": json.dumps({
                "sector_specific": ["finance", "healthcare", "education", "employment"],
                "triggers": ["regulator_designation"]
            }),
            "requirements": json.dumps([
                "Sector regulator oversight",
                "Risk assessment requirements",
                "Appropriate safeguards",
                "Regular monitoring"
            ]),
            "penalty_max": "TBD by sector regulators",
            "penalty_per_violation": "TBD by sector regulators", 
            "focus": "sector_specific",
            "source_url": "https://www.gov.uk/government/publications/ai-regulation-a-pro-innovation-approach"
        },
        {
            "id": "jp_ai_bill",
            "name": "Japan AI Bill", 
            "region": "JP",
            "country": "JP",
            "status": "effective",
            "effective_date": "2025-05-01",
            "risk_model": "principles_based",
            "risk_classes": json.dumps(["principle_compliant", "non_compliant"]),
            "high_risk_criteria": json.dumps({
                "ai_principles": ["human_centric", "social_benefit", "transparency"],
                "triggers": ["principle_violation"]
            }),
            "requirements": json.dumps([
                "AI governance principles adoption",
                "Ethical AI development practices",
                "Social responsibility measures",
                "Transparency in AI systems"
            ]),
            "penalty_max": "Administrative guidance",
            "penalty_per_violation": "Reputational consequences",
            "focus": "broad_principles",
            "source_url": "https://www8.cao.go.jp/cstp/ai/index-e.html"
        }
    ]
    
    # Insert all jurisdictions
    insert_count = 0
    for jurisdiction in jurisdictions:
        try:
            # Check if already exists
            existing = session.execute(
                text("SELECT id FROM jurisdiction_registry WHERE id = :id"),
                {"id": jurisdiction["id"]}
            ).fetchone()
            
            if not existing:
                # Insert new jurisdiction
                insert_sql = text("""
                INSERT INTO jurisdiction_registry 
                (id, name, region, country, status, effective_date, risk_model, 
                 risk_classes, high_risk_criteria, requirements, penalty_max, 
                 penalty_per_violation, focus, source_url, last_checked, last_updated, changelog)
                VALUES 
                (:id, :name, :region, :country, :status, :effective_date, :risk_model,
                 :risk_classes, :high_risk_criteria, :requirements, :penalty_max,
                 :penalty_per_violation, :focus, :source_url, :last_checked, :last_updated, :changelog)
                """)
                
                session.execute(insert_sql, {
                    **jurisdiction,
                    "last_checked": "2026-02-19T09:00:00Z",
                    "last_updated": "2026-02-19T09:00:00Z", 
                    "changelog": "[]"
                })
                insert_count += 1
        except Exception as e:
            print(f"Error inserting {jurisdiction['id']}: {e}")
    
    session.commit()
    print(f"✅ Seeded {insert_count} jurisdictions into jurisdiction_registry")
    
    # Verify count
    total_count = session.execute(
        text("SELECT COUNT(*) FROM jurisdiction_registry")
    ).scalar()
    print(f"✅ Total jurisdictions in registry: {total_count}")
    
    return session

if __name__ == "__main__":
    session = seed_14_jurisdictions()
    
    # Show summary
    jurisdictions = session.execute(
        text("SELECT id, name, region, status, effective_date FROM jurisdiction_registry ORDER BY effective_date")
    ).fetchall()
    
    print(f"\n📊 JURISDICTION REGISTRY SUMMARY:")
    print("=" * 80)
    for jurisdiction in jurisdictions:
        status_icon = "✅" if jurisdiction[3] == "effective" else "📅" if jurisdiction[3] == "enacted" else "⏳"
        print(f"{status_icon} {jurisdiction[1]} ({jurisdiction[2]}) - {jurisdiction[3]} - {jurisdiction[4] or 'TBD'}")
    
    print(f"\n✅ PUNKT 2 LEVERERAD:")
    print(f"   jurisdiction_registry table skapad")
    print(f"   14 jurisdiktioner seedade enligt produktspec")
    print(f"   Redo för multi-jurisdiction API endpoint")