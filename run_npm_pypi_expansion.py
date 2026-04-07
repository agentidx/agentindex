#!/usr/bin/env python3
"""
Run npm + PyPI Expanded Crawlers - Live Execution

Executes expanded npm and PyPI crawling with broader AI/ML package discovery.
Target: 10K-20K npm + 5K-10K PyPI = 15K-30K new agents
"""

import os
import sys
import time
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Add project path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agentindex.db.models import Agent, get_session
from sqlalchemy import func, select

# Expanded search queries for maximum coverage
EXPANDED_NPM_QUERIES = [
    # Original core terms
    "ai-agent", "llm-agent", "mcp-server", "model-context-protocol",
    "autonomous-agent", "agent-framework", "langchain-agent", "openai-agent",
    
    # AI/ML tools and frameworks
    "ai", "llm", "gpt", "agent", "chatbot", "assistant", "anthropic", "claude",
    "openai", "langchain", "crewai", "autogen", "multi-agent", "ai-tool",
    
    # Vector and RAG
    "vector", "embedding", "rag", "retrieval", "semantic-search", "faiss",
    "pinecone", "weaviate", "chromadb", "vector-db",
    
    # Prompt engineering
    "prompt", "prompt-engineering", "prompt-template", "few-shot",
    "chain-of-thought", "prompt-optimization",
    
    # AI frameworks and libraries  
    "transformers", "tensorflow", "pytorch", "huggingface", "ollama",
    "ml", "machine-learning", "deep-learning", "neural", "model",
    
    # Generation and fine-tuning
    "text-generation", "code-generation", "image-generation", "fine-tuning",
    "training", "inference", "model-serving", "deployment",
    
    # Domain-specific
    "legal-ai", "medical-ai", "finance-ai", "customer-service", "writing-ai",
    "coding-ai", "research-ai", "data-ai", "content-generation"
]

EXPANDED_PYPI_QUERIES = [
    # Core AI terms
    "ai", "llm", "gpt", "agent", "assistant", "chatbot", "anthropic", "openai",
    "langchain", "crewai", "autogen", "multi-agent", "autonomous",
    
    # ML frameworks
    "pytorch", "tensorflow", "transformers", "huggingface", "scikit-learn",
    "keras", "ml", "machine-learning", "deep-learning", "neural-network",
    
    # Vector and embeddings
    "vector", "embedding", "faiss", "pinecone", "weaviate", "chromadb",
    "rag", "retrieval", "semantic-search", "similarity",
    
    # NLP and generation
    "nlp", "text-generation", "code-generation", "summarization",
    "translation", "sentiment-analysis", "named-entity", "classification",
    
    # Prompt and fine-tuning
    "prompt", "prompt-engineering", "fine-tuning", "lora", "training",
    "inference", "model-serving", "deployment", "optimization",
    
    # Computer Vision
    "cv", "computer-vision", "image", "vision", "detection", "recognition",
    "segmentation", "opencv", "pillow", "matplotlib",
    
    # Domain applications
    "medical-ai", "finance-ai", "legal-ai", "research", "data-science",
    "automation", "workflow", "pipeline", "api", "web-scraping"
]

def run_npm_expansion():
    """Run expanded npm crawler."""
    print("📦 STARTING NPM EXPANSION")
    print(f"   Queries: {len(EXPANDED_NPM_QUERIES)} terms")
    
    try:
        from agentindex.spiders.npm_spider import NpmSpider
        
        # Patch the queries for expansion
        import agentindex.spiders.npm_spider as npm_module
        original_queries = npm_module.SEARCH_QUERIES
        npm_module.SEARCH_QUERIES = EXPANDED_NPM_QUERIES
        
        spider = NpmSpider()
        result = spider.crawl(max_results_per_query=100)
        
        # Restore original queries
        npm_module.SEARCH_QUERIES = original_queries
        
        print(f"📦 NPM Results: {result.get('found', 0)} packages")
        return result
        
    except Exception as e:
        print(f"📦 NPM Error: {e}")
        return {'source': 'npm', 'found': 0, 'error': str(e)}

def run_pypi_expansion():
    """Run expanded PyPI crawler.""" 
    print("🐍 STARTING PYPI EXPANSION")
    print(f"   Queries: {len(EXPANDED_PYPI_QUERIES)} terms")
    
    try:
        from agentindex.spiders.pypi_spider import PypiSpider
        
        # Patch the queries for expansion
        import agentindex.spiders.pypi_spider as pypi_module
        original_queries = getattr(pypi_module, 'SEARCH_QUERIES', [])
        pypi_module.SEARCH_QUERIES = EXPANDED_PYPI_QUERIES
        
        spider = PypiSpider()
        result = spider.crawl(max_results_per_query=100)
        
        # Restore original queries if they existed
        if original_queries:
            pypi_module.SEARCH_QUERIES = original_queries
            
        print(f"🐍 PyPI Results: {result.get('found', 0)} packages")
        return result
        
    except Exception as e:
        print(f"🐍 PyPI Error: {e}")
        return {'source': 'pypi', 'found': 0, 'error': str(e)}

