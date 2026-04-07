"""
Discovery Dashboard - Real-time Analytics
Live monitoring of agent discovery patterns and trends
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
import sqlite3
import os


@dataclass
class QueryAnalytics:
    """Analytics for a discovery query"""
    query: str
    timestamp: datetime
    results_count: int
    response_time_ms: int
    category: Optional[str]
    protocols: List[str]
    user_agent: Optional[str]
    ip_address: Optional[str]
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "timestamp": self.timestamp.isoformat(),
            "protocols": self.protocols or []
        }


@dataclass
class TrendingAgent:
    """Trending agent data"""
    id: str
    name: str
    category: str
    search_count: int
    growth_rate: float
    trust_score: Optional[float]
    last_searched: datetime
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "last_searched": self.last_searched.isoformat()
        }


class DiscoveryDashboard:
    """Real-time analytics dashboard for agent discovery"""
    
    def __init__(self, db_path: str = "discovery_analytics.db"):
        self.db_path = db_path
        self.init_database()
        self.cache = {
            "trending_queries": [],
            "trending_agents": [],
            "category_stats": {},
            "protocol_stats": {},
            "hourly_activity": [],
            "response_times": [],
            "last_updated": None
        }
        self.cache_ttl = timedelta(minutes=5)
    
    def init_database(self):
        """Initialize SQLite database for analytics storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create queries table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                results_count INTEGER,
                response_time_ms INTEGER,
                category TEXT,
                protocols TEXT,
                user_agent TEXT,
                ip_address TEXT
            )
        ''')
        
        # Create agents table for tracking popularity
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                agent_name TEXT,
                category TEXT,
                timestamp DATETIME NOT NULL,
                query TEXT
            )
        ''')
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_queries_category ON queries(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_searches_timestamp ON agent_searches(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_searches_agent_id ON agent_searches(agent_id)')
        
        conn.commit()
        conn.close()
    
    def log_query(self, analytics: QueryAnalytics, results: List[Dict] = None):
        """Log a discovery query for analytics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert query log
        cursor.execute('''
            INSERT INTO queries (query, timestamp, results_count, response_time_ms, 
                               category, protocols, user_agent, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            analytics.query,
            analytics.timestamp,
            analytics.results_count,
            analytics.response_time_ms,
            analytics.category,
            json.dumps(analytics.protocols) if analytics.protocols else None,
            analytics.user_agent,
            analytics.ip_address
        ))
        
        # Log individual agent searches
        if results:
            for result in results:
                cursor.execute('''
                    INSERT INTO agent_searches (agent_id, agent_name, category, timestamp, query)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    result.get("id"),
                    result.get("name"),
                    result.get("category"),
                    analytics.timestamp,
                    analytics.query
                ))
        
        conn.commit()
        conn.close()
        
        # Clear cache to force refresh
        self._clear_cache()
    
    def _clear_cache(self):
        """Clear analytics cache"""
        self.cache["last_updated"] = None
    
    def _should_refresh_cache(self) -> bool:
        """Check if cache should be refreshed"""
        if self.cache["last_updated"] is None:
            return True
        return datetime.utcnow() - self.cache["last_updated"] > self.cache_ttl
    
    def get_trending_queries(self, hours: int = 24, limit: int = 20) -> List[Dict]:
        """Get trending search queries"""
        if not self._should_refresh_cache():
            return self.cache["trending_queries"]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT query, COUNT(*) as search_count, 
                   AVG(results_count) as avg_results,
                   AVG(response_time_ms) as avg_response_time,
                   MAX(timestamp) as last_searched
            FROM queries 
            WHERE timestamp >= ?
            GROUP BY LOWER(TRIM(query))
            HAVING search_count > 1
            ORDER BY search_count DESC
            LIMIT ?
        ''', (since, limit))
        
        trending = []
        for row in cursor.fetchall():
            trending.append({
                "query": row[0],
                "search_count": row[1],
                "avg_results": round(row[2], 1),
                "avg_response_time": round(row[3], 1),
                "last_searched": row[4]
            })
        
        conn.close()
        self.cache["trending_queries"] = trending
        return trending
    
    def get_trending_agents(self, hours: int = 24, limit: int = 15) -> List[TrendingAgent]:
        """Get trending agents based on search frequency"""
        if not self._should_refresh_cache():
            return self.cache["trending_agents"]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        previous_period = since - timedelta(hours=hours)
        
        # Get current period counts
        cursor.execute('''
            SELECT agent_id, agent_name, category, COUNT(*) as current_count,
                   MAX(timestamp) as last_searched
            FROM agent_searches 
            WHERE timestamp >= ? AND agent_id IS NOT NULL
            GROUP BY agent_id
            ORDER BY current_count DESC
            LIMIT ?
        ''', (since, limit))
        
        current_results = cursor.fetchall()
        
        trending_agents = []
        for row in current_results:
            agent_id, agent_name, category, current_count, last_searched = row
            
            # Get previous period count for growth rate calculation
            cursor.execute('''
                SELECT COUNT(*) FROM agent_searches 
                WHERE agent_id = ? AND timestamp >= ? AND timestamp < ?
            ''', (agent_id, previous_period, since))
            
            previous_count = cursor.fetchone()[0]
            
            # Calculate growth rate
            if previous_count > 0:
                growth_rate = ((current_count - previous_count) / previous_count) * 100
            else:
                growth_rate = 100.0 if current_count > 0 else 0.0
            
            trending_agent = TrendingAgent(
                id=agent_id,
                name=agent_name or "Unknown Agent",
                category=category or "unknown",
                search_count=current_count,
                growth_rate=round(growth_rate, 1),
                trust_score=None,  # Would need to fetch from main DB
                last_searched=datetime.fromisoformat(last_searched)
            )
            
            trending_agents.append(trending_agent)
        
        conn.close()
        self.cache["trending_agents"] = trending_agents
        return trending_agents
    
    def get_category_stats(self, hours: int = 24) -> Dict[str, Dict]:
        """Get category search statistics"""
        if not self._should_refresh_cache():
            return self.cache["category_stats"]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT category, COUNT(*) as search_count,
                   AVG(results_count) as avg_results,
                   AVG(response_time_ms) as avg_response_time
            FROM queries 
            WHERE timestamp >= ? AND category IS NOT NULL
            GROUP BY category
            ORDER BY search_count DESC
        ''', (since,))
        
        category_stats = {}
        total_searches = 0
        
        for row in cursor.fetchall():
            category, count, avg_results, avg_response = row
            category_stats[category] = {
                "search_count": count,
                "avg_results": round(avg_results, 1),
                "avg_response_time": round(avg_response, 1)
            }
            total_searches += count
        
        # Add percentages
        for category in category_stats:
            category_stats[category]["percentage"] = round(
                (category_stats[category]["search_count"] / total_searches) * 100, 1
            ) if total_searches > 0 else 0
        
        conn.close()
        self.cache["category_stats"] = category_stats
        return category_stats
    
    def get_hourly_activity(self, hours: int = 24) -> List[Dict]:
        """Get hourly search activity"""
        if not self._should_refresh_cache():
            return self.cache["hourly_activity"]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                   COUNT(*) as query_count,
                   AVG(response_time_ms) as avg_response_time
            FROM queries 
            WHERE timestamp >= ?
            GROUP BY hour
            ORDER BY hour
        ''', (since,))
        
        hourly_data = []
        for row in cursor.fetchall():
            hourly_data.append({
                "hour": row[0],
                "query_count": row[1],
                "avg_response_time": round(row[2], 1)
            })
        
        conn.close()
        self.cache["hourly_activity"] = hourly_data
        return hourly_data
    
    def get_response_time_distribution(self, hours: int = 24) -> Dict[str, Any]:
        """Get response time statistics"""
        if not self._should_refresh_cache():
            return self.cache["response_times"]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT response_time_ms FROM queries 
            WHERE timestamp >= ? AND response_time_ms IS NOT NULL
            ORDER BY response_time_ms
        ''', (since,))
        
        response_times = [row[0] for row in cursor.fetchall()]
        
        if not response_times:
            return {"percentiles": {}, "avg": 0, "count": 0}
        
        response_times.sort()
        count = len(response_times)
        
        percentiles = {
            "p50": response_times[int(count * 0.5)],
            "p90": response_times[int(count * 0.9)],
            "p95": response_times[int(count * 0.95)],
            "p99": response_times[int(count * 0.99)]
        }
        
        stats = {
            "percentiles": percentiles,
            "avg": round(sum(response_times) / count, 1),
            "min": min(response_times),
            "max": max(response_times),
            "count": count
        }
        
        conn.close()
        self.cache["response_times"] = stats
        return stats
    
    def get_protocol_stats(self, hours: int = 24) -> Dict[str, int]:
        """Get protocol usage statistics"""
        if not self._should_refresh_cache():
            return self.cache["protocol_stats"]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        cursor.execute('''
            SELECT protocols FROM queries 
            WHERE timestamp >= ? AND protocols IS NOT NULL
        ''', (since,))
        
        protocol_counts = Counter()
        
        for row in cursor.fetchall():
            protocols = json.loads(row[0]) if row[0] else []
            for protocol in protocols:
                protocol_counts[protocol] += 1
        
        conn.close()
        protocol_stats = dict(protocol_counts.most_common())
        self.cache["protocol_stats"] = protocol_stats
        return protocol_stats
    
    def get_dashboard_data(self, hours: int = 24) -> Dict[str, Any]:
        """Get complete dashboard data"""
        
        # Update cache timestamp
        self.cache["last_updated"] = datetime.utcnow()
        
        return {
            "trending_queries": self.get_trending_queries(hours),
            "trending_agents": [agent.to_dict() for agent in self.get_trending_agents(hours)],
            "category_stats": self.get_category_stats(hours),
            "protocol_stats": self.get_protocol_stats(hours),
            "hourly_activity": self.get_hourly_activity(hours),
            "response_times": self.get_response_time_distribution(hours),
            "summary": self._get_summary_stats(hours),
            "last_updated": self.cache["last_updated"].isoformat()
        }
    
    def _get_summary_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get summary statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        # Total queries
        cursor.execute('SELECT COUNT(*) FROM queries WHERE timestamp >= ?', (since,))
        total_queries = cursor.fetchone()[0]
        
        # Unique agents searched
        cursor.execute('''
            SELECT COUNT(DISTINCT agent_id) FROM agent_searches 
            WHERE timestamp >= ? AND agent_id IS NOT NULL
        ''', (since,))
        unique_agents = cursor.fetchone()[0]
        
        # Average results per query
        cursor.execute('''
            SELECT AVG(results_count) FROM queries 
            WHERE timestamp >= ? AND results_count IS NOT NULL
        ''', (since,))
        avg_results = cursor.fetchone()[0] or 0
        
        # Most active hour
        cursor.execute('''
            SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
            FROM queries WHERE timestamp >= ?
            GROUP BY hour ORDER BY count DESC LIMIT 1
        ''', (since,))
        
        most_active_result = cursor.fetchone()
        most_active_hour = int(most_active_result[0]) if most_active_result else 0
        
        conn.close()
        
        return {
            "total_queries": total_queries,
            "unique_agents_searched": unique_agents,
            "avg_results_per_query": round(avg_results, 1),
            "most_active_hour": f"{most_active_hour:02d}:00",
            "queries_per_hour": round(total_queries / hours, 1) if hours > 0 else 0
        }
    
    def generate_insights(self, hours: int = 24) -> List[str]:
        """Generate AI-powered insights from the data"""
        dashboard_data = self.get_dashboard_data(hours)
        insights = []
        
        # Query volume insights
        summary = dashboard_data["summary"]
        if summary["total_queries"] > 100:
            insights.append(f"🔥 High activity: {summary['total_queries']} queries in {hours}h ({summary['queries_per_hour']:.1f}/hour)")
        elif summary["total_queries"] < 10:
            insights.append(f"📊 Low activity: Only {summary['total_queries']} queries in {hours}h")
        
        # Response time insights
        response_times = dashboard_data["response_times"]
        if response_times.get("percentiles", {}).get("p95", 0) > 1000:
            insights.append(f"⚠️ Slow responses: 95th percentile is {response_times['percentiles']['p95']}ms")
        elif response_times.get("avg", 0) < 200:
            insights.append(f"⚡ Fast responses: Average {response_times['avg']}ms response time")
        
        # Category insights
        category_stats = dashboard_data["category_stats"]
        if category_stats:
            top_category = max(category_stats.keys(), key=lambda k: category_stats[k]["search_count"])
            percentage = category_stats[top_category]["percentage"]
            insights.append(f"📈 Most popular category: {top_category} ({percentage}% of searches)")
        
        # Trending insights
        trending_agents = dashboard_data["trending_agents"]
        if trending_agents:
            fastest_growing = max(trending_agents, key=lambda x: x["growth_rate"])
            if fastest_growing["growth_rate"] > 50:
                insights.append(f"🚀 Fastest growing: {fastest_growing['name']} (+{fastest_growing['growth_rate']}%)")
        
        return insights


# Dashboard HTML template
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>📊 Discovery Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-number { font-size: 32px; font-weight: bold; color: #007cba; margin-bottom: 5px; }
        .stat-label { color: #666; font-size: 14px; }
        .dashboard-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
        .panel { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .panel h3 { margin-top: 0; color: #333; }
        .trend-item { padding: 10px 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
        .trend-item:last-child { border-bottom: none; }
        .trend-query { font-weight: 500; }
        .trend-count { color: #007cba; font-weight: bold; }
        .insight { background: #e8f4f8; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #007cba; }
        .chart-container { height: 300px; margin: 20px 0; }
        .category-bar { height: 20px; background: #ddd; border-radius: 10px; margin: 5px 0; overflow: hidden; }
        .category-fill { height: 100%; background: linear-gradient(90deg, #007cba, #00a0d0); }
        .agent-item { padding: 8px 0; border-bottom: 1px solid #eee; }
        .agent-name { font-weight: 500; }
        .agent-stats { font-size: 12px; color: #666; }
        .growth-up { color: #28a745; }
        .growth-down { color: #dc3545; }
        .refresh-btn { background: #007cba; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }
        .last-updated { color: #666; font-size: 12px; text-align: right; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Discovery Dashboard</h1>
            <p>Real-time analytics for agent discovery patterns</p>
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Data</button>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number" id="total-queries">{{total_queries}}</div>
                <div class="stat-label">Total Queries (24h)</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="unique-agents">{{unique_agents}}</div>
                <div class="stat-label">Unique Agents Searched</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="avg-response">{{avg_response}}ms</div>
                <div class="stat-label">Avg Response Time</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="queries-per-hour">{{queries_per_hour}}</div>
                <div class="stat-label">Queries per Hour</div>
            </div>
        </div>
        
        <div class="dashboard-grid">
            <div class="panel">
                <h3>🔥 Trending Queries</h3>
                <div id="trending-queries">
                    <!-- Trending queries will be inserted here -->
                </div>
            </div>
            
            <div class="panel">
                <h3>📈 Trending Agents</h3>
                <div id="trending-agents">
                    <!-- Trending agents will be inserted here -->
                </div>
            </div>
        </div>
        
        <div class="dashboard-grid">
            <div class="panel">
                <h3>📊 Category Distribution</h3>
                <div id="category-stats">
                    <!-- Category stats will be inserted here -->
                </div>
            </div>
            
            <div class="panel">
                <h3>💡 Insights</h3>
                <div id="insights">
                    <!-- Insights will be inserted here -->
                </div>
            </div>
        </div>
        
        <div class="last-updated">
            Last updated: <span id="last-updated">{{last_updated}}</span>
        </div>
    </div>
    
    <script>
        // Auto-refresh every 5 minutes
        setTimeout(() => location.reload(), 5 * 60 * 1000);
        
        // Add interactive features here
        function showQueryDetails(query) {
            alert(`Query: ${query}\\nClick OK to see detailed analytics`);
        }
    </script>
</body>
</html>
'''


if __name__ == "__main__":
    # Demo the dashboard
    dashboard = DiscoveryDashboard()
    
    # Log some sample queries
    sample_queries = [
        QueryAnalytics(
            query="web scraping tool",
            timestamp=datetime.utcnow() - timedelta(minutes=30),
            results_count=15,
            response_time_ms=250,
            category="web-scraping",
            protocols=["rest", "mcp"],
            user_agent="Mozilla/5.0",
            ip_address="192.168.1.1"
        ),
        QueryAnalytics(
            query="data analysis agent",
            timestamp=datetime.utcnow() - timedelta(minutes=15),
            results_count=8,
            response_time_ms=180,
            category="data-analysis", 
            protocols=["rest"],
            user_agent="Python/requests",
            ip_address="10.0.0.1"
        )
    ]
    
    for query in sample_queries:
        dashboard.log_query(query, [
            {"id": "agent-1", "name": "Test Agent", "category": query.category}
        ])
    
    # Get dashboard data
    data = dashboard.get_dashboard_data(24)
    print(f"📊 Dashboard Data:")
    print(f"  Total Queries: {data['summary']['total_queries']}")
    print(f"  Trending Queries: {len(data['trending_queries'])}")
    print(f"  Trending Agents: {len(data['trending_agents'])}")
    
    # Generate insights
    insights = dashboard.generate_insights(24)
    print(f"\\n💡 Insights:")
    for insight in insights:
        print(f"  {insight}")