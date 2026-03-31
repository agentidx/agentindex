"""
Enhanced Risk Classifier for MCP Servers
Combines rule-based detection for obvious cases + LLM for edge cases.
"""

import logging
import re
from typing import Dict, List, Optional
from .risk_classifier import RiskClassifier

logger = logging.getLogger("agentindex.enhanced_classifier")

class EnhancedRiskClassifier(RiskClassifier):
    """Enhanced classifier with rule-based pre-filtering for obvious MCP compliance risks."""
    
    # High-risk financial keywords
    FINANCIAL_HIGH_RISK = [
        'trading', 'stock', 'forex', 'financial-modeling', 'yfinance', 'market-data',
        'investment', 'portfolio', 'trading-signals', 'financial-analysis', 
        'algorithmic-trading', 'quantitative-finance', 'risk-assessment',
        'credit-scoring', 'loan-approval', 'insurance-pricing', 'banking',
        'payment-processing', 'fraud-detection', 'aml', 'kyc'
    ]
    
    # High-risk healthcare/medical keywords  
    HEALTHCARE_HIGH_RISK = [
        'medical', 'dicom', 'healthcare', 'patient', 'clinical', 'diagnosis',
        'radiology', 'medical-imaging', 'health-records', 'hipaa', 'phi',
        'medical-device', 'treatment', 'therapy', 'pharmaceutical', 'drug',
        'medical-research', 'clinical-trial', 'pathology', 'oncology'
    ]
    
    # High-risk personal data keywords
    PERSONAL_DATA_HIGH_RISK = [
        'calendar', 'email', 'contacts', 'personal-assistant', 'scheduler',
        'crm', 'customer-data', 'user-profile', 'personal-information',
        'social-media', 'messaging', 'chat-history', 'location-tracking',
        'biometric', 'facial-recognition', 'voice-recognition', 'identity'
    ]
    
    # High-risk AI/ML decision systems
    AI_DECISION_HIGH_RISK = [
        'recommendation-system', 'content-moderation', 'sentiment-analysis',
        'behavior-prediction', 'user-scoring', 'ranking-algorithm',
        'personalization', 'targeting', 'classification', 'decision-support',
        'automated-decision', 'risk-scoring', 'eligibility-assessment'
    ]
    
    # Limited risk (transparency required but not high-risk)
    LIMITED_RISK = [
        'chatbot', 'conversational-ai', 'text-generation', 'translation',
        'content-generation', 'code-generation', 'documentation',
        'search-enhancement', 'data-analysis', 'reporting', 'dashboard'
    ]

    def classify(self, name: str, description: str, 
                 capabilities: list = None, category: str = None,
                 source_url: str = None, use_llm: bool = True) -> Dict:
        """
        Enhanced classification with rule-based pre-filtering.
        """
        
        # Prepare text for analysis
        text_content = f"{name} {description or ''} {' '.join(capabilities or [])}".lower()
        text_content = re.sub(r'[^a-z0-9\s-]', ' ', text_content)  # Clean text
        
        # Rule-based detection for obvious cases
        rule_result = self._rule_based_classification(text_content, name, description)
        
        if rule_result['confidence'] >= 0.9:  # High confidence from rules
            logger.info(f"Rule-based classification: {name} → {rule_result['risk_class']} ({rule_result['confidence']:.2f})")
            return rule_result
            
        # Fall back to LLM for uncertain cases
        if use_llm:
            try:
                llm_result = super().classify(name, description, capabilities, category, source_url, use_llm)
                
                # Combine rule-based signals with LLM result
                if rule_result['confidence'] > 0.5 and rule_result['risk_class'] in ['high', 'limited']:
                    # Trust rule-based for high/limited over LLM minimal
                    if llm_result['risk_class'] == 'minimal' and rule_result['risk_class'] != 'minimal':
                        logger.info(f"Rule override: {name} → {rule_result['risk_class']} (LLM said {llm_result['risk_class']})")
                        return rule_result
                        
                return llm_result
                
            except Exception as e:
                logger.error(f"LLM classification failed for {name}: {e}")
                return rule_result  # Fall back to rule-based
                
        return rule_result

    def _rule_based_classification(self, text_content: str, name: str, description: str) -> Dict:
        """Rule-based classification for obvious high-risk cases."""
        
        reasoning = []
        risk_class = "minimal"
        confidence = 0.5
        compliance_score = 95.0
        
        # Check for high-risk financial systems
        financial_matches = [kw for kw in self.FINANCIAL_HIGH_RISK if kw in text_content]
        if financial_matches:
            risk_class = "high"
            confidence = 0.95
            compliance_score = 25.0
            reasoning.append(f"Financial system detected: {', '.join(financial_matches[:3])}")
            reasoning.append("EU AI Act Annex III.5a: AI systems for credit scoring, loan approvals")
            reasoning.append("Colorado AI Act: Consequential decisions in financial services")
            
        # Check for high-risk healthcare systems
        healthcare_matches = [kw for kw in self.HEALTHCARE_HIGH_RISK if kw in text_content]
        if healthcare_matches:
            risk_class = "high"  
            confidence = 0.95
            compliance_score = 20.0
            reasoning.append(f"Healthcare system detected: {', '.join(healthcare_matches[:3])}")
            reasoning.append("EU AI Act Annex III.5b: AI systems for medical device classification")
            reasoning.append("HIPAA compliance required for health data processing")
            
        # Check for personal data systems
        personal_matches = [kw for kw in self.PERSONAL_DATA_HIGH_RISK if kw in text_content]
        if personal_matches:
            if risk_class != "high":  # Don't downgrade from high
                risk_class = "limited"
                confidence = 0.85
                compliance_score = 60.0
            reasoning.append(f"Personal data processing: {', '.join(personal_matches[:3])}")
            reasoning.append("GDPR Article 22: Automated decision-making")
            reasoning.append("Transparency requirements for personal data processing")
            
        # Check for AI decision systems
        ai_decision_matches = [kw for kw in self.AI_DECISION_HIGH_RISK if kw in text_content]
        if ai_decision_matches:
            if risk_class == "minimal":  # Don't downgrade from high/limited
                risk_class = "limited"
                confidence = 0.8
                compliance_score = 65.0
            reasoning.append(f"AI decision system: {', '.join(ai_decision_matches[:3])}")
            reasoning.append("Automated decision-making requires transparency")
            
        # Check for limited risk systems
        limited_matches = [kw for kw in self.LIMITED_RISK if kw in text_content]
        if limited_matches and risk_class == "minimal":
            risk_class = "limited"
            confidence = 0.7
            compliance_score = 75.0
            reasoning.append(f"AI interaction system: {', '.join(limited_matches[:3])}")
            reasoning.append("User disclosure requirements for AI interaction")
            
        # Special name-based patterns
        if any(pattern in name.lower() for pattern in ['financial', 'stock', 'trading', 'market']):
            risk_class = "high"
            confidence = 0.9
            compliance_score = 30.0
            reasoning.append("Financial system indicated by name")
            
        if any(pattern in name.lower() for pattern in ['medical', 'health', 'dicom', 'patient']):
            risk_class = "high"
            confidence = 0.9  
            compliance_score = 25.0
            reasoning.append("Healthcare system indicated by name")
            
        return {
            "risk_class": risk_class,
            "confidence": confidence,
            "compliance_score": compliance_score,
            "reasoning": ". ".join(reasoning) if reasoning else "No specific risk indicators detected",
            "annex_category": self._get_annex_category(risk_class, reasoning),
            "requirements": self._get_requirements(risk_class)
        }
        
    def _get_annex_category(self, risk_class: str, reasoning: List[str]) -> Optional[str]:
        """Map risk classification to EU AI Act Annex III categories."""
        if risk_class != "high":
            return None
            
        reasoning_text = " ".join(reasoning).lower()
        
        if any(term in reasoning_text for term in ['financial', 'credit', 'loan', 'banking']):
            return "5a_financial_services"
        elif any(term in reasoning_text for term in ['medical', 'healthcare', 'patient', 'clinical']):
            return "5b_medical_devices" 
        elif any(term in reasoning_text for term in ['employment', 'recruitment', 'hiring']):
            return "4a_employment"
        elif any(term in reasoning_text for term in ['education', 'assessment', 'evaluation']):
            return "3a_education_training"
        else:
            return "other_high_risk"
            
    def _get_requirements(self, risk_class: str) -> List[str]:
        """Get compliance requirements based on risk class."""
        if risk_class == "high":
            return [
                "Risk management system (Art. 9)",
                "Data governance measures (Art. 10)", 
                "Technical documentation (Art. 11)",
                "Record keeping (Art. 12)",
                "Transparency for users (Art. 13)",
                "Human oversight (Art. 14)",
                "Accuracy, robustness, cybersecurity (Art. 15)"
            ]
        elif risk_class == "limited":
            return [
                "User transparency disclosure (Art. 50)",
                "Clear information about AI system capabilities",
                "User notification of AI interaction"
            ]
        else:
            return ["No specific regulatory requirements"]