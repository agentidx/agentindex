#!/usr/bin/env python3
"""Test local LLM generation for cost savings"""

from smart_router import SmartRouter, TaskType, TaskComplexity
import time

router = SmartRouter()

# Test a code generation task that would normally cost money with Claude
test_prompt = """
Create a Python function that validates email addresses using regex.
The function should:
1. Accept an email string as parameter  
2. Return True if valid, False if invalid
3. Include basic format checking (@ symbol, domain, etc.)
4. Handle common edge cases
"""

print("=== LOCAL LLM COST SAVINGS TEST ===")
print(f"Task: Email validation function generation")
print(f"Prompt length: {len(test_prompt)} characters")
print()

# Get routing decision
use_local, reason = router.should_use_local(
    TaskType.CODE_GENERATION, 
    TaskComplexity.SIMPLE
)

print(f"Routing decision: {'LOCAL LLM' if use_local else 'CLAUDE API'}")
print(f"Reason: {reason}")
print()

if use_local:
    print("🚀 Testing local generation...")
    start_time = time.time()
    
    # Route the actual request
    result = router.route_request(
        prompt=test_prompt,
        task_type=TaskType.CODE_GENERATION,
        complexity=TaskComplexity.SIMPLE,
        system_prompt="You are a helpful coding assistant. Provide clean, well-commented Python code.",
        max_tokens=500
    )
    
    end_time = time.time()
    
    if result and result.get("response"):
        print(f"✅ Generated successfully in {end_time - start_time:.2f}s")
        print(f"Model used: {result.get('model', 'unknown')}")
        print(f"Cost: $0.00 (vs ~$0.01-0.02 with Claude)")
        print(f"Response length: {len(result['response'])} characters")
        print()
        print("📝 Generated code:")
        print("=" * 50)
        print(result["response"])
        print("=" * 50)
    else:
        print("❌ Local generation failed")
        if result:
            print(f"Error: {result.get('error', 'Unknown error')}")
else:
    print("⚠️ Would use Claude API (cost: ~$0.01-0.02)")

# Show current budget status
print("\n💰 BUDGET STATUS AFTER TEST:")
daily_stats = router.cost_tracker.get_daily_costs()
print(f"Total costs today: ${daily_stats['total_cost_usd']:.4f}")
print(f"Budget usage: {daily_stats['budget_used_percent']:.1f}%")
print(f"Budget remaining: ${daily_stats['budget_remaining']:.2f}")