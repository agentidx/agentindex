"""
Newsletter Automation System
Automatically generates and sends weekly AgentIndex reports
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from pathlib import Path

# Import for database access
import sys
sys.path.append('/Users/anstudio/agentindex')
from agentindex.db.models import get_session, Agent, SystemStatus
from sqlalchemy import select, func, text


class NewsletterGenerator:
    """Generates weekly newsletters with AgentIndex insights"""
    
    def __init__(self, output_dir: str = "newsletters"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Newsletter settings
        self.newsletter_title = "AgentIndex Weekly"
        self.newsletter_subtitle = "Your Weekly Dose of AI Agent Discovery"
        
    async def generate_weekly_report(self, week_offset: int = 0) -> Dict[str, Any]:
        """Generate comprehensive weekly report"""
        
        # Calculate date range
        end_date = datetime.utcnow() - timedelta(days=week_offset * 7)
        start_date = end_date - timedelta(days=7)
        
        # Get database session
        session = get_session()
        
        # Collect statistics
        stats = await self._collect_weekly_stats(session, start_date, end_date)
        new_agents = await self._get_new_agents(session, start_date, end_date)
        trending_categories = await self._get_trending_categories(session, start_date, end_date)
        quality_insights = await self._get_quality_insights(session)
        growth_metrics = await self._get_growth_metrics(session, start_date, end_date)
        ecosystem_updates = await self._get_ecosystem_updates(session, start_date, end_date)
        
        # Close session
        session.close()
        
        report = {
            "week_period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "generated_at": datetime.utcnow().isoformat(),
            "stats": stats,
            "new_agents": new_agents,
            "trending_categories": trending_categories,
            "quality_insights": quality_insights,
            "growth_metrics": growth_metrics,
            "ecosystem_updates": ecosystem_updates,
            "highlights": self._generate_highlights(stats, new_agents, growth_metrics)
        }
        
        return report
    
    async def _collect_weekly_stats(self, session, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Collect weekly statistics"""
        
        # Total agents
        total_agents = session.execute(
            select(func.count(Agent.id))
        ).scalar() or 0
        
        # New agents this week
        new_agents_count = session.execute(
            select(func.count(Agent.id))
            .where(Agent.first_indexed >= start_date)
            .where(Agent.first_indexed < end_date)
        ).scalar() or 0
        
        # Active agents (good quality)
        active_agents = session.execute(
            select(func.count(Agent.id))
            .where(Agent.is_active == True)
            .where(Agent.quality_score >= 0.7)
        ).scalar() or 0
        
        # Source distribution
        source_stats = session.execute(
            select(Agent.source, func.count(Agent.id))
            .group_by(Agent.source)
        ).all()
        
        # Category distribution
        category_stats = session.execute(
            select(Agent.category, func.count(Agent.id))
            .where(Agent.category.isnot(None))
            .group_by(Agent.category)
            .order_by(func.count(Agent.id).desc())
        ).all()
        
        return {
            "total_agents": total_agents,
            "new_agents_this_week": new_agents_count,
            "active_agents": active_agents,
            "growth_rate": round((new_agents_count / max(total_agents - new_agents_count, 1)) * 100, 2),
            "source_distribution": dict(source_stats),
            "top_categories": dict(category_stats[:10])
        }
    
    async def _get_new_agents(self, session, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get notable new agents from this week"""
        
        new_agents = session.execute(
            select(Agent)
            .where(Agent.first_indexed >= start_date)
            .where(Agent.first_indexed < end_date)
            .where(Agent.is_active == True)
            .order_by(Agent.quality_score.desc())
            .limit(10)
        ).scalars().all()
        
        return [
            {
                "id": str(agent.id),
                "name": agent.name,
                "description": agent.description,
                "category": agent.category,
                "source": agent.source,
                "url": agent.source_url,
                "quality_score": agent.quality_score,
                "stars": agent.stars,
                "trust_score": getattr(agent, 'trust_score', None)
            }
            for agent in new_agents
        ]
    
    async def _get_trending_categories(self, session, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get trending categories based on new agent additions"""
        
        trending = session.execute(
            select(
                Agent.category,
                func.count(Agent.id).label('new_count'),
                func.avg(Agent.quality_score).label('avg_quality')
            )
            .where(Agent.first_indexed >= start_date)
            .where(Agent.first_indexed < end_date)
            .where(Agent.category.isnot(None))
            .group_by(Agent.category)
            .having(func.count(Agent.id) >= 2)  # At least 2 new agents
            .order_by(func.count(Agent.id).desc())
            .limit(5)
        ).all()
        
        return [
            {
                "category": row.category,
                "new_agents": row.new_count,
                "avg_quality": round(row.avg_quality, 2) if row.avg_quality else 0
            }
            for row in trending
        ]
    
    async def _get_quality_insights(self, session) -> Dict[str, Any]:
        """Get insights about agent quality distribution"""
        
        # Quality score distribution
        quality_ranges = [
            ("Excellent (90-100%)", 0.9, 1.0),
            ("Good (70-89%)", 0.7, 0.9),
            ("Fair (50-69%)", 0.5, 0.7),
            ("Poor (<50%)", 0.0, 0.5)
        ]
        
        quality_dist = {}
        for label, min_score, max_score in quality_ranges:
            count = session.execute(
                select(func.count(Agent.id))
                .where(Agent.quality_score >= min_score)
                .where(Agent.quality_score < max_score)
            ).scalar() or 0
            quality_dist[label] = count
        
        # Average quality by source
        source_quality = session.execute(
            select(
                Agent.source,
                func.avg(Agent.quality_score).label('avg_quality'),
                func.count(Agent.id).label('agent_count')
            )
            .where(Agent.quality_score.isnot(None))
            .group_by(Agent.source)
            .order_by(func.avg(Agent.quality_score).desc())
        ).all()
        
        return {
            "quality_distribution": quality_dist,
            "source_quality_ranking": [
                {
                    "source": row.source,
                    "avg_quality": round(row.avg_quality, 3),
                    "agent_count": row.agent_count
                }
                for row in source_quality
            ]
        }
    
    async def _get_growth_metrics(self, session, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Calculate growth metrics and trends"""
        
        # Get previous week for comparison
        prev_week_start = start_date - timedelta(days=7)
        prev_week_end = start_date
        
        # This week's additions
        this_week = session.execute(
            select(func.count(Agent.id))
            .where(Agent.first_indexed >= start_date)
            .where(Agent.first_indexed < end_date)
        ).scalar() or 0
        
        # Previous week's additions
        prev_week = session.execute(
            select(func.count(Agent.id))
            .where(Agent.first_indexed >= prev_week_start)
            .where(Agent.first_indexed < prev_week_end)
        ).scalar() or 0
        
        # Calculate growth rate
        growth_rate = 0.0
        if prev_week > 0:
            growth_rate = ((this_week - prev_week) / prev_week) * 100
        
        # Monthly growth (last 30 days)
        month_start = end_date - timedelta(days=30)
        monthly_additions = session.execute(
            select(func.count(Agent.id))
            .where(Agent.first_indexed >= month_start)
            .where(Agent.first_indexed < end_date)
        ).scalar() or 0
        
        return {
            "weekly_additions": this_week,
            "previous_week_additions": prev_week,
            "week_over_week_growth": round(growth_rate, 1),
            "monthly_additions": monthly_additions,
            "daily_average": round(this_week / 7, 1)
        }
    
    async def _get_ecosystem_updates(self, session, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get ecosystem updates and notable changes"""
        
        # New sources discovered
        sources_this_week = session.execute(
            select(Agent.source)
            .where(Agent.first_indexed >= start_date)
            .where(Agent.first_indexed < end_date)
            .distinct()
        ).scalars().all()
        
        # Top starred new agents
        top_starred = session.execute(
            select(Agent)
            .where(Agent.first_indexed >= start_date)
            .where(Agent.first_indexed < end_date)
            .where(Agent.stars.isnot(None))
            .where(Agent.stars > 100)
            .order_by(Agent.stars.desc())
            .limit(3)
        ).scalars().all()
        
        updates = []
        
        # Source diversity update
        if sources_this_week:
            updates.append({
                "type": "ecosystem_expansion",
                "title": "Source Diversity Growing",
                "description": f"Discovered agents from {len(sources_this_week)} different sources this week",
                "details": list(sources_this_week)
            })
        
        # High-quality additions
        if top_starred:
            updates.append({
                "type": "quality_additions",
                "title": "High-Quality Agents Added",
                "description": f"Added {len(top_starred)} highly-starred agents (100+ stars)",
                "details": [
                    {
                        "name": agent.name,
                        "stars": agent.stars,
                        "category": agent.category
                    }
                    for agent in top_starred
                ]
            })
        
        return updates
    
    def _generate_highlights(self, stats: Dict, new_agents: List, growth_metrics: Dict) -> List[str]:
        """Generate newsletter highlights"""
        
        highlights = []
        
        # Growth highlight
        if growth_metrics["weekly_additions"] > 0:
            highlights.append(f"🚀 Added {growth_metrics['weekly_additions']} new agents this week")
        
        # Quality highlight
        if stats["active_agents"] > 0:
            quality_percentage = round((stats["active_agents"] / stats["total_agents"]) * 100, 1)
            highlights.append(f"✅ {quality_percentage}% of agents meet high quality standards")
        
        # Category highlight
        if stats["top_categories"]:
            top_category = list(stats["top_categories"].keys())[0]
            top_count = stats["top_categories"][top_category]
            highlights.append(f"📈 {top_category} leads with {top_count} agents")
        
        # New agent highlight
        if new_agents:
            best_new = max(new_agents, key=lambda x: x.get("quality_score", 0) or 0)
            highlights.append(f"⭐ Best new addition: {best_new['name']} ({best_new['category']})")
        
        return highlights
    
    def generate_html_newsletter(self, report: Dict[str, Any]) -> str:
        """Generate HTML newsletter from report data"""
        
        html = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{self.newsletter_title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #007cba, #00a0d0); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 28px; }}
        .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
        .content {{ padding: 30px; }}
        .section {{ margin-bottom: 30px; }}
        .section h2 {{ color: #333; border-bottom: 2px solid #007cba; padding-bottom: 10px; margin-bottom: 20px; }}
        .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }}
        .stat-number {{ font-size: 24px; font-weight: bold; color: #007cba; }}
        .stat-label {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .highlight {{ background: #e8f4f8; padding: 15px; border-radius: 8px; border-left: 4px solid #007cba; margin: 10px 0; }}
        .agent-list {{ background: #f8f9fa; padding: 15px; border-radius: 8px; }}
        .agent-item {{ padding: 10px 0; border-bottom: 1px solid #e9ecef; }}
        .agent-item:last-child {{ border-bottom: none; }}
        .agent-name {{ font-weight: 600; color: #333; }}
        .agent-category {{ background: #007cba; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin-left: 10px; }}
        .category-list {{ display: flex; flex-wrap: wrap; gap: 10px; }}
        .category-tag {{ background: #e8f4f8; color: #007cba; padding: 8px 12px; border-radius: 20px; font-size: 14px; }}
        .footer {{ background: #333; color: white; padding: 20px; text-align: center; font-size: 14px; }}
        .footer a {{ color: #00a0d0; text-decoration: none; }}
        .growth-positive {{ color: #28a745; }}
        .growth-negative {{ color: #dc3545; }}
        .quality-bar {{ height: 8px; background: #ddd; border-radius: 4px; margin: 5px 0; overflow: hidden; }}
        .quality-fill {{ height: 100%; background: linear-gradient(90deg, #28a745, #ffc107, #dc3545); }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.newsletter_title}</h1>
            <p>{self.newsletter_subtitle}</p>
            <p><strong>{report["week_period"]}</strong></p>
        </div>
        
        <div class="content">
            <div class="section">
                <h2>📊 Weekly Highlights</h2>
                {''.join(f'<div class="highlight">• {highlight}</div>' for highlight in report["highlights"])}
            </div>
            
            <div class="section">
                <h2>📈 Growth Metrics</h2>
                <div class="stat-grid">
                    <div class="stat-card">
                        <div class="stat-number">{report["stats"]["total_agents"]:,}</div>
                        <div class="stat-label">Total Agents</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{report["stats"]["new_agents_this_week"]}</div>
                        <div class="stat-label">New This Week</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{report["growth_metrics"]["daily_average"]}</div>
                        <div class="stat-label">Daily Average</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number {'growth-positive' if report['growth_metrics']['week_over_week_growth'] >= 0 else 'growth-negative'}">{report["growth_metrics"]["week_over_week_growth"]}%</div>
                        <div class="stat-label">Week/Week Growth</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>🔥 Trending Categories</h2>
                <div class="category-list">
                    {''.join(f'<span class="category-tag">{cat["category"]} (+{cat["new_agents"]})</span>' for cat in report["trending_categories"])}
                </div>
            </div>
            
            <div class="section">
                <h2>⭐ Notable New Agents</h2>
                <div class="agent-list">
                    {''.join(f'''
                    <div class="agent-item">
                        <div class="agent-name">{agent["name"]}<span class="agent-category">{agent["category"]}</span></div>
                        <div style="font-size: 14px; color: #666; margin-top: 5px;">{agent["description"][:100]}{'...' if len(agent["description"]) > 100 else ''}</div>
                        <div style="font-size: 12px; color: #999; margin-top: 5px;">
                            {agent["source"]} • Quality: {(agent["quality_score"] * 100):.0f}%
                            {f' • ⭐ {agent["stars"]}' if agent["stars"] else ''}
                        </div>
                    </div>
                    ''' for agent in report["new_agents"][:5])}
                </div>
            </div>
            
            <div class="section">
                <h2>🔍 Quality Insights</h2>
                {''.join(f'''
                <div style="margin: 15px 0;">
                    <div style="display: flex; justify-content: space-between;">
                        <span>{quality_range}</span>
                        <span><strong>{count}</strong> agents</span>
                    </div>
                    <div class="quality-bar">
                        <div class="quality-fill" style="width: {(count / report['stats']['total_agents'] * 100) if report['stats']['total_agents'] > 0 else 0}%"></div>
                    </div>
                </div>
                ''' for quality_range, count in report["quality_insights"]["quality_distribution"].items())}
            </div>
        </div>
        
        <div class="footer">
            <p><strong>AgentIndex</strong> - The DNS for AI Agents</p>
            <p>
                <a href="https://agentcrawl.dev">🌐 agentcrawl.dev</a> • 
                <a href="https://api.agentcrawl.dev">🔌 API</a> • 
                <a href="https://github.com/agentidx">💻 GitHub</a>
            </p>
            <p style="font-size: 12px; opacity: 0.7;">
                Generated automatically • {report["generated_at"][:10]}
            </p>
        </div>
    </div>
</body>
</html>
'''
        
        return html
    
    def save_newsletter(self, report: Dict[str, Any], filename: Optional[str] = None) -> str:
        """Save newsletter to file"""
        
        if not filename:
            week_str = report["week_period"].replace(" to ", "_").replace("-", "")
            filename = f"newsletter_{week_str}.html"
        
        filepath = self.output_dir / filename
        html_content = self.generate_html_newsletter(report)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"📧 Newsletter saved: {filepath}")
        return str(filepath)
    
    async def generate_and_save_newsletter(self, week_offset: int = 0) -> str:
        """Generate and save newsletter for specified week"""
        
        print("📊 Generating weekly report...")
        report = await self.generate_weekly_report(week_offset)
        
        print("📧 Creating HTML newsletter...")
        filepath = self.save_newsletter(report)
        
        print(f"✅ Newsletter complete!")
        print(f"   Period: {report['week_period']}")
        print(f"   Total Agents: {report['stats']['total_agents']:,}")
        print(f"   New This Week: {report['stats']['new_agents_this_week']}")
        print(f"   Trending Categories: {len(report['trending_categories'])}")
        
        return filepath


class NewsletterScheduler:
    """Schedules automatic newsletter generation"""
    
    def __init__(self):
        self.generator = NewsletterGenerator()
    
    async def run_weekly_generation(self):
        """Run weekly newsletter generation (called by cron)"""
        try:
            print(f"🔄 Starting weekly newsletter generation at {datetime.utcnow()}")
            
            # Generate current week's newsletter
            filepath = await self.generator.generate_and_save_newsletter()
            
            # Also generate a JSON version for API consumption
            report = await self.generator.generate_weekly_report()
            json_path = filepath.replace('.html', '.json')
            with open(json_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            print(f"✅ Newsletter generation complete!")
            print(f"   HTML: {filepath}")
            print(f"   JSON: {json_path}")
            
            return {
                "success": True,
                "html_path": filepath,
                "json_path": json_path,
                "report_summary": {
                    "total_agents": report["stats"]["total_agents"],
                    "new_this_week": report["stats"]["new_agents_this_week"],
                    "growth_rate": report["stats"]["growth_rate"]
                }
            }
            
        except Exception as e:
            print(f"❌ Newsletter generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


if __name__ == "__main__":
    # Demo newsletter generation
    async def demo():
        scheduler = NewsletterScheduler()
        result = await scheduler.run_weekly_generation()
        print(f"\\n📋 Result: {result}")
    
    asyncio.run(demo())