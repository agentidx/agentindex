"""
Performance Optimization Suite - Target: Sub-100ms Response Times
Implements caching, query optimization, and response compression
"""

import asyncio
import asyncpg
import redis
import json
import gzip
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Response
from fastapi.middleware.base import BaseHTTPMiddleware
import time


class PerformanceOptimizer:
    """Comprehensive performance optimization system"""
    
    def __init__(self, 
                 db_url: str = "postgresql://anstudio@localhost/agentindex",
                 redis_url: str = "redis://localhost:6379"):
        self.db_url = db_url
        self.redis_client = redis.from_url(redis_url)
        self.cache_ttl = 300  # 5 minutes default TTL
        self.hot_cache_ttl = 60   # 1 minute for hot queries
    
    async def get_cached_search_results(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached search results"""
        
        try:
            cached = self.redis_client.get(f"search:{query_hash}")
            if cached:
                return json.loads(gzip.decompress(cached).decode())
        except Exception as e:
            print(f"Cache get error: {e}")
        
        return None
    
    async def cache_search_results(
        self, 
        query_hash: str, 
        results: Dict[str, Any],
        is_hot_query: bool = False
    ) -> None:
        """Cache search results with compression"""
        
        try:
            # Compress results
            compressed = gzip.compress(json.dumps(results).encode())
            
            # Use shorter TTL for frequently searched queries
            ttl = self.hot_cache_ttl if is_hot_query else self.cache_ttl
            
            self.redis_client.setex(
                f"search:{query_hash}", 
                ttl, 
                compressed
            )
        except Exception as e:
            print(f"Cache set error: {e}")
    
    def generate_query_hash(self, query: str, limit: int = 10, category: str = None) -> str:
        """Generate consistent hash for query caching"""
        
        cache_key = f"{query}:{limit}:{category or 'all'}"
        return hashlib.md5(cache_key.encode()).hexdigest()
    
    async def is_hot_query(self, query: str) -> bool:
        """Check if query is frequently searched (hot)"""
        
        try:
            key = f"query_count:{hashlib.md5(query.encode()).hexdigest()}"
            count = self.redis_client.get(key)
            
            if count and int(count) > 10:  # More than 10 searches in last hour
                return True
            
            # Increment counter
            pipe = self.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, 3600)  # Expire after 1 hour
            pipe.execute()
            
            return False
            
        except Exception:
            return False
    
    async def optimize_database_query(self, query_params: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize database query with indexes and query planning"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # Use prepared statements and optimized queries
            need = query_params.get("need", "")
            limit = query_params.get("limit", 10)
            category = query_params.get("category")
            
            # Build optimized query with proper indexes
            base_query = """
                SELECT id, name, description, source_url as url, source, 
                       category, quality_score, stars, downloads,
                       trust_score,
                       -- Optimized similarity calculation
                       1 - (embedding <=> $1) as similarity
                FROM agents 
                WHERE is_active = true
            """
            
            params = [need]  # Embedding will be calculated
            param_count = 1
            
            # Add category filter if specified (uses index)
            if category:
                param_count += 1
                base_query += f" AND category = ${param_count}"
                params.append(category)
            
            # Add quality filter for faster results (uses index)
            base_query += " AND quality_score > 30"
            
            # Optimized ordering and limit
            base_query += f"""
                ORDER BY similarity DESC, quality_score DESC
                LIMIT ${param_count + 1}
            """
            params.append(limit)
            
            # Execute optimized query
            start_time = time.time()
            results = await conn.fetch(base_query, *params)
            query_time = int((time.time() - start_time) * 1000)
            
            # Format results
            formatted_results = []
            for row in results:
                result = dict(row)
                
                # Add trust score data if available
                if result.get("trust_score"):
                    trust_data = result["trust_score"]
                    result["trust_score"] = trust_data.get("total_score", 50.0)
                    result["trust_explanation"] = trust_data.get("score_explanation", "")
                else:
                    result["trust_score"] = None
                    result["trust_explanation"] = ""
                
                formatted_results.append(result)
            
            return {
                "results": formatted_results,
                "total": len(formatted_results),
                "query_time_ms": query_time
            }
            
        finally:
            await conn.close()
    
    async def precompute_trending_cache(self) -> None:
        """Precompute frequently accessed data"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # Precompute trending agents
            trending = await conn.fetch("""
                SELECT id, name, description, source_url, source, quality_score, stars
                FROM agents
                WHERE is_active = true 
                AND quality_score > 70
                AND stars > 100
                ORDER BY quality_score DESC, stars DESC
                LIMIT 20
            """)
            
            trending_data = [dict(row) for row in trending]
            
            # Cache trending data
            compressed = gzip.compress(json.dumps(trending_data).encode())
            self.redis_client.setex("trending_agents", 1800, compressed)  # 30 min TTL
            
            # Precompute popular categories
            categories = await conn.fetch("""
                SELECT category, COUNT(*) as agent_count,
                       AVG(quality_score) as avg_quality
                FROM agents
                WHERE is_active = true AND category IS NOT NULL
                GROUP BY category
                HAVING COUNT(*) > 10
                ORDER BY agent_count DESC
                LIMIT 15
            """)
            
            categories_data = [dict(row) for row in categories]
            compressed = gzip.compress(json.dumps(categories_data).encode())
            self.redis_client.setex("popular_categories", 1800, compressed)
            
            print(f"✅ Precomputed cache updated: {len(trending_data)} trending agents, {len(categories_data)} categories")
            
        finally:
            await conn.close()
    
    async def setup_database_indexes(self) -> None:
        """Setup database indexes for optimal performance"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            indexes = [
                # Core search indexes
                "CREATE INDEX IF NOT EXISTS idx_agents_active ON agents(is_active) WHERE is_active = true",
                "CREATE INDEX IF NOT EXISTS idx_agents_quality ON agents(quality_score DESC) WHERE is_active = true",
                "CREATE INDEX IF NOT EXISTS idx_agents_category ON agents(category) WHERE is_active = true",
                "CREATE INDEX IF NOT EXISTS idx_agents_source ON agents(source)",
                
                # Performance indexes
                "CREATE INDEX IF NOT EXISTS idx_agents_stars ON agents(stars DESC NULLS LAST) WHERE is_active = true",
                "CREATE INDEX IF NOT EXISTS idx_agents_composite ON agents(is_active, quality_score DESC, stars DESC)",
                
                # Trust score index (JSONB)
                "CREATE INDEX IF NOT EXISTS idx_agents_trust_score ON agents USING GIN(trust_score) WHERE trust_score IS NOT NULL",
                
                # Query logs for analytics
                "CREATE INDEX IF NOT EXISTS idx_query_logs_timestamp ON query_logs(timestamp DESC)",
                "CREATE INDEX IF NOT EXISTS idx_query_logs_query ON query_logs(query)",
                
                # Experiment tracking indexes
                "CREATE INDEX IF NOT EXISTS idx_experiment_events_compound ON experiment_events(experiment_id, timestamp DESC)"
            ]
            
            for index_sql in indexes:
                await conn.execute(index_sql)
            
            # Analyze tables for better query planning
            await conn.execute("ANALYZE agents")
            await conn.execute("ANALYZE query_logs")
            
            print("✅ Database indexes optimized")
            
        finally:
            await conn.close()


class CompressionMiddleware(BaseHTTPMiddleware):
    """Middleware for response compression"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Skip compression for small responses or specific content types
        if (hasattr(response, 'body') and 
            len(response.body) > 1000 and
            'application/json' in response.headers.get('content-type', '')):
            
            # Check if client accepts gzip
            accept_encoding = request.headers.get('accept-encoding', '')
            if 'gzip' in accept_encoding:
                compressed_body = gzip.compress(response.body)
                
                # Only compress if it saves space
                if len(compressed_body) < len(response.body):
                    response.body = compressed_body
                    response.headers['content-encoding'] = 'gzip'
                    response.headers['content-length'] = str(len(compressed_body))
        
        return response


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware for performance monitoring and caching"""
    
    def __init__(self, app, optimizer: PerformanceOptimizer):
        super().__init__(app)
        self.optimizer = optimizer
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Try cache for GET requests
        if request.method == "GET":
            cache_key = f"response:{request.url}"
            cached_response = await self._get_cached_response(cache_key)
            if cached_response:
                return cached_response
        
        # Process request
        response = await call_next(request)
        
        # Add performance headers
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))
        response.headers["X-Cache"] = "MISS"
        
        # Cache successful GET responses
        if (request.method == "GET" and 
            response.status_code == 200 and 
            process_time < 1.0):  # Only cache fast responses
            await self._cache_response(cache_key, response, ttl=60)
        
        return response
    
    async def _get_cached_response(self, cache_key: str):
        # Simplified cache check
        return None
    
    async def _cache_response(self, cache_key: str, response, ttl: int):
        # Simplified response caching
        pass


class PerformanceMonitor:
    """Monitor and alert on performance metrics"""
    
    def __init__(self, optimizer: PerformanceOptimizer):
        self.optimizer = optimizer
    
    async def collect_performance_metrics(self) -> Dict[str, Any]:
        """Collect current performance metrics"""
        
        try:
            # Redis connection test
            redis_start = time.time()
            self.optimizer.redis_client.ping()
            redis_latency = (time.time() - redis_start) * 1000
            
            # Database connection test  
            db_start = time.time()
            conn = await asyncpg.connect(self.optimizer.db_url)
            await conn.fetchval("SELECT 1")
            await conn.close()
            db_latency = (time.time() - db_start) * 1000
            
            # Cache hit rate
            cache_info = self.optimizer.redis_client.info("stats")
            cache_hits = cache_info.get("keyspace_hits", 0)
            cache_misses = cache_info.get("keyspace_misses", 0)
            total_cache_requests = cache_hits + cache_misses
            cache_hit_rate = (cache_hits / max(total_cache_requests, 1)) * 100
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "redis_latency_ms": round(redis_latency, 2),
                "database_latency_ms": round(db_latency, 2), 
                "cache_hit_rate": round(cache_hit_rate, 2),
                "cache_keys": self.optimizer.redis_client.dbsize(),
                "status": "healthy" if db_latency < 50 and redis_latency < 10 else "degraded"
            }
            
        except Exception as e:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
                "status": "error"
            }
    
    async def setup_performance_monitoring(self) -> None:
        """Setup continuous performance monitoring"""
        
        # This would typically integrate with monitoring services
        print("📊 Performance monitoring initialized")
        
        # Log initial metrics
        metrics = await self.collect_performance_metrics()
        print(f"   Database latency: {metrics.get('database_latency_ms', 'N/A')}ms")
        print(f"   Redis latency: {metrics.get('redis_latency_ms', 'N/A')}ms")
        print(f"   Cache hit rate: {metrics.get('cache_hit_rate', 'N/A')}%")


# Integration with main FastAPI app
def setup_performance_optimizations(app: FastAPI) -> PerformanceOptimizer:
    """Setup all performance optimizations for the FastAPI app"""
    
    optimizer = PerformanceOptimizer()
    
    # Add middleware
    app.add_middleware(CompressionMiddleware)
    app.add_middleware(PerformanceMiddleware, optimizer=optimizer)
    
    # Background tasks for cache warming
    @app.on_event("startup")
    async def startup_optimizations():
        await optimizer.setup_database_indexes()
        await optimizer.precompute_trending_cache()
        
        monitor = PerformanceMonitor(optimizer)
        await monitor.setup_performance_monitoring()
    
    # Periodic cache warming (would be handled by scheduler in production)
    @app.on_event("startup") 
    async def schedule_cache_warming():
        # This would integrate with a proper task scheduler
        print("⚡ Performance optimizations enabled")
    
    return optimizer


if __name__ == "__main__":
    async def test_performance_optimizations():
        optimizer = PerformanceOptimizer()
        monitor = PerformanceMonitor(optimizer)
        
        print("⚡ Testing performance optimizations...")
        
        try:
            # Setup indexes
            await optimizer.setup_database_indexes()
            
            # Test cache warming
            await optimizer.precompute_trending_cache()
            
            # Test performance monitoring
            metrics = await monitor.collect_performance_metrics()
            
            print("✅ Performance test completed!")
            print(f"   Database: {metrics.get('database_latency_ms', 'N/A')}ms")
            print(f"   Redis: {metrics.get('redis_latency_ms', 'N/A')}ms")
            print(f"   Status: {metrics.get('status', 'Unknown')}")
            
        except Exception as e:
            print(f"❌ Performance test failed: {e}")
            print("Note: Requires Redis server running")
    
    asyncio.run(test_performance_optimizations())