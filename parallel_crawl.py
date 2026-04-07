#!/usr/bin/env python3
"""
Parallel Crawler for AgentIndex Scale-Up

Runs all crawlers in parallel to accelerate indexing from 43K to 500K agents.
Includes new high-volume sources: Docker Hub, Replicate, MCP Registries.

Usage:
    python parallel_crawl.py --sources all
    python parallel_crawl.py --sources dockerhub,replicate
    python parallel_crawl.py --quick-test
"""

import os
import sys
import asyncio
import logging
import time
import argparse
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
from datetime import datetime

# Add project path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("parallel_crawl.log")
    ]
)
logger = logging.getLogger("parallel_crawl")

class ParallelCrawler:
    """Parallel crawler coordinator for rapid scaling."""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        
        # Configure crawler settings for maximum throughput
        self.crawler_configs = {
            'github': {'max_results': 20000, 'priority': 1},
            'dockerhub': {'max_results': 10000, 'priority': 2},
            'replicate': {'max_results': 8000, 'priority': 3}, 
            'npm': {'max_results': 5000, 'priority': 4},
            'mcp': {'max_results': 3000, 'priority': 5},
            'mcp_registries': {'max_results': 1000, 'priority': 6},
            'huggingface': {'max_results': 2000, 'priority': 7},
            'pypi': {'max_results': 1000, 'priority': 8}
        }
    
    async def run_dockerhub_crawler(self) -> Dict:
        """Run Docker Hub crawler."""
        logger.info("🐳 Starting Docker Hub crawler")
        try:
            from agentindex.spiders.dockerhub_spider import DockerHubSpider
            
            spider = DockerHubSpider()
            result = await spider.crawl(max_results_per_query=200)
            
            logger.info(f"🐳 Docker Hub: {result['total_found']} containers in {result['duration_seconds']}s")
            return result
            
        except Exception as e:
            logger.error(f"🐳 Docker Hub crawler failed: {e}")
            return {'source': 'dockerhub', 'total_found': 0, 'error': str(e), 'repositories': []}
    
    async def run_replicate_crawler(self) -> Dict:
        """Run Replicate models crawler."""
        logger.info("🤖 Starting Replicate crawler")
        try:
            from agentindex.spiders.replicate_spider import ReplicateSpider
            
            spider = ReplicateSpider()
            result = await spider.crawl(max_results_total=5000)
            
            logger.info(f"🤖 Replicate: {result['total_found']} models in {result['duration_seconds']}s")
            return result
            
        except Exception as e:
            logger.error(f"🤖 Replicate crawler failed: {e}")
            return {'source': 'replicate', 'total_found': 0, 'error': str(e), 'models': []}
    
    async def run_mcp_registries_crawler(self) -> Dict:
        """Run MCP registries crawler."""
        logger.info("📋 Starting MCP registries crawler")
        try:
            from agentindex.spiders.mcp_registries_spider import MCPRegistriesSpider
            
            spider = MCPRegistriesSpider()
            result = await spider.crawl()
            
            logger.info(f"📋 MCP Registries: {result['total_found']} servers in {result['duration_seconds']}s")
            return result
            
        except Exception as e:
            logger.error(f"📋 MCP registries crawler failed: {e}")
            return {'source': 'mcp_registries', 'total_found': 0, 'error': str(e), 'servers': []}
    
    def run_github_crawler(self) -> Dict:
        """Run GitHub crawler (synchronous)."""
        logger.info("🐙 Starting GitHub crawler")
        try:
            from agentindex.spiders.github_spider import GitHubSpider
            
            spider = GitHubSpider()
            result = spider.crawl(max_results_per_query=300)
            
            logger.info(f"🐙 GitHub: {result.get('total_found', 0)} agents")
            return result
            
        except Exception as e:
            logger.error(f"🐙 GitHub crawler failed: {e}")
            return {'source': 'github', 'total_found': 0, 'error': str(e)}
    
    def run_npm_crawler(self) -> Dict:
        """Run npm crawler (synchronous)."""
        logger.info("📦 Starting npm crawler")
        try:
            from agentindex.spiders.npm_spider import NpmSpider
            
            spider = NpmSpider()
            result = spider.crawl(max_results_per_query=200)
            
            logger.info(f"📦 npm: {result.get('total_found', 0)} packages")
            return result
            
        except Exception as e:
            logger.error(f"📦 npm crawler failed: {e}")
            return {'source': 'npm', 'total_found': 0, 'error': str(e)}
    
    def run_mcp_crawler(self) -> Dict:
        """Run MCP GitHub crawler (synchronous)."""
        logger.info("🔌 Starting MCP GitHub crawler")
        try:
            from agentindex.spiders.mcp_spider import McpSpider
            
            spider = McpSpider()
            result = spider.crawl()
            
            logger.info(f"🔌 MCP: {result.get('total_found', 0)} servers")
            return result
            
        except Exception as e:
            logger.error(f"🔌 MCP crawler failed: {e}")
            return {'source': 'mcp', 'total_found': 0, 'error': str(e)}
    
    def run_huggingface_crawler(self) -> Dict:
        """Run HuggingFace crawler (synchronous)."""
        logger.info("🤗 Starting HuggingFace crawler")
        try:
            from agentindex.spiders.huggingface_spider import HuggingFaceSpider
            
            spider = HuggingFaceSpider()
            result = spider.crawl(max_results_per_query=300)
            
            logger.info(f"🤗 HuggingFace: {result.get('total_found', 0)} models")
            return result
            
        except Exception as e:
            logger.error(f"🤗 HuggingFace crawler failed: {e}")
            return {'source': 'huggingface', 'total_found': 0, 'error': str(e)}
    
    def run_pypi_crawler(self) -> Dict:
        """Run PyPI crawler (synchronous).""" 
        logger.info("🐍 Starting PyPI crawler")
        try:
            from agentindex.spiders.pypi_spider import PypiSpider
            
            spider = PypiSpider()
            result = spider.crawl(max_results_per_query=100)
            
            logger.info(f"🐍 PyPI: {result.get('total_found', 0)} packages")
            return result
            
        except Exception as e:
            logger.error(f"🐍 PyPI crawler failed: {e}")
            return {'source': 'pypi', 'total_found': 0, 'error': str(e)}
    
    async def run_parallel_crawl(self, sources: List[str]) -> Dict:
        """Run multiple crawlers in parallel."""
        self.start_time = time.time()
        logger.info(f"🚀 Starting parallel crawl with sources: {sources}")
        
        # Separate async and sync crawlers
        async_crawlers = []
        sync_crawlers = []
        
        for source in sources:
            if source == 'dockerhub':
                async_crawlers.append(('dockerhub', self.run_dockerhub_crawler()))
            elif source == 'replicate':
                async_crawlers.append(('replicate', self.run_replicate_crawler()))
            elif source == 'mcp_registries':
                async_crawlers.append(('mcp_registries', self.run_mcp_registries_crawler()))
            elif source == 'github':
                sync_crawlers.append(('github', self.run_github_crawler))
            elif source == 'npm':
                sync_crawlers.append(('npm', self.run_npm_crawler))
            elif source == 'mcp':
                sync_crawlers.append(('mcp', self.run_mcp_crawler))
            elif source == 'huggingface':
                sync_crawlers.append(('huggingface', self.run_huggingface_crawler))
            elif source == 'pypi':
                sync_crawlers.append(('pypi', self.run_pypi_crawler))
            else:
                logger.warning(f"Unknown source: {source}")
        
        # Run async crawlers concurrently
        async_results = {}
        if async_crawlers:
            logger.info(f"Running {len(async_crawlers)} async crawlers...")
            tasks = [crawler_func for _, crawler_func in async_crawlers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, (source_name, _) in enumerate(async_crawlers):
                result = results[i]
                if isinstance(result, Exception):
                    logger.error(f"Async crawler {source_name} failed: {result}")
                    async_results[source_name] = {'source': source_name, 'total_found': 0, 'error': str(result)}
                else:
                    async_results[source_name] = result
        
        # Run sync crawlers in thread pool
        sync_results = {}
        if sync_crawlers:
            logger.info(f"Running {len(sync_crawlers)} sync crawlers in thread pool...")
            
            with ThreadPoolExecutor(max_workers=min(len(sync_crawlers), 4)) as executor:
                future_to_source = {
                    executor.submit(crawler_func): source_name 
                    for source_name, crawler_func in sync_crawlers
                }
                
                for future in future_to_source:
                    source_name = future_to_source[future]
                    try:
                        result = future.result(timeout=1800)  # 30 min timeout per crawler
                        sync_results[source_name] = result
                    except Exception as e:
                        logger.error(f"Sync crawler {source_name} failed: {e}")
                        sync_results[source_name] = {'source': source_name, 'total_found': 0, 'error': str(e)}
        
        # Combine results
        all_results = {**async_results, **sync_results}
        
        end_time = time.time()
        duration = end_time - self.start_time
        
        # Calculate totals
        total_found = sum(result.get('total_found', 0) for result in all_results.values())
        successful_sources = sum(1 for result in all_results.values() if not result.get('error'))
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'sources_requested': sources,
            'sources_completed': list(all_results.keys()),
            'sources_successful': successful_sources,
            'sources_failed': len(all_results) - successful_sources,
            'total_agents_found': total_found,
            'duration_seconds': round(duration, 2),
            'agents_per_second': round(total_found / duration, 2) if duration > 0 else 0,
            'results_by_source': all_results
        }
        
        logger.info(f"🎯 Parallel crawl completed!")
        logger.info(f"   Sources: {successful_sources}/{len(sources)} successful")
        logger.info(f"   Total agents: {total_found:,}")
        logger.info(f"   Duration: {duration:.1f}s")
        logger.info(f"   Rate: {summary['agents_per_second']:.1f} agents/sec")
        
        return summary
    
    async def quick_test(self) -> Dict:
        """Quick test of new crawlers with small samples."""
        logger.info("🧪 Running quick test of new crawlers")
        
        test_sources = ['dockerhub', 'mcp_registries']  # Skip replicate for now due to API issues
        return await self.run_parallel_crawl(test_sources)
    
    async def full_crawl(self) -> Dict:
        """Full crawl of all sources for maximum scale."""
        logger.info("🌟 Running full crawl - all sources")
        
        all_sources = ['github', 'dockerhub', 'npm', 'mcp', 'mcp_registries', 'huggingface', 'pypi']
        # Skip replicate for now until API endpoints are fixed
        
        return await self.run_parallel_crawl(all_sources)

