"""
Experiment Tracking System - Google 20%-Time Approach
Tracks usage, traction, and success metrics for experimental features
"""

import asyncio
import asyncpg
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json


class ExperimentStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    PROMOTED = "promoted"  # Graduated to main features
    DEPRECATED = "deprecated"  # Being phased out
    ARCHIVED = "archived"  # No longer maintained


@dataclass
class ExperimentMetrics:
    """Metrics for tracking experiment success"""
    experiment_id: str
    total_users: int
    daily_active_users: int
    engagement_rate: float  # Actions per user
    retention_rate: float   # Users coming back
    conversion_rate: float  # Users taking desired action
    user_feedback_score: float  # Average rating 1-5
    last_updated: datetime


class ExperimentTracker:
    """Tracks experimental features following Google 20%-time approach"""
    
    def __init__(self, db_url: str = "postgresql://anstudio@localhost/agentindex"):
        self.db_url = db_url
        self.experiments = self._define_experiments()
    
    def _define_experiments(self) -> Dict[str, Dict[str, Any]]:
        """Define all current experiments with their success criteria"""
        
        return {
            "agent_battle": {
                "name": "Agent Battle Royale",
                "description": "Community voting system for agent comparisons",
                "success_metrics": {
                    "min_daily_votes": 50,
                    "min_battles_created": 10,
                    "min_user_retention": 0.3
                },
                "launch_date": "2026-02-15",
                "status": ExperimentStatus.ACTIVE,
                "team": "growth",
                "effort_percentage": 15
            },
            "discovery_dashboard": {
                "name": "Developer Discovery Dashboard", 
                "description": "Real-time analytics and trending insights",
                "success_metrics": {
                    "min_daily_views": 100,
                    "min_session_duration": 120,  # seconds
                    "min_return_rate": 0.25
                },
                "launch_date": "2026-02-15",
                "status": ExperimentStatus.ACTIVE,
                "team": "product",
                "effort_percentage": 20
            },
            "agent_sommelier": {
                "name": "AI Agent Sommelier",
                "description": "Personalized agent recommendations",
                "success_metrics": {
                    "min_recommendation_clicks": 0.4,  # Click-through rate
                    "min_user_profiles": 25,
                    "min_satisfaction_score": 4.0
                },
                "launch_date": "2026-02-15", 
                "status": ExperimentStatus.ACTIVE,
                "team": "ai",
                "effort_percentage": 25
            },
            "integration_generator": {
                "name": "One-Click Integration Generator",
                "description": "Auto-generates framework integration code", 
                "success_metrics": {
                    "min_code_generations": 30,
                    "min_frameworks_used": 3,
                    "min_user_satisfaction": 4.2
                },
                "launch_date": "2026-02-15",
                "status": ExperimentStatus.ACTIVE,
                "team": "developer-experience", 
                "effort_percentage": 30
            }
        }
    
    async def log_experiment_event(
        self,
        experiment_id: str,
        event_type: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an event for experiment tracking"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            await self._ensure_tracking_tables(conn)
            
            await conn.execute("""
                INSERT INTO experiment_events (
                    experiment_id, event_type, user_id, metadata, timestamp
                ) VALUES ($1, $2, $3, $4, $5)
            """, experiment_id, event_type, user_id, 
                json.dumps(metadata) if metadata else None,
                datetime.utcnow()
            )
            
        finally:
            await conn.close()
    
    async def calculate_experiment_metrics(self, experiment_id: str) -> ExperimentMetrics:
        """Calculate current metrics for an experiment"""
        
        conn = await asyncpg.connect(self.db_url)
        
        try:
            # Total users who have interacted with experiment
            total_users = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id) 
                FROM experiment_events 
                WHERE experiment_id = $1 AND user_id IS NOT NULL
            """, experiment_id)
            
            # Daily active users (last 24h)
            daily_active = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id)
                FROM experiment_events
                WHERE experiment_id = $1 
                AND timestamp > NOW() - INTERVAL '24 hours'
                AND user_id IS NOT NULL
            """, experiment_id)
            
            # Engagement rate (actions per user)
            total_events = await conn.fetchval("""
                SELECT COUNT(*)
                FROM experiment_events
                WHERE experiment_id = $1
            """, experiment_id)
            
            engagement_rate = (total_events / max(total_users, 1)) if total_users > 0 else 0.0
            
            # Retention rate (users who came back)
            retention_users = await conn.fetchval("""
                WITH user_days AS (
                    SELECT user_id, DATE(timestamp) as event_date
                    FROM experiment_events
                    WHERE experiment_id = $1 AND user_id IS NOT NULL
                    GROUP BY user_id, DATE(timestamp)
                ),
                user_day_counts AS (
                    SELECT user_id, COUNT(DISTINCT event_date) as active_days
                    FROM user_days
                    GROUP BY user_id
                )
                SELECT COUNT(*)::float / NULLIF(
                    (SELECT COUNT(DISTINCT user_id) FROM experiment_events WHERE experiment_id = $1), 0
                )
                FROM user_day_counts
                WHERE active_days > 1
            """, experiment_id)
            
            retention_rate = retention_users or 0.0
            
            # Conversion rate (depends on experiment type)
            conversion_rate = await self._calculate_conversion_rate(conn, experiment_id)
            
            # User feedback score (if available)
            feedback_score = await conn.fetchval("""
                SELECT AVG((metadata->>'rating')::float)
                FROM experiment_events
                WHERE experiment_id = $1 
                AND event_type = 'feedback'
                AND metadata->>'rating' IS NOT NULL
            """, experiment_id) or 0.0
            
            return ExperimentMetrics(
                experiment_id=experiment_id,
                total_users=total_users or 0,
                daily_active_users=daily_active or 0,
                engagement_rate=engagement_rate,
                retention_rate=retention_rate,
                conversion_rate=conversion_rate,
                user_feedback_score=feedback_score,
                last_updated=datetime.utcnow()
            )
            
        finally:
            await conn.close()
    
    async def _calculate_conversion_rate(self, conn: asyncpg.Connection, experiment_id: str) -> float:
        """Calculate conversion rate specific to experiment type"""
        
        experiment_config = self.experiments.get(experiment_id, {})
        
        if experiment_id == "agent_battle":
            # Conversion = users who voted / users who viewed
            voters = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id)
                FROM experiment_events
                WHERE experiment_id = $1 AND event_type = 'vote'
            """, experiment_id) or 0
            
            viewers = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id) 
                FROM experiment_events
                WHERE experiment_id = $1 AND event_type = 'view_battle'
            """, experiment_id) or 1
            
            return voters / max(viewers, 1)
            
        elif experiment_id == "discovery_dashboard":
            # Conversion = users who stayed >2 minutes / total viewers
            long_sessions = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id)
                FROM experiment_events
                WHERE experiment_id = $1 
                AND event_type = 'session_end'
                AND (metadata->>'duration')::int > 120
            """, experiment_id) or 0
            
            total_sessions = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id)
                FROM experiment_events
                WHERE experiment_id = $1 AND event_type = 'session_start'
            """, experiment_id) or 1
            
            return long_sessions / max(total_sessions, 1)
            
        elif experiment_id == "agent_sommelier":
            # Conversion = users who clicked recommendations / users who got recommendations
            clicks = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id)
                FROM experiment_events
                WHERE experiment_id = $1 AND event_type = 'recommendation_click'
            """, experiment_id) or 0
            
            recommendations = await conn.fetchval("""
                SELECT COUNT(DISTINCT user_id)
                FROM experiment_events
                WHERE experiment_id = $1 AND event_type = 'recommendations_shown'
            """, experiment_id) or 1
            
            return clicks / max(recommendations, 1)
            
        elif experiment_id == "integration_generator":
            # Conversion = users who copied code / users who generated code
            copies = await conn.fetchval("""
                SELECT COUNT(*)
                FROM experiment_events
                WHERE experiment_id = $1 AND event_type = 'code_copied'
            """, experiment_id) or 0
            
            generations = await conn.fetchval("""
                SELECT COUNT(*)
                FROM experiment_events
                WHERE experiment_id = $1 AND event_type = 'code_generated'
            """, experiment_id) or 1
            
            return copies / max(generations, 1)
        
        return 0.0
    
    async def evaluate_experiments(self) -> Dict[str, Dict[str, Any]]:
        """Evaluate all experiments against success criteria"""
        
        evaluations = {}
        
        for experiment_id, config in self.experiments.items():
            metrics = await self.calculate_experiment_metrics(experiment_id)
            success_criteria = config["success_metrics"]
            
            # Check each success criterion
            results = {}
            overall_success = True
            
            if experiment_id == "agent_battle":
                # Check daily votes (simulate based on total events)
                daily_votes = metrics.daily_active_users * metrics.engagement_rate
                results["daily_votes"] = {
                    "current": daily_votes,
                    "target": success_criteria["min_daily_votes"],
                    "met": daily_votes >= success_criteria["min_daily_votes"]
                }
                
                results["user_retention"] = {
                    "current": metrics.retention_rate,
                    "target": success_criteria["min_user_retention"], 
                    "met": metrics.retention_rate >= success_criteria["min_user_retention"]
                }
                
            elif experiment_id == "discovery_dashboard":
                results["daily_views"] = {
                    "current": metrics.daily_active_users,
                    "target": success_criteria["min_daily_views"],
                    "met": metrics.daily_active_users >= success_criteria["min_daily_views"]
                }
                
                results["return_rate"] = {
                    "current": metrics.retention_rate,
                    "target": success_criteria["min_return_rate"],
                    "met": metrics.retention_rate >= success_criteria["min_return_rate"]
                }
                
            elif experiment_id == "agent_sommelier":
                results["click_through_rate"] = {
                    "current": metrics.conversion_rate,
                    "target": success_criteria["min_recommendation_clicks"],
                    "met": metrics.conversion_rate >= success_criteria["min_recommendation_clicks"]
                }
                
                results["satisfaction_score"] = {
                    "current": metrics.user_feedback_score,
                    "target": success_criteria["min_satisfaction_score"],
                    "met": metrics.user_feedback_score >= success_criteria["min_satisfaction_score"]
                }
                
            elif experiment_id == "integration_generator":
                # Simulate code generations based on events
                code_generations = metrics.total_users * metrics.engagement_rate
                results["code_generations"] = {
                    "current": code_generations,
                    "target": success_criteria["min_code_generations"],
                    "met": code_generations >= success_criteria["min_code_generations"]
                }
            
            # Determine overall success
            overall_success = all(result["met"] for result in results.values())
            
            evaluations[experiment_id] = {
                "config": config,
                "metrics": metrics.__dict__,
                "results": results,
                "overall_success": overall_success,
                "recommendation": self._get_recommendation(overall_success, metrics)
            }
        
        return evaluations
    
    def _get_recommendation(self, success: bool, metrics: ExperimentMetrics) -> str:
        """Get recommendation for experiment based on performance"""
        
        if success and metrics.total_users > 100:
            return "PROMOTE - Graduate to main product"
        elif success and metrics.total_users > 20:
            return "SCALE - Increase promotion and resources"
        elif metrics.total_users > 50 and metrics.user_feedback_score > 3.5:
            return "ITERATE - Good engagement, needs improvement"
        elif metrics.total_users < 10 and (datetime.utcnow() - datetime.fromisoformat("2026-02-15")).days > 7:
            return "PAUSE - Low engagement after 1 week"
        else:
            return "MONITOR - Continue collecting data"
    
    async def _ensure_tracking_tables(self, conn: asyncpg.Connection) -> None:
        """Create experiment tracking tables if they don't exist"""
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS experiment_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                experiment_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                user_id TEXT,
                metadata JSONB,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_experiment_events_experiment_id 
            ON experiment_events(experiment_id)
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_experiment_events_timestamp 
            ON experiment_events(timestamp)
        """)
    
    def generate_experiment_report(self, evaluations: Dict[str, Dict[str, Any]]) -> str:
        """Generate human-readable experiment report"""
        
        report = f"""# 🧪 Experiment Status Report - {datetime.now().strftime('%B %d, %Y')}

