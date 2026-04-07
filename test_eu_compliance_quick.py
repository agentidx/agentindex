#!/usr/bin/env python3
"""Quick test of EU compliance on 10 high-risk MCP candidates."""

import sys, os
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

from agentindex.db.models import Agent, get_session
from agentindex.compliance.risk_classifier import RiskClassifier
from sqlalchemy import select

def quick_test():
    session = get_session()
    classifier = RiskClassifier()
    
    # Test high-risk kandidater
    high_risk_names = [
        'Financial-Modeling-Prep-MCP-Server',
        'yfinance-mcp', 
        'stock-mcp',
        'dicom-mcp',
        'google-calendar-mcp',
        'supabase-mcp',
        'bank-api'
    ]
    
    results = []
    for name in high_risk_names:
        agent = session.execute(select(Agent).where(Agent.name == name).where(Agent.source == "mcp")).scalar_one_or_none()
        if agent:
            try:
                print(f"Testing: {name}")
                result = classifier.classify(
                    name=agent.name,
                    description=agent.description or "",
                    capabilities=agent.capabilities or [],
                    use_llm=True
                )
                results.append({
                    'name': name,
                    'risk_class': result['risk_class'],
                    'confidence': result['confidence'],
                    'reasoning': result.get('reasoning', '')
                })
                print(f"  → {result['risk_class']} ({result['confidence']:.2f})")
            except Exception as e:
                print(f"  → Error: {e}")
                
    return results

if __name__ == "__main__":
    results = quick_test()
    print(f"\n✅ Test complete. Found {len([r for r in results if r['risk_class'] in ['high', 'unacceptable']])} high-risk servers")