"""
EU AI Act Risk Classification Engine

Classifies AI systems into risk categories:
- Unacceptable (Art. 5 prohibited)
- High-risk (Annex III)
- Limited risk (Art. 50 transparency)
- Minimal risk

Uses two-phase approach:
1. Keyword pre-filter (fast, zero-cost)
2. LLM refinement via Ollama (accurate, local)
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from ollama import Client
from .eu_ai_act_data import (
    ANNEX_III_CATEGORIES, PROHIBITED_PRACTICES, LIMITED_RISK_REQUIREMENTS,
    HIGH_RISK_REQUIREMENTS, get_deadline_countdown
)
import os

logger = logging.getLogger("openclaw.classifier")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("COMPLIANCE_MODEL", "qwen2.5:7b")


class RiskClassifier:
    """Classifies AI systems under the EU AI Act."""

    def __init__(self):
        self.ollama = Client(host=OLLAMA_BASE_URL)

    def classify(self, name: str, description: str, 
                 capabilities: list = None, category: str = None,
                 source_url: str = None, use_llm: bool = True) -> Dict:
        """
        Classify an AI system's risk level.
        
        Returns: {
            "risk_class": "unacceptable|high|limited|minimal",
            "confidence": 0.0-1.0,
            "annex_category": str or None,
            "annex_subcategory": str or None,
            "compliance_score": 0-100,
            "gaps": [...],
            "deadlines": {...},
            "explanation": str,
            "model_used": str,
            "input_hash": str
        }
        """
        # Build input text
        text = self._build_input_text(name, description, capabilities, category)
        input_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        # Phase 1: Keyword pre-filter
        keyword_result = self._keyword_classify(text)

        # Phase 2: LLM refinement (if available and useful)
        if use_llm and keyword_result["confidence"] < 0.9:
            try:
                llm_result = self._llm_classify(name, description, capabilities, category)
                result = self._merge_results(keyword_result, llm_result)
                result["model_used"] = OLLAMA_MODEL
            except Exception as e:
                logger.warning(f"LLM classification failed, using keyword only: {e}")
                result = keyword_result
                result["model_used"] = "keyword_only"
        else:
            result = keyword_result
            result["model_used"] = "keyword_only" if keyword_result["confidence"] >= 0.9 else "keyword_low_confidence"

        # Add gaps and compliance score
        result["gaps"] = self._identify_gaps(result["risk_class"])
        result["compliance_score"] = self._calculate_compliance_score(result)
        result["deadlines"] = get_deadline_countdown()
        result["input_hash"] = input_hash

        return result

    def _build_input_text(self, name, description, capabilities, category):
        parts = [name or ""]
        if description:
            parts.append(description)
        if capabilities:
            parts.append(" ".join(str(c) for c in capabilities))
        if category:
            parts.append(category)
        return " ".join(parts).lower()

    def _keyword_classify(self, text: str) -> Dict:
        """Fast keyword-based pre-classification."""
        
        # Check prohibited practices first (unacceptable risk)
        for practice in PROHIBITED_PRACTICES:
            matches = sum(1 for kw in practice["keywords"] if kw in text)
            if matches >= 2:
                return {
                    "risk_class": "unacceptable",
                    "confidence": min(0.7 + matches * 0.1, 0.95),
                    "annex_category": None,
                    "annex_subcategory": practice["title"],
                    "explanation": f"Potential prohibited practice: {practice['title']}. "
                                   f"Matched {matches} indicators. Requires careful review.",
                    "matched_practice": practice["id"]
                }

        # Check Annex III categories (high risk)
        best_match = None
        best_score = 0
        for cat in ANNEX_III_CATEGORIES:
            matches = sum(1 for kw in cat["keywords"] if kw in text)
            risk_matches = sum(1 for ri in cat.get("risk_indicators", []) if ri in text)
            score = matches + risk_matches * 2
            if score > best_score:
                best_score = score
                best_match = cat

        if best_match and best_score >= 3:
            confidence = min(0.5 + best_score * 0.08, 0.95)
            return {
                "risk_class": "high",
                "confidence": confidence,
                "annex_category": best_match["category"],
                "annex_subcategory": best_match["subcategories"][0] if best_match["subcategories"] else None,
                "explanation": f"Matches Annex III category '{best_match['category']}' with {best_score} indicators.",
            }

        # Check limited risk (transparency obligations)
        for req in LIMITED_RISK_REQUIREMENTS:
            matches = sum(1 for kw in req["keywords"] if kw in text)
            if matches >= 2:
                return {
                    "risk_class": "limited",
                    "confidence": min(0.6 + matches * 0.1, 0.9),
                    "annex_category": None,
                    "annex_subcategory": req["title"],
                    "explanation": f"Transparency obligation: {req['title']}. Requirement: {req['requirement']}",
                }

        # Default: minimal risk
        return {
            "risk_class": "minimal",
            "confidence": 0.5,
            "annex_category": None,
            "annex_subcategory": None,
            "explanation": "No high-risk indicators detected. Classified as minimal risk. "
                           "Note: classification confidence is moderate - consider LLM review.",
        }

    def _llm_classify(self, name, description, capabilities, category) -> Dict:
        """LLM-based classification using local Ollama model."""

        prompt = f"""/no_think