Following Google's 20%-time approach, here are the current experimental features:

"""
        
        for exp_id, evaluation in evaluations.items():
            config = evaluation["config"]
            metrics = evaluation["metrics"]
            results = evaluation["results"]
            success = evaluation["overall_success"]
            recommendation = evaluation["recommendation"]
            
            status_emoji = "✅" if success else "⚠️"
            
            report += f"""## {status_emoji} {config['name']}

**Description:** {config['description']}
**Team:** {config['team']} • **Effort:** {config['effort_percentage']}% of team time
**Status:** {config['status'].value} • **Launch:** {config['launch_date']}

### 📊 Current Metrics:
- **Total Users:** {metrics['total_users']:,}
- **Daily Active:** {metrics['daily_active_users']:,}
- **Engagement Rate:** {metrics['engagement_rate']:.2f} actions/user
- **Retention Rate:** {metrics['retention_rate']:.1%}
- **Conversion Rate:** {metrics['conversion_rate']:.1%}
- **User Satisfaction:** {metrics['user_feedback_score']:.1f}/5.0

### 🎯 Success Criteria:
"""
            
            for criterion, result in results.items():
                check = "✅" if result["met"] else "❌"
                report += f"- {check} **{criterion.replace('_', ' ').title()}:** {result['current']:.2f} / {result['target']:.2f}\\n"
            
            report += f"""
