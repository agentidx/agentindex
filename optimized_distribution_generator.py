#!/usr/bin/env python3
"""
Optimized distribution content generation - minimal tokens, maximum quality
Uses prompt compression + batching for efficiency within budget constraint
"""

import anthropic
import json
from datetime import datetime

# Initialize cost tracking
from cost_tracker import CostTracker
cost_tracker = CostTracker()

def compress_prompt(text: str) -> str:
    """Compress prompt to minimum viable size"""
    # Remove unnecessary words while preserving meaning
    compressed = text.replace("Please create ", "Create ")
    compressed = compressed.replace("should include", "must have")
    compressed = compressed.replace("is essential", "required")
    compressed = compressed.replace("would be helpful", "helpful")
    return compressed

def generate_all_content():
    """Generate all distribution content with single optimized API call"""
    
    client = anthropic.Anthropic()
    
    # Batch all content generation in one call - maximum efficiency
    batch_prompt = """Gen AgentIndex marketing content:
1. Reddit r/MachineLearning post (200w): problem (agent discovery hard), solution (40k agents, semantic search), call-to-action
2. Reddit r/LocalLLaMA post (200w): local-first approach, cost optimization (60-80% savings), framework integrations
3. Glama registry description (300w): title, short desc (50w), long desc with problem/solution/benefits
4. PulseMCP description (200w): server name, capabilities, use case

Constraints: factual, no hype, focus on developer benefits, dev/friendly tone"""

    print("🚀 GENERATING OPTIMIZED DISTRIBUTION CONTENT")
    print("=" * 60)
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": batch_prompt
            }]
        )
        
        content = response.content[0].text
        
        # Log cost
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = (input_tokens * 0.003 + output_tokens * 0.006) / 1000  # Sonnet pricing
        
        cost_tracker.log_api_call(
            model="claude-sonnet-4-20250514",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            task_type="marketing_content",
            notes="Batched distribution content generation"
        )
        
        # Parse and save
        output = {
            "generated_at": datetime.now().isoformat(),
            "model": "claude-sonnet-4-20250514",
            "content": content,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens
            },
            "cost_usd": round(cost, 4)
        }
        
        with open("distribution_content_ready.json", "w") as f:
            json.dump(output, f, indent=2)
        
        print(f"✅ Content generated successfully")
        print(f"📊 Tokens: {input_tokens} input + {output_tokens} output = {input_tokens + output_tokens} total")
        print(f"💰 Cost: ${cost:.4f}")
        print(f"💾 Saved to: distribution_content_ready.json")
        
        # Check budget
        daily_stats = cost_tracker.get_daily_costs()
        print(f"\n💳 Daily budget: ${daily_stats['total_cost_usd']:.4f}/{cost_tracker.daily_budget} ({daily_stats['budget_used_percent']:.1f}%)")
        
        return output
        
    except Exception as e:
        print(f"❌ Error generating content: {e}")
        return None

if __name__ == "__main__":
    result = generate_all_content()
    
    if result:
        print("\n" + "=" * 60)
        print("📋 CONTENT PREVIEW:")
        print(result['content'][:500] + "..." if len(result['content']) > 500 else result['content'])