"""
EU AI Act - Structured Regulatory Data
Annex III high-risk categories + key articles for compliance checking.

This is the regulatory knowledge base that powers risk classification.
"""

# EU AI Act Annex III - High-Risk AI Systems
ANNEX_III_CATEGORIES = [
    {
        "id": "annex3_1",
        "category": "Biometrics",
        "subcategories": [
            "Remote biometric identification systems",
            "AI systems for biometric categorisation by sensitive attributes",
            "AI systems for emotion recognition"
        ],
        "keywords": ["biometric", "facial recognition", "face detection", "emotion recognition",
                      "fingerprint", "iris scan", "voice identification", "gait analysis",
                      "biometric categorisation", "remote identification"],
        "articles": ["Art. 5", "Art. 26"],
        "risk_indicators": ["real-time", "public spaces", "law enforcement"]
    },
    {
        "id": "annex3_2",
        "category": "Critical Infrastructure",
        "subcategories": [
            "Safety components of critical infrastructure",
            "AI in management/operation of road traffic",
            "AI in supply of water, gas, heating, electricity"
        ],
        "keywords": ["infrastructure", "traffic", "road", "water supply", "gas", "electricity",
                      "power grid", "heating", "safety component", "scada", "iot",
                      "autonomous driving", "traffic management", "energy management"],
        "articles": ["Art. 6"],
        "risk_indicators": ["safety-critical", "physical harm", "essential services"]
    },
    {
        "id": "annex3_3",
        "category": "Education & Vocational Training",
        "subcategories": [
            "AI to determine access to education",
            "AI to evaluate learning outcomes",
            "AI to determine level of education",
            "AI to monitor prohibited behaviour during tests"
        ],
        "keywords": ["education", "school", "university", "exam", "grading", "admission",
                      "student", "learning", "assessment", "proctoring", "cheating detection",
                      "academic", "enrollment", "vocational training"],
        "articles": ["Art. 6"],
        "risk_indicators": ["access determination", "evaluation", "proctoring"]
    },
    {
        "id": "annex3_4",
        "category": "Employment & Workers Management",
        "subcategories": [
            "AI for recruitment/selection",
            "AI for decisions on employment conditions",
            "AI for task allocation based on behaviour/traits",
            "AI for monitoring/evaluating workers"
        ],
        "keywords": ["recruitment", "hiring", "cv screening", "resume", "employee",
                      "worker", "performance review", "promotion", "termination",
                      "workforce management", "hr", "human resources", "talent",
                      "interview", "candidate screening", "workplace monitoring",
                      "cv", "screening", "candidate", "job application",
                      "applicant", "recruit", "rank candidate", "shortlist"],
        "articles": ["Art. 6", "Art. 26"],
        "risk_indicators": ["hiring decisions", "performance evaluation", "workplace surveillance"]
    },
    {
        "id": "annex3_5",
        "category": "Essential Services Access",
        "subcategories": [
            "AI for creditworthiness assessment",
            "AI for risk assessment in life/health insurance",
            "AI for evaluating eligibility for public benefits",
            "AI for credit scoring"
        ],
        "keywords": ["credit", "loan", "insurance", "benefits", "social security",
                      "creditworthiness", "credit score", "risk assessment", "underwriting",
                      "eligibility", "welfare", "public assistance", "financial services",
                      "banking", "mortgage"],
        "articles": ["Art. 6"],
        "risk_indicators": ["financial access", "benefit determination", "insurance pricing"]
    },
    {
        "id": "annex3_6",
        "category": "Law Enforcement",
        "subcategories": [
            "AI for risk assessment of natural persons",
            "AI as polygraph or similar",
            "AI for evaluation of evidence reliability",
            "AI for profiling/risk assessment for crimes",
            "AI for crime analytics on personal data"
        ],
        "keywords": ["law enforcement", "police", "crime", "criminal", "evidence",
                      "polygraph", "lie detection", "profiling", "predictive policing",
                      "forensic", "investigation", "suspect", "recidivism"],
        "articles": ["Art. 5", "Art. 6"],
        "risk_indicators": ["criminal justice", "profiling", "evidence assessment"]
    },
    {
        "id": "annex3_7",
        "category": "Migration, Asylum & Border Control",
        "subcategories": [
            "AI as polygraph or similar during interviews",
            "AI for risk assessment regarding security/health risks",
            "AI for examining applications for asylum/visa/residence",
            "AI for identification of persons in migration context"
        ],
        "keywords": ["migration", "asylum", "border", "visa", "immigration",
                      "refugee", "residence permit", "border control", "customs",
                      "travel document", "identity verification border"],
        "articles": ["Art. 5", "Art. 6"],
        "risk_indicators": ["border screening", "asylum decisions", "migration profiling"]
    },
    {
        "id": "annex3_8",
        "category": "Administration of Justice & Democratic Processes",
        "subcategories": [
            "AI for researching/interpreting facts and law",
            "AI for applying law to facts",
            "AI used to influence voters in elections"
        ],
        "keywords": ["judicial", "court", "judge", "legal decision", "sentencing",
                      "election", "voting", "democratic", "political", "campaign",
                      "legal research", "case law", "dispute resolution"],
        "articles": ["Art. 6"],
        "risk_indicators": ["judicial decisions", "election influence", "legal outcomes"]
    }
]

