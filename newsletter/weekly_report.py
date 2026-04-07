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
        
        # This would need a query_logs table tracking agent mentions
        results = await conn.fetch("""
            SELECT a.name, a.description, a.url, a.source,
                   COUNT(ql.query) as query_count,
                   a.trust_score->>'total_score' as trust_score
            FROM agents a
            LEFT JOIN query_logs ql ON a.name = ANY(string_to_array(ql.query, ' '))
            WHERE ql.timestamp > $1
            GROUP BY a.id, a.name, a.description, a.url, a.source, a.trust_score
            HAVING COUNT(ql.query) > 0
            ORDER BY query_count DESC
            LIMIT 10
        """, since)
        
        return [dict(row) for row in results]
    
    async def _get_hot_categories(self, conn: asyncpg.Connection, since: datetime) -> List[Dict[str, str]]:
        \"\"\"Get categories with most new agents\"\"\"\n        \n        results = await conn.fetch(\"\"\"\n            SELECT category, COUNT(*) as new_count\n            FROM agents \n            WHERE created_at > $1 AND category IS NOT NULL\n            GROUP BY category\n            ORDER BY new_count DESC\n            LIMIT 5\n        \"\"\", since)\n        \n        return [{\n            \"category\": row[\"category\"], \n            \"new_agents\": row[\"new_count\"]\n        } for row in results]\n    \n    async def _get_broken_links(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:\n        \"\"\"Get agents with low availability scores (broken links)\"\"\"\n        \n        results = await conn.fetch(\"\"\"\n            SELECT name, url, source,\n                   trust_score->'components'->>'availability' as availability_score\n            FROM agents \n            WHERE trust_score IS NOT NULL\n            AND (trust_score->'components'->>'availability')::float < 50.0\n            ORDER BY (trust_score->'components'->>'availability')::float ASC\n            LIMIT 10\n        \"\"\")\n        \n        return [dict(row) for row in results]\n    \n    async def _get_hidden_gems(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:\n        \"\"\"Get high-quality agents with low visibility\"\"\"\n        \n        results = await conn.fetch(\"\"\"\n            SELECT name, description, url, source,\n                   (trust_score->>'total_score')::float as trust_score,\n                   COALESCE((metadata->>'stars')::int, 0) as stars\n            FROM agents\n            WHERE trust_score IS NOT NULL\n            AND (trust_score->>'total_score')::float > 80.0\n            AND (\n                COALESCE((metadata->>'stars')::int, 0) < 100 \n                OR COALESCE((metadata->>'downloads')::int, 0) < 1000\n            )\n            ORDER BY (trust_score->>'total_score')::float DESC\n            LIMIT 5\n        \"\"\")\n        \n        return [dict(row) for row in results]\n    \n    async def _get_top_queries(self, conn: asyncpg.Connection, since: datetime) -> List[Dict[str, Any]]:\n        \"\"\"Get most popular search queries this week\"\"\"\n        \n        results = await conn.fetch(\"\"\"\n            SELECT query, COUNT(*) as query_count,\n                   AVG(result_count) as avg_results\n            FROM query_logs\n            WHERE timestamp > $1\n            GROUP BY query\n            ORDER BY query_count DESC\n            LIMIT 10\n        \"\"\", since)\n        \n        return [dict(row) for row in results]\n\n\nclass NewsletterFormatter:\n    \"\"\"Formats weekly stats into newsletter content\"\"\"\n    \n    def format_html_newsletter(self, stats: WeeklyStats) -> str:\n        \"\"\"Format stats as HTML newsletter\"\"\"\n        \n        html = f\"\"\"\n<!DOCTYPE html>\n<html>\n<head>\n    <title>AgentIndex Weekly Report</title>\n    <style>\n        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; }}\n        .header {{ background: #2563eb; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}\n        .section {{ margin-bottom: 30px; }}\n        .agent-list {{ list-style: none; padding: 0; }}\n        .agent-item {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 6px; border-left: 4px solid #2563eb; }}\n        .trust-score {{ background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; }}\n        .category-tag {{ background: #6b7280; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.7em; }}\n        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }}\n        .stat-card {{ background: #f1f5f9; padding: 20px; border-radius: 8px; text-align: center; }}\n        .stat-number {{ font-size: 2em; font-weight: bold; color: #2563eb; }}\n    </style>\n</head>\n<body>\n    <div class=\"header\">\n        <h1>🤖 AgentIndex Weekly Report</h1>\n        <p>Week of {datetime.now().strftime('%B %d, %Y')}</p>\n    </div>\n    \n    <div class=\"stats-grid\">\n        <div class=\"stat-card\">\n            <div class=\"stat-number\">{stats.total_agents:,}</div>\n            <div>Total Agents</div>\n        </div>\n        <div class=\"stat-card\">\n            <div class=\"stat-number\">+{stats.new_agents}</div>\n            <div>New This Week</div>\n        </div>\n        <div class=\"stat-card\">\n            <div class=\"stat-number\">{len(stats.trending_agents)}</div>\n            <div>Trending Agents</div>\n        </div>\n        <div class=\"stat-card\">\n            <div class=\"stat-number\">{len(stats.hidden_gems)}</div>\n            <div>Hidden Gems</div>\n        </div>\n    </div>\n\"\"\"\n        \n        # Trending Agents Section\n        if stats.trending_agents:\n            html += \"\"\"\n    <div class=\"section\">\n        <h2>📈 Trending This Week</h2>\n        <ul class=\"agent-list\">\n\"\"\"\n            for agent in stats.trending_agents[:5]:\n                trust_badge = f'<span class=\"trust-score\">{agent.get(\"trust_score\", \"N/A\")}/100</span>' if agent.get(\"trust_score\") else \"\"\n                html += f\"\"\"\n            <li class=\"agent-item\">\n                <strong>{agent['name']}</strong> {trust_badge}\n                <br><small>{agent['description'][:100]}...</small>\n                <br><a href=\"{agent['url']}\">{agent['source']}</a>\n            </li>\n\"\"\"\n            html += \"        </ul>\\n    </div>\\n\"\n        \n        # Hidden Gems Section\n        if stats.hidden_gems:\n            html += \"\"\"\n    <div class=\"section\">\n        <h2>💎 Hidden Gems</h2>\n        <p>High-quality agents that deserve more attention:</p>\n        <ul class=\"agent-list\">\n\"\"\"\n            for gem in stats.hidden_gems:\n                html += f\"\"\"\n            <li class=\"agent-item\">\n                <strong>{gem['name']}</strong> <span class=\"trust-score\">{gem['trust_score']:.1f}/100</span>\n                <br><small>{gem['description'][:100]}...</small>\n                <br><a href=\"{gem['url']}\">{gem['source']}</a> • {gem['stars']} stars\n            </li>\n\"\"\"\n            html += \"        </ul>\\n    </div>\\n\"\n        \n        # Hot Categories\n        if stats.hot_categories:\n            html += \"\"\"\n    <div class=\"section\">\n        <h2>🔥 Hot Categories</h2>\n        <p>Categories with most new agents this week:</p>\n        <ul>\n\"\"\"\n            for cat in stats.hot_categories:\n                html += f\"<li><span class=\\\"category-tag\\\">{cat['category']}</span> +{cat['new_agents']} new agents</li>\\n\"\n            html += \"        </ul>\\n    </div>\\n\"\n        \n        # Popular Queries\n        if stats.top_queries:\n            html += \"\"\"\n    <div class=\"section\">\n        <h2>🔍 What Developers Are Searching For</h2>\n        <ul>\n\"\"\"\n            for query in stats.top_queries[:5]:\n                html += f\"<li><strong>\\\"{query['query']}\\\"</strong> - {query['query_count']} searches</li>\\n\"\n            html += \"        </ul>\\n    </div>\\n\"\n        \n        html += \"\"\"\n    <div class=\"section\" style=\"background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;\">\n        <h3>Try AgentIndex</h3>\n        <p><strong>Demo:</strong> <a href=\"https://agentcrawl.dev\">agentcrawl.dev</a></p>\n        <p><strong>API:</strong> <a href=\"https://api.agentcrawl.dev/docs\">api.agentcrawl.dev/docs</a></p>\n        <p><strong>GitHub:</strong> <a href=\"https://github.com/agentidx/agentindex\">github.com/agentidx/agentindex</a></p>\n    </div>\n    \n    <div style=\"text-align: center; margin-top: 40px; color: #6b7280; font-size: 0.9em;\">\n        <p>AgentIndex Newsletter • <a href=\"#\">Unsubscribe</a></p>\n    </div>\n</body>\n</html>\n\"\"\"\n        \n        return html\n    \n    def format_markdown_newsletter(self, stats: WeeklyStats) -> str:\n        \"\"\"Format stats as Markdown for platforms like Reddit/Discord\"\"\"\n        \n        md = f\"\"\"# 🤖 AgentIndex Weekly Report\n\n**Week of {datetime.now().strftime('%B %d, %Y')}**\n\n## 📊 Quick Stats\n- **{stats.total_agents:,}** total agents indexed\n- **+{stats.new_agents}** new agents this week\n- **{len(stats.trending_agents)}** trending agents\n- **{len(stats.hidden_gems)}** hidden gems discovered\n\n\"\"\"\n        \n        if stats.trending_agents:\n            md += \"## 📈 Trending This Week\\n\\n\"\n            for i, agent in enumerate(stats.trending_agents[:3], 1):\n                trust = f\" (Trust: {agent.get('trust_score', 'N/A')}/100)\" if agent.get('trust_score') else \"\"\n                md += f\"{i}. **{agent['name']}**{trust}\\n   {agent['description'][:100]}...\\n   [{agent['source']}]({agent['url']})\\n\\n\"\n        \n        if stats.hidden_gems:\n            md += \"## 💎 Hidden Gems\\n\\n\"\n            for gem in stats.hidden_gems[:3]:\n                md += f\"- **{gem['name']}** (Trust: {gem['trust_score']:.1f}/100)\\n  {gem['description'][:80]}...\\n  [{gem['source']}]({gem['url']})\\n\\n\"\n        \n        if stats.top_queries:\n            md += \"## 🔍 Popular Searches\\n\\n\"\n            for query in stats.top_queries[:5]:\n                md += f\"- \\\"{query['query']}\\\" ({query['query_count']} searches)\\n\"\n        \n        md += \"\\n---\\n\\n**Try AgentIndex:**\\n- Demo: https://agentcrawl.dev\\n- API: https://api.agentcrawl.dev/docs\\n- GitHub: https://github.com/agentidx/agentindex\"\n        \n        return md\n\n\nif __name__ == \"__main__\":\n    async def generate_sample_report():\n        generator = WeeklyReportGenerator()\n        formatter = NewsletterFormatter()\n        \n        print(\"📊 Generating weekly report...\")\n        stats = await generator.generate_weekly_report()\n        \n        print(f\"✅ Report generated:\")\n        print(f\"   Total agents: {stats.total_agents:,}\")\n        print(f\"   New agents: {stats.new_agents}\")\n        print(f\"   Trending: {len(stats.trending_agents)}\")\n        print(f\"   Hidden gems: {len(stats.hidden_gems)}\")\n        \n        # Generate HTML newsletter\n        html_newsletter = formatter.format_html_newsletter(stats)\n        with open(\"weekly_report.html\", \"w\") as f:\n            f.write(html_newsletter)\n        print(\"📧 HTML newsletter saved to weekly_report.html\")\n        \n        # Generate Markdown version\n        md_newsletter = formatter.format_markdown_newsletter(stats)\n        with open(\"weekly_report.md\", \"w\") as f:\n            f.write(md_newsletter)\n        print(\"📝 Markdown newsletter saved to weekly_report.md\")\n    \n    asyncio.run(generate_sample_report())