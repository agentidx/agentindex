#!/usr/bin/env python3
"""
Database Connection Manager - Prevents PostgreSQL "too many clients" errors
Monitors and manages database connections across all AgentIndex components
"""

import psycopg2
from psycopg2 import sql
import subprocess
import time
from datetime import datetime
import os

class DatabaseConnectionManager:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'agentindex',
            'user': 'anstudio'
        }
    
    def get_connection_stats(self):
        """Get current PostgreSQL connection statistics"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Get max connections setting
            cursor.execute("SHOW max_connections")
            max_connections = cursor.fetchone()[0]
            
            # Get current connections by state
            cursor.execute("""
                SELECT 
                    state,
                    COUNT(*) as count,
                    MIN(state_change) as oldest_state_change
                FROM pg_stat_activity 
                WHERE datname = 'agentindex'
                GROUP BY state
            """)
            
            connections_by_state = cursor.fetchall()
            
            # Get idle connections older than 10 minutes
            cursor.execute("""
                SELECT COUNT(*) FROM pg_stat_activity 
                WHERE datname = 'agentindex' 
                AND state = 'idle' 
                AND state_change < NOW() - INTERVAL '10 minutes'
            """)
            
            old_idle_connections = cursor.fetchone()[0]
            
            # Get total active connections
            cursor.execute("""
                SELECT COUNT(*) FROM pg_stat_activity 
                WHERE datname = 'agentindex'
            """)
            
            total_connections = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return {
                "max_connections": int(max_connections),
                "total_connections": total_connections,
                "connections_by_state": connections_by_state,
                "old_idle_connections": old_idle_connections,
                "usage_percent": round((total_connections / int(max_connections)) * 100, 1)
            }
            
        except Exception as e:
            print(f"Error getting connection stats: {e}")
            return None
    
    def kill_old_idle_connections(self, minutes_old: int = 15):
        """Kill idle connections older than specified minutes"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Get PIDs of old idle connections (excluding our own)
            cursor.execute("""
                SELECT pid, application_name, state_change
                FROM pg_stat_activity 
                WHERE datname = 'agentindex'
                AND state = 'idle'
                AND state_change < NOW() - INTERVAL '%s minutes'
                AND pid != pg_backend_pid()
            """, (minutes_old,))
            
            old_connections = cursor.fetchall()
            
            killed_count = 0
            for pid, app_name, state_change in old_connections:
                try:
                    cursor.execute("SELECT pg_terminate_backend(%s)", (pid,))
                    killed_count += 1
                    print(f"Killed idle connection PID {pid} (app: {app_name}, idle since: {state_change})")
                except Exception as e:
                    print(f"Failed to kill PID {pid}: {e}")
            
            cursor.close()
            conn.close()
            
            return killed_count
            
        except Exception as e:
            print(f"Error killing idle connections: {e}")
            return 0
    
    def optimize_postgresql_settings(self):
        """Suggest PostgreSQL configuration optimizations"""
        stats = self.get_connection_stats()
        if not stats:
            return
        
        recommendations = []
        
        if stats["usage_percent"] > 80:
            recommendations.append("🔴 Connection usage over 80% - consider increasing max_connections")
            recommendations.append("💡 Add connection pooling with PgBouncer or similar")
        
        if stats["old_idle_connections"] > 10:
            recommendations.append(f"⚠️ {stats['old_idle_connections']} old idle connections found")
            recommendations.append("💡 Consider shorter idle_in_transaction_session_timeout")
        
        recommendations.append("💡 Ensure all SQLAlchemy sessions use 'with' statements or explicit close()")
        recommendations.append("💡 Configure connection pool size in applications")
        
        return {
            "stats": stats,
            "recommendations": recommendations
        }
    
    def emergency_connection_cleanup(self):
        """Emergency cleanup when approaching connection limits"""
        print("🚨 EMERGENCY CONNECTION CLEANUP")
        print("=" * 50)
        
        stats = self.get_connection_stats()
        if not stats:
            print("❌ Could not get connection stats")
            return
        
        print(f"Current connections: {stats['total_connections']}/{stats['max_connections']} ({stats['usage_percent']}%)")
        
        if stats["usage_percent"] > 90:
            print("🔴 CRITICAL: Over 90% connection usage")
            killed = self.kill_old_idle_connections(5)  # Kill connections idle > 5 minutes
            print(f"✅ Killed {killed} old idle connections")
        elif stats["usage_percent"] > 80:
            print("⚠️ WARNING: Over 80% connection usage")  
            killed = self.kill_old_idle_connections(15)  # Kill connections idle > 15 minutes
            print(f"✅ Killed {killed} old idle connections")
        
        # Check again after cleanup
        new_stats = self.get_connection_stats()
        if new_stats:
            print(f"After cleanup: {new_stats['total_connections']}/{new_stats['max_connections']} ({new_stats['usage_percent']}%)")
    
    def monitor_and_alert(self):
        """Continuous monitoring with alerts"""
        stats = self.get_connection_stats()
        if not stats:
            return
        
        if stats["usage_percent"] > 85:
            return {
                "alert": True,
                "severity": "critical" if stats["usage_percent"] > 95 else "warning",
                "message": f"PostgreSQL connection usage at {stats['usage_percent']}% ({stats['total_connections']}/{stats['max_connections']})",
                "action_needed": "emergency_cleanup" if stats["usage_percent"] > 95 else "cleanup_recommended"
            }
        
        return {
            "alert": False,
            "stats": stats
        }

def main():
    manager = DatabaseConnectionManager()
    
    print("📊 DATABASE CONNECTION STATUS")
    print("=" * 50)
    
    # Get current stats
    optimization = manager.optimize_postgresql_settings()
    if optimization:
        stats = optimization["stats"]
        print(f"Max connections: {stats['max_connections']}")
        print(f"Current connections: {stats['total_connections']} ({stats['usage_percent']}%)")
        print(f"Old idle connections: {stats['old_idle_connections']}")
        
        print("\nConnections by state:")
        for state, count, oldest in stats["connections_by_state"]:
            print(f"  {state}: {count}")
        
        print("\n💡 RECOMMENDATIONS:")
        for rec in optimization["recommendations"]:
            print(f"  {rec}")
        
        # Emergency cleanup if needed
        if stats["usage_percent"] > 85:
            print("\n🚨 RUNNING EMERGENCY CLEANUP...")
            manager.emergency_connection_cleanup()

if __name__ == "__main__":
    main()