def run_npm_pypi_expansion():
    """Run both npm and PyPI crawlers in parallel."""
    
    print("🚀 NPM + PYPI EXPANSION - LIVE EXECUTION")
    print("=" * 60)
    print(f"Start time: {datetime.now().isoformat()}")
    
    # Get baseline
    session = get_session()
    baseline_count = session.execute(select(func.count(Agent.id))).scalar()
    npm_baseline = session.execute(select(func.count(Agent.id)).where(Agent.source == 'npm')).scalar()
    pypi_baseline = session.execute(select(func.count(Agent.id)).where(Agent.source == 'pypi')).scalar()
    session.close()
    
    print(f"📊 BASELINE:")
    print(f"   Total agents: {baseline_count:,}")
    print(f"   npm packages: {npm_baseline:,}")
    print(f"   PyPI packages: {pypi_baseline:,}")
    print(f"   Target: +15K-30K packages total")
    
    start_time = time.time()
    
    # Run both crawlers in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        print(f"\n🔄 Starting parallel npm + PyPI crawlers...")
        
        # Submit both tasks
        npm_future = executor.submit(run_npm_expansion)
        pypi_future = executor.submit(run_pypi_expansion)
        
        # Wait for completion
        npm_result = npm_future.result()
        pypi_result = pypi_future.result()
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Get new counts
    session = get_session()
    new_total_count = session.execute(select(func.count(Agent.id))).scalar()
    new_npm_count = session.execute(select(func.count(Agent.id)).where(Agent.source == 'npm')).scalar()
    new_pypi_count = session.execute(select(func.count(Agent.id)).where(Agent.source == 'pypi')).scalar()
    session.close()
    
    # Calculate additions
    total_added = new_total_count - baseline_count
    npm_added = new_npm_count - npm_baseline
    pypi_added = new_pypi_count - pypi_baseline
    
    print(f"\n🎯 NPM + PYPI EXPANSION RESULTS:")
    print(f"=" * 60)
    print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    print(f"")
    print(f"📊 AGENT COUNTS:")
    print(f"   Before: {baseline_count:,} total ({npm_baseline:,} npm, {pypi_baseline:,} PyPI)")
    print(f"   After:  {new_total_count:,} total ({new_npm_count:,} npm, {new_pypi_count:,} PyPI)")
    print(f"   Added:  +{total_added:,} total (+{npm_added:,} npm, +{pypi_added:,} PyPI)")
    print(f"")
    print(f"📈 EXPANSION RESULTS:")
    print(f"   npm: {new_npm_count:,} (was {npm_baseline:,}) → {(new_npm_count/max(npm_baseline,1)):.2f}x")
    print(f"   PyPI: {new_pypi_count:,} (was {pypi_baseline:,}) → {(new_pypi_count/max(pypi_baseline,1)):.2f}x")
    print(f"   Combined: +{npm_added + pypi_added:,} packages")
    
    # Performance metrics
    packages_per_second = (npm_added + pypi_added) / duration if duration > 0 else 0
    print(f"")
    print(f"⚡ PERFORMANCE:")
    print(f"   Rate: {packages_per_second:.1f} packages/second")
    print(f"   npm queries: {len(EXPANDED_NPM_QUERIES)} terms")
    print(f"   PyPI queries: {len(EXPANDED_PYPI_QUERIES)} terms")
    
    # Errors
    npm_error = npm_result.get('error')
    pypi_error = pypi_result.get('error')
    
    if npm_error or pypi_error:
        print(f"")
        print(f"❌ ERRORS:")
        if npm_error:
            print(f"   npm: {npm_error}")
        if pypi_error:
            print(f"   PyPI: {pypi_error}")
    
    return {
        'success': True,
        'baseline': baseline_count,
        'new_total': new_total_count,
        'total_added': total_added,
        'npm_added': npm_added,
        'pypi_added': pypi_added,
        'duration': duration,
        'npm_result': npm_result,
        'pypi_result': pypi_result
    }

if __name__ == "__main__":
    result = run_npm_pypi_expansion()
    
    if result['success']:
        print(f"\n🏆 NPM + PYPI EXPANSION COMPLETED")
        print(f"Added {result['total_added']:,} new packages in {result['duration']:.1f}s")
        print(f"npm: +{result['npm_added']:,}, PyPI: +{result['pypi_added']:,}")
    else:
        print(f"\n💥 NPM + PYPI EXPANSION FAILED")