You are an EU AI Act compliance expert. Classify this AI system.

System Name: {name}
Description: {description}
Capabilities: {json.dumps(capabilities or [])}
Category: {category or 'unknown'}

Classify into ONE of these risk levels:
1. UNACCEPTABLE - Matches Art. 5 prohibited practices (social scoring, subliminal manipulation, real-time biometric in public, etc.)
2. HIGH - Matches Annex III categories (biometrics, critical infrastructure, education, employment, essential services, law enforcement, migration, justice)
3. LIMITED - Has transparency obligations under Art. 50 (chatbots, content generation, emotion recognition)
4. MINIMAL - No specific regulatory requirements

Respond with ONLY valid JSON:
{{
    "risk_class": "unacceptable|high|limited|minimal",
    "confidence": 0.0-1.0,
    "annex_category": "category name or null",
    "annex_subcategory": "subcategory or null",
    "explanation": "brief explanation"
}}"""

        response = self.ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 500}
        )

        text = response["message"]["content"].strip()
        
        # Extract JSON from response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response: {text[:200]}")
            return {"risk_class": "minimal", "confidence": 0.3, "explanation": "LLM response unparseable"}

    def _merge_results(self, keyword: Dict, llm: Dict) -> Dict:
        """Merge keyword and LLM results, preferring higher-risk classification when confident."""
        
        risk_order = {"unacceptable": 4, "high": 3, "limited": 2, "minimal": 1}
        
        kw_level = risk_order.get(keyword.get("risk_class", "minimal"), 1)
        llm_level = risk_order.get(llm.get("risk_class", "minimal"), 1)
        kw_conf = keyword.get("confidence", 0.5)
        llm_conf = llm.get("confidence", 0.5)

        # If both agree, high confidence
        if keyword["risk_class"] == llm["risk_class"]:
            result = llm.copy()
            result["confidence"] = min((kw_conf + llm_conf) / 2 + 0.15, 0.99)
            return result

        # If they disagree, prefer the higher-risk classification if either is confident
        if kw_level > llm_level and kw_conf > 0.6:
            return keyword
        elif llm_level > kw_level and llm_conf > 0.6:
            return llm
        
        # Low confidence on both sides - use LLM but note disagreement
        result = llm.copy()
        result["confidence"] = min(kw_conf, llm_conf) * 0.8
        result["explanation"] = (result.get("explanation", "") + 
                                  f" Note: keyword analysis suggested '{keyword['risk_class']}' "
                                  f"while LLM suggested '{llm['risk_class']}'. Review recommended.")
        return result

    def _identify_gaps(self, risk_class: str) -> List[Dict]:
        """Identify compliance gaps based on risk classification."""
        
        if risk_class == "minimal":
            return []

        if risk_class == "unacceptable":
            return [{
                "id": "gap_prohibited",
                "title": "System may be prohibited under EU AI Act",
                "article": "Art. 5",
                "severity": "critical",
                "remediation": "This system potentially falls under prohibited AI practices. "
                               "Immediate legal review required. The system may need to be "
                               "discontinued or fundamentally redesigned. Consult qualified legal counsel."
            }]

        if risk_class == "limited":
            return [{
                "id": "gap_transparency",
                "title": "Transparency obligation",
                "article": "Art. 50",
                "severity": "medium",
                "remediation": "Ensure all AI-generated output is clearly marked as such. "
                               "Users must be informed they are interacting with an AI system."
            }]

        # High-risk: check all requirements
        gaps = []
        for i, req in enumerate(HIGH_RISK_REQUIREMENTS):
            gaps.append({
                "id": f"gap_{i+1}",
                "title": req["title"],
                "article": req["article"],
                "severity": "critical" if req["type"] == "organizational" else "high",
                "requirement_type": req["type"],
                "check": req["check"],
                "evidence_required": req["evidence"],
                "remediation": req["summary"]
            })
        return gaps

    def _calculate_compliance_score(self, result: Dict) -> int:
        """Calculate compliance score 0-100."""
        
        risk_class = result.get("risk_class", "minimal")
        
        if risk_class == "minimal":
            return 95  # Almost compliant by default
        
        if risk_class == "unacceptable":
            return 0  # Cannot be compliant
        
        if risk_class == "limited":
            return 60  # Needs transparency measures
        
        # High-risk: starts at 15 (many gaps to fill)
        return 15


def classify_agent(name: str, description: str, **kwargs) -> Dict:
    """Convenience function for single classification."""
    classifier = RiskClassifier()
    return classifier.classify(name, description, **kwargs)