### 💡 Recommendation: **{recommendation}**

---

"""
        
        # Summary
        total_experiments = len(evaluations)
        successful = sum(1 for e in evaluations.values() if e["overall_success"])
        
        report += f"""## 📈 Summary

- **Total Experiments:** {total_experiments}
- **Successful:** {successful} ({successful/total_experiments:.1%})
- **Ready for Promotion:** {sum(1 for e in evaluations.values() if "PROMOTE" in e["recommendation"])}
- **Need Iteration:** {sum(1 for e in evaluations.values() if "ITERATE" in e["recommendation"])}

### Next Actions:
1. **Promote successful experiments** to main product roadmap
2. **Scale experiments** with good traction
3. **Pause/Archive** experiments with low engagement
4. **Launch new experiments** to replace archived ones

*Following Google's approach: Quick MVPs → Measure traction → Promote winners → Archive losers*
"""
        
        return report


if __name__ == "__main__":
    async def generate_experiment_report():
        tracker = ExperimentTracker()
        
        print("🧪 Generating experiment evaluation report...")
        
        try:
            # Simulate some experiment events for demo
            await tracker.log_experiment_event("agent_battle", "view_battle", "user1")
            await tracker.log_experiment_event("agent_battle", "vote", "user1", {"choice": "agent1"})
            await tracker.log_experiment_event("discovery_dashboard", "session_start", "user2")
            await tracker.log_experiment_event("integration_generator", "code_generated", "user3", {"framework": "langchain"})
            
            # Evaluate all experiments
            evaluations = await tracker.evaluate_experiments()
            
            # Generate report
            report = tracker.generate_experiment_report(evaluations)
            
            with open("experiment_report.md", "w") as f:
                f.write(report)
            
            print("✅ Experiment report generated!")
            print("📄 Report saved to experiment_report.md")
            
            # Print summary
            total = len(evaluations)
            successful = sum(1 for e in evaluations.values() if e["overall_success"])
            print(f"📊 Summary: {successful}/{total} experiments meeting success criteria")
            
        except Exception as e:
            print(f"❌ Report generation failed: {e}")
    
    asyncio.run(generate_experiment_report())