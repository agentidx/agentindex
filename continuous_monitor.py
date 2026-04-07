#!/usr/bin/env python3
"""
Continuous System Monitor - Runs every 5 minutes
Discovers issues and sends Discord alerts automatically
"""

from system_monitor import SystemMonitor
import time
import json
import requests
from datetime import datetime

class ContinuousMonitor:
    def __init__(self):
        self.monitor = SystemMonitor()
        self.discord_webhook = None  # Set if we want Discord alerts
        
    def send_discord_alert(self, message: str):
        """Send alert to Discord if configured"""
        if self.discord_webhook:
            try:
                requests.post(self.discord_webhook, json={"content": message})
            except:
                pass
    
    def run_monitoring_cycle(self):
        """Run one monitoring cycle"""
        results = self.monitor.run_full_check()
        
        # Check for critical issues
        if results["critical_issues"]:
            alert_msg = f"🚨 **SYSTEM ALERT** - {datetime.now().strftime('%H:%M')}\n"
            for issue in results["critical_issues"]:
                alert_msg += f"• {issue}\n"
            
            print(alert_msg)
            self.send_discord_alert(alert_msg)
            
            # Save alert status
            with open("system_alerts.json", "w") as f:
                json.dump({
                    "timestamp": results["timestamp"],
                    "critical_issues": results["critical_issues"],
                    "alert_sent": True
                }, f)
        else:
            print(f"✅ All systems healthy - {datetime.now().strftime('%H:%M:%S')}")
    
    def run_continuous(self, interval_minutes: int = 5):
        """Run continuous monitoring"""
        print(f"🔄 Starting continuous monitoring (every {interval_minutes} minutes)")
        
        while True:
            try:
                self.run_monitoring_cycle()
                time.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                print("\n🛑 Monitoring stopped by user")
                break
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                time.sleep(60)  # Wait 1 minute before retry

if __name__ == "__main__":
    monitor = ContinuousMonitor()
    monitor.run_continuous(5)  # Every 5 minutes