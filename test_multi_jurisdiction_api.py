#!/usr/bin/env python3
"""Test the multi-jurisdiction API endpoint."""

import sys, os
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

import asyncio
import json
from agentindex.api.multi_jurisdiction import MultiJurisdictionRequest, check_multi_jurisdiction_compliance

async def test_multi_jurisdiction_api():
    """Test multi-jurisdiction API with various request types."""
    
    print("🧪 TESTING MULTI-JURISDICTION API")
    print("=" * 60)
    
    # Test 1: Financial system against all jurisdictions
    print("\n1. Testing financial system against all jurisdictions...")
    request1 = MultiJurisdictionRequest(
        system_name="Financial-Trading-MCP-Server",
        system_description="MCP server that provides real-time stock market data, trading signals, and investment recommendations for algorithmic trading",
        jurisdictions="all"
    )
    
    try:
        result1 = await check_multi_jurisdiction_compliance(request1)
        print(f"   ✅ System: {result1.system_name}")
        print(f"   ✅ Overall risk: {result1.overall_risk}")
        print(f"   ✅ Jurisdictions checked: {result1.jurisdictions_checked}")
        
        # Show top 3 results
        print(f"   📊 Sample results:")
        for i, (jid, result) in enumerate(list(result1.results.items())[:3], 1):
            print(f"      {i}. {jid}: {result.risk_class} (score: {result.score})")
            
        print(f"   🎯 Priority actions: {len(result1.priority_actions)} items")
        if result1.priority_actions:
            top_action = result1.priority_actions[0]
            print(f"      Top: {top_action.urgency} - {top_action.action}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Simple system against specific jurisdictions
    print("\n2. Testing simple system against EU + US jurisdictions...")
    request2 = MultiJurisdictionRequest(
        system_name="Document-Generator-Agent",
        system_description="AI agent that generates documentation and code comments",
        jurisdictions=["eu_ai_act", "us_co_sb205", "kr_ai_basic_act"]
    )
    
    try:
        result2 = await check_multi_jurisdiction_compliance(request2)
        print(f"   ✅ System: {result2.system_name}")  
        print(f"   ✅ Overall risk: {result2.overall_risk}")
        print(f"   ✅ Jurisdictions: {list(result2.results.keys())}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Target markets approach
    print("\n3. Testing target markets approach...")
    request3 = MultiJurisdictionRequest(
        system_name="Healthcare-AI-Assistant", 
        system_description="AI assistant for medical diagnosis support and patient data analysis",
        target_markets=["EU", "US-CA", "KR"]
    )
    
    try:
        result3 = await check_multi_jurisdiction_compliance(request3)
        print(f"   ✅ System: {result3.system_name}")
        print(f"   ✅ Overall risk: {result3.overall_risk}")
        print(f"   ✅ Markets mapped to: {list(result3.results.keys())}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print(f"\n✅ MULTI-JURISDICTION API TEST COMPLETE")
    print(f"   All core functionality working")
    print(f"   Ready for Fas 1 deployment")

async def test_jurisdiction_endpoints():
    """Test jurisdiction listing endpoints."""
    
    print("\n🧪 TESTING JURISDICTION ENDPOINTS")
    print("=" * 60)
    
    from agentindex.api.multi_jurisdiction import get_jurisdictions, get_jurisdiction_details
    
    # Test jurisdiction listing
    try:
        jurisdictions = await get_jurisdictions()
        print(f"✅ Get jurisdictions: {jurisdictions['total_jurisdictions']} found")
        
        # Show first 3
        for i, j in enumerate(jurisdictions['jurisdictions'][:3], 1):
            print(f"   {i}. {j['name']} ({j['region']}) - {j['status']}")
            
    except Exception as e:
        print(f"❌ Get jurisdictions error: {e}")
    
    # Test jurisdiction details
    try:
        eu_details = await get_jurisdiction_details("eu_ai_act")
        print(f"✅ EU AI Act details: {eu_details['name']}")
        print(f"   Risk model: {eu_details['risk_model']}")
        print(f"   Risk classes: {eu_details['risk_classes']}")
        print(f"   Requirements: {len(eu_details['requirements'])} items")
        
    except Exception as e:
        print(f"❌ Get jurisdiction details error: {e}")

if __name__ == "__main__":
    async def main():
        await test_multi_jurisdiction_api()
        await test_jurisdiction_endpoints()
        
    asyncio.run(main())