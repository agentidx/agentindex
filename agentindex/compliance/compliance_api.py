"""
OpenClaw Compliance API

Adds compliance endpoints to existing AgentIndex FastAPI app.
Mount this as a sub-application or include the router.

Endpoints:
  POST /compliance/check          - Free compliance check (anonymous)
  GET  /compliance/check/{id}     - Get assessment result
  GET  /compliance/agent/{id}     - Get compliance for indexed agent
  POST /compliance/assess         - Full assessment (future: paid)
  GET  /compliance/deadlines      - EU AI Act deadline countdown
  GET  /compliance/stats          - Aggregate compliance statistics
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
import json

from agentindex.compliance.risk_classifier import RiskClassifier
from agentindex.compliance.eu_ai_act_data import get_deadline_countdown

logger = logging.getLogger("openclaw.compliance.api")

router = APIRouter(prefix="/compliance", tags=["compliance"])

# Disclaimer shown on EVERY response
DISCLAIMER = (
    "INFORMATIONAL ONLY: This assessment is provided for informational purposes only. "
    "It does not constitute legal advice, regulatory guidance, or a guarantee of compliance "
    "with the EU AI Act or any other law. You are solely responsible for ensuring your AI systems "
    "comply with applicable regulations. We recommend consulting qualified legal counsel. "
    "This analysis was generated with AI. Review carefully."
)


# --- Request/Response Models ---

class ComplianceCheckRequest(BaseModel):
    """Free compliance check - just describe your AI system."""
    system_name: str = Field(..., max_length=500, description="Name of your AI system")
    system_description: str = Field(..., max_length=5000, description="Describe what your AI system does")
    system_category: Optional[str] = Field(None, description="Category (e.g., 'recruitment', 'content generation')")
    capabilities: Optional[list[str]] = Field(None, description="List of capabilities")
    jurisdictions: Optional[list[str]] = Field(default=["eu_ai_act"], description="Jurisdictions to check against")
    persona: Optional[str] = Field(None, description="User persona for frontend tracking")


class ComplianceCheckResponse(BaseModel):
    """Result of a compliance check."""
    assessment_id: str
    disclaimer: str
    
    # Classification
    risk_class: str
    risk_class_confidence: float
    annex_category: Optional[str]
    annex_subcategory: Optional[str]
    
    # Score and gaps
    compliance_score: int
    gaps: list[dict]
    gaps_count: int
    
    # Deadlines
    deadlines: dict
    
    # Explanation
    explanation: str
    model_used: str
    
    # Meta
    regulation_version: str = "EU_AI_ACT_2024"
    assessed_at: str


class DeadlineResponse(BaseModel):
    """EU AI Act deadlines."""
    deadlines: dict
    disclaimer: str


class ComplianceStatsResponse(BaseModel):
    """Aggregate compliance stats across indexed agents."""
    total_assessed: int
    by_risk_class: dict
    average_compliance_score: float
    most_common_gaps: list[dict]
    disclaimer: str


# --- Database helper ---

def get_db_session():
    """Get database session from existing AgentIndex models."""
    try:
        from agentindex.db.models import get_session
        return get_session()
    except ImportError:
        logger.warning("AgentIndex models not available, running standalone")
        return None


def save_assessment(session, request, result, assessment_id):
    """Save assessment to database."""
    if not session:
        return
    try:
        session.execute(text("""
            INSERT INTO compliance_assessments 
                (id, system_name, system_description, risk_class, risk_class_confidence,
                 annex_category, annex_subcategory, compliance_score, gaps, 
                 assessment_model, input_hash, status, created_at, updated_at,
                 expires_at, regulation_version)
            VALUES
                (:id, :name, :desc, :risk, :conf, :annex_cat, :annex_sub, :score,
                 CAST(:gaps AS jsonb), :model, :hash, 'completed', NOW(), NOW(),
                 NOW() + interval '90 days', 'EU_AI_ACT_2024')
        """), {
            "id": assessment_id,
            "name": request.system_name,
            "desc": request.system_description,
            "risk": result["risk_class"],
            "conf": result["confidence"],
            "annex_cat": result.get("annex_category"),
            "annex_sub": result.get("annex_subcategory"),
            "score": result["compliance_score"],
            "gaps": json.dumps(result["gaps"]),
            "model": result.get("model_used", "unknown"),
            "hash": result.get("input_hash", ""),
        })
        session.commit()
    except Exception as e:
        logger.error(f"Failed to save assessment: {e}")
        session.rollback()


def save_checker_usage(session, result, referrer=None):
    """Track anonymous usage for PMF metrics."""
    if not session:
        return
    try:
        session.execute(text("""
            INSERT INTO checker_usage 
                (id, input_type, risk_class_result, compliance_score_result, gaps_count, referrer, created_at)
            VALUES 
                (gen_random_uuid(), 'description', :risk, :score, :gaps, :ref, NOW())
        """), {
            "risk": result["risk_class"],
            "score": result["compliance_score"],
            "gaps": len(result.get("gaps", [])),
            "ref": referrer,
        })
        session.commit()
    except Exception as e:
        logger.error(f"Failed to save checker usage: {e}")
        session.rollback()


# --- Endpoints ---

@router.post("/check")
async def compliance_check(request: ComplianceCheckRequest, req: Request):
    """
    Free compliance check against multiple jurisdictions.
    
    Describe your AI system and get instant risk classifications,
    compliance scores, identified gaps, and deadline countdowns
    across all selected jurisdictions.
    
    **This is informational only and does not constitute legal advice.**
    """
    try:
        jurisdictions = request.jurisdictions or ["eu_ai_act"]
        
        # Single jurisdiction (legacy support) vs multi-jurisdiction
        if len(jurisdictions) == 1 and jurisdictions[0] == "eu_ai_act":
            # Legacy EU-only mode
            classifier = RiskClassifier()
            result = classifier.classify(
                name=request.system_name,
                description=request.system_description,
                capabilities=request.capabilities,
                category=request.system_category,
                use_llm=True
            )
            
            assessment_id = str(uuid.uuid4())
            
            # Save to DB
            session = get_db_session()
            if session:
                save_assessment(session, request, result, assessment_id)
                save_checker_usage(session, result, referrer=req.headers.get("referer"))
                session.close()
            
            return {
                "assessment_id": assessment_id,
                "disclaimer": DISCLAIMER,
                "risk_class": result["risk_class"],
                "risk_class_confidence": result["confidence"],
                "annex_category": result.get("annex_category"),
                "annex_subcategory": result.get("annex_subcategory"),
                "compliance_score": result["compliance_score"],
                "gaps": result["gaps"],
                "gaps_count": len(result["gaps"]),
                "deadlines": result.get("deadlines", {}),
                "explanation": result.get("explanation", ""),
                "model_used": result.get("model_used", "unknown"),
                "regulation_version": "EU_AI_ACT_2024",
                "assessed_at": datetime.utcnow().isoformat()
            }
        
        else:
            # Multi-jurisdiction mode
            from agentindex.api.multi_jurisdiction import MultiJurisdictionClassifier
            
            classifier = MultiJurisdictionClassifier()
            
            # Get jurisdiction details
            jurisdiction_details = classifier.get_jurisdictions(jurisdictions)
            
            if not jurisdiction_details:
                raise HTTPException(status_code=400, detail="No valid jurisdictions found")
            
            # Classify system against all jurisdictions
            classification_result = classifier.classify_system_multi_jurisdiction(
                request.system_name,
                request.system_description,
                jurisdiction_details
            )
            
            assessment_id = str(uuid.uuid4())
            
            # Convert results to frontend format
            results = {}
            for jur_id, result in classification_result["results"].items():
                # Find jurisdiction metadata
                jur_meta = next((j for j in jurisdiction_details if j["id"] == jur_id), {})
                
                results[jur_id] = {
                    "risk_class": result.risk_class,
                    "native_risk_class": getattr(result, 'native_risk_class', result.risk_class),
                    "classifier_confidence": getattr(result, 'classifier_confidence', 'native'),
                    "score": result.score,
                    "confidence": 0.8,  # Default confidence for multi-jur
                    "explanation": f"Classified as {result.risk_class} under {jur_meta.get('name', jur_id)}",
                    "gaps": [{"title": gap, "severity": "medium"} for gap in result.gaps],
                    "deadlines": {"main_deadline": {"date": result.deadline, "status": "upcoming"}} if result.deadline else {}
                }
            
            return {
                "assessment_id": assessment_id,
                "disclaimer": DISCLAIMER,
                "system_name": request.system_name,
                "overall_risk": classification_result["overall_risk"],
                "jurisdictions_checked": len(jurisdictions),
                "results": results,
                "priority_actions": [
                    {"urgency": action.urgency, "jurisdiction": action.jurisdiction, "action": action.action}
                    for action in classification_result["priority_actions"]
                ],
                "assessed_at": datetime.utcnow().isoformat(),
                "regulation_version": "MULTI_JURISDICTION_2026"
            }
            
    except Exception as e:
        logger.error(f"Compliance check error: {e}")
        raise HTTPException(status_code=500, detail=f"Classification error: {str(e)}")


@router.get("/check/{assessment_id}")
async def get_assessment(assessment_id: str):
    """Retrieve a previous compliance assessment by ID."""
    session = get_db_session()
    if not session:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        row = session.execute(text(
            "SELECT * FROM compliance_assessments WHERE id = :id"
        ), {"id": assessment_id}).mappings().first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Assessment not found")
        
        return {
            "assessment_id": str(row["id"]),
            "disclaimer": DISCLAIMER,
            "system_name": row["system_name"],
            "risk_class": row["risk_class"],
            "risk_class_confidence": row["risk_class_confidence"],
            "annex_category": row["annex_category"],
            "compliance_score": row["compliance_score"],
            "gaps": row["gaps"],
            "regulation_version": row["regulation_version"],
            "assessed_at": row["created_at"].isoformat() if row["created_at"] else None,
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        }
    finally:
        session.close()


@router.get("/agent/{agent_id}")
async def get_agent_compliance(agent_id: str):
    """Get compliance assessment for an indexed agent."""
    session = get_db_session()
    if not session:
        raise HTTPException(status_code=503, detail="Database unavailable")
    
    try:
        # Check if we have an existing assessment
        row = session.execute(text("""
            SELECT * FROM compliance_assessments 
            WHERE agent_id = :aid AND status = 'completed'
            ORDER BY created_at DESC LIMIT 1
        """), {"aid": agent_id}).mappings().first()
        
        if row:
            return {
                "assessment_id": str(row["id"]),
                "disclaimer": DISCLAIMER,
                "risk_class": row["risk_class"],
                "compliance_score": row["compliance_score"],
                "gaps": row["gaps"],
                "assessed_at": row["created_at"].isoformat(),
            }
        
        # No assessment yet - classify on the fly (capabilities not in entity_lookup)
        session.execute(text("SET LOCAL work_mem = '2MB'"))
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        agent = session.execute(text(
            "SELECT name, description, capabilities, category FROM agents WHERE id = :id"
        ), {"id": agent_id}).mappings().first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        classifier = RiskClassifier()
        result = classifier.classify(
            name=agent["name"],
            description=agent["description"] or "",
            capabilities=agent["capabilities"],
            category=agent["category"]
        )
        
        # Save assessment linked to agent
        aid = str(uuid.uuid4())
        session.execute(text("""
            INSERT INTO compliance_assessments 
                (id, agent_id, system_name, system_description, risk_class, risk_class_confidence,
                 annex_category, compliance_score, gaps, assessment_model, status)
            VALUES (:id, :agent_id, :name, :desc, :risk, :conf, :annex, :score, CAST(:gaps AS jsonb), :model, 'completed')
        """), {
            "id": aid, "agent_id": agent_id, "name": agent["name"],
            "desc": agent["description"], "risk": result["risk_class"],
            "conf": result["confidence"], "annex": result.get("annex_category"),
            "score": result["compliance_score"], "gaps": json.dumps(result["gaps"]),
            "model": result.get("model_used", "unknown")
        })
        
        # Update agent record
        session.execute(text("""
            UPDATE agents SET eu_risk_class = :risk, eu_risk_confidence = :conf,
                compliance_score = :score, last_compliance_check = NOW()
            WHERE id = :id
        """), {"risk": result["risk_class"], "conf": result["confidence"],
               "score": result["compliance_score"], "id": agent_id})
        
        session.commit()
        
        return {
            "assessment_id": aid,
            "disclaimer": DISCLAIMER,
            "risk_class": result["risk_class"],
            "risk_class_confidence": result["confidence"],
            "compliance_score": result["compliance_score"],
            "gaps": result["gaps"],
            "explanation": result.get("explanation", ""),
            "assessed_at": datetime.utcnow().isoformat()
        }
    finally:
        session.close()


@router.get("/deadlines", response_model=DeadlineResponse)
async def get_deadlines():
    """Get EU AI Act deadline countdown."""
    return DeadlineResponse(
        deadlines=get_deadline_countdown(),
        disclaimer=DISCLAIMER
    )


@router.get("/stats", response_model=ComplianceStatsResponse)
async def get_compliance_stats():
    """Aggregate compliance statistics across all assessments."""
    session = get_db_session()
    if not session:
        return ComplianceStatsResponse(
            total_assessed=0, by_risk_class={}, average_compliance_score=0,
            most_common_gaps=[], disclaimer=DISCLAIMER
        )
    
    try:
        total = session.execute(text(
            "SELECT COUNT(*) FROM entity_lookup WHERE eu_risk_class IS NOT NULL"
        )).scalar() or 0

        by_class = {}
        rows = session.execute(text(
            "SELECT eu_risk_class, COUNT(*) as cnt FROM entity_lookup "
            "WHERE eu_risk_class IS NOT NULL GROUP BY eu_risk_class"
        )).fetchall()
        for r in rows:
            by_class[r[0]] = r[1]

        avg_score = session.execute(text(
            "SELECT AVG(compliance_score) FROM entity_lookup WHERE eu_risk_class IS NOT NULL"
        )).scalar() or 0
        
        return ComplianceStatsResponse(
            total_assessed=total,
            by_risk_class=by_class,
            average_compliance_score=round(float(avg_score), 1),
            most_common_gaps=[],
            disclaimer=DISCLAIMER
        )
    finally:
        session.close()
