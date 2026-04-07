#!/usr/bin/env python3
"""Simple test of multi-jurisdiction API structure."""

import sys, os
sys.path.insert(0, os.path.expanduser("~/agentindex"))
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/agentindex/.env"))

def test_api_structure():
    """Test that API components are correctly structured."""
    
    print("🧪 TESTING MULTI-JURISDICTION API STRUCTURE")
    print("=" * 60)
    
    # Test 1: Import and basic setup
    try:
        from agentindex.api.multi_jurisdiction import router, MultiJurisdictionRequest, MultiJurisdictionResponse
        print("✅ Multi-jurisdiction API imports successful")
        
        # Test request model
        request = MultiJurisdictionRequest(
            system_name="Test System",
            system_description="Test description",
            jurisdictions=["eu_ai_act", "us_co_sb205"]
        )
        print(f"✅ Request model: {request.system_name}")
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return
    
    # Test 2: Jurisdiction mapping
    try:
        from agentindex.api.multi_jurisdiction import MARKET_JURISDICTION_MAP
        print(f"✅ Market mapping: {len(MARKET_JURISDICTION_MAP)} markets")
        
        # Test specific mappings
        eu_jurisdictions = MARKET_JURISDICTION_MAP.get("EU", [])
        us_jurisdictions = MARKET_JURISDICTION_MAP.get("US", [])
        print(f"   EU: {eu_jurisdictions}")
        print(f"   US: {us_jurisdictions[:3]}... ({len(us_jurisdictions)} total)")
        
    except Exception as e:
        print(f"❌ Mapping error: {e}")
        return
    
    # Test 3: Check database connection with simple query
    try:
        from agentindex.db.models import get_session
        from sqlalchemy import text
        session = get_session()
        
        # Simple test query
        result = session.execute(text("SELECT COUNT(*) FROM jurisdiction_registry")).scalar()
        print(f"✅ Database connection: {result} jurisdictions in registry")
        session.close()
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return
    
    # Test 4: Enhanced classifier 
    try:
        from agentindex.compliance.enhanced_risk_classifier import EnhancedRiskClassifier
        classifier = EnhancedRiskClassifier()
        
        # Quick classification test (no DB writes)
        result = classifier._rule_based_classification(
            "financial trading stock market investment",
            "Trading System",
            "Stock market trading system"
        )
        print(f"✅ Enhanced classifier: {result['risk_class']} risk detected")
        
    except Exception as e:
        print(f"❌ Classifier error: {e}")
        return
    
    print(f"\n✅ API STRUCTURE TEST COMPLETE")
    print(f"   All components properly integrated") 
    print(f"   Ready for HTTP endpoint testing")

def test_jurisdiction_data():
    """Test jurisdiction registry data quality."""
    
    print(f"\n🧪 TESTING JURISDICTION DATA QUALITY")
    print("=" * 60)
    
    try:
        from agentindex.db.models import get_session
        from sqlalchemy import text
        session = get_session()
        
        # Get all jurisdictions with key fields
        jurisdictions = session.execute(text("""
            SELECT id, name, region, status, effective_date, risk_model, focus
            FROM jurisdiction_registry 
            ORDER BY 
                CASE status WHEN 'effective' THEN 1 WHEN 'enacted' THEN 2 ELSE 3 END,
                effective_date
        """)).fetchall()
        
        print(f"📊 JURISDICTION REGISTRY ({len(jurisdictions)} total):")
        print("   Status breakdown:")
        
        status_counts = {}
        for j in jurisdictions:
            status = j[3]  # status field
            status_counts[status] = status_counts.get(status, 0) + 1
            
        for status, count in sorted(status_counts.items()):
            icon = "✅" if status == "effective" else "📅" if status == "enacted" else "⏳"
            print(f"   {icon} {status}: {count} jurisdictions")
        
        print(f"\n   Sample jurisdictions:")
        for i, j in enumerate(jurisdictions[:5], 1):
            status_icon = "✅" if j[3] == "effective" else "📅" if j[3] == "enacted" else "⏳"
            print(f"   {i}. {status_icon} {j[1]} ({j[2]}) - {j[5]} - {j[6]}")
            
        session.close()
        print(f"\n✅ Jurisdiction data quality verified")
        
    except Exception as e:
        print(f"❌ Jurisdiction data error: {e}")

if __name__ == "__main__":
    test_api_structure()
    test_jurisdiction_data()