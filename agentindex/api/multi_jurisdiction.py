"""
Multi-Jurisdiction Compliance API

Implements the multi-jurisdiction checker endpoint exactly per produktspec.
Checks AI systems against multiple jurisdictions and returns compliance matrix.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Union
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from agentindex.db.models import get_session
from agentindex.compliance.enhanced_risk_classifier import EnhancedRiskClassifier

logger = logging.getLogger("agentindex.api.multi_jurisdiction")

router = APIRouter(prefix="/compliance", tags=["Multi-Jurisdiction Compliance"])

class MultiJurisdictionRequest(BaseModel):
    """Request model for multi-jurisdiction compliance checking."""
    system_name: str = Field(..., description="Name of the AI system")
    system_description: str = Field(..., description="Description of the AI system's functionality")
    jurisdictions: Union[List[str], str] = Field(
        default="all",
        description="List of jurisdiction IDs to check against, or 'all' for all jurisdictions"
    )
    target_markets: Optional[List[str]] = Field(
        default=None,
        description="Alternative: specify target markets (e.g., ['EU', 'US', 'KR']) to map to relevant laws"
    )

class JurisdictionResult(BaseModel):
    """Result for a single jurisdiction."""
    risk_class: str
    score: int
    deadline: Optional[str]
    gaps: List[str]
    requirements: List[str]
    native_risk_class: Optional[str] = None
    classifier_confidence: str = "native"  # "native" or "approximate"

class PriorityAction(BaseModel):
    """Priority action item."""
    urgency: str  # "critical", "high", "medium", "low"
    jurisdiction: str
    action: str

class MultiJurisdictionResponse(BaseModel):
    """Response model for multi-jurisdiction compliance checking."""
    system_name: str
    overall_risk: str
    jurisdictions_checked: int
    results: Dict[str, JurisdictionResult]
    priority_actions: List[PriorityAction]
    badge_url: str

# Market to jurisdiction mapping
MARKET_JURISDICTION_MAP = {
    "EU": ["eu_ai_act"],
    "US": ["us_co_sb205", "us_ca_sb53", "us_ca_sb942", "us_tx_raiga", "us_il_aivi"],
    "US-CO": ["us_co_sb205"],
    "US-CA": ["us_ca_sb53", "us_ca_sb942"], 
    "US-TX": ["us_tx_raiga"],
    "US-IL": ["us_il_aivi"],
    "KR": ["kr_ai_basic_act"],
    "CN": ["cn_cybersecurity"],
    "VN": ["vn_ai_law"],
    "BR": ["br_ai_bill"],
    "CA": ["ca_aida"],
    "SG": ["sg_ai_governance"],
    "UK": ["uk_ai_regulation"], 
    "JP": ["jp_ai_bill"]
}

class MultiJurisdictionClassifier:
    """Multi-jurisdiction compliance classifier."""
    
    def __init__(self):
        self.base_classifier = EnhancedRiskClassifier()
        self.session = get_session()
        
    def get_jurisdictions(self, jurisdiction_request: Union[List[str], str], target_markets: Optional[List[str]] = None) -> List[Dict]:
        """Get jurisdictions to check based on request."""
        
        jurisdiction_ids = []
        
        if target_markets:
            # Map markets to jurisdictions
            for market in target_markets:
                if market in MARKET_JURISDICTION_MAP:
                    jurisdiction_ids.extend(MARKET_JURISDICTION_MAP[market])
                    
        elif isinstance(jurisdiction_request, str) and jurisdiction_request == "all":
            # Get all jurisdictions
            all_jurisdictions = self.session.execute(
                text("SELECT id FROM jurisdiction_registry WHERE status IN ('effective', 'enacted')")
            ).fetchall()
            jurisdiction_ids = [j[0] for j in all_jurisdictions]
            
        elif isinstance(jurisdiction_request, list):
            jurisdiction_ids = jurisdiction_request
            
        # Remove duplicates and get jurisdiction details
        jurisdiction_ids = list(set(jurisdiction_ids))
        
        jurisdictions = []
        for jid in jurisdiction_ids:
            jurisdiction_data = self.session.execute(
                text("SELECT * FROM jurisdiction_registry WHERE id = :id"),
                {"id": jid}
            ).fetchone()
            
            if jurisdiction_data:
                jurisdictions.append({
                    "id": jurisdiction_data[0],
                    "name": jurisdiction_data[1],
                    "region": jurisdiction_data[2],
                    "country": jurisdiction_data[3],
                    "status": jurisdiction_data[4],
                    "effective_date": jurisdiction_data[5],
                    "risk_model": jurisdiction_data[6],
                    "risk_classes": json.loads(jurisdiction_data[7]),
                    "high_risk_criteria": json.loads(jurisdiction_data[8] or "{}"),
                    "requirements": json.loads(jurisdiction_data[9] or "[]"),
                    "penalty_max": jurisdiction_data[10],
                    "focus": jurisdiction_data[12]
                })
                
        return jurisdictions
    
    def classify_system_multi_jurisdiction(self, system_name: str, system_description: str, jurisdictions: List[Dict]) -> Dict:
        """Classify AI system against multiple jurisdictions."""
        
        # Get base EU classification first
        base_result = self.base_classifier.classify(
            name=system_name,
            description=system_description,
            use_llm=True  # CRITICAL: Use LLM for accurate EU classification
        )
        
        results = {}
        overall_risk_levels = []
        
        for jurisdiction in jurisdictions:
            jid = jurisdiction["id"]
            
            # Apply jurisdiction-specific classification logic
            jurisdiction_result = self._classify_for_jurisdiction(
                base_result, jurisdiction, system_name, system_description
            )
            
            # Normalize risk class to standard three levels
            native_risk = jurisdiction_result["risk_class"]
            normalized_risk = self._normalize_risk_class(native_risk)
            
            results[jid] = JurisdictionResult(
                risk_class=normalized_risk,
                score=int(jurisdiction_result["compliance_score"]),
                deadline=jurisdiction.get("effective_date"),
                gaps=jurisdiction_result.get("gaps", []),
                requirements=jurisdiction_result.get("requirements", []),
                native_risk_class=native_risk,
                classifier_confidence=jurisdiction_result.get("classifier_confidence", "native")
            )
            
            # Track for overall risk calculation using normalized risk
            normalized_risk = self._normalize_risk_class(jurisdiction_result["risk_class"])
            overall_risk_levels.append(normalized_risk)
        
        # Determine overall risk (highest risk across all jurisdictions)
        if "high" in overall_risk_levels:
            overall_risk = "high"
        elif "limited" in overall_risk_levels:
            overall_risk = "limited" 
        else:
            overall_risk = "minimal"
            
        # Generate priority actions
        priority_actions = self._generate_priority_actions(results, jurisdictions)
        
        return {
            "results": results,
            "overall_risk": overall_risk,
            "priority_actions": priority_actions
        }
    
    def _classify_for_jurisdiction(self, base_result: Dict, jurisdiction: Dict, system_name: str, system_description: str) -> Dict:
        """Apply jurisdiction-specific classification logic."""
        
        jid = jurisdiction["id"]
        risk_model = jurisdiction["risk_model"]
        
        # Jurisdictions with explicit high-risk criteria (similar to EU Annex III)
        jurisdictions_with_specific_criteria = [
            "eu_ai_act",        # Has Annex III high-risk list
            "us_co_sb205",      # Algorithmic discrimination focus
            "us_il_aivi",       # Hiring AI specific
            "kr_ai_basic_act",  # High-impact categories
            "us_ca_sb53",       # Frontier models specific
            "cn_cybersecurity"  # Critical sector focus
        ]
        
        # Determine classifier confidence and base approach
        if jid in jurisdictions_with_specific_criteria:
            classifier_confidence = "native"
            
            # Sector-specific jurisdictions start from scratch
            if jid in ["us_ca_sb53", "cn_cybersecurity", "us_il_aivi"]:
                result = {
                    "risk_class": "minimal",  # Start conservative, override if criteria match
                    "compliance_score": 90, 
                    "explanation": f"Assessing under {jurisdiction.get('name', jid)} specific criteria",
                    "gaps": [],
                    "requirements": jurisdiction.get("requirements", []),
                    "classifier_confidence": classifier_confidence
                }
            else:
                # General AI frameworks (EU, Colorado, South Korea) use EU classification as base
                result = {
                    "risk_class": base_result["risk_class"],
                    "compliance_score": base_result["compliance_score"], 
                    "explanation": base_result.get("explanation", ""),
                    "gaps": [],
                    "requirements": jurisdiction.get("requirements", []),
                    "classifier_confidence": classifier_confidence
                }
        else:
            # Jurisdictions without specific high-risk criteria default to minimal
            classifier_confidence = "approximate"
            result = {
                "risk_class": "minimal",
                "compliance_score": 90,
                "explanation": f"No specific high-risk criteria defined under {jurisdiction.get('name', jid)}. Default assessment based on general principles.",
                "gaps": [],
                "requirements": jurisdiction.get("requirements", []),
                "classifier_confidence": classifier_confidence
            }
        
        # Apply jurisdiction-specific adaptations only for native confidence jurisdictions
        if classifier_confidence == "native":
            if jid == "us_co_sb205":  # Colorado AI Act
                # Binary risk model: high_risk or not_high_risk
                if base_result["risk_class"] in ["high", "limited"]:
                    result["risk_class"] = "high_risk"
                    result["compliance_score"] = 35
                    result["gaps"] = ["impact_assessment", "consumer_disclosure", "annual_review"]
                else:
                    result["risk_class"] = "not_high_risk" 
                    result["compliance_score"] = 85
                    
            elif jid == "us_il_aivi":  # Illinois AI Video Interview Act
                # Specific to hiring/recruitment AI
                text_content = f"{system_name} {system_description}".lower()
                if any(term in text_content for term in ["hiring", "recruitment", "interview", "cv", "resume", "applicant", "job"]):
                    result["risk_class"] = "covered_system"
                    result["compliance_score"] = 40
                    result["gaps"] = ["notification_requirements", "data_privacy", "bias_testing"]
                else:
                    result["risk_class"] = "not_covered"
                    result["compliance_score"] = 95
                    
            elif jid == "us_ca_sb53":  # California Frontier AI
                # Sector-specific for frontier models
                text_content = f"{system_name} {system_description}".lower()
                if any(term in text_content for term in ["llm", "large language", "frontier", "gpt", "claude"]):
                    result["risk_class"] = "covered_model"
                    result["compliance_score"] = 40
                    result["gaps"] = ["safety_protocols", "third_party_audit", "incident_reporting"]
                else:
                    result["risk_class"] = "not_covered"
                    result["compliance_score"] = 95
                    
            elif jid == "cn_cybersecurity":  # China
                # Focus on cybersecurity and critical infrastructure
                text_content = f"{system_name} {system_description}".lower()
                if any(term in text_content for term in ["financial", "banking", "infrastructure", "government", "military", "critical", "telecoms", "energy"]):
                    result["risk_class"] = "critical_sector"
                    result["compliance_score"] = 25
                    result["gaps"] = ["data_localization", "security_assessment", "government_approval"]
                else:
                    result["risk_class"] = "general"
                    result["compliance_score"] = 80
                
            elif jid == "kr_ai_basic_act":  # South Korea
                # Map to Korean risk classes
                if base_result["risk_class"] == "high":
                    result["risk_class"] = "high_impact"
                    result["compliance_score"] = 30
                elif base_result["risk_class"] == "limited":
                    result["risk_class"] = "moderate_impact"
                    result["compliance_score"] = 60
                else:
                    result["risk_class"] = "low_impact"
                    result["compliance_score"] = 90
                
            # Add jurisdiction-specific gaps based on focus (only for native confidence)
            focus = jurisdiction.get("focus", "")
            if focus == "algorithmic_discrimination" and result["risk_class"] in ["high_risk", "high"]:
                result["gaps"].extend(["discrimination_testing", "bias_mitigation"])
            elif focus == "transparency" and result["risk_class"] != "minimal":
                result["gaps"].extend(["transparency_disclosure", "user_notification"])
            
        return result
    
    def _normalize_risk_class(self, native_risk: str) -> str:
        """Normalize jurisdiction-specific risk classes to standard three levels."""
        
        # High risk variations
        high_risk_classes = [
            "high", "unacceptable", "high_risk", "high_impact", 
            "critical_sector", "covered_model", "covered_system", "prohibited"
        ]
        
        # Limited/moderate risk variations  
        limited_risk_classes = [
            "limited", "moderate_risk", "moderate_impact", "restricted"
        ]
        
        # Minimal/low risk variations
        minimal_risk_classes = [
            "minimal", "low_risk", "low_impact", "general", 
            "not_high_risk", "not_covered", "acceptable"
        ]
        
        native_lower = native_risk.lower()
        
        if native_lower in high_risk_classes:
            return "high"
        elif native_lower in limited_risk_classes:
            return "limited" 
        elif native_lower in minimal_risk_classes:
            return "minimal"
        else:
            # Fallback - treat unknown as minimal but log for review
            logger.warning(f"Unknown risk class '{native_risk}' normalized to minimal")
            return "minimal"
    
    def _generate_priority_actions(self, results: Dict, jurisdictions: List[Dict]) -> List[PriorityAction]:
        """Generate prioritized action items based on deadlines and risk levels."""
        
        actions = []
        
        # Create jurisdiction lookup
        jurisdiction_map = {j["id"]: j for j in jurisdictions}
        
        for jid, result in results.items():
            jurisdiction = jurisdiction_map.get(jid)
            if not jurisdiction:
                continue
                
            # Determine urgency based on deadline and risk
            effective_date = jurisdiction.get("effective_date")
            status = jurisdiction.get("status", "")
            
            if status == "effective" and result.risk_class == "high":
                urgency = "critical" 
                action = f"Already effective — immediate compliance needed"
            elif effective_date and "2026" in effective_date:
                if result.risk_class == "high":
                    urgency = "high"
                    action = f"{effective_date} — begin compliance process now"
                else:
                    urgency = "medium"
                    action = f"{effective_date} — prepare for compliance"
            elif status == "proposed":
                urgency = "low"
                action = "Monitor proposed legislation"
            else:
                urgency = "medium"
                action = "Review requirements and prepare"
                
            actions.append(PriorityAction(
                urgency=urgency,
                jurisdiction=jid, 
                action=action
            ))
        
        # Sort by urgency priority
        urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        actions.sort(key=lambda x: urgency_order.get(x.urgency, 4))
        
        return actions

@router.post("/multi-check", response_model=MultiJurisdictionResponse)
async def check_multi_jurisdiction_compliance(request: MultiJurisdictionRequest):
    """
    Check AI system compliance against multiple jurisdictions.
    
    Exactly per produktspec API design.
    """
    try:
        classifier = MultiJurisdictionClassifier()
        
        # Get jurisdictions to check
        jurisdictions = classifier.get_jurisdictions(request.jurisdictions, request.target_markets)
        
        if not jurisdictions:
            raise HTTPException(status_code=400, detail="No valid jurisdictions found")
            
        # Perform multi-jurisdiction classification
        classification_result = classifier.classify_system_multi_jurisdiction(
            request.system_name,
            request.system_description, 
            jurisdictions
        )
        
        # Generate badge URL (placeholder for now)
        badge_url = f"https://nerq.ai/compliance/badge/multi/assessment_{hash(request.system_name + request.system_description) % 100000}"
        
        response = MultiJurisdictionResponse(
            system_name=request.system_name,
            overall_risk=classification_result["overall_risk"],
            jurisdictions_checked=len(jurisdictions),
            results=classification_result["results"],
            priority_actions=classification_result["priority_actions"],
            badge_url=badge_url
        )
        
        logger.info(f"Multi-jurisdiction check completed: {request.system_name} - {len(jurisdictions)} jurisdictions")
        
        return response
        
    except Exception as e:
        logger.error(f"Multi-jurisdiction check error: {e}")
        raise HTTPException(status_code=500, detail=f"Classification error: {str(e)}")

@router.get("/jurisdictions")
async def get_jurisdictions():
    """Get all available jurisdictions."""
    session = get_session()
    
    try:
        jurisdictions = session.execute(
            text("""
            SELECT id, name, region, country, status, effective_date, focus, penalty_max
            FROM jurisdiction_registry 
            ORDER BY 
                CASE status 
                    WHEN 'effective' THEN 1
                    WHEN 'enacted' THEN 2  
                    WHEN 'proposed' THEN 3
                    WHEN 'voluntary' THEN 4
                END,
                effective_date
            """)
        ).fetchall()
        
        result = []
        for j in jurisdictions:
            result.append({
                "id": j[0],
                "name": j[1], 
                "region": j[2],
                "country": j[3],
                "status": j[4],
                "effective_date": j[5],
                "focus": j[6],
                "penalty_max": j[7]
            })
            
        return {
            "total_jurisdictions": len(result),
            "jurisdictions": result
        }
        
    except Exception as e:
        logger.error(f"Get jurisdictions error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/jurisdictions/{jurisdiction_id}")
async def get_jurisdiction_details(jurisdiction_id: str):
    """Get detailed information about a specific jurisdiction."""
    session = get_session()
    
    try:
        jurisdiction = session.execute(
            text("SELECT * FROM jurisdiction_registry WHERE id = :id"),
            {"id": jurisdiction_id}
        ).fetchone()
        
        if not jurisdiction:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
            
        return {
            "id": jurisdiction[0],
            "name": jurisdiction[1],
            "region": jurisdiction[2], 
            "country": jurisdiction[3],
            "status": jurisdiction[4],
            "effective_date": jurisdiction[5],
            "risk_model": jurisdiction[6],
            "risk_classes": json.loads(jurisdiction[7]),
            "high_risk_criteria": json.loads(jurisdiction[8] or "{}"),
            "requirements": json.loads(jurisdiction[9] or "[]"),
            "penalty_max": jurisdiction[10],
            "penalty_per_violation": jurisdiction[11],
            "focus": jurisdiction[12],
            "source_url": jurisdiction[13],
            "last_updated": jurisdiction[15]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get jurisdiction details error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/changelog")
async def get_regulatory_changelog(since: Optional[str] = None):
    """Get regulatory changelog since specified date."""
    # Placeholder for regulatory changelog
    # Will be populated by Sentinel agent
    return {
        "changes": [],
        "message": "Regulatory changelog will be populated by Sentinel agent"
    }