"""
Developer Discovery Dashboard - Experimental Feature
Real-time trending agents, query patterns, and discovery insights
"""

import asyncio
import asyncpg
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json


class DiscoveryAnalytics:
    """Analyzes real-time discovery patterns and trends"""
    
    def __init__(self, db_url: str = "postgresql://anstudio@localhost/agentindex"):
        self.db_url = db_url
    
    async def get_realtime_dashboard_data(self) -> Dict[str, Any]:
        """Get all data for real-time dashboard"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # Get various metrics in parallel
            tasks = [
                self._get_trending_now(conn),
                self._get_hot_queries(conn),
                self._get_discovery_velocity(conn),
                self._get_category_momentum(conn),
                self._get_language_trends(conn),
                self._get_quality_distribution(conn),
                self._get_geographic_patterns(conn),
                self._get_time_patterns(conn)
            ]
            
            results = await asyncio.gather(*tasks)
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "trending_agents": results[0],
                "hot_queries": results[1], 
                "discovery_velocity": results[2],
                "category_momentum": results[3],
                "language_trends": results[4],
                "quality_distribution": results[5],
                "geographic_patterns": results[6],
                "time_patterns": results[7],
                "summary": {
                    "total_active_agents": await conn.fetchval("SELECT COUNT(*) FROM agents WHERE is_active = true"),
                    "queries_last_hour": len(results[1]),
                    "trending_count": len(results[0]),
                    "top_category": results[3][0]["category"] if results[3] else "N/A"
                }
            }
            
        finally:
            await conn.close()
    
    async def _get_trending_now(self, conn: asyncpg.Connection, hours: int = 24) -> List[Dict[str, Any]]:
        """Get agents trending in the last 24 hours"""
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        # Simulate trending based on recent activity and quality
        results = await conn.fetch("""
            SELECT a.name, a.description, a.source, a.source_url,
                   a.quality_score, a.stars, a.category,
                   EXTRACT(epoch FROM (NOW() - a.first_indexed)) / 3600 as hours_old,
                   a.stars * 0.3 + a.quality_score * 0.7 as trend_score
            FROM agents a
            WHERE a.is_active = true
            AND a.first_indexed > $1
            AND a.quality_score > 40
            ORDER BY trend_score DESC
            LIMIT 10
        """, since)
        
        return [{
            **dict(row),
            "trend_reason": self._generate_trend_reason(dict(row))
        } for row in results]
    
    async def _get_hot_queries(self, conn: asyncpg.Connection, hours: int = 1) -> List[Dict[str, Any]]:
        """Get most popular search queries in last hour"""
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        results = await conn.fetch("""
            SELECT query, COUNT(*) as frequency,
                   AVG(result_count) as avg_results,
                   MAX(timestamp) as last_searched
            FROM query_logs
            WHERE timestamp > $1
            GROUP BY query
            ORDER BY frequency DESC
            LIMIT 20
        """, since)
        
        return [dict(row) for row in results]
    
    async def _get_discovery_velocity(self, conn: asyncpg.Connection) -> Dict[str, Any]:
        """Get rate of new agent discoveries"""
        
        # Last 24 hours broken down by hour
        results = await conn.fetch("""
            SELECT DATE_TRUNC('hour', first_indexed) as hour,
                   COUNT(*) as new_agents
            FROM agents
            WHERE first_indexed > NOW() - INTERVAL '24 hours'
            AND is_active = true
            GROUP BY hour
            ORDER BY hour DESC
        """)
        
        hourly_data = [{"hour": row["hour"].isoformat(), "count": row["new_agents"]} for row in results]
        
        total_24h = sum(row["count"] for row in hourly_data)
        avg_per_hour = total_24h / 24 if hourly_data else 0
        
        return {
            "hourly_breakdown": hourly_data,
            "total_24h": total_24h,
            "avg_per_hour": round(avg_per_hour, 1),
            "velocity_trend": "increasing" if len(hourly_data) > 12 else "stable"
        }
    
    async def _get_category_momentum(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get categories gaining/losing momentum"""
        
        # Compare last 24h vs previous 24h
        results = await conn.fetch("""
            WITH recent AS (
                SELECT category, COUNT(*) as recent_count
                FROM agents
                WHERE first_indexed > NOW() - INTERVAL '24 hours'
                AND category IS NOT NULL AND is_active = true
                GROUP BY category
            ),
            previous AS (
                SELECT category, COUNT(*) as previous_count
                FROM agents
                WHERE first_indexed BETWEEN NOW() - INTERVAL '48 hours' AND NOW() - INTERVAL '24 hours'
                AND category IS NOT NULL AND is_active = true
                GROUP BY category
            )
            SELECT r.category,
                   r.recent_count,
                   COALESCE(p.previous_count, 0) as previous_count,
                   r.recent_count - COALESCE(p.previous_count, 0) as momentum
            FROM recent r
            LEFT JOIN previous p ON r.category = p.category
            ORDER BY momentum DESC
            LIMIT 10
        """)
        
        return [dict(row) for row in results]
    
    async def _get_language_trends(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get programming language trends"""
        
        results = await conn.fetch("""
            SELECT language, COUNT(*) as agent_count,
                   AVG(quality_score) as avg_quality,
                   SUM(COALESCE(stars, 0)) as total_stars,
                   COUNT(*) FILTER (WHERE first_indexed > NOW() - INTERVAL '7 days') as new_this_week
            FROM agents
            WHERE language IS NOT NULL AND is_active = true
            GROUP BY language
            HAVING COUNT(*) > 10
            ORDER BY new_this_week DESC, agent_count DESC
            LIMIT 15
        """)
        
        return [dict(row) for row in results]
    
    async def _get_quality_distribution(self, conn: asyncpg.Connection) -> Dict[str, Any]:
        """Get distribution of quality scores"""
        
        results = await conn.fetch("""
            SELECT 
                COUNT(*) FILTER (WHERE quality_score >= 90) as excellent,
                COUNT(*) FILTER (WHERE quality_score >= 70 AND quality_score < 90) as good,
                COUNT(*) FILTER (WHERE quality_score >= 50 AND quality_score < 70) as fair,
                COUNT(*) FILTER (WHERE quality_score < 50) as poor,
                AVG(quality_score) as average_quality
            FROM agents
            WHERE quality_score IS NOT NULL AND is_active = true
        """)
        
        row = results[0]
        total = row['excellent'] + row['good'] + row['fair'] + row['poor']
        
        return {
            "distribution": dict(row),
            "percentages": {
                "excellent": round((row['excellent'] / total) * 100, 1) if total > 0 else 0,
                "good": round((row['good'] / total) * 100, 1) if total > 0 else 0,
                "fair": round((row['fair'] / total) * 100, 1) if total > 0 else 0,
                "poor": round((row['poor'] / total) * 100, 1) if total > 0 else 0
            }
        }
    
    async def _get_geographic_patterns(self, conn: asyncpg.Connection) -> List[Dict[str, Any]]:
        """Get geographic patterns (simulated based on source patterns)"""
        
        # This is a simplified version - in reality you'd track user locations
        results = await conn.fetch("""
            SELECT source, COUNT(*) as agent_count,
                   AVG(quality_score) as avg_quality
            FROM agents
            WHERE is_active = true
            GROUP BY source
            ORDER BY agent_count DESC
            LIMIT 10
        """)
        
        # Map sources to approximate regions
        region_mapping = {
            "github": "Global",
            "pypi": "Python Community",
            "npm": "Node.js Community", 
            "huggingface": "ML Community"
        }
        
        return [{
            "region": region_mapping.get(row["source"], row["source"]),
            "agent_count": row["agent_count"],
            "avg_quality": row["avg_quality"]
        } for row in results]
    
    async def _get_time_patterns(self, conn: asyncpg.Connection) -> Dict[str, Any]:
        """Get patterns of when agents are discovered/searched"""
        
        # Query patterns by hour of day
        results = await conn.fetch("""
            SELECT EXTRACT(hour FROM timestamp) as hour,
                   COUNT(*) as query_count
            FROM query_logs
            WHERE timestamp > NOW() - INTERVAL '7 days'
            GROUP BY hour
            ORDER BY hour
        """)
        
        hourly_patterns = [{"hour": int(row["hour"]), "queries": row["query_count"]} for row in results]
        
        # Find peak hour
        peak_hour = max(hourly_patterns, key=lambda x: x["queries"])["hour"] if hourly_patterns else 12
        
        return {
            "hourly_query_patterns": hourly_patterns,
            "peak_hour": peak_hour,
            "peak_hour_formatted": f"{peak_hour:02d}:00 UTC"
        }
    
    def _generate_trend_reason(self, agent: Dict[str, Any]) -> str:
        """Generate human-readable reason why agent is trending"""
        
        if agent["hours_old"] < 6:
            return "🆕 Just discovered"
        elif agent["stars"] > 1000:
            return f"⭐ Popular on GitHub ({agent['stars']:,} stars)"
        elif agent["quality_score"] > 85:
            return f"🏆 High quality score ({agent['quality_score']:.1f}/100)"
        else:
            return "📈 Growing interest"


class DashboardGenerator:
    """Generates HTML dashboard from analytics data"""
    
    def generate_dashboard_html(self, data: Dict[str, Any]) -> str:
        """Generate complete dashboard HTML"""
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>🔍 AgentIndex Discovery Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; overflow-x: hidden; }}
        .dashboard {{ padding: 20px; max-width: 1400px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .header h1 {{ font-size: 2.5em; background: linear-gradient(135deg, #3b82f6, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px; }}
        .timestamp {{ color: #64748b; font-size: 0.9em; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
        .card {{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%); border-radius: 16px; padding: 25px; border: 1px solid #334155; }}
        .card h3 {{ color: #3b82f6; margin-bottom: 15px; display: flex; align-items: center; gap: 10px; }}
        .metric {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #334155; }}
        .metric:last-child {{ border-bottom: none; }}
        .metric-value {{ font-weight: bold; color: #22d3ee; }}
        .trending-item {{ background: #1e293b; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #3b82f6; }}
        .trending-item h4 {{ color: #f8fafc; margin-bottom: 8px; }}
        .trending-item p {{ color: #94a3b8; font-size: 0.85em; margin-bottom: 8px; }}
        .trending-reason {{ color: #22d3ee; font-size: 0.8em; }}
        .quality-bar {{ width: 100%; height: 8px; background: #334155; border-radius: 4px; overflow: hidden; margin: 5px 0; }}
        .quality-fill {{ height: 100%; background: linear-gradient(90deg, #ef4444, #f59e0b, #10b981, #3b82f6); border-radius: 4px; }}
        .pulse {{ animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .live-indicator {{ color: #22c55e; animation: blink 1s infinite; }}
        @keyframes blink {{ 0%, 50% {{ opacity: 1; }} 51%, 100% {{ opacity: 0.3; }} }}
    </style>
    <script>
        // Auto-refresh every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>🔍 Discovery Dashboard</h1>
            <div class="timestamp">
                <span class="live-indicator">● LIVE</span> 
                Last updated: {data['timestamp'][:19]}
            </div>
        </div>
        
        <div class="grid">
            <!-- Summary Stats -->
            <div class="card">
                <h3>📊 Live Stats</h3>
                <div class="metric">
                    <span>Active Agents</span>
                    <span class="metric-value">{data['summary']['total_active_agents']:,}</span>
                </div>
                <div class="metric">
                    <span>Queries (Last Hour)</span>
                    <span class="metric-value">{data['summary']['queries_last_hour']}</span>
                </div>
                <div class="metric">
                    <span>Trending Now</span>
                    <span class="metric-value">{data['summary']['trending_count']}</span>
                </div>
                <div class="metric">
                    <span>Top Category</span>
                    <span class="metric-value">{data['summary']['top_category']}</span>
                </div>
            </div>
            
            <!-- Trending Agents -->
            <div class="card">
                <h3>🔥 Trending Right Now</h3>
                {self._render_trending_agents(data.get('trending_agents', [])[:5])}
            </div>
            
            <!-- Hot Queries -->
            <div class="card">
                <h3>🔍 Hot Searches</h3>
                {self._render_hot_queries(data.get('hot_queries', [])[:8])}
            </div>
            
            <!-- Discovery Velocity -->
            <div class="card">
                <h3>⚡ Discovery Velocity</h3>
                <div class="metric">
                    <span>New Agents (24h)</span>
                    <span class="metric-value">{data.get('discovery_velocity', {}).get('total_24h', 0)}</span>
                </div>
                <div class="metric">
                    <span>Average/Hour</span>
                    <span class="metric-value">{data.get('discovery_velocity', {}).get('avg_per_hour', 0)}</span>
                </div>
                <div class="metric">
                    <span>Trend</span>
                    <span class="metric-value">{data.get('discovery_velocity', {}).get('velocity_trend', 'stable').title()}</span>
                </div>
            </div>
            
            <!-- Language Trends -->
            <div class="card">
                <h3>💻 Language Trends</h3>
                {self._render_language_trends(data.get('language_trends', [])[:6])}
            </div>
            
            <!-- Quality Distribution -->
            <div class="card">
                <h3>🏆 Quality Distribution</h3>
                {self._render_quality_distribution(data.get('quality_distribution', {}))}
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 40px; color: #64748b;">
            <p>Powered by <strong>AgentIndex</strong> | Refreshes every 30 seconds</p>
            <p><a href="https://agentcrawl.dev" style="color: #3b82f6;">agentcrawl.dev</a> | 
               <a href="https://api.agentcrawl.dev/docs" style="color: #3b82f6;">API</a></p>
        </div>
    </div>
</body>
</html>
        """
    
    def _render_trending_agents(self, agents: List[Dict[str, Any]]) -> str:
        """Render trending agents section"""
        if not agents:
            return '<p style="color: #64748b;">No trending agents right now</p>'
        
        html = ""
        for agent in agents:
            html += f"""
            <div class="trending-item">
                <h4>{agent['name']}</h4>
                <p>{agent['description'][:80] if agent.get('description') else 'No description'}...</p>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span class="trending-reason">{agent.get('trend_reason', 'Trending')}</span>
                    <span style="color: #94a3b8; font-size: 0.8em;">{agent.get('quality_score', 0):.1f}/100</span>
                </div>
            </div>
            """
        return html
    
    def _render_hot_queries(self, queries: List[Dict[str, Any]]) -> str:
        """Render hot queries section"""
        if not queries:
            return '<p style="color: #64748b;">No recent queries</p>'
        
        html = ""
        for query in queries:
            html += f"""
            <div class="metric">
                <span>"{query['query']}"</span>
                <span class="metric-value">{query['frequency']}×</span>
            </div>
            """
        return html
    
    def _render_language_trends(self, languages: List[Dict[str, Any]]) -> str:
        """Render language trends section"""
        if not languages:
            return '<p style="color: #64748b;">No language data</p>'
        
        html = ""
        for lang in languages:
            new_indicator = f" (+{lang['new_this_week']})" if lang.get('new_this_week', 0) > 0 else ""
            html += f"""
            <div class="metric">
                <span>{lang['language']}{new_indicator}</span>
                <span class="metric-value">{lang['agent_count']}</span>
            </div>
            """
        return html
    
    def _render_quality_distribution(self, quality_data: Dict[str, Any]) -> str:
        """Render quality distribution section"""
        if not quality_data:
            return '<p style="color: #64748b;">No quality data</p>'
        
        dist = quality_data.get('distribution', {})
        perc = quality_data.get('percentages', {})
        
        return f"""
        <div class="metric">
            <span>🏆 Excellent (90+)</span>
            <span class="metric-value">{dist.get('excellent', 0)} ({perc.get('excellent', 0)}%)</span>
        </div>
        <div class="metric">
            <span>✅ Good (70-89)</span>
            <span class="metric-value">{dist.get('good', 0)} ({perc.get('good', 0)}%)</span>
        </div>
        <div class="metric">
            <span>⚡ Fair (50-69)</span>
            <span class="metric-value">{dist.get('fair', 0)} ({perc.get('fair', 0)}%)</span>
        </div>
        <div class="metric">
            <span>⚠️ Poor (<50)</span>
            <span class="metric-value">{dist.get('poor', 0)} ({perc.get('poor', 0)}%)</span>
        </div>
        """


if __name__ == "__main__":
    async def generate_dashboard():
        analytics = DiscoveryAnalytics()
        generator = DashboardGenerator()
        
        print("📊 Generating discovery dashboard...")
        try:
            data = await analytics.get_realtime_dashboard_data()
            html = generator.generate_dashboard_html(data)
            
            with open("discovery_dashboard.html", "w") as f:
                f.write(html)
            
            print("✅ Dashboard generated!")
            print(f"   📈 {data['summary']['total_active_agents']:,} active agents")
            print(f"   🔥 {data['summary']['trending_count']} trending")
            print(f"   🔍 {data['summary']['queries_last_hour']} queries/hour")
            print("📄 Dashboard saved to discovery_dashboard.html")
            
        except Exception as e:
            print(f"❌ Dashboard generation failed: {e}")
    
    asyncio.run(generate_dashboard())