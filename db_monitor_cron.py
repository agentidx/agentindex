#!/usr/bin/env python3
"""
Database Connection Monitoring Cron Job
Runs every 10 minutes to prevent "too many clients" errors
"""

from db_connection_manager import DatabaseConnectionManager
import sys
import subprocess

def main():
    manager = DatabaseConnectionManager()
    
    # Check current status
    alert = manager.monitor_and_alert()
    
    if alert["alert"]:
        print(f"🚨 DB CONNECTION ALERT: {alert['message']}")
        
        if alert["action_needed"] == "emergency_cleanup":
            print("Running emergency cleanup...")
            manager.emergency_connection_cleanup()
            
            # If still critical after cleanup, restart components
            post_cleanup = manager.monitor_and_alert()
            if post_cleanup["alert"] and post_cleanup["severity"] == "critical":
                print("🔴 CRITICAL: Restarting AgentIndex components...")
                
                # Restart dashboard processes to reset their connections
                subprocess.run(["pkill", "-f", "agentindex.dashboard"], check=False)
                subprocess.run(["sleep", "2"], check=False)
                
                # They should auto-restart via nohup or be restarted by system monitoring
        
        elif alert["action_needed"] == "cleanup_recommended":
            print("Running connection cleanup...")
            killed = manager.kill_old_idle_connections(10)
            print(f"Cleaned up {killed} old connections")
    
    else:
        stats = alert["stats"]
        if stats["usage_percent"] > 50:
            print(f"ℹ️ DB connection usage: {stats['usage_percent']}% - monitoring")

if __name__ == "__main__":
    main()