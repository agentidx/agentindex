#!/usr/bin/env python3
"""
Human vs AI Cost Comparison System
Tracks real AgentIndex costs vs estimated human equivalent costs
Based on Anders' analysis: AI is 3,200x cheaper for development, 1,000x cheaper for operations
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from cost_tracker import CostTracker
import os

class HumanVsAICostTracker:
    def __init__(self):
        self.db_path = os.path.expanduser("~/agentindex/human_vs_ai_costs.db")
        self.cost_tracker = CostTracker()
        self.init_database()
        
        # From Anders' corrected analysis - human equivalent costs
        self.human_cost_estimates = {
            # Development tasks ($/hour rates for equivalent human work)
            "code_generation": 120,  # Senior developer
            "documentation": 80,     # Technical writer
            "data_processing": 100,  # Data engineer
            "system_monitoring": 130, # DevOps engineer
            "strategic_planning": 200, # Product manager/strategist
            "marketing_content": 100, # Marketing specialist
            "classification": 100,    # Data engineer
            "api_development": 120,   # Senior backend developer
            "infrastructure": 130,    # DevOps/Platform engineer
            "competitive_analysis": 150, # Business analyst
            "community_outreach": 90,  # Developer relations
            "distribution": 90,       # Marketing coordinator
            
            # Time estimates (corrected from Anders' analysis)
            "human_time_multiplier": 19.0,  # Humans take 19x longer (8 days vs 150 days)
            
            # Baseline hourly rates
            "senior_developer": 120,
            "data_engineer": 100, 
            "devops_engineer": 130,
            "product_manager": 200,
            "marketing_specialist": 90
        }
        
        # Project phases from Anders' corrected analysis  
        self.project_phases = {
            "development_phase": {
                "start_date": "2026-02-07",
                "end_date": "2026-02-15", 
                "ai_total_cost": 140,  # From corrected analysis
                "human_equivalent": 450000,  # From corrected analysis
                "calendar_days": 8,  # Corrected: 8 days, not 15
                "ai_work_hours": 40,  # ~32-48 hours, average 40
                "human_work_hours": 840  # 7 people × 5 months × 24 hours/month average
            },
            "operation_phase": {
                "start_date": "2026-02-15",  # When Buzz took over
                "ai_monthly_cost": 55,  # Average $50-60
                "human_monthly_cost": 50000  # Average $40k-60k
            }
        }
    
    def init_database(self):
        """Initialize cost comparison database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_cost_comparison (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                ai_cost_usd REAL,
                human_equivalent_cost_usd REAL,
                tasks_completed INTEGER,
                ai_time_hours REAL,
                human_equivalent_time_hours REAL,
                cost_ratio REAL,
                time_ratio REAL,
                primary_tasks TEXT,
                notes TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_cost_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                task_description TEXT,
                task_type VARCHAR(50),
                ai_cost_usd REAL,
                ai_time_hours REAL,
                human_equivalent_cost_usd REAL,
                human_equivalent_time_hours REAL,
                complexity_factor REAL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def estimate_human_cost_for_task(self, task_type: str, ai_cost: float, ai_time_hours: float) -> Tuple[float, float]:
        """Estimate what humans would cost for equivalent task"""
        
        # Get base hourly rate for task type
        hourly_rate = self.human_cost_estimates.get(task_type, 120)  # Default to senior dev
        
        # Humans typically take 4x longer than AI for same task
        human_time = ai_time_hours * self.human_cost_estimates["human_time_multiplier"]
        
        # Calculate human cost
        human_cost = human_time * hourly_rate
        
        # Add overhead (benefits, management, office, etc.) - typically 1.5x
        human_cost_with_overhead = human_cost * 1.5
        
        return human_cost_with_overhead, human_time
    
    def log_daily_comparison(self, date: str = None):
        """Calculate and log daily AI vs Human cost comparison"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        # Get AI costs for the day
        target_date = datetime.strptime(date, '%Y-%m-%d')
        daily_ai_costs = self.cost_tracker.get_daily_costs(target_date)
        
        ai_cost = daily_ai_costs['total_cost_usd']
        ai_calls = daily_ai_costs['total_calls']
        
        # Estimate task completion time (rough estimate)
        ai_time_hours = ai_calls * 0.02  # ~1.2 minutes per API call on average
        
        # Calculate human equivalent
        # Use weighted average based on task breakdown
        weighted_human_cost = 0
        weighted_human_time = 0
        
        for task, calls, cost in daily_ai_costs['task_breakdown']:
            task_human_cost, task_human_time = self.estimate_human_cost_for_task(
                task, cost, calls * 0.02
            )
            weighted_human_cost += task_human_cost
            weighted_human_time += task_human_time
        
        # If no task breakdown, use default estimation
        if weighted_human_cost == 0:
            weighted_human_cost, weighted_human_time = self.estimate_human_cost_for_task(
                "code_generation", ai_cost, ai_time_hours
            )
        
        # Calculate ratios
        cost_ratio = weighted_human_cost / max(ai_cost, 0.0001)  # Avoid division by zero
        time_ratio = weighted_human_time / max(ai_time_hours, 0.01)
        
        # Save to database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO daily_cost_comparison 
            (date, ai_cost_usd, human_equivalent_cost_usd, tasks_completed, 
             ai_time_hours, human_equivalent_time_hours, cost_ratio, time_ratio, primary_tasks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date, ai_cost, weighted_human_cost, ai_calls,
            ai_time_hours, weighted_human_time, cost_ratio, time_ratio,
            json.dumps(daily_ai_costs['task_breakdown'])
        ))
        
        conn.commit()
        conn.close()
        
        return {
            "date": date,
            "ai_cost": ai_cost,
            "human_equivalent_cost": weighted_human_cost,
            "cost_ratio": cost_ratio,
            "time_ratio": time_ratio,
            "ai_time_hours": ai_time_hours,
            "human_time_hours": weighted_human_time,
            "tasks_completed": ai_calls
        }
    
    def generate_comparison_report(self, period: str = "all") -> Dict:
        """Generate comprehensive AI vs Human comparison report"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if period == "today":
            date_filter = "date = ?"
            params = (datetime.now().strftime('%Y-%m-%d'),)
        elif period == "since_takeover":
            date_filter = "date >= ?"
            params = ('2026-02-15',)  # When Buzz took over
        elif period == "all":
            date_filter = "date >= ?"
            params = ('2026-02-07',)  # Project start
        else:
            date_filter = "1=1"
            params = ()
        
        cursor.execute(f"""
            SELECT 
                COUNT(*) as days,
                SUM(ai_cost_usd) as total_ai_cost,
                SUM(human_equivalent_cost_usd) as total_human_cost,
                SUM(tasks_completed) as total_tasks,
                SUM(ai_time_hours) as total_ai_time,
                SUM(human_equivalent_time_hours) as total_human_time,
                AVG(cost_ratio) as avg_cost_ratio,
                AVG(time_ratio) as avg_time_ratio
            FROM daily_cost_comparison 
            WHERE {date_filter}
        """, params)
        
        result = cursor.fetchone()
        
        if result and result[0] > 0:
            days, total_ai_cost, total_human_cost, total_tasks, total_ai_time, total_human_time, avg_cost_ratio, avg_time_ratio = result
            
            report = {
                "period": period,
                "days_analyzed": days,
                "ai_costs": {
                    "total_usd": round(total_ai_cost, 2),
                    "average_per_day": round(total_ai_cost / days, 2),
                    "total_hours": round(total_ai_time, 2)
                },
                "human_equivalent": {
                    "total_usd": round(total_human_cost, 2),
                    "average_per_day": round(total_human_cost / days, 2),
                    "total_hours": round(total_human_time, 2)
                },
                "savings": {
                    "cost_savings_usd": round(total_human_cost - total_ai_cost, 2),
                    "cost_ratio": round(total_human_cost / max(total_ai_cost, 0.01), 1),
                    "time_savings_hours": round(total_human_time - total_ai_time, 2),
                    "time_ratio": round(total_human_time / max(total_ai_time, 0.01), 1)
                },
                "productivity": {
                    "total_tasks": int(total_tasks),
                    "tasks_per_day": round(total_tasks / days, 1),
                    "cost_per_task_ai": round(total_ai_cost / max(total_tasks, 1), 4),
                    "cost_per_task_human": round(total_human_cost / max(total_tasks, 1), 2)
                }
            }
        else:
            # Use historical data from Anders' corrected analysis for development phase
            if period == "all":
                report = {
                    "period": "all",
                    "includes_development_phase": True,
                    "development_phase": {
                        "ai_cost": 140,
                        "human_equivalent": 450000,
                        "cost_ratio": 3214,  # 450000/140 (unchanged)
                        "time_ratio": 19     # 150 days / 8 days (corrected)
                    },
                    "note": "Development phase from Anders' corrected analysis, operation phase from tracking"
                }
            else:
                report = {"error": "No data available for specified period"}
        
        conn.close()
        return report
    
    def print_comparison_summary(self):
        """Print formatted comparison summary"""
        today = self.generate_comparison_report("today")
        since_takeover = self.generate_comparison_report("since_takeover") 
        all_time = self.generate_comparison_report("all")
        
        print("🤖 vs 👥 HUMAN VS AI COST COMPARISON")
        print("=" * 60)
        
        print(f"\n📅 TODAY ({datetime.now().strftime('%Y-%m-%d')}):")
        if "error" not in today:
            print(f"AI Cost: ${today['ai_costs']['total_usd']}")
            print(f"Human Equivalent: ${today['human_equivalent']['total_usd']:,.2f}")
            print(f"💰 Cost Ratio: {today['savings']['cost_ratio']:.1f}x cheaper with AI")
            print(f"⚡ Time Ratio: {today['savings']['time_ratio']:.1f}x faster with AI")
        else:
            print("No activity today yet")
        
        print(f"\n🚀 SINCE BUZZ TAKEOVER (Feb 15):")
        if "error" not in since_takeover:
            print(f"AI Cost: ${since_takeover['ai_costs']['total_usd']}")
            print(f"Human Equivalent: ${since_takeover['human_equivalent']['total_usd']:,.2f}")
            print(f"💰 Savings: ${since_takeover['savings']['cost_savings_usd']:,.2f}")
            print(f"📊 Cost Ratio: {since_takeover['savings']['cost_ratio']:.1f}x cheaper")
            print(f"⚡ Time Ratio: {since_takeover['savings']['time_ratio']:.1f}x faster")
        else:
            print("Building comparison data...")
        
        print(f"\n🏆 PROJECT TOTAL (Feb 7 - Present):")
        print("Development Phase (Feb 7-15, Anders + Claude):")
        print("  AI Cost: $140")
        print("  Human Equivalent: $450,000")
        print("  💰 Ratio: 3,214x cheaper with AI")
        print("  ⚡ Time: 19x faster (8 days vs 150 days)")
        
        if "error" not in since_takeover:
            total_ai = 140 + since_takeover['ai_costs']['total_usd']
            total_human = 450000 + since_takeover['human_equivalent']['total_usd']
            print(f"\nOperation Phase (Feb 15 - Present, Buzz):")
            print(f"  AI Cost: ${since_takeover['ai_costs']['total_usd']}")
            print(f"  Human Equivalent: ${since_takeover['human_equivalent']['total_usd']:,.2f}")
            
            print(f"\n🎯 TOTAL PROJECT COMPARISON:")
            print(f"AI Total: ${total_ai:.2f}")
            print(f"Human Total: ${total_human:,.2f}")
            print(f"💰 OVERALL RATIO: {total_human/total_ai:,.0f}x CHEAPER WITH AI")
            print(f"💾 Total savings: ${total_human - total_ai:,.2f}")

if __name__ == "__main__":
    tracker = HumanVsAICostTracker()
    
    # Log today's comparison
    today_result = tracker.log_daily_comparison()
    
    # Print summary
    tracker.print_comparison_summary()