async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Parallel AgentIndex Crawler")
    parser.add_argument('--sources', default='all', 
                       help='Comma-separated list of sources or "all"')
    parser.add_argument('--quick-test', action='store_true',
                       help='Run quick test with new crawlers only')
    
    args = parser.parse_args()
    
    crawler = ParallelCrawler()
    
    if args.quick_test:
        result = await crawler.quick_test()
    else:
        if args.sources == 'all':
            result = await crawler.full_crawl()
        else:
            sources = [s.strip() for s in args.sources.split(',')]
            result = await crawler.run_parallel_crawl(sources)
    
    # Print summary
    print("\\n" + "="*60)
    print("PARALLEL CRAWL SUMMARY")
    print("="*60)
    print(f"Total agents found: {result['total_agents_found']:,}")
    print(f"Duration: {result['duration_seconds']:.1f} seconds")
    print(f"Rate: {result['agents_per_second']:.1f} agents/second")
    print(f"Successful sources: {result['sources_successful']}/{len(result['sources_requested'])}")
    
    print("\\nBy source:")
    for source, data in result['results_by_source'].items():
        status = "✅" if not data.get('error') else "❌"
        count = data.get('total_found', 0)
        print(f"  {status} {source}: {count:,} agents")
        if data.get('error'):
            print(f"     Error: {data['error']}")
    
    print("\\n🎯 Scale progress toward 500K target:")
    # Assume current total is 43,865 + new findings
    current_estimate = 43865 + result['total_agents_found']
    target = 500000
    progress = (current_estimate / target) * 100
    print(f"   Estimated total: {current_estimate:,}/500,000 ({progress:.1f}%)")
    remaining = target - current_estimate
    print(f"   Remaining needed: {remaining:,} agents")

if __name__ == "__main__":
    asyncio.run(main())