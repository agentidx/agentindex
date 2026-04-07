#!/usr/bin/env python3
"""
PostgreSQL Connection Monitor
Övervakar databasanslutningar och warnar om läckor
"""

import psycopg2
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [pg-monitor] %(message)s")
logger = logging.getLogger("pg_monitor")

class PostgreSQLConnectionMonitor:
    def __init__(self):
        self.max_connections_warning = 30
        self.max_connections_critical = 50
        self.idle_transaction_warning = 5  # minutes
        
    def get_connection_stats(self):
        """Get current connection statistics."""
        conn = psycopg2.connect('postgresql://localhost/agentindex')
        cursor = conn.cursor()
        
        # Count by state
        cursor.execute("""
            SELECT state, COUNT(*) as count 
            FROM pg_stat_activity 
            WHERE datname = 'agentindex' 
            GROUP BY state
        """)
        stats = dict(cursor.fetchall())
        
        # Count idle in transaction > 5 minutes
        cursor.execute("""
            SELECT COUNT(*) 
            FROM pg_stat_activity 
            WHERE datname = 'agentindex' 
            AND state = 'idle in transaction' 
            AND NOW() - state_change > interval '5 minutes'
        """)
        old_idle_tx = cursor.fetchone()[0]
        
        # Total connections
        total = sum(stats.values())
        
        cursor.close()
        conn.close()
        
        return {
            'total': total,
            'by_state': stats,
            'old_idle_transactions': old_idle_tx,
            'timestamp': datetime.now()
        }
    
    def check_and_alert(self):
        """Check connection status and log alerts."""
        stats = self.get_connection_stats()
        total = stats['total']
        old_idle_tx = stats['old_idle_transactions']
        
        # Total connections check
        if total >= self.max_connections_critical:
            logger.critical(f"🚨 CRITICAL: {total} connections (max: {self.max_connections_critical})")
        elif total >= self.max_connections_warning:
            logger.warning(f"⚠️  WARNING: {total} connections (target: <{self.max_connections_warning})")
        else:
            logger.info(f"✅ OK: {total} connections")
        
        # Idle in transaction check  
        if old_idle_tx > 0:
            logger.warning(f"⚠️  {old_idle_tx} long-running idle transactions detected")
        
        # State breakdown
        states = stats['by_state']
        logger.info(f"📊 States: idle={states.get('idle', 0)}, active={states.get('active', 0)}, idle_tx={states.get('idle in transaction', 0)}")
        
        return stats
    
    def cleanup_old_connections(self):
        """Clean up old idle connections."""
        conn = psycopg2.connect('postgresql://localhost/agentindex')
        cursor = conn.cursor()
        
        # Kill idle in transaction > 10 minutes
        cursor.execute("""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = 'agentindex' 
            AND state = 'idle in transaction' 
            AND NOW() - state_change > interval '10 minutes'
        """)
        killed_tx = len(cursor.fetchall())
        
        # Kill idle > 30 minutes
        cursor.execute("""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = 'agentindex' 
            AND state = 'idle' 
            AND NOW() - state_change > interval '30 minutes'
        """)
        killed_idle = len(cursor.fetchall())
        
        if killed_tx + killed_idle > 0:
            logger.info(f"🧹 Cleaned up {killed_tx} idle_tx + {killed_idle} idle connections")
        
        cursor.close()
        conn.close()
        
        return killed_tx + killed_idle

if __name__ == "__main__":
    monitor = PostgreSQLConnectionMonitor()
    
    logger.info("🔍 Starting PostgreSQL connection monitoring")
    
    # Run once for immediate check
    stats = monitor.check_and_alert()
    cleanup_count = monitor.cleanup_old_connections()
    
    print(f"\n📊 Current Status:")
    print(f"Total connections: {stats['total']}")
    print(f"Connections by state: {stats['by_state']}")
    if cleanup_count > 0:
        print(f"Cleaned up: {cleanup_count} old connections")
    print(f"Status: {'✅ HEALTHY' if stats['total'] <= 30 else '⚠️  NEEDS ATTENTION'}")