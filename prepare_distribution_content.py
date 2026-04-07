#!/usr/bin/env python3
"""
Prepare optimized distribution content using budget-conscious local LLM
Anders tempo: Generate all content locally at ZERO cost
"""

from smart_router import SmartRouter, TaskType, TaskComplexity
import json

router = SmartRouter()

# Define our distribution targets and required content
distribution_tasks = {
    "reddit_machinelearning": {
        "platform": "Reddit - r/MachineLearning",
        "task_type": TaskType.MARKETING,
        "complexity": TaskComplexity.MEDIUM,
        "prompt": """Create a compelling Reddit post for r/MachineLearning about AgentIndex.

Content should:
1. Lead with the unique value proposition: 40,000+ AI agents indexed and discoverable
2. Explain the problem: Developers waste time searching GitHub, npm, PyPI for agents
3. Show the solution: AgentIndex provides semantic search + trust scoring + framework integrations
4. Include statistics: 40k+ agents from 4 protocols (REST, MCP, A2A, Python)
5. Call-to-action: Visit agentcrawl.dev or try our Python SDK

Tone: Technical, conversational, no hype. Focus on developer benefits.
Length: 200-300 words
Include: 1-2 code snippet examples if relevant"""
    },
    
    "reddit_localllama": {
        "platform": "Reddit - r/LocalLLaMA",
        "task_type": TaskType.MARKETING,
        "complexity": TaskComplexity.MEDIUM,
        "prompt": """Create a Reddit post for r/LocalLLaMA about AgentIndex's local-first development approach.

Content should:
1. Explain: AgentIndex uses local LLMs extensively (Ollama with qwen, llama3, codellama)
2. Show the business case: 60-80% cost optimization with smart routing
3. Technical details: How we route code generation to local LLMs vs Claude API
4. Performance: Sub-100ms search responses with Redis caching
5. CTA: Developers can discover agents optimized for local deployment

Tone: Technical, encouraging. Appeal to local-first developer values.
Length: 200-300 words"""
    },
    
    "registry_glama": {
        "platform": "Glama Registry",
        "task_type": TaskType.MARKETING,
        "complexity": TaskComplexity.MEDIUM,
        "prompt": """Create product description for AgentIndex on Glama registry (glama.ai).

Format:
- Title: AgentIndex - AI Agent Discovery Platform
- Short description (50 words): One-liner about what we do
- Long description (300-400 words): 
  * Problem: Finding right AI agents is difficult
  * Solution: Semantic search across 40k+ agents
  * Key features: Trust scoring, framework integrations, cross-protocol
  * Developer benefits: Faster agent discovery, quality filtering
- Categories: Agent Discovery, AI Tools, Developer Tools
- Links: agentcrawl.dev, API docs, GitHub

Focus: Developer productivity and discovery efficiency"""
    },
    
    "registry_pulsemcp": {
        "platform": "PulseMCP Registry",
        "task_type": TaskType.MARKETING,
        "complexity": TaskComplexity.MEDIUM,
        "prompt": """Create registry listing for AgentIndex on PulseMCP (pulsemcp.com).

Include:
1. Agent name: AgentIndex MCP Server
2. Description: Semantic search across 40,000+ AI agents from GitHub, npm, PyPI, HuggingFace
3. Capabilities: 
   - Full-text semantic search with trust scoring
   - Agent metadata and quality indicators
   - Framework integration discovery
   - Cross-protocol agent aggregation
4. Use case: Find the right AI agent for your project in seconds
5. Status: Actively maintained, performance optimized

Format: JSON-compatible field descriptions"""
    }
}

print("🎯 GENERATING DISTRIBUTION CONTENT WITH BUDGET OPTIMIZATION")
print("=" * 60)

results = {}

for task_id, task_config in distribution_tasks.items():
    print(f"\n📝 {task_config['platform']}")
    print("-" * 40)
    
    # Generate content using local LLM (ZERO cost)
    use_local, reason = router.should_use_local(
        task_config["task_type"], 
        task_config["complexity"]
    )
    
    result = router.route_request(
        prompt=task_config["prompt"],
        task_type=task_config["task_type"],
        complexity=task_config["complexity"],
        system_prompt="You are an expert technical marketer and writer. Create content that is clear, compelling, and focused on developer benefits. Avoid hype and corporate speak.",
        max_tokens=800
    )
    
    if result and result.get("response"):
        results[task_id] = {
            "platform": task_config["platform"],
            "content": result["response"],
            "cost": "🆓 FREE (Local LLM)",
            "model": result.get("model"),
            "routing": result.get("routing_decision")
        }
        print(f"✅ Generated: {len(result['response'])} chars")
        print(f"💰 Cost: FREE (Local LLM)")
    else:
        print("❌ Generation failed")
        results[task_id] = {
            "platform": task_config["platform"],
            "error": "Generation failed"
        }

# Save results
with open("distribution_content.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n" + "=" * 60)
print("📊 SUMMARY")
print(f"✅ Generated {len([r for r in results.values() if 'content' in r])}/{len(results)} content pieces")
print("💾 Saved to: distribution_content.json")
print(f"💰 Total cost: 🆓 FREE (all local LLM)")

# Budget impact check
budget_status = router.cost_tracker.check_budget_status()
daily_stats = router.cost_tracker.get_daily_costs()
print(f"\n💳 Budget Status: {daily_stats['total_cost_usd']:.4f} used ({daily_stats['budget_used_percent']:.1f}%)")