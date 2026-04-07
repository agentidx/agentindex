"""
Weekly Agent Report Generator - Updated for actual database schema
Automatically generates newsletter content from AgentIndex data
"""

import asyncio
import asyncpg
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class WeeklyStats:
    """Weekly statistics for newsletter"""
    total_agents: int
    new_agents: int
    top_rated_agents: List[Dict[str, Any]]
    hot_categories: List[Dict[str, Any]]
    trending_languages: List[Dict[str, Any]]
    top_protocols: List[Dict[str, Any]]


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
            
            # New agents this week (based on first_indexed)
            new_agents = await self._get_new_agents(conn, week_start)
            
            # Top rated agents (by quality_score)
            top_rated = await self._get_top_rated_agents(conn)
            
            # Hot categories
            hot_categories = await self._get_hot_categories(conn)
            
            # Trending languages
            trending_languages = await self._get_trending_languages(conn)
            
            # Top protocols
            top_protocols = await self._get_top_protocols(conn)
            
            return WeeklyStats(
                total_agents=total_agents,
                new_agents=len(new_agents),
                top_rated_agents=top_rated,
                hot_categories=hot_categories,
                trending_languages=trending_languages,
                top_protocols=top_protocols
            )
            
        finally:
            await conn.close()
    
    async def _get_total_agents(self, conn: asyncpg.Connection) -> int:
        """Get total number of indexed agents"""
        return await conn.fetchval("SELECT COUNT(*) FROM agents WHERE is_active = true")
    
    async def _get_new_agents(self, conn: asyncpg.Connection, since: datetime) -> List[Dict[str, Any]]:
        """Get agents added in the last week"""
        
        results = await conn.fetch("""
            SELECT name, description, source_url, source, quality_score, 
                   stars, downloads, first_indexed, category
            FROM agents 
            WHERE first_indexed > $1 AND is_active = true
            ORDER BY first_indexed DESC
            LIMIT 20
        """, since)
        
        return [dict(row) for row in results]
    
    async def _get_top_rated_agents(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get highest quality agents"""
        
        results = await conn.fetch("""
            SELECT name, description, source_url, source, quality_score,
                   stars, downloads, category, language
            FROM agents
            WHERE quality_score IS NOT NULL 
            AND is_active = true
            AND quality_score > 80.0
            ORDER BY quality_score DESC
            LIMIT 10
        """)
        
        return [dict(row) for row in results]
    
    async def _get_hot_categories(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get categories with most agents"""
        
        results = await conn.fetch("""
            SELECT category, COUNT(*) as agent_count,
                   AVG(quality_score) as avg_quality
            FROM agents 
            WHERE category IS NOT NULL 
            AND is_active = true
            AND quality_score IS NOT NULL
            GROUP BY category
            HAVING COUNT(*) > 5
            ORDER BY agent_count DESC, avg_quality DESC
            LIMIT 8
        """)
        
        return [dict(row) for row in results]
    
    async def _get_trending_languages(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get most popular programming languages"""
        
        results = await conn.fetch("""
            SELECT language, COUNT(*) as agent_count,
                   AVG(quality_score) as avg_quality,
                   SUM(COALESCE(stars, 0)) as total_stars
            FROM agents 
            WHERE language IS NOT NULL 
            AND is_active = true
            GROUP BY language
            HAVING COUNT(*) > 3
            ORDER BY agent_count DESC
            LIMIT 8
        """)
        
        return [dict(row) for row in results]
    
    async def _get_top_protocols(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get most common protocols"""
        
        results = await conn.fetch("""
            SELECT unnest(protocols) as protocol, COUNT(*) as usage_count
            FROM agents 
            WHERE protocols IS NOT NULL 
            AND array_length(protocols, 1) > 0
            AND is_active = true
            GROUP BY protocol
            ORDER BY usage_count DESC
            LIMIT 6
        """)
        
        return [dict(row) for row in results]


class NewsletterFormatter:
    """Formats weekly stats into newsletter content"""
    
    def format_markdown_newsletter(self, stats: WeeklyStats) -> str:
        """Format stats as Markdown for platforms"""
        
        md = f"""# 🤖 AgentIndex Weekly Report

**Week of {datetime.now().strftime('%B %d, %Y')}**

## 📊 Quick Stats
- **{stats.total_agents:,}** active agents indexed
- **+{stats.new_agents}** new agents this week
- **{len(stats.top_rated_agents)}** premium quality agents (80+ score)
- **{len(stats.hot_categories)}** active categories

"""
        
        if stats.top_rated_agents:
            md += "## ⭐ Top Quality Agents\n\n"
            for i, agent in enumerate(stats.top_rated_agents[:5], 1):
                stars_info = f" ⭐ {agent['stars']:,}" if agent.get('stars') and agent['stars'] > 0 else ""
                quality = f"{agent['quality_score']:.1f}/100" if agent.get('quality_score') else "N/A"
                md += f"{i}. **{agent['name']}** (Quality: {quality}){stars_info}\n"
                md += f"   {agent['description'][:100] if agent.get('description') else 'No description'}...\n"
                md += f"   [{agent['source']}]({agent['source_url']})\n\n"
        
        if stats.hot_categories:
            md += "## 🔥 Popular Categories\n\n"
            for cat in stats.hot_categories[:6]:
                avg_qual = f"{cat['avg_quality']:.1f}" if cat.get('avg_quality') else "N/A"
                md += f"- **{cat['category']}**: {cat['agent_count']} agents (avg quality: {avg_qual})\n"
        
        if stats.trending_languages:
            md += "\n## 💻 Programming Languages\n\n"
            for lang in stats.trending_languages[:6]:
                stars_info = f" ({lang['total_stars']:,} total ⭐)" if lang.get('total_stars') and lang['total_stars'] > 0 else ""
                md += f"- **{lang['language']}**: {lang['agent_count']} agents{stars_info}\n"
        
        if stats.top_protocols:
            md += "\n## 🔌 Popular Protocols\n\n"
            for proto in stats.top_protocols[:5]:
                md += f"- **{proto['protocol']}**: {proto['usage_count']} implementations\n"
        
        md += """

---

**Try AgentIndex:**
- Demo: https://agentcrawl.dev
- API: https://api.agentcrawl.dev/docs  
- GitHub: https://github.com/agentidx/agentindex

*Discover AI agents with semantic search across 40,000+ tools and integrations.*"""
        
        return md


if __name__ == "__main__":
    async def generate_sample_report():
        generator = WeeklyReportGenerator()
        formatter = NewsletterFormatter()
        
        print("📊 Generating weekly report...")
        try:
            stats = await generator.generate_weekly_report()
            
            print(f"✅ Report generated:")
            print(f"   Total agents: {stats.total_agents:,}")
            print(f"   New agents: {stats.new_agents}")
            print(f"   Top rated: {len(stats.top_rated_agents)}")
            print(f"   Hot categories: {len(stats.hot_categories)}")
            print(f"   Languages: {len(stats.trending_languages)}")
            print(f"   Protocols: {len(stats.top_protocols)}")
            
            # Generate newsletter
            md_newsletter = formatter.format_markdown_newsletter(stats)
            print("\n" + "="*60)
            print("SAMPLE NEWSLETTER:")
            print("="*60)
            print(md_newsletter[:1000] + "..." if len(md_newsletter) > 1000 else md_newsletter)
            
        except Exception as e:
            print(f"❌ Report generation failed: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(generate_sample_report())