"""
Weekly Agent Report Generator
Automatically generates newsletter content from AgentIndex data
"""

import asyncio
import asyncpg
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json


@dataclass
class WeeklyStats:
    """Weekly statistics for newsletter"""
    total_agents: int
    new_agents: int
    trending_agents: List[Dict[str, Any]]
    hot_categories: List[Dict[str, str]]
    broken_links: List[Dict[str, Any]]
    hidden_gems: List[Dict[str, Any]]
    top_queries: List[Dict[str, Any]]


class WeeklyReportGenerator:
    """Generates weekly newsletter content from database analytics"""
    
    def __init__(self, db_url: str = "postgresql://anstudio@localhost/agentindex"):
        self.db_url = db_url
    
    async def generate_weekly_report(self, date: Optional[datetime] = None) -> WeeklyStats:
        """Generate complete weekly statistics report"""
        
        if not date:
            date = datetime.now()
        
        week_start = date - timedelta(days=7)
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # Total agents
            total_agents = await self._get_total_agents(conn)
            
            # New agents this week
            new_agents = await self._get_new_agents(conn, week_start)
            
            # Trending agents (high query volume)
            trending = await self._get_trending_agents(conn, week_start)
            
            # Hot categories (fastest growing)
            hot_categories = await self._get_hot_categories(conn, week_start)
            
            # Broken links check
            broken_links = await self._get_broken_links(conn)
            
            # Hidden gems (high trust, low visibility)
            hidden_gems = await self._get_hidden_gems(conn)
            
            # Top search queries
            top_queries = await self._get_top_queries(conn, week_start)
            
            return WeeklyStats(
                total_agents=total_agents,
                new_agents=len(new_agents),
                trending_agents=trending,
                hot_categories=hot_categories,
                broken_links=broken_links,
                hidden_gems=hidden_gems,
                top_queries=top_queries
            )
            
        finally:
            await conn.close()
    
    async def _get_total_agents(self, conn: asyncpg.Connection) -> int:
        """Get total number of indexed agents"""
        return await conn.fetchval("SELECT COUNT(*) FROM agents")
    
    async def _get_new_agents(self, conn: asyncpg.Connection, since: datetime) -> List[Dict[str, Any]]:
        """Get agents added in the last week"""
        
        results = await conn.fetch("""
            SELECT name, description, url, source, created_at,
                   trust_score->>'total_score' as trust_score
            FROM agents 
            WHERE created_at > $1 
            ORDER BY created_at DESC
            LIMIT 20
        """, since)
        
        return [dict(row) for row in results]
    
    async def _get_trending_agents(self, conn: asyncpg.Connection, since: datetime) -> List[Dict[str, Any]]:
        """Get agents with high query volume this week"""
        
        # Simplified version - just get recent high-trust agents
        results = await conn.fetch("""
            SELECT name, description, url, source,
                   trust_score->>'total_score' as trust_score,
                   trust_score->>'score_explanation' as trust_explanation
            FROM agents
            WHERE trust_score IS NOT NULL
            AND created_at > $1
            AND (trust_score->>'total_score')::float > 70.0
            ORDER BY (trust_score->>'total_score')::float DESC
            LIMIT 10
        """, since)
        
        return [dict(row) for row in results]
    
    async def _get_hot_categories(self, conn: asyncpg.Connection, since: datetime) -> List[Dict[str, str]]:
        """Get categories with most new agents"""
        
        results = await conn.fetch("""
            SELECT category, COUNT(*) as new_count
            FROM agents 
            WHERE created_at > $1 AND category IS NOT NULL
            GROUP BY category
            ORDER BY new_count DESC
            LIMIT 5
        """, since)
        
        return [{
            "category": row["category"], 
            "new_agents": row["new_count"]
        } for row in results]
    
    async def _get_broken_links(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get agents with low availability scores (broken links)"""
        
        results = await conn.fetch("""
            SELECT name, url, source,
                   trust_score->'components'->>'availability' as availability_score
            FROM agents 
            WHERE trust_score IS NOT NULL
            AND (trust_score->'components'->>'availability')::float < 50.0
            ORDER BY (trust_score->'components'->>'availability')::float ASC
            LIMIT 10
        """)
        
        return [dict(row) for row in results]
    
    async def _get_hidden_gems(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get high-quality agents with low visibility"""
        
        results = await conn.fetch("""
            SELECT name, description, url, source,
                   (trust_score->>'total_score')::float as trust_score,
                   COALESCE((metadata->>'stars')::int, 0) as stars
            FROM agents
            WHERE trust_score IS NOT NULL
            AND (trust_score->>'total_score')::float > 80.0
            AND (
                COALESCE((metadata->>'stars')::int, 0) < 100 
                OR COALESCE((metadata->>'downloads')::int, 0) < 1000
            )
            ORDER BY (trust_score->>'total_score')::float DESC
            LIMIT 5
        """)
        
        return [dict(row) for row in results]
    
    async def _get_top_queries(self, conn: asyncpg.Connection, since: datetime) -> List[Dict[str, Any]]:
        """Get most popular search queries this week"""
        
        results = await conn.fetch("""
            SELECT query, COUNT(*) as query_count,
                   AVG(result_count) as avg_results
            FROM query_logs
            WHERE timestamp > $1
            GROUP BY query
            ORDER BY query_count DESC
            LIMIT 10
        """, since)
        
        return [dict(row) for row in results]


if __name__ == "__main__":
    async def generate_sample_report():
        generator = WeeklyReportGenerator()
        
        print("📊 Generating weekly report...")
        try:
            stats = await generator.generate_weekly_report()
            
            print(f"✅ Report generated:")
            print(f"   Total agents: {stats.total_agents:,}")
            print(f"   New agents: {stats.new_agents}")
            print(f"   Trending: {len(stats.trending_agents)}")
            print(f"   Hidden gems: {len(stats.hidden_gems)}")
            print(f"   Hot categories: {len(stats.hot_categories)}")
            print(f"   Top queries: {len(stats.top_queries)}")
            
        except Exception as e:
            print(f"❌ Report generation failed: {e}")
    
    asyncio.run(generate_sample_report())