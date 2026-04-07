#!/usr/bin/env python3
"""
Autonomous Marketing Monitoring Loop
Tracks Phase 1 results and prepares for Phase 2 expansion
"""

import time
import requests
from datetime import datetime, timedelta
import json
import subprocess

class AutonomousMonitoring:
    def __init__(self):
        self.monitoring_active = True
        self.last_report_time = datetime.now()
        
    def check_website_traffic(self):
        """Check if agentcrawl.dev is getting traffic"""
        try:
            # Check website response time as proxy for traffic
            start = time.time()
            response = requests.get("https://agentcrawl.dev", timeout=10)
            response_time = time.time() - start
            
            return {
                "status": "online" if response.status_code == 200 else "issues",
                "response_time": response_time,
                "status_code": response.status_code
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def check_api_usage(self):
        """Check API endpoint for new usage"""
        try:
            response = requests.get("https://api.agentcrawl.dev/v1/health", timeout=5)
            return {
                "api_status": "healthy" if response.status_code == 200 else "issues",
                "response_time": response.elapsed.total_seconds()
            }
        except Exception as e:
            return {"api_status": "error", "error": str(e)}
    
    def check_system_health(self):
        """Check overall AgentIndex system health"""
        try:
            # Check database connections  
            result = subprocess.run([
                "python3", "-c", 
                "from db_connection_manager import DatabaseConnectionManager; "
                "m = DatabaseConnectionManager(); "
                "s = m.get_connection_stats(); "
                "print(f'{s[\"total_connections\"]}/{s[\"max_connections\"]}' if s else 'error')"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                conn_info = result.stdout.strip()
                return {"database": "healthy", "connections": conn_info}
            else:
                return {"database": "error", "error": result.stderr}
                
        except Exception as e:
            return {"database": "error", "error": str(e)}
    
    def generate_status_update(self):
        """Generate proactive status update"""
        
        website_check = self.check_website_traffic()
        api_check = self.check_api_usage() 
        system_check = self.check_system_health()
        
        # Calculate time since last Phase 1 execution
        hours_since_launch = (datetime.now() - self.last_report_time).total_seconds() / 3600
        
        status_report = {
            "timestamp": datetime.now().isoformat(),
            "hours_since_phase1": round(hours_since_launch, 1),
            "system_status": {
                "website": website_check,
                "api": api_check,
                "database": system_check
            },
            "phase1_monitoring": {
                "registry_submissions": "pending_results",
                "reddit_post_reach": "monitoring",
                "github_updates": "active"
            },
            "next_actions": []
        }
        
        # Determine next proactive actions
        if hours_since_launch > 24:
            status_report["next_actions"].append("Phase 1 results evaluation ready")
            status_report["next_actions"].append("Phase 2 Twitter content prepared")
            
        if hours_since_launch > 8:
            status_report["next_actions"].append("Monitor registry submission approvals")
            status_report["next_actions"].append("Check Reddit post engagement")
            
        return status_report
    
    def should_escalate_to_anders(self, status_report):
        """Determine if status needs Anders' attention"""
        
        escalation_needed = False
        reasons = []
        
        # System issues
        if status_report["system_status"]["website"]["status"] != "online":
            escalation_needed = True
            reasons.append("Website accessibility issues")
            
        if status_report["system_status"]["database"].get("database") == "error":
            escalation_needed = True
            reasons.append("Database connection problems")
        
        # Timeline milestones
        hours = status_report["hours_since_phase1"]
        if hours > 72:  # 3 days
            escalation_needed = True
            reasons.append("Phase 1 evaluation period complete - results ready")
            
        return escalation_needed, reasons

def main():
    print("🔄 AUTONOMOUS MONITORING - PROACTIVE STATUS CHECK")
    print("=" * 60)
    
    monitor = AutonomousMonitoring()
    status = monitor.generate_status_update()
    
    print(f"⏰ Time since Phase 1: {status['hours_since_phase1']} hours")
    print(f"🌐 Website: {status['system_status']['website']['status']}")
    print(f"🔗 API: {status['system_status']['api']['api_status']}")
    print(f"💾 Database: {status['system_status']['database'].get('database', 'unknown')}")
    
    if status["next_actions"]:
        print(f"\n📋 Proactive Actions Ready:")
        for action in status["next_actions"]:
            print(f"  • {action}")
    
    # Check if escalation needed
    escalate, reasons = monitor.should_escalate_to_anders(status)
    
    if escalate:
        print(f"\n🔔 ESCALATION TO ANDERS RECOMMENDED:")
        for reason in reasons:
            print(f"  ⚠️ {reason}")
    else:
        print(f"\n✅ All systems running smoothly - continuing autonomous monitoring")
    
    # Save status
    with open("autonomous_monitoring_status.json", "w") as f:
        json.dump(status, f, indent=2)
    
    print(f"\n💾 Status saved: autonomous_monitoring_status.json")
    
    return status, escalate, reasons

if __name__ == "__main__":
    status, escalate, reasons = main()
    
    if escalate:
        print(f"\n🚨 Escalation triggered - reporting to Anders")
    else:
        print(f"\n🔄 Continuing autonomous operations")