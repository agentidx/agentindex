#!/usr/bin/env python3
"""Test enhanced classifier on problematic MCP servers."""

import sys, os
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

from agentindex.db.models import Agent, get_session
from agentindex.compliance.enhanced_risk_classifier import EnhancedRiskClassifier
from sqlalchemy import select

def test_enhanced_classifier():
    session = get_session()
    classifier = EnhancedRiskClassifier()
    
    # Test cases that should be high-risk
    test_cases = [
        'Financial-Modeling-Prep-MCP-Server',
        'yfinance-mcp', 
        'stock-mcp',
        'dicom-mcp',
        'google-calendar-mcp',
        'bank-api',
        'supabase-mcp',  # Database - could be high depending on usage
        'teams-mcp',     # Corporate communication 
        'chrome-devtools-mcp',  # Development tool - should be minimal
        'mcp-server-calculator'  # Simple tool - should be minimal
    ]
    
    results = []
    print("=== ENHANCED CLASSIFIER TEST ===")
    
    for name in test_cases:
        agent = session.execute(
            select(Agent).where(Agent.name == name).where(Agent.source == "mcp").limit(1)
        ).scalar_one_or_none()
        
        if agent:
            try:
                result = classifier.classify(
                    name=agent.name,
                    description=agent.description or "",
                    capabilities=agent.capabilities or [],
                    use_llm=False  # Test rule-based only first
                )
                
                results.append({
                    'name': name,
                    'risk_class': result['risk_class'],
                    'confidence': result['confidence'],
                    'score': result['compliance_score'],
                    'reasoning': result['reasoning'][:150] + "..." if len(result['reasoning']) > 150 else result['reasoning']
                })
                
                # Color code results
                icon = "🚨" if result['risk_class'] == 'high' else "⚠️" if result['risk_class'] == 'limited' else "✅"
                print(f"{icon} {name}")
                print(f"   → {result['risk_class'].upper()} ({result['confidence']:.2f}) - Score: {result['compliance_score']}")
                print(f"   → {result['reasoning']}")
                print()
                
            except Exception as e:
                print(f"❌ {name}: Error - {e}")
        else:
            print(f"❓ {name}: Not found in database")
    
    # Summary
    high_risk = [r for r in results if r['risk_class'] == 'high']
    limited_risk = [r for r in results if r['risk_class'] == 'limited']
    minimal_risk = [r for r in results if r['risk_class'] == 'minimal']
    
    print("=== SUMMARY ===")
    print(f"🚨 HIGH risk: {len(high_risk)} servers")
    print(f"⚠️  LIMITED risk: {len(limited_risk)} servers") 
    print(f"✅ MINIMAL risk: {len(minimal_risk)} servers")
    
    return results

if __name__ == "__main__":
    results = test_enhanced_classifier()
    
    # Expected results check
    expected_high = ['Financial-Modeling-Prep-MCP-Server', 'yfinance-mcp', 'stock-mcp', 'dicom-mcp', 'bank-api']
    actual_high = [r['name'] for r in results if r['risk_class'] == 'high']
    
    print(f"\n✅ Enhanced classifier test:")
    print(f"   Expected high-risk: {len(expected_high)}")  
    print(f"   Actual high-risk: {len(actual_high)}")
    print(f"   Improvement: {len(actual_high)} vs 0 (old classifier)")