# Unacceptable Risk (Art. 5 Prohibited Practices)
PROHIBITED_PRACTICES = [
    {
        "id": "art5_a",
        "title": "Subliminal/manipulative techniques",
        "description": "AI that deploys subliminal, manipulative, or deceptive techniques to distort behaviour causing significant harm",
        "keywords": ["subliminal", "manipulative", "deceptive", "dark pattern", "behaviour manipulation"]
    },
    {
        "id": "art5_b",
        "title": "Exploitation of vulnerabilities",
        "description": "AI exploiting vulnerabilities of persons due to age, disability, or social/economic situation",
        "keywords": ["exploit vulnerability", "elderly", "disabled", "children targeting", "vulnerable groups"]
    },
    {
        "id": "art5_c",
        "title": "Social scoring",
        "description": "AI for evaluation or classification of persons based on social behaviour leading to detrimental treatment",
        "keywords": ["social scoring", "social credit", "citizen score", "behaviour scoring", "social rating"]
    },
    {
        "id": "art5_d",
        "title": "Real-time remote biometric identification in public spaces",
        "description": "Real-time remote biometric identification in publicly accessible spaces for law enforcement (with exceptions)",
        "keywords": ["real-time biometric", "public space surveillance", "mass surveillance", "live facial recognition"]
    },
    {
        "id": "art5_e",
        "title": "Untargeted scraping of facial images",
        "description": "AI using untargeted scraping of facial images from internet/CCTV to build facial recognition databases",
        "keywords": ["facial scraping", "face database", "clearview", "untargeted scraping", "facial image collection"]
    },
    {
        "id": "art5_f",
        "title": "Emotion recognition in workplace/education",
        "description": "AI for inferring emotions in workplace and educational settings (except medical/safety)",
        "keywords": ["emotion workplace", "emotion school", "sentiment employee", "mood detection work"]
    },
    {
        "id": "art5_g",
        "title": "Biometric categorisation by sensitive attributes",
        "description": "AI categorising persons by race, political opinions, trade union, religion, sex life, sexual orientation",
        "keywords": ["race classification", "political categorisation", "religion detection", "sexual orientation detection"]
    },
    {
        "id": "art5_h",
        "title": "Predictive policing (individual)",
        "description": "AI making risk assessments of individuals for criminal offences based solely on profiling/personality traits",
        "keywords": ["predictive policing individual", "crime prediction person", "criminal risk profile"]
    }
]

# Limited Risk Transparency Requirements (Art. 50)
LIMITED_RISK_REQUIREMENTS = [
    {
        "id": "art50_1",
        "title": "AI-generated content disclosure",
        "description": "AI systems generating synthetic content (text, image, audio, video) must be marked as AI-generated",
        "keywords": ["chatbot", "text generation", "image generation", "deepfake", "synthetic content",
                      "ai generated", "content creation", "writing assistant", "copywriting"],
        "requirement": "Mark output as artificially generated or manipulated"
    },
    {
        "id": "art50_2",
        "title": "Chatbot disclosure",
        "description": "AI systems interacting with persons must disclose they are interacting with AI",
        "keywords": ["chatbot", "conversational ai", "virtual assistant", "customer service bot",
                      "dialog system", "chat agent"],
        "requirement": "Inform users they are interacting with an AI system"
    },
    {
        "id": "art50_3",
        "title": "Emotion recognition disclosure",
        "description": "AI systems performing emotion recognition must inform exposed persons",
        "keywords": ["emotion recognition", "sentiment analysis", "mood detection", "affective computing"],
        "requirement": "Inform persons that emotion recognition is being applied"
    }
]

