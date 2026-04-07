#!/usr/bin/env python3
"""
AgentIndex System Monitor - Upptäcker när komponenter går ner
Integrerat med budget tracking och Discord alerts
"""

import requests
import time
import json
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import sqlite3
import os

@dataclass
class EndpointCheck:
    name: str
    url: str
    expected_status: int = 200
    timeout: int = 10
    critical: bool = True

class SystemMonitor:
    def __init__(self):
        self.db_path = os.path.expanduser("~/agentindex/system_monitor.db")
        self.init_database()
        
        # Kritiska endpoints att övervaka
        self.endpoints = [
            EndpointCheck("Landing Page", "https://agentcrawl.dev", critical=True),
            EndpointCheck("External API", "https://api.agentcrawl.dev/v1/health", critical=True),
            EndpointCheck("Dashboard", "https://dash.agentcrawl.dev", critical=True),
            EndpointCheck("Local API", "http://localhost:8100/v1/health", critical=True),
            EndpointCheck("Local Dashboard", "http://localhost:8200/", critical=False),
            EndpointCheck("Budget Dashboard", "http://localhost:8203/", critical=False),
        ]
        
        # Process checks
        self.required_processes = [
            "agentindex.api.discovery",
            "agentindex.dashboard", 
            "agentindex.run",
            "run_parser_loop.py",
            "cloudflared"
        ]
    
    def init_database(self):
        """Initialize monitoring database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                endpoint_name VARCHAR(100),
                endpoint_url VARCHAR(500),
                status_code INTEGER,
                response_time REAL,
                error_message TEXT,
                is_healthy BOOLEAN
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                alert_type VARCHAR(50),
                component VARCHAR(100),
                message TEXT,
                severity VARCHAR(20),
                resolved BOOLEAN DEFAULT FALSE
            )
        """)
        
        conn.commit()
        conn.close()
    
    def check_endpoint(self, endpoint: EndpointCheck) -> Dict:
        """Check single endpoint health"""
        start_time = time.time()
        
        try:
            response = requests.get(
                endpoint.url, 
                timeout=endpoint.timeout,
                headers={'User-Agent': 'AgentIndex-Monitor/1.0'}
            )
            
            response_time = time.time() - start_time
            is_healthy = response.status_code == endpoint.expected_status
            
            result = {
                "name": endpoint.name,
                "url": endpoint.url,
                "status_code": response.status_code,
                "response_time": response_time,
                "is_healthy": is_healthy,
                "error": None,
                "critical": endpoint.critical
            }
            
            # Log to database
            self.log_check(result)
            
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            result = {
                "name": endpoint.name,
                "url": endpoint.url,
                "status_code": 0,
                "response_time": response_time,
                "is_healthy": False,
                "error": str(e),
                "critical": endpoint.critical
            }
            
            # Log error
            self.log_check(result)
            
            return result
    
    def check_processes(self) -> Dict:
        """Check required processes are running"""
        try:
            ps_output = subprocess.check_output(['ps', 'aux'], text=True)
            
            process_status = {}
            for process in self.required_processes:
                is_running = process in ps_output
                process_status[process] = {
                    "running": is_running,
                    "critical": True
                }
                
                if not is_running:
                    self.create_alert("process_down", process, f"Process {process} not running", "critical")
            
            return process_status
            
        except Exception as e:
            self.create_alert("monitoring_error", "process_check", f"Failed to check processes: {e}", "warning")
            return {}
    
    def log_check(self, result: Dict):
        """Log check result to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO system_checks 
            (endpoint_name, endpoint_url, status_code, response_time, error_message, is_healthy)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            result["name"],
            result["url"], 
            result["status_code"],
            result["response_time"],
            result.get("error"),
            result["is_healthy"]
        ))
        
        conn.commit()
        conn.close()
    
    def create_alert(self, alert_type: str, component: str, message: str, severity: str):
        """Create system alert"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO system_alerts (alert_type, component, message, severity)
            VALUES (?, ?, ?, ?)
        """, (alert_type, component, message, severity))
        
        conn.commit()
        conn.close()
    
    def run_full_check(self) -> Dict:
        """Run complete system health check"""
        print(f"🔍 System Health Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "endpoints": [],
            "processes": {},
            "critical_issues": [],
            "warnings": []
        }
        
        # Check all endpoints
        for endpoint in self.endpoints:
            result = self.check_endpoint(endpoint)
            results["endpoints"].append(result)
            
            print(f"{'🟢' if result['is_healthy'] else '🔴'} {result['name']}: "
                  f"HTTP {result['status_code']} ({result['response_time']:.3f}s)")
            
            if not result["is_healthy"] and endpoint.critical:
                issue = f"{result['name']} DOWN - {result.get('error', 'HTTP ' + str(result['status_code']))}"
                results["critical_issues"].append(issue)
                self.create_alert("endpoint_down", result['name'], issue, "critical")
        
        # Check processes
        results["processes"] = self.check_processes()
        
        print("\n📊 SUMMARY:")
        print(f"Endpoints healthy: {len([r for r in results['endpoints'] if r['is_healthy']])}/{len(results['endpoints'])}")
        print(f"Critical issues: {len(results['critical_issues'])}")
        print(f"Processes running: {len([p for p in results['processes'].values() if p['running']])}/{len(self.required_processes)}")
        
        if results["critical_issues"]:
            print("\n🚨 CRITICAL ISSUES:")
            for issue in results["critical_issues"]:
                print(f"  - {issue}")
        
        return results
    
    def get_health_summary(self, hours_back: int = 24) -> Dict:
        """Get health summary for dashboard"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = datetime.now() - timedelta(hours=hours_back)
        
        cursor.execute("""
            SELECT 
                endpoint_name,
                COUNT(*) as total_checks,
                SUM(CASE WHEN is_healthy THEN 1 ELSE 0 END) as healthy_checks,
                AVG(response_time) as avg_response_time,
                MAX(response_time) as max_response_time
            FROM system_checks 
            WHERE timestamp >= ?
            GROUP BY endpoint_name
        """, (since,))
        
        results = cursor.fetchall()
        conn.close()
        
        summary = {}
        for row in results:
            name, total, healthy, avg_time, max_time = row
            uptime = (healthy / total * 100) if total > 0 else 0
            summary[name] = {
                "uptime_percent": round(uptime, 2),
                "avg_response_time": round(avg_time, 3),
                "max_response_time": round(max_time, 3),
                "total_checks": total
            }
        
        return summary

if __name__ == "__main__":
    monitor = SystemMonitor()
    results = monitor.run_full_check()
    
    # Save results for other systems to read
    with open("system_health_status.json", "w") as f:
        json.dump(results, f, indent=2)