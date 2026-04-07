"""
AgentIndex Cost Tracking System
Tracks Anthropic Claude API costs and optimizes budget usage
Budget: $10 USD per 24h period
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from typing import Dict, List, Optional

class CostTracker:
    def __init__(self, db_path: str = "~/agentindex/cost_tracking.db"):
        self.db_path = os.path.expanduser(db_path)
        self.daily_budget = 10.0  # $10 USD
        self.init_database()
    
    def init_database(self):
        """Initialize cost tracking database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                model VARCHAR(50),
                input_tokens INTEGER,
                output_tokens INTEGER,
                cost_usd REAL,
                task_type VARCHAR(100),
                session_id VARCHAR(100),
                notes TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS budget_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                budget_used REAL,
                alert_level VARCHAR(20),
                message TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def log_api_call(self, model: str, input_tokens: int, output_tokens: int, 
                    cost_usd: float, task_type: str = "unknown", 
                    session_id: str = "main", notes: str = ""):
        """Log an API call with cost"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO api_costs 
            (model, input_tokens, output_tokens, cost_usd, task_type, session_id, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (model, input_tokens, output_tokens, cost_usd, task_type, session_id, notes))
        
        conn.commit()
        conn.close()
        
        # Check budget and alert if needed
        self.check_budget_status()
    
    def get_daily_costs(self, date: Optional[datetime] = None) -> Dict:
        """Get costs for specific day"""
        if date is None:
            date = datetime.now()
        
        start_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_calls,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(cost_usd) as total_cost,
                AVG(cost_usd) as avg_cost_per_call
            FROM api_costs 
            WHERE timestamp >= ? AND timestamp < ?
        """, (start_date, end_date))
        
        result = cursor.fetchone()
        
        # Get breakdown by task type
        cursor.execute("""
            SELECT task_type, COUNT(*), SUM(cost_usd)
            FROM api_costs 
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY task_type
            ORDER BY SUM(cost_usd) DESC
        """, (start_date, end_date))
        
        task_breakdown = cursor.fetchall()
        
        conn.close()
        
        return {
            "date": date.strftime("%Y-%m-%d"),
            "total_calls": result[0] or 0,
            "total_input_tokens": result[1] or 0,
            "total_output_tokens": result[2] or 0,
            "total_cost_usd": round(result[3] or 0, 4),
            "avg_cost_per_call": round(result[4] or 0, 4),
            "budget_used_percent": round(((result[3] or 0) / self.daily_budget) * 100, 1),
            "budget_remaining": round(self.daily_budget - (result[3] or 0), 2),
            "task_breakdown": [(task, calls, round(cost, 4)) for task, calls, cost in task_breakdown]
        }
    
    def get_hourly_usage(self, hours_back: int = 24) -> List[Dict]:
        """Get hourly usage for last N hours"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours_back)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                strftime('%Y-%m-%d %H:00', timestamp) as hour,
                COUNT(*) as calls,
                SUM(cost_usd) as cost
            FROM api_costs 
            WHERE timestamp >= ?
            GROUP BY strftime('%Y-%m-%d %H:00', timestamp)
            ORDER BY hour DESC
            LIMIT ?
        """, (start_time, hours_back))
        
        results = cursor.fetchall()
        conn.close()
        
        return [{"hour": hour, "calls": calls, "cost": round(cost, 4)} 
                for hour, calls, cost in results]
    
    def check_budget_status(self) -> Dict:
        """Check current budget status and create alerts if needed"""
        daily_stats = self.get_daily_costs()
        budget_used_percent = daily_stats["budget_used_percent"]
        
        alert_level = None
        message = None
        
        if budget_used_percent >= 90:
            alert_level = "critical"
            message = f"CRITICAL: {budget_used_percent}% of daily budget used (${daily_stats['total_cost_usd']:.2f}/${self.daily_budget})"
        elif budget_used_percent >= 70:
            alert_level = "warning"  
            message = f"WARNING: {budget_used_percent}% of daily budget used (${daily_stats['total_cost_usd']:.2f}/${self.daily_budget})"
        elif budget_used_percent >= 50:
            alert_level = "info"
            message = f"INFO: {budget_used_percent}% of daily budget used (${daily_stats['total_cost_usd']:.2f}/${self.daily_budget})"
        
        if alert_level:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO budget_alerts (budget_used, alert_level, message)
                VALUES (?, ?, ?)
            """, (daily_stats['total_cost_usd'], alert_level, message))
            conn.commit()
            conn.close()
        
        return {
            "status": alert_level or "ok",
            "message": message or f"Budget OK: {budget_used_percent}% used",
            "daily_stats": daily_stats
        }
    
    def get_optimization_suggestions(self) -> List[str]:
        """Get suggestions for cost optimization based on usage patterns"""
        daily_stats = self.get_daily_costs()
        suggestions = []
        
        if daily_stats["budget_used_percent"] > 80:
            suggestions.extend([
                "🚨 URGENT: Switch to local LLM for non-critical tasks",
                "📝 Implement prompt compression techniques",
                "⚡ Use batching for similar requests",
                "🎯 Cache common responses"
            ])
        elif daily_stats["budget_used_percent"] > 60:
            suggestions.extend([
                "💡 Consider using local LLM for code generation",
                "📊 Batch data processing requests",
                "🔍 Use smaller context windows where possible"
            ])
        else:
            suggestions.extend([
                "✅ Budget usage is healthy",
                "🔄 Continue current optimization strategies",
                "📈 Room for more aggressive development"
            ])
        
        # Add task-specific suggestions
        task_breakdown = daily_stats.get("task_breakdown", [])
        if task_breakdown:
            highest_cost_task = task_breakdown[0]
            suggestions.append(f"🎯 Highest cost task: {highest_cost_task[0]} (${highest_cost_task[2]:.2f})")
        
        return suggestions

# Anthropic Claude pricing (approximate)
CLAUDE_PRICING = {
    "claude-3-5-sonnet-20241022": {
        "input": 0.000003,   # $3 per 1M input tokens
        "output": 0.000015   # $15 per 1M output tokens
    },
    "claude-3-5-haiku-20241022": {
        "input": 0.000001,   # $1 per 1M input tokens  
        "output": 0.000005   # $5 per 1M output tokens
    }
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for an API call"""
    if model not in CLAUDE_PRICING:
        # Default to Sonnet pricing
        model = "claude-3-5-sonnet-20241022"
    
    pricing = CLAUDE_PRICING[model]
    cost = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])
    return round(cost, 6)

if __name__ == "__main__":
    # Test the cost tracker
    tracker = CostTracker()
    
    # Simulate some API calls
    tracker.log_api_call("claude-3-5-sonnet-20241022", 1000, 500, 0.0105, "development", "main", "Test call")
    
    # Get daily stats
    stats = tracker.get_daily_costs()
    print(f"Daily cost: ${stats['total_cost_usd']:.4f}")
    print(f"Budget used: {stats['budget_used_percent']}%")
    
    # Get suggestions
    suggestions = tracker.get_optimization_suggestions()
    for suggestion in suggestions:
        print(suggestion)