# Key compliance requirements for high-risk systems
HIGH_RISK_REQUIREMENTS = [
    {"article": "Art. 9", "title": "Risk Management System", "type": "organizational",
     "summary": "Establish, implement, document and maintain a risk management system throughout the AI system's lifecycle.",
     "check": "Does the system have a documented risk management process?",
     "evidence": "Risk management plan, risk register, mitigation measures documentation"},
    
    {"article": "Art. 10", "title": "Data & Data Governance", "type": "technical",
     "summary": "Training, validation, and testing datasets must meet quality criteria. Data governance practices must be in place.",
     "check": "Are training datasets documented with quality criteria and governance?",
     "evidence": "Dataset documentation, data cards, bias assessments, data governance policy"},
    
    {"article": "Art. 11", "title": "Technical Documentation", "type": "documentation",
     "summary": "Technical documentation must be drawn up before the system is placed on the market.",
     "check": "Is comprehensive technical documentation available?",
     "evidence": "Technical documentation per Annex IV requirements"},
    
    {"article": "Art. 12", "title": "Record-Keeping", "type": "technical",
     "summary": "Systems must have automatic logging capabilities for traceability.",
     "check": "Does the system maintain automatic logs for traceability?",
     "evidence": "Logging architecture, log retention policy, audit trail"},
    
    {"article": "Art. 13", "title": "Transparency & Information", "type": "documentation",
     "summary": "Systems must be designed to be sufficiently transparent for deployers to interpret output.",
     "check": "Are users provided with sufficient information to understand the system?",
     "evidence": "User documentation, instructions for use, known limitations disclosure"},
    
    {"article": "Art. 14", "title": "Human Oversight", "type": "organizational",
     "summary": "Systems must be designed to allow effective human oversight during use.",
     "check": "Can humans effectively oversee and intervene in the system's operation?",
     "evidence": "Human oversight procedures, intervention mechanisms, override capabilities"},
    
    {"article": "Art. 15", "title": "Accuracy, Robustness & Cybersecurity", "type": "technical",
     "summary": "Systems must achieve appropriate levels of accuracy, robustness, and cybersecurity.",
     "check": "Has the system been tested for accuracy, robustness and cybersecurity?",
     "evidence": "Test reports, accuracy metrics, adversarial testing results, security audit"},
    
    {"article": "Art. 16", "title": "Provider Obligations", "type": "organizational",
     "summary": "Providers must ensure compliance, establish QMS, conduct conformity assessment.",
     "check": "Has the provider fulfilled all obligations under Art. 16?",
     "evidence": "Quality management system, CE marking, EU declaration of conformity"},
    
    {"article": "Art. 17", "title": "Quality Management System", "type": "organizational",
     "summary": "Providers must put a quality management system in place.",
     "check": "Is a quality management system documented and operational?",
     "evidence": "QMS documentation, internal audit records, corrective action procedures"},
]

# Key deadlines
DEADLINES = {
    "prohibited_practices": {"date": "2025-02-02", "description": "Prohibited AI practices ban effective"},
    "ai_literacy": {"date": "2025-02-02", "description": "AI literacy obligations effective"},
    "gpai_rules": {"date": "2025-08-02", "description": "GPAI model rules apply"},
    "high_risk_annex_iii": {"date": "2026-08-02", "description": "High-risk AI systems (Annex III) - full compliance required"},
    "high_risk_annex_ii": {"date": "2027-08-02", "description": "High-risk AI systems (Annex II) - full compliance required"},
}


def get_deadline_countdown():
    """Get days until each deadline."""
    from datetime import date
    today = date.today()
    result = {}
    for key, dl in DEADLINES.items():
        deadline = date.fromisoformat(dl["date"])
        days = (deadline - today).days
        result[key] = {
            "date": dl["date"],
            "description": dl["description"],
            "days_remaining": max(0, days),
            "status": "passed" if days < 0 else "imminent" if days < 90 else "upcoming"
        }
    return result
