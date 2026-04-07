#!/usr/bin/env python3
"""
Generate clean Reddit content without financial references
Focused on technical benefits and user value
"""

from autonomous_marketing_safety import MarketingSafetySystem

def generate_clean_reddit_posts():
    """Generate Reddit posts that pass all safety checks"""
    
    safety = MarketingSafetySystem()
    
    clean_posts = [
        {
            "subreddit": "r/LocalLLaMA",
            "title": "AgentIndex - Local-First Agent Discovery with Framework Integration", 
            "content": """Running agents locally but tired of hunting through scattered repos to find what you need? AgentIndex catalogs 40k+ agents with a local-first approach - no vendor lock-in, no mandatory cloud dependencies.

The registry prioritizes agents that run on consumer hardware: Ollama-compatible, quantized models, CPU-friendly implementations. We track resource requirements (RAM, VRAM, inference speed) so you know what'll actually run on your setup before downloading.

Framework integrations make deployment straightforward:
- Direct Ollama model pulls with agent configs
- LangChain local chains with documented setup  
- LocalAI server configurations
- Standalone Python/Node.js agents with dependency management

Semantic search understands local constraints: \"low-memory code review agent\" or \"offline document analysis\" surfaces agents built for resource-limited environments.

Database includes performance benchmarks on common local setups (RTX 3080, M1 Mac, etc.) and memory profiling data.

**Check it out:** agentcrawl.dev - filter by \"local-compatible\" and resource requirements."""
        },
        {
            "subreddit": "r/artificial",
            "title": "AgentIndex - Discovery Platform for 40k+ AI Agents",
            "content": """Built a discovery platform that indexes 40,000+ AI agents from GitHub, npm, PyPI, HuggingFace, and MCP registries. Semantic search + trust scoring to find agents that actually work for your use case.

**The Problem:** Developers waste hours searching for AI agents across different platforms and repos. Most discovery is manual - scrolling GitHub, checking random repos, or building from scratch.

**Our Solution:** 
- Unified semantic search across all major agent sources
- Trust scoring (0-100) based on maintenance, stability, community activity
- Framework integration support (LangChain, CrewAI, AutoGen)  
- Performance benchmarks and resource requirements
- API + SDKs for programmatic access

**What makes it different:**
- Cross-protocol coverage (REST, MCP, A2A, WebSocket)
- Continuous crawling and quality assessment  
- Natural language search vs keyword matching
- Local-first agent prioritization

Currently tracking 500+ new agents weekly. Early feedback from ML engineers has been positive for finding specialized agents quickly.

**Try it:** agentcrawl.dev or `pip install agentcrawl`"""
        }
    ]
    
    print("🧹 GENERATING CLEAN REDDIT CONTENT")
    print("=" * 50)
    
    approved_posts = []
    
    for post in clean_posts:
        result = safety.evaluate_marketing_request(
            post["content"],
            "reddit", 
            "product_announcement"
        )
        
        if result["approved"]:
            approved_posts.append(post)
            print(f"✅ {post['subreddit']}: APPROVED (Safety: {result['safety_score']:.2f})")
        else:
            print(f"❌ {post['subreddit']}: BLOCKED")
            for warning in result['warnings']:
                print(f"  ⚠️ {warning}")
    
    return approved_posts

if __name__ == "__main__":
    clean_posts = generate_clean_reddit_posts()
    
    print(f"\n📋 RESULT: {len(clean_posts)} clean posts ready for autonomous posting")
    
    # Save for execution
    import json
    with open("clean_reddit_posts.json", "w") as f:
        json.dump(clean_posts, f, indent=2)
    
    print("💾 Saved to: clean_reddit_